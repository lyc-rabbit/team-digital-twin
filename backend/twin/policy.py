"""P2-21 制度库、P2-22 效果评估、P2-23 冲突检测。"""

from datetime import datetime

from newcomer.repository import list_newcomers, list_tasks

from .common import cite, judgment
from . import repository as repo

KNOWN_CONFLICTS = [
    {
        "left": "pol_newcomer",
        "right": "pol_ai_week12",
        "level": "medium",
        "reason": "一边要求新人独立完成任务，一边要求前两周所有任务必须导师确认。",
        "suggestion": "明确「独立完成」的定义和适用阶段：前两周导师确认，第3周起在范围内独立。",
    }
]


def catalog():
    policies = repo.list_policies()
    outcomes = repo.list_policy_outcomes()
    by_p = {}
    for o in outcomes:
        by_p.setdefault(o["policy_id"], []).append(o)
    items = []
    for p in policies:
        items.append({**p, "outcomes": by_p.get(p["id"]) or [], "effectiveness": _effect(by_p.get(p["id"]) or [], p)})
    return {
        "policies": items,
        "conflicts": detect_conflicts(policies),
        "categories": sorted({p["category"] for p in policies if p.get("category")}),
    }


def _effect(outcomes, policy):
    if outcomes:
        o = outcomes[0]
        before, after = o.get("before_value"), o.get("after_value")
        if before and after and before != 0:
            delta = round((before - after) / abs(before) * 100, 1) if "周期" in (o.get("metric") or "") or "时间" in (o.get("metric") or "") else round((after - before) / abs(before) * 100, 1)
            return {
                "metric": o.get("metric"),
                "before": before,
                "after": after,
                "change_pct": delta,
                "verdict": "制度有效" if (delta > 0 and "周期" in (o.get("metric") or "时间")) or (delta > 0) else "效果不明显",
                "note": o.get("note"),
            }
    auto = _auto_newcomer_cycle(policy)
    return auto


def _auto_newcomer_cycle(policy):
    if "新人" not in (policy.get("title") or "") and "培养" not in (policy.get("category") or ""):
        return {"verdict": "样本不足", "note": "尚无对照数据"}
    ncs = list_newcomers("active") or []
    days = []
    created = policy.get("created_at") or ""
    before, after = [], []
    for nc in ncs:
        tasks = list_tasks(nc["id"])
        done = [t for t in tasks if t.get("status") == "completed"]
        if not done:
            continue
        try:
            start = datetime.strptime((nc.get("entry_date") or "")[:10], "%Y-%m-%d")
            end = datetime.strptime((done[-1].get("completed_at") or done[-1].get("created_at") or "")[:10], "%Y-%m-%d")
            d = max(1, (end - start).days)
        except Exception:
            continue
        days.append(d)
        if created and (nc.get("entry_date") or "") >= created[:10]:
            after.append(d)
        else:
            before.append(d)
    if before and after:
        b = sum(before) / len(before)
        a = sum(after) / len(after)
        pct = round((b - a) / b * 100, 1) if b else 0
        return {
            "metric": "平均达标时间（天）",
            "before": round(b, 1),
            "after": round(a, 1),
            "change_pct": pct,
            "verdict": "制度有效" if pct >= 10 else "效果不明显",
            "note": f"对照 {len(before)} 人 / 实施后 {len(after)} 人",
        }
    if days:
        return {"metric": "平均达标时间（天）", "after": round(sum(days) / len(days), 1), "verdict": "仅有实施后样本", "note": f"{len(days)} 名新人"}
    return {"verdict": "样本不足", "note": "还没有可对照的培养周期"}


def detect_conflicts(policies=None):
    policies = policies if policies is not None else repo.list_policies()
    active = [p for p in policies if (p.get("status") or "active") == "active"]
    by_id = {p["id"]: p for p in active}
    found = []
    for spec in KNOWN_CONFLICTS:
        if spec["left"] in by_id and spec["right"] in by_id:
            found.append({
                **spec,
                "left_title": by_id[spec["left"]]["title"],
                "right_title": by_id[spec["right"]]["title"],
                "kind": "制度冲突检测",
            })
    tags = {}
    for p in active:
        for t in p.get("tags") or []:
            tags.setdefault(t, []).append(p)
    if tags.get("independence") and tags.get("mentor_confirm"):
        a, b = tags["independence"][0], tags["mentor_confirm"][0]
        if a["id"] != b["id"] and not any(x["left"] == a["id"] and x["right"] == b["id"] for x in found):
            found.append({
                "left": a["id"],
                "right": b["id"],
                "left_title": a["title"],
                "right_title": b["title"],
                "level": "medium",
                "reason": "独立完成与导师确认同时存在，需要分期适用。",
                "suggestion": "明确独立完成的定义和适用阶段。",
                "kind": "制度冲突检测",
            })
    return found


def evaluate_policy(policy_id):
    p = repo.get_policy(policy_id)
    if not p:
        return None
    outcomes = repo.list_policy_outcomes(policy_id)
    effect = _effect(outcomes, p)
    return {
        "policy": p,
        "outcomes": outcomes,
        "effectiveness": effect,
        "judgment": judgment(
            f"《{p['title']}》效果：{effect.get('verdict')}",
            effect.get("note") or "用实施前后培养周期或登记指标对照，不由模型空评。",
            [cite("policy", p["title"], p.get("body") or "")],
        ),
    }
