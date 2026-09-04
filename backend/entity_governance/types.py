"""统一实体层：类型、状态、阈值、来源可信度。"""

from organization_graph.ontology.nodes import NODE_TYPES

# 图谱节点类型 → 治理实体类型
GRAPH_TO_ENTITY = {
    "Person": "PERSON",
    "Role": "ROLE",
    "Department": "DEPARTMENT",
    "Project": "PROJECT",
    "Resource": "RESOURCE",
    "Knowledge": "KNOWLEDGE",
    "Event": "EVENT",
    "InformalGroup": "ORG_GROUP",
    "Achievement": "ACHIEVEMENT",
    "Contribution": "CONTRIBUTION",
    "TrainingAction": "TRAINING_ACTION",
    "CapabilityEvidence": "CAPABILITY_EVIDENCE",
    "ProjectStage": "PROJECT_STAGE",
    "Capability": "CAPABILITY",
}

ENTITY_TO_GRAPH = {v: k for k, v in GRAPH_TO_ENTITY.items()}

ENTITY_TYPES = tuple(GRAPH_TO_ENTITY.values())

ENTITY_TYPE_LABELS = {
    "PERSON": "人员",
    "ROLE": "角色",
    "DEPARTMENT": "部门",
    "PROJECT": "项目",
    "RESOURCE": "资源",
    "KNOWLEDGE": "知识",
    "EVENT": "事件",
    "ORG_GROUP": "非正式组织",
    "ACHIEVEMENT": "成果",
    "CONTRIBUTION": "贡献",
    "TRAINING_ACTION": "培养行为",
    "CAPABILITY_EVIDENCE": "能力证据",
    "PROJECT_STAGE": "项目阶段",
    "CAPABILITY": "能力",
}

ID_PREFIX = {
    "PERSON": "person",
    "ROLE": "role",
    "DEPARTMENT": "dept",
    "PROJECT": "project",
    "RESOURCE": "resource",
    "KNOWLEDGE": "knowledge",
    "EVENT": "event",
    "ORG_GROUP": "group",
    "ACHIEVEMENT": "achv",
    "CONTRIBUTION": "contrib",
    "TRAINING_ACTION": "train",
    "CAPABILITY_EVIDENCE": "capev",
    "PROJECT_STAGE": "stage",
    "CAPABILITY": "cap",
}

STATUS_ACTIVE = "ACTIVE"
STATUS_MERGED = "MERGED"
STATUS_ARCHIVED = "ARCHIVED"

LIFECYCLE_NEW = "NEW"
LIFECYCLE_NORMALIZED = "NORMALIZED"
LIFECYCLE_CANDIDATE = "CANDIDATE"
LIFECYCLE_MATCHED = "MATCHED"
LIFECYCLE_CANONICAL = "CANONICAL"
LIFECYCLE_NOT_MATCH = "NOT_MATCH"
LIFECYCLE_MERGED = "MERGED"

DECISION_AUTO_MATCH = "AUTO_MATCH"
DECISION_REVIEW = "REVIEW"
DECISION_NEW = "NEW"
DECISION_FORCE_REVIEW = "FORCE_REVIEW"
DECISION_MATCH = "MATCH"

CANDIDATE_PENDING = "pending"
CANDIDATE_AUTO_MERGED = "auto_merged"
CANDIDATE_MERGED = "merged"
CANDIDATE_REJECTED = "rejected"
CANDIDATE_SKIPPED = "skipped"

# 匹配阈值
AUTO_MERGE_THRESHOLD = 0.95
REVIEW_THRESHOLD = 0.75
EVENT_AUTO_THRESHOLD = 0.98
RECALL_LIMIT = 20

# 永不自动合并
NO_AUTO_MERGE_TYPES = {"KNOWLEDGE"}

# 来源可信度（Survivorship）
SOURCE_RANK = {
    "enterprise": 100,
    "hr": 95,
    "human": 80,
    "manual": 80,
    "project": 60,
    "daily_report": 55,
    "event": 40,
    "graph_builder": 35,
    "llm": 20,
    "inferred": 10,
}

# 字段级来源默认
DEFAULT_SOURCE_BY_CONTEXT = {
    "graph_builder": "inferred",
    "document": "llm",
    "event": "event",
    "daily_report": "daily_report",
    "manual": "human",
}

# 四层匹配在不同类型上的权重
LAYER_WEIGHTS = {
    "PERSON": {"exact": 0.70, "rule": 0.20, "semantic": 0.05, "graph": 0.05},
    "PROJECT": {"exact": 0.15, "rule": 0.55, "semantic": 0.15, "graph": 0.15},
    "RESOURCE": {"exact": 0.35, "rule": 0.40, "semantic": 0.15, "graph": 0.10},
    "KNOWLEDGE": {"exact": 0.05, "rule": 0.35, "semantic": 0.40, "graph": 0.20},
    "EVENT": {"exact": 0.20, "rule": 0.70, "semantic": 0.05, "graph": 0.05},
    "ROLE": {"exact": 0.30, "rule": 0.50, "semantic": 0.15, "graph": 0.05},
    "DEPARTMENT": {"exact": 0.30, "rule": 0.50, "semantic": 0.15, "graph": 0.05},
    "ORG_GROUP": {"exact": 0.20, "rule": 0.45, "semantic": 0.20, "graph": 0.15},
}

PERSON_FIELD_WEIGHTS = {
    "unique_id": 0.50,
    "email": 0.20,
    "account": 0.15,
    "name": 0.10,
    "org_context": 0.05,
}

PROJECT_FIELD_WEIGHTS = {
    "name": 0.30,
    "owner": 0.15,
    "members": 0.15,
    "time": 0.10,
    "resources": 0.10,
    "knowledge": 0.10,
    "embedding": 0.10,
}

RESOURCE_FIELD_WEIGHTS = {
    "name": 0.30,
    "url": 0.30,
    "type": 0.10,
    "project": 0.10,
    "tech": 0.10,
    "embedding": 0.10,
}

KNOWLEDGE_FIELD_WEIGHTS = {
    "embedding": 0.40,
    "title": 0.20,
    "topic": 0.10,
    "project": 0.10,
    "author": 0.05,
    "citation": 0.15,
}

EVENT_FIELD_WEIGHTS = {
    "type": 0.15,
    "time": 0.20,
    "subject": 0.15,
    "object": 0.10,
    "project": 0.10,
    "action": 0.15,
    "source": 0.15,
}

GOVERNANCE_RELATIONS = ("MERGED_INTO", "ALIAS_OF")

PERSON_ID_KEYS = (
    "employee_id",
    "enterprise_id",
    "email",
    "enterprise_wechat",
    "github_account",
    "id",
)


def to_entity_type(graph_or_entity: str) -> str:
    if not graph_or_entity:
        return "PROJECT"
    if graph_or_entity in ENTITY_TO_GRAPH:
        return graph_or_entity
    return GRAPH_TO_ENTITY.get(graph_or_entity, graph_or_entity.upper())


def to_graph_type(graph_or_entity: str) -> str:
    if graph_or_entity in GRAPH_TO_ENTITY:
        return graph_or_entity
    return ENTITY_TO_GRAPH.get(graph_or_entity, graph_or_entity)


def is_known_graph_type(node_type: str) -> bool:
    return node_type in NODE_TYPES
