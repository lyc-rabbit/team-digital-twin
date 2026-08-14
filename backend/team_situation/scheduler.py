"""每天 12:00 自动跑态势分析。"""

import threading
import time
from datetime import datetime, timedelta

from . import repository as repo
from .pipeline import start_analyze


_started = False


def start_scheduler():
    global _started
    if _started:
        return
    _started = True
    threading.Thread(target=_loop, daemon=True).start()
    print("[situation] 已启动每日 12:00 调度")


def _loop():
    while True:
        try:
            cfg = repo.get_config()
            enabled = cfg.get("scheduler_enabled", True)
            hour = int(cfg.get("scheduler_hour", 12) or 12)
            minute = int(cfg.get("scheduler_minute", 0) or 0)
            now = datetime.now()
            target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            if now >= target:
                target += timedelta(days=1)
            wait = max(5, (target - datetime.now()).total_seconds())
            time.sleep(min(wait, 3600))
            if datetime.now() < target - timedelta(seconds=2):
                continue
            if not enabled:
                continue
            today = datetime.now().strftime("%Y-%m-%d")
            print("[situation] 到达每日分析窗口，启动 pipeline")
            start_analyze(idempotency_key=f"scheduler-{today}", trigger="scheduler")
            time.sleep(70)
        except Exception as e:
            print(f"[situation] 调度异常: {e}")
            time.sleep(30)
