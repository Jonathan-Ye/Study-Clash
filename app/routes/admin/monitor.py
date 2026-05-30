import os
from datetime import datetime, timedelta, timezone
from flask import render_template, jsonify, current_app
from flask_login import login_required
from app import db
from app.models import User
from app.routes.admin import admin_bp, admin_required


@admin_bp.route('/monitor')
@login_required
@admin_required
def monitor():
    """系统监控页面"""
    stats = _get_monitor_stats()
    breadcrumb = [
        {'label': '系统管理'},
        {'label': '系统监控'}
    ]
    return render_template('admin/monitor.html', stats=stats, breadcrumb=breadcrumb)


@admin_bp.route('/api/monitor/stats')
@login_required
@admin_required
def monitor_stats():
    """系统监控数据API（JSON）"""
    stats = _get_monitor_stats()
    return jsonify(stats)


def _get_monitor_stats():
    """收集系统监控数据"""
    # CPU、内存、磁盘
    try:
        import psutil
        cpu_percent = psutil.cpu_percent(interval=1)
        mem = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        mem_data = {
            'total': _sizeof_fmt(mem.total),
            'used': _sizeof_fmt(mem.used),
            'percent': mem.percent
        }
        disk_data = {
            'total': _sizeof_fmt(disk.total),
            'used': _sizeof_fmt(disk.used),
            'percent': disk.percent
        }
    except (ImportError, Exception):
        cpu_percent = 'N/A'
        mem_data = {'total': 'N/A', 'used': 'N/A', 'percent': 'N/A'}
        disk_data = {'total': 'N/A', 'used': 'N/A', 'percent': 'N/A'}

    # 数据库大小
    try:
        db_path = current_app.config.get('DB_PATH', '')
        if db_path and os.path.exists(db_path):
            db_size = _sizeof_fmt(os.path.getsize(db_path))
        else:
            db_size = 'N/A'
    except Exception:
        db_size = 'N/A'

    # 在线用户（30分钟内登录且活跃）
    try:
        thirty_min_ago = datetime.now(timezone.utc) - timedelta(minutes=30)
        online_users = User.query.filter(
            User.last_login >= thirty_min_ago,
            User.is_active == True
        ).count()
    except Exception:
        online_users = 0

    # 系统运行时间
    try:
        start_time = current_app.config.get('APP_START_TIME')
        if start_time:
            uptime_delta = datetime.now(timezone.utc) - start_time
            uptime = _format_uptime(uptime_delta)
        else:
            uptime = 'N/A'
    except Exception:
        uptime = 'N/A'

    return {
        'cpu_percent': cpu_percent,
        'memory': mem_data,
        'disk': disk_data,
        'db_size': db_size,
        'online_users': online_users,
        'uptime': uptime
    }


def _sizeof_fmt(num, suffix='B'):
    """格式化文件大小"""
    for unit in ['', 'K', 'M', 'G', 'T']:
        if abs(num) < 1024.0:
            return "%3.1f %s%s" % (num, unit, suffix)
        num /= 1024.0
    return "%.1f %s%s" % (num, 'Y', suffix)


def _format_uptime(delta):
    """格式化运行时间"""
    total_seconds = int(delta.total_seconds())
    days = total_seconds // 86400
    hours = (total_seconds % 86400) // 3600
    minutes = (total_seconds % 3600) // 60
    seconds = total_seconds % 60
    parts = []
    if days > 0:
        parts.append(f'{days}天')
    if hours > 0:
        parts.append(f'{hours}小时')
    if minutes > 0:
        parts.append(f'{minutes}分钟')
    parts.append(f'{seconds}秒')
    return ' '.join(parts)
