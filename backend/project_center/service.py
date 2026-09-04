"""项目中心业务：阶段推进、健康度、日报动态合并。"""

from datetime import datetime

from timeutil import today as beijing_today

from database import get_member, get_all_members, get_daily_reports

from . import repository as repo


PROJECT_STATUS = ("open", "paused", "closed")
STATUS_LABEL = {
    "open": "开启",
    "paused": "暂停",
    "closed": "关闭",
}
STATUS_ALIAS = {
    "open": "open", "开启": "open",
    "draft": "open", "planning": "open", "active": "open", "进行中": "open", "规划中": "open", "草稿": "open",
    "paused": "paused", "暂停": "paused", "已暂停": "paused",
    "closed": "closed", "关闭": "closed",
    "completed": "closed", "archived": "closed", "已完成": "closed", "已归档": "closed",
}
STAGE_STATUS = ("not_started", "in_progress", "completed", "paused", "delayed", "cancelled")
STAGE_LABEL = {
    "not_started": "未开始", "in_progress": "进行中", "completed": "已完成",
    "paused": "暂停", "delayed": "延期", "cancelled": "取消",
}
TRANSITIONS = {
    "open": {"paused", "closed"},
    "paused": {"open", "closed"},
    "closed": {"open", "paused"},
}

HEALTH_LABEL = {
    "healthy": "健康",
    "attention": "关注",
    "risk": "风险",
    "insufficient": "信息不足",
}


def _today():
    return beijing_today()


def normalize_status(raw, default="open"):
    if raw is None or str(raw).strip() == "":
        return default
    key = str(raw).strip()
    mapped = STATUS_ALIAS.get(key) or STATUS_ALIAS.get(key.lower())
    if mapped not in PROJECT_STATUS:
        raise ValueError("项目状态无效，请选择：开启 / 暂停 / 关闭")
    return mapped


def stage_progress_view(stage, milestones):
    related = [m for m in (milestones or []) if m.get("stage_id") == stage.get("id")]
    if related:
        done = sum(1 for m in related if m.get("status") == "completed")
        return {
            "value": round(100.0 * done / max(1, len(related)), 1),
            "mode": "milestone",
            "label": f"{done}/{len(related)} 里程碑",
        }
    if stage.get("progress") is not None:
        return {"value": float(stage["progress"]), "mode": "manual", "label": "人工填写"}
    return {"value": None, "mode": "unknown", "label": "未知"}


def collect_missing(project):
    """进度 / 健康度还缺哪些可补信息。不编造分数。"""
    items = []
    stages = project.get("stages") or []
    current = next((s for s in stages if s.get("id") == project.get("current_stage_id")), None)
    if not current and stages:
        current = stages[0]
    view = stage_progress_view(current, project.get("milestones") or []) if current else {}
    has_manual = any(s.get("progress") is not None for s in stages)
    if not stages:
        items.append({
            "key": "stage",
            "label": "尚未定义阶段",
            "where": "阶段进度",
            "need": "progress",
            "detail": "至少添加一个阶段，才有进度主链路",
        })
    elif view.get("value") is None and not has_manual:
        items.append({
            "key": "progress",
            "label": "当前阶段进度未知",
            "where": "阶段进度 → 人工进度",
            "need": "progress",
            "detail": "填写 0–100，或给当前阶段加里程碑（完成数会自动换算进度）",
        })
    if not (project.get("milestones") or []):
        items.append({
            "key": "milestone",
            "label": "没有里程碑",
            "where": "里程碑",
            "need": "progress",
            "detail": "可选。有里程碑后可用完成比例作为进度",
        })
    if not (project.get("risks") or []):
        items.append({
            "key": "risk",
            "label": "没有风险记录",
            "where": "风险",
            "need": "health",
            "detail": "可选。记过风险后，健康度才会计入风险项",
        })
    start = (project.get("start_date") or "").strip()
    end = (project.get("end_date") or "").strip()
    if not start or not end:
        lack = []
        if not start:
            lack.append("开始时间")
        if not end:
            lack.append("预计结束时间")
        items.append({
            "key": "dates",
            "label": "缺少" + "、".join(lack),
            "where": "项目概览",
            "need": "health",
            "detail": "起止时间都填了，健康度才会考虑时间维度",
        })
    return items


def compute_health(project):
    stages = project.get("stages") or []
    milestones = project.get("milestones") or []
    risks = [r for r in (project.get("risks") or []) if r.get("status") in ("open", "processing")]
    has_manual_progress = any(s.get("progress") is not None for s in stages)
    has_milestone = bool(milestones)
    has_risk_data = bool(project.get("risks"))
    has_dates = bool((project.get("start_date") or "").strip() and (project.get("end_date") or "").strip())
    missing = collect_missing(project)
    if not has_manual_progress and not has_milestone and not has_risk_data and not has_dates:
        return {
            "status": "insufficient",
            "label": "信息不足",
            "score": None,
            "reasons": ["仅有名称 / 负责人 / 阶段，不足以评分"],
            "weights": {},
            "missing": missing,
        }

    weights = {"stage": 35, "milestone": 25, "risk": 20, "time": 10, "task": 10}
    if not has_milestone:
        weights["milestone"] = 0
    weights["task"] = 0
    if not has_risk_data:
        weights["risk"] = 0
    if not has_dates:
        weights["time"] = 0
    total_w = sum(weights.values()) or 1

    n = max(1, len(stages))
    done = sum(1 for s in stages if s.get("status") == "completed")
    delayed = sum(1 for s in stages if s.get("status") == "delayed")
    current = next((s for s in stages if s["id"] == project.get("current_stage_id")), None)
    cur_prog = stage_progress_view(current, milestones) if current else {"value": None}
    stage_score = done / n * 70
    if cur_prog.get("value") is not None:
        stage_score += cur_prog["value"] * 0.3
    else:
        stage_score += (30 if (current or {}).get("status") == "in_progress" else 0)
    stage_score = max(0, min(100, stage_score - delayed * 12))

    if has_milestone:
        md = sum(1 for m in milestones if m.get("status") == "completed")
        overdue = sum(
            1 for m in milestones
            if m.get("planned_date") and m.get("status") != "completed" and m["planned_date"] < _today()
        )
        milestone_score = max(0, md / max(1, len(milestones)) * 100 - overdue * 15)
    else:
        milestone_score = 0

    high = sum(1 for r in risks if r.get("level") in ("high", "高"))
    medium = sum(1 for r in risks if r.get("level") in ("medium", "中"))
    risk_score = max(0, 100 - high * 30 - medium * 12) if has_risk_data else 0

    time_score = 0
    if has_dates:
        try:
            start = datetime.strptime(project["start_date"][:10], "%Y-%m-%d")
            end = datetime.strptime(project["end_date"][:10], "%Y-%m-%d")
            now = datetime.strptime(_today(), "%Y-%m-%d")
            span = max(1, (end - start).days)
            used = (now - start).days
            ratio = used / span
            if current and cur_prog.get("value") is not None:
                gap = ratio - cur_prog["value"] / 100
                time_score = max(0, 100 - max(0, gap) * 120)
            else:
                time_score = 70 if ratio < 1 else 40
        except ValueError:
            time_score = 0
            weights["time"] = 0
            total_w = sum(weights.values()) or 1

    score = (
        stage_score * weights["stage"]
        + milestone_score * weights["milestone"]
        + risk_score * weights["risk"]
        + time_score * weights["time"]
    ) / total_w

    if high or delayed:
        status = "risk"
    elif score < 60 or medium:
        status = "attention"
    else:
        status = "healthy"
    reasons = []
    if delayed:
        reasons.append(f"{delayed} 个阶段延期")
    if high:
        reasons.append(f"{high} 条高风险未关闭")
    if not reasons:
        reasons.append("阶段推进可用，未发现高风险")
    return {
        "status": status,
        "label": HEALTH_LABEL[status],
        "score": round(score, 1),
        "reasons": reasons,
        "weights": {k: round(v / total_w * 100, 1) for k, v in weights.items() if v},
        "parts": {
            "stage": round(stage_score, 1),
            "milestone": round(milestone_score, 1) if has_milestone else None,
            "risk": round(risk_score, 1) if has_risk_data else None,
            "time": round(time_score, 1) if weights.get("time") else None,
        },
        "missing": missing,
    }


def enrich(project):
    if not project:
        return None
    mmap = {m["id"]: m for m in get_all_members()}
    project["owner_name"] = (mmap.get(project["owner_id"]) or {}).get("name") or project["owner_id"]
    for s in project.get("stages") or []:
        s["status_label"] = STAGE_LABEL.get(s.get("status"), s.get("status"))
        s["progress_view"] = stage_progress_view(s, project.get("milestones") or [])
        s["owner_name"] = (mmap.get(s.get("owner_id")) or {}).get("name") if s.get("owner_id") else None
    for m in project.get("members") or []:
        m["user_name"] = (mmap.get(m.get("user_id")) or {}).get("name") or m.get("user_id")
    for r in project.get("risks") or []:
        r["owner_name"] = (mmap.get(r.get("owner_id")) or {}).get("name") if r.get("owner_id") else None
    for ms in project.get("milestones") or []:
        ms["owner_name"] = (mmap.get(ms.get("owner_id")) or {}).get("name") if ms.get("owner_id") else None
        st = next((s for s in (project.get("stages") or []) if s["id"] == ms.get("stage_id")), None)
        ms["stage_name"] = (st or {}).get("name")
    if project.get("current_stage"):
        project["current_stage"]["progress_view"] = stage_progress_view(
            project["current_stage"], project.get("milestones") or []
        )
        project["current_stage"]["status_label"] = STAGE_LABEL.get(
            project["current_stage"].get("status"), project["current_stage"].get("status")
        )
    project["status"] = STATUS_ALIAS.get(project.get("status") or "open", project.get("status")) or "open"
    project["status_label"] = STATUS_LABEL.get(project.get("status"), project.get("status"))
    project["health"] = compute_health(project)
    cur = project.get("current_stage") or {}
    project["stage_progress"] = (cur.get("progress_view") or {}).get("value")
    return project


def list_projects(filters=None):
    rows = repo.list_projects(filters)
    return [enrich(r) for r in rows]


def get_project(project_id):
    item = repo.get_project(project_id)
    if not item:
        return None
    item = enrich(item)
    item["activities"] = merge_daily_activities(item)
    return item


def merge_daily_activities(project):
    stored = list(project.get("activities") or [])
    names = {project.get("name")}
    names.update(s.get("name") for s in (project.get("stages") or []) if s.get("name"))
    try:
        reports = get_daily_reports(limit=400)
    except Exception:
        reports = []
    seen = {(a.get("source"), a.get("source_id")) for a in stored}
    extra = []
    for r in reports:
        tags = r.get("projects") or []
        if not any(n and n in tags for n in names):
            continue
        key = ("DAILY_REPORT", str(r.get("id")))
        if key in seen:
            continue
        member = get_member(r.get("member_id"))
        extra.append({
            "id": f"dr_{r.get('id')}",
            "project_id": project["id"],
            "stage_id": project.get("current_stage_id"),
            "type": "daily_report",
            "content": (r.get("content") or "")[:240],
            "source": "DAILY_REPORT",
            "source_id": str(r.get("id")),
            "operator_id": r.get("member_id"),
            "operator_name": (member or {}).get("name") or r.get("member_id"),
            "created_at": r.get("report_date"),
        })
    merged = stored + extra
    merged.sort(key=lambda a: a.get("created_at") or "", reverse=True)
    return merged[:80]


def create_project(payload):
    name = (payload.get("name") or "").strip()
    desc = (payload.get("description") or "").strip()
    owner = payload.get("owner_id") or ""
    if not name or not desc or not owner:
        raise ValueError("项目名称、简介、负责人为必填")
    stages = payload.get("stages") or []
    if not any((s.get("name") or "").strip() for s in stages):
        raise ValueError("请至少定义一个阶段")
    payload = {**payload, "name": name, "description": desc, "owner_id": owner}
    payload["status"] = normalize_status(payload.get("status"), default="open")
    item = repo.create_project(payload)
    return enrich(item)


def _normalize_progress(value):
    if value is None:
        return None
    try:
        n = float(value)
    except (TypeError, ValueError):
        raise ValueError("进度须为 0–100 的数字")
    if n < 0 or n > 100:
        raise ValueError("进度须在 0–100 之间")
    return n


def update_stage(project_id, stage_id, payload):
    stage = repo.get_stage(stage_id)
    if not stage or stage.get("project_id") != project_id:
        return None
    data = dict(payload)
    if "progress" in data:
        data["progress"] = _normalize_progress(data.get("progress"))
    updated = repo.update_stage(stage_id, data)
    if not updated:
        return None
    return get_project(project_id)


def update_project(project_id, payload, force=False):
    current = repo.get_project(project_id)
    if not current:
        return None
    if payload.get("status") is not None:
        payload = {**payload, "status": normalize_status(payload.get("status"))}
        cur_status = STATUS_ALIAS.get(current.get("status") or "open", current.get("status")) or "open"
        if payload["status"] != cur_status:
            allowed = TRANSITIONS.get(cur_status, set())
            if payload["status"] not in allowed and not force:
                raise ValueError(
                    f"不允许从 {STATUS_LABEL.get(cur_status)} 变更为 "
                    f"{STATUS_LABEL.get(payload['status'])}"
                )
            repo.add_activity(project_id, {
                "type": "status",
                "content": f"项目状态：{STATUS_LABEL.get(cur_status)} → {STATUS_LABEL.get(payload['status'])}",
                "source": "SYSTEM",
                "operator_id": payload.get("operator_id") or current.get("owner_id"),
            })
    item = repo.update_project(project_id, payload)
    return enrich(item)


def complete_stage(project_id, stage_id, summary="", operator_id=""):
    project = repo.get_project(project_id)
    if not project:
        raise ValueError("项目不存在")
    stages = sorted(project.get("stages") or [], key=lambda s: s.get("sort_order") or 0)
    current = next((s for s in stages if s["id"] == stage_id), None)
    if not current:
        raise ValueError("阶段不存在")
    if current.get("status") == "completed":
        raise ValueError("该阶段已完成")
    repo.update_stage(stage_id, {
        "status": "completed",
        "progress": 100,
        "actual_end_date": _today(),
    })
    nxt = None
    for s in stages:
        if s.get("sort_order", 0) > current.get("sort_order", 0) and s.get("status") != "cancelled":
            nxt = s
            break
    content = f"阶段推进：{current.get('name')} → 已完成"
    if nxt:
        repo.update_stage(nxt["id"], {
            "status": "in_progress",
            "actual_start_date": _today(),
        })
        repo.update_project(project_id, {"current_stage_id": nxt["id"]})
        content = f"阶段推进：{current.get('name')} → {nxt.get('name')}"
    if summary:
        content = f"{content}。总结：{summary}"
    repo.add_activity(project_id, {
        "stage_id": stage_id,
        "type": "stage_complete",
        "content": content,
        "source": "STAGE",
        "operator_id": operator_id or project.get("owner_id"),
    })
    return get_project(project_id)
