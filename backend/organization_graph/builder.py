"""
从现有数字孪生数据源构建 OIG：

日报、项目记录、会议/事件、评价反馈（关系网格）、
组织架构（成员+角色）、AI Native 角色卡。
"""

import json
import re
import threading
from collections import defaultdict
from datetime import datetime

from database import (
    get_all_members,
    get_ai_native_roles,
    get_ai_role_assignments,
    get_daily_reports,
    get_events,
    get_relationship_logs,
)
from memory_engine import compute_relationship_grid

from .ontology.nodes import node_template
from .ontology.relations import (
    REL_BELONGS_TO,
    REL_COLLABORATE,
    REL_CONFLICT,
    REL_CONTROL,
    REL_HAS_KNOWLEDGE,
    REL_HAS_ROLE,
    REL_INFORMAL,
    REL_INVOLVED_IN,
    REL_MENTOR,
    REL_OWNER,
    REL_REPORT_TO,
    REL_TRUST,
    REL_WORKS_ON,
    relation_template,
)
from .repository.store import get_sqlite_store
from .repository.neo4j import get_neo4j
from .repository.facade import get_facade
from .algorithms.influence import compute_influence
from .algorithms.community import detect_communities


def _slug(text, prefix):
    raw = re.sub(r"[^0-9a-zA-Z\u4e00-\u9fff]+", "_", (text or "").strip()).strip("_")
    raw = raw.lower() or "unknown"
    return f"{prefix}_{raw}"[:80]


def _today():
    return datetime.now().strftime("%Y-%m-%d")


class GraphBuilder:
    def __init__(self, store=None):
        self.store = store or get_sqlite_store()
        self._lock = threading.RLock()

    def rebuild(self, persist_communities=True, sync_neo4j=True):
        with self._lock:
            return self._rebuild_unlocked(persist_communities, sync_neo4j)

    def _rebuild_unlocked(self, persist_communities=True, sync_neo4j=True):
        members = get_all_members()
        self.store.clear()

        self._build_org(members)
        self._build_roles()
        self._build_from_daily_reports(members)
        self._build_from_events(members)
        self._build_from_trust_grid(members)
        self._infer_report_to(members)
        self._infer_resources(members)

        influence = self._write_influence()
        communities = []
        if persist_communities:
            communities = self._write_communities()

        neo4j_ok = False
        if sync_neo4j:
            neo4j_ok = self._sync_neo4j()

        self.store.set_meta("rebuilt_at", datetime.now().isoformat(timespec="seconds"))
        self.store.set_meta("backend", "neo4j" if neo4j_ok else "sqlite")
        primary = get_facade()
        return {
            "stats": primary.stats(),
            "influence_count": len(influence),
            "communities": len(communities),
            "neo4j": neo4j_ok,
            "primary": "neo4j" if neo4j_ok else "sqlite",
            "member_count": len(members),
        }

    def ensure_built(self):
        with self._lock:
            stats = get_facade().stats()
            members = get_all_members()
            if stats["node_count"] == 0 and members:
                return self._rebuild_unlocked()
            person_count = stats.get("nodes_by_type", {}).get("Person", 0)
            if members and person_count != len(members):
                return self._rebuild_unlocked()
            return None

    def _upsert_rel(self, source, target, relation, **props):
        if not source or not target or source == target:
            return
        edge = relation_template(source, target, relation, **props)
        self.store.upsert_edge(source, target, relation, edge["properties"], record_history=False)

    def _build_org(self, members):
        dept_names = set()
        for m in members:
            dept = _infer_department(m)
            dept_names.add(dept)
            skills = []
            node = node_template(
                "Person",
                m["id"],
                m["name"],
                department=dept,
                position=m.get("role") or "",
                join_date=(m.get("created_at") or "")[:7],
                skills=skills,
                persona=m.get("persona") or "",
                decision_style=m.get("decision_style") or "",
            )
            self.store.upsert_node(node)

        if not dept_names:
            dept_names.add("核心团队")
        for name in dept_names:
            self.store.upsert_node(node_template("Department", _slug(name, "dept"), name))

        for m in members:
            dept = _infer_department(m)
            self._upsert_rel(m["id"], _slug(dept, "dept"), REL_BELONGS_TO)

    def _build_roles(self):
        roles = get_ai_native_roles()
        assignments = get_ai_role_assignments()
        assign_by_role = defaultdict(list)
        for a in assignments:
            assign_by_role[a["role_id"]].append(a)

        for role in roles:
            rid = f"role_{role['id']}"
            skills = role.get("required_skills") or []
            self.store.upsert_node(node_template(
                "Role",
                rid,
                role.get("role_name") or role["id"],
                description=role.get("description") or "",
                required_skills=skills,
                requirements={
                    "technical": 80 if any("技术" in s or "编码" in s or "架构" in s for s in skills) else 70,
                    "management": 85 if "负责" in (role.get("role_name") or "") else 65,
                    "communication": 75,
                },
            ))
            owners = sorted(assign_by_role.get(role["id"], []), key=lambda x: x.get("match_score", 0), reverse=True)
            if owners:
                top = owners[0]
                self._upsert_rel(
                    top["employee_id"], rid, REL_HAS_ROLE,
                    match_score=top.get("match_score") or 0,
                    strength=min(1.0, (top.get("match_score") or 0) / 100.0),
                )

    def _build_from_daily_reports(self, members):
        reports = get_daily_reports(limit=1000)
        member_ids = {m["id"] for m in members}
        project_members = defaultdict(lambda: defaultdict(int))
        skill_members = defaultdict(set)
        person_skills = defaultdict(lambda: defaultdict(int))

        for r in reports:
            mid = r.get("member_id")
            if mid not in member_ids:
                continue
            projects = r.get("projects") or []
            skills = r.get("skills") or []
            for p in projects:
                if not p or p == "未分类":
                    continue
                project_members[p][mid] += 1
            for s in skills:
                if not s:
                    continue
                skill_members[s].add(mid)
                person_skills[mid][s] += 1

        ranked_projects = sorted(
            project_members.items(),
            key=lambda x: sum(x[1].values()),
            reverse=True,
        )
        for name, counts in ranked_projects[:24]:
            total_days = sum(counts.values())
            if total_days < 2:
                continue
            pid = _slug(name, "project")
            importance = "high" if total_days >= 8 else ("medium" if total_days >= 3 else "low")
            self.store.upsert_node(node_template(
                "Project", pid, name,
                importance=importance,
                status="running",
                business_value=min(95, 50 + total_days * 4),
            ))
            ranked = sorted(counts.items(), key=lambda x: x[1], reverse=True)
            for i, (mid, days) in enumerate(ranked):
                self._upsert_rel(mid, pid, REL_WORKS_ON, days=days, strength=min(1.0, days / 10.0))
                if i == 0 and days >= 2:
                    self._upsert_rel(mid, pid, REL_OWNER, strength=min(1.0, days / 8.0))
            ids = [mid for mid, _ in ranked]
            for i, a in enumerate(ids):
                for b in ids[i + 1:]:
                    freq = min(counts[a], counts[b])
                    self._upsert_rel(
                        a, b, REL_COLLABORATE,
                        project=name,
                        frequency=freq,
                        impact=min(90, 40 + freq * 8),
                        strength=min(1.0, 0.35 + freq * 0.08),
                        evidence=[f"共同投入项目「{name}」"],
                    )

        ranked_skills = sorted(skill_members.items(), key=lambda x: len(x[1]), reverse=True)
        for skill, people in ranked_skills[:18]:
            if len(people) < 1:
                continue
            kid = _slug(skill, "knowledge")
            self.store.upsert_node(node_template("Knowledge", kid, f"{skill}经验", domain=skill))
            for mid in people:
                self._upsert_rel(mid, kid, REL_HAS_KNOWLEDGE, level=0.7, strength=0.6)
            if len(people) >= 2:
                gid = _slug(f"{skill}圈", "group")
                self.store.upsert_node(node_template("InformalGroup", gid, f"{skill}圈", theme=skill))
                for mid in people:
                    self._upsert_rel(mid, gid, REL_INFORMAL, affinity=0.7, strength=0.55)

        for mid, skills in person_skills.items():
            node = self.store.get_node(mid)
            if not node:
                continue
            top = sorted(skills.items(), key=lambda x: x[1], reverse=True)[:10]
            node["skills"] = [s for s, _ in top]
            self.store.upsert_node(node)

    def _build_from_events(self, members):
        events = get_events(include_hypothetical=False)
        member_ids = {m["id"] for m in members}

        for ev in events:
            involved = ev.get("involved_members") or []
            if isinstance(involved, str):
                try:
                    involved = json.loads(involved)
                except json.JSONDecodeError:
                    involved = []
            involved = [x for x in involved if x in member_ids]
            summary = ev.get("raw_summary") or ""
            etime = (ev.get("event_time") or "")[:10]
            eid = f"event_{ev.get('id')}"
            self.store.upsert_node(node_template(
                "Event", eid, (summary[:24] or f"事件{ev.get('id')}"),
                time=etime,
                description=summary,
            ))
            for mid in involved:
                self._upsert_rel(mid, eid, REL_INVOLVED_IN, role="participant", strength=0.5)

            if len(involved) >= 2:
                rel, extra = _classify_event(summary)
                for i, a in enumerate(involved):
                    for b in involved[i + 1:]:
                        self._upsert_rel(
                            a, b, rel,
                            evidence=[summary[:80]],
                            last_update=etime or extra.get("last_update") or _today(),
                            **{k: v for k, v in extra.items() if k != "last_update"},
                        )

    def _build_from_trust_grid(self, members):
        grid = compute_relationship_grid(include_hypothetical=False)
        logs = get_relationship_logs(include_hypothetical=False)
        samples = defaultdict(int)
        for log in logs:
            key = f"{log['from_member_id']}→{log['to_member_id']}"
            samples[key] += 1

        for key, val in (grid or {}).items():
            if "→" not in key:
                continue
            src, tgt = key.split("→", 1)
            trust = float(val.get("trust") or 0)
            sentiment = float(val.get("sentiment") or 0)
            tag = val.get("tag") or ""
            last = (val.get("last_event_time") or "")[:10] or _today()
            n = samples.get(key) or 1
            if trust > 5:
                score = min(1.0, (trust + 20) / 120.0)
                self._upsert_rel(
                    src, tgt, REL_TRUST,
                    score=round(score, 3),
                    sample_count=n,
                    strength=round(score, 3),
                    evidence=[tag] if tag else [],
                    last_update=last,
                )
            if sentiment <= -15 or trust <= -20:
                self._upsert_rel(
                    src, tgt, REL_CONFLICT,
                    reason=tag or "关系紧张",
                    frequency=max(1, n),
                    impact=min(90, int(abs(sentiment) * 1.2 + abs(min(trust, 0)))),
                    strength=min(1.0, abs(sentiment) / 80.0),
                    evidence=[tag] if tag else [],
                    last_update=last,
                )

    def _infer_report_to(self, members):
        if not members:
            return
        # AI Native 负责人
        assignments = get_ai_role_assignments()
        leader_assigns = [a for a in assignments if a.get("role_id") == "leader"]
        leader_id = None
        if leader_assigns:
            leader_id = sorted(leader_assigns, key=lambda x: x.get("match_score", 0), reverse=True)[0]["employee_id"]
        if not leader_id:
            for m in members:
                role = m.get("role") or ""
                if any(k in role for k in ("负责", "主管", "经理", "Leader", "lead", "总监")):
                    leader_id = m["id"]
                    break
        if not leader_id:
            return
        for m in members:
            if m["id"] == leader_id:
                continue
            self._upsert_rel(
                m["id"], leader_id, REL_REPORT_TO,
                start_date=(m.get("created_at") or "")[:10],
                current=True,
                strength=0.9,
            )

    def _infer_resources(self, members):
        keywords = {
            "GPU": ("GPU集群", "tech", 90),
            "数据": ("核心数据资源", "data", 80),
            "模型": ("核心模型资产", "tech", 85),
            "客户": ("客户资源", "customer", 75),
            "预算": ("预算资源", "budget", 70),
        }
        # 从人员技能 / 知识节点推断资源控制
        for n in self.store.list_nodes("Knowledge"):
            domain = n.get("domain") or n.get("name") or ""
            for kw, (rname, cat, imp) in keywords.items():
                if kw in domain or kw in (n.get("name") or ""):
                    rid = _slug(rname, "resource")
                    self.store.upsert_node(node_template("Resource", rid, rname, importance=imp, category=cat))
                    for e in self.store.list_edges(relation=REL_HAS_KNOWLEDGE, target=n["id"]):
                        self._upsert_rel(
                            e["source"], rid, REL_CONTROL,
                            resource_value=imp,
                            strength=min(1.0, imp / 100.0),
                        )

        # 高频项目负责人视为控制该项目对应的交付资源
        for proj in self.store.list_nodes("Project"):
            owners = self.store.list_edges(relation=REL_OWNER, target=proj["id"])
            if not owners:
                continue
            rname = f"{proj['name']}交付资源"
            rid = _slug(rname, "resource")
            self.store.upsert_node(node_template(
                "Resource", rid, rname,
                importance=int(proj.get("business_value") or 70),
                category="project",
            ))
            for e in owners:
                self._upsert_rel(
                    e["source"], rid, REL_CONTROL,
                    resource_value=int(proj.get("business_value") or 70),
                    strength=0.7,
                )

    def _write_influence(self):
        nodes = self.store.list_nodes()
        edges = self.store.list_edges()
        influence = compute_influence(nodes, edges)
        for pid, info in influence.items():
            node = self.store.get_node(pid)
            if not node:
                continue
            node["influence_score"] = info["influence_score"]
            self.store.upsert_node(node)
        return influence

    def _write_communities(self):
        nodes = self.store.list_nodes()
        edges = self.store.list_edges()
        communities = detect_communities(nodes, edges)
        for comm in communities:
            gid = comm["id"] if str(comm["id"]).startswith("group_") else _slug(comm["name"], "group")
            # 避免覆盖技能圈：若已存在同名则复用
            existing = None
            for g in self.store.list_nodes("InformalGroup"):
                if g.get("name") == comm["name"]:
                    existing = g
                    break
            nid = existing["id"] if existing else gid
            self.store.upsert_node(node_template("InformalGroup", nid, comm["name"], theme=comm["name"]))
            for m in comm.get("members") or []:
                self._upsert_rel(m["id"], nid, REL_INFORMAL, affinity=0.65, strength=0.5)
        return communities

    def _sync_neo4j(self):
        neo = get_neo4j()
        if not neo.enabled:
            return False
        return neo.replace_graph(self.store.list_nodes(), self.store.list_edges())


def _infer_department(member):
    role = member.get("role") or ""
    for token in ("部", "组", "团队", "中心"):
        idx = role.find(token)
        if idx > 0:
            start = 0
            for i, ch in enumerate(role):
                if ch in "·/-_| ":
                    start = i + 1
            return role[start:idx + 1]
    return "核心团队"


def _classify_event(summary):
    text = summary or ""
    extra = {"strength": 0.55, "last_update": _today()}
    if any(k in text for k in ("帮助", "指导", "带教", "培养", "教会")):
        extra.update({"skill": "", "duration": 1, "strength": 0.7})
        return REL_MENTOR, extra
    if any(k in text for k in ("冲突", "争议", "反对", "分歧", "投诉")):
        extra.update({"reason": text[:40], "frequency": 1, "impact": 70, "strength": 0.65})
        return REL_CONFLICT, extra
    extra.update({"project": "", "frequency": 1, "impact": 55})
    return REL_COLLABORATE, extra
