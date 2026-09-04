"""关系分值详情：正向/负向证据、变化原因、时间线。分值是证据计算结果。"""

from datetime import datetime, timedelta

from timeutil import now_naive

from database import get_all_members, get_relationship_logs

from .analyzer import DIMENSIONS
from . import repository as repo
from .taxonomy import tag_label, type_label

BASE_SCORE = 50
PERIOD_DAYS = 7


def _clip(v):
    return int(max(0, min(100, round(v))))


def _parse_time(raw):
    if not raw:
        return None
    text = str(raw).replace("Z", "").replace(" ", "T")
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(text[:len(fmt) + (1 if "T" in fmt else 0)][:19], fmt if "T" in text else "%Y-%m-%d")
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(text[:19])
    except ValueError:
        return None


def _member_name(mmap, mid):
    m = mmap.get(mid) or {}
    return m.get("name") or mid


def _legacy_as_evidence():
    """把旧 relationship_logs 映射成信任/情绪证据，保证历史数据可解释。"""
    logs = get_relationship_logs(include_hypothetical=False)
    out = []
    for log in logs:
        event_id = log.get("event_id")
        # 若该事件已有新证据，不再用旧日志重复计算信任
        existing = repo.list_relationship_evidence(event_id=event_id)
        has_trust = any(e.get("dimension") in ("trust", "sentiment") for e in existing)
        if has_trust:
            continue
        trust = int(log.get("trust_delta") or 0)
        senti = int(log.get("sentiment_delta") or 0)
        reason = log.get("tag") or log.get("reason") or "历史关系增量"
        base = {
            "event_id": event_id,
            "from_member_id": log.get("from_member_id"),
            "to_member_id": log.get("to_member_id"),
            "event_time": log.get("event_time"),
            "facts": "",
            "result": "",
            "impact": reason,
            "event_type": "",
            "event_tag": "",
            "raw_summary": "",
            "legacy": True,
        }
        if trust:
            out.append({
                **base,
                "dimension": "trust",
                "delta": trust,
                "polarity": "positive" if trust >= 0 else "negative",
                "reason": reason,
            })
        if senti:
            out.append({
                **base,
                "dimension": "sentiment",
                "delta": senti,
                "polarity": "positive" if senti >= 0 else "negative",
                "reason": reason,
            })
    return out


def all_evidence(from_id=None, to_id=None, dimension=None):
    items = repo.list_relationship_evidence(from_id=from_id, to_id=to_id, dimension=dimension)
    if not items:
        legacy = _legacy_as_evidence()
        return [
            e for e in legacy
            if (not from_id or e["from_member_id"] == from_id)
            and (not to_id or e["to_member_id"] == to_id)
            and (not dimension or e["dimension"] == dimension)
        ]
    # 补历史：仅对还没有任何新证据的 pair+dimension
    covered = {(e["from_member_id"], e["to_member_id"], e["dimension"]) for e in items}
    for e in _legacy_as_evidence():
        key = (e["from_member_id"], e["to_member_id"], e["dimension"])
        if key in covered:
            continue
        if from_id and e["from_member_id"] != from_id:
            continue
        if to_id and e["to_member_id"] != to_id:
            continue
        if dimension and e["dimension"] != dimension:
            continue
        items.append(e)
    return items


def compute_score(evidences, at_time=None):
    total = BASE_SCORE
    for e in evidences:
        t = _parse_time(e.get("event_time"))
        if at_time and t and t > at_time:
            continue
        total += int(e.get("delta") or 0)
    return _clip(total)


def _period_delta(evidences, days=PERIOD_DAYS):
    now = now_naive()
    start = now - timedelta(days=days)
    current = compute_score(evidences, now)
    previous = compute_score(evidences, start)
    return current, previous, current - previous


def _timeline(evidences):
    acc = BASE_SCORE
    points = [{"time": None, "score": BASE_SCORE, "event_id": None, "delta": 0, "reason": "初始分值"}]
    for e in evidences:
        acc = _clip(acc + int(e.get("delta") or 0))
        points.append({
            "time": e.get("event_time"),
            "score": acc,
            "event_id": e.get("event_id"),
            "delta": int(e.get("delta") or 0),
            "reason": e.get("reason") or "",
            "dimension": e.get("dimension"),
        })
    return points


def _serialize_item(e, mmap):
    type_id = e.get("event_type") or ""
    tag_id = e.get("event_tag") or ""
    delta = int(e.get("delta") or 0)
    return {
        "id": e.get("id"),
        "event_id": e.get("event_id"),
        "event_time": e.get("event_time"),
        "from_member_id": e.get("from_member_id"),
        "from_name": _member_name(mmap, e.get("from_member_id")),
        "to_member_id": e.get("to_member_id"),
        "to_name": _member_name(mmap, e.get("to_member_id")),
        "dimension": e.get("dimension"),
        "dimension_label": DIMENSIONS.get(e.get("dimension"), e.get("dimension")),
        "delta": delta,
        "polarity": e.get("polarity") or ("positive" if delta >= 0 else "negative"),
        "reason": e.get("reason") or "",
        "facts": e.get("facts") or e.get("event_facts") or "",
        "result": e.get("result") or e.get("event_result") or "",
        "impact": e.get("impact") or "",
        "event_title": tag_label(type_id, tag_id) or e.get("scene") or "事件",
        "event_type_label": type_label(type_id),
        "raw_summary": e.get("raw_summary") or "",
        "legacy": bool(e.get("legacy")),
    }


def pair_overview(from_id, to_id):
    mmap = {m["id"]: m for m in get_all_members()}
    items = all_evidence(from_id, to_id)
    by_dim = {}
    for e in items:
        by_dim.setdefault(e.get("dimension") or "trust", []).append(e)
    dimensions = []
    for dim, label in DIMENSIONS.items():
        evs = by_dim.get(dim) or []
        if not evs and dim not in ("trust", "professional_trust"):
            continue
        current, previous, delta = _period_delta(evs)
        pos = [x for x in evs if int(x.get("delta") or 0) > 0]
        neg = [x for x in evs if int(x.get("delta") or 0) < 0]
        dimensions.append({
            "id": dim,
            "label": label,
            "current": current,
            "previous": previous,
            "period_delta": delta,
            "trend": "up" if delta > 0 else ("down" if delta < 0 else "flat"),
            "positive_count": len(pos),
            "negative_count": len(neg),
        })
    if not dimensions:
        dimensions.append({
            "id": "trust",
            "label": "信任",
            "current": BASE_SCORE,
            "previous": BASE_SCORE,
            "period_delta": 0,
            "trend": "flat",
            "positive_count": 0,
            "negative_count": 0,
        })
    return {
        "from_member_id": from_id,
        "from_name": _member_name(mmap, from_id),
        "to_member_id": to_id,
        "to_name": _member_name(mmap, to_id),
        "dimensions": dimensions,
    }


def score_detail(from_id, to_id, dimension="trust"):
    mmap = {m["id"]: m for m in get_all_members()}
    evs = all_evidence(from_id, to_id, dimension)
    current, previous, delta = _period_delta(evs)
    serialized = [_serialize_item(e, mmap) for e in evs]
    positive = [x for x in serialized if x["delta"] > 0]
    negative = [x for x in serialized if x["delta"] < 0]
    positive.reverse()
    negative.reverse()
    return {
        "from_member_id": from_id,
        "from_name": _member_name(mmap, from_id),
        "to_member_id": to_id,
        "to_name": _member_name(mmap, to_id),
        "dimension": dimension,
        "dimension_label": DIMENSIONS.get(dimension, dimension),
        "current": current,
        "previous": previous,
        "period_days": PERIOD_DAYS,
        "period_delta": delta,
        "trend": "up" if delta > 0 else ("down" if delta < 0 else "flat"),
        "positive": positive,
        "negative": negative,
        "why": {
            "growth": [f"{'+' if x['delta'] > 0 else ''}{x['delta']}  {x['reason']}" for x in positive],
            "decline": [f"{x['delta']}  {x['reason']}" for x in negative],
        },
        "timeline": _timeline(evs),
        "items": list(reversed(serialized)),
    }


def evidence_item(evidence_id):
    mmap = {m["id"]: m for m in get_all_members()}
    with __import__("database").get_db() as conn:
        row = conn.execute(
            """SELECT re.*, te.event_time, te.event_type, te.event_tag, te.raw_summary,
                      te.background, te.facts AS event_facts, te.result AS event_result,
                      te.judgement, te.scene, te.expected, te.difference, te.actions,
                      te.evidence AS event_evidence
               FROM relationship_evidence re
               JOIN team_events te ON re.event_id = te.id
               WHERE re.id = ?""",
            (evidence_id,),
        ).fetchone()
    if not row:
        return None
    item = _serialize_item(dict(row), mmap)
    event = repo.get_event(item["event_id"])
    item["event"] = event
    return item


def grid_display(at_time=None):
    """给总览网格：在原 trust/sentiment 之外提供 0-100 可解释分值。"""
    members = get_all_members()
    ids = [m["id"] for m in members]
    grid = {}
    for a in ids:
        for b in ids:
            if a == b:
                continue
            evs = all_evidence(a, b, "trust")
            current, previous, delta = _period_delta(evs)
            grid[f"{a}→{b}"] = {
                "trust_score": current,
                "period_delta": delta,
                "previous": previous,
                "trend": "up" if delta > 0 else ("down" if delta < 0 else "flat"),
            }
    return grid
