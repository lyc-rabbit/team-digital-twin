"""入职指南 / 任务推荐的 LLM 调用。失败则走模板。"""

import json

from llm_client import get_client, is_mock_mode, _log_llm_failure, _get_env
from .templates import template_guide, recommend_tasks_for_gaps, CAPABILITIES


def generate_guide(member, team_names, projects, role_name, tech_stack):
    fallback = template_guide(member, team_names, projects, role_name, tech_stack)
    if is_mock_mode():
        fallback["source"] = "template"
        return fallback
    try:
        client = get_client()
        prompt = f"""为新人生成入职指南 JSON。
新人：{member.get('name')} 职位：{member.get('role')} 人设：{(member.get('persona') or '')[:120]}
目标角色：{role_name or '未指定'}
团队：{'、'.join(team_names[:12])}
项目：{'、'.join(projects[:8]) or '未知'}
技术栈线索：{'、'.join(tech_stack[:8]) or '未知'}

输出：
{{
  "title": "xx入职指南",
  "sections": [
    {{"id": "01", "title": "团队介绍", "body": "..."}},
    {{"id": "02", "title": "项目介绍", "body": "..."}},
    {{"id": "03", "title": "当前项目目标", "body": "..."}},
    {{"id": "04", "title": "技术栈", "body": "..."}},
    {{"id": "05", "title": "开发环境", "body": "..."}},
    {{"id": "06", "title": "Git规范", "body": "..."}},
    {{"id": "07", "title": "AI Coding规范", "body": "..."}},
    {{"id": "08", "title": "项目规则", "body": "..."}},
    {{"id": "09", "title": "常见问题", "body": "..."}},
    {{"id": "10", "title": "联系人", "body": "..."}}
  ]
}}
只输出 JSON，中文，具体可执行，不要空话。"""
        print("[newcomer][AI] 生成入职指南", member.get("name"), "model=", _get_env("DEEPSEEK_MODEL_EXTRACT", "deepseek-ai/DeepSeek-V3"))
        resp = client.chat.completions.create(
            model=_get_env("DEEPSEEK_MODEL_EXTRACT", "deepseek-ai/DeepSeek-V3"),
            messages=[
                {"role": "system", "content": "你是团队入职教练，只输出 JSON。"},
                {"role": "user", "content": prompt},
            ],
            response_format={"type": "json_object"},
            temperature=0.3,
            max_tokens=2500,
        )
        raw = json.loads(resp.choices[0].message.content or "{}")
        sections = raw.get("sections") or fallback["sections"]
        if len(sections) < 8:
            sections = fallback["sections"]
        return {
            "title": raw.get("title") or fallback["title"],
            "generated_at": fallback["generated_at"],
            "sections": sections,
            "source": "ai",
        }
    except Exception as e:
        _log_llm_failure("newcomer_guide", e)
        fallback["source"] = "template"
        return fallback


def recommend_next_tasks(member, target_role, gaps, current_level, evidence_summary):
    fallback = recommend_tasks_for_gaps(
        (target_role or {}).get("id"), gaps, current_level,
    )
    if is_mock_mode():
        return fallback
    try:
        client = get_client()
        cap_text = "、".join(f"{k}:{v}" for k, v in (CAPABILITIES.items()))
        prompt = f"""为新人推荐最多 3 个培养任务，JSON。
新人：{member.get('name')} 当前职位：{member.get('role')}
目标角色：{(target_role or {}).get('role_name')}
能力要求：{', '.join((target_role or {}).get('required_skills') or [])}
能力差距：{', '.join(gaps or []) or '未知'}
当前最高已完成等级：{current_level}
已有证据：{evidence_summary or '无'}
可用能力ID：{cap_text}

下一任务等级不能跳过，应是 {current_level} 的下一级（L0→L1→…→L5）。
输出：
{{"tasks":[{{"task_name":"","task_level":"L1","description":"","requirements":[""],"estimated_hours":4,"ai_allowed":true,"review_required":true,"capability_ids":["debug"]}}]}}
"""
        print("[newcomer][AI] 推荐培养任务", member.get("name"))
        resp = client.chat.completions.create(
            model=_get_env("DEEPSEEK_MODEL_EXTRACT", "deepseek-ai/DeepSeek-V3"),
            messages=[
                {"role": "system", "content": "你是新人培养教练，只输出 JSON。"},
                {"role": "user", "content": prompt},
            ],
            response_format={"type": "json_object"},
            temperature=0.3,
            max_tokens=1800,
        )
        raw = json.loads(resp.choices[0].message.content or "{}")
        tasks = raw.get("tasks") or fallback
        out = []
        for t in tasks[:3]:
            out.append({
                "task_name": t.get("task_name") or "培养任务",
                "task_level": t.get("task_level") or fallback[0]["task_level"],
                "description": t.get("description") or "",
                "requirements": t.get("requirements") or [],
                "estimated_hours": float(t.get("estimated_hours") or 4),
                "ai_allowed": bool(t.get("ai_allowed", True)),
                "review_required": bool(t.get("review_required", True)),
                "capability_ids": t.get("capability_ids") or ["project_structure"],
            })
        return out or fallback
    except Exception as e:
        _log_llm_failure("newcomer_recommend", e)
        return fallback
