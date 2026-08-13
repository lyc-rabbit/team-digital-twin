"""晋升推演预置领导风格与默认权重。"""

LAYER_DEFAULTS = {
    "boss": 40,
    "team": 25,
    "role": 25,
    "custom": 10,
}

LAYER_LABELS = {
    "boss": "老板视角",
    "team": "团队认可",
    "role": "岗位匹配",
    "custom": "个性化要求",
}

BOSS_WEIGHTS = {
    "strategy_alignment": 20,
    "delivery": 25,
    "management_potential": 25,
    "coordination": 15,
    "risk_control": 10,
    "professional": 5,
}

BOSS_LABELS = {
    "strategy_alignment": "战略一致性",
    "delivery": "结果交付",
    "management_potential": "管理潜力",
    "coordination": "组织协调",
    "risk_control": "风险控制",
    "professional": "专业能力",
}

TEAM_WEIGHTS = {
    "fairness": 25,
    "mentoring": 20,
    "protection": 20,
    "communication": 15,
    "expertise": 10,
    "stability": 10,
}

TEAM_LABELS = {
    "fairness": "公平性",
    "mentoring": "培养能力",
    "protection": "保护团队",
    "communication": "沟通方式",
    "expertise": "专业可信",
    "stability": "情绪稳定",
}

STYLE_TEMPLATES = [
    {
        "id": "tech_expert",
        "name": "技术专家型",
        "type": "技术领导型",
        "description": "希望领导具备技术判断能力，同时能够培养团队。强调技术判断、架构能力与解决复杂问题。",
        "weights": {
            "professional": 40,
            "innovation": 25,
            "delivery": 20,
            "management_potential": 15,
        },
        "labels": {
            "professional": "专业能力",
            "innovation": "创新能力",
            "delivery": "结果能力",
            "management_potential": "管理能力",
        },
    },
    {
        "id": "manager_growth",
        "name": "管理成长型",
        "type": "管理成长型",
        "description": "强调培养人才与组织协调，适合带团队扩张的负责人。",
        "weights": {
            "management_potential": 40,
            "influence": 25,
            "communication": 20,
            "professional": 15,
        },
        "labels": {
            "management_potential": "管理能力",
            "influence": "团队影响",
            "communication": "沟通能力",
            "professional": "专业能力",
        },
    },
    {
        "id": "startup",
        "name": "创业突破型",
        "type": "创业突破型",
        "description": "强调快速推进与高风险承担，适合攻坚和从 0 到 1 的阶段。",
        "weights": {
            "delivery": 40,
            "innovation": 30,
            "execution": 20,
            "risk_taking": 10,
        },
        "labels": {
            "delivery": "结果能力",
            "innovation": "创新能力",
            "execution": "执行力",
            "risk_taking": "风险承担",
        },
    },
]

REQUIREMENT_ALIASES = {
    "技术深度": "professional",
    "技术": "professional",
    "专业能力": "professional",
    "架构": "professional",
    "创新能力": "innovation",
    "创新": "innovation",
    "团队培养": "mentoring",
    "培养人才": "mentoring",
    "培养下属": "mentoring",
    "业务理解": "business",
    "业务": "business",
    "管理能力": "management_potential",
    "管理": "management_potential",
    "沟通": "communication",
    "沟通能力": "communication",
    "结果": "delivery",
    "交付": "delivery",
    "执行力": "execution",
    "影响力": "influence",
    "风险承担": "risk_taking",
}


def get_style(style_id):
    for t in STYLE_TEMPLATES:
        if t["id"] == style_id:
            return t
    return STYLE_TEMPLATES[0]


def list_templates():
    return {
        "layer_defaults": LAYER_DEFAULTS,
        "layer_labels": LAYER_LABELS,
        "boss_weights": BOSS_WEIGHTS,
        "boss_labels": BOSS_LABELS,
        "team_weights": TEAM_WEIGHTS,
        "team_labels": TEAM_LABELS,
        "styles": STYLE_TEMPLATES,
    }
