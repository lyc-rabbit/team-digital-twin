"""V3 Entity Extractor —— 从非结构化文本抽取人员 / 关系 / 事件。"""

import json
import re

from llm_client import get_client, is_mock_mode, _log_llm_failure, _get_env
from ..ontology.relations import (
    RELATION_TYPES,
    REL_COLLABORATE,
    REL_MENTOR,
    REL_CONFLICT,
    REL_TRUST,
    REL_OWNER,
    REL_REPORT_TO,
    relation_template,
)
from ..ontology.nodes import node_template
from ..repository.facade import get_store


EXTRACT_SYSTEM = """你是组织知识图谱抽取器。从文本中抽取人员、项目、事件及其关系。
只使用给定成员名单中的姓名进行匹配。关系类型必须是以下之一：
REPORT_TO, COLLABORATE_WITH, MENTOR, TRUST, CONFLICT, CONTROL_RESOURCE, OWNER, INFORMAL_MEMBER

输出 JSON：
{
  "entities": [
    {"type":"Person|Project|Event|Resource|Knowledge|InformalGroup","name":"...","attributes":{}}
  ],
  "relations": [
    {
      "source":"张三",
      "relation":"MENTOR",
      "target":"李四",
      "confidence":0.87,
      "properties":{"skill":"Agent开发","evidence":["..."]}
    }
  ]
}
没有把握的关系不要输出。confidence 范围 0-1。"""


def extract_relations(text, members, source_type="document"):
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
            temperature=0.0,
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


def apply_extraction(result, members=None):
    """把抽取结果写入图谱，返回写入的节点/边数量。"""
    store = get_store()
    members = members or []
    name_to_id = {m["name"]: m["id"] for m in members}
    for n in store.list_nodes("Person"):
        name_to_id.setdefault(n.get("name"), n["id"])

    written_nodes = 0
    written_edges = 0

    for ent in result.get("entities") or []:
        etype = ent.get("type") or "Event"
        name = (ent.get("name") or "").strip()
        if not name:
            continue
        if etype == "Person":
            if name not in name_to_id:
                continue
            continue
        nid = _id_of(etype, name)
        attrs = ent.get("attributes") or {}
        store.upsert_node(node_template(etype, nid, name, **attrs))
        written_nodes += 1
        name_to_id.setdefault(name, nid)

    for rel in result.get("relations") or []:
        relation = rel.get("relation") or REL_COLLABORATE
        if relation not in RELATION_TYPES:
            continue
        src = _resolve(rel.get("source"), name_to_id)
        tgt = _resolve(rel.get("target"), name_to_id)
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

    return {"nodes": written_nodes, "edges": written_edges}


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
                "mentor": REL_MENTOR,
                "collaborate": REL_COLLABORATE,
                "collaborate_with": REL_COLLABORATE,
                "conflict": REL_CONFLICT,
                "trust": REL_TRUST,
                "report_to": REL_REPORT_TO,
                "owner": REL_OWNER,
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
            add(a, REL_MENTOR, b, 0.75, skill=_guess_skill(text), evidence=[evidence])
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
            add(hit[0]["name"], REL_OWNER, proj, 0.7, evidence=[evidence])

    return {"entities": entities, "relations": relations}


def _guess_skill(text):
    for kw in ("Agent", "LLM", "Python", "架构", "测试", "产品", "部署"):
        if kw.lower() in text.lower() or kw in text:
            return kw
    return ""


def _guess_project(text):
    m = re.search(r"([\u4e00-\u9fffA-Za-z0-9]{2,16}(?:项目|系统|平台))", text)
    return m.group(1) if m else ""
