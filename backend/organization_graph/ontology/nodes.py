"""图谱节点本体"""

from timeutil import today


NODE_TYPES = (
    "Person",
    "Role",
    "Department",
    "Project",
    "ProjectStage",
    "Resource",
    "Knowledge",
    "Event",
    "InformalGroup",
    "Achievement",
    "Contribution",
    "Capability",
    "TrainingAction",
    "CapabilityEvidence",
)


def _now():
    return today()


def node_template(node_type, node_id, name, **extra):
    """按类型生成规范化节点。"""
    base = {
        "id": node_id,
        "type": node_type,
        "name": name,
        "entity_status": extra.get("entity_status") or "ACTIVE",
        "canonical_entity_id": extra.get("canonical_entity_id") or node_id,
        "lifecycle_status": extra.get("lifecycle_status") or "ACTIVE",
        "valid_from": extra.get("valid_from") or "",
        "valid_to": extra.get("valid_to") or "",
    }
    if node_type == "Person":
        base.update({
            "department": extra.get("department") or "未分组",
            "position": extra.get("position") or "",
            "level": extra.get("level") or "",
            "join_date": extra.get("join_date") or "",
            "skills": list(extra.get("skills") or []),
            "leadership_score": int(extra.get("leadership_score") or 0),
            "influence_score": int(extra.get("influence_score") or 0),
        })
    elif node_type == "Role":
        req = extra.get("requirements") or {}
        base["requirements"] = {
            "technical": int(req.get("technical") or 70),
            "management": int(req.get("management") or 70),
            "communication": int(req.get("communication") or 70),
        }
        base["description"] = extra.get("description") or ""
        base["required_skills"] = list(extra.get("required_skills") or [])
    elif node_type == "Department":
        pass
    elif node_type == "Project":
        base.update({
            "importance": extra.get("importance") or "medium",
            "status": extra.get("status") or "running",
            "business_value": int(extra.get("business_value") or 60),
        })
    elif node_type == "Resource":
        base["importance"] = int(extra.get("importance") or 60)
        base["category"] = extra.get("category") or "tech"
        base["resource_kind"] = extra.get("resource_kind") or "instance"
        if extra.get("parent_resource_id"):
            base["parent_resource_id"] = extra.get("parent_resource_id")
    elif node_type == "Knowledge":
        base["domain"] = extra.get("domain") or "通用"
    elif node_type == "Event":
        base["time"] = extra.get("time") or _now()
        base["description"] = extra.get("description") or ""
    elif node_type == "InformalGroup":
        base["theme"] = extra.get("theme") or name
    elif node_type == "ProjectStage":
        base.update({
            "stage_name": extra.get("stage_name") or name,
            "project": extra.get("project") or "",
            "status": extra.get("status") or "running",
        })
    elif node_type == "Achievement":
        base.update({
            "achievement_type": extra.get("achievement_type") or "delivery",
            "project": extra.get("project") or "",
            "stage": extra.get("stage") or "",
            "start_time": extra.get("start_time") or "",
            "achieved_time": extra.get("achieved_time") or "",
            "evidence": extra.get("evidence") or "",
            "confidence": float(extra.get("confidence") or 0.7),
            "status": extra.get("status") or "ACTIVE",
        })
    elif node_type == "Contribution":
        base.update({
            "contribution_type": extra.get("contribution_type") or "technical",
            "contribution_level": extra.get("contribution_level") or "important",
            "workload": extra.get("workload"),
            "evidence_level": extra.get("evidence_level") or "medium",
            "start_time": extra.get("start_time") or "",
            "end_time": extra.get("end_time") or "",
            "source": extra.get("source") or "",
            "confidence": float(extra.get("confidence") or 0.7),
            "status": extra.get("status") or "ACTIVE",
        })
    elif node_type == "Capability":
        base.update({
            "category": extra.get("category") or "",
            "description": extra.get("description") or "",
        })
    elif node_type == "TrainingAction":
        base.update({
            "action_type": extra.get("action_type") or "指导",
            "duration": extra.get("duration") or "",
            "frequency": extra.get("frequency") or "",
            "target_capability": extra.get("target_capability") or "",
            "evidence": extra.get("evidence") or "",
            "result": extra.get("result") or "",
            "confidence": float(extra.get("confidence") or 0.7),
        })
    elif node_type == "CapabilityEvidence":
        base.update({
            "capability_name": extra.get("capability_name") or "",
            "evidence_level": extra.get("evidence_level") or "medium",
            "independence": extra.get("independence") or "",
            "quality": extra.get("quality") or "",
            "persistence": extra.get("persistence") or "",
            "complexity": extra.get("complexity") or "",
            "evaluation": extra.get("evaluation") or "",
            "confidence": float(extra.get("confidence") or 0.5),
            "status": extra.get("status") or "candidate",
        })
    # 透传其余扩展字段
    for k, v in extra.items():
        if k not in base:
            base[k] = v
    return base
