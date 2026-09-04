"""按时间点 / 时间窗查询时态事实，组装图谱快照。"""

from timeutil import interval_contains, intervals_overlap, parse_day, today

from organization_graph.repository.facade import get_facade

from .repository import get_temporal_store
from .types import LIFECYCLE_ACTIVE


def edge_valid_at(edge, when):
    props = edge.get("properties") or {}
    return interval_contains(props.get("valid_from"), props.get("valid_to"), when)


def filter_current_edges(edges, when=None):
    when = when or today()
    out = []
    for e in edges:
        props = e.get("properties") or {}
        if not props.get("valid_from") and not props.get("valid_to"):
            out.append(e)
            continue
        if edge_valid_at(e, when):
            out.append(e)
    return out


def node_alive_at(node, when, lifecycle=None):
    if lifecycle:
        if not interval_contains(lifecycle.get("valid_from"), lifecycle.get("valid_to") or None, when):
            if lifecycle.get("valid_from"):
                return False
        if lifecycle.get("status") == "INACTIVE":
            end = parse_day(lifecycle.get("valid_to"))
            day = parse_day(when)
            if end and day and day >= end:
                return False
            if not end:
                return False
        return True
    vf = node.get("valid_from")
    vt = node.get("valid_to")
    if vf or vt:
        return interval_contains(vf, vt, when)
    status = node.get("lifecycle_status") or LIFECYCLE_ACTIVE
    if status == "INACTIVE":
        return interval_contains(node.get("valid_from"), node.get("valid_to"), when)
    return True


def facts_to_edges(facts, nodes_by_id=None):
    edges = []
    for f in facts:
        src, tgt = f["subject_id"], f["object_id"]
        evidence = f.get("evidence") if isinstance(f.get("evidence"), list) else []
        explanation = ""
        if isinstance(f.get("evidence"), dict):
            explanation = f["evidence"].get("explanation") or ""
            evidence = f["evidence"].get("chain") or []
        edges.append({
            "id": f"{src}|{f['predicate']}|{tgt}",
            "source": src,
            "target": tgt,
            "relation": f["predicate"],
            "properties": {
                "valid_from": f.get("valid_from") or "",
                "valid_to": f.get("valid_to") or "",
                "confidence": f.get("confidence") or 1,
                "inferred": bool(f.get("inferred")),
                "temporal_fact_id": f["id"],
                "source_event": f.get("source_event_id") or "",
                "evidence": evidence,
                "explanation": explanation,
                "strength": 0.55,
            },
        })
    return edges


def snapshot(when, graph=None):
    """某日组织状态：当时有效的人/项目/资源/关系。"""
    when = parse_day(when) or today()
    store = get_temporal_store()
    graph = graph or get_facade()
    try:
        nodes = graph.list_nodes(include_merged=False)
    except TypeError:
        nodes = graph.list_nodes()
    life = {x["entity_id"]: x for x in store.list_lifecycles()}
    alive = []
    for n in nodes:
        if (n.get("entity_status") or "ACTIVE") == "MERGED":
            continue
        if node_alive_at(n, when, life.get(n["id"])):
            rec = dict(n)
            lc = life.get(n["id"])
            if lc:
                rec["lifecycle_status"] = lc.get("status")
                rec["valid_from"] = lc.get("valid_from") or rec.get("valid_from")
                rec["valid_to"] = lc.get("valid_to") or rec.get("valid_to")
            alive.append(rec)
    by_id = {n["id"]: n for n in alive}
    facts = store.facts_as_of(when)
    edges = []
    for e in facts_to_edges(facts):
        if e["source"] in by_id and e["target"] in by_id:
            edges.append(e)
        elif e["source"] in by_id or e["target"] in by_id:
            # 对端节点可能未出现在当前重建图，仍保留事实
            edges.append(e)
    return {
        "as_of": when,
        "nodes": alive,
        "edges": edges,
        "fact_count": len(facts),
    }


def range_participants(object_id, start, end, predicates=None):
    store = get_temporal_store()
    start, end = parse_day(start), parse_day(end) or today()
    facts = store.facts_overlapping(start, end, object_id=object_id)
    if predicates:
        allowed = set(predicates)
        facts = [f for f in facts if f["predicate"] in allowed]
    people = []
    seen = set()
    for f in facts:
        sid = f["subject_id"]
        if sid in seen:
            continue
        seen.add(sid)
        people.append({
            "id": sid,
            "predicate": f["predicate"],
            "valid_from": f.get("valid_from"),
            "valid_to": f.get("valid_to") or "今",
            "fact_id": f["id"],
        })
    return {"object_id": object_id, "from": start, "to": end, "participants": people}


def person_timeline(person_id):
    store = get_temporal_store()
    facts = store.list_facts(subject_id=person_id) + [
        f for f in store.list_facts(object_id=person_id) if f["subject_id"] != person_id
    ]
    events = store.list_events(limit=200, entity_id=person_id)
    names = {}
    try:
        for n in get_facade().list_nodes():
            names[n["id"]] = n.get("name") or n["id"]
    except Exception:
        pass
    items = []
    for f in facts:
        items.append({
            "kind": "fact",
            "time": f.get("valid_from"),
            "end": f.get("valid_to") or "",
            "predicate": f["predicate"],
            "subject_id": f["subject_id"],
            "subject_name": names.get(f["subject_id"], f["subject_id"]),
            "object_id": f["object_id"],
            "object_name": names.get(f["object_id"], f["object_id"]),
            "inferred": f.get("inferred"),
            "source_event_id": f.get("source_event_id"),
            "id": f["id"],
        })
    for ev in events:
        items.append({
            "kind": "event",
            "time": ev.get("event_time"),
            "end": "",
            "predicate": ev.get("event_type"),
            "description": ev.get("description"),
            "id": ev["id"],
            "payload": ev.get("payload"),
        })
    items.sort(key=lambda x: (x.get("time") or "", x.get("kind") or ""))
    return {"person_id": person_id, "items": items, "lifecycle": store.get_lifecycle(person_id)}


def project_timeline(project_id):
    store = get_temporal_store()
    facts = store.list_facts(object_id=project_id) + store.list_facts(subject_id=project_id)
    events = store.list_events(limit=200, entity_id=project_id)
    phases = [e for e in events if e.get("event_type") in (
        "PROJECT_START", "PROJECT_PHASE_CHANGE", "PROJECT_COMPLETE", "PROJECT_OWNER_CHANGE",
    )]
    return {
        "project_id": project_id,
        "facts": facts,
        "events": events,
        "phases": phases,
    }
