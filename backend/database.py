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

        # 6. AI Native 角色模型
        c.execute("""
            CREATE TABLE IF NOT EXISTS ai_native_roles (
                id               TEXT PRIMARY KEY,
                role_code        TEXT NOT NULL UNIQUE,
                role_name        TEXT NOT NULL,
                description      TEXT,
                responsibilities TEXT,
                required_skills  TEXT,
                status           TEXT DEFAULT 'active',
                created_at       TEXT DEFAULT (datetime('now')),
                updated_at       TEXT DEFAULT (datetime('now'))
            )
        """)

        # 7. 人员角色匹配
        c.execute("""
            CREATE TABLE IF NOT EXISTS ai_role_assignments (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                role_id          TEXT NOT NULL REFERENCES ai_native_roles(id) ON DELETE CASCADE,
                employee_id      TEXT NOT NULL,
                match_score      REAL NOT NULL DEFAULT 0,
                confidence       REAL DEFAULT 0.8,
                analysis_result  TEXT,
                created_at       TEXT DEFAULT (datetime('now')),
                updated_at       TEXT DEFAULT (datetime('now')),
                UNIQUE(role_id, employee_id)
            )
        """)

        # 8. 角色竞争排名
        c.execute("""
            CREATE TABLE IF NOT EXISTS ai_role_competitions (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                role_id          TEXT NOT NULL REFERENCES ai_native_roles(id) ON DELETE CASCADE,
                employee_id      TEXT NOT NULL,
                rank             INTEGER NOT NULL,
                score            REAL NOT NULL DEFAULT 0,
                reason           TEXT,
                analysis_version TEXT,
                created_at       TEXT DEFAULT (datetime('now'))
            )
        """)

        c.execute("CREATE INDEX IF NOT EXISTS idx_ai_assign_role ON ai_role_assignments(role_id)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_ai_comp_role ON ai_role_competitions(role_id)")

        # 9. 日报主表（日期 + 成员唯一）
        c.execute("""
            CREATE TABLE IF NOT EXISTS daily_report (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                report_date  TEXT NOT NULL,
                member_id    TEXT NOT NULL,
                content      TEXT NOT NULL,
                content_hash TEXT NOT NULL,
                version      INTEGER NOT NULL DEFAULT 1,
                status       TEXT DEFAULT 'active',
                created_at   TEXT DEFAULT (datetime('now')),
                updated_at   TEXT DEFAULT (datetime('now')),
                UNIQUE(report_date, member_id)
            )
        """)

        # 10. 日报历史版本
        c.execute("""
            CREATE TABLE IF NOT EXISTS daily_report_history (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                report_id    INTEGER NOT NULL REFERENCES daily_report(id) ON DELETE CASCADE,
                old_content  TEXT,
                new_content  TEXT,
                change_type  TEXT NOT NULL,
                operator     TEXT,
                created_at   TEXT DEFAULT (datetime('now'))
            )
        """)

        # 11. 日报导入任务
        c.execute("""
            CREATE TABLE IF NOT EXISTS daily_import_task (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                file_name     TEXT,
                total_count   INTEGER DEFAULT 0,
                new_count     INTEGER DEFAULT 0,
                update_count  INTEGER DEFAULT 0,
                skip_count    INTEGER DEFAULT 0,
                error_count   INTEGER DEFAULT 0,
                status        TEXT DEFAULT 'pending',
                message       TEXT,
                result_json   TEXT,
                created_at    TEXT DEFAULT (datetime('now')),
                updated_at    TEXT DEFAULT (datetime('now'))
            )
        """)

        # 12. 日报 AI 分析
        c.execute("""
            CREATE TABLE IF NOT EXISTS daily_report_analysis (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                report_id       INTEGER NOT NULL REFERENCES daily_report(id) ON DELETE CASCADE,
                skills          TEXT,
                projects        TEXT,
                activity_type   TEXT,
                difficulty      INTEGER DEFAULT 3,
                impact_score    REAL DEFAULT 0,
                embedding_id    TEXT,
                analysis_json   TEXT,
                version         INTEGER DEFAULT 1,
                created_at      TEXT DEFAULT (datetime('now')),
                updated_at      TEXT DEFAULT (datetime('now')),
                UNIQUE(report_id)
            )
        """)

        c.execute("CREATE INDEX IF NOT EXISTS idx_daily_report_date ON daily_report(report_date)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_daily_report_member ON daily_report(member_id)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_daily_history_report ON daily_report_history(report_id)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_daily_analysis_report ON daily_report_analysis(report_id)")

        _ensure_column(c, "ai_native_roles", "evaluation_scope_type", "TEXT DEFAULT 'TEAM'")
        _ensure_column(c, "ai_native_roles", "evaluation_scope_config", "TEXT DEFAULT '{}'")
        _ensure_column(c, "ai_native_roles", "minimum_competition_level", "TEXT DEFAULT 'L2'")
        _ensure_column(c, "ai_native_roles", "minimum_match_score", "REAL DEFAULT 60")

        c.execute("""
            CREATE TABLE IF NOT EXISTS newcomers (
                id                 TEXT PRIMARY KEY,
                employee_id        TEXT NOT NULL UNIQUE,
                entry_date         TEXT NOT NULL,
                current_role       TEXT,
                current_role_id    TEXT,
                target_role_id     TEXT,
                onboarding_stage   TEXT DEFAULT 'onboarding',
                compete_in_ranking INTEGER DEFAULT 0,
                status             TEXT DEFAULT 'active',
                progress           REAL DEFAULT 0,
                created_at         TEXT DEFAULT (datetime('now')),
                updated_at         TEXT DEFAULT (datetime('now'))
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS newcomer_tasks (
                id               TEXT PRIMARY KEY,
                newcomer_id      TEXT NOT NULL REFERENCES newcomers(id) ON DELETE CASCADE,
                task_name        TEXT NOT NULL,
                task_level       TEXT NOT NULL,
                description      TEXT,
                requirements     TEXT,
                estimated_hours  REAL DEFAULT 4,
                ai_allowed       INTEGER DEFAULT 1,
                review_required  INTEGER DEFAULT 1,
                status           TEXT DEFAULT 'todo',
                due_at           TEXT,
                started_at       TEXT,
                completed_at     TEXT,
                blocked_reason   TEXT,
                help_requested   INTEGER DEFAULT 0,
                capability_ids   TEXT,
                sort_order       INTEGER DEFAULT 0,
                created_at       TEXT DEFAULT (datetime('now'))
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS capability_evidence (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                employee_id      TEXT NOT NULL,
                task_id          TEXT,
                capability_id    TEXT NOT NULL,
                capability_name  TEXT,
                evidence_type    TEXT,
                evidence_content TEXT,
                score            REAL DEFAULT 0,
                created_at       TEXT DEFAULT (datetime('now'))
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS newcomer_interventions (
                id                  TEXT PRIMARY KEY,
                newcomer_id         TEXT NOT NULL REFERENCES newcomers(id) ON DELETE CASCADE,
                level               TEXT NOT NULL,
                reason              TEXT,
                recommended_action  TEXT,
                status              TEXT DEFAULT 'open',
                created_at          TEXT DEFAULT (datetime('now')),
                resolved_at         TEXT
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS newcomer_guides (
                newcomer_id  TEXT PRIMARY KEY REFERENCES newcomers(id) ON DELETE CASCADE,
                content_json TEXT,
                status       TEXT DEFAULT 'draft',
                source       TEXT DEFAULT 'template',
                updated_at   TEXT
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS analysis_tasks (
                id             TEXT PRIMARY KEY,
                task_type      TEXT NOT NULL,
                status         TEXT DEFAULT 'pending',
                progress       INTEGER DEFAULT 0,
                current_step   TEXT,
                payload        TEXT,
                error_message  TEXT,
                started_at     TEXT,
                finished_at    TEXT
            )
        """)
        c.execute("CREATE INDEX IF NOT EXISTS idx_newcomers_employee ON newcomers(employee_id)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_nc_tasks_newcomer ON newcomer_tasks(newcomer_id)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_nc_evidence_emp ON capability_evidence(employee_id)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_nc_interv_nc ON newcomer_interventions(newcomer_id)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_analysis_type ON analysis_tasks(task_type, status)")

        c.execute("""
            CREATE TABLE IF NOT EXISTS team_situation_report (
                id                   TEXT PRIMARY KEY,
                report_date          TEXT NOT NULL,
                team_health_score    REAL,
                team_status          TEXT,
                project_score        REAL,
                member_score         REAL,
                task_score           REAL,
                collaboration_score  REAL,
                summary              TEXT,
                llm_json             TEXT,
                weights_json         TEXT,
                snapshot_json        TEXT,
                trigger              TEXT,
                created_at           TEXT
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS member_situation (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                report_id      TEXT NOT NULL,
                member_id      TEXT NOT NULL,
                workload_score REAL,
                work_focus     TEXT,
                focus_change   TEXT,
                project_count  INTEGER,
                role_change    TEXT,
                risk_level     TEXT,
                summary        TEXT,
                confidence     REAL,
                metrics_json   TEXT
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS project_situation (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                report_id        TEXT NOT NULL,
                project_id       TEXT NOT NULL,
                project_name     TEXT,
                progress         REAL,
                progress_change  REAL,
                schedule_status  TEXT,
                risk_level       TEXT,
                summary          TEXT,
                confidence       REAL,
                metrics_json     TEXT
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS situation_risk (
                id           TEXT PRIMARY KEY,
                report_id    TEXT NOT NULL,
                object_type  TEXT,
                object_id    TEXT,
                risk_type    TEXT,
                severity     TEXT,
                title        TEXT,
                description  TEXT,
                evidence     TEXT,
                confidence   REAL,
                status       TEXT DEFAULT 'open',
                created_at   TEXT
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS situation_change (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                report_id     TEXT NOT NULL,
                object_type   TEXT,
                object_id     TEXT,
                change_type   TEXT,
                before_value  TEXT,
                after_value   TEXT,
                change_score  REAL,
                description   TEXT,
                confidence    REAL,
                evidence      TEXT
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS team_context (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                context_date  TEXT NOT NULL,
                context_type  TEXT,
                content       TEXT,
                source        TEXT DEFAULT 'manual',
                creator_id    TEXT,
                created_at    TEXT
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS situation_question (
                id            TEXT PRIMARY KEY,
                report_id     TEXT,
                member_id     TEXT,
                question      TEXT,
                status        TEXT DEFAULT 'open',
                answer        TEXT,
                created_at    TEXT,
                resolved_at   TEXT
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS team_situation_job (
                id               TEXT PRIMARY KEY,
                report_date      TEXT,
                status           TEXT,
                progress         INTEGER DEFAULT 0,
                current_step     TEXT,
                idempotency_key  TEXT,
                error_message    TEXT,
                started_at       TEXT,
                finished_at      TEXT
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS team_situation_config (
                key   TEXT PRIMARY KEY,
                value TEXT
            )
        """)
        c.execute("CREATE INDEX IF NOT EXISTS idx_sit_report_date ON team_situation_report(report_date)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_sit_member_report ON member_situation(report_id)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_sit_proj_report ON project_situation(report_id)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_sit_risk_report ON situation_risk(report_id)")

        c.execute("""
            CREATE TABLE IF NOT EXISTS pc_project (
                id                 TEXT PRIMARY KEY,
                name               TEXT NOT NULL,
                description        TEXT NOT NULL,
                owner_id           TEXT NOT NULL,
                status             TEXT NOT NULL,
                type               TEXT,
                priority           TEXT,
                business           TEXT,
                tags_json          TEXT,
                start_date         TEXT,
                end_date           TEXT,
                current_stage_id   TEXT,
                created_at         TEXT,
                updated_at         TEXT,
                archived_at        TEXT
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS pc_stage (
                id                  TEXT PRIMARY KEY,
                project_id          TEXT NOT NULL,
                name                TEXT NOT NULL,
                description         TEXT,
                sort_order          INTEGER NOT NULL,
                status              TEXT NOT NULL,
                progress            REAL,
                owner_id            TEXT,
                planned_start_date  TEXT,
                planned_end_date    TEXT,
                actual_start_date   TEXT,
                actual_end_date     TEXT,
                created_at          TEXT,
                updated_at          TEXT
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS pc_objective (
                id           TEXT PRIMARY KEY,
                project_id   TEXT NOT NULL,
                title        TEXT NOT NULL,
                description  TEXT,
                status       TEXT,
                created_at   TEXT,
                updated_at   TEXT
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS pc_kr (
                id             TEXT PRIMARY KEY,
                objective_id   TEXT NOT NULL,
                name           TEXT NOT NULL,
                target_value   TEXT,
                current_value  TEXT,
                unit           TEXT,
                status         TEXT
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS pc_milestone (
                id            TEXT PRIMARY KEY,
                project_id    TEXT NOT NULL,
                stage_id      TEXT,
                name          TEXT NOT NULL,
                description   TEXT,
                owner_id      TEXT,
                planned_date  TEXT,
                actual_date   TEXT,
                status        TEXT,
                importance    TEXT
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS pc_member (
                id                   TEXT PRIMARY KEY,
                project_id           TEXT NOT NULL,
                user_id              TEXT NOT NULL,
                role                 TEXT,
                responsibility       TEXT,
                participation_level  TEXT
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS pc_risk (
                id            TEXT PRIMARY KEY,
                project_id    TEXT NOT NULL,
                title         TEXT NOT NULL,
                description   TEXT,
                type          TEXT,
                level         TEXT,
                probability   TEXT,
                impact        TEXT,
                owner_id      TEXT,
                mitigation    TEXT,
                status        TEXT,
                created_at    TEXT,
                resolved_at   TEXT
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS pc_activity (
                id            TEXT PRIMARY KEY,
                project_id    TEXT NOT NULL,
                stage_id      TEXT,
                type          TEXT,
                content       TEXT NOT NULL,
                source        TEXT,
                source_id     TEXT,
                operator_id   TEXT,
                created_at    TEXT
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS pc_relation (
                id                  TEXT PRIMARY KEY,
                source_project_id   TEXT NOT NULL,
                target_project_id   TEXT NOT NULL,
                relation_type       TEXT NOT NULL,
                description         TEXT,
                created_at          TEXT
            )
        """)
        c.execute("CREATE INDEX IF NOT EXISTS idx_pc_owner ON pc_project(owner_id)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_pc_status ON pc_project(status)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_pc_stage_proj ON pc_stage(project_id)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_pc_member_proj ON pc_member(project_id)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_pc_risk_proj ON pc_risk(project_id)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_pc_act_proj ON pc_activity(project_id)")
        c.execute("""
            UPDATE pc_project SET status = CASE
                WHEN status IN ('draft', 'planning', 'active') OR status IS NULL OR status = '' THEN 'open'
                WHEN status IN ('completed', 'archived') THEN 'closed'
                ELSE status
            END
            WHERE status NOT IN ('open', 'paused', 'closed')
        """)

        # 填充初始人设（如果为空）
        c.execute("SELECT COUNT(*) as cnt FROM team_members")
        if c.fetchone()["cnt"] == 0:
            seed_members(c)

        # 填充示例事件（如果为空）
        c.execute("SELECT COUNT(*) as cnt FROM team_events")
        if c.fetchone()["cnt"] == 0:
            seed_sample_events(c)

        # 填充 AI Native 内置角色
        c.execute("SELECT COUNT(*) as cnt FROM ai_native_roles")
        if c.fetchone()["cnt"] == 0:
            seed_ai_native_roles(c)


def _ensure_column(cursor, table, name, col_ddl):
    cols = [row[1] for row in cursor.execute(f"PRAGMA table_info({table})").fetchall()]
    if name not in cols:
        cursor.execute(f"ALTER TABLE {table} ADD COLUMN {name} {col_ddl}")


def seed_members(c):
    """已清空:不再预置 Mock 人设,成员由前端「成员管理」手动维护"""
    pass


def seed_sample_events(c):
    """已清空:不再预置 Mock 事件,事件由前端「记录团队新事件」手动录入"""
    pass


AI_NATIVE_ROLE_SEEDS = [
    {
        "id": "leader",
        "role_code": "leader",
        "role_name": "负责人",
        "description": "对团队目标、资源与最终结果负责，统筹 AI Native 组织运转",
        "responsibilities": ["目标对齐", "资源决策", "风险兜底", "组织演进"],
        "required_skills": ["战略判断", "决策力", "人才识别", "跨职能协同"],
    },
    {
        "id": "product_manager",
        "role_code": "product_manager",
        "role_name": "产品经理",
        "description": "负责业务系统设计和规则沉淀",
        "responsibilities": ["Business Rules", "Acceptance Criteria", "Gherkin", "需求结构化"],
        "required_skills": ["业务建模", "需求结构化", "验收标准设计", "Gherkin设计"],
    },
    {
        "id": "project_manager",
        "role_code": "project_manager",
        "role_name": "项目经理",
        "description": "负责交付节奏、依赖管理和风险跟踪",
        "responsibilities": ["排期管理", "依赖协调", "风险跟踪", "交付复盘"],
        "required_skills": ["计划管理", "沟通协调", "风险管理", "敏捷协作"],
    },
    {
        "id": "architect",
        "role_code": "architect",
        "role_name": "架构师",
        "description": "负责系统架构治理、技术边界与演进路径",
        "responsibilities": ["架构设计", "技术选型", "边界治理", "质量基线"],
        "required_skills": ["系统设计", "技术深度", "可扩展性", "架构治理"],
    },
    {
        "id": "developer",
        "role_code": "developer",
        "role_name": "开发工程师",
        "description": "负责功能实现、代码质量与工程交付",
        "responsibilities": ["功能开发", "代码评审", "工程实践", "技术债治理"],
        "required_skills": ["编码实现", "调试排障", "工程规范", "AI辅助开发"],
    },
    {
        "id": "tester",
        "role_code": "tester",
        "role_name": "测试工程师",
        "description": "负责质量策略、验收验证与风险发现",
        "responsibilities": ["测试策略", "用例设计", "回归验证", "质量度量"],
        "required_skills": ["测试设计", "自动化测试", "缺陷分析", "质量门禁"],
    },
    {
        "id": "ui_designer",
        "role_code": "ui_designer",
        "role_name": "UI设计师",
        "description": "负责交互体验与界面表达一致性",
        "responsibilities": ["交互设计", "视觉规范", "原型产出", "体验走查"],
        "required_skills": ["交互设计", "视觉设计", "设计系统", "用户体验"],
    },
    {
        "id": "business_owner",
        "role_code": "business_owner",
        "role_name": "业务负责人",
        "description": "代表业务侧定义价值优先级与验收口径",
        "responsibilities": ["业务优先级", "价值定义", "验收拍板", "业务反馈"],
        "required_skills": ["业务洞察", "优先级判断", "利益相关者管理", "价值评估"],
    },
    {
        "id": "context_owner",
        "role_code": "context_owner",
        "role_name": "AI Context Owner",
        "description": "负责团队知识资产、提示词与 AI 上下文质量治理",
        "responsibilities": ["知识沉淀", "Context 治理", "提示词规范", "AI 协作流程"],
        "required_skills": ["知识工程", "Prompt 设计", "上下文管理", "AI 工作流"],
    },
]


def seed_ai_native_roles(c):
    """预置 AI Native 内置角色模型"""
    now = datetime.now().isoformat(timespec="seconds")
    for role in AI_NATIVE_ROLE_SEEDS:
        c.execute(
            """INSERT INTO ai_native_roles
               (id, role_code, role_name, description, responsibilities, required_skills, status, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, 'active', ?, ?)""",
            (
                role["id"],
                role["role_code"],
                role["role_name"],
                role["description"],
                json.dumps(role["responsibilities"], ensure_ascii=False),
                json.dumps(role["required_skills"], ensure_ascii=False),
                now,
                now,
            ),
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


def create_member(member_id, name, role, persona, decision_style=None, weaknesses=None):
    """新增成员。id 重复时抛出 ValueError"""
    with get_db() as conn:
        exists = conn.execute("SELECT 1 FROM team_members WHERE id = ?", (member_id,)).fetchone()
        if exists:
            raise ValueError(f"成员ID已存在: {member_id}")
        conn.execute(
            """INSERT INTO team_members (id, name, role, persona, decision_style, weaknesses)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (member_id, name, role, persona, decision_style, weaknesses),
        )
    return get_member(member_id)


def update_member(member_id, name=None, role=None, persona=None,
                  decision_style=None, weaknesses=None):
    """更新成员字段,仅更新非 None 的字段。成员不存在抛出 ValueError"""
    with get_db() as conn:
        exists = conn.execute("SELECT 1 FROM team_members WHERE id = ?", (member_id,)).fetchone()
        if not exists:
            raise ValueError(f"成员不存在: {member_id}")
        fields = []
        params = []
        for col, val in [("name", name), ("role", role), ("persona", persona),
                         ("decision_style", decision_style), ("weaknesses", weaknesses)]:
            if val is not None:
                fields.append(f"{col} = ?")
                params.append(val)
        if fields:
            params.append(member_id)
            conn.execute(f"UPDATE team_members SET {', '.join(fields)} WHERE id = ?", params)
    return get_member(member_id)


def delete_member(member_id):
    """删除成员。返回关联事件数(供前端提示)。成员不存在抛出 ValueError。
    注意:历史事件中的 involved_members 是 JSON 文组,不会级联删除,保留为历史事实。"""
    with get_db() as conn:
        exists = conn.execute("SELECT 1 FROM team_members WHERE id = ?", (member_id,)).fetchone()
        if not exists:
            raise ValueError(f"成员不存在: {member_id}")
        # 统计关联事件数(用于前端提示)
        event_count = conn.execute(
            "SELECT COUNT(*) as cnt FROM team_events WHERE involved_members LIKE ?",
            (f'%"{member_id}"%',),
        ).fetchone()["cnt"]
        conn.execute("DELETE FROM team_members WHERE id = ?", (member_id,))
    return event_count


def get_events(date_from=None, date_to=None, member_id=None, include_hypothetical=True):
    """获取事件列表，支持按日期范围和成员过滤

    date_from / date_to 支持：
    - 纯日期 YYYY-MM-DD（按整天包含，兼容 event_time 中空格或 T 分隔）
    - 完整时间字符串（按字典序比较）
    """
    query = "SELECT * FROM team_events WHERE 1=1"
    params = []
    if date_from:
        # 纯日期：下界取当天 00:00，兼容 "YYYY-MM-DD" / "YYYY-MM-DDTHH:MM" / 空格格式
        bound = f"{date_from}T00:00:00" if len(date_from) == 10 else date_from
        query += " AND replace(event_time, ' ', 'T') >= replace(?, ' ', 'T')"
        params.append(bound)
    if date_to:
        if len(date_to) == 10:
            bound = f"{date_to}T23:59:59"
        else:
            bound = date_to
        query += " AND replace(event_time, ' ', 'T') <= replace(?, ' ', 'T')"
        params.append(bound)
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


def delete_relationship_logs_by_event(event_id):
    """删除指定事件的所有关系日志"""
    with get_db() as conn:
        conn.execute("DELETE FROM relationship_logs WHERE event_id = ?", (event_id,))


def delete_emotion_logs_by_event(event_id):
    """删除指定事件的所有情绪日志"""
    with get_db() as conn:
        conn.execute("DELETE FROM member_state_logs WHERE event_id = ?", (event_id,))


def update_event_parsed(event_id, parsed_task=None, scene=None, confidence=None):
    """更新事件的解析结果字段"""
    fields = []
    params = []
    if parsed_task is not None:
        fields.append("parsed_task = ?")
        params.append(parsed_task)
    if scene is not None:
        fields.append("scene = ?")
        params.append(scene)
    if confidence is not None:
        fields.append("confidence = ?")
        params.append(confidence)
    if fields:
        params.append(event_id)
        with get_db() as conn:
            conn.execute(f"UPDATE team_events SET {', '.join(fields)} WHERE id = ?", params)


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


# ========== AI Native 数据访问 ==========

def _parse_json_list(raw, default=None):
    if not raw:
        return default if default is not None else []
    if isinstance(raw, list):
        return raw
    try:
        data = json.loads(raw)
        return data if isinstance(data, list) else (default if default is not None else [])
    except (json.JSONDecodeError, TypeError):
        return default if default is not None else []


def _parse_json_obj(raw, default=None):
    if not raw:
        return default if default is not None else {}
    if isinstance(raw, dict):
        return raw
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else (default if default is not None else {})
    except (json.JSONDecodeError, TypeError):
        return default if default is not None else {}


def get_ai_native_roles(active_only=True):
    query = "SELECT * FROM ai_native_roles"
    if active_only:
        query += " WHERE status = 'active'"
    query += " ORDER BY created_at ASC, id ASC"
    with get_db() as conn:
        rows = conn.execute(query).fetchall()
        result = []
        for r in rows:
            item = dict(r)
            result.append(_hydrate_ai_role(item))
        # 按内置角色顺序展示
        order = {r["id"]: i for i, r in enumerate(AI_NATIVE_ROLE_SEEDS)}
        result.sort(key=lambda x: order.get(x["id"], 999))
        return result


def get_ai_native_role(role_id):
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM ai_native_roles WHERE id = ?", (role_id,)
        ).fetchone()
        if not row:
            return None
        return _hydrate_ai_role(dict(row))


def _hydrate_ai_role(item):
    item["responsibilities"] = _parse_json_list(item.get("responsibilities"))
    item["required_skills"] = _parse_json_list(item.get("required_skills"))
    item["evaluation_scope_type"] = (item.get("evaluation_scope_type") or "TEAM").upper()
    item["evaluation_scope_config"] = _parse_json_obj(item.get("evaluation_scope_config"))
    item["minimum_competition_level"] = item.get("minimum_competition_level") or "L2"
    item["minimum_match_score"] = float(item.get("minimum_match_score") or 60)
    return item


def update_ai_native_evaluation_scope(role_id, scope_type, config=None,
                                      minimum_competition_level=None,
                                      minimum_match_score=None):
    now = datetime.now().isoformat(timespec="seconds")
    fields = ["evaluation_scope_type = ?", "evaluation_scope_config = ?", "updated_at = ?"]
    params = [
        (scope_type or "TEAM").upper(),
        json.dumps(config or {}, ensure_ascii=False),
        now,
    ]
    if minimum_competition_level is not None:
        fields.append("minimum_competition_level = ?")
        params.append(minimum_competition_level)
    if minimum_match_score is not None:
        fields.append("minimum_match_score = ?")
        params.append(float(minimum_match_score))
    params.append(role_id)
    with get_db() as conn:
        conn.execute(
            f"UPDATE ai_native_roles SET {', '.join(fields)} WHERE id = ?",
            params,
        )
    return get_ai_native_role(role_id)


def get_ai_role_assignments(role_id=None):
    query = "SELECT * FROM ai_role_assignments WHERE 1=1"
    params = []
    if role_id:
        query += " AND role_id = ?"
        params.append(role_id)
    query += " ORDER BY match_score DESC"
    with get_db() as conn:
        rows = conn.execute(query, params).fetchall()
        result = []
        for r in rows:
            item = dict(r)
            item["analysis_result"] = _parse_json_obj(item.get("analysis_result"))
            result.append(item)
        return result


def get_ai_role_competitions(role_id=None, limit_per_role=None):
    query = "SELECT * FROM ai_role_competitions WHERE 1=1"
    params = []
    if role_id:
        query += " AND role_id = ?"
        params.append(role_id)
    query += " ORDER BY role_id ASC, rank ASC"
    with get_db() as conn:
        rows = conn.execute(query, params).fetchall()
        items = [dict(r) for r in rows]
    if limit_per_role is None:
        return items
    # 每个角色只保留前 N 名
    grouped = {}
    for item in items:
        rid = item["role_id"]
        grouped.setdefault(rid, [])
        if len(grouped[rid]) < limit_per_role:
            grouped[rid].append(item)
    result = []
    for rid in grouped:
        result.extend(grouped[rid])
    return result


def clear_ai_role_analysis():
    """清空匹配与竞争结果，准备写入新一轮分析"""
    with get_db() as conn:
        conn.execute("DELETE FROM ai_role_competitions")
        conn.execute("DELETE FROM ai_role_assignments")


def upsert_ai_role_assignment(role_id, employee_id, match_score, confidence=0.8, analysis_result=None):
    now = datetime.now().isoformat(timespec="seconds")
    analysis_json = json.dumps(analysis_result or {}, ensure_ascii=False)
    with get_db() as conn:
        conn.execute(
            """INSERT INTO ai_role_assignments
               (role_id, employee_id, match_score, confidence, analysis_result, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(role_id, employee_id) DO UPDATE SET
                 match_score = excluded.match_score,
                 confidence = excluded.confidence,
                 analysis_result = excluded.analysis_result,
                 updated_at = excluded.updated_at
            """,
            (role_id, employee_id, match_score, confidence, analysis_json, now, now),
        )


def insert_ai_role_competition(role_id, employee_id, rank, score, reason=None, analysis_version=None):
    with get_db() as conn:
        conn.execute(
            """INSERT INTO ai_role_competitions
               (role_id, employee_id, rank, score, reason, analysis_version)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (role_id, employee_id, rank, score, reason, analysis_version),
        )


def replace_ai_role_analysis(assignments, competitions, analysis_version):
    """原子替换一轮分析结果

    assignments: [{role_id, employee_id, match_score, confidence, analysis_result}, ...]
    competitions: [{role_id, employee_id, rank, score, reason}, ...]
    """
    now = datetime.now().isoformat(timespec="seconds")
    with get_db() as conn:
        conn.execute("DELETE FROM ai_role_competitions")
        conn.execute("DELETE FROM ai_role_assignments")
        for a in assignments:
            conn.execute(
                """INSERT INTO ai_role_assignments
                   (role_id, employee_id, match_score, confidence, analysis_result, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    a["role_id"],
                    a["employee_id"],
                    a["match_score"],
                    a.get("confidence", 0.8),
                    json.dumps(a.get("analysis_result") or {}, ensure_ascii=False),
                    now,
                    now,
                ),
            )
        for c in competitions:
            conn.execute(
                """INSERT INTO ai_role_competitions
                   (role_id, employee_id, rank, score, reason, analysis_version)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    c["role_id"],
                    c["employee_id"],
                    c["rank"],
                    c["score"],
                    c.get("reason"),
                    analysis_version,
                ),
            )


# ========== 日报数据访问 ==========

def get_daily_reports(date_from=None, date_to=None, member_id=None, project=None, skill=None, limit=200):
    query = """
        SELECT dr.*, dra.skills, dra.projects, dra.activity_type, dra.difficulty,
               dra.impact_score, dra.analysis_json
        FROM daily_report dr
        LEFT JOIN daily_report_analysis dra ON dra.report_id = dr.id
        WHERE 1=1
    """
    params = []
    if date_from:
        query += " AND dr.report_date >= ?"
        params.append(date_from)
    if date_to:
        query += " AND dr.report_date <= ?"
        params.append(date_to)
    if member_id:
        query += " AND dr.member_id = ?"
        params.append(member_id)
    if project:
        query += " AND (dra.projects LIKE ? OR dr.content LIKE ?)"
        params.extend([f"%{project}%", f"%{project}%"])
    if skill:
        query += " AND (dra.skills LIKE ? OR dr.content LIKE ?)"
        params.extend([f"%{skill}%", f"%{skill}%"])
    query += " ORDER BY dr.report_date DESC, dr.member_id ASC LIMIT ?"
    params.append(limit)

    with get_db() as conn:
        rows = conn.execute(query, params).fetchall()
        result = []
        for r in rows:
            item = dict(r)
            item["skills"] = _parse_json_list(item.get("skills"))
            item["projects"] = _parse_json_list(item.get("projects"))
            item["analysis_json"] = _parse_json_obj(item.get("analysis_json"))
            result.append(item)
        return result


def get_daily_reports_by_dates(dates):
    """批量按日期查询，返回 dict: f'{date}_{member_id}' -> row"""
    if not dates:
        return {}
    placeholders = ",".join("?" for _ in dates)
    with get_db() as conn:
        rows = conn.execute(
            f"SELECT * FROM daily_report WHERE report_date IN ({placeholders})",
            list(dates),
        ).fetchall()
        return {f"{r['report_date']}_{r['member_id']}": dict(r) for r in rows}


def insert_daily_report(report_date, member_id, content, content_hash, status="active"):
    now = datetime.now().isoformat(timespec="seconds")
    with get_db() as conn:
        c = conn.cursor()
        c.execute(
            """INSERT INTO daily_report
               (report_date, member_id, content, content_hash, version, status, created_at, updated_at)
               VALUES (?, ?, ?, ?, 1, ?, ?, ?)""",
            (report_date, member_id, content, content_hash, status, now, now),
        )
        report_id = c.lastrowid
        c.execute(
            """INSERT INTO daily_report_history
               (report_id, old_content, new_content, change_type, operator)
               VALUES (?, NULL, ?, 'NEW', 'excel_import')""",
            (report_id, content),
        )
        return report_id


def update_daily_report(report_id, content, content_hash, old_content, operator="excel_import"):
    now = datetime.now().isoformat(timespec="seconds")
    with get_db() as conn:
        row = conn.execute("SELECT version FROM daily_report WHERE id = ?", (report_id,)).fetchone()
        version = (row["version"] if row else 1) + 1
        conn.execute(
            """UPDATE daily_report
               SET content = ?, content_hash = ?, version = ?, updated_at = ?
               WHERE id = ?""",
            (content, content_hash, version, now, report_id),
        )
        conn.execute(
            """INSERT INTO daily_report_history
               (report_id, old_content, new_content, change_type, operator)
               VALUES (?, ?, ?, 'UPDATED', ?)""",
            (report_id, old_content, content, operator),
        )
        return version


def get_daily_report_history(report_id):
    with get_db() as conn:
        rows = conn.execute(
            """SELECT * FROM daily_report_history
               WHERE report_id = ? ORDER BY created_at DESC""",
            (report_id,),
        ).fetchall()
        return [dict(r) for r in rows]


def create_daily_import_task(file_name):
    now = datetime.now().isoformat(timespec="seconds")
    with get_db() as conn:
        c = conn.cursor()
        c.execute(
            """INSERT INTO daily_import_task
               (file_name, status, created_at, updated_at)
               VALUES (?, 'processing', ?, ?)""",
            (file_name, now, now),
        )
        return c.lastrowid


def update_daily_import_task(task_id, **fields):
    if not fields:
        return
    fields = dict(fields)
    fields["updated_at"] = datetime.now().isoformat(timespec="seconds")
    if "result_json" in fields and not isinstance(fields["result_json"], str):
        fields["result_json"] = json.dumps(fields["result_json"], ensure_ascii=False)
    cols = ", ".join(f"{k} = ?" for k in fields)
    params = list(fields.values()) + [task_id]
    with get_db() as conn:
        conn.execute(f"UPDATE daily_import_task SET {cols} WHERE id = ?", params)


def get_daily_import_task(task_id):
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM daily_import_task WHERE id = ?", (task_id,)
        ).fetchone()
        if not row:
            return None
        item = dict(row)
        item["result_json"] = _parse_json_obj(item.get("result_json"))
        return item


def list_daily_import_tasks(limit=20):
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM daily_import_task ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        result = []
        for r in rows:
            item = dict(r)
            item["result_json"] = _parse_json_obj(item.get("result_json"))
            result.append(item)
        return result


def upsert_daily_report_analysis(report_id, skills, projects, activity_type,
                                 difficulty=3, impact_score=0, analysis_json=None, version=1):
    now = datetime.now().isoformat(timespec="seconds")
    with get_db() as conn:
        conn.execute(
            """INSERT INTO daily_report_analysis
               (report_id, skills, projects, activity_type, difficulty, impact_score,
                analysis_json, version, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(report_id) DO UPDATE SET
                 skills = excluded.skills,
                 projects = excluded.projects,
                 activity_type = excluded.activity_type,
                 difficulty = excluded.difficulty,
                 impact_score = excluded.impact_score,
                 analysis_json = excluded.analysis_json,
                 version = excluded.version,
                 updated_at = excluded.updated_at
            """,
            (
                report_id,
                json.dumps(skills or [], ensure_ascii=False),
                json.dumps(projects or [], ensure_ascii=False),
                activity_type,
                difficulty,
                impact_score,
                json.dumps(analysis_json or {}, ensure_ascii=False),
                version,
                now,
                now,
            ),
        )


def get_member_report_statistics(days=30):
    """人员投入聚合：member -> {project: days_count}"""
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT dr.member_id, dra.projects, COUNT(*) as cnt
            FROM daily_report dr
            LEFT JOIN daily_report_analysis dra ON dra.report_id = dr.id
            WHERE dr.report_date >= date('now', ?)
            GROUP BY dr.member_id, dra.projects
            """,
            (f"-{int(days)} days",),
        ).fetchall()

    stats = {}
    for r in rows:
        mid = r["member_id"]
        stats.setdefault(mid, {})
        projects = _parse_json_list(r["projects"])
        if not projects:
            projects = ["未分类"]
        for p in projects:
            stats[mid][p] = stats[mid].get(p, 0) + int(r["cnt"] or 0)
    return stats


def get_daily_report_calendar_events(date_from=None, date_to=None):
    reports = get_daily_reports(date_from=date_from, date_to=date_to, limit=1000)
    events = []
    for r in reports:
        projects = r.get("projects") or []
        title = projects[0] if projects else (r.get("content") or "")[:40]
        events.append({
            "date": r["report_date"],
            "title": title,
            "member": r["member_id"],
            "report_id": r["id"],
            "content": r["content"],
        })
    return events


def get_member_recent_report_summary(member_id=None, days=30, limit=100):
    """供 AI Native / Smart Chat 消费的日报摘要"""
    with get_db() as conn:
        query = """
            SELECT dr.report_date, dr.member_id, dr.content, dr.version,
                   dra.skills, dra.projects, dra.activity_type, dra.impact_score
            FROM daily_report dr
            LEFT JOIN daily_report_analysis dra ON dra.report_id = dr.id
            WHERE dr.report_date >= date('now', ?)
        """
        params = [f"-{int(days)} days"]
        if member_id:
            query += " AND dr.member_id = ?"
            params.append(member_id)
        query += " ORDER BY dr.report_date DESC LIMIT ?"
        params.append(limit)
        rows = conn.execute(query, params).fetchall()
        result = []
        for r in rows:
            item = dict(r)
            item["skills"] = _parse_json_list(item.get("skills"))
            item["projects"] = _parse_json_list(item.get("projects"))
            result.append(item)
        return result

