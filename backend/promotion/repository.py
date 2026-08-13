"""晋升推演持久化。"""

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
        data = json.loads(raw)
        return data
    except (json.JSONDecodeError, TypeError):
        return {} if default is None else default


class PromotionStore:
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
                CREATE TABLE IF NOT EXISTS promotion_simulation (
                    id                  TEXT PRIMARY KEY,
                    name                TEXT NOT NULL,
                    target_role_id      TEXT,
                    target_role_name    TEXT,
                    department          TEXT,
                    candidate_scope     TEXT,
                    leadership_style    TEXT,
                    custom_requirements TEXT,
                    layer_weights       TEXT,
                    sub_weights         TEXT,
                    status              TEXT DEFAULT 'draft',
                    progress            INTEGER DEFAULT 0,
                    message             TEXT,
                    error               TEXT,
                    mock_mode           INTEGER DEFAULT 0,
                    creator             TEXT,
                    created_at          TEXT,
                    updated_at          TEXT
                )
            """)
            c.execute("""
                CREATE TABLE IF NOT EXISTS promotion_weight_config (
                    id             INTEGER PRIMARY KEY AUTOINCREMENT,
                    simulation_id  TEXT NOT NULL,
                    dimension      TEXT NOT NULL,
                    weight         REAL NOT NULL,
                    source         TEXT,
                    label          TEXT
                )
            """)
            c.execute("""
                CREATE TABLE IF NOT EXISTS promotion_result (
                    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
                    simulation_id           TEXT NOT NULL,
                    person_id               TEXT NOT NULL,
                    score                   REAL DEFAULT 0,
                    rank                    INTEGER DEFAULT 0,
                    promotion_probability   REAL DEFAULT 0,
                    layer_scores            TEXT,
                    feature_scores          TEXT,
                    analysis_json           TEXT,
                    UNIQUE(simulation_id, person_id)
                )
            """)
            c.execute("CREATE INDEX IF NOT EXISTS idx_promo_sim_created ON promotion_simulation(created_at)")
            c.execute("CREATE INDEX IF NOT EXISTS idx_promo_result_sim ON promotion_result(simulation_id)")

    def create_simulation(self, sim: dict):
        now = _now()
        with self._db() as conn:
            conn.execute(
                """INSERT INTO promotion_simulation
                   (id, name, target_role_id, target_role_name, department, candidate_scope,
                    leadership_style, custom_requirements, layer_weights, sub_weights,
                    status, progress, message, creator, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    sim["id"], sim["name"], sim.get("target_role_id"), sim.get("target_role_name"),
                    sim.get("department") or "",
                    _dumps(sim.get("candidate_scope") or ["all"]),
                    _dumps(sim.get("leadership_style") or {}),
                    _dumps(sim.get("custom_requirements") or []),
                    _dumps(sim.get("layer_weights") or {}),
                    _dumps(sim.get("sub_weights") or {}),
                    sim.get("status") or "running",
                    sim.get("progress") or 0,
                    sim.get("message") or "",
                    sim.get("creator") or "",
                    now, now,
                ),
            )
        self.replace_weight_config(sim["id"], sim.get("weight_rows") or [])
        return self.get_simulation(sim["id"])

    def replace_weight_config(self, simulation_id, rows):
        with self._db() as conn:
            conn.execute("DELETE FROM promotion_weight_config WHERE simulation_id = ?", (simulation_id,))
            for row in rows:
                conn.execute(
                    """INSERT INTO promotion_weight_config
                       (simulation_id, dimension, weight, source, label)
                       VALUES (?, ?, ?, ?, ?)""",
                    (
                        simulation_id,
                        row["dimension"],
                        float(row["weight"]),
                        row.get("source") or "",
                        row.get("label") or "",
                    ),
                )

    def update_simulation(self, simulation_id, **fields):
        if not fields:
            return
        payload = dict(fields)
        payload["updated_at"] = _now()
        for key in ("candidate_scope", "leadership_style", "custom_requirements",
                    "layer_weights", "sub_weights"):
            if key in payload and not isinstance(payload[key], str):
                payload[key] = _dumps(payload[key])
        cols = ", ".join(f"{k} = ?" for k in payload)
        params = list(payload.values()) + [simulation_id]
        with self._db() as conn:
            conn.execute(f"UPDATE promotion_simulation SET {cols} WHERE id = ?", params)

    def get_simulation(self, simulation_id) -> Optional[dict]:
        with self._db() as conn:
            row = conn.execute(
                "SELECT * FROM promotion_simulation WHERE id = ?", (simulation_id,)
            ).fetchone()
        return self._sim_from_row(row) if row else None

    def list_simulations(self, limit=50):
        with self._db() as conn:
            rows = conn.execute(
                "SELECT * FROM promotion_simulation ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [self._sim_from_row(r) for r in rows]

    def delete_simulation(self, simulation_id):
        with self._db() as conn:
            conn.execute("DELETE FROM promotion_result WHERE simulation_id = ?", (simulation_id,))
            conn.execute("DELETE FROM promotion_weight_config WHERE simulation_id = ?", (simulation_id,))
            conn.execute("DELETE FROM promotion_simulation WHERE id = ?", (simulation_id,))

    def list_weights(self, simulation_id):
        with self._db() as conn:
            rows = conn.execute(
                "SELECT * FROM promotion_weight_config WHERE simulation_id = ? ORDER BY id",
                (simulation_id,),
            ).fetchall()
        return [dict(r) for r in rows]

    def replace_results(self, simulation_id, results):
        with self._db() as conn:
            conn.execute("DELETE FROM promotion_result WHERE simulation_id = ?", (simulation_id,))
            for r in results:
                conn.execute(
                    """INSERT INTO promotion_result
                       (simulation_id, person_id, score, rank, promotion_probability,
                        layer_scores, feature_scores, analysis_json)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        simulation_id,
                        r["person_id"],
                        float(r.get("score") or 0),
                        int(r.get("rank") or 0),
                        float(r.get("promotion_probability") or 0),
                        _dumps(r.get("layer_scores") or {}),
                        _dumps(r.get("feature_scores") or {}),
                        _dumps(r.get("analysis_json") or {}),
                    ),
                )

    def list_results(self, simulation_id):
        with self._db() as conn:
            rows = conn.execute(
                """SELECT * FROM promotion_result
                   WHERE simulation_id = ? ORDER BY rank ASC, score DESC""",
                (simulation_id,),
            ).fetchall()
        out = []
        for r in rows:
            item = dict(r)
            item["layer_scores"] = _loads(item.get("layer_scores"), default={})
            item["feature_scores"] = _loads(item.get("feature_scores"), default={})
            item["analysis_json"] = _loads(item.get("analysis_json"), default={})
            out.append(item)
        return out

    def _sim_from_row(self, row):
        item = dict(row)
        item["candidate_scope"] = _loads(item.get("candidate_scope"), default=["all"])
        item["leadership_style"] = _loads(item.get("leadership_style"), default={})
        item["custom_requirements"] = _loads(item.get("custom_requirements"), default=[])
        item["layer_weights"] = _loads(item.get("layer_weights"), default={})
        item["sub_weights"] = _loads(item.get("sub_weights"), default={})
        item["mock_mode"] = bool(item.get("mock_mode"))
        return item


_store = None


def get_promo_store() -> PromotionStore:
    global _store
    if _store is None:
        _store = PromotionStore()
    return _store
