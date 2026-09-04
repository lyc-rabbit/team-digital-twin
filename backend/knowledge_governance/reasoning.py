"""Relation Reasoning Engine —— 规则存库，运行时模式匹配，不写死业务。"""

from .relations import (
    REL_HAS_SUB_RESOURCE,
    REL_IS_A,
    REL_PART_OF,
    RELATION_EQUIV,
    SEMANTIC_RELATIONS,
)
from .repository import get_kg_store
from .semantic_domains import ILLEGAL_ADD_RULES, is_forbidden_inference
from timeutil import intersect_interval, format_validity


def _is_var(token):
    return isinstance(token, str) and token.startswith("?")


def _orientation(wanted, actual):
    """正向匹配，或用 HAS_SUB_RESOURCE 反向充当 IS_A / PART_OF。"""
    if not wanted or not actual:
        return None
    equiv = RELATION_EQUIV.get(wanted, (wanted,))
    if actual == wanted or actual in equiv:
        return "forward"
    if wanted in (REL_IS_A, REL_PART_OF) and actual == REL_HAS_SUB_RESOURCE:
        return "swap"
    if wanted == REL_HAS_SUB_RESOURCE and actual in (REL_IS_A, REL_PART_OF):
        return "swap"
    return None


def _match_pattern(pattern, edge, binding):
    wanted = pattern.get("relation")
    orient = _orientation(wanted, edge.get("relation"))
    if not orient:
        return None
    src, tgt = edge.get("source"), edge.get("target")
    if orient == "swap":
        src, tgt = tgt, src
    nxt = dict(binding)
    nxt["_edges"] = list(binding.get("_edges") or []) + [edge]
    for token, value in ((pattern.get("source"), src), (pattern.get("target"), tgt)):
        if _is_var(token):
            if token in nxt and nxt[token] != value:
                return None
            nxt[token] = value
        elif token and token != value:
            return None
    if not nxt.get(pattern.get("source")) or not nxt.get(pattern.get("target")):
        if _is_var(pattern.get("source")) and not nxt.get(pattern.get("source")):
            return None
        if _is_var(pattern.get("target")) and not nxt.get(pattern.get("target")):
            return None
    return nxt


def _instantiate(template, binding):
    src = template.get("source")
    tgt = template.get("target")
    rel = template.get("relation")
    source = binding.get(src, src) if _is_var(src) else src
    target = binding.get(tgt, tgt) if _is_var(tgt) else tgt
    relation = binding.get(rel, rel) if _is_var(rel) else rel
    return source, relation, target


def _format_chain(edges, nodes):
    chain = []
    for e in edges or []:
        src = nodes.get(e.get("source")) or {}
        tgt = nodes.get(e.get("target")) or {}
        chain.append({
            "source": e.get("source"),
            "source_name": src.get("name") or e.get("source"),
            "relation": e.get("relation"),
            "target": e.get("target"),
            "target_name": tgt.get("name") or e.get("target"),
        })
    return chain


def explanation_from_chain(chain, conclusion):
    lines = []
    for step in chain or []:
        lines.append(f"{step.get('source_name')} {step.get('relation')} {step.get('target_name')}")
    src, rel, tgt, src_name, tgt_name = conclusion
    lines.append(f"因此: {src_name} {rel} {tgt_name}")
    return "\n".join(lines)


def apply_rules(nodes, edges, rules=None, max_rounds=3):
    """在已有边上做前向链式推理。返回新增边列表，不直接写库。"""
    rules = rules if rules is not None else get_kg_store().list_rules()
    node_map = {n["id"]: n for n in nodes}
    facts = list(edges)
    seen = {(e.get("source"), e.get("relation"), e.get("target")) for e in facts}
    inferred = []

    for _ in range(max_rounds):
        added = 0
        for rule in rules:
            if (rule.get("status") or "ACTIVE") != "ACTIVE":
                continue
            if rule.get("name") in ILLEGAL_ADD_RULES:
                continue
            action = rule.get("action") or {}
            if action.get("forbid") and not (action.get("add") or []):
                continue
            conditions = rule.get("condition") or []
            action = rule.get("action") or {}
            adds = action.get("add") or []
            if action.get("inheritRelation") and not adds:
                continue
            if not conditions or not adds:
                continue
            bindings = [{}]
            for pattern in conditions:
                nxt = []
                for binding in bindings:
                    for edge in facts:
                        hit = _match_pattern(pattern, edge, binding)
                        if hit:
                            nxt.append(hit)
                bindings = nxt
                if not bindings:
                    break
            for binding in bindings:
                evidence_edges = binding.get("_edges") or []
                chain = _format_chain(evidence_edges, node_map)
                for tmpl in adds:
                    source, relation, target = _instantiate(tmpl, binding)
                    if not source or not target or not relation or source == target:
                        continue
                    if is_forbidden_inference(relation, evidence_edges):
                        continue
                    key = (source, relation, target)
                    if key in seen:
                        continue
                    src_name = (node_map.get(source) or {}).get("name") or source
                    tgt_name = (node_map.get(target) or {}).get("name") or target
                    interval = None
                    for ev in evidence_edges:
                        props_e = ev.get("properties") or {}
                        vf, vt = props_e.get("valid_from") or "", props_e.get("valid_to") or ""
                        if interval is None:
                            interval = (vf, vt)
                        else:
                            interval = intersect_interval(interval[0], interval[1], vf, vt)
                            if interval is None:
                                break
                    if evidence_edges and interval is None:
                        continue
                    vf, vt = interval or ("", "")
                    if vf and str(vf).startswith("0001"):
                        vf = ""
                    window = format_validity(vf, vt)
                    explain = explanation_from_chain(
                        chain, (source, relation, target, src_name, tgt_name)
                    )
                    explain = f"{explain}\n有效期: {window}"
                    rec = {
                        "source": source,
                        "target": target,
                        "relation": relation,
                        "properties": {
                            "inferred": True,
                            "semantic": True,
                            "rule_id": rule.get("id"),
                            "rule_name": rule.get("name"),
                            "strength": 0.55,
                            "evidence": chain,
                            "explanation": explain,
                            "valid_from": vf,
                            "valid_to": vt,
                        },
                    }
                    seen.add(key)
                    facts.append({
                        "source": source,
                        "target": target,
                        "relation": relation,
                        "properties": rec["properties"],
                    })
                    inferred.append(rec)
                    added += 1
        if added == 0:
            break
    return inferred


def is_semantic_relation(name):
    return name in SEMANTIC_RELATIONS
