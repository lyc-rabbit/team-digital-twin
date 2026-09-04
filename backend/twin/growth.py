"""P2-01 人才成长预测、P2-02 晋升时间预测。禁止纯 LLM 拍脑袋。"""

from .common import clip, cite, judgment
from . import snapshot as snap
from . import repository as repo

HORIZONS = (30, 60, 90, 180)

CAP_FOCUS = [
    ("project_mgmt", "项目能力"),
    ("mentoring", "带人能力"),
    ("upward", "向上协同"),
]


def _project(current, per_day, days, stalled=False, plan_boost=1.0):
    speed = max(-0.15, min(0.12, float(per_day or 0))) * plan_boost
    if stalled:
        speed *= 0.45
    return clip(current + speed * days)


def predict_growth(person_id, days=90):
    person = snap.person_snapshot(person_id)
    if not person:
        return None
    days = int(days or 90)
    vel = person["velocity"]
    plan_boost = 1.15 if vel["recent_event_count"] >= 4 else 1.0
    if person.get("newcomer"):
        plan_boost += 0.1
    caps = []
    evidence = []
    for item in person["capabilities"]:
        predicted = _project(item["current"], vel["per_day"], days, vel["stalled"], plan_boost)
        if item["id"] in {c[0] for c in CAP_FOCUS} or True:
            caps.append({
                "id": item["id"],
                "label": item["label"],
                "current": item["current"],
                "predicted": predicted,
                "status": item["status"],
            })
        evidence.append(cite(
            "capability", item["label"],
            f"当前 {item['current']}（{item['status']}），证据 {item['evidence_count']} 条",
        ))
    readiness_now = person["readiness"]
    readiness_pred = _project(readiness_now, vel["per_day"] * 0.9, days, vel["stalled"], plan_boost)
    timeline = []
    for h in HORIZONS:
        timeline.append({
            "days": h,
            "readiness": _project(readiness_now, vel["per_day"] * 0.9, h, vel["stalled"], plan_boost),
        })
    daily = max(0.04, min(0.12, vel["per_day"] * 0.9) * plan_boost)
    remain = max(0, 85 - readiness_now)
    days_to_bar = int(round(remain / daily)) if daily else None
    accelerators = []
    delays = list(person.get("gaps") or [])
    if any(c["id"] == "mentoring" and c["status"] != "已验证" for c in person["capabilities"]):
        accelerators.append("完成一次完整新人培养周期")
    if any(c["id"] == "institution" and c["status"] != "已验证" for c in person["capabilities"]):
        accelerators.append("主导一次制度建设")
    if vel["stalled"]:
        delays.append("近窗口缺少成长事件，速度被下调")
    focus = [c for c in caps if c["id"] in {x[0] for x in CAP_FOCUS}]
    result = {
        "person_id": person_id,
        "name": person["name"],
        "person_type": person["person_type"],
        "horizon_days": days,
        "capabilities": focus or caps[:4],
        "all_capabilities": caps,
        "readiness": {"current": readiness_now, "predicted": readiness_pred},
        "timeline": timeline,
        "days_to_target": days_to_bar,
        "target_label": "管理岗位观察线（约 85%）",
        "accelerators": accelerators,
        "delays": delays,
        "basis": {
            "current_readiness": readiness_now,
            "velocity_per_day": vel["per_day"],
            "recent_events": vel["recent_event_count"],
            "practices": person.get("experiences") or [],
            "gaps": person.get("gaps") or [],
            "stalled": vel["stalled"],
            "plan_boost": plan_boost,
        },
        "judgment": judgment(
            f"按当前速度，{days} 天后管理岗位准备度约 {readiness_pred}%（现 {readiness_now}%）。",
            f"速度来自近{vel['window_days']}天能力证据与事件频率（{vel['recent_event_count']} 条），"
            f"{'因近期无成长事件已降速。' if vel['stalled'] else '并按培养活跃度加权。'}"
            f"缺口：{'、'.join(delays[:3]) or '关键经历较完整'}。",
            evidence[:8] + [
                cite("practice", "已完成实践", "；".join((person.get("experiences") or [])[:4]) or "尚无归档实践"),
            ],
        ),
        "note": "预测由历史速度外推，不是 LLM 主观判断。",
    }
    result["prediction_id"] = repo.save_prediction("growth", person_id, days, {
        "readiness": readiness_pred,
        "days_to_target": days_to_bar,
        "days": days_to_bar,
    })
    return result
