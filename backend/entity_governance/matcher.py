"""EntityMatchEngine —— 四层匹配 + 分类型加权，LLM 不参与最终判定。"""

from collections import defaultdict

from .conflicts import detect_conflicts
from .normalizer import (
    jaccard,
    match_key,
    name_similarity,
    ngram_cosine,
    normalize_text,
    person_name_similarity,
    tokenize,
    url_key,
)
from .types import (
    AUTO_MERGE_THRESHOLD,
    DECISION_AUTO_MATCH,
    DECISION_FORCE_REVIEW,
    DECISION_NEW,
    DECISION_REVIEW,
    EVENT_AUTO_THRESHOLD,
    EVENT_FIELD_WEIGHTS,
    KNOWLEDGE_FIELD_WEIGHTS,
    LAYER_WEIGHTS,
    NO_AUTO_MERGE_TYPES,
    PERSON_FIELD_WEIGHTS,
    PERSON_ID_KEYS,
    PROJECT_FIELD_WEIGHTS,
    RECALL_LIMIT,
    RESOURCE_FIELD_WEIGHTS,
    REVIEW_THRESHOLD,
    to_entity_type,
)


class EntityMatchEngine:
    def __init__(self, graph_store=None):
        self.graph = graph_store

    def recall(self, entity: dict, pool: list, aliases_by_norm=None, limit=RECALL_LIMIT) -> list:
        """Candidate Retrieval：名称倒排 / Alias / 关键词 / 邻居，Top N。"""
        eid = entity.get("id")
        etype = entity.get("type")
        if not eid:
            return []
        aliases_by_norm = aliases_by_norm or {}
        my_tokens = set(tokenize(entity.get("name")))
        my_norm = normalize_text(entity.get("name"))
        my_key = match_key(entity.get("name"))
        my_neighbors = self._neighbor_ids(eid)

        scored = []
        for other in pool:
            oid = other.get("id")
            if not oid or oid == eid or other.get("type") != etype:
                continue
            if (other.get("entity_status") or "ACTIVE") == "MERGED":
                continue
            hit = 0.0
            onorm = normalize_text(other.get("name"))
            okey = match_key(other.get("name"))
            if my_norm and onorm == my_norm:
                hit += 5
            if my_key and okey == my_key:
                hit += 4
            otokens = set(tokenize(other.get("name")))
            if my_tokens and otokens:
                hit += 3 * len(my_tokens & otokens) / max(len(my_tokens | otokens), 1)
            alias = aliases_by_norm.get((to_entity_type(etype), onorm))
            if alias and alias.get("entity_id") == eid:
                hit += 6
            shared = my_neighbors & self._neighbor_ids(oid)
            if shared:
                hit += min(2.0, 0.3 * len(shared))
            # 精确 ID / URL
            if self._exact_id_hit(entity, other):
                hit += 8
            if hit > 0 or name_similarity(entity.get("name"), other.get("name")) >= 0.55:
                hit += name_similarity(entity.get("name"), other.get("name"))
                scored.append((hit, other))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [item for _, item in scored[:limit]]

    def match(self, left: dict, right: dict, neighbors_left=None, neighbors_right=None) -> dict:
        from organization_graph.ontology.resources import is_resource_hierarchy_pair

        entity_type = to_entity_type(left.get("type") or right.get("type") or "PROJECT")
        n_left = neighbors_left if neighbors_left is not None else self._neighbors(left.get("id"))
        n_right = neighbors_right if neighbors_right is not None else self._neighbors(right.get("id"))

        if entity_type == "RESOURCE" and is_resource_hierarchy_pair(left, right):
            return {
                "entity_a_id": left.get("id"),
                "entity_b_id": right.get("id"),
                "entity_type": entity_type,
                "score": 0.12,
                "decision": DECISION_NEW,
                "field_scores": {"name": name_similarity(left.get("name"), right.get("name"))},
                "match_layers": {"exact": 0, "rule": 0.12, "semantic": 0, "graph": 0},
                "graph_evidence": [],
                "semantic_evidence": [{"note": "总类与明细资源，不是重复实体"}],
                "conflicts": [{
                    "code": "RESOURCE_HIERARCHY",
                    "message": "一方是资源总类、一方是明细，应保留层级而不是合并",
                    "severity": "high",
                }],
                "evidence": [],
            }

        exact, exact_fields = self._exact_layer(left, right, entity_type)
        rule, rule_fields = self._rule_layer(left, right, entity_type, n_left, n_right)
        semantic, semantic_ev = self._semantic_layer(left, right, entity_type)
        graph_s, graph_ev = self._graph_layer(left, right, n_left, n_right)

        orig_weights = dict(LAYER_WEIGHTS.get(entity_type) or LAYER_WEIGHTS["PROJECT"])
        weights = dict(orig_weights)
        available = {"rule": rule, "semantic": semantic}
        if exact > 0 or self._has_exact_keys(left, right, entity_type):
            available["exact"] = exact
        else:
            weights.pop("exact", None)
        if graph_s > 0 or self._other_ids(left.get("id"), n_left) or self._other_ids(right.get("id"), n_right):
            available["graph"] = graph_s
        else:
            weights.pop("graph", None)
        total_w = sum(weights.get(k, 0) for k in available) or 1.0
        if exact >= 0.999:
            final = 1.0
        else:
            final = sum(weights.get(k, 0) / total_w * available[k] for k in available)

        name_s = float(rule_fields.get("name") or 0)
        if entity_type in {"PROJECT", "RESOURCE", "DEPARTMENT", "ORG_GROUP", "ROLE", "KNOWLEDGE"}:
            if name_s >= 0.96:
                final = max(final, 0.88)
            elif name_s >= 0.82:
                final = max(final, 0.78)
        final = max(0.0, min(1.0, round(final, 4)))

        field_scores = {}
        field_scores.update(exact_fields)
        field_scores.update(rule_fields)
        field_scores["semantic"] = round(semantic, 4)
        field_scores["graph"] = round(graph_s, 4)

        conflicts = detect_conflicts(left, right, entity_type, n_left, n_right)
        decision = self._decide(entity_type, final, conflicts, exact, rule_fields)

        evidence = []
        for k, v in field_scores.items():
            if isinstance(v, (int, float)) and v >= 0.5:
                evidence.append({"field": k, "score": v})

        return {
            "entity_a_id": left.get("id"),
            "entity_b_id": right.get("id"),
            "entity_type": entity_type,
            "score": final,
            "decision": decision,
            "field_scores": field_scores,
            "match_layers": {
                "exact": round(exact, 4),
                "rule": round(rule, 4),
                "semantic": round(semantic, 4),
                "graph": round(graph_s, 4),
                "weights": orig_weights,
            },
            "graph_evidence": graph_ev,
            "semantic_evidence": semantic_ev,
            "conflicts": conflicts,
            "evidence": evidence,
        }

    def _decide(self, entity_type, score, conflicts, exact, rule_fields):
        has_high_conflict = any(c.get("severity") == "high" for c in conflicts or [])
        if has_high_conflict:
            return DECISION_FORCE_REVIEW
        if entity_type in NO_AUTO_MERGE_TYPES:
            return DECISION_REVIEW if score >= REVIEW_THRESHOLD else DECISION_NEW
        auto_th = EVENT_AUTO_THRESHOLD if entity_type == "EVENT" else AUTO_MERGE_THRESHOLD
        if entity_type == "EVENT":
            # 事件必须关键字段高度一致
            must = ("time", "subject", "action", "type")
            if any((rule_fields.get(k) or 0) < 0.9 for k in must if k in rule_fields):
                if score >= REVIEW_THRESHOLD:
                    return DECISION_REVIEW
                return DECISION_NEW
        if score >= auto_th and not conflicts:
            # 自动合并还要求没有强冲突（已检查）且名称/规则不是“空壳高分”
            if exact >= 0.999:
                return DECISION_AUTO_MATCH
            name_s = rule_fields.get("name") or 0
            if name_s >= 0.7 or exact >= 0.8:
                return DECISION_AUTO_MATCH
            return DECISION_REVIEW
        if score >= REVIEW_THRESHOLD:
            return DECISION_REVIEW
        return DECISION_NEW

    def _exact_layer(self, a, b, entity_type):
        fields = {}
        if entity_type == "PERSON":
            score = 0.0
            for key in PERSON_ID_KEYS:
                va = _scalar(a.get(key) if key != "id" else a.get("employee_id") or a.get("id"))
                vb = _scalar(b.get(key) if key != "id" else b.get("employee_id") or b.get("id"))
                if key == "id":
                    va = _scalar(a.get("employee_id"))
                    vb = _scalar(b.get("employee_id"))
                if va and vb and va == vb:
                    fields[key] = 1.0
                    score = 1.0
                    break
            email_a, email_b = _scalar(a.get("email")), _scalar(b.get("email"))
            if email_a and email_b and email_a == email_b:
                fields["email"] = 1.0
                score = max(score, 1.0)
            return score, fields

        if entity_type == "PROJECT":
            pa, pb = _scalar(a.get("project_id")), _scalar(b.get("project_id"))
            if pa and pb and pa == pb:
                fields["project_id"] = 1.0
                return 1.0, fields
            fields["project_id"] = 0.0
            return 0.0, fields

        if entity_type == "RESOURCE":
            ua = url_key(a.get("url") or a.get("repo") or a.get("repository"))
            ub = url_key(b.get("url") or b.get("repo") or b.get("repository"))
            if ua and ub and ua == ub:
                fields["url"] = 1.0
                return 1.0, fields
            fields["url"] = 0.0
            return 0.0, fields

        if entity_type == "EVENT":
            if a.get("id") and a.get("id") == b.get("id"):
                fields["event_id"] = 1.0
                return 1.0, fields
            return 0.0, fields

        return 0.0, fields

    def _rule_layer(self, a, b, entity_type, n_a, n_b):
        if entity_type == "PERSON":
            return self._rule_person(a, b, n_a, n_b)
        if entity_type == "PROJECT":
            return self._rule_project(a, b, n_a, n_b)
        if entity_type == "RESOURCE":
            return self._rule_resource(a, b, n_a, n_b)
        if entity_type == "KNOWLEDGE":
            return self._rule_knowledge(a, b, n_a, n_b)
        if entity_type == "EVENT":
            return self._rule_event(a, b, n_a, n_b)
        name_s = name_similarity(a.get("name"), b.get("name"))
        return name_s, {"name": round(name_s, 4)}

    def _rule_person(self, a, b, n_a, n_b):
        w = PERSON_FIELD_WEIGHTS
        unique = 1.0 if self._exact_id_hit(a, b) else 0.0
        email = 1.0 if _same(a.get("email"), b.get("email")) else 0.0
        account = 0.0
        for k in ("enterprise_wechat", "github_account"):
            if _same(a.get(k), b.get(k)):
                account = 1.0
        name_s = person_name_similarity(a.get("name"), b.get("name"))
        org = 0.0
        if _same(a.get("department"), b.get("department")) and a.get("department"):
            org += 0.5
        if _same(a.get("position") or a.get("role"), b.get("position") or b.get("role")):
            org += 0.3
        shared_proj = self._shared_targets(n_a, n_b, "WORKS_ON") | self._shared_targets(n_a, n_b, "OWNER")
        if shared_proj:
            org += min(0.4, 0.15 * len(shared_proj))
        org = min(1.0, org)
        score = (
            w["unique_id"] * unique
            + w["email"] * email
            + w["account"] * account
            + w["name"] * name_s
            + w["org_context"] * org
        )
        fields = {
            "unique_id": round(unique, 4),
            "email": round(email, 4),
            "account": round(account, 4),
            "name": round(name_s, 4),
            "org_context": round(org, 4),
        }
        return min(1.0, score), fields

    def _rule_project(self, a, b, n_a, n_b):
        w = PROJECT_FIELD_WEIGHTS
        name_s = name_similarity(a.get("name"), b.get("name"))
        owners_a = self._owners(a, n_a)
        owners_b = self._owners(b, n_b)
        owner_s = _known_jaccard(owners_a, owners_b)
        members_a = self._endpoints(n_a, ("WORKS_ON", "OWNER", "INVOLVED_IN"))
        members_b = self._endpoints(n_b, ("WORKS_ON", "OWNER", "INVOLVED_IN"))
        member_s = _known_jaccard(members_a, members_b)
        time_s = _time_overlap(a, b)
        res_s = _known_jaccard(
            self._neighbor_names(n_a, "Resource"),
            self._neighbor_names(n_b, "Resource"),
        )
        kn_s = _known_jaccard(
            self._neighbor_names(n_a, "Knowledge"),
            self._neighbor_names(n_b, "Knowledge"),
        )
        emb = ngram_cosine(
            f"{a.get('name') or ''} {a.get('description') or ''}",
            f"{b.get('name') or ''} {b.get('description') or ''}",
        )
        parts = {
            "name": (w["name"], name_s),
            "owner": (w["owner"], owner_s),
            "members": (w["members"], member_s),
            "time": (w["time"], time_s),
            "resources": (w["resources"], res_s),
            "knowledge": (w["knowledge"], kn_s),
            "embedding": (w["embedding"], emb),
        }
        score, fields = _weighted_known(parts)
        return score, fields

    def _rule_resource(self, a, b, n_a, n_b):
        w = RESOURCE_FIELD_WEIGHTS
        name_s = name_similarity(a.get("name"), b.get("name"))
        ua = url_key(a.get("url") or a.get("repo") or a.get("repository"))
        ub = url_key(b.get("url") or b.get("repo") or b.get("repository"))
        url_s = 1.0 if ua and ub and ua == ub else (name_s if not ua and not ub else 0.0)
        type_s = 1.0 if _same(a.get("category") or a.get("type"), b.get("category") or b.get("type")) and (a.get("category") or a.get("type")) else 0.4
        proj_s = jaccard(self._neighbor_names(n_a, "Project"), self._neighbor_names(n_b, "Project"))
        tech_s = name_similarity(a.get("tech_stack") or a.get("domain") or "", b.get("tech_stack") or b.get("domain") or "")
        emb = ngram_cosine(a.get("name"), b.get("name"))
        score = (
            w["name"] * name_s
            + w["url"] * url_s
            + w["type"] * type_s
            + w["project"] * proj_s
            + w["tech"] * tech_s
            + w["embedding"] * emb
        )
        fields = {
            "name": round(name_s, 4),
            "url": round(url_s, 4),
            "type": round(type_s, 4),
            "project": round(proj_s, 4),
            "tech": round(tech_s, 4),
            "embedding": round(emb, 4),
        }
        return min(1.0, score), fields

    def _rule_knowledge(self, a, b, n_a, n_b):
        w = KNOWLEDGE_FIELD_WEIGHTS
        title_s = name_similarity(a.get("name"), b.get("name"))
        topic_s = name_similarity(a.get("domain") or a.get("topic") or "", b.get("domain") or b.get("topic") or "")
        proj_s = jaccard(self._neighbor_names(n_a, "Project"), self._neighbor_names(n_b, "Project"))
        author_s = jaccard(
            self._endpoints(n_a, ("HAS_KNOWLEDGE",)),
            self._endpoints(n_b, ("HAS_KNOWLEDGE",)),
        )
        text_a = f"{a.get('name') or ''} {a.get('description') or ''} {a.get('domain') or ''}"
        text_b = f"{b.get('name') or ''} {b.get('description') or ''} {b.get('domain') or ''}"
        emb = ngram_cosine(text_a, text_b)
        cite_s = proj_s
        score = (
            w["embedding"] * emb
            + w["title"] * title_s
            + w["topic"] * topic_s
            + w["project"] * proj_s
            + w["author"] * author_s
            + w["citation"] * cite_s
        )
        fields = {
            "embedding": round(emb, 4),
            "title": round(title_s, 4),
            "topic": round(topic_s, 4),
            "project": round(proj_s, 4),
            "author": round(author_s, 4),
            "citation": round(cite_s, 4),
            "name": round(title_s, 4),
        }
        return min(1.0, score), fields

    def _rule_event(self, a, b, n_a, n_b):
        w = EVENT_FIELD_WEIGHTS
        type_s = 1.0 if _same(a.get("event_type") or a.get("type"), b.get("event_type") or b.get("type")) else 0.0
        ta = (a.get("time") or "")[:16]
        tb = (b.get("time") or "")[:16]
        time_s = 1.0 if ta and tb and ta == tb else 0.0
        subj_s = jaccard(self._endpoints(n_a, ("INVOLVED_IN",)), self._endpoints(n_b, ("INVOLVED_IN",)))
        obj_s = name_similarity(a.get("object") or "", b.get("object") or "")
        proj_s = jaccard(self._neighbor_names(n_a, "Project"), self._neighbor_names(n_b, "Project"))
        action_s = name_similarity(
            a.get("description") or a.get("name") or "",
            b.get("description") or b.get("name") or "",
        )
        src_s = 1.0 if _same(a.get("source") or a.get("id"), b.get("source") or b.get("id")) else 0.0
        score = (
            w["type"] * type_s
            + w["time"] * time_s
            + w["subject"] * subj_s
            + w["object"] * obj_s
            + w["project"] * proj_s
            + w["action"] * action_s
            + w["source"] * src_s
        )
        fields = {
            "type": round(type_s, 4),
            "time": round(time_s, 4),
            "subject": round(subj_s, 4),
            "object": round(obj_s, 4),
            "project": round(proj_s, 4),
            "action": round(action_s, 4),
            "source": round(src_s, 4),
            "name": round(action_s, 4),
        }
        return min(1.0, score), fields

    def _semantic_layer(self, a, b, entity_type):
        text_a = " ".join(str(a.get(k) or "") for k in ("name", "description", "domain", "theme", "category"))
        text_b = " ".join(str(b.get(k) or "") for k in ("name", "description", "domain", "theme", "category"))
        score = ngram_cosine(text_a, text_b)
        return score, [{
            "method": "char_ngram_cosine",
            "score": round(score, 4),
            "note": "P0 使用字符 n-gram 作为 embedding 代理，不由 LLM 判定是否同一实体",
        }]

    def _graph_layer(self, a, b, n_a, n_b):
        ids_a = self._other_ids(a.get("id"), n_a)
        ids_b = self._other_ids(b.get("id"), n_b)
        shared = ids_a & ids_b
        score = jaccard(ids_a, ids_b)
        rel_types_a = {e.get("relation") for e in n_a or []}
        rel_types_b = {e.get("relation") for e in n_b or []}
        type_s = jaccard(rel_types_a, rel_types_b)
        combined = 0.7 * score + 0.3 * type_s if (ids_a or ids_b) else 0.0
        evidence = []
        for nid in list(shared)[:8]:
            evidence.append({"neighbor_id": nid, "reason": "共同邻居"})
        return combined, evidence

    def _neighbors(self, node_id):
        if not self.graph or not node_id:
            return []
        try:
            return self.graph.neighbors(node_id)
        except Exception:
            return []

    def _neighbor_ids(self, node_id):
        return self._other_ids(node_id, self._neighbors(node_id))

    def _other_ids(self, node_id, edges):
        ids = set()
        for e in edges or []:
            if e.get("source") == node_id:
                ids.add(e.get("target"))
            elif e.get("target") == node_id:
                ids.add(e.get("source"))
        ids.discard(node_id)
        return ids

    def _owners(self, node, edges):
        owners = set()
        if node.get("owner_id"):
            owners.add(str(node["owner_id"]))
        if node.get("owner"):
            owners.add(normalize_text(node["owner"]))
        for e in edges or []:
            if e.get("relation") == "OWNER":
                owners.add(e.get("source"))
        return {x for x in owners if x}

    def _endpoints(self, edges, relations):
        allowed = set(relations)
        ids = set()
        for e in edges or []:
            if e.get("relation") in allowed:
                ids.add(e.get("source"))
                ids.add(e.get("target"))
        return ids

    def _shared_targets(self, n_a, n_b, relation):
        ta = {e.get("target") for e in n_a or [] if e.get("relation") == relation}
        tb = {e.get("target") for e in n_b or [] if e.get("relation") == relation}
        return {x for x in (ta & tb) if x}

    def _neighbor_names(self, edges, node_type):
        if not self.graph:
            return set()
        names = set()
        for e in edges or []:
            for nid in (e.get("source"), e.get("target")):
                node = self.graph.get_node(nid) if nid else None
                if node and node.get("type") == node_type:
                    names.add(node.get("id"))
        return names

    def _exact_id_hit(self, a, b):
        for key in ("employee_id", "enterprise_id", "email", "enterprise_wechat", "github_account"):
            if _same(a.get(key), b.get(key)) and a.get(key):
                return True
        return False

    def _has_exact_keys(self, a, b, entity_type):
        if entity_type == "PERSON":
            return any(a.get(k) or b.get(k) for k in PERSON_ID_KEYS)
        if entity_type == "PROJECT":
            return bool(a.get("project_id") or b.get("project_id"))
        if entity_type == "RESOURCE":
            return bool(a.get("url") or a.get("repo") or b.get("url") or b.get("repo"))
        return False


def _known_jaccard(a, b):
    if not a and not b:
        return None
    return jaccard(a, b)


def _weighted_known(parts):
    used = {k: v for k, v in parts.items() if v[1] is not None}
    total_w = sum(w for w, _ in used.values()) or 1.0
    score = sum(w / total_w * s for w, s in used.values())
    fields = {k: round(s, 4) if s is not None else 0.0 for k, (_, s) in parts.items()}
    return min(1.0, score), fields


def _scalar(v):
    if v is None:
        return ""
    return str(v).strip().lower()


def _same(a, b):
    sa, sb = _scalar(a), _scalar(b)
    return bool(sa) and sa == sb


def _time_overlap(a, b):
    def span(n):
        start = (n.get("start_date") or n.get("start") or n.get("time") or "")[:10]
        end = (n.get("end_date") or n.get("end") or start)[:10]
        return start, end
    a0, a1 = span(a)
    b0, b1 = span(b)
    if not (a0 and b0):
        return None if not a0 and not b0 else 0.0
    if a1 < b0 or b1 < a0:
        return 0.0
    try:
        from datetime import datetime
        fmt = "%Y-%m-%d"
        da0, da1 = datetime.strptime(a0, fmt), datetime.strptime(a1 or a0, fmt)
        db0, db1 = datetime.strptime(b0, fmt), datetime.strptime(b1 or b0, fmt)
        lo = max(da0, db0)
        hi = min(da1, db1)
        inter = max(0, (hi - lo).days + 1)
        union = (max(da1, db1) - min(da0, db0)).days + 1
        return inter / union if union else 0.0
    except ValueError:
        return 1.0 if a0 == b0 else 0.0


def build_alias_index(alias_rows):
    index = {}
    for row in alias_rows or []:
        key = (row.get("entity_type"), row.get("normalized_value"))
        index[key] = row
    return index
