"""图谱关系本体 —— 所有关系必须带属性。"""

from timeutil import today


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
REL_HAS_SUB_RESOURCE = "HAS_SUB_RESOURCE"
REL_HAS_RESOURCE = "HAS_RESOURCE"
# 责任拆分：组织挂名 ≠ 执行 ≠ 管理 ≠ 汇报
REL_ORG_RESPONSIBILITY = "ORG_RESPONSIBILITY"
REL_EXECUTION_RESPONSIBILITY = "EXECUTION_RESPONSIBILITY"
REL_MANAGEMENT_RESPONSIBILITY = "MANAGEMENT_RESPONSIBILITY"
REL_REPORTING_RESPONSIBILITY = "REPORTING_RESPONSIBILITY"
# 成果 / 贡献（贡献必须经 Contribution 节点，不能从归属推出）
REL_ACHIEVEMENT_OWNERSHIP = "ACHIEVEMENT_OWNERSHIP"
REL_MADE_CONTRIBUTION = "MADE_CONTRIBUTION"
REL_CONTRIBUTES_TO = "CONTRIBUTES_TO"
REL_HAS_STAGE = "HAS_STAGE"
REL_PRODUCED = "PRODUCED"
# 培养行为（不能从汇报/管理推出 MENTOR）
REL_PERFORMED_TRAINING = "PERFORMED_TRAINING"
REL_TRAINING_TARGET = "TRAINING_TARGET"
# 能力证据（证据 ≠ 掌握）
REL_EVIDENCES_CAPABILITY = "EVIDENCES_CAPABILITY"
REL_HAS_CAPABILITY_EVIDENCE = "HAS_CAPABILITY_EVIDENCE"

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
    REL_HAS_SUB_RESOURCE,
    REL_HAS_RESOURCE,
    REL_ORG_RESPONSIBILITY,
    REL_EXECUTION_RESPONSIBILITY,
    REL_MANAGEMENT_RESPONSIBILITY,
    REL_REPORTING_RESPONSIBILITY,
    REL_ACHIEVEMENT_OWNERSHIP,
    REL_MADE_CONTRIBUTION,
    REL_CONTRIBUTES_TO,
    REL_HAS_STAGE,
    REL_PRODUCED,
    REL_PERFORMED_TRAINING,
    REL_TRAINING_TARGET,
    REL_EVIDENCES_CAPABILITY,
    REL_HAS_CAPABILITY_EVIDENCE,
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
    return today()


def relation_template(source, target, relation, **props):
    """统一关系格式。"""
    merged = {
        "strength": float(props.get("strength") if props.get("strength") is not None else 0.5),
        "last_update": props.get("last_update") or _today(),
        "valid_from": props.get("valid_from") or _today(),
        "valid_to": props.get("valid_to") or "",
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
        REL_HAS_SUB_RESOURCE: {"kind": "taxonomy"},
        REL_HAS_RESOURCE: {"role": "delivery"},
        REL_ORG_RESPONSIBILITY: {"scope": "org"},
        REL_EXECUTION_RESPONSIBILITY: {"scope": "execution"},
        REL_MANAGEMENT_RESPONSIBILITY: {"scope": "management"},
        REL_REPORTING_RESPONSIBILITY: {"scope": "reporting"},
        REL_ACHIEVEMENT_OWNERSHIP: {"kind": "org_attribution"},
        REL_MADE_CONTRIBUTION: {},
        REL_CONTRIBUTES_TO: {},
        REL_HAS_STAGE: {},
        REL_PRODUCED: {},
        REL_PERFORMED_TRAINING: {},
        REL_TRAINING_TARGET: {},
        REL_EVIDENCES_CAPABILITY: {"not_mastery": True},
        REL_HAS_CAPABILITY_EVIDENCE: {"not_mastery": True},
    }
    merged.update(defaults.get(relation, {}))
    for k, v in props.items():
        if v is not None:
            merged[k] = v
    if "evidence" not in merged:
        merged["evidence"] = list(props.get("evidence") or [])
    merged.setdefault("entity_status", props.get("entity_status") or "ACTIVE")
    if props.get("source_relationship_ids"):
        merged["source_relationship_ids"] = list(props.get("source_relationship_ids") or [])
    return {
        "source": source,
        "target": target,
        "relation": relation,
        "properties": merged,
    }
