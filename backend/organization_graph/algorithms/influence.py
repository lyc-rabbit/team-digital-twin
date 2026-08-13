"""影响力计算：Degree / Betweenness / PageRank。"""

from collections import defaultdict

from ..ontology.relations import PERSON_RELATIONS, REL_CONFLICT


def person_subgraph(nodes, edges, include_conflict=True):
    """抽取人员子图：{id: name}, adjacency weighted undirected."""
    persons = {n["id"]: n for n in nodes if n.get("type") == "Person"}
    adj = defaultdict(dict)  # u -> v -> weight
    for e in edges:
        rel = e.get("relation")
        if rel not in PERSON_RELATIONS:
            continue
        if rel == REL_CONFLICT and not include_conflict:
            continue
        src, tgt = e["source"], e["target"]
        if src not in persons or tgt not in persons or src == tgt:
            continue
        strength = float((e.get("properties") or {}).get("strength") or 0.4)
        if rel == REL_CONFLICT:
            strength = max(0.15, strength * 0.5)
        w = max(adj[src].get(tgt, 0), strength)
        adj[src][tgt] = w
        adj[tgt][src] = max(adj[tgt].get(src, 0), w)
    return persons, adj


def _nx_graph(persons, adj):
    try:
        import networkx as nx
    except ImportError:
        return None
    g = nx.Graph()
    g.add_nodes_from(persons.keys())
    for u, nbrs in adj.items():
        for v, w in nbrs.items():
            if u < v:
                g.add_edge(u, v, weight=w)
    return g


def degree_centrality(persons, adj):
    n = max(len(persons) - 1, 1)
    scores = {}
    for pid in persons:
        scores[pid] = len(adj.get(pid, {})) / n
    return scores


def betweenness_centrality(persons, adj):
    g = _nx_graph(persons, adj)
    if g is not None:
        import networkx as nx
        if g.number_of_edges() == 0:
            return {pid: 0.0 for pid in persons}
        return dict(nx.betweenness_centrality(g, weight="weight", normalized=True))
    return _betweenness_fallback(persons, adj)


def pagerank_scores(persons, adj, damping=0.85, iters=40):
    g = _nx_graph(persons, adj)
    if g is not None and g.number_of_nodes():
        import networkx as nx
        if g.number_of_edges() == 0:
            return {pid: 1.0 / len(persons) for pid in persons}
        return dict(nx.pagerank(g, alpha=damping, weight="weight"))
    return _pagerank_fallback(persons, adj, damping, iters)


def _pagerank_fallback(persons, adj, damping, iters):
    n = len(persons) or 1
    ids = list(persons.keys())
    pr = {pid: 1.0 / n for pid in ids}
    for _ in range(iters):
        nxt = {pid: (1 - damping) / n for pid in ids}
        for u in ids:
            nbrs = adj.get(u) or {}
            total = sum(nbrs.values()) or 1.0
            if not nbrs:
                share = pr[u] / n
                for v in ids:
                    nxt[v] += damping * share
                continue
            for v, w in nbrs.items():
                nxt[v] += damping * pr[u] * (w / total)
        pr = nxt
    return pr


def _betweenness_fallback(persons, adj):
    """无 networkx 时的 BFS 近似 betweenness。"""
    ids = list(persons.keys())
    cb = {pid: 0.0 for pid in ids}
    for s in ids:
        stack = []
        pred = {v: [] for v in ids}
        sigma = {v: 0.0 for v in ids}
        dist = {v: -1 for v in ids}
        sigma[s] = 1.0
        dist[s] = 0
        queue = [s]
        while queue:
            v = queue.pop(0)
            stack.append(v)
            for w in adj.get(v, {}):
                if dist[w] < 0:
                    dist[w] = dist[v] + 1
                    queue.append(w)
                if dist[w] == dist[v] + 1:
                    sigma[w] += sigma[v]
                    pred[w].append(v)
        delta = {v: 0.0 for v in ids}
        while stack:
            w = stack.pop()
            for v in pred[w]:
                if sigma[w]:
                    delta[v] += (sigma[v] / sigma[w]) * (1 + delta[w])
            if w != s:
                cb[w] += delta[w]
    scale = 2.0 / ((len(ids) - 1) * (len(ids) - 2)) if len(ids) > 2 else 1.0
    return {k: v * scale for k, v in cb.items()}


def compute_influence(nodes, edges):
    """
    返回每人:
      degree, betweenness, pagerank, influence_score (0-100)
    """
    persons, adj = person_subgraph(nodes, edges, include_conflict=True)
    if not persons:
        return {}
    deg = degree_centrality(persons, adj)
    bet = betweenness_centrality(persons, adj)
    pr = pagerank_scores(persons, adj)

    def _scale(mapping):
        vals = list(mapping.values())
        lo, hi = min(vals), max(vals)
        if hi - lo < 1e-9:
            return {k: 50.0 for k in mapping}
        return {k: (v - lo) / (hi - lo) * 100.0 for k, v in mapping.items()}

    deg_s, bet_s, pr_s = _scale(deg), _scale(bet), _scale(pr)
    result = {}
    for pid, person in persons.items():
        score = round(0.25 * deg_s[pid] + 0.30 * bet_s[pid] + 0.45 * pr_s[pid])
        result[pid] = {
            "id": pid,
            "name": person.get("name") or pid,
            "degree": round(deg[pid], 4),
            "betweenness": round(bet[pid], 4),
            "pagerank": round(pr[pid], 6),
            "influence_score": int(max(0, min(100, score))),
            "connections": len(adj.get(pid, {})),
        }
    return result
