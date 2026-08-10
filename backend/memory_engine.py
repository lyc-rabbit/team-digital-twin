"""
记忆引擎 —— 关系状态与情绪状态的重放计算

核心设计：
- 事件溯源：当前状态 = 所有历史事件增量的加权求和
- 时间衰减：信任衰减慢（半衰期 90 天），情绪衰减快（半衰期 14 天）
- 时间穿梭：传入 at_time 参数即可重放到任意时刻
"""

import math
from datetime import datetime
from database import get_relationship_logs, get_emotion_logs, get_all_members


# 衰减半衰期（天）
TRUST_HALF_LIFE_DAYS = 90
SENTIMENT_HALF_LIFE_DAYS = 14


def _decay_factor(event_time_str, at_time_str, half_life_days):
    """
    计算时间衰减因子
    距离越远，因子越小（贡献越弱）
    """
    try:
        event_time = datetime.fromisoformat(event_time_str.replace("Z", ""))
        at_time = datetime.fromisoformat(at_time_str.replace("Z", ""))
    except (ValueError, AttributeError):
        return 1.0

    days_elapsed = (at_time - event_time).total_seconds() / 86400.0
    if days_elapsed <= 0:
        return 1.0

    # 指数衰减: factor = 0.5 ^ (days / half_life)
    return 0.5 ** (days_elapsed / half_life_days)


def compute_relationship_grid(at_time=None, include_hypothetical=True):
    """
    计算当前（或指定时刻）的 3x3 关系网格

    返回格式:
    {
        "user_a→user_b": {"trust": -8, "sentiment": -6, "tag": "..."},
        ...
    }
    """
    members = get_all_members()
    member_ids = [m["id"] for m in members]

    # 初始化网格
    grid = {}
    for from_id in member_ids:
        for to_id in member_ids:
            if from_id != to_id:
                key = f"{from_id}→{to_id}"
                grid[key] = {"trust": 0, "sentiment": 0, "tag": "初始状态", "last_event_time": None}

    # 获取所有关系增量日志
    logs = get_relationship_logs(date_to=at_time, include_hypothetical=include_hypothetical)

    # 重放计算（带衰减）
    for log in logs:
        key = f"{log['from_member_id']}→{log['to_member_id']}"
        if key not in grid:
            continue

        # 计算衰减因子
        trust_decay = _decay_factor(log["event_time"], at_time or datetime.now().isoformat(), TRUST_HALF_LIFE_DAYS)
        sentiment_decay = _decay_factor(log["event_time"], at_time or datetime.now().isoformat(), SENTIMENT_HALF_LIFE_DAYS)

        grid[key]["trust"] += log["trust_delta"] * trust_decay
        grid[key]["sentiment"] += log["sentiment_delta"] * sentiment_decay
        grid[key]["tag"] = log["tag"]
        grid[key]["last_event_time"] = log["event_time"]

    # 取整并限制范围
    for key in grid:
        grid[key]["trust"] = round(max(-100, min(100, grid[key]["trust"])))
        grid[key]["sentiment"] = round(max(-100, min(100, grid[key]["sentiment"])))

    return grid


def compute_member_states(at_time=None, include_hypothetical=True):
    """
    计算各成员当前的情绪状态

    返回格式:
    {
        "user_a": {"emotion": "压抑/让步", "intensity": 6, "last_event_time": "..."},
        ...
    }
    """
    members = get_all_members()
    member_ids = {m["id"] for m in members}

    states = {mid: {"emotion": "平静", "intensity": 3, "last_event_time": None} for mid in member_ids}

    logs = get_emotion_logs(date_to=at_time, include_hypothetical=include_hypothetical)

    # 取每个成员最近的一条情绪记录
    latest_by_member = {}
    for log in logs:
        mid = log["member_id"]
        if mid not in member_ids:
            continue
        if mid not in latest_by_member or log["event_time"] > latest_by_member[mid]["event_time"]:
            latest_by_member[mid] = log

    for mid, log in latest_by_member.items():
        states[mid] = {
            "emotion": log["emotion"],
            "intensity": log["intensity"],
            "last_event_time": log["event_time"],
        }

    return states


def compute_team_health(at_time=None):
    """
    计算团队整体健康度评分（0-100）

    综合考虑：
    - 平均信任度（权重 50%）
    - 平均情绪值（权重 30%）
    - 关系极端值的惩罚（权重 20%）
    """
    grid = compute_relationship_grid(at_time)
    if not grid:
        return {"score": 75, "level": "良好", "description": "团队关系尚在建立中"}

    trusts = [v["trust"] for v in grid.values()]
    sentiments = [v["sentiment"] for v in grid.values()]

    avg_trust = sum(trusts) / len(trusts)  # -100 ~ 100
    avg_sentiment = sum(sentiments) / len(sentiments)

    # 转换到 0-100 区间
    trust_score = (avg_trust + 100) / 2  # 0~100
    sentiment_score = (avg_sentiment + 100) / 2

    # 极端值惩罚：如果有任何一对关系低于 -30，扣分
    min_trust = min(trusts)
    penalty = max(0, (-min_trust - 30) * 0.5) if min_trust < -30 else 0

    health = trust_score * 0.5 + sentiment_score * 0.3 + 20 - penalty
    health = max(0, min(100, health))

    if health >= 75:
        level = "良好"
        desc = "团队协作顺畅，关系健康"
    elif health >= 50:
        level = "关注"
        desc = "存在一定摩擦，建议关注"
    elif health >= 30:
        level = "预警"
        desc = "关系紧张，需要主动干预"
    else:
        level = "危险"
        desc = "团队关系严重恶化，急需调解"

    return {
        "score": round(health),
        "level": level,
        "description": desc,
        "avg_trust": round(avg_trust),
        "avg_sentiment": round(avg_sentiment),
    }


def get_relationship_history(member_pair=None, days=30):
    """
    获取关系变化历史时间线（用于趋势图）

    member_pair: "user_a→user_b" 或 None（返回所有对）
    """
    logs = get_relationship_logs(include_hypothetical=False)

    # 按时间排序，累积计算
    history = {}
    for log in logs:
        key = f"{log['from_member_id']}→{log['to_member_id']}"
        if member_pair and key != member_pair:
            continue

        if key not in history:
            history[key] = []
        history[key].append({
            "time": log["event_time"],
            "trust": log["trust_delta"],
            "sentiment": log["sentiment_delta"],
            "tag": log["tag"],
        })

    return history
