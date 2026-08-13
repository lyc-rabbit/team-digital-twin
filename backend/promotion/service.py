"""晋升推演编排：先特征+打分，再 AI 事实；改权重只重算。"""

import threading
import time
import uuid
from copy import deepcopy

from database import get_all_members, get_ai_native_role

from .repository import get_promo_store
from .templates import (
    LAYER_DEFAULTS, LAYER_LABELS, BOSS_WEIGHTS, BOSS_LABELS,
    TEAM_WEIGHTS, TEAM_LABELS, get_style,
)
from .features import collect_context, extract_features
from .engine import compute_layer_scores, rank_candidates
from .analyzer import analyze_candidates


# 各阶段经验耗时（秒），用于 ETA
PHASE_EXPECTED = {
    "start": 3,
    "context": 12,
    "score": 4,
    "ai": 75,
}

_lock = threading.Lock()
_tasks = {}  # sim_id -> live status
_cancels = {}  # sim_id -> Event


def _cancel_event(sim_id):
    with _lock:
        ev = _cancels.get(sim_id)
        if ev is None:
            ev = threading.Event()
            _cancels[sim_id] = ev
        return ev


def _is_cancelled(sim_id):
    return _cancel_event(sim_id).is_set()


def _task(sim_id, **kwargs):
    now = time.time()
    with _lock:
        cur = _tasks.setdefault(sim_id, {
            "status": "idle",
            "progress": 0,
            "message": "",
            "phase": "start",
            "started_at": now,
            "phase_started_at": now,
        })
        if "phase" in kwargs and kwargs["phase"] != cur.get("phase"):
            kwargs["phase_started_at"] = now
        cur.update(kwargs)
        return deepcopy(cur)


def _eta_fields(live):
    if not live or live.get("status") != "running":
        return {
            "phase": live.get("phase") if live else None,
            "elapsed_seconds": 0,
            "eta_seconds": 0,
            "eta_text": "",
        }
    now = time.time()
    started = live.get("started_at") or now
    phase_started = live.get("phase_started_at") or started
    phase = live.get("phase") or "start"
    expected = PHASE_EXPECTED.get(phase, 30)
    elapsed_total = max(0, now - started)
    elapsed_phase = max(0, now - phase_started)
    remaining = expected - elapsed_phase
    if remaining < 0:
        remaining = min(90, max(15, int(expected * 0.35)))
    remaining = int(max(0, remaining))
    return {
        "phase": phase,
        "elapsed_seconds": int(elapsed_total),
        "eta_seconds": remaining,
        "eta_text": _format_eta(remaining, overtime=elapsed_phase > expected),
    }


def _format_eta(seconds, overtime=False):
    if seconds <= 2 and not overtime:
        return "即将完成"
    if seconds < 60:
        text = f"预计还需约 {seconds} 秒"
    else:
        text = f"预计还需约 {seconds // 60} 分 {seconds % 60} 秒"
    if overtime:
        return f"仍在等待模型，{text}"
    return text


def get_status(sim_id):
    store = get_promo_store()
    sim = store.get_simulation(sim_id)
    if not sim:
        return None
    live = None
    with _lock:
        live = deepcopy(_tasks.get(sim_id))
    if live:
        sim["status"] = live.get("status") or sim["status"]
        sim["progress"] = live.get("progress", sim.get("progress") or 0)
        sim["message"] = live.get("message") or sim.get("message") or ""
        sim.update(_eta_fields(live))
    elif sim.get("status") == "running":
        sim["eta_text"] = "正在计算预计时间…"
        sim["eta_seconds"] = PHASE_EXPECTED["ai"]
        sim["elapsed_seconds"] = 0
    return sim


def create_simulation(payload, creator=""):
    members = get_all_members()
    if not members:
        raise ValueError("团队尚无成员，请先在「成员管理」中添加人员")

    role_id = (payload.get("target_role_id") or "").strip()
    role = get_ai_native_role(role_id) if role_id else None
    style_id = payload.get("style_id") or "tech_expert"
    style_tpl = get_style(style_id)
    style = payload.get("leadership_style") or {
        "id": style_tpl["id"],
        "type": style_tpl["type"],
        "name": style_tpl["name"],
        "description": style_tpl["description"],
        "weights": style_tpl["weights"],
    }
    custom = payload.get("custom_requirements") or [
        {"name": label, "weight": w}
        for label, w in zip(
            (style_tpl.get("labels") or {}).values(),
            (style_tpl.get("weights") or {}).values(),
        )
    ]
    layer = dict(LAYER_DEFAULTS)
    layer.update(payload.get("layer_weights") or {})
    sub = {
        "boss": dict(BOSS_WEIGHTS),
        "team": dict(TEAM_WEIGHTS),
        "style": dict(style.get("weights") or style_tpl["weights"]),
    }
    sub.update(payload.get("sub_weights") or {})

    scope = payload.get("candidate_scope") or ["all"]
    sim_id = f"promo_{uuid.uuid4().hex[:12]}"
    name = (payload.get("name") or "").strip() or (
        f"{(role or {}).get('role_name') or '目标岗位'}晋升分析"
    )

    weight_rows = _weight_rows(layer, sub, custom)
    store = get_promo_store()
    sim = store.create_simulation({
        "id": sim_id,
        "name": name,
        "target_role_id": role_id,
        "target_role_name": (role or {}).get("role_name") or payload.get("target_role_name") or "",
        "department": payload.get("department") or "",
        "candidate_scope": scope,
        "leadership_style": style,
        "custom_requirements": custom,
        "layer_weights": layer,
        "sub_weights": sub,
        "status": "running",
        "progress": 5,
        "message": "任务已启动",
        "creator": creator,
        "weight_rows": weight_rows,
    })
    _cancel_event(sim_id).clear()
    _task(sim_id, status="running", progress=5, message="任务已启动", phase="start")
    thread = threading.Thread(target=_run, args=(sim_id,), daemon=True)
    thread.start()
    return sim


def _run(sim_id):
    store = get_promo_store()
    try:
        if _is_cancelled(sim_id):
            _mark_cancelled(sim_id)
            return
        sim = store.get_simulation(sim_id)
        _task(sim_id, status="running", progress=15, message="读取角色卡、人员孪生与影响力图谱", phase="context")
        store.update_simulation(sim_id, status="running", progress=15, message="读取组织数据")

        ctx = collect_context(sim.get("target_role_id"))
        if _is_cancelled(sim_id):
            _mark_cancelled(sim_id)
            return
        members = _select_members(ctx["members"], sim.get("candidate_scope") or ["all"])
        if not members:
            raise ValueError("候选范围内没有成员")

        _task(sim_id, progress=40, message="计算基础领导 / 团队认可 / 岗位匹配特征", phase="score")
        store.update_simulation(sim_id, progress=40, message="计算特征")

        style = sim.get("leadership_style") or get_style("tech_expert")
        custom = sim.get("custom_requirements") or []
        sub = sim.get("sub_weights") or {}
        features_map = {}
        rows = []
        for m in members:
            if _is_cancelled(sim_id):
                _mark_cancelled(sim_id)
                return
            feat = extract_features(m, ctx)
            features_map[m["id"]] = feat
            layers = compute_layer_scores(feat, sub, style, custom)
            rows.append({
                "person_id": m["id"],
                "feature_scores": feat,
                "layer_scores": layers,
                "analysis_json": {},
            })

        ranked = rank_candidates(rows, sim.get("layer_weights") or LAYER_DEFAULTS)
        store.replace_results(sim_id, ranked)

        if _is_cancelled(sim_id):
            _mark_cancelled(sim_id, "已终止（排名已算出，事实报告未生成）")
            return

        _task(sim_id, progress=65, message="生成 AI 事实分析报告", phase="ai")
        store.update_simulation(sim_id, progress=65, message="AI 分析中")

        box = {}

        def _do_ai():
            try:
                box["ai"] = analyze_candidates({
                    "role": ctx.get("role") or {"role_name": sim.get("target_role_name")},
                    "style": style,
                    "custom_requirements": custom,
                    "members": members,
                    "features": features_map,
                    "evidence": ctx.get("evidence") or {},
                    "events": ctx.get("events") or [],
                })
            except Exception as e:
                box["err"] = e

        worker = threading.Thread(target=_do_ai, daemon=True)
        worker.start()
        while worker.is_alive():
            if _is_cancelled(sim_id):
                print(f"[promotion] 任务 {sim_id} 已请求终止，不再等待 AI 返回")
                _mark_cancelled(sim_id, "已终止（排名已算出，事实报告未生成）")
                return
            worker.join(timeout=0.4)

        if _is_cancelled(sim_id):
            _mark_cancelled(sim_id, "已终止（排名已算出，事实报告未生成）")
            return
        if box.get("err"):
            raise box["err"]
        ai = box.get("ai") or {"candidates": [], "degraded": True}

        by_pid = {c["person_id"]: c for c in (ai.get("candidates") or [])}
        for row in ranked:
            analysis = by_pid.get(row["person_id"]) or {}
            row["analysis_json"] = analysis
        ranked = rank_candidates(ranked, sim.get("layer_weights") or LAYER_DEFAULTS)
        if _is_cancelled(sim_id):
            _mark_cancelled(sim_id, "已终止（排名已算出，事实报告未生成）")
            return
        store.replace_results(sim_id, ranked)

        msg = "推演完成"
        if ai.get("degraded") or ai.get("mock_mode"):
            msg = "推演完成（规则引擎/降级模式，排名仍基于组织数据）"
        if _is_cancelled(sim_id):
            _mark_cancelled(sim_id, "已终止")
            return
        store.update_simulation(
            sim_id,
            status="ready",
            progress=100,
            message=msg,
            mock_mode=1 if (ai.get("mock_mode") or ai.get("degraded")) else 0,
            error="",
        )
        _task(sim_id, status="ready", progress=100, message=msg, phase="done")
    except Exception as e:
        if _is_cancelled(sim_id):
            _mark_cancelled(sim_id)
            return
        store.update_simulation(
            sim_id, status="failed", progress=100,
            message=str(e), error=str(e),
        )
        _task(sim_id, status="failed", progress=100, message=str(e))


def _mark_cancelled(sim_id, message="已终止"):
    store = get_promo_store()
    store.update_simulation(
        sim_id, status="cancelled", progress=100, message=message, error="",
    )
    _task(sim_id, status="cancelled", progress=100, message=message, phase="done")


def cancel_simulation(sim_id):
    store = get_promo_store()
    sim = store.get_simulation(sim_id)
    if not sim:
        return None
    with _lock:
        live_status = (_tasks.get(sim_id) or {}).get("status")
    status = live_status or sim.get("status")
    if status != "running":
        return get_status(sim_id)
    print(f"[promotion] 收到终止请求 sim_id={sim_id}")
    _cancel_event(sim_id).set()
    _mark_cancelled(sim_id, "已终止")
    return get_status(sim_id)


def _select_members(members, scope):
    if not scope or scope == ["all"] or "全部成员" in scope or "all" in scope:
        return members
    wanted = set(scope)
    return [m for m in members if m["id"] in wanted or m.get("name") in wanted]


def _weight_rows(layer, sub, custom):
    rows = []
    for k, w in layer.items():
        rows.append({
            "dimension": k, "weight": w, "source": "layer",
            "label": LAYER_LABELS.get(k, k),
        })
    for k, w in (sub.get("boss") or BOSS_WEIGHTS).items():
        rows.append({"dimension": k, "weight": w, "source": "boss", "label": BOSS_LABELS.get(k, k)})
    for k, w in (sub.get("team") or TEAM_WEIGHTS).items():
        rows.append({"dimension": k, "weight": w, "source": "team", "label": TEAM_LABELS.get(k, k)})
    for req in custom or []:
        rows.append({
            "dimension": req.get("name") or "",
            "weight": req.get("weight") or 0,
            "source": "custom",
            "label": req.get("name") or "",
        })
    return rows


def list_simulations():
    store = get_promo_store()
    items = store.list_simulations()
    for s in items:
        live = get_status(s["id"])
        if live:
            s["status"] = live.get("status")
            s["progress"] = live.get("progress")
            s["message"] = live.get("message")
            s["eta_text"] = live.get("eta_text")
            s["eta_seconds"] = live.get("eta_seconds")
        results = store.list_results(s["id"])
        s["candidate_count"] = len(results)
        top = results[0] if results else None
        s["top"] = None
        if top:
            member = next((m for m in get_all_members() if m["id"] == top["person_id"]), None)
            s["top"] = {
                "person_id": top["person_id"],
                "name": (member or {}).get("name") or top["person_id"],
                "score": top.get("score"),
                "promotion_probability": top.get("promotion_probability"),
            }
    return items


def get_simulation_detail(sim_id):
    store = get_promo_store()
    sim = get_status(sim_id)
    if not sim:
        return None
    members = {m["id"]: m for m in get_all_members()}
    results = []
    for r in store.list_results(sim_id):
        m = members.get(r["person_id"]) or {}
        analysis = r.get("analysis_json") or {}
        results.append({
            **r,
            "name": m.get("name") or r["person_id"],
            "role": m.get("role") or "",
            "person": analysis.get("person") or m.get("name") or r["person_id"],
        })
    return {
        "simulation": sim,
        "weights": store.list_weights(sim_id),
        "results": results,
        "model": {
            "layer_weights": sim.get("layer_weights") or LAYER_DEFAULTS,
            "layer_labels": LAYER_LABELS,
            "leadership_style": sim.get("leadership_style") or {},
            "custom_requirements": sim.get("custom_requirements") or [],
        },
    }


def update_weights(sim_id, layer_weights=None, custom_requirements=None, sub_weights=None):
    """改权重后只重算分数与排名，不重新调用 AI。"""
    store = get_promo_store()
    sim = store.get_simulation(sim_id)
    if not sim:
        return None
    if sim.get("status") not in ("ready", "failed", "cancelled"):
        raise ValueError("分析尚未完成，请稍后再调整权重")

    layer = dict(sim.get("layer_weights") or LAYER_DEFAULTS)
    if layer_weights:
        layer.update(layer_weights)
    total = sum(float(layer.get(k) or 0) for k in ("boss", "team", "role", "custom")) or 100.0
    layer = {k: round(float(layer.get(k) or 0) / total * 100, 1) for k in ("boss", "team", "role", "custom")}
    custom = custom_requirements if custom_requirements is not None else sim.get("custom_requirements")
    sub = dict(sim.get("sub_weights") or {})
    if sub_weights:
        sub.update(sub_weights)

    rows = store.list_results(sim_id)
    rebuilt = []
    style = sim.get("leadership_style") or get_style("tech_expert")
    for r in rows:
        feat = r.get("feature_scores") or {}
        layers = compute_layer_scores(feat, sub, style, custom or [])
        rebuilt.append({
            "person_id": r["person_id"],
            "feature_scores": feat,
            "layer_scores": layers,
            "analysis_json": r.get("analysis_json") or {},
        })
    ranked = rank_candidates(rebuilt, layer)
    store.replace_results(sim_id, ranked)
    store.update_simulation(
        sim_id,
        layer_weights=layer,
        custom_requirements=custom,
        sub_weights=sub,
        message="已按新权重重算排名（未重新调用 AI）",
    )
    store.replace_weight_config(sim_id, _weight_rows(layer, sub, custom or []))
    return get_simulation_detail(sim_id)


def delete_simulation(sim_id):
    store = get_promo_store()
    if not store.get_simulation(sim_id):
        return False
    _cancel_event(sim_id).set()
    store.delete_simulation(sim_id)
    with _lock:
        _tasks.pop(sim_id, None)
        _cancels.pop(sim_id, None)
    return True
