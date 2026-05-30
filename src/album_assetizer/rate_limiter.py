"""线程安全的速率限制器，基于单调时钟控制每分钟请求数。"""

from __future__ import annotations

import threading
import time

from album_assetizer.models import StopRequested


class RateLimiter:
    def __init__(self, rpm: int, stop_event: threading.Event) -> None:
        self.stop_event = stop_event
        self._lock = threading.Lock()
        self._rpm = max(1, rpm)
        self._next_allowed_at = 0.0

    def set_rpm(self, rpm: int) -> None:
        with self._lock:
            self._rpm = max(1, rpm)

    def get_rpm(self) -> int:
        with self._lock:
            return self._rpm

    def acquire(self) -> None:
        """阻塞直到速率限制允许发出下一个请求，若收到停止信号则抛出 StopRequested。"""
        while not self.stop_event.is_set():
            with self._lock:
                now = time.monotonic()
                interval = 60.0 / self._rpm
                if now >= self._next_allowed_at:
                    self._next_allowed_at = now + interval
                    return
                wait_for = self._next_allowed_at - now
            if wait_for > 0:
                self.stop_event.wait(min(wait_for, 1.0))
        raise StopRequested("收到停止信号，速率限制器中止")
