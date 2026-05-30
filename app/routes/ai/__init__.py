from flask import Blueprint, render_template, jsonify, request
from flask_login import login_required
from .attribution import ai_attribution_bp
from .prediction import ai_prediction_bp
from .strategy import ai_strategy_bp
from .visualization import ai_visualization_bp
from .content import ai_content_bp
from .admin import ai_admin_bp
from .smart_analysis import smart_analysis_bp

ai_analysis_bp = Blueprint('ai_analysis', __name__, template_folder='../../templates/ai', static_folder='../../static')

MODULE_ROUTE_MAP = {
    'attribution': '/ai/attribution',
    'prediction': '/ai/prediction',
    'strategy': '/ai/strategy',
    'visualization': '/ai/visualization',
    'content': '/ai/content',
    'explanation': '/ai/content',
    'variant': '/ai/content',
    'report': '/ai/content',
    'smart_analysis': '/ai/smart',
}


@ai_analysis_bp.route('/')
@login_required
def index():
    from app.services.ai.feature_switch import AIFeatureSwitchService
    switches = AIFeatureSwitchService.get_all_switches()
    return render_template('ai/smart_analysis.html', ai_switches=switches)
