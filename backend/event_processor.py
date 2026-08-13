"""
事件处理器 —— 协调录入流程：保存原始事件 → LLM 解析 → 写入关系/情绪增量

这是"团队记忆构建"的核心链路。
"""

from database import (
    get_all_members,
    get_event_detail,
    get_events,
    insert_event,
    update_event_parsed,
    delete_relationship_logs_by_event,
    delete_emotion_logs_by_event,
    insert_relationship_log,
    insert_emotion_log,
)
from llm_client import extract_event, is_mock_mode, last_call_degraded


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


def reanalyze_event(event_id):
    """
    重新分析指定事件：
    1. 获取事件原始数据
    2. 调用 LLM 重新解析
    3. 删除旧的关系/情绪日志
    4. 写入新的关系/情绪日志
    5. 更新事件的解析字段

    返回: 与 process_event_submission 相同格式
    """
    event = get_event_detail(event_id)
    if not event:
        raise ValueError(f"事件不存在: {event_id}")

    members = get_all_members()
    members_info = [
        {"id": m["id"], "name": m["name"], "role": m["role"]}
        for m in members
    ]

    # Step 1: LLM 重新解析
    parsed = extract_event(event["raw_summary"], members_info)
    # last_call_degraded() 反映本次调用是否走了降级(配置降级或调用失败降级)
    degraded = last_call_degraded()

    # Step 2: 更新事件字段
    update_event_parsed(
        event_id=event_id,
        parsed_task=parsed["task"],
        scene=parsed.get("scene", event.get("scene", "未分类")),
        confidence=parsed["confidence"],
    )

    # Step 3: 删除旧日志
    delete_relationship_logs_by_event(event_id)
    delete_emotion_logs_by_event(event_id)

    # Step 4: 写入新关系增量
    for rel in parsed["relations"]:
        insert_relationship_log(
            event_id=event_id,
            from_id=rel["from"],
            to_id=rel["to"],
            trust_delta=rel["trust_delta"],
            sentiment_delta=rel["sentiment_delta"],
            tag=rel["tag"],
        )

    # Step 5: 写入新情绪快照
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
        "degraded": degraded,  # 真实降级标志(含调用失败降级)
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


def reanalyze_all_events():
    """
    批量重新分析所有事件：
    遍历数据库中全部事件，逐一调用 reanalyze_event 重跑 LLM 解析。
    用于当成员人设变更、或想让 LLM 以新视角重新解读历史时使用。

    返回: { "total": int, "success": int, "failed": int, "degraded": int, "errors": [...] }
    degraded: 走了降级 fallback 的事件数(配置降级或调用失败降级)
    """
    events_list = get_events()
    total = len(events_list)
    success = 0
    failed = 0
    degraded_count = 0
    errors = []

    for e in events_list:
        try:
            result = reanalyze_event(e["id"])
            success += 1
            # reanalyze_event 返回 degraded 字段反映本次 LLM 调用是否降级
            if result.get("degraded"):
                degraded_count += 1
        except Exception as ex:
            failed += 1
            errors.append({"event_id": e["id"], "error": str(ex)})

    return {
        "total": total,
        "success": success,
        "failed": failed,
        "degraded": degraded_count,
        "errors": errors,
    }
