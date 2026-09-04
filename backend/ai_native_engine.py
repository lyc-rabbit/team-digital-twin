"""
AI Native 角色分析引擎

- 角色匹配 / 竞争排名 / 风险分析
- 后台任务状态机（IDLE → RUNNING → SUCCESS / FAILED）
- MVP 使用进程内状态（与 Spec Redis key 对齐，便于后续替换）
"""

import threading
import time
import uuid
from timeutil import now_stamp
from copy import deepcopy

from database import (
    get_ai_native_roles,
    get_ai_native_role,
    get_ai_role_assignments,
    get_ai_role_competitions,
    get_all_members,
    get_events,
    replace_ai_role_analysis,
    update_ai_native_evaluation_scope,
)
from llm_client import analyze_ai_native_roles, is_mock_mode, last_call_degraded
from daily_report_service import build_ai_native_report_evidence
from newcomer.eligibility import resolve_candidates_for_role, scope_label
from newcomer.repository import list_known_projects

# Spec Redis key 语义: ai_native:ranking:update
RANKING_TASK_KEY = "ai_native:ranking:update"

_lock = threading.Lock()
_task_state = {
    "status": "idle",  # idle | running | success | failed
    "task_id": None,
    "start_time": None,
    "end_time": None,
    "progress": 0,
    "message": "",
    "error": None,
}


def get_ranking_status():
    with _lock:
        return deepcopy(_task_state)


def _set_status(**kwargs):
    with _lock:
        _task_state.update(kwargs)


def _member_map(members):
    return {m["id"]: m for m in members}


def get_coverage_summary(roles=None, assignments=None, competitions=None, members=None):
    roles = roles if roles is not None else get_ai_native_roles()
    assignments = assignments if assignments is not None else get_ai_role_assignments()
    competitions = competitions if competitions is not None else get_ai_role_competitions()
    members = members if members is not None else get_all_members()

    covered = 0
    risk_roles = 0
    for role in roles:
        rid = role["id"]
        owners = [a for a in assignments if a["role_id"] == rid]
        comps = [c for c in competitions if c["role_id"] == rid]
        if owners and owners[0].get("match_score", 0) >= 50:
            covered += 1
        # 有负责人但竞争 Top1 分数接近 → 竞争风险；无备份也算风险
        if owners:
            backup = [c for c in comps if c["employee_id"] != owners[0]["employee_id"]]
            if not backup or (backup and owners[0]["match_score"] - backup[0]["score"] < 8):
                risk_roles += 1
        else:
            risk_roles += 1

    total = len(roles) or 1
    return {
        "role_count": len(roles),
        "member_count": len(members),
        "covered_count": covered,
        "coverage_rate": round(covered / total * 100),
        "competition_risk": risk_roles,
        "high_risk_roles": risk_roles,
        "last_analysis_at": _task_state.get("end_time") if _task_state.get("status") == "success" else None,
        "mock_mode": is_mock_mode(),
    }


def list_role_cards():
    """首页角色卡聚合数据"""
    roles = get_ai_native_roles()
    members = get_all_members()
    mmap = _member_map(members)
    assignments = get_ai_role_assignments()
    competitions = get_ai_role_competitions()

    cards = []
    for role in roles:
        rid = role["id"]
        role_assigns = sorted(
            [a for a in assignments if a["role_id"] == rid],
            key=lambda x: x.get("match_score", 0),
            reverse=True,
        )
        owner = role_assigns[0] if role_assigns else None
        owner_member = mmap.get(owner["employee_id"]) if owner else None

        comps = sorted(
            [c for c in competitions if c["role_id"] == rid],
            key=lambda x: x.get("rank", 999),
        )
        # 竞争 Top2：排除当前负责人
        competitors = []
        for c in comps:
            if owner and c["employee_id"] == owner["employee_id"]:
                continue
            m = mmap.get(c["employee_id"])
            competitors.append({
                "employee_id": c["employee_id"],
                "name": m["name"] if m else c["employee_id"],
                "score": round(c.get("score", 0)),
                "reason": c.get("reason") or "",
                "rank": c.get("rank"),
            })
            if len(competitors) >= 2:
                break

        analysis = (owner or {}).get("analysis_result") or {}
        risk = analysis.get("risk_analysis") or {}
        impact = risk.get("impact") or ("高" if not owner else "低")
        risk_level = {"高": "high", "中": "medium", "低": "low"}.get(impact, "medium")
        cards.append({
            "id": rid,
            "role_id": rid,
            "name": role["role_name"],
            "role_name": role["role_name"],
            "description": role.get("description") or "",
            "responsibility_summary": analysis.get("summary") or role.get("description") or "",
            "summary": analysis.get("summary") or role.get("description") or "",
            "owner": {
                "employee_id": owner["employee_id"],
                "name": owner_member["name"] if owner_member else owner["employee_id"],
                "score": round(owner.get("match_score", 0)),
                "confidence": owner.get("confidence", 0),
            } if owner else None,
            "current_owner": {
                "employee_id": owner["employee_id"],
                "name": owner_member["name"] if owner_member else owner["employee_id"],
                "score": round(owner.get("match_score", 0)),
            } if owner else None,
            "competitors": competitors,
            "responsibilities": role.get("responsibilities") or [],
            "required_skills": _with_communication_skill(role.get("required_skills") or []),
            "evaluation_scope": {
                "type": role.get("evaluation_scope_type") or "TEAM",
                "label": scope_label(role),
                "config": role.get("evaluation_scope_config") or {},
                "minimum_competition_level": role.get("minimum_competition_level") or "L2",
                "minimum_match_score": role.get("minimum_match_score") or 60,
            },
            "risk_level": risk_level,
            "updated_at": role.get("updated_at"),
        })

    summary = get_coverage_summary(roles, assignments, competitions, members)
    return {"roles": cards, "summary": summary, "ranking_status": get_ranking_status()}


def _with_communication_skill(skills):
    items = list(skills or [])
    if "问题定义与结构化沟通" not in items:
        items.append("问题定义与结构化沟通")
    return items


def _role_standards(role_id):
    try:
        from growth.standards import get_role_standards
        return get_role_standards(role_id)
    except Exception:
        return {"dimensions": []}


def _communication_capability():
    try:
        from growth.standards import COMMUNICATION_CAPABILITY
        return COMMUNICATION_CAPABILITY
    except Exception:
        return {}


def _human_ai(role_id):
    try:
        from growth.standards import human_ai_for_role
        return human_ai_for_role(role_id)
    except Exception:
        return []


def get_role_detail(role_id):
    role = get_ai_native_role(role_id)
    if not role:
        return None

    members = get_all_members()
    mmap = _member_map(members)
    assignments = sorted(
        get_ai_role_assignments(role_id),
        key=lambda x: x.get("match_score", 0),
        reverse=True,
    )
    competitions = sorted(
        get_ai_role_competitions(role_id),
        key=lambda x: x.get("rank", 999),
    )

    owner_assign = assignments[0] if assignments else None
    owner_member = mmap.get(owner_assign["employee_id"]) if owner_assign else None
    owner_analysis = (owner_assign or {}).get("analysis_result") or {}

    current_owner = None
    if owner_assign and owner_member:
        current_owner = {
            "employee_id": owner_member["id"],
            "name": owner_member["name"],
            "role": owner_member.get("role"),
            "score": round(owner_assign.get("match_score", 0)),
            "confidence": owner_assign.get("confidence", 0),
            "strengths": owner_analysis.get("strengths") or [],
            "gaps": owner_analysis.get("gaps") or [],
            "analysis": owner_analysis.get("summary") or owner_analysis.get("analysis") or "",
        }

    competition = []
    for c in competitions:
        if owner_assign and c["employee_id"] == owner_assign["employee_id"]:
            continue
        m = mmap.get(c["employee_id"])
        # 尝试从 assignments 取更细分析
        a = next((x for x in assignments if x["employee_id"] == c["employee_id"]), None)
        a_result = (a or {}).get("analysis_result") or {}
        competition.append({
            "employee_id": c["employee_id"],
            "name": m["name"] if m else c["employee_id"],
            "score": round(c.get("score", 0)),
            "rank": c.get("rank"),
            "reason": c.get("reason") or "",
            "strengths": a_result.get("strengths") or [],
            "gaps": a_result.get("gaps") or [],
        })
        if len(competition) >= 5:
            break

    risk = owner_analysis.get("risk_analysis") or {}
    if not risk:
        if not current_owner:
            risk = {
                "impact": "高",
                "if_owner_leaves": f"角色「{role['role_name']}」当前无人承担",
                "suggestion": "尽快指定负责人或通过「更新排名」重新匹配",
            }
        elif not competition:
            risk = {
                "impact": "高",
                "if_owner_leaves": f"若 {current_owner['name']} 离开，该角色无可用备份",
                "suggestion": "尽快培养至少一名备份人选",
            }
        else:
            top = competition[0]
            gap = current_owner["score"] - top["score"]
            impact = "高" if gap < 8 else ("中" if gap < 15 else "低")
            risk = {
                "impact": impact,
                "if_owner_leaves": f"若 {current_owner['name']} 离开，建议由 {top['name']}（匹配度 {top['score']}%）接任",
                "suggestion": f"培养 {top['name']} 作为备份" + (
                    f"；关注差距：{gap} 分" if gap >= 0 else ""
                ),
            }

    def _oig_profile(employee_id):
        try:
            from organization_graph.service import leadership_profile
            return leadership_profile(employee_id)
        except Exception:
            return None

    if current_owner:
        current_owner["oig"] = _oig_profile(current_owner["employee_id"])
    for c in competition:
        c["oig"] = _oig_profile(c["employee_id"])

    return {
        "role": {
            "id": role["id"],
            "name": role["role_name"],
            "description": role.get("description") or "",
            "responsibilities": role.get("responsibilities") or [],
            "required_skills": _with_communication_skill(role.get("required_skills") or []),
        },
        "current_owner": current_owner,
        "competition": competition,
        "risk_analysis": risk,
        "risk_level": {"高": "high", "中": "medium", "低": "low"}.get((risk or {}).get("impact"), "medium"),
        "evaluation_scope": {
            "type": role.get("evaluation_scope_type") or "TEAM",
            "label": scope_label(role),
            "config": role.get("evaluation_scope_config") or {},
            "minimum_competition_level": role.get("minimum_competition_level") or "L2",
            "minimum_match_score": role.get("minimum_match_score") or 60,
            "candidate_count": len(resolve_candidates_for_role(role, members)),
        },
        "evaluation_options": {
            "members": [{"id": m["id"], "name": m["name"], "role": m.get("role")} for m in members],
            "projects": list_known_projects(),
        },
        "leadership_formula": "能力 + 业绩 + 团队认可 + 组织影响力 + 资源控制 - 冲突风险",
        "training_standards": _role_standards(role["id"]),
        "communication_capability": _communication_capability(),
        "human_ai_division": _human_ai(role["id"]),
    }


def update_evaluation_scope(role_id, payload):
    role = get_ai_native_role(role_id)
    if not role:
        return None
    scope_type = (payload.get("type") or payload.get("evaluation_scope_type") or "TEAM").upper()
    if scope_type not in ("TEAM", "PROJECT", "ALL", "CUSTOM"):
        raise ValueError("评估范围必须是 TEAM / PROJECT / ALL / CUSTOM")
    config = payload.get("config") or payload.get("evaluation_scope_config") or {}
    if payload.get("employee_ids") is not None:
        config["employee_ids"] = payload.get("employee_ids")
    if payload.get("project") is not None:
        config["project"] = payload.get("project")
    updated = update_ai_native_evaluation_scope(
        role_id,
        scope_type,
        config,
        payload.get("minimum_competition_level"),
        payload.get("minimum_match_score"),
    )
    return {
        "role": updated,
        "evaluation_scope": {
            "type": updated.get("evaluation_scope_type"),
            "label": scope_label(updated),
            "config": updated.get("evaluation_scope_config") or {},
            "minimum_competition_level": updated.get("minimum_competition_level"),
            "minimum_match_score": updated.get("minimum_match_score"),
        },
        "message": "评估范围已修改，请点击「更新排名」重新分析。",
        "reranked": False,
    }


def start_ranking_update():
    """触发更新排名。已有 running 任务时幂等返回。"""
    with _lock:
        if _task_state["status"] == "running":
            return {
                "status": "running",
                "task_id": _task_state["task_id"],
                "message": "已有角色排名分析任务正在执行",
                "progress": _task_state["progress"],
            }
        task_id = f"task_{uuid.uuid4().hex[:12]}"
        _task_state.update({
            "status": "running",
            "task_id": task_id,
            "start_time": now_stamp(),
            "end_time": None,
            "progress": 0,
            "message": "任务已启动",
            "error": None,
        })

    thread = threading.Thread(target=_run_ranking_task, args=(task_id,), daemon=True)
    thread.start()
    return {"task_id": task_id, "status": "running", "message": "分析任务已启动"}


def _run_ranking_task(task_id):
    try:
        _set_status(progress=5, message="加载团队与角色数据")
        members = get_all_members()
        roles = get_ai_native_roles()
        events = get_events()[-30:]

        if not members:
            raise ValueError("团队尚无成员，请先在「成员管理」中添加人员")
        if not roles:
            raise ValueError("AI Native 角色模型为空，请重启后端以初始化内置角色")

        _set_status(progress=25, message="正在抽取人员能力画像（含日报证据）")
        evidence = build_ai_native_report_evidence(days=30)
        time.sleep(0.2)

        _set_status(progress=45, message="正在按评估范围进行角色匹配分析")
        result = analyze_ai_native_roles(members, roles, events, daily_evidence=evidence)

        _set_status(progress=75, message="正在计算竞争排名与风险")
        analysis_version = now_stamp("%Y%m%d%H%M%S")
        assignments, competitions = _normalize_analysis_result(result, members, roles)

        _set_status(progress=90, message="写入分析结果")
        replace_ai_role_analysis(assignments, competitions, analysis_version)

        degraded = last_call_degraded()
        msg = "分析完成"
        if degraded or is_mock_mode():
            msg = "分析完成（规则引擎/降级模式）"

        _set_status(
            status="success",
            progress=100,
            message=msg,
            end_time=now_stamp(),
            error=None,
        )
    except Exception as e:
        _set_status(
            status="failed",
            progress=_task_state.get("progress", 0),
            message=f"分析失败：{e}",
            end_time=now_stamp(),
            error=str(e),
        )


def _normalize_analysis_result(result, members, roles):
    """将 LLM/mock 输出规范为 DB 写入结构；每位成员每个角色都应有分数时，补全缺失。"""
    member_ids = {m["id"] for m in members}
    role_ids = {r["id"] for r in roles}
    role_results = result.get("roles") or []

    assignments = []
    competitions = []

    by_role = {item.get("role_id"): item for item in role_results if item.get("role_id") in role_ids}

    for role in roles:
        rid = role["id"]
        item = by_role.get(rid) or {}
        candidates = item.get("candidates") or []
        allowed_ids = {m["id"] for m in resolve_candidates_for_role(role, members)}

        # 规范化候选
        scored = []
        seen = set()
        for c in candidates:
            eid = c.get("employee_id")
            if not eid or eid not in member_ids or eid in seen:
                continue
            if allowed_ids and eid not in allowed_ids:
                continue
            seen.add(eid)
            scored.append({
                "employee_id": eid,
                "score": float(c.get("score", 0)),
                "confidence": float(c.get("confidence", 0.75)),
                "reason": c.get("reason") or "",
                "strengths": c.get("strengths") or [],
                "gaps": c.get("gaps") or [],
                "summary": c.get("summary") or c.get("reason") or "",
                "risk_analysis": c.get("risk_analysis"),
            })

        scored.sort(key=lambda x: x["score"], reverse=True)

        # 若 LLM 漏人，仅在评估范围内用低分补齐
        fill_pool = [m for m in members if m["id"] in allowed_ids] if allowed_ids else []
        for m in fill_pool:
            if m["id"] not in seen:
                scored.append({
                    "employee_id": m["id"],
                    "score": 35.0,
                    "confidence": 0.5,
                    "reason": "信息不足，默认较低匹配",
                    "strengths": [],
                    "gaps": role.get("required_skills") or [],
                    "summary": "暂无足够数据支撑匹配判断",
                    "risk_analysis": None,
                })
        scored.sort(key=lambda x: x["score"], reverse=True)

        for idx, c in enumerate(scored):
            analysis = {
                "strengths": c["strengths"],
                "gaps": c["gaps"],
                "summary": c["summary"],
                "reason": c["reason"],
            }
            if idx == 0 and c.get("risk_analysis"):
                analysis["risk_analysis"] = c["risk_analysis"]
            elif idx == 0:
                # 基于竞争差距生成默认风险
                backup = scored[1] if len(scored) > 1 else None
                if backup:
                    gap = c["score"] - backup["score"]
                    impact = "高" if gap < 8 else ("中" if gap < 15 else "低")
                    analysis["risk_analysis"] = {
                        "impact": impact,
                        "if_owner_leaves": f"匹配度差距约 {round(gap)} 分",
                        "suggestion": f"培养备份人选（当前次优匹配度 {round(backup['score'])}%）",
                    }

            assignments.append({
                "role_id": rid,
                "employee_id": c["employee_id"],
                "match_score": round(c["score"], 1),
                "confidence": c["confidence"],
                "analysis_result": analysis,
            })
            competitions.append({
                "role_id": rid,
                "employee_id": c["employee_id"],
                "rank": idx + 1,
                "score": round(c["score"], 1),
                "reason": c["reason"] or c["summary"],
            })

    return assignments, competitions
