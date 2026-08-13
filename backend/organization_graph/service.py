"""OIG 领域服务 —— 查询、影响力、圈层、风险、晋升画像、抽取。"""

from database import get_all_members, get_ai_role_assignments, get_member_report_statistics

from .builder import GraphBuilder
from .repository.facade import get_facade, get_store
from .repository.neo4j import get_neo4j, is_neo4j_configured
from .algorithms.influence import compute_influence
from .algorithms.community import detect_communities, structural_holes
from .algorithms.risk import analyze_risks
from .extractor.llm_extract import extract_relations, apply_extraction
from .ontology.relations import REL_CONFLICT, REL_CONTROL, REL_TRUST


_builder = GraphBuilder()


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


def get_graph(node_types=None, relations=None):
    store = _ready()
    nodes = store.list_nodes()
    edges = store.list_edges()
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


def influence_ranking():
    store = _ready()
    nodes = store.list_nodes()
    edges = store.list_edges()
    inf = compute_influence(nodes, edges)
    ranking = sorted(inf.values(), key=lambda x: x["influence_score"], reverse=True)
    for i, item in enumerate(ranking, start=1):
        item["rank"] = i
    return {"ranking": ranking, "algorithm": ["Degree Centrality", "Betweenness Centrality", "PageRank"]}


def get_communities():
    store = _ready()
    nodes = store.list_nodes()
    edges = store.list_edges()
    communities = detect_communities(nodes, edges)
    holes = structural_holes(nodes, edges)
    return {
        "communities": communities,
        "structural_holes": holes[:10],
        "algorithm": {"community": "Louvain", "broker": "Structural Hole (Burt Constraint)"},
    }


def get_risks():
    store = _ready()
    nodes = store.list_nodes()
    edges = store.list_edges()
    inf = compute_influence(nodes, edges)
    return analyze_risks(nodes, edges, inf)


def leadership_profile(person_id):
    """晋升推演调用：能力/业绩/信任/影响力/冲突风险。"""
    store = _ready()
    person = store.find_person(person_id)
    if not person:
        return None

    pid = person["id"]
    inf_map = compute_influence(store.list_nodes(), store.list_edges())
    inf = inf_map.get(pid) or {}
    influence = int(inf.get("influence_score") or person.get("influence_score") or 0)

    trust_scores = []
    conflict_impact = 0
    conflict_n = 0
    resource_values = []
    for e in store.neighbors(pid):
        props = e.get("properties") or {}
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


def extract_and_apply(text, source_type="document"):
    members = get_all_members()
    store = _ready()
    result = extract_relations(text, members, source_type=source_type)
    applied = apply_extraction(result, members)
    store.save_extraction(source_type, text, {**result, "applied": applied})
    # 抽取后重算影响力
    inf = compute_influence(store.list_nodes(), store.list_edges())
    for pid, info in inf.items():
        node = store.get_node(pid)
        if node:
            node["influence_score"] = info["influence_score"]
            store.upsert_node(node)
    return {
        "extraction": result,
        "applied": applied,
        "mock_mode": result.get("mock_mode"),
        "degraded": result.get("degraded"),
    }


def extraction_history(limit=20):
    return get_store().list_extractions(limit)


def apply_event_update(name, time, description, members_hint=None):
    """V3 事件驱动更新：写入 Event 节点并抽取关系。"""
    store = _ready()
    from .ontology.nodes import node_template
    from .builder import _slug

    eid = _slug(name or "event", "event")
    store.upsert_node(node_template("Event", eid, name or "未命名事件", time=time or "", description=description or ""))
    text = f"{time or ''} {name or ''} {description or ''}".strip()
    extracted = extract_and_apply(text, source_type="event")
    return {"event_id": eid, **extracted}
