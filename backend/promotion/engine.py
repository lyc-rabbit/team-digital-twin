"""评分引擎：只消费 feature_scores + 权重，不调用 AI。"""

from .templates import (
    LAYER_DEFAULTS,
    BOSS_WEIGHTS,
    TEAM_WEIGHTS,
    REQUIREMENT_ALIASES,
    get_style,
)


def _norm(weights: dict) -> dict:
    total = sum(float(v) for v in weights.values()) or 1.0
    return {k: float(v) / total for k, v in weights.items()}


def _weighted(scores: dict, weights: dict) -> float:
    nw = _norm(weights)
    acc = 0.0
    for k, w in nw.items():
        acc += float(scores.get(k) or 0) * w
    return acc


def compute_layer_scores(features: dict, sub_weights: dict, style: dict, custom_requirements: list):
    boss_w = (sub_weights or {}).get("boss") or BOSS_WEIGHTS
    team_w = (sub_weights or {}).get("team") or TEAM_WEIGHTS
    boss = _weighted(features, boss_w)
    team = _weighted(features, team_w)

    role_keys = {
        "role_skill_match": 50,
        "role_assignment": 35,
        "role_coverage": 15,
    }
    role = _weighted(features, role_keys)

    custom_w = {}
    if custom_requirements:
        for req in custom_requirements:
            name = (req.get("name") or "").strip()
            key = REQUIREMENT_ALIASES.get(name) or _slug_key(name)
            custom_w[key] = float(req.get("weight") or 0)
    elif style:
        custom_w = dict(style.get("weights") or {})
    if not custom_w:
        custom_w = dict((get_style("tech_expert") or {}).get("weights") or {})
    custom = _weighted(features, custom_w)

    return {
        "boss": round(boss, 2),
        "team": round(team, 2),
        "role": round(role, 2),
        "custom": round(custom, 2),
        "trend": round(float(features.get("trend") or 50), 2),
    }


def compute_score(layer_scores: dict, layer_weights: dict) -> float:
    lw = dict(LAYER_DEFAULTS)
    lw.update(layer_weights or {})
    nw = _norm(lw)
    score = 0.0
    for key in ("boss", "team", "role", "custom"):
        score += nw.get(key, 0) * float(layer_scores.get(key) or 0)
    return round(max(0, min(100, score)), 2)


def compute_probability(score: float, features: dict, rank: int, total: int) -> float:
    trend = float(features.get("trend") or 50)
    conflict = float(features.get("conflict_risk") or 10)
    p = score * 0.82 + (trend - 50) * 0.25 - conflict * 0.08 + 8
    if total > 1 and rank == 1:
        p += 3
    return round(max(5, min(95, p)), 1)


def rank_candidates(rows, layer_weights):
    """rows: [{person_id, feature_scores, analysis_json, ...}] 就地计算 score/rank/probability。"""
    scored = []
    for row in rows:
        features = row.get("feature_scores") or {}
        layers = row.get("layer_scores") or {}
        if not layers:
            continue
        score = compute_score(layers, layer_weights)
        item = dict(row)
        item["score"] = score
        scored.append(item)
    scored.sort(key=lambda x: x["score"], reverse=True)
    total = len(scored)
    for i, item in enumerate(scored, start=1):
        item["rank"] = i
        item["promotion_probability"] = compute_probability(
            item["score"], item.get("feature_scores") or {}, i, total
        )
    return scored


def _slug_key(name: str) -> str:
    mapping = REQUIREMENT_ALIASES
    if name in mapping:
        return mapping[name]
    return "professional"
