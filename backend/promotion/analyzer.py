"""晋升推演 AI 事实分析：仅第一次生成，后续权重调整不调用。"""

import json
import time

from llm_client import get_client, is_mock_mode, _log_llm_failure, _get_env


SYSTEM_PROMPT = """你是组织晋升推演分析师。根据候选人数字孪生事实，为每个候选人生成结构化分析。
只基于给定事实，不要编造不存在的项目或关系。
输出 JSON：
{
  "candidates": [
    {
      "person_id": "成员ID",
      "person": "姓名",
      "facts": ["可核验事实1", "事实2"],
      "relationship": {"influence": "一句话影响力描述"},
      "reasoning": ["晋升理由1", "理由2"],
      "risk": ["风险1"],
      "future_prediction": {
        "team_size_growth": 8,
        "expected_result": "成为领导后的预期表现"
      }
    }
  ]
}
facts 3-5 条；reasoning 2-4 条；risk 1-3 条。中文。"""

AI_TIMEOUT_SECONDS = 90


def analyze_candidates(payload):
    """
    payload: {
      role, style, custom_requirements, members: [{id,name,role,persona,...}],
      features: {id: {...}}, evidence, events
    }
    """
    members = payload.get("members") or []
    if is_mock_mode():
        print("[promotion][AI] 跳过真实请求：未配置 API Key，走规则引擎")
        result = _mock_analyze(payload)
        result["mock_mode"] = True
        result["degraded"] = True
        return result

    prompt = _build_prompt(payload)
    model = _get_env("DEEPSEEK_MODEL_EXTRACT", "deepseek-ai/DeepSeek-V3")
    base_url = _get_env("SILICONFLOW_BASE_URL", "https://api.siliconflow.cn/v1")
    print("[promotion][AI] ========== 请求开始 ==========")
    print(f"[promotion][AI] model={model}")
    print(f"[promotion][AI] base_url={base_url}")
    print(f"[promotion][AI] timeout={AI_TIMEOUT_SECONDS}s")
    print(f"[promotion][AI] candidates={len(members)}")
    print(f"[promotion][AI] prompt_chars={len(prompt)}")
    print(f"[promotion][AI] max_tokens=4096 temperature=0.2 json_object")
    names = ", ".join((m.get("name") or m.get("id") or "") for m in members[:12])
    print(f"[promotion][AI] people={names}")
    started = time.time()
    try:
        client = get_client()
        if client is None:
            raise ValueError("LLM 客户端未初始化")
        if hasattr(client, "with_options"):
            client = client.with_options(timeout=AI_TIMEOUT_SECONDS)
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            response_format={"type": "json_object"},
            temperature=0.2,
            max_tokens=4096,
        )
        elapsed = time.time() - started
        content = response.choices[0].message.content
        usage = getattr(response, "usage", None)
        print(f"[promotion][AI] 请求成功 elapsed={elapsed:.1f}s")
        if usage:
            print(
                f"[promotion][AI] tokens prompt={getattr(usage, 'prompt_tokens', None)} "
                f"completion={getattr(usage, 'completion_tokens', None)} "
                f"total={getattr(usage, 'total_tokens', None)}"
            )
        print(f"[promotion][AI] response_chars={len(content or '')}")
        if not content:
            raise ValueError("LLM 返回空 content")
        raw = json.loads(content)
        result = _normalize(raw, payload)
        print(f"[promotion][AI] parsed_candidates={len(result.get('candidates') or [])}")
        print("[promotion][AI] ========== 请求结束 ==========")
        result["mock_mode"] = False
        result["degraded"] = False
        return result
    except Exception as e:
        elapsed = time.time() - started
        print(f"[promotion][AI] 请求失败 elapsed={elapsed:.1f}s type={type(e).__name__} err={e}")
        print("[promotion][AI] 降级到规则引擎")
        print("[promotion][AI] ========== 请求结束 ==========")
        _log_llm_failure("promotion", e)
        result = _mock_analyze(payload)
        result["mock_mode"] = is_mock_mode()
        result["degraded"] = True
        return result


def _build_prompt(payload):
    role = payload.get("role") or {}
    style = payload.get("style") or {}
    reqs = payload.get("custom_requirements") or []
    req_text = "、".join(f"{r.get('name')}({r.get('weight')}%)" for r in reqs) or "无"
    lines = []
    for m in payload.get("members") or []:
        feat = (payload.get("features") or {}).get(m["id"]) or {}
        ev = (payload.get("evidence") or {}).get(m["id"]) or {}
        projects = ", ".join(list((ev.get("projects") or {}).keys())[:5]) or "无"
        skills = ", ".join(list((ev.get("skills") or {}).keys())[:6]) or "无"
        lines.append(
            f"- ID:{m['id']} 姓名:{m.get('name')} 职位:{m.get('role')} "
            f"人设:{m.get('persona','')[:80]} "
            f"影响力:{feat.get('influence')} 交付:{feat.get('delivery')} "
            f"培养:{feat.get('mentoring')} 冲突风险:{feat.get('conflict_risk')} "
            f"岗位匹配:{feat.get('role_skill_match')} "
            f"近30天项目:{projects} 技能:{skills} 日报{ev.get('days',0)}条"
        )
    events = payload.get("events") or []
    ev_text = "\n".join(
        f"- [{e.get('event_time','')}] {e.get('raw_summary','')}" for e in events[-10:]
    ) or "（无）"
    return f"""目标岗位：{role.get('role_name') or '未指定'}
岗位要求：{', '.join(role.get('required_skills') or [])}
领导风格：{style.get('type') or ''} — {style.get('description') or ''}
个性化要求：{req_text}

候选人：
{chr(10).join(lines)}

近期事件：
{ev_text}

请输出 JSON。"""


def _normalize(raw, payload):
    by_id = {m["id"]: m for m in payload.get("members") or []}
    items = raw.get("candidates") or raw.get("results") or []
    if isinstance(raw, list):
        items = raw
    out = []
    for item in items:
        pid = item.get("person_id") or item.get("id")
        if pid not in by_id:
            name = item.get("person") or item.get("name")
            pid = next((m["id"] for m in by_id.values() if m.get("name") == name), None)
        if not pid:
            continue
        out.append({
            "person_id": pid,
            "person": by_id[pid].get("name"),
            "facts": list(item.get("facts") or [])[:6],
            "relationship": item.get("relationship") if isinstance(item.get("relationship"), dict) else {
                "influence": str(item.get("relationship") or ""),
            },
            "reasoning": list(item.get("reasoning") or [])[:5],
            "risk": list(item.get("risk") or [])[:4],
            "future_prediction": item.get("future_prediction") or {},
        })
    return {"candidates": out}


def _mock_analyze(payload):
    candidates = []
    for m in payload.get("members") or []:
        feat = (payload.get("features") or {}).get(m["id"]) or {}
        ev = (payload.get("evidence") or {}).get(m["id"]) or {}
        projects = list((ev.get("projects") or {}).keys())[:3]
        facts = []
        if projects:
            facts.append(f"近30天主要投入：{'、'.join(projects)}")
        if ev.get("days"):
            facts.append(f"近30天提交日报 {ev.get('days')} 条，累计影响分 {ev.get('impact') or 0}")
        if feat.get("influence"):
            facts.append(f"组织影响力 {int(feat.get('influence') or 0)}，协作连接较{'密' if feat.get('coordination',0)>60 else '疏'}")
        if not facts:
            facts.append("当前可核验行为数据有限，评分主要来自岗位与关系模型")
        reasoning = []
        if feat.get("professional", 0) >= 60:
            reasoning.append("专业能力与岗位技能要求匹配较好")
        if feat.get("delivery", 0) >= 60:
            reasoning.append("近期结果交付有连续证据")
        if feat.get("mentoring", 0) >= 55:
            reasoning.append("具备带教/培养他人的痕迹")
        if not reasoning:
            reasoning.append("综合画像中规中矩，需更多管理场景验证")
        risks = []
        if feat.get("conflict_risk", 0) >= 40:
            risks.append("跨协作冲突信号偏高，晋升后需关注协同成本")
        if feat.get("management_potential", 0) < 55:
            risks.append("管理经验证据不足")
        if feat.get("stability", 0) < 50:
            risks.append("情绪稳定性一般，高压场景需观察")
        if not risks:
            risks.append("未见显著红线风险，主要不确定性在任职后的带队规模")
        growth = 4 + int((feat.get("influence") or 40) / 20)
        candidates.append({
            "person_id": m["id"],
            "person": m.get("name"),
            "facts": facts,
            "relationship": {
                "influence": f"影响力 {int(feat.get('influence') or 0)}，信任 {int(feat.get('trust') or 50)}",
            },
            "reasoning": reasoning,
            "risk": risks,
            "future_prediction": {
                "team_size_growth": growth,
                "expected_result": (
                    "有望提升团队交付效率与技术判断质量"
                    if feat.get("professional", 0) >= 65
                    else "任领导后需补齐管理与协同短板，短期内以稳定交付为主"
                ),
            },
        })
    return {"candidates": candidates}
