"""结构化指标：先算分，再交给 LLM 解释。"""

from collections import Counter, defaultdict
from datetime import datetime, timedelta

from timeutil import today_minus_days

from .collectors import FOCUS_LABELS, classify_focus
from . import repository as repo


def status_from_score(score):
    s = float(score or 0)
    if s >= 80:
        return "normal"
    if s >= 60:
        return "attention"
    return "risk"


def status_label(code):
    return {"normal": "正常", "attention": "关注", "risk": "风险"}.get(code, "关注")


def workload_band(score):
    s = float(score or 0)
    if s < 40:
        return "低"
    if s < 70:
        return "正常"
    if s < 85:
        return "较高"
    return "高负载"


def _in_range(reports, days):
    start = today_minus_days(days)
    return [r for r in reports if (r.get("report_date") or "") >= start]


def focus_distribution(reports):
    counts = Counter()
    for r in reports:
        counts[classify_focus(r.get("activity_type"), r.get("content") or "")] += 1
    total = sum(counts.values()) or 1
    return {k: round(counts.get(k, 0) / total * 100, 1) for k in FOCUS_LABELS}


def compute_member_metrics(member, snapshot):
    mid = member["id"]
    reports = [r for r in snapshot["daily_reports"] if r.get("member_id") == mid]
    r30 = _in_range(reports, 30)
    start7 = today_minus_days(7)
    r7 = [r for r in r30 if (r.get("report_date") or "") >= start7]
    r_old = [r for r in r30 if (r.get("report_date") or "") < start7]
    focus7 = focus_distribution(r7)
    focus30 = focus_distribution(r30)
    deltas = {k: round(focus7.get(k, 0) - focus30.get(k, 0), 1) for k in FOCUS_LABELS}
    projects7 = set()
    projects_old = set()
    for r in r7:
        projects7.update(p for p in (r.get("projects") or []) if p and p != "未分类")
    for r in r_old:
        projects_old.update(p for p in (r.get("projects") or []) if p and p != "未分类")
    added = sorted(projects7 - projects_old)
    exited = sorted(projects_old - projects7)
    difficulties = [float(r.get("difficulty") or 3) for r in r7]
    avg_diff = sum(difficulties) / len(difficulties) if difficulties else 3
    top_focus = max(focus7, key=focus7.get) if r7 else "其他"
    main_project = Counter(
        p for r in r7 for p in (r.get("projects") or []) if p and p != "未分类"
    ).most_common(1)
    pc_roles = []
    owned = []
    core_n = 0
    p0_n = 0
    for p in snapshot.get("projects") or []:
        if p.get("source") != "project_center":
            continue
        if p.get("project_status") in ("archived", "draft", "closed", "completed"):
            continue
        is_owner = p.get("owner_id") == mid
        roles = p.get("member_roles") or []
        mine = next((r for r in roles if r.get("id") == mid), None)
        if not is_owner and not mine:
            continue
        role_name = "负责人" if is_owner else (mine.get("role") if mine else "成员")
        level = "核心" if is_owner else ((mine or {}).get("participation_level") or "主要")
        pc_roles.append({
            "project_id": p.get("project_id"),
            "project_name": p.get("project_name"),
            "role": role_name,
            "participation_level": level,
            "priority": p.get("priority"),
            "status": p.get("project_status"),
            "stage": p.get("current_stage"),
        })
        if is_owner:
            owned.append(p.get("project_name"))
        if is_owner or level == "核心":
            core_n += 1
        if p.get("priority") in ("P0", "P1"):
            p0_n += 1
    if pc_roles:
        projects7 = set(r["project_name"] for r in pc_roles) | projects7
        added = sorted(set(added) | (set(r["project_name"] for r in pc_roles) - projects_old))
    load = min(100, round(
        min(len(r7), 7) / 5 * 22
        + len(pc_roles or projects7) * 10
        + len(owned) * 12
        + p0_n * 8
        + core_n * 6
        + (avg_diff - 3) * 6
    ))
    collab_pairs = []
    for rel in snapshot.get("relationships") or []:
        pair = rel.get("pair") or ""
        if f"{mid}→" in pair or f"→{mid}" in pair:
            if abs(rel.get("trust") or 0) >= 6 or abs(rel.get("sentiment") or 0) >= 6:
                collab_pairs.append(rel)
    role_cards = [c for c in (snapshot.get("role_competitions") or []) if c.get("member_id") == mid]
    return {
        "member_id": mid,
        "name": member.get("name"),
        "role": member.get("role"),
        "workload_score": load,
        "workload_band": workload_band(load),
        "work_focus": {"d7": focus7, "d30": focus30, "primary": top_focus},
        "focus_change": deltas,
        "project_count": len(pc_roles) or len(projects7),
        "projects": [r["project_name"] for r in pc_roles] or sorted(projects7),
        "projects_added": added,
        "projects_exited": exited,
        "owned_projects": owned,
        "pc_roles": pc_roles,
        "core_project_count": core_n,
        "p0_project_count": p0_n,
        "collab_signals": collab_pairs[:6],
        "role_cards": role_cards[:4],
        "report_days_7": len(r7),
        "report_days_30": len(r30),
        "main_work": owned[0] if owned else (main_project[0][0] if main_project else (top_focus or "—")),
        "metrics": {
            "name": member.get("name"),
            "avg_difficulty_7": round(avg_diff, 2),
            "report_days_7": len(r7),
            "project_count_7": len(pc_roles) or len(projects7),
            "owner_count": len(owned),
            "core_project_count": core_n,
        },
    }


def _health_status(health):
    if isinstance(health, dict):
        return health.get("status")
    return health


def _health_obj(health):
    if isinstance(health, dict):
        return health
    return {"status": health} if health else {}


def compute_project_metrics(project, report_date):
    acts = project.get("activities") or []
    last = project.get("last_date")
    start = project.get("start_date")
    days_since = 99
    if last:
        try:
            days_since = (datetime.strptime(report_date, "%Y-%m-%d") - datetime.strptime(last, "%Y-%m-%d")).days
        except ValueError:
            days_since = 99
    d7 = [a for a in acts if a["date"] >= (datetime.strptime(report_date, "%Y-%m-%d") - timedelta(days=7)).strftime("%Y-%m-%d")]
    d3 = [a for a in acts if a["date"] >= (datetime.strptime(report_date, "%Y-%m-%d") - timedelta(days=3)).strftime("%Y-%m-%d")]
    test_n = sum(1 for a in d7 if a.get("activity_type") == "测试")
    dev_n = sum(1 for a in d7 if a.get("activity_type") == "开发")
    # 进度：项目中心有事实则用事实；没有则允许未知，不编造百分比
    if project.get("source") == "project_center":
        progress = project.get("progress")
        stage = project.get("current_stage") or "阶段未知"
    else:
        progress = min(92, 18 + project.get("active_days", 0) * 3 + (12 if test_n else 0) + min(20, len(d7) * 3))
        stage = "开发进行中"
        if test_n and not dev_n:
            stage = "测试进行中"
        elif test_n and dev_n:
            stage = "开发+测试并行"
        elif not d7:
            stage = "近期无日报进展"
    hist = repo.previous_project_progress(project["project_id"], report_date, days=3)
    hist_vals = [h.get("progress") for h in hist if h.get("progress") is not None]
    stalled_hist = len(hist_vals) >= 2 and max(hist_vals) - min(hist_vals) < 1
    if project.get("source") == "project_center":
        inactive = False
        stalled = project.get("project_status") == "paused"
        progress_change = 0
        if progress is not None and hist_vals:
            progress_change = round(progress - hist_vals[0], 1)
        schedule = "stalled" if stalled else "normal"
        risk = "info"
        hstat = _health_status(project.get("health"))
        if hstat == "risk":
            risk = "high"
        elif hstat in ("attention", "insufficient") or stalled:
            risk = "attention"
    else:
        inactive = days_since > 14
        stalled = (not inactive) and ((days_since >= 3 and project.get("active_days", 0) >= 2) or stalled_hist)
        progress_change = 0
        if hist_vals:
            progress_change = round((progress or 0) - hist_vals[0], 1)
        schedule = "normal"
        risk = "info"
        if inactive:
            schedule = "inactive"
            risk = "info"
        elif stalled:
            schedule = "stalled"
            risk = "medium"
            if days_since >= 7:
                risk = "high"
    # 人员瓶颈：一人承担过半活动
    counts = Counter(a["member_id"] for a in acts)
    bottleneck = None
    if counts:
        top_id, top_n = counts.most_common(1)[0]
        if top_n / max(1, len(acts)) >= 0.7 and len(counts) >= 1 and len(acts) >= 4:
            bottleneck = top_id
            if risk == "info":
                risk = "attention"
    return {
        "project_id": project["project_id"],
        "project_name": project["project_name"],
        "owner_id": project.get("owner_id"),
        "members": project.get("members") or [],
        "progress": progress,
        "progress_change": progress_change,
        "schedule_status": schedule,
        "risk_level": risk,
        "current_stage": stage,
        "start_date": start,
        "last_date": last,
        "days_since_update": days_since,
        "week": {
            "dev": dev_n,
            "test": test_n,
            "mentions": len(d7),
            "last_3d": len(d3),
        },
        "bottleneck_member_id": bottleneck,
        "source": project.get("source"),
        "project_status": project.get("project_status"),
        "priority": project.get("priority"),
        "owner_name": project.get("owner_name"),
        "previous_stage": None,
        "recent_changes": [],
        "health": _health_obj(project.get("health")),
        "open_risks": project.get("open_risks") or [],
        "milestones": project.get("milestones") or [],
        "member_roles": project.get("member_roles") or [],
        "metrics": {
            "active_days": project.get("active_days"),
            "days_since_update": days_since,
            "stalled": stalled,
            "source": project.get("source"),
            "project_status": project.get("project_status"),
            "priority": project.get("priority"),
            "health": _health_obj(project.get("health")),
            "open_risks": project.get("open_risks") or [],
            "milestones": project.get("milestones") or [],
            "member_roles": project.get("member_roles") or [],
            "owner_name": project.get("owner_name"),
        },
        "confidence": min(0.92, 0.45 + min(len(acts), 20) * 0.02),
    }


def compute_health(member_rows, project_rows, snapshot, weights):
    members = snapshot["members"]
    included_ids = {m["id"] for m in members}
    reports7 = [
        r for r in _in_range(snapshot["daily_reports"], 7)
        if r.get("member_id") in included_ids
    ]
    n = max(1, len(members))
    high_load = sum(1 for m in member_rows if (m.get("workload_score") or 0) >= 85)
    missing = sum(1 for m in members if not any(r["member_id"] == m["id"] for r in reports7))
    member_score = max(0, 100 - high_load / n * 35 - missing / n * 25)
    use_rows = [p for p in project_rows if p.get("source") == "project_center"] or project_rows
    stalled = sum(1 for p in use_rows if p.get("schedule_status") == "stalled")
    high_risk = sum(1 for p in use_rows if p.get("risk_level") == "high")
    active_n = sum(1 for p in use_rows if p.get("schedule_status") != "inactive" and p.get("project_status") not in ("completed", "closed"))
    pn = max(1, active_n)
    project_score = 82 if not use_rows else max(0, 100 - stalled / pn * 40 - high_risk / pn * 20)
    expected = n * 4
    task_score = min(100, len(reports7) / max(1, expected) * 100)
    # 协作：同一天同一项目出现 >=2 人
    pairs = set()
    by_day_proj = defaultdict(set)
    for r in reports7:
        if r.get("member_id") not in included_ids:
            continue
        for p in r.get("projects") or []:
            if p and p != "未分类":
                by_day_proj[(r["report_date"], p)].add(r["member_id"])
    for people in by_day_proj.values():
        pl = sorted(people)
        for i, a in enumerate(pl):
            for b in pl[i + 1:]:
                pairs.add((a, b))
    collab_score = min(100, 48 + len(pairs) * 8)
    pw = float(weights.get("project_weight", 40))
    mw = float(weights.get("member_weight", 25))
    tw = float(weights.get("task_weight", 20))
    cw = float(weights.get("collab_weight", 15))
    total_w = pw + mw + tw + cw or 100
    team = (project_score * pw + member_score * mw + task_score * tw + collab_score * cw) / total_w
    reasons = []
    if stalled:
        reasons.append(f"{stalled} 个项目近期缺少进展")
    if high_load:
        reasons.append(f"{high_load} 人处于高负载")
    if missing:
        reasons.append(f"{missing} 人近7天无日报")
    if not reasons:
        reasons.append("近7天日报与项目活动整体连续")
    return {
        "team_health_score": round(team, 1),
        "team_status": status_from_score(team),
        "project_score": round(project_score, 1),
        "member_score": round(member_score, 1),
        "task_score": round(task_score, 1),
        "collaboration_score": round(collab_score, 1),
        "reasons": reasons,
        "collab_pairs": len(pairs),
        "included_member_ids": [m["id"] for m in members],
        "included_count": len(members),
    }
