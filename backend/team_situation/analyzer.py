"""态势 LLM：只解释结构化指标，区分事实/推断/建议。"""

import json

from llm_client import get_client, is_mock_mode, _log_llm_failure, _get_env


SYSTEM_PROMPT = """你是企业团队态势分析系统。项目中心负责项目事实（阶段/成员/里程碑/风险），你只解释变化并给出管理判断。

禁止：
1. 编造不存在的事实
2. 将推断描述为事实
3. 根据单日数据判断长期趋势
4. 根据日报字数判断工作量
5. 对员工做没有证据的人格判断
6. 将可能性直接描述为确定结论
7. 把项目中心尚未登记的阶段/进度当成已确认事实
8. 建议去「管理项目」（改阶段、改负责人）——那些属于项目中心；你只指出需要关注的变化

所有结论必须：有数据依据、标记事实/推断、给出置信度、尽量提供时间范围。
阶段变化、负责人、开放风险一律视为项目中心事实。日报只用于工作重心与协作推断。
只输出 JSON：
{
  "summary": "一句话团队态势（基于证据）",
  "key_changes": [
    {"title": "", "kind": "人员变化|项目变化|职责变化|风险变化|资源变化", "severity": "info|attention|medium|high",
     "object_id": "", "object_type": "member|project|team", "fact": "", "inference": "", "suggestion": "", "confidence": 0.0, "evidence": []}
  ],
  "member_insights": [
    {"member_id": "", "summary": "", "fact": "", "inference": "", "suggestion": "", "confidence": 0.0}
  ],
  "project_insights": [
    {"project_id": "", "summary": "", "fact": "", "inference": "", "suggestion": "", "confidence": 0.0}
  ],
  "risks": [
    {"title": "", "severity": "", "category": "PROJECT|PERSON|RESOURCE|COLLAB|PROGRESS|STRUCTURE",
     "fact": "", "inference": "", "suggestion": "", "evidence": []}
  ],
  "trends": [
    {"name": "", "direction": "up|down|flat", "fact": "", "inference": ""}
  ],
  "questions": [
    {"member_id": "", "question": ""}
  ],
  "recommendations": [{"text": "", "kind": "suggestion"}]
}
key_changes 最多 5 条。不要输出 Markdown。"""


def analyze(payload):
    if is_mock_mode():
        return _from_metrics(payload, degraded=True)
    try:
        client = get_client()
        if client is None:
            return _from_metrics(payload, degraded=True)
        compact = {
            "health": payload.get("health"),
            "members": [
                {
                    "member_id": m["member_id"], "name": m.get("name"),
                    "workload": m.get("workload_score"), "focus7": m.get("work_focus", {}).get("d7"),
                    "focus_delta": m.get("focus_change"), "projects": m.get("projects"),
                    "owned_projects": m.get("owned_projects"),
                    "pc_roles": m.get("pc_roles"),
                    "core_project_count": m.get("core_project_count"),
                    "report_days_7": m.get("report_days_7"),
                }
                for m in (payload.get("members") or [])[:20]
            ],
            "projects": [
                {
                    "project_id": p["project_id"], "name": p.get("project_name"),
                    "source": p.get("source"),
                    "status": p.get("project_status"),
                    "priority": p.get("priority"),
                    "progress": p.get("progress"),
                    "stage": p.get("current_stage"),
                    "previous_stage": p.get("previous_stage"),
                    "recent_changes": p.get("recent_changes"),
                    "health": p.get("health"),
                    "health_trend": p.get("health_trend"),
                    "open_risks": p.get("open_risks"),
                    "days_since_update": p.get("days_since_update"),
                    "risk_level": p.get("risk_level"),
                    "owner_name": p.get("owner_name"),
                }
                for p in (payload.get("projects") or [])[:20]
            ],
            "detected_changes": (payload.get("changes") or [])[:10],
            "detected_risks": [
                {"title": r.get("title"), "type": r.get("type"), "category": r.get("category"), "evidence": r.get("evidence")}
                for r in (payload.get("risks") or [])[:10]
            ],
            "resource_conflicts": payload.get("resource_conflicts") or [],
            "project_stats": payload.get("project_stats") or {},
            "attention_items": [
                {"title": a.get("title"), "priority": a.get("priority"), "description": a.get("description")}
                for a in (payload.get("attention_items") or [])[:8]
            ],
            "manual_context": [
                {"type": c.get("context_type"), "content": c.get("content"), "source": "manual"}
                for c in (payload.get("manual_context") or [])[:8]
            ],
        }
        print("[situation][AI] 开始态势解释 compact_chars=", len(json.dumps(compact, ensure_ascii=False)))
        resp = client.chat.completions.create(
            model=_get_env("DEEPSEEK_MODEL_EXTRACT", "deepseek-ai/DeepSeek-V3"),
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": "根据下列已计算指标生成态势 JSON，不要新增没有出现的人名或项目名。\n" + json.dumps(compact, ensure_ascii=False)},
            ],
            response_format={"type": "json_object"},
            temperature=0.2,
            max_tokens=3500,
        )
        raw = json.loads(resp.choices[0].message.content or "{}")
        raw["degraded"] = False
        return _merge(payload, raw)
    except Exception as e:
        _log_llm_failure("team_situation", e)
        return _from_metrics(payload, degraded=True)


def _from_metrics(payload, degraded=False):
    health = payload.get("health") or {}
    changes = payload.get("changes") or []
    key = []
    for c in changes[:5]:
        key.append({
            "title": c.get("title"),
            "kind": c.get("change_label") or "人员变化",
            "severity": c.get("severity") or "info",
            "object_id": c.get("object_id"),
            "fact": c.get("description"),
            "inference": "尚需更多天数才能判断是否为长期变化" if (c.get("confidence") or 0) < 0.7 else "可能反映近期职责倾斜",
            "suggestion": "结合当事人确认是临时任务还是职责调整",
            "confidence": c.get("confidence") or 0.6,
            "evidence": c.get("evidence") or [],
        })
    summary = "；".join((health.get("reasons") or [])[:3]) or "数据不足，仅完成结构化汇总"
    return _merge(payload, {
        "summary": summary,
        "key_changes": key,
        "member_insights": [],
        "project_insights": [],
        "risks": [{"title": r.get("title"), "severity": r.get("severity"), "fact": r.get("description"), "inference": "", "suggestion": "", "evidence": r.get("evidence")} for r in (payload.get("risks") or [])[:6]],
        "trends": [],
        "questions": payload.get("questions") or [],
        "recommendations": [],
        "degraded": degraded,
    })


def _merge(payload, llm):
    by_mid = {m["member_id"]: m for m in payload.get("members") or []}
    for ins in llm.get("member_insights") or []:
        row = by_mid.get(ins.get("member_id"))
        if row:
            parts = [ins.get("fact"), ins.get("inference"), ins.get("suggestion")]
            row["summary"] = ins.get("summary") or " ".join(p for p in parts if p)
            if ins.get("confidence"):
                row["confidence"] = ins["confidence"]
    by_pid = {p["project_id"]: p for p in payload.get("projects") or []}
    for ins in llm.get("project_insights") or []:
        row = by_pid.get(ins.get("project_id"))
        if row:
            row["summary"] = ins.get("summary") or ins.get("inference") or ins.get("fact") or ""
    questions = list(payload.get("questions") or [])
    for q in llm.get("questions") or []:
        if q.get("question") and not any(x.get("question") == q["question"] for x in questions):
            questions.append(q)
    return {
        "summary": llm.get("summary") or "",
        "key_changes": (llm.get("key_changes") or [])[:5],
        "member_insights": llm.get("member_insights") or [],
        "project_insights": llm.get("project_insights") or [],
        "risks_comment": llm.get("risks") or [],
        "trends": llm.get("trends") or [],
        "questions": questions,
        "recommendations": llm.get("recommendations") or [],
        "degraded": bool(llm.get("degraded")),
    }
