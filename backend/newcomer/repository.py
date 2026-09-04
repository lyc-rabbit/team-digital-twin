"""新人地图数据访问。"""

import json
import uuid
from timeutil import now_iso

from database import get_db


def _now():
    return now_iso()


def _dumps(obj):
    return json.dumps(obj, ensure_ascii=False)


def _loads(raw, default=None):
    if raw is None:
        return [] if default is None else default
    if isinstance(raw, (list, dict)):
        return raw
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return [] if default is None else default


def _row_newcomer(row):
    item = dict(row)
    item["compete_in_ranking"] = bool(item.get("compete_in_ranking"))
    item["progress"] = float(item.get("progress") or 0)
    return item


def _row_task(row):
    item = dict(row)
    item["requirements"] = _loads(item.get("requirements"), default=[])
    item["capability_ids"] = _loads(item.get("capability_ids"), default=[])
    item["ai_allowed"] = bool(item.get("ai_allowed"))
    item["review_required"] = bool(item.get("review_required"))
    item["help_requested"] = bool(item.get("help_requested"))
    return item


def list_newcomers(status="active"):
    query = "SELECT * FROM newcomers WHERE 1=1"
    params = []
    if status:
        query += " AND status = ?"
        params.append(status)
    query += " ORDER BY entry_date DESC, created_at DESC"
    with get_db() as conn:
        return [_row_newcomer(r) for r in conn.execute(query, params).fetchall()]


def get_newcomer(newcomer_id):
    with get_db() as conn:
        row = conn.execute("SELECT * FROM newcomers WHERE id = ?", (newcomer_id,)).fetchone()
        return _row_newcomer(row) if row else None


def get_newcomer_by_employee(employee_id):
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM newcomers WHERE employee_id = ?", (employee_id,)
        ).fetchone()
        return _row_newcomer(row) if row else None


def create_newcomer(payload):
    nid = payload.get("id") or f"nc_{uuid.uuid4().hex[:10]}"
    now = _now()
    with get_db() as conn:
        conn.execute(
            """INSERT INTO newcomers
               (id, employee_id, entry_date, current_role, current_role_id, target_role_id,
                onboarding_stage, compete_in_ranking, status, progress, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'active', 0, ?, ?)""",
            (
                nid,
                payload["employee_id"],
                payload["entry_date"],
                payload.get("current_role") or "",
                payload.get("current_role_id") or "",
                payload.get("target_role_id") or "",
                payload.get("onboarding_stage") or "onboarding",
                1 if payload.get("compete_in_ranking") else 0,
                now,
                now,
            ),
        )
    return get_newcomer(nid)


def update_newcomer(newcomer_id, **fields):
    allowed = {
        "entry_date", "current_role", "current_role_id", "target_role_id",
        "onboarding_stage", "compete_in_ranking", "status", "progress",
    }
    sets = []
    params = []
    for k, v in fields.items():
        if k not in allowed or v is None:
            continue
        if k == "compete_in_ranking":
            v = 1 if v else 0
        sets.append(f"{k} = ?")
        params.append(v)
    if not sets:
        return get_newcomer(newcomer_id)
    sets.append("updated_at = ?")
    params.append(_now())
    params.append(newcomer_id)
    with get_db() as conn:
        conn.execute(f"UPDATE newcomers SET {', '.join(sets)} WHERE id = ?", params)
    return get_newcomer(newcomer_id)


def delete_newcomer(newcomer_id):
    with get_db() as conn:
        conn.execute("DELETE FROM newcomers WHERE id = ?", (newcomer_id,))


def list_tasks(newcomer_id):
    with get_db() as conn:
        rows = conn.execute(
            """SELECT * FROM newcomer_tasks
               WHERE newcomer_id = ?
               ORDER BY sort_order ASC, created_at ASC""",
            (newcomer_id,),
        ).fetchall()
        return [_row_task(r) for r in rows]


def get_task(task_id):
    with get_db() as conn:
        row = conn.execute("SELECT * FROM newcomer_tasks WHERE id = ?", (task_id,)).fetchone()
        return _row_task(row) if row else None


def insert_task(newcomer_id, payload, sort_order=0):
    tid = payload.get("id") or f"nct_{uuid.uuid4().hex[:10]}"
    with get_db() as conn:
        conn.execute(
            """INSERT INTO newcomer_tasks
               (id, newcomer_id, task_name, task_level, description, requirements,
                estimated_hours, ai_allowed, review_required, status, due_at,
                capability_ids, sort_order, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                tid,
                newcomer_id,
                payload["task_name"],
                payload.get("task_level") or "L0",
                payload.get("description") or "",
                _dumps(payload.get("requirements") or []),
                float(payload.get("estimated_hours") or 4),
                1 if payload.get("ai_allowed", True) else 0,
                1 if payload.get("review_required", True) else 0,
                payload.get("status") or "todo",
                payload.get("due_at"),
                _dumps(payload.get("capability_ids") or []),
                sort_order,
                _now(),
            ),
        )
    return get_task(tid)


def update_task(task_id, **fields):
    allowed = {
        "task_name", "task_level", "description", "requirements", "estimated_hours",
        "ai_allowed", "review_required", "status", "due_at", "started_at",
        "completed_at", "blocked_reason", "help_requested", "capability_ids", "sort_order",
    }
    sets = []
    params = []
    for k, v in fields.items():
        if k not in allowed:
            continue
        if k in ("requirements", "capability_ids"):
            v = _dumps(v or [])
        elif k in ("ai_allowed", "review_required", "help_requested"):
            v = 1 if v else 0
        sets.append(f"{k} = ?")
        params.append(v)
    if not sets:
        return get_task(task_id)
    params.append(task_id)
    with get_db() as conn:
        conn.execute(f"UPDATE newcomer_tasks SET {', '.join(sets)} WHERE id = ?", params)
    return get_task(task_id)


def insert_evidence(employee_id, task_id, capability_id, capability_name, content, score):
    with get_db() as conn:
        conn.execute(
            """INSERT INTO capability_evidence
               (employee_id, task_id, capability_id, capability_name,
                evidence_type, evidence_content, score, created_at)
               VALUES (?, ?, ?, ?, 'task', ?, ?, ?)""",
            (employee_id, task_id, capability_id, capability_name, content, score, _now()),
        )


def list_evidence(employee_id):
    with get_db() as conn:
        rows = conn.execute(
            """SELECT * FROM capability_evidence
               WHERE employee_id = ? ORDER BY created_at DESC""",
            (employee_id,),
        ).fetchall()
        return [dict(r) for r in rows]


def list_open_interventions(newcomer_id=None):
    query = "SELECT * FROM newcomer_interventions WHERE status = 'open'"
    params = []
    if newcomer_id:
        query += " AND newcomer_id = ?"
        params.append(newcomer_id)
    query += " ORDER BY created_at DESC"
    with get_db() as conn:
        return [dict(r) for r in conn.execute(query, params).fetchall()]


def close_open_interventions(newcomer_id):
    with get_db() as conn:
        conn.execute(
            """UPDATE newcomer_interventions
               SET status = 'resolved', resolved_at = ?
               WHERE newcomer_id = ? AND status = 'open'""",
            (_now(), newcomer_id),
        )


def insert_intervention(newcomer_id, level, reason, action):
    iid = f"nci_{uuid.uuid4().hex[:10]}"
    with get_db() as conn:
        conn.execute(
            """INSERT INTO newcomer_interventions
               (id, newcomer_id, level, reason, recommended_action, status, created_at)
               VALUES (?, ?, ?, ?, ?, 'open', ?)""",
            (iid, newcomer_id, level, reason, action, _now()),
        )
    return iid


def get_guide(newcomer_id):
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM newcomer_guides WHERE newcomer_id = ?", (newcomer_id,)
        ).fetchone()
        if not row:
            return None
        item = dict(row)
        item["content"] = _loads(item.pop("content_json", None), default={})
        return item


def upsert_guide(newcomer_id, content, source="template", status="draft"):
    now = _now()
    with get_db() as conn:
        conn.execute(
            """INSERT INTO newcomer_guides (newcomer_id, content_json, status, source, updated_at)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(newcomer_id) DO UPDATE SET
                 content_json = excluded.content_json,
                 status = excluded.status,
                 source = excluded.source,
                 updated_at = excluded.updated_at""",
            (newcomer_id, _dumps(content), status, source, now),
        )
    return get_guide(newcomer_id)


def list_known_projects():
    from database import get_daily_reports
    names = {}
    for r in get_daily_reports(limit=1000):
        for p in r.get("projects") or []:
            if not p or p == "未分类":
                continue
            names[p] = names.get(p, 0) + 1
    return [{"name": k, "count": v} for k, v in sorted(names.items(), key=lambda x: -x[1])]


def project_member_ids(project_name=None):
    from database import get_daily_reports
    ids = set()
    for r in get_daily_reports(limit=1000):
        projects = r.get("projects") or []
        if project_name:
            if project_name in projects:
                ids.add(r["member_id"])
        elif projects:
            ids.add(r["member_id"])
    return ids
