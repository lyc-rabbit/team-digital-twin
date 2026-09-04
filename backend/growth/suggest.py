"""草稿文本 → 候选事件标签。LLM 只分类，不写库、不改写事实。"""

import json

from database import get_all_members
from llm_client import get_client, is_mock_mode, _get_env, _log_llm_failure

from .taxonomy import EVENT_TYPES, FIELD_DEFS, get_template, get_tag, get_type

ALLOWED_FIELDS = set(FIELD_DEFS.keys())
MAX_MATCHES = 5

KEYWORD_RULES = [
    ("project", "project_risk", ("风险", "延期", "延误", "阻塞", "事故", "故障", "blocked", "延期了")),
    ("project", "project_delivery", ("交付", "上线", "验收", "发布", "交付物")),
    ("project", "project_progress", ("推进", "进度", "里程碑", "排期", "迭代")),
    ("project", "tech_decision", ("技术决策", "方案选型", "架构", "技术选型")),
    ("project", "tech_breakthrough", ("突破", "攻克", "跑通")),
    ("project", "tech_failure", ("失败", "回滚", "没过", "挂了")),
    ("project", "project_retro", ("复盘", "回顾")),
    ("people_development", "newcomer_progress", ("新人进步", "上手很快", "独立完成")),
    ("people_development", "newcomer_issue", ("新人问题", "带不起来", "不会做")),
    ("people_development", "newcomer_task", ("新人任务", "入职任务", "L0", "L1")),
    ("people_development", "coaching", ("指导", "带教", "辅导", "code review")),
    ("people_development", "authorization", ("授权给", "让他负责")),
    ("people_development", "empowerment", ("放权", "自己拍板")),
    ("people_development", "development_result", ("培养结果", "出师")),
    ("management", "task_assignment", ("分配任务", "布置", "派活")),
    ("management", "decision", ("拍板", "做了决定", "决策")),
    ("management", "conflict", ("冲突", "争执", "吵起来", "对立")),
    ("management", "coordination", ("协调", "对齐各方")),
    ("management", "resource_seek", ("要人", "要资源", "争取资源")),
    ("management", "risk_escalate", ("上报", "升级风险", "同步领导风险")),
    ("management", "institution", ("制度", "规范", "流程建设")),
    ("upward", "report", ("汇报", "周报", "向领导", "跟上级说")),
    ("upward", "superior_decision", ("上级决定", "领导拍板", "上面定了")),
    ("upward", "superior_auth", ("上级授权", "领导让我负责")),
    ("upward", "superior_feedback", ("上级反馈", "领导说", "被点评")),
    ("upward", "superior_recognition", ("认可", "表扬", "夸了")),
    ("upward", "superior_challenge", ("质疑", "被问住", "挑战")),
    ("upward", "resource_support", ("给了资源", "批了人", "支持到位")),
    ("communication", "problem_raise", ("问题", "求助", "帮忙看", "卡住了", "请教")),
    ("communication", "requirement_clarify", ("需求不清", "澄清需求", "理解不一致")),
    ("communication", "info_pass", ("同步", "转告", "通知", "信息传递")),
    ("communication", "comm_error", ("听错", "理解偏差", "没传达到", "误传")),
    ("communication", "problem_define", ("问题定义", "根因", "边界是")),
    ("communication", "cross_collab", ("跨组", "跨专业", "协作")),
    ("relationship", "trust_up", ("更信任", "信任增强")),
    ("relationship", "trust_down", ("不信任", "信任下降", "说话不算")),
    ("relationship", "cooperate", ("一起做", "合作")),
    ("relationship", "help", ("帮了他", "帮忙")),
    ("relationship", "resource_exchange", ("换资源", "互相支援")),
    ("relationship", "informal_shift", ("小圈子", "私下", "非正式")),
]


def catalog_pairs():
    out = []
    for t in EVENT_TYPES:
        for tag in t["tags"]:
            out.append({
                "event_type": t["id"],
                "event_tag": tag["id"],
                "type_label": t["label"],
                "tag_label": tag["label"],
            })
    return out


def _pair_key(type_id, tag_id):
    return f"{type_id}::{tag_id}"


def _valid_pair(type_id, tag_id):
    return bool(get_tag(type_id, tag_id))


def _mention_members(text, members):
    found = []
    blob = text or ""
    ranked = sorted(members, key=lambda m: len(m.get("name") or ""), reverse=True)
    for m in ranked:
        name = (m.get("name") or "").strip()
        if len(name) < 2:
            continue
        if name in blob and m["id"] not in found:
            found.append(m["id"])
    return found


def _fill_fields(type_id, tag_id, text, llm_fields=None):
    tpl = get_template(type_id, tag_id)
    ids = [f["id"] for f in (tpl.get("fields") or [])]
    llm_fields = llm_fields or {}
    out = {}
    primary = "facts" if "facts" in ids else (ids[0] if ids else "facts")
    out[primary] = (text or "").strip()
    for fid in ids:
        if fid == primary:
            continue
        val = str(llm_fields.get(fid) or "").strip()
        if val and val != out[primary]:
            out[fid] = val
    return out


def _decorate(type_id, tag_id, text, confidence, reason, llm_fields=None, person_id="", related=None):
    tpl = get_template(type_id, tag_id)
    t = get_type(type_id) or {}
    tag = get_tag(type_id, tag_id) or {}
    return {
        "event_type": type_id,
        "event_tag": tag_id,
        "type_label": t.get("label") or type_id,
        "tag_label": tag.get("label") or tag_id,
        "title": tpl.get("title") or tag.get("label") or tag_id,
        "confidence": round(float(confidence), 2),
        "reason": reason or "",
        "suggested_fields": _fill_fields(type_id, tag_id, text, llm_fields),
        "person_id": person_id or "",
        "related_persons": related or [],
        "selected_default": float(confidence) >= 0.55,
    }


def _rule_suggest(text):
    blob = text or ""
    scored = []
    for type_id, tag_id, words in KEYWORD_RULES:
        hits = [w for w in words if w.lower() in blob.lower()]
        if not hits:
            continue
        score = min(0.95, 0.42 + 0.16 * len(hits))
        scored.append((score, type_id, tag_id, "命中：" + "、".join(hits[:4])))
    scored.sort(key=lambda x: -x[0])
    uniq = []
    seen = set()
    for score, type_id, tag_id, reason in scored:
        key = _pair_key(type_id, tag_id)
        if key in seen:
            continue
        seen.add(key)
        uniq.append(_decorate(type_id, tag_id, text, score, reason + "（规则匹配）"))
        if len(uniq) >= MAX_MATCHES:
            break
    return uniq


def _catalog_prompt():
    lines = []
    for item in catalog_pairs():
        lines.append(f"- {item['event_type']}/{item['event_tag']}  {item['type_label']} / {item['tag_label']}")
    return "\n".join(lines)


def _sanitize_llm_fields(raw):
    if not isinstance(raw, dict):
        return {}
    out = {}
    for k, v in raw.items():
        if k in ALLOWED_FIELDS and str(v).strip():
            out[k] = str(v).strip()
    return out


def _from_llm_payload(data, text, members, created_by):
    rows = data.get("matches") or data.get("tags") or data.get("candidates") or []
    if isinstance(rows, dict):
        rows = [rows]
    mentioned = _mention_members(text, members)
    created = created_by or ""
    default_person = next((mid for mid in mentioned if mid != created), "")
    default_related = [mid for mid in mentioned if mid not in {created, default_person}]
    out = []
    seen = set()
    for row in rows:
        if not isinstance(row, dict):
            continue
        type_id = (row.get("event_type") or row.get("type") or "").strip()
        tag_id = (row.get("event_tag") or row.get("tag") or "").strip()
        if not _valid_pair(type_id, tag_id):
            continue
        key = _pair_key(type_id, tag_id)
        if key in seen:
            continue
        seen.add(key)
        try:
            conf = float(row.get("confidence") or 0)
        except (TypeError, ValueError):
            conf = 0.0
        conf = max(0.0, min(1.0, conf))
        person = (row.get("person_id") or "").strip()
        if person not in {m["id"] for m in members}:
            person = default_person
        related = row.get("related_persons") if isinstance(row.get("related_persons"), list) else default_related
        related = [x for x in related if x in {m["id"] for m in members} and x not in {created, person}]
        out.append(_decorate(
            type_id, tag_id, text, conf,
            (row.get("reason") or "").strip(),
            _sanitize_llm_fields(row.get("suggested_fields")),
            person_id=person,
            related=related,
        ))
        if len(out) >= MAX_MATCHES:
            break
    return out


def _llm_suggest(text, members, created_by):
    client = get_client()
    if client is None:
        raise ValueError("LLM 未初始化")
    members_desc = "\n".join(
        f"- ID:{m['id']} 姓名:{m['name']} 职位:{m.get('role') or ''}" for m in members
    ) or "（暂无成员）"
    prompt = f"""从清单中为这段团队事件草稿匹配 1～{MAX_MATCHES} 个标签。只能用清单里的 event_type/event_tag，不要发明。

标签清单：
{_catalog_prompt()}

成员：
{members_desc}

草稿：
{text}

规则：
- 一件事可以对应多个标签（例如既是汇报也是项目风险）
- confidence 0～1，无关的不要返回
- reason 用一句话说明为何匹配，不要编造草稿里没有的情节
- suggested_fields 只能摘录草稿已有信息；没有的字段不要填
- facts 填用户原文；不要润色、不要扩写
- person_id / related_persons 只能用上面的成员 ID，对不上就留空

输出 JSON：
{{"matches":[{{"event_type":"","event_tag":"","confidence":0.0,"reason":"","suggested_fields":{{"background":"","facts":""}},"person_id":"","related_persons":[]}}]}}"""
    response = client.chat.completions.create(
        model=_get_env("DEEPSEEK_MODEL_EXTRACT", "deepseek-ai/DeepSeek-V3"),
        messages=[
            {"role": "system", "content": "你只做事件标签分类。不写库、不算分、不编造事实。只输出 JSON。"},
            {"role": "user", "content": prompt},
        ],
        response_format={"type": "json_object"},
        temperature=0.0,
        max_tokens=2048,
    )
    content = response.choices[0].message.content
    if not content:
        raise ValueError("LLM 返回空 content")
    data = json.loads(content)
    return _from_llm_payload(data, text, members, created_by)


def suggest_tags(text, created_by=""):
    raw = (text or "").strip()
    if not raw:
        raise ValueError("请先输入要记录的事件内容")
    if len(raw) > 8000:
        raw = raw[:8000]
    members = get_all_members()
    mentioned = _mention_members(raw, members)
    created = created_by or ""
    person_id = next((mid for mid in mentioned if mid != created), "")
    related = [mid for mid in mentioned if mid not in {created, person_id}]

    degraded = False
    source = "llm"
    matches = []
    if is_mock_mode():
        matches = _rule_suggest(raw)
        degraded = True
        source = "rules"
    else:
        try:
            matches = _llm_suggest(raw, members, created)
        except Exception as e:
            _log_llm_failure("suggest_tags", e)
            matches = _rule_suggest(raw)
            degraded = True
            source = "rules"

    for item in matches:
        if not item.get("person_id"):
            item["person_id"] = person_id
        if not item.get("related_persons"):
            item["related_persons"] = related

    return {
        "text": raw,
        "matches": matches,
        "mentioned_member_ids": mentioned,
        "source": source,
        "mock_mode": is_mock_mode(),
        "degraded": degraded,
        "catalog": catalog_pairs(),
    }
