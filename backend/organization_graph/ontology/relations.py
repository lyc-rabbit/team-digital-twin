"""图谱关系本体 —— 所有关系必须带属性。"""

from datetime import datetime


# V1
REL_REPORT_TO = "REPORT_TO"
REL_COLLABORATE = "COLLABORATE_WITH"
REL_MENTOR = "MENTOR"
REL_TRUST = "TRUST"
# V2
REL_CONFLICT = "CONFLICT"
REL_CONTROL = "CONTROL_RESOURCE"
REL_INFORMAL = "INFORMAL_MEMBER"
# 结构补充
REL_OWNER = "OWNER"
REL_HAS_ROLE = "HAS_ROLE"
REL_BELONGS_TO = "BELONGS_TO"
REL_WORKS_ON = "WORKS_ON"
REL_HAS_KNOWLEDGE = "HAS_KNOWLEDGE"
REL_INVOLVED_IN = "INVOLVED_IN"

RELATION_TYPES = (
    REL_REPORT_TO,
    REL_COLLABORATE,
    REL_MENTOR,
    REL_TRUST,
    REL_CONFLICT,
    REL_CONTROL,
    REL_INFORMAL,
    REL_OWNER,
    REL_HAS_ROLE,
    REL_BELONGS_TO,
    REL_WORKS_ON,
    REL_HAS_KNOWLEDGE,
    REL_INVOLVED_IN,
)

# 人员之间的核心关系（可视化 / 影响力计算主图）
PERSON_RELATIONS = (
    REL_REPORT_TO,
    REL_COLLABORATE,
    REL_MENTOR,
    REL_TRUST,
    REL_CONFLICT,
)


def _today():
    return datetime.now().strftime("%Y-%m-%d")


def relation_template(source, target, relation, **props):
    """统一关系格式。"""
    merged = {
        "strength": float(props.get("strength") if props.get("strength") is not None else 0.5),
        "last_update": props.get("last_update") or _today(),
    }
    defaults = {
        REL_REPORT_TO: {"start_date": "", "current": True},
        REL_COLLABORATE: {"project": "", "frequency": 1, "impact": 50},
        REL_MENTOR: {"duration": 0, "skill": ""},
        REL_TRUST: {"score": 0.5, "sample_count": 1},
        REL_CONFLICT: {"reason": "", "frequency": 1, "impact": 50},
        REL_CONTROL: {"resource_value": 60},
        REL_INFORMAL: {"affinity": 0.6},
        REL_OWNER: {"responsibility": "owner"},
        REL_HAS_ROLE: {"match_score": 0},
        REL_BELONGS_TO: {},
        REL_WORKS_ON: {"days": 1},
        REL_HAS_KNOWLEDGE: {"level": 0.6},
        REL_INVOLVED_IN: {"role": "participant"},
    }
    merged.update(defaults.get(relation, {}))
    for k, v in props.items():
        if v is not None:
            merged[k] = v
    if "evidence" not in merged:
        merged["evidence"] = list(props.get("evidence") or [])
    return {
        "source": source,
        "target": target,
        "relation": relation,
        "properties": merged,
    }
