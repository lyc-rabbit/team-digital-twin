"""本进程绕过本机 7897 代理。

只改当前 Python 进程的 os.environ，不写用户/系统环境变量，
其它仍走 7897 的程序不受影响。
"""

import os

LOCAL_PROXY_PORT = "7897"
_PROXY_KEY_SUFFIXES = frozenset({
    "http_proxy", "https_proxy", "all_proxy", "ftp_proxy",
    "ws_proxy", "wss_proxy", "no_proxy",
})


def _is_proxy_key(key: str) -> bool:
    return key.lower() in _PROXY_KEY_SUFFIXES


def _points_at_local_proxy(value: str) -> bool:
    text = (value or "").strip().lower()
    if not text:
        return False
    return f":{LOCAL_PROXY_PORT}" in text or text.endswith(LOCAL_PROXY_PORT)


def disable_local_proxy():
    """去掉指向本机 7897 的代理变量，供本进程内 HTTP / Bolt 直连。"""
    removed = []
    for key in list(os.environ.keys()):
        if not _is_proxy_key(key):
            continue
        if key.lower() == "no_proxy":
            continue
        if _points_at_local_proxy(os.environ.get(key, "")):
            removed.append(key)
            del os.environ[key]
    if removed:
        print(f"[proxy] 本进程已忽略 :{LOCAL_PROXY_PORT} 代理: {', '.join(removed)}")
    return removed
