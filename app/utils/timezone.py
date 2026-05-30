from datetime import datetime, timezone, timedelta
from config import BEIJING_TZ


def now_beijing():
    """获取当前北京时间"""
    return datetime.now(BEIJING_TZ)


def to_beijing(dt):
    """将datetime转换为北京时间"""
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(BEIJING_TZ)


def make_aware(dt, tz=BEIJING_TZ):
    """为naive datetime添加时区信息"""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=tz)
    return dt.astimezone(tz)
