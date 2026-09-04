"""时态图谱常量。节点生命周期与关系生命周期分离。"""

from organization_graph.ontology.relations import (
    REL_BELONGS_TO,
    REL_COLLABORATE,
    REL_CONFLICT,
    REL_CONTROL,
    REL_HAS_KNOWLEDGE,
    REL_HAS_ROLE,
    REL_INFORMAL,
    REL_MENTOR,
    REL_OWNER,
    REL_REPORT_TO,
    REL_TRUST,
    REL_WORKS_ON,
)

LIFECYCLE_ACTIVE = "ACTIVE"
LIFECYCLE_INACTIVE = "INACTIVE"

EVT_JOIN_COMPANY = "JOIN_COMPANY"
EVT_LEAVE_COMPANY = "LEAVE_COMPANY"
EVT_ROLE_CHANGE = "ROLE_CHANGE"
EVT_TRANSFER = "TRANSFER"
EVT_PROJECT_START = "PROJECT_START"
EVT_PROJECT_PHASE_CHANGE = "PROJECT_PHASE_CHANGE"
EVT_PROJECT_COMPLETE = "PROJECT_COMPLETE"
EVT_PROJECT_OWNER_CHANGE = "PROJECT_OWNER_CHANGE"
EVT_RESOURCE_ACQUIRE = "RESOURCE_ACQUIRE"
EVT_RESOURCE_TRANSFER = "RESOURCE_TRANSFER"
EVT_RESOURCE_RELEASE = "RESOURCE_RELEASE"

TEMPORAL_EVENT_TYPES = (
    {"id": EVT_JOIN_COMPANY, "group": "person", "label": "员工入职"},
    {"id": EVT_LEAVE_COMPANY, "group": "person", "label": "员工离职"},
    {"id": EVT_ROLE_CHANGE, "group": "person", "label": "角色变化"},
    {"id": EVT_TRANSFER, "group": "person", "label": "组织调动"},
    {"id": EVT_PROJECT_START, "group": "project", "label": "项目启动"},
    {"id": EVT_PROJECT_PHASE_CHANGE, "group": "project", "label": "项目阶段变化"},
    {"id": EVT_PROJECT_COMPLETE, "group": "project", "label": "项目完成"},
    {"id": EVT_PROJECT_OWNER_CHANGE, "group": "project", "label": "项目负责人交接"},
    {"id": EVT_RESOURCE_ACQUIRE, "group": "resource", "label": "获取资源"},
    {"id": EVT_RESOURCE_TRANSFER, "group": "resource", "label": "资源转交"},
    {"id": EVT_RESOURCE_RELEASE, "group": "resource", "label": "释放资源"},
)

# 同一客体同时只能有一条开放事实
EXCLUSIVE_BY_TARGET = {REL_OWNER}

# 同一主体同时只能有一条开放事实
EXCLUSIVE_BY_SOURCE = {REL_REPORT_TO, REL_BELONGS_TO}

LEAVE_CLOSE_PREDICATES = {
    REL_OWNER,
    REL_WORKS_ON,
    REL_BELONGS_TO,
    REL_REPORT_TO,
    REL_CONTROL,
    REL_HAS_ROLE,
    REL_COLLABORATE,
    REL_MENTOR,
    REL_TRUST,
    REL_CONFLICT,
    REL_INFORMAL,
    REL_HAS_KNOWLEDGE,
}
