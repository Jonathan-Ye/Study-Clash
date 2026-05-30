from app.routes.auth import auth_bp
from app.routes.main import main_bp
from app.routes.questions import questions_bp
from app.routes.game import game_bp
from app.routes.points import points_bp
from app.routes.wrong_questions import wrong_bp
from app.routes.admin import admin_bp
from app.routes.api import api_bp
import app.routes.socket_events  # 仅触发模块加载，注册事件处理器

__all__ = [
    'auth_bp', 'main_bp', 'questions_bp', 'game_bp',
    'points_bp', 'wrong_bp', 'admin_bp', 'api_bp'
]
