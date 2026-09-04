"""干部成长档案：第一期只做经历归档，不做复杂算法。"""

from database import get_all_members, get_member
from project_center import repository as pc_repo

from . import repository as repo
from .taxonomy import tag_label

CAPABILITY_DEFS = [
    {"id": "project_mgmt", "label": "项目管理", "caps": ("delivery", "项目管理")},
    {"id": "tech_decision", "label": "技术决策", "caps": ("professional", "技术决策")},
    {"id": "ai_collab", "label": "AI协作", "caps": ("ai_coding", "ai_collab", "AI")},
    {"id": "problem_definition", "label": "问题定义", "caps": ("problem_definition",)},
    {"id": "mentoring", "label": "带人能力", "caps": ("mentoring", "带人")},
    {"id": "upward", "label": "向上协同", "caps": ("upward",)},
    {"id": "institution", "label": "组织建设", "caps": ("institution", "组织建设")},
]


def _status_from_scores(scores):
    if not scores:
        return "未验证"
    avg = sum(scores) / len(scores)
    if len(scores) >= 3 and avg >= 70:
        return "已验证"
    if len(scores) >= 1 and avg >= 55:
        return "形成中"
    return "未验证"


def _project_experiences(person_id):
    items = []
    projects = pc_repo.list_projects({"include_archived": True, "member_id": person_id}) or []
    for p in projects:
        is_owner = p.get("owner_id") == person_id
        growth = repo.get_project_growth(p["id"], person_id)
        role = (growth or {}).get("project_role") or ("负责人" if is_owner else "参与")
        title = p.get("name") or p["id"]
        if is_owner:
            items.append(f"独立负责项目{title}")
        elif (p.get("type") or "") in ("探索项目", "AI项目", "技术项目"):
            items.append(f"复杂技术探索项目{title}")
        else:
            items.append(f"参与项目{title}（{role}）")
    for g in repo.list_project_growth(person_id=person_id):
        if g.get("newcomer_training"):
            items.append("新人培养实践")
            break
    return list(dict.fromkeys(items))


def _event_flags(person_id):
    events = repo.list_events({"member_id": person_id, "limit": 400})
    flags = {
        "mentoring_events": 0,
        "mentoring_cycle": False,
        "institution": 0,
        "upward": 0,
        "problem_def": 0,
        "management_result": False,
    }
    for e in events:
        t, tag = e.get("event_type"), e.get("event_tag")
        if t == "people_development":
            flags["mentoring_events"] += 1
            if tag == "development_result":
                flags["mentoring_cycle"] = True
        if t == "management" and tag == "institution":
            flags["institution"] += 1
        if t == "upward":
            flags["upward"] += 1
        if tag in ("problem_raise", "problem_define") or t == "communication":
            flags["problem_def"] += 1
        if t == "management" and tag in ("decision", "institution"):
            flags["management_result"] = True
    return flags, events


def build_profile(person_id):
    member = get_member(person_id)
    if not member:
        return None
    experiences = _project_experiences(person_id)
    flags, events = _event_flags(person_id)
    caps_raw = repo.list_capability_evidence(person_id)

    if flags["mentoring_events"] and "新人培养实践" not in experiences:
        experiences.append("新人培养实践")

    capabilities = []
    for spec in CAPABILITY_DEFS:
        scores = []
        for c in caps_raw:
            cid = (c.get("capability_id") or "") + (c.get("capability_name") or "")
            if any(k.lower() in cid.lower() for k in spec["caps"]):
                scores.append(float(c.get("score") or 0))
        if spec["id"] == "upward" and flags["upward"]:
            scores.extend([60] * min(3, flags["upward"]))
        if spec["id"] == "mentoring" and flags["mentoring_events"]:
            scores.extend([62] * min(3, flags["mentoring_events"]))
        if spec["id"] == "institution" and flags["institution"]:
            scores.extend([75] * flags["institution"])
        if spec["id"] == "problem_definition" and flags["problem_def"]:
            scores.extend([65] * min(3, flags["problem_def"]))
        status = _status_from_scores(scores)
        if spec["id"] == "mentoring" and flags["mentoring_cycle"]:
            status = "已验证"
        capabilities.append({
            "id": spec["id"],
            "label": spec["label"],
            "status": status,
            "evidence_count": len(scores),
        })

    missing = []
    if not flags["mentoring_cycle"]:
        missing.append("暂无完整新人培养周期")
    if not flags["institution"]:
        missing.append("暂无制度建设实践")
    if not flags["management_result"]:
        missing.append("暂无正式团队管理结果")

    stage = "储备干部培养期"
    verified = sum(1 for c in capabilities if c["status"] == "已验证")
    if verified >= 5 and not missing:
        stage = "具备晋升观察条件"
    elif verified <= 1 and not experiences:
        stage = "能力积累期"

    return {
        "person_id": person_id,
        "name": member.get("name"),
        "role": member.get("role"),
        "current_stage": stage,
        "experiences": experiences,
        "capabilities": capabilities,
        "missing_experiences": missing,
        "event_count": len(events),
        "recent_events": [
            {
                "id": e["id"],
                "event_time": e.get("event_time"),
                "title": tag_label(e.get("event_type"), e.get("event_tag")) or e.get("scene") or "事件",
                "summary": (e.get("raw_summary") or "")[:120],
            }
            for e in events[:8]
        ],
    }


def list_profiles():
    return [p for p in (build_profile(m["id"]) for m in get_all_members()) if p]


def promotion_assessment(person_id):
    """晋升领导输入：成长证据 overlay，不改原算法。"""
    profile = build_profile(person_id)
    if not profile:
        return None
    missing = list(profile.get("missing_experiences") or [])
    forming = [c["label"] for c in profile.get("capabilities") or [] if c.get("status") == "形成中"]
    unverified = [c["label"] for c in profile.get("capabilities") or [] if c.get("status") == "未验证"]
    verified = [c["label"] for c in profile.get("capabilities") or [] if c.get("status") == "已验证"]
    why_not = []
    if missing:
        why_not.extend(missing)
    if unverified:
        why_not.append("尚未验证：" + "、".join(unverified))
    if forming:
        why_not.append("仍在形成中：" + "、".join(forming))
    if not why_not:
        why_not.append("关键经历已较完整，仍需结合关系网与上级评价判断稳定性。")
    actions = []
    if "暂无完整新人培养周期" in missing:
        actions.append("带完一名新人的完整培养周期，并留下阶段评价与事实事件")
    if "暂无制度建设实践" in missing:
        actions.append("补一次制度/规范建设事件，形成可复用的团队规则")
    if "暂无正式团队管理结果" in missing:
        actions.append("独立负责一次管理决策或团队结果，并记录复盘")
    if "问题定义" in forming or "问题定义" in unverified:
        actions.append("要求协作对象用结构化问题定义沟通，自己也留下对应事件")
    if not actions:
        actions.append("继续积累向上协同与带人证据，避免只有项目交付没有管理经历")
    mgmt = next((c for c in profile.get("capabilities") or [] if c["id"] == "mentoring"), None)
    return {
        "current_stage": profile.get("current_stage"),
        "management_ability": (mgmt or {}).get("status") or "未验证",
        "experiences": profile.get("experiences") or [],
        "capabilities": profile.get("capabilities") or [],
        "strengths": verified,
        "weaknesses": forming + unverified,
        "missing_experiences": missing,
        "promotion_risks": missing[:3] or ["管理结果样本不足"],
        "recommended_actions": actions,
        "why_not_promote": why_not,
    }
