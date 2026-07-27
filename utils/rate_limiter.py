import time
from collections import defaultdict
from typing import List
from .config_loader import get


class RateLimiter:
    """滑动窗口速率限制器"""

    def __init__(self, max_requests: int = 10, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._requests: dict[str, List[float]] = defaultdict(list)
        self._whitelist: set[str] = set()

    @classmethod
    def from_config(cls) -> "RateLimiter":
        max_req = int(get("llm.rate_limit_per_min", 10))
        window = 60
        return cls(max_requests=max_req, window_seconds=window)

    def add_whitelist(self, user_id: str) -> None:
        self._whitelist.add(user_id)

    def check(self, user_id: str) -> bool:
        if user_id in self._whitelist:
            return True
        now = time.time()
        window_start = now - self.window_seconds
        self._requests[user_id] = [t for t in self._requests[user_id] if t > window_start]
        if len(self._requests[user_id]) >= self.max_requests:
            return False
        self._requests[user_id].append(now)
        return True

    def remaining(self, user_id: str) -> int:
        if user_id in self._whitelist:
            return self.max_requests
        now = time.time()
        window_start = now - self.window_seconds
        self._requests[user_id] = [t for t in self._requests[user_id] if t > window_start]
        return max(0, self.max_requests - len(self._requests[user_id]))
