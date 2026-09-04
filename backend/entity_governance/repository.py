"""实体治理仓储：Canonical / Alias / Candidate / MergeHistory / Evidence。"""

import json
import sqlite3
import uuid
from contextlib import contextmanager

from database import DB_PATH
from timeutil import now_iso

from .types import (
    LIFECYCLE_CANONICAL,
    STATUS_ACTIVE,
    STATUS_MERGED,
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


class GovernanceStore:
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
                CREATE TABLE IF NOT EXISTS eg_entities (
                    entity_id            TEXT PRIMARY KEY,
                    entity_type          TEXT NOT NULL,
                    canonical_name       TEXT NOT NULL,
                    status               TEXT NOT NULL DEFAULT 'ACTIVE',
                    lifecycle            TEXT NOT NULL DEFAULT 'CANONICAL',
                    source_count         INTEGER DEFAULT 1,
                    confidence           REAL DEFAULT 1.0,
                    canonical_source     TEXT,
                    canonical_entity_id  TEXT,
                    merge_batch_id       TEXT,
                    merged_at            TEXT,
                    created_at           TEXT,
                    updated_at           TEXT,
                    metadata             TEXT
                )
            """)
            c.execute("""
                CREATE TABLE IF NOT EXISTS eg_aliases (
                    alias_id          TEXT PRIMARY KEY,
                    entity_id         TEXT NOT NULL,
                    entity_type       TEXT NOT NULL,
                    value             TEXT NOT NULL,
                    normalized_value  TEXT NOT NULL,
                    source            TEXT,
                    created_at        TEXT,
                    UNIQUE(entity_type, normalized_value)
                )
            """)
            c.execute("""
                CREATE TABLE IF NOT EXISTS eg_candidates (
                    candidate_id   TEXT PRIMARY KEY,
                    entity_a_id    TEXT NOT NULL,
                    entity_b_id    TEXT NOT NULL,
                    entity_type    TEXT NOT NULL,
                    score          REAL NOT NULL,
                    decision       TEXT NOT NULL,
                    status         TEXT NOT NULL DEFAULT 'pending',
                    field_scores   TEXT,
                    graph_evidence TEXT,
                    semantic_evidence TEXT,
                    conflicts      TEXT,
                    match_layers   TEXT,
                    operator       TEXT,
                    reason         TEXT,
                    merge_id       TEXT,
                    created_at     TEXT,
                    updated_at     TEXT,
                    UNIQUE(entity_a_id, entity_b_id)
                )
            """)
            c.execute("""
                CREATE TABLE IF NOT EXISTS eg_merge_history (
                    merge_id            TEXT PRIMARY KEY,
                    source_entity_id    TEXT NOT NULL,
                    target_entity_id    TEXT NOT NULL,
                    operator            TEXT,
                    reason              TEXT,
                    score               REAL,
                    evidence            TEXT,
                    candidate_id        TEXT,
                    snapshot            TEXT,
                    influence_before    TEXT,
                    influence_after     TEXT,
                    influence_delta     TEXT,
                    unmerged            INTEGER DEFAULT 0,
                    unmerged_at         TEXT,
                    unmerged_by         TEXT,
                    created_at          TEXT
                )
            """)
            c.execute("""
                CREATE TABLE IF NOT EXISTS eg_evidence (
                    evidence_id   TEXT PRIMARY KEY,
                    entity_id     TEXT NOT NULL,
                    relation_id   TEXT,
                    source_type   TEXT,
                    source_id     TEXT,
                    snippet       TEXT,
                    created_at    TEXT
                )
            """)
            c.execute("""
                CREATE TABLE IF NOT EXISTS eg_meta (
                    key   TEXT PRIMARY KEY,
                    value TEXT
                )
            """)
            c.execute("CREATE INDEX IF NOT EXISTS idx_eg_ent_type ON eg_entities(entity_type)")
            c.execute("CREATE INDEX IF NOT EXISTS idx_eg_ent_status ON eg_entities(status)")
            c.execute("CREATE INDEX IF NOT EXISTS idx_eg_alias_norm ON eg_aliases(normalized_value)")
            c.execute("CREATE INDEX IF NOT EXISTS idx_eg_cand_status ON eg_candidates(status)")
            c.execute("CREATE INDEX IF NOT EXISTS idx_eg_ev_entity ON eg_evidence(entity_id)")

    def set_meta(self, key, value):
        with self._db() as conn:
            conn.execute(
                """INSERT INTO eg_meta (key, value) VALUES (?, ?)
                   ON CONFLICT(key) DO UPDATE SET value = excluded.value""",
                (key, value if isinstance(value, str) else _dumps(value)),
            )

    def get_meta(self, key, default=None):
        with self._db() as conn:
            row = conn.execute("SELECT value FROM eg_meta WHERE key = ?", (key,)).fetchone()
            return row["value"] if row else default

    # ----- entities -----

    def upsert_entity(self, entity: dict):
        eid = entity["entity_id"]
        now = _now()
        existing = self.get_entity(eid)
        created = existing.get("created_at") if existing else entity.get("created_at") or now
        row = {
            "entity_id": eid,
            "entity_type": entity.get("entity_type") or (existing or {}).get("entity_type"),
            "canonical_name": entity.get("canonical_name") or (existing or {}).get("canonical_name") or eid,
            "status": entity.get("status") or (existing or {}).get("status") or STATUS_ACTIVE,
            "lifecycle": entity.get("lifecycle") or (existing or {}).get("lifecycle") or LIFECYCLE_CANONICAL,
            "source_count": int(entity.get("source_count") if entity.get("source_count") is not None else ((existing or {}).get("source_count") or 1)),
            "confidence": float(entity.get("confidence") if entity.get("confidence") is not None else ((existing or {}).get("confidence") or 1.0)),
            "canonical_source": entity.get("canonical_source") if "canonical_source" in entity else (existing or {}).get("canonical_source"),
            "canonical_entity_id": entity.get("canonical_entity_id") if "canonical_entity_id" in entity else (existing or {}).get("canonical_entity_id"),
            "merge_batch_id": entity.get("merge_batch_id") if "merge_batch_id" in entity else (existing or {}).get("merge_batch_id"),
            "merged_at": entity.get("merged_at") if "merged_at" in entity else (existing or {}).get("merged_at"),
            "created_at": created,
            "updated_at": now,
            "metadata": _dumps(entity.get("metadata") if "metadata" in entity else ((existing or {}).get("metadata") or {})),
        }
        with self._db() as conn:
            conn.execute(
                """INSERT INTO eg_entities (
                     entity_id, entity_type, canonical_name, status, lifecycle,
                     source_count, confidence, canonical_source, canonical_entity_id,
                     merge_batch_id, merged_at, created_at, updated_at, metadata
                   ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(entity_id) DO UPDATE SET
                     entity_type=excluded.entity_type,
                     canonical_name=excluded.canonical_name,
                     status=excluded.status,
                     lifecycle=excluded.lifecycle,
                     source_count=excluded.source_count,
                     confidence=excluded.confidence,
                     canonical_source=excluded.canonical_source,
                     canonical_entity_id=excluded.canonical_entity_id,
                     merge_batch_id=excluded.merge_batch_id,
                     merged_at=excluded.merged_at,
                     updated_at=excluded.updated_at,
                     metadata=excluded.metadata
                """,
                (
                    row["entity_id"], row["entity_type"], row["canonical_name"], row["status"],
                    row["lifecycle"], row["source_count"], row["confidence"], row["canonical_source"],
                    row["canonical_entity_id"], row["merge_batch_id"], row["merged_at"],
                    row["created_at"], row["updated_at"], row["metadata"],
                ),
            )
        return self.get_entity(eid)

    def get_entity(self, entity_id: str):
        if not entity_id:
            return None
        with self._db() as conn:
            row = conn.execute("SELECT * FROM eg_entities WHERE entity_id = ?", (entity_id,)).fetchone()
        return self._row_entity(row) if row else None

    def list_entities(self, entity_type=None, status=None, include_merged=True):
        query = "SELECT * FROM eg_entities WHERE 1=1"
        params = []
        if entity_type:
            query += " AND entity_type = ?"
            params.append(entity_type)
        if status:
            query += " AND status = ?"
            params.append(status)
        elif not include_merged:
            query += " AND status = ?"
            params.append(STATUS_ACTIVE)
        query += " ORDER BY entity_type, canonical_name"
        with self._db() as conn:
            rows = conn.execute(query, params).fetchall()
        return [self._row_entity(r) for r in rows]

    def count_entities(self, status=None):
        query = "SELECT count(*) AS c FROM eg_entities WHERE 1=1"
        params = []
        if status:
            query += " AND status = ?"
            params.append(status)
        with self._db() as conn:
            row = conn.execute(query, params).fetchone()
        return int(row["c"] if row else 0)

    # ----- aliases -----

    def add_alias(self, entity_id, entity_type, value, source="merge", normalized_value=None):
        from .normalizer import normalize_text
        value = (value or "").strip()
        if not value:
            return None
        norm = normalized_value or normalize_text(value)
        if not norm:
            return None
        existing = self.find_alias(entity_type, norm)
        if existing:
            return existing
        alias_id = f"alias_{uuid.uuid4().hex[:12]}"
        with self._db() as conn:
            try:
                conn.execute(
                    """INSERT INTO eg_aliases
                       (alias_id, entity_id, entity_type, value, normalized_value, source, created_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (alias_id, entity_id, entity_type, value, norm, source, _now()),
                )
            except sqlite3.IntegrityError:
                return self.find_alias(entity_type, norm)
        return self.get_alias(alias_id)

    def get_alias(self, alias_id):
        with self._db() as conn:
            row = conn.execute("SELECT * FROM eg_aliases WHERE alias_id = ?", (alias_id,)).fetchone()
        return dict(row) if row else None

    def find_alias(self, entity_type, normalized_value):
        with self._db() as conn:
            row = conn.execute(
                """SELECT * FROM eg_aliases
                   WHERE entity_type = ? AND normalized_value = ?""",
                (entity_type, normalized_value),
            ).fetchone()
        return dict(row) if row else None

    def list_aliases(self, entity_id=None, entity_type=None):
        query = "SELECT * FROM eg_aliases WHERE 1=1"
        params = []
        if entity_id:
            query += " AND entity_id = ?"
            params.append(entity_id)
        if entity_type:
            query += " AND entity_type = ?"
            params.append(entity_type)
        query += " ORDER BY created_at"
        with self._db() as conn:
            rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]

    def delete_aliases(self, alias_ids):
        if not alias_ids:
            return
        with self._db() as conn:
            conn.executemany("DELETE FROM eg_aliases WHERE alias_id = ?", [(x,) for x in alias_ids])

    def count_aliases(self):
        with self._db() as conn:
            row = conn.execute("SELECT count(*) AS c FROM eg_aliases").fetchone()
        return int(row["c"] if row else 0)

    def reassign_aliases(self, from_entity_id, to_entity_id):
        with self._db() as conn:
            conn.execute(
                "UPDATE eg_aliases SET entity_id = ? WHERE entity_id = ?",
                (to_entity_id, from_entity_id),
            )

    # ----- candidates -----

    def upsert_candidate(self, rec: dict):
        a, b = sorted([rec["entity_a_id"], rec["entity_b_id"]])
        existing = self.get_candidate_pair(a, b)
        cid = rec.get("candidate_id") or (existing or {}).get("candidate_id") or f"cand_{uuid.uuid4().hex[:12]}"
        now = _now()
        created = (existing or {}).get("created_at") or now
        payload = (
            cid, a, b, rec["entity_type"], float(rec.get("score") or 0),
            rec.get("decision") or "REVIEW", rec.get("status") or "pending",
            _dumps(rec.get("field_scores") or {}),
            _dumps(rec.get("graph_evidence") or []),
            _dumps(rec.get("semantic_evidence") or []),
            _dumps(rec.get("conflicts") or []),
            _dumps(rec.get("match_layers") or {}),
            rec.get("operator"), rec.get("reason"), rec.get("merge_id"),
            created, now,
        )
        with self._db() as conn:
            conn.execute(
                """INSERT INTO eg_candidates (
                     candidate_id, entity_a_id, entity_b_id, entity_type, score,
                     decision, status, field_scores, graph_evidence, semantic_evidence,
                     conflicts, match_layers, operator, reason, merge_id, created_at, updated_at
                   ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(entity_a_id, entity_b_id) DO UPDATE SET
                     score=excluded.score,
                     decision=excluded.decision,
                     status=excluded.status,
                     field_scores=excluded.field_scores,
                     graph_evidence=excluded.graph_evidence,
                     semantic_evidence=excluded.semantic_evidence,
                     conflicts=excluded.conflicts,
                     match_layers=excluded.match_layers,
                     operator=COALESCE(excluded.operator, eg_candidates.operator),
                     reason=COALESCE(excluded.reason, eg_candidates.reason),
                     merge_id=COALESCE(excluded.merge_id, eg_candidates.merge_id),
                     updated_at=excluded.updated_at
                """,
                payload,
            )
        return self.get_candidate(cid) or self.get_candidate_pair(a, b)

    def get_candidate(self, candidate_id):
        with self._db() as conn:
            row = conn.execute("SELECT * FROM eg_candidates WHERE candidate_id = ?", (candidate_id,)).fetchone()
        return self._row_candidate(row) if row else None

    def get_candidate_pair(self, a, b):
        a, b = sorted([a, b])
        with self._db() as conn:
            row = conn.execute(
                "SELECT * FROM eg_candidates WHERE entity_a_id = ? AND entity_b_id = ?",
                (a, b),
            ).fetchone()
        return self._row_candidate(row) if row else None

    def list_candidates(self, status=None, entity_type=None, min_score=None, page=1, page_size=50):
        query = "SELECT * FROM eg_candidates WHERE 1=1"
        params = []
        if status and status != "all":
            if status == "pending_review":
                query += " AND status = 'pending' AND decision IN ('REVIEW', 'FORCE_REVIEW')"
            elif status == "conflict":
                query += " AND decision = 'FORCE_REVIEW'"
            elif status == "auto":
                query += " AND (status = 'auto_merged' OR decision = 'AUTO_MATCH')"
            elif status == "done":
                query += " AND status IN ('merged', 'auto_merged', 'rejected')"
            else:
                query += " AND status = ?"
                params.append(status)
        if entity_type:
            query += " AND entity_type = ?"
            params.append(entity_type)
        if min_score is not None:
            query += " AND score >= ?"
            params.append(float(min_score))
        query += " ORDER BY CASE decision WHEN 'FORCE_REVIEW' THEN 0 WHEN 'AUTO_MATCH' THEN 1 ELSE 2 END, score DESC, updated_at DESC"
        count_q = "SELECT count(*) AS c FROM (" + query + ") t"
        with self._db() as conn:
            total = conn.execute(count_q, params).fetchone()["c"]
            page = max(1, int(page or 1))
            page_size = max(1, min(200, int(page_size or 50)))
            query += " LIMIT ? OFFSET ?"
            rows = conn.execute(query, params + [page_size, (page - 1) * page_size]).fetchall()
        return {
            "items": [self._row_candidate(r) for r in rows],
            "total": int(total),
            "page": page,
            "page_size": page_size,
        }

    def update_candidate(self, candidate_id, **fields):
        if not fields:
            return self.get_candidate(candidate_id)
        allowed = {"status", "decision", "operator", "reason", "merge_id"}
        sets = []
        params = []
        for k, v in fields.items():
            if k in allowed:
                sets.append(f"{k} = ?")
                params.append(v)
        if not sets:
            return self.get_candidate(candidate_id)
        sets.append("updated_at = ?")
        params.append(_now())
        params.append(candidate_id)
        with self._db() as conn:
            conn.execute(f"UPDATE eg_candidates SET {', '.join(sets)} WHERE candidate_id = ?", params)
        return self.get_candidate(candidate_id)

    def candidate_counts(self):
        with self._db() as conn:
            rows = conn.execute(
                "SELECT status, decision, count(*) AS c FROM eg_candidates GROUP BY status, decision"
            ).fetchall()
        return [dict(r) for r in rows]

    def clear_pending_candidates(self, entity_types=None):
        with self._db() as conn:
            if entity_types:
                placeholders = ",".join("?" * len(entity_types))
                conn.execute(
                    f"DELETE FROM eg_candidates WHERE status = 'pending' AND entity_type IN ({placeholders})",
                    list(entity_types),
                )
            else:
                conn.execute("DELETE FROM eg_candidates WHERE status = 'pending'")

    # ----- merge history -----

    def insert_merge(self, rec: dict):
        merge_id = rec.get("merge_id") or f"merge_{uuid.uuid4().hex[:12]}"
        with self._db() as conn:
            conn.execute(
                """INSERT INTO eg_merge_history (
                     merge_id, source_entity_id, target_entity_id, operator, reason,
                     score, evidence, candidate_id, snapshot, influence_before,
                     influence_after, influence_delta, unmerged, created_at
                   ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,0,?)""",
                (
                    merge_id, rec["source_entity_id"], rec["target_entity_id"],
                    rec.get("operator") or "system", rec.get("reason") or "",
                    rec.get("score"), _dumps(rec.get("evidence") or []),
                    rec.get("candidate_id"), _dumps(rec.get("snapshot") or {}),
                    _dumps(rec.get("influence_before") or {}),
                    _dumps(rec.get("influence_after") or {}),
                    _dumps(rec.get("influence_delta") or {}),
                    _now(),
                ),
            )
        return self.get_merge(merge_id)

    def get_merge(self, merge_id):
        with self._db() as conn:
            row = conn.execute("SELECT * FROM eg_merge_history WHERE merge_id = ?", (merge_id,)).fetchone()
        return self._row_merge(row) if row else None

    def list_merges(self, include_unmerged=True, limit=100):
        query = "SELECT * FROM eg_merge_history WHERE 1=1"
        if not include_unmerged:
            query += " AND unmerged = 0"
        query += " ORDER BY created_at DESC LIMIT ?"
        with self._db() as conn:
            rows = conn.execute(query, (limit,)).fetchall()
        return [self._row_merge(r) for r in rows]

    def mark_unmerged(self, merge_id, operator="user"):
        with self._db() as conn:
            conn.execute(
                """UPDATE eg_merge_history
                   SET unmerged = 1, unmerged_at = ?, unmerged_by = ?
                   WHERE merge_id = ?""",
                (_now(), operator, merge_id),
            )
        return self.get_merge(merge_id)

    def latest_merge_for_source(self, source_entity_id):
        with self._db() as conn:
            row = conn.execute(
                """SELECT * FROM eg_merge_history
                   WHERE source_entity_id = ? AND unmerged = 0
                   ORDER BY created_at DESC LIMIT 1""",
                (source_entity_id,),
            ).fetchone()
        return self._row_merge(row) if row else None

    def auto_merge_stats(self):
        with self._db() as conn:
            auto = conn.execute(
                "SELECT count(*) AS c FROM eg_merge_history WHERE operator = 'system' AND unmerged = 0"
            ).fetchone()["c"]
            false_m = conn.execute(
                "SELECT count(*) AS c FROM eg_merge_history WHERE operator = 'system' AND unmerged = 1"
            ).fetchone()["c"]
        return int(auto), int(false_m)

    # ----- evidence -----

    def add_evidence(self, entity_id, source_type, source_id=None, snippet=None, relation_id=None):
        eid = f"ev_{uuid.uuid4().hex[:12]}"
        with self._db() as conn:
            conn.execute(
                """INSERT INTO eg_evidence
                   (evidence_id, entity_id, relation_id, source_type, source_id, snippet, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (eid, entity_id, relation_id, source_type, source_id, snippet, _now()),
            )
        return eid

    def list_evidence(self, entity_id):
        with self._db() as conn:
            rows = conn.execute(
                "SELECT * FROM eg_evidence WHERE entity_id = ? ORDER BY created_at DESC",
                (entity_id,),
            ).fetchall()
        return [dict(r) for r in rows]

    def reassign_evidence(self, from_entity_id, to_entity_id):
        with self._db() as conn:
            conn.execute(
                "UPDATE eg_evidence SET entity_id = ? WHERE entity_id = ?",
                (to_entity_id, from_entity_id),
            )

    @staticmethod
    def _row_entity(row):
        item = dict(row)
        item["metadata"] = _loads(item.get("metadata"), default={})
        return item

    @staticmethod
    def _row_candidate(row):
        item = dict(row)
        item["field_scores"] = _loads(item.get("field_scores"), default={})
        item["graph_evidence"] = _loads(item.get("graph_evidence"), default=[])
        item["semantic_evidence"] = _loads(item.get("semantic_evidence"), default=[])
        item["conflicts"] = _loads(item.get("conflicts"), default=[])
        item["match_layers"] = _loads(item.get("match_layers"), default={})
        return item

    @staticmethod
    def _row_merge(row):
        item = dict(row)
        item["evidence"] = _loads(item.get("evidence"), default=[])
        item["snapshot"] = _loads(item.get("snapshot"), default={})
        item["influence_before"] = _loads(item.get("influence_before"), default={})
        item["influence_after"] = _loads(item.get("influence_after"), default={})
        item["influence_delta"] = _loads(item.get("influence_delta"), default={})
        return item


_store = None


def get_gov_store() -> GovernanceStore:
    global _store
    if _store is None:
        _store = GovernanceStore()
    return _store
