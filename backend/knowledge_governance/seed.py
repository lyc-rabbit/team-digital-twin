"""从当前图谱类型反向生成初始本体 + 默认可配置推理规则。"""

from organization_graph.ontology.nodes import NODE_TYPES
from organization_graph.ontology.resources import RESOURCE_CLASSES
from organization_graph.ontology.relations import REL_OWNER

from .relations import (
    REL_BELONGS_TO,
    REL_CONTRIBUTE_TO,
    REL_CONTROL,
    REL_CONTROL_KEY,
    REL_DEPENDS_ON,
    REL_HAS_RESOURCE,
    REL_HAS_SUB_RESOURCE,
    REL_IS_A,
    REL_MANAGES,
    REL_PART_OF,
    REL_USES,
    REL_WORKS_ON,
)
from .repository import get_kg_store
from .schema import (
    CORE_TYPE_DESCRIPTIONS,
    CORE_TYPE_NAMES,
    ONTOLOGY_SPEC,
    REPLACEABLE_TYPE_NAMES,
    SPECIAL_TYPE_NAMES,
    normalize_relation_rule,
    normalize_type_schema,
)

GRAPH_TO_ONTOLOGY = {
    "Person": "Person",
    "Role": "Role",
    "Department": "Department",
    "Project": "Project",
    "Resource": "Resource",
    "Knowledge": "Knowledge",
    "Event": "Event",
    "InformalGroup": "Organization",
    "Task": "Task",
    "Capability": "Capability",
    "ProjectStage": "ProjectStage",
    "Achievement": "Achievement",
    "Contribution": "Contribution",
    "TrainingAction": "TrainingAction",
    "CapabilityEvidence": "CapabilityEvidence",
    "Evaluation": "Evaluation",
    "AI_Capability": "AI_Capability",
    "Evidence": "Evidence",
    "Relationship": "Relationship",
}

RESOURCE_SUBTYPES = (
    {
        "name": "DeliveryResource",
        "label": "交付资源",
        "description": "项目交付物、交付能力。实例如「越南代理交付资源」。",
        "match": {"name_suffix": "交付资源", "categories": ["delivery", "project"]},
    },
    {
        "name": "TechnicalResource",
        "label": "技术资源",
        "description": "算力、模型、工具链等技术资产。",
        "match": {"categories": ["tech"], "class_names": ["技术资源"]},
    },
    {
        "name": "DataResource",
        "label": "数据资源",
        "description": "数据资产与数据权限。",
        "match": {"categories": ["data"], "class_names": ["数据资源"]},
    },
    {
        "name": "BusinessResource",
        "label": "业务资源",
        "description": "客户、渠道、预算等业务侧资源。",
        "match": {"categories": ["customer", "budget"], "class_names": ["客户资源", "预算资源"]},
    },
    {
        "name": "HumanResource",
        "label": "人力资源",
        "description": "编制、关键岗位能力等（当前图谱较少独立出现）。",
        "match": {"categories": ["human"]},
    },
)

CONTRIBUTION_SUBTYPES = (
    {"name": "TechnicalContribution", "label": "技术贡献", "match": {"contribution_type": "technical"}},
    {"name": "ArchitectureContribution", "label": "架构贡献", "match": {"contribution_type": "architecture"}},
    {"name": "ProductContribution", "label": "产品贡献", "match": {"contribution_type": "product"}},
    {"name": "ProjectManagementContribution", "label": "项目管理贡献", "match": {"contribution_type": "project_management"}},
    {"name": "ResourceContribution", "label": "资源贡献", "match": {"contribution_type": "resource"}},
    {"name": "DecisionContribution", "label": "决策贡献", "match": {"contribution_type": "decision"}},
    {"name": "CoordinationContribution", "label": "协调贡献", "match": {"contribution_type": "coordination"}},
    {"name": "TrainingContribution", "label": "培养贡献", "match": {"contribution_type": "training"}},
    {"name": "ReportingContribution", "label": "汇报贡献", "match": {"contribution_type": "reporting"}},
)

TRAINING_SUBTYPES = (
    {"name": "MentoringAction", "label": "指导行为", "match": {"action_type": "指导"}},
    {"name": "FeedbackAction", "label": "反馈行为", "match": {"action_type": "反馈"}},
    {"name": "CoachingAction", "label": "带教行为", "match": {"action_type": "带教"}},
)

TYPE_SCHEMAS = {
    "Person": {"relations": [
        "BELONG_TO", "MANAGE", "REPORT_TO", "HAS_ROLE", "SERVES_AS",
        "OWNER", "ORG_RESPONSIBILITY", "EXECUTION_RESPONSIBILITY",
        "MANAGEMENT_RESPONSIBILITY", "REPORTING_RESPONSIBILITY",
        "CORE_MEMBER", "PARTICIPATE", "SUPPORT", "RESPONSIBLE_FOR",
        "ACTOR_OF", "HAS_CAPABILITY", "DEMONSTRATED_CAPABILITY",
        "USES_AI_CAPABILITY", "DEMONSTRATES_AI_CAPABILITY", "EVALUATES",
        "COLLABORATE", "MENTOR", "DEPEND_ON", "ALLY", "COMPETE", "CONFLICT",
        "OWNS_RESOURCE", "PROVIDES_RESOURCE", "NEEDS_RESOURCE", "CONNECTED_TO_RESOURCE",
        "MADE_CONTRIBUTION", "ACHIEVEMENT_OWNERSHIP", "PERFORMED_TRAINING",
    ]},
    "Organization": {"relations": ["PARENT_OF", "BELONG_TO", "MANAGE"]},
    "Department": {"relations": ["BELONG_TO", "MANAGE", "PARENT_OF"]},
    "Project": {"relations": [
        "BELONG_TO", "OWNER", "ORG_RESPONSIBILITY", "EXECUTION_RESPONSIBILITY",
        "MANAGEMENT_RESPONSIBILITY", "REPORTING_RESPONSIBILITY",
        "CORE_MEMBER", "PARTICIPATE", "SUPPORT",
        "DEPEND_ON", "HAS_TASK", "HAS_STAGE", "USES_RESOURCE", "PRODUCED",
    ]},
    "ProjectStage": {"relations": ["HAS_STAGE", "PRODUCED", "BELONG_TO"]},
    "Achievement": {"relations": [
        "ACHIEVEMENT_OWNERSHIP", "CONTRIBUTES_TO", "PRODUCED", "HAS_STAGE",
    ]},
    "Contribution": {"relations": ["MADE_CONTRIBUTION", "CONTRIBUTES_TO"]},
    "TrainingAction": {"relations": ["PERFORMED_TRAINING", "TRAINING_TARGET"]},
    "CapabilityEvidence": {"relations": [
        "EVIDENCES_CAPABILITY", "HAS_CAPABILITY_EVIDENCE", "CONTRIBUTES_TO", "BASED_ON",
    ]},
    "Task": {"relations": ["BELONG_TO", "RESPONSIBLE_FOR", "PARTICIPATE", "DEPEND_ON", "EXECUTES"]},
    "Event": {"relations": [
        "ACTOR_OF", "RELATED_TO", "EXECUTES", "INVOLVES", "PRODUCES", "SUPPORTED_BY",
    ]},
    "Role": {"relations": ["HAS_ROLE", "SERVES_AS", "REQUIRES_CAPABILITY", "REQUIRES_AI_CAPABILITY"]},
    "Capability": {"relations": ["HAS_CAPABILITY", "DEMONSTRATED_CAPABILITY", "REQUIRES_CAPABILITY"]},
    "Evaluation": {"relations": ["EVALUATES", "TARGETS", "BASED_ON"]},
    "AI_Capability": {"relations": ["USES_AI_CAPABILITY", "DEMONSTRATES_AI_CAPABILITY", "REQUIRES_AI_CAPABILITY"]},
    "Resource": {"relations": [
        "OWNS_RESOURCE", "PROVIDES_RESOURCE", "NEEDS_RESOURCE", "CONNECTED_TO_RESOURCE",
        "USES_RESOURCE", "PRODUCES", "IS_A", "PART_OF",
    ]},
    "Relationship": {"relations": []},
    "Evidence": {"relations": ["BASED_ON", "SUPPORTED_BY"]},
    "Knowledge": {"relations": ["HAS_KNOWLEDGE"]},
}


def _rel(name, src, tgt, desc, cardinality="n:n", temporal=True, symmetric=False, aliases=None, sources=None):
    rule = {"cardinality": cardinality, "temporal": temporal, "symmetric": symmetric}
    if aliases:
        rule["aliases"] = list(aliases)
    if sources:
        rule["sources"] = list(sources)
    return {
        "name": name,
        "source_type": src,
        "target_type": tgt,
        "description": desc,
        "rule": rule,
    }


ALLOWED_RELATIONS = (
    # A. 组织关系
    _rel("BELONG_TO", "Person", "Organization", "人员隶属组织", "n:1", aliases=["BELONGS_TO", "INFORMAL_MEMBER"]),
    _rel("BELONG_TO", "Person", "Department", "人员隶属部门（Organization 的部门形态）", "n:1", aliases=["BELONGS_TO"]),
    _rel("MANAGE", "Person", "Organization", "人员管理组织", aliases=["MANAGE_ORG"]),
    _rel("MANAGE", "Person", "Department", "人员管理部门", aliases=["MANAGE_ORG"]),
    _rel("REPORT_TO", "Person", "Person", "汇报关系", "n:1"),
    _rel("PARENT_OF", "Organization", "Organization", "上级组织包含下级", "1:n"),
    _rel("PARENT_OF", "Organization", "Department", "组织包含部门", "1:n"),
    # B. 项目 / 任务
    _rel("OWNER", "Person", "Project", "遗留：项目挂名负责人。语义等同 OrgResponsibility，不能推出技术贡献或能力", "n:1", aliases=["ORG_RESPONSIBILITY"]),
    _rel("ORG_RESPONSIBILITY", "Person", "Project", "组织责任：谁在编制上对项目负责。不能推出实际贡献或能力", aliases=["OWNER"]),
    _rel("EXECUTION_RESPONSIBILITY", "Person", "Project", "执行责任：谁实际把项目做出来"),
    _rel("MANAGEMENT_RESPONSIBILITY", "Person", "Project", "管理责任：谁做项目管理。只能推出承担管理责任，不能推出技术能力"),
    _rel("REPORTING_RESPONSIBILITY", "Person", "Project", "汇报责任：谁对项目/成果做汇报。汇报 ≠ 创造"),
    _rel("REPORTING_RESPONSIBILITY", "Person", "Achievement", "对成果的汇报责任"),
    _rel("HAS_STAGE", "Project", "ProjectStage", "项目包含阶段", "1:n"),
    _rel("BELONG_TO", "ProjectStage", "Project", "阶段从属于项目", "n:1", aliases=["BELONGS_TO"]),
    _rel("PRODUCED", "Project", "Achievement", "项目产出成果"),
    _rel("PRODUCED", "ProjectStage", "Achievement", "阶段产出成果"),
    _rel("PRODUCED", "Event", "Achievement", "事件达成成果"),
    _rel("ACHIEVEMENT_OWNERSHIP", "Person", "Achievement", "成果组织/业务归属。不能作为能力或实际贡献的推理依据"),
    _rel("MADE_CONTRIBUTION", "Person", "Contribution", "人对贡献实例：实际做了什么"),
    _rel("CONTRIBUTES_TO", "Contribution", "Achievement", "该贡献作用于哪项成果"),
    _rel("PERFORMED_TRAINING", "Person", "TrainingAction", "实施了培养行为。培养是行为证据，不是职位关系"),
    _rel("TRAINING_TARGET", "TrainingAction", "Person", "培养行为的对象"),
    _rel("HAS_CAPABILITY_EVIDENCE", "Person", "CapabilityEvidence", "拥有一条能力证据（证据 ≠ 掌握）"),
    _rel("EVIDENCES_CAPABILITY", "CapabilityEvidence", "Capability", "该证据指向哪项能力，不做一次贡献=掌握"),
    _rel("CONTRIBUTES_TO", "Contribution", "CapabilityEvidence", "贡献可支撑能力证据"),
    _rel("CORE_MEMBER", "Person", "Project", "项目核心成员"),
    _rel("PARTICIPATE", "Person", "Project", "参与项目", aliases=["WORKS_ON"]),
    _rel("SUPPORT", "Person", "Project", "支持项目"),
    _rel("RESPONSIBLE_FOR", "Person", "Task", "任务责任人", "n:1"),
    _rel("PARTICIPATE", "Person", "Task", "参与任务"),
    _rel("BELONG_TO", "Project", "Organization", "项目归属组织", "n:1", aliases=["BELONGS_TO"]),
    _rel("BELONG_TO", "Project", "Department", "项目归属部门", "n:1", aliases=["BELONGS_TO"]),
    _rel("HAS_TASK", "Project", "Task", "项目包含任务", "1:n"),
    _rel("BELONG_TO", "Task", "Project", "任务从属于项目", "n:1", aliases=["BELONGS_TO"]),
    _rel("DEPEND_ON", "Project", "Project", "项目依赖项目"),
    _rel("DEPEND_ON", "Task", "Task", "任务依赖任务"),
    # C. 事件
    _rel("ACTOR_OF", "Person", "Event", "事件主角/执行者", sources=["event", "human"], aliases=["INVOLVED_IN"]),
    _rel("RELATED_TO", "Event", "Project", "事件关联项目"),
    _rel("RELATED_TO", "Event", "TrainingAction", "事件中出现培养行为（不因此写出 MENTOR）"),
    _rel("EXECUTES", "Event", "Task", "事件执行了某项计划任务"),
    _rel("INVOLVES", "Event", "Person", "事件涉及人员"),
    _rel("PRODUCES", "Event", "Resource", "事件产出资源"),
    _rel("SUPPORTED_BY", "Event", "Evidence", "事件由证据支撑", "n:n", sources=["event", "human"]),
    # D. 角色 / 能力
    _rel("HAS_ROLE", "Person", "Role", "担任角色"),
    _rel("SERVES_AS", "Person", "Role", "在具体情境中担任角色"),
    _rel("REQUIRES_CAPABILITY", "Role", "Capability", "角色要求能力"),
    _rel("HAS_CAPABILITY", "Person", "Capability", "当前能力画像。禁止从 OWNER / 管理责任直接写入"),
    _rel("DEMONSTRATED_CAPABILITY", "Person", "Capability", "有证据支撑的能力实证。证据应来自 Contribution + Achievement，而非职位", sources=["event", "human"]),
    _rel("USES_AI_CAPABILITY", "Person", "AI_Capability", "使用过该 AI 能力"),
    _rel("DEMONSTRATES_AI_CAPABILITY", "Person", "AI_Capability", "有证据表明完成了该 AI 能力转型", sources=["event", "human"]),
    _rel("REQUIRES_AI_CAPABILITY", "Role", "AI_Capability", "角色要求 AI 能力"),
    # E. 评价
    _rel("EVALUATES", "Person", "Person", "人员评价人员"),
    _rel("TARGETS", "Evaluation", "Person", "评价指向被评价人", "n:1"),
    _rel("BASED_ON", "Evaluation", "Evidence", "评价基于证据"),
    # F. 人际关系
    _rel("COLLABORATE", "Person", "Person", "协作", symmetric=True, aliases=["COLLABORATE_WITH"]),
    _rel("MENTOR", "Person", "Person", "指导（遗留简写）。规范路径是 Person → TrainingAction → Person，禁止从 REPORT_TO 推出"),
    _rel("DEPEND_ON", "Person", "Person", "人际依赖"),
    _rel("ALLY", "Person", "Person", "同盟", symmetric=True),
    _rel("COMPETE", "Person", "Person", "竞争", symmetric=True),
    _rel("CONFLICT", "Person", "Person", "冲突"),
    # G. 资源
    _rel("OWNS_RESOURCE", "Person", "Resource", "拥有资源", aliases=["CONTROL_RESOURCE"]),
    _rel("PROVIDES_RESOURCE", "Person", "Resource", "提供资源"),
    _rel("NEEDS_RESOURCE", "Person", "Resource", "需要资源"),
    _rel("CONNECTED_TO_RESOURCE", "Person", "Resource", "连接到资源"),
    _rel("USES_RESOURCE", "Project", "Resource", "项目使用资源", aliases=["USES", "HAS_RESOURCE"]),
    # H. 遗留图关系：资源层级 / 知识 / 推断边
    _rel("IS_A", "Resource", "Resource", "资源实例属于资源总类", "n:1", temporal=False),
    _rel("PART_OF", "Resource", "Resource", "明细从属于总类", "n:1", temporal=False),
    _rel("HAS_SUB_RESOURCE", "Resource", "Resource", "资源总类包含明细", "1:n", temporal=False),
    _rel("HAS_KNOWLEDGE", "Person", "Knowledge", "掌握知识主题；能力请走 Capability + Evidence"),
    _rel("MANAGES", "Person", "Resource", "人员管理/控制资源（遗留，规范名 OWNS_RESOURCE）"),
    _rel("DEPENDS_ON", "Project", "Resource", "项目依赖某类资源能力"),
    _rel("CONTRIBUTE_TO", "Person", "Department", "遗留：人对部门贡献。禁止从 WORKS_ON/OWNER 自动推出，须经 Contribution"),
    _rel("CONTRIBUTE_TO", "Person", "Organization", "遗留：人对组织贡献。禁止从项目参与自动推出"),
    _rel("CONTROL_KEY_RESOURCE", "Person", "Project", "人员通过关键资源影响项目"),
    _rel("TRUST", "Person", "Person", "信任"),
)

DEFAULT_RULES = (
    {
        "name": "ResourceHierarchyPropagation",
        "description": "项目使用明细资源 → 同时依赖其所属交付/技术总类能力",
        "condition": [
            {"source": "?p", "relation": REL_HAS_RESOURCE, "target": "?r"},
            {"source": "?c", "relation": REL_HAS_SUB_RESOURCE, "target": "?r"},
        ],
        "action": {
            "add": [
                {"source": "?p", "relation": REL_USES, "target": "?r"},
                {"source": "?p", "relation": REL_USES, "target": "?c"},
                {"source": "?p", "relation": REL_DEPENDS_ON, "target": "?c"},
            ],
            "inheritRelation": True,
        },
    },
    {
        "name": "InstanceIsAClass",
        "description": "总类-明细边反向写成 IS_A / PART_OF，便于查询与解释",
        "condition": [
            {"source": "?c", "relation": REL_HAS_SUB_RESOURCE, "target": "?r"},
        ],
        "action": {
            "add": [
                {"source": "?r", "relation": REL_IS_A, "target": "?c"},
                {"source": "?r", "relation": REL_PART_OF, "target": "?c"},
            ],
        },
    },
    {
        "name": "ControlMeansManages",
        "description": "CONTROL_RESOURCE 增强为 MANAGES，不删除原边",
        "condition": [
            {"source": "?person", "relation": REL_CONTROL, "target": "?r"},
        ],
        "action": {
            "add": [
                {"source": "?person", "relation": REL_MANAGES, "target": "?r"},
            ],
        },
    },
    {
        "name": "KeyResourceToProject",
        "description": "人控制资源且项目产出该资源 → 人掌握项目关键资源",
        "condition": [
            {"source": "?person", "relation": REL_CONTROL, "target": "?r"},
            {"source": "?proj", "relation": REL_HAS_RESOURCE, "target": "?r"},
        ],
        "action": {
            "add": [
                {"source": "?person", "relation": REL_CONTROL_KEY, "target": "?proj"},
            ],
        },
    },
    {
        "name": "ContributeViaProjectDept",
        "description": "【已停用】人做项目不能推出对部门的实际贡献。实际贡献必须经 Contribution 节点。",
        "status": "INACTIVE",
        "condition": [
            {"source": "?person", "relation": REL_WORKS_ON, "target": "?proj"},
            {"source": "?proj", "relation": REL_BELONGS_TO, "target": "?dept"},
        ],
        "action": {
            "add": [
                {"source": "?person", "relation": REL_CONTRIBUTE_TO, "target": "?dept"},
            ],
        },
    },
    {
        "name": "ProjectDeptFromOwner",
        "description": "用负责人部门推断项目归属（推断边，可回滚）",
        "condition": [
            {"source": "?person", "relation": REL_OWNER, "target": "?proj"},
            {"source": "?person", "relation": REL_BELONGS_TO, "target": "?dept"},
        ],
        "action": {
            "add": [
                {"source": "?proj", "relation": REL_BELONGS_TO, "target": "?dept"},
            ],
        },
    },
)


def _type_id(name):
    return "ot_" + str(name).lower()


def seed_ontology(force=False):
    store = get_kg_store()
    if store.list_types() and not force:
        if not store.list_rules():
            _seed_rules(store)
        ensure_property_schemas(store)
        return {"seeded": False, "types": len(store.list_types())}

    store.snapshot(reason="seed-ontology")
    ids = {}
    for gtype in NODE_TYPES:
        oname = GRAPH_TO_ONTOLOGY.get(gtype, gtype)
        if oname in store.retired_type_names():
            continue
        rec = store.upsert_type({
            "id": _type_id(oname),
            "name": oname,
            "parent_id": None,
            "description": CORE_TYPE_DESCRIPTIONS.get(oname) or f"由现有图谱节点类型 {gtype} 反向生成",
            "schema": normalize_type_schema(oname, TYPE_SCHEMAS.get(oname) or TYPE_SCHEMAS.get(gtype) or {}, replace_properties=True),
        })
        ids[oname] = rec["id"]

    resource_id = ids.get("Resource")
    for sub in RESOURCE_SUBTYPES:
        rec = store.upsert_type({
            "id": _type_id(sub["name"]),
            "name": sub["name"],
            "parent_id": resource_id,
            "description": sub["description"],
            "schema": normalize_type_schema(sub["name"], {
                "label": sub["label"], "match": sub["match"],
            }, replace_properties=True),
        })
        ids[sub["name"]] = rec["id"]

    ensure_core_types(store, replace_properties=True)
    _seed_relations(store)
    _seed_rules(store)
    store.set_meta("ontology_seeded", "1")
    store.set_meta("property_schema_v1", "1")
    store.set_meta("ontology_spec", ONTOLOGY_SPEC)
    return {"seeded": True, "types": len(store.list_types()), "rules": len(store.list_rules())}


def ensure_property_schemas(store=None):
    store = store or get_kg_store()
    replace = store.get_meta("ontology_spec") != ONTOLOGY_SPEC
    if replace:
        store.snapshot(reason=f"ontology-spec:{ONTOLOGY_SPEC}")
    ensure_core_types(store, replace_properties=replace)
    if replace:
        _migrate_legacy_relations(store)
    for t in store.list_types():
        replace_this = replace and (
            t["name"] in REPLACEABLE_TYPE_NAMES
            or (t["name"].endswith("Resource") and t["name"] != "Resource")
        )
        normalized = normalize_type_schema(
            t["name"], t.get("schema"),
            replace_properties=replace_this,
        )
        desc = t.get("description") or ""
        new_desc = CORE_TYPE_DESCRIPTIONS.get(t["name"])
        if new_desc and (replace or not desc or "反向生成" in desc):
            desc = new_desc
        if normalized != (t.get("schema") or {}) or desc != (t.get("description") or ""):
            store.upsert_type({**t, "description": desc, "schema": normalized})
    _seed_relations(store)
    store.set_meta("property_schema_v1", "1")
    store.set_meta("ontology_spec", ONTOLOGY_SPEC)
    ensure_semantic_guardrails(store)
    return {"types": len(store.list_types()), "spec": ONTOLOGY_SPEC, "replaced": replace}


def ensure_core_types(store, replace_properties=False):
    by_name = {t["name"]: t for t in store.list_types()}
    retired = store.retired_type_names()

    def _upsert(name, parent_name=None):
        if name in retired:
            return None
        parent_id = (by_name.get(parent_name) or {}).get("id") if parent_name else None
        existing = by_name.get(name)
        if existing and not replace_properties:
            if parent_name and existing.get("parent_id") != parent_id and parent_id:
                rec = store.upsert_type({**existing, "parent_id": parent_id})
                by_name[name] = rec
                return rec
            return existing
        existing_desc = (existing or {}).get("description") or ""
        canned = CORE_TYPE_DESCRIPTIONS.get(name) or ""
        desc = canned if canned and (replace_properties or not existing_desc or "反向生成" in existing_desc) else existing_desc or canned
        rec = store.upsert_type({
            "id": (existing or {}).get("id") or _type_id(name),
            "name": name,
            "parent_id": parent_id if parent_name else (existing or {}).get("parent_id"),
            "description": desc,
            "schema": normalize_type_schema(
                name,
                (existing or {}).get("schema") or TYPE_SCHEMAS.get(name) or {},
                replace_properties=replace_properties,
            ),
        })
        by_name[name] = rec
        return rec

    for name in CORE_TYPE_NAMES:
        _upsert(name)
    for name in SPECIAL_TYPE_NAMES:
        _upsert(name)
    _upsert("Department", "Organization")
    resource_id = (by_name.get("Resource") or {}).get("id")
    for sub in RESOURCE_SUBTYPES:
        if sub["name"] in retired:
            continue
        existing = by_name.get(sub["name"])
        if existing and not replace_properties:
            if existing.get("parent_id") != resource_id and resource_id:
                rec = store.upsert_type({**existing, "parent_id": resource_id})
                by_name[sub["name"]] = rec
            continue
        rec = store.upsert_type({
            "id": (existing or {}).get("id") or _type_id(sub["name"]),
            "name": sub["name"],
            "parent_id": resource_id,
            "description": (existing or {}).get("description") or sub["description"],
            "schema": normalize_type_schema(sub["name"], {
                **((existing or {}).get("schema") or {}),
                "label": sub["label"],
                "match": sub["match"],
            }, replace_properties=replace_properties),
        })
        by_name[sub["name"]] = rec

    contrib_id = (by_name.get("Contribution") or {}).get("id")
    for sub in CONTRIBUTION_SUBTYPES:
        _upsert_leaf(store, by_name, retired, sub, contrib_id, replace_properties,
                     f"贡献子类：{sub['label']}。图谱 type 仍为 Contribution，用 contribution_type 区分。")
    train_id = (by_name.get("TrainingAction") or {}).get("id")
    for sub in TRAINING_SUBTYPES:
        _upsert_leaf(store, by_name, retired, sub, train_id, replace_properties,
                     f"培养行为子类：{sub['label']}。图谱 type 仍为 TrainingAction。")


def _upsert_leaf(store, by_name, retired, sub, parent_id, replace_properties, default_desc):
    if sub["name"] in retired:
        return
    existing = by_name.get(sub["name"])
    if existing and not replace_properties:
        if parent_id and existing.get("parent_id") != parent_id:
            rec = store.upsert_type({**existing, "parent_id": parent_id})
            by_name[sub["name"]] = rec
        return
    rec = store.upsert_type({
        "id": (existing or {}).get("id") or _type_id(sub["name"]),
        "name": sub["name"],
        "parent_id": parent_id,
        "description": (existing or {}).get("description") or default_desc,
        "schema": normalize_type_schema(sub["name"], {
            **((existing or {}).get("schema") or {}),
            "label": sub["label"],
            "match": sub["match"],
        }, replace_properties=replace_properties),
    })
    by_name[sub["name"]] = rec


LEGACY_RELATION_RENAMES = (
    ("BELONGS_TO", "Person", "Department", "BELONG_TO", "Person", "Department", ["BELONGS_TO"]),
    ("BELONGS_TO", "Project", "Department", "BELONG_TO", "Project", "Department", ["BELONGS_TO"]),
    ("WORKS_ON", "Person", "Project", "PARTICIPATE", "Person", "Project", ["WORKS_ON"]),
    ("COLLABORATE_WITH", "Person", "Person", "COLLABORATE", "Person", "Person", ["COLLABORATE_WITH"]),
    ("INVOLVED_IN", "Person", "Event", "ACTOR_OF", "Person", "Event", ["INVOLVED_IN"]),
    ("USES", "Project", "Resource", "USES_RESOURCE", "Project", "Resource", ["USES", "HAS_RESOURCE"]),
    ("USES", "Project", "DeliveryResource", "USES_RESOURCE", "Project", "DeliveryResource", ["USES"]),
    ("HAS_RESOURCE", "Project", "Resource", "USES_RESOURCE", "Project", "Resource", ["USES", "HAS_RESOURCE"]),
    ("INFORMAL_MEMBER", "Person", "Organization", "BELONG_TO", "Person", "Organization", ["BELONGS_TO", "INFORMAL_MEMBER"]),
    ("CONTROL_RESOURCE", "Person", "Resource", "OWNS_RESOURCE", "Person", "Resource", ["CONTROL_RESOURCE"]),
    ("IS_A", "Resource", "DeliveryResource", "IS_A", "Resource", "Resource", []),
    ("PART_OF", "Resource", "DeliveryResource", "PART_OF", "Resource", "Resource", []),
)


def _migrate_legacy_relations(store):
    for old_n, old_s, old_t, new_n, new_s, new_t, aliases in LEGACY_RELATION_RENAMES:
        old = store.find_ontology_relation(old_n, old_s, old_t)
        if not old:
            continue
        new = store.find_ontology_relation(new_n, new_s, new_t)
        merged_aliases = list(dict.fromkeys(list(aliases) + list((old.get("rule") or {}).get("aliases") or [])))
        if old_n != new_n:
            merged_aliases = list(dict.fromkeys([old_n, *merged_aliases]))
        payload = {
            **old,
            "name": new_n,
            "source_type": new_s,
            "target_type": new_t,
            "rule": normalize_relation_rule({**(old.get("rule") or {}), "aliases": merged_aliases}),
        }
        if new and new["id"] != old["id"]:
            store.delete_ontology_relation(old["id"])
            store.upsert_ontology_relation({
                **new,
                "description": new.get("description") or old.get("description") or "",
                "rule": normalize_relation_rule({
                    **(new.get("rule") or {}),
                    "aliases": list(dict.fromkeys(
                        list((new.get("rule") or {}).get("aliases") or []) + merged_aliases
                    )),
                }),
            })
        else:
            store.upsert_ontology_relation(payload)


def _seed_relations(store):
    type_names = {t["name"] for t in store.list_types()}
    retired = store.retired_type_names()
    for rel in ALLOWED_RELATIONS:
        src, tgt = rel["source_type"], rel["target_type"]
        if src in retired or tgt in retired:
            continue
        if src not in type_names or tgt not in type_names:
            continue
        existing = store.find_ontology_relation(rel["name"], src, tgt)
        wanted = normalize_relation_rule(rel.get("rule"))
        if existing:
            rule = existing.get("rule") or {}
            aliases = list(dict.fromkeys(list(rule.get("aliases") or []) + list(wanted.get("aliases") or [])))
            needs = (
                not rule.get("cardinality")
                or aliases != list(rule.get("aliases") or [])
                or (not existing.get("description") and rel.get("description"))
            )
            if needs:
                store.upsert_ontology_relation({
                    **existing,
                    "description": existing.get("description") or rel.get("description") or "",
                    "rule": normalize_relation_rule({**wanted, **rule, "aliases": aliases}),
                })
            continue
        store.upsert_ontology_relation({
            **rel,
            "rule": wanted,
        })


def _seed_rules(store):
    existing = {r["name"]: r for r in store.list_rules(include_inactive=True)}
    for rule in DEFAULT_RULES:
        prev = existing.get(rule["name"])
        if prev and rule["name"] != "ContributeViaProjectDept":
            continue
        payload = dict(rule)
        if prev:
            payload["id"] = prev["id"]
        store.upsert_rule(payload)
    ensure_semantic_guardrails(store)


def ensure_semantic_guardrails(store=None):
    """写入禁止跨语义域推理的规则，并停用非法贡献推导。"""
    store = store or get_kg_store()
    from .semantic_domains import FORBIDDEN_RULES, META_RULES, CONTRIBUTE_VIA_PROJECT_RULE

    by_name = {r["name"]: r for r in store.list_rules(include_inactive=True)}
    illegal = by_name.get(CONTRIBUTE_VIA_PROJECT_RULE)
    if illegal and illegal.get("status") != "INACTIVE":
        store.upsert_rule({
            **illegal,
            "status": "INACTIVE",
            "description": "【已停用】人做项目不能推出对部门的实际贡献。实际贡献必须经 Contribution 节点。",
        })
    for rule in FORBIDDEN_RULES:
        prev = by_name.get(rule["name"])
        store.upsert_rule({**(prev or {}), **rule, "id": rule.get("id") or (prev or {}).get("id")})

    existing_c = {c.get("id"): c for c in store.list_constraints()}
    cid = "auto:meta:cross_domain:forbid"
    if cid not in existing_c:
        store.upsert_constraint({
            "id": cid,
            "name": "CrossDomainNoFreeInference",
            "kind": "semantic",
            "code": "cross_domain",
            "object_type": "Fact",
            "message": "事实可以证明事实；事实不能跨语义域无条件推理。" + "；".join(META_RULES),
            "status": "ACTIVE",
            "origin": "schema",
            "expression": {"meta_rules": list(META_RULES)},
        })
    _seed_relations(store)


def classify_resource_subtype(node) -> str:
    name = (node.get("name") or "").strip()
    category = node.get("category") or ""
    kind = node.get("resource_kind")
    if name in {c["name"] for c in RESOURCE_CLASSES} or kind == "class":
        mapping = {
            "交付资源": "DeliveryResource",
            "技术资源": "TechnicalResource",
            "数据资源": "DataResource",
            "客户资源": "BusinessResource",
            "预算资源": "BusinessResource",
        }
        return mapping.get(name) or "Resource"
    if name.endswith("交付资源") or category in ("delivery", "project"):
        return "DeliveryResource"
    if category == "tech":
        return "TechnicalResource"
    if category == "data":
        return "DataResource"
    if category in ("customer", "budget"):
        return "BusinessResource"
    return "Resource"
