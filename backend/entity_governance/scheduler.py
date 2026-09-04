"""每天一次实体重复检测。"""

import threading
import time
from datetime import timedelta

from timeutil import now_naive, today as beijing_today

from . import service

_started = False


def start_scheduler():
    global _started
    if _started:
        return
    _started = True
    threading.Thread(target=_loop, daemon=True).start()
    print("[entity-governance] 已启动每日北京时间 02:30 重复检测")


def _loop():
    while True:
        try:
            now = now_naive()
            target = now.replace(hour=2, minute=30, second=0, microsecond=0)
            if now >= target:
                target += timedelta(days=1)
            wait = max(5, (target - now_naive()).total_seconds())
            time.sleep(min(wait, 3600))
            if now_naive() < target - timedelta(seconds=2):
                continue
            today = beijing_today()
            print("[entity-governance] 到达每日检测窗口")
            service.detect_duplicates(force=True, auto_merge=True, operator=f"scheduler-{today}")
            time.sleep(70)
        except Exception as e:
            print(f"[entity-governance] 调度异常: {e}")
            time.sleep(30)
