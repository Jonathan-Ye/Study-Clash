from flask import Blueprint, jsonify, request
from flask_login import login_required, current_user
from app.services.ai.visualization_service import VisualizationService

ai_visualization_bp = Blueprint('ai_visualization', __name__)


@ai_visualization_bp.route('/distribution', methods=['GET'])
@login_required
def get_distribution():
    dimension = request.args.get('dimension', 'chapter')
    result = VisualizationService.get_distribution_chart_data(current_user.id, dimension)
    return jsonify(result)


@ai_visualization_bp.route('/radar', methods=['GET'])
@login_required
def get_radar():
    result = VisualizationService.get_radar_chart_data(current_user.id)
    return jsonify(result)


@ai_visualization_bp.route('/heatmap', methods=['GET'])
@login_required
def get_heatmap():
    subject_id = request.args.get('subject_id', type=int)
    result = VisualizationService.get_heatmap_data(current_user.id, subject_id)
    return jsonify(result)


@ai_visualization_bp.route('/trend', methods=['GET'])
@login_required
def get_trend():
    result = VisualizationService.get_trend_chart_data(current_user.id)
    return jsonify(result)


@ai_visualization_bp.route('/export', methods=['POST'])
@login_required
def export_chart():
    data = request.get_json()
    return jsonify({'status': 'success', 'message': '图表导出功能请使用前端ECharts getDataURL()'})
