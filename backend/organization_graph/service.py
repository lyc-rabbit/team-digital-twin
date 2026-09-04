"""OIG 领域服务 —— 查询、影响力、圈层、风险、晋升画像、抽取。"""

from database import get_all_members, get_ai_role_assignments, get_member_report_statistics

from .builder import GraphBuilder
from .repository.facade import get_facade, get_store
from .repository.neo4j import get_neo4j, is_neo4j_configured
from .algorithms.influence import compute_influence
from .algorithms.community import detect_communities, structural_holes
from .algorithms.risk import analyze_risks
from .extractor.llm_extract import extract_relations, merge_extraction_runs
from .ontology.relations import REL_CONFLICT, REL_CONTROL, REL_TRUST
from timeutil import today


_builder = GraphBuilder()


def _current_edges(store, when=None, include_history=False):
    edges = store.list_edges()
    if include_history:
        return edges
    try:
        from temporal_graph.query import filter_current_edges
        return filter_current_edges(edges, when or today())
    except Exception:
        return edges


def _ready():
    _builder.ensure_built()
    return get_facade()


def graph_status():
    store = get_facade()
    neo = get_neo4j()
    primary = "neo4j" if neo.enabled else "sqlite"
    return {
        "sqlite": True,
        "sqlite_fallback": True,
        "primary": primary,
        "neo4j_configured": is_neo4j_configured(),
        "neo4j_connected": bool(neo.enabled),
        "neo4j_error": neo.error,
        "stats": store.stats(),
    }


def rebuild_graph():
    return _builder.rebuild()


def get_graph(node_types=None, relations=None, include_merged=False, as_of=None, include_history=False):
    if as_of:
        from temporal_graph.query import snapshot
        data = snapshot(as_of)
        data["status"] = graph_status()
        if node_types:
            allowed = set(node_types)
            data["nodes"] = [n for n in data["nodes"] if n.get("type") in allowed]
            ids = {n["id"] for n in data["nodes"]}
            data["edges"] = [e for e in data["edges"] if e["source"] in ids and e["target"] in ids]
        if relations:
            allowed_r = set(relations)
            data["edges"] = [e for e in data["edges"] if e["relation"] in allowed_r]
        return data
    store = _ready()
    nodes = store.list_nodes(include_merged=include_merged)
    edges = _current_edges(store, include_history=include_history)
    if node_types:
        allowed = set(node_types)
        nodes = [n for n in nodes if n.get("type") in allowed]
        ids = {n["id"] for n in nodes}
        edges = [e for e in edges if e["source"] in ids and e["target"] in ids]
    if relations:
        allowed_r = set(relations)
        edges = [e for e in edges if e["relation"] in allowed_r]
    return {
        "nodes": nodes,
        "edges": edges,
        "status": graph_status(),
    }


def person_network(person_id):
    store = _ready()
    person = store.find_person(person_id)
    if not person:
        return None
    edges = store.neighbors(person["id"])
    try:
        from temporal_graph.query import filter_current_edges
        edges = filter_current_edges(edges)
    except Exception:
        pass
    by_id = {n["id"]: n for n in store.list_nodes()}
    relations = []
    for e in edges:
        other_id = e["target"] if e["source"] == person["id"] else e["source"]
        other = by_id.get(other_id) or {"id": other_id, "name": other_id, "type": "Unknown"}
        props = e.get("properties") or {}
        relations.append({
            "type": e["relation"].lower(),
            "relation": e["relation"],
            "direction": "out" if e["source"] == person["id"] else "in",
            "target": other.get("name"),
            "target_id": other_id,
            "target_type": other.get("type"),
            "strength": round(float(props.get("strength") or 0.5), 3),
            "properties": props,
        })
    relations.sort(key=lambda x: x["strength"], reverse=True)
    return {
        "person": person.get("name"),
        "person_id": person["id"],
        "node": person,
        "relations": relations,
        "trends": store.person_relation_trends(person["id"]),
    }


def influence_ranking(as_of=None, date_from=None, date_to=None):
    store = _ready()
    nodes = store.list_nodes()
    edges = store.list_edges()
    if as_of or date_from or date_to:
        from temporal_graph.service import influence_window
        inf, meta = influence_window(nodes, edges, date_from, date_to, as_of)
    else:
        inf = compute_influence(nodes, _current_edges(store))
        meta = {"as_of": today()}
    ranking = sorted(inf.values(), key=lambda x: x["influence_score"], reverse=True)
    for i, item in enumerate(ranking, start=1):
        item["rank"] = i
    return {
        "ranking": ranking,
        "algorithm": ["Degree Centrality", "Betweenness Centrality", "PageRank"],
        "temporal": meta,
    }


def get_communities():
    store = _ready()
    nodes = store.list_nodes()
    edges = _current_edges(store)
    communities = detect_communities(nodes, edges)
    holes = structural_holes(nodes, edges, communities)
    return {
        "communities": communities,
        "structural_holes": holes[:10],
        "algorithm": {
            "community": "Louvain",
            "broker": "Structural Hole (Burt Constraint)",
            "score": "桥梁分 = (1 − 圈子束缚) × 100；束缚越低越像桥梁",
        },
    }


def get_risks():
    store = _ready()
    nodes = store.list_nodes()
    edges = _current_edges(store)
    inf = compute_influence(nodes, edges)
    return analyze_risks(nodes, edges, inf)


def leadership_profile(person_id):
    """晋升推演调用：能力/业绩/信任/影响力/冲突风险。"""
    store = _ready()
    person = store.find_person(person_id)
    if not person:
        return None

    pid = person["id"]
    inf_map = compute_influence(store.list_nodes(), _current_edges(store))
    inf = inf_map.get(pid) or {}
    influence = int(inf.get("influence_score") or person.get("influence_score") or 0)

    trust_scores = []
    conflict_impact = 0
    conflict_n = 0
    resource_values = []
    for e in store.neighbors(pid):
        props = e.get("properties") or {}
        if props.get("valid_to"):
            continue
        rel = e["relation"]
        if rel == REL_TRUST:
            trust_scores.append(float(props.get("score") or props.get("strength") or 0))
        elif rel == REL_CONFLICT:
            conflict_n += 1
            conflict_impact += float(props.get("impact") or 50)
        elif rel == REL_CONTROL:
            resource_values.append(float(props.get("resource_value") or 60))

    trust = int(round(sum(trust_scores) / len(trust_scores) * 100)) if trust_scores else 50
    resource_control = int(round(sum(resource_values) / len(resource_values))) if resource_values else 20
    if conflict_n:
        conflict_risk = min(95, int(20 + conflict_n * 12 + (conflict_impact / conflict_n) * 0.25))
    else:
        conflict_risk = 10

    # 能力：技能覆盖 + AI Native 匹配
    skills = person.get("skills") or []
    capability = min(90, 40 + len(skills) * 8)
    assignments = get_ai_role_assignments()
    mine = [a for a in assignments if a.get("employee_id") == pid]
    if mine:
        capability = int(max(capability, max(a.get("match_score") or 0 for a in mine)))

    # 业绩：近 30 日报项目投入
    stats = get_member_report_statistics(days=30).get(pid) or {}
    days = sum(stats.values()) if stats else 0
    performance = min(90, 35 + days * 4)

    # 团队认可 ≈ 入边 TRUST
    recognition = trust
    leadership = int(round(
        0.18 * capability
        + 0.18 * performance
        + 0.12 * recognition
        + 0.32 * influence
        + 0.10 * resource_control
        - 0.20 * conflict_risk
        + 20
    ))
    leadership = max(0, min(100, leadership))

    node = dict(person)
    node["leadership_score"] = leadership
    node["influence_score"] = influence
    store.upsert_node(node)

    return {
        "person": person.get("name"),
        "person_id": pid,
        "influence": influence,
        "trust": trust,
        "resource_control": resource_control,
        "conflict_risk": conflict_risk,
        "capability": capability,
        "performance": performance,
        "recognition": recognition,
        "leadership_score": leadership,
        "formula": "能力 + 业绩 + 团队认可 + 组织影响力 + 资源控制 - 冲突风险",
        "breakdown": {
            "degree": inf.get("degree"),
            "betweenness": inf.get("betweenness"),
            "pagerank": inf.get("pagerank"),
            "connections": inf.get("connections"),
            "skills": skills,
            "recent_project_days": days,
        },
    }


def extract_preview(text, source_type="document", rounds=3):
    """调用抽取模型多次，去重后只返回候选，不写图谱。"""
    members = get_all_members()
    temps = [0.0, 0.25, 0.45]
    runs = []
    for i in range(max(1, int(rounds or 3))):
        temp = temps[i] if i < len(temps) else 0.35
        runs.append(extract_relations(text, members, source_type=source_type, temperature=temp))
    merged = merge_extraction_runs(runs)
    return {
        "extraction": merged,
        "applied": None,
        "pending_confirm": True,
        "runs": merged.get("runs") or len(runs),
        "mock_mode": merged.get("mock_mode"),
        "degraded": merged.get("degraded"),
    }


def apply_confirmed_extraction(payload, text="", source_type="document"):
    """用户确认后：先登记事实并确认写图，不再绕过事实层。"""
    store = _ready()
    from fact_governance.bridge import ingest_confirmed_graph_relations
    written = ingest_confirmed_graph_relations(
        payload.get("relations") or [],
        text=text or "",
        source_type=source_type,
        source_title="LLM 关系抽取",
        entities=payload.get("entities") or [],
    )
    result = {
        "entities": payload.get("entities") or [],
        "relations": payload.get("relations") or [],
        "mock_mode": payload.get("mock_mode"),
        "degraded": payload.get("degraded"),
    }
    store.save_extraction(source_type, text or "", {**result, "applied": written.get("applied"), "confirmed": True, "facts": written})
    inf = compute_influence(store.list_nodes(), store.list_edges())
    for pid, info in inf.items():
        node = store.get_node(pid)
        if node:
            node["influence_score"] = info["influence_score"]
            store.upsert_node(node)
    return {
        "extraction": result,
        "applied": written.get("applied") or {"nodes": 0, "edges": 0},
        "facts": written,
        "pending_confirm": False,
        "mock_mode": result.get("mock_mode"),
        "degraded": result.get("degraded"),
    }


def extract_and_apply(text, source_type="document"):
    members = get_all_members()
    store = _ready()
    result = extract_relations(text, members, source_type=source_type)
    from fact_governance.bridge import ingest_confirmed_graph_relations
    written = ingest_confirmed_graph_relations(
        result.get("relations") or [],
        text=text or "",
        source_type=source_type,
        source_title="事件驱动抽取",
        entities=result.get("entities") or [],
    )
    store.save_extraction(source_type, text, {**result, "applied": written.get("applied"), "facts": written})
    inf = compute_influence(store.list_nodes(), store.list_edges())
    for pid, info in inf.items():
        node = store.get_node(pid)
        if node:
            node["influence_score"] = info["influence_score"]
            store.upsert_node(node)
    return {
        "extraction": result,
        "applied": written.get("applied") or {"nodes": 0, "edges": 0},
        "facts": written,
        "mock_mode": result.get("mock_mode"),
        "degraded": result.get("degraded"),
    }


def extraction_history(limit=20):
    return get_store().list_extractions(limit)


def apply_event_update(name, time, description, members_hint=None):
    """V3 事件驱动更新：写入 Event 节点并抽取关系。"""
    from entity_governance.service import resolve_entity

    resolved = resolve_entity(
        "EVENT",
        name or "未命名事件",
        attributes={"time": time or "", "description": description or ""},
        source={"type": "event"},
        create_if_new=True,
    )
    eid = resolved["canonical_entity_id"]
    text = f"{time or ''} {name or ''} {description or ''}".strip()
    extracted = extract_and_apply(text, source_type="event")
    return {"event_id": eid, "resolve": resolved, **extracted}
