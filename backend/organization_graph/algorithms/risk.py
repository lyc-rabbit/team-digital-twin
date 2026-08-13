"""组织风险分析：单点依赖、冲突、无人备份。"""

from collections import defaultdict

from ..ontology.relations import (
    REL_COLLABORATE,
    REL_CONFLICT,
    REL_CONTROL,
    REL_OWNER,
    REL_WORKS_ON,
)


def analyze_risks(nodes, edges, influence=None):
    by_id = {n["id"]: n for n in nodes}
    projects = [n for n in nodes if n.get("type") == "Project"]
    persons = [n for n in nodes if n.get("type") == "Person"]
    influence = influence or {}

    project_people = defaultdict(set)
    for e in edges:
        rel = e.get("relation")
        if rel not in (REL_WORKS_ON, REL_OWNER, REL_COLLABORATE):
            continue
        src, tgt = e["source"], e["target"]
        src_n, tgt_n = by_id.get(src), by_id.get(tgt)
        if rel == REL_COLLABORATE:
            proj_name = (e.get("properties") or {}).get("project")
            if proj_name:
                for p in projects:
                    if p.get("name") == proj_name:
                        if src_n and src_n.get("type") == "Person":
                            project_people[p["id"]].add(src)
                        if tgt_n and tgt_n.get("type") == "Person":
                            project_people[p["id"]].add(tgt)
            continue
        if src_n and src_n.get("type") == "Person" and tgt_n and tgt_n.get("type") == "Project":
            project_people[tgt].add(src)
        elif tgt_n and tgt_n.get("type") == "Person" and src_n and src_n.get("type") == "Project":
            project_people[src].add(tgt)

    risks = []

    for proj in projects:
        owners = project_people.get(proj["id"]) or set()
        importance = proj.get("business_value") or (90 if proj.get("importance") == "high" else 60)
        if int(importance) < 70 and proj.get("importance") != "high":
            continue
        if len(owners) <= 1:
            person = by_id.get(next(iter(owners))) if owners else None
            score = min(95, int(importance) + (15 if not owners else 10))
            risks.append({
                "id": f"risk_proj_{proj['id']}",
                "type": "single_point",
                "level": "high" if score >= 80 else "medium",
                "score": score,
                "title": f"项目「{proj['name']}」依赖单点",
                "detail": (
                    f"依赖 {person.get('name')}，没有替代者" if person
                    else "当前没有明确负责人"
                ),
                "project": proj["name"],
                "person": person.get("name") if person else None,
            })

    conflict_count = defaultdict(int)
    conflict_impact = defaultdict(float)
    for e in edges:
        if e.get("relation") != REL_CONFLICT:
            continue
        props = e.get("properties") or {}
        impact = float(props.get("impact") or 50)
        for pid in (e["source"], e["target"]):
            if by_id.get(pid, {}).get("type") == "Person":
                conflict_count[pid] += int(props.get("frequency") or 1)
                conflict_impact[pid] += impact

    for pid, cnt in conflict_count.items():
        person = by_id.get(pid)
        if not person:
            continue
        avg_impact = conflict_impact[pid] / max(cnt, 1)
        score = min(95, int(30 + cnt * 12 + avg_impact * 0.3))
        if score < 45:
            continue
        inf = (influence.get(pid) or {}).get("influence_score") or person.get("influence_score") or 0
        risks.append({
            "id": f"risk_conflict_{pid}",
            "type": "conflict",
            "level": "high" if score >= 70 else "medium",
            "score": score,
            "title": f"{person.get('name')} 跨协作冲突偏高",
            "detail": f"冲突关系 {cnt} 条；技术影响力 {inf}。晋升时需评估协作风险。",
            "person": person.get("name"),
            "person_id": pid,
        })

    # 高影响力无人备份：betweenness 高但邻居少
    for pid, person in ((p["id"], p) for p in persons):
        inf = influence.get(pid) or {}
        if inf.get("influence_score", 0) >= 70 and inf.get("connections", 0) <= 1:
            risks.append({
                "id": f"risk_key_{pid}",
                "type": "key_person",
                "level": "high",
                "score": min(90, int(inf.get("influence_score") or 80)),
                "title": f"{person.get('name')} 是关键连接人且缺少备份",
                "detail": "影响力高但连接稀疏，离职或缺位会对组织运转产生结构性冲击。",
                "person": person.get("name"),
                "person_id": pid,
            })

    resource_owners = defaultdict(list)
    for e in edges:
        if e.get("relation") != REL_CONTROL:
            continue
        src_n = by_id.get(e["source"])
        tgt_n = by_id.get(e["target"])
        if src_n and src_n.get("type") == "Person" and tgt_n and tgt_n.get("type") in ("Resource", "Knowledge"):
            resource_owners[tgt_n["id"]].append(src_n)

    for rid, owners in resource_owners.items():
        res = by_id.get(rid)
        if not res:
            continue
        if len(owners) == 1:
            importance = int(res.get("importance") or 70)
            if importance < 80:
                continue
            risks.append({
                "id": f"risk_res_{rid}",
                "type": "resource_lock",
                "level": "high" if importance >= 80 else "medium",
                "score": min(92, importance + 5),
                "title": f"资源「{res.get('name')}」被独占",
                "detail": f"仅 {owners[0].get('name')} 掌握，资源影响力无法转移。",
                "person": owners[0].get("name"),
                "resource": res.get("name"),
            })

    if not persons:
        risks.append({
            "id": "risk_empty",
            "type": "empty",
            "level": "low",
            "score": 0,
            "title": "图谱尚无人员节点",
            "detail": "请先在成员管理中添加人员，然后重建图谱。",
        })

    risks.sort(key=lambda x: x.get("score", 0), reverse=True)
    summary = {
        "high": sum(1 for r in risks if r.get("level") == "high"),
        "medium": sum(1 for r in risks if r.get("level") == "medium"),
        "low": sum(1 for r in risks if r.get("level") == "low"),
        "count": len(risks),
    }
    return {"summary": summary, "items": risks}
