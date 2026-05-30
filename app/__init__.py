from flask import Flask, jsonify, render_template, request, current_app
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_socketio import SocketIO
from flask_migrate import Migrate
from flask_wtf.csrf import CSRFProtect
from functools import wraps
from datetime import timedelta, datetime, timezone
from config import BEIJING_TZ
import time
from config import config
import os

db = SQLAlchemy()
login_manager = LoginManager()
socketio = SocketIO(
    async_mode='eventlet',
    cors_allowed_origins='*',
    logger=False,
    engineio_logger=False,
    ping_timeout=20,
    ping_interval=25,
    max_http_buffer_size=1024 * 1024,
    message_queue=None  # 会在 init_app 时从配置中读取
)
migrate = Migrate()
csrf = CSRFProtect()

login_manager.login_view = 'auth.login'
login_manager.login_message = '请先登录后再访问此页面'

# 为API端点创建自定义的login_required装饰器，返回JSON而非重定向
def api_login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        from flask_login import current_user
        if not current_user.is_authenticated:
            return jsonify({'error': '请先登录'}), 401
        return f(*args, **kwargs)
    return decorated_function


def create_app(config_name='default'):
    app = Flask(__name__)
    app.config.from_object(config[config_name])

    app.config.setdefault('LOG_DIR', os.path.join(app.root_path, '..', 'logs'))
    app.config.setdefault('LOG_RETENTION_DAYS', 30)

    from app.utils.system_logger import init_logging, SystemLogger
    init_logging(app)

    # 生产环境密钥安全检测
    from config import Config
    if config_name == 'production':
        if Config._SECRET_KEY_IS_DEFAULT:
            raise RuntimeError(
                '生产环境使用了不安全的 SECRET_KEY！'
                '请在 .env 中设置强随机密钥。'
            )
    elif Config._SECRET_KEY_IS_DEFAULT:
        import warnings
        warnings.warn(
            'SECRET_KEY 使用了默认/不安全值，请确保仅在开发环境使用。',
            stacklevel=2
        )
    
    # 记录应用启动时间，供系统监控使用
    app.config['APP_START_TIME'] = datetime.now(BEIJING_TZ)
    
    db.init_app(app)
    login_manager.init_app(app)
    socketio.init_app(app, message_queue=app.config.get('SOCKETIO_MESSAGE_QUEUE'))
    migrate.init_app(app, db)
    csrf.init_app(app)
    
    # 记录数据库路径，供调试使用
    app.logger.info(f'数据库路径: {app.config["SQLALCHEMY_DATABASE_URI"]}')
    
    # 确保csrf_token在模板中可用
    @app.context_processor
    def inject_builtins():
        return dict(range=range)
    
    @app.context_processor
    def inject_csrf_token():
        from flask_wtf.csrf import generate_csrf
        return dict(csrf_token=generate_csrf)
    
    # 图片URL修正函数，供模板使用
    @app.context_processor
    def inject_image_url_fix():
        def fix_image_url(url):
            if not url:
                return None
            if url.startswith(('http://', 'https://', '/static/')):
                return url
            return '/static/images/questions/' + url
        return dict(fix_image_url=fix_image_url)
    
    from app.models import user, question, game, points, wrong_question, system, achievements, ranks, admin_log, announcement, login_security, ai_analysis, question_feedback, notification

    # 注册数据库监控命令
    from app.utils.db_monitor import init_monitor_commands
    init_monitor_commands(app)

    from app.routes.auth import auth_bp
    from app.routes.main import main_bp
    from app.routes.questions import questions_bp
    from app.routes.game import game_bp
    from app.routes.points import points_bp
    from app.routes.wrong_questions import wrong_bp
    from app.routes.admin import admin_bp
    from app.routes.api import api_bp
    from app.routes.ai import ai_analysis_bp
    from app.routes.ai.attribution import ai_attribution_bp
    from app.routes.ai.prediction import ai_prediction_bp
    from app.routes.ai.strategy import ai_strategy_bp
    from app.routes.ai.visualization import ai_visualization_bp
    from app.routes.ai.content import ai_content_bp
    from app.routes.ai.admin import ai_admin_bp
    from app.routes.ai.chat import ai_chat_bp
    from app.routes.ai.report import ai_report_bp
    from app.routes.ai.plan import ai_plan_bp
    from app.routes.ai.comparison import ai_comparison_bp
    from app.routes.ai.smart_analysis import smart_analysis_bp
    
    app.register_blueprint(auth_bp, url_prefix='/auth')
    app.register_blueprint(questions_bp, url_prefix='/questions')
    app.register_blueprint(game_bp, url_prefix='/game')
    app.register_blueprint(points_bp, url_prefix='/points')
    app.register_blueprint(wrong_bp, url_prefix='/wrong')
    app.register_blueprint(admin_bp, url_prefix='/admin')
    app.register_blueprint(api_bp, url_prefix='/api')
    app.register_blueprint(main_bp)
    app.register_blueprint(ai_analysis_bp, url_prefix='/ai')
    app.register_blueprint(ai_attribution_bp, url_prefix='/ai/attribution')
    app.register_blueprint(ai_prediction_bp, url_prefix='/ai/prediction')
    app.register_blueprint(ai_strategy_bp, url_prefix='/ai/strategy')
    app.register_blueprint(ai_visualization_bp, url_prefix='/ai/visualization')
    app.register_blueprint(ai_content_bp, url_prefix='/ai/content')
    app.register_blueprint(ai_admin_bp, url_prefix='/ai/admin')
    app.register_blueprint(ai_chat_bp, url_prefix='/ai/chat')
    app.register_blueprint(ai_report_bp, url_prefix='/ai/report')
    app.register_blueprint(ai_plan_bp, url_prefix='/ai/plan')
    app.register_blueprint(ai_comparison_bp, url_prefix='/ai/comparison')
    app.register_blueprint(smart_analysis_bp, url_prefix='/ai/smart')

    with app.app_context():
        from app.services.ai.feature_switch import AIFeatureSwitchService
        AIFeatureSwitchService.init_defaults()
        from app.services.ai.badge_service import AIBadgeService
        AIBadgeService.init_defaults()

    @app.before_request
    def check_ai_feature_access():
        if not request.path.startswith('/ai') or request.path.startswith('/ai/admin'):
            return None
        from app.services.ai.feature_switch import AIFeatureSwitchService, MODULE_KEYS
        if not AIFeatureSwitchService.is_global_enabled():
            if request.accept_mimetypes.best == 'json':
                return jsonify({'status': 'disabled', 'message': 'AI功能维护中，请稍后再试'}), 503
            return render_template('ai/disabled.html', message='AI功能维护中，请稍后再试'), 503
        module_route_map = {
            '/ai/attribution': 'attribution',
            '/ai/prediction': 'prediction',
            '/ai/strategy': 'strategy',
            '/ai/visualization': 'visualization',
            '/ai/content': 'content',
            '/ai/chat': 'chat',
            '/ai/report': 'report',
            '/ai/plan': 'plan',
            '/ai/comparison': 'comparison',
        }
        for prefix, module in module_route_map.items():
            if request.path.startswith(prefix):
                allowed, msg = AIFeatureSwitchService.check_access(module)
                if not allowed:
                    if request.accept_mimetypes.best == 'json':
                        return jsonify({'status': 'disabled', 'message': msg}), 503
                    return render_template('ai/disabled.html', message=msg), 503
                break
        return None
    
    @app.template_filter('basename')
    def basename_filter(path):
        return os.path.basename(path) if path else ''
    
    @app.template_filter('sizeof_fmt')
    def sizeof_fmt_filter(num):
        try:
            num = float(num)
        except (ValueError, TypeError, AttributeError):
            return '0.0 B'
        try:
            for unit in ['', 'K', 'M', 'G', 'T']:
                if abs(num) < 1024.0:
                    return "%3.1f %sB" % (num, unit)
                num /= 1024.0
            return "%.1f YB" % num
        except (ValueError, TypeError):
            return '0.0 B'

    @app.template_filter('get_reason_label')
    def get_reason_label(reason_key):
        from app.models import PointRecord
        return PointRecord.REASONS.get(reason_key, reason_key)
    
    @app.template_filter('to_beijing')
    def to_beijing_filter(dt):
        from app.utils.timezone import to_beijing
        return to_beijing(dt)
    
    @app.template_filter('strftime')
    def strftime_filter(dt, fmt):
        if dt is None:
            return ''
        return dt.strftime(fmt)
    
    # 自定义错误页面
    @app.errorhandler(404)
    def not_found(e):
        if request.accept_mimetypes.best_match(['application/json', 'text/html']) == 'application/json':
            return jsonify({'error': '资源不存在'}), 404
        return render_template('404.html'), 404
    
    @app.errorhandler(500)
    def internal_error(e):
        current_app.logger.error(f'服务器内部错误: {str(e)}', exc_info=True)
        from app.utils.system_logger import log_exception
        log_exception(app, e, request)
        if request.accept_mimetypes.best_match(['application/json', 'text/html']) == 'application/json':
            return jsonify({'error': '服务器内部错误'}), 500
        return render_template('500.html'), 500

    @app.after_request
    def log_request_info(response):
        from app.utils.system_logger import log_request
        log_request(app, request, response)
        return response
    
    # 自动清理数据库会话，防止连接泄漏
    @app.teardown_appcontext
    def shutdown_session(exception=None):
        db.session.remove()
    
    # 添加模板上下文处理器
    @app.context_processor
    def inject_logo_url():
        from app.models.system import SystemSetting
        return dict(get_logo_url=SystemSetting.get_logo_url)
    
    @app.context_processor
    def inject_admin_nav():
        from app.routes.admin import ADMIN_NAV_CONFIG, TEACHER_NAV_CONFIG, TEACHER_NAV_PERMISSION_MAP
        from flask_login import current_user
        from flask import url_for
        # 根据角色选择导航配置
        if current_user.is_authenticated and current_user.role == 'teacher':
            nav_config = TEACHER_NAV_CONFIG
        else:
            nav_config = ADMIN_NAV_CONFIG
        # 预先解析URL，避免模板中url_for抛出BuildError
        resolved_nav = []
        for group in nav_config:
            resolved_items = []
            for item in group['nav_items']:
                try:
                    resolved_url = url_for(item['endpoint'])
                    # 教师权限过滤：检查该导航项是否需要特定权限
                    if current_user.is_authenticated and current_user.role == 'teacher':
                        perm_key = TEACHER_NAV_PERMISSION_MAP.get(item['endpoint'])
                        if perm_key and not current_user.has_permission(perm_key):
                            continue  # 跳过无权限的导航项
                    resolved_items.append({
                        'label': item['label'],
                        'endpoint': item['endpoint'],
                        'icon': item['icon'],
                        'url': resolved_url
                    })
                except Exception:
                    pass  # 跳过无法解析的endpoint
            if resolved_items:
                resolved_nav.append({
                    'group': group['group'],
                    'label': group['label'],
                    'icon': group['icon'],
                    'nav_items': resolved_items
                })
        return dict(admin_nav_config=resolved_nav)
    
    @app.context_processor
    def inject_announcements():
        from app.models.announcement import Announcement
        from datetime import datetime
        try:
            now = datetime.now(BEIJING_TZ)
            active_announcements = Announcement.query.filter(
                Announcement.display_position == 'top_banner',
                Announcement.status.in_(['published', 'pending']),
                db.or_(Announcement.publish_at.is_(None), Announcement.publish_at <= now),
                db.or_(Announcement.expire_at.is_(None), Announcement.expire_at > now)
            ).order_by(
                db.case(
                    (Announcement.priority == 'urgent', 1),
                    (Announcement.priority == 'important', 2),
                    else_=3
                ),
                Announcement.created_at.desc()
            ).limit(3).all()

            popup_announcements = Announcement.query.filter(
                Announcement.display_position == 'home_popup',
                Announcement.status.in_(['published', 'pending']),
                db.or_(Announcement.publish_at.is_(None), Announcement.publish_at <= now),
                db.or_(Announcement.expire_at.is_(None), Announcement.expire_at > now)
            ).order_by(
                db.case(
                    (Announcement.priority == 'urgent', 1),
                    (Announcement.priority == 'important', 2),
                    else_=3
                ),
                Announcement.created_at.desc()
            ).limit(1).all()
        except Exception:
            active_announcements = []
            popup_announcements = []
        return dict(active_announcements=active_announcements, popup_announcements=popup_announcements)
    
    @app.context_processor
    def inject_site_info():
        from app.models.system import SystemSetting
        return dict(
            site_info={
                'site_name': SystemSetting.get('site_name', 'Study Clash'),
                'site_desc': SystemSetting.get('site_desc', '让学习变得更有趣，让竞争激发潜能。通过游戏化的方式提升学习效率。'),
                'contact_email': SystemSetting.get('contact_email', 'contact@studyclash.com'),
                'contact_phone': SystemSetting.get('contact_phone', '400-123-4567'),
                'copyright': SystemSetting.get('copyright', '© 2024 Study Clash. All rights reserved.'),
                'icp': SystemSetting.get('icp', ''),
                'footer_slogan': SystemSetting.get('footer_slogan', 'Made with <i class="bi bi-heart-fill text-danger"></i> for learners'),
                
                'social_wechat': SystemSetting.get('social_wechat', ''),
                'social_qq': SystemSetting.get('social_qq', ''),
                'social_weibo': SystemSetting.get('social_weibo', ''),
                'social_github': SystemSetting.get('social_github', ''),
                'social_email': SystemSetting.get('social_email', ''),
                
                'show_site_info': SystemSetting.get('show_site_info', 'true') == 'true',
                'show_game_modes': SystemSetting.get('show_game_modes', 'true') == 'true',
                'show_features': SystemSetting.get('show_features', 'true') == 'true',
                'show_help': SystemSetting.get('show_help', 'true') == 'true',
                'show_contact': SystemSetting.get('show_contact', 'true') == 'true',
                'show_contact_email': SystemSetting.get('show_contact_email', 'true') == 'true',
                'show_contact_phone': SystemSetting.get('show_contact_phone', 'true') == 'true',
                'show_copyright': SystemSetting.get('show_copyright', 'true') == 'true',
                'show_icp': SystemSetting.get('show_icp', 'false') == 'true',
                'show_social': SystemSetting.get('show_social', 'false') == 'true',
                'show_slogan': SystemSetting.get('show_slogan', 'true') == 'true',
                'registration_enabled': SystemSetting.get('registration_enabled', 'true') == 'true',
            }
        )
    
    with app.app_context():
        db.create_all()
        from app.models.system import SystemSetting
        session_hours = SystemSetting.get('session_lifetime_hours')
        if session_hours:
            try:
                hours = int(session_hours)
                app.config['SESSION_LIFETIME_HOURS'] = hours
                app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=hours)
            except (ValueError, TypeError):
                pass

    @app.before_request
    def auto_cleanup_expired():
        pass

    def _cleanup_loop():
        while True:
            time.sleep(60)
            try:
                with app.app_context():
                    from app.utils.common import clean_expired_rooms
                    clean_expired_rooms()
                    from app.models.game import RematchInvitation
                    RematchInvitation.clean_expired()
                    from app.utils.system_logger import run_cleanup
                    run_cleanup()
            except Exception:
                pass

    socketio.start_background_task(_cleanup_loop)
    
    return app
