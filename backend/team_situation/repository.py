"""团队态势持久化。"""

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
        return {} if default is None else default
    if isinstance(raw, (dict, list)):
        return raw
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return {} if default is None else default


def get_config():
    defaults = {
        "project_weight": 40,
        "member_weight": 25,
        "task_weight": 20,
        "collab_weight": 15,
        "scheduler_enabled": True,
        "scheduler_hour": 12,
        "scheduler_minute": 0,
        "included_member_ids": None,
    }
    with get_db() as conn:
        rows = conn.execute("SELECT key, value FROM team_situation_config").fetchall()
    for r in rows:
        try:
            defaults[r["key"]] = json.loads(r["value"])
        except (json.JSONDecodeError, TypeError):
            defaults[r["key"]] = r["value"]
    return defaults


def resolve_included_members(all_members, config=None):
    """未配置时计入全部成员；配置后只计入勾选人员。"""
    cfg = config if config is not None else get_config()
    ids = cfg.get("included_member_ids")
    if not ids or not isinstance(ids, list):
        return list(all_members or [])
    idset = {str(x) for x in ids}
    return [m for m in (all_members or []) if str(m.get("id")) in idset]


def set_config(updates: dict):
    with get_db() as conn:
        for k, v in (updates or {}).items():
            conn.execute(
                """INSERT INTO team_situation_config (key, value) VALUES (?, ?)
                   ON CONFLICT(key) DO UPDATE SET value = excluded.value""",
                (k, _dumps(v) if not isinstance(v, str) else v),
            )
    return get_config()


def get_job(job_id=None):
    with get_db() as conn:
        if job_id:
            row = conn.execute("SELECT * FROM team_situation_job WHERE id = ?", (job_id,)).fetchone()
        else:
            row = conn.execute(
                "SELECT * FROM team_situation_job ORDER BY started_at DESC LIMIT 1"
            ).fetchone()
        return dict(row) if row else None


def get_running_job():
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM team_situation_job WHERE status = 'running' ORDER BY started_at DESC LIMIT 1"
        ).fetchone()
        return dict(row) if row else None


def find_job_by_key(idempotency_key, report_date):
    with get_db() as conn:
        row = conn.execute(
            """SELECT * FROM team_situation_job
               WHERE idempotency_key = ? AND report_date = ?
               ORDER BY started_at DESC LIMIT 1""",
            (idempotency_key, report_date),
        ).fetchone()
        return dict(row) if row else None


def create_job(report_date, idempotency_key, trigger="manual"):
    job_id = f"sit_{uuid.uuid4().hex[:12]}"
    now = _now()
    with get_db() as conn:
        conn.execute(
            """INSERT INTO team_situation_job
               (id, report_date, status, progress, current_step, idempotency_key, started_at)
               VALUES (?, ?, 'running', 2, '数据采集', ?, ?)""",
            (job_id, report_date, idempotency_key, now),
        )
    return get_job(job_id)


def update_job(job_id, **fields):
    if not fields:
        return
    sets = ", ".join(f"{k} = ?" for k in fields)
    params = list(fields.values()) + [job_id]
    with get_db() as conn:
        conn.execute(f"UPDATE team_situation_job SET {sets} WHERE id = ?", params)


def save_report(payload):
    rid = payload.get("id") or f"tsr_{payload['report_date'].replace('-', '')}_{uuid.uuid4().hex[:6]}"
    now = _now()
    with get_db() as conn:
        conn.execute("DELETE FROM member_situation WHERE report_id IN (SELECT id FROM team_situation_report WHERE report_date = ?)", (payload["report_date"],))
        conn.execute("DELETE FROM project_situation WHERE report_id IN (SELECT id FROM team_situation_report WHERE report_date = ?)", (payload["report_date"],))
        conn.execute("DELETE FROM situation_risk WHERE report_id IN (SELECT id FROM team_situation_report WHERE report_date = ?)", (payload["report_date"],))
        conn.execute("DELETE FROM situation_change WHERE report_id IN (SELECT id FROM team_situation_report WHERE report_date = ?)", (payload["report_date"],))
        conn.execute("DELETE FROM situation_question WHERE report_id IN (SELECT id FROM team_situation_report WHERE report_date = ?)", (payload["report_date"],))
        conn.execute("DELETE FROM team_situation_report WHERE report_date = ?", (payload["report_date"],))
        conn.execute(
            """INSERT INTO team_situation_report
               (id, report_date, team_health_score, team_status, project_score, member_score,
                task_score, collaboration_score, summary, llm_json, weights_json, snapshot_json,
                trigger, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                rid, payload["report_date"], payload.get("team_health_score"),
                payload.get("team_status"), payload.get("project_score"),
                payload.get("member_score"), payload.get("task_score"),
                payload.get("collaboration_score"), payload.get("summary"),
                _dumps(payload.get("llm_json") or {}),
                _dumps(payload.get("weights") or {}),
                _dumps(payload.get("snapshot_meta") or {}),
                payload.get("trigger") or "manual", now,
            ),
        )
        for m in payload.get("members") or []:
            extras = {
                **(m.get("metrics") or {}),
                "name": m.get("name"),
                "role": m.get("role"),
                "main_work": m.get("main_work"),
                "projects": m.get("projects") or [],
                "projects_added": m.get("projects_added") or [],
                "projects_exited": m.get("projects_exited") or [],
                "owned_projects": m.get("owned_projects") or [],
                "pc_roles": m.get("pc_roles") or [],
                "core_project_count": m.get("core_project_count") or 0,
                "p0_project_count": m.get("p0_project_count") or 0,
                "collab_signals": m.get("collab_signals") or [],
                "role_cards": m.get("role_cards") or [],
                "workload_band": m.get("workload_band"),
                "report_days_7": m.get("report_days_7"),
                "report_days_30": m.get("report_days_30"),
            }
            conn.execute(
                """INSERT INTO member_situation
                   (report_id, member_id, workload_score, work_focus, focus_change, project_count,
                    role_change, risk_level, summary, confidence, metrics_json)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    rid, m["member_id"], m.get("workload_score"),
                    _dumps(m.get("work_focus") or {}),
                    _dumps(m.get("focus_change") or {}),
                    m.get("project_count") or 0, m.get("role_change") or "",
                    m.get("risk_level") or "info", m.get("summary") or "",
                    m.get("confidence") or 0, _dumps(extras),
                ),
            )
        for p in payload.get("projects") or []:
            extras = {
                **(p.get("metrics") or {}),
                "current_stage": p.get("current_stage"),
                "week": p.get("week") or {},
                "members": p.get("members") or [],
                "owner_id": p.get("owner_id"),
                "days_since_update": p.get("days_since_update"),
                "start_date": p.get("start_date"),
                "last_date": p.get("last_date"),
                "bottleneck_member_id": p.get("bottleneck_member_id"),
                "source": p.get("source"),
                "project_status": p.get("project_status"),
                "priority": p.get("priority"),
                "owner_name": p.get("owner_name"),
                "previous_stage": p.get("previous_stage"),
                "recent_changes": p.get("recent_changes") or [],
                "health": p.get("health") or {},
                "health_trend": p.get("health_trend"),
                "open_risks": p.get("open_risks") or [],
                "milestones": p.get("milestones") or [],
                "member_roles": p.get("member_roles") or [],
            }
            conn.execute(
                """INSERT INTO project_situation
                   (report_id, project_id, project_name, progress, progress_change,
                    schedule_status, risk_level, summary, confidence, metrics_json)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    rid, p["project_id"], p.get("project_name"), p.get("progress"),
                    p.get("progress_change") or 0, p.get("schedule_status") or "normal",
                    p.get("risk_level") or "info", p.get("summary") or "",
                    p.get("confidence") or 0, _dumps(extras),
                ),
            )
        for r in payload.get("risks") or []:
            conn.execute(
                """INSERT INTO situation_risk
                   (id, report_id, object_type, object_id, risk_type, severity, title,
                    description, evidence, confidence, status, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    r.get("risk_id") or r.get("id") or f"R{uuid.uuid4().hex[:10]}", rid,
                    r.get("object_type"), r.get("object_id"), r.get("type") or r.get("risk_type"),
                    r.get("severity"), r.get("title"), r.get("description"),
                    _dumps({
                        "facts": r.get("evidence") or [],
                        "category": r.get("category"),
                        "attention": bool(r.get("attention")),
                        "member_id": r.get("member_id"),
                        "project_id": r.get("project_id"),
                        "priority": r.get("priority"),
                    }), r.get("confidence") or 0,
                    r.get("status") or "open", now,
                ),
            )
        for c in payload.get("changes") or []:
            conn.execute(
                """INSERT INTO situation_change
                   (report_id, object_type, object_id, change_type, before_value, after_value,
                    change_score, description, confidence, evidence)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    rid, c.get("object_type"), c.get("object_id"), c.get("change_type"),
                    str(c.get("before_value") or ""), str(c.get("after_value") or ""),
                    c.get("change_score") or 0, c.get("description") or "",
                    c.get("confidence") or 0,                     _dumps({
                        "facts": c.get("evidence") or [],
                        "title": c.get("title"),
                        "change_label": c.get("change_label"),
                        "stars": c.get("stars"),
                        "severity": c.get("severity"),
                        "project_name": c.get("project_name"),
                    }),
                ),
            )
        for q in payload.get("questions") or []:
            conn.execute(
                """INSERT INTO situation_question
                   (id, report_id, member_id, question, status, created_at)
                   VALUES (?, ?, ?, ?, 'open', ?)""",
                (q.get("id") or f"q_{uuid.uuid4().hex[:10]}", rid, q.get("member_id"), q.get("question"), now),
            )
    return get_report(rid)


def _hydrate_report(row):
    item = dict(row)
    item["llm_json"] = _loads(item.get("llm_json"), default={})
    item["weights"] = _loads(item.get("weights_json"), default={})
    item["snapshot_meta"] = _loads(item.get("snapshot_json"), default={})
    item.pop("weights_json", None)
    item.pop("snapshot_json", None)
    return item


def get_report(report_id):
    with get_db() as conn:
        row = conn.execute("SELECT * FROM team_situation_report WHERE id = ?", (report_id,)).fetchone()
        if not row:
            return None
        return _assemble(_hydrate_report(row), conn)


def get_report_by_date(report_date):
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM team_situation_report WHERE report_date = ? ORDER BY created_at DESC LIMIT 1",
            (report_date,),
        ).fetchone()
        if not row:
            return None
        return _assemble(_hydrate_report(row), conn)


def latest_report():
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM team_situation_report ORDER BY report_date DESC, created_at DESC LIMIT 1"
        ).fetchone()
        if not row:
            return None
        return _assemble(_hydrate_report(row), conn)


def list_reports(start_date=None, end_date=None, limit=30):
    query = "SELECT * FROM team_situation_report WHERE 1=1"
    params = []
    if start_date:
        query += " AND report_date >= ?"
        params.append(start_date)
    if end_date:
        query += " AND report_date <= ?"
        params.append(end_date)
    query += " ORDER BY report_date DESC, created_at DESC LIMIT ?"
    params.append(limit)
    with get_db() as conn:
        rows = conn.execute(query, params).fetchall()
        return [_hydrate_report(r) for r in rows]


def list_recent_reports(days=7):
    with get_db() as conn:
        rows = conn.execute(
            """SELECT * FROM team_situation_report
               WHERE report_date >= date('now', '+8 hours', ?)
               ORDER BY report_date ASC""",
            (f"-{int(days)} days",),
        ).fetchall()
        return [_hydrate_report(r) for r in rows]


def latest_report_before(report_date):
    with get_db() as conn:
        row = conn.execute(
            """SELECT * FROM team_situation_report
               WHERE report_date < ?
               ORDER BY report_date DESC, created_at DESC LIMIT 1""",
            (report_date,),
        ).fetchone()
        if not row:
            return None
        return _assemble(_hydrate_report(row), conn)


def previous_project_progress(project_id, before_date, days=3):
    with get_db() as conn:
        rows = conn.execute(
            """SELECT ps.progress, r.report_date
               FROM project_situation ps
               JOIN team_situation_report r ON r.id = ps.report_id
               WHERE ps.project_id = ? AND r.report_date < ? AND r.report_date >= date(?, ?)
               ORDER BY r.report_date DESC""",
            (project_id, before_date, before_date, f"-{int(days)} days"),
        ).fetchall()
        return [dict(r) for r in rows]


def _assemble(report, conn):
    rid = report["id"]
    members = []
    for r in conn.execute("SELECT * FROM member_situation WHERE report_id = ?", (rid,)).fetchall():
        item = dict(r)
        item["work_focus"] = _loads(item.get("work_focus"), default={})
        item["focus_change"] = _loads(item.get("focus_change"), default={})
        item["metrics"] = _loads(item.get("metrics_json"), default={})
        item.pop("metrics_json", None)
        mx = item["metrics"]
        item["name"] = mx.get("name") or item.get("name")
        item["role"] = mx.get("role")
        item["main_work"] = mx.get("main_work")
        item["projects"] = mx.get("projects") or []
        item["projects_added"] = mx.get("projects_added") or []
        item["projects_exited"] = mx.get("projects_exited") or []
        item["owned_projects"] = mx.get("owned_projects") or []
        item["pc_roles"] = mx.get("pc_roles") or []
        item["core_project_count"] = mx.get("core_project_count") or 0
        item["p0_project_count"] = mx.get("p0_project_count") or 0
        item["collab_signals"] = mx.get("collab_signals") or []
        item["role_cards"] = mx.get("role_cards") or []
        item["workload_band"] = mx.get("workload_band")
        item["report_days_7"] = mx.get("report_days_7")
        item["report_days_30"] = mx.get("report_days_30")
        members.append(item)
    projects = []
    for r in conn.execute("SELECT * FROM project_situation WHERE report_id = ?", (rid,)).fetchall():
        item = dict(r)
        item["metrics"] = _loads(item.get("metrics_json"), default={})
        item.pop("metrics_json", None)
        mx = item["metrics"]
        item["current_stage"] = mx.get("current_stage")
        item["week"] = mx.get("week") or {}
        item["members"] = mx.get("members") or []
        item["owner_id"] = mx.get("owner_id")
        item["days_since_update"] = mx.get("days_since_update")
        item["start_date"] = mx.get("start_date")
        item["last_date"] = mx.get("last_date")
        item["bottleneck_member_id"] = mx.get("bottleneck_member_id")
        item["source"] = mx.get("source")
        item["project_status"] = mx.get("project_status")
        item["priority"] = mx.get("priority")
        item["owner_name"] = mx.get("owner_name")
        item["previous_stage"] = mx.get("previous_stage")
        item["recent_changes"] = mx.get("recent_changes") or []
        item["health"] = mx.get("health") or {}
        item["health_trend"] = mx.get("health_trend")
        item["open_risks"] = mx.get("open_risks") or []
        item["milestones"] = mx.get("milestones") or []
        item["member_roles"] = mx.get("member_roles") or []
        projects.append(item)
    risks = []
    for r in conn.execute("SELECT * FROM situation_risk WHERE report_id = ?", (rid,)).fetchall():
        item = dict(r)
        item["risk_id"] = item.get("id")
        item["type"] = item.get("risk_type")
        ev = _loads(item.get("evidence"), default=[])
        if isinstance(ev, dict):
            item["evidence"] = ev.get("facts") or []
            item["category"] = ev.get("category")
            item["attention"] = bool(ev.get("attention"))
            item["member_id"] = ev.get("member_id")
            item["project_id"] = ev.get("project_id")
            item["priority"] = ev.get("priority")
        else:
            item["evidence"] = ev if isinstance(ev, list) else []
        risks.append(item)
    changes = []
    for r in conn.execute("SELECT * FROM situation_change WHERE report_id = ?", (rid,)).fetchall():
        item = dict(r)
        ev = _loads(item.get("evidence"), default=[])
        if isinstance(ev, dict):
            item["evidence"] = ev.get("facts") or []
            item["title"] = ev.get("title") or item.get("description")
            item["change_label"] = ev.get("change_label")
            item["stars"] = ev.get("stars")
            item["severity"] = ev.get("severity")
        else:
            item["evidence"] = ev if isinstance(ev, list) else []
            item["title"] = item.get("description")
        changes.append(item)
    questions = [dict(r) for r in conn.execute(
        "SELECT * FROM situation_question WHERE report_id = ?", (rid,)
    ).fetchall()]
    report["members"] = members
    report["projects"] = projects
    report["risks"] = risks
    report["changes"] = changes
    report["questions"] = questions
    meta = report.get("snapshot_meta") or {}
    open_ids = {r.get("risk_id") or r.get("id") for r in risks if r.get("status") == "open"}
    attn = meta.get("attention_items") or []
    report["attention_items"] = [
        a for a in attn if (a.get("risk_id") or a.get("id")) in open_ids
    ]
    if not report["attention_items"]:
        report["attention_items"] = [r for r in risks if r.get("attention") and r.get("status") == "open"]
    report["project_stats"] = meta.get("project_stats") or {}
    report["resource_conflicts"] = meta.get("resource_conflicts") or []
    report["member_status"] = meta.get("member_status") or report.get("team_status")
    report["project_status_label"] = meta.get("project_status") or report.get("team_status")
    return report


def list_context(context_date=None, days=7):
    query = "SELECT * FROM team_context WHERE 1=1"
    params = []
    if context_date:
        query += " AND context_date = ?"
        params.append(context_date)
    else:
        query += " AND context_date >= date('now', '+8 hours', ?)"
        params.append(f"-{int(days)} days")
    query += " ORDER BY created_at DESC"
    with get_db() as conn:
        return [dict(r) for r in conn.execute(query, params).fetchall()]


def add_context(context_date, context_type, content, creator_id=""):
    now = _now()
    with get_db() as conn:
        c = conn.cursor()
        c.execute(
            """INSERT INTO team_context
               (context_date, context_type, content, source, creator_id, created_at)
               VALUES (?, ?, ?, 'manual', ?, ?)""",
            (context_date, context_type, content, creator_id, now),
        )
        return c.lastrowid


def update_risk(risk_id, status):
    with get_db() as conn:
        conn.execute("UPDATE situation_risk SET status = ? WHERE id = ?", (status, risk_id))
        row = conn.execute("SELECT * FROM situation_risk WHERE id = ?", (risk_id,)).fetchone()
        if not row:
            return None
        item = dict(row)
        item["evidence"] = _loads(item.get("evidence"), default=[])
        return item


def answer_question(question_id, status, answer=""):
    now = _now()
    with get_db() as conn:
        conn.execute(
            """UPDATE situation_question
               SET status = ?, answer = ?, resolved_at = ? WHERE id = ?""",
            (status, answer, now, question_id),
        )
        row = conn.execute("SELECT * FROM situation_question WHERE id = ?", (question_id,)).fetchone()
        return dict(row) if row else None
