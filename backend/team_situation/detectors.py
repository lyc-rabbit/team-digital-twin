"""规则 / 统计 / 变化检测。LLM 只解释，不发明风险。团队态势只读取项目中心事实。"""

from collections import defaultdict
import uuid

from timeutil import today as beijing_today


CHANGE_LABELS = {
    "member": "人员变化",
    "project": "项目变化",
    "duty": "职责变化",
    "resource": "资源变化",
    "collab": "协作变化",
    "risk": "风险变化",
    "role": "角色变化",
    "stage": "阶段变化",
    "milestone": "里程碑变化",
}

CATEGORY_LABEL = {
    "PROJECT": "项目风险",
    "PERSON": "人员风险",
    "RESOURCE": "资源风险",
    "COLLAB": "协作风险",
    "PROGRESS": "进度风险",
    "STRUCTURE": "结构风险",
}

HIGH_STAGE_HINTS = ("开发", "接入", "联调", "核心")
TEST_STAGE_HINTS = ("测试", "验收", "上线")


def _stars(score):
    n = max(1, min(5, round(abs(score) / 8)))
    return "★" * n + "☆" * (5 - n)


def _health_obj(health):
    if isinstance(health, dict):
        return health
    return {"status": health} if health else {}


def _health_status(health):
    return _health_obj(health).get("status")


def _health_score(health):
    return _health_obj(health).get("score")


def _by_id(items, key="project_id"):
    return {str(x.get(key)): x for x in (items or []) if x.get(key) is not None}


def _item_key(item):
    return str(item.get("id") or item.get("name") or item.get("title") or "")


def _member_name(snapshot, mid):
    for m in snapshot.get("members") or []:
        if m.get("id") == mid:
            return m.get("name") or mid
    return mid


def detect(member_rows, project_rows, snapshot, health):
    changes = []
    risks = []
    questions = []
    attention = []
    today = beijing_today()
    seq = 1

    def risk_id():
        nonlocal seq
        rid = f"R{today.replace('-', '')}{seq:03d}"
        seq += 1
        return rid

    def add_risk(**kwargs):
        item = {
            "risk_id": kwargs.pop("risk_id", None) or risk_id(),
            "status": "open",
            **kwargs,
        }
        item.setdefault("evidence", [])
        item.setdefault("confidence", 0.75)
        risks.append(item)
        return item

    def add_attention(priority, title, description, *, category, member_id=None, project_id=None, evidence=None, confidence=0.8):
        rid = risk_id()
        item = {
            "id": rid,
            "risk_id": rid,
            "priority": priority,
            "title": title,
            "description": description,
            "category": category,
            "member_id": member_id,
            "project_id": project_id,
            "evidence": evidence or [],
            "confidence": confidence,
        }
        attention.append(item)
        add_risk(
            risk_id=rid,
            type=f"ATTENTION_{category}",
            severity={"high": "high", "medium": "medium"}.get(priority, "attention"),
            object_type="project" if project_id and not member_id else ("member" if member_id else "team"),
            object_id=project_id or member_id or "team",
            title=title,
            description=description,
            evidence=evidence or [],
            confidence=confidence,
            category=category,
            attention=True,
            member_id=member_id,
            project_id=project_id,
        )
        return item

    prev = snapshot.get("prev_report") or {}
    week_ago = snapshot.get("week_ago_report") or {}
    prev_projects = _by_id(prev.get("projects"))
    week_projects = _by_id(week_ago.get("projects"))
    prev_members = _by_id(prev.get("members"), "member_id")

    _detect_member_changes(member_rows, prev_members, snapshot, changes, add_risk, questions)
    conflicts = _detect_resource_conflicts(member_rows, project_rows, add_risk, add_attention, changes)
    _detect_project_changes(project_rows, prev_projects, week_projects, snapshot, changes, add_risk, add_attention)
    _detect_person_project_link(member_rows, project_rows, snapshot, add_risk, add_attention, questions)
    _detect_collab_and_structure(member_rows, project_rows, snapshot, add_risk, add_attention, changes)
    _detect_newcomers(snapshot, member_rows, add_attention)

    open_tasks = [t for t in snapshot.get("tasks") or [] if t.get("status") in ("todo", "in_progress", "blocked")]
    if len(open_tasks) >= 8:
        add_risk(
            type="TASK_BACKLOG",
            severity="attention",
            object_type="team",
            object_id="team",
            title="未完成培养/探索任务数量偏多",
            description=f"当前未完成任务 {len(open_tasks)} 项。",
            evidence=[f"open_tasks={len(open_tasks)}"],
            confidence=0.7,
            category="PROGRESS",
        )

    changes.sort(key=lambda c: c.get("change_score") or 0, reverse=True)
    project_stats = _project_stats(project_rows, prev_projects, week_projects, changes)
    member_status = health.get("team_status")
    high_load = sum(1 for m in member_rows if (m.get("workload_score") or 0) >= 85)
    if high_load or any((m.get("core_project_count") or 0) >= 3 for m in member_rows):
        member_status = "attention"
    if any((m.get("owned_projects") or []) and (m.get("core_project_count") or 0) >= 3 for m in member_rows):
        if high_load:
            member_status = "risk"
    project_status = health.get("team_status")
    if any(p.get("risk_level") == "high" for p in project_rows):
        project_status = "risk"
    elif any(p.get("risk_level") in ("attention", "medium") for p in project_rows):
        project_status = "attention"
    else:
        project_status = "normal"

    return {
        "changes": changes[:16],
        "risks": risks,
        "questions": questions,
        "health": health,
        "attention_items": attention,
        "resource_conflicts": conflicts,
        "project_stats": project_stats,
        "member_status": member_status or health.get("team_status"),
        "project_status": project_status,
    }


def _detect_member_changes(member_rows, prev_members, snapshot, changes, add_risk, questions):
    for m in member_rows:
        deltas = m.get("focus_change") or {}
        significant = {k: v for k, v in deltas.items() if abs(v) >= 10}
        days7 = m.get("report_days_7") or 0
        if significant:
            top = max(significant.items(), key=lambda x: abs(x[1]))
            conf = min(0.93, 0.5 + days7 * 0.06)
            desc = "；".join(
                f"{k} {v:+g}%" for k, v in sorted(significant.items(), key=lambda x: -abs(x[1]))[:4]
            )
            changes.append({
                "object_type": "member",
                "object_id": m["member_id"],
                "change_type": "duty",
                "change_label": "职责变化",
                "before_value": m.get("work_focus", {}).get("d30"),
                "after_value": m.get("work_focus", {}).get("d7"),
                "change_score": abs(top[1]),
                "stars": _stars(abs(top[1])),
                "title": f"{m.get('name')} 工作重心发生变化",
                "description": desc,
                "confidence": round(conf, 2),
                "evidence": [
                    f"近7天日报 {days7} 条",
                    f"近30天任务占比 vs 近7天：{desc}",
                ],
                "severity": "medium" if abs(top[1]) >= 18 else "attention",
            })
            if days7 < 3:
                questions.append({
                    "id": f"q_{uuid.uuid4().hex[:10]}",
                    "member_id": m["member_id"],
                    "question": (
                        f"{m.get('name')} 工作重心出现变化（{desc}），"
                        f"但近7天只有 {days7} 条日报，系统无法判断这是临时任务还是长期职责变化。"
                    ),
                })
        if (m.get("workload_score") or 0) >= 85:
            add_risk(
                type="HIGH_WORKLOAD",
                severity="high" if m["workload_score"] >= 92 else "medium",
                object_type="member",
                object_id=m["member_id"],
                title=f"{m.get('name')} 工作负载偏高",
                description=(
                    f"结构化负载 {m['workload_score']}（{m.get('workload_band')}），"
                    f"项目 {m.get('project_count')} 个，负责人 {len(m.get('owned_projects') or [])} 个。"
                    "未使用日报字数。"
                ),
                evidence=[
                    f"近7天出勤 {days7} 天",
                    f"并发项目 {m.get('project_count')}",
                    f"负责项目 {len(m.get('owned_projects') or [])}",
                    f"平均难度 {m.get('metrics', {}).get('avg_difficulty_7')}",
                ],
                confidence=0.84,
                category="PERSON",
            )
        if m.get("projects_added"):
            changes.append({
                "object_type": "member",
                "object_id": m["member_id"],
                "change_type": "project",
                "change_label": "项目变化",
                "before_value": m.get("projects_exited"),
                "after_value": m.get("projects_added"),
                "change_score": 12 * len(m["projects_added"]),
                "stars": _stars(12 * len(m["projects_added"])),
                "title": f"{m.get('name')} 新增项目投入",
                "description": "、".join(m["projects_added"]),
                "confidence": 0.8,
                "evidence": [f"近7天新增项目：{'、'.join(m['projects_added'])}"],
                "severity": "info",
            })
        if m.get("projects_exited"):
            changes.append({
                "object_type": "member",
                "object_id": m["member_id"],
                "change_type": "project",
                "change_label": "项目变化",
                "before_value": m.get("projects_exited"),
                "after_value": m.get("projects") or [],
                "change_score": 10 * len(m["projects_exited"]),
                "stars": _stars(10 * len(m["projects_exited"])),
                "title": f"{m.get('name')} 退出项目投入",
                "description": "、".join(m["projects_exited"]),
                "confidence": 0.72,
                "evidence": [f"近7天不再出现：{'、'.join(m['projects_exited'])}"],
                "severity": "info",
            })
        prev_m = prev_members.get(m["member_id"]) or {}
        prev_owned = set(prev_m.get("owned_projects") or [])
        now_owned = set(m.get("owned_projects") or [])
        new_owned = sorted(now_owned - prev_owned)
        for pname in new_owned:
            changes.append({
                "object_type": "member",
                "object_id": m["member_id"],
                "change_type": "duty",
                "change_label": "职责变化",
                "before_value": sorted(prev_owned),
                "after_value": sorted(now_owned),
                "change_score": 22,
                "stars": _stars(22),
                "title": f"{m.get('name')} 新增「{pname}」项目负责人职责",
                "description": "来自项目中心成员/负责人记录。",
                "confidence": 0.92,
                "evidence": [f"项目中心：{m.get('name')} 现为 {pname} 负责人"],
                "severity": "attention",
                "project_name": pname,
            })
        if (m.get("core_project_count") or 0) >= 3 and not (m.get("owned_projects") or []):
            add_risk(
                type="MULTI_PROJECT",
                severity="attention",
                object_type="member",
                object_id=m["member_id"],
                title=f"{m.get('name')} 同时承担 {m['core_project_count']} 个核心项目",
                description="多项目并行可能造成上下文切换成本上升。",
                evidence=[f"项目中心：{'、'.join(m.get('projects') or [])}"],
                confidence=0.78,
                category="PERSON",
            )
        for rel in m.get("collab_signals") or []:
            pair = rel.get("pair") or ""
            other = pair.replace(f"{m['member_id']}→", "").replace(f"→{m['member_id']}", "")
            other_name = _member_name(snapshot, other)
            if abs(rel.get("trust") or 0) >= 7 or abs(rel.get("sentiment") or 0) >= 7:
                changes.append({
                    "object_type": "member",
                    "object_id": m["member_id"],
                    "change_type": "collab",
                    "change_label": "协作变化",
                    "before_value": None,
                    "after_value": pair,
                    "change_score": max(abs(rel.get("trust") or 0), abs(rel.get("sentiment") or 0)),
                    "stars": _stars(16),
                    "title": f"{m.get('name')} 与 {other_name} 近期协作信号较强",
                    "description": f"关系网 trust={rel.get('trust')} sentiment={rel.get('sentiment')}",
                    "confidence": 0.7,
                    "evidence": [f"人际关系网 {pair} tag={rel.get('tag')}"],
                    "severity": "info",
                })
                break
        cards = m.get("role_cards") or []
        if cards:
            top = max(cards, key=lambda c: float(c.get("match_score") or 0))
            if float(top.get("match_score") or 0) >= 70:
                m["role_change"] = m.get("role_change") or f"角色卡倾向：{top.get('role_name')}"
        m["risk_level"] = "risk" if (m.get("workload_score") or 0) >= 85 else (
            "attention" if significant or (m.get("core_project_count") or 0) >= 3 or (m.get("project_count") or 0) >= 3 else "normal"
        )
        if not m.get("role_change"):
            m["role_change"] = ""
            if significant:
                topk = max(significant.items(), key=lambda x: x[1])
                if topk[1] > 0:
                    m["role_change"] = f"{topk[0]}倾向 ↑"
        m["confidence"] = min(0.92, 0.4 + days7 * 0.07)


def _detect_resource_conflicts(member_rows, project_rows, add_risk, add_attention, changes):
    conflicts = []
    active = [
        p for p in project_rows
        if p.get("source") == "project_center"
        and p.get("project_status") not in ("archived", "draft", "completed", "closed")
    ]
    for m in member_rows:
        owned = [p for p in active if p.get("owner_id") == m["member_id"]]
        core = [p for p in owned if p.get("priority") in ("P0", "P1") or p.get("project_status") in ("active", "open")]
        if len(owned) >= 3 or (len(core) >= 2 and len(owned) >= 2):
            names = [p.get("project_name") for p in owned]
            title = f"{m.get('name')}同时承担{len(owned)}个核心项目，存在负责人资源冲突"
            desc = "、".join(names)
            high_stage = [
                p for p in owned
                if any(h in (p.get("current_stage") or "") for h in HIGH_STAGE_HINTS)
            ]
            extra = ""
            if len(high_stage) >= 2:
                extra = f"{'与'.join(p.get('project_name') for p in high_stage[:2])}当前处于高投入阶段，存在资源竞争。"
            item = {
                "member_id": m["member_id"],
                "name": m.get("name"),
                "projects": names,
                "count": len(owned),
                "high_stage": [p.get("project_name") for p in high_stage],
            }
            conflicts.append(item)
            add_risk(
                type="OWNER_CONCENTRATION",
                severity="high" if len(owned) >= 3 else "medium",
                object_type="member",
                object_id=m["member_id"],
                title=title,
                description=f"{desc}。{extra}".strip(),
                evidence=[f"项目中心负责人：{desc}", extra or "同一人承担多个进行中项目"],
                confidence=0.9,
                category="RESOURCE",
            )
            add_attention(
                "high" if len(owned) >= 3 else "medium",
                title,
                f"{desc}。建议检查是否需要重新分配负责人。{extra}",
                category="STRUCTURE",
                member_id=m["member_id"],
                project_id=(owned[0].get("project_id") if owned else None),
                evidence=[f"负责人项目数 {len(owned)}", desc],
                confidence=0.9,
            )
            changes.append({
                "object_type": "member",
                "object_id": m["member_id"],
                "change_type": "resource",
                "change_label": "资源变化",
                "before_value": None,
                "after_value": names,
                "change_score": 18 + len(owned) * 4,
                "stars": _stars(24),
                "title": "团队出现资源集中",
                "description": f"{m.get('name')}当前同时承担{len(owned)}个核心项目负责人职责。",
                "confidence": 0.9,
                "evidence": [desc],
                "severity": "high" if len(owned) >= 3 else "attention",
            })
        p0s = [p for p in active if p.get("priority") in ("P0", "P1") and (
            p.get("owner_id") == m["member_id"]
            or any(r.get("id") == m["member_id"] and r.get("participation_level") == "核心" for r in (p.get("member_roles") or []))
        )]
        if len(p0s) >= 2 and m["member_id"] not in {c["member_id"] for c in conflicts}:
            add_risk(
                type="P0_CONTENTION",
                severity="medium",
                object_type="member",
                object_id=m["member_id"],
                title=f"多个高优先级项目竞争 {m.get('name')}",
                description="、".join(p.get("project_name") for p in p0s),
                evidence=[f"{p.get('project_name')} {p.get('priority')}" for p in p0s],
                confidence=0.82,
                category="RESOURCE",
            )
    return conflicts


def _detect_project_changes(project_rows, prev_projects, week_projects, snapshot, changes, add_risk, add_attention):
    for p in project_rows:
        pid = p["project_id"]
        prev = prev_projects.get(pid) or {}
        week = week_projects.get(pid) or {}
        recent = []
        prev_stage = prev.get("current_stage") or (week.get("current_stage") if week else None)
        p["previous_stage"] = prev_stage
        p["health_trend"] = "flat"
        cur_h = _health_score(p.get("health"))
        prev_h = _health_score(prev.get("health") or (prev.get("metrics") or {}).get("health"))
        if cur_h is not None and prev_h is not None:
            if cur_h < prev_h - 1.5:
                p["health_trend"] = "down"
                recent.append("↓ 健康度下降")
                add_attention(
                    "medium",
                    f"{p.get('project_name')}项目健康度连续下降，建议关注",
                    f"项目中心健康度 {prev_h} → {cur_h}。团队态势按历史变化判断，不重新维护健康分。",
                    category="PROGRESS",
                    project_id=pid,
                    evidence=[f"健康度 {prev_h} → {cur_h}"],
                    confidence=0.86,
                )
            elif cur_h > prev_h + 1.5:
                p["health_trend"] = "up"
                recent.append("↑ 健康度回升")

        if prev_stage and p.get("current_stage") and prev_stage != p.get("current_stage"):
            recent.append("↑ 阶段推进")
            changes.append({
                "object_type": "project",
                "object_id": pid,
                "change_type": "stage",
                "change_label": "项目变化",
                "before_value": prev_stage,
                "after_value": p.get("current_stage"),
                "change_score": 26,
                "stars": _stars(26),
                "title": f"{p.get('project_name')}进入新阶段",
                "description": f"项目中心记录该项目已从「{prev_stage}」进入「{p.get('current_stage')}」。",
                "confidence": 0.95,
                "evidence": ["阶段变化来自项目中心，不是日报推断"],
                "severity": "attention",
            })

        prev_status = prev.get("project_status") or (prev.get("metrics") or {}).get("project_status")
        if prev_status and p.get("project_status") and prev_status != p.get("project_status"):
            recent.append(f"状态 {prev_status} → {p.get('project_status')}")
            changes.append({
                "object_type": "project",
                "object_id": pid,
                "change_type": "project",
                "change_label": "项目变化",
                "before_value": prev_status,
                "after_value": p.get("project_status"),
                "change_score": 20,
                "stars": _stars(20),
                "title": f"{p.get('project_name')} 项目状态变化",
                "description": f"{prev_status} → {p.get('project_status')}",
                "confidence": 0.95,
                "evidence": ["来自项目中心状态字段"],
                "severity": "attention",
            })

        prev_owner = prev.get("owner_id") or (prev.get("metrics") or {}).get("owner_id")
        if prev_owner and p.get("owner_id") and prev_owner != p.get("owner_id"):
            recent.append("负责人变化")
            changes.append({
                "object_type": "project",
                "object_id": pid,
                "change_type": "duty",
                "change_label": "职责变化",
                "before_value": prev_owner,
                "after_value": p.get("owner_id"),
                "change_score": 18,
                "stars": _stars(18),
                "title": f"{p.get('project_name')} 负责人变化",
                "description": f"{_member_name(snapshot, prev_owner)} → {p.get('owner_name') or p.get('owner_id')}",
                "confidence": 0.93,
                "evidence": ["来自项目中心负责人"],
                "severity": "attention",
            })

        prev_ms = {_item_key(x): x for x in (prev.get("milestones") or (prev.get("metrics") or {}).get("milestones") or []) if _item_key(x)}
        now_ms = {_item_key(x): x for x in (p.get("milestones") or []) if _item_key(x)}
        for k, ms in now_ms.items():
            old = prev_ms.get(k)
            if not old:
                recent.append(f"新增里程碑 {ms.get('name')}")
            elif old.get("status") != ms.get("status"):
                label = {"completed": "完成", "delayed": "延期", "cancelled": "取消"}.get(ms.get("status"), ms.get("status"))
                recent.append(f"里程碑{label} {ms.get('name')}")
                if ms.get("status") == "delayed":
                    add_risk(
                        type="MILESTONE_DELAY",
                        severity="medium",
                        object_type="project",
                        object_id=pid,
                        title=f"{p.get('project_name')} 里程碑延期",
                        description=ms.get("name") or "",
                        evidence=[f"{ms.get('name')} {old.get('status')} → {ms.get('status')}"],
                        confidence=0.9,
                        category="PROGRESS",
                    )
        for k, ms in prev_ms.items():
            if k not in now_ms:
                recent.append(f"取消里程碑 {ms.get('name')}")

        prev_risks = {_item_key(x): x for x in (prev.get("open_risks") or (prev.get("metrics") or {}).get("open_risks") or []) if _item_key(x)}
        now_risks = {_item_key(x): x for x in (p.get("open_risks") or []) if _item_key(x)}
        added_risks = [x for k, x in now_risks.items() if k not in prev_risks]
        closed_risks = [x for k, x in prev_risks.items() if k not in now_risks]
        if added_risks:
            recent.append(f"新增风险 {len(added_risks)} 项")
            changes.append({
                "object_type": "project",
                "object_id": pid,
                "change_type": "risk",
                "change_label": "风险变化",
                "before_value": len(prev_risks),
                "after_value": len(now_risks),
                "change_score": 14 + 4 * len(added_risks),
                "stars": _stars(16),
                "title": f"{p.get('project_name')} 新增开放风险",
                "description": "、".join(x.get("title") or "" for x in added_risks[:3]),
                "confidence": 0.92,
                "evidence": ["来自项目中心开放风险"],
                "severity": "medium",
            })
        if closed_risks:
            recent.append(f"风险解除 {len(closed_risks)} 项")

        prev_people = {r.get("id") for r in (prev.get("member_roles") or (prev.get("metrics") or {}).get("member_roles") or []) if r.get("id")}
        now_people = {r.get("id") for r in (p.get("member_roles") or []) if r.get("id")}
        if p.get("owner_id"):
            now_people.add(p["owner_id"])
        if prev.get("owner_id"):
            prev_people.add(prev["owner_id"])
        joined = now_people - prev_people
        left = prev_people - now_people
        if joined:
            recent.append("人员增加")
        if left:
            recent.append("成员退出")
        if not joined and not left and now_people:
            recent.append("→ 人员稳定")

        if p.get("source") != "project_center":
            seen = set()
            uniq = []
            for x in recent:
                if x not in seen:
                    seen.add(x)
                    uniq.append(x)
            p["recent_changes"] = uniq[:6]
            continue

        for rsk in p.get("open_risks") or []:
            lvl = (rsk.get("level") or "").lower()
            if lvl in ("high", "高"):
                add_risk(
                    type="PC_OPEN_RISK",
                    severity="high",
                    object_type="project",
                    object_id=pid,
                    title=f"{p.get('project_name')}：{rsk.get('title')}",
                    description="项目中心开放风险，团队态势只读取不做项目管理。",
                    evidence=[f"level={rsk.get('level')} status={rsk.get('status')}"],
                    confidence=0.94,
                    category="PROJECT",
                )
                add_attention(
                    "medium",
                    f"{p.get('project_name')}关键风险尚未解除",
                    rsk.get("title") or "",
                    category="PROJECT",
                    project_id=pid,
                    evidence=[rsk.get("title") or ""],
                    confidence=0.9,
                )

        if p.get("schedule_status") == "stalled":
            add_risk(
                type="PROJECT_PAUSED",
                severity="attention",
                object_type="project",
                object_id=pid,
                title=f"{p.get('project_name')} 当前处于暂停",
                description="项目中心状态为暂停。",
                evidence=[f"project_status={p.get('project_status')}"],
                confidence=0.9,
                category="PROGRESS",
            )

        if p.get("bottleneck_member_id"):
            name = next(
                (x.get("name") for x in (p.get("members") or []) if x.get("id") == p["bottleneck_member_id"]),
                p["bottleneck_member_id"],
            )
            add_risk(
                type="PERSON_BOTTLENECK",
                severity="attention",
                object_type="project",
                object_id=pid,
                title=f"{p.get('project_name')} 存在人员瓶颈",
                description=f"核心项目过度依赖 {name}。",
                evidence=[f"主要投入人：{name}"],
                confidence=0.74,
                category="PERSON",
            )

        seen = set()
        uniq = []
        for x in recent:
            if x not in seen:
                seen.add(x)
                uniq.append(x)
        p["recent_changes"] = uniq[:6]


def _detect_person_project_link(member_rows, project_rows, snapshot, add_risk, add_attention, questions):
    by_name = {p.get("project_name"): p for p in project_rows}
    for m in member_rows:
        focus7 = (m.get("work_focus") or {}).get("d7") or {}
        for role in m.get("pc_roles") or []:
            proj = by_name.get(role.get("project_name"))
            if not proj:
                continue
            stage = proj.get("current_stage") or ""
            if any(h in stage for h in TEST_STAGE_HINTS) and (focus7.get("测试") or 0) < 8 and role.get("participation_level") in ("核心", "主要"):
                add_attention(
                    "medium",
                    f"{m.get('name')}主要参与{proj.get('project_name')}，但测试投入偏少",
                    f"项目中心当前阶段为「{stage}」，近7天日报测试类占比 {focus7.get('测试') or 0}%。",
                    category="PROGRESS",
                    member_id=m["member_id"],
                    project_id=proj.get("project_id"),
                    evidence=[f"阶段={stage}", f"测试占比={focus7.get('测试')}"],
                    confidence=0.7,
                )
            if role.get("role") == "负责人" and any(h in stage for h in HIGH_STAGE_HINTS):
                owned_high = [
                    r for r in (m.get("pc_roles") or [])
                    if r.get("role") == "负责人" and any(h in (r.get("stage") or "") for h in HIGH_STAGE_HINTS)
                ]
                if len(owned_high) >= 2:
                    add_risk(
                        type="SPAN_OF_CONTROL",
                        severity="medium",
                        object_type="member",
                        object_id=m["member_id"],
                        title=f"{m.get('name')}管理跨度过大",
                        description=(
                            f"承担{len([r for r in m.get('pc_roles') or [] if r.get('role') == '负责人'])}个项目负责人角色，"
                            f"其中{len(owned_high)}个同时进入高投入阶段。"
                        ),
                        evidence=[f"{r.get('project_name')} · {r.get('stage')}" for r in owned_high],
                        confidence=0.82,
                        category="STRUCTURE",
                    )
                    break


def _detect_collab_and_structure(member_rows, project_rows, snapshot, add_risk, add_attention, changes):
    neg = []
    for rel in snapshot.get("relationships") or []:
        if (rel.get("trust") or 0) <= -6 or (rel.get("sentiment") or 0) <= -6:
            neg.append(rel)
    if neg:
        pair = neg[0].get("pair")
        add_risk(
            type="COLLAB_TENSION",
            severity="attention",
            object_type="team",
            object_id="team",
            title="协作关系出现紧张信号",
            description=f"人际关系网 {pair} trust={neg[0].get('trust')} sentiment={neg[0].get('sentiment')}",
            evidence=[f"{r.get('pair')} trust={r.get('trust')} sentiment={r.get('sentiment')}" for r in neg[:4]],
            confidence=0.68,
            category="COLLAB",
        )


def _detect_newcomers(snapshot, member_rows, add_attention):
    try:
        from newcomer.repository import list_newcomers
        ncs = list_newcomers() or []
    except Exception:
        ncs = []
    included = {m["id"] for m in (snapshot.get("members") or [])}
    for nc in ncs:
        eid = nc.get("employee_id")
        if included and eid not in included:
            continue
        row = next((m for m in member_rows if m["member_id"] == eid), None)
        if not row:
            continue
        if (row.get("project_count") or 0) <= 1 and (row.get("report_days_7") or 0) <= 3:
            add_attention(
                "watch",
                f"{row.get('name')}近期开始参与项目，目前承担任务较少",
                "建议观察其是否已经形成稳定职责。",
                category="PERSON",
                member_id=eid,
                evidence=[f"近7天日报 {row.get('report_days_7')}", f"项目数 {row.get('project_count')}"],
                confidence=0.62,
            )


def _project_stats(project_rows, prev_projects, week_projects, changes):
    pc = [p for p in project_rows if p.get("source") == "project_center"]
    rows = pc or project_rows
    by_status = defaultdict(int)
    for p in rows:
        by_status[p.get("project_status") or "unknown"] += 1
    stage_adv = sum(1 for c in changes if c.get("change_type") == "stage")
    risks_added = 0
    risks_resolved = 0
    delayed_ms = 0
    for p in rows:
        prev = prev_projects.get(p["project_id"]) or week_projects.get(p["project_id"]) or {}
        prev_r = {
            _item_key(x) for x in (prev.get("open_risks") or (prev.get("metrics") or {}).get("open_risks") or [])
            if _item_key(x)
        }
        now_r = {_item_key(x) for x in (p.get("open_risks") or []) if _item_key(x)}
        risks_added += max(0, len(now_r - prev_r))
        risks_resolved += max(0, len(prev_r - now_r))
        delayed_ms += sum(1 for ms in (p.get("milestones") or []) if ms.get("status") == "delayed")
    open_n = by_status.get("open", 0) + by_status.get("active", 0) + by_status.get("planning", 0)
    paused_n = by_status.get("paused", 0)
    closed_n = by_status.get("closed", 0) + by_status.get("completed", 0) + by_status.get("archived", 0)
    summary_bits = []
    if risks_resolved > risks_added:
        summary_bits.append("风险解决速度高于风险产生速度")
    elif risks_added > risks_resolved:
        summary_bits.append("新增风险多于已解除风险")
    if stage_adv:
        summary_bits.append(f"完成阶段推进 {stage_adv} 次")
    if delayed_ms:
        summary_bits.append(f"{delayed_ms} 个延期里程碑")
    return {
        "total": len(rows),
        "open": open_n,
        "paused": paused_n,
        "closed": closed_n,
        "active": open_n,
        "completed": closed_n,
        "planning": by_status.get("planning", 0),
        "by_status": dict(by_status),
        "week": {
            "stage_advances": stage_adv,
            "risks_added": risks_added,
            "risks_resolved": risks_resolved,
            "milestones_delayed": delayed_ms,
        },
        "summary": "；".join(summary_bits) or "本周项目事实变化有限，需继续积累对比样本。",
    }
