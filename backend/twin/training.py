"""P2-06 培养方案生成、P2-07 自动优化、P2-08 方案对比、P2-09 虚拟新人群体。"""

from math import ceil

from newcomer.templates import LEVEL_LABELS

from .common import clip, cite, judgment
from . import snapshot as snap
from . import repository as repo

STAGE_TEMPLATE = [
    {"week": "第1-2周", "theme": "业务理解", "goal": "能讲清主流程、关键系统和当前负责模块边界。", "ai": "允许查询文档和对比方案，禁止直接生成最终结论。", "mentor": "高频：每天可答一次结构化问题。"},
    {"week": "第3-4周", "theme": "AI协作", "goal": "能验证 AI 输出，区分事实、假设和结论。", "ai": "允许代码草稿和日志分析，必须人工复核。", "mentor": "中频：每周 2 次代码/方案点评。"},
    {"week": "第5-6周", "theme": "独立任务", "goal": "独立完成一个小功能或排查，提交可核验结果。", "ai": "允许辅助，禁止让 AI 代替问题定义。", "mentor": "低频：只在阻塞和验收时介入。"},
    {"week": "第7周", "theme": "复杂问题解决", "goal": "处理一次跨模块问题，留下事实-假设-验证记录。", "ai": "允许检索，最终判断必须本人给出。", "mentor": "观察式介入，不直接给答案。"},
    {"week": "第8周", "theme": "综合考核", "goal": "对照角色 L2 标准做一次综合验收。", "ai": "考核任务限制 AI，验证独立性。", "mentor": "验收与复盘。"},
]


def generate_plan(person_id, mentor_id=None, role_id="developer", from_level="L1", to_level="L2", days=60):
    person = snap.person_snapshot(person_id) if person_id else None
    mentor = snap.person_snapshot(mentor_id) if mentor_id else None
    stages = []
    for i, s in enumerate(STAGE_TEMPLATE):
        risk = "进度落后" if (person and person.get("velocity", {}).get("stalled") and i >= 2) else "阶段跳过导致基础不牢"
        if person and person.get("newcomer") and i == 2:
            indep = next((c["current"] for c in person["capabilities"] if c["id"] == "problem_definition"), 50)
            if indep < 55:
                risk = "问题定义能力不足，独立任务阶段可能反复求助"
        stages.append({
            **s,
            "tasks": [f"完成与「{s['theme']}」对应的可核验任务，并记录事件"],
            "criteria": f"达到{to_level}要求中与{s['theme']}相关的条目",
            "risk": risk,
            "eval_event": f"{s['theme']}阶段评价事件",
        })
    plan = {
        "person_id": person_id,
        "person_name": (person or {}).get("name"),
        "mentor_id": mentor_id,
        "mentor_name": (mentor or {}).get("name"),
        "role_id": role_id,
        "from_level": from_level,
        "to_level": to_level,
        "from_label": LEVEL_LABELS.get(from_level, from_level),
        "to_label": LEVEL_LABELS.get(to_level, to_level),
        "days": int(days or 60),
        "stages": stages,
        "judgment": judgment(
            f"生成 {from_level}→{to_level}、周期 {days} 天的培养方案。",
            "阶段来自角色培养标准模板，风险结合当前能力与导师负荷，不是自由发挥。",
            [
                cite("standard", "角色标准", f"{role_id} {from_level}→{to_level}"),
                cite("person", "当前状态", f"{(person or {}).get('person_type') or '未指定'}，准备度 {(person or {}).get('readiness')}"),
            ],
        ),
    }
    plan["plan_id"] = repo.save_plan(person_id, mentor_id, role_id, from_level, to_level, days, plan)
    return plan


def optimize_plan(person_id, days=60):
    person = snap.person_snapshot(person_id)
    if not person:
        return None
    nc = person.get("newcomer") or {}
    planned_weeks = max(1, int(days or 60) / 7)
    progress = float(nc.get("progress") or 0)
    expected = min(100, (nc.get("completed") or 0) / max(1, nc.get("task_count") or 8) * 100)
    ahead = progress >= expected + 15 or (nc.get("completed") or 0) >= 3
    vel = person["velocity"]
    ai_heavy = any(c["id"] == "ai_collab" and c["current"] >= 70 for c in person["capabilities"])
    indep_low = any(c["id"] == "problem_definition" and c["current"] < 55 for c in person["capabilities"])
    adjustments = []
    if ahead:
        adjustments.append({
            "type": "accelerate",
            "title": "基础能力提前达标",
            "action": "将后续独立任务提前一周，缩短业务理解阶段。",
        })
    if ai_heavy and indep_low:
        adjustments.append({
            "type": "rebalance",
            "title": "AI 依赖增长过快",
            "action": "增加人工独立任务，考核阶段限制 AI 给出最终结论。",
        })
    if vel.get("stalled"):
        adjustments.append({
            "type": "intervene",
            "title": "培养事件停滞",
            "action": "本周必须完成一次可核验任务并记录结构化事件。",
        })
    if not adjustments:
        adjustments.append({
            "type": "hold",
            "title": "按原计划执行",
            "action": "偏差未超过阈值，维持当前阶段顺序。",
        })
    return {
        "person_id": person_id,
        "name": person["name"],
        "planned_weeks": planned_weeks,
        "progress": progress,
        "expected": round(expected, 1),
        "adjustments": adjustments,
        "judgment": judgment(
            "培养方案进入「计划→执行→数据→偏差→调整」。",
            f"进度 {progress}，任务完成 {nc.get('completed') or 0}/{nc.get('task_count') or 0}。"
            + ("已提前。" if ahead else "未明显提前。"),
            [cite("newcomer", "培养数据", f"阶段 {nc.get('stage') or '无新人档案'}")],
        ),
    }


def compare_schemes(person_id, mentor_id=None):
    person = snap.person_snapshot(person_id) if person_id else None
    mentor = snap.person_snapshot(mentor_id) if mentor_id else None
    indep = 50
    if person:
        indep = next((c["current"] for c in person["capabilities"] if c["id"] == "problem_definition"), 50)
    load = (mentor or {}).get("load", {}).get("owned_open", 1)
    base = 60
    if person and person.get("newcomer"):
        done = (person["newcomer"].get("completed") or 0)
        base = max(40, 70 - done * 4)

    def pack(name, mentor_int, ai_int, task_drive):
        days = clip(base - ai_int * 4 + (8 if indep < 50 else 0) - task_drive * 2, 28, 90)
        mentor_cost = "高" if mentor_int >= 0.7 else ("中" if mentor_int >= 0.4 else "低")
        ai_dep = "高" if ai_int >= 0.7 else ("中" if ai_int >= 0.4 else "低")
        independence = "高" if (1 - ai_int + task_drive) >= 1.1 else ("中" if (1 - ai_int) >= 0.4 else "低")
        rate = clip(100 - (days - 45) * 1.4 - load * 4 + (8 if independence == "高" else 0) - (10 if ai_dep == "高" and indep < 55 else 0))
        return {
            "id": name,
            "name": name,
            "days": days,
            "mentor_cost": mentor_cost,
            "ai_dependency": ai_dep,
            "independence": independence,
            "score": rate,
        }

    schemes = [
        pack("方案A 导师高频介入", 0.85, 0.25, 0.3),
        pack("方案B AI高频介入", 0.3, 0.85, 0.35),
        pack("方案C 任务驱动", 0.45, 0.4, 0.85),
    ]
    best = max(schemes, key=lambda x: x["score"])
    return {
        "person_id": person_id,
        "mentor_id": mentor_id,
        "schemes": schemes,
        "recommended": best["id"],
        "judgment": judgment(
            f"综合推荐 {best['id']}（{best['score']} 分）。",
            "达标时间、导师成本、AI 依赖、独立性由当前能力、独立性分和导师负荷计算，LLM 不参与打分。",
            [cite("capability", "问题定义", f"当前约 {indep}"), cite("load", "导师负荷", f"开启项目 {(mentor or {}).get('load', {}).get('owned_open', 0)}")],
        ),
        "is_prediction": True,
    }


def simulate_cohort(hire_count=10, mix=None):
    mix = mix or {"技术型": 40, "业务型": 30, "学习型": 20, "执行型": 10}
    team = snap.team_snapshot()
    n = int(hire_count or 10)
    mentors = team.get("mentor_pool") or []
    available = max(1, len(mentors))
    need = ceil(n / 3)
    load = []
    for i, m in enumerate(mentors):
        assigned = n // max(1, len(mentors)) + (1 if i < n % max(1, len(mentors)) else 0)
        load.append({
            "person_id": m["person_id"],
            "name": m["name"],
            "assigned": assigned,
            "current_projects": m.get("load", {}).get("owned_open", 0),
            "overloaded": assigned >= 3 and m.get("load", {}).get("owned_open", 0) >= 2,
        })
    reach = clip(72 * min(1.0, available / max(need, 1)) - (8 if need > available else 0))
    return {
        "hire_count": n,
        "mix": mix,
        "mentor_needed": need,
        "mentor_available": available,
        "suitable_mentors": load,
        "expected_l2_rate": reach,
        "expected_l2_count": int(round(n * reach / 100)),
        "risks": (
            ["导师数量不足"] if need > available else []
        ) + (["部分导师项目负荷与带人叠加"] if any(x["overloaded"] for x in load) else []),
        "judgment": judgment(
            f"招 {n} 人大约需要 {need} 名导师，当前池 {available} 人；预计 {int(round(n * reach / 100))} 人达到 L2。",
            "导师按 1 带 3 估算，达标率随导师供给下降。这是群体模拟，不是录用承诺。",
            [cite("pipeline", "人才梯队", str(team.get("pipeline")))],
        ),
        "is_prediction": True,
    }
