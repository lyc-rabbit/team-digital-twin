"""图谱节点本体"""

from datetime import datetime


NODE_TYPES = (
    "Person",
    "Role",
    "Department",
    "Project",
    "Resource",
    "Knowledge",
    "Event",
    "InformalGroup",
)


def _now():
    return datetime.now().strftime("%Y-%m-%d")


def node_template(node_type, node_id, name, **extra):
    """按类型生成规范化节点。"""
    base = {
        "id": node_id,
        "type": node_type,
        "name": name,
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
    elif node_type == "Knowledge":
        base["domain"] = extra.get("domain") or "通用"
    elif node_type == "Event":
        base["time"] = extra.get("time") or _now()
        base["description"] = extra.get("description") or ""
    elif node_type == "InformalGroup":
        base["theme"] = extra.get("theme") or name
    # 透传其余扩展字段
    for k, v in extra.items():
        if k not in base:
            base[k] = v
    return base
