"""Survivorship —— 按来源可信度合并字段，冲突值保留不覆盖。"""

from .types import SOURCE_RANK


PROTECTED_KEYS = {
    "id", "type", "entity_status", "canonical_entity_id",
    "merge_batch_id", "merged_at", "updated_at",
}

CONCAT_KEYS = {"description", "evidence_text", "notes", "summary"}
MAX_LIST = {"skills", "required_skills", "aliases"}


def source_rank(source: str) -> int:
    if not source:
        return 0
    key = str(source).lower()
    if key in SOURCE_RANK:
        return SOURCE_RANK[key]
    for k, v in SOURCE_RANK.items():
        if k in key:
            return v
    return 15


def recommend_canonical(left: dict, right: dict, edges_left=None, edges_right=None) -> dict:
    """系统推荐主实体：来源最多 / 最新 / 关系最多 / 信息完整度最高。"""
    def score(node, edges):
        completeness = sum(1 for k, v in node.items() if v not in (None, "", [], {}))
        rel_n = len(edges or [])
        sources = int(node.get("source_count") or 1)
        updated = str(node.get("updated_at") or "")
        return (
            sources * 10
            + rel_n * 3
            + completeness
            + (1 if updated else 0),
            updated,
            rel_n,
            completeness,
        )

    sl = score(left, edges_left)
    sr = score(right, edges_right)
    pick = left if sl >= sr else right
    other = right if pick is left else left
    reasons = []
    if int(pick.get("source_count") or 1) > int(other.get("source_count") or 1):
        reasons.append("来源最多")
    if len(edges_left or []) != len(edges_right or []):
        more = "关系最多"
        if (len(edges_left or []) > len(edges_right or []) and pick is left) or (
            len(edges_right or []) > len(edges_left or []) and pick is right
        ):
            reasons.append(more)
    if str(pick.get("updated_at") or "") > str(other.get("updated_at") or ""):
        reasons.append("最新")
    reasons.append("信息完整度较高" if "来源最多" not in reasons else "综合完整度更高")
    return {
        "entity_id": pick.get("id") or pick.get("entity_id"),
        "name": pick.get("name") or pick.get("canonical_name"),
        "reasons": reasons,
    }


def merge_fields(canonical: dict, incoming: dict, incoming_source="event"):
    """
    合并到 canonical。不直接覆盖：低可信来源写入 metadata.conflicts。
    返回 (merged_node, field_log)
    """
    merged = dict(canonical)
    log = []
    conflicts = list(((canonical.get("metadata") or {}) if isinstance(canonical.get("metadata"), dict) else {}).get("conflicts") or [])
    src_rank = source_rank(incoming_source)
    canon_src = canonical.get("canonical_source") or canonical.get("source") or "inferred"
    canon_rank = source_rank(canon_src)

    for key, new_val in incoming.items():
        if key in PROTECTED_KEYS or new_val in (None, "", [], {}):
            continue
        old_val = merged.get(key)
        if old_val in (None, "", [], {}):
            merged[key] = new_val
            log.append({"field": key, "action": "fill", "value": new_val, "source": incoming_source})
            continue
        if old_val == new_val:
            continue
        if key in CONCAT_KEYS:
            old_s, new_s = str(old_val), str(new_val)
            if new_s not in old_s:
                merged[key] = f"{old_s}\n{new_s}".strip()
                log.append({"field": key, "action": "concat", "source": incoming_source})
            continue
        if key in MAX_LIST and isinstance(old_val, list) and isinstance(new_val, list):
            seen = list(old_val)
            for x in new_val:
                if x not in seen:
                    seen.append(x)
            merged[key] = seen
            log.append({"field": key, "action": "union", "source": incoming_source})
            continue
        if src_rank > canon_rank:
            conflicts.append({
                "field": key,
                "kept": new_val,
                "rejected": old_val,
                "kept_source": incoming_source,
                "rejected_source": canon_src,
                "status": "SURVIVED",
            })
            merged[key] = new_val
            log.append({"field": key, "action": "replace_higher_trust", "from": old_val, "to": new_val})
        else:
            conflicts.append({
                "field": key,
                "kept": old_val,
                "rejected": new_val,
                "kept_source": canon_src,
                "rejected_source": incoming_source,
                "status": "CONFLICTED",
            })
            log.append({"field": key, "action": "keep_canonical", "rejected": new_val, "source": incoming_source})

    meta = dict(merged.get("metadata") or {}) if isinstance(merged.get("metadata"), dict) else {}
    if conflicts:
        meta["conflicts"] = conflicts[-40:]
    merged["metadata"] = meta
    return merged, log
