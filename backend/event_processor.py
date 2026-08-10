"""
事件处理器 —— 协调录入流程：保存原始事件 → LLM 解析 → 写入关系/情绪增量

这是"团队记忆构建"的核心链路。
"""

from database import (
    get_all_members,
    insert_event,
    insert_relationship_log,
    insert_emotion_log,
)
from llm_client import extract_event, is_mock_mode


def process_event_submission(event_time, involved_members, raw_summary, scene=None):
    """
    处理事件录入的完整链路：
    1. 保存原始事件到 team_events
    2. 调用 LLM 解析结构化数据
    3. 写入 relationship_logs 和 member_state_logs
    4. 返回解析结果

    返回: {
        "event_id": int,
        "parsed_analysis": {...},
        "mock_mode": bool
    }
    """
    members = get_all_members()
    members_info = [
        {"id": m["id"], "name": m["name"], "role": m["role"]}
        for m in members
    ]

    # Step 1: LLM 解析
    parsed = extract_event(raw_summary, members_info)

    # Step 2: 保存事件
    event_id = insert_event(
        event_time=event_time,
        involved_members=involved_members,
        raw_summary=raw_summary,
        scene=scene or parsed.get("scene", "未分类"),
        parsed_task=parsed["task"],
        confidence=parsed["confidence"],
    )

    # Step 3: 写入关系增量
    for rel in parsed["relations"]:
        insert_relationship_log(
            event_id=event_id,
            from_id=rel["from"],
            to_id=rel["to"],
            trust_delta=rel["trust_delta"],
            sentiment_delta=rel["sentiment_delta"],
            tag=rel["tag"],
        )

    # Step 4: 写入情绪快照
    for emo in parsed["emotions"]:
        insert_emotion_log(
            event_id=event_id,
            member_id=emo["member_id"],
            emotion=emo["emotion"],
            intensity=emo.get("intensity", 5),
        )

    return {
        "event_id": event_id,
        "mock_mode": is_mock_mode(),
        "parsed_analysis": {
            "task": parsed["task"],
            "scene": parsed.get("scene", "未分类"),
            "emotions": parsed["emotions"],
            "relations": [
                {
                    "from": r["from"],
                    "to": r["to"],
                    "trust_delta": r["trust_delta"],
                    "sentiment_delta": r["sentiment_delta"],
                    "tag": r["tag"],
                }
                for r in parsed["relations"]
            ],
            "confidence": parsed["confidence"],
        },
    }


def build_sample_parsed():
    """占位函数，供 seed 调用时引用（实际 seed 数据直接内联在 database.py 中）"""
    return {}
