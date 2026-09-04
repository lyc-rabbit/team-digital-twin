"""知识图谱语义治理：分析 → 工单确认 → 写图。不删节点、不改 type。"""

from organization_graph.ontology.relations import relation_template
from organization_graph.repository.facade import get_facade

from .analyzer import analyze_graph, suppress_handled_issues
from .discovery import discover_ontology
from .reasoning import apply_rules, explanation_from_chain
from .relations import INFERRED_FLAG
from .repository import get_kg_store
from .seed import GRAPH_TO_ONTOLOGY, seed_ontology, ensure_property_schemas
from . import workitems
from .schema import (
    compile_constraints,
    fill_property,
    normalize_relation_rule,
    normalize_type_schema,
    properties_of,
    schema_value,
)

# 人员来自成员模块，本体页不能下线。部门/角色等可下线，重建时按 id 或「类型+名称」跳过。
PROTECTED_TYPES = {"Person"}


def _graph(store=None):
    return store or get_facade()


def _list_nodes(store):
    try:
        return store.list_nodes(include_merged=False)
    except TypeError:
        return store.list_nodes()


def _list_edges(store):
    try:
        return store.list_edges(include_merged=False)
    except TypeError:
        return store.list_edges()


def ensure_seeded():
    result = seed_ontology(force=False)
    ensure_property_schemas()
    return result


def analyze(store=None):
    ensure_seeded()
    report = analyze_graph(store)
    report = suppress_handled_issues(report)
    report["ontology_seeded"] = bool(get_kg_store().list_types())
    return report


def ontology_draft(store=None):
    ensure_seeded()
    return discover_ontology(store)


def type_tree(store=None):
    ensure_seeded()
    kg = get_kg_store()
    types = kg.list_types()
    by_id = {t["id"]: dict(t, children=[], members=[], unclassified=[]) for t in types}
    roots = []
    for t in by_id.values():
        pid = t.get("parent_id")
        if pid and pid in by_id:
            by_id[pid]["children"].append(t)
        else:
            roots.append(t)

    graph = _graph(store)
    nodes = _list_nodes(graph)
    suppressed_ids = kg.suppressed_node_ids()
    suppressed_keys = kg.suppressed_keys()
    name_to_type = {t["name"]: t for t in by_id.values()}
    open_ids = {
        i.get("object_id")
        for i in kg.list_work_items(status="open", page_size=2000)["items"]
        if i.get("object_type") == "node"
    }
    for n in nodes:
        if n.get("id") in suppressed_ids:
            continue
        key = (n.get("type") or "", (n.get("name") or "").strip())
        if key[1] and key in suppressed_keys:
            continue
        onto = n.get("ontology_type")
        rec = name_to_type.get(onto) if onto else None
        desc = (n.get("description") or n.get("name") or "").strip()
        summary = {
            "id": n["id"],
            "name": n.get("name"),
            "description": desc,
            "graph_type": n.get("type"),
            "ontology_type": onto or "",
            "resource_kind": n.get("resource_kind"),
            "has_open_item": n["id"] in open_ids,
            "deletable": n.get("type") not in PROTECTED_TYPES,
        }
        if rec is not None:
            rec["members"].append(summary)
        else:
            mapped = GRAPH_TO_ONTOLOGY.get(n.get("type"), n.get("type"))
            bucket = name_to_type.get(mapped)
            if bucket is not None:
                bucket["unclassified"].append(summary)
    types_out = []
    for t in types:
        rec = by_id[t["id"]]
        rec["deletable"] = (
            not rec["children"]
            and not rec["members"]
            and not rec["unclassified"]
        )
        types_out.append({
            **t,
            "member_count": len(rec["members"]),
            "unclassified_count": len(rec["unclassified"]),
            "deletable": rec["deletable"],
        })
    return {"roots": roots, "types": types_out, "relations": kg.list_ontology_relations()}


def compiled_schema():
    ensure_seeded()
    kg = get_kg_store()
    types = kg.list_types()
    relations = [
        {**r, "rule": normalize_relation_rule(r.get("rule"))}
        for r in kg.list_ontology_relations()
    ]
    extras = kg.list_constraints(include_inactive=True)
    return {
        "types": [
            {**t, "schema": normalize_type_schema(t["name"], t.get("schema")), "properties": properties_of(t)}
            for t in types
        ],
        "relations": relations,
        "constraints": compile_constraints(types, relations, extras),
        "manual_constraints": extras,
    }


def save_type_properties(tid, properties):
    kg = get_kg_store()
    existing = kg.get_type(tid)
    if not existing:
        raise ValueError("类型不存在")
    kg.snapshot(reason=f"type-properties:{existing['name']}")
    schema = dict(existing.get("schema") or {})
    schema["properties"] = [fill_property(p) for p in (properties or [])]
    schema = normalize_type_schema(existing["name"], schema)
    return kg.upsert_type({**existing, "schema": schema})


def save_ontology_relation(payload):
    kg = get_kg_store()
    kg.snapshot(reason="upsert-relation-schema")
    rec = dict(payload or {})
    if not rec.get("name") or not rec.get("source_type") or not rec.get("target_type"):
        raise ValueError("关系名、源类型、目标类型必填")
    rec["rule"] = normalize_relation_rule(rec.get("rule"))
    existing = None
    if rec.get("id"):
        existing = kg.get_ontology_relation(rec["id"])
    if not existing:
        existing = kg.find_ontology_relation(rec["name"], rec["source_type"], rec["target_type"])
    if existing:
        rec["id"] = existing["id"]
    return kg.upsert_ontology_relation(rec)


def delete_ontology_relation(rid):
    kg = get_kg_store()
    existing = kg.get_ontology_relation(rid)
    if not existing:
        raise ValueError("关系定义不存在")
    kg.snapshot(reason=f"delete-relation:{existing.get('name')}")
    return kg.delete_ontology_relation(rid)


def save_constraint(payload):
    kg = get_kg_store()
    kg.snapshot(reason="upsert-constraint")
    rec = dict(payload or {})
    if not rec.get("name") or not rec.get("kind"):
        raise ValueError("约束名称与种类必填")
    return kg.upsert_constraint(rec)


def delete_constraint(cid):
    kg = get_kg_store()
    existing = kg.get_constraint(cid)
    if not existing:
        raise ValueError("约束不存在")
    if str(existing.get("id") or "").startswith("auto:"):
        raise ValueError("Schema 编译出的约束请改属性/关系定义，不能直接删")
    kg.snapshot(reason=f"delete-constraint:{existing.get('name')}")
    return kg.delete_constraint(cid)


def _strip_unconfirmed_inferred(store):
    """只去掉未确认的推断边，已确认的留下。"""
    removed = 0
    for e in _list_edges(store):
        props = e.get("properties") or {}
        if not (props.get(INFERRED_FLAG) or props.get("inferred")):
            continue
        if props.get("confirmed"):
            continue
        store.delete_edge(e["source"], e["target"], e["relation"])
        removed += 1
    return removed


def _is_inferred_edge(edge):
    props = edge.get("properties") or {}
    return bool(props.get(INFERRED_FLAG) or props.get("inferred"))


def _allowed_relation(kg, src_node, relation, tgt_node, type_index, parent_of):
    specs = [r for r in kg.list_ontology_relations() if r.get("name") == relation]
    if not specs:
        return True
    src_onto = (src_node or {}).get("ontology_type") or GRAPH_TO_ONTOLOGY.get((src_node or {}).get("type"))
    tgt_onto = (tgt_node or {}).get("ontology_type") or GRAPH_TO_ONTOLOGY.get((tgt_node or {}).get("type"))
    for spec in specs:
        if _is_subtype(src_onto, spec["source_type"], parent_of) and _is_subtype(
            tgt_onto, spec["target_type"], parent_of
        ):
            return True
    return False


def _is_subtype(actual, allowed, parent_of):
    if not actual or not allowed:
        return True
    if actual == allowed:
        return True
    seen = set()
    cur = actual
    while cur and cur not in seen:
        seen.add(cur)
        if cur == allowed:
            return True
        cur = parent_of.get(cur)
    return False


def _parent_map(kg):
    types = kg.list_types()
    by_id = {t["id"]: t for t in types}
    parent_of = {}
    for t in types:
        parent = by_id.get(t.get("parent_id"))
        parent_of[t["name"]] = parent["name"] if parent else None
    return parent_of, {t["name"]: t for t in types}


def _write_inferred(store, recs, nodes, kg):
    node_map = {n["id"]: n for n in nodes}
    parent_of, type_index = _parent_map(kg)
    written = 0
    skipped = 0
    existing = {(e["source"], e["relation"], e["target"]) for e in _list_edges(store)}
    for rec in recs:
        src, rel, tgt = rec["source"], rec["relation"], rec["target"]
        if (src, rel, tgt) in existing:
            skipped += 1
            continue
        if not _allowed_relation(kg, node_map.get(src), rel, node_map.get(tgt), type_index, parent_of):
            skipped += 1
            continue
        props = dict(rec.get("properties") or {})
        edge = relation_template(src, tgt, rel, **props)
        merged = dict(edge.get("properties") or {})
        merged.update(props)
        store.upsert_edge(src, tgt, rel, merged, record_history=False)
        existing.add((src, rel, tgt))
        written += 1
    return written, skipped


def enhance_graph(store=None, generate_suggestions=True, mode="propose"):
    """重建/刷新默认 propose：只产工单并回放已确认项，不自动分类、不写未确认推断边。"""
    return propose_semantics(store, source="rebuild" if mode == "propose" else "analyze")


def propose_semantics(store=None, source="analyze", force=False):
    ensure_seeded()
    graph = _graph(store)
    kg = get_kg_store()
    stripped = _strip_unconfirmed_inferred(graph)
    nodes = _list_nodes(graph)
    edges = _list_edges(graph)
    inferred = apply_rules(nodes, edges, kg.list_rules())
    report = analyze_graph(graph)
    published = {"created": 0, "updated": 0}
    published = workitems.publish_work_items(
        report, inferred_candidates=inferred, store=graph, source=source, force=force,
    )
    replayed = workitems.replay_accepted(graph)
    report["work_items"] = published
    report["replayed"] = replayed
    report["stripped_unconfirmed_inferred"] = stripped
    report["inferred_candidates"] = len(inferred)
    report["mode"] = "propose"
    return suppress_handled_issues(report)


def apply_confirmed(store=None):
    return workitems.replay_accepted(_graph(store))


def apply_ontology_draft(store=None):
    """不再整包写图，只生成待确认工单。"""
    return propose_semantics(store, source="analyze")


def list_inferred(store=None, limit=80):
    graph = _graph(store)
    nodes = {n["id"]: n for n in _list_nodes(graph)}
    out = []
    for e in _list_edges(graph):
        if not _is_inferred_edge(e):
            continue
        props = e.get("properties") or {}
        if not props.get("confirmed"):
            continue
        ev = props.get("evidence") or []
        if not isinstance(ev, list):
            ev = []
        src = nodes.get(e["source"]) or {}
        tgt = nodes.get(e["target"]) or {}
        out.append({
            "id": e.get("id"),
            "source": e["source"],
            "source_name": src.get("name") or e["source"],
            "target": e["target"],
            "target_name": tgt.get("name") or e["target"],
            "relation": e["relation"],
            "rule_id": props.get("rule_id"),
            "rule_name": props.get("rule_name"),
            "evidence": ev,
            "explanation": props.get("explanation") or explanation_from_chain(
                ev,
                (
                    e["source"], e["relation"], e["target"],
                    src.get("name") or e["source"], tgt.get("name") or e["target"],
                ),
            ),
        })
        if len(out) >= limit:
            break
    return out


def upsert_type(payload):
    kg = get_kg_store()
    kg.snapshot(reason="upsert-type")
    rec = kg.upsert_type(payload)
    kg.unretire_type_name(rec.get("name"))
    return rec


def merge_types(source_id, target_id, store=None):
    kg = get_kg_store()
    source = kg.get_type(source_id)
    target = kg.get_type(target_id)
    if not source or not target:
        raise ValueError("类型不存在")
    if source["id"] == target["id"]:
        raise ValueError("不能与自身合并")
    kg.snapshot(reason=f"merge-type:{source['name']}->{target['name']}")
    for t in kg.list_types():
        if t.get("parent_id") == source["id"]:
            kg.upsert_type({**t, "parent_id": target["id"]})
    graph = _graph(store)
    for n in _list_nodes(graph):
        if n.get("ontology_type") == source["name"]:
            n["ontology_type"] = target["name"]
            graph.upsert_node(n)
    kg.delete_type(source["id"])
    kg.retire_type_name(source.get("name"))
    after = len(_list_nodes(graph))
    return {
        "merged": source["name"],
        "into": target["name"],
        "graph_nodes_unchanged": True,
        "node_count": after,
        "note": "只合并本体类型，不会把图里的人/事件合成一个节点。",
    }


def delete_ontology_type(tid, store=None):
    kg = get_kg_store()
    existing = kg.get_type(tid)
    if not existing:
        raise ValueError("类型不存在")
    tname = existing.get("name")
    if tname == "Person":
        raise ValueError("Person 是核心类型，不能从本体删除")
    if any(t.get("parent_id") == tid for t in kg.list_types()):
        raise ValueError("还有子类型，请先删除或移走子节点")
    graph = _graph(store)
    suppressed_ids = kg.suppressed_node_ids()
    suppressed_keys = kg.suppressed_keys()
    used = []
    for n in _list_nodes(graph):
        if n.get("id") in suppressed_ids:
            continue
        key = (n.get("type") or "", (n.get("name") or "").strip())
        if key[1] and key in suppressed_keys:
            continue
        onto = n.get("ontology_type")
        mapped = GRAPH_TO_ONTOLOGY.get(n.get("type"), n.get("type"))
        if onto == tname or (not onto and mapped == tname):
            used.append(n)
    if used:
        raise ValueError("该类型下还有图实例，请先下线或重分类")
    kg.snapshot(reason=f"delete-type:{existing['name']}")
    for rel in kg.list_ontology_relations():
        if rel.get("source_type") == tname or rel.get("target_type") == tname:
            kg.delete_ontology_relation(rel["id"])
    kg.retire_type_name(tname)
    kg.delete_type(tid)
    return {"deleted": existing["name"], "id": tid, "graph_nodes_unchanged": True}


def accept_suggestion(sid, store=None, proposed=None):
    return accept_work_item(sid, store=store, proposed=proposed)


def accept_work_item(sid, store=None, proposed=None):
    kg = get_kg_store()
    item = kg.get_suggestion(sid)
    if not item:
        raise ValueError("工单不存在")
    if item.get("status") not in ("open", "pending", "deferred"):
        raise ValueError("只能确认待处理工单")
    graph = _graph(store)
    merged_proposed = dict(item.get("proposed") or item.get("payload") or {})
    if proposed:
        merged_proposed.update(proposed)
    applied = workitems.apply_work_item(item, graph, proposed=merged_proposed)
    kg.update_suggestion(sid, status="accepted", proposed=merged_proposed, applied=applied, payload=merged_proposed)
    return kg.get_suggestion(sid)


def ignore_suggestion(sid):
    return reject_work_item(sid)


def reject_work_item(sid):
    kg = get_kg_store()
    if not kg.get_suggestion(sid):
        raise ValueError("工单不存在")
    return kg.update_suggestion(sid, status="rejected")


def defer_work_item(sid):
    kg = get_kg_store()
    if not kg.get_suggestion(sid):
        raise ValueError("工单不存在")
    return kg.update_suggestion(sid, status="deferred")


def patch_work_item(sid, proposed):
    kg = get_kg_store()
    item = kg.get_suggestion(sid)
    if not item:
        raise ValueError("工单不存在")
    if item.get("status") not in ("open", "pending", "deferred"):
        raise ValueError("终态工单不能改建议")
    merged = dict(item.get("proposed") or item.get("payload") or {})
    merged.update(proposed or {})
    return kg.update_suggestion(sid, proposed=merged, payload=merged)


def instance_detail(node_id, store=None):
    graph = _graph(store)
    node = graph.get_node(node_id)
    if not node:
        raise ValueError("实例不存在")
    kg = get_kg_store()
    onto = node.get("ontology_type") or GRAPH_TO_ONTOLOGY.get(node.get("type"), node.get("type"))
    type_rec = kg.get_type_by_name(onto) if onto else None
    schema_props = []
    declared = set()
    if type_rec:
        for prop in properties_of(type_rec):
            name = prop["name"]
            declared.add(name)
            schema_props.append({
                "name": name,
                "label": prop.get("label") or name,
                "description": prop.get("description") or "",
                "data_type": prop.get("data_type") or "String",
                "value": schema_value(node, prop, type_rec),
                "raw": node.get(name),
            })
    extras = []
    for key, value in node.items():
        if key in declared or key == "id":
            continue
        extras.append({"name": key, "value": value})
    neighbors = []
    try:
        edges = graph.list_edges(include_merged=False)
    except TypeError:
        edges = graph.list_edges()
    related = [e for e in edges if e.get("source") == node_id or e.get("target") == node_id]
    for e in related[:80]:
        outbound = e.get("source") == node_id
        other_id = e.get("target") if outbound else e.get("source")
        other = graph.get_node(other_id) or {}
        neighbors.append({
            "id": e.get("id"),
            "relation": e.get("relation"),
            "direction": "out" if outbound else "in",
            "other_id": other_id,
            "other_name": other.get("name") or other_id,
            "other_type": other.get("type") or "",
            "other_ontology_type": other.get("ontology_type") or "",
        })
    return {
        "id": node.get("id"),
        "name": node.get("name"),
        "graph_type": node.get("type"),
        "ontology_type": onto or "",
        "entity_status": node.get("entity_status") or "ACTIVE",
        "description": node.get("description") or node.get("profile") or "",
        "node": node,
        "schema_properties": schema_props,
        "extras": extras,
        "edges": neighbors,
        "edge_count": len(related),
    }


def classify_instance_ticket(node_id, store=None, type_id=None, ontology_type=None):
    graph = _graph(store)
    node = graph.get_node(node_id)
    if not node:
        raise ValueError("节点不存在")
    return workitems.open_classify_item(
        node, preferred_type=ontology_type, preferred_type_id=type_id,
    )


def retire_instance(node_id, store=None):
    """抽取错误：下线图实例，不物理删除。重建时跳过。"""
    graph = _graph(store)
    node = graph.get_node(node_id)
    if not node:
        raise ValueError("节点不存在")
    if node.get("type") in PROTECTED_TYPES:
        raise ValueError("人员不能从本体页删除，请到成员模块处理")
    kg = get_kg_store()
    source_event_id = ""
    if str(node_id).startswith("event_"):
        source_event_id = str(node_id)[6:]
    kg.add_suppressed_instance({
        "node_id": node_id,
        "graph_type": node.get("type"),
        "name": node.get("name"),
        "source_event_id": source_event_id,
    })
    node["entity_status"] = "RETIRED"
    graph.upsert_node(node)
    closed = 0
    pending = []
    for status in ("open", "deferred"):
        pending.extend(kg.list_work_items(status=status, page_size=5000)["items"])
    seen = set()
    for item in pending:
        iid = item.get("id")
        if iid in seen:
            continue
        seen.add(iid)
        oid = item.get("object_id")
        proposed = item.get("proposed") or {}
        current = item.get("current") or {}
        involved = {
            oid,
            proposed.get("node_id"),
            proposed.get("source"),
            proposed.get("target"),
            current.get("source"),
            current.get("target"),
        }
        if node_id in involved:
            kg.update_suggestion(iid, status="resolved", reason="实例已下线，工单自动关闭。")
            closed += 1
    return {"id": node_id, "status": "RETIRED", "graph_nodes_deleted": False, "closed_work_items": closed}


def overview(store=None):
    ensure_seeded()
    report = suppress_handled_issues(analyze_graph(store))
    kg = get_kg_store()
    open_n = kg.list_work_items(status="open", page_size=1)["total"]
    return {
        "analysis": report,
        "types": len(kg.list_types()),
        "rules": len(kg.list_rules()),
        "pending_suggestions": open_n,
        "open_work_items": open_n,
        "inferred": len(list_inferred(store, limit=500)),
        "revisions": kg.list_revisions(8),
    }


def rollback_ontology(revision_id):
    return get_kg_store().rollback(revision_id)
