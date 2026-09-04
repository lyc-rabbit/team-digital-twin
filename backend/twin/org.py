"""P2-10 扩张、P2-11 结构、P2-12 离开、P2-13 知识依赖、P2-20 梯队。"""

from math import ceil

from growth import repository as growth_repo

from .common import clip, cite, judgment, risk_level, risk_label
from . import snapshot as snap

KNOWLEDGE_KEYS = (
    ("TikTok", "TikTok API"),
    ("订单", "订单工具"),
    ("客服", "AI客服"),
    ("API", "接口资产"),
    ("AI", "AI 协作规范"),
    ("支付", "支付链路"),
    ("数据", "数据口径"),
)


def pipeline():
    team = snap.team_snapshot()
    pipe = team["pipeline"]
    newcomers = pipe.get("新人", 0)
    mentors = max(1, pipe.get("储备干部", 0) + pipe.get("高潜人员", 0) + pipe.get("管理层", 0))
    health = "健康"
    issues = []
    if pipe.get("储备干部", 0) < 2 and team["size"] >= 6:
        health = "关注"
        issues.append("储备干部不足")
    if newcomers > mentors * 3:
        health = "风险"
        issues.append("新人增长速度超过导师供给能力")
    return {
        "pipeline": pipe,
        "size": team["size"],
        "health": health,
        "issues": issues,
        "mentor_pool": team["mentor_pool"],
        "judgment": judgment(
            f"梯队健康度：{health}。",
            f"管理层 {pipe.get('管理层', 0)} / 储备 {pipe.get('储备干部', 0)} / 高潜 {pipe.get('高潜人员', 0)} / 中级 {pipe.get('普通成员', 0)} / 新人 {newcomers}。",
            [cite("team", "团队快照", f"{team['size']} 人，{team['newcomer_count']} 名在册新人")],
        ),
    }


def knowledge_map(person_id):
    person = snap.person_snapshot(person_id)
    if not person:
        return None
    blob = " ".join(
        [person.get("role") or ""]
        + [p.get("name") or "" for p in person.get("projects") or []]
        + (person.get("experiences") or [])
    )
    events = growth_repo.list_events({"member_id": person_id, "limit": 80})
    blob += " " + " ".join((e.get("raw_summary") or "") + (e.get("facts") or "") for e in events[:40])
    items = []
    for key, label in KNOWLEDGE_KEYS:
        if key.lower() in blob.lower() or key in blob:
            items.append(label)
    if not items:
        items = [p["name"] for p in (person.get("projects") or [])[:4]]
    conc = clip(40 + 12 * len(items) + 10 * person["load"]["owned_open"])
    return {
        "person_id": person_id,
        "name": person["name"],
        "chain": [person["name"], *items[:4]],
        "knowledge": items,
        "concentration": conc,
        "single_point": conc >= 70 and person["load"]["owned_open"] >= 1,
        "judgment": judgment(
            f"{person['name']} 的知识集中度 {conc}。" + ("存在知识单点风险。" if conc >= 70 else ""),
            "从项目名称、经历和事件摘要提取主题，不是外部知识库臆测。",
            [cite("project", p["name"], "项目知识") for p in (person.get("projects") or [])[:4]],
        ),
        "is_prediction": True,
    }


def departure(person_id):
    person = snap.person_snapshot(person_id)
    if not person:
        return None
    km = knowledge_map(person_id)
    impacts = []
    for p in person.get("projects") or []:
        level = "high" if p.get("is_owner") else "medium"
        impacts.append({"object": p["name"], "kind": "项目", "level": level, "need": "指定备份负责人" if p.get("is_owner") else "知识沉淀"})
    for d in person.get("dependents") or []:
        impacts.append({"object": d["name"], "kind": "新人/依赖者", "level": "high", "need": "第二导师"})
    if km and km.get("single_point"):
        for k in km["knowledge"][:3]:
            impacts.append({"object": k, "kind": "技术知识", "level": "high", "need": "知识沉淀"})
    degree = person["load"]["relationship_degree"]
    net_level = "high" if degree >= 8 else ("medium" if degree >= 3 else "low")
    impacts.append({"object": "关系网络", "kind": "关系网络", "level": net_level, "need": "明确信息传递备份"})
    org_dep = clip(50 + 10 * sum(1 for i in impacts if i["level"] == "high") + person["load"]["owned_open"] * 8)
    backups = []
    seen = set()
    for i in impacts:
        key = (i["object"], i["need"])
        if key in seen:
            continue
        seen.add(key)
        backups.append(f"{i['object']} → {i['need']}")
    return {
        "person_id": person_id,
        "name": person["name"],
        "impacts": impacts,
        "org_dependency": org_dep,
        "backups": backups[:8],
        "knowledge": km,
        "judgment": judgment(
            f"若 {person['name']} 离开/休假/调岗，综合组织依赖 {org_dep}。",
            f"负责开启项目 {person['load']['owned_open']}，关系度数 {degree}，依赖者 {len(person.get('dependents') or [])} 人。这是风险预测。",
            [cite("project", i["object"], f"{i['kind']}影响 {i['level']}") for i in impacts[:6]],
        ),
        "is_prediction": True,
        "kind_note": "风险预测，不能当作已发生事实。",
    }


def expand(add_newcomers=10, add_seniors=2, add_managers=1):
    team = snap.team_snapshot()
    cur = team["size"] or 5
    add_n = int(add_newcomers or 0)
    add_s = int(add_seniors or 0)
    add_m = int(add_managers or 0)
    future = cur + add_n + add_s + add_m
    managers = max(1, team["pipeline"].get("管理层", 0) + add_m)
    span = round(future / managers, 1)
    mentor_need = ceil(add_n / 3)
    mentor_have = len(team.get("mentor_pool") or [])
    bottlenecks = []
    if mentor_need > mentor_have:
        bottlenecks.append("技术导师不足")
    owners = len({p["owner_id"] for p in team.get("open_projects") or [] if p.get("owner_id")})
    if add_n + add_s >= 6 and owners < 3:
        bottlenecks.append("项目负责人不足")
    from .repository import list_policies
    ai_pol = [p for p in list_policies("active") if "AI" in (p.get("title") or "")]
    if add_n >= 5 and not ai_pol:
        bottlenecks.append("AI规范不足")
    span_risk = risk_level(span * 12)
    recs = [
        f"扩张后建议至少 {max(managers, ceil(future / 7))} 个管理节点，控制跨度。",
        f"新人培养需约 {mentor_need} 名导师，当前池 {mentor_have} 人。",
    ]
    if bottlenecks:
        recs.append("先补：" + "、".join(bottlenecks))
    recs.append("先把带人实践和制度沉淀做实，再线性加人。")
    return {
        "current_size": cur,
        "future_size": future,
        "added": {"newcomers": add_n, "seniors": add_s, "managers": add_m},
        "span": span,
        "span_risk": span_risk,
        "mentor_needed": mentor_need,
        "mentor_available": mentor_have,
        "train_cycle_weeks": "6-10",
        "bottlenecks": bottlenecks,
        "recommendations": recs,
        "pipeline_after": {
            "管理层": managers,
            "储备干部": team["pipeline"].get("储备干部", 0),
            "高级开发": team["pipeline"].get("高潜人员", 0) + add_s,
            "中级开发": team["pipeline"].get("普通成员", 0),
            "新人": team["pipeline"].get("新人", 0) + add_n,
        },
        "judgment": judgment(
            f"团队从 {cur} 人扩到 {future} 人，管理跨度风险{risk_label(span_risk)}。",
            f"跨度 {span} 人/管理者；导师需求 {mentor_need}，可用 {mentor_have}。瓶颈：{'、'.join(bottlenecks) or '暂无规则命中'}。",
            [cite("team", "当前团队", f"{cur} 人"), cite("pipeline", "扩张后梯队", str({"新人": add_n, "高级": add_s, "管理": add_m}))],
        ),
        "is_prediction": True,
    }


def _span_of(tree):
    """tree: {id, name, children:[...]}"""
    if not tree:
        return 0, 0, 0
    spans = []
    leaves = 0
    nodes = 0

    def walk(n, depth):
        nonlocal leaves, nodes
        nodes += 1
        ch = n.get("children") or []
        spans.append(len(ch))
        if not ch:
            leaves += 1
            return depth
        return max(walk(c, depth + 1) for c in ch)

    depth = walk(tree, 0)
    max_span = max(spans) if spans else 0
    info_cost = sum(s * s for s in spans)
    return max_span, depth, info_cost


def compare_structures(trees):
    """trees: [{id, name, tree}]"""
    rows = []
    for item in trees or []:
        tree = item.get("tree") or item
        span, depth, info = _span_of(tree)
        single = clip(span * 12 + max(0, 3 - depth) * 10)
        rows.append({
            "id": item.get("id") or tree.get("id"),
            "name": item.get("name") or tree.get("name") or "方案",
            "span": span,
            "depth": depth,
            "info_cost": info,
            "decision": clip(100 - info / 2),
            "single_point": single,
            "development": clip(70 - max(0, span - 4) * 8),
            "project_risk": risk_level(single),
        })
    best = min(rows, key=lambda x: (x["single_point"], x["info_cost"])) if rows else None
    return {
        "options": rows,
        "recommended": (best or {}).get("id"),
        "judgment": judgment(
            f"结构比较完成，更均衡的是 {(best or {}).get('name') or '无'}。",
            "管理跨度取最大直接下属数；信息传递成本取各节点跨度平方和；单点依赖随扁平且集中上升。",
            [cite("structure", r["name"], f"跨度{r['span']} 深度{r['depth']} 信息成本{r['info_cost']}") for r in rows],
        ),
        "is_prediction": True,
    }


def default_structures():
    team = snap.team_snapshot()
    people = team["people"]
    if not people:
        return []
    lead = next((p for p in people if p["person_type"] in ("管理候选人", "储备干部")), people[0])
    rest = [p for p in people if p["person_id"] != lead["person_id"]]
    mid = rest[0] if rest else None

    def node(p, children=None):
        return {"id": p["person_id"], "name": p["name"], "children": children or []}

    a_children = [node(p) for p in rest[:4]]
    b_children = []
    if mid:
        b_children = [node(mid, [node(p) for p in rest[1:4]])] + [node(p) for p in rest[4:6]]
    else:
        b_children = a_children
    return [
        {"id": "A", "name": "方案A 扁平", "tree": node(lead, a_children)},
        {"id": "B", "name": "方案B 两层", "tree": node(lead, b_children)},
    ]
