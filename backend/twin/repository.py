"""P2 推演 / 预测 / 制度 持久化。"""

import json
import uuid
from timeutil import now_iso

from database import get_db


def _now():
    return now_iso()


def _dumps(obj):
    return json.dumps(obj, ensure_ascii=False)


def _loads(raw, default=None):
    if raw is None or raw == "":
        return {} if default is None else default
    if isinstance(raw, (list, dict)):
        return raw
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return {} if default is None else default


POLICY_SEEDS = [
    {
        "id": "pol_newcomer",
        "category": "新人培养制度",
        "title": "新人培养制度",
        "body": "新人按阶段完成入职指南、项目熟悉、第一任务、独立任务。第3周起应能独立完成指定范围内任务。",
        "tags": ["newcomer", "independence", "stage"],
    },
    {
        "id": "pol_ai",
        "category": "AI开发规范",
        "title": "AI辅助开发规范",
        "body": "允许使用 AI 查询、方案对比和日志分析；禁止直接把 AI 结论当最终结论。关键决策必须人工确认。",
        "tags": ["ai", "review", "decision"],
    },
    {
        "id": "pol_ai_week12",
        "category": "AI开发规范",
        "title": "新人前两周任务确认规则",
        "body": "新人前两周所有任务必须导师确认后才能提交。",
        "tags": ["newcomer", "mentor_confirm", "week1-2"],
    },
    {
        "id": "pol_project",
        "category": "项目管理规范",
        "title": "项目管理规范",
        "body": "项目须有负责人、阶段、开放风险清单。重大风险须在发现当天向上同步。",
        "tags": ["project", "risk", "owner"],
    },
    {
        "id": "pol_report",
        "category": "汇报规范",
        "title": "向上汇报规范",
        "body": "汇报只写已核验事实：背景、当前状态、关键事实、风险、判断、待决策事项。禁止虚构。",
        "tags": ["report", "facts"],
    },
    {
        "id": "pol_comm",
        "category": "问题沟通规范",
        "title": "问题定义与沟通规范",
        "body": "提问须包含背景、实际表现、预期、已尝试方案和明确请求，区分事实与判断。",
        "tags": ["communication", "problem_definition"],
    },
    {
        "id": "pol_promo",
        "category": "晋升标准",
        "title": "管理岗位晋升标准",
        "body": "晋升观察需验证项目负责、技术决策、带人周期、向上协同和至少一次制度沉淀。",
        "tags": ["promotion", "mentoring", "institution"],
    },
    {
        "id": "pol_role",
        "category": "角色能力标准",
        "title": "角色能力标准",
        "body": "各角色按 L1–L4 及管理级标准评价，能力分值只能由事件证据计算，不可手改。",
        "tags": ["role", "evidence"],
    },
]


def init_tables():
    with get_db() as conn:
        c = conn.cursor()
        c.execute("""
            CREATE TABLE IF NOT EXISTS twin_simulation (
                id           TEXT PRIMARY KEY,
                scenario     TEXT NOT NULL,
                title        TEXT,
                input_json   TEXT,
                result_json  TEXT,
                created_at   TEXT
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS twin_prediction (
                id              TEXT PRIMARY KEY,
                kind            TEXT NOT NULL,
                person_id       TEXT,
                horizon_days    INTEGER,
                predicted_json  TEXT,
                actual_json     TEXT,
                error_pct       REAL,
                simulation_id   TEXT,
                created_at      TEXT
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS twin_training_plan (
                id          TEXT PRIMARY KEY,
                person_id   TEXT,
                mentor_id   TEXT,
                role_id     TEXT,
                from_level  TEXT,
                to_level    TEXT,
                days        INTEGER,
                plan_json   TEXT,
                status      TEXT DEFAULT 'draft',
                created_at  TEXT
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS twin_policy (
                id          TEXT PRIMARY KEY,
                category    TEXT,
                title       TEXT NOT NULL,
                body        TEXT,
                tags_json   TEXT,
                status      TEXT DEFAULT 'active',
                created_at  TEXT,
                updated_at  TEXT
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS twin_policy_outcome (
                id           TEXT PRIMARY KEY,
                policy_id    TEXT NOT NULL,
                metric       TEXT,
                before_value REAL,
                after_value  REAL,
                note         TEXT,
                created_at   TEXT
            )
        """)
        n = c.execute("SELECT COUNT(*) AS cnt FROM twin_policy").fetchone()["cnt"]
        if n == 0:
            now = _now()
            for p in POLICY_SEEDS:
                c.execute(
                    """INSERT INTO twin_policy
                       (id, category, title, body, tags_json, status, created_at, updated_at)
                       VALUES (?, ?, ?, ?, ?, 'active', ?, ?)""",
                    (p["id"], p["category"], p["title"], p["body"], _dumps(p["tags"]), now, now),
                )


def save_simulation(scenario, title, payload, result):
    sid = f"sim_{uuid.uuid4().hex[:12]}"
    with get_db() as conn:
        conn.execute(
            """INSERT INTO twin_simulation (id, scenario, title, input_json, result_json, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (sid, scenario, title, _dumps(payload), _dumps(result), _now()),
        )
    return sid


def get_simulation(sid):
    with get_db() as conn:
        row = conn.execute("SELECT * FROM twin_simulation WHERE id = ?", (sid,)).fetchone()
        if not row:
            return None
        item = dict(row)
        item["input"] = _loads(item.pop("input_json"), default={})
        item["result"] = _loads(item.pop("result_json"), default={})
        return item


def list_simulations(limit=40):
    with get_db() as conn:
        rows = conn.execute(
            "SELECT id, scenario, title, created_at FROM twin_simulation ORDER BY created_at DESC LIMIT ?",
            (int(limit),),
        ).fetchall()
        return [dict(r) for r in rows]


def save_prediction(kind, person_id, horizon_days, predicted, simulation_id=None):
    pid = f"pred_{uuid.uuid4().hex[:12]}"
    with get_db() as conn:
        conn.execute(
            """INSERT INTO twin_prediction
               (id, kind, person_id, horizon_days, predicted_json, simulation_id, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (pid, kind, person_id, horizon_days, _dumps(predicted), simulation_id, _now()),
        )
    return pid


def get_prediction(pid):
    with get_db() as conn:
        row = conn.execute("SELECT * FROM twin_prediction WHERE id = ?", (pid,)).fetchone()
        if not row:
            return None
        item = dict(row)
        item["predicted"] = _loads(item.pop("predicted_json"), default={})
        item["actual"] = _loads(item.pop("actual_json"), default=None)
        return item


def list_predictions(person_id=None, kind=None, limit=40):
    query = "SELECT * FROM twin_prediction WHERE 1=1"
    params = []
    if person_id:
        query += " AND person_id = ?"
        params.append(person_id)
    if kind:
        query += " AND kind = ?"
        params.append(kind)
    query += " ORDER BY created_at DESC LIMIT ?"
    params.append(int(limit))
    with get_db() as conn:
        out = []
        for r in conn.execute(query, params).fetchall():
            item = dict(r)
            item["predicted"] = _loads(item.pop("predicted_json"), default={})
            item["actual"] = _loads(item.pop("actual_json"), default=None)
            out.append(item)
        return out


def record_actual(prediction_id, actual):
    pred = get_prediction(prediction_id)
    if not pred:
        return None
    predicted = pred.get("predicted") or {}
    error = _error_pct(predicted, actual)
    with get_db() as conn:
        conn.execute(
            "UPDATE twin_prediction SET actual_json = ?, error_pct = ? WHERE id = ?",
            (_dumps(actual), error, prediction_id),
        )
    return get_prediction(prediction_id)


def _error_pct(predicted, actual):
    keys = ["days_to_target", "readiness", "score", "days"]
    for k in keys:
        pv = predicted.get(k)
        av = (actual or {}).get(k)
        if pv is None or av is None:
            continue
        try:
            pv, av = float(pv), float(av)
        except (TypeError, ValueError):
            continue
        if pv == 0:
            continue
        return round(abs(pv - av) / abs(pv) * 100, 1)
    return None


def save_plan(person_id, mentor_id, role_id, from_level, to_level, days, plan):
    pid = f"plan_{uuid.uuid4().hex[:12]}"
    with get_db() as conn:
        conn.execute(
            """INSERT INTO twin_training_plan
               (id, person_id, mentor_id, role_id, from_level, to_level, days, plan_json, status, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'draft', ?)""",
            (pid, person_id, mentor_id, role_id, from_level, to_level, days, _dumps(plan), _now()),
        )
    return pid


def list_plans(person_id=None, limit=20):
    query = "SELECT * FROM twin_training_plan WHERE 1=1"
    params = []
    if person_id:
        query += " AND person_id = ?"
        params.append(person_id)
    query += " ORDER BY created_at DESC LIMIT ?"
    params.append(int(limit))
    with get_db() as conn:
        out = []
        for r in conn.execute(query, params).fetchall():
            item = dict(r)
            item["plan"] = _loads(item.pop("plan_json"), default={})
            out.append(item)
        return out


def list_policies(status=None):
    query = "SELECT * FROM twin_policy WHERE 1=1"
    params = []
    if status:
        query += " AND status = ?"
        params.append(status)
    query += " ORDER BY created_at ASC"
    with get_db() as conn:
        out = []
        for r in conn.execute(query, params).fetchall():
            item = dict(r)
            item["tags"] = _loads(item.pop("tags_json"), default=[])
            out.append(item)
        return out


def get_policy(pid):
    with get_db() as conn:
        row = conn.execute("SELECT * FROM twin_policy WHERE id = ?", (pid,)).fetchone()
        if not row:
            return None
        item = dict(row)
        item["tags"] = _loads(item.pop("tags_json"), default=[])
        return item


def upsert_policy(payload):
    pid = payload.get("id") or f"pol_{uuid.uuid4().hex[:10]}"
    now = _now()
    existing = get_policy(pid)
    with get_db() as conn:
        if existing:
            conn.execute(
                """UPDATE twin_policy
                   SET category=?, title=?, body=?, tags_json=?, status=?, updated_at=?
                   WHERE id=?""",
                (
                    payload.get("category") or existing["category"],
                    payload.get("title") or existing["title"],
                    payload.get("body") if payload.get("body") is not None else existing["body"],
                    _dumps(payload.get("tags") if payload.get("tags") is not None else existing.get("tags") or []),
                    payload.get("status") or existing["status"],
                    now,
                    pid,
                ),
            )
        else:
            conn.execute(
                """INSERT INTO twin_policy
                   (id, category, title, body, tags_json, status, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    pid,
                    payload.get("category") or "其他",
                    payload.get("title") or "未命名制度",
                    payload.get("body") or "",
                    _dumps(payload.get("tags") or []),
                    payload.get("status") or "draft",
                    now,
                    now,
                ),
            )
    return get_policy(pid)


def add_policy_outcome(policy_id, metric, before_value, after_value, note=""):
    oid = f"po_{uuid.uuid4().hex[:10]}"
    with get_db() as conn:
        conn.execute(
            """INSERT INTO twin_policy_outcome
               (id, policy_id, metric, before_value, after_value, note, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (oid, policy_id, metric, before_value, after_value, note, _now()),
        )
    return oid


def list_policy_outcomes(policy_id=None):
    query = "SELECT * FROM twin_policy_outcome WHERE 1=1"
    params = []
    if policy_id:
        query += " AND policy_id = ?"
        params.append(policy_id)
    query += " ORDER BY created_at DESC"
    with get_db() as conn:
        return [dict(r) for r in conn.execute(query, params).fetchall()]
