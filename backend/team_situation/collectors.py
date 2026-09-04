"""从现有模块采集快照：日报、成员、推断项目、培养任务。"""

import re
from collections import defaultdict, Counter

from timeutil import now_iso, today as beijing_today, today_minus_days

from database import get_all_members, get_daily_reports
from newcomer.repository import list_newcomers, list_tasks as list_nc_tasks

from . import repository as repo


FOCUS_LABELS = (
    "技术开发", "产品设计", "项目管理", "沟通协调",
    "研究", "测试", "文档", "新人培养", "其他",
)

ACTIVITY_TO_FOCUS = {
    "开发": "技术开发",
    "设计": "产品设计",
    "测试": "测试",
    "会议": "沟通协调",
    "调研": "研究",
    "文档": "文档",
    "运维": "其他",
    "其他": "其他",
}

FOCUS_KEYWORDS = {
    "项目管理": ["排期", "里程碑", "进度管理", "项目管理", "跟进项目"],
    "沟通协调": ["对齐", "协调", "同步", "沟通", "会议"],
    "新人培养": ["带教", "新人", "培养", "onboard", "入职"],
    "研究": ["调研", "预研", "POC", "探索"],
}


def _today():
    return beijing_today()


def _days_ago(n):
    return today_minus_days(n)


def _slug(name):
    raw = re.sub(r"[^0-9a-zA-Z\u4e00-\u9fff]+", "_", (name or "").strip()).strip("_")
    return f"proj_{(raw or 'unknown').lower()}"[:80]


def classify_focus(activity_type, content=""):
    text = content or ""
    for focus, kws in FOCUS_KEYWORDS.items():
        if any(k in text for k in kws):
            return focus
    return ACTIVITY_TO_FOCUS.get(activity_type or "其他", "其他")


def collect_snapshot(days=90):
    all_members = get_all_members()
    cfg = repo.get_config()
    members = repo.resolve_included_members(all_members, cfg)
    included_ids = {m["id"] for m in members}
    reports = get_daily_reports(date_from=_days_ago(days), date_to=_today(), limit=3000)
    team_reports = [r for r in reports if r.get("member_id") in included_ids] if included_ids else reports
    tasks = []
    try:
        for nc in list_newcomers():
            if included_ids and nc.get("employee_id") not in included_ids:
                continue
            for t in list_nc_tasks(nc["id"]):
                tasks.append({
                    "id": t["id"],
                    "name": t.get("task_name"),
                    "level": t.get("task_level"),
                    "status": t.get("status"),
                    "employee_id": nc.get("employee_id"),
                    "estimated_hours": t.get("estimated_hours"),
                })
    except Exception as e:
        print(f"[situation] 培养任务采集跳过: {e}")
    context = repo.list_context(days=14)
    recent_reports = [r for r in team_reports if (r.get("report_date") or "") >= _days_ago(30)]
    relationships = []
    try:
        from memory_engine import compute_relationship_grid
        grid = compute_relationship_grid() or {}
        relationships = [
            {"pair": k, "trust": v.get("trust"), "sentiment": v.get("sentiment"), "tag": v.get("tag")}
            for k, v in grid.items()
            if abs(v.get("trust") or 0) >= 4 or abs(v.get("sentiment") or 0) >= 4
        ]
    except Exception as e:
        print(f"[situation] 关系网采集跳过: {e}")
    role_competitions = []
    try:
        from database import get_ai_role_assignments, get_ai_native_roles
        roles = {r["id"]: r for r in get_ai_native_roles()}
        for a in get_ai_role_assignments():
            eid = a.get("employee_id") or a.get("member_id")
            if included_ids and eid not in included_ids:
                continue
            role = roles.get(a.get("role_id")) or {}
            role_competitions.append({
                "member_id": eid,
                "role_id": a.get("role_id"),
                "role_name": role.get("name") or role.get("role_code"),
                "match_score": a.get("match_score"),
            })
    except Exception as e:
        print(f"[situation] 角色竞争采集跳过: {e}")
    today = _today()
    prev = repo.latest_report_before(today)
    week_ago_date = _days_ago(7)
    week_ago = repo.get_report_by_date(week_ago_date) or repo.latest_report_before(week_ago_date)
    return {
        "collected_at": now_iso(),
        "members": members,
        "all_members": all_members,
        "included_member_ids": [m["id"] for m in members],
        "daily_reports": team_reports,
        "projects": _projects_for_situation(recent_reports, members),
        "tasks": tasks,
        "roles": role_competitions,
        "relationships": relationships,
        "role_competitions": role_competitions,
        "manual_context": context,
        "prev_report": prev,
        "week_ago_report": week_ago,
    }


def _projects_for_situation(reports, members):
    derived = _derive_projects(reports, members)
    registered = []
    try:
        from project_center.service import list_projects as list_pc_projects
        registered = list_pc_projects({"include_archived": False}) or []
    except Exception as e:
        print(f"[situation] 项目中心采集跳过: {e}")
        return derived
    if not registered:
        return derived
    mmap = {m["id"]: m for m in members}
    by_name = {}
    for d in derived:
        by_name[d["project_name"]] = d
    out = []
    used_names = set()
    for p in registered:
        if p.get("status") in ("closed", "archived", "draft", "completed"):
            continue
        name = p.get("name")
        used_names.add(name)
        d = by_name.get(name) or {}
        acts = d.get("activities") or []
        dates = sorted({a["date"] for a in acts}) if acts else []
        cur = p.get("current_stage") or {}
        prog = (cur.get("progress_view") or {}).get("value") if isinstance(cur, dict) else None
        if prog is None:
            prog = cur.get("progress") if isinstance(cur, dict) else None
        members_info = []
        for m in p.get("members") or []:
            uid = m.get("user_id")
            members_info.append({"id": uid, "name": (mmap.get(uid) or {}).get("name") or uid})
        if not members_info and p.get("owner_id"):
            members_info = [{"id": p["owner_id"], "name": p.get("owner_name") or p["owner_id"]}]
        out.append({
            "project_id": p["id"],
            "project_name": name,
            "owner_id": p.get("owner_id"),
            "owner_name": p.get("owner_name"),
            "members": members_info,
            "member_roles": [
                {
                    "id": m.get("user_id"),
                    "name": (mmap.get(m.get("user_id")) or {}).get("name") or m.get("user_id"),
                    "role": m.get("role"),
                    "participation_level": m.get("participation_level"),
                }
                for m in (p.get("members") or [])
            ],
            "start_date": p.get("start_date") or (dates[0] if dates else None),
            "last_date": dates[-1] if dates else (p.get("updated_at") or "")[:10],
            "active_days": len(dates) or 1,
            "activities": acts,
            "source": "project_center",
            "progress": prog,
            "current_stage": (cur or {}).get("name") or "",
            "current_stage_id": p.get("current_stage_id"),
            "project_status": p.get("status"),
            "priority": p.get("priority"),
            "health": p.get("health") or {},
            "open_risks": [
                {"id": r.get("id"), "title": r.get("title"), "level": r.get("level"), "status": r.get("status")}
                for r in (p.get("risks") or []) if r.get("status") in ("open", "processing", "开放", "处理中")
            ],
            "milestones": [
                {"id": ms.get("id"), "name": ms.get("name"), "status": ms.get("status"), "planned_date": ms.get("planned_date")}
                for ms in (p.get("milestones") or [])
            ],
            "stages": [
                {"id": s.get("id"), "name": s.get("name"), "status": s.get("status"), "sort_order": s.get("sort_order")}
                for s in (p.get("stages") or [])
            ],
        })
    for d in derived:
        if d["project_name"] not in used_names:
            d["source"] = "daily_report"
            out.append(d)
    return out


def _derive_projects(reports, members):
    mmap = {m["id"]: m for m in members}
    by_id = defaultdict(lambda: {
        "dates": set(), "members": set(), "activities": [], "names": Counter(),
    })
    for r in reports:
        for name in r.get("projects") or []:
            if not name or name == "未分类":
                continue
            bucket = by_id[_slug(name)]
            bucket["names"][name] += 1
            bucket["dates"].add(r["report_date"])
            bucket["members"].add(r["member_id"])
            bucket["activities"].append({
                "date": r["report_date"],
                "member_id": r["member_id"],
                "activity_type": r.get("activity_type") or "其他",
                "difficulty": r.get("difficulty") or 3,
            })
    projects = []
    for pid, b in by_id.items():
        dates = sorted(b["dates"])
        if len(dates) < 2 and len(b["activities"]) < 3:
            continue
        name = b["names"].most_common(1)[0][0]
        members_info = [
            {"id": mid, "name": (mmap.get(mid) or {}).get("name") or mid}
            for mid in b["members"] if mid
        ]
        counts = defaultdict(int)
        for a in b["activities"]:
            counts[a["member_id"]] += 1
        owner_id = max(counts, key=counts.get) if counts else None
        projects.append({
            "project_id": pid,
            "project_name": name,
            "owner_id": owner_id,
            "members": members_info,
            "start_date": dates[0] if dates else None,
            "last_date": dates[-1] if dates else None,
            "active_days": len(dates),
            "activities": b["activities"],
        })
    projects.sort(key=lambda p: p["active_days"], reverse=True)
    return projects
