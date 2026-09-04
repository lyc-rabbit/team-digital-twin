"""
从现有数字孪生数据源构建 OIG：

日报、项目记录、会议/事件、评价反馈（关系网格）、
组织架构（成员+角色）、AI Native 角色卡。
"""

import json
import re
import threading
from collections import defaultdict

from timeutil import now_iso, today

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
    REL_REPORT_TO,
    REL_TRUST,
    REL_WORKS_ON,
    REL_HAS_SUB_RESOURCE,
    REL_HAS_RESOURCE,
    REL_EXECUTION_RESPONSIBILITY,
    REL_PERFORMED_TRAINING,
    REL_TRAINING_TARGET,
    relation_template,
)
from .ontology.resources import KEYWORD_RESOURCES, RESOURCE_CLASSES
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
    return today()


class GraphBuilder:
    def __init__(self, store=None):
        self.store = store or get_sqlite_store()
        self._lock = threading.RLock()

    def _is_suppressed(self, node_type, name, *ids):
        id_set = getattr(self, "_suppressed_ids", set())
        key_set = getattr(self, "_suppressed_keys", set())
        for nid in ids:
            if nid and nid in id_set:
                return True
        key = (node_type, (name or "").strip())
        return bool(key[1]) and key in key_set

    def _ensure_entity(self, node_type, name, preferred_id=None, **attrs):
        """经统一实体层解析后再写入，避免同名不同源拆成多个节点。"""
        if self._is_suppressed(node_type, name, preferred_id):
            return None
        from entity_governance.service import resolve_entity

        result = resolve_entity(
            node_type,
            name,
            attributes=attrs,
            source={"type": "graph_builder"},
            preferred_id=preferred_id,
            create_if_new=True,
        )
        nid = result["canonical_entity_id"]
        display = result.get("canonical_name") or name
        if self._is_suppressed(node_type, display, nid, preferred_id):
            return None
        existing = self.store.get_node(nid)
        if existing:
            node = dict(existing)
            for k, v in attrs.items():
                if v not in (None, "", [], {}) and node.get(k) in (None, "", [], {}):
                    node[k] = v
            node["entity_status"] = "ACTIVE"
            node["canonical_entity_id"] = nid
            if result.get("via") in ("alias", "auto_match"):
                node["name"] = existing.get("name") or display
            self.store.upsert_node(node)
            return nid
        node = node_template(node_type, nid, display, **attrs)
        node["entity_status"] = "ACTIVE"
        node["canonical_entity_id"] = nid
        self.store.upsert_node(node)
        return nid

    def rebuild(self, persist_communities=True, sync_neo4j=True):
        with self._lock:
            return self._rebuild_unlocked(persist_communities, sync_neo4j)

    def _rebuild_unlocked(self, persist_communities=True, sync_neo4j=True):
        members = get_all_members()
        self._suppressed_ids = set()
        self._suppressed_keys = set()
        try:
            from knowledge_governance.repository import get_kg_store
            kg = get_kg_store()
            self._suppressed_ids = set(kg.suppressed_node_ids())
            self._suppressed_keys = set(kg.suppressed_keys())
        except Exception:
            self._suppressed_ids = set()
            self._suppressed_keys = set()
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

        self._enhance_semantics()
        self._sync_temporal()

        neo4j_ok = False
        if sync_neo4j:
            neo4j_ok = self._sync_neo4j()

        self.store.set_meta("rebuilt_at", now_iso())
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
            self._ensure_entity(
                "Person",
                m["name"],
                preferred_id=m["id"],
                department=dept,
                position=m.get("role") or "",
                join_date=(m.get("created_at") or "")[:7],
                skills=[],
                persona=m.get("persona") or "",
                decision_style=m.get("decision_style") or "",
                employee_id=m["id"],
            )

        if not dept_names:
            dept_names.add("核心团队")
        dept_ids = {}
        for name in dept_names:
            dept_ids[name] = self._ensure_entity("Department", name)

        for m in members:
            dept = _infer_department(m)
            self._upsert_rel(m["id"], dept_ids[dept], REL_BELONGS_TO)

    def _build_roles(self):
        roles = get_ai_native_roles()
        assignments = get_ai_role_assignments()
        assign_by_role = defaultdict(list)
        for a in assignments:
            assign_by_role[a["role_id"]].append(a)

        for role in roles:
            skills = role.get("required_skills") or []
            rid = self._ensure_entity(
                "Role",
                role.get("role_name") or role["id"],
                preferred_id=f"role_{role['id']}",
                description=role.get("description") or "",
                required_skills=skills,
                requirements={
                    "technical": 80 if any("技术" in s or "编码" in s or "架构" in s for s in skills) else 70,
                    "management": 85 if "负责" in (role.get("role_name") or "") else 65,
                    "communication": 75,
                },
            )
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
            importance = "high" if total_days >= 8 else ("medium" if total_days >= 3 else "low")
            pid = self._ensure_entity(
                "Project", name,
                importance=importance,
                status="running",
                business_value=min(95, 50 + total_days * 4),
            )
            ranked = sorted(counts.items(), key=lambda x: x[1], reverse=True)
            for i, (mid, days) in enumerate(ranked):
                self._upsert_rel(mid, pid, REL_WORKS_ON, days=days, strength=min(1.0, days / 10.0))
                if i == 0 and days >= 2:
                    self._upsert_rel(mid, pid, REL_EXECUTION_RESPONSIBILITY, strength=min(1.0, days / 8.0))
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
            kid = self._ensure_entity("Knowledge", f"{skill}经验", domain=skill)
            for mid in people:
                self._upsert_rel(mid, kid, REL_HAS_KNOWLEDGE, level=0.7, strength=0.6)
            if len(people) >= 2:
                gid = self._ensure_entity("InformalGroup", f"{skill}圈", theme=skill)
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
            eid = f"event_{ev.get('id')}"
            if eid in getattr(self, "_suppressed_ids", set()):
                continue
            involved = ev.get("involved_members") or []
            if isinstance(involved, str):
                try:
                    involved = json.loads(involved)
                except json.JSONDecodeError:
                    involved = []
            involved = [x for x in involved if x in member_ids]
            summary = ev.get("raw_summary") or ""
            etime = (ev.get("event_time") or "")[:10]
            self._ensure_entity(
                "Event",
                summary[:24] or f"事件{ev.get('id')}",
                preferred_id=eid,
                time=etime,
                description=summary,
                event_type=ev.get("event_type") or "",
            )
            for mid in involved:
                self._upsert_rel(mid, eid, REL_INVOLVED_IN, role="participant", strength=0.5)

            if len(involved) >= 2:
                rel, extra = _classify_event(summary)
                if rel == "TRAINING_ACTION":
                    self._write_training_action(involved, ev, summary, etime, extra)
                    continue
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

    def _write_training_action(self, involved, ev, summary, etime, extra):
        """培养是行为节点，不因同场人员两两连 MENTOR，也不从汇报关系推出。"""
        tid = self._ensure_entity(
            "TrainingAction",
            f"培养·{(summary or '')[:18] or ev.get('id')}",
            preferred_id=f"train_{ev.get('id')}",
            action_type=extra.get("action_type") or "指导",
            evidence=(summary or "")[:200],
            confidence=float(extra.get("strength") or 0.7),
        )
        if not tid:
            return
        eid = f"event_{ev.get('id')}"
        if self.store.get_node(eid):
            self._upsert_rel(eid, tid, "RELATED_TO", role="training", strength=0.5)

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

    def _ensure_resource_class(self, spec):
        return self._ensure_entity(
            "Resource",
            spec["name"],
            importance=spec.get("importance") or 70,
            category=spec.get("category") or "tech",
            resource_kind="class",
        )

    def _ensure_resource_instance(self, name, *, category, importance, parent_id):
        rid = self._ensure_entity(
            "Resource",
            name,
            importance=importance,
            category=category,
            resource_kind="instance",
            parent_resource_id=parent_id,
        )
        if parent_id:
            self._upsert_rel(parent_id, rid, REL_HAS_SUB_RESOURCE, strength=0.85)
        return rid

    def _infer_resources(self, members):
        class_ids = {}
        for spec in RESOURCE_CLASSES:
            class_ids[spec["name"]] = self._ensure_resource_class(spec)

        # 从人员技能 / 知识节点推断明细资源，并挂到总类下
        for n in self.store.list_nodes("Knowledge"):
            domain = n.get("domain") or n.get("name") or ""
            for kw, spec in KEYWORD_RESOURCES.items():
                if kw in domain or kw in (n.get("name") or ""):
                    parent_id = class_ids.get(spec["class_name"])
                    rid = self._ensure_resource_instance(
                        spec["name"],
                        category=spec["category"],
                        importance=spec["importance"],
                        parent_id=parent_id,
                    )
                    for e in self.store.list_edges(relation=REL_HAS_KNOWLEDGE, target=n["id"]):
                        self._upsert_rel(
                            e["source"], rid, REL_CONTROL,
                            resource_value=spec["importance"],
                            strength=min(1.0, spec["importance"] / 100.0),
                        )

        # 项目交付：总类「交付资源」→「越南代理交付资源」；项目同时挂到明细
        delivery_id = class_ids.get("交付资源")
        for proj in self.store.list_nodes("Project"):
            owners = self.store.list_edges(relation=REL_EXECUTION_RESPONSIBILITY, target=proj["id"])
            if not owners:
                continue
            rname = f"{proj['name']}交付资源"
            rid = self._ensure_resource_instance(
                rname,
                category="delivery",
                importance=int(proj.get("business_value") or 70),
                parent_id=delivery_id,
            )
            self._upsert_rel(proj["id"], rid, REL_HAS_RESOURCE, strength=0.75)
            for e in owners:
                self._upsert_rel(
                    e["source"], rid, REL_CONTROL,
                    resource_value=int(proj.get("business_value") or 70),
                    strength=0.7,
                )

    def _enhance_semantics(self):
        """propose：只产工单并回放已确认项。未确认不得写 ontology_type / 推断边。"""
        try:
            from knowledge_governance.service import propose_semantics
            result = propose_semantics(self.store, source="rebuild")
            wi = result.get("work_items") or {}
            print(
                f"[KG] 本体提议 open+={wi.get('created')} replay={ (result.get('replayed') or {}).get('replayed') }"
            )
        except Exception as err:
            print(f"[KG] 语义提议跳过: {err}")

    def _sync_temporal(self):
        try:
            from temporal_graph.service import sync_after_rebuild
            result = sync_after_rebuild(self.store)
            print(
                f"[TKG] 时态同步 open={result.get('open_facts')} "
                f"all={result.get('all_facts')} replayed={result.get('replayed_closed')}"
            )
        except Exception as err:
            print(f"[TKG] 时态同步跳过: {err}")

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
            nid = self._ensure_entity("InformalGroup", comm["name"], theme=comm["name"])
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
        extra.update({"skill": "", "duration": 1, "strength": 0.7, "action_type": "指导"})
        return "TRAINING_ACTION", extra
    if any(k in text for k in ("冲突", "争议", "反对", "分歧", "投诉")):
        extra.update({"reason": text[:40], "frequency": 1, "impact": 70, "strength": 0.65})
        return REL_CONFLICT, extra
    extra.update({"project": "", "frequency": 1, "impact": 55})
    return REL_COLLABORATE, extra
