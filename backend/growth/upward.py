"""向上协同 P1：信任/授权分析、汇报助手、协同风险。结论必须可解释。"""

from datetime import timedelta

from timeutil import now_naive

from database import get_all_members, get_member, get_daily_reports
from llm_client import get_client, is_mock_mode, _get_env, _log_llm_failure

from . import repository as repo
from .scores import pair_overview, score_detail, _parse_time
from .taxonomy import tag_label

UPWARD_DIMENSIONS = [
    ("professional_trust", "专业判断信任"),
    ("delivery_trust", "项目交付信任"),
    ("risk_trust", "风险处理信任"),
    ("autonomy_trust", "自主决策信任"),
    ("management_trust", "人员管理信任"),
]

AUTH_LEVELS = [
    {"id": "L0", "order": 0, "label": "领导直接决策", "meaning": "事项仍由上级拍板，你主要承接执行信息。"},
    {"id": "L1", "order": 1, "label": "你执行", "meaning": "上级给出方向，你负责落地执行并同步进展。"},
    {"id": "L2", "order": 2, "label": "你提出建议，领导决策", "meaning": "你可以给出方案和建议，最终决策仍在上级。"},
    {"id": "L3", "order": 3, "label": "你自主决策，领导知情", "meaning": "你可在范围内自主决策，事后或同步告知上级。"},
    {"id": "L4", "order": 4, "label": "完整领域授权", "meaning": "某方向/项目的完整决策责任已交给你。"},
]

EVENT_GROUPS = {
    "report": "汇报事件",
    "superior_decision": "决策事件",
    "superior_auth": "授权事件",
    "superior_feedback": "反馈事件",
    "superior_recognition": "上级评价",
    "superior_challenge": "上级评价",
    "resource_support": "资源支持",
    "project_delivery": "项目结果",
}

POSITIVE_RESULT_HINTS = ("完成", "通过", "认可", "成功", "独立", "提前", "良好", "达标")
NEGATIVE_RESULT_HINTS = ("失败", "延期", "滞后", "质疑", "未同步", "未经", "事故")
LOOKBACK_DAYS = 30


def _now():
    return now_naive()


def _days_ago(n):
    return _now() - timedelta(days=n)


def _in_window(event, since):
    t = _parse_time(event.get("event_time"))
    if not t:
        return True
    return t >= since


def _blob(event):
    extra = event.get("extra_fields") or {}
    return " ".join([
        event.get("background") or "",
        event.get("facts") or "",
        event.get("result") or "",
        event.get("judgement") or "",
        event.get("raw_summary") or "",
        extra.get("attempts") or "",
    ])


def _cite(event, text=None):
    return {
        "event_id": event.get("id"),
        "time": event.get("event_time"),
        "source": "event",
        "title": tag_label(event.get("event_type"), event.get("event_tag")) or event.get("scene") or "事件",
        "text": (text or event.get("result") or event.get("facts") or event.get("raw_summary") or "")[:220],
    }


def _judgment(conclusion, reason, evidence, source="rule"):
    times = [e.get("time") for e in (evidence or []) if e.get("time")]
    return {
        "conclusion": conclusion,
        "reason": reason,
        "evidence": evidence or [],
        "time": times[-1] if times else _now().isoformat(timespec="seconds"),
        "source": source,
    }


def _upward_events(person_id):
    events = repo.list_events({"member_id": person_id, "limit": 400})
    return [
        e for e in events
        if e.get("event_type") == "upward" or e.get("event_tag") in EVENT_GROUPS
    ]


def _all_person_events(person_id):
    return repo.list_events({"member_id": person_id, "limit": 400})


def _counterparty(event, person_id):
    related = event.get("related_persons") or []
    for pid in related:
        if pid and pid != person_id:
            return pid
    created = event.get("created_by")
    if created and created != person_id:
        return created
    for mid in event.get("involved_members") or []:
        if mid and mid != person_id:
            return mid
    return None


def _filter_pair(events, person_id, manager_id):
    if not manager_id:
        return events
    out = []
    for e in events:
        involved = e.get("involved_members") or []
        related = e.get("related_persons") or []
        if manager_id in involved or manager_id == e.get("created_by") or manager_id in related:
            out.append(e)
    return out


def _is_positive(event):
    blob = _blob(event)
    if any(h in blob for h in NEGATIVE_RESULT_HINTS):
        return False
    if any(h in blob for h in POSITIVE_RESULT_HINTS):
        return True
    tag = event.get("event_tag") or ""
    if tag in ("superior_challenge", "tech_failure", "trust_down", "comm_error"):
        return False
    if tag in ("superior_recognition", "superior_auth", "project_delivery", "tech_breakthrough"):
        return True
    return None


def _auth_from_events(events):
    """根据授权/决策类事件推断当前授权等级，并给出证据。"""
    tags = [e.get("event_tag") for e in events]
    evidence = []
    level = 0

    reports = [e for e in events if e.get("event_tag") == "report"]
    if reports:
        level = max(level, 1)
        evidence.append(_cite(reports[-1], "已出现向上汇报，说明你在执行并同步。"))

    suggest = [e for e in events if e.get("event_tag") in ("report", "superior_feedback") and (e.get("judgement") or e.get("actions"))]
    if suggest:
        level = max(level, 2)
        evidence.append(_cite(suggest[-1], "汇报中包含判断或建议，决策仍可能在上级。"))

    auth_events = [e for e in events if e.get("event_tag") in ("superior_auth", "empowerment", "authorization")]
    decisions = [
        e for e in events
        if e.get("event_tag") in ("tech_decision", "decision", "project_delivery", "superior_decision")
    ]
    good_decisions = [e for e in decisions if _is_positive(e) is not False]
    consecutive = 0
    for e in reversed(decisions[-8:]):
        if _is_positive(e) is False:
            break
        if _is_positive(e) is True or e.get("event_tag") in ("project_delivery", "tech_decision"):
            consecutive += 1
        else:
            break

    if auth_events or consecutive >= 3 or len(good_decisions) >= 3:
        level = max(level, 3)
        if auth_events:
            evidence.append(_cite(auth_events[-1], "出现上级授权/放权事件。"))
        if consecutive >= 3:
            evidence.append(_cite(decisions[-1], f"连续 {consecutive} 次项目/技术决策结果可核验为正向。"))
        elif good_decisions:
            evidence.append(_cite(good_decisions[-1], "多次决策或交付结果良好。"))

    support = [e for e in events if e.get("event_tag") == "resource_support"]
    if auth_events and support:
        level = max(level, 4)
        evidence.append(_cite(support[-1], "授权同时伴随资源支持，接近完整领域授权。"))
    elif "完整授权" in " ".join(_blob(e) for e in auth_events):
        level = max(level, 4)

    if not events:
        evidence = []
        level = 0

    spec = AUTH_LEVELS[min(level, 4)]
    if level >= 3 and consecutive >= 3 and level < 4:
        suggestion = "下一阶段可以主动争取完整项目推进授权。"
    elif level == 2:
        suggestion = "用一次可核验的自主决策结果（领导知情）验证能否升到 L3。"
    elif level <= 1:
        suggestion = "先保证阶段性同步，再在汇报中给出判断和建议，而不是只报进度。"
    else:
        suggestion = "保持决策结果可追溯，并明确责任与决策边界。"

    conclusion = f"当前授权等级 {spec['id']}：{spec['label']}"
    if consecutive >= 3:
        reason = f"连续 {consecutive} 次项目决策结果良好，授权判断上调。"
    elif auth_events:
        reason = "存在明确的上级授权/放权事件。"
    elif reports:
        reason = "已有执行与汇报，但完整自主决策证据仍有限。"
    else:
        reason = "尚无足够向上协同事件，默认视为领导直接决策。"

    return {
        "level": spec["id"],
        "order": spec["order"],
        "label": spec["label"],
        "meaning": spec["meaning"],
        "levels": AUTH_LEVELS,
        "consecutive_good_decisions": consecutive,
        "suggestion": suggestion,
        "judgment": _judgment(conclusion, reason, evidence[-5:]),
    }


def _dimension_judgment(detail):
    label = detail.get("dimension_label") or "信任"
    current = detail.get("current") or 50
    delta = detail.get("period_delta") or 0
    pos = detail.get("positive") or []
    neg = detail.get("negative") or []
    if delta > 0 and pos:
        reason = f"近{detail.get('period_days') or 7}天{label}上升 {delta} 分，主要来自 {len(pos)} 条正向证据。"
        conclusion = f"{label}正在增强"
    elif delta < 0 and neg:
        reason = f"近{detail.get('period_days') or 7}天{label}下降 {abs(delta)} 分，出现 {len(neg)} 条负向证据。"
        conclusion = f"{label}出现回落"
    elif not pos and not neg:
        reason = f"尚无足够事件证明{label}变化，分值停留在基线附近。"
        conclusion = f"{label}证据不足，暂维持观察"
    else:
        reason = f"{label}当前 {current}，近期变化有限。"
        conclusion = f"{label}相对稳定"
    evidence = []
    for x in (pos[:2] + neg[:2]):
        evidence.append({
            "event_id": x.get("event_id"),
            "time": x.get("event_time"),
            "source": "event",
            "title": x.get("event_title") or label,
            "text": x.get("reason") or "",
        })
    return _judgment(conclusion, reason, evidence)


def _detect_risks(person_id, manager_id, events, all_events, projects):
    risks = []
    since = _days_ago(LOOKBACK_DAYS)
    recent_all = [e for e in all_events if _in_window(e, since)]
    recent_up = [e for e in events if _in_window(e, since)]
    reports = [e for e in recent_up if e.get("event_tag") in ("report", "info_pass")]
    techish = [
        e for e in recent_all
        if e.get("event_type") in ("project", "communication")
        or e.get("event_tag") in ("tech_decision", "tech_breakthrough", "project_progress", "project_risk")
    ]

    # 风险一：信息差
    if len(techish) >= 3 and len(reports) == 0:
        risks.append({
            "id": "info_gap",
            "title": "上级近期获得信息不足",
            "severity": "high",
            "suggestion": "增加阶段性同步，把关键技术进展改写成上级可决策的事实。",
            "judgment": _judgment(
                "你掌握大量技术/项目信息，但上级近期获得信息不足。",
                f"近{LOOKBACK_DAYS}天有 {len(techish)} 条项目或技术事实，同期向上汇报/同步仅 {len(reports)} 条。",
                [_cite(e) for e in techish[-3:]],
            ),
        })
    elif len(techish) >= 4 and len(reports) < 2:
        risks.append({
            "id": "info_gap",
            "title": "同步频率偏低",
            "severity": "medium",
            "suggestion": "建立固定节奏的进展同步，避免信息堆到出问题才上报。",
            "judgment": _judgment(
                "项目事实多于向上同步。",
                f"近{LOOKBACK_DAYS}天项目/技术事件 {len(techish)} 条，汇报 {len(reports)} 条。",
                [_cite(e) for e in (techish[-2:] + reports[-1:])],
            ),
        })

    # 风险二：风险未提前沟通
    risk_events = [
        e for e in recent_all
        if e.get("event_tag") in ("project_risk", "tech_failure", "risk_escalate")
        or "风险" in _blob(e)
    ]
    escalated = [e for e in recent_up if e.get("event_tag") in ("risk_escalate", "report") and "风险" in _blob(e)]
    unannounced = []
    for e in risk_events:
        t = _parse_time(e.get("event_time"))
        prior = False
        for r in escalated + reports:
            rt = _parse_time(r.get("event_time"))
            if t and rt and rt <= t and r.get("id") != e.get("id"):
                prior = True
                break
        if not prior and e.get("event_tag") != "risk_escalate":
            unannounced.append(e)
    if len(unannounced) >= 2:
        risks.append({
            "id": "late_risk",
            "title": "项目风险未提前同步",
            "severity": "high",
            "suggestion": "提前建立风险同步机制：发现风险的当天先同步事实、影响和已尝试，再谈方案。",
            "judgment": _judgment(
                "近期连续出现未经提前沟通的项目风险。",
                f"近{LOOKBACK_DAYS}天识别到 {len(unannounced)} 次风险相关事件，缺少事先向上同步。",
                [_cite(e) for e in unannounced[-3:]],
            ),
        })
    elif len(unannounced) == 1:
        risks.append({
            "id": "late_risk",
            "title": "存在一次风险后置同步",
            "severity": "medium",
            "suggestion": "下一次风险先报事实和影响，再讨论处理。",
            "judgment": _judgment(
                "出现风险事件时，上级可能没有提前知情。",
                "该风险事件前后缺少对应的向上汇报。",
                [_cite(unannounced[0])],
            ),
        })

    # 风险三：责任增加但授权未同步
    owned = [p for p in projects if p.get("owner_id") == person_id]
    open_owned = [p for p in owned if (p.get("status") or "open") == "open"]
    mgmt_events = [
        e for e in recent_all
        if e.get("event_type") == "management"
        or e.get("event_tag") in ("task_assignment", "decision", "coordination", "institution")
    ]
    auth = _auth_from_events(events)
    if (open_owned or len(mgmt_events) >= 2) and auth["order"] <= 1:
        cites = [_cite(e) for e in (mgmt_events[-2:] or events[-1:])]
        for p in open_owned[:2]:
            cites.append({
                "event_id": None,
                "time": p.get("updated_at") or p.get("created_at"),
                "source": "project",
                "title": p.get("name") or "项目",
                "text": f"项目负责人：{p.get('name')}，状态 {p.get('status_label') or p.get('status')}",
            })
        risks.append({
            "id": "auth_mismatch",
            "title": "责任与授权不匹配",
            "severity": "high" if open_owned else "medium",
            "suggestion": "与上级确认责任与决策边界：哪些事项可自主决策，哪些必须事先请示。",
            "judgment": _judgment(
                "你承担责任增加，但授权没有同步增加。",
                f"当前授权 {auth['level']}（{auth['label']}），同时是 {len(open_owned)} 个开启项目的负责人，近{LOOKBACK_DAYS}天管理事件 {len(mgmt_events)} 条。",
                cites[:5],
            ),
        })

    if not risks:
        risks.append({
            "id": "none",
            "title": "暂无明显向上协同风险",
            "severity": "low",
            "suggestion": "保持现有同步节奏，继续用事件留下可核验事实。",
            "judgment": _judgment(
                "近窗口内未触发信息差、滞后风险或权责错配规则。",
                f"近{LOOKBACK_DAYS}天向上事件 {len(recent_up)} 条，项目/技术事实 {len(techish)} 条。",
                [_cite(e) for e in recent_up[-2:]],
            ),
        })
    return risks


def _person_projects(person_id):
    try:
        from project_center.repository import list_projects
        return list_projects({"include_archived": True, "member_id": person_id}) or []
    except Exception:
        return []


def build_archive(person_id, manager_id=None):
    member = get_member(person_id)
    if not member:
        return None
    mmap = {m["id"]: m for m in get_all_members()}
    all_events = _all_person_events(person_id)
    events = _upward_events(person_id)
    counterparts = {}
    for e in events:
        other = _counterparty(e, person_id)
        if other:
            counterparts[other] = counterparts.get(other, 0) + 1
    if not manager_id:
        manager_id = max(counterparts, key=counterparts.get) if counterparts else None
    pair_events = _filter_pair(events, person_id, manager_id)

    grouped = {label: [] for label in dict.fromkeys(EVENT_GROUPS.values())}
    grouped.setdefault("项目结果", [])
    grouped.setdefault("上级评价", [])
    for e in pair_events:
        label = EVENT_GROUPS.get(e.get("event_tag")) or "汇报事件"
        grouped.setdefault(label, []).append({
            "id": e["id"],
            "event_time": e.get("event_time"),
            "title": tag_label(e.get("event_type"), e.get("event_tag")),
            "summary": (e.get("raw_summary") or "")[:160],
            "result": e.get("result") or "",
            "judgement": e.get("judgement") or "",
            "event_type": e.get("event_type"),
            "event_tag": e.get("event_tag"),
        })

    dimensions = []
    if manager_id:
        overview = pair_overview(manager_id, person_id)
        by_id = {d["id"]: d for d in overview.get("dimensions") or []}
        for dim, label in UPWARD_DIMENSIONS:
            d = by_id.get(dim) or {"id": dim, "current": 50, "period_delta": 0, "trend": "flat"}
            detail = score_detail(manager_id, person_id, dim)
            detail["dimension_label"] = label
            dimensions.append({
                "id": dim,
                "label": label,
                "current": d.get("current") or 50,
                "period_delta": d.get("period_delta") or 0,
                "trend": d.get("trend") or "flat",
                "positive": (detail.get("positive") or [])[:5],
                "negative": (detail.get("negative") or [])[:5],
                "judgment": _dimension_judgment(detail),
            })

    projects = _person_projects(person_id)
    authorization = _auth_from_events(pair_events)
    risks = _detect_risks(person_id, manager_id, pair_events, all_events, projects)
    manager = mmap.get(manager_id) if manager_id else None

    return {
        "person_id": person_id,
        "name": member.get("name"),
        "role": member.get("role"),
        "manager_id": manager_id,
        "manager_name": (manager or {}).get("name"),
        "managers": [
            {"id": mid, "name": (mmap.get(mid) or {}).get("name") or mid, "event_count": n}
            for mid, n in sorted(counterparts.items(), key=lambda x: -x[1])
        ],
        "groups": grouped,
        "dimensions": dimensions,
        "authorization": authorization,
        "risks": risks,
        "event_count": len(pair_events),
        "lookback_days": LOOKBACK_DAYS,
        "projects": [
            {
                "id": p.get("id"),
                "name": p.get("name"),
                "status": p.get("status"),
                "owner_id": p.get("owner_id"),
                "is_owner": p.get("owner_id") == person_id,
                "open_risk_count": p.get("open_risk_count") or 0,
                "current_stage": (p.get("current_stage") or {}).get("name"),
            }
            for p in projects[:20]
        ],
    }


def collect_report_facts(person_id, manager_id=None, project_id=None, extra_notes=""):
    """只收集已有事实，不编造。"""
    member = get_member(person_id) or {}
    mmap = {m["id"]: m for m in get_all_members()}
    archive = build_archive(person_id, manager_id)
    manager_id = (archive or {}).get("manager_id")
    facts = []

    projects = _person_projects(person_id)
    if project_id:
        projects = [p for p in projects if p.get("id") == project_id]
        if not projects:
            try:
                from project_center.repository import get_project
                one = get_project(project_id)
                if one:
                    projects = [one]
            except Exception:
                pass

    for p in projects[:8]:
        stage = (p.get("current_stage") or {}).get("name") or "未知阶段"
        facts.append({
            "source": "project",
            "source_id": p.get("id"),
            "time": p.get("updated_at") or p.get("created_at"),
            "text": f"项目「{p.get('name')}」状态 {p.get('status_label') or p.get('status')}，当前阶段 {stage}。",
        })
        for r in (p.get("risks") or [])[:5]:
            if (r.get("status") or "open") in ("closed", "resolved", "关闭", "已关闭"):
                continue
            facts.append({
                "source": "project_risk",
                "source_id": r.get("id"),
                "time": r.get("created_at"),
                "text": f"项目「{p.get('name')}」开放风险：{r.get('title') or r.get('description') or '未命名风险'}（{r.get('level') or r.get('status') or ''}）。",
            })

    events = _filter_pair(_upward_events(person_id) or [], person_id, manager_id)
    if project_id:
        related = repo.list_events({"member_id": person_id, "project_id": project_id, "limit": 80})
        seen = {e.get("id") for e in events}
        for e in related:
            if e.get("id") not in seen:
                events.append(e)
    for e in events[:20]:
        text = (e.get("facts") or e.get("result") or e.get("raw_summary") or "").strip()
        if not text:
            continue
        facts.append({
            "source": "event",
            "source_id": e.get("id"),
            "time": e.get("event_time"),
            "text": f"[{tag_label(e.get('event_type'), e.get('event_tag'))}] {text[:200]}",
        })

    try:
        reports = get_daily_reports(member_id=person_id, limit=12)
    except Exception:
        reports = []
    for r in reports:
        content = (r.get("content") or "").strip()
        if not content:
            continue
        facts.append({
            "source": "daily_report",
            "source_id": r.get("id"),
            "time": r.get("report_date"),
            "text": f"日报 {r.get('report_date')}：{content[:180]}",
        })

    notes = (extra_notes or "").strip()
    if notes:
        facts.append({
            "source": "manual",
            "source_id": None,
            "time": _now().isoformat(timespec="seconds"),
            "text": notes,
        })

    return {
        "person_id": person_id,
        "person_name": member.get("name") or person_id,
        "manager_id": manager_id,
        "manager_name": (mmap.get(manager_id) or {}).get("name") if manager_id else None,
        "project_id": project_id,
        "facts": facts,
        "fact_count": len(facts),
    }


REPORT_SECTIONS = [
    ("background", "背景"),
    ("status", "当前状态"),
    ("facts", "关键事实"),
    ("risks", "主要风险"),
    ("judgment", "我的判断"),
    ("options", "建议方案"),
    ("decisions", "需要领导决策事项"),
    ("next_steps", "下一步"),
]


def _empty_section(key, label):
    return {
        "id": key,
        "label": label,
        "text": "事实不足，未写入。",
        "sources": [],
    }


def _template_report(pack):
    facts = pack.get("facts") or []
    by_src = {}
    for f in facts:
        by_src.setdefault(f.get("source"), []).append(f)

    def join(items, empty="事实不足，未写入。"):
        if not items:
            return empty, []
        return "\n".join(f"- {x['text']}" for x in items[:8]), items[:8]

    bg_items = (by_src.get("project") or [])[:3] + (by_src.get("manual") or [])[:1]
    st_items = by_src.get("project") or []
    fact_items = [f for f in facts if f.get("source") in ("event", "daily_report", "project")][:8]
    risk_items = by_src.get("project_risk") or [f for f in facts if "风险" in (f.get("text") or "")]
    judge_items = [f for f in facts if f.get("source") == "event" and ("判断" in f.get("text") or "建议" in f.get("text"))]

    mapping = {
        "background": join(bg_items),
        "status": join(st_items),
        "facts": join(fact_items),
        "risks": join(risk_items),
        "judgment": join(judge_items, "给定事实中没有单独标注的判断，未写入。"),
        "options": ("给定事实中没有明确的备选方案，未写入。", []),
        "decisions": ("给定事实中没有明确的待决策事项，未写入。", []),
        "next_steps": join((by_src.get("manual") or [])[-1:], "给定事实中没有明确下一步，未写入。"),
    }
    sections = []
    for key, label in REPORT_SECTIONS:
        text, srcs = mapping.get(key) or ("事实不足，未写入。", [])
        sections.append({"id": key, "label": label, "text": text, "sources": srcs})
    return sections


def _llm_report(pack):
    import json
    if is_mock_mode():
        return _template_report(pack), True
    lines = []
    for i, f in enumerate(pack.get("facts") or [], 1):
        lines.append(f"{i}. [{f.get('source')}|{f.get('time') or ''}] {f.get('text')}")
    if not lines:
        return _template_report(pack), True
    prompt = f"""你是向上汇报起草助手。只能重组下面已给出的事实，禁止编造任何项目、风险、数字或结论。
若某段落没有对应事实，必须写「事实不足，未写入。」
汇报人：{pack.get('person_name')}
上级：{pack.get('manager_name') or '未指定'}

【已核验事实】
{chr(10).join(lines)}

输出 JSON：
{{
  "background": "背景",
  "status": "当前状态",
  "facts": "关键事实",
  "risks": "主要风险",
  "judgment": "我的判断（只能来自事实中已有判断，否则写事实不足）",
  "options": "建议方案（只能来自事实，否则写事实不足）",
  "decisions": "需要领导决策事项（只能来自事实，否则写事实不足）",
  "next_steps": "下一步"
}}"""
    try:
        client = get_client()
        if client is None:
            raise ValueError("LLM 未初始化")
        response = client.chat.completions.create(
            model=_get_env("DEEPSEEK_MODEL_EXTRACT", "deepseek-ai/DeepSeek-V3"),
            messages=[
                {"role": "system", "content": "只重组给定事实，不编造。输出 JSON。"},
                {"role": "user", "content": prompt},
            ],
            response_format={"type": "json_object"},
            temperature=0.0,
            max_tokens=2048,
        )
        raw = json.loads(response.choices[0].message.content or "{}")
        sections = []
        for key, label in REPORT_SECTIONS:
            text = (raw.get(key) or "").strip() or "事实不足，未写入。"
            sections.append({"id": key, "label": label, "text": text, "sources": []})
        return sections, False
    except Exception as e:
        _log_llm_failure("upward_report", e)
        return _template_report(pack), True


def generate_report(person_id, manager_id=None, project_id=None, extra_notes=""):
    pack = collect_report_facts(person_id, manager_id, project_id, extra_notes)
    sections, degraded = _llm_report(pack)
    return {
        "person_id": person_id,
        "person_name": pack.get("person_name"),
        "manager_id": pack.get("manager_id"),
        "manager_name": pack.get("manager_name"),
        "project_id": project_id,
        "generated_at": _now().isoformat(timespec="seconds"),
        "fact_count": pack.get("fact_count") or 0,
        "facts": pack.get("facts") or [],
        "sections": sections,
        "degraded": degraded or is_mock_mode(),
        "mock_mode": is_mock_mode(),
        "note": "所有段落只能来自项目、事件、日报或你手动补充的事实，系统不会虚构。",
    }
