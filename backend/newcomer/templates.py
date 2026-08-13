"""新人培养模板：阶段、任务等级、能力、入职指南骨架。"""

from datetime import datetime

STAGES = [
    {"id": "onboarding", "label": "入职指南", "order": 1},
    {"id": "project_familiarization", "label": "项目熟悉", "order": 2},
    {"id": "first_task", "label": "第一任务", "order": 3},
    {"id": "independent_task", "label": "独立任务", "order": 4},
    {"id": "independent_module", "label": "独立模块", "order": 5},
]

STAGE_ORDER = [s["id"] for s in STAGES]

LEVELS = ["L0", "L1", "L2", "L3", "L4", "L5"]
LEVEL_LABELS = {
    "L0": "项目探索",
    "L1": "简单问题",
    "L2": "小功能",
    "L3": "独立功能",
    "L4": "独立模块",
    "L5": "复杂技术问题",
}

CAPABILITIES = {
    "git": "Git 能力",
    "python": "Python",
    "docker": "Docker",
    "ai_coding": "AI Coding",
    "api": "API 理解",
    "project_structure": "项目结构理解",
    "debug": "Debug 能力",
    "testing": "测试",
    "ai_context": "AI Context",
    "architecture": "架构理解",
}

ROLE_CAPABILITIES = {
    "developer": ["git", "python", "ai_coding", "debug", "testing", "api", "project_structure"],
    "architect": ["architecture", "api", "project_structure", "ai_coding", "debug"],
    "tester": ["testing", "debug", "api", "git", "ai_coding"],
    "product_manager": ["api", "project_structure", "ai_context"],
    "project_manager": ["project_structure", "git", "ai_context"],
    "ui_designer": ["project_structure", "ai_coding"],
    "context_owner": ["ai_context", "ai_coding", "project_structure"],
    "leader": ["architecture", "ai_context", "project_structure"],
    "business_owner": ["api", "project_structure"],
}

LEVEL_TO_STAGE = {
    "L0": "project_familiarization",
    "L1": "first_task",
    "L2": "independent_task",
    "L3": "independent_task",
    "L4": "independent_module",
    "L5": "independent_module",
}

SCOPE_LABELS = {
    "TEAM": "当前团队",
    "PROJECT": "当前项目",
    "ALL": "全体人员",
    "CUSTOM": "指定人员",
}


def level_index(level):
    try:
        return LEVELS.index((level or "L0").upper())
    except ValueError:
        return 0


def next_level(level):
    idx = level_index(level)
    return LEVELS[min(idx + 1, len(LEVELS) - 1)]


def default_l0_task():
    return {
        "task_name": "完成项目核心调用链分析",
        "task_level": "L0",
        "description": (
            "理解 Frontend → API → Service → Database 的主路径，"
            "跑通一个真实流程并提交总结。"
        ),
        "requirements": [
            "启动项目",
            "跑通一个真实流程",
            "找到核心代码",
            "绘制调用链",
            "修改一个低风险问题",
            "提交总结",
        ],
        "estimated_hours": 4,
        "ai_allowed": True,
        "review_required": True,
        "capability_ids": ["api", "project_structure", "debug", "git", "ai_coding"],
    }


def recommend_tasks_for_gaps(target_role_id, gaps, current_level="L0"):
    """根据能力差距生成下一等级推荐任务（规则，可被 AI 覆盖）。"""
    nxt = next_level(current_level)
    catalog = [
        {
            "task_name": "完成 AI Coding 规范任务",
            "capability_ids": ["ai_coding", "git"],
            "description": "按团队 AI Coding 规范完成一次受控改动，并记录提示词与结果。",
            "requirements": ["阅读规范", "用 AI 辅助改一处低风险代码", "提交并说明取舍"],
        },
        {
            "task_name": "完成一个自动测试任务",
            "capability_ids": ["testing", "python", "debug"],
            "description": "为已有功能补一条自动化测试并跑通。",
            "requirements": ["定位测试目录", "补一条用例", "本地跑通", "提交"],
        },
        {
            "task_name": "修改一个 AI 生成 Bug",
            "capability_ids": ["debug", "ai_coding", "git"],
            "description": "定位并修复一处由 AI 生成或引入的缺陷。",
            "requirements": ["复现", "定位根因", "最小修复", "回归验证"],
        },
        {
            "task_name": "补齐项目结构说明",
            "capability_ids": ["project_structure", "architecture", "api"],
            "description": "画出模块边界并标注你负责的入口。",
            "requirements": ["列出核心目录", "标注调用入口", "指出风险点"],
        },
    ]
    gap_set = set(gaps or [])
    picked = []
    for item in catalog:
        if gap_set & set(item["capability_ids"]) or not gap_set:
            picked.append({
                **item,
                "task_level": nxt,
                "estimated_hours": 4 if nxt in ("L1", "L2") else 8,
                "ai_allowed": True,
                "review_required": True,
            })
        if len(picked) >= 3:
            break
    if not picked:
        picked = [{
            **catalog[0],
            "task_level": nxt,
            "estimated_hours": 4,
            "ai_allowed": True,
            "review_required": True,
        }]
    return picked


def template_guide(member, team_names, projects, role_name, tech_stack):
    contacts = "、".join(team_names[:8]) or "团队负责人"
    proj = "、".join(projects[:6]) or "当前团队项目"
    stack = "、".join(tech_stack[:8]) or "以仓库 README 为准"
    today = datetime.now().strftime("%Y-%m-%d")
    return {
        "title": f"{member.get('name') or '新人'}入职指南",
        "generated_at": today,
        "sections": [
            {"id": "01", "title": "团队介绍", "body": f"当前团队成员：{contacts}。有问题先看本指南，再找对应联系人。"},
            {"id": "02", "title": "项目介绍", "body": f"近期相关项目：{proj}。先跑通主流程，再深入模块。"},
            {"id": "03", "title": "当前项目目标", "body": "本周期以能独立完成 L0 探索、提交一次有效总结为目标。"},
            {"id": "04", "title": "技术栈", "body": stack},
            {"id": "05", "title": "开发环境", "body": "按仓库 README 安装依赖、配置环境变量、启动前后端，确认健康检查通过。"},
            {"id": "06", "title": "Git 规范", "body": "小步提交；分支命名 feature/xxx；PR 需说明动机、改动与验证方式。"},
            {"id": "07", "title": "AI Coding 规范", "body": "允许使用 AI，但必须理解每一处改动；禁止直接提交看不懂的代码。"},
            {"id": "08", "title": "项目规则", "body": "先本地验证再提交；高风险改动需负责人 Review。"},
            {"id": "09", "title": "常见问题", "body": "启动失败先看端口占用与 .env；接口 404 先对路由前缀 /api。"},
            {"id": "10", "title": "联系人", "body": f"日常问题：团队频道。目标角色相关：对应 {role_name or '角色'} 负责人。"},
        ],
    }
