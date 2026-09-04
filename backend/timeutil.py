"""全站统一使用北京时间（UTC+8）。中国无夏令时。

存储格式：YYYY-MM-DDTHH:MM:SS（无时区后缀），语义一律为北京时间。
SQLite 的 datetime('now') / date('now') 是 UTC，查询与默认值必须加 '+8 hours'。
"""

from datetime import datetime, timedelta, timezone

BEIJING = timezone(timedelta(hours=8), name="Asia/Shanghai")
TZ_NAME = "Asia/Shanghai"
TZ_LABEL = "北京时间"
UTC_OFFSET = "+08:00"

SQLITE_NOW = "datetime('now','+8 hours')"
SQLITE_TODAY = "date('now','+8 hours')"


def now():
    """带时区的当前北京时间。"""
    return datetime.now(BEIJING)


def now_naive():
    """无时区的北京墙钟，用于和库内 naive 时间字符串比较。"""
    return now().replace(tzinfo=None)


def now_iso():
    return now_naive().strftime("%Y-%m-%dT%H:%M:%S")


def now_stamp(fmt="%Y-%m-%d %H:%M"):
    return now_naive().strftime(fmt)


def today():
    return now_naive().strftime("%Y-%m-%d")


def days_ago(n):
    return now_naive() - timedelta(days=int(n))


def today_minus_days(n):
    return days_ago(n).strftime("%Y-%m-%d")


def parse_day(value):
    """取 YYYY-MM-DD。空值表示开放区间一端。"""
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if "T" in text:
        text = text.split("T", 1)[0]
    if " " in text:
        text = text.split(" ", 1)[0]
    if len(text) >= 10 and text[4] == "-" and text[7] == "-":
        return text[:10]
    if len(text) == 7 and text[4] == "-":
        return text + "-01"
    return text


def interval_contains(valid_from, valid_to, when):
    """半开区间 [valid_from, valid_to)；valid_to 为空表示仍有效。"""
    day = parse_day(when)
    if not day:
        return True
    start = parse_day(valid_from) or "0001-01-01"
    end = parse_day(valid_to)
    if day < start:
        return False
    if end and day >= end:
        return False
    return True


def intervals_overlap(a_from, a_to, b_from, b_to):
    a0 = parse_day(a_from) or "0001-01-01"
    b0 = parse_day(b_from) or "0001-01-01"
    a1 = parse_day(a_to) or "9999-12-31"
    b1 = parse_day(b_to) or "9999-12-31"
    return a0 < b1 and b0 < a1


def intersect_interval(a_from, a_to, b_from, b_to):
    def _start(value):
        day = parse_day(value)
        if not day or day.startswith("0001"):
            return ""
        return day

    a0, b0 = _start(a_from), _start(b_from)
    if a0 and b0:
        start = max(a0, b0)
    else:
        start = a0 or b0
    ends = [x for x in (parse_day(a_to), parse_day(b_to)) if x]
    end = min(ends) if ends else ""
    if end and start and start >= end:
        return None
    return start, end or ""


def format_validity(valid_from, valid_to):
    start = parse_day(valid_from)
    if start and start.startswith("0001"):
        start = None
    end = parse_day(valid_to)
    return f"{start or '不限'}~{end or '永久'}"
