"""从人员孪生 / 角色卡 / OIG / 日报抽取可复用数值特征（不调用 AI）。"""

from database import (
    get_all_members,
    get_ai_native_role,
    get_ai_role_assignments,
    get_ai_role_competitions,
    get_events,
)
from daily_report_service import build_ai_native_report_evidence
from memory_engine import compute_relationship_grid, compute_member_states
from organization_graph.builder import GraphBuilder
from organization_graph.repository.facade import get_store
from organization_graph.algorithms.influence import compute_influence
from organization_graph.ontology.relations import (
    REL_COLLABORATE,
    REL_CONFLICT,
    REL_CONTROL,
    REL_EXECUTION_RESPONSIBILITY,
    REL_MANAGEMENT_RESPONSIBILITY,
    REL_MENTOR,
    REL_PERFORMED_TRAINING,
    REL_TRUST,
)


def collect_context(target_role_id=None, date_from=None, date_to=None):
    GraphBuilder().ensure_built()
    members = get_all_members()
    store = get_store()
    nodes = store.list_nodes()
    edges = store.list_edges()
    from timeutil import today, intervals_overlap, parse_day
    date_to = parse_day(date_to) or today()
    date_from = parse_day(date_from) or f"{date_to[:4]}-01-01"
    windowed = []
    for e in edges:
        props = e.get("properties") or {}
        vf, vt = props.get("valid_from"), props.get("valid_to")
        if not vf and not vt:
            windowed.append(e)
        elif intervals_overlap(vf, vt, date_from, date_to):
            windowed.append(e)
    influence = compute_influence(nodes, windowed)
    role = get_ai_native_role(target_role_id) if target_role_id else None
    return {
        "members": members,
        "role": role,
        "assignments": get_ai_role_assignments(target_role_id) if target_role_id else get_ai_role_assignments(),
        "competitions": get_ai_role_competitions(target_role_id) if target_role_id else [],
        "grid": compute_relationship_grid(include_hypothetical=False),
        "states": compute_member_states(include_hypothetical=False),
        "evidence": build_ai_native_report_evidence(days=30),
        "events": get_events(include_hypothetical=False)[-40:],
        "influence": influence,
        "edges": windowed,
        "nodes": {n["id"]: n for n in nodes},
        "window": {"from": date_from, "to": date_to},
    }


def extract_features(member, ctx) -> dict:
    mid = member["id"]
    inf = (ctx.get("influence") or {}).get(mid) or {}
    ev = (ctx.get("evidence") or {}).get(mid) or {}
    state = (ctx.get("states") or {}).get(mid) or {}
    role = ctx.get("role") or {}
    node = (ctx.get("nodes") or {}).get(mid) or {}

    trust_in, trust_n = 0.0, 0
    mentor_out = 0
    conflict_n, conflict_impact = 0, 0.0
    collab = 0
    resource = 0.0
    exec_n = 0
    mgmt_n = 0
    train_n = 0
    for e in ctx.get("edges") or []:
        props = e.get("properties") or {}
        rel = e.get("relation")
        src, tgt = e.get("source"), e.get("target")
        if rel == REL_TRUST and tgt == mid:
            trust_in += float(props.get("score") or props.get("strength") or 0)
            trust_n += 1
        if rel == REL_MENTOR and src == mid:
            mentor_out += 1
        if rel == REL_PERFORMED_TRAINING and src == mid:
            train_n += 1
        if rel == REL_CONFLICT and mid in (src, tgt):
            conflict_n += 1
            conflict_impact += float(props.get("impact") or 50)
        if rel == REL_COLLABORATE and mid in (src, tgt):
            collab += 1
        if rel == REL_CONTROL and src == mid:
            resource = max(resource, float(props.get("resource_value") or 60))
        if rel == "CONTROL_KEY_RESOURCE" and src == mid:
            resource = max(resource, 78)
        if rel == REL_EXECUTION_RESPONSIBILITY and src == mid:
            exec_n += 1
        if rel == REL_MANAGEMENT_RESPONSIBILITY and src == mid:
            mgmt_n += 1

    try:
        from knowledge_governance.semantic_domains import contribution_counts
        cc = contribution_counts(mid, ctx.get("edges") or [], list((ctx.get("nodes") or {}).values()))
        tech_n = cc.get("technical", 0) + cc.get("architecture", 0)
        report_n = cc.get("reporting", 0) + cc.get("reporting_resp", 0)
        exec_n = max(exec_n, cc.get("execution_resp", 0))
        mgmt_n = max(mgmt_n, cc.get("management_resp", 0))
        train_n = max(train_n, cc.get("training_actions", 0))
    except Exception:
        tech_n, report_n = 0, 0

    trust = (trust_in / trust_n * 100) if trust_n else 50
    conflict_risk = min(95, 12 + conflict_n * 14 + (conflict_impact / max(conflict_n, 1)) * 0.2) if conflict_n else 10
    influence_score = float(inf.get("influence_score") or node.get("influence_score") or 40)
    connections = int(inf.get("connections") or 0)
    betweenness = float(inf.get("betweenness") or 0) * 100

    days = int(ev.get("days") or 0)
    impact = float(ev.get("impact") or 0)
    delivery = min(95, 32 + days * 3 + min(25, impact / 4) + exec_n * 4 + tech_n * 3)
    professional = min(95, 38 + len(ev.get("skills") or {}) * 4 + len(node.get("skills") or []) * 2 + tech_n * 5)

    required = [s.lower() for s in (role.get("required_skills") or [])]
    person_skills = [s.lower() for s in (ev.get("skills") or {}).keys()] + [
        s.lower() for s in (node.get("skills") or [])
    ]
    blob = " ".join([
        member.get("role") or "",
        member.get("persona") or "",
        member.get("decision_style") or "",
        " ".join(person_skills),
    ]).lower()
    skill_hits = sum(1 for s in required if s and (s.lower() in blob or any(s.lower() in p for p in person_skills)))
    role_skill = min(95, 20 + skill_hits * (70 / max(len(required), 1))) if required else 50

    assign = next((a for a in (ctx.get("assignments") or []) if a.get("employee_id") == mid
                   and (not role or a.get("role_id") == role.get("id"))), None)
    if not assign:
        assign = next((a for a in (ctx.get("assignments") or []) if a.get("employee_id") == mid), None)
    role_assignment = float((assign or {}).get("match_score") or 0)
    comps = [c for c in (ctx.get("competitions") or []) if c.get("employee_id") == mid]
    role_coverage = 70 if comps else (55 if assign else 35)

    # 战略 / 管理：人设 + 角色词
    text = blob
    strategy = 45
    for kw, add in (("战略", 18), ("目标", 8), ("对齐", 8), ("决策", 10), ("方向", 8)):
        if kw in text:
            strategy = min(92, strategy + add)
    management = 40 + mgmt_n * 10 + report_n * 2
    management = min(92, management + (6 if "管理" in text else 0))

    coordination = min(95, 30 + connections * 8 + collab * 3 + betweenness * 0.4)
    risk_control = max(15, min(95, 88 - conflict_risk * 0.7 + (10 if "风险" in text else 0)))
    fairness = min(95, trust * 0.7 + 20)
    protection = max(20, min(95, 90 - conflict_risk * 0.6))
    communication = min(95, 40 + collab * 4 + (12 if "沟通" in text or "协同" in text else 0) + report_n * 3)
    intensity = float(state.get("intensity") or 3)
    stability = max(25, min(95, 95 - (intensity - 3) * 10))
    expertise = professional
    mentoring = min(95, 35 + train_n * 15 + mentor_out * 8)
    try:
        from growth.repository import list_capability_evidence
        from growth.cadre import promotion_assessment
        caps = list_capability_evidence(mid)
        if any((c.get("capability_id") or "") == "problem_definition" for c in caps):
            communication = min(95, communication + 8)
        if any((c.get("capability_id") or "") == "mentoring" for c in caps):
            mentoring = min(95, mentoring + 10)
        assess = promotion_assessment(mid) or {}
        if assess.get("management_ability") == "已验证":
            management = min(95, management + 8)
    except Exception:
        pass

    innovation = 42
    for kw in ("创新", "探索", "Agent", "架构", "突破", "从0"):
        if kw.lower() in text:
            innovation = min(90, innovation + 10)
    business = 40
    for kw in ("业务", "客户", "价值", "产品"):
        if kw in text:
            business = min(90, business + 12)
    execution = min(95, delivery * 0.7 + days * 1.5)
    risk_taking = min(90, 40 + (20 if "突破" in text or "创业" in text else 0) + (delivery - 50) * 0.3)

    # 趋势：近 30 天投入越多、影响越大 → 上升
    trend = min(85, 45 + min(25, days) + min(15, impact / 8))
    if days == 0:
        trend = 42

    return {
        "strategy_alignment": _clip(strategy),
        "delivery": _clip(delivery),
        "management_potential": _clip(management),
        "coordination": _clip(coordination),
        "risk_control": _clip(risk_control),
        "professional": _clip(professional),
        "fairness": _clip(fairness),
        "mentoring": _clip(mentoring),
        "protection": _clip(protection),
        "communication": _clip(communication),
        "expertise": _clip(expertise),
        "stability": _clip(stability),
        "role_skill_match": _clip(role_skill),
        "role_assignment": _clip(role_assignment if role_assignment else role_skill * 0.7),
        "role_coverage": _clip(role_coverage),
        "innovation": _clip(innovation),
        "business": _clip(business),
        "execution": _clip(execution),
        "risk_taking": _clip(risk_taking),
        "influence": _clip(influence_score),
        "conflict_risk": _clip(conflict_risk),
        "trust": _clip(trust),
        "trend": _clip(trend),
        "resource_control": _clip(resource or 20),
    }


def _clip(v):
    try:
        return round(max(0, min(100, float(v))), 2)
    except (TypeError, ValueError):
        return 50.0
