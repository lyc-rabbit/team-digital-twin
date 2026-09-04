"""P2-14 非正式组织、P2-15 冲突预测。"""

from collections import defaultdict

from database import get_all_members
from growth.scores import all_evidence
from growth import repository as growth_repo

from .common import clip, cite, judgment, risk_level
from . import snapshot as snap


def informal_groups():
    try:
        from organization_graph.service import get_graph
        from organization_graph.algorithms.community import detect_communities, structural_holes
        g = get_graph()
        communities = detect_communities(g.get("nodes") or [], g.get("edges") or [])
        holes = structural_holes(g.get("nodes") or [], g.get("edges") or [])
    except Exception:
        communities, holes = [], []

    if not communities:
        communities = _fallback_clusters()
        holes = []

    mmap = {m["id"]: m for m in get_all_members()}
    members_in = set()
    for c in communities:
        for x in c.get("members") or []:
            members_in.add(x.get("id") or x)
    isolates = []
    for m in mmap.values():
        if m["id"] not in members_in:
            isolates.append({"id": m["id"], "name": m.get("name") or m["id"]})

    hubs = []
    for h in (holes or [])[:5]:
        hubs.append({
            "id": h.get("id"),
            "name": h.get("name"),
            "role": "跨群体连接人" if h.get("hole_score", 0) >= 60 else "信息中心",
            "score": h.get("hole_score"),
        })
    cores = []
    for c in communities[:3]:
        mem = c.get("members") or []
        if mem:
            cores.append({"group": c.get("name"), "person": mem[0].get("name"), "role": "核心人物"})

    return {
        "groups": communities,
        "cores": cores,
        "bridges": hubs,
        "isolates": isolates[:12],
        "note": "非正式组织来自关系图聚类或高信任对，属于结构观察，不是小团体定性。",
        "judgment": judgment(
            f"识别到 {len(communities)} 个协作圈，孤立成员 {len(isolates)} 人。",
            "优先使用组织影响力图的社群发现；图为空时回退到高信任关系对聚类。",
            [cite("group", c.get("name") or c.get("id"), f"{c.get('size') or len(c.get('members') or [])} 人") for c in communities[:5]],
        ),
    }


def _fallback_clusters():
    members = get_all_members()
    pairs = defaultdict(int)
    for m in members:
        for e in all_evidence(from_id=m["id"]):
            if int(e.get("delta") or 0) <= 0:
                continue
            if e.get("dimension") not in ("trust", "professional_trust", "communication"):
                continue
            a, b = m["id"], e.get("to_member_id")
            if not b or a == b:
                continue
            key = tuple(sorted([a, b]))
            pairs[key] += int(e.get("delta") or 0)
    parent = {m["id"]: m["id"] for m in members}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for (a, b), w in pairs.items():
        if w < 4:
            continue
        pa, pb = find(a), find(b)
        if pa != pb:
            parent[pb] = pa
    groups = defaultdict(list)
    mmap = {m["id"]: m for m in members}
    for m in members:
        groups[find(m["id"])].append(m)
    named = []
    for i, (gid, people) in enumerate(groups.items(), 1):
        if len(people) < 2:
            continue
        named.append({
            "id": f"cluster_{i}",
            "name": f"协作圈{i}",
            "size": len(people),
            "members": [{"id": p["id"], "name": p.get("name"), "position": p.get("role")} for p in people],
        })
    named.sort(key=lambda x: x["size"], reverse=True)
    return named


def predict_conflict(person_a, person_b):
    a = snap.person_snapshot(person_a)
    b = snap.person_snapshot(person_b)
    if not a or not b:
        return None
    pair_ab = snap.pair_scores(person_a, person_b)
    pair_ba = snap.pair_scores(person_b, person_a)
    neg = pair_ab["negative_count"] + pair_ba["negative_count"]
    shared = {p["id"] for p in a.get("projects") or []} & {p["id"] for p in b.get("projects") or []}
    events = growth_repo.list_events({"member_id": person_a, "limit": 120})
    conflict_ev = [
        e for e in events
        if e.get("event_tag") in ("conflict", "superior_challenge", "comm_error")
        or "冲突" in ((e.get("raw_summary") or "") + (e.get("facts") or ""))
    ]
    related = [e for e in conflict_ev if person_b in (e.get("involved_members") or []) or person_b in (e.get("related_persons") or [])]
    score = clip(20 + neg * 12 + (18 if shared else 0) + len(related) * 15)
    reasons = []
    if shared:
        reasons.append("资源/项目重叠，存在资源竞争")
    if a["load"]["owned_open"] and b["load"]["owned_open"]:
        reasons.append("双方都有负责事项，职责边界可能不清")
    if related:
        reasons.append("历史负面/冲突事件")
    if not reasons:
        reasons.append("当前负向证据有限，属于低样本预测")
    recs = []
    if shared:
        recs.append("提前明确重叠项目的责任边界")
    if score >= 50:
        recs.append("把可能冲突的决策点写成书面分工，而不是靠默契")
    return {
        "person_a": {"id": person_a, "name": a["name"]},
        "person_b": {"id": person_b, "name": b["name"]},
        "risk": score,
        "level": risk_level(score),
        "reasons": reasons,
        "recommendations": recs or ["维持观察，继续用事件记录协作质量"],
        "kind": "风险预测",
        "is_prediction": True,
        "judgment": judgment(
            f"{a['name']} ↔ {b['name']} 冲突风险 {score}（风险预测，不是事实）。",
            f"负向证据 {neg} 条，共同项目 {len(shared)}，历史冲突事件 {len(related)}。",
            pair_ab.get("cites") or [],
        ),
    }
