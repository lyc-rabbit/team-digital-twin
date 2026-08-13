"""
SQLite 图存储（兜底）

Neo4j 不可用时保证读写不挂；重建时作为暂存层，再全量发布到 Neo4j。
"""

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from typing import Optional

from database import DB_PATH


def _now():
    return datetime.now().isoformat(timespec="seconds")


def _dumps(obj):
    return json.dumps(obj, ensure_ascii=False)


def _loads(raw, default=None):
    if raw is None:
        return {} if default is None else default
    if isinstance(raw, (dict, list)):
        return raw
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return {} if default is None else default


class GraphStore:
    """OIG 节点 / 边 / 演化历史 / 抽取日志。"""

    def __init__(self, db_path=None):
        self.db_path = db_path or DB_PATH
        self.init_schema()

    def _connect(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    @contextmanager
    def _db(self):
        conn = self._connect()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def init_schema(self):
        with self._db() as conn:
            c = conn.cursor()
            c.execute("""
                CREATE TABLE IF NOT EXISTS oig_nodes (
                    id          TEXT PRIMARY KEY,
                    type        TEXT NOT NULL,
                    name        TEXT NOT NULL,
                    properties  TEXT,
                    updated_at  TEXT
                )
            """)
            c.execute("""
                CREATE TABLE IF NOT EXISTS oig_edges (
                    id          TEXT PRIMARY KEY,
                    source      TEXT NOT NULL,
                    target      TEXT NOT NULL,
                    relation    TEXT NOT NULL,
                    properties  TEXT,
                    updated_at  TEXT
                )
            """)
            c.execute("""
                CREATE TABLE IF NOT EXISTS oig_edge_history (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    edge_id     TEXT NOT NULL,
                    strength    REAL,
                    properties  TEXT,
                    recorded_at TEXT
                )
            """)
            c.execute("""
                CREATE TABLE IF NOT EXISTS oig_extractions (
                    id           INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_type  TEXT,
                    source_text  TEXT,
                    result_json  TEXT,
                    created_at   TEXT
                )
            """)
            c.execute("""
                CREATE TABLE IF NOT EXISTS oig_meta (
                    key   TEXT PRIMARY KEY,
                    value TEXT
                )
            """)
            c.execute("CREATE INDEX IF NOT EXISTS idx_oig_nodes_type ON oig_nodes(type)")
            c.execute("CREATE INDEX IF NOT EXISTS idx_oig_edges_rel ON oig_edges(relation)")
            c.execute("CREATE INDEX IF NOT EXISTS idx_oig_edges_src ON oig_edges(source)")
            c.execute("CREATE INDEX IF NOT EXISTS idx_oig_edges_tgt ON oig_edges(target)")

    def set_meta(self, key, value):
        with self._db() as conn:
            conn.execute(
                """INSERT INTO oig_meta (key, value) VALUES (?, ?)
                   ON CONFLICT(key) DO UPDATE SET value = excluded.value""",
                (key, value if isinstance(value, str) else _dumps(value)),
            )

    def get_meta(self, key, default=None):
        with self._db() as conn:
            row = conn.execute("SELECT value FROM oig_meta WHERE key = ?", (key,)).fetchone()
            return row["value"] if row else default

    def clear(self):
        with self._db() as conn:
            conn.execute("DELETE FROM oig_edges")
            conn.execute("DELETE FROM oig_nodes")

    def upsert_node(self, node: dict):
        nid = node["id"]
        ntype = node["type"]
        name = node.get("name") or nid
        props = {k: v for k, v in node.items() if k not in ("id", "type", "name")}
        with self._db() as conn:
            conn.execute(
                """INSERT INTO oig_nodes (id, type, name, properties, updated_at)
                   VALUES (?, ?, ?, ?, ?)
                   ON CONFLICT(id) DO UPDATE SET
                     type = excluded.type,
                     name = excluded.name,
                     properties = excluded.properties,
                     updated_at = excluded.updated_at""",
                (nid, ntype, name, _dumps(props), _now()),
            )
        return nid

    def get_node(self, node_id: str) -> Optional[dict]:
        with self._db() as conn:
            row = conn.execute("SELECT * FROM oig_nodes WHERE id = ?", (node_id,)).fetchone()
            if not row:
                return None
            return self._row_to_node(row)

    def find_person(self, person_id: str) -> Optional[dict]:
        node = self.get_node(person_id)
        if node and node.get("type") == "Person":
            return node
        with self._db() as conn:
            rows = conn.execute(
                "SELECT * FROM oig_nodes WHERE type = 'Person'"
            ).fetchall()
        for row in rows:
            node = self._row_to_node(row)
            if node["id"] == person_id or node.get("name") == person_id:
                return node
        return None

    def list_nodes(self, node_type: Optional[str] = None) -> list:
        query = "SELECT * FROM oig_nodes"
        params = []
        if node_type:
            query += " WHERE type = ?"
            params.append(node_type)
        query += " ORDER BY type, name"
        with self._db() as conn:
            rows = conn.execute(query, params).fetchall()
        return [self._row_to_node(r) for r in rows]

    def upsert_edge(self, source, target, relation, properties=None, record_history=True):
        properties = dict(properties or {})
        properties.setdefault("last_update", datetime.now().strftime("%Y-%m-%d"))
        edge_id = f"{source}|{relation}|{target}"
        existing = self.get_edge(edge_id)
        if existing:
            old_props = existing.get("properties") or {}
            merged = dict(old_props)
            merged.update(properties)
            # 协作频率累加
            if "frequency" in properties and "frequency" in old_props:
                try:
                    merged["frequency"] = int(old_props.get("frequency") or 0) + int(properties.get("frequency") or 0)
                except (TypeError, ValueError):
                    pass
            if "evidence" in old_props or "evidence" in properties:
                ev = list(old_props.get("evidence") or [])
                for item in properties.get("evidence") or []:
                    if item not in ev:
                        ev.append(item)
                merged["evidence"] = ev[:20]
            properties = merged
            if record_history:
                old_strength = float(old_props.get("strength") or 0)
                new_strength = float(properties.get("strength") or old_strength)
                if abs(new_strength - old_strength) >= 0.05:
                    self._append_history(edge_id, new_strength, properties)
        with self._db() as conn:
            conn.execute(
                """INSERT INTO oig_edges (id, source, target, relation, properties, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?)
                   ON CONFLICT(id) DO UPDATE SET
                     properties = excluded.properties,
                     updated_at = excluded.updated_at""",
                (edge_id, source, target, relation, _dumps(properties), _now()),
            )
        return edge_id

    def get_edge(self, edge_id: str) -> Optional[dict]:
        with self._db() as conn:
            row = conn.execute("SELECT * FROM oig_edges WHERE id = ?", (edge_id,)).fetchone()
            return self._row_to_edge(row) if row else None

    def list_edges(self, relation: Optional[str] = None, source=None, target=None) -> list:
        query = "SELECT * FROM oig_edges WHERE 1=1"
        params = []
        if relation:
            query += " AND relation = ?"
            params.append(relation)
        if source:
            query += " AND source = ?"
            params.append(source)
        if target:
            query += " AND target = ?"
            params.append(target)
        with self._db() as conn:
            rows = conn.execute(query, params).fetchall()
        return [self._row_to_edge(r) for r in rows]

    def neighbors(self, node_id: str, relations=None) -> list:
        query = """
            SELECT * FROM oig_edges
            WHERE source = ? OR target = ?
        """
        with self._db() as conn:
            rows = conn.execute(query, (node_id, node_id)).fetchall()
        edges = [self._row_to_edge(r) for r in rows]
        if relations:
            allowed = set(relations)
            edges = [e for e in edges if e["relation"] in allowed]
        return edges

    def edge_history(self, edge_id: str) -> list:
        with self._db() as conn:
            rows = conn.execute(
                """SELECT * FROM oig_edge_history
                   WHERE edge_id = ? ORDER BY recorded_at ASC""",
                (edge_id,),
            ).fetchall()
        return [dict(r) | {"properties": _loads(r["properties"])} for r in rows]

    def person_relation_trends(self, person_id: str) -> list:
        edges = self.neighbors(person_id)
        result = []
        for e in edges:
            hist = self.edge_history(e["id"])
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

    def save_extraction(self, source_type, source_text, result):
        with self._db() as conn:
            c = conn.cursor()
            c.execute(
                """INSERT INTO oig_extractions (source_type, source_text, result_json, created_at)
                   VALUES (?, ?, ?, ?)""",
                (source_type, source_text, _dumps(result), _now()),
            )
            return c.lastrowid

    def list_extractions(self, limit=20):
        with self._db() as conn:
            rows = conn.execute(
                "SELECT * FROM oig_extractions ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        result = []
        for r in rows:
            item = dict(r)
            item["result_json"] = _loads(item.get("result_json"), default={})
            result.append(item)
        return result

    def stats(self):
        nodes = self.list_nodes()
        edges = self.list_edges()
        by_type = {}
        for n in nodes:
            by_type[n["type"]] = by_type.get(n["type"], 0) + 1
        by_rel = {}
        for e in edges:
            by_rel[e["relation"]] = by_rel.get(e["relation"], 0) + 1
        return {
            "node_count": len(nodes),
            "edge_count": len(edges),
            "nodes_by_type": by_type,
            "edges_by_relation": by_rel,
            "rebuilt_at": self.get_meta("rebuilt_at"),
            "backend": self.get_meta("backend") or "sqlite",
        }

    def _append_history(self, edge_id, strength, properties):
        with self._db() as conn:
            conn.execute(
                """INSERT INTO oig_edge_history (edge_id, strength, properties, recorded_at)
                   VALUES (?, ?, ?, ?)""",
                (edge_id, strength, _dumps(properties), _now()),
            )

    @staticmethod
    def _row_to_node(row):
        item = dict(row)
        props = _loads(item.pop("properties", None))
        node = {
            "id": item["id"],
            "type": item["type"],
            "name": item["name"],
            **props,
        }
        node["updated_at"] = item.get("updated_at")
        return node

    @staticmethod
    def _row_to_edge(row):
        item = dict(row)
        return {
            "id": item["id"],
            "source": item["source"],
            "target": item["target"],
            "relation": item["relation"],
            "properties": _loads(item.get("properties")),
            "updated_at": item.get("updated_at"),
        }


_store = None


def get_sqlite_store() -> GraphStore:
    global _store
    if _store is None:
        _store = GraphStore()
    return _store


def get_store() -> GraphStore:
    """SQLite 实例。业务读写请走 facade.get_facade()。"""
    return get_sqlite_store()
