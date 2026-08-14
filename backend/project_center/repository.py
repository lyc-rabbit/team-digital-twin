"""项目中心持久化。"""

import json
import uuid
from datetime import datetime

from database import get_db, get_member


def _now():
    return datetime.now().isoformat(timespec="seconds")


def _today():
    return datetime.now().strftime("%Y-%m-%d")


def _id(prefix):
    return f"{prefix}_{uuid.uuid4().hex[:10]}"


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


def _row(r):
    return dict(r) if r else None


def create_project(payload):
    pid = _id("proj")
    now = _now()
    stages = payload.get("stages") or []
    if not stages:
        raise ValueError("项目至少需要一个阶段")
    with get_db() as conn:
        conn.execute(
            """INSERT INTO pc_project
               (id, name, description, owner_id, status, type, priority, business,
                tags_json, start_date, end_date, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                pid, payload["name"].strip(), payload["description"].strip(),
                payload["owner_id"], payload.get("status") or "open",
                payload.get("type") or "", payload.get("priority") or "",
                payload.get("business") or "", _dumps(payload.get("tags") or []),
                payload.get("start_date") or "", payload.get("end_date") or "",
                now, now,
            ),
        )
        first_id = None
        for i, st in enumerate(stages):
            sid = _id("stg")
            if i == 0:
                first_id = sid
            status = st.get("status") or ("in_progress" if i == 0 else "not_started")
            conn.execute(
                """INSERT INTO pc_stage
                   (id, project_id, name, description, sort_order, status, progress,
                    owner_id, planned_start_date, planned_end_date, actual_start_date,
                    created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    sid, pid, (st.get("name") or "").strip(), st.get("description") or "",
                    i + 1, status, st.get("progress"),
                    st.get("owner_id") or payload["owner_id"],
                    st.get("planned_start_date") or "", st.get("planned_end_date") or "",
                    _today() if status == "in_progress" else "",
                    now, now,
                ),
            )
        conn.execute(
            "UPDATE pc_project SET current_stage_id = ?, updated_at = ? WHERE id = ?",
            (first_id, now, pid),
        )
        conn.execute(
            """INSERT INTO pc_member (id, project_id, user_id, role, participation_level)
               VALUES (?, ?, ?, '负责人', '核心')""",
            (_id("pm"), pid, payload["owner_id"]),
        )
        for m in payload.get("members") or []:
            uid = m.get("user_id") or m.get("member_id")
            if not uid or uid == payload["owner_id"]:
                continue
            conn.execute(
                """INSERT INTO pc_member (id, project_id, user_id, role, responsibility, participation_level)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    _id("pm"), pid, uid, m.get("role") or "其他",
                    m.get("responsibility") or "", m.get("participation_level") or "主要",
                ),
            )
        conn.execute(
            """INSERT INTO pc_activity
               (id, project_id, stage_id, type, content, source, operator_id, created_at)
               VALUES (?, ?, ?, 'created', ?, 'SYSTEM', ?, ?)""",
            (_id("act"), pid, first_id, f"创建项目「{payload['name'].strip()}」", payload["owner_id"], now),
        )
    return get_project(pid)


def update_project(project_id, payload):
    item = get_project(project_id)
    if not item:
        return None
    fields = {}
    for k in ("name", "description", "owner_id", "status", "type", "priority", "business",
              "start_date", "end_date", "current_stage_id"):
        if k in payload and payload[k] is not None:
            fields[k] = payload[k]
    if "tags" in payload:
        fields["tags_json"] = _dumps(payload["tags"] or [])
    if payload.get("status") == "closed" and not item.get("archived_at"):
        fields["archived_at"] = _now()
    if payload.get("status") and payload["status"] != "closed":
        fields["archived_at"] = ""
    if not fields:
        return item
    fields["updated_at"] = _now()
    sets = ", ".join(f"{k} = ?" for k in fields)
    with get_db() as conn:
        conn.execute(f"UPDATE pc_project SET {sets} WHERE id = ?", list(fields.values()) + [project_id])
        if payload.get("owner_id") and payload["owner_id"] != item.get("owner_id"):
            exists = conn.execute(
                "SELECT id FROM pc_member WHERE project_id = ? AND user_id = ?",
                (project_id, payload["owner_id"]),
            ).fetchone()
            if not exists:
                conn.execute(
                    """INSERT INTO pc_member (id, project_id, user_id, role, participation_level)
                       VALUES (?, ?, ?, '负责人', '核心')""",
                    (_id("pm"), project_id, payload["owner_id"]),
                )
    return get_project(project_id)


def delete_project(project_id):
    with get_db() as conn:
        row = conn.execute("SELECT id FROM pc_project WHERE id = ?", (project_id,)).fetchone()
        if not row:
            return False
        objs = conn.execute("SELECT id FROM pc_objective WHERE project_id = ?", (project_id,)).fetchall()
        for o in objs:
            conn.execute("DELETE FROM pc_kr WHERE objective_id = ?", (o["id"],))
        for table in ("pc_stage", "pc_objective", "pc_milestone", "pc_member", "pc_risk", "pc_activity"):
            conn.execute(f"DELETE FROM {table} WHERE project_id = ?", (project_id,))
        conn.execute(
            "DELETE FROM pc_relation WHERE source_project_id = ? OR target_project_id = ?",
            (project_id, project_id),
        )
        conn.execute("DELETE FROM pc_project WHERE id = ?", (project_id,))
    return True


def list_projects(filters=None):
    filters = filters or {}
    query = "SELECT * FROM pc_project WHERE 1=1"
    params = []
    if filters.get("owner_id"):
        query += " AND owner_id = ?"
        params.append(filters["owner_id"])
    if filters.get("status"):
        query += " AND status = ?"
        params.append(filters["status"])
    elif filters.get("archived_only"):
        query += " AND status = 'closed'"
    elif not filters.get("include_archived"):
        query += " AND (status IS NULL OR status NOT IN ('closed', 'archived'))"
    if filters.get("type"):
        query += " AND type = ?"
        params.append(filters["type"])
    if filters.get("priority"):
        query += " AND priority = ?"
        params.append(filters["priority"])
    sort = filters.get("sort") or "updated_at"
    order_sql = {
        "updated_at": "updated_at DESC",
        "priority": "CASE priority WHEN 'P0' THEN 0 WHEN 'P1' THEN 1 WHEN 'P2' THEN 2 ELSE 3 END, updated_at DESC",
        "end_date": "CASE WHEN end_date IS NULL OR end_date = '' THEN 1 ELSE 0 END, end_date ASC",
        "name": "name ASC",
    }.get(sort, "updated_at DESC")
    query += f" ORDER BY {order_sql}"
    with get_db() as conn:
        rows = [dict(r) for r in conn.execute(query, params).fetchall()]
        result = []
        for row in rows:
            item = _hydrate_list_item(row, conn)
            if filters.get("member_id"):
                mid = filters["member_id"]
                member_ids = {m["user_id"] for m in item.get("members") or []}
                if item["owner_id"] != mid and mid not in member_ids:
                    continue
            if filters.get("mine") == "owner" and item["owner_id"] != filters.get("viewer_id"):
                continue
            if filters.get("mine") == "member":
                mid = filters.get("viewer_id")
                member_ids = {m["user_id"] for m in item.get("members") or []}
                if mid not in member_ids or item["owner_id"] == mid:
                    continue
            if filters.get("current_stage"):
                name = (item.get("current_stage") or {}).get("name") or ""
                if filters["current_stage"] not in name:
                    continue
            if filters.get("risk_level"):
                if item.get("top_risk_level") != filters["risk_level"]:
                    continue
            result.append(item)
        if filters.get("sort") == "risk":
            rank = {"high": 0, "medium": 1, "low": 2, "": 3, None: 3}
            result.sort(key=lambda x: rank.get(x.get("top_risk_level"), 9))
        return result


def _hydrate_list_item(row, conn):
    item = dict(row)
    item["tags"] = _loads(item.pop("tags_json", None), default=[])
    pid = item["id"]
    stages = [dict(r) for r in conn.execute(
        "SELECT * FROM pc_stage WHERE project_id = ? ORDER BY sort_order", (pid,)
    ).fetchall()]
    members = [dict(r) for r in conn.execute(
        "SELECT * FROM pc_member WHERE project_id = ?", (pid,)
    ).fetchall()]
    risks = [dict(r) for r in conn.execute(
        "SELECT * FROM pc_risk WHERE project_id = ?", (pid,)
    ).fetchall()]
    milestones = [dict(r) for r in conn.execute(
        "SELECT * FROM pc_milestone WHERE project_id = ?", (pid,)
    ).fetchall()]
    item["stages"] = stages
    item["members"] = members
    item["risks"] = risks
    item["milestones"] = milestones
    item["current_stage"] = _pick_current_stage(stages, item.get("current_stage_id"))
    if item.get("current_stage"):
        item["current_stage_id"] = item["current_stage"]["id"]
    open_risks = [r for r in risks if r.get("status") in ("open", "processing", "开放", "处理中")]
    levels = [r.get("level") for r in open_risks]
    item["open_risk_count"] = len(open_risks)
    item["top_risk_level"] = "high" if "high" in levels or "高" in levels else (
        "medium" if "medium" in levels or "中" in levels else (
            "low" if levels else None
        )
    )
    owner = get_member(item["owner_id"])
    item["owner_name"] = (owner or {}).get("name") or item["owner_id"]
    return item


def get_project(project_id):
    with get_db() as conn:
        row = conn.execute("SELECT * FROM pc_project WHERE id = ?", (project_id,)).fetchone()
        if not row:
            return None
        item = _hydrate_list_item(dict(row), conn)
        item["objectives"] = []
        for o in conn.execute(
            "SELECT * FROM pc_objective WHERE project_id = ? ORDER BY created_at", (project_id,)
        ).fetchall():
            obj = dict(o)
            obj["krs"] = [dict(k) for k in conn.execute(
                "SELECT * FROM pc_kr WHERE objective_id = ?", (obj["id"],)
            ).fetchall()]
            item["objectives"].append(obj)
        item["activities"] = [dict(r) for r in conn.execute(
            "SELECT * FROM pc_activity WHERE project_id = ? ORDER BY created_at DESC LIMIT 80",
            (project_id,),
        ).fetchall()]
        item["relations"] = [dict(r) for r in conn.execute(
            """SELECT * FROM pc_relation
               WHERE source_project_id = ? OR target_project_id = ?
               ORDER BY created_at DESC""",
            (project_id, project_id),
        ).fetchall()]
        return item


def add_stage(project_id, payload):
    with get_db() as conn:
        n = conn.execute("SELECT COUNT(*) AS c FROM pc_stage WHERE project_id = ?", (project_id,)).fetchone()["c"]
        sid = _id("stg")
        now = _now()
        conn.execute(
            """INSERT INTO pc_stage
               (id, project_id, name, description, sort_order, status, progress, owner_id,
                planned_start_date, planned_end_date, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                sid, project_id, payload["name"].strip(), payload.get("description") or "",
                payload.get("sort_order") or (n + 1),
                payload.get("status") or "not_started", payload.get("progress"),
                payload.get("owner_id") or "",
                payload.get("planned_start_date") or "", payload.get("planned_end_date") or "",
                now, now,
            ),
        )
        conn.execute("UPDATE pc_project SET updated_at = ? WHERE id = ?", (now, project_id))
    return get_stage(sid)


def get_stage(stage_id):
    with get_db() as conn:
        row = conn.execute("SELECT * FROM pc_stage WHERE id = ?", (stage_id,)).fetchone()
        return dict(row) if row else None


def _pick_current_stage(stages, current_stage_id):
    """列表/详情的当前阶段：若指针停在已完成阶段、后面还有进行中，则用进行中的。"""
    if not stages:
        return None
    current = next((s for s in stages if s.get("id") == current_stage_id), None)
    in_prog = next((s for s in stages if s.get("status") == "in_progress"), None)
    if in_prog and (not current or current.get("status") == "completed"):
        return in_prog
    return current or in_prog or stages[0]


def update_stage(stage_id, payload):
    stage = get_stage(stage_id)
    if not stage:
        return None
    fields = {}
    for k in ("name", "description", "sort_order", "status", "progress", "owner_id",
              "planned_start_date", "planned_end_date", "actual_start_date", "actual_end_date"):
        if k not in payload:
            continue
        # progress 允许显式写成 NULL（设为未知）；其它字段忽略 None
        if k == "progress" or payload[k] is not None:
            fields[k] = payload[k]
    if not fields:
        return stage
    fields["updated_at"] = _now()
    sets = ", ".join(f"{k} = ?" for k in fields)
    with get_db() as conn:
        conn.execute(f"UPDATE pc_stage SET {sets} WHERE id = ?", list(fields.values()) + [stage_id])
        conn.execute("UPDATE pc_project SET updated_at = ? WHERE id = ?", (_now(), stage["project_id"]))
    return get_stage(stage_id)


def add_activity(project_id, payload):
    aid = _id("act")
    now = _now()
    with get_db() as conn:
        conn.execute(
            """INSERT INTO pc_activity
               (id, project_id, stage_id, type, content, source, source_id, operator_id, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                aid, project_id, payload.get("stage_id") or "",
                payload.get("type") or "note", payload["content"],
                payload.get("source") or "MANUAL", payload.get("source_id") or "",
                payload.get("operator_id") or "", now,
            ),
        )
        conn.execute("UPDATE pc_project SET updated_at = ? WHERE id = ?", (now, project_id))
    with get_db() as conn:
        row = conn.execute("SELECT * FROM pc_activity WHERE id = ?", (aid,)).fetchone()
        return dict(row)


def add_member(project_id, payload):
    with get_db() as conn:
        exists = conn.execute(
            "SELECT id FROM pc_member WHERE project_id = ? AND user_id = ?",
            (project_id, payload["user_id"]),
        ).fetchone()
        if exists:
            conn.execute(
                """UPDATE pc_member SET role = ?, responsibility = ?, participation_level = ?
                   WHERE id = ?""",
                (
                    payload.get("role") or "其他", payload.get("responsibility") or "",
                    payload.get("participation_level") or "主要", exists["id"],
                ),
            )
            mid = exists["id"]
        else:
            mid = _id("pm")
            conn.execute(
                """INSERT INTO pc_member (id, project_id, user_id, role, responsibility, participation_level)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    mid, project_id, payload["user_id"], payload.get("role") or "其他",
                    payload.get("responsibility") or "", payload.get("participation_level") or "主要",
                ),
            )
        conn.execute("UPDATE pc_project SET updated_at = ? WHERE id = ?", (_now(), project_id))
    with get_db() as conn:
        return dict(conn.execute("SELECT * FROM pc_member WHERE id = ?", (mid,)).fetchone())


def delete_member(project_id, member_row_id):
    with get_db() as conn:
        conn.execute("DELETE FROM pc_member WHERE id = ? AND project_id = ?", (member_row_id, project_id))
        conn.execute("UPDATE pc_project SET updated_at = ? WHERE id = ?", (_now(), project_id))
    return True


def add_milestone(project_id, payload):
    mid = _id("ms")
    with get_db() as conn:
        conn.execute(
            """INSERT INTO pc_milestone
               (id, project_id, stage_id, name, description, owner_id, planned_date, actual_date, status, importance)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                mid, project_id, payload.get("stage_id") or "", payload["name"].strip(),
                payload.get("description") or "", payload.get("owner_id") or "",
                payload.get("planned_date") or "", payload.get("actual_date") or "",
                payload.get("status") or "not_started", payload.get("importance") or "normal",
            ),
        )
        conn.execute("UPDATE pc_project SET updated_at = ? WHERE id = ?", (_now(), project_id))
    with get_db() as conn:
        return dict(conn.execute("SELECT * FROM pc_milestone WHERE id = ?", (mid,)).fetchone())


def update_milestone(milestone_id, payload):
    with get_db() as conn:
        row = conn.execute("SELECT * FROM pc_milestone WHERE id = ?", (milestone_id,)).fetchone()
        if not row:
            return None
        fields = {}
        for k in ("name", "description", "stage_id", "owner_id", "planned_date", "actual_date", "status", "importance"):
            if k in payload and payload[k] is not None:
                fields[k] = payload[k]
        if payload.get("status") == "completed" and not (row["actual_date"] or payload.get("actual_date")):
            fields["actual_date"] = _today()
        if fields:
            sets = ", ".join(f"{k} = ?" for k in fields)
            conn.execute(f"UPDATE pc_milestone SET {sets} WHERE id = ?", list(fields.values()) + [milestone_id])
            conn.execute("UPDATE pc_project SET updated_at = ? WHERE id = ?", (_now(), row["project_id"]))
        return dict(conn.execute("SELECT * FROM pc_milestone WHERE id = ?", (milestone_id,)).fetchone())


def add_risk(project_id, payload):
    rid = _id("rk")
    now = _now()
    with get_db() as conn:
        conn.execute(
            """INSERT INTO pc_risk
               (id, project_id, title, description, type, level, probability, impact,
                owner_id, mitigation, status, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                rid, project_id, payload["title"].strip(), payload.get("description") or "",
                payload.get("type") or "其他", payload.get("level") or "medium",
                payload.get("probability") or "", payload.get("impact") or "",
                payload.get("owner_id") or "", payload.get("mitigation") or "",
                payload.get("status") or "open", now,
            ),
        )
        conn.execute("UPDATE pc_project SET updated_at = ? WHERE id = ?", (now, project_id))
    with get_db() as conn:
        return dict(conn.execute("SELECT * FROM pc_risk WHERE id = ?", (rid,)).fetchone())


def update_risk(risk_id, payload):
    with get_db() as conn:
        row = conn.execute("SELECT * FROM pc_risk WHERE id = ?", (risk_id,)).fetchone()
        if not row:
            return None
        fields = {}
        for k in ("title", "description", "type", "level", "probability", "impact",
                  "owner_id", "mitigation", "status"):
            if k in payload and payload[k] is not None:
                fields[k] = payload[k]
        if payload.get("status") in ("resolved", "已解决") and not row["resolved_at"]:
            fields["resolved_at"] = _now()
        if fields:
            sets = ", ".join(f"{k} = ?" for k in fields)
            conn.execute(f"UPDATE pc_risk SET {sets} WHERE id = ?", list(fields.values()) + [risk_id])
            conn.execute("UPDATE pc_project SET updated_at = ? WHERE id = ?", (_now(), row["project_id"]))
        return dict(conn.execute("SELECT * FROM pc_risk WHERE id = ?", (risk_id,)).fetchone())


def add_objective(project_id, payload):
    oid = _id("obj")
    now = _now()
    with get_db() as conn:
        conn.execute(
            """INSERT INTO pc_objective (id, project_id, title, description, status, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                oid, project_id, payload["title"].strip(), payload.get("description") or "",
                payload.get("status") or "not_started", now, now,
            ),
        )
    with get_db() as conn:
        obj = dict(conn.execute("SELECT * FROM pc_objective WHERE id = ?", (oid,)).fetchone())
        obj["krs"] = []
        return obj


def add_kr(objective_id, payload):
    kid = _id("kr")
    with get_db() as conn:
        conn.execute(
            """INSERT INTO pc_kr (id, objective_id, name, target_value, current_value, unit, status)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                kid, objective_id, payload["name"].strip(), payload.get("target_value") or "",
                payload.get("current_value") or "", payload.get("unit") or "",
                payload.get("status") or "not_started",
            ),
        )
        return dict(conn.execute("SELECT * FROM pc_kr WHERE id = ?", (kid,)).fetchone())


def add_relation(payload):
    rid = _id("rel")
    with get_db() as conn:
        conn.execute(
            """INSERT INTO pc_relation
               (id, source_project_id, target_project_id, relation_type, description, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                rid, payload["source_project_id"], payload["target_project_id"],
                payload.get("relation_type") or "关联", payload.get("description") or "", _now(),
            ),
        )
        return dict(conn.execute("SELECT * FROM pc_relation WHERE id = ?", (rid,)).fetchone())


def delete_relation(relation_id):
    with get_db() as conn:
        conn.execute("DELETE FROM pc_relation WHERE id = ?", (relation_id,))
    return True


def list_projects_for_snapshot():
    """团队态势采集用：非归档项目的事实快照。"""
    return list_projects({"include_archived": False})
