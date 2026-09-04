"""V3 Entity Extractor —— 从非结构化文本抽取人员 / 关系 / 事件。"""

import json
import re

from llm_client import get_client, is_mock_mode, _log_llm_failure, _get_env
from ..ontology.relations import (
    RELATION_TYPES,
    REL_COLLABORATE,
    REL_CONFLICT,
    REL_EXECUTION_RESPONSIBILITY,
    REL_ORG_RESPONSIBILITY,
    REL_REPORT_TO,
    REL_TRUST,
    relation_template,
)
from ..ontology.nodes import node_template
from ..repository.facade import get_store


EXTRACT_SYSTEM = """你是组织知识图谱抽取器。从文本中抽取人员、项目、成果、贡献、培养行为及其关系。
只使用给定成员名单中的姓名进行匹配。

关系类型必须是以下之一：
REPORT_TO, COLLABORATE_WITH, TRUST, CONFLICT, CONTROL_RESOURCE, INFORMAL_MEMBER,
ORG_RESPONSIBILITY, EXECUTION_RESPONSIBILITY, MANAGEMENT_RESPONSIBILITY, REPORTING_RESPONSIBILITY,
OWNER, WORKS_ON, MADE_CONTRIBUTION, CONTRIBUTES_TO, ACHIEVEMENT_OWNERSHIP,
PERFORMED_TRAINING, TRAINING_TARGET

禁止跨语义域猜测：
- 不能因为 A 是 B 的上级 / 存在 REPORT_TO 就输出 MENTOR 或培养。
- 不能因为 A 是项目 OWNER / 负责人 就输出技术贡献或 HAS_CAPABILITY。
- 不能因为成果归 A 就输出 A 对成果的 TechnicalContribution。
- 成果汇报请用 REPORTING_RESPONSIBILITY 或 contribution_type=reporting，不要写成技术贡献。
培养必须是文本里明确的指导/反馈/Code Review 行为，写成 TrainingAction + PERFORMED_TRAINING / TRAINING_TARGET。

输出 JSON：
{
  "entities": [
    {"type":"Person|Project|Event|Resource|Knowledge|Achievement|Contribution|TrainingAction","name":"...","attributes":{}}
  ],
  "relations": [
    {
      "source":"张三",
      "relation":"EXECUTION_RESPONSIBILITY",
      "target":"AI客服",
      "confidence":0.87,
      "properties":{"evidence":["..."]}
    }
  ]
}
没有把握的关系不要输出。confidence 范围 0-1。"""


def extract_relations(text, members, source_type="document", temperature=0.0):
    """
    输入非结构化文本，输出 {entities, relations, mock_mode, degraded}
    """
    members = members or []
    if is_mock_mode():
        result = _mock_extract(text, members)
        result["mock_mode"] = True
        result["degraded"] = True
        return result

    members_desc = "\n".join(
        f"- ID:{m.get('id')} 姓名:{m.get('name')} 职位:{m.get('role','')}"
        for m in members
    ) or "（暂无成员名单）"

    prompt = f"""已知团队成员：
{members_desc}

待抽取文本（来源:{source_type}）：
{text}

请输出 JSON。"""

    try:
        client = get_client()
        response = client.chat.completions.create(
            model=_get_env("DEEPSEEK_MODEL_EXTRACT", "deepseek-ai/DeepSeek-V3"),
            messages=[
                {"role": "system", "content": EXTRACT_SYSTEM},
                {"role": "user", "content": prompt},
            ],
            response_format={"type": "json_object"},
            temperature=float(temperature if temperature is not None else 0.0),
            max_tokens=2048,
        )
        content = response.choices[0].message.content
        if not content:
            raise ValueError("LLM 返回空 content")
        raw = json.loads(content)
        result = _normalize(raw, members)
        result["mock_mode"] = False
        result["degraded"] = False
        return result
    except Exception as e:
        _log_llm_failure("oig_extract", e)
        result = _mock_extract(text, members)
        result["mock_mode"] = is_mock_mode()
        result["degraded"] = True
        return result


def merge_extraction_runs(runs):
    """多次抽取结果按 实体(type,name) / 关系(source,relation,target) 去重，置信度取最高。"""
    entities = {}
    relations = {}
    for idx, run in enumerate(runs or []):
        for ent in run.get("entities") or []:
            name = (ent.get("name") or "").strip()
            if not name:
                continue
            key = ((ent.get("type") or "Entity"), name)
            entities.setdefault(key, dict(ent, name=name))
        for rel in run.get("relations") or []:
            src = (rel.get("source") or "").strip()
            tgt = (rel.get("target") or "").strip()
            kind = rel.get("relation") or REL_COLLABORATE
            if not src or not tgt:
                continue
            key = (src, kind, tgt)
            conf = float(rel.get("confidence") or 0)
            prev = relations.get(key)
            if not prev:
                item = dict(rel, source=src, target=tgt, relation=kind, seen_in_runs=1)
                item["confidence"] = conf
                relations[key] = item
                continue
            prev["seen_in_runs"] = int(prev.get("seen_in_runs") or 1) + 1
            if conf > float(prev.get("confidence") or 0):
                props = dict(prev.get("properties") or {})
                extra = dict(rel.get("properties") or {})
                ev = list(props.get("evidence") or [])
                for x in extra.get("evidence") or []:
                    if x not in ev:
                        ev.append(x)
                extra["evidence"] = ev[:20]
                merged = dict(rel, source=src, target=tgt, relation=kind)
                merged["properties"] = extra
                merged["confidence"] = conf
                merged["seen_in_runs"] = prev["seen_in_runs"]
                relations[key] = merged
            else:
                props = dict(prev.get("properties") or {})
                ev = list(props.get("evidence") or [])
                for x in (rel.get("properties") or {}).get("evidence") or []:
                    if x not in ev:
                        ev.append(x)
                props["evidence"] = ev[:20]
                prev["properties"] = props
    any_ok = any(not r.get("degraded") for r in (runs or []))
    return {
        "entities": list(entities.values()),
        "relations": sorted(relations.values(), key=lambda x: -float(x.get("confidence") or 0)),
        "mock_mode": all(bool(r.get("mock_mode")) for r in (runs or [])) if runs else False,
        "degraded": not any_ok if runs else True,
        "runs": len(runs or []),
    }


def apply_extraction(result, members=None, source_type="document"):
    """把抽取结果写入图谱。实体必须先 Normalize → Resolve，禁止直接 CREATE。"""
    from entity_governance.service import follow_canonical, resolve_entity
    from entity_governance.types import to_entity_type

    store = get_store()
    members = members or []
    name_to_id = {m["name"]: m["id"] for m in members}
    for n in store.list_nodes("Person"):
        name_to_id.setdefault(n.get("name"), n["id"])

    written_nodes = 0
    written_edges = 0
    resolved_log = []

    for ent in result.get("entities") or []:
        etype = ent.get("type") or "Event"
        name = (ent.get("name") or "").strip()
        if not name:
            continue
        if etype == "Person":
            if name not in name_to_id:
                continue
            continue
        attrs = ent.get("attributes") or {}
        resolved = resolve_entity(
            to_entity_type(etype),
            name,
            attributes=attrs,
            source={"type": source_type},
            create_if_new=True,
        )
        nid = resolved["canonical_entity_id"]
        display = resolved.get("canonical_name") or name
        existing = store.get_node(nid)
        if not existing:
            node = node_template(etype, nid, display, **attrs)
            node["entity_status"] = "ACTIVE"
            node["canonical_entity_id"] = nid
            store.upsert_node(node)
            written_nodes += 1
        elif resolved.get("via") == "created":
            written_nodes += 1
        name_to_id.setdefault(name, nid)
        resolved_log.append({
            "name": name,
            "decision": resolved.get("decision"),
            "canonical_entity_id": nid,
            "via": resolved.get("via"),
            "score": resolved.get("score"),
        })

    for rel in result.get("relations") or []:
        relation = rel.get("relation") or REL_COLLABORATE
        if relation not in RELATION_TYPES:
            continue
        src = _resolve(rel.get("source"), name_to_id)
        tgt = _resolve(rel.get("target"), name_to_id)
        if src:
            src = follow_canonical(src)
        if tgt:
            tgt = follow_canonical(tgt)
        if not src or not tgt or src == tgt:
            continue
        confidence = float(rel.get("confidence") or 0.6)
        if confidence < 0.45:
            continue
        props = dict(rel.get("properties") or {})
        props["strength"] = float(props.get("strength") or confidence)
        props.setdefault("evidence", [])
        if rel.get("evidence"):
            props["evidence"] = list(props["evidence"]) + [rel["evidence"]]
        edge = relation_template(src, tgt, relation, **props)
        store.upsert_edge(src, tgt, relation, edge["properties"])
        written_edges += 1

    return {"nodes": written_nodes, "edges": written_edges, "resolved": resolved_log}


def _resolve(name, name_to_id):
    if not name:
        return None
    if name in name_to_id:
        return name_to_id[name]
    store = get_store()
    node = store.get_node(name)
    if node:
        return node["id"]
    for n in store.list_nodes():
        if n.get("name") == name:
            return n["id"]
    return None


def _id_of(etype, name):
    slug = re.sub(r"[^0-9a-zA-Z\u4e00-\u9fff]+", "_", name).strip("_").lower()
    prefix = {
        "Project": "project",
        "Event": "event",
        "Resource": "resource",
        "Knowledge": "knowledge",
        "InformalGroup": "group",
        "Department": "dept",
        "Role": "role",
        "Person": "person",
    }.get(etype, "node")
    return f"{prefix}_{slug}"[:80]


def _normalize(raw, members):
    entities = raw.get("entities") or []
    relations = raw.get("relations") or []
    names = {m["name"] for m in members}
    clean_rel = []
    for r in relations:
        src, tgt = r.get("source"), r.get("target")
        if names and src not in names and tgt not in names:
            # 允许项目/资源作为一端
            pass
        rel = r.get("relation") or REL_COLLABORATE
        if rel not in RELATION_TYPES:
            mapping = {
                "collaborate": REL_COLLABORATE,
                "collaborate_with": REL_COLLABORATE,
                "conflict": REL_CONFLICT,
                "trust": REL_TRUST,
                "report_to": REL_REPORT_TO,
                "owner": REL_ORG_RESPONSIBILITY,
                "org_responsibility": REL_ORG_RESPONSIBILITY,
                "execution_responsibility": REL_EXECUTION_RESPONSIBILITY,
                "mentor": REL_COLLABORATE,
            }
            rel = mapping.get(str(rel).lower(), REL_COLLABORATE)
        r = dict(r)
        r["relation"] = rel
        r["confidence"] = float(r.get("confidence") or 0.7)
        clean_rel.append(r)
    return {"entities": entities, "relations": clean_rel}


def _mock_extract(text, members):
    """规则降级：按姓名共现 + 关键词推断关系。"""
    text = text or ""
    hit = [m for m in members if m.get("name") and m["name"] in text]
    entities = [{"type": "Person", "name": m["name"], "attributes": {}} for m in hit]
    relations = []

    def add(src, rel, tgt, conf, **props):
        relations.append({
            "source": src,
            "relation": rel,
            "target": tgt,
            "confidence": conf,
            "properties": props,
        })

    evidence = text.strip()[:80]
    if len(hit) >= 2:
        a, b = hit[0]["name"], hit[1]["name"]
        if any(k in text for k in ("帮助", "指导", "带教", "培养", "教会", "解决")):
            entities.append({
                "type": "TrainingAction",
                "name": f"培养行为:{evidence[:16]}",
                "attributes": {"action_type": "指导", "evidence": evidence},
            })
        elif any(k in text for k in ("冲突", "争议", "反对", "分歧", "撕", "抱怨")):
            add(a, REL_CONFLICT, b, 0.7, reason=evidence, impact=70, evidence=[evidence])
        elif any(k in text for k in ("汇报", "向", "主管")):
            add(a, REL_REPORT_TO, b, 0.6, current=True, evidence=[evidence])
        else:
            add(a, REL_COLLABORATE, b, 0.65, project=_guess_project(text),
                frequency=1, impact=60, evidence=[evidence])

    if any(k in text for k in ("负责", "owner", "主导")) and hit:
        proj = _guess_project(text)
        if proj:
            entities.append({"type": "Project", "name": proj, "attributes": {"status": "running"}})
            add(hit[0]["name"], REL_ORG_RESPONSIBILITY, proj, 0.7, evidence=[evidence])
            if any(k in text for k in ("主导", "执行", "落地", "开发")):
                add(hit[0]["name"], REL_EXECUTION_RESPONSIBILITY, proj, 0.65, evidence=[evidence])

    return {"entities": entities, "relations": relations}


def _guess_skill(text):
    for kw in ("Agent", "LLM", "Python", "架构", "测试", "产品", "部署"):
        if kw.lower() in text.lower() or kw in text:
            return kw
    return ""


def _guess_project(text):
    m = re.search(r"([\u4e00-\u9fffA-Za-z0-9]{2,16}(?:项目|系统|平台))", text)
    return m.group(1) if m else ""
