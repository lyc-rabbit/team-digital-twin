"""角色培养标准 + 问题定义与结构化沟通能力模型。"""

COMMUNICATION_CAPABILITY = {
    "id": "problem_definition",
    "name": "问题定义与结构化沟通",
    "description": "找人帮忙时先说背景、事实、理解与需求，而不是直接说「帮我做什么」。",
    "evaluations": [
        {"id": "background_completeness", "label": "背景完整度"},
        {"id": "fact_accuracy", "label": "事实准确性"},
        {"id": "fact_judgement_split", "label": "事实/判断区分"},
        {"id": "goal_clarity", "label": "目标明确性"},
        {"id": "problem_boundary", "label": "问题边界"},
        {"id": "assumption_quality", "label": "假设合理性"},
        {"id": "request_clarity", "label": "请求明确性"},
    ],
}

# 人 / AI 分工默认项（按角色微调）
DEFAULT_HUMAN_AI = [
    {"item": "需求理解", "human": True, "ai": "assist", "owner": "人"},
    {"item": "信息检索", "human": "assist", "ai": True, "owner": "人"},
    {"item": "代码生成", "human": "review", "ai": True, "owner": "人"},
    {"item": "技术方案", "human": True, "ai": "assist", "owner": "人"},
    {"item": "测试用例", "human": "review", "ai": True, "owner": "人"},
    {"item": "最终决策", "human": True, "ai": False, "owner": "人"},
]

ROLE_HUMAN_AI = {
    "developer": DEFAULT_HUMAN_AI,
    "tester": [
        {"item": "质量策略", "human": True, "ai": "assist", "owner": "人"},
        {"item": "用例生成", "human": "review", "ai": True, "owner": "人"},
        {"item": "缺陷判断", "human": True, "ai": "assist", "owner": "人"},
        {"item": "回归验证", "human": "review", "ai": True, "owner": "人"},
        {"item": "最终放行", "human": True, "ai": False, "owner": "人"},
    ],
    "product_manager": [
        {"item": "需求理解", "human": True, "ai": "assist", "owner": "人"},
        {"item": "信息检索", "human": "assist", "ai": True, "owner": "人"},
        {"item": "规则沉淀", "human": True, "ai": "assist", "owner": "人"},
        {"item": "验收标准", "human": True, "ai": "assist", "owner": "人"},
        {"item": "最终决策", "human": True, "ai": False, "owner": "人"},
    ],
    "architect": [
        {"item": "问题定义", "human": True, "ai": "assist", "owner": "人"},
        {"item": "方案检索", "human": "assist", "ai": True, "owner": "人"},
        {"item": "架构设计", "human": True, "ai": "assist", "owner": "人"},
        {"item": "边界治理", "human": True, "ai": False, "owner": "人"},
        {"item": "最终决策", "human": True, "ai": False, "owner": "人"},
    ],
    "leader": [
        {"item": "目标对齐", "human": True, "ai": "assist", "owner": "人"},
        {"item": "信息检索", "human": "assist", "ai": True, "owner": "人"},
        {"item": "人才培养", "human": True, "ai": "assist", "owner": "人"},
        {"item": "风险兜底", "human": True, "ai": False, "owner": "人"},
        {"item": "最终决策", "human": True, "ai": False, "owner": "人"},
    ],
}

ROLE_STANDARDS = {
    "developer": {
        "dimensions": [
            {
                "id": "ai_coding",
                "name": "AI 协作开发",
                "levels": {
                    "L1": "能使用 AI 完成基础任务",
                    "L2": "能验证 AI 输出",
                    "L3": "能独立解决复杂问题",
                    "L4": "能指导他人使用 AI",
                    "management": "能建立团队 AI 开发规范",
                },
            },
            {
                "id": "problem_definition",
                "name": "问题定义与结构化沟通",
                "levels": {
                    "L1": "能按背景/事实/预期描述问题，而不是直接要答案",
                    "L2": "能区分事实与判断，并给出已尝试路径",
                    "L3": "能独立完成问题边界与假设验证",
                    "L4": "能指导他人做结构化问题定义",
                    "management": "能把结构化沟通变成团队协作规范",
                },
            },
            {
                "id": "debug",
                "name": "问题定位",
                "levels": {
                    "L1": "能在指导下定位简单问题",
                    "L2": "能独立排查常见异常",
                    "L3": "能定位跨模块复杂问题",
                    "L4": "能指导他人建立排查方法",
                    "management": "能沉淀团队排障规范",
                },
            },
            {
                "id": "delivery",
                "name": "工程交付",
                "levels": {
                    "L1": "能完成被拆好的小任务",
                    "L2": "能独立交付小功能并自测",
                    "L3": "能独立交付模块并处理风险",
                    "L4": "能带领他人完成模块交付",
                    "management": "能建立交付节奏与质量门禁",
                },
            },
        ],
    },
    "tester": {
        "dimensions": [
            {
                "id": "quality",
                "name": "质量策略",
                "levels": {
                    "L1": "能按用例执行验证",
                    "L2": "能设计有效用例并发现风险",
                    "L3": "能独立制定模块质量策略",
                    "L4": "能指导他人做质量设计",
                    "management": "能建立团队质量门禁",
                },
            },
            {
                "id": "problem_definition",
                "name": "问题定义与结构化沟通",
                "levels": {
                    "L1": "能完整描述缺陷背景与复现步骤",
                    "L2": "能区分现象、根因假设与影响范围",
                    "L3": "能独立完成风险定义与验收口径",
                    "L4": "能指导他人写高质量缺陷/风险单",
                    "management": "能把问题定义变成质量协作规范",
                },
            },
        ],
    },
    "architect": {
        "dimensions": [
            {
                "id": "architecture",
                "name": "架构判断",
                "levels": {
                    "L1": "能理解现有架构并说明边界",
                    "L2": "能评估 AI/方案输出是否越界",
                    "L3": "能独立给出复杂问题的技术路径",
                    "L4": "能指导他人做架构取舍",
                    "management": "能建立团队架构治理规范",
                },
            },
            {
                "id": "problem_definition",
                "name": "问题定义与结构化沟通",
                "levels": {
                    "L1": "能把模糊诉求转成可讨论的问题",
                    "L2": "能拆出约束、假设与验收口径",
                    "L3": "能独立完成复杂问题定义",
                    "L4": "能带领跨角色对齐问题定义",
                    "management": "能把问题定义变成组织决策习惯",
                },
            },
        ],
    },
    "product_manager": {
        "dimensions": [
            {
                "id": "requirement",
                "name": "需求结构化",
                "levels": {
                    "L1": "能使用 AI 整理需求草稿",
                    "L2": "能验证 AI 输出是否覆盖验收",
                    "L3": "能独立完成复杂规则设计",
                    "L4": "能指导他人写结构化需求",
                    "management": "能建立团队需求与验收规范",
                },
            },
            {
                "id": "problem_definition",
                "name": "问题定义与结构化沟通",
                "levels": {
                    "L1": "能写清背景、用户与目标",
                    "L2": "能区分事实、假设与优先级",
                    "L3": "能独立完成问题边界与验收",
                    "L4": "能指导业务/研发对齐问题定义",
                    "management": "能把问题定义变成产品协作规范",
                },
            },
        ],
    },
    "project_manager": {
        "dimensions": [
            {
                "id": "delivery",
                "name": "交付管理",
                "levels": {
                    "L1": "能跟踪任务状态",
                    "L2": "能识别风险并同步",
                    "L3": "能独立推动复杂依赖",
                    "L4": "能指导他人做计划与风险",
                    "management": "能建立团队交付节奏",
                },
            },
            {
                "id": "problem_definition",
                "name": "问题定义与结构化沟通",
                "levels": {
                    "L1": "能完整同步背景与卡点",
                    "L2": "能区分阻塞事实与判断",
                    "L3": "能独立定义升级问题",
                    "L4": "能带领多方对齐问题与动作",
                    "management": "能把结构化同步变成管理习惯",
                },
            },
        ],
    },
    "leader": {
        "dimensions": [
            {
                "id": "people",
                "name": "带人与组织",
                "levels": {
                    "L1": "能跟进单人任务",
                    "L2": "能完成一次有效指导并留下证据",
                    "L3": "能带完一个培养周期",
                    "L4": "能建立团队培养标准",
                    "management": "能把人才培养变成组织能力",
                },
            },
            {
                "id": "problem_definition",
                "name": "问题定义与结构化沟通",
                "levels": {
                    "L1": "要求他人先说背景与事实",
                    "L2": "能识别沟通中的事实/判断混用",
                    "L3": "能把复杂冲突定义成可决策问题",
                    "L4": "能训练团队结构化沟通",
                    "management": "能把问题定义变成组织决策机制",
                },
            },
        ],
    },
}

GENERIC_DIMENSIONS = [
    {
        "id": "problem_definition",
        "name": "问题定义与结构化沟通",
        "levels": {
            "L1": "能按背景/事实/预期描述问题",
            "L2": "能区分事实与判断，并给出已尝试路径",
            "L3": "能独立完成问题边界与假设验证",
            "L4": "能指导他人做结构化问题定义",
            "management": "能把结构化沟通变成团队规范",
        },
    },
    {
        "id": "ai_collab",
        "name": "AI 协作",
        "levels": {
            "L1": "能使用 AI 完成基础任务",
            "L2": "能验证 AI 输出",
            "L3": "能独立解决复杂问题",
            "L4": "能指导他人使用 AI",
            "management": "能建立团队 AI 协作规范",
        },
    },
]


def get_role_standards(role_id):
    spec = ROLE_STANDARDS.get(role_id)
    dimensions = list((spec or {}).get("dimensions") or GENERIC_DIMENSIONS)
    ids = {d["id"] for d in dimensions}
    if "problem_definition" not in ids:
        dimensions.insert(0, GENERIC_DIMENSIONS[0])
    return {
        "role_id": role_id,
        "communication": COMMUNICATION_CAPABILITY,
        "dimensions": dimensions,
        "human_ai_division": ROLE_HUMAN_AI.get(role_id) or DEFAULT_HUMAN_AI,
        "level_labels": {
            "L1": "L1 标准",
            "L2": "L2 标准",
            "L3": "L3 标准",
            "L4": "管理/高级标准",
            "management": "干部要求",
        },
    }


def human_ai_for_role(role_id):
    return ROLE_HUMAN_AI.get(role_id) or DEFAULT_HUMAN_AI
