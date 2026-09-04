"""时态治理服务：同步重建图、物化当前视图、晋升时间窗。"""

from timeutil import parse_day, today

from organization_graph.ontology.relations import relation_template
from organization_graph.repository.facade import get_facade

from .query import filter_current_edges, snapshot
from .repository import get_temporal_store
from .types import (
    EXCLUSIVE_BY_SOURCE,
    EXCLUSIVE_BY_TARGET,
    LIFECYCLE_ACTIVE,
    TEMPORAL_EVENT_TYPES,
)


def _list_nodes(graph):
    try:
        return graph.list_nodes(include_merged=False)
    except TypeError:
        return graph.list_nodes()


def _list_edges(graph):
    try:
        return graph.list_edges(include_merged=False)
    except TypeError:
        return graph.list_edges()


def _guess_from(edge, nodes):
    props = edge.get("properties") or {}
    if props.get("valid_from"):
        return parse_day(props["valid_from"])
    tgt = nodes.get(edge.get("target")) or {}
    src = nodes.get(edge.get("source")) or {}
    if edge.get("relation") == "INVOLVED_IN":
        return parse_day(tgt.get("time")) or parse_day(props.get("last_update"))
    if edge.get("relation") == "BELONGS_TO":
        return parse_day(src.get("join_date")) or parse_day(src.get("valid_from"))
    return parse_day(props.get("last_update")) or today()


def observe_edge(edge, nodes, source="rebuild"):
    """当前图上的一条边 → 确保有开放事实；不覆盖已关闭的历史。"""
    store = get_temporal_store()
    src, rel, tgt = edge.get("source"), edge.get("relation"), edge.get("target")
    if not src or not rel or not tgt or src == tgt:
        return None
    if rel in ("MERGED_INTO", "ALIAS_OF"):
        return None
    props = edge.get("properties") or {}
    if props.get("valid_to"):
        return None
    open_fact = store.find_open(src, rel, tgt)
    if open_fact:
        return open_fact
    if rel in EXCLUSIVE_BY_TARGET:
        store.close_open_matching(predicate=rel, object_id=tgt, valid_to=today(), exclude_subject=src)
    if rel in EXCLUSIVE_BY_SOURCE:
        others = store.list_facts(subject_id=src, predicate=rel, open_only=True)
        for f in others:
            if f["object_id"] != tgt:
                store.close_fact(f["id"], today())
    return store.insert_fact({
        "subject_id": src,
        "predicate": rel,
        "object_id": tgt,
        "valid_from": _guess_from(edge, nodes),
        "valid_to": "",
        "source": source,
        "inferred": bool(props.get("inferred")),
        "confidence": float(props.get("strength") or 0.7),
        "evidence": {
            "explanation": props.get("explanation") or "",
            "chain": props.get("evidence") if isinstance(props.get("evidence"), list) else [],
        },
    })


def stamp_edge(graph, fact):
    src, rel, tgt = fact["subject_id"], fact["predicate"], fact["object_id"]
    existing = None
    try:
        existing = graph.get_edge(f"{src}|{rel}|{tgt}")
    except Exception:
        existing = None
    props = dict((existing or {}).get("properties") or {})
    props["valid_from"] = fact.get("valid_from") or props.get("valid_from") or today()
    props["valid_to"] = fact.get("valid_to") or ""
    props["temporal_fact_id"] = fact["id"]
    props["confidence"] = fact.get("confidence") or props.get("confidence") or 1
    if fact.get("inferred"):
        props["inferred"] = True
    edge = relation_template(src, tgt, rel, **props)
    merged = dict(edge["properties"])
    merged.update(props)
    graph.upsert_edge(src, tgt, rel, merged, record_history=False)


def replay_closed_facts(graph, nodes):
    """把已关闭但重建时丢掉的历史边写回图谱（带 valid_to），供时间查询。"""
    store = get_temporal_store()
    written = 0
    for fact in store.list_facts():
        if not fact.get("valid_to"):
            continue
        src, tgt = fact["subject_id"], fact["object_id"]
        if src not in nodes and tgt not in nodes:
            continue
        key = f"{src}|{fact['predicate']}|{tgt}"
        existing = None
        try:
            existing = graph.get_edge(key)
        except Exception:
            existing = None
        if existing:
            props = existing.get("properties") or {}
            if not props.get("valid_to"):
                continue
        stamp_edge(graph, fact)
        written += 1
    return written


def apply_lifecycles(graph, members=None):
    store = get_temporal_store()
    nodes = {n["id"]: n for n in _list_nodes(graph)}
    seeded = 0
    for n in nodes.values():
        lc = store.get_lifecycle(n["id"])
        if not lc and n.get("type") == "Person":
            vf = parse_day(n.get("join_date")) or parse_day(n.get("valid_from")) or ""
            lc = store.upsert_lifecycle({
                "entity_id": n["id"],
                "entity_type": "Person",
                "status": LIFECYCLE_ACTIVE,
                "valid_from": vf,
                "valid_to": "",
            })
            seeded += 1
        if not lc:
            continue
        n["lifecycle_status"] = lc.get("status") or LIFECYCLE_ACTIVE
        n["valid_from"] = lc.get("valid_from") or n.get("valid_from") or ""
        n["valid_to"] = lc.get("valid_to") or ""
        graph.upsert_node(n)
    return seeded


def persist_inferred(graph):
    """语义推断边写入时态事实，时间取前提交集（已写在边属性上）。"""
    store = get_temporal_store()
    nodes = {n["id"]: n for n in _list_nodes(graph)}
    count = 0
    for e in _list_edges(graph):
        props = e.get("properties") or {}
        if not props.get("inferred"):
            continue
        vf, vt = props.get("valid_from"), props.get("valid_to") or ""
        open_fact = store.find_open(e["source"], e["relation"], e["target"])
        if open_fact:
            stamp_edge(graph, open_fact)
            continue
        store.insert_fact({
            "subject_id": e["source"],
            "predicate": e["relation"],
            "object_id": e["target"],
            "valid_from": parse_day(vf) or _guess_from(e, nodes),
            "valid_to": parse_day(vt) or "",
            "source": "reasoning",
            "inferred": True,
            "evidence": {
                "explanation": props.get("explanation") or "",
                "chain": props.get("evidence") if isinstance(props.get("evidence"), list) else [],
                "rule": props.get("rule_name"),
            },
        })
        count += 1
    return count


def sync_after_rebuild(graph=None):
    """重建后：观察当前边、对齐互斥事实、回放历史边、打生命周期。"""
    graph = graph or get_facade()
    store = get_temporal_store()
    nodes = {n["id"]: n for n in _list_nodes(graph)}
    observed = 0
    for e in _list_edges(graph):
        if observe_edge(e, nodes):
            observed += 1
    for e in _list_edges(graph):
        src, rel, tgt = e.get("source"), e.get("relation"), e.get("target")
        fact = store.find_open(src, rel, tgt)
        if fact:
            stamp_edge(graph, fact)
    replayed = replay_closed_facts(graph, nodes)
    inferred = persist_inferred(graph)
    seeded = apply_lifecycles(graph)
    store.add_snapshot(today(), graph_version="rebuild", stats={
        "observed": observed, "replayed": replayed, "inferred": inferred,
    })
    return {
        "observed_facts": observed,
        "replayed_closed": replayed,
        "inferred_facts": inferred,
        "lifecycle_seeded": seeded,
        "open_facts": len(store.list_facts(open_only=True)),
        "all_facts": len(store.list_facts()),
    }


def current_graph(graph=None, as_of=None):
    if as_of:
        return snapshot(as_of, graph)
    graph = graph or get_facade()
    nodes = _list_nodes(graph)
    edges = filter_current_edges(_list_edges(graph), today())
    return {"as_of": today(), "nodes": nodes, "edges": edges, "current": True}


def influence_window(nodes, edges, date_from=None, date_to=None, as_of=None):
    from organization_graph.algorithms.influence import compute_influence
    from timeutil import intervals_overlap

    if as_of:
        snap = snapshot(as_of)
        return compute_influence(snap["nodes"], snap["edges"]), snap

    if date_from or date_to:
        start = parse_day(date_from) or "0001-01-01"
        end = parse_day(date_to) or today()
        picked = []
        for e in edges:
            props = e.get("properties") or {}
            vf, vt = props.get("valid_from"), props.get("valid_to")
            if not vf and not vt:
                picked.append(e)
                continue
            if intervals_overlap(vf, vt, start, end):
                picked.append(e)
        return compute_influence(nodes, picked), {"from": start, "to": end, "edge_count": len(picked)}

    return compute_influence(nodes, filter_current_edges(edges)), {"as_of": today()}


def overview():
    store = get_temporal_store()
    facts = store.list_facts()
    open_n = sum(1 for f in facts if not f.get("valid_to"))
    return {
        "fact_count": len(facts),
        "open_facts": open_n,
        "closed_facts": len(facts) - open_n,
        "events": len(store.list_events(limit=500)),
        "event_types": TEMPORAL_EVENT_TYPES,
        "snapshots": store.list_snapshots(8),
    }
