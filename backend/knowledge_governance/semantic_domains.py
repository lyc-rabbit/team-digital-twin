"""语义域隔离：事实可以证明事实，不能跨域无条件推理。

责任 ≠ 贡献 ≠ 培养 ≠ 能力。禁止从职位/汇报/成果归属直接推出能力、贡献、培养。
"""

from organization_graph.ontology.relations import (
    REL_ACHIEVEMENT_OWNERSHIP,
    REL_CONTRIBUTES_TO,
    REL_EVIDENCES_CAPABILITY,
    REL_EXECUTION_RESPONSIBILITY,
    REL_HAS_CAPABILITY_EVIDENCE,
    REL_MADE_CONTRIBUTION,
    REL_MANAGEMENT_RESPONSIBILITY,
    REL_MENTOR,
    REL_ORG_RESPONSIBILITY,
    REL_OWNER,
    REL_PERFORMED_TRAINING,
    REL_REPORT_TO,
    REL_REPORTING_RESPONSIBILITY,
    REL_TRAINING_TARGET,
    REL_WORKS_ON,
)

from .relations import REL_CONTRIBUTE_TO, REL_MANAGES

DOMAIN_RESPONSIBILITY = "responsibility"
DOMAIN_ACHIEVEMENT = "achievement"
DOMAIN_TRAINING = "training"
DOMAIN_CAPABILITY = "capability"

DOMAIN_RELATIONS = {
    DOMAIN_RESPONSIBILITY: {
        REL_ORG_RESPONSIBILITY, REL_EXECUTION_RESPONSIBILITY,
        REL_MANAGEMENT_RESPONSIBILITY, REL_REPORTING_RESPONSIBILITY,
        REL_OWNER, REL_REPORT_TO, REL_MANAGES, "MANAGE",
    },
    DOMAIN_ACHIEVEMENT: {
        REL_ACHIEVEMENT_OWNERSHIP, REL_MADE_CONTRIBUTION, REL_CONTRIBUTES_TO,
        "TechnicalContribution", "ReportingContribution",
    },
    DOMAIN_TRAINING: {
        REL_PERFORMED_TRAINING, REL_TRAINING_TARGET, REL_MENTOR,
        "MentoringAction", "FeedbackAction", "CoachingAction",
    },
    DOMAIN_CAPABILITY: {
        "HAS_CAPABILITY", "DEMONSTRATED_CAPABILITY",
        REL_EVIDENCES_CAPABILITY, REL_HAS_CAPABILITY_EVIDENCE,
    },
}

# 不能当作「实际贡献 / 技术能力 / 培养」证据的关系
NOT_CONTRIBUTION_EVIDENCE = frozenset({
    REL_OWNER, REL_ORG_RESPONSIBILITY, REL_MANAGEMENT_RESPONSIBILITY,
    REL_REPORTING_RESPONSIBILITY, REL_ACHIEVEMENT_OWNERSHIP, REL_REPORT_TO,
    REL_WORKS_ON, REL_CONTRIBUTE_TO,
})
NOT_TRAINING_EVIDENCE = frozenset({
    REL_REPORT_TO, REL_MANAGES, "MANAGE", REL_OWNER, REL_MANAGEMENT_RESPONSIBILITY,
})
NOT_CAPABILITY_EVIDENCE = frozenset({
    REL_OWNER, REL_ORG_RESPONSIBILITY, REL_MANAGEMENT_RESPONSIBILITY,
    REL_REPORTING_RESPONSIBILITY, REL_ACHIEVEMENT_OWNERSHIP, REL_REPORT_TO,
    REL_WORKS_ON,
})

META_RULES = (
    "负责项目 ≠ 实际完成项目",
    "成果归属 ≠ 实际贡献",
    "成果汇报 ≠ 成果创造",
    "管理下属 ≠ 培养下属",
    "项目成功 ≠ 项目负责人具备全部项目能力",
    "职位高 ≠ 能力高",
)

# 稳定 id，ensure 时覆盖描述/动作，不重复插入
FORBIDDEN_RULES = (
    {
        "id": "rr_forbid_train_from_report",
        "name": "ForbidTrainFromManage",
        "description": "Rule 001：禁止从汇报/管理职位推导培养。A 向 B 汇报，不能推出 B 培养了 A。",
        "condition": [{"source": "?a", "relation": REL_REPORT_TO, "target": "?b"}],
        "action": {
            "forbid": [
                {"source": "?b", "relation": REL_MENTOR, "target": "?a"},
                {"source": "?a", "relation": REL_MENTOR, "target": "?b"},
            ],
        },
        "status": "ACTIVE",
    },
    {
        "id": "rr_forbid_contrib_from_ownership",
        "name": "ForbidContributeFromOwnership",
        "description": "Rule 002：禁止从成果归属推导实际贡献。AchievementOwnership 只能表达组织/业务挂名。",
        "condition": [{"source": "?a", "relation": REL_ACHIEVEMENT_OWNERSHIP, "target": "?ach"}],
        "action": {
            "forbid": [
                {"source": "?a", "relation": REL_MADE_CONTRIBUTION, "target": "?c"},
                {"source": "?a", "relation": REL_CONTRIBUTE_TO, "target": "?ach"},
            ],
        },
        "status": "ACTIVE",
    },
    {
        "id": "rr_forbid_contrib_from_owner",
        "name": "ForbidContributeFromProjectOwner",
        "description": "Rule 002b：项目 OWNER / 组织责任不能推出对项目或部门的实际贡献。",
        "condition": [{"source": "?a", "relation": REL_OWNER, "target": "?proj"}],
        "action": {
            "forbid": [
                {"source": "?a", "relation": REL_CONTRIBUTE_TO, "target": "?dept"},
                {"source": "?a", "relation": REL_MADE_CONTRIBUTION, "target": "?c"},
                {"source": "?a", "relation": "HAS_CAPABILITY", "target": "?cap"},
                {"source": "?a", "relation": "DEMONSTRATED_CAPABILITY", "target": "?cap"},
            ],
        },
        "status": "ACTIVE",
    },
    {
        "id": "rr_forbid_techcap_from_mgmt",
        "name": "ForbidTechCapabilityFromManagement",
        "description": "Rule 003：禁止从项目管理责任推导全部项目技术能力。只能认定其承担管理责任。",
        "condition": [{"source": "?a", "relation": REL_MANAGEMENT_RESPONSIBILITY, "target": "?proj"}],
        "action": {
            "forbid": [
                {"source": "?a", "relation": "HAS_CAPABILITY", "target": "?cap"},
                {"source": "?a", "relation": "DEMONSTRATED_CAPABILITY", "target": "?cap"},
                {"source": "?a", "relation": REL_MADE_CONTRIBUTION, "target": "?c"},
            ],
        },
        "status": "ACTIVE",
    },
)

ILLEGAL_ADD_RULES = frozenset({
    "ContributeViaProjectDept",
})

CONTRIBUTE_VIA_PROJECT_RULE = "ContributeViaProjectDept"


def is_forbidden_inference(relation, evidence_edges):
    """根据推出该边所用的前提边，判断是否跨语义域。"""
    evid_rels = {e.get("relation") for e in (evidence_edges or []) if e}
    if not evid_rels:
        return None
    if relation == REL_MENTOR:
        if evid_rels & NOT_TRAINING_EVIDENCE and not (evid_rels & {REL_PERFORMED_TRAINING, REL_TRAINING_TARGET}):
            return "ForbidTrainFromManage"
    if relation in (REL_CONTRIBUTE_TO, REL_MADE_CONTRIBUTION, REL_CONTRIBUTES_TO):
        if evid_rels & NOT_CONTRIBUTION_EVIDENCE and REL_CONTRIBUTES_TO not in evid_rels:
            return "ForbidContributeFromOwnership"
    if relation in ("HAS_CAPABILITY", "DEMONSTRATED_CAPABILITY"):
        if evid_rels & NOT_CAPABILITY_EVIDENCE:
            return "ForbidTechCapabilityFromManagement"
    return None


def is_forbidden_add(source, relation, target, facts, evidence_edges=None, forbid_rules=None):
    hit = is_forbidden_inference(relation, evidence_edges)
    if hit:
        return {"name": hit}
    if evidence_edges is not None:
        return None
    rules = [r for r in (forbid_rules or FORBIDDEN_RULES) if (r.get("status") or "ACTIVE") == "ACTIVE"]
    for rule in rules:
        forbids = (rule.get("action") or {}).get("forbid") or []
        if not forbids:
            continue
        for binding in _match_all(rule.get("condition") or [], facts):
            for tmpl in forbids:
                want_rel = _bind(tmpl.get("relation"), binding)
                if want_rel and want_rel != relation:
                    continue
                want_src = _bind(tmpl.get("source"), binding)
                want_tgt = _bind(tmpl.get("target"), binding)
                if (want_src is None or want_src == source) and (want_tgt is None or want_tgt == target):
                    return rule
    return None


def _is_var(token):
    return isinstance(token, str) and token.startswith("?")


def _bind(token, binding):
    if _is_var(token):
        return binding.get(token)
    return token


def _match_all(conditions, facts):
    bindings = [{}]
    for pattern in conditions or []:
        nxt = []
        for binding in bindings:
            for edge in facts:
                hit = _match_one(pattern, edge, binding)
                if hit:
                    nxt.append(hit)
        bindings = nxt
        if not bindings:
            return []
    return bindings


def _match_one(pattern, edge, binding):
    if (pattern.get("relation") or "") != (edge.get("relation") or ""):
        return None
    nxt = dict(binding)
    for token, value in ((pattern.get("source"), edge.get("source")), (pattern.get("target"), edge.get("target"))):
        if _is_var(token):
            if token in nxt and nxt[token] != value:
                return None
            nxt[token] = value
        elif token and token != value:
            return None
    return nxt


def illegal_existing_edges(nodes, edges):
    """扫描图上已有的跨语义域误推（含历史推断边）。"""
    node_map = {n["id"]: n for n in nodes or []}
    by_rel = {}
    for e in edges or []:
        by_rel.setdefault(e.get("relation"), []).append(e)

    found = []

    report_pairs = {(e.get("source"), e.get("target")) for e in by_rel.get(REL_REPORT_TO, [])}
    managed = {(e.get("target"), e.get("source")) for e in by_rel.get(REL_REPORT_TO, [])}
    has_training = set()
    for e in by_rel.get(REL_PERFORMED_TRAINING, []):
        has_training.add(e.get("source"))
    training_pairs = set()
    actions_by_id = {n["id"]: n for n in nodes or [] if n.get("type") == "TrainingAction"}
    performers = {}
    for e in by_rel.get(REL_PERFORMED_TRAINING, []):
        performers.setdefault(e.get("target"), []).append(e.get("source"))
    for e in by_rel.get(REL_TRAINING_TARGET, []):
        for person in performers.get(e.get("source")) or []:
            training_pairs.add((person, e.get("target")))

    for e in by_rel.get(REL_MENTOR, []):
        src, tgt = e.get("source"), e.get("target")
        props = e.get("properties") or {}
        if (tgt, src) in report_pairs or (src, tgt) in report_pairs or (src, tgt) in managed:
            if (src, tgt) not in training_pairs:
                found.append(_issue(
                    "ILLEGAL_INFER_TRAIN_FROM_ROLE",
                    "从汇报/管理推出培养",
                    e, node_map,
                    "存在汇报关系但没有 TrainingAction 证据，不能把 MENTOR 当作培养事实。",
                    inferred=bool(props.get("inferred")),
                ))

    owner_people = {e.get("source") for e in by_rel.get(REL_OWNER, [])}
    owner_people |= {e.get("source") for e in by_rel.get(REL_ORG_RESPONSIBILITY, [])}
    owner_people |= {e.get("source") for e in by_rel.get(REL_ACHIEVEMENT_OWNERSHIP, [])}
    mgmt_people = {e.get("source") for e in by_rel.get(REL_MANAGEMENT_RESPONSIBILITY, [])}

    for e in by_rel.get(REL_CONTRIBUTE_TO, []):
        props = e.get("properties") or {}
        if props.get("inferred") or props.get("rule_name") == CONTRIBUTE_VIA_PROJECT_RULE:
            found.append(_issue(
                "ILLEGAL_INFER_CONTRIBUTE_FROM_OWNER",
                "从参与/负责项目推出部门贡献",
                e, node_map,
                "WORKS_ON / OWNER 不能推出 CONTRIBUTE_TO。实际贡献必须经 Contribution 节点。",
                inferred=True,
            ))

    for rel in ("HAS_CAPABILITY", "DEMONSTRATED_CAPABILITY"):
        for e in by_rel.get(rel, []):
            props = e.get("properties") or {}
            src = e.get("source")
            if not props.get("inferred"):
                continue
            if src in owner_people or src in mgmt_people:
                found.append(_issue(
                    "ILLEGAL_INFER_CAPABILITY_FROM_OWNER",
                    "从项目负责人推出技术能力",
                    e, node_map,
                    "管理/组织责任只能证明承担管理责任，不能推出 HAS_CAPABILITY。",
                    inferred=True,
                ))

    return found


def _issue(code, title, edge, nodes, detail, inferred=False):
    src, tgt = edge.get("source"), edge.get("target")
    return {
        "code": code,
        "title": title,
        "detail": detail,
        "source": src,
        "target": tgt,
        "relation": edge.get("relation"),
        "source_name": (nodes.get(src) or {}).get("name") or src,
        "target_name": (nodes.get(tgt) or {}).get("name") or tgt,
        "inferred": inferred,
        "id": edge.get("id") or f"{src}|{edge.get('relation')}|{tgt}",
    }


def contribution_counts(mid, edges, nodes):
    """分析层用：按贡献类型计数，不把 OWNER/汇报算进技术贡献。"""
    node_map = {n["id"]: n for n in nodes or []}
    made = [e for e in edges or [] if e.get("relation") == REL_MADE_CONTRIBUTION and e.get("source") == mid]
    counts = {
        "technical": 0, "architecture": 0, "product": 0, "management": 0,
        "resource": 0, "decision": 0, "coordination": 0, "training": 0, "reporting": 0,
        "execution_resp": 0, "management_resp": 0, "org_resp": 0, "reporting_resp": 0,
        "training_actions": 0, "achievement_ownership": 0,
    }
    for e in made:
        n = node_map.get(e.get("target")) or {}
        kind = (n.get("contribution_type") or n.get("ontology_type") or "").lower()
        if "architect" in kind:
            counts["architecture"] += 1
        elif "report" in kind:
            counts["reporting"] += 1
        elif "manage" in kind:
            counts["management"] += 1
        elif "product" in kind:
            counts["product"] += 1
        elif "resource" in kind:
            counts["resource"] += 1
        elif "decision" in kind:
            counts["decision"] += 1
        elif "coordinat" in kind:
            counts["coordination"] += 1
        elif "train" in kind:
            counts["training"] += 1
        else:
            counts["technical"] += 1
    for e in edges or []:
        if e.get("source") != mid:
            continue
        rel = e.get("relation")
        if rel == REL_EXECUTION_RESPONSIBILITY:
            counts["execution_resp"] += 1
        elif rel == REL_MANAGEMENT_RESPONSIBILITY:
            counts["management_resp"] += 1
        elif rel in (REL_ORG_RESPONSIBILITY, REL_OWNER):
            counts["org_resp"] += 1
        elif rel == REL_REPORTING_RESPONSIBILITY:
            counts["reporting_resp"] += 1
        elif rel == REL_PERFORMED_TRAINING:
            counts["training_actions"] += 1
        elif rel == REL_ACHIEVEMENT_OWNERSHIP:
            counts["achievement_ownership"] += 1
    return counts
