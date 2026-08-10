"""
FastAPI 后端 —— 团队数字孪生系统 API

API 路由总览:
  GET  /api/health              - 健康检查 + 模式状态
  GET  /api/members             - 团队成员列表
  GET  /api/members/{id}        - 成员详情

  GET  /api/events              - 事件列表（支持日期/成员过滤）
  GET  /api/events/{id}         - 事件详情
  POST /api/events/log          - 录入新事件（触发 LLM 解析）

  GET  /api/relationships       - 当前关系网格
  GET  /api/relationships/history - 关系变化历史
  GET  /api/states              - 当前成员情绪状态
  GET  /api/dashboard           - 仪表盘聚合数据

  POST /api/chat/query          - 问答模式
  POST /api/chat/simulate       - 模拟推演模式
  GET  /api/chat/history        - 对话历史
"""

import os
import sys
from datetime import datetime
from pathlib import Path
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional

# 确保能找到同目录模块
sys.path.insert(0, os.path.dirname(__file__))

from database import (
    init_db,
    get_all_members,
    get_member,
    get_events,
    get_event_detail,
    save_chat_history,
    get_chat_history,
)
from event_processor import process_event_submission
from memory_engine import (
    compute_relationship_grid,
    compute_member_states,
    compute_team_health,
    get_relationship_history,
)
from llm_client import chat_query, simulate_decision, is_mock_mode

# ========== 初始化 ==========

app = FastAPI(title="团队数字孪生 API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup():
    init_db()


# ========== 请求/响应模型 ==========

class EventLogRequest(BaseModel):
    event_time: str
    involved_members: list[str]
    summary: str
    scene: Optional[str] = None


class ChatRequest(BaseModel):
    message: str


class SimulateRequest(BaseModel):
    scenario: str


# ========== 基础接口 ==========

@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "mock_mode": is_mock_mode(),
        "message": "降级模式（未配置 API Key）" if is_mock_mode() else "DeepSeek 已连接",
    }


@app.get("/api/members")
def members():
    return get_all_members()


@app.get("/api/members/{member_id}")
def member_detail(member_id: str):
    m = get_member(member_id)
    if not m:
        raise HTTPException(status_code=404, detail="成员不存在")
    return m


# ========== 事件接口 ==========

@app.get("/api/events")
def events(
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    member_id: Optional[str] = Query(None),
    include_hypothetical: bool = Query(True),
):
    import json
    events_list = get_events(date_from, date_to, member_id, include_hypothetical)
    for e in events_list:
        e["involved_members"] = json.loads(e["involved_members"])
    return events_list


@app.get("/api/events/{event_id}")
def event_detail(event_id: int):
    detail = get_event_detail(event_id)
    if not detail:
        raise HTTPException(status_code=404, detail="事件不存在")
    return detail


@app.post("/api/events/log")
def log_event(req: EventLogRequest):
    """
    录入新事件：保存原文 → LLM 解析 → 写入关系/情绪增量 → 返回解析结果
    """
    if not req.involved_members:
        raise HTTPException(status_code=400, detail="请至少选择一名涉及成员")
    if not req.summary.strip():
        raise HTTPException(status_code=400, detail="事件摘要不能为空")

    result = process_event_submission(
        event_time=req.event_time,
        involved_members=req.involved_members,
        raw_summary=req.summary,
        scene=req.scene,
    )
    return {"status": "success", **result}


# ========== 关系与状态接口 ==========

@app.get("/api/relationships")
def relationships(
    at_time: Optional[str] = Query(None, description="重放到指定时刻（时间穿梭）"),
    include_hypothetical: bool = Query(True),
):
    grid = compute_relationship_grid(at_time=at_time, include_hypothetical=include_hypothetical)
    members = get_all_members()
    return {"grid": grid, "members": members}


@app.get("/api/relationships/history")
def relationship_history(
    member_pair: Optional[str] = Query(None, description="如 user_a→user_b"),
    days: int = Query(30),
):
    return get_relationship_history(member_pair=member_pair, days=days)


@app.get("/api/states")
def member_states(
    at_time: Optional[str] = Query(None),
    include_hypothetical: bool = Query(True),
):
    states = compute_member_states(at_time=at_time, include_hypothetical=include_hypothetical)
    members = get_all_members()
    # 附加成员信息
    result = []
    for m in members:
        s = states.get(m["id"], {})
        result.append({
            **m,
            "current_emotion": s.get("emotion", "平静"),
            "intensity": s.get("intensity", 3),
            "last_event_time": s.get("last_event_time"),
        })
    return result


@app.get("/api/dashboard")
def dashboard(at_time: Optional[str] = Query(None)):
    """仪表盘聚合数据：团队健康度 + 关系网格 + 成员状态 + 近期事件"""
    health = compute_team_health(at_time)
    grid = compute_relationship_grid(at_time)
    states = compute_member_states(at_time)
    members = get_all_members()
    events_list = get_events()[-10:]  # 最近10条

    import json
    for e in events_list:
        e["involved_members"] = json.loads(e["involved_members"])

    return {
        "health": health,
        "grid": grid,
        "members": members,
        "states": states,
        "recent_events": list(reversed(events_list)),
    }


# ========== 对话接口 ==========

@app.post("/api/chat/query")
def chat_query_api(req: ChatRequest):
    """问答模式：基于历史事件回答关于团队的问题"""
    if not req.message.strip():
        raise HTTPException(status_code=400, detail="问题不能为空")

    members = get_all_members()
    members_detail = [
        {
            "id": m["id"],
            "name": m["name"],
            "role": m["role"],
            "persona": m["persona"],
            "decision_style": m.get("decision_style", ""),
            "weaknesses": m.get("weaknesses", ""),
        }
        for m in members
    ]
    grid = compute_relationship_grid()
    events_list = get_events(include_hypothetical=False)

    response = chat_query(members_detail, grid, events_list, req.message)
    save_chat_history("query", req.message, response)

    return {
        "response": response,
        "mock_mode": is_mock_mode(),
    }


@app.post("/api/chat/simulate")
def chat_simulate_api(req: SimulateRequest):
    """模拟推演模式：输入假设场景，推演 3 人反应"""
    if not req.scenario.strip():
        raise HTTPException(status_code=400, detail="推演场景不能为空")

    members = get_all_members()
    members_detail = [
        {
            "id": m["id"],
            "name": m["name"],
            "role": m["role"],
            "persona": m["persona"],
            "decision_style": m.get("decision_style", ""),
            "weaknesses": m.get("weaknesses", ""),
        }
        for m in members
    ]
    grid = compute_relationship_grid()
    events_list = get_events(include_hypothetical=False)

    response = simulate_decision(members_detail, grid, events_list, req.scenario)
    save_chat_history("simulate", req.scenario, response)

    return {
        "response": response,
        "mock_mode": is_mock_mode(),
    }


@app.get("/api/chat/history")
def chat_history(limit: int = Query(20)):
    return get_chat_history(limit)


# ========== 启动 ==========

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        reload_dirs=[os.path.dirname(__file__)],
    )
