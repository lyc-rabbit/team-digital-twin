"""态势分析流水线：采集 → 校验 → 指标 → 变化/风险 → LLM → 落库。"""

import threading
from datetime import datetime

from . import repository as repo
from .collectors import collect_snapshot
from .metrics import compute_member_metrics, compute_project_metrics, compute_health
from .detectors import detect
from . import analyzer as llm_analyzer


_lock = threading.Lock()


def get_status():
    job = repo.get_running_job() or repo.get_job()
    if not job:
        return {"status": "idle", "progress": 0, "current_step": "", "message": "尚未分析"}
    return {
        "status": job.get("status"),
        "progress": job.get("progress") or 0,
        "current_step": job.get("current_step") or "",
        "message": job.get("current_step") or job.get("error_message") or "",
        "task_id": job.get("id"),
        "report_date": job.get("report_date"),
        "error_message": job.get("error_message"),
        "started_at": job.get("started_at"),
        "finished_at": job.get("finished_at"),
    }


def start_analyze(idempotency_key=None, trigger="manual"):
    today = datetime.now().strftime("%Y-%m-%d")
    key = (idempotency_key or "").strip() or f"manual-{today}"
    with _lock:
        running = repo.get_running_job()
        if running:
            return {
                "status": "running",
                "task_id": running["id"],
                "progress": running.get("progress") or 0,
                "current_step": running.get("current_step"),
                "message": "已有态势分析任务正在执行",
            }
        if key:
            existed = repo.find_job_by_key(key, today)
            if existed and existed.get("status") == "running":
                return {
                    "status": "running",
                    "task_id": existed["id"],
                    "progress": existed.get("progress") or 0,
                    "current_step": existed.get("current_step"),
                    "message": "相同请求已受理，避免重复生成报告",
                    "report_date": today,
                }
        job = repo.create_job(today, key, trigger)
    thread = threading.Thread(target=_run, args=(job["id"], today, trigger), daemon=True)
    thread.start()
    return {
        "status": "running",
        "task_id": job["id"],
        "progress": 2,
        "current_step": "数据采集",
        "message": "分析任务已启动",
    }


def _run(job_id, report_date, trigger):
    try:
        repo.update_job(job_id, progress=8, current_step="数据采集")
        snapshot = collect_snapshot(days=90)
        repo.update_job(job_id, progress=22, current_step="数据校验")
        members = snapshot.get("members") or []
        reports = snapshot.get("daily_reports") or []
        if not members:
            raise ValueError("计入团队的人员为空，请先勾选团队人员后再分析")
        weights = repo.get_config()
        repo.update_job(job_id, progress=40, current_step="趋势计算")
        raw_projects = snapshot.get("projects") or []
        pc_projects = [p for p in raw_projects if p.get("source") == "project_center"]
        member_rows = [compute_member_metrics(m, snapshot) for m in members]
        project_rows = [compute_project_metrics(p, report_date) for p in (pc_projects or raw_projects)]
        health = compute_health(member_rows, project_rows, snapshot, weights)
        repo.update_job(job_id, progress=58, current_step="异常检测")
        detected = detect(member_rows, project_rows, snapshot, health)
        repo.update_job(job_id, progress=72, current_step="AI分析")
        llm = llm_analyzer.analyze({
            "health": health,
            "members": member_rows,
            "projects": project_rows,
            "changes": detected["changes"],
            "risks": detected["risks"],
            "questions": detected["questions"],
            "attention_items": detected.get("attention_items") or [],
            "resource_conflicts": detected.get("resource_conflicts") or [],
            "project_stats": detected.get("project_stats") or {},
            "manual_context": snapshot.get("manual_context") or [],
        })
        repo.update_job(job_id, progress=88, current_step="报告生成")
        insight_by_pid = {i.get("project_id"): i for i in llm.get("project_insights") or []}
        for p in project_rows:
            ins = insight_by_pid.get(p["project_id"])
            if ins and not p.get("summary"):
                p["summary"] = ins.get("summary") or ins.get("fact") or ""
        report = repo.save_report({
            "report_date": report_date,
            "team_health_score": health["team_health_score"],
            "team_status": health["team_status"],
            "project_score": health["project_score"],
            "member_score": health["member_score"],
            "task_score": health["task_score"],
            "collaboration_score": health["collaboration_score"],
            "summary": llm.get("summary") or "；".join(health.get("reasons") or []),
            "llm_json": llm,
            "weights": {
                "project_weight": weights.get("project_weight"),
                "member_weight": weights.get("member_weight"),
                "task_weight": weights.get("task_weight"),
                "collab_weight": weights.get("collab_weight"),
            },
            "snapshot_meta": {
                "member_count": len(members),
                "report_count": len(reports),
                "project_count": len(project_rows),
                "degraded": llm.get("degraded"),
                "health_reasons": health.get("reasons"),
                "included_member_ids": [m["id"] for m in members],
                "included_member_names": [m.get("name") for m in members],
                "scoped": bool(weights.get("included_member_ids")),
                "attention_items": detected.get("attention_items") or [],
                "resource_conflicts": detected.get("resource_conflicts") or [],
                "project_stats": detected.get("project_stats") or {},
                "member_status": detected.get("member_status") or health.get("team_status"),
                "project_status": detected.get("project_status") or health.get("team_status"),
            },
            "trigger": trigger,
            "members": member_rows,
            "projects": project_rows,
            "risks": detected["risks"],
            "changes": detected["changes"],
            "questions": llm.get("questions") or detected["questions"],
        })
        repo.update_job(
            job_id, status="success", progress=100, current_step="今日分析完成",
            finished_at=datetime.now().isoformat(timespec="seconds"),
        )
        print(f"[situation] 报告已生成 {report_date} id={report['id']} score={health['team_health_score']}")
    except Exception as e:
        repo.update_job(
            job_id, status="failed", current_step="失败",
            error_message=str(e),
            finished_at=datetime.now().isoformat(timespec="seconds"),
        )
        print(f"[situation] 分析失败: {e}")


def today_payload():
    today = datetime.now().strftime("%Y-%m-%d")
    report = repo.get_report_by_date(today) or repo.latest_report()
    job = get_status()
    cfg = repo.get_config()
    return {
        "report": report,
        "job": job,
        "is_today": bool(report and report.get("report_date") == today),
        "config": cfg,
        "server_time": datetime.now().isoformat(timespec="seconds"),
    }


def member_payload(member_id):
    report = repo.latest_report()
    if not report:
        return None
    row = next((m for m in report.get("members") or [] if m["member_id"] == member_id), None)
    if not row:
        return None
    related = [c for c in report.get("changes") or [] if c.get("object_id") == member_id]
    risks = [r for r in report.get("risks") or [] if r.get("object_id") == member_id]
    return {"report_date": report["report_date"], "member": row, "changes": related, "risks": risks}


def project_payload(project_id):
    report = repo.latest_report()
    if not report:
        return None
    row = next((p for p in report.get("projects") or [] if p["project_id"] == project_id), None)
    if not row:
        return None
    risks = [r for r in report.get("risks") or [] if r.get("object_id") == project_id]
    return {"report_date": report["report_date"], "project": row, "risks": risks}


def trends_payload(range_key="7d"):
    days = {"7d": 7, "30d": 30, "90d": 90}.get(range_key, 7)
    reports = repo.list_recent_reports(days)
    latest = repo.latest_report()
    health_series = [
        {"date": r["report_date"], "score": r.get("team_health_score"), "status": r.get("team_status")}
        for r in reports
    ]
    member_focus = []
    if latest:
        from database import get_member
        for m in latest.get("members") or []:
            mem = get_member(m["member_id"])
            member_focus.append({
                "name": (mem or {}).get("name") or m["member_id"],
                "member_id": m["member_id"],
                "d7": (m.get("work_focus") or {}).get("d7") or {},
                "d30": (m.get("work_focus") or {}).get("d30") or {},
                "delta": m.get("focus_change") or {},
                "workload": m.get("workload_score"),
            })
    project_trend = []
    if latest:
        project_trend = [
            {
                "project_id": p["project_id"],
                "name": p.get("project_name"),
                "progress": p.get("progress"),
                "risk_level": p.get("risk_level"),
                "stage": p.get("current_stage"),
                "previous_stage": p.get("previous_stage"),
                "health_trend": p.get("health_trend"),
                "status": p.get("project_status"),
                "days_since_update": (p.get("metrics") or {}).get("days_since_update"),
            }
            for p in latest.get("projects") or []
        ]
    llm = (latest or {}).get("llm_json") or {}
    meta = (latest or {}).get("snapshot_meta") or {}
    stats = meta.get("project_stats") or {}
    week = stats.get("week") or {}
    member_trend = {"dev": 0, "mgmt": 0, "collab": 0, "mentor": 0, "n": 0}
    if latest:
        for m in latest.get("members") or []:
            d7 = (m.get("work_focus") or {}).get("d7") or {}
            member_trend["dev"] += d7.get("技术开发") or 0
            member_trend["mgmt"] += (d7.get("项目管理") or 0) + (d7.get("沟通协调") or 0)
            member_trend["collab"] += d7.get("沟通协调") or 0
            member_trend["mentor"] += d7.get("新人培养") or 0
            member_trend["n"] += 1
        n = max(1, member_trend["n"])
        for k in ("dev", "mgmt", "collab", "mentor"):
            member_trend[k] = round(member_trend[k] / n, 1)
    load_avg = 0
    if latest and latest.get("members"):
        load_avg = round(
            sum(m.get("workload_score") or 0 for m in latest["members"]) / max(1, len(latest["members"])),
            1,
        )
    return {
        "range": range_key,
        "days": days,
        "health": health_series,
        "member_focus": member_focus,
        "projects": project_trend,
        "project_stats": stats,
        "member_trend": member_trend,
        "team": {
            "risk_count": len((latest or {}).get("risks") or []),
            "project_count": stats.get("total") or len((latest or {}).get("projects") or []),
            "collaboration_score": (latest or {}).get("collaboration_score"),
            "load_avg": load_avg,
            "resource_conflicts": len(meta.get("resource_conflicts") or []),
            "week_stage_advances": week.get("stage_advances"),
            "week_risks_added": week.get("risks_added"),
            "week_risks_resolved": week.get("risks_resolved"),
            "week_milestones_delayed": week.get("milestones_delayed"),
        },
        "ai_trends": llm.get("trends") or [],
        "ai_summary": llm.get("summary") or stats.get("summary"),
        "note": "项目事实来自项目中心；趋势来自每日态势快照对比（昨天/7天前 vs 今天）。",
    }
