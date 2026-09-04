"""P2-04 带人推演、P2-05 管理者-人员匹配。"""

from .common import clip, cite, judgment, risk_level, risk_label
from . import snapshot as snap


def match_mentor(mentor_id, mentee_id):
    mentor = snap.person_snapshot(mentor_id)
    mentee = snap.person_snapshot(mentee_id)
    if not mentor or not mentee:
        return None
    pair = snap.pair_scores(mentee_id, mentor_id)
    tech_gap = abs(
        next((c["current"] for c in mentor["capabilities"] if c["id"] == "tech_decision"), 60)
        - next((c["current"] for c in mentee["capabilities"] if c["id"] == "tech_decision"), 50)
    )
    complement = clip(70 + min(20, tech_gap / 2) + (8 if pair["communication"] >= 60 else -6))
    comm_fit = pair["communication"]
    relation = pair["trust"]
    dep_risk = pair["professional_trust"] >= 70 and pair["independence"] <= 55
    load_risk = mentor["load"]["owned_open"] >= 2 or mentor["load"]["project_count"] >= 4
    score = clip(
        0.35 * complement + 0.25 * comm_fit + 0.25 * relation
        + (10 if mentee.get("newcomer") else 0)
        - (12 if dep_risk else 0)
        - (10 if load_risk else 0)
    )
    if score >= 78:
        rec = "推荐带人"
    elif score >= 60:
        rec = "谨慎带人"
    else:
        rec = "不推荐当前组合"
    advantages, risks = [], []
    if complement >= 70:
        advantages.append("技术能力互补")
    if comm_fit >= 60:
        advantages.append("沟通模式匹配")
    if relation >= 60:
        advantages.append("当前关系良好")
    if dep_risk:
        risks.append("新人存在较高依赖倾向（信任高、独立性低）")
    if load_risk:
        risks.append("导师自身项目负荷较高")
    if pair["negative_count"] >= 2:
        risks.append("历史上有负向协作证据")
    return {
        "mentor": {"person_id": mentor_id, "name": mentor["name"], "load": mentor["load"]},
        "mentee": {"person_id": mentee_id, "name": mentee["name"], "person_type": mentee["person_type"]},
        "match": score,
        "recommendation": rec,
        "advantages": advantages or ["暂无足够正向匹配证据"],
        "risks": risks,
        "scores": {"complement": complement, "communication": comm_fit, "relation": relation, "independence": pair["independence"]},
        "is_prediction": True,
        "judgment": judgment(
            f"匹配度 {score}%：{rec}。",
            f"互补 {complement}、沟通 {comm_fit}、关系 {relation}；"
            + ("存在依赖风险。" if dep_risk else "独立性尚可。")
            + ("导师项目负荷偏高。" if load_risk else ""),
            pair.get("cites") or [],
        ),
    }


def simulate_span(manager_id, reportee_ids):
    manager = snap.person_snapshot(manager_id)
    if not manager:
        return None
    ids = [x for x in (reportee_ids or []) if x and x != manager_id]
    people = [snap.person_snapshot(i) for i in ids]
    people = [p for p in people if p]
    matches = [match_mentor(manager_id, p["person_id"]) for p in people]
    span = len(people)
    complement_avg = clip(sum(((m or {}).get("scores") or {}).get("complement") or 50 for m in matches) / max(1, len(matches)))
    conflict = clip(sum(100 - (((m or {}).get("scores") or {}).get("relation") or 50) for m in matches) / max(1, len(matches)))
    deps = []
    for p in people:
        for d in manager.get("dependents") or []:
            if d["person_id"] == p["person_id"]:
                deps.append(d)
        pair = snap.pair_scores(p["person_id"], manager_id)
        if pair["professional_trust"] >= 68 and pair["independence"] <= 58:
            deps.append({"person_id": p["person_id"], "name": p["name"], "risk": "技术依赖偏高"})
    unique_deps = {d["person_id"]: d for d in deps}
    train_pressure = clip(40 + span * 12 + 8 * sum(1 for p in people if p.get("newcomer")))
    load_pressure = clip(30 + manager["load"]["owned_open"] * 18 + manager["load"]["project_count"] * 6 + span * 8)
    delivery = clip(70 + manager["load"]["owned_open"] * 3 - (8 if load_pressure >= 75 else 0))
    org_risk = clip((train_pressure + load_pressure + len(unique_deps) * 12) / 2.4)

    recs = []
    if unique_deps and people:
        others = [p for p in people if p["person_id"] not in unique_deps]
        if others:
            recs.append(f"将 {others[0]['name']} 设为依赖较高新人的技术协作者，降低 {manager['name']} 单点指导压力。")
        else:
            recs.append("指定第二导师或技术协作者，避免新人问题只流向同一人。")
    if load_pressure >= 70:
        recs.append("减少管理者本人并行项目，或把部分技术决策授权出去。")
    if span >= 3:
        recs.append("每周一次小组同步，避免一对一指导把管理跨度吃满。")
    if not recs:
        recs.append("保持当前组合，继续用事件留下培养与授权证据。")

    metrics = {
        "管理跨度": {"value": span, "level": risk_level(span * 22)},
        "能力互补": {"value": complement_avg, "level": "low" if complement_avg >= 70 else "medium"},
        "潜在冲突": {"value": conflict, "level": risk_level(conflict)},
        "技术依赖": {"value": clip(40 + len(unique_deps) * 22), "level": risk_level(40 + len(unique_deps) * 22)},
        "培养压力": {"value": train_pressure, "level": risk_level(train_pressure)},
        "管理压力": {"value": load_pressure, "level": risk_level(load_pressure)},
        "交付能力": {"value": delivery, "level": "low" if delivery >= 70 else "medium"},
        "组织风险": {"value": org_risk, "level": risk_level(org_risk)},
    }
    evidence = [
        cite("load", "管理者负荷", f"开启负责项目 {manager['load']['owned_open']}，参与项目 {manager['load']['project_count']}"),
        cite("span", "管理跨度", f"{span} 人：" + "、".join(p["name"] for p in people)),
    ]
    for d in unique_deps.values():
        evidence.append(cite("relation", "依赖", f"{d.get('name')} → {manager['name']}：{d.get('risk')}"))
    return {
        "manager": {"person_id": manager_id, "name": manager["name"], "person_type": manager["person_type"]},
        "reportees": [{"person_id": p["person_id"], "name": p["name"], "person_type": p["person_type"]} for p in people],
        "matches": matches,
        "metrics": metrics,
        "dependencies": list(unique_deps.values()),
        "risks": [
            {"title": k, "level": v["level"], "score": v["value"]}
            for k, v in metrics.items() if v["level"] in ("high", "medium") and k != "能力互补"
        ],
        "recommendations": recs,
        "judgment": judgment(
            f"{manager['name']} 带 {span} 人：培养压力{risk_label(metrics['培养压力']['level'])}，管理压力{risk_label(metrics['管理压力']['level'])}。",
            f"跨度 {span}；项目负荷 owned={manager['load']['owned_open']}；技术依赖 {len(unique_deps)} 人。"
            "该结论是情景推演，不是既成事实。",
            evidence,
        ),
        "is_prediction": True,
    }
