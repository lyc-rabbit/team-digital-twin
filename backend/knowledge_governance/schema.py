"""本体属性 Schema / 关系 Schema / 约束编译。

属性属于类型自身特征；关系是类型之间的连接。约束从 Schema 编译，也可额外手写。
"""

DATA_TYPES = (
    "String", "Text", "Integer", "Float", "Boolean",
    "Date", "DateTime", "Enum", "EntityRef", "Array",
)

SOURCES = ("hr", "human", "llm", "inferred", "event")

SOURCE_LABELS = {
    "hr": "HR系统",
    "human": "人工",
    "llm": "AI抽取",
    "inferred": "推理",
    "event": "事件证据",
}

CARDINALITIES = ("1:1", "1:n", "n:1", "n:n")


def _p(name, data_type="String", **kw):
    prop = {
        "name": name,
        "label": kw.get("label") or name,
        "data_type": data_type,
        "required": bool(kw.get("required")),
        "unique": bool(kw.get("unique")),
        "enum_values": list(kw.get("enum_values") or []),
        "enum_aliases": dict(kw.get("enum_aliases") or {}),
        "min": kw.get("min"),
        "max": kw.get("max"),
        "default": kw.get("default"),
        "sources": list(kw.get("sources") or ["human", "llm"]),
        "match": bool(kw.get("match", False)),
        "extract": bool(kw.get("extract", True)),
        "ref_type": kw.get("ref_type") or "",
        "description": kw.get("description") or "",
    }
    return prop


ONTOLOGY_SPEC = "twin_v3"

CORE_TYPE_NAMES = (
    "Person", "Organization", "Project", "ProjectStage", "Task", "Event",
    "Role", "Capability", "Evaluation", "AI_Capability", "Resource",
    "Achievement", "Contribution", "TrainingAction", "CapabilityEvidence",
)

SPECIAL_TYPE_NAMES = ("Relationship", "Evidence")

CORE_TYPE_DESCRIPTIONS = {
    "Person": "谁？数字孪生核心节点。能力、项目、同事必须用关系，不能写成人员字段。",
    "Organization": "公司/部门/团队/小组。Department 是组织的一种形态。",
    "Project": "长期业务对象。不是 Task，也不是 Event。谁负责要拆成组织/执行/管理/汇报责任，不能用一条 OWNER 推出贡献或能力。",
    "ProjectStage": "项目阶段。成果挂阶段，不要把阶段写成 Project 字段列表。",
    "Achievement": "客观产生的结果（上线/交付/指标），不是某个人的属性。归属用 AchievementOwnership，实际做什么用 Contribution。",
    "Contribution": "某人对某成果实际做了什么。必须带 contribution_type；汇报贡献 ≠ 技术贡献。",
    "TrainingAction": "实际发生的培养行为。不能因为上级关系就认为发生了培养。",
    "CapabilityEvidence": "能力证据，不是能力掌握。一次贡献不能直接写成 HAS_CAPABILITY。",
    "Task": "计划要做什么。从属于 Project。",
    "Event": "实际发生了什么。是事实层，不是计划。",
    "Role": "在组织/项目中承担的角色。职位 ≠ 角色，一人可多角色。",
    "Capability": "具备什么能力。实证必须走 DEMONSTRATED_CAPABILITY + Evidence。",
    "Evaluation": "别人如何评价他。指向 Person，并基于 Evidence。",
    "AI_Capability": "AI 能力本身，不要写进 Person。区分「用过 AI」和「完成 AI Native 转型」。",
    "Resource": "能调动的资源。支撑人际关系网，不要做成人员属性。",
    "Relationship": "关系实例：类型、强度、时间、证据、状态。不是枚举字段。",
    "Evidence": "凭什么认为这个事实为真。来源可以是日报/会议/评价/任务/人工。",
    "Department": "组织的部门形态，属性与 Organization 相同，type=department。",
    "Knowledge": "遗留知识主题。能力请用 Capability，不要把技能写进 Person。",
}

STATUS_ALIASES = {
    "finished": "completed", "done": "completed", "end": "completed",
    "complete": "completed", "已完成": "completed", "结束": "completed",
    "active": "running", "进行中": "running", "in_progress": "running",
    "pause": "running", "暂停": "running", "paused": "running",
    "cancel": "failed", "取消": "failed", "cancelled": "failed",
    "fail": "failed", "失败": "failed",
    "plan": "planning", "规划中": "planning",
}

PERSON_STATUS_ALIASES = {
    "active": "在职", "employed": "在职", "onboard": "在职",
    "left": "离职", "resigned": "离职", "quit": "离职",
    "transfer": "转岗", "moved": "转岗",
}

_ORG_PROPS = [
    _p("id", unique=True, match=True, extract=False, sources=["hr"], label="ID", description="唯一ID"),
    _p("name", required=True, unique=True, match=True, sources=["hr", "human"], label="名称", description="名称"),
    _p("type", "Enum", enum_values=["company", "department", "team", "group"], default="department",
       sources=["hr", "human"], label="组织类型", description="组织类型：company/department/team/group"),
    _p("parent_id", "EntityRef", ref_type="Organization", extract=False, sources=["hr", "human"],
       label="上级组织", description="上级组织。图上用 PARENT_OF / BELONG_TO 表达"),
    _p("status", "Enum", enum_values=["ACTIVE", "INACTIVE"], default="ACTIVE", sources=["hr", "human"],
       label="状态", description="当前状态"),
    _p("start_date", "Date", sources=["hr", "human"], extract=False, label="成立时间", description="成立时间"),
    _p("end_date", "Date", sources=["hr", "human"], extract=False, label="结束时间", description="结束时间"),
]

DEFAULT_PROPERTIES = {
    "Person": [
        _p("id", unique=True, match=True, extract=False, sources=["hr"], label="ID", description="唯一ID"),
        _p("name", required=True, unique=True, match=True, sources=["hr", "human"], label="姓名", description="姓名"),
        _p("employee_no", unique=True, match=True, sources=["hr"], extract=False, label="员工标识", description="员工标识"),
        _p("position", sources=["hr", "human"], match=True, label="当前职位",
           description="当前职位。职位 ≠ 角色，角色用 HAS_ROLE → Role"),
        _p("level", sources=["hr", "human"], label="职级", description="职级"),
        _p("status", "Enum", enum_values=["在职", "离职", "转岗"],
           enum_aliases=PERSON_STATUS_ALIASES, default="在职", sources=["hr", "human"],
           label="状态", description="在职/离职/转岗等"),
        _p("join_date", "Date", sources=["hr", "human"], extract=False, label="入职时间", description="入职时间"),
        _p("leave_date", "Date", sources=["hr", "human"], extract=False, label="离职时间", description="离职时间"),
        _p("profile", "Text", sources=["hr", "human"], label="人员基础描述", description="人员基础描述"),
    ],
    "Organization": [dict(p) for p in _ORG_PROPS],
    "Department": [
        dict(p, default="department") if p["name"] == "type" else dict(p) for p in _ORG_PROPS
    ],
    "Project": [
        _p("id", unique=True, match=True, extract=False, sources=["human"], label="ID", description="项目ID"),
        _p("name", required=True, unique=True, match=True, label="项目名称", description="项目名称"),
        _p("description", "Text", label="项目描述", description="项目描述"),
        _p("type", label="项目类型", description="项目类型"),
        _p("priority", "Enum", enum_values=["P0", "P1", "P2"], default="P1", label="优先级", description="优先级"),
        _p("status", "Enum", required=True,
           enum_values=["planning", "running", "completed", "failed"],
           enum_aliases=STATUS_ALIASES, default="running",
           label="状态", description="planning/running/completed/failed"),
        _p("stage", label="当前阶段", description="当前阶段"),
        _p("start_date", "Date", label="开始", description="开始"),
        _p("planned_end_date", "Date", label="计划结束", description="计划结束"),
        _p("actual_end_date", "Date", sources=["human", "event"], label="实际结束", description="实际结束"),
        _p("goal", "Text", label="项目目标", description="项目目标"),
    ],
    "ProjectStage": [
        _p("id", unique=True, match=True, extract=False, sources=["human"], label="ID", description="阶段ID"),
        _p("name", required=True, match=True, label="阶段名称", description="阶段名称"),
        _p("stage_name", label="阶段名", description="与 name 相同的展示名"),
        _p("status", "Enum", enum_values=["planning", "running", "completed", "failed"], default="running",
           label="状态", description="阶段状态"),
    ],
    "Achievement": [
        _p("id", unique=True, match=True, extract=False, sources=["human"], label="ID", description="成果ID"),
        _p("name", required=True, unique=True, match=True, label="成果名称", description="客观结果名称，不是某人的属性"),
        _p("achievement_type", "Enum",
           enum_values=["launch", "delivery", "metric", "proposal", "patent", "other"],
           enum_aliases={"上线": "launch", "交付": "delivery", "指标": "metric", "方案": "proposal", "专利": "patent"},
           default="delivery", label="成果类型", description="上线/交付/指标/方案/专利"),
        _p("start_time", "DateTime", sources=["human", "event"], label="开始时间", description="开始时间"),
        _p("achieved_time", "DateTime", sources=["human", "event"], label="达成时间", description="达成时间"),
        _p("evidence", "Text", sources=["human", "event"], label="证据", description="证据原文"),
        _p("confidence", "Float", min=0, max=1, default=0.7, extract=False, sources=["llm", "inferred"],
           label="可信度", description="可信度"),
        _p("status", "Enum", enum_values=["ACTIVE", "INACTIVE"], default="ACTIVE", label="状态", description="有效/失效"),
    ],
    "Contribution": [
        _p("id", unique=True, match=True, extract=False, sources=["human"], label="ID", description="贡献ID"),
        _p("name", required=True, match=True, label="名称", description="贡献实例名称"),
        _p("contribution_type", "Enum", required=True,
           enum_values=[
               "technical", "architecture", "product", "project_management",
               "resource", "decision", "coordination", "training", "reporting",
           ],
           enum_aliases={
               "技术": "technical", "开发": "technical", "架构": "architecture",
               "产品": "product", "项目管理": "project_management", "管理": "project_management",
               "资源": "resource", "决策": "decision", "协调": "coordination",
               "培养": "training", "汇报": "reporting",
           },
           default="technical", label="贡献类型",
           description="必须拆开：技术/架构/产品/项目管理/资源/决策/协调/培养/汇报。汇报 ≠ 成果产生"),
        _p("contribution_level", "Enum",
           enum_values=["lead", "core", "important", "support"],
           enum_aliases={"主导": "lead", "核心": "core", "重要": "important", "辅助": "support"},
           default="important", label="贡献程度", description="主导/核心/重要/辅助"),
        _p("workload", "Float", min=0, sources=["human"], extract=False, label="工作量", description="可选工作量"),
        _p("evidence_level", "Enum", enum_values=["strong", "medium", "weak"],
           enum_aliases={"强": "strong", "中": "medium", "弱": "weak"},
           default="medium", label="证据强度", description="强/中/弱"),
        _p("start_time", "DateTime", sources=["human", "event"], label="开始", description="开始"),
        _p("end_time", "DateTime", sources=["human", "event"], label="结束", description="结束"),
        _p("source", sources=["human", "event"], extract=False, label="来源事实", description="来源事实 ID"),
        _p("confidence", "Float", min=0, max=1, default=0.7, extract=False, sources=["llm", "inferred"],
           label="可信度", description="可信度"),
        _p("status", "Enum", enum_values=["ACTIVE", "EXPIRED", "DISPUTED"], default="ACTIVE",
           label="状态", description="Active/Expired/Disputed"),
    ],
    "TrainingAction": [
        _p("id", unique=True, match=True, extract=False, sources=["human"], label="ID", description="培养行为ID"),
        _p("name", required=True, match=True, label="名称", description="培养行为名称"),
        _p("action_type", "Enum",
           enum_values=["指导", "反馈", "教学", "Code Review", "带教", "其他"],
           default="指导", label="行为类型", description="指导/反馈/教学/Code Review"),
        _p("duration", label="时长", description="如 2小时"),
        _p("frequency", label="频率", description="如 每周"),
        _p("target_capability", label="目标能力", description="此次培养针对的能力"),
        _p("evidence", "Text", sources=["human", "event"], label="证据", description="会议记录等"),
        _p("result", "Text", sources=["human"], label="结果", description="如能力提升观察"),
        _p("confidence", "Float", min=0, max=1, default=0.7, extract=False, sources=["llm", "inferred"],
           label="可信度", description="可信度"),
    ],
    "CapabilityEvidence": [
        _p("id", unique=True, match=True, extract=False, sources=["inferred"], label="ID", description="能力证据ID"),
        _p("name", required=True, match=True, label="名称", description="证据名称"),
        _p("capability_name", label="能力名", description="指向的能力"),
        _p("evidence_level", "Enum", enum_values=["strong", "medium", "weak"], default="medium",
           label="证据强度", description="单次贡献默认弱/中，需多独立事实才强"),
        _p("independence", "Text", extract=False, sources=["inferred", "human"], label="独立性", description="是否独立于职位/归属"),
        _p("quality", "Text", sources=["human"], label="成果质量", description="成果质量"),
        _p("persistence", "Text", sources=["human"], label="持续性", description="持续性"),
        _p("complexity", "Text", sources=["human"], label="复杂度", description="复杂度"),
        _p("evaluation", "Text", sources=["human"], label="他人评价", description="他人评价"),
        _p("confidence", "Float", min=0, max=1, default=0.5, extract=False, sources=["inferred"],
           label="可信度", description="做过一次 ≠ 掌握；需多项证据共同推理"),
        _p("status", "Enum", enum_values=["candidate", "confirmed", "rejected"], default="candidate",
           extract=False, sources=["human", "inferred"], label="状态", description="候选/确认/驳回"),
    ],
    "Task": [
        _p("id", unique=True, match=True, extract=False, sources=["human"], label="ID", description="任务ID"),
        _p("name", required=True, match=True, label="任务名称", description="任务名称"),
        _p("description", "Text", label="任务描述", description="任务描述"),
        _p("type", "Enum",
           enum_values=["development", "design", "research", "review", "ops", "other"],
           default="development", label="任务类型", description="development/design/research等"),
        _p("status", "Enum", required=True,
           enum_values=["todo", "doing", "done", "cancelled"], default="todo",
           label="状态", description="todo/doing/done/cancelled"),
        _p("priority", "Enum", enum_values=["P0", "P1", "P2"], default="P1",
           label="优先级", description="优先级"),
        _p("stage", label="所属项目阶段", description="所属项目阶段"),
        _p("planned_start", "Date", sources=["human"], label="计划开始", description="计划开始"),
        _p("deadline", "Date", sources=["human"], label="截止时间", description="截止时间"),
        _p("difficulty", "Enum", enum_values=["low", "medium", "high"], sources=["human"],
           label="难度", description="难度"),
    ],
    "Event": [
        _p("id", unique=True, match=True, extract=False, sources=["event"], label="ID", description="事件ID"),
        _p("type", "Enum",
           enum_values=[
               "WORK_EVENT", "COMMUNICATION", "DELIVERY", "DECISION", "CONFLICT",
               "LEARNING", "ROLE_CHANGE", "ORG_CHANGE", "PROJECT_CHANGE",
           ],
           enum_aliases={
               "DELIVERY_EVENT": "DELIVERY", "MEETING": "COMMUNICATION", "COACHING": "LEARNING",
               "OTHER": "WORK_EVENT",
           },
           sources=["human", "llm", "event"], label="事件类型", description="事件类型"),
        _p("time", "DateTime", required=True, sources=["human", "event"], label="发生时间", description="发生时间"),
        _p("description", "Text", required=True, sources=["human", "llm", "event"],
           label="事件描述", description="事件描述"),
        _p("source_type", "Enum",
           enum_values=["daily_report", "project", "meeting", "chat", "evaluation", "task", "system", "human"],
           default="human", extract=False, label="来源类型", description="来源类型"),
        _p("source_id", extract=False, sources=["event", "human"], label="来源ID", description="来源ID"),
        _p("confidence", "Float", min=0, max=1, default=0.6, extract=False, sources=["llm", "inferred"],
           label="抽取置信度", description="抽取置信度"),
        _p("status", "Enum", enum_values=["candidate", "confirmed", "rejected"], default="candidate",
           extract=False, sources=["human", "inferred"],
           label="状态", description="candidate/confirmed/rejected"),
    ],
    "Role": [
        _p("id", unique=True, match=True, extract=False, sources=["human"], label="ID", description="角色ID"),
        _p("name", required=True, unique=True, match=True, label="角色名称", description="角色名称"),
        _p("type", label="角色类型", description="角色类型。职位 ≠ 角色，如项目负责人/架构师/新人导师"),
        _p("description", "Text", label="角色定义", description="角色定义"),
        _p("responsibilities", "Text", sources=["human"], label="职责", description="职责"),
        _p("requirements", "Text", sources=["human"], label="要求",
           description="要求。人员实际能力用 HAS_CAPABILITY，不要写进 Person"),
    ],
    "Capability": [
        _p("id", unique=True, match=True, extract=False, sources=["human"], label="ID", description="能力ID"),
        _p("name", required=True, unique=True, match=True, label="能力名称", description="能力名称"),
        _p("category", label="能力分类", description="能力分类"),
        _p("description", "Text", label="定义", description="定义"),
        _p("level_definition", "Text", sources=["human"], extract=False, label="等级定义",
           description="等级定义。实证用 DEMONSTRATED_CAPABILITY + Evidence，禁止把分数写进 Person"),
    ],
    "Evaluation": [
        _p("id", unique=True, match=True, extract=False, sources=["human"], label="ID", description="评价ID"),
        _p("evaluator", "EntityRef", ref_type="Person", sources=["human"], label="评价人", description="评价人"),
        _p("target", "EntityRef", ref_type="Person", sources=["human"], label="被评价人", description="被评价人"),
        _p("dimension", sources=["human"], label="评价维度", description="评价维度"),
        _p("score", "Float", min=0, max=10, sources=["human", "event"], label="分数", description="分数"),
        _p("comment", "Text", sources=["human"], label="评价内容", description="评价内容"),
        _p("time", "DateTime", sources=["human", "event"], label="评价时间", description="评价时间"),
        _p("confidence", "Float", min=0, max=1, default=0.7, extract=False,
           label="可信度", description="可信度"),
        _p("source", sources=["human", "event"], label="来源", description="来源"),
    ],
    "AI_Capability": [
        _p("id", unique=True, match=True, extract=False, sources=["human"], label="ID", description="ID"),
        _p("name", required=True, unique=True, match=True, label="AI能力名称", description="AI能力名称"),
        _p("category", "Enum",
           enum_values=["coding", "research", "planning", "testing", "analysis", "agent", "other"],
           default="other", label="分类", description="coding/research/planning等"),
        _p("description", "Text", label="能力定义", description="能力定义"),
    ],
    "Resource": [
        _p("id", unique=True, match=True, extract=False, sources=["human"], label="ID", description="ID"),
        _p("name", required=True, match=True, label="名称", description="名称"),
        _p("type", "Enum",
           enum_values=["tech", "customer", "vendor", "information", "expert", "project", "permission", "external", "other"],
           enum_aliases={"data": "information", "budget": "project", "delivery": "project", "human": "expert"},
           label="资源类型", description="资源类型"),
        _p("value", "Text", label="资源价值描述", description="资源价值描述"),
        _p("status", "Enum", enum_values=["ACTIVE", "INACTIVE"], default="ACTIVE",
           label="状态", description="状态"),
    ],
    "Relationship": [
        _p("id", unique=True, extract=False, sources=["inferred"], label="ID", description="关系实例ID"),
        _p("source", "EntityRef", extract=False, label="起点", description="关系起点"),
        _p("target", "EntityRef", extract=False, label="终点", description="关系终点"),
        _p("type", label="关系类型",
           description="关系类型，如 COLLABORATION/MENTOR。不要把好友写成 Person 字段"),
        _p("strength", "Float", min=0, max=1, default=0.5, sources=["inferred", "event"],
           label="强度", description="关系强度"),
        _p("start_time", "DateTime", sources=["event", "human"], label="开始时间", description="开始时间"),
        _p("end_time", "DateTime", sources=["event", "human"], label="结束时间", description="结束时间"),
        _p("status", "Enum", enum_values=["ACTIVE", "INACTIVE"], default="ACTIVE",
           label="状态", description="状态，如 ACTIVE"),
    ],
    "Evidence": [
        _p("id", unique=True, extract=False, sources=["event"], label="ID", description="证据ID"),
        _p("source_type", "Enum",
           enum_values=["daily_report", "project", "meeting", "chat", "evaluation", "task", "system", "human"],
           default="human", label="来源类型", description="来源类型：日报/项目记录/会议纪要/聊天/评价/任务记录/系统日志/人工录入"),
        _p("source_id", extract=False, sources=["event", "human"], label="来源ID", description="来源ID"),
        _p("content", "Text", sources=["human", "event"], label="内容", description="证据内容"),
        _p("author", "EntityRef", ref_type="Person", sources=["human", "event"], label="作者", description="作者"),
        _p("time", "DateTime", sources=["event", "human"], label="时间", description="时间"),
        _p("confidence", "Float", min=0, max=1, default=0.5, extract=False,
           label="可信度", description="可信度。回答：凭什么认为这个事实是真的"),
    ],
    "Knowledge": [
        _p("name", required=True, match=True, sources=["human", "llm"], label="名称", description="知识主题名称"),
        _p("domain", sources=["human", "llm"], label="领域", description="知识领域"),
    ],
}

# 属性 vs 关系：这些名字禁止再当类型字段
FORBIDDEN_AS_PROPERTY = {
    "Person": {
        "projects", "skills", "manager", "colleagues", "friends", "capability",
        "capabilities", "owner", "department", "ai_usage",
    },
    "Project": {"members", "owner", "tasks", "resources", "achievements"},
    "Task": {"assignee", "project"},
    "Role": {"required_skills", "holders"},
    "Achievement": {"owner", "contributors"},
    "Contribution": {"person", "achievement"},
    "TrainingAction": {"mentor", "mentee"},
}

DEFAULT_RELATION_RULE = {
    "cardinality": "n:n",
    "required": False,
    "symmetric": False,
    "temporal": True,
    "sources": ["human", "llm", "inferred"],
    "aliases": [],
}

REPLACEABLE_TYPE_NAMES = set(CORE_TYPE_NAMES) | set(SPECIAL_TYPE_NAMES) | {"Department", "Knowledge"}


def empty_property(name="field"):
    return _p(name, extract=True, sources=["human", "llm"])


def fill_property(raw):
    if isinstance(raw, str):
        return empty_property(raw)
    if not isinstance(raw, dict):
        return empty_property("field")
    base = empty_property(raw.get("name") or "field")
    merged = {**base, **{k: v for k, v in raw.items() if v is not None}}
    merged["enum_values"] = list(merged.get("enum_values") or [])
    merged["enum_aliases"] = dict(merged.get("enum_aliases") or {})
    merged["sources"] = list(merged.get("sources") or ["human", "llm"])
    merged["required"] = bool(merged.get("required"))
    merged["unique"] = bool(merged.get("unique"))
    merged["match"] = bool(merged.get("match"))
    merged["extract"] = bool(merged.get("extract")) if "extract" in merged else True
    dt = merged.get("data_type") or "String"
    merged["data_type"] = dt if dt in DATA_TYPES else "String"
    return merged


def default_properties(type_name):
    if type_name in DEFAULT_PROPERTIES:
        return [dict(p) for p in DEFAULT_PROPERTIES[type_name]]
    if type_name.endswith("Resource") and type_name != "Resource":
        return [dict(p) for p in DEFAULT_PROPERTIES["Resource"]]
    return [_p("name", required=True, match=True)]


def normalize_type_schema(type_name, schema, replace_properties=False):
    schema = dict(schema or {})
    defaults = default_properties(type_name)
    if replace_properties:
        schema["properties"] = [dict(p) for p in defaults]
        schema["forbidden_as_property"] = sorted(FORBIDDEN_AS_PROPERTY.get(type_name) or [])
        if "relations" not in schema:
            schema["relations"] = []
        return schema
    default_by_name = {p["name"]: dict(p) for p in defaults}
    raw = schema.get("properties")
    out = []
    seen = set()
    if isinstance(raw, list):
        for item in raw:
            if isinstance(item, str):
                filled = fill_property(default_by_name.get(item) or empty_property(item))
            else:
                name = (item or {}).get("name") or "field"
                filled = fill_property({**(default_by_name.get(name) or empty_property(name)), **item})
            name = filled["name"]
            if name in seen:
                continue
            if not str(filled.get("description") or "").strip():
                filled["description"] = (default_by_name.get(name) or {}).get("description") or ""
            seen.add(name)
            out.append(filled)
    for name, prop in default_by_name.items():
        if name not in seen:
            out.append(prop)
            seen.add(name)
    if not out:
        out = defaults
    schema["properties"] = out
    schema["forbidden_as_property"] = sorted(FORBIDDEN_AS_PROPERTY.get(type_name) or [])
    if "relations" not in schema:
        schema["relations"] = []
    return schema


def properties_of(type_rec):
    schema = normalize_type_schema((type_rec or {}).get("name") or "", (type_rec or {}).get("schema"))
    return schema.get("properties") or []


def normalize_relation_rule(rule):
    merged = {**DEFAULT_RELATION_RULE, **(rule or {})}
    merged["cardinality"] = merged.get("cardinality") if merged.get("cardinality") in CARDINALITIES else "n:n"
    merged["sources"] = list(merged.get("sources") or DEFAULT_RELATION_RULE["sources"])
    merged["aliases"] = list(merged.get("aliases") or [])
    merged["required"] = bool(merged.get("required"))
    merged["symmetric"] = bool(merged.get("symmetric"))
    merged["temporal"] = bool(merged.get("temporal")) if "temporal" in merged else True
    return merged


def relation_names_of(rel):
    names = {rel.get("name")}
    names.update((rel.get("rule") or {}).get("aliases") or [])
    return {n for n in names if n}


def relation_matches(edge_name, schema_rel):
    return bool(edge_name) and edge_name in relation_names_of(schema_rel)


def map_enum(prop, value):
    if value is None or value == "":
        return value, False
    text = str(value).strip()
    allowed = [str(x) for x in (prop.get("enum_values") or [])]
    if not allowed:
        return text, False
    if text in allowed:
        return text, False
    aliases = {str(k): str(v) for k, v in (prop.get("enum_aliases") or {}).items()}
    mapped = aliases.get(text) or aliases.get(text.lower())
    if mapped and mapped in allowed:
        return mapped, True
    lower = {a.lower(): a for a in allowed}
    if text.lower() in lower:
        return lower[text.lower()], True
    return text, False


def is_empty(value):
    return value is None or value == "" or value == [] or value == {}


# 图节点用 type 表示 Person/Event/Project…；本体 Event.type 是事件类别。不能拿节点类别去对枚举。
TYPE_FIELD_FALLBACKS = {
    "Event": ("event_type", "kind"),
    "Organization": ("org_type",),
    "Department": ("org_type",),
    "Resource": ("category", "resource_type"),
    "Role": ("role_type",),
    "Project": ("project_type",),
    "Task": ("task_type",),
    "Achievement": ("achievement_type",),
    "Contribution": ("contribution_type",),
    "TrainingAction": ("action_type",),
    "Relationship": ("relation_type", "rel_type"),
}


def _graph_type_labels(node, type_rec):
    labels = {node.get("type"), (type_rec or {}).get("name")}
    return {str(x) for x in labels if x}


def schema_storage_field(node, field, type_rec=None):
    """Schema 属性在图节点上的实际存放字段。禁止用本体 type 覆盖图的节点类别。"""
    if field != "type":
        return field
    onto = (type_rec or {}).get("name") or node.get("type") or ""
    if str(node.get("type") or "") in _graph_type_labels(node, {"name": onto}):
        alts = TYPE_FIELD_FALLBACKS.get(onto) or ()
        if alts:
            return alts[0]
    return field


def schema_value(node, prop, type_rec=None):
    name = prop["name"]
    value = node.get(name)
    onto = (type_rec or {}).get("name") or ""
    if name == "type" and value is not None and str(value) in _graph_type_labels(node, type_rec):
        for alt in TYPE_FIELD_FALLBACKS.get(onto, ()):
            if not is_empty(node.get(alt)):
                return node.get(alt)
        return None
    return value


def validate_node(node, type_rec):
    """对照属性 Schema 检查一个图实例。不写图。"""
    issues = []
    props = properties_of(type_rec)
    declared = {p["name"] for p in props}
    forbidden = set((type_rec.get("schema") or {}).get("forbidden_as_property") or [])
    for name in forbidden:
        # 只拦「被写进类型属性表」的错误字段；图上遗留的 department/skills 等不刷工单
        if name not in declared:
            continue
        if not is_empty(node.get(name)):
            issues.append({
                "kind": "forbidden_property",
                "field": name,
                "message": f"{name} 应建模为关系，而不是 {type_rec.get('name')} 的属性",
                "value": node.get(name),
            })
    for prop in props:
        name = prop["name"]
        value = schema_value(node, prop, type_rec)
        if prop.get("required") and is_empty(value):
            issues.append({
                "kind": "required",
                "field": name,
                "message": f"{prop.get('label') or name} 为必填",
            })
            continue
        if is_empty(value):
            continue
        if prop["data_type"] == "Enum":
            mapped, _ = map_enum(prop, value)
            allowed = [str(x) for x in (prop.get("enum_values") or [])]
            if str(mapped) not in allowed:
                issues.append({
                    "kind": "enum",
                    "field": name,
                    "message": f"{name}={value} 不在枚举 {allowed} 中",
                    "value": value,
                    "proposed_value": mapped if str(mapped) in allowed else (prop.get("default") or (allowed[0] if allowed else "")),
                    "enum_values": allowed,
                })
            elif str(mapped) != str(value):
                issues.append({
                    "kind": "enum_alias",
                    "field": name,
                    "message": f"{name}={value} 应规范为 {mapped}",
                    "value": value,
                    "proposed_value": mapped,
                    "enum_values": allowed,
                })
        if prop["data_type"] in ("Integer", "Float"):
            try:
                num = float(value)
            except (TypeError, ValueError):
                issues.append({"kind": "type", "field": name, "message": f"{name} 应为数字", "value": value})
                continue
            if prop.get("min") is not None and num < float(prop["min"]):
                issues.append({"kind": "range", "field": name, "message": f"{name} 小于下限 {prop['min']}", "value": value})
            if prop.get("max") is not None and num > float(prop["max"]):
                issues.append({"kind": "range", "field": name, "message": f"{name} 大于上限 {prop['max']}", "value": value})
        if not prop.get("extract") and prop.get("sources") == ["inferred", "event"]:
            pass
    return issues


def compile_constraints(types, relations, extras=None):
    """从属性/关系 Schema 编译可读约束，供约束规则页与解析器共用。"""
    items = []
    for t in types or []:
        tname = t.get("name")
        for prop in properties_of(t):
            name = prop["name"]
            if prop.get("required"):
                items.append(_auto(tname, "property", "required", f"{tname}.{name} 必填", prop=name))
            if prop.get("unique"):
                items.append(_auto(tname, "uniqueness", "unique", f"{tname}.{name} 唯一", prop=name))
            if prop.get("data_type") == "Enum" and prop.get("enum_values"):
                items.append(_auto(
                    tname, "enum", "enum",
                    f"{tname}.{name} ∈ {prop['enum_values']}",
                    prop=name, extra={"enum_values": prop["enum_values"], "enum_aliases": prop.get("enum_aliases") or {}},
                ))
            if prop.get("min") is not None or prop.get("max") is not None:
                items.append(_auto(
                    tname, "range", "range",
                    f"{tname}.{name} 范围 {prop.get('min')} ~ {prop.get('max')}",
                    prop=name, extra={"min": prop.get("min"), "max": prop.get("max")},
                ))
            if not prop.get("extract"):
                items.append(_auto(
                    tname, "property", "extract",
                    f"{tname}.{name} 禁止 LLM 直填（来源 {prop.get('sources')}）",
                    prop=name, extra={"sources": prop.get("sources")},
                ))
        for fname in (t.get("schema") or {}).get("forbidden_as_property") or []:
            items.append(_auto(tname, "type", "not_attribute", f"{tname}.{fname} 必须是关系，不能当属性"))
    for rel in relations or []:
        rule = normalize_relation_rule(rel.get("rule"))
        items.append(_auto(
            rel.get("name"), "relation", "allowed",
            f"{rel.get('source_type')} --{rel.get('name')}--> {rel.get('target_type')}  cardinality={rule.get('cardinality')}",
            extra={"relation_id": rel.get("id"), "cardinality": rule.get("cardinality"), "temporal": rule.get("temporal")},
        ))
    for extra in extras or []:
        items.append({**extra, "origin": extra.get("origin") or "manual"})
    return items


def _auto(object_name, kind, code, message, prop="", extra=None):
    rec = {
        "id": f"auto:{object_name}:{prop or '_'}:{code}",
        "name": f"{object_name}.{prop}" if prop else object_name,
        "kind": kind,
        "code": code,
        "object_type": object_name,
        "property": prop,
        "message": message,
        "status": "ACTIVE",
        "origin": "schema",
        "expression": extra or {},
    }
    return rec
