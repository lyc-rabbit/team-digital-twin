"""
FastAPI 后端 —— 团队数字孪生系统 API

API 路由总览:
  GET  /api/health              - 健康检查 + 模式状态
  GET  /api/members             - 团队成员列表
  GET  /api/members/{id}        - 成员详情

  GET  /api/events              - 事件列表（支持日期/成员过滤）
  GET  /api/events/{id}         - 事件详情
  POST /api/events/log          - 录入新事件（触发 LLM 解析）
  POST /api/events/{id}/reanalyze - 重新分析单个事件
  POST /api/events/reanalyze-all - 批量重新分析所有事件

  GET  /api/relationships       - 当前关系网格
  GET  /api/relationships/history - 关系变化历史
  GET  /api/states              - 当前成员情绪状态
  GET  /api/dashboard           - 仪表盘聚合数据

  GET  /api/ai-native/roles           - AI Native 角色卡列表
  GET  /api/ai-native/roles/{role_id} - AI Native 角色详情
  POST /api/ai-native/ranking/update  - 触发角色竞争排名更新
  GET  /api/ai-native/ranking/status  - 查询排名任务状态

  POST /api/daily-report/import              - Excel 日报增量同步
  GET  /api/daily-report/import/{task_id}    - 导入任务状态
  GET  /api/daily-report/import              - 导入任务列表
  GET  /api/daily-report                     - 查询日报
  GET  /api/daily-report/{id}/history        - 日报历史版本
  GET  /api/report/statistics/member         - 人员投入统计
  GET  /api/calendar/events                  - 日历事件（含日报）

  POST /api/chat/query          - 问答模式
  POST /api/chat/simulate       - 模拟推演模式
  GET  /api/chat/history        - 对话历史

  GET  /api/v1/graph                     - 组织影响力图谱
  POST /api/v1/graph/rebuild             - 从业务数据重建图谱
  GET  /api/v1/person/{id}/network       - 人员关系查询
  GET  /api/v1/person/{id}/leadership-profile - 晋升画像
  GET  /api/v1/influence/ranking         - 影响力排名
  GET  /api/v1/community                 - 组织圈层 / 结构洞
  GET  /api/v1/risk                      - 组织风险
  POST /api/v1/extract                   - LLM 关系抽取

  GET  /api/promotion/templates                 - 领导风格模板
  GET  /api/promotion/simulations               - 推演任务列表
  POST /api/promotion/simulations               - 创建推演（AI 分析一次）
  GET  /api/promotion/simulations/{id}          - 推演结果
  PUT  /api/promotion/simulations/{id}/weights  - 调整权重并重算（不调 AI）
"""

import os
import sys
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional

# 确保能找到同目录模块
sys.path.insert(0, os.path.dirname(__file__))

# 加载 .env 配置(必须在 import llm_client 之前)
load_dotenv(Path(__file__).parent / ".env")

from database import (
    init_db,
    get_all_members,
    get_member,
    create_member,
    update_member,
    delete_member,
    get_events,
    get_event_detail,
    save_chat_history,
    get_chat_history,
    get_daily_reports,
    get_daily_report_history,
    list_daily_import_tasks,
    get_member_report_statistics,
    get_daily_report_calendar_events,
    get_member_recent_report_summary,
)
from event_processor import process_event_submission, reanalyze_event, reanalyze_all_events
from memory_engine import (
    compute_relationship_grid,
    compute_member_states,
    compute_team_health,
    get_relationship_history,
)
from llm_client import chat_query, simulate_decision, is_mock_mode
from ai_native_engine import (
    list_role_cards,
    get_role_detail,
    start_ranking_update,
    get_ranking_status,
    update_evaluation_scope,
)
from daily_report_service import start_import_task, get_import_task_status
from organization_graph import router as oig_router
from organization_graph.repository.facade import bootstrap_graph
from promotion import router as promo_router
from promotion.repository import get_promo_store
from newcomer import router as newcomer_router, task_router as newcomer_task_router
from team_situation import router as situation_router, start_scheduler
from project_center import router as project_router

# ========== 初始化 ==========

app = FastAPI(title="团队数字孪生 API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(oig_router)
app.include_router(promo_router)
app.include_router(newcomer_router)
app.include_router(newcomer_task_router)
app.include_router(situation_router)
app.include_router(project_router)


@app.on_event("startup")
def startup():
    init_db()
    bootstrap_graph()
    get_promo_store()
    start_scheduler()


# ========== 请求/响应模型 ==========

class EventLogRequest(BaseModel):
    event_time: str
    involved_members: list[str]
    summary: str
    scene: Optional[str] = None


class MemberCreateRequest(BaseModel):
    id: str
    name: str
    role: str
    persona: str
    decision_style: Optional[str] = None
    weaknesses: Optional[str] = None


class MemberUpdateRequest(BaseModel):
    name: Optional[str] = None
    role: Optional[str] = None
    persona: Optional[str] = None
    decision_style: Optional[str] = None
    weaknesses: Optional[str] = None


class ChatRequest(BaseModel):
    message: str


class SimulateRequest(BaseModel):
    scenario: str


class LlmConfigUpdate(BaseModel):
    api_key: Optional[str] = None      # None=不改;空串=清空(降级模式)
    base_url: Optional[str] = None
    model_extract: Optional[str] = None
    model_simulate: Optional[str] = None
    model_chat: Optional[str] = None


class EvaluationScopeRequest(BaseModel):
    type: Optional[str] = "TEAM"
    evaluation_scope_type: Optional[str] = None
    employee_ids: Optional[list[str]] = None
    project: Optional[str] = None
    config: Optional[dict] = None
    minimum_competition_level: Optional[str] = None
    minimum_match_score: Optional[float] = None


# ========== 基础接口 ==========

@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "mock_mode": is_mock_mode(),
        "message": "降级模式（未配置 API Key）" if is_mock_mode() else "DeepSeek 已连接",
    }


def _mask_key(key: str) -> str:
    """API Key 脱敏:保留前3后3,中间用 *** 代替"""
    if not key:
        return ""
    if len(key) <= 8:
        return "***"
    return f"{key[:3]}***{key[-3:]}"


@app.get("/api/config/llm")
def get_llm_config():
    """获取当前 LLM 配置。API Key 脱敏返回。"""
    from dotenv import dotenv_values
    env_path = Path(__file__).parent / ".env"
    cfg = dotenv_values(env_path) if env_path.exists() else {}
    return {
        "api_key_masked": _mask_key(cfg.get("SILICONFLOW_API_KEY", "")),
        "api_key_set": bool(cfg.get("SILICONFLOW_API_KEY", "")),
        "base_url": cfg.get("SILICONFLOW_BASE_URL", "https://api.siliconflow.cn/v1"),
        "model_extract": cfg.get("DEEPSEEK_MODEL_EXTRACT", "deepseek-ai/DeepSeek-V3"),
        "model_simulate": cfg.get("DEEPSEEK_MODEL_SIMULATE", "deepseek-ai/DeepSeek-R1"),
        "model_chat": cfg.get("DEEPSEEK_MODEL_CHAT", "deepseek-ai/DeepSeek-V3"),
        "mock_mode": is_mock_mode(),
    }


@app.put("/api/config/llm")
def update_llm_config(req: LlmConfigUpdate):
    """更新 LLM 配置,写入 .env 文件。修改后需重启后端生效。"""
    from dotenv import set_key
    env_path = Path(__file__).parent / ".env"
    # .env 不存在时 set_key 会自动创建
    changes = []
    if req.api_key is not None:
        set_key(str(env_path), "SILICONFLOW_API_KEY", req.api_key)
        changes.append("api_key")
    if req.base_url is not None and req.base_url.strip():
        set_key(str(env_path), "SILICONFLOW_BASE_URL", req.base_url.strip())
        changes.append("base_url")
    if req.model_extract is not None and req.model_extract.strip():
        set_key(str(env_path), "DEEPSEEK_MODEL_EXTRACT", req.model_extract.strip())
        changes.append("model_extract")
    if req.model_simulate is not None and req.model_simulate.strip():
        set_key(str(env_path), "DEEPSEEK_MODEL_SIMULATE", req.model_simulate.strip())
        changes.append("model_simulate")
    if req.model_chat is not None and req.model_chat.strip():
        set_key(str(env_path), "DEEPSEEK_MODEL_CHAT", req.model_chat.strip())
        changes.append("model_chat")
    return {
        "status": "success",
        "message": f"配置已写入 .env(共 {len(changes)} 项)。需重启后端生效。",
        "changes": changes,
        "restart_required": True,
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


@app.post("/api/members")
def create_member_api(req: MemberCreateRequest):
    """新增团队成员"""
    if not req.id.strip() or not req.name.strip() or not req.role.strip() or not req.persona.strip():
        raise HTTPException(status_code=400, detail="id/name/role/persona 不能为空")
    try:
        m = create_member(
            member_id=req.id.strip(),
            name=req.name.strip(),
            role=req.role.strip(),
            persona=req.persona.strip(),
            decision_style=req.decision_style,
            weaknesses=req.weaknesses,
        )
        return {"status": "success", "member": m}
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))


@app.put("/api/members/{member_id}")
def update_member_api(member_id: str, req: MemberUpdateRequest):
    """更新团队成员信息"""
    try:
        m = update_member(
            member_id=member_id,
            name=req.name,
            role=req.role,
            persona=req.persona,
            decision_style=req.decision_style,
            weaknesses=req.weaknesses,
        )
        return {"status": "success", "member": m}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.delete("/api/members/{member_id}")
def delete_member_api(member_id: str):
    """删除团队成员。历史事件保留(不可变事实),但关联日志级联删除。"""
    try:
        event_count = delete_member(member_id)
        return {
            "status": "success",
            "message": f"成员已删除,关联历史事件 {event_count} 条(已保留为历史事实)",
            "related_events": event_count,
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


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


@app.post("/api/events/{event_id}/reanalyze")
def reanalyze_event_api(event_id: int):
    """重新分析指定事件：使用 LLM 重新解析并更新关系/情绪增量"""
    try:
        result = reanalyze_event(event_id)
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"重新分析失败: {str(e)}")


@app.post("/api/events/reanalyze-all")
def reanalyze_all_events_api():
    """批量重新分析所有事件：使用 LLM 重新解析全部历史事件"""
    try:
        result = reanalyze_all_events()
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"批量重新分析失败: {str(e)}")


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


# ========== AI Native 接口 ==========

@app.get("/api/ai-native/roles")
def ai_native_roles():
    """AI Native 角色卡列表 + 覆盖摘要 + 任务状态"""
    return list_role_cards()


@app.get("/api/ai-native/roles/{role_id}")
def ai_native_role_detail(role_id: str):
    detail = get_role_detail(role_id)
    if not detail:
        raise HTTPException(status_code=404, detail="角色不存在")
    return detail


@app.post("/api/ai-native/ranking/update")
def ai_native_ranking_update():
    """触发角色竞争排名更新（幂等：已有 running 任务则直接返回）"""
    return start_ranking_update()


@app.get("/api/ai-native/ranking/status")
def ai_native_ranking_status():
    """查询排名任务状态（支持页面切换后恢复）"""
    return get_ranking_status()


@app.get("/api/ai-native/analysis/status")
def ai_native_analysis_status():
    """与 ranking/status 相同，满足 Spec 统一查询入口。"""
    st = get_ranking_status()
    return {
        **st,
        "task_type": "role_ranking",
        "current_step": st.get("message"),
        "error_message": st.get("error"),
        "started_at": st.get("start_time"),
        "finished_at": st.get("end_time"),
    }


@app.put("/api/ai-native/roles/{role_id}/evaluation-scope")
def ai_native_evaluation_scope(role_id: str, req: EvaluationScopeRequest):
    """修改评估范围。不自动重算排名。"""
    try:
        result = update_evaluation_scope(role_id, req.model_dump())
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not result:
        raise HTTPException(status_code=404, detail="角色不存在")
    return result


# ========== 日报接口 ==========

@app.post("/api/daily-report/import")
async def daily_report_import(file: UploadFile = File(...)):
    """Excel 日报增量同步：解析 → Diff → NEW/UPDATE/SKIP → AI 分析"""
    if not file.filename:
        raise HTTPException(status_code=400, detail="请上传 Excel 文件")
    lower = file.filename.lower()
    if not (lower.endswith(".xlsx") or lower.endswith(".xlsm")):
        raise HTTPException(status_code=400, detail="仅支持 .xlsx 文件")
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="文件为空")
    return start_import_task(file.filename, data)


@app.get("/api/daily-report/import/{task_id}")
def daily_report_import_status(task_id: int):
    task = get_import_task_status(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="导入任务不存在")
    return task


@app.get("/api/daily-report/import")
def daily_report_import_list(limit: int = Query(20)):
    return list_daily_import_tasks(limit)


@app.get("/api/daily-report")
def daily_report_list(
    date: Optional[str] = Query(None, description="精确日期 YYYY-MM-DD"),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    member: Optional[str] = Query(None, description="成员ID"),
    project: Optional[str] = Query(None),
    skill: Optional[str] = Query(None),
    limit: int = Query(200),
):
    members = get_all_members()
    mmap = {m["id"]: m for m in members}
    df = date or date_from
    dt = date or date_to
    rows = get_daily_reports(
        date_from=df, date_to=dt, member_id=member,
        project=project, skill=skill, limit=limit,
    )
    for r in rows:
        m = mmap.get(r["member_id"])
        r["member_name"] = m["name"] if m else r["member_id"]
    return {"reports": rows, "count": len(rows)}


@app.get("/api/daily-report/{report_id}/history")
def daily_report_history(report_id: int):
    history = get_daily_report_history(report_id)
    return {"report_id": report_id, "history": history}


@app.get("/api/report/statistics/member")
def report_statistics_member(days: int = Query(30)):
    """人员投入统计：member_id -> {project: days}"""
    stats = get_member_report_statistics(days=days)
    members = get_all_members()
    named = {}
    mmap = {m["id"]: m["name"] for m in members}
    for mid, projects in stats.items():
        named[mmap.get(mid, mid)] = projects
    return {"days": days, "by_member_id": stats, "by_member_name": named}


@app.get("/api/calendar/events")
def calendar_events(
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
):
    """日历事件：日报转事件（可与团队事件并存消费）"""
    members = get_all_members()
    mmap = {m["id"]: m["name"] for m in members}
    events = get_daily_report_calendar_events(date_from=date_from, date_to=date_to)
    for e in events:
        e["member_name"] = mmap.get(e["member"], e["member"])
    return events


@app.get("/api/daily-report/ai-evidence")
def daily_report_ai_evidence(days: int = Query(30), member: Optional[str] = Query(None)):
    """AI Native / Smart Chat 消费的日报证据摘要"""
    rows = get_member_recent_report_summary(member_id=member, days=days)
    members = get_all_members()
    mmap = {m["id"]: m["name"] for m in members}
    for r in rows:
        r["member_name"] = mmap.get(r["member_id"], r["member_id"])
    return {"days": days, "items": rows}


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
        port=8765,
        reload=True,
        reload_dirs=[os.path.dirname(__file__)],
    )
