"""推演共用：分数裁剪、风险分级、可解释判断。分数由规则计算，不由 LLM 决定。"""

from timeutil import now_iso, days_ago

from growth.scores import _parse_time


def clip(v, lo=0, hi=100):
    return int(max(lo, min(hi, round(v))))


def risk_level(score):
    s = int(score or 0)
    if s >= 75:
        return "high"
    if s >= 50:
        return "medium"
    return "low"


def risk_label(level):
    return {"high": "高", "medium": "中", "low": "低"}.get(level, "中")


def delta_arrow(v):
    if v >= 12:
        return "↑↑"
    if v > 0:
        return "↑"
    if v <= -12:
        return "↓↓"
    if v < 0:
        return "↓"
    return "→"


def judgment(conclusion, reason, evidence=None, source="rule"):
    times = [e.get("time") for e in (evidence or []) if e.get("time")]
    return {
        "conclusion": conclusion,
        "reason": reason,
        "evidence": evidence or [],
        "time": times[-1] if times else now_iso(),
        "source": source,
        "kind": "风险预测" if "风险" in (conclusion or "") else "推演结论",
    }


def cite(source, title, text="", time=None, source_id=None):
    return {
        "source": source,
        "title": title,
        "text": (text or "")[:240],
        "time": time,
        "source_id": source_id,
    }


def in_window(raw, since):
    t = _parse_time(raw)
    if not t:
        return True
    return t >= since


def parse_time(raw):
    return _parse_time(raw)
