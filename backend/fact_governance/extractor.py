"""通用事实抽取：产出 Fact 候选，不直接写图谱。"""

import json
import re

from llm_client import get_client, is_mock_mode, _log_llm_failure, _get_env

from .types import METHOD_LLM, ontology_relation_of

FACT_EXTRACT_SYSTEM = """你是组织数字孪生的通用事实抽取器。从文本抽取「现实世界发生了什么」，不要直接生成最终关系网。
每条事实是一个主谓宾三元组，可带时间。

输出 JSON：
{
  "facts": [
    {
      "subject": "张三",
      "subject_type": "Person|Project|Organization|Task|Event|Resource|Role|Capability|Achievement|Contribution|TrainingAction",
      "predicate": "组织责任|执行责任|管理责任|汇报责任|参与|协作|指导|汇报|分歧|成果归属|技术贡献|架构贡献|隶属",
      "object": "AI客服项目",
      "object_type": "Person|Project|Organization|Task|Event|Resource|Role|Capability|Achievement|Contribution|TrainingAction",
      "fact_type": "RELATION|EVENT|ATTRIBUTE|DECISION",
      "valid_from": "YYYY-MM-DD 或空",
      "valid_to": "YYYY-MM-DD 或空",
      "confidence": 0.94,
      "source_text": "支撑该事实的原文短句"
    }
  ]
}
规则：
- 一条原文可抽多条事实（职责、协作、分歧、决策都要分开）。
- 「负责」必须拆开：组织责任 / 执行责任 / 管理责任 / 汇报责任，不要写成一条笼统负责。
- 不能因为上级/汇报就输出「指导/培养」。
- 不能因为成果归属就输出技术贡献。
- 不要合并成一条「关系网」。
- 没有把握不要输出。confidence 0-1。
- 人名尽量用文本中的原名。
"""


def extract_facts(text, members=None, source_type="document"):
    members = members or []
    if is_mock_mode() or not (text or "").strip():
        result = _mock_facts(text, members)
        result["mock_mode"] = True
        result["degraded"] = True
        result["model"] = "mock"
        return result

    members_desc = "\n".join(
        f"- {m.get('name')} ({m.get('id')})" for m in members if m.get("name")
    ) or "（无成员名单）"
    prompt = f"""已知人员：
{members_desc}

来源类型：{source_type}

文本：
{text}

请输出 JSON。"""
    model = _get_env("DEEPSEEK_MODEL_EXTRACT", "deepseek-ai/DeepSeek-V3")
    try:
        client = get_client()
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": FACT_EXTRACT_SYSTEM},
                {"role": "user", "content": prompt},
            ],
            response_format={"type": "json_object"},
            temperature=0.0,
            max_tokens=2500,
        )
        content = response.choices[0].message.content or "{}"
        raw = json.loads(content)
        facts = _normalize_facts(raw.get("facts") or [])
        return {
            "facts": facts,
            "mock_mode": False,
            "degraded": False,
            "model": model,
            "method": METHOD_LLM,
        }
    except Exception as e:
        _log_llm_failure("fact-extract", e)
        result = _mock_facts(text, members)
        result["mock_mode"] = False
        result["degraded"] = True
        result["model"] = model
        return result


def _normalize_facts(items):
    out = []
    for it in items:
        sub = (it.get("subject") or "").strip()
        pred = (it.get("predicate") or "").strip()
        obj = (it.get("object") or "").strip()
        if not sub or not pred or not obj:
            continue
        try:
            conf = float(it.get("confidence") or 0.7)
        except (TypeError, ValueError):
            conf = 0.7
        out.append({
            "subject": sub,
            "predicate": pred,
            "object": obj,
            "subject_type": it.get("subject_type") or "",
            "object_type": it.get("object_type") or "",
            "fact_type": it.get("fact_type") or "RELATION",
            "valid_from": str(it.get("valid_from") or "")[:10],
            "valid_to": str(it.get("valid_to") or "")[:10],
            "confidence": max(0.0, min(1.0, conf)),
            "source_text": (it.get("source_text") or "")[:500],
            "ontology_relation": ontology_relation_of(pred),
        })
    return out


def _mock_facts(text, members):
    text = text or ""
    hit = [m for m in members if m.get("name") and m["name"] in text]
    facts = []

    def add(sub, pred, obj, **kw):
        facts.append({
            "subject": sub,
            "predicate": pred,
            "object": obj,
            "subject_type": kw.get("st", "Person"),
            "object_type": kw.get("ot", "Project"),
            "fact_type": "RELATION",
            "valid_from": "",
            "valid_to": "",
            "confidence": kw.get("c", 0.7),
            "source_text": text.strip()[:120],
            "ontology_relation": ontology_relation_of(pred),
        })

    project = _guess_project(text)
    if "负责" in text and hit:
        add(hit[0]["name"], "负责", project or "未命名项目", c=0.78)
        if len(hit) >= 2:
            add(hit[1]["name"], "协助", project or "未命名项目", c=0.7)
    if any(k in text for k in ("分歧", "争议", "冲突")) and len(hit) >= 2:
        add(hit[0]["name"], "分歧", hit[1]["name"], ot="Person", c=0.72)
    if "协调" in text and len(hit) >= 3:
        add(hit[2]["name"], "协调", f"{hit[0]['name']}/{hit[1]['name']}", ot="Person", c=0.68)
    if not facts and len(hit) >= 2:
        add(hit[0]["name"], "协作", hit[1]["name"], ot="Person", c=0.65)
    return {"facts": facts, "method": "mock", "model": "mock"}


def _guess_project(text):
    m = re.search(r"([\u4e00-\u9fffA-Za-z0-9]{2,20}(?:项目|系统|平台))", text or "")
    return m.group(1) if m else ""
