"""社群发现（Louvain）与结构洞分析。"""

from collections import defaultdict

from .influence import person_subgraph, _nx_graph


def detect_communities(nodes, edges):
    """
    返回:
    [
      {"id": "community_1", "name": "AI核心圈", "members": [...], "modularity_hint": ...}
    ]
    """
    persons, adj = person_subgraph(nodes, edges, include_conflict=False)
    if not persons:
        return []

    groups = _louvain(persons, adj)
    named = []
    for i, member_ids in enumerate(groups, start=1):
        member_nodes = [persons[mid] for mid in member_ids if mid in persons]
        name = _community_name(member_nodes, i)
        named.append({
            "id": f"community_{i}",
            "name": name,
            "size": len(member_ids),
            "members": [
                {
                    "id": n["id"],
                    "name": n.get("name") or n["id"],
                    "position": n.get("position") or "",
                    "department": n.get("department") or "",
                }
                for n in member_nodes
            ],
        })
    named.sort(key=lambda x: x["size"], reverse=True)
    return named


def structural_holes(nodes, edges, communities=None):
    """
    Burt 约束系数：越低越可能是桥梁（结构洞）。

    桥梁分 = (1 - constraint) × 100
    同样连接 7 个人，若这 7 人彼此已经连成一团，约束高、桥梁分低；
    若这 7 人分属不同圈子且互不相连，约束低、桥梁分高。
    """
    persons, adj = person_subgraph(nodes, edges, include_conflict=False)
    comm_of = {}
    comm_name = {}
    for c in communities or []:
        cid = c.get("id")
        cname = c.get("name") or cid
        for m in c.get("members") or []:
            mid = m.get("id") if isinstance(m, dict) else m
            if mid:
                comm_of[mid] = cid
                comm_name[cid] = cname

    result = []
    for pid, person in persons.items():
        nbrs = adj.get(pid) or {}
        constraint = _burt_constraint(pid, nbrs, adj)
        hole = max(0.0, min(100.0, (1.0 - constraint) * 100.0))
        bridges = []
        cross_bridges = 0
        neighbor_ids = list(nbrs.keys())
        neighbor_comms = {comm_of[x] for x in neighbor_ids if x in comm_of}
        if pid in comm_of:
            neighbor_comms.add(comm_of[pid])
        for i, a in enumerate(neighbor_ids):
            for b in neighbor_ids[i + 1:]:
                if b in (adj.get(a) or {}):
                    continue
                item = {
                    "from": persons.get(a, {}).get("name", a),
                    "to": persons.get(b, {}).get("name", b),
                    "cross": bool(comm_of.get(a) and comm_of.get(b) and comm_of[a] != comm_of[b]),
                }
                if item["cross"]:
                    cross_bridges += 1
                bridges.append(item)
        result.append({
            "id": pid,
            "name": person.get("name") or pid,
            "constraint": round(constraint, 4),
            "openness": round(1.0 - constraint, 4),
            "hole_score": int(round(hole)),
            "formula": f"(1 − {round(constraint, 4)}) × 100",
            "bridges": bridges[:8],
            "bridge_count": len(bridges),
            "cross_bridge_count": cross_bridges,
            "communities_spanned": len(neighbor_comms),
            "community_names": [comm_name[c] for c in neighbor_comms if c in comm_name],
            "degree": len(nbrs),
        })
    result.sort(key=lambda x: (x["hole_score"], x["cross_bridge_count"], x["degree"]), reverse=True)
    return result


def _burt_constraint(node, nbrs, adj):
    if not nbrs:
        return 1.0
    total = sum(nbrs.values()) or 1.0
    p = {j: w / total for j, w in nbrs.items()}
    c = 0.0
    for j in nbrs:
        indirect = 0.0
        for q, pq in p.items():
            if q == j:
                continue
            q_nbrs = adj.get(q) or {}
            q_total = sum(q_nbrs.values()) or 1.0
            p_qj = (q_nbrs.get(j, 0) / q_total) if q_total else 0
            indirect += pq * p_qj
        c += (p[j] + indirect) ** 2
    return min(1.0, c)


def _louvain(persons, adj):
    g = _nx_graph(persons, adj)
    if g is not None:
        import networkx as nx
        try:
            from networkx.algorithms.community import louvain_communities
            comms = louvain_communities(g, weight="weight", seed=7)
            return [list(c) for c in comms if c]
        except Exception:
            try:
                from networkx.algorithms.community import greedy_modularity_communities
                comms = greedy_modularity_communities(g, weight="weight")
                return [list(c) for c in comms if c]
            except Exception:
                pass
    return _label_propagation(persons, adj)


def _label_propagation(persons, adj, rounds=20):
    labels = {pid: pid for pid in persons}
    ids = list(persons.keys())
    for _ in range(rounds):
        changed = False
        for pid in ids:
            votes = defaultdict(float)
            for nb, w in (adj.get(pid) or {}).items():
                votes[labels[nb]] += w
            if not votes:
                continue
            best = max(votes.items(), key=lambda x: x[1])[0]
            if best != labels[pid]:
                labels[pid] = best
                changed = True
        if not changed:
            break
    groups = defaultdict(list)
    for pid, lab in labels.items():
        groups[lab].append(pid)
    return list(groups.values())


def _community_name(members, index):
    if not members:
        return f"圈层 {index}"
    skills = defaultdict(int)
    depts = defaultdict(int)
    for m in members:
        for s in m.get("skills") or []:
            skills[s] += 1
        if m.get("department"):
            depts[m["department"]] += 1
    if skills:
        top = max(skills.items(), key=lambda x: x[1])[0]
        return f"{top}核心圈"
    if depts:
        top = max(depts.items(), key=lambda x: x[1])[0]
        if top and top != "未分组":
            return f"{top}圈"
    if len(members) == 1:
        return f"{members[0].get('name') or '成员'}独立圈"
    return f"协作圈 {index}"
