"""本体 / 推理规则 / 语义建议仓储。修改可回滚。"""

import json
import sqlite3
import uuid
from contextlib import contextmanager

from database import DB_PATH
from timeutil import now_iso


def _now():
    return now_iso()


def _dumps(obj):
    return json.dumps(obj, ensure_ascii=False)


def _loads(raw, default=None):
    if raw is None or raw == "":
        return {} if default is None else default
    if isinstance(raw, (dict, list)):
        return raw
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return {} if default is None else default


class KnowledgeGovernanceStore:
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
                CREATE TABLE IF NOT EXISTS ontology_type (
                    id            TEXT PRIMARY KEY,
                    name          TEXT NOT NULL UNIQUE,
                    parent_id     TEXT,
                    description   TEXT,
                    schema_json   TEXT,
                    created_time  TEXT,
                    updated_time  TEXT
                )
            """)
            c.execute("""
                CREATE TABLE IF NOT EXISTS ontology_relation (
                    id            TEXT PRIMARY KEY,
                    name          TEXT NOT NULL,
                    source_type   TEXT NOT NULL,
                    target_type   TEXT NOT NULL,
                    description   TEXT,
                    rule_json     TEXT,
                    created_time  TEXT
                )
            """)
            c.execute("""
                CREATE TABLE IF NOT EXISTS reasoning_rule (
                    id              TEXT PRIMARY KEY,
                    name            TEXT NOT NULL,
                    condition_json  TEXT NOT NULL,
                    action_json     TEXT NOT NULL,
                    status          TEXT NOT NULL DEFAULT 'ACTIVE',
                    description     TEXT,
                    created_time    TEXT
                )
            """)
            c.execute("""
                CREATE TABLE IF NOT EXISTS semantic_suggestion (
                    id               TEXT PRIMARY KEY,
                    object_type      TEXT,
                    object_id        TEXT,
                    suggestion_type  TEXT,
                    confidence       REAL,
                    reason           TEXT,
                    payload_json     TEXT,
                    status           TEXT NOT NULL DEFAULT 'pending',
                    created_time     TEXT,
                    updated_time     TEXT
                )
            """)
            c.execute("""
                CREATE TABLE IF NOT EXISTS ontology_revision (
                    id            TEXT PRIMARY KEY,
                    reason        TEXT,
                    snapshot_json TEXT NOT NULL,
                    created_time  TEXT
                )
            """)
            c.execute("""
                CREATE TABLE IF NOT EXISTS kg_meta (
                    key   TEXT PRIMARY KEY,
                    value TEXT
                )
            """)
            self._migrate_work_items(c)
            self._migrate_constraints(c)

    @staticmethod
    def _migrate_work_items(c):
        cols = {row[1] for row in c.execute("PRAGMA table_info(semantic_suggestion)").fetchall()}
        for name, ddl in (
            ("fingerprint", "TEXT"),
            ("problem_code", "TEXT"),
            ("title", "TEXT"),
            ("current_json", "TEXT"),
            ("proposed_json", "TEXT"),
            ("applied_json", "TEXT"),
            ("source", "TEXT"),
        ):
            if name not in cols:
                c.execute(f"ALTER TABLE semantic_suggestion ADD COLUMN {name} {ddl}")
        c.execute(
            "UPDATE semantic_suggestion SET status = 'open' WHERE status IN ('pending', '')"
        )
        c.execute(
            "UPDATE semantic_suggestion SET status = 'rejected' WHERE status IN ('ignored')"
        )
        c.execute(
            """CREATE UNIQUE INDEX IF NOT EXISTS idx_sg_fingerprint
               ON semantic_suggestion(fingerprint) WHERE fingerprint IS NOT NULL AND fingerprint != ''"""
        )

    @staticmethod
    def _migrate_constraints(c):
        c.execute("""
            CREATE TABLE IF NOT EXISTS ontology_constraint (
                id               TEXT PRIMARY KEY,
                name             TEXT NOT NULL,
                kind             TEXT NOT NULL,
                object_type      TEXT,
                property         TEXT,
                message          TEXT,
                expression_json  TEXT,
                status           TEXT NOT NULL DEFAULT 'ACTIVE',
                created_time     TEXT,
                updated_time     TEXT
            )
        """)

    def set_meta(self, key, value):
        with self._db() as conn:
            conn.execute(
                """INSERT INTO kg_meta (key, value) VALUES (?, ?)
                   ON CONFLICT(key) DO UPDATE SET value = excluded.value""",
                (key, value if isinstance(value, str) else _dumps(value)),
            )

    def get_meta(self, key, default=None):
        with self._db() as conn:
            row = conn.execute("SELECT value FROM kg_meta WHERE key = ?", (key,)).fetchone()
            return row["value"] if row else default

    # ----- snapshot / rollback -----

    def snapshot(self, reason=""):
        data = {
            "types": self.list_types(),
            "relations": self.list_ontology_relations(),
            "rules": self.list_rules(include_inactive=True),
            "constraints": self.list_constraints(include_inactive=True),
            "retired_types": self.list_retired_types(),
        }
        rid = f"rev_{uuid.uuid4().hex[:12]}"
        with self._db() as conn:
            conn.execute(
                """INSERT INTO ontology_revision (id, reason, snapshot_json, created_time)
                   VALUES (?, ?, ?, ?)""",
                (rid, reason, _dumps(data), _now()),
            )
        return rid

    def list_revisions(self, limit=20):
        with self._db() as conn:
            rows = conn.execute(
                "SELECT id, reason, created_time FROM ontology_revision ORDER BY created_time DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]

    def rollback(self, revision_id):
        with self._db() as conn:
            row = conn.execute(
                "SELECT * FROM ontology_revision WHERE id = ?", (revision_id,)
            ).fetchone()
        if not row:
            raise ValueError("回滚点不存在")
        snap = _loads(row["snapshot_json"], default={})
        self.snapshot(reason=f"rollback-before:{revision_id}")
        with self._db() as conn:
            conn.execute("DELETE FROM ontology_type")
            conn.execute("DELETE FROM ontology_relation")
            conn.execute("DELETE FROM reasoning_rule")
            conn.execute("DELETE FROM ontology_constraint")
            for t in snap.get("types") or []:
                conn.execute(
                    """INSERT INTO ontology_type
                       (id, name, parent_id, description, schema_json, created_time, updated_time)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (
                        t["id"], t["name"], t.get("parent_id"), t.get("description"),
                        _dumps(t.get("schema") or t.get("schema_json") or {}),
                        t.get("created_time") or _now(), _now(),
                    ),
                )
            for r in snap.get("relations") or []:
                conn.execute(
                    """INSERT INTO ontology_relation
                       (id, name, source_type, target_type, description, rule_json, created_time)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (
                        r["id"], r["name"], r["source_type"], r["target_type"],
                        r.get("description"), _dumps(r.get("rule") or r.get("rule_json") or {}),
                        r.get("created_time") or _now(),
                    ),
                )
            for ru in snap.get("rules") or []:
                conn.execute(
                    """INSERT INTO reasoning_rule
                       (id, name, condition_json, action_json, status, description, created_time)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (
                        ru["id"], ru["name"],
                        _dumps(ru.get("condition") or ru.get("condition_json") or []),
                        _dumps(ru.get("action") or ru.get("action_json") or {}),
                        ru.get("status") or "ACTIVE", ru.get("description"),
                        ru.get("created_time") or _now(),
                    ),
                )
            for cons in snap.get("constraints") or []:
                conn.execute(
                    """INSERT INTO ontology_constraint
                       (id, name, kind, object_type, property, message, expression_json, status, created_time, updated_time)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        cons["id"], cons.get("name") or cons["id"], cons.get("kind") or "custom",
                        cons.get("object_type") or "", cons.get("property") or "",
                        cons.get("message") or "",
                        _dumps(cons.get("expression") or cons.get("expression_json") or {}),
                        cons.get("status") or "ACTIVE",
                        cons.get("created_time") or _now(), _now(),
                    ),
                )
        self.set_meta("retired_ontology_types", snap.get("retired_types") or [])
        return {"restored": revision_id}

    # ----- types -----

    def upsert_type(self, rec):
        tid = rec.get("id") or f"ot_{uuid.uuid4().hex[:10]}"
        existing = self.get_type(tid) or self.get_type_by_name(rec.get("name"))
        if existing:
            tid = existing["id"]
        now = _now()
        schema = rec.get("schema") if "schema" in rec else rec.get("schema_json")
        if existing and schema is None:
            schema = existing.get("schema")
        with self._db() as conn:
            conn.execute(
                """INSERT INTO ontology_type
                   (id, name, parent_id, description, schema_json, created_time, updated_time)
                   VALUES (?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(id) DO UPDATE SET
                     name=excluded.name,
                     parent_id=excluded.parent_id,
                     description=excluded.description,
                     schema_json=excluded.schema_json,
                     updated_time=excluded.updated_time
                """,
                (
                    tid, rec["name"], rec.get("parent_id"), rec.get("description") or "",
                    _dumps(schema or {}), existing["created_time"] if existing else now, now,
                ),
            )
        return self.get_type(tid)

    def get_type(self, tid):
        if not tid:
            return None
        with self._db() as conn:
            row = conn.execute("SELECT * FROM ontology_type WHERE id = ?", (tid,)).fetchone()
        return self._row_type(row) if row else None

    def get_type_by_name(self, name):
        if not name:
            return None
        with self._db() as conn:
            row = conn.execute("SELECT * FROM ontology_type WHERE name = ?", (name,)).fetchone()
        return self._row_type(row) if row else None

    def list_types(self):
        with self._db() as conn:
            rows = conn.execute("SELECT * FROM ontology_type ORDER BY name").fetchall()
        return [self._row_type(r) for r in rows]

    def delete_type(self, tid):
        with self._db() as conn:
            conn.execute("UPDATE ontology_type SET parent_id = NULL WHERE parent_id = ?", (tid,))
            conn.execute("DELETE FROM ontology_type WHERE id = ?", (tid,))

    # ----- ontology relations -----

    def upsert_ontology_relation(self, rec):
        rid = rec.get("id") or f"or_{uuid.uuid4().hex[:10]}"
        with self._db() as conn:
            conn.execute(
                """INSERT INTO ontology_relation
                   (id, name, source_type, target_type, description, rule_json, created_time)
                   VALUES (?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(id) DO UPDATE SET
                     name=excluded.name,
                     source_type=excluded.source_type,
                     target_type=excluded.target_type,
                     description=excluded.description,
                     rule_json=excluded.rule_json
                """,
                (
                    rid, rec["name"], rec["source_type"], rec["target_type"],
                    rec.get("description") or "", _dumps(rec.get("rule") or {}),
                    rec.get("created_time") or _now(),
                ),
            )
        return self.get_ontology_relation(rid)

    def get_ontology_relation(self, rid):
        with self._db() as conn:
            row = conn.execute("SELECT * FROM ontology_relation WHERE id = ?", (rid,)).fetchone()
        return self._row_orel(row) if row else None

    def list_ontology_relations(self):
        with self._db() as conn:
            rows = conn.execute("SELECT * FROM ontology_relation ORDER BY name").fetchall()
        return [self._row_orel(r) for r in rows]

    def find_ontology_relation(self, name, source_type, target_type):
        with self._db() as conn:
            row = conn.execute(
                """SELECT * FROM ontology_relation
                   WHERE name = ? AND source_type = ? AND target_type = ?""",
                (name, source_type, target_type),
            ).fetchone()
        return self._row_orel(row) if row else None

    def delete_ontology_relation(self, rid):
        with self._db() as conn:
            conn.execute("DELETE FROM ontology_relation WHERE id = ?", (rid,))
        return {"deleted": rid}

    # ----- constraints -----

    def upsert_constraint(self, rec):
        cid = rec.get("id") or f"oc_{uuid.uuid4().hex[:10]}"
        existing = self.get_constraint(cid)
        now = _now()
        with self._db() as conn:
            conn.execute(
                """INSERT INTO ontology_constraint
                   (id, name, kind, object_type, property, message, expression_json, status, created_time, updated_time)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(id) DO UPDATE SET
                     name=excluded.name,
                     kind=excluded.kind,
                     object_type=excluded.object_type,
                     property=excluded.property,
                     message=excluded.message,
                     expression_json=excluded.expression_json,
                     status=excluded.status,
                     updated_time=excluded.updated_time
                """,
                (
                    cid,
                    rec.get("name") or cid,
                    rec.get("kind") or "custom",
                    rec.get("object_type") or "",
                    rec.get("property") or "",
                    rec.get("message") or "",
                    _dumps(rec.get("expression") or rec.get("expression_json") or {}),
                    rec.get("status") or "ACTIVE",
                    existing["created_time"] if existing else now,
                    now,
                ),
            )
        return self.get_constraint(cid)

    def get_constraint(self, cid):
        if not cid:
            return None
        with self._db() as conn:
            row = conn.execute("SELECT * FROM ontology_constraint WHERE id = ?", (cid,)).fetchone()
        return self._row_cons(row) if row else None

    def list_constraints(self, include_inactive=False):
        q = "SELECT * FROM ontology_constraint"
        if not include_inactive:
            q += " WHERE status = 'ACTIVE'"
        q += " ORDER BY kind, name"
        with self._db() as conn:
            rows = conn.execute(q).fetchall()
        return [self._row_cons(r) for r in rows]

    def delete_constraint(self, cid):
        with self._db() as conn:
            conn.execute("DELETE FROM ontology_constraint WHERE id = ?", (cid,))
        return {"deleted": cid}

    # ----- rules -----

    def upsert_rule(self, rec):
        rid = rec.get("id") or f"rr_{uuid.uuid4().hex[:10]}"
        with self._db() as conn:
            conn.execute(
                """INSERT INTO reasoning_rule
                   (id, name, condition_json, action_json, status, description, created_time)
                   VALUES (?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(id) DO UPDATE SET
                     name=excluded.name,
                     condition_json=excluded.condition_json,
                     action_json=excluded.action_json,
                     status=excluded.status,
                     description=excluded.description
                """,
                (
                    rid, rec["name"],
                    _dumps(rec.get("condition") or rec.get("condition_json") or []),
                    _dumps(rec.get("action") or rec.get("action_json") or {}),
                    rec.get("status") or "ACTIVE",
                    rec.get("description") or "",
                    rec.get("created_time") or _now(),
                ),
            )
        return self.get_rule(rid)

    def get_rule(self, rid):
        with self._db() as conn:
            row = conn.execute("SELECT * FROM reasoning_rule WHERE id = ?", (rid,)).fetchone()
        return self._row_rule(row) if row else None

    def list_rules(self, include_inactive=False):
        q = "SELECT * FROM reasoning_rule"
        if not include_inactive:
            q += " WHERE status = 'ACTIVE'"
        q += " ORDER BY name"
        with self._db() as conn:
            rows = conn.execute(q).fetchall()
        return [self._row_rule(r) for r in rows]

    def set_rule_status(self, rid, status):
        with self._db() as conn:
            conn.execute("UPDATE reasoning_rule SET status = ? WHERE id = ?", (status, rid))
        return self.get_rule(rid)

    # ----- work items (semantic_suggestion) -----

    def get_by_fingerprint(self, fingerprint):
        if not fingerprint:
            return None
        with self._db() as conn:
            row = conn.execute(
                "SELECT * FROM semantic_suggestion WHERE fingerprint = ?", (fingerprint,)
            ).fetchone()
        return self._row_sug(row) if row else None

    def upsert_work_item(self, rec, force=False):
        fp = rec.get("fingerprint") or ""
        existing = self.get_by_fingerprint(fp) if fp else None
        if existing and existing.get("status") in ("accepted", "rejected", "deferred", "resolved") and not force:
            return existing, False
        now = _now()
        proposed = rec.get("proposed") if "proposed" in rec else rec.get("proposed_json")
        current = rec.get("current") if "current" in rec else rec.get("current_json")
        payload = rec.get("payload") or proposed or {}
        if existing:
            sid = existing["id"]
            with self._db() as conn:
                conn.execute(
                    """UPDATE semantic_suggestion SET
                         object_type=?, object_id=?, suggestion_type=?, confidence=?, reason=?,
                         payload_json=?, status=?, fingerprint=?, problem_code=?, title=?,
                         current_json=?, proposed_json=?, source=?, updated_time=?
                       WHERE id=?""",
                    (
                        rec.get("object_type") or existing.get("object_type"),
                        rec.get("object_id") or existing.get("object_id"),
                        rec.get("suggestion_type") or existing.get("suggestion_type"),
                        rec.get("confidence") if rec.get("confidence") is not None else existing.get("confidence"),
                        rec.get("reason") or existing.get("reason") or "",
                        _dumps(payload),
                        "open" if force else (rec.get("status") or "open"),
                        fp,
                        rec.get("problem_code") or existing.get("problem_code") or "",
                        rec.get("title") or existing.get("title") or "",
                        _dumps(current if current is not None else existing.get("current") or {}),
                        _dumps(proposed if proposed is not None else existing.get("proposed") or payload),
                        rec.get("source") or existing.get("source") or "analyze",
                        now,
                        sid,
                    ),
                )
            return self.get_suggestion(sid), False
        sid = rec.get("id") or f"sg_{uuid.uuid4().hex[:12]}"
        with self._db() as conn:
            conn.execute(
                """INSERT INTO semantic_suggestion
                   (id, object_type, object_id, suggestion_type, confidence, reason,
                    payload_json, status, created_time, updated_time,
                    fingerprint, problem_code, title, current_json, proposed_json, applied_json, source)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    sid, rec.get("object_type"), rec.get("object_id"),
                    rec.get("suggestion_type"), rec.get("confidence") or 0,
                    rec.get("reason") or "", _dumps(payload),
                    rec.get("status") or "open", now, now,
                    fp, rec.get("problem_code") or "", rec.get("title") or "",
                    _dumps(current or {}), _dumps(proposed or payload),
                    _dumps(rec.get("applied") or {}),
                    rec.get("source") or "analyze",
                ),
            )
        return self.get_suggestion(sid), True

    def add_suggestion(self, rec):
        item, _ = self.upsert_work_item(rec)
        return item

    def get_suggestion(self, sid):
        with self._db() as conn:
            row = conn.execute("SELECT * FROM semantic_suggestion WHERE id = ?", (sid,)).fetchone()
        return self._row_sug(row) if row else None

    def list_work_items(self, status="open", suggestion_type=None, problem_code=None, page=1, page_size=80):
        q = "SELECT * FROM semantic_suggestion WHERE 1=1"
        params = []
        if status and status != "all":
            if status == "open":
                q += " AND status IN ('open', 'pending')"
            elif status == "rejected":
                q += " AND status IN ('rejected', 'ignored')"
            else:
                q += " AND status = ?"
                params.append(status)
        if suggestion_type:
            q += " AND suggestion_type = ?"
            params.append(suggestion_type)
        if problem_code:
            q += " AND problem_code = ?"
            params.append(problem_code)
        q += " ORDER BY confidence DESC, created_time DESC"
        with self._db() as conn:
            total = conn.execute(
                f"SELECT COUNT(*) FROM ({q})", params
            ).fetchone()[0]
            q += " LIMIT ? OFFSET ?"
            rows = conn.execute(q, [*params, page_size, max(0, (page - 1) * page_size)]).fetchall()
        return {"total": total, "items": [self._row_sug(r) for r in rows]}

    def list_suggestions(self, status="pending"):
        mapped = "open" if status in ("pending", "open") else status
        return self.list_work_items(status=mapped)["items"]

    def update_suggestion(self, sid, **fields):
        allowed = ("status", "reason", "title", "proposed", "applied", "payload")
        sets, params = [], []
        for k in allowed:
            if k not in fields:
                continue
            col = {
                "proposed": "proposed_json",
                "applied": "applied_json",
                "payload": "payload_json",
            }.get(k, k)
            val = fields[k]
            if col.endswith("_json"):
                val = _dumps(val)
            sets.append(f"{col} = ?")
            params.append(val)
        if not sets:
            return self.get_suggestion(sid)
        sets.append("updated_time = ?")
        params.append(_now())
        params.append(sid)
        with self._db() as conn:
            conn.execute(f"UPDATE semantic_suggestion SET {', '.join(sets)} WHERE id = ?", params)
        return self.get_suggestion(sid)

    def list_accepted(self):
        return self.list_work_items(status="accepted", page_size=2000)["items"]

    def clear_pending_suggestions(self):
        """Spec V1.1：禁止清空 open 工单。保留空实现以免旧调用误删。"""
        return None

    def list_suppressed_instances(self):
        raw = self.get_meta("suppressed_instances", "[]")
        data = _loads(raw, default=[])
        return data if isinstance(data, list) else []

    def suppressed_node_ids(self):
        ids = set()
        for item in self.list_suppressed_instances():
            if isinstance(item, str):
                ids.add(item)
            elif item.get("node_id"):
                ids.add(item["node_id"])
        return ids

    def suppressed_keys(self):
        """(graph_type, name)，用于重建时跳过没有 preferred_id 的部门/项目等。"""
        keys = set()
        for item in self.list_suppressed_instances():
            if not isinstance(item, dict):
                continue
            gtype = (item.get("graph_type") or "").strip()
            name = (item.get("name") or "").strip()
            if gtype and name:
                keys.add((gtype, name))
        return keys

    def add_suppressed_instance(self, rec):
        items = self.list_suppressed_instances()
        nid = rec.get("node_id")
        items = [x for x in items if (x if isinstance(x, str) else x.get("node_id")) != nid]
        items.append({
            "node_id": nid,
            "graph_type": rec.get("graph_type") or "",
            "name": rec.get("name") or "",
            "source_event_id": rec.get("source_event_id") or "",
            "updated_time": _now(),
        })
        self.set_meta("suppressed_instances", items)

    def list_retired_types(self):
        raw = self.get_meta("retired_ontology_types", "[]")
        data = _loads(raw, default=[])
        return [str(x) for x in data if x] if isinstance(data, list) else []

    def retired_type_names(self):
        return set(self.list_retired_types())

    def retire_type_name(self, name):
        name = (name or "").strip()
        if not name:
            return
        items = self.list_retired_types()
        if name not in items:
            items.append(name)
            self.set_meta("retired_ontology_types", items)

    def unretire_type_name(self, name):
        name = (name or "").strip()
        items = [x for x in self.list_retired_types() if x != name]
        self.set_meta("retired_ontology_types", items)

    @staticmethod
    def _row_type(row):
        item = dict(row)
        item["schema"] = _loads(item.pop("schema_json", None), default={})
        return item

    @staticmethod
    def _row_orel(row):
        item = dict(row)
        item["rule"] = _loads(item.pop("rule_json", None), default={})
        return item

    @staticmethod
    def _row_cons(row):
        item = dict(row)
        item["expression"] = _loads(item.pop("expression_json", None), default={})
        return item

    @staticmethod
    def _row_rule(row):
        item = dict(row)
        item["condition"] = _loads(item.pop("condition_json", None), default=[])
        item["action"] = _loads(item.pop("action_json", None), default={})
        return item

    @staticmethod
    def _row_sug(row):
        item = dict(row)
        item["payload"] = _loads(item.pop("payload_json", None), default={})
        item["current"] = _loads(item.pop("current_json", None), default={})
        item["proposed"] = _loads(item.pop("proposed_json", None), default={}) or item.get("payload") or {}
        item["applied"] = _loads(item.pop("applied_json", None), default={})
        if item.get("status") == "pending":
            item["status"] = "open"
        if item.get("status") == "ignored":
            item["status"] = "rejected"
        return item


_store = None


def get_kg_store() -> KnowledgeGovernanceStore:
    global _store
    if _store is None:
        _store = KnowledgeGovernanceStore()
    return _store
