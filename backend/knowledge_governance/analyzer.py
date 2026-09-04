"""Graph Semantic Analyzer —— 只读分析现有图谱，不改数据。"""

from collections import Counter, defaultdict

from organization_graph.ontology.nodes import NODE_TYPES
from organization_graph.ontology.resources import RESOURCE_CLASS_NAMES, class_name_for_resource
from organization_graph.repository.facade import get_facade

from .seed import GRAPH_TO_ONTOLOGY, classify_resource_subtype
from .schema import relation_matches, relation_names_of, validate_node
from .repository import get_kg_store


GENERIC_REL_HINTS = {"RELATED", "ASSOCIATED", "关联", "LINK"}

SUFFIX_GROUPS = (
    ("交付资源", "DeliveryResource"),
    ("经验", "Knowledge"),
    ("圈", "Organization"),
)


def analyze_graph(store=None):
    store = store or get_facade()
    try:
        nodes = store.list_nodes(include_merged=False)
        edges = store.list_edges(include_merged=False)
    except TypeError:
        nodes = store.list_nodes()
        edges = store.list_edges()

    type_counts = Counter((n.get("type") or "Unknown") for n in nodes)
    unknown_types = [t for t in type_counts if t not in NODE_TYPES]
    rel_counts = Counter((e.get("relation") or "Unknown") for e in edges)

    ambiguous = _ambiguous_names(nodes)
    hierarchy = _potential_hierarchy(nodes, edges)
    clusters = _suffix_clusters(nodes)
    missing_semantics = _missing_semantics(edges)
    mixed_class_instance = _class_instance_mix(nodes)
    schema_issues, relation_issues = _schema_issues(nodes, edges)
    from .semantic_domains import illegal_existing_edges
    illegal_inferences = illegal_existing_edges(nodes, edges)

    report = {
        "total_nodes": len(nodes),
        "total_edges": len(edges),
        "types": dict(type_counts),
        "unknown_types": unknown_types,
        "unknown_type_count": sum(type_counts[t] for t in unknown_types),
        "relations": dict(rel_counts),
        "possible_hierarchy": len(hierarchy),
        "hierarchy_candidates": hierarchy[:30],
        "clusters": clusters,
        "ambiguous_names": ambiguous[:20],
        "class_instance_mix": mixed_class_instance[:20],
        "weak_relations": missing_semantics[:20],
        "schema_issues": schema_issues[:40],
        "relation_schema_issues": relation_issues[:40],
        "illegal_inferences": illegal_inferences[:40],
        "ontology_mapping": {
            g: GRAPH_TO_ONTOLOGY.get(g, g) for g in type_counts
        },
    }
    report["problems"] = problems_from_report(report)
    return report


def problems_from_report(report):
    problems = []
    mixed = report.get("class_instance_mix") or []
    clusters = report.get("clusters") or []
    missing = report.get("weak_relations") or []
    ambiguous = report.get("ambiguous_names") or []
    schema_issues = report.get("schema_issues") or []
    relation_issues = report.get("relation_schema_issues") or []
    if mixed:
        problems.append({
            "code": "CLASS_INSTANCE_MIX",
            "title": "类别与实例混在同一 Resource 类型",
            "detail": "「交付资源」总类和「越南代理交付资源」明细都是 type=Resource，缺少 IS_A / 本体子类。",
            "count": len(mixed),
        })
    if clusters:
        problems.append({
            "code": "FLAT_RESOURCE_FAMILY",
            "title": "同族资源可能未挂到总类下",
            "detail": "名称同后缀的节点应属于同一本体子类（如 DeliveryResource）。",
            "count": sum(len(c.get("members") or []) for c in clusters),
        })
    if missing:
        problems.append({
            "code": "WEAK_RELATION_SEMANTICS",
            "title": "关系语义偏弱",
            "detail": "存在仅表示「关联」的边，或项目-资源边尚未写成 USES / DEPENDS_ON。",
            "count": len(missing),
        })
    if ambiguous:
        problems.append({
            "code": "NAME_TYPE_AMBIGUITY",
            "title": "同名可能跨类型（项目/知识/资源）",
            "detail": "例如「AI客服」既可能是项目也可能是知识主题。",
            "count": len(ambiguous),
        })
    if schema_issues:
        problems.append({
            "code": "SCHEMA_VIOLATION",
            "title": "属性不符合本体 Schema",
            "detail": "必填缺失、枚举越界或把关系写成了属性。确认后按 Schema 规范化，不改图谱 type。",
            "count": len(schema_issues),
        })
    illegal = report.get("illegal_inferences") or []
    if relation_issues:
        problems.append({
            "code": "RELATION_NOT_IN_SCHEMA",
            "title": "关系不在关系 Schema 中",
            "detail": "该边的源/目标类型与已声明的允许关系不匹配。",
            "count": len(relation_issues),
        })
    if illegal:
        problems.append({
            "code": "ILLEGAL_CROSS_DOMAIN_INFERENCE",
            "title": "跨语义域非法推理",
            "detail": "职位/汇报/成果归属被当成培养、贡献或能力。确认后撤销该推断边，不删节点。",
            "count": len(illegal),
        })
    return problems


ACTIVE_WORK_STATUSES = frozenset({"open", "pending", "deferred"})
TERMINAL_WORK_STATUSES = frozenset({"accepted", "rejected", "resolved", "ignored"})


def suppress_handled_issues(report):
    """已同意/关闭/自动关闭的工单不再作为「当前语义问题」展示。"""
    from .workitems import fingerprint

    kg = get_kg_store()
    active_fp, terminal_fp = set(), set()
    active_code, terminal_code = Counter(), Counter()
    seen = set()
    for status in ("open", "deferred", "accepted", "rejected", "resolved"):
        for it in kg.list_work_items(status=status, page_size=5000)["items"]:
            iid = it.get("id")
            if iid in seen:
                continue
            seen.add(iid)
            st = it.get("status")
            fp = it.get("fingerprint") or ""
            code = it.get("problem_code") or ""
            if st in ACTIVE_WORK_STATUSES:
                if fp:
                    active_fp.add(fp)
                if code:
                    active_code[code] += 1
            elif st in TERMINAL_WORK_STATUSES:
                if fp:
                    terminal_fp.add(fp)
                if code:
                    terminal_code[code] += 1

    def handled(fp):
        return bool(fp) and fp in terminal_fp and fp not in active_fp

    def rel_fp(iss):
        eid = iss.get("id") or f"{iss.get('source')}|{iss.get('relation')}|{iss.get('target')}"
        return fingerprint("SCHEMA_RELATION", "edge", eid)

    report["relation_schema_issues"] = [
        i for i in (report.get("relation_schema_issues") or []) if not handled(rel_fp(i))
    ]
    report["schema_issues"] = [
        i for i in (report.get("schema_issues") or [])
        if not handled(fingerprint("SCHEMA_FIX", "node", f"{i.get('node_id')}:{i.get('field')}:{i.get('kind')}"))
    ]
    clusters = []
    for c in report.get("clusters") or []:
        members = [
            m for m in (c.get("members") or [])
            if not handled(fingerprint("CLASSIFY_INSTANCE", "node", m.get("id")))
        ]
        if members:
            clusters.append({**c, "members": members})
    report["clusters"] = clusters
    report["weak_relations"] = [
        w for w in (report.get("weak_relations") or [])
        if not handled(fingerprint(
            "WEAK_RELATION", "edge",
            w.get("id") or f"{w.get('source')}|{w.get('relation')}|{w.get('target')}",
        ))
    ]
    report["class_instance_mix"] = [
        m for m in (report.get("class_instance_mix") or [])
        if m.get("kind") == "class" or not handled(fingerprint("CLASSIFY_INSTANCE", "node", m.get("id")))
    ]
    report["hierarchy_candidates"] = [
        h for h in (report.get("hierarchy_candidates") or [])
        if not handled(fingerprint("HIERARCHY_REFACTOR", "node", h.get("child_id")))
    ]
    report["ambiguous_names"] = [
        a for a in (report.get("ambiguous_names") or [])
        if not all(
            handled(fingerprint("CLASSIFY_INSTANCE", "node", n.get("id")))
            for n in (a.get("nodes") or [])
        )
    ]

    report["illegal_inferences"] = [
        i for i in (report.get("illegal_inferences") or [])
        if not handled(fingerprint("RETRACT_INFERENCE", "edge", i.get("id") or f"{i.get('source')}|{i.get('relation')}|{i.get('target')}"))
    ]

    visible = []
    for p in problems_from_report(report):
        code = p["code"]
        open_n = int(active_code.get(code, 0))
        term_n = int(terminal_code.get(code, 0))
        p["open_count"] = open_n
        p["handled_count"] = term_n
        if open_n == 0 and term_n > 0:
            continue
        visible.append(p)
    report["problems"] = visible
    return report


def _ambiguous_names(nodes):
    by_name = defaultdict(set)
    samples = defaultdict(list)
    for n in nodes:
        name = (n.get("name") or "").strip()
        if len(name) < 2:
            continue
        by_name[name].add(n.get("type"))
        samples[name].append({"id": n["id"], "type": n.get("type")})
    out = []
    for name, types in by_name.items():
        if len(types) >= 2:
            out.append({"name": name, "types": sorted(types), "nodes": samples[name][:6]})
    return out


def _potential_hierarchy(nodes, edges):
    """名称包含关系 + 已有 HAS_SUB_RESOURCE。"""
    existing = set()
    for e in edges:
        if e.get("relation") in ("HAS_SUB_RESOURCE", "IS_A", "PART_OF"):
            existing.add((e["source"], e["target"]))
    resources = [n for n in nodes if n.get("type") == "Resource"]
    by_name = {n.get("name"): n for n in resources}
    found = []
    for n in resources:
        name = n.get("name") or ""
        parent_name = class_name_for_resource(name, n.get("category"), n.get("resource_kind"))
        if not parent_name:
            continue
        parent = by_name.get(parent_name)
        item = {
            "child_id": n["id"],
            "child": name,
            "parent": parent_name,
            "parent_id": parent["id"] if parent else None,
            "reason": f"名称归入总类「{parent_name}」",
            "already_linked": bool(parent and ((parent["id"], n["id"]) in existing or (n["id"], parent["id"]) in existing)),
            "suggested_ontology": classify_resource_subtype(n),
        }
        found.append(item)
    return found


def _suffix_clusters(nodes):
    groups = defaultdict(list)
    for n in nodes:
        name = n.get("name") or ""
        for suffix, onto in SUFFIX_GROUPS:
            if name.endswith(suffix) and name != suffix:
                if (n.get("ontology_type") or "") == onto:
                    continue
                groups[(suffix, onto, n.get("type"))].append(n)
    clusters = []
    for (suffix, onto, ntype), members in groups.items():
        if len(members) < 2:
            continue
        clusters.append({
            "cluster": suffix,
            "ontology_type": onto,
            "graph_type": ntype,
            "confidence": min(0.95, 0.7 + 0.04 * len(members)),
            "members": [{"id": m["id"], "name": m.get("name")} for m in members[:40]],
        })
    clusters.sort(key=lambda x: -len(x["members"]))
    return clusters


def _missing_semantics(edges):
    weak = []
    for e in edges:
        rel = e.get("relation") or ""
        if rel in GENERIC_REL_HINTS or rel == "RELATED":
            weak.append({"id": e.get("id"), "source": e["source"], "target": e["target"], "relation": rel})
        if rel == "HAS_RESOURCE":
            weak.append({
                "id": e.get("id"),
                "source": e["source"],
                "target": e["target"],
                "relation": rel,
                "suggest": "USES / DEPENDS_ON",
                "note": "项目产出/使用资源，语义可增强为 USES",
            })
    return weak


def _class_instance_mix(nodes):
    resources = [n for n in nodes if n.get("type") == "Resource"]
    classes = [n for n in resources if n.get("resource_kind") == "class" or n.get("name") in RESOURCE_CLASS_NAMES]
    instances = [n for n in resources if n not in classes]
    if classes and instances:
        return [
            {"kind": "class", "id": n["id"], "name": n.get("name")} for n in classes
        ] + [
            {"kind": "instance", "id": n["id"], "name": n.get("name")} for n in instances[:12]
        ]
    return []


def _schema_issues(nodes, edges):
    try:
        kg = get_kg_store()
        types = {t["name"]: t for t in kg.list_types()}
        relations = kg.list_ontology_relations()
    except Exception:
        return [], []
    allowed = list(relations)
    parent_of = {}
    for t in types.values():
        pid = t.get("parent_id")
        if not pid:
            continue
        parent = next((x for x in types.values() if x.get("id") == pid), None)
        if parent:
            parent_of[t["name"]] = parent["name"]
    allowed_names = set()
    for r in allowed:
        allowed_names.update(relation_names_of(r))
    node_map = {n["id"]: n for n in nodes}
    attr_issues = []
    for n in nodes:
        onto = n.get("ontology_type") or GRAPH_TO_ONTOLOGY.get(n.get("type"), n.get("type"))
        rec = types.get(onto)
        if not rec:
            continue
        for issue in validate_node(n, rec):
            attr_issues.append({
                "node_id": n["id"],
                "node_name": n.get("name"),
                "ontology_type": onto,
                **issue,
            })
    rel_issues = []
    if not allowed:
        return attr_issues, rel_issues
    for e in edges:
        rel = e.get("relation") or ""
        if rel in ("MERGED_INTO", "ALIAS_OF"):
            continue
        src = node_map.get(e.get("source")) or {}
        tgt = node_map.get(e.get("target")) or {}
        src_onto = src.get("ontology_type") or GRAPH_TO_ONTOLOGY.get(src.get("type"), src.get("type"))
        tgt_onto = tgt.get("ontology_type") or GRAPH_TO_ONTOLOGY.get(tgt.get("type"), tgt.get("type"))
        if not src_onto or not tgt_onto:
            continue
        if any(
            relation_matches(rel, r)
            and _is_subtype(src_onto, r.get("source_type"), parent_of)
            and _is_subtype(tgt_onto, r.get("target_type"), parent_of)
            for r in allowed
        ):
            continue
        if rel not in allowed_names:
            rel_issues.append({
                "id": e.get("id"),
                "source": e.get("source"),
                "target": e.get("target"),
                "relation": rel,
                "source_type": src_onto,
                "target_type": tgt_onto,
                "note": f"{rel} 未在关系 Schema 中声明",
            })
            continue
        # 同名关系存在，但端点类型不匹配
        rel_issues.append({
            "id": e.get("id"),
            "source": e.get("source"),
            "target": e.get("target"),
            "relation": rel,
            "source_type": src_onto,
            "target_type": tgt_onto,
            "note": f"{src_onto} --{rel}--> {tgt_onto} 不在允许的端点类型中",
        })
    return attr_issues, rel_issues


def _is_subtype(actual, allowed, parent_of):
    if not actual or not allowed:
        return True
    if actual == allowed:
        return True
    seen = set()
    cur = actual
    while cur and cur not in seen:
        if cur == allowed:
            return True
        seen.add(cur)
        cur = parent_of.get(cur)
    return False
