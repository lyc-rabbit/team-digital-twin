"""事实 / 来源 / 绑定 / 血缘 / 冲突 / 抽取任务仓储。删除为软删除。"""

import json
import sqlite3
import uuid
from contextlib import contextmanager

from database import DB_PATH
from timeutil import now_iso, today

from .types import (
    STATUS_EXTRACTED,
    STATUS_CONFIRMED,
    STATUS_DELETED,
    STATUS_CONFLICT,
    ACTIVE_FACT_STATUSES,
    DERIVED_ACTIVE,
)


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


def _new_id(prefix):
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


class FactStore:
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
                CREATE TABLE IF NOT EXISTS fg_facts (
                    fact_id            TEXT PRIMARY KEY,
                    subject            TEXT NOT NULL,
                    predicate          TEXT NOT NULL,
                    object             TEXT NOT NULL,
                    fact_type          TEXT NOT NULL DEFAULT 'RELATION',
                    subject_type       TEXT,
                    object_type        TEXT,
                    ontology_relation  TEXT,
                    valid_from         TEXT,
                    valid_to           TEXT,
                    status             TEXT NOT NULL DEFAULT 'EXTRACTED',
                    confidence         REAL DEFAULT 0.7,
                    extract_job_id     TEXT,
                    extract_method     TEXT,
                    extract_model      TEXT,
                    extracted_at       TEXT,
                    extract_raw_json   TEXT,
                    superseded_by      TEXT,
                    supersedes         TEXT,
                    created_by         TEXT,
                    created_at         TEXT,
                    confirmed_at       TEXT,
                    rejected_at        TEXT,
                    deleted_at         TEXT,
                    deleted_by         TEXT,
                    delete_reason      TEXT,
                    extra_json         TEXT,
                    origin_key         TEXT
                )
            """)
            try:
                c.execute("ALTER TABLE fg_facts ADD COLUMN origin_key TEXT")
            except sqlite3.OperationalError:
                pass
            c.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_fg_origin_key ON fg_facts(origin_key) WHERE origin_key IS NOT NULL AND origin_key != ''")
            c.execute("""
                CREATE TABLE IF NOT EXISTS fg_fact_sources (
                    source_id     TEXT PRIMARY KEY,
                    fact_id       TEXT NOT NULL,
                    source_type   TEXT,
                    source_ref    TEXT,
                    title         TEXT,
                    page          TEXT,
                    paragraph     TEXT,
                    source_text   TEXT,
                    locator       TEXT,
                    created_at    TEXT
                )
            """)
            c.execute("""
                CREATE TABLE IF NOT EXISTS fg_entity_bindings (
                    binding_id     TEXT PRIMARY KEY,
                    fact_id        TEXT NOT NULL,
                    role           TEXT NOT NULL,
                    mention        TEXT,
                    entity_type    TEXT,
                    graph_node_id  TEXT,
                    created_at     TEXT
                )
            """)
            c.execute("""
                CREATE TABLE IF NOT EXISTS fg_relation_bindings (
                    binding_id      TEXT PRIMARY KEY,
                    fact_id         TEXT NOT NULL,
                    graph_edge_id   TEXT,
                    relation        TEXT,
                    source_node_id  TEXT,
                    target_node_id  TEXT,
                    created_at      TEXT
                )
            """)
            c.execute("""
                CREATE TABLE IF NOT EXISTS fg_derived_objects (
                    derived_id     TEXT PRIMARY KEY,
                    kind           TEXT NOT NULL,
                    object_id      TEXT NOT NULL,
                    title          TEXT,
                    status         TEXT NOT NULL DEFAULT 'ACTIVE',
                    stale_reason   TEXT,
                    extra_json     TEXT,
                    created_at     TEXT,
                    updated_at     TEXT,
                    UNIQUE(kind, object_id)
                )
            """)
            c.execute("""
                CREATE TABLE IF NOT EXISTS fg_dependencies (
                    dep_id      TEXT PRIMARY KEY,
                    fact_id     TEXT NOT NULL,
                    derived_id  TEXT NOT NULL,
                    link_kind   TEXT NOT NULL DEFAULT 'DIRECT',
                    created_at  TEXT,
                    UNIQUE(fact_id, derived_id)
                )
            """)
            c.execute("""
                CREATE TABLE IF NOT EXISTS fg_conflicts (
                    conflict_id  TEXT PRIMARY KEY,
                    fact_a_id    TEXT NOT NULL,
                    fact_b_id    TEXT NOT NULL,
                    reason       TEXT,
                    status       TEXT NOT NULL DEFAULT 'OPEN',
                    created_at   TEXT,
                    UNIQUE(fact_a_id, fact_b_id)
                )
            """)
            c.execute("""
                CREATE TABLE IF NOT EXISTS fg_extract_jobs (
                    job_id        TEXT PRIMARY KEY,
                    source_type   TEXT,
                    source_title  TEXT,
                    source_text   TEXT,
                    status        TEXT,
                    model         TEXT,
                    fact_count    INTEGER DEFAULT 0,
                    extra_json    TEXT,
                    created_at    TEXT
                )
            """)
            c.execute("""
                CREATE TABLE IF NOT EXISTS fg_rebuild_tasks (
                    task_id     TEXT PRIMARY KEY,
                    fact_id     TEXT,
                    derived_id  TEXT,
                    kind        TEXT,
                    title       TEXT,
                    status      TEXT NOT NULL DEFAULT 'PENDING',
                    created_at  TEXT,
                    done_at     TEXT
                )
            """)
            c.execute("CREATE INDEX IF NOT EXISTS idx_fg_facts_status ON fg_facts(status)")
            c.execute("CREATE INDEX IF NOT EXISTS idx_fg_facts_triple ON fg_facts(subject, predicate, object)")
            c.execute("CREATE INDEX IF NOT EXISTS idx_fg_src_fact ON fg_fact_sources(fact_id)")
            c.execute("CREATE INDEX IF NOT EXISTS idx_fg_dep_fact ON fg_dependencies(fact_id)")

    def _row_fact(self, row, conn=None):
        if not row:
            return None
        rec = dict(row)
        rec["extract_raw"] = _loads(rec.pop("extract_raw_json", None), {})
        rec["extra"] = _loads(rec.pop("extra_json", None), {})
        fid = rec["fact_id"]
        if conn is not None:
            rec["sources"] = [dict(r) for r in conn.execute(
                "SELECT * FROM fg_fact_sources WHERE fact_id = ? ORDER BY created_at", (fid,)
            )]
            rec["entity_bindings"] = [dict(r) for r in conn.execute(
                "SELECT * FROM fg_entity_bindings WHERE fact_id = ?", (fid,)
            )]
            rec["relation_bindings"] = [dict(r) for r in conn.execute(
                "SELECT * FROM fg_relation_bindings WHERE fact_id = ?", (fid,)
            )]
            rec["downstream_count"] = conn.execute(
                "SELECT COUNT(*) FROM fg_dependencies WHERE fact_id = ?", (fid,)
            ).fetchone()[0]
            rec["conflict_count"] = conn.execute(
                """SELECT COUNT(*) FROM fg_conflicts
                   WHERE status='OPEN' AND (fact_a_id=? OR fact_b_id=?)""",
                (fid, fid),
            ).fetchone()[0]
        return rec

    def insert_fact(self, rec, sources=None):
        fid = rec.get("fact_id") or _new_id("f")
        now = _now()
        confirmed_at = rec.get("confirmed_at") or (now if rec.get("status") == STATUS_CONFIRMED else "")
        with self._db() as conn:
            conn.execute(
                """INSERT INTO fg_facts (
                    fact_id, subject, predicate, object, fact_type, subject_type, object_type,
                    ontology_relation, valid_from, valid_to, status, confidence,
                    extract_job_id, extract_method, extract_model, extracted_at, extract_raw_json,
                    superseded_by, supersedes, created_by, created_at, confirmed_at, extra_json, origin_key
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    fid, rec.get("subject") or "", rec.get("predicate") or "", rec.get("object") or "",
                    rec.get("fact_type") or "RELATION", rec.get("subject_type") or "",
                    rec.get("object_type") or "", rec.get("ontology_relation") or "",
                    rec.get("valid_from") or "", rec.get("valid_to") or "",
                    rec.get("status") or STATUS_EXTRACTED, float(rec.get("confidence") or 0.7),
                    rec.get("extract_job_id") or "", rec.get("extract_method") or "",
                    rec.get("extract_model") or "", rec.get("extracted_at") or now,
                    _dumps(rec.get("extract_raw") or {}), rec.get("superseded_by") or "",
                    rec.get("supersedes") or "", rec.get("created_by") or "", now, confirmed_at,
                    _dumps(rec.get("extra") or {}), rec.get("origin_key") or "",
                ),
            )
            for src in sources or []:
                conn.execute(
                    """INSERT INTO fg_fact_sources (
                        source_id, fact_id, source_type, source_ref, title, page, paragraph,
                        source_text, locator, created_at
                    ) VALUES (?,?,?,?,?,?,?,?,?,?)""",
                    (
                        src.get("source_id") or _new_id("fs"), fid,
                        src.get("source_type") or "manual", src.get("source_ref") or "",
                        src.get("title") or "", str(src.get("page") or ""),
                        src.get("paragraph") or "", src.get("source_text") or "",
                        src.get("locator") or "", now,
                    ),
                )
        return self.get_fact(fid)

    def origin_keys(self):
        with self._db() as conn:
            rows = conn.execute(
                "SELECT origin_key FROM fg_facts WHERE origin_key IS NOT NULL AND origin_key != ''"
            ).fetchall()
        return {r["origin_key"] for r in rows}

    def get_by_origin_key(self, origin_key):
        if not origin_key:
            return None
        with self._db() as conn:
            row = conn.execute(
                "SELECT * FROM fg_facts WHERE origin_key = ?", (origin_key,)
            ).fetchone()
            return self._row_fact(row, conn) if row else None

    def get_fact(self, fact_id):
        with self._db() as conn:
            row = conn.execute("SELECT * FROM fg_facts WHERE fact_id = ?", (fact_id,)).fetchone()
            return self._row_fact(row, conn)

    def list_facts(self, status=None, q=None, page=1, page_size=80):
        where = ["1=1"]
        params = []
        if status and status != "all":
            if status == "pending":
                where.append("status IN ('EXTRACTED','CONFLICT')")
            elif status == "open":
                where.append("status IN ('EXTRACTED','CONFIRMED','CONFLICT')")
            else:
                where.append("status = ?")
                params.append(status)
        if q:
            where.append("(subject LIKE ? OR object LIKE ? OR predicate LIKE ? OR fact_id LIKE ?)")
            like = f"%{q}%"
            params.extend([like, like, like, like])
        clause = " AND ".join(where)
        with self._db() as conn:
            total = conn.execute(f"SELECT COUNT(*) FROM fg_facts WHERE {clause}", params).fetchone()[0]
            rows = conn.execute(
                f"""SELECT * FROM fg_facts WHERE {clause}
                    ORDER BY created_at DESC LIMIT ? OFFSET ?""",
                [*params, page_size, max(0, (page - 1) * page_size)],
            ).fetchall()
            items = [self._row_fact(r, conn) for r in rows]
        return {"total": total, "items": items, "page": page, "page_size": page_size}

    def overview(self):
        with self._db() as conn:
            def n(sql, params=()):
                return conn.execute(sql, params).fetchone()[0]
            day = today()
            return {
                "total": n("SELECT COUNT(*) FROM fg_facts WHERE status != ?", (STATUS_DELETED,)),
                "pending": n("SELECT COUNT(*) FROM fg_facts WHERE status IN ('EXTRACTED','CONFLICT')"),
                "confirmed": n("SELECT COUNT(*) FROM fg_facts WHERE status = ?", (STATUS_CONFIRMED,)),
                "conflicts": n("SELECT COUNT(*) FROM fg_conflicts WHERE status='OPEN'"),
                "deleted": n("SELECT COUNT(*) FROM fg_facts WHERE status = ?", (STATUS_DELETED,)),
                "recent_new": n("SELECT COUNT(*) FROM fg_facts WHERE created_at LIKE ?", (f"{day}%",)),
                "recent_changed": n(
                    """SELECT COUNT(*) FROM fg_facts
                       WHERE (confirmed_at LIKE ? OR deleted_at LIKE ? OR rejected_at LIKE ?)""",
                    (f"{day}%", f"{day}%", f"{day}%"),
                ),
                "rebuild_pending": n("SELECT COUNT(*) FROM fg_rebuild_tasks WHERE status='PENDING'"),
            }

    def update_fact_status(self, fact_id, status, **fields):
        now = _now()
        sets = ["status=?", "extra_json=COALESCE(extra_json, '{}')"]
        params = [status]
        if status == STATUS_CONFIRMED:
            sets.append("confirmed_at=?")
            params.append(now)
        if status == "REJECTED":
            sets.append("rejected_at=?")
            params.append(now)
        if status == STATUS_DELETED:
            sets.append("deleted_at=?")
            params.append(now)
            if fields.get("deleted_by"):
                sets.append("deleted_by=?")
                params.append(fields["deleted_by"])
            if fields.get("delete_reason") is not None:
                sets.append("delete_reason=?")
                params.append(fields["delete_reason"])
        if fields.get("superseded_by"):
            sets.append("superseded_by=?")
            params.append(fields["superseded_by"])
        if fields.get("ontology_relation"):
            sets.append("ontology_relation=?")
            params.append(fields["ontology_relation"])
        params.append(fact_id)
        with self._db() as conn:
            conn.execute(f"UPDATE fg_facts SET {', '.join(sets)} WHERE fact_id=?", params)
        return self.get_fact(fact_id)

    def list_active_similar(self, predicate, obj, exclude_id=None):
        with self._db() as conn:
            q = """SELECT * FROM fg_facts
                   WHERE predicate=? AND object=? AND status IN ({})""".format(
                ",".join("?" * len(ACTIVE_FACT_STATUSES))
            )
            params = [predicate, obj, *ACTIVE_FACT_STATUSES]
            if exclude_id:
                q += " AND fact_id != ?"
                params.append(exclude_id)
            return [self._row_fact(r, conn) for r in conn.execute(q, params)]

    def list_active_facts(self):
        with self._db() as conn:
            rows = conn.execute(
                f"""SELECT * FROM fg_facts WHERE status IN ({','.join('?' * len(ACTIVE_FACT_STATUSES))})""",
                ACTIVE_FACT_STATUSES,
            ).fetchall()
            return [self._row_fact(r, conn) for r in rows]

    def add_entity_binding(self, fact_id, role, mention, entity_type, graph_node_id):
        bid = _new_id("feb")
        with self._db() as conn:
            conn.execute(
                """INSERT INTO fg_entity_bindings
                   (binding_id, fact_id, role, mention, entity_type, graph_node_id, created_at)
                   VALUES (?,?,?,?,?,?,?)""",
                (bid, fact_id, role, mention or "", entity_type or "", graph_node_id or "", _now()),
            )
        return bid

    def add_relation_binding(self, fact_id, graph_edge_id, relation, source_node_id, target_node_id):
        bid = _new_id("frb")
        with self._db() as conn:
            conn.execute(
                """INSERT INTO fg_relation_bindings
                   (binding_id, fact_id, graph_edge_id, relation, source_node_id, target_node_id, created_at)
                   VALUES (?,?,?,?,?,?,?)""",
                (bid, fact_id, graph_edge_id or "", relation or "", source_node_id or "", target_node_id or "", _now()),
            )
        return bid

    def relation_bindings_for_edge(self, graph_edge_id):
        with self._db() as conn:
            rows = conn.execute(
                """SELECT b.*, f.status AS fact_status FROM fg_relation_bindings b
                   JOIN fg_facts f ON f.fact_id = b.fact_id
                   WHERE b.graph_edge_id = ?""",
                (graph_edge_id,),
            ).fetchall()
            return [dict(r) for r in rows]

    def ensure_derived(self, kind, object_id, title=""):
        did = f"drv_{kind}_{object_id}"[:80]
        now = _now()
        with self._db() as conn:
            existing = conn.execute(
                "SELECT derived_id FROM fg_derived_objects WHERE kind=? AND object_id=?",
                (kind, object_id),
            ).fetchone()
            if existing:
                return existing["derived_id"]
            conn.execute(
                """INSERT INTO fg_derived_objects
                   (derived_id, kind, object_id, title, status, created_at, updated_at, extra_json)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (did, kind, object_id, title or object_id, DERIVED_ACTIVE, now, now, "{}"),
            )
        return did

    def get_derived(self, derived_id):
        with self._db() as conn:
            row = conn.execute(
                "SELECT * FROM fg_derived_objects WHERE derived_id=?", (derived_id,)
            ).fetchone()
            if not row:
                return None
            rec = dict(row)
            rec["extra"] = _loads(rec.pop("extra_json", None), {})
            return rec

    def mark_derived(self, derived_id, status, reason=""):
        with self._db() as conn:
            conn.execute(
                """UPDATE fg_derived_objects SET status=?, stale_reason=?, updated_at=?
                   WHERE derived_id=?""",
                (status, reason or "", _now(), derived_id),
            )

    def add_dependency(self, fact_id, derived_id, link_kind):
        with self._db() as conn:
            existing = conn.execute(
                "SELECT dep_id FROM fg_dependencies WHERE fact_id=? AND derived_id=?",
                (fact_id, derived_id),
            ).fetchone()
            if existing:
                return existing["dep_id"]
            did = _new_id("fd")
            conn.execute(
                """INSERT INTO fg_dependencies (dep_id, fact_id, derived_id, link_kind, created_at)
                   VALUES (?,?,?,?,?)""",
                (did, fact_id, derived_id, link_kind, _now()),
            )
            return did

    def list_dependencies(self, fact_id):
        with self._db() as conn:
            rows = conn.execute(
                """SELECT d.*, o.kind, o.object_id, o.title, o.status AS derived_status
                   FROM fg_dependencies d
                   JOIN fg_derived_objects o ON o.derived_id = d.derived_id
                   WHERE d.fact_id = ?
                   ORDER BY d.link_kind, o.kind""",
                (fact_id,),
            ).fetchall()
            return [dict(r) for r in rows]

    def lineage_tree(self, fact_id):
        deps = self.list_dependencies(fact_id)
        children = []
        for d in deps:
            children.append({
                "derived_id": d["derived_id"],
                "kind": d["kind"],
                "title": d.get("title") or d.get("object_id"),
                "object_id": d.get("object_id"),
                "link_kind": d["link_kind"],
                "status": d.get("derived_status"),
            })
        return {"fact_id": fact_id, "children": children}

    def add_conflict(self, fact_a, fact_b, reason):
        a, b = sorted([fact_a, fact_b])
        cid = _new_id("fc")
        with self._db() as conn:
            existing = conn.execute(
                "SELECT conflict_id FROM fg_conflicts WHERE fact_a_id=? AND fact_b_id=?",
                (a, b),
            ).fetchone()
            if existing:
                return existing["conflict_id"]
            conn.execute(
                """INSERT INTO fg_conflicts (conflict_id, fact_a_id, fact_b_id, reason, status, created_at)
                   VALUES (?,?,?,?,?,?)""",
                (cid, a, b, reason or "", "OPEN", _now()),
            )
        return cid

    def list_conflicts(self, status="OPEN"):
        with self._db() as conn:
            rows = conn.execute(
                "SELECT * FROM fg_conflicts WHERE status=? ORDER BY created_at DESC",
                (status,),
            ).fetchall()
            items = []
            for r in rows:
                rec = dict(r)
                rec["fact_a"] = self._row_fact(
                    conn.execute("SELECT * FROM fg_facts WHERE fact_id=?", (rec["fact_a_id"],)).fetchone(),
                    conn,
                )
                rec["fact_b"] = self._row_fact(
                    conn.execute("SELECT * FROM fg_facts WHERE fact_id=?", (rec["fact_b_id"],)).fetchone(),
                    conn,
                )
                items.append(rec)
            return items

    def resolve_conflicts_for(self, fact_id):
        with self._db() as conn:
            conn.execute(
                """UPDATE fg_conflicts SET status='RESOLVED'
                   WHERE status='OPEN' AND (fact_a_id=? OR fact_b_id=?)""",
                (fact_id, fact_id),
            )

    def insert_job(self, rec):
        jid = rec.get("job_id") or _new_id("fj")
        with self._db() as conn:
            conn.execute(
                """INSERT INTO fg_extract_jobs
                   (job_id, source_type, source_title, source_text, status, model, fact_count, extra_json, created_at)
                   VALUES (?,?,?,?,?,?,?,?,?)""",
                (
                    jid, rec.get("source_type") or "document", rec.get("source_title") or "",
                    rec.get("source_text") or "", rec.get("status") or "done",
                    rec.get("model") or "", int(rec.get("fact_count") or 0),
                    _dumps(rec.get("extra") or {}), _now(),
                ),
            )
        return self.get_job(jid)

    def update_job(self, job_id, **fields):
        sets, params = [], []
        for k in ("status", "model", "fact_count"):
            if k in fields:
                sets.append(f"{k}=?")
                params.append(fields[k])
        if not sets:
            return self.get_job(job_id)
        params.append(job_id)
        with self._db() as conn:
            conn.execute(f"UPDATE fg_extract_jobs SET {', '.join(sets)} WHERE job_id=?", params)
        return self.get_job(job_id)

    def get_job(self, job_id):
        with self._db() as conn:
            row = conn.execute("SELECT * FROM fg_extract_jobs WHERE job_id=?", (job_id,)).fetchone()
            if not row:
                return None
            rec = dict(row)
            rec["extra"] = _loads(rec.pop("extra_json", None), {})
            rec["facts"] = [self._row_fact(r, conn) for r in conn.execute(
                "SELECT * FROM fg_facts WHERE extract_job_id=? ORDER BY created_at", (job_id,)
            )]
            return rec

    def list_jobs(self, limit=40):
        with self._db() as conn:
            rows = conn.execute(
                "SELECT * FROM fg_extract_jobs ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
            out = []
            for r in rows:
                rec = dict(r)
                rec["extra"] = _loads(rec.pop("extra_json", None), {})
                rec.pop("source_text", None)
                out.append(rec)
            return out

    def add_rebuild_task(self, fact_id, derived_id, kind, title):
        tid = _new_id("frt")
        with self._db() as conn:
            conn.execute(
                """INSERT INTO fg_rebuild_tasks
                   (task_id, fact_id, derived_id, kind, title, status, created_at)
                   VALUES (?,?,?,?,?,?,?)""",
                (tid, fact_id, derived_id, kind, title or "", "PENDING", _now()),
            )
        return tid

    def list_rebuild_tasks(self, status="PENDING"):
        with self._db() as conn:
            rows = conn.execute(
                "SELECT * FROM fg_rebuild_tasks WHERE status=? ORDER BY created_at DESC",
                (status,),
            ).fetchall()
            return [dict(r) for r in rows]


_store = None


def get_fact_store():
    global _store
    if _store is None:
        _store = FactStore()
    return _store
