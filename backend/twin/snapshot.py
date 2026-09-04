"""把 P0/P1 事实收成可推演的人员/团队数字孪生快照。"""

from collections import defaultdict

from database import get_all_members, get_member
from growth.cadre import build_profile, CAPABILITY_DEFS
from growth.scores import all_evidence, compute_score
from growth import repository as growth_repo
from project_center import repository as pc_repo

from .common import clip, cite, days_ago, in_window, parse_time

STATUS_SCORE = {"已验证": 82, "形成中": 62, "未验证": 42}


def _projects(person_id):
    try:
        return pc_repo.list_projects({"include_archived": True, "member_id": person_id}) or []
    except Exception:
        return []


def _newcomers():
    try:
        from newcomer.repository import list_newcomers
        return list_newcomers("active") or []
    except Exception:
        return []


def _newcomer_of(person_id):
    try:
        from newcomer.repository import get_newcomer_by_employee, list_tasks
        nc = get_newcomer_by_employee(person_id)
        if not nc:
            return None
        tasks = list_tasks(nc["id"])
        done = [t for t in tasks if t.get("status") == "completed"]
        return {**nc, "tasks": tasks, "completed_tasks": done, "task_count": len(tasks)}
    except Exception:
        return None


def _cap_numeric(profile):
    items = []
    for spec in CAPABILITY_DEFS:
        row = next((c for c in (profile.get("capabilities") or []) if c["id"] == spec["id"]), None)
        status = (row or {}).get("status") or "未验证"
        n = int((row or {}).get("evidence_count") or 0)
        base = STATUS_SCORE.get(status, 42)
        current = clip(base + min(12, n * 2))
        items.append({
            "id": spec["id"],
            "label": spec["label"],
            "status": status,
            "current": current,
            "evidence_count": n,
        })
    return items


def _velocity(person_id, days=30):
    """近窗口能力证据净增量 / 天数，作为成长速度。"""
    evidence = growth_repo.list_capability_evidence(person_id)
    since = days_ago(days)
    prev = days_ago(days * 2)
    recent, older = 0.0, 0.0
    for e in evidence:
        t = parse_time(e.get("created_at"))
        score = float(e.get("score") or 0)
        if t and t >= since:
            recent += score
        elif t and t >= prev:
            older += score
    per_day = (recent - older) / max(days, 1) / 8.0
    events = growth_repo.list_events({"member_id": person_id, "limit": 200})
    recent_ev = [e for e in events if in_window(e.get("event_time"), since)]
    event_boost = min(0.25, len(recent_ev) * 0.02)
    stalled = len(recent_ev) == 0
    return {
        "per_day": round(per_day + event_boost, 4),
        "recent_evidence_sum": round(recent, 1),
        "older_evidence_sum": round(older, 1),
        "recent_event_count": len(recent_ev),
        "stalled": stalled,
        "window_days": days,
    }


def classify_person(member, profile, newcomer):
    role = (member.get("role") or "") + (member.get("persona") or "")
    stage = (profile or {}).get("current_stage") or ""
    if newcomer:
        return "新人"
    if "具备晋升" in stage:
        return "管理候选人"
    if "储备干部" in stage:
        return "储备干部"
    if any(k in role for k in ("负责", "经理", "主管", "Leader", "leader")):
        return "高潜人员"
    verified = sum(1 for c in (profile or {}).get("capabilities") or [] if c.get("status") == "已验证")
    if verified >= 3:
        return "高潜人员"
    return "普通成员"


def person_snapshot(person_id):
    member = get_member(person_id)
    if not member:
        return None
    profile = build_profile(person_id) or {}
    nc = _newcomer_of(person_id)
    caps = _cap_numeric(profile)
    vel = _velocity(person_id)
    projects = _projects(person_id)
    owned = [p for p in projects if p.get("owner_id") == person_id]
    open_owned = [p for p in owned if (p.get("status") or "open") not in ("closed", "archived")]
    events = growth_repo.list_events({"member_id": person_id, "limit": 300})
    mentoring_ev = [e for e in events if e.get("event_type") == "people_development"]
    upward_ev = [e for e in events if e.get("event_type") == "upward"]
    rels = all_evidence(to_id=person_id)
    from_rels = all_evidence(from_id=person_id)
    degree = len({(e.get("from_member_id"), e.get("to_member_id")) for e in rels + from_rels})
    dependents = _dependents(person_id)
    readiness = _readiness(caps, profile)
    return {
        "person_id": person_id,
        "name": member.get("name") or person_id,
        "role": member.get("role") or "",
        "person_type": classify_person(member, profile, nc),
        "stage": profile.get("current_stage"),
        "capabilities": caps,
        "velocity": vel,
        "readiness": readiness,
        "gaps": profile.get("missing_experiences") or [],
        "experiences": profile.get("experiences") or [],
        "projects": [
            {
                "id": p.get("id"),
                "name": p.get("name"),
                "status": p.get("status"),
                "owner_id": p.get("owner_id"),
                "is_owner": p.get("owner_id") == person_id,
                "open_risk_count": p.get("open_risk_count") or 0,
            }
            for p in projects[:20]
        ],
        "load": {
            "project_count": len(projects),
            "owned_open": len(open_owned),
            "mentoring_events": len(mentoring_ev),
            "upward_events": len(upward_ev),
            "relationship_degree": degree,
        },
        "dependents": dependents,
        "newcomer": {
            "id": nc.get("id"),
            "entry_date": nc.get("entry_date"),
            "stage": nc.get("onboarding_stage"),
            "target_role_id": nc.get("target_role_id"),
            "progress": nc.get("progress"),
            "completed": len(nc.get("completed_tasks") or []),
            "task_count": nc.get("task_count") or 0,
        } if nc else None,
        "event_count": len(events),
    }


def _readiness(caps, profile):
    if not caps:
        return 50
    avg = sum(c["current"] for c in caps) / len(caps)
    missing = len(profile.get("missing_experiences") or [])
    penalty = missing * 4
    return clip(avg - penalty)


def _dependents(person_id):
    """对 person 专业依赖高、独立性偏低的人。"""
    mmap = {m["id"]: m for m in get_all_members()}
    from_map = defaultdict(list)
    for e in all_evidence(to_id=person_id):
        from_map[e.get("from_member_id")].append(e)
    out = []
    for fid, evs in from_map.items():
        if not fid or fid == person_id:
            continue
        prof = compute_score([x for x in evs if x.get("dimension") in ("professional_trust", "trust")])
        indep = compute_score([x for x in evs if x.get("dimension") == "independence"])
        if prof >= 70 and indep <= 55:
            out.append({
                "person_id": fid,
                "name": (mmap.get(fid) or {}).get("name") or fid,
                "professional_trust": prof,
                "independence": indep,
                "risk": "依赖风险",
            })
    return out


def team_snapshot():
    members = get_all_members()
    people = []
    for m in members:
        snap = person_snapshot(m["id"])
        if snap:
            people.append(snap)
    ncs = _newcomers()
    projects = []
    try:
        projects = pc_repo.list_projects({"include_archived": False}) or []
    except Exception:
        pass
    types = defaultdict(int)
    for p in people:
        types[p["person_type"]] += 1
    mentors = [p for p in people if p["person_type"] in ("储备干部", "管理候选人", "高潜人员") or p["load"]["mentoring_events"] > 0]
    return {
        "size": len(people),
        "people": people,
        "newcomer_count": len(ncs),
        "newcomers": ncs,
        "project_count": len(projects),
        "open_projects": [
            {"id": p.get("id"), "name": p.get("name"), "owner_id": p.get("owner_id"), "open_risk_count": p.get("open_risk_count") or 0}
            for p in projects[:30]
        ],
        "pipeline": {
            "管理层": types.get("管理候选人", 0) and 1 or sum(1 for p in people if "负责" in (p.get("role") or "")),
            "储备干部": types.get("储备干部", 0),
            "高潜人员": types.get("高潜人员", 0),
            "普通成员": types.get("普通成员", 0),
            "新人": types.get("新人", 0) or len(ncs),
        },
        "mentor_pool": [{"person_id": p["person_id"], "name": p["name"], "load": p["load"]} for p in mentors],
    }


def pair_scores(from_id, to_id):
    evs = all_evidence(from_id, to_id)
    return {
        "trust": compute_score([e for e in evs if e.get("dimension") in ("trust", "professional_trust")]),
        "professional_trust": compute_score([e for e in evs if e.get("dimension") == "professional_trust"]),
        "independence": compute_score([e for e in evs if e.get("dimension") == "independence"]),
        "communication": compute_score([e for e in evs if e.get("dimension") == "communication"]),
        "conflict": compute_score([e for e in evs if int(e.get("delta") or 0) < 0]),
        "evidence_count": len(evs),
        "negative_count": sum(1 for e in evs if int(e.get("delta") or 0) < 0),
        "cites": [
            cite("event", e.get("reason") or "关系证据", e.get("reason") or "", e.get("event_time"), e.get("event_id"))
            for e in evs[-4:]
        ],
    }
