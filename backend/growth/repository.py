"""P0 事件 / 证据 / 阶段培养 / 项目成长 数据访问。"""

import json
import uuid
from timeutil import now_iso

from database import get_db, _ensure_column


EVENT_COLUMNS = [
    ("event_type", "TEXT"),
    ("event_tag", "TEXT"),
    ("related_project_id", "TEXT"),
    ("related_stage_id", "TEXT"),
    ("related_role_id", "TEXT"),
    ("related_newcomer_id", "TEXT"),
    ("created_by", "TEXT"),
    ("source", "TEXT DEFAULT 'manual'"),
    ("subjects_json", "TEXT"),
    ("related_persons_json", "TEXT"),
    ("background", "TEXT"),
    ("facts", "TEXT"),
    ("expected", "TEXT"),
    ("difference", "TEXT"),
    ("actions", "TEXT"),
    ("result", "TEXT"),
    ("evidence", "TEXT"),
    ("judgement", "TEXT"),
    ("extra_fields_json", "TEXT"),
    ("updated_at", "TEXT"),
]


def _now():
    return now_iso()


def _dumps(obj):
    return json.dumps(obj, ensure_ascii=False)


def _loads(raw, default=None):
    if raw is None or raw == "":
        return [] if default is None else default
    if isinstance(raw, (list, dict)):
        return raw
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return [] if default is None else default


def init_tables():
    with get_db() as conn:
        c = conn.cursor()
        for name, ddl in EVENT_COLUMNS:
            _ensure_column(c, "team_events", name, ddl)
        _ensure_column(c, "capability_evidence", "event_id", "INTEGER")
        _ensure_column(c, "capability_evidence", "dimension", "TEXT")
        _ensure_column(c, "capability_evidence", "polarity", "TEXT")
        _ensure_column(c, "capability_evidence", "reason", "TEXT")
        _ensure_column(c, "relationship_logs", "dimension", "TEXT")
        _ensure_column(c, "relationship_logs", "reason", "TEXT")
        _ensure_column(c, "relationship_logs", "polarity", "TEXT")

        c.execute("""
            CREATE TABLE IF NOT EXISTS relationship_evidence (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id        INTEGER NOT NULL REFERENCES team_events(id) ON DELETE CASCADE,
                from_member_id  TEXT NOT NULL,
                to_member_id    TEXT NOT NULL,
                dimension       TEXT NOT NULL,
                delta           INTEGER NOT NULL DEFAULT 0,
                polarity        TEXT NOT NULL,
                reason          TEXT,
                facts           TEXT,
                result          TEXT,
                impact          TEXT,
                created_at      TEXT DEFAULT (datetime('now','+8 hours'))
            )
        """)
        c.execute("CREATE INDEX IF NOT EXISTS idx_rel_ev_pair ON relationship_evidence(from_member_id, to_member_id)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_rel_ev_event ON relationship_evidence(event_id)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_rel_ev_dim ON relationship_evidence(dimension)")

        c.execute("""
            CREATE TABLE IF NOT EXISTS newcomer_stage_records (
                id                       TEXT PRIMARY KEY,
                newcomer_id              TEXT NOT NULL,
                stage_id                 TEXT NOT NULL,
                stage_goal               TEXT,
                role_requirements        TEXT,
                stage_tasks_json         TEXT,
                human_ai_json            TEXT,
                self_eval                TEXT,
                mentor_eval              TEXT,
                result                   TEXT,
                capability_changes_json  TEXT,
                passed                   INTEGER DEFAULT 0,
                updated_at               TEXT,
                UNIQUE(newcomer_id, stage_id)
            )
        """)

        c.execute("""
            CREATE TABLE IF NOT EXISTS project_growth_evidence (
                id                      TEXT PRIMARY KEY,
                project_id              TEXT NOT NULL,
                person_id               TEXT NOT NULL,
                project_role            TEXT,
                responsibility          TEXT,
                key_decisions           TEXT,
                risk_handling           TEXT,
                resource_coordination   TEXT,
                collaboration           TEXT,
                newcomer_training       TEXT,
                outcome                 TEXT,
                retrospective           TEXT,
                event_id                INTEGER,
                updated_at              TEXT,
                UNIQUE(project_id, person_id)
            )
        """)
        c.execute("CREATE INDEX IF NOT EXISTS idx_pge_project ON project_growth_evidence(project_id)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_pge_person ON project_growth_evidence(person_id)")


def insert_structured_event(payload):
    now = _now()
    involved = payload.get("involved_members") or []
    subjects = payload.get("subjects") or []
    related_persons = payload.get("related_persons") or []
    extra = payload.get("extra_fields") or {}
    with get_db() as conn:
        c = conn.cursor()
        c.execute(
            """INSERT INTO team_events
               (event_time, involved_members, raw_summary, scene, parsed_task, confidence,
                is_hypothetical, event_type, event_tag, related_project_id, related_stage_id,
                related_role_id, related_newcomer_id, created_by, source, subjects_json,
                related_persons_json, background, facts, expected, difference, actions,
                result, evidence, judgement, extra_fields_json, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                payload.get("event_time") or now,
                _dumps(involved),
                payload.get("raw_summary") or "",
                payload.get("scene"),
                payload.get("parsed_task"),
                float(payload.get("confidence") or 0.8),
                int(payload.get("is_hypothetical") or 0),
                payload.get("event_type") or "",
                payload.get("event_tag") or "",
                payload.get("related_project_id") or "",
                payload.get("related_stage_id") or "",
                payload.get("related_role_id") or "",
                payload.get("related_newcomer_id") or "",
                payload.get("created_by") or "",
                payload.get("source") or "manual",
                _dumps(subjects),
                _dumps(related_persons),
                payload.get("background") or "",
                payload.get("facts") or "",
                payload.get("expected") or "",
                payload.get("difference") or "",
                payload.get("actions") or "",
                payload.get("result") or "",
                payload.get("evidence") or "",
                payload.get("judgement") or "",
                _dumps(extra),
                now,
                now,
            ),
        )
        return c.lastrowid


def update_event_structured(event_id, **fields):
    allowed = {
        "parsed_task", "scene", "confidence", "event_type", "event_tag",
        "related_project_id", "related_stage_id", "related_role_id",
        "related_newcomer_id", "created_by", "source", "background", "facts",
        "expected", "difference", "actions", "result", "evidence", "judgement",
        "raw_summary",
    }
    sets = []
    params = []
    for k, v in fields.items():
        if k not in allowed:
            continue
        sets.append(f"{k} = ?")
        params.append(v)
    if "subjects" in fields:
        sets.append("subjects_json = ?")
        params.append(_dumps(fields["subjects"] or []))
    if "related_persons" in fields:
        sets.append("related_persons_json = ?")
        params.append(_dumps(fields["related_persons"] or []))
    if "extra_fields" in fields:
        sets.append("extra_fields_json = ?")
        params.append(_dumps(fields["extra_fields"] or {}))
    if not sets:
        return
    sets.append("updated_at = ?")
    params.append(_now())
    params.append(event_id)
    with get_db() as conn:
        conn.execute(f"UPDATE team_events SET {', '.join(sets)} WHERE id = ?", params)


def hydrate_event(row):
    if not row:
        return None
    item = dict(row)
    item["involved_members"] = _loads(item.get("involved_members"), default=[])
    item["subjects"] = _loads(item.get("subjects_json"), default=[])
    item["related_persons"] = _loads(item.get("related_persons_json"), default=[])
    item["extra_fields"] = _loads(item.get("extra_fields_json"), default={})
    item["event_id"] = f"evt_{item['id']}"
    return item


def get_event(event_id):
    with get_db() as conn:
        row = conn.execute("SELECT * FROM team_events WHERE id = ?", (event_id,)).fetchone()
        return hydrate_event(row)


def list_events(filters=None):
    filters = filters or {}
    query = "SELECT * FROM team_events WHERE 1=1"
    params = []
    if filters.get("event_type"):
        query += " AND event_type = ?"
        params.append(filters["event_type"])
    if filters.get("event_tag"):
        query += " AND event_tag = ?"
        params.append(filters["event_tag"])
    if filters.get("member_id"):
        query += " AND (involved_members LIKE ? OR created_by = ? OR related_persons_json LIKE ?)"
        mid = filters["member_id"]
        params.extend([f'%"{mid}"%', mid, f'%"{mid}"%'])
    if filters.get("project_id"):
        query += " AND related_project_id = ?"
        params.append(filters["project_id"])
    if filters.get("newcomer_id"):
        query += " AND related_newcomer_id = ?"
        params.append(filters["newcomer_id"])
    if filters.get("date_from"):
        bound = filters["date_from"]
        if len(bound) == 10:
            bound = f"{bound}T00:00:00"
        query += " AND replace(event_time, ' ', 'T') >= replace(?, ' ', 'T')"
        params.append(bound)
    if filters.get("date_to"):
        bound = filters["date_to"]
        if len(bound) == 10:
            bound = f"{bound}T23:59:59"
        query += " AND replace(event_time, ' ', 'T') <= replace(?, ' ', 'T')"
        params.append(bound)
    query += " ORDER BY event_time DESC"
    limit = int(filters.get("limit") or 200)
    query += " LIMIT ?"
    params.append(limit)
    with get_db() as conn:
        return [hydrate_event(r) for r in conn.execute(query, params).fetchall()]


def insert_relationship_evidence(event_id, from_id, to_id, dimension, delta, reason,
                                 facts="", result="", impact=""):
    polarity = "positive" if int(delta) >= 0 else "negative"
    with get_db() as conn:
        c = conn.cursor()
        c.execute(
            """INSERT INTO relationship_evidence
               (event_id, from_member_id, to_member_id, dimension, delta, polarity,
                reason, facts, result, impact, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (event_id, from_id, to_id, dimension, int(delta), polarity,
             reason, facts, result, impact, _now()),
        )
        return c.lastrowid


def delete_relationship_evidence_by_event(event_id):
    with get_db() as conn:
        conn.execute("DELETE FROM relationship_evidence WHERE event_id = ?", (event_id,))


def list_relationship_evidence(from_id=None, to_id=None, dimension=None, event_id=None):
    query = """
        SELECT re.*, te.event_time, te.event_type, te.event_tag, te.raw_summary,
               te.background, te.facts AS event_facts, te.result AS event_result,
               te.judgement, te.scene
        FROM relationship_evidence re
        JOIN team_events te ON re.event_id = te.id
        WHERE 1=1
    """
    params = []
    if from_id:
        query += " AND re.from_member_id = ?"
        params.append(from_id)
    if to_id:
        query += " AND re.to_member_id = ?"
        params.append(to_id)
    if dimension:
        query += " AND re.dimension = ?"
        params.append(dimension)
    if event_id:
        query += " AND re.event_id = ?"
        params.append(event_id)
    query += " ORDER BY te.event_time ASC, re.id ASC"
    with get_db() as conn:
        rows = []
        for r in conn.execute(query, params).fetchall():
            item = dict(r)
            item["polarity"] = item.get("polarity") or ("positive" if (item.get("delta") or 0) >= 0 else "negative")
            rows.append(item)
        return rows


def insert_capability_from_event(employee_id, capability_id, capability_name, content,
                                 score, event_id=None, reason="", polarity="positive",
                                 dimension=""):
    with get_db() as conn:
        conn.execute(
            """INSERT INTO capability_evidence
               (employee_id, task_id, capability_id, capability_name, evidence_type,
                evidence_content, score, event_id, dimension, polarity, reason, created_at)
               VALUES (?, NULL, ?, ?, 'event', ?, ?, ?, ?, ?, ?, ?)""",
            (employee_id, capability_id, capability_name, content, score,
             event_id, dimension or capability_id, polarity, reason, _now()),
        )


def list_capability_evidence(employee_id=None, capability_id=None, event_id=None):
    query = "SELECT * FROM capability_evidence WHERE 1=1"
    params = []
    if employee_id:
        query += " AND employee_id = ?"
        params.append(employee_id)
    if capability_id:
        query += " AND capability_id = ?"
        params.append(capability_id)
    if event_id:
        query += " AND event_id = ?"
        params.append(event_id)
    query += " ORDER BY created_at DESC"
    with get_db() as conn:
        return [dict(r) for r in conn.execute(query, params).fetchall()]


def delete_capability_evidence_by_event(event_id):
    with get_db() as conn:
        conn.execute(
            "DELETE FROM capability_evidence WHERE event_id = ? AND evidence_type = 'event'",
            (event_id,),
        )


def get_stage_record(newcomer_id, stage_id):
    with get_db() as conn:
        row = conn.execute(
            """SELECT * FROM newcomer_stage_records
               WHERE newcomer_id = ? AND stage_id = ?""",
            (newcomer_id, stage_id),
        ).fetchone()
        return _row_stage(row) if row else None


def list_stage_records(newcomer_id):
    with get_db() as conn:
        rows = conn.execute(
            """SELECT * FROM newcomer_stage_records
               WHERE newcomer_id = ?""",
            (newcomer_id,),
        ).fetchall()
        return [_row_stage(r) for r in rows]


def upsert_stage_record(newcomer_id, stage_id, payload):
    existing = get_stage_record(newcomer_id, stage_id)
    now = _now()
    rid = (existing or {}).get("id") or f"nsr_{uuid.uuid4().hex[:10]}"
    fields = {
        "stage_goal": payload.get("stage_goal") if payload.get("stage_goal") is not None else (existing or {}).get("stage_goal") or "",
        "role_requirements": payload.get("role_requirements") if payload.get("role_requirements") is not None else (existing or {}).get("role_requirements") or "",
        "stage_tasks": payload.get("stage_tasks") if payload.get("stage_tasks") is not None else (existing or {}).get("stage_tasks") or [],
        "human_ai_division": payload.get("human_ai_division") if payload.get("human_ai_division") is not None else (existing or {}).get("human_ai_division") or [],
        "self_eval": payload.get("self_eval") if payload.get("self_eval") is not None else (existing or {}).get("self_eval") or "",
        "mentor_eval": payload.get("mentor_eval") if payload.get("mentor_eval") is not None else (existing or {}).get("mentor_eval") or "",
        "result": payload.get("result") if payload.get("result") is not None else (existing or {}).get("result") or "",
        "capability_changes": payload.get("capability_changes") if payload.get("capability_changes") is not None else (existing or {}).get("capability_changes") or [],
        "passed": payload.get("passed") if payload.get("passed") is not None else (existing or {}).get("passed") or 0,
    }
    with get_db() as conn:
        conn.execute(
            """INSERT INTO newcomer_stage_records
               (id, newcomer_id, stage_id, stage_goal, role_requirements, stage_tasks_json,
                human_ai_json, self_eval, mentor_eval, result, capability_changes_json,
                passed, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(newcomer_id, stage_id) DO UPDATE SET
                 stage_goal = excluded.stage_goal,
                 role_requirements = excluded.role_requirements,
                 stage_tasks_json = excluded.stage_tasks_json,
                 human_ai_json = excluded.human_ai_json,
                 self_eval = excluded.self_eval,
                 mentor_eval = excluded.mentor_eval,
                 result = excluded.result,
                 capability_changes_json = excluded.capability_changes_json,
                 passed = excluded.passed,
                 updated_at = excluded.updated_at""",
            (
                rid, newcomer_id, stage_id,
                fields["stage_goal"], fields["role_requirements"],
                _dumps(fields["stage_tasks"]), _dumps(fields["human_ai_division"]),
                fields["self_eval"], fields["mentor_eval"], fields["result"],
                _dumps(fields["capability_changes"]),
                1 if fields["passed"] else 0, now,
            ),
        )
    return get_stage_record(newcomer_id, stage_id)


def _row_stage(row):
    item = dict(row)
    item["stage_tasks"] = _loads(item.pop("stage_tasks_json", None), default=[])
    item["human_ai_division"] = _loads(item.pop("human_ai_json", None), default=[])
    item["capability_changes"] = _loads(item.pop("capability_changes_json", None), default=[])
    item["passed"] = bool(item.get("passed"))
    return item


def get_project_growth(project_id, person_id):
    with get_db() as conn:
        row = conn.execute(
            """SELECT * FROM project_growth_evidence
               WHERE project_id = ? AND person_id = ?""",
            (project_id, person_id),
        ).fetchone()
        return dict(row) if row else None


def list_project_growth(project_id=None, person_id=None):
    query = "SELECT * FROM project_growth_evidence WHERE 1=1"
    params = []
    if project_id:
        query += " AND project_id = ?"
        params.append(project_id)
    if person_id:
        query += " AND person_id = ?"
        params.append(person_id)
    query += " ORDER BY updated_at DESC"
    with get_db() as conn:
        return [dict(r) for r in conn.execute(query, params).fetchall()]


def upsert_project_growth(project_id, person_id, payload):
    existing = get_project_growth(project_id, person_id) or {}
    now = _now()
    rid = existing.get("id") or f"pge_{uuid.uuid4().hex[:10]}"
    keys = [
        "project_role", "responsibility", "key_decisions", "risk_handling",
        "resource_coordination", "collaboration", "newcomer_training",
        "outcome", "retrospective",
    ]
    values = {}
    for k in keys:
        if k in payload and payload[k] is not None:
            values[k] = payload[k]
        else:
            values[k] = existing.get(k) or ""
    event_id = payload.get("event_id") if "event_id" in payload else existing.get("event_id")
    with get_db() as conn:
        conn.execute(
            """INSERT INTO project_growth_evidence
               (id, project_id, person_id, project_role, responsibility, key_decisions,
                risk_handling, resource_coordination, collaboration, newcomer_training,
                outcome, retrospective, event_id, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(project_id, person_id) DO UPDATE SET
                 project_role = excluded.project_role,
                 responsibility = excluded.responsibility,
                 key_decisions = excluded.key_decisions,
                 risk_handling = excluded.risk_handling,
                 resource_coordination = excluded.resource_coordination,
                 collaboration = excluded.collaboration,
                 newcomer_training = excluded.newcomer_training,
                 outcome = excluded.outcome,
                 retrospective = excluded.retrospective,
                 event_id = excluded.event_id,
                 updated_at = excluded.updated_at""",
            (
                rid, project_id, person_id,
                values["project_role"], values["responsibility"], values["key_decisions"],
                values["risk_handling"], values["resource_coordination"],
                values["collaboration"], values["newcomer_training"],
                values["outcome"], values["retrospective"], event_id, now,
            ),
        )
    return get_project_growth(project_id, person_id)
