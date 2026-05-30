import threading
import time
from datetime import datetime, timezone, date
from collections import defaultdict


class TokenBudgetManager:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._daily_usage = defaultdict(int)
                    cls._instance._last_reset = date.today()
        return cls._instance

    def _check_reset(self):
        today = date.today()
        if today != self._last_reset:
            with self._lock:
                if today != self._last_reset:
                    self._daily_usage.clear()
                    self._last_reset = today

    def allow_request(self, provider_id: int, daily_budget: int) -> tuple:
        self._check_reset()
        current = self._daily_usage.get(provider_id, 0)
        if daily_budget <= 0:
            return True, 'normal', 0.0
        ratio = current / daily_budget
        if ratio >= 1.0:
            return False, 'exceeded', ratio
        if ratio >= 0.8:
            return True, 'warning', ratio
        return True, 'normal', ratio

    def consume(self, provider_id: int, tokens: int):
        self._check_reset()
        with self._lock:
            self._daily_usage[provider_id] += tokens

    def get_usage(self, provider_id: int) -> int:
        self._check_reset()
        return self._daily_usage.get(provider_id, 0)
