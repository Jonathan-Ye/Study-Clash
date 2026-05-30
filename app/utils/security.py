import re
import time
from functools import wraps
from flask import request, jsonify, current_app
from flask_login import current_user


def validate_password(password):
    """校验密码是否符合当前密码策略

    Returns:
        tuple: (is_valid, errors_list)
    """
    try:
        from app.models.system import SystemSetting
        policy_enabled = SystemSetting.get('password_policy_enabled', 'false') == 'true'
    except Exception:
        policy_enabled = False

    errors = []

    if policy_enabled:
        min_length = int(SystemSetting.get('password_min_length', '8'))
        require_upper = SystemSetting.get('password_require_uppercase', 'true') == 'true'
        require_lower = SystemSetting.get('password_require_lowercase', 'true') == 'true'
        require_digit = SystemSetting.get('password_require_digit', 'true') == 'true'
        require_special = SystemSetting.get('password_require_special', 'true') == 'true'

        if len(password) < min_length:
            errors.append(f'密码至少需要{min_length}个字符')
        if require_upper and not re.search(r'[A-Z]', password):
            errors.append('密码需要包含至少1个大写字母')
        if require_lower and not re.search(r'[a-z]', password):
            errors.append('密码需要包含至少1个小写字母')
        if require_digit and not re.search(r'[0-9]', password):
            errors.append('密码需要包含至少1个数字')
        if require_special and not re.search(r'[!@#$%^&*()_+\-=\[\]{};\'\\:"|,<.>/?`~]', password):
            errors.append('密码需要包含至少1个特殊字符')
    else:
        if len(password) < 6:
            errors.append('密码至少需要6个字符')

    return len(errors) == 0, errors


def get_password_policy_config():
    """获取当前密码策略配置（供前端API使用）"""
    try:
        from app.models.system import SystemSetting
        policy_enabled = SystemSetting.get('password_policy_enabled', 'false') == 'true'
    except Exception:
        policy_enabled = False

    if policy_enabled:
        from app.models.system import SystemSetting
        return {
            'enabled': True,
            'min_length': int(SystemSetting.get('password_min_length', '8')),
            'require_uppercase': SystemSetting.get('password_require_uppercase', 'true') == 'true',
            'require_lowercase': SystemSetting.get('password_require_lowercase', 'true') == 'true',
            'require_digit': SystemSetting.get('password_require_digit', 'true') == 'true',
            'require_special': SystemSetting.get('password_require_special', 'true') == 'true',
        }
    else:
        return {
            'enabled': False,
            'min_length': 6,
            'require_uppercase': False,
            'require_lowercase': False,
            'require_digit': False,
            'require_special': False,
        }


class RateLimiter:
    """基于内存的滑动窗口请求限流器"""

    _storage = {}  # {key: [(timestamp, ...), ...]}
    _last_cleanup = time.time()

    @classmethod
    def is_allowed(cls, key, limit, period=60):
        """检查请求是否允许

        Args:
            key: 限流键（如 "login:username" 或 "api:user_id"）
            limit: 时间窗口内允许的最大请求数
            period: 时间窗口（秒）

        Returns:
            bool: 是否允许请求
        """
        now = time.time()

        # 每5分钟清理一次过期数据
        if now - cls._last_cleanup > 300:
            cls._cleanup(period)
            cls._last_cleanup = now

        if key not in cls._storage:
            cls._storage[key] = []

        # 移除窗口外的记录
        window_start = now - period
        cls._storage[key] = [ts for ts in cls._storage[key] if ts > window_start]

        if len(cls._storage[key]) >= limit:
            return False

        cls._storage[key].append(now)
        return True

    @classmethod
    def get_retry_after(cls, key, period=60):
        """获取需要等待的秒数"""
        now = time.time()
        if key not in cls._storage or not cls._storage[key]:
            return 0
        # 最早的记录过期时间
        earliest = min(cls._storage[key])
        retry_after = int(earliest + period - now) + 1
        return max(1, retry_after)

    @classmethod
    def _cleanup(cls, period):
        """清理过期的限流记录"""
        now = time.time()
        expired_keys = []
        for key, timestamps in cls._storage.items():
            cls._storage[key] = [ts for ts in timestamps if ts > now - period * 2]
            if not cls._storage[key]:
                expired_keys.append(key)
        for key in expired_keys:
            del cls._storage[key]


def rate_limit(limit, period=60, key_func=None):
    """请求限流装饰器

    Args:
        limit: 时间窗口内允许的最大请求数
        period: 时间窗口（秒）
        key_func: 生成限流键的函数，接收无参数，返回字符串
                  默认使用用户ID或IP地址
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if key_func:
                key = key_func()
            else:
                if current_user.is_authenticated:
                    key = f"{f.__name__}:user:{current_user.id}"
                else:
                    key = f"{f.__name__}:ip:{request.remote_addr}"

            if not RateLimiter.is_allowed(key, limit, period):
                retry_after = RateLimiter.get_retry_after(key, period)
                if request.accept_mimetypes.best_match(['application/json', 'text/html']) == 'application/json':
                    response = jsonify({'error': f'请求过于频繁，请{retry_after}秒后再试'})
                    response.status_code = 429
                    response.headers['Retry-After'] = str(retry_after)
                    return response
                from flask import flash, redirect, url_for
                flash(f'请求过于频繁，请稍后再试', 'error')
                return redirect(request.url or url_for('main.index'))

            return f(*args, **kwargs)
        return decorated_function
    return decorator
