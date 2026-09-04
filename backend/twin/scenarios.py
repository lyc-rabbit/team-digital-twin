"""P2-24 / P2-30 管理推演入口：规则算出结果，再可选让 LLM 写摘要。"""

from llm_client import get_client, is_mock_mode, _get_env, _log_llm_failure

from .common import cite, judgment
from . import snapshot as snap
from . import growth as growth_mod
from . import mentoring
from . import training
from . import org
from . import social
from . import leadership
from . import repository as repo

SCENARIOS = [
    {"id": "mentor_people", "label": "我要带新人", "hint": "选择管理者和被带的人，模拟跨度、依赖和培养压力。"},
    {"id": "own_project", "label": "我要负责项目", "hint": "模拟完整项目责任对负荷、授权和交付风险的影响。"},
    {"id": "promotion", "label": "我要晋升管理岗位", "hint": "准备度、缺口和预计达到观察线的时间。"},
    {"id": "expand", "label": "团队扩大", "hint": "部门加人后的跨度、导师需求和瓶颈。"},
    {"id": "departure", "label": "人员调岗 / 离开", "hint": "核心成员离开后的项目、新人与知识单点。"},
    {"id": "custom", "label": "自定义场景", "hint": "用一句话描述「如果……会怎样」。"},
]


def bootstrap():
    team = snap.team_snapshot()
    return {
        "scenarios": SCENARIOS,
        "members": [
            {"id": p["person_id"], "name": p["name"], "role": p["role"], "person_type": p["person_type"], "readiness": p["readiness"]}
            for p in team["people"]
        ],
        "newcomers": [
            {"id": n.get("employee_id") or n.get("id"), "newcomer_id": n.get("id"), "employee_id": n.get("employee_id")}
            for n in team.get("newcomers") or []
        ],
        "projects": team.get("open_projects") or [],
        "pipeline": org.pipeline(),
        "recent": repo.list_simulations(12),
    }


def run(payload):
    payload = payload or {}
    question = payload.get("question") or payload.get("custom") or ""
    sid = payload.get("scenario")
    if not sid or sid == "custom":
        sid = _infer_scenario(question) if question else (sid or "custom")
    handler = {
        "mentor_people": _scene_mentor,
        "own_project": _scene_project,
        "promotion": _scene_promotion,
        "expand": _scene_expand,
        "departure": _scene_departure,
        "custom": _scene_custom,
        "match": _scene_match,
        "training": _scene_training,
        "structure": _scene_structure,
        "conflict": _scene_conflict,
        "auth": _scene_auth,
        "cohort": _scene_cohort,
    }.get(sid, _scene_custom)
    result = handler(payload)
    result["scenario"] = sid
    result["scenario_label"] = next((s["label"] for s in SCENARIOS if s["id"] == sid), sid)
    result["engine"] = "rules"
    result["llm_role"] = "explanation_only"
    result["narrative"] = _narrate(result)
    title = result.get("title") or result.get("scenario_label") or sid
    result["simulation_id"] = repo.save_simulation(sid, title, payload, result)
    return result


def _infer_scenario(text):
    t = text or ""
    if any(k in t for k in ("离开", "休假", "调岗", "离职")):
        return "departure"
    if any(k in t for k in ("扩大", "扩张", "招", "15人", "10个人", "10人")):
        return "expand"
    if any(k in t for k in ("多久", "达到", "L1", "L2", "达标", "准备度")):
        return "promotion"
    if any(k in t for k in ("晋升", "管理岗位")):
        return "promotion"
    if any(k in t for k in ("授权", "完整责任")):
        return "auth"
    if any(k in t for k in ("同时带", "带3", "带三", "带 A", "带A")):
        return "mentor_people"
    if "培养方案" in t or ("培养" in t and "方案" in t):
        return "training"
    if any(k in t for k in ("带新人", "带人", "匹配")):
        return "mentor_people"
    if any(k in t for k in ("项目", "负责")):
        return "own_project"
    return "custom"


def _pack(title, current, change, metrics, risks, recs, judgment_obj, extra=None):
    data = {
        "title": title,
        "current_state": current,
        "simulated_change": change,
        "metrics": metrics or {},
        "impact": metrics or {},
        "risks": risks or [],
        "opportunities": [r for r in (recs or []) if "争取" in r or "提升" in r],
        "recommendations": recs or [],
        "judgment": judgment_obj,
        "is_prediction": True,
    }
    if extra:
        data.update(extra)
    return data


def _scene_mentor(p):
    manager_id = p.get("manager_id") or p.get("person_id")
    ids = p.get("reportee_ids") or p.get("mentee_ids") or []
    if p.get("mentee_id") and p["mentee_id"] not in ids:
        ids.append(p["mentee_id"])
    sim = mentoring.simulate_span(manager_id, ids)
    if not sim:
        raise ValueError("管理者不存在")
    metrics = {
        k: {"value": v["value"], "arrow": "↑↑" if v["level"] == "high" else ("↑" if v["level"] == "medium" else "→"), "level": v["level"]}
        for k, v in sim["metrics"].items()
    }
    risks = [{"title": r["title"], "level": r["level"]} for r in sim["risks"]]
    return _pack(
        f"{sim['manager']['name']}负责{len(sim['reportees'])}人小组",
        {"manager": sim["manager"], "reportees": sim["reportees"]},
        {"span": len(sim["reportees"]), "dependencies": sim["dependencies"]},
        metrics, risks, sim["recommendations"], sim["judgment"], {"detail": sim},
    )


def _scene_match(p):
    m = mentoring.match_mentor(p.get("manager_id") or p.get("mentor_id"), p.get("mentee_id"))
    if not m:
        raise ValueError("成员不存在")
    return _pack(
        f"导师 {m['mentor']['name']} × 新人 {m['mentee']['name']}",
        m, {"match": m["match"], "recommendation": m["recommendation"]},
        {"匹配度": {"value": m["match"], "level": "low" if m["match"] >= 78 else "medium"}},
        [{"title": x, "level": "medium"} for x in m["risks"]],
        [m["recommendation"]] + m["advantages"],
        m["judgment"], {"detail": m},
    )


def _scene_project(p):
    person_id = p.get("person_id") or p.get("manager_id")
    person = snap.person_snapshot(person_id)
    if not person:
        raise ValueError("成员不存在")
    project_id = p.get("project_id")
    auth = leadership.auth_if_own_project(person_id, project_id)
    dep = org.departure(person_id)
    load = clip_load(person)
    recs = [
        "明确该项目的决策边界：哪些可自主，哪些必须请示",
        "重大风险当天同步，作为授权上调前提",
    ]
    if person["dependents"]:
        recs.append("指定第二负责人，避免项目与带人单点重叠")
    metrics = {
        "交付能力": {"value": load["delivery"], "arrow": "↑", "level": "medium"},
        "管理压力": {"value": load["pressure"], "arrow": "↑↑" if load["pressure"] >= 70 else "↑", "level": "high" if load["pressure"] >= 70 else "medium"},
        "组织风险": {"value": (dep or {}).get("org_dependency") or 50, "arrow": "↑", "level": "medium"},
        "授权预期": {"value": 70, "arrow": "↑", "level": "low"},
    }
    return _pack(
        f"{person['name']}承担项目完整责任",
        {"load": person["load"], "auth": auth},
        {"project_id": project_id, "auth_to": (auth or {}).get("auth_to"), "premises": (auth or {}).get("premises")},
        metrics,
        [{"title": x["object"] + " 依赖", "level": x["level"]} for x in ((dep or {}).get("impacts") or [])[:4]],
        recs,
        (auth or {}).get("judgment") or judgment("项目责任情景", "缺少授权档案时仅评估负荷。"),
        {"detail": {"auth": auth, "departure_if_fail": dep}},
    )


def clip_load(person):
    pressure = min(100, 35 + person["load"]["owned_open"] * 18 + person["load"]["project_count"] * 6)
    delivery = min(100, 68 + person["load"]["owned_open"] * 4)
    return {"pressure": pressure, "delivery": delivery}


def _scene_promotion(p):
    person_id = p.get("person_id") or p.get("manager_id")
    days = int(p.get("days") or 90)
    pred = growth_mod.predict_growth(person_id, days)
    if not pred:
        raise ValueError("成员不存在")
    path = leadership.cadre_path(person_id)
    recs = list(pred.get("accelerators") or []) + [path.get("next_practice")] if path else pred.get("accelerators")
    metrics = {
        "管理岗位准备度": {"value": pred["readiness"]["predicted"], "arrow": "↑", "current": pred["readiness"]["current"]},
        "预计天数": {"value": pred.get("days_to_target") or days, "arrow": "→"},
    }
    risks = [{"title": d, "level": "medium"} for d in (pred.get("delays") or [])]
    return _pack(
        f"{pred['name']}晋升管理岗位时间",
        pred["basis"],
        {"timeline": pred["timeline"], "days_to_target": pred.get("days_to_target")},
        metrics, risks, recs, pred["judgment"],
        {"detail": {"growth": pred, "path": path}},
    )


def _scene_expand(p):
    sim = org.expand(p.get("add_newcomers", 10), p.get("add_seniors", 2), p.get("add_managers", 1))
    metrics = {
        "管理跨度风险": {"value": int(sim["span"] * 12), "arrow": "↑↑" if sim["span_risk"] == "high" else "↑", "level": sim["span_risk"]},
        "导师需求": {"value": sim["mentor_needed"], "arrow": "↑"},
        "培养周期周": {"value": 8, "arrow": "→"},
    }
    risks = [{"title": b, "level": "high"} for b in sim["bottlenecks"]]
    return _pack(
        f"部门从{sim['current_size']}人扩大到{sim['future_size']}人",
        {"current_size": sim["current_size"], "pipeline": org.pipeline()["pipeline"]},
        sim,
        metrics, risks, sim["recommendations"], sim["judgment"], {"detail": sim},
    )


def _scene_departure(p):
    person_id = p.get("person_id") or p.get("target_id")
    sim = org.departure(person_id)
    if not sim:
        raise ValueError("成员不存在")
    metrics = {"综合组织依赖": {"value": sim["org_dependency"], "arrow": "↑↑" if sim["org_dependency"] >= 75 else "↑"}}
    risks = [{"title": f"{i['kind']}：{i['object']}", "level": i["level"]} for i in sim["impacts"][:6]]
    return _pack(
        f"如果{sim['name']}离开",
        {"person": sim["name"]},
        {"backups": sim["backups"], "knowledge": sim.get("knowledge")},
        metrics, risks, sim["backups"], sim["judgment"], {"detail": sim},
    )


def _scene_training(p):
    plan = training.generate_plan(
        p.get("person_id") or p.get("mentee_id"),
        p.get("mentor_id") or p.get("manager_id"),
        p.get("role_id") or "developer",
        p.get("from_level") or "L1",
        p.get("to_level") or "L2",
        p.get("days") or 60,
    )
    opt = training.optimize_plan(p.get("person_id") or p.get("mentee_id")) if p.get("person_id") or p.get("mentee_id") else None
    return _pack(
        "培养方案",
        {"from": plan["from_level"], "to": plan["to_level"]},
        plan,
        {"周期天": {"value": plan["days"], "arrow": "→"}},
        [{"title": s["risk"], "level": "medium"} for s in plan["stages"] if s.get("risk")],
        [a["action"] for a in (opt or {}).get("adjustments") or []],
        plan["judgment"],
        {"detail": {"plan": plan, "optimize": opt}},
    )


def _scene_structure(p):
    trees = p.get("trees") or org.default_structures()
    sim = org.compare_structures(trees)
    return _pack("组织结构推演", {"trees": trees}, sim, {}, [], [f"更均衡：{sim.get('recommended')}"], sim["judgment"], {"detail": sim})


def _scene_conflict(p):
    sim = social.predict_conflict(p.get("person_a"), p.get("person_b"))
    if not sim:
        raise ValueError("需要两名成员")
    return _pack(
        f"{sim['person_a']['name']} ↔ {sim['person_b']['name']} 冲突风险预测",
        sim, sim,
        {"冲突风险": {"value": sim["risk"], "level": sim["level"]}},
        [{"title": r, "level": sim["level"]} for r in sim["reasons"]],
        sim["recommendations"], sim["judgment"], {"detail": sim},
    )


def _scene_auth(p):
    sim = leadership.auth_if_own_project(p.get("person_id"), p.get("project_id"))
    if not sim:
        raise ValueError("成员不存在")
    return _pack(
        "向上授权情景",
        {"from": sim["auth_from"]},
        sim,
        {"授权": {"value": 70, "arrow": "↑"}},
        [{"title": x, "level": "medium"} for x in sim["premises"]],
        sim["premises"], sim["judgment"], {"detail": sim},
    )


def _scene_cohort(p):
    sim = training.simulate_cohort(p.get("hire_count") or 10, p.get("mix"))
    return _pack("虚拟新人群体", sim, sim, {"L2达标率": {"value": sim["expected_l2_rate"]}}, [{"title": r, "level": "high"} for r in sim["risks"]], sim.get("suitable_mentors") and ["按导师池分配"] or [], sim["judgment"], {"detail": sim})


def _scene_custom(p):
    q = p.get("question") or p.get("custom") or ""
    inferred = _infer_scenario(q)
    if inferred != "custom":
        p = {**p, "scenario": inferred, "question": q}
        if inferred == "expand":
            p.setdefault("add_newcomers", 10)
        handler = {
            "mentor_people": _scene_mentor,
            "own_project": _scene_project,
            "promotion": _scene_promotion,
            "expand": _scene_expand,
            "departure": _scene_departure,
            "auth": _scene_auth,
            "training": _scene_training,
        }.get(inferred)
        if handler:
            out = handler(p)
            out["inferred_from"] = q
            return out
    person_id = p.get("person_id")
    bits = []
    if person_id:
        bits.append(growth_mod.predict_growth(person_id, 90))
        bits.append(org.departure(person_id))
    team = org.pipeline()
    return _pack(
        q or "自定义情景",
        {"pipeline": team["pipeline"], "question": q},
        {"note": "未能精确匹配预设情景，已返回梯队与（若指定人员）成长/离开影响。"},
        {},
        team.get("issues") and [{"title": x, "level": "medium"} for x in team["issues"]] or [],
        ["请改用带人 / 扩张 / 离开 / 晋升等明确情景以获得完整推演"],
        judgment("自定义问题已尽量映射到规则引擎。", "未识别到明确动词时只给团队梯队，避免 LLM 编造组织结论。", [cite("query", "原问题", q)]),
        {"detail": {"growth": bits[0] if bits else None, "departure": bits[1] if len(bits) > 1 else None, "pipeline": team}},
    )


def _narrate(result):
    """解释层：默认用规则结论。仅当显式开启时才让模型复述，且禁止新增数字。"""
    j = result.get("judgment") or {}
    base = j.get("conclusion") or ""
    if is_mock_mode() or _get_env("TWIN_LLM_NARRATE", "") not in ("1", "true", "TRUE"):
        return base
    try:
        client = get_client()
        if client is None:
            return base
        prompt = (
            "用不超过 120 字复述下面已经算好的推演结论，禁止增加新数字或新事实。\n"
            f"结论：{j.get('conclusion')}\n原因：{j.get('reason')}\n"
            f"建议：{'；'.join(result.get('recommendations') or [])[:200]}"
        )
        resp = client.chat.completions.create(
            model=_get_env("DEEPSEEK_MODEL_EXTRACT", "deepseek-ai/DeepSeek-V3"),
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
            max_tokens=300,
            timeout=12,
        )
        return (resp.choices[0].message.content or "").strip() or base
    except Exception as e:
        _log_llm_failure("twin_narrate", e)
        return base
