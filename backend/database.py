"""
数据库层 —— 基于 SQLite + 事件溯源模式

核心设计：
- 事件 (team_events) 是不可变事实，只增不删
- 关系日志 (relationship_logs) 和情绪快照 (member_state_logs) 均以增量形式绑定到事件
- 当前关系状态 = 对所有历史事件的增量重放求和（支持时间穿梭）
- trust（信任）和 sentiment（情绪）分离为双维度：信任衰减慢，情绪衰减快
"""

import sqlite3
import json
import os
from datetime import datetime
from contextlib import contextmanager

DB_PATH = os.path.join(os.path.dirname(__file__), "team_twin.db")


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def get_db():
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    """初始化数据库表结构并填充初始人设数据"""
    with get_db() as conn:
        c = conn.cursor()

        # 1. 团队成员表
        c.execute("""
            CREATE TABLE IF NOT EXISTS team_members (
                id          TEXT PRIMARY KEY,
                name        TEXT NOT NULL,
                role        TEXT NOT NULL,
                persona     TEXT NOT NULL,
                decision_style TEXT,
                weaknesses  TEXT,
                created_at  TEXT DEFAULT (datetime('now'))
            )
        """)

        # 2. 事件记录表（不可变事实）
        c.execute("""
            CREATE TABLE IF NOT EXISTS team_events (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                event_time      TEXT NOT NULL,
                involved_members TEXT NOT NULL,   -- JSON 数组
                raw_summary     TEXT NOT NULL,
                scene           TEXT,
                parsed_task     TEXT,             -- 事务影响
                is_hypothetical INTEGER DEFAULT 0, -- 1=假设性事件（时间穿梭推演）
                confidence      REAL DEFAULT 0.8,
                created_at      TEXT DEFAULT (datetime('now'))
            )
        """)

        # 3. 关系增量日志（绑定事件，记录 trust + sentiment 双维度增量）
        c.execute("""
            CREATE TABLE IF NOT EXISTS relationship_logs (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id        INTEGER NOT NULL REFERENCES team_events(id) ON DELETE CASCADE,
                from_member_id  TEXT NOT NULL,
                to_member_id    TEXT NOT NULL,
                trust_delta     INTEGER DEFAULT 0,   -- 信任度变化 (-20~+20)
                sentiment_delta INTEGER DEFAULT 0,    -- 情绪变化 (-20~+20)
                tag             TEXT,                 -- 关系标签
                created_at      TEXT DEFAULT (datetime('now'))
            )
        """)

        # 4. 成员情绪快照表
        c.execute("""
            CREATE TABLE IF NOT EXISTS member_state_logs (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id    INTEGER NOT NULL REFERENCES team_events(id) ON DELETE CASCADE,
                member_id   TEXT NOT NULL,
                emotion     TEXT NOT NULL,
                intensity   INTEGER DEFAULT 5,  -- 1~10
                created_at  TEXT DEFAULT (datetime('now'))
            )
        """)

        # 5. 对话历史表
        c.execute("""
            CREATE TABLE IF NOT EXISTS chat_history (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                mode        TEXT NOT NULL,   -- 'query' | 'simulate'
                user_input  TEXT NOT NULL,
                ai_response TEXT NOT NULL,
                created_at  TEXT DEFAULT (datetime('now'))
            )
        """)

        # 创建索引
        c.execute("CREATE INDEX IF NOT EXISTS idx_events_time ON team_events(event_time)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_rel_event ON relationship_logs(event_id)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_state_event ON member_state_logs(event_id)")

        # 填充初始人设（如果为空）
        c.execute("SELECT COUNT(*) as cnt FROM team_members")
        if c.fetchone()["cnt"] == 0:
            seed_members(c)

        # 填充示例事件（如果为空）
        c.execute("SELECT COUNT(*) as cnt FROM team_events")
        if c.fetchone()["cnt"] == 0:
            seed_sample_events(c)


def seed_members(c):
    """初始化 3 位团队成员的人设"""
    members = [
        {
            "id": "user_a",
            "name": "张三",
            "role": "产品负责人",
            "persona": "急躁、强目标导向、容易情绪化但来得快去得快。重用户价值轻技术成本，习惯用数据说话但也会凭直觉拍板。",
            "decision_style": "激进、直觉驱动、用户价值优先",
            "weaknesses": "被质疑'不懂技术'时会防御性反弹；对排期妥协后内心记账，容易翻旧账",
        },
        {
            "id": "user_b",
            "name": "李四",
            "role": "技术负责人",
            "persona": "冷静、逻辑至上、情绪内敛但会'默默扣分'。反感拍脑袋决定，追求工程质量和可维护性。",
            "decision_style": "保守、数据导向、工程质量优先",
            "weaknesses": "长期承压后进入'消极执行'模式——不反对但也不主动；对反复变更需求容忍度极低",
        },
        {
            "id": "user_c",
            "name": "王五",
            "role": "运营/增长",
            "persona": "圆滑务实、擅长察言观色、天然的团队润滑剂。习惯找'大家都能接受'的方案，重视团队和谐。",
            "decision_style": "折中、关系导向、平衡各方利益",
            "weaknesses": "为维持和谐可能隐藏真实意见，积压后在关键节点突然倒向一方",
        },
    ]
    for m in members:
        c.execute(
            """INSERT INTO team_members (id, name, role, persona, decision_style, weaknesses)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (m["id"], m["name"], m["role"], m["persona"], m["decision_style"], m["weaknesses"]),
        )


def seed_sample_events(c):
    """填充几条示例事件，让系统开箱即用"""
    from event_processor import build_sample_parsed  # 延迟导入避免循环

    samples = [
        {
            "event_time": "2026-08-04T10:00:00",
            "involved_members": ["user_a", "user_b"],
            "raw_summary": "张三和李四就新功能排期开会。张三希望一周内上线，李四认为技术方案需要两周。双方激烈争论，最终张三妥协，同意延长到十天。",
            "scene": "排期会议",
            "parsed": {
                "task": "新功能排期确定为十天，比张三预期多三天",
                "emotions": [
                    {"member_id": "user_a", "emotion": "压抑/让步", "intensity": 6},
                    {"member_id": "user_b", "emotion": "强势/坚持", "intensity": 7},
                ],
                "relations": [
                    {"from": "user_a", "to": "user_b", "trust_delta": -8, "sentiment_delta": -6, "tag": "排期分歧/内心记账"},
                    {"from": "user_b", "to": "user_a", "trust_delta": 0, "sentiment_delta": -2, "tag": "赢了争论但察觉对方不满"},
                ],
            },
            "confidence": 0.85,
        },
        {
            "event_time": "2026-08-06T15:00:00",
            "involved_members": ["user_b", "user_c"],
            "raw_summary": "李四和王五一起喝咖啡，聊到最近项目压力大。王五安慰李四，表示理解技术团队的辛苦，两人聊得很投机。",
            "scene": "非正式交流",
            "parsed": {
                "task": "无具体事务进展，属关系维护",
                "emotions": [
                    {"member_id": "user_b", "emotion": "放松/被理解", "intensity": 7},
                    {"member_id": "user_c", "emotion": "同理/积极", "intensity": 6},
                ],
                "relations": [
                    {"from": "user_b", "to": "user_c", "trust_delta": 5, "sentiment_delta": 8, "tag": "情感共鸣/信任加深"},
                    {"from": "user_c", "to": "user_b", "trust_delta": 3, "sentiment_delta": 5, "tag": "关系拉近"},
                ],
            },
            "confidence": 0.9,
        },
        {
            "event_time": "2026-08-08T14:00:00",
            "involved_members": ["user_a", "user_b", "user_c"],
            "raw_summary": "三人周会。张三提出要砍掉一个技术债重构计划，把人力转去做新功能。李四当场黑脸但没发作。王五打圆场，建议折中——先做一半新功能，保留一半重构时间。最终采纳王五方案。",
            "scene": "周会决策",
            "parsed": {
                "task": "技术债重构计划缩减为50%，新功能并行推进",
                "emotions": [
                    {"member_id": "user_a", "emotion": "基本满意/略有遗憾", "intensity": 5},
                    {"member_id": "user_b", "emotion": "不满/隐忍", "intensity": 8},
                    {"member_id": "user_c", "emotion": "如释重负/有成就感", "intensity": 6},
                ],
                "relations": [
                    {"from": "user_b", "to": "user_a", "trust_delta": -10, "sentiment_delta": -8, "tag": "技术债被砍/严重不满"},
                    {"from": "user_a", "to": "user_c", "trust_delta": 4, "sentiment_delta": 3, "tag": "感谢打圆场"},
                    {"from": "user_b", "to": "user_c", "trust_delta": 2, "sentiment_delta": 3, "tag": "至少保住了一半"},
                ],
            },
            "confidence": 0.88,
        },
    ]

    for s in samples:
        c.execute(
            """INSERT INTO team_events (event_time, involved_members, raw_summary, scene, parsed_task, confidence)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                s["event_time"],
                json.dumps(s["involved_members"]),
                s["raw_summary"],
                s["scene"],
                s["parsed"]["task"],
                s["confidence"],
            ),
        )
        event_id = c.lastrowid

        for rel in s["parsed"]["relations"]:
            c.execute(
                """INSERT INTO relationship_logs
                   (event_id, from_member_id, to_member_id, trust_delta, sentiment_delta, tag)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (event_id, rel["from"], rel["to"], rel["trust_delta"], rel["sentiment_delta"], rel["tag"]),
            )

        for emo in s["parsed"]["emotions"]:
            c.execute(
                """INSERT INTO member_state_logs (event_id, member_id, emotion, intensity)
                   VALUES (?, ?, ?, ?)""",
                (event_id, emo["member_id"], emo["emotion"], emo.get("intensity", 5)),
            )


# ========== 数据访问函数 ==========

def get_all_members():
    with get_db() as conn:
        rows = conn.execute("SELECT * FROM team_members ORDER BY id").fetchall()
        return [dict(r) for r in rows]


def get_member(member_id):
    with get_db() as conn:
        row = conn.execute("SELECT * FROM team_members WHERE id = ?", (member_id,)).fetchone()
        return dict(row) if row else None


def get_events(date_from=None, date_to=None, member_id=None, include_hypothetical=True):
    """获取事件列表，支持按日期范围和成员过滤"""
    query = "SELECT * FROM team_events WHERE 1=1"
    params = []
    if date_from:
        query += " AND event_time >= ?"
        params.append(date_from)
    if date_to:
        query += " AND event_time <= ?"
        params.append(date_to)
    if not include_hypothetical:
        query += " AND is_hypothetical = 0"
    if member_id:
        # involved_members 是 JSON 数组，用 LIKE 简单匹配
        query += " AND involved_members LIKE ?"
        params.append(f'%"{member_id}"%')
    query += " ORDER BY event_time ASC"

    with get_db() as conn:
        rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]


def get_event_detail(event_id):
    with get_db() as conn:
        event = conn.execute("SELECT * FROM team_events WHERE id = ?", (event_id,)).fetchone()
        if not event:
            return None
        event = dict(event)
        event["involved_members"] = json.loads(event["involved_members"])

        rels = conn.execute(
            "SELECT * FROM relationship_logs WHERE event_id = ?", (event_id,)
        ).fetchall()
        event["relations"] = [dict(r) for r in rels]

        states = conn.execute(
            "SELECT * FROM member_state_logs WHERE event_id = ?", (event_id,)
        ).fetchall()
        event["emotions"] = [dict(r) for r in states]

        return event


def insert_event(event_time, involved_members, raw_summary, scene=None,
                 parsed_task=None, confidence=0.8, is_hypothetical=0):
    """插入一条事件记录，返回 event_id"""
    with get_db() as conn:
        c = conn.cursor()
        c.execute(
            """INSERT INTO team_events
               (event_time, involved_members, raw_summary, scene, parsed_task, confidence, is_hypothetical)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                event_time,
                json.dumps(involved_members),
                raw_summary,
                scene,
                parsed_task,
                confidence,
                is_hypothetical,
            ),
        )
        return c.lastrowid


def insert_relationship_log(event_id, from_id, to_id, trust_delta, sentiment_delta, tag):
    with get_db() as conn:
        conn.execute(
            """INSERT INTO relationship_logs
               (event_id, from_member_id, to_member_id, trust_delta, sentiment_delta, tag)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (event_id, from_id, to_id, trust_delta, sentiment_delta, tag),
        )


def insert_emotion_log(event_id, member_id, emotion, intensity=5):
    with get_db() as conn:
        conn.execute(
            """INSERT INTO member_state_logs (event_id, member_id, emotion, intensity)
               VALUES (?, ?, ?, ?)""",
            (event_id, member_id, emotion, intensity),
        )


def get_relationship_logs(date_to=None, include_hypothetical=True):
    """获取所有关系增量日志，用于重放计算"""
    query = """
        SELECT rl.*, te.event_time, te.is_hypothetical
        FROM relationship_logs rl
        JOIN team_events te ON rl.event_id = te.id
        WHERE 1=1
    """
    params = []
    if date_to:
        query += " AND te.event_time <= ?"
        params.append(date_to)
    if not include_hypothetical:
        query += " AND te.is_hypothetical = 0"
    query += " ORDER BY te.event_time ASC"

    with get_db() as conn:
        rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]


def get_emotion_logs(date_to=None, include_hypothetical=True):
    """获取所有情绪快照日志"""
    query = """
        SELECT ml.*, te.event_time, te.is_hypothetical
        FROM member_state_logs ml
        JOIN team_events te ON ml.event_id = te.id
        WHERE 1=1
    """
    params = []
    if date_to:
        query += " AND te.event_time <= ?"
        params.append(date_to)
    if not include_hypothetical:
        query += " AND te.is_hypothetical = 0"
    query += " ORDER BY te.event_time ASC"

    with get_db() as conn:
        rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]


def save_chat_history(mode, user_input, ai_response):
    with get_db() as conn:
        conn.execute(
            "INSERT INTO chat_history (mode, user_input, ai_response) VALUES (?, ?, ?)",
            (mode, user_input, ai_response),
        )


def get_chat_history(limit=20):
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM chat_history ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in reversed(rows)]
