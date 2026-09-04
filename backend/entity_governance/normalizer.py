"""EntityNormalizer —— 标准化只用于匹配，不改写原始名称。"""

import re
import unicodedata
from difflib import SequenceMatcher

# 匹配用噪声后缀 / 版本号（不改原始名）
_NOISE_SUFFIXES = (
    "系统", "项目", "平台", "工程", "产品", "服务", "中心", "应用",
    "模块", "组件", "工具", "网关", "方案", "设计", "文档",
    "system", "project", "platform", "service", "app", "tool",
    "gateway", "kit",
)

_VERSION_RE = re.compile(
    r"(?:v|ver|version)?\s*\d+(?:\.\d+)*$|（.*?）|\(.*?\)",
    re.IGNORECASE,
)


def _fullwidth_to_halfwidth(text: str) -> str:
    out = []
    for ch in text:
        code = ord(ch)
        if code == 0x3000:
            out.append(" ")
        elif 0xFF01 <= code <= 0xFF5E:
            out.append(chr(code - 0xFEE0))
        else:
            out.append(ch)
    return "".join(out)


def normalize_text(value) -> str:
    """大小写 / 空白 / 中英文标点 / 全角半角 / 特殊符号。"""
    if value is None:
        return ""
    text = unicodedata.normalize("NFKC", str(value))
    text = _fullwidth_to_halfwidth(text)
    text = text.strip().lower()
    text = text.replace("—", "-").replace("–", "-").replace("＿", "_")
    text = re.sub(r"[\s\u00a0\u3000]+", "", text)
    text = re.sub(r"[·•・、，。；：！？“”‘’\"'`~!@#$%^&*+=|\\/<>\[\]{}]+", "", text)
    return text


def strip_noise(normalized: str) -> str:
    """去掉版本号和常见实体后缀，仅用于召回/匹配。"""
    text = normalized or ""
    text = _VERSION_RE.sub("", text)
    changed = True
    while changed and text:
        changed = False
        for suf in _NOISE_SUFFIXES:
            if text.endswith(suf) and len(text) - len(suf) >= 2:
                text = text[: -len(suf)]
                changed = True
                break
    return text


def match_key(value) -> str:
    return strip_noise(normalize_text(value))


_CN_EN = {
    "gateway": "网关",
    "tool": "工具",
    "system": "系统",
    "platform": "平台",
    "service": "服务",
    "project": "项目",
    "cluster": "集群",
    "model": "模型",
    "data": "数据",
    "customer": "客户",
    "budget": "预算",
    "permission": "权限",
    "auth": "权限",
}

_EN_CN = {v: k for k, v in _CN_EN.items()}


def tokenize(value) -> list:
    raw = str(value or "")
    raw = _fullwidth_to_halfwidth(unicodedata.normalize("NFKC", raw))
    parts = re.split(r"[\s_\-./·]+", raw.strip())
    tokens = []
    for part in parts:
        if not part:
            continue
        camel = re.sub(r"([a-z])([A-Z])", r"\1 \2", part)
        for tok in camel.split():
            n = normalize_text(tok)
            if n:
                tokens.append(n)
                syn = _CN_EN.get(n) or _EN_CN.get(tok)
                if syn:
                    tokens.append(normalize_text(syn))
            if re.search(r"[\u4e00-\u9fff]", tok) and len(tok) >= 2:
                for i in range(len(tok) - 1):
                    piece = tok[i:i + 2]
                    tokens.append(normalize_text(piece))
                    if piece in _EN_CN:
                        tokens.append(_EN_CN[piece])
    key = match_key(raw)
    if key:
        tokens.append(key)
    return list(dict.fromkeys(tokens))


def char_ngrams(text: str, n=2) -> set:
    s = normalize_text(text)
    if len(s) < n:
        return {s} if s else set()
    return {s[i:i + n] for i in range(len(s) - n + 1)}


def ngram_cosine(a, b, n=2) -> float:
    sa, sb = char_ngrams(a, n), char_ngrams(b, n)
    if not sa or not sb:
        return 0.0
    inter = len(sa & sb)
    return inter / ((len(sa) * len(sb)) ** 0.5)


def token_jaccard(a, b) -> float:
    ta, tb = set(tokenize(a)), set(tokenize(b))
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def name_similarity(a, b) -> float:
    """综合字符 / 包含 / 噪声剥离后的名称相似度 0-1。"""
    if not a or not b:
        return 0.0
    na, nb = normalize_text(a), normalize_text(b)
    if na == nb:
        return 1.0
    sa, sb = strip_noise(na), strip_noise(nb)
    if sa and sb and sa == sb:
        return 0.97
    scores = [
        SequenceMatcher(None, na, nb).ratio(),
        SequenceMatcher(None, sa, sb).ratio() if sa and sb else 0.0,
        token_jaccard(a, b),
        ngram_cosine(a, b),
    ]
    tj = token_jaccard(a, b)
    if tj >= 0.45:
        scores.append(0.75 + 0.2 * tj)
    if sa and sb:
        shorter, longer = (sa, sb) if len(sa) <= len(sb) else (sb, sa)
        if shorter and shorter in longer and len(shorter) >= 2:
            ratio = len(shorter) / len(longer)
            scores.append(0.82 + 0.14 * ratio)
    return max(scores)


def person_name_similarity(a, b) -> float:
    """Angel / Angel Zhang / 张Angel / A.Zhang。"""
    base = name_similarity(a, b)
    ta = [t for t in tokenize(a) if len(t) >= 1]
    tb = [t for t in tokenize(b) if len(t) >= 1]
    if not ta or not tb:
        return base
    # 英文名：短名被长名包含
    na, nb = normalize_text(a), normalize_text(b)
    if na and nb and (na in nb or nb in na) and min(len(na), len(nb)) >= 2:
        base = max(base, 0.86)
    # 首字母：a.zhang vs angel zhang
    initials_a = "".join(t[0] for t in ta if t)
    initials_b = "".join(t[0] for t in tb if t)
    if len(initials_a) >= 2 and initials_a == initials_b:
        base = max(base, 0.78)
    overlap = set(ta) & set(tb)
    if overlap and min(len(ta), len(tb)) >= 1:
        base = max(base, 0.55 + 0.4 * len(overlap) / max(len(ta), len(tb)))
    return min(1.0, base)


def url_key(value) -> str:
    text = (value or "").strip().lower()
    text = re.sub(r"^https?://", "", text)
    text = text.rstrip("/")
    return normalize_text(text)


def jaccard(a: set, b: set) -> float:
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)
