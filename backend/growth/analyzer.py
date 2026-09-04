"""事件 → 关系证据 / 能力证据。规则优先，保证可解释、可追溯。"""

from . import repository as repo
from .taxonomy import get_template, tag_label, type_label

DIMENSIONS = {
    "trust": "信任",
    "professional_trust": "专业信任",
    "independence": "独立性信任",
    "problem_solving": "问题解决能力",
    "communication": "沟通能力",
    "delivery_trust": "项目交付信任",
    "risk_trust": "风险处理信任",
    "autonomy_trust": "自主决策信任",
    "management_trust": "管理能力信任",
    "sentiment": "情绪",
}

STRUCTURED_FIELDS = [
    "background", "facts", "expected", "difference",
    "actions", "result", "evidence", "judgement", "attempts", "help_request",
]

TAG_IMPACTS = {
    ("people_development", "newcomer_progress"): [
        ("trust", 3, "新人表现出可核验的进步"),
        ("independence", 3, "独立性提升"),
        ("problem_solving", 3, "问题解决能力提升"),
        ("communication", 2, "沟通质量提升"),
        ("professional_trust", 2, "专业信任增强"),
    ],
    ("people_development", "newcomer_issue"): [
        ("trust", -1, "出现需要介入的培养问题"),
        ("independence", -2, "独立性不足"),
        ("problem_solving", -1, "问题仍需外部解决"),
    ],
    ("people_development", "coaching"): [
        ("trust", 1, "完成一次指导"),
        ("management_trust", 2, "带人实践"),
        ("communication", 1, "指导过程中的沟通"),
    ],
    ("people_development", "authorization"): [
        ("autonomy_trust", 3, "给予授权"),
        ("trust", 2, "授权建立信任"),
        ("management_trust", 2, "管理授权实践"),
    ],
    ("people_development", "empowerment"): [
        ("autonomy_trust", 3, "放权"),
        ("independence", 2, "要求独立承担"),
        ("management_trust", 2, "放权管理实践"),
    ],
    ("people_development", "newcomer_task"): [
        ("trust", 1, "布置并跟踪新人任务"),
        ("management_trust", 1, "培养任务实践"),
    ],
    ("people_development", "development_result"): [
        ("trust", 3, "培养结果可验证"),
        ("management_trust", 3, "带人结果"),
        ("professional_trust", 2, "培养对象能力结果"),
    ],
    ("communication", "problem_raise"): [
        ("communication", 1, "提出问题"),
    ],
    ("communication", "problem_define"): [
        ("communication", 3, "完成问题定义"),
        ("professional_trust", 2, "问题定义质量"),
        ("independence", 2, "先自行定义问题"),
    ],
    ("communication", "requirement_clarify"): [
        ("communication", 2, "需求澄清"),
        ("professional_trust", 1, "需求理解"),
    ],
    ("communication", "info_pass"): [
        ("communication", 1, "信息传递"),
    ],
    ("communication", "comm_error"): [
        ("communication", -3, "出现沟通误差"),
        ("trust", -2, "沟通误差影响信任"),
    ],
    ("communication", "cross_collab"): [
        ("communication", 2, "跨专业协作"),
        ("trust", 1, "协作增进信任"),
    ],
    ("project", "project_risk"): [
        ("risk_trust", 3, "识别或处理项目风险"),
        ("professional_trust", 2, "风险判断"),
        ("delivery_trust", 1, "风险对交付的影响被看见"),
    ],
    ("project", "tech_decision"): [
        ("professional_trust", 3, "做出技术决策"),
        ("autonomy_trust", 2, "技术判断"),
    ],
    ("project", "tech_breakthrough"): [
        ("professional_trust", 4, "技术突破"),
        ("trust", 2, "专业结果增强信任"),
    ],
    ("project", "tech_failure"): [
        ("professional_trust", -3, "技术判断未达预期"),
        ("trust", -1, "失败影响信任"),
    ],
    ("project", "project_delivery"): [
        ("delivery_trust", 4, "项目交付"),
        ("professional_trust", 2, "交付结果"),
        ("trust", 2, "交付增强信任"),
    ],
    ("project", "project_progress"): [
        ("delivery_trust", 1, "项目推进"),
    ],
    ("project", "project_retro"): [
        ("professional_trust", 1, "复盘"),
        ("management_trust", 1, "复盘管理实践"),
    ],
    ("management", "conflict"): [
        ("management_trust", 1, "处理冲突"),
        ("trust", -1, "冲突本身消耗信任"),
    ],
    ("management", "decision"): [
        ("management_trust", 2, "管理决策"),
        ("autonomy_trust", 2, "决策担当"),
    ],
    ("management", "task_assignment"): [
        ("management_trust", 1, "任务分配"),
    ],
    ("management", "coordination"): [
        ("management_trust", 2, "协调"),
        ("communication", 1, "协调沟通"),
    ],
    ("management", "resource_seek"): [
        ("management_trust", 2, "资源争取"),
    ],
    ("management", "risk_escalate"): [
        ("risk_trust", 3, "风险上报"),
        ("professional_trust", 1, "风险判断"),
    ],
    ("management", "institution"): [
        ("management_trust", 4, "制度建设实践"),
    ],
    ("upward", "report"): [
        ("delivery_trust", 1, "向上汇报"),
        ("communication", 1, "汇报沟通"),
    ],
    ("upward", "superior_decision"): [
        ("autonomy_trust", 1, "承接上级决策"),
    ],
    ("upward", "superior_auth"): [
        ("autonomy_trust", 3, "获得上级授权"),
        ("trust", 2, "授权增强信任"),
    ],
    ("upward", "superior_feedback"): [
        ("professional_trust", 1, "上级反馈"),
    ],
    ("upward", "superior_recognition"): [
        ("professional_trust", 3, "上级认可"),
        ("trust", 3, "认可增强信任"),
        ("delivery_trust", 2, "结果被认可"),
    ],
    ("upward", "superior_challenge"): [
        ("professional_trust", -2, "上级质疑"),
        ("trust", -1, "质疑消耗信任"),
    ],
    ("upward", "resource_support"): [
        ("trust", 2, "获得资源支持"),
        ("delivery_trust", 1, "资源支持交付"),
    ],
    ("relationship", "trust_up"): [
        ("trust", 4, "信任增强事件"),
        ("professional_trust", 2, "专业信任随关系上升"),
    ],
    ("relationship", "trust_down"): [
        ("trust", -4, "信任下降事件"),
        ("professional_trust", -2, "专业信任随关系下降"),
    ],
    ("relationship", "cooperate"): [
        ("trust", 2, "合作"),
        ("communication", 1, "合作沟通"),
    ],
    ("relationship", "conflict"): [
        ("trust", -3, "关系冲突"),
        ("communication", -2, "冲突中的沟通损耗"),
    ],
    ("relationship", "help"): [
        ("trust", 2, "提供或接受帮助"),
    ],
    ("relationship", "resource_exchange"): [
        ("trust", 1, "资源交换"),
    ],
    ("relationship", "informal_shift"): [
        ("trust", 1, "非正式组织变化"),
    ],
}

NEGATIVE_HINTS = ("未经验证", "滞后", "失败", "错误", "冲突", "质疑", "下降", "不准", "未完成")
POSITIVE_HINTS = ("独立", "自行", "提前", "准确", "突破", "认可", "结构化", "主动")


def _text_blob(event):
    extra = event.get("extra_fields") or {}
    parts = [
        event.get("background") or "",
        event.get("facts") or "",
        event.get("expected") or "",
        event.get("difference") or "",
        event.get("actions") or "",
        extra.get("attempts") or "",
        event.get("result") or "",
        event.get("evidence") or "",
        event.get("judgement") or "",
        extra.get("help_request") or "",
        event.get("raw_summary") or "",
    ]
    return "\n".join(parts)


def _filled_count(event):
    extra = event.get("extra_fields") or {}
    n = 0
    for fid in STRUCTURED_FIELDS:
        val = extra.get(fid) if fid in extra else event.get(fid)
        if (val or "").strip():
            n += 1
    return n


def is_structured_problem(event):
    extra = event.get("extra_fields") or {}
    keys = ["background", "facts", "expected", "difference", "judgement"]
    filled = 0
    for k in keys:
        val = extra.get(k) if extra.get(k) is not None else event.get(k)
        if (val or "").strip():
            filled += 1
    attempts = (extra.get("attempts") or event.get("actions") or "").strip()
    help_req = (extra.get("help_request") or "").strip()
    blob = _text_blob(event)
    asked_directly = any(x in blob for x in ("帮我看看", "直接帮我", "给我改一下", "帮我解决"))
    has_structure = filled >= 4 and bool(attempts or help_req or event.get("judgement"))
    return has_structure and not (asked_directly and filled < 3)


def _quality_boost(event):
    filled = _filled_count(event)
    if filled >= 6:
        return 2
    if filled >= 4:
        return 1
    return 0


def _polarity_adjust(delta, blob):
    if delta > 0 and any(h in blob for h in NEGATIVE_HINTS):
        return max(-abs(delta), delta - 2)
    if delta < 0 and any(h in blob for h in POSITIVE_HINTS):
        return min(abs(delta), delta + 1)
    if delta > 0 and any(h in blob for h in POSITIVE_HINTS):
        return delta + 1
    return delta


def _targets(event):
    subjects = event.get("subjects") or []
    targets = [s.get("person_id") for s in subjects if s.get("person_id") and s.get("role") in ("target", "subject", None)]
    if not targets:
        targets = [s.get("person_id") for s in subjects if s.get("person_id")]
    involved = event.get("involved_members") or []
    created_by = event.get("created_by") or ""
    if not targets:
        targets = [mid for mid in involved if mid and mid != created_by]
    if not targets and involved:
        targets = list(involved)
    return [t for t in targets if t]


def _observer(event, target_id):
    created_by = event.get("created_by") or ""
    if created_by and created_by != target_id:
        return created_by
    related = event.get("related_persons") or []
    for pid in related:
        if pid and pid != target_id:
            return pid
    involved = event.get("involved_members") or []
    for mid in involved:
        if mid and mid != target_id:
            return mid
    return created_by or None


def _upward_observer(event, target_id):
    """向上协同：观察者是上级，对象是汇报人。"""
    related = event.get("related_persons") or []
    created_by = event.get("created_by") or ""
    for pid in related:
        if pid and pid != target_id:
            return pid
    if created_by and created_by != target_id:
        return created_by
    involved = event.get("involved_members") or []
    for mid in involved:
        if mid and mid != target_id:
            return mid
    return None


def analyze_event(event):
    type_id = event.get("event_type") or ""
    tag_id = event.get("event_tag") or ""
    blob = _text_blob(event)
    boost = _quality_boost(event)
    impacts = list(TAG_IMPACTS.get((type_id, tag_id)) or [])
    rels = []
    caps = []

    facts = (event.get("facts") or event.get("background") or "")[:400]
    result = (event.get("result") or event.get("evidence") or "")[:400]
    title = tag_label(type_id, tag_id) or type_label(type_id)

    structured = is_structured_problem(event)
    if tag_id in ("problem_raise", "problem_define") or structured:
        if structured:
            impacts = [
                ("communication", 3, "完成结构化问题定义，而不是直接索要解决方案"),
                ("professional_trust", 3, "问题描述可核验，增强专业信任"),
                ("independence", 2, "先自行整理背景、事实和判断"),
                ("problem_solving", 2, "问题定位与结构化沟通能力提升"),
            ]
        elif tag_id == "problem_raise":
            impacts = [
                ("communication", 1, "提出了问题，但结构化程度有限"),
            ]

    if not impacts and (type_id or blob):
        impacts = [("trust", 1 if boost else 0, "记录了一次相关事件")]

    targets = _targets(event)
    for target in targets:
        observer = _upward_observer(event, target) if type_id == "upward" else _observer(event, target)
        if not observer or observer == target:
            continue
        # 关系方向：观察者 → 对象（我对你的信任）
        for dim, delta, reason in impacts:
            adj = _polarity_adjust(int(delta) + (boost if delta > 0 else 0), blob)
            if adj == 0:
                continue
            impact = f"{'增强' if adj > 0 else '削弱'}对「{DIMENSIONS.get(dim, dim)}」的判断。"
            rels.append({
                "from_member_id": observer,
                "to_member_id": target,
                "dimension": dim,
                "delta": adj,
                "reason": reason,
                "facts": facts,
                "result": result,
                "impact": impact,
            })
        if structured or tag_id in ("problem_raise", "problem_define", "newcomer_progress"):
            score = 72 if structured else 58
            caps.append({
                "employee_id": target,
                "capability_id": "problem_definition",
                "capability_name": "问题定义与结构化沟通",
                "content": facts or blob[:300],
                "score": score,
                "reason": "结构化问题定义" if structured else f"{title}相关沟通",
                "polarity": "positive" if structured else "positive",
                "dimension": "problem_definition",
            })
            if structured and observer:
                caps.append({
                    "employee_id": observer,
                    "capability_id": "mentoring",
                    "capability_name": "带人能力",
                    "content": "完成一次有效培养实践：要求并见证结构化问题定义",
                    "score": 66,
                    "reason": "完成一次有效培养实践",
                    "polarity": "positive",
                    "dimension": "mentoring",
                })
        if tag_id in ("newcomer_progress", "development_result", "coaching", "empowerment"):
            caps.append({
                "employee_id": observer,
                "capability_id": "mentoring",
                "capability_name": "带人能力",
                "content": result or facts or blob[:300],
                "score": 64 if tag_id != "development_result" else 78,
                "reason": f"完成一次{title}实践",
                "polarity": "positive",
                "dimension": "mentoring",
            })
        if type_id == "project" and tag_id in ("project_risk", "tech_decision", "project_delivery"):
            caps.append({
                "employee_id": target,
                "capability_id": "delivery" if tag_id == "project_delivery" else "professional",
                "capability_name": "项目管理" if tag_id == "project_delivery" else "技术决策",
                "content": result or facts,
                "score": 70,
                "reason": title,
                "polarity": "positive",
                "dimension": "professional",
            })
        if type_id == "management" and tag_id == "institution":
            caps.append({
                "employee_id": observer or target,
                "capability_id": "institution",
                "capability_name": "组织建设",
                "content": result or facts,
                "score": 75,
                "reason": "制度建设实践",
                "polarity": "positive",
                "dimension": "management",
            })

    return {
        "relationship_evidence": rels,
        "capability_evidence": caps,
        "structured_problem": structured,
        "template": get_template(type_id, tag_id),
    }


def persist_analysis(event_id, analysis):
    repo.delete_relationship_evidence_by_event(event_id)
    repo.delete_capability_evidence_by_event(event_id)
    for rel in analysis.get("relationship_evidence") or []:
        repo.insert_relationship_evidence(
            event_id,
            rel["from_member_id"],
            rel["to_member_id"],
            rel["dimension"],
            rel["delta"],
            rel.get("reason") or "",
            rel.get("facts") or "",
            rel.get("result") or "",
            rel.get("impact") or "",
        )
    for cap in analysis.get("capability_evidence") or []:
        repo.insert_capability_from_event(
            cap["employee_id"],
            cap["capability_id"],
            cap["capability_name"],
            cap.get("content") or "",
            cap.get("score") or 60,
            event_id=event_id,
            reason=cap.get("reason") or "",
            polarity=cap.get("polarity") or "positive",
            dimension=cap.get("dimension") or "",
        )
    return analysis
