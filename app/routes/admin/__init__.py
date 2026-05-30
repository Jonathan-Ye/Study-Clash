from flask import Blueprint
from flask_login import current_user
from functools import wraps
import io

admin_bp = Blueprint('admin', __name__)


# 管理后台导航配置（数据驱动）
ADMIN_NAV_CONFIG = [
    {
        'group': 'data_stats',
        'label': '数据统计',
        'icon': 'bi-graph-up',
        'nav_items': [
            {'label': '仪表盘', 'endpoint': 'admin.index', 'icon': 'bi-speedometer2'},
            {'label': '数据统计', 'endpoint': 'admin.statistics', 'icon': 'bi-bar-chart'},
            {'label': '学生分析', 'endpoint': 'admin.student_analysis', 'icon': 'bi-mortarboard'},
            {'label': '积分审计', 'endpoint': 'admin.points_audit', 'icon': 'bi-cash-stack'},
        ]
    },
    {
        'group': 'user_mgmt',
        'label': '用户管理',
        'icon': 'bi-people',
        'nav_items': [
            {'label': '用户管理', 'endpoint': 'admin.users', 'icon': 'bi-person-badge'},
        ]
    },
    {
        'group': 'content_mgmt',
        'label': '内容管理',
        'icon': 'bi-book',
        'nav_items': [
            {'label': '学科管理', 'endpoint': 'admin.subjects', 'icon': 'bi-journal-text'},
            {'label': '章节管理', 'endpoint': 'admin.chapters', 'icon': 'bi-list-ul'},
            {'label': '题目管理', 'endpoint': 'admin.questions', 'icon': 'bi-question-circle'},
            {'label': '题目反馈', 'endpoint': 'admin.feedback_list', 'icon': 'bi-flag-fill'},
            {'label': '字典管理', 'endpoint': 'admin.dictionaries', 'icon': 'bi-bookmarks'},
        ]
    },
    {
        'group': 'game_mgmt',
        'label': '游戏管理',
        'icon': 'bi-controller',
        'nav_items': [
            {'label': '游戏记录', 'endpoint': 'admin.games', 'icon': 'bi-controller'},
            {'label': '排行榜管理', 'endpoint': 'admin.leaderboard_manage', 'icon': 'bi-trophy'},
            {'label': '段位管理', 'endpoint': 'admin.rank_tiers_index', 'icon': 'bi-award'},
        ]
    },
    {
        'group': 'system_mgmt',
        'label': '系统管理',
        'icon': 'bi-gear',
        'nav_items': [
            {'label': '系统设置', 'endpoint': 'admin.settings', 'icon': 'bi-sliders'},
            {'label': '数据备份', 'endpoint': 'admin.backup', 'icon': 'bi-database'},
            {'label': '题库备份', 'endpoint': 'admin.quiz_backup', 'icon': 'bi-archive'},
            {'label': '操作日志', 'endpoint': 'admin.op_logs', 'icon': 'bi-clock-history'},
            {'label': '系统公告', 'endpoint': 'admin.announcements', 'icon': 'bi-megaphone'},
            {'label': '系统监控', 'endpoint': 'admin.monitor', 'icon': 'bi-activity'},
            {'label': '系统日志', 'endpoint': 'admin.logs', 'icon': 'bi-journal-text'},
        ]
    },
    {
        'group': 'ai_mgmt',
        'label': 'AI智能分析',
        'icon': 'bi-robot',
        'nav_items': [
            {'label': '服务商配置', 'endpoint': 'admin.ai_providers', 'icon': 'bi-cloud'},
            {'label': '调用策略', 'endpoint': 'admin.ai_strategies', 'icon': 'bi-toggles'},
            {'label': '变式题审核', 'endpoint': 'admin.ai_review', 'icon': 'bi-check2-circle'},
            {'label': 'AI审计监控', 'endpoint': 'admin.ai_audit', 'icon': 'bi-graph-up-arrow'},
        ]
    },
]


# 教师工作台导航配置
TEACHER_NAV_CONFIG = [
    {
        'group': 'content_mgmt',
        'label': '内容管理',
        'icon': 'bi-book',
        'nav_items': [
            {'label': '学科管理', 'endpoint': 'admin.subjects', 'icon': 'bi-journal-text'},
            {'label': '章节管理', 'endpoint': 'admin.chapters', 'icon': 'bi-list-ul'},
            {'label': '题目管理', 'endpoint': 'admin.questions', 'icon': 'bi-question-circle'},
        ]
    },
    {
        'group': 'user_mgmt',
        'label': '学生管理',
        'icon': 'bi-people',
        'nav_items': [
            {'label': '学生导入', 'endpoint': 'admin.teacher_student_import', 'icon': 'bi-person-plus'},
        ]
    },
    {
        'group': 'data_stats',
        'label': '数据分析',
        'icon': 'bi-graph-up',
        'nav_items': [
            {'label': '学生分析', 'endpoint': 'admin.student_analysis', 'icon': 'bi-mortarboard'},
            {'label': '知识点分析', 'endpoint': 'admin.knowledge_analysis', 'icon': 'bi-graph-up-arrow'},
        ]
    },
]


def role_required(*roles):
    """角色权限装饰器，允许指定多个角色访问"""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated:
                from flask import flash, redirect, url_for, request, jsonify
                if request.accept_mimetypes.best_match(['application/json', 'text/html']) == 'application/json':
                    return jsonify({'error': '请先登录'}), 401
                flash('请先登录', 'error')
                return redirect(url_for('auth.login'))
            if current_user.role not in roles:
                from flask import flash, redirect, url_for, request, jsonify
                if request.accept_mimetypes.best_match(['application/json', 'text/html']) == 'application/json':
                    return jsonify({'error': '权限不足'}), 403
                flash('您没有权限访问此功能', 'error')
                return redirect(url_for('main.index'))
            return f(*args, **kwargs)
        return decorated_function
    return decorator


def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            from flask import flash, redirect, url_for, request, jsonify
            if request.accept_mimetypes.best_match(['application/json', 'text/html']) == 'application/json':
                return jsonify({'error': '需要管理员权限'}), 403
            flash('需要管理员权限', 'error')
            return redirect(url_for('main.index'))
        return f(*args, **kwargs)
    return decorated_function


# 教师导航项与权限字段的映射
TEACHER_NAV_PERMISSION_MAP = {
    'admin.subjects': 'can_manage_subjects',
    'admin.chapters': 'can_manage_chapters',
    'admin.questions': 'can_manage_questions',
    'admin.quiz_export': 'can_export_questions',
    'admin.quiz_import': 'can_import_questions',
    'admin.quiz_backup': 'can_import_questions',
    'admin.chapter_export': 'can_manage_chapters',
    'admin.chapter_import': 'can_manage_chapters',
    'admin.teacher_student_import': 'can_import_students',
    'admin.student_analysis': 'can_view_student_analysis',
    'admin.knowledge_analysis': 'can_view_knowledge_analysis',
}


def teacher_permission_required(perm_key):
    """教师细粒度权限装饰器。管理员始终通过，教师需检查对应权限字段。"""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated:
                from flask import flash, redirect, url_for, request, jsonify
                if request.accept_mimetypes.best_match(['application/json', 'text/html']) == 'application/json':
                    return jsonify({'error': '请先登录'}), 401
                flash('请先登录', 'error')
                return redirect(url_for('auth.login'))
            if not current_user.has_permission(perm_key):
                from flask import flash, redirect, url_for, request, jsonify
                if request.accept_mimetypes.best_match(['application/json', 'text/html']) == 'application/json':
                    return jsonify({'error': '您没有此功能的权限，请联系管理员'}), 403
                flash('您没有此功能的权限，请联系管理员', 'error')
                return redirect(url_for('admin.index') if current_user.role in ('admin', 'teacher') else url_for('main.index'))
            return f(*args, **kwargs)
        return decorated_function
    return decorator

def sizeof_fmt(num, suffix='B'):
    for unit in ['', 'K', 'M', 'G', 'T']:
        if abs(num) < 1024.0:
            return "%3.1f %s%s" % (num, unit, suffix)
        num /= 1024.0
    return "%.1f %s%s" % (num, 'Y', suffix)


from app.routes.admin.dashboard import *
from app.routes.admin.users import *
from app.routes.admin.content import *
from app.routes.admin.games_admin import *
from app.routes.admin.statistics import *
from app.routes.admin.settings import *
from app.routes.admin.backup import *
from app.routes.admin.leaderboard_admin import *
from app.routes.admin.audit import *
from app.routes.admin.dictionary import *
from app.routes.admin.rank_tiers import *
from app.routes.admin.audit_log import *
from app.routes.admin.announcements import *
from app.routes.admin.student_analysis import *
from app.routes.admin.knowledge_analysis import *
from app.routes.admin.teacher import *
from app.routes.admin.monitor import *
from app.routes.admin.logs import *
from app.routes.admin.ai_admin import *
from app.routes.admin.feedback import *
