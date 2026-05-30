import json
import hashlib
from datetime import datetime, timezone, timedelta
from flask import current_app


class CacheManager:
    _prefix = 'ai_cache'

    @staticmethod
    def _get_cache():
        from flask import current_app
        cache = current_app.extensions.get('cache')
        return cache

    @staticmethod
    def _make_key(*parts) -> str:
        return f"{CacheManager._prefix}:{':'.join(str(p) for p in parts)}"

    @staticmethod
    def get_analysis(user_id: int, data_hash: str) -> dict:
        cache = CacheManager._get_cache()
        if cache:
            key = CacheManager._make_key('analysis', user_id, data_hash)
            return cache.get(key)
        return None

    @staticmethod
    def save_analysis(user_id: int, data_hash: str, result: dict, timeout: int = 3600):
        cache = CacheManager._get_cache()
        if cache:
            key = CacheManager._make_key('analysis', user_id, data_hash)
            cache.set(key, result, timeout=timeout)

    @staticmethod
    def get_prediction(user_id: int) -> dict:
        cache = CacheManager._get_cache()
        if cache:
            key = CacheManager._make_key('prediction', user_id)
            return cache.get(key)
        return None

    @staticmethod
    def save_prediction(user_id: int, result: dict, timeout: int = 604800):
        cache = CacheManager._get_cache()
        if cache:
            key = CacheManager._make_key('prediction', user_id)
            cache.set(key, result, timeout=timeout)

    @staticmethod
    def get_strategy(user_id: int) -> dict:
        cache = CacheManager._get_cache()
        if cache:
            key = CacheManager._make_key('strategy', user_id)
            return cache.get(key)
        return None

    @staticmethod
    def save_strategy(user_id: int, result: dict, timeout: int = 3600):
        cache = CacheManager._get_cache()
        if cache:
            key = CacheManager._make_key('strategy', user_id)
            cache.set(key, result, timeout=timeout)

    @staticmethod
    def compute_data_hash(data: dict) -> str:
        raw = json.dumps(data, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(raw.encode()).hexdigest()
