"""
图谱访问门面

Neo4j 主存：已连接时读、写、计算数据都走 Neo4j。
SQLite 兜底：未配置/连不上/读写失败时降级，保证功能不挂。
增量写入双写 SQLite，方便下次 Neo4j 挂掉时仍有数据。
"""

from typing import Optional

from .neo4j import get_neo4j, is_neo4j_configured
from .store import get_sqlite_store


class GraphFacade:
    def __init__(self):
        self.sqlite = get_sqlite_store()
        self.neo = get_neo4j()

    @property
    def primary(self) -> str:
        return "neo4j" if self.neo.enabled else "sqlite"

    def _use_neo(self) -> bool:
        return bool(self.neo.enabled)

    def _disable_neo(self, err):
        self.neo.enabled = False
        self.neo.error = str(err)
        print(f"[OIG] Neo4j 不可用，读写改走 SQLite 兜底: {err}")

    def list_nodes(self, node_type: Optional[str] = None, include_merged: bool = False) -> list:
        if self._use_neo():
            try:
                return self.neo.list_nodes(node_type, include_merged=include_merged)
            except TypeError:
                nodes = self.neo.list_nodes(node_type)
                if include_merged:
                    return nodes
                return [n for n in nodes if (n.get("entity_status") or "ACTIVE") == "ACTIVE"]
            except Exception as e:
                self._disable_neo(e)
        return self.sqlite.list_nodes(node_type, include_merged=include_merged)

    def get_node(self, node_id: str) -> Optional[dict]:
        if self._use_neo():
            try:
                return self.neo.get_node(node_id)
            except Exception as e:
                self._disable_neo(e)
        return self.sqlite.get_node(node_id)

    def find_person(self, person_id: str) -> Optional[dict]:
        if self._use_neo():
            try:
                return self.neo.find_person(person_id)
            except Exception as e:
                self._disable_neo(e)
        return self.sqlite.find_person(person_id)

    def list_edges(self, relation: Optional[str] = None, source=None, target=None, include_merged: bool = False) -> list:
        if self._use_neo():
            try:
                return self.neo.list_edges(relation, source, target, include_merged=include_merged)
            except Exception as e:
                self._disable_neo(e)
        return self.sqlite.list_edges(relation, source, target, include_merged=include_merged)

    def neighbors(self, node_id: str, relations=None) -> list:
        if self._use_neo():
            try:
                return self.neo.neighbors(node_id, relations)
            except Exception as e:
                self._disable_neo(e)
        return self.sqlite.neighbors(node_id, relations)

    def upsert_node(self, node: dict):
        nid = self.sqlite.upsert_node(node)
        if self._use_neo():
            try:
                self.neo.upsert_node(node)
            except Exception as e:
                self._disable_neo(e)
        return nid

    def upsert_edge(self, source, target, relation, properties=None, record_history=True):
        edge_id = self.sqlite.upsert_edge(
            source, target, relation, properties, record_history=record_history,
        )
        if self._use_neo():
            try:
                edge = self.sqlite.get_edge(edge_id) or {}
                self.neo.upsert_edge(
                    source, target, relation, edge.get("properties") or properties,
                )
            except Exception as e:
                self._disable_neo(e)
        return edge_id

    def delete_edge(self, source, target, relation):
        edge_id = self.sqlite.delete_edge(source, target, relation)
        if self._use_neo():
            try:
                self.neo.delete_edge(source, target, relation)
            except Exception as e:
                self._disable_neo(e)
        return edge_id

    def get_edge(self, edge_id: str):
        if self._use_neo():
            try:
                parts = (edge_id or "").split("|")
                if len(parts) == 3:
                    rows = self.neo.list_edges(relation=parts[1], source=parts[0], target=parts[2])
                    if rows:
                        return rows[0]
            except Exception as e:
                self._disable_neo(e)
        return self.sqlite.get_edge(edge_id)

    def clear(self):
        self.sqlite.clear()
        if self._use_neo():
            try:
                self.neo.clear()
            except Exception as e:
                self._disable_neo(e)

    def stats(self):
        if self._use_neo():
            try:
                s = self.neo.stats()
                s["rebuilt_at"] = self.sqlite.get_meta("rebuilt_at")
                s["backend"] = "neo4j"
                s["primary"] = "neo4j"
                s["fallback"] = "sqlite"
                return s
            except Exception as e:
                self._disable_neo(e)
        s = self.sqlite.stats()
        s["backend"] = "sqlite"
        s["primary"] = "sqlite"
        s["fallback"] = "sqlite"
        return s

    def set_meta(self, key, value):
        return self.sqlite.set_meta(key, value)

    def get_meta(self, key, default=None):
        return self.sqlite.get_meta(key, default)

    def save_extraction(self, source_type, source_text, result):
        return self.sqlite.save_extraction(source_type, source_text, result)

    def list_extractions(self, limit=20):
        return self.sqlite.list_extractions(limit)

    def edge_history(self, edge_id: str):
        return self.sqlite.edge_history(edge_id)

    def person_relation_trends(self, person_id: str) -> list:
        edges = self.neighbors(person_id)
        result = []
        for e in edges:
            hist = self.sqlite.edge_history(e["id"])
            if not hist:
                continue
            result.append({
                "edge_id": e["id"],
                "source": e["source"],
                "target": e["target"],
                "relation": e["relation"],
                "current_strength": (e.get("properties") or {}).get("strength"),
                "history": [
                    {"strength": h["strength"], "recorded_at": h["recorded_at"]}
                    for h in hist
                ],
            })
        return result

    def replace_from_sqlite(self) -> bool:
        if not self._use_neo():
            return False
        nodes = self.sqlite.list_nodes()
        edges = self.sqlite.list_edges()
        return self.neo.replace_graph(nodes, edges)


_facade: Optional[GraphFacade] = None


def get_facade() -> GraphFacade:
    global _facade
    if _facade is None:
        _facade = GraphFacade()
    return _facade


def get_store() -> GraphFacade:
    return get_facade()


def bootstrap_graph():
    """启动时：Neo4j 为空则从 SQLite 导入；SQLite 为空则从 Neo4j 回填兜底。"""
    sqlite = get_sqlite_store()
    facade = get_facade()
    neo = get_neo4j()
    sql_n = sqlite.stats().get("node_count") or 0
    if not neo.enabled:
        print(f"[OIG] 主存=SQLite 兜底（Neo4j 不可用，nodes={sql_n}）")
        sqlite.set_meta("backend", "sqlite")
        return {"primary": "sqlite", "sqlite_nodes": sql_n, "neo4j": False}

    try:
        neo_n = neo.count_nodes()
        if neo_n == 0 and sql_n > 0:
            print(f"[OIG] Neo4j 为空，从 SQLite 导入 {sql_n} 个节点…")
            ok = neo.replace_graph(sqlite.list_nodes(), sqlite.list_edges())
            if ok:
                sqlite.set_meta("backend", "neo4j")
                print(f"[OIG] 主存=Neo4j，已导入 SQLite 数据")
                return {"primary": "neo4j", "imported": "sqlite_to_neo4j", "nodes": sql_n}
            print("[OIG] 导入 Neo4j 失败，继续使用 SQLite 兜底")
            return {"primary": "sqlite", "imported": False}

        if neo_n > 0 and sql_n == 0:
            print(f"[OIG] SQLite 为空，从 Neo4j 回填兜底 {neo_n} 个节点…")
            _copy_neo_to_sqlite(neo, sqlite)
            sqlite.set_meta("backend", "neo4j")
            print("[OIG] 主存=Neo4j，SQLite 兜底已回填")
            return {"primary": "neo4j", "imported": "neo4j_to_sqlite", "nodes": neo_n}

        sqlite.set_meta("backend", "neo4j")
        print(f"[OIG] 主存=Neo4j（{neo_n} 节点），SQLite 兜底（{sql_n} 节点）")
        return {
            "primary": "neo4j",
            "neo4j_nodes": neo_n,
            "sqlite_nodes": sql_n,
            "neo4j_configured": is_neo4j_configured(),
        }
    except Exception as e:
        facade._disable_neo(e)
        sqlite.set_meta("backend", "sqlite")
        return {"primary": "sqlite", "error": str(e)}


def _copy_neo_to_sqlite(neo, sqlite):
    for node in neo.list_nodes():
        sqlite.upsert_node(node)
    for edge in neo.list_edges():
        sqlite.upsert_edge(
            edge["source"],
            edge["target"],
            edge["relation"],
            edge.get("properties") or {},
            record_history=False,
        )
