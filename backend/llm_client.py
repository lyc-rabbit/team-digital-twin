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
import traceback
from openai import OpenAI

# ========== 配置(实时读取,支持运行时热更新) ==========

_client = None
_cached_key = None

# 模块级标志:记录最近一次 LLM 调用是否走了降级 fallback
# (is_mock_mode 只能判断 Key 是否配置,无法反映"调用失败降级")
_last_call_degraded = False


def _get_env(key, default=""):
    """从 os.environ 读取,兼容 .env 文件"""
    return os.getenv(key, default)


def get_client():
    global _client, _cached_key
    current_key = _get_env("SILICONFLOW_API_KEY", "")
    base_url = _get_env("SILICONFLOW_BASE_URL", "https://api.siliconflow.cn/v1")
    # Key 变更时重建客户端
    if _client is None or _cached_key != current_key:
        if current_key:
            _client = OpenAI(api_key=current_key, base_url=base_url)
            _cached_key = current_key
        else:
            _client = None
    return _client


def is_mock_mode():
    """实时判断:API Key 是否为空"""
    return not bool(_get_env("SILICONFLOW_API_KEY", ""))


def last_call_degraded():
    """返回最近一次 LLM 调用是否走了降级 fallback。
    与 is_mock_mode() 区别:这个能反映"调用失败降级"的情况。"""
    return _last_call_degraded


def _log_llm_failure(stage, err, response=None):
    """统一打印 LLM 调用失败的详细日志(便于排查降级原因)

    stage: 调用阶段标识(如 "extract" / "chat" / "simulate")
    err:   捕获到的异常对象
    response: 可选,API 返回的 response 对象(用于打印 choices 等字段)
    """
    print(f"[LLM][{stage}] 调用失败,降级到 mock")
    print(f"  异常类型: {type(err).__name__}")
    print(f"  repr(e): {repr(err)}")
    print(f"  str(e):  {err}")
    if response is not None:
        try:
            print(f"  response.choices: {response.choices}")
            if getattr(response, "choices", None):
                print(f"  response.choices[0]: {response.choices[0]}")
                msg = response.choices[0].message
                print(f"  response.choices[0].message: {msg}")
                print(f"  response.choices[0].message.content: {getattr(msg, 'content', None)}")
            print(f"  response.model: {getattr(response, 'model', None)}")
            print(f"  response.usage: {getattr(response, 'usage', None)}")
        except Exception as inspect_err:
            print(f"  (打印 response 字段时出错: {inspect_err!r})")
    print(f"  完整 traceback:")
    traceback.print_exc()


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
    global _last_call_degraded
    if is_mock_mode():
        _last_call_degraded = True  # 配置即降级
        return _mock_extract(raw_text, members_info)
    _last_call_degraded = False  # 先假设本次不降级

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
            model=_get_env("DEEPSEEK_MODEL_EXTRACT", "deepseek-ai/DeepSeek-V3"),
            messages=[
                {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            response_format={"type": "json_object"},
            temperature=0.0,
            max_tokens=2048,
        )
        content = response.choices[0].message.content
        if not content:
            raise ValueError("LLM 返回空 content(可能被限流/内容过滤)")
        result = json.loads(content)
        # 规范化字段
        return _normalize_extraction(result, members_info)
    except Exception as e:
        _last_call_degraded = True  # 调用失败降级
        _log_llm_failure("extract", e, response=None)
        return _mock_extract(raw_text, members_info)


def simulate_decision(members_detail, relationship_grid, recent_events, scenario):
    """
    模拟推演：给定假设场景，推演 3 人反应

    members_detail: [{"id","name","role","persona","decision_style","weaknesses"}, ...]
    relationship_grid: {"user_a→user_b": {"trust": -8, "sentiment": -6, "tag": "..."}, ...}
    recent_events: [{"event_time","raw_summary","parsed_task"}, ...]
    scenario: 用户输入的假设场景文本
    """
    global _last_call_degraded
    if is_mock_mode():
        _last_call_degraded = True
        return _mock_simulate(members_detail, relationship_grid, recent_events, scenario)
    _last_call_degraded = False

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
            model=_get_env("DEEPSEEK_MODEL_SIMULATE", "deepseek-ai/DeepSeek-R1"),
            messages=[
                {"role": "system", "content": SIMULATION_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.7,
            max_tokens=4096,
        )
        content = response.choices[0].message.content
        if not content:
            raise ValueError("LLM 返回空 content(可能被限流/内容过滤)")
        return content
    except Exception as e:
        _last_call_degraded = True
        _log_llm_failure("simulate", e, response=None)
        return _mock_simulate(members_detail, relationship_grid, recent_events, scenario)


def chat_query(members_detail, relationship_grid, recent_events, question):
    """
    问答模式：基于历史事件回答用户关于团队的问题
    """
    global _last_call_degraded
    if is_mock_mode():
        _last_call_degraded = True
        return _mock_chat(members_detail, relationship_grid, recent_events, question)
    _last_call_degraded = False

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
            model=_get_env("DEEPSEEK_MODEL_CHAT", "deepseek-ai/DeepSeek-V3"),
            messages=[
                {"role": "system", "content": QA_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.5,
            max_tokens=2048,
        )
        content = response.choices[0].message.content
        if not content:
            raise ValueError("LLM 返回空 content(可能被限流/内容过滤)")
        return content
    except Exception as e:
        _last_call_degraded = True
        _log_llm_failure("chat", e, response=None)
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


# ========== AI Native 角色匹配 ==========

AI_NATIVE_SYSTEM_PROMPT = """你是 AI Native 组织能力分析专家。你的任务是根据团队成员画像与历史事件，评估每位成员对各 AI Native 角色的匹配度，并给出竞争排序依据。

综合评分权重（必须遵守）：
- 技能匹配 40%
- 项目经验 30%
- 历史职责 20%
- 学习潜力 10%

严格输出 JSON（不要输出其他内容）：
{
  "roles": [
    {
      "role_id": "product_manager",
      "candidates": [
        {
          "employee_id": "成员ID",
          "score": 0到100的数字,
          "confidence": 0到1的浮点数,
          "reason": "一句话匹配理由",
          "strengths": ["优势1", "优势2"],
          "gaps": ["不足1"],
          "summary": "对该角色的匹配摘要"
        }
      ]
    }
  ]
}

要求：
- 每个角色至少给出全体成员的评分，按 score 降序
- score 要有区分度，避免全部相同
- employee_id 必须使用输入中的成员 ID
- role_id 必须使用输入中的角色 ID
- 用中文写 reason / strengths / gaps / summary"""


def analyze_ai_native_roles(members, roles, recent_events=None, daily_evidence=None):
    """
    分析团队成员与 AI Native 角色的匹配与竞争。

    daily_evidence: { member_id: {projects, skills, days, impact, snippets} }
    返回: {"roles": [{"role_id", "candidates": [...]}]}
    """
    global _last_call_degraded
    recent_events = recent_events or []
    daily_evidence = daily_evidence or {}

    if is_mock_mode():
        _last_call_degraded = True
        return _mock_analyze_ai_native_roles(members, roles, recent_events, daily_evidence)
    _last_call_degraded = False

    members_text = "\n".join(
        f"- ID:{m['id']} | 姓名:{m.get('name') or ''} | 职位:{m.get('role') or ''} | "
        f"人设:{m.get('persona') or ''} | 决策风格:{m.get('decision_style') or ''} | "
        f"弱点:{m.get('weaknesses') or ''}"
        for m in members
    )
    roles_text = "\n".join(
        f"- ID:{r['id']} | 名称:{r['role_name']} | 描述:{r.get('description') or ''} | "
        f"职责:{', '.join(r.get('responsibilities') or [])} | "
        f"能力:{', '.join(r.get('required_skills') or [])} | "
        f"评估范围:{(r.get('evaluation_scope_type') or 'TEAM')}"
        for r in roles
    )
    events_text = "\n".join(
        f"- [{e.get('event_time','')}] {e.get('raw_summary','')}"
        for e in (recent_events or [])[-15:]
    ) or "（暂无历史事件）"

    evidence_lines = []
    for m in members:
        ev = daily_evidence.get(m["id"]) or {}
        if not ev:
            continue
        projects = ", ".join(f"{k}({v}天)" for k, v in list((ev.get("projects") or {}).items())[:5]) or "无"
        skills = ", ".join((ev.get("skills") or {}).keys()) or "无"
        evidence_lines.append(
            f"- {m.get('name') or m['id']}：近30天日报 {ev.get('days',0)} 条；"
            f"项目={projects}；技能={skills}；影响分={ev.get('impact',0)}"
        )
    evidence_text = "\n".join(evidence_lines) or "（暂无日报行为数据）"

    user_prompt = f"""请对以下团队进行 AI Native 角色匹配与竞争分析。
评分时请综合：技能匹配、项目经验、历史职责、学习潜力，并优先参考日报行为证据。

## 团队成员
{members_text}

## AI Native 角色
{roles_text}

## 近期事件
{events_text}

## 日报行为证据（近30天）
{evidence_text}

请输出 JSON。"""

    try:
        client = get_client()
        response = client.chat.completions.create(
            model=_get_env("DEEPSEEK_MODEL_EXTRACT", "deepseek-ai/DeepSeek-V3"),
            messages=[
                {"role": "system", "content": AI_NATIVE_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            response_format={"type": "json_object"},
            temperature=0.2,
            max_tokens=8192,
        )
        content = response.choices[0].message.content
        if not content:
            raise ValueError("LLM 返回空 content")
        result = json.loads(content)
        if not isinstance(result.get("roles"), list):
            raise ValueError("LLM 返回缺少 roles 数组")
        return result
    except Exception as e:
        _last_call_degraded = True
        _log_llm_failure("ai_native", e, response=None)
        return _mock_analyze_ai_native_roles(members, roles, recent_events, daily_evidence)


def _mock_analyze_ai_native_roles(members, roles, recent_events=None, daily_evidence=None):
    """规则引擎：按职位关键词 + 人设关键词 + 日报证据估算角色匹配度"""
    recent_events = recent_events or []
    daily_evidence = daily_evidence or {}
    event_blob = " ".join(e.get("raw_summary", "") for e in recent_events)

    # 角色关键词启发式
    role_keywords = {
        "leader": ["负责", "领导", "负责人", "管理", "决策", "统筹", "总监", "经理"],
        "product_manager": ["产品", "需求", "业务建模", "PRD", "验收", "Gherkin", "规则"],
        "project_manager": ["项目", "排期", "交付", "进度", "协调", "风险", "敏捷", "PM"],
        "architect": ["架构", "技术", "系统设计", "选型", "治理", "架构师", "技术负责人"],
        "developer": ["开发", "工程", "编码", "实现", "后端", "前端", "程序员", "研发"],
        "tester": ["测试", "质量", "QA", "用例", "回归", "缺陷", "自动化"],
        "ui_designer": ["设计", "UI", "UX", "交互", "视觉", "体验", "原型"],
        "business_owner": ["业务", "运营", "增长", "价值", "客户", "商业"],
        "context_owner": ["知识", "文档", "AI", "Context", "提示词", "Prompt", "沉淀"],
    }

    result_roles = []
    for role in roles:
        rid = role["id"]
        keywords = role_keywords.get(rid, [])
        # 把角色名称/职责也纳入匹配
        keywords = list(dict.fromkeys(
            keywords
            + [role.get("role_name", "")]
            + (role.get("required_skills") or [])
            + (role.get("responsibilities") or [])
        ))

        candidates = []
        for m in members:
            profile = " ".join([
                m.get("name") or "",
                m.get("role") or "",
                m.get("persona") or "",
                m.get("decision_style") or "",
                m.get("weaknesses") or "",
            ])
            hit = sum(1 for kw in keywords if kw and str(kw) in profile)
            name = m.get("name") or ""
            event_hit = sum(1 for kw in keywords if kw and str(kw) in event_blob and name and name in event_blob)

            # 日报证据加分
            ev = daily_evidence.get(m["id"]) or {}
            report_blob = " ".join(list((ev.get("skills") or {}).keys()) + list((ev.get("projects") or {}).keys()) + (ev.get("snippets") or []))
            report_hit = sum(1 for kw in keywords if kw and str(kw) in report_blob)
            report_boost = min(18, report_hit * 4 + min(8, int(ev.get("days") or 0)))

            # 权重近似：技能40 + 经验30 + 职责20 + 潜力10，再叠加日报行为证据
            skill = min(40, hit * 8 + min(10, report_hit * 3))
            role_title = m.get("role") or ""
            experience = min(30, 12 + event_hit * 6 + (8 if any(k in role_title for k in keywords[:3] if k) else 0) + min(10, report_boost // 2))
            duty = min(20, hit * 4 + min(6, report_hit * 2))
            potential = 10 if ("学习" in profile or "成长" in profile or "AI" in profile or "AI" in report_blob) else 6
            score = skill + experience + duty + potential
            # 轻微扰动，避免同分
            score = max(20, min(96, score + (hash(m["id"] + rid) % 7) - 3))

            strengths = []
            gaps = []
            for kw in keywords[:6]:
                if not kw:
                    continue
                kw_s = str(kw)
                if kw_s in profile or kw_s in report_blob:
                    strengths.append(f"具备「{kw_s}」相关背景")
                else:
                    gaps.append(f"「{kw_s}」待加强")
            if ev.get("days"):
                strengths.append(f"近30天有 {ev['days']} 条日报行为证据")
            strengths = strengths[:3] or ["具备基础团队协作能力"]
            gaps = gaps[:3] or ["角色专精度有限"]

            candidates.append({
                "employee_id": m["id"],
                "score": score,
                "confidence": 0.62 if not ev else 0.72,
                "reason": f"基于职位/人设/日报证据与「{role['role_name']}」匹配估算",
                "strengths": strengths,
                "gaps": gaps,
                "summary": f"{m.get('name') or m['id']} 对「{role['role_name']}」匹配度约 {score}%",
            })

        candidates.sort(key=lambda x: x["score"], reverse=True)
        result_roles.append({"role_id": rid, "candidates": candidates})

    return {"roles": result_roles}


# ========== 日报标签分析 ==========

DAILY_REPORT_SYSTEM_PROMPT = """你是团队日报分析专家。根据一条日报内容，提取结构化标签。

严格输出 JSON：
{
  "skills": ["技能标签"],
  "projects": ["项目/产品名称"],
  "activity_type": "开发|设计|测试|会议|调研|文档|运维|其他",
  "difficulty": 1到5的整数,
  "impact_score": 0到10的数字,
  "summary": "一句话摘要"
}

要求：
- skills / projects 各不超过 5 个
- 从文本中抽取，不要臆造不存在的项目名
- 用中文"""


def analyze_daily_report(content, member_name=None, report_date=None):
    """分析单条日报，提取 skills/projects/activity 等标签"""
    global _last_call_degraded
    if is_mock_mode():
        _last_call_degraded = True
        return _mock_analyze_daily_report(content)
    _last_call_degraded = False

    user_prompt = f"""成员：{member_name or '未知'}
日期：{report_date or '未知'}
日报内容：
{content}

请输出 JSON。"""
    try:
        client = get_client()
        response = client.chat.completions.create(
            model=_get_env("DEEPSEEK_MODEL_EXTRACT", "deepseek-ai/DeepSeek-V3"),
            messages=[
                {"role": "system", "content": DAILY_REPORT_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            response_format={"type": "json_object"},
            temperature=0.0,
            max_tokens=1024,
        )
        raw = response.choices[0].message.content
        if not raw:
            raise ValueError("LLM 返回空 content")
        data = json.loads(raw)
        return {
            "skills": data.get("skills") or [],
            "projects": data.get("projects") or [],
            "activity_type": data.get("activity_type") or "其他",
            "difficulty": max(1, min(5, int(data.get("difficulty", 3)))),
            "impact_score": max(0, min(10, float(data.get("impact_score", 5)))),
            "summary": data.get("summary") or content[:60],
        }
    except Exception as e:
        _last_call_degraded = True
        _log_llm_failure("daily_report", e, response=None)
        return _mock_analyze_daily_report(content)


def _mock_analyze_daily_report(content):
    text = content or ""
    skills = []
    projects = []
    activity = "其他"

    skill_map = [
        (["架构", "设计", "选型"], "架构设计"),
        (["开发", "编码", "实现", "接口", "前端", "后端"], "工程开发"),
        (["测试", "用例", "回归", "缺陷"], "测试验证"),
        (["AI", "Agent", "LLM", "Prompt", "模型"], "AI工程"),
        (["需求", "产品", "验收", "PRD"], "产品需求"),
        (["文档", "知识", "沉淀"], "知识沉淀"),
        (["联调", "排期", "会议"], "协作沟通"),
    ]
    for keys, label in skill_map:
        if any(k in text for k in keys):
            skills.append(label)

    # 简单项目抽取：含「AI/客服/视频」等常见词
    project_hints = ["AI客服", "AI视频", "基础设施", "数字孪生", "中台", "官网", "管理后台"]
    for p in project_hints:
        if p in text:
            projects.append(p)
    if not projects:
        m = re.search(r"([\u4e00-\u9fa5A-Za-z0-9]{2,12})(项目|系统|平台|模块|二期)", text)
        if m:
            projects.append(m.group(0))

    if any(k in text for k in ["测试", "用例", "回归"]):
        activity = "测试"
    elif any(k in text for k in ["设计", "原型", "UI"]):
        activity = "设计"
    elif any(k in text for k in ["会议", "评审", "讨论"]):
        activity = "会议"
    elif any(k in text for k in ["文档", "wiki", "说明"]):
        activity = "文档"
    elif any(k in text for k in ["开发", "实现", "修复", "联调", "编码"]):
        activity = "开发"

    difficulty = 4 if any(k in text for k in ["架构", "重构", "难点", "复杂"]) else 3
    impact = 7 if projects else 5
    return {
        "skills": skills[:5] or ["通用协作"],
        "projects": projects[:5] or ["未分类"],
        "activity_type": activity,
        "difficulty": difficulty,
        "impact_score": impact,
        "summary": text[:60],
    }
