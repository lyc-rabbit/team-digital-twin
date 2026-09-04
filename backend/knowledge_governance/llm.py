"""LLM 只解释 / 建议，禁止直接改图谱。"""

from llm_client import get_client, is_mock_mode, _log_llm_failure, _get_env


def explain_inference(chain, conclusion_text):
    """把推理链说成人话。无 Key 或失败时返回模板。"""
    steps = []
    for step in chain or []:
        steps.append(
            f"{step.get('source_name')} --{step.get('relation')}--> {step.get('target_name')}"
        )
    template = "推理来源:\n" + "\n".join(steps) + f"\n因此:\n{conclusion_text}"
    if is_mock_mode():
        return template
    client = get_client()
    if not client:
        return template
    try:
        model = _get_env("SILICONFLOW_EXTRACT_MODEL", "deepseek-ai/DeepSeek-V3")
        resp = client.chat.completions.create(
            model=model,
            temperature=0,
            messages=[
                {
                    "role": "system",
                    "content": "你解释知识图谱推理。只用已给的边，不要发明新事实。用中文两三句话。",
                },
                {
                    "role": "user",
                    "content": f"已知关系：\n" + "\n".join(steps) + f"\n结论：{conclusion_text}",
                },
            ],
        )
        text = (resp.choices[0].message.content or "").strip()
        return text or template
    except Exception as e:
        _log_llm_failure("kg_explain", e)
        return template


def suggest_parent_type(node_name, description, neighbors, candidates):
    """本体父类建议。失败则返回空。"""
    if is_mock_mode() or not get_client():
        return None
    client = get_client()
    try:
        model = _get_env("SILICONFLOW_EXTRACT_MODEL", "deepseek-ai/DeepSeek-V3")
        resp = client.chat.completions.create(
            model=model,
            temperature=0,
            response_format={"type": "json_object"},
            messages=[
                {
                    "role": "system",
                    "content": (
                        '根据节点名称、描述和邻居，从候选本体类型中选一个父类。'
                        '只输出 JSON：{"parent":"类型名","confidence":0-1,"reason":"一句"}。'
                        "不要建议修改图谱。"
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"名称:{node_name}\n描述:{description or ''}\n"
                        f"邻居:{neighbors}\n候选:{candidates}"
                    ),
                },
            ],
        )
        import json
        return json.loads(resp.choices[0].message.content or "{}")
    except Exception as e:
        _log_llm_failure("kg_parent", e)
        return None
