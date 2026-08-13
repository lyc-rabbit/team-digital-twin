"""
Neo4j 图存储

有库时作为主存：读写节点/边、全量覆盖、统计都走这里。
未配置或连接失败时 enabled=False，由 facade 降级到 SQLite。
"""

from collections import defaultdict
from typing import Optional


def neo4j_config():
    import os
    return {
        "uri": os.getenv("NEO4J_URI", "").strip(),
        "user": os.getenv("NEO4J_USER", "neo4j").strip(),
        "password": os.getenv("NEO4J_PASSWORD", "").strip(),
    }


def is_neo4j_configured():
    cfg = neo4j_config()
    return bool(cfg["uri"])


class Neo4jRepository:
    def __init__(self):
        self.driver = None
        self.enabled = False
        self.error = None
        self._connect()

    def _connect(self):
        cfg = neo4j_config()
        if not cfg["uri"]:
            self.error = "未配置 NEO4J_URI"
            return
        try:
            from neo4j import GraphDatabase
            self.driver = GraphDatabase.driver(
                cfg["uri"],
                auth=(cfg["user"], cfg["password"]),
            )
            with self.driver.session() as session:
                session.run("RETURN 1")
            self.enabled = True
            self.error = None
            print(f"[OIG] Neo4j 已连接 {cfg['uri']}")
        except Exception as e:
            self.enabled = False
            self.error = str(e)
            self.driver = None
            print(f"[OIG] Neo4j 不可用，将降级 SQLite: {e}")

    def close(self):
        if self.driver:
            self.driver.close()
            self.driver = None
            self.enabled = False

    def ping(self):
        if not self.enabled or not self.driver:
            return False
        try:
            with self.driver.session() as session:
                session.run("RETURN 1")
            return True
        except Exception as e:
            self._disable(e)
            return False

    def _disable(self, err):
        self.enabled = False
        self.error = str(err)
        print(f"[OIG] Neo4j 操作失败，降级 SQLite: {err}")

    def _session(self):
        if not self.enabled or not self.driver:
            raise RuntimeError(self.error or "Neo4j 未连接")
        return self.driver.session()

    def count_nodes(self) -> int:
        with self._session() as session:
            rec = session.run("MATCH (n) RETURN count(n) AS c").single()
            return int(rec["c"] if rec else 0)

    def count_edges(self) -> int:
        with self._session() as session:
            rec = session.run("MATCH ()-[r]->() RETURN count(r) AS c").single()
            return int(rec["c"] if rec else 0)

    def clear(self):
        with self._session() as session:
            session.run("MATCH (n) DETACH DELETE n")

    def list_nodes(self, node_type: Optional[str] = None) -> list:
        cypher = "MATCH (n) "
        params = {}
        if node_type:
            cypher += "WHERE n.type = $node_type "
            params["node_type"] = node_type
        cypher += "RETURN n ORDER BY n.type, n.name"
        with self._session() as session:
            return [_node_from_graph(rec["n"]) for rec in session.run(cypher, **params)]

    def get_node(self, node_id: str) -> Optional[dict]:
        with self._session() as session:
            rec = session.run(
                "MATCH (n {id: $id}) RETURN n LIMIT 1",
                id=node_id,
            ).single()
            return _node_from_graph(rec["n"]) if rec else None

    def find_person(self, person_id: str) -> Optional[dict]:
        node = self.get_node(person_id)
        if node and node.get("type") == "Person":
            return node
        with self._session() as session:
            rec = session.run(
                """
                MATCH (n)
                WHERE n.type = 'Person' AND (n.id = $id OR n.name = $id)
                RETURN n LIMIT 1
                """,
                id=person_id,
            ).single()
            return _node_from_graph(rec["n"]) if rec else None

    def list_edges(self, relation: Optional[str] = None, source=None, target=None) -> list:
        cypher = "MATCH (a)-[r]->(b) WHERE 1=1 "
        params = {}
        if relation:
            cypher += "AND type(r) = $relation "
            params["relation"] = _safe_label(relation)
        if source:
            cypher += "AND a.id = $source "
            params["source"] = source
        if target:
            cypher += "AND b.id = $target "
            params["target"] = target
        cypher += "RETURN a.id AS source, b.id AS target, type(r) AS relation, properties(r) AS props"
        with self._session() as session:
            return [_edge_from_record(rec) for rec in session.run(cypher, **params)]

    def neighbors(self, node_id: str, relations=None) -> list:
        with self._session() as session:
            rows = session.run(
                """
                MATCH (n {id: $id})-[r]-(m)
                RETURN
                  startNode(r).id AS source,
                  endNode(r).id AS target,
                  type(r) AS relation,
                  properties(r) AS props
                """,
                id=node_id,
            )
            edges = [_edge_from_record(rec) for rec in rows]
        if relations:
            allowed = {_safe_label(x) for x in relations}
            edges = [e for e in edges if e["relation"] in allowed]
        return edges

    def upsert_node(self, node: dict):
        label = _safe_label(node.get("type") or "Entity")
        props = _node_props(node)
        with self._session() as session:
            session.run(
                f"MERGE (n:{label} {{id: $id}}) SET n += $props",
                id=node["id"],
                props=props,
            )
        return node["id"]

    def upsert_edge(self, source, target, relation, properties=None):
        rel = _safe_label(relation or "RELATED")
        props = _edge_props(properties or {})
        with self._session() as session:
            session.run(
                f"""
                MATCH (a {{id: $source}})
                MATCH (b {{id: $target}})
                MERGE (a)-[r:{rel}]->(b)
                SET r += $props
                """,
                source=source,
                target=target,
                props=props,
            )
        return f"{source}|{relation}|{target}"

    def stats(self):
        with self._session() as session:
            by_type = {}
            for rec in session.run(
                "MATCH (n) RETURN coalesce(n.type, 'Entity') AS t, count(*) AS c"
            ):
                by_type[rec["t"]] = rec["c"]
            by_rel = {}
            for rec in session.run(
                "MATCH ()-[r]->() RETURN type(r) AS t, count(*) AS c"
            ):
                by_rel[rec["t"]] = rec["c"]
            node_count = sum(by_type.values())
            edge_count = sum(by_rel.values())
        return {
            "node_count": node_count,
            "edge_count": edge_count,
            "nodes_by_type": by_type,
            "edges_by_relation": by_rel,
            "backend": "neo4j",
        }

    def replace_graph(self, nodes: list, edges: list):
        """全量覆盖写入。按标签/关系类型 UNWIND 批量提交。"""
        if not self.enabled:
            return False
        try:
            with self._session() as session:
                session.run("MATCH (n) DETACH DELETE n")
                by_label = defaultdict(list)
                for node in nodes:
                    label = _safe_label(node.get("type") or "Entity")
                    by_label[label].append(_node_props(node))
                for label, rows in by_label.items():
                    session.run(
                        f"UNWIND $rows AS row MERGE (n:{label} {{id: row.id}}) SET n += row",
                        rows=rows,
                    )
                by_rel = defaultdict(list)
                for edge in edges:
                    rel = _safe_label(edge.get("relation") or "RELATED")
                    by_rel[rel].append({
                        "source": edge["source"],
                        "target": edge["target"],
                        "props": _edge_props(edge.get("properties") or {}),
                    })
                for rel, rows in by_rel.items():
                    session.run(
                        f"""
                        UNWIND $rows AS row
                        MATCH (a {{id: row.source}})
                        MATCH (b {{id: row.target}})
                        MERGE (a)-[r:{rel}]->(b)
                        SET r += row.props
                        """,
                        rows=rows,
                    )
            print(f"[OIG] Neo4j 全量写入完成 nodes={len(nodes)} edges={len(edges)}")
            return True
        except Exception as e:
            self._disable(e)
            return False


def _safe_label(label: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch == "_" else "_" for ch in (label or "Entity"))
    if not cleaned or cleaned[0].isdigit():
        cleaned = "N_" + cleaned
    return cleaned


def _neo4j_value(value):
    if value is None:
        return None
    if isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, list):
        if all(isinstance(x, (str, int, float, bool)) for x in value):
            return value
        return ",".join(str(x) for x in value)
    if isinstance(value, dict):
        return str(value)
    return str(value)


def _node_props(node: dict) -> dict:
    props = {}
    for k, v in (node or {}).items():
        nv = _neo4j_value(v)
        if nv is not None:
            props[k] = nv
    props["id"] = node["id"]
    props.setdefault("type", node.get("type") or "Entity")
    props.setdefault("name", node.get("name") or node["id"])
    return props


def _edge_props(properties: dict) -> dict:
    flat = {k: _neo4j_value(v) for k, v in (properties or {}).items()}
    return {k: v for k, v in flat.items() if v is not None}


def _node_from_graph(n) -> dict:
    data = dict(n)
    nid = data.get("id")
    ntype = data.get("type") or "Entity"
    name = data.get("name") or nid
    extra = {k: v for k, v in data.items() if k not in ("id", "type", "name")}
    return {"id": nid, "type": ntype, "name": name, **extra}


def _edge_from_record(rec) -> dict:
    source = rec["source"]
    target = rec["target"]
    relation = rec["relation"]
    props = dict(rec["props"] or {})
    return {
        "id": f"{source}|{relation}|{target}",
        "source": source,
        "target": target,
        "relation": relation,
        "properties": props,
        "updated_at": props.get("last_update") or props.get("updated_at"),
    }


_neo4j: Optional[Neo4jRepository] = None


def get_neo4j() -> Neo4jRepository:
    global _neo4j
    if _neo4j is None:
        _neo4j = Neo4jRepository()
    elif not _neo4j.enabled and is_neo4j_configured():
        _neo4j._connect()
    return _neo4j
