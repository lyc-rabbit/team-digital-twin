"""P2-16 领导关系推演、P2-17 干部路线、P2-18 管理类型、P2-19 管理风格。"""

from growth import repository as growth_repo
from growth.upward import build_archive, AUTH_LEVELS

from .common import clip, cite, judgment
from . import snapshot as snap
from . import growth as growth_pred

PATH_STEPS = [
    ("delivery", "项目交付", "project_mgmt"),
    ("explore", "复杂技术/项目探索", "tech_decision"),
    ("mentoring", "带新人", "mentoring"),
    ("institution", "制度建设", "institution"),
    ("coord", "跨团队协调", "project_mgmt"),
    ("team", "完整团队管理", "mentoring"),
    ("candidate", "晋升候选", "upward"),
]


def auth_if_own_project(person_id, project_id=None):
    person = snap.person_snapshot(person_id)
    if not person:
        return None
    archive = build_archive(person_id)
    auth = (archive or {}).get("authorization") or {}
    dims = {d["id"]: d for d in (archive or {}).get("dimensions") or []}
    delivery = (dims.get("delivery_trust") or {}).get("current") or next(
        (c["current"] for c in person["capabilities"] if c["id"] == "project_mgmt"), 60
    )
    risk_hist = person["load"]["upward_events"]
    deltas = {
        "专业判断信任": 4 if next((c["current"] for c in person["capabilities"] if c["id"] == "tech_decision"), 50) >= 60 else 2,
        "项目交付信任": 6 if delivery >= 60 else 3,
        "自主决策信任": 8 if (auth.get("consecutive_good_decisions") or 0) >= 1 or person["load"]["owned_open"] >= 1 else 4,
    }
    order = int(auth.get("order") or 0)
    next_order = min(4, order + (1 if deltas["自主决策信任"] >= 6 else 0))
    cur_lv = AUTH_LEVELS[order]["id"]
    nxt_lv = AUTH_LEVELS[next_order]["id"]
    project_name = None
    if project_id:
        project_name = next((p["name"] for p in person["projects"] if p["id"] == project_id), project_id)
    premises = ["项目按期完成", "重大风险提前同步", "汇报只使用可核验事实"]
    if risk_hist < 2:
        premises.append("补齐向上同步事件，否则授权上调不成立")
    return {
        "person_id": person_id,
        "name": person["name"],
        "project_id": project_id,
        "project_name": project_name,
        "trust_deltas": deltas,
        "auth_from": cur_lv,
        "auth_to": nxt_lv,
        "auth_from_label": AUTH_LEVELS[order]["label"],
        "auth_to_label": AUTH_LEVELS[next_order]["label"],
        "premises": premises,
        "is_prediction": True,
        "judgment": judgment(
            f"若承担「{project_name or '该项目'}」完整责任，授权可能 {cur_lv}→{nxt_lv}（情景推演）。",
            f"依据当前交付信任 {delivery}、已有向上事件 {risk_hist}、现授权 {cur_lv}。"
            "上调前提是按期交付且风险提前同步，不是承诺。",
            [
                cite("auth", "当前授权", auth.get("judgment", {}).get("reason") or cur_lv),
                cite("project", project_name or "未指定项目", "完整责任情景"),
            ],
        ),
    }


def cadre_path(person_id):
    person = snap.person_snapshot(person_id)
    if not person:
        return None
    caps = {c["id"]: c for c in person["capabilities"]}
    steps = []
    current_idx = 0
    for i, (sid, label, cap_id) in enumerate(PATH_STEPS):
        cap = caps.get(cap_id) or {}
        status = cap.get("status") or "未验证"
        if sid == "mentoring" and any("新人" in x for x in person.get("experiences") or []):
            status = "当前" if status != "已验证" else "已验证"
        if sid == "delivery" and person["load"]["owned_open"] + person["load"]["project_count"] > 0:
            status = "已验证" if cap.get("status") == "已验证" else ("当前" if status == "未验证" else status)
        done = status == "已验证"
        if done:
            current_idx = i + 1
        steps.append({"id": sid, "label": label, "status": "✓" if done else ("当前" if status == "当前" else "未到"), "capability": cap.get("label")})
    if current_idx < len(steps):
        steps[min(current_idx, len(steps) - 1)]["status"] = "当前"
        if current_idx + 1 < len(steps):
            steps[current_idx + 1]["status"] = "下一阶段"
    next_practice = "完成一次完整人员培养实践"
    if any(s["id"] == "mentoring" and s["status"] in ("当前", "下一阶段") for s in steps):
        next_practice = "当前最有价值的不是继续做技术，而是完成一次完整人员培养实践。"
    elif any(s["id"] == "institution" and s["status"] in ("当前", "下一阶段") for s in steps):
        next_practice = "下一管理实践：把有效方法沉淀为部门规范。"
    promo = growth_pred.predict_growth(person_id, 90)
    return {
        "person_id": person_id,
        "name": person["name"],
        "stage": person["stage"],
        "steps": steps,
        "next_practice": next_practice,
        "readiness": person["readiness"],
        "predicted_readiness": (promo or {}).get("readiness", {}).get("predicted"),
        "judgment": judgment(
            f"干部成长导航：{person['stage']}。{next_practice}",
            "路线按缺口排序：交付 → 探索 → 带人 → 制度 → 协调 → 团队管理 → 晋升候选。",
            [cite("capability", c["label"], c["status"]) for c in person["capabilities"]],
        ),
    }


def management_type(person_id):
    person = snap.person_snapshot(person_id)
    if not person:
        return None
    scores = {c["id"]: c["current"] for c in person["capabilities"]}
    axes = {
        "技术型管理候选人": scores.get("tech_decision", 50) + scores.get("ai_collab", 50),
        "项目型管理候选人": scores.get("project_mgmt", 50) + scores.get("tech_decision", 40),
        "人员培养型管理候选人": scores.get("mentoring", 50) + scores.get("upward", 40),
    }
    label = max(axes, key=axes.get)
    return {
        "person_id": person_id,
        "name": person["name"],
        "type": label,
        "axes": {k: clip(v / 2) for k, v in axes.items()},
        "evidence": person["capabilities"],
        "judgment": judgment(
            f"{person['name']} 更接近「{label}」。",
            "由技术决策、项目、带人、向上四类能力证据加权，而不是性格标签。",
            [cite("capability", c["label"], f"{c['current']} {c['status']}") for c in person["capabilities"]],
        ),
    }


def management_style(person_id):
    person = snap.person_snapshot(person_id)
    if not person:
        return None
    events = growth_repo.list_events({"member_id": person_id, "limit": 250})
    tags = [e.get("event_tag") for e in events]
    types = [e.get("event_type") for e in events]
    n = max(1, len(events))

    def lvl(count, high=6, mid=2):
        if count >= high:
            return "高"
        if count >= mid:
            return "中"
        return "低"

    profile = {
        "任务授权": lvl(tags.count("superior_auth") + tags.count("empowerment") + types.count("management")),
        "过程干预": lvl(tags.count("task_assignment") + tags.count("review"), 8, 3),
        "技术介入": lvl(tags.count("tech_decision") + tags.count("tech_breakthrough")),
        "新人指导": lvl(types.count("people_development")),
        "风险控制": lvl(tags.count("project_risk") + tags.count("risk_escalate")),
        "向上同步": lvl(types.count("upward") + tags.count("report")),
    }
    if profile["技术介入"] == "高" and profile["任务授权"] in ("高", "中"):
        fit = "高技术密度团队"
    elif profile["新人指导"] == "高":
        fit = "新人占比高、需要教练型管理的团队"
    elif profile["向上同步"] == "高":
        fit = "需要频繁对齐上级的项目型团队"
    else:
        fit = "中小规模执行型团队"
    return {
        "person_id": person_id,
        "name": person["name"],
        "behaviors": profile,
        "fit_team": fit,
        "sample_size": n,
        "judgment": judgment(
            f"管理行为画像更适合「{fit}」，不是简单的领导风格标签。",
            f"基于 {n} 条历史事件的授权/干预/技术/带人/风险/同步频次。",
            [cite("event_stat", k, v) for k, v in profile.items()],
        ),
    }
