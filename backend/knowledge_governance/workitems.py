"""工单：指纹去重、分析发布、确认写图、重建回放。"""

from organization_graph.ontology.relations import relation_template
from organization_graph.ontology.resources import RESOURCE_CLASS_NAMES
from timeutil import parse_day

from .discovery import classify_node
from .relations import REL_IS_A, REL_PART_OF, REL_USES
from .repository import get_kg_store
from .schema import schema_storage_field
from .seed import GRAPH_TO_ONTOLOGY


def _endpoint_meta(node_map, nid):
    n = (node_map or {}).get(nid) or {}
    return {
        "id": nid,
        "name": n.get("name") or nid or "",
        "graph_type": n.get("type") or "",
        "ontology_type": n.get("ontology_type") or "",
    }


def _edge_ends(node_map, src, tgt):
    s = _endpoint_meta(node_map, src)
    t = _endpoint_meta(node_map, tgt)
    return {
        "source": src,
        "target": tgt,
        "source_name": s["name"],
        "target_name": t["name"],
        "source_type": s["graph_type"],
        "target_type": t["graph_type"],
    }


def fingerprint(suggestion_type, object_type, object_id, extra=""):
    parts = [suggestion_type or "", object_type or "", str(object_id or "")]
    if extra:
        parts.append(str(extra))
    return "|".join(parts)


def _clean_day(value):
    day = parse_day(value)
    if not day or day.startswith("0001"):
        return ""
    return day


def _edge_times(proposed):
    current_time = (proposed.get("current_time") or "").replace(" ", "T")
    valid_from = _clean_day(proposed.get("valid_from"))
    valid_to = _clean_day(proposed.get("valid_to"))
    return {
        "valid_from": valid_from,
        "valid_to": valid_to,
        "current_time": current_time or (f"{valid_from}T00:00:00" if valid_from else ""),
    }


def _graph_nodes_edges(store):
    try:
        nodes = store.list_nodes(include_merged=False)
        edges = store.list_edges(include_merged=False)
    except TypeError:
        nodes = store.list_nodes()
        edges = store.list_edges()
    return nodes, edges


def publish_work_items(report, inferred_candidates=None, store=None, source="analyze", force=False):
    """只 upsert open 工单，不写图。已 accepted/rejected 默认跳过。"""
    kg = get_kg_store()
    created, updated, skipped = 0, 0, 0
    items = []

    def _put(rec):
        nonlocal created, updated, skipped
        rec["source"] = rec.get("source") or source
        item, is_new = kg.upsert_work_item(rec, force=force)
        if item and item.get("status") in ("accepted", "rejected", "deferred") and not is_new:
            skipped += 1
        elif is_new:
            created += 1
        else:
            updated += 1
        items.append(item)
        return item

    nodes, edges = _graph_nodes_edges(store) if store else ([], [])
    node_map = {n["id"]: n for n in nodes}
    existing_edges = {(e["source"], e["relation"], e["target"]) for e in edges}

    for amb in report.get("ambiguous_names") or []:
        types = amb.get("types") or []
        for n in amb.get("nodes") or []:
            nid = n.get("id")
            _put({
                "fingerprint": fingerprint("CLASSIFY_INSTANCE", "node", nid),
                "suggestion_type": "CLASSIFY_INSTANCE",
                "object_type": "node",
                "object_id": nid,
                "problem_code": "NAME_TYPE_AMBIGUITY",
                "title": f"「{amb.get('name')}」可能不是 {n.get('type')}",
                "reason": f"同名节点同时出现为 {('、'.join(types))}。请确认本体类，不要改图谱 type。",
                "confidence": 0.7,
                "current": {"graph_type": n.get("type"), "name": amb.get("name")},
                "proposed": {
                    "node_id": nid,
                    "graph_type": n.get("type"),
                    "current_ontology_type": n.get("type"),
                    "proposed_ontology_type": types[0] if types else n.get("type"),
                    "candidates": sorted(set(types + [GRAPH_TO_ONTOLOGY.get(t, t) for t in types])),
                },
            })

    for item in report.get("hierarchy_candidates") or []:
        child_id = item.get("child_id")
        child = item.get("child") or ""
        if not child_id or child in RESOURCE_CLASS_NAMES:
            continue
        _put({
            "fingerprint": fingerprint("HIERARCHY_REFACTOR", "node", child_id),
            "suggestion_type": "HIERARCHY_REFACTOR",
            "object_type": "node",
            "object_id": child_id,
            "problem_code": "CLASS_INSTANCE_MIX",
            "title": f"「{child}」应挂在「{item.get('parent')}」下",
            "reason": (
                f"{item.get('reason') or ''} 当前是 Resource 实例。"
                f"建议本体类 {item.get('suggested_ontology')}，并 IS_A 总类。"
                "交付资源 ≠ 越南代理交付资源，禁止实体合并。"
            ),
            "confidence": 0.9 if str(child).endswith(str(item.get("parent") or "")) else 0.75,
            "current": {
                "child": child,
                "already_linked": item.get("already_linked"),
                "graph_type": "Resource",
            },
            "proposed": {
                "child_id": child_id,
                "child_name": child,
                "parent_id": item.get("parent_id"),
                "parent_name": item.get("parent"),
                "proposed_ontology_type": item.get("suggested_ontology") or "DeliveryResource",
                "do_not_merge": True,
            },
        })

    for mix in report.get("class_instance_mix") or []:
        if mix.get("kind") != "instance":
            continue
        mid = mix.get("id")
        if not mid:
            continue
        if any(h.get("child_id") == mid for h in report.get("hierarchy_candidates") or []):
            continue
        node = node_map.get(mid) or {"id": mid, "name": mix.get("name"), "type": "Resource"}
        onto = classify_node(node) or GRAPH_TO_ONTOLOGY.get(node.get("type"), "Resource")
        _put({
            "fingerprint": fingerprint("CLASSIFY_INSTANCE", "node", mid),
            "suggestion_type": "CLASSIFY_INSTANCE",
            "object_type": "node",
            "object_id": mid,
            "problem_code": "CLASS_INSTANCE_MIX",
            "title": f"「{mix.get('name')}」与总类同为 Resource，建议标明本体类",
            "reason": "总类与明细都是 type=Resource。只改 ontology_type 并可选 IS_A，禁止实体合并。",
            "confidence": 0.72,
            "current": {"graph_type": node.get("type"), "name": mix.get("name")},
            "proposed": {
                "node_id": mid,
                "graph_type": node.get("type"),
                "current_ontology_type": node.get("ontology_type") or node.get("type"),
                "proposed_ontology_type": onto,
                "candidates": sorted({onto, "Resource", "DeliveryResource", "Knowledge", "Event", "Project"}),
            },
        })

    for cluster in report.get("clusters") or []:
        onto = cluster.get("ontology_type")
        for m in cluster.get("members") or []:
            mid = m.get("id")
            if not mid:
                continue
            _put({
                "fingerprint": fingerprint("CLASSIFY_INSTANCE", "node", mid),
                "suggestion_type": "CLASSIFY_INSTANCE",
                "object_type": "node",
                "object_id": mid,
                "problem_code": "FLAT_RESOURCE_FAMILY",
                "title": f"「{m.get('name')}」建议归入 {onto}",
                "reason": f"与同后缀「{cluster.get('cluster')}」实例成族，彼此不是同一实体。",
                "confidence": cluster.get("confidence") or 0.8,
                "current": {"graph_type": cluster.get("graph_type"), "name": m.get("name")},
                "proposed": {
                    "node_id": mid,
                    "graph_type": cluster.get("graph_type"),
                    "current_ontology_type": cluster.get("graph_type"),
                    "proposed_ontology_type": onto,
                    "candidates": sorted({onto, cluster.get("graph_type"), "Resource", "Knowledge", "Event", "Project"}),
                },
            })

    for weak in report.get("weak_relations") or []:
        eid = weak.get("id") or f"{weak.get('source')}|{weak.get('relation')}|{weak.get('target')}"
        rel = weak.get("relation") or ""
        proposed_rel = "USES" if rel == "HAS_RESOURCE" else (weak.get("suggest") or "USES")
        if "DEPENDS_ON" in str(proposed_rel):
            proposed_rel = "USES"
        _put({
            "fingerprint": fingerprint("WEAK_RELATION", "edge", eid),
            "suggestion_type": "WEAK_RELATION",
            "object_type": "edge",
            "object_id": eid,
            "problem_code": "WEAK_RELATION_SEMANTICS",
            "title": f"{rel} 可增强为 {proposed_rel}",
            "reason": weak.get("note") or "原边保留，确认后另写语义边，不删除 HAS_RESOURCE。",
            "confidence": 0.8 if rel == "HAS_RESOURCE" else 0.6,
            "current": {"relation": rel, **_edge_ends(node_map, weak.get("source"), weak.get("target"))},
            "proposed": {
                "edge_id": eid,
                **_edge_ends(node_map, weak.get("source"), weak.get("target")),
                "current_relation": rel,
                "proposed_relation": proposed_rel.split("/")[0].strip() if isinstance(proposed_rel, str) else "USES",
                "keep_original": True,
            },
        })

    for issue in report.get("schema_issues") or []:
        if issue.get("kind") not in ("enum", "enum_alias", "forbidden_property"):
            continue
        nid = issue.get("node_id")
        field = issue.get("field") or ""
        node = node_map.get(nid) or {}
        _put({
            "fingerprint": fingerprint("SCHEMA_FIX", "node", f"{nid}:{field}:{issue.get('kind')}"),
            "suggestion_type": "SCHEMA_FIX",
            "object_type": "node",
            "object_id": nid,
            "problem_code": "SCHEMA_VIOLATION",
            "title": f"「{issue.get('node_name')}」.{field} 不符合 Schema",
            "reason": issue.get("message") or "属性约束不满足。可规范属性、下线实例，或关闭工单。不改图谱节点类别 type。",
            "confidence": 0.82 if issue.get("kind") == "enum_alias" else 0.7,
            "current": {
                "field": field,
                "value": issue.get("value"),
                "kind": issue.get("kind"),
                "graph_type": node.get("type"),
                "node_name": issue.get("node_name"),
            },
            "proposed": {
                "node_id": nid,
                "field": field,
                "kind": issue.get("kind"),
                "proposed_value": issue.get("proposed_value"),
                "enum_values": issue.get("enum_values") or [],
                "clear_forbidden": issue.get("kind") == "forbidden_property",
            },
        })

    for issue in report.get("relation_schema_issues") or []:
        eid = issue.get("id") or f"{issue.get('source')}|{issue.get('relation')}|{issue.get('target')}"
        _put({
            "fingerprint": fingerprint("SCHEMA_RELATION", "edge", eid),
            "suggestion_type": "SCHEMA_RELATION",
            "object_type": "edge",
            "object_id": eid,
            "problem_code": "RELATION_NOT_IN_SCHEMA",
            "title": f"{issue.get('relation')} 不在关系 Schema",
            "reason": issue.get("note") or "关系不在当前 Schema。可更换关系或两端实例后写入，也可下线错误实例或关闭工单。不会自动删原边。",
            "confidence": 0.6,
            "current": {
                **(issue if isinstance(issue, dict) else {}),
                **_edge_ends(node_map, issue.get("source"), issue.get("target")),
            },
            "proposed": {
                **_edge_ends(node_map, issue.get("source"), issue.get("target")),
                "relation": issue.get("relation"),
                "action": "acknowledge",
            },
        })

    for issue in report.get("illegal_inferences") or []:
        eid = issue.get("id") or f"{issue.get('source')}|{issue.get('relation')}|{issue.get('target')}"
        _put({
            "fingerprint": fingerprint("RETRACT_INFERENCE", "edge", eid),
            "suggestion_type": "RETRACT_INFERENCE",
            "object_type": "edge",
            "object_id": eid,
            "problem_code": issue.get("code") or "ILLEGAL_CROSS_DOMAIN_INFERENCE",
            "title": issue.get("title") or "跨语义域非法推理",
            "reason": issue.get("detail") or "确认后删除该推断边，不删除节点、不改 type。",
            "confidence": 0.86,
            "current": {
                **_edge_ends(node_map, issue.get("source"), issue.get("target")),
                "relation": issue.get("relation"),
            },
            "proposed": {
                **_edge_ends(node_map, issue.get("source"), issue.get("target")),
                "relation": issue.get("relation"),
                "action": "delete_edge",
            },
        })

    for rec in inferred_candidates or []:
        src, rel, tgt = rec.get("source"), rec.get("relation"), rec.get("target")
        if not src or not rel or not tgt:
            continue
        if (src, rel, tgt) in existing_edges:
            continue
        extra = f"{src}|{rel}|{tgt}"
        props = rec.get("properties") or {}
        _put({
            "fingerprint": fingerprint("INFER_RELATION", "edge", extra),
            "suggestion_type": "INFER_RELATION",
            "object_type": "edge",
            "object_id": extra,
            "problem_code": "INFER_RELATION",
            "title": f"推理 {rel}",
            "reason": props.get("explanation") or "由规则从前提出边，确认后才写入图谱。",
            "confidence": 0.7,
            "current": _edge_ends(node_map, src, tgt),
            "proposed": {
                **_edge_ends(node_map, src, tgt),
                "relation": rel,
                "valid_from": _clean_day(props.get("valid_from")),
                "valid_to": _clean_day(props.get("valid_to")),
                "rule_id": props.get("rule_id"),
                "rule_name": props.get("rule_name"),
                "explanation": props.get("explanation") or "",
                "evidence": props.get("evidence") if isinstance(props.get("evidence"), list) else [],
            },
        })

    published_fps = {it.get("fingerprint") for it in items if it}
    closed = 0
    pending = []
    for status in ("open", "deferred"):
        pending.extend(kg.list_work_items(status=status, page_size=5000)["items"])
    seen_ids = set()
    for old in pending:
        oid = old.get("id")
        if oid in seen_ids:
            continue
        seen_ids.add(oid)
        if old.get("suggestion_type") not in ("SCHEMA_FIX", "SCHEMA_RELATION"):
            continue
        if old.get("fingerprint") in published_fps:
            continue
        kg.update_suggestion(
            old["id"],
            status="resolved",
            reason="刷新分析后已符合当前 Schema，工单自动关闭。",
        )
        closed += 1

    return {
        "created": created,
        "updated": updated,
        "skipped_terminal": skipped,
        "resolved_stale": closed,
        "count": len(items),
    }


def apply_work_item(item, graph, proposed=None):
    """执行一张已确认工单。不改 node.type。幂等。"""
    kind = item.get("suggestion_type")
    proposed = proposed or item.get("proposed") or item.get("payload") or {}
    applied = {"kind": kind, "type_unchanged": True}
    times = _edge_times(proposed)

    if kind == "CLASSIFY_INSTANCE":
        nid = proposed.get("node_id") or item.get("object_id")
        onto = proposed.get("proposed_ontology_type")
        if proposed.get("proposed_type_id"):
            typed = get_kg_store().get_type(proposed["proposed_type_id"])
            if typed:
                onto = typed["name"]
        node = graph.get_node(nid) if nid else None
        if not node or not onto:
            raise ValueError("缺少节点或建议类型")
        graph_type = node.get("type")
        node["ontology_type"] = onto
        graph.upsert_node(node)
        applied.update({"node_id": nid, "ontology_type": onto, "graph_type": graph_type})
        for other in _nodes(graph):
            if other["id"] == nid:
                continue
            if other.get("name") == onto and (
                other.get("resource_kind") == "class" or other.get("name") in RESOURCE_CLASS_NAMES
            ):
                _write_confirmed_edge(
                    graph, nid, other["id"], REL_IS_A,
                    explanation=f"确认本体类 {onto}，图谱 type 仍为 {graph_type}。",
                    rule_name="ManualClassifyConfirm",
                    **times,
                )
                applied["isa"] = f"{nid}|IS_A|{other['id']}"
                break

    elif kind == "HIERARCHY_REFACTOR":
        child_id = proposed.get("child_id") or item.get("object_id")
        parent_id = proposed.get("parent_id")
        onto = proposed.get("proposed_ontology_type") or proposed.get("ontology_type")
        if proposed.get("proposed_type_id"):
            typed = get_kg_store().get_type(proposed["proposed_type_id"])
            if typed:
                onto = typed["name"]
        child = graph.get_node(child_id) if child_id else None
        if not child:
            raise ValueError("子节点不存在")
        if onto:
            child["ontology_type"] = onto
            graph.upsert_node(child)
        added = []
        if child_id and parent_id and child_id != parent_id:
            existing = {(e["source"], e["relation"], e["target"]) for e in _edges(graph)}
            for rel, src, tgt in ((REL_IS_A, child_id, parent_id), (REL_PART_OF, child_id, parent_id)):
                if (src, rel, tgt) in existing:
                    continue
                _write_confirmed_edge(
                    graph, src, tgt, rel,
                    explanation=f"人工确认层级：{child.get('name')} IS_A 总类，禁止与总类合并。",
                    rule_name="ManualHierarchyConfirm",
                    **times,
                )
                added.append(f"{src}|{rel}|{tgt}")
        applied.update({
            "child_id": child_id, "ontology_type": onto, "parent_id": parent_id, "added_edges": added,
        })

    elif kind == "WEAK_RELATION":
        src, tgt = proposed.get("source"), proposed.get("target")
        new_rel = proposed.get("proposed_relation") or REL_USES
        if not src or not tgt:
            raise ValueError("缺少边端点")
        _write_confirmed_edge(
            graph, src, tgt, new_rel,
            explanation=f"保留 {proposed.get('current_relation')}，另写 {new_rel}。",
            rule_name="WeakRelationConfirm",
            **times,
        )
        applied.update({
            "kept": proposed.get("current_relation"),
            "added": f"{src}|{new_rel}|{tgt}",
            **times,
        })

    elif kind == "RETRACT_INFERENCE":
        src, rel, tgt = proposed.get("source"), proposed.get("relation"), proposed.get("target")
        if not src or not rel or not tgt:
            raise ValueError("缺少要撤销的三元组")
        graph.delete_edge(src, tgt, rel)
        applied.update({"removed": f"{src}|{rel}|{tgt}"})

    elif kind == "INFER_RELATION":
        src, rel, tgt = proposed.get("source"), proposed.get("relation"), proposed.get("target")
        if not src or not rel or not tgt:
            raise ValueError("缺少推理三元组")
        props = {
            "inferred": True,
            "confirmed": True,
            "semantic": True,
            "rule_id": proposed.get("rule_id"),
            "rule_name": proposed.get("rule_name"),
            "explanation": proposed.get("explanation") or "",
            "evidence": proposed.get("evidence") or [],
            **times,
        }
        _write_confirmed_edge(graph, src, tgt, rel, **props)
        applied.update({"added": f"{src}|{rel}|{tgt}", **times})
        try:
            from temporal_graph.service import observe_edge
            nodes = {n["id"]: n for n in _nodes(graph)}
            observe_edge({"source": src, "target": tgt, "relation": rel, "properties": props}, nodes, source="ontology-confirm")
        except Exception:
            pass

    elif kind == "SUBTYPE_CLUSTER":
        onto = proposed.get("ontology_type")
        ids = []
        for m in proposed.get("members") or []:
            node = graph.get_node(m.get("id"))
            if not node or not onto:
                continue
            node["ontology_type"] = onto
            graph.upsert_node(node)
            ids.append(node["id"])
        applied.update({"ontology_type": onto, "nodes": ids})

    elif kind == "TYPE_SCHEMA":
        kg = get_kg_store()
        kg.snapshot(reason="type-schema-workitem")
        kg.upsert_type({
            "id": proposed.get("type_id"),
            "name": proposed.get("name"),
            "parent_id": proposed.get("parent_id"),
            "description": proposed.get("description") or "",
        })
        applied.update({"type_id": proposed.get("type_id")})

    elif kind == "SCHEMA_FIX":
        nid = proposed.get("node_id") or item.get("object_id")
        node = graph.get_node(nid) if nid else None
        if not node:
            raise ValueError("节点不存在")
        field = proposed.get("field")
        onto = node.get("ontology_type") or GRAPH_TO_ONTOLOGY.get(node.get("type"), node.get("type"))
        storage = schema_storage_field(node, field, {"name": onto}) if field else field
        if field == "type" and storage == "type":
            raise ValueError("不能把图节点类别 type 改成事件/资源枚举")
        if proposed.get("clear_forbidden") and storage:
            node.pop(storage, None)
        elif storage and proposed.get("proposed_value") not in (None, ""):
            node[storage] = proposed.get("proposed_value")
        graph.upsert_node(node)
        applied.update({"node_id": nid, "field": field, "storage": storage, "value": node.get(storage) if storage else None})

    elif kind == "SCHEMA_RELATION":
        src, rel, tgt = proposed.get("source"), proposed.get("relation"), proposed.get("target")
        if src and rel and tgt and proposed.get("action") != "acknowledge":
            _write_confirmed_edge(
                graph, src, tgt, rel,
                explanation=proposed.get("explanation") or "确认关系 Schema 工单后写入。",
                rule_name="SchemaRelationConfirm",
                **times,
            )
            applied.update({"added": f"{src}|{rel}|{tgt}", **times})
        else:
            applied.update({"action": proposed.get("action") or "acknowledge", "unchanged_edge": True})

    else:
        raise ValueError(f"未知工单类型: {kind}")

    return applied


def _nodes(graph):
    try:
        return graph.list_nodes(include_merged=False)
    except TypeError:
        return graph.list_nodes()


def _edges(graph):
    try:
        return graph.list_edges(include_merged=False)
    except TypeError:
        return graph.list_edges()


def _write_confirmed_edge(graph, src, tgt, rel, explanation="", rule_name="", **extra):
    props = relation_template(src, tgt, rel, inferred=True, semantic=True, strength=0.55)["properties"]
    props["inferred"] = True
    props["confirmed"] = True
    props["explanation"] = explanation
    props["rule_name"] = rule_name
    props.update({k: v for k, v in extra.items() if v is not None})
    graph.upsert_edge(src, tgt, rel, props, record_history=False)


def replay_accepted(graph):
    kg = get_kg_store()
    items = kg.list_accepted()
    items = sorted(items, key=lambda x: x.get("updated_time") or x.get("created_time") or "")
    ok, failed = 0, 0
    for item in items:
        try:
            proposed = item.get("applied") or item.get("proposed") or item.get("payload") or {}
            if item.get("applied") and item["applied"].get("kind"):
                proposed = item.get("proposed") or item.get("payload") or {}
            apply_work_item(item, graph, proposed=item.get("proposed") or item.get("payload"))
            ok += 1
        except Exception:
            failed += 1
    return {"replayed": ok, "failed": failed, "total": len(items)}


def open_classify_item(node, source="manual", preferred_type=None, preferred_type_id=None):
    kg = get_kg_store()
    nid = node["id"]
    gtype = node.get("type")
    mapped = GRAPH_TO_ONTOLOGY.get(gtype, gtype)
    all_types = kg.list_types()
    candidates = [t["name"] for t in all_types if t.get("name")]
    suggested = preferred_type or classify_node(node) or mapped
    type_id = preferred_type_id
    if not type_id:
        match = next((t for t in all_types if t.get("name") == suggested), None)
        type_id = match["id"] if match else None
    rec, _ = kg.upsert_work_item({
        "fingerprint": fingerprint("CLASSIFY_INSTANCE", "node", nid),
        "suggestion_type": "CLASSIFY_INSTANCE",
        "object_type": "node",
        "object_id": nid,
        "problem_code": "MANUAL",
        "title": f"重分类「{node.get('name')}」",
        "reason": "从类型体系手动提出。只改 ontology_type，不改图谱 type。可改归属到左侧类型树任意节点。",
        "confidence": 0.5,
        "source": source,
        "current": {"graph_type": gtype, "ontology_type": node.get("ontology_type")},
        "proposed": {
            "node_id": nid,
            "graph_type": gtype,
            "current_ontology_type": node.get("ontology_type") or mapped,
            "proposed_ontology_type": suggested,
            "proposed_type_id": type_id,
            "candidates": candidates,
        },
    }, force=True)
    return rec
