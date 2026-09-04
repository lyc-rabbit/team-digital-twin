"""P0 事件类型、标签与动态描述框架。"""

FIELD_DEFS = {
    "background": {"id": "background", "label": "背景", "placeholder": "当时是什么情况？"},
    "facts": {"id": "facts", "label": "发生了什么 / 事实", "placeholder": "具体发生了什么？可核验的事实是什么？"},
    "expected": {"id": "expected", "label": "预期", "placeholder": "本来应该怎样？"},
    "difference": {"id": "difference", "label": "与之前 / 预期相比", "placeholder": "实际和预期（或以往）差在哪里？"},
    "actions": {"id": "actions", "label": "你做了什么", "placeholder": "你提供了什么指导、决策或资源？"},
    "result": {"id": "result", "label": "最终表现 / 结果", "placeholder": "最终独立完成了什么？结果是什么？"},
    "evidence": {"id": "evidence", "label": "事实证据", "placeholder": "有什么具体结果可以证明？"},
    "judgement": {"id": "judgement", "label": "你的判断", "placeholder": "你认为能力或关系发生了什么变化？"},
    "attempts": {"id": "attempts", "label": "已尝试", "placeholder": "已经做了哪些排查或尝试？"},
    "help_request": {"id": "help_request", "label": "希望获得帮助", "placeholder": "希望对方帮什么？边界是什么？"},
}

CORE_FIELD_IDS = [
    "background", "facts", "expected", "difference",
    "actions", "result", "evidence", "judgement",
]


def _fields(*ids, overrides=None):
    overrides = overrides or {}
    out = []
    for fid in ids:
        base = dict(FIELD_DEFS[fid])
        if fid in overrides:
            base.update(overrides[fid])
        out.append(base)
    return out


DEFAULT_FIELDS = _fields(*CORE_FIELD_IDS)

EVENT_TYPES = [
    {
        "id": "project",
        "code": "project",
        "label": "项目事件",
        "tags": [
            {"id": "project_progress", "label": "项目推进"},
            {"id": "project_delivery", "label": "项目交付"},
            {"id": "project_risk", "label": "项目风险"},
            {"id": "tech_decision", "label": "技术决策"},
            {"id": "tech_breakthrough", "label": "技术突破"},
            {"id": "tech_failure", "label": "技术失败"},
            {"id": "project_retro", "label": "项目复盘"},
        ],
    },
    {
        "id": "people_development",
        "code": "people_development",
        "label": "人员培养",
        "tags": [
            {"id": "newcomer_task", "label": "新人任务"},
            {"id": "newcomer_progress", "label": "新人进步"},
            {"id": "newcomer_issue", "label": "新人问题"},
            {"id": "coaching", "label": "指导"},
            {"id": "authorization", "label": "授权"},
            {"id": "empowerment", "label": "放权"},
            {"id": "development_result", "label": "培养结果"},
        ],
    },
    {
        "id": "management",
        "code": "management",
        "label": "管理事件",
        "tags": [
            {"id": "task_assignment", "label": "任务分配"},
            {"id": "decision", "label": "决策"},
            {"id": "conflict", "label": "冲突"},
            {"id": "coordination", "label": "协调"},
            {"id": "resource_seek", "label": "资源争取"},
            {"id": "risk_escalate", "label": "风险上报"},
            {"id": "institution", "label": "制度建设"},
        ],
    },
    {
        "id": "upward",
        "code": "upward",
        "label": "向上协同",
        "tags": [
            {"id": "report", "label": "汇报"},
            {"id": "superior_decision", "label": "上级决策"},
            {"id": "superior_auth", "label": "上级授权"},
            {"id": "superior_feedback", "label": "上级反馈"},
            {"id": "superior_recognition", "label": "上级认可"},
            {"id": "superior_challenge", "label": "上级质疑"},
            {"id": "resource_support", "label": "资源支持"},
        ],
    },
    {
        "id": "communication",
        "code": "communication",
        "label": "沟通事件",
        "tags": [
            {"id": "problem_raise", "label": "问题提出"},
            {"id": "requirement_clarify", "label": "需求澄清"},
            {"id": "info_pass", "label": "信息传递"},
            {"id": "comm_error", "label": "沟通误差"},
            {"id": "problem_define", "label": "问题定义"},
            {"id": "cross_collab", "label": "跨专业协作"},
        ],
    },
    {
        "id": "relationship",
        "code": "relationship",
        "label": "关系事件",
        "tags": [
            {"id": "trust_up", "label": "信任增强"},
            {"id": "trust_down", "label": "信任下降"},
            {"id": "cooperate", "label": "合作"},
            {"id": "conflict", "label": "冲突"},
            {"id": "help", "label": "帮助"},
            {"id": "resource_exchange", "label": "资源交换"},
            {"id": "informal_shift", "label": "非正式组织变化"},
        ],
    },
]

TEMPLATES = {
    ("people_development", "newcomer_progress"): {
        "title": "新人进步",
        "hint": "把「进步挺大」拆成可核验的前后对比与证据。",
        "fields": _fields(
            "background", "facts", "difference", "actions", "result", "evidence", "judgement",
            overrides={
                "background": {"label": "背景", "placeholder": "当时是什么情况？"},
                "facts": {"label": "原始状态", "placeholder": "新人当时表现如何？"},
                "difference": {"label": "发生了什么 / 与之前相比", "placeholder": "新人具体做了什么？发生了什么变化？"},
                "actions": {"label": "你做了什么", "placeholder": "你提供了什么指导或资源？"},
                "result": {"label": "新人最终表现", "placeholder": "新人最终独立完成了什么？"},
                "evidence": {"label": "事实证据", "placeholder": "有什么具体结果可以证明这次进步？"},
                "judgement": {"label": "你的判断", "placeholder": "你认为新人能力发生了什么变化？"},
            },
        ),
    },
    ("people_development", "newcomer_issue"): {
        "title": "新人问题",
        "hint": "先写事实，再写你如何介入。",
        "fields": _fields("background", "facts", "expected", "difference", "actions", "result", "judgement"),
    },
    ("people_development", "coaching"): {
        "title": "指导",
        "hint": "记录指导方式，而不是只写「我帮他看了一下」。",
        "fields": _fields("background", "facts", "actions", "result", "difference", "judgement"),
    },
    ("people_development", "authorization"): {
        "title": "授权",
        "fields": _fields("background", "facts", "actions", "result", "judgement"),
    },
    ("people_development", "empowerment"): {
        "title": "放权",
        "fields": _fields("background", "facts", "actions", "result", "difference", "judgement"),
    },
    ("people_development", "newcomer_task"): {
        "title": "新人任务",
        "fields": _fields("background", "facts", "expected", "actions", "result", "judgement"),
    },
    ("people_development", "development_result"): {
        "title": "培养结果",
        "fields": _fields("background", "result", "evidence", "difference", "judgement"),
    },
    ("communication", "problem_raise"): {
        "title": "问题提出",
        "hint": "不要直接说「帮我做什么」。先写背景、事实、预期、差异、已尝试和当前判断。",
        "fields": _fields(
            "background", "facts", "expected", "difference", "attempts", "judgement", "help_request",
            overrides={
                "background": {"label": "背景", "placeholder": "当时是什么情况？上下文是什么？"},
                "facts": {"label": "事实", "placeholder": "观察到了什么？日志、现象、复现步骤？"},
                "expected": {"label": "预期", "placeholder": "本来应该怎样？"},
                "difference": {"label": "差异", "placeholder": "实际和预期差在哪里？"},
                "attempts": {"label": "已尝试", "placeholder": "已经做了哪些排查？结果如何？"},
                "judgement": {"label": "当前判断", "placeholder": "你现在怎么看？哪些是事实、哪些是假设？"},
                "help_request": {"label": "希望获得帮助", "placeholder": "希望对方帮什么？问题边界是什么？"},
            },
        ),
    },
    ("communication", "problem_define"): {
        "title": "问题定义",
        "hint": "区分事实与判断，明确目标与边界。",
        "fields": _fields(
            "background", "facts", "expected", "difference", "attempts", "judgement", "help_request",
        ),
    },
    ("communication", "requirement_clarify"): {
        "title": "需求澄清",
        "fields": _fields("background", "facts", "expected", "difference", "result", "judgement"),
    },
    ("communication", "info_pass"): {
        "title": "信息传递",
        "fields": _fields("background", "facts", "actions", "result"),
    },
    ("communication", "comm_error"): {
        "title": "沟通误差",
        "fields": _fields("background", "facts", "expected", "difference", "result", "judgement"),
    },
    ("communication", "cross_collab"): {
        "title": "跨专业协作",
        "fields": _fields("background", "facts", "actions", "result", "judgement"),
    },
    ("project", "project_risk"): {
        "title": "项目风险",
        "fields": _fields("background", "facts", "expected", "actions", "result", "evidence", "judgement"),
    },
    ("project", "tech_decision"): {
        "title": "技术决策",
        "fields": _fields("background", "facts", "expected", "actions", "result", "judgement"),
    },
    ("project", "tech_breakthrough"): {
        "title": "技术突破",
        "fields": _fields("background", "facts", "actions", "result", "evidence", "judgement"),
    },
    ("project", "tech_failure"): {
        "title": "技术失败",
        "fields": _fields("background", "facts", "expected", "difference", "actions", "result", "judgement"),
    },
    ("project", "project_delivery"): {
        "title": "项目交付",
        "fields": _fields("background", "result", "evidence", "judgement"),
    },
    ("project", "project_progress"): {
        "title": "项目推进",
        "fields": _fields("background", "facts", "actions", "result", "judgement"),
    },
    ("project", "project_retro"): {
        "title": "项目复盘",
        "fields": _fields("background", "facts", "difference", "result", "judgement"),
    },
    ("management", "conflict"): {
        "title": "冲突",
        "fields": _fields("background", "facts", "actions", "result", "judgement"),
    },
    ("management", "decision"): {
        "title": "决策",
        "fields": _fields("background", "facts", "expected", "actions", "result", "judgement"),
    },
    ("management", "task_assignment"): {
        "title": "任务分配",
        "fields": _fields("background", "facts", "actions", "result", "judgement"),
    },
    ("management", "coordination"): {
        "title": "协调",
        "fields": _fields("background", "facts", "actions", "result", "judgement"),
    },
    ("management", "resource_seek"): {
        "title": "资源争取",
        "fields": _fields("background", "facts", "actions", "result", "judgement"),
    },
    ("management", "risk_escalate"): {
        "title": "风险上报",
        "fields": _fields("background", "facts", "expected", "actions", "result", "judgement"),
    },
    ("management", "institution"): {
        "title": "制度建设",
        "fields": _fields("background", "facts", "actions", "result", "evidence", "judgement"),
    },
    ("upward", "report"): {
        "title": "汇报",
        "fields": _fields("background", "facts", "actions", "result", "judgement"),
    },
    ("upward", "superior_decision"): {
        "title": "上级决策",
        "fields": _fields("background", "facts", "result", "judgement"),
    },
    ("upward", "superior_auth"): {
        "title": "上级授权",
        "fields": _fields("background", "facts", "result", "judgement"),
    },
    ("upward", "superior_feedback"): {
        "title": "上级反馈",
        "fields": _fields("background", "facts", "result", "judgement"),
    },
    ("upward", "superior_recognition"): {
        "title": "上级认可",
        "fields": _fields("background", "facts", "result", "evidence", "judgement"),
    },
    ("upward", "superior_challenge"): {
        "title": "上级质疑",
        "fields": _fields("background", "facts", "difference", "actions", "result", "judgement"),
    },
    ("upward", "resource_support"): {
        "title": "资源支持",
        "fields": _fields("background", "facts", "actions", "result", "judgement"),
    },
    ("relationship", "trust_up"): {
        "title": "信任增强",
        "fields": _fields("background", "facts", "result", "evidence", "judgement"),
    },
    ("relationship", "trust_down"): {
        "title": "信任下降",
        "fields": _fields("background", "facts", "difference", "result", "judgement"),
    },
    ("relationship", "cooperate"): {
        "title": "合作",
        "fields": _fields("background", "facts", "actions", "result", "judgement"),
    },
    ("relationship", "conflict"): {
        "title": "冲突",
        "fields": _fields("background", "facts", "actions", "result", "judgement"),
    },
    ("relationship", "help"): {
        "title": "帮助",
        "fields": _fields("background", "facts", "actions", "result", "judgement"),
    },
    ("relationship", "resource_exchange"): {
        "title": "资源交换",
        "fields": _fields("background", "facts", "actions", "result", "judgement"),
    },
    ("relationship", "informal_shift"): {
        "title": "非正式组织变化",
        "fields": _fields("background", "facts", "result", "judgement"),
    },
}


def list_taxonomy():
    return {
        "types": EVENT_TYPES,
        "core_fields": CORE_FIELD_IDS,
    }


def get_type(type_id):
    return next((t for t in EVENT_TYPES if t["id"] == type_id), None)


def get_tag(type_id, tag_id):
    t = get_type(type_id)
    if not t:
        return None
    return next((x for x in t["tags"] if x["id"] == tag_id), None)


def get_template(type_id, tag_id):
    t = get_type(type_id)
    tag = get_tag(type_id, tag_id)
    tpl = TEMPLATES.get((type_id, tag_id))
    if tpl:
        return {
            "event_type": type_id,
            "event_tag": tag_id,
            "type_label": (t or {}).get("label") or type_id,
            "tag_label": (tag or {}).get("label") or tag_id,
            **tpl,
        }
    return {
        "event_type": type_id,
        "event_tag": tag_id,
        "type_label": (t or {}).get("label") or type_id or "事件",
        "tag_label": (tag or {}).get("label") or tag_id or "未分类",
        "title": (tag or {}).get("label") or "事件描述",
        "hint": "按框架填写，后续才能作为关系分值与能力变化的事实依据。",
        "fields": DEFAULT_FIELDS,
    }


def compose_summary(payload):
    """把结构化字段拼成可检索、可给旧解析链路使用的原文。"""
    type_id = payload.get("event_type") or ""
    tag_id = payload.get("event_tag") or ""
    tpl = get_template(type_id, tag_id)
    parts = []
    if tpl.get("title"):
        parts.append(f"【{tpl['type_label']} / {tpl['title']}】")
    extra = payload.get("extra_fields") or {}
    values = {**{k: payload.get(k) for k in CORE_FIELD_IDS}, **extra}
    for field in tpl.get("fields") or DEFAULT_FIELDS:
        val = (values.get(field["id"]) or "").strip()
        if val:
            parts.append(f"【{field['label']}】{val}")
    legacy = (payload.get("summary") or payload.get("raw_summary") or "").strip()
    if legacy and legacy not in "\n".join(parts):
        parts.append(f"【补充】{legacy}")
    return "\n".join(parts).strip()


def type_label(type_id):
    t = get_type(type_id)
    return (t or {}).get("label") or type_id or "未分类"


def tag_label(type_id, tag_id):
    tag = get_tag(type_id, tag_id)
    return (tag or {}).get("label") or tag_id or ""
