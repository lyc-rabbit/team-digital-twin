"""
LLM 客户端 —— 硅基流动 DeepSeek API 集成

设计要点：
- 模型分层：事件解析用 DeepSeek-V3（快+便宜），模拟推演用 DeepSeek-R1（深度推理）
- JSON Mode：解析任务强制 response_format=json_object + temperature=0
- 降级模式：无 API Key 时自动切换到规则引擎 mock，保证系统可演示
- 统一 OpenAI SDK 兼容接口
"""

import os
import json
import re
from openai import OpenAI

# ========== 配置 ==========

SILICONFLOW_API_KEY = os.getenv("SILICONFLOW_API_KEY", "")
SILICONFLOW_BASE_URL = os.getenv("SILICONFLOW_BASE_URL", "https://api.siliconflow.cn/v1")

MODEL_EXTRACT = os.getenv("DEEPSEEK_MODEL_EXTRACT", "deepseek-ai/DeepSeek-V3")
MODEL_SIMULATE = os.getenv("DEEPSEEK_MODEL_SIMULATE", "deepseek-ai/DeepSeek-R1")
MODEL_CHAT = os.getenv("DEEPSEEK_MODEL_CHAT", "deepseek-ai/DeepSeek-V3")

USE_MOCK = not bool(SILICONFLOW_API_KEY)

_client = None


def get_client():
    global _client
    if _client is None and not USE_MOCK:
        _client = OpenAI(api_key=SILICONFLOW_API_KEY, base_url=SILICONFLOW_BASE_URL)
    return _client


def is_mock_mode():
    return USE_MOCK


# ========== Prompt 模板 ==========

EXTRACTION_SYSTEM_PROMPT = """你是一个专业的团队关系与事务分析专家。你的任务是分析输入的团队事件描述，提取其中的事务进展、人员情绪变化以及两两之间的关系变化。

你需要严格输出以下 JSON 格式（不要输出任何其他内容）：

{
  "task_summary": "提取出来的事务性进展或结果",
  "emotions": [
    {"member_id": "成员ID", "emotion": "情绪描述词", "intensity": 1到10的整数}
  ],
  "relationship_deltas": [
    {
      "from_member_id": "主体成员ID",
      "to_member_id": "客体成员ID",
      "trust_delta": -20到20之间的整数,
      "sentiment_delta": -20到20之间的整数,
      "tag": "简短的关系描述词"
    }
  ],
  "confidence": 0到1之间的浮点数,
  "scene": "事件场景简述（如：周会决策、非正式交流、排期争论）"
}

注意事项：
- trust_delta 表示信任度的长期变化，sentiment_delta 表示短期情绪波动
- 只提取事件中明确涉及到的成员之间的关系变化，未涉及的成员不要臆造
- 如果事件描述模糊或信息不足，confidence 应相应降低
- intensity 表示情绪强度，1为轻微，10为极端强烈"""

SIMULATION_SYSTEM_PROMPT = """你是一个精密的团队行为模拟器。你将收到团队3位成员的人设、当前的关系网格状态、近期重要事件摘要，以及一个待推演的假设性新事件。

你的任务是以极其贴近现实职场人性逻辑的方式，模拟每位成员的心理活动、公开表态和最终决定。

输出格式要求（使用 Markdown）：

### 张三（产品负责人）
**心理活动**：（内心真实想法，不对外说出口的部分）
**公开表态**：（在团队面前实际会说的话）
**最终决定**：（实际会做出的行动或立场）

### 李四（技术负责人）
**心理活动**：...
**公开表态**：...
**最终决定**：...

### 王五（运营/增长）
**心理活动**：...
**公开表态**：...
**最终决定**：...

### 团队整体风险预测
（综合三人反应，预测可能出现的冲突、协作风险及建议）

要求：
- 心理活动和公开表态要有明显反差（职场常见表里不一）
- 结合人设中的弱点/敏感点来设计反应
- 结合当前关系状态（如信任度低时更容易产生负面解读）
- 最终决定要具体、可执行，不要泛泛而谈"""

QA_SYSTEM_PROMPT = """你是一个团队数字孪生系统的智能助手，代号"团队知心者"。你拥有这个团队的全部历史记忆——包括所有事件记录、关系变化和情绪状态。

你的职责：
1. 回答关于团队历史、关系变化、事件细节的问题
2. 分析潜在的协作风险和人际矛盾
3. 给出基于数据的团队管理建议

回答要求：
- 基于提供的历史事件和关系数据作答，不要臆造没有发生过的事
- 回答要具体、有理有据，引用具体事件作为依据
- 使用自然流畅的中文，像一位了解团队内部的顾问在说话
- 如果信息不足以回答，坦诚说明"""


# ========== 核心 API ==========

def extract_event(raw_text, members_info):
    """
    事件结构化解析：文本 → {task, emotions, relations, confidence, scene}

    members_info: [{"id": "user_a", "name": "张三", "role": "产品负责人"}, ...]
    """
    if USE_MOCK:
        return _mock_extract(raw_text, members_info)

    members_desc = "\n".join(
        f"- ID: {m['id']}, 姓名: {m['name']}, 职位: {m['role']}" for m in members_info
    )

    user_prompt = f"""团队当前包含以下成员：
{members_desc}

请分析以下团队事件描述，提取结构化 JSON 数据：

事件描述：{raw_text}

请输出 JSON。"""

    try:
        client = get_client()
        response = client.chat.completions.create(
            model=MODEL_EXTRACT,
            messages=[
                {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            response_format={"type": "json_object"},
            temperature=0.0,
            max_tokens=2048,
        )
        content = response.choices[0].message.content
        result = json.loads(content)
        # 规范化字段
        return _normalize_extraction(result, members_info)
    except Exception as e:
        print(f"[LLM] 解析失败，降级到 mock: {e}")
        return _mock_extract(raw_text, members_info)


def simulate_decision(members_detail, relationship_grid, recent_events, scenario):
    """
    模拟推演：给定假设场景，推演 3 人反应

    members_detail: [{"id","name","role","persona","decision_style","weaknesses"}, ...]
    relationship_grid: {"user_a→user_b": {"trust": -8, "sentiment": -6, "tag": "..."}, ...}
    recent_events: [{"event_time","raw_summary","parsed_task"}, ...]
    scenario: 用户输入的假设场景文本
    """
    if USE_MOCK:
        return _mock_simulate(members_detail, relationship_grid, recent_events, scenario)

    # 构建上下文
    members_text = "\n".join(
        f"- {m['name']}（{m['role']}）：{m['persona']}\n  决策风格：{m.get('decision_style','')}\n  弱点/敏感点：{m.get('weaknesses','')}"
        for m in members_detail
    )

    grid_lines = []
    for key, val in relationship_grid.items():
        grid_lines.append(
            f"  {key}: 信任度={val['trust']:+d}, 情绪={val['sentiment']:+d} ({val.get('tag','')})"
        )
    grid_text = "\n".join(grid_lines) if grid_lines else "  （暂无历史关系数据）"

    events_text = "\n".join(
        f"- [{e['event_time']}] {e['raw_summary']}\n  事务影响: {e.get('parsed_task','无')}"
        for e in recent_events[-8:]  # 最近8条事件
    ) or "（暂无历史事件）"

    user_prompt = f"""【团队现状】

1. 人员设定：
{members_text}

2. 当前关系网格（基于历史事件重放计算）：
{grid_text}

3. 近期重要事件：
{events_text}

【待推演场景】
{scenario}

请按照指定格式，分别模拟三位成员的心理活动、公开表态和最终决定，并给出团队整体风险预测。"""

    try:
        client = get_client()
        response = client.chat.completions.create(
            model=MODEL_SIMULATE,
            messages=[
                {"role": "system", "content": SIMULATION_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.7,
            max_tokens=4096,
        )
        return response.choices[0].message.content
    except Exception as e:
        print(f"[LLM] 模拟失败，降级到 mock: {e}")
        return _mock_simulate(members_detail, relationship_grid, recent_events, scenario)


def chat_query(members_detail, relationship_grid, recent_events, question):
    """
    问答模式：基于历史事件回答用户关于团队的问题
    """
    if USE_MOCK:
        return _mock_chat(members_detail, relationship_grid, recent_events, question)

    events_text = "\n".join(
        f"- [{e['event_time']}] {e['raw_summary']}\n  事务影响: {e.get('parsed_task','无')}"
        for e in recent_events[-15:]
    ) or "（暂无历史事件）"

    grid_lines = []
    for key, val in relationship_grid.items():
        grid_lines.append(
            f"  {key}: 信任度={val['trust']:+d}, 情绪={val['sentiment']:+d}"
        )
    grid_text = "\n".join(grid_lines) if grid_lines else "（暂无）"

    members_text = "\n".join(
        f"- {m['name']}（{m['role']}）：{m['persona']}" for m in members_detail
    )

    user_prompt = f"""以下是团队的完整记忆数据：

【团队成员】
{members_text}

【当前关系网格】
{grid_text}

【历史事件记录】
{events_text}

【用户提问】
{question}

请基于以上数据回答。"""

    try:
        client = get_client()
        response = client.chat.completions.create(
            model=MODEL_CHAT,
            messages=[
                {"role": "system", "content": QA_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.5,
            max_tokens=2048,
        )
        return response.choices[0].message.content
    except Exception as e:
        print(f"[LLM] 问答失败，降级到 mock: {e}")
        return _mock_chat(members_detail, relationship_grid, recent_events, question)


# ========== 降级 Mock 实现 ==========

def _normalize_extraction(result, members_info):
    """规范化 LLM 返回的解析结果"""
    member_ids = {m["id"] for m in members_info}

    emotions = []
    for emo in result.get("emotions", []):
        if emo.get("member_id") in member_ids:
            emotions.append({
                "member_id": emo["member_id"],
                "emotion": emo.get("emotion", "平静"),
                "intensity": max(1, min(10, int(emo.get("intensity", 5)))),
            })

    relations = []
    for rel in result.get("relationship_deltas", []):
        if rel.get("from_member_id") in member_ids and rel.get("to_member_id") in member_ids:
            if rel["from_member_id"] != rel["to_member_id"]:
                relations.append({
                    "from": rel["from_member_id"],
                    "to": rel["to_member_id"],
                    "trust_delta": max(-20, min(20, int(rel.get("trust_delta", 0)))),
                    "sentiment_delta": max(-20, min(20, int(rel.get("sentiment_delta", 0)))),
                    "tag": rel.get("tag", ""),
                })

    return {
        "task": result.get("task_summary", "无法提取事务信息"),
        "emotions": emotions,
        "relations": relations,
        "confidence": max(0.0, min(1.0, float(result.get("confidence", 0.7)))),
        "scene": result.get("scene", "未分类"),
    }


def _mock_extract(raw_text, members_info):
    """无 API Key 时的规则引擎 mock 解析"""
    text = raw_text.lower()
    relations = []
    emotions = []
    task_parts = []

    # 检测冲突关键词
    conflict_words = ["争执", "争吵", "吵", "冲突", "激辩", "争论", "不满", "黑脸", "反对",
                      "抵制", "拍桌", "发火", "怒", "沉默", "冷战", "僵", "不爽", "怼", "训",
                      "批评", "指责", "甩", "翻脸", "积怨"]
    positive_words = ["合作", "默契", "理解", "安慰", "认同", "赞同", "顺利", "开心", "信任",
                      "和谐", "开心", "愉快", "表扬", "赞赏", "达成一致", "支持"]
    compromise_words = ["妥协", "让步", "折中", "采纳", "同意", "接受", "随便", "算了"]

    has_conflict = any(w in raw_text for w in conflict_words)
    has_positive = any(w in raw_text for w in positive_words)
    has_compromise = any(w in raw_text for w in compromise_words)

    # 识别涉及成员
    involved = []
    for m in members_info:
        if m["name"] in raw_text or m["id"] in raw_text:
            involved.append(m)

    if len(involved) < 2:
        involved = members_info[:2]

    # 生成关系增量
    for i, m_from in enumerate(involved):
        for j, m_to in enumerate(involved):
            if i == j:
                continue
            if has_conflict:
                trust_d = -10
                senti_d = -8
                tag = "产生分歧/信任受损"
            elif has_positive:
                trust_d = 6
                senti_d = 8
                tag = "关系拉近/信任加深"
            elif has_compromise:
                trust_d = -3
                senti_d = -4
                tag = "妥协让步/内心记账"
            else:
                trust_d = 0
                senti_d = -1
                tag = "无明显变化"

            relations.append({
                "from": m_from["id"],
                "to": m_to["id"],
                "trust_delta": trust_d,
                "sentiment_delta": senti_d,
                "tag": tag,
            })

    # 生成情绪
    for m in involved:
        if has_conflict:
            emotion = "愤怒/不满"
            intensity = 8
        elif has_positive:
            emotion = "积极/愉悦"
            intensity = 7
        elif has_compromise:
            emotion = "压抑/让步"
            intensity = 6
        else:
            emotion = "平静"
            intensity = 4
        emotions.append({"member_id": m["id"], "emotion": emotion, "intensity": intensity})

    # 提取事务摘要
    if "排期" in raw_text or "上线" in raw_text:
        task_parts.append("涉及项目排期调整")
    if "方案" in raw_text or "技术" in raw_text:
        task_parts.append("涉及技术方案讨论")
    if "功能" in raw_text:
        task_parts.append("涉及功能需求决策")
    if not task_parts:
        task_parts.append("团队事务性沟通")

    return {
        "task": "；".join(task_parts),
        "emotions": emotions,
        "relations": relations,
        "confidence": 0.6,
        "scene": "自动分类" if not has_conflict else "冲突场景",
    }


def _mock_simulate(members_detail, relationship_grid, recent_events, scenario):
    """无 API Key 时的 mock 模拟推演"""
    name_map = {m["id"]: m["name"] for m in members_detail}

    # 找出关系最紧张的一对
    min_trust = 0
    tense_pair = ""
    for key, val in relationship_grid.items():
        if val["trust"] < min_trust:
            min_trust = val["trust"]
            tense_pair = key

    lines = [f"> **[降级模式]** 未配置 API Key，以下为规则引擎生成的模拟结果。配置 `SILICONFLOW_API_KEY` 后将使用 DeepSeek 真实推演。\n"]

    for m in members_detail:
        name = m["name"]
        role = m["role"]
        style = m.get("decision_style", "")
        weakness = m.get("weaknesses", "")

        lines.append(f"### {name}（{role}）")
        lines.append(f"**心理活动**：基于「{style}」的决策风格，面对「{scenario}」这个情况，内心可能会联想到之前的经历。{f'考虑到自身敏感点——{weakness}，' if weakness else ''}内心会有所顾虑但需要权衡利弊。")
        lines.append(f"**公开表态**：会从{role}的立场出发表达意见，措辞会比较职业化，不完全暴露真实想法。")
        lines.append(f"**最终决定**：会根据当前团队氛围和自身角色定位做出务实的选择。\n")

    lines.append("### 团队整体风险预测")
    if tense_pair:
        names = tense_pair.replace("→", " 对 ")
        lines.append(f"当前{names}之间信任度较低（{min_trust:+d}），在压力场景下可能加剧摩擦。建议提前做一对一沟通，降低冲突升级风险。")
    else:
        lines.append("团队整体关系尚可，但仍需关注个体压力承受能力，避免长期积累导致爆发。")

    return "\n".join(lines)


def _mock_chat(members_detail, relationship_grid, recent_events, question):
    """无 API Key 时的 mock 问答"""
    lines = [f"> **[降级模式]** 未配置 API Key。以下为基于本地数据的简单回答。配置 `SILICONFLOW_API_KEY` 后将使用 DeepSeek 深度分析。\n"]

    event_count = len(recent_events)
    lines.append(f"目前系统共记录了 **{event_count} 条历史事件**。")

    if "关系" in question or "信任" in question:
        lines.append("\n当前关系网格状态：")
        for key, val in relationship_grid.items():
            lines.append(f"- {key}：信任度 {val['trust']:+d}，情绪 {val['sentiment']:+d}")

    if "情绪" in question or "状态" in question:
        lines.append("\n近期事件中各成员的情绪变化可以通过日历视图查看。")

    lines.append("\n*（配置 API Key 后可获得更深入的自然语言分析）*")
    return "\n".join(lines)
