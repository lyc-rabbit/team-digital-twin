"""新人地图编排：入职指南、培养任务、能力证据、待我介入。"""

import threading
import uuid
from copy import deepcopy
from datetime import datetime, timedelta

from database import get_all_members, get_member, get_ai_native_role, get_ai_native_roles, get_ai_role_assignments

from . import repository as repo
from . import analyzer
from .eligibility import max_completed_level
from .templates import (
    STAGES, STAGE_ORDER, LEVELS, LEVEL_LABELS, CAPABILITIES, ROLE_CAPABILITIES,
    LEVEL_TO_STAGE, default_l0_task, level_index, template_guide,
)


_lock = threading.Lock()
_tasks = {}


def _task_key(kind, newcomer_id):
    return f"{kind}:{newcomer_id}"


def get_analysis_status(kind=None, newcomer_id=None):
    with _lock:
        if kind and newcomer_id:
            return deepcopy(_tasks.get(_task_key(kind, newcomer_id)) or {
                "status": "idle", "progress": 0, "message": "",
            })
        return {k: deepcopy(v) for k, v in _tasks.items()}


def _set_task(kind, newcomer_id, **kwargs):
    key = _task_key(kind, newcomer_id)
    with _lock:
        cur = _tasks.setdefault(key, {
            "task_id": None, "task_type": kind, "status": "idle",
            "progress": 0, "message": "", "newcomer_id": newcomer_id,
        })
        cur.update(kwargs)
        return deepcopy(cur)


def _days_since(entry_date):
    try:
        d = datetime.strptime((entry_date or "")[:10], "%Y-%m-%d")
        return max(0, (datetime.now() - d).days)
    except ValueError:
        return 0


def _capability_scores(employee_id, target_role_id=None):
    keys = ROLE_CAPABILITIES.get(target_role_id) or list(CAPABILITIES.keys())
    evidence = repo.list_evidence(employee_id)
    by_cap = {}
    for e in evidence:
        cid = e.get("capability_id")
        by_cap.setdefault(cid, []).append(float(e.get("score") or 0))
    scores = []
    for cid in keys:
        vals = by_cap.get(cid) or []
        score = round(sum(vals) / len(vals), 1) if vals else 0
        scores.append({
            "id": cid,
            "name": CAPABILITIES.get(cid, cid),
            "score": score,
        })
    return scores


def _match_score(employee_id, role_id):
    if not role_id:
        return None
    assigns = get_ai_role_assignments(role_id)
    mine = next((a for a in assigns if a["employee_id"] == employee_id), None)
    return round(float(mine["match_score"])) if mine else None


def _growth_match(employee_id, role_id, cap_scores):
    base = _match_score(employee_id, role_id)
    if cap_scores:
        avg = sum(c["score"] for c in cap_scores) / len(cap_scores)
    else:
        avg = 0
    if base is None:
        return round(avg)
    return round(0.6 * base + 0.4 * avg)


def _current_task(tasks):
    running = [t for t in tasks if t.get("status") in ("in_progress", "blocked")]
    if running:
        return running[0]
    todos = [t for t in tasks if t.get("status") == "todo"]
    return todos[0] if todos else None


def _progress(nc, tasks):
    if not tasks:
        return 8 if nc.get("onboarding_stage") != "onboarding" else 4
    done = len([t for t in tasks if t.get("status") == "completed"])
    return min(100, round((done / max(1, len(tasks))) * 100))


def refresh_interventions(newcomer_id):
    nc = repo.get_newcomer(newcomer_id)
    if not nc:
        return []
    tasks = repo.list_tasks(newcomer_id)
    repo.close_open_interventions(newcomer_id)
    member = get_member(nc["employee_id"]) or {}
    name = member.get("name") or nc["employee_id"]
    now = datetime.now()

    for t in tasks:
        if t.get("help_requested") and t.get("status") != "completed":
            repo.insert_intervention(
                newcomer_id, "required",
                f"{name} 主动请求帮助：{t['task_name']}",
                "尽快沟通一次，确认卡点",
            )
        if t.get("status") == "blocked":
            repo.insert_intervention(
                newcomer_id, "required",
                f"{name} 任务阻塞：{t['task_name']}" + (f"（{t.get('blocked_reason')}）" if t.get("blocked_reason") else ""),
                "查看一次并协助解阻",
            )
        if t.get("status") == "in_progress" and t.get("started_at"):
            try:
                started = datetime.fromisoformat(t["started_at"])
            except ValueError:
                started = now
            hours = (now - started).total_seconds() / 3600
            est = float(t.get("estimated_hours") or 4)
            if hours >= est + 4:
                repo.insert_intervention(
                    newcomer_id, "required",
                    f"{name} 第一任务卡住约 {int(hours)} 小时" if t.get("task_level") == "L1"
                    else f"{name} 任务超时：{t['task_name']}",
                    "查看一次",
                )
        if t.get("status") == "in_progress" and t.get("review_required") and t.get("task_level") in ("L1", "L2"):
            if t.get("task_name") and "PR" in t["task_name"].upper():
                repo.insert_intervention(
                    newcomer_id, "attention",
                    f"{name} 第一次独立 PR",
                    "进行 Code Review",
                )

    completed_levels = [level_index(t.get("task_level")) for t in tasks if t.get("status") == "completed"]
    if completed_levels and max(completed_levels) >= 1:
        last = sorted(
            [t for t in tasks if t.get("status") == "completed"],
            key=lambda x: x.get("completed_at") or "",
        )
        if last:
            latest = last[-1]
            try:
                done_at = datetime.fromisoformat(latest["completed_at"]) if latest.get("completed_at") else None
            except ValueError:
                done_at = None
            if done_at and (now - done_at) < timedelta(hours=24) and latest.get("task_level") in ("L2", "L3", "L4"):
                repo.insert_intervention(
                    newcomer_id, "attention",
                    f"{name} 完成阶段目标（{latest['task_level']}）",
                    "可以扩大权限或布置下一任务",
                )
    return repo.list_open_interventions(newcomer_id)


def _card(nc):
    member = get_member(nc["employee_id"]) or {}
    role = get_ai_native_role(nc.get("target_role_id")) if nc.get("target_role_id") else None
    tasks = repo.list_tasks(nc["id"])
    current = _current_task(tasks)
    interventions = repo.list_open_interventions(nc["id"])
    if any(i["level"] == "required" for i in interventions):
        level = "required"
    elif any(i["level"] == "attention" for i in interventions):
        level = "attention"
    else:
        level = "none"
    stage = next((s for s in STAGES if s["id"] == nc.get("onboarding_stage")), STAGES[0])
    next_action = None
    if current:
        next_action = f"推进：{current['task_name']}"
    elif nc.get("onboarding_stage") == "onboarding":
        next_action = "发布入职指南并开始项目熟悉"
    else:
        next_action = "生成下一培养任务"
    return {
        "id": nc["id"],
        "employee_id": nc["employee_id"],
        "employee_name": member.get("name") or nc["employee_id"],
        "current_job": member.get("role") or nc.get("current_role") or "",
        "entry_date": nc.get("entry_date"),
        "days": _days_since(nc.get("entry_date")),
        "current_role": nc.get("current_role") or member.get("role") or "",
        "target_role": (role or {}).get("role_name"),
        "target_role_id": nc.get("target_role_id"),
        "onboarding_stage": nc.get("onboarding_stage"),
        "onboarding_stage_label": stage["label"],
        "current_task": current,
        "progress": _progress(nc, tasks),
        "intervention_level": level,
        "next_action": next_action,
        "compete_in_ranking": nc.get("compete_in_ranking"),
        "status": nc.get("status"),
    }


def list_overview():
    cards = [_card(n) for n in repo.list_newcomers()]
    need = [c for c in cards if c["intervention_level"] in ("required", "attention")]
    return {
        "summary": {
            "newcomer_count": len(cards),
            "need_intervention": len(need),
            "on_track": len(cards) - len(need),
        },
        "newcomers": cards,
        "stages": STAGES,
        "levels": [{"id": k, "label": v} for k, v in LEVEL_LABELS.items()],
        "roles": [
            {"id": r["id"], "role_name": r["role_name"]}
            for r in get_ai_native_roles()
        ],
        "projects": repo.list_known_projects(),
        "members": get_all_members(),
    }


def get_detail(employee_id):
    nc = repo.get_newcomer_by_employee(employee_id) or repo.get_newcomer(employee_id)
    if not nc:
        return None
    refresh_interventions(nc["id"])
    member = get_member(nc["employee_id"])
    if not member:
        return None
    role = get_ai_native_role(nc.get("target_role_id")) if nc.get("target_role_id") else None
    tasks = repo.list_tasks(nc["id"])
    caps = _capability_scores(nc["employee_id"], nc.get("target_role_id"))
    match = _growth_match(nc["employee_id"], nc.get("target_role_id"), caps)
    gaps = [c["name"] for c in caps if c["score"] < 60]
    guide = repo.get_guide(nc["id"])
    stage_id = nc.get("onboarding_stage") or "onboarding"
    stages = []
    reached = False
    for s in STAGES:
        if s["id"] == stage_id:
            state = "current"
            reached = True
        elif not reached:
            state = "done"
        else:
            state = "todo"
        stages.append({**s, "state": state})
    current = _current_task(tasks)
    analysis = get_analysis_status()
    return {
        "newcomer": {**nc, **_card(nc)},
        "member": member,
        "target_role": role,
        "stages": stages,
        "tasks": tasks,
        "current_task": current,
        "capabilities": caps,
        "match_score": match,
        "gaps": gaps,
        "evidence": repo.list_evidence(nc["employee_id"]),
        "guide": guide,
        "interventions": repo.list_open_interventions(nc["id"]),
        "analysis": {
            "guide": analysis.get(_task_key("guide", nc["id"])),
            "recommend": analysis.get(_task_key("recommend", nc["id"])),
        },
        "suggested_next": (
            f"完成{current['task_name']}" if current
            else "生成下一培养任务"
        ),
    }


def create_newcomer(payload):
    employee_id = (payload.get("employee_id") or "").strip()
    member = get_member(employee_id)
    if not member:
        raise ValueError("成员不存在")
    if repo.get_newcomer_by_employee(employee_id):
        raise ValueError("该成员已在新人地图中")
    entry = (payload.get("entry_date") or datetime.now().strftime("%Y-%m-%d"))[:10]
    nc = repo.create_newcomer({
        "employee_id": employee_id,
        "entry_date": entry,
        "current_role": payload.get("current_role") or member.get("role") or "",
        "current_role_id": payload.get("current_role_id") or "",
        "target_role_id": payload.get("target_role_id") or "developer",
        "compete_in_ranking": bool(payload.get("compete_in_ranking")),
        "onboarding_stage": "onboarding",
    })
    repo.insert_task(nc["id"], {**default_l0_task(), "status": "todo"}, sort_order=1)
    team = [m["name"] for m in get_all_members()]
    projects = [p["name"] for p in repo.list_known_projects()]
    role = get_ai_native_role(nc.get("target_role_id"))
    tech = list((role or {}).get("required_skills") or [])
    repo.upsert_guide(
        nc["id"],
        template_guide(member, team, projects, (role or {}).get("role_name"), tech),
        source="template",
        status="draft",
    )
    refresh_interventions(nc["id"])
    return get_detail(employee_id)


def set_target_role(employee_id, target_role_id, compete_in_ranking=None):
    nc = repo.get_newcomer_by_employee(employee_id) or repo.get_newcomer(employee_id)
    if not nc:
        return None
    if target_role_id and not get_ai_native_role(target_role_id):
        raise ValueError("目标角色不存在")
    fields = {"target_role_id": target_role_id}
    if compete_in_ranking is not None:
        fields["compete_in_ranking"] = bool(compete_in_ranking)
    repo.update_newcomer(nc["id"], **fields)
    return get_detail(nc["employee_id"])


def get_guide(employee_id):
    nc = repo.get_newcomer_by_employee(employee_id) or repo.get_newcomer(employee_id)
    if not nc:
        return None
    return repo.get_guide(nc["id"])


def save_guide(employee_id, content, status=None):
    nc = repo.get_newcomer_by_employee(employee_id) or repo.get_newcomer(employee_id)
    if not nc:
        return None
    cur = repo.get_guide(nc["id"]) or {}
    return repo.upsert_guide(
        nc["id"],
        content or (cur.get("content") or {}),
        source="edited",
        status=status or cur.get("status") or "draft",
    )


def publish_guide(employee_id):
    nc = repo.get_newcomer_by_employee(employee_id) or repo.get_newcomer(employee_id)
    if not nc:
        return None
    guide = repo.get_guide(nc["id"])
    if not guide:
        raise ValueError("尚未生成入职指南")
    repo.upsert_guide(nc["id"], guide["content"], source=guide.get("source") or "edited", status="published")
    if nc.get("onboarding_stage") == "onboarding":
        repo.update_newcomer(nc["id"], onboarding_stage="project_familiarization")
        tasks = repo.list_tasks(nc["id"])
        l0 = next((t for t in tasks if t.get("task_level") == "L0" and t.get("status") == "todo"), None)
        if l0:
            repo.update_task(l0["id"], status="in_progress", started_at=datetime.now().isoformat(timespec="seconds"))
    return get_detail(nc["employee_id"])


def start_generate_guide(employee_id):
    nc = repo.get_newcomer_by_employee(employee_id) or repo.get_newcomer(employee_id)
    if not nc:
        return None
    st = get_analysis_status("guide", nc["id"])
    if st.get("status") == "running":
        return {**st, "message": "已有入职指南生成任务正在执行"}
    task_id = f"task_{uuid.uuid4().hex[:12]}"
    _set_task("guide", nc["id"], task_id=task_id, status="running", progress=5,
              message="正在生成入职指南", task_type="newcomer_analysis")
    threading.Thread(target=_run_generate_guide, args=(nc["id"],), daemon=True).start()
    return get_analysis_status("guide", nc["id"])


def _run_generate_guide(newcomer_id):
    try:
        _set_task("guide", newcomer_id, progress=20, message="收集团队与项目信息")
        nc = repo.get_newcomer(newcomer_id)
        member = get_member(nc["employee_id"])
        role = get_ai_native_role(nc.get("target_role_id")) if nc.get("target_role_id") else None
        team = [m["name"] for m in get_all_members()]
        projects = [p["name"] for p in repo.list_known_projects()]
        tech = list((role or {}).get("required_skills") or [])
        _set_task("guide", newcomer_id, progress=55, message="请求模型生成指南")
        content = analyzer.generate_guide(member, team, projects, (role or {}).get("role_name"), tech)
        repo.upsert_guide(newcomer_id, content, source=content.get("source") or "ai", status="draft")
        _set_task("guide", newcomer_id, status="success", progress=100, message="入职指南已生成（草稿）")
    except Exception as e:
        _set_task("guide", newcomer_id, status="failed", message=str(e), error_message=str(e))


def start_recommend_tasks(employee_id):
    nc = repo.get_newcomer_by_employee(employee_id) or repo.get_newcomer(employee_id)
    if not nc:
        return None
    st = get_analysis_status("recommend", nc["id"])
    if st.get("status") == "running":
        return {**st, "message": "已有任务推荐正在执行"}
    _set_task("recommend", nc["id"], task_id=f"task_{uuid.uuid4().hex[:12]}",
              status="running", progress=8, message="分析能力差距", task_type="newcomer_analysis")
    threading.Thread(target=_run_recommend, args=(nc["id"],), daemon=True).start()
    return get_analysis_status("recommend", nc["id"])


def _run_recommend(newcomer_id):
    try:
        nc = repo.get_newcomer(newcomer_id)
        member = get_member(nc["employee_id"])
        role = get_ai_native_role(nc.get("target_role_id")) if nc.get("target_role_id") else None
        caps = _capability_scores(nc["employee_id"], nc.get("target_role_id"))
        gaps = [c["id"] for c in caps if c["score"] < 60]
        current = "L-1"
        lv = max_completed_level(newcomer_id)
        current = LEVELS[lv] if lv >= 0 else "L0"
        evidence = repo.list_evidence(nc["employee_id"])
        summary = "；".join(
            f"{e.get('capability_name')} {e.get('score')}" for e in evidence[:8]
        )
        _set_task("recommend", newcomer_id, progress=50, message="生成推荐任务")
        recs = analyzer.recommend_next_tasks(member, role, gaps, current, summary)
        existing = {(t["task_name"], t["task_level"]) for t in repo.list_tasks(newcomer_id)}
        order = len(repo.list_tasks(newcomer_id)) + 1
        created = 0
        for rec in recs:
            key = (rec["task_name"], rec["task_level"])
            if key in existing:
                continue
            repo.insert_task(newcomer_id, rec, sort_order=order)
            order += 1
            created += 1
        _set_task("recommend", newcomer_id, status="success", progress=100,
                  message=f"已推荐 {created} 个任务")
    except Exception as e:
        _set_task("recommend", newcomer_id, status="failed", message=str(e), error_message=str(e))


def update_task(task_id, payload):
    task = repo.get_task(task_id)
    if not task:
        return None
    fields = {}
    for k in ("status", "blocked_reason", "help_requested", "task_name", "description",
              "estimated_hours", "due_at", "review_required", "ai_allowed", "task_level"):
        if k in payload:
            fields[k] = payload[k]
    if payload.get("status") == "in_progress" and not task.get("started_at"):
        fields["started_at"] = datetime.now().isoformat(timespec="seconds")
    if payload.get("status") == "todo":
        fields["blocked_reason"] = ""
    updated = repo.update_task(task_id, **fields)
    refresh_interventions(task["newcomer_id"])
    nc = repo.get_newcomer(task["newcomer_id"])
    return {"task": updated, "detail": get_detail(nc["employee_id"]) if nc else None}


def complete_task(task_id, note=""):
    task = repo.get_task(task_id)
    if not task:
        return None
    nc = repo.get_newcomer(task["newcomer_id"])
    now = datetime.now().isoformat(timespec="seconds")
    repo.update_task(
        task_id,
        status="completed",
        completed_at=now,
        help_requested=False,
        blocked_reason="",
    )
    caps = task.get("capability_ids") or []
    content = note or f"完成任务「{task['task_name']}」"
    score = 55 + level_index(task.get("task_level")) * 8
    for cid in caps:
        repo.insert_evidence(
            nc["employee_id"], task_id, cid,
            CAPABILITIES.get(cid, cid), content, min(95, score),
        )
    next_stage = LEVEL_TO_STAGE.get(task.get("task_level"))
    if next_stage and next_stage in STAGE_ORDER:
        cur = nc.get("onboarding_stage") if nc.get("onboarding_stage") in STAGE_ORDER else STAGE_ORDER[0]
        task_idx = STAGE_ORDER.index(next_stage)
        cur_idx = STAGE_ORDER.index(cur)
        advance_to = STAGE_ORDER[min(task_idx + 1, len(STAGE_ORDER) - 1)]
        if STAGE_ORDER.index(advance_to) > cur_idx:
            repo.update_newcomer(nc["id"], onboarding_stage=advance_to)
    tasks = repo.list_tasks(nc["id"])
    repo.update_newcomer(nc["id"], progress=_progress(nc, tasks))
    refresh_interventions(nc["id"])
    return get_detail(nc["employee_id"])


def list_interventions():
    items = []
    for card in [_card(n) for n in repo.list_newcomers()]:
        for iv in repo.list_open_interventions(card["id"]):
            items.append({
                **iv,
                "employee_id": card["employee_id"],
                "employee_name": card["employee_name"],
                "days": card["days"],
                "onboarding_stage_label": card["onboarding_stage_label"],
            })
    order = {"required": 0, "attention": 1, "none": 2}
    items.sort(key=lambda x: (order.get(x.get("level"), 9), x.get("created_at") or ""))
    return {
        "items": items,
        "required": len([i for i in items if i.get("level") == "required"]),
        "attention": len([i for i in items if i.get("level") == "attention"]),
        "on_track": list_overview()["summary"]["on_track"],
    }


def resolve_intervention(intervention_id):
    from database import get_db
    now = datetime.now().isoformat(timespec="seconds")
    with get_db() as conn:
        conn.execute(
            """UPDATE newcomer_interventions
               SET status = 'resolved', resolved_at = ? WHERE id = ?""",
            (now, intervention_id),
        )
    return {"status": "resolved"}
