"""时态事实 / 事件 / 快照仓储。只关闭事实，不删除。"""

import json
import sqlite3
import uuid
from contextlib import contextmanager

from database import DB_PATH
from timeutil import now_iso, parse_day, interval_contains, intervals_overlap

from .types import LIFECYCLE_ACTIVE


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


class TemporalStore:
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
                CREATE TABLE IF NOT EXISTS temporal_fact (
                    id               TEXT PRIMARY KEY,
                    subject_id       TEXT NOT NULL,
                    predicate        TEXT NOT NULL,
                    object_id        TEXT NOT NULL,
                    valid_from       TEXT NOT NULL,
                    valid_to         TEXT,
                    confidence       REAL DEFAULT 1.0,
                    source_event_id  TEXT,
                    source           TEXT,
                    inferred         INTEGER DEFAULT 0,
                    evidence_json    TEXT,
                    created_time     TEXT,
                    updated_time     TEXT
                )
            """)
            c.execute("CREATE INDEX IF NOT EXISTS idx_tf_subj ON temporal_fact(subject_id, predicate)")
            c.execute("CREATE INDEX IF NOT EXISTS idx_tf_obj ON temporal_fact(object_id, predicate)")
            c.execute("CREATE INDEX IF NOT EXISTS idx_tf_time ON temporal_fact(valid_from, valid_to)")
            c.execute("""
                CREATE TABLE IF NOT EXISTS temporal_event (
                    id               TEXT PRIMARY KEY,
                    event_type       TEXT NOT NULL,
                    event_time       TEXT NOT NULL,
                    description      TEXT,
                    operator         TEXT,
                    team_event_id    TEXT,
                    payload_json     TEXT,
                    created_time     TEXT
                )
            """)
            c.execute("""
                CREATE TABLE IF NOT EXISTS entity_lifecycle (
                    entity_id        TEXT PRIMARY KEY,
                    entity_type      TEXT,
                    status           TEXT NOT NULL,
                    valid_from       TEXT,
                    valid_to         TEXT,
                    source_event_id  TEXT,
                    updated_time     TEXT
                )
            """)
            c.execute("""
                CREATE TABLE IF NOT EXISTS temporal_snapshot (
                    id               TEXT PRIMARY KEY,
                    snapshot_time    TEXT NOT NULL,
                    graph_version    TEXT,
                    stats_json       TEXT,
                    created_time     TEXT
                )
            """)

    def insert_fact(self, rec):
        fid = rec.get("id") or f"tf_{uuid.uuid4().hex[:12]}"
        now = now_iso()
        with self._db() as conn:
            conn.execute(
                """INSERT INTO temporal_fact
                   (id, subject_id, predicate, object_id, valid_from, valid_to,
                    confidence, source_event_id, source, inferred, evidence_json,
                    created_time, updated_time)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    fid,
                    rec["subject_id"],
                    rec["predicate"],
                    rec["object_id"],
                    parse_day(rec.get("valid_from")) or parse_day(now) or now[:10],
                    parse_day(rec.get("valid_to")) or "",
                    rec.get("confidence") if rec.get("confidence") is not None else 1.0,
                    rec.get("source_event_id") or "",
                    rec.get("source") or "system",
                    1 if rec.get("inferred") else 0,
                    _dumps(rec.get("evidence") or rec.get("evidence_json") or {}),
                    rec.get("created_time") or now,
                    now,
                ),
            )
        return self.get_fact(fid)

    def get_fact(self, fid):
        with self._db() as conn:
            row = conn.execute("SELECT * FROM temporal_fact WHERE id = ?", (fid,)).fetchone()
        return self._row_fact(row) if row else None

    def list_facts(self, subject_id=None, object_id=None, predicate=None, open_only=False, inferred=None):
        q = "SELECT * FROM temporal_fact WHERE 1=1"
        params = []
        if subject_id:
            q += " AND subject_id = ?"
            params.append(subject_id)
        if object_id:
            q += " AND object_id = ?"
            params.append(object_id)
        if predicate:
            q += " AND predicate = ?"
            params.append(predicate)
        if open_only:
            q += " AND (valid_to IS NULL OR valid_to = '')"
        if inferred is True:
            q += " AND inferred = 1"
        elif inferred is False:
            q += " AND inferred = 0"
        q += " ORDER BY valid_from, created_time"
        with self._db() as conn:
            rows = conn.execute(q, params).fetchall()
        return [self._row_fact(r) for r in rows]

    def facts_as_of(self, when, predicate=None):
        items = self.list_facts(predicate=predicate)
        return [f for f in items if interval_contains(f.get("valid_from"), f.get("valid_to"), when)]

    def facts_overlapping(self, start, end, subject_id=None, object_id=None, predicate=None):
        items = self.list_facts(subject_id=subject_id, object_id=object_id, predicate=predicate)
        return [
            f for f in items
            if intervals_overlap(f.get("valid_from"), f.get("valid_to"), start, end)
        ]

    def find_open(self, subject_id, predicate, object_id):
        with self._db() as conn:
            row = conn.execute(
                """SELECT * FROM temporal_fact
                   WHERE subject_id = ? AND predicate = ? AND object_id = ?
                     AND (valid_to IS NULL OR valid_to = '')
                   ORDER BY valid_from DESC LIMIT 1""",
                (subject_id, predicate, object_id),
            ).fetchone()
        return self._row_fact(row) if row else None

    def close_fact(self, fid, valid_to, source_event_id=""):
        day = parse_day(valid_to)
        with self._db() as conn:
            conn.execute(
                """UPDATE temporal_fact
                   SET valid_to = ?, source_event_id = CASE
                     WHEN ? = '' THEN source_event_id ELSE ?
                   END, updated_time = ?
                   WHERE id = ? AND (valid_to IS NULL OR valid_to = '')""",
                (day or "", source_event_id or "", source_event_id or "", now_iso(), fid),
            )
        return self.get_fact(fid)

    def close_open_matching(self, *, predicate, subject_id=None, object_id=None,
                            valid_to="", source_event_id="", exclude_subject=None):
        closed = []
        for fact in self.list_facts(subject_id=subject_id, object_id=object_id, predicate=predicate, open_only=True):
            if exclude_subject and fact["subject_id"] == exclude_subject:
                continue
            rec = self.close_fact(fact["id"], valid_to, source_event_id)
            if rec:
                closed.append(rec)
        return closed

    def insert_event(self, rec):
        eid = rec.get("id") or f"te_{uuid.uuid4().hex[:12]}"
        with self._db() as conn:
            conn.execute(
                """INSERT INTO temporal_event
                   (id, event_type, event_time, description, operator, team_event_id, payload_json, created_time)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    eid,
                    rec["event_type"],
                    parse_day(rec.get("event_time")) or now_iso()[:10],
                    rec.get("description") or "",
                    rec.get("operator") or "",
                    str(rec.get("team_event_id") or ""),
                    _dumps(rec.get("payload") or {}),
                    now_iso(),
                ),
            )
        return self.get_event(eid)

    def get_event(self, eid):
        with self._db() as conn:
            row = conn.execute("SELECT * FROM temporal_event WHERE id = ?", (eid,)).fetchone()
        return self._row_event(row) if row else None

    def list_events(self, limit=80, entity_id=None):
        with self._db() as conn:
            rows = conn.execute(
                "SELECT * FROM temporal_event ORDER BY event_time DESC, created_time DESC LIMIT ?",
                (limit,),
            ).fetchall()
        items = [self._row_event(r) for r in rows]
        if entity_id:
            filtered = []
            for ev in items:
                payload = ev.get("payload") or {}
                blob = " ".join(str(x) for x in payload.values()) + (ev.get("description") or "")
                if entity_id in blob or entity_id in (payload.get("person_id"), payload.get("project_id"), payload.get("resource_id")):
                    filtered.append(ev)
            return filtered
        return items

    def upsert_lifecycle(self, rec):
        now = now_iso()
        with self._db() as conn:
            conn.execute(
                """INSERT INTO entity_lifecycle
                   (entity_id, entity_type, status, valid_from, valid_to, source_event_id, updated_time)
                   VALUES (?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(entity_id) DO UPDATE SET
                     entity_type=excluded.entity_type,
                     status=excluded.status,
                     valid_from=excluded.valid_from,
                     valid_to=excluded.valid_to,
                     source_event_id=excluded.source_event_id,
                     updated_time=excluded.updated_time""",
                (
                    rec["entity_id"],
                    rec.get("entity_type") or "",
                    rec.get("status") or LIFECYCLE_ACTIVE,
                    parse_day(rec.get("valid_from")) or "",
                    parse_day(rec.get("valid_to")) or "",
                    rec.get("source_event_id") or "",
                    now,
                ),
            )
        return self.get_lifecycle(rec["entity_id"])

    def get_lifecycle(self, entity_id):
        with self._db() as conn:
            row = conn.execute(
                "SELECT * FROM entity_lifecycle WHERE entity_id = ?", (entity_id,)
            ).fetchone()
        return dict(row) if row else None

    def list_lifecycles(self):
        with self._db() as conn:
            rows = conn.execute("SELECT * FROM entity_lifecycle").fetchall()
        return [dict(r) for r in rows]

    def add_snapshot(self, snapshot_time, graph_version="", stats=None):
        sid = f"ts_{uuid.uuid4().hex[:12]}"
        with self._db() as conn:
            conn.execute(
                """INSERT INTO temporal_snapshot
                   (id, snapshot_time, graph_version, stats_json, created_time)
                   VALUES (?, ?, ?, ?, ?)""",
                (sid, parse_day(snapshot_time) or snapshot_time, graph_version, _dumps(stats or {}), now_iso()),
            )
        return sid

    def list_snapshots(self, limit=20):
        with self._db() as conn:
            rows = conn.execute(
                "SELECT * FROM temporal_snapshot ORDER BY snapshot_time DESC, created_time DESC LIMIT ?",
                (limit,),
            ).fetchall()
        out = []
        for r in rows:
            item = dict(r)
            item["stats"] = _loads(item.pop("stats_json", None), default={})
            out.append(item)
        return out

    @staticmethod
    def _row_fact(row):
        item = dict(row)
        item["evidence"] = _loads(item.pop("evidence_json", None), default={})
        item["inferred"] = bool(item.get("inferred"))
        return item

    @staticmethod
    def _row_event(row):
        item = dict(row)
        item["payload"] = _loads(item.pop("payload_json", None), default={})
        return item


_store = None


def get_temporal_store() -> TemporalStore:
    global _store
    if _store is None:
        _store = TemporalStore()
    return _store
