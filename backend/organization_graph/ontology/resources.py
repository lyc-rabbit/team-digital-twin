"""资源分层：总类资源 → 明细资源，避免「××交付资源」平铺散落。"""

RESOURCE_CLASSES = (
    {"name": "交付资源", "category": "delivery", "importance": 72},
    {"name": "技术资源", "category": "tech", "importance": 80},
    {"name": "数据资源", "category": "data", "importance": 80},
    {"name": "客户资源", "category": "customer", "importance": 75},
    {"name": "预算资源", "category": "budget", "importance": 70},
)

RESOURCE_CLASS_NAMES = tuple(c["name"] for c in RESOURCE_CLASSES)

# 从知识领域关键词落到「总类 + 明细」
KEYWORD_RESOURCES = {
    "GPU": {"class_name": "技术资源", "name": "GPU集群", "category": "tech", "importance": 90},
    "数据": {"class_name": "数据资源", "name": "核心数据资源", "category": "data", "importance": 80},
    "模型": {"class_name": "技术资源", "name": "核心模型资产", "category": "tech", "importance": 85},
    "客户": {"class_name": "客户资源", "name": "客户渠道资源", "category": "customer", "importance": 75},
    "预算": {"class_name": "预算资源", "name": "预算额度", "category": "budget", "importance": 70},
}


def class_name_for_resource(name, category=None, resource_kind=None):
    """根据名称判断应挂到哪一个总类。总类自身返回 None。"""
    raw = (name or "").strip()
    if not raw or raw in RESOURCE_CLASS_NAMES or resource_kind == "class":
        return None
    if raw.endswith("交付资源"):
        return "交付资源"
    if category == "project":
        return "交付资源"
    if category in ("tech", "data", "customer", "budget", "delivery"):
        mapping = {
            "tech": "技术资源",
            "data": "数据资源",
            "customer": "客户资源",
            "budget": "预算资源",
            "delivery": "交付资源",
            "project": "交付资源",
        }
        return mapping.get(category)
    return None


def is_resource_hierarchy_pair(left, right) -> bool:
    """总类 vs 明细，不是重复实体。"""
    a, b = left or {}, right or {}
    kinds = {a.get("resource_kind"), b.get("resource_kind")}
    if kinds == {"class", "instance"}:
        return True
    na = (a.get("name") or "").strip()
    nb = (b.get("name") or "").strip()
    if not na or not nb or na == nb:
        return False
    if na in RESOURCE_CLASS_NAMES and (nb.endswith(na) or class_name_for_resource(nb, b.get("category")) == na):
        return True
    if nb in RESOURCE_CLASS_NAMES and (na.endswith(nb) or class_name_for_resource(na, a.get("category")) == nb):
        return True
    return False
