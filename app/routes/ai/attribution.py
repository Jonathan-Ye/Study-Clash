import logging
import threading
from flask import Blueprint, jsonify, request
from flask_login import login_required, current_user
from app import socketio
from app.services.ai.attribution_service import AttributionService
from app.services.ai.prediction_service import PredictionService
from app.services.ai.strategy_service import StrategyService
from app.services.ai.task_manager import TaskManager

logger = logging.getLogger(__name__)
ai_attribution_bp = Blueprint('ai_attribution', __name__)


@ai_attribution_bp.route('/trigger', methods=['POST'])
@login_required
def trigger_attribution():
    task = TaskManager.create_task('attribution', current_user.id)
    thread = threading.Thread(target=_run_attribution, args=(current_user.id, task.id), daemon=True)
    thread.start()
    return jsonify({
        'status': 'started',
        'task_id': task.id,
        'message': '归因分析已触发',
    })


def _run_attribution(user_id, task_id):
    try:
        with socketio.server.app.app_context():
            TaskManager.update_task_progress(task_id, 5, '归因分析启动中')
            AttributionService.analyze(user_id, task_id)
    except Exception as e:
        logger.error(f'归因分析后台任务异常: {e}', exc_info=True)
        try:
            with socketio.server.app.app_context():
                TaskManager.fail_task(task_id, str(e))
        except Exception:
            pass


@ai_attribution_bp.route('/result', methods=['GET'])
@login_required
def get_attribution_result():
    user_id = current_user.id
    if current_user.is_admin and request.args.get('user_id'):
        user_id = int(request.args.get('user_id'))
    result = AttributionService.get_result(user_id)
    return jsonify(result)


@ai_attribution_bp.route('/task-status', methods=['GET'])
@login_required
def get_task_status():
    task_id = request.args.get('task_id', type=int)
    if not task_id:
        return jsonify({'error': '缺少task_id参数'}), 400
    task = TaskManager.get_task(task_id)
    if not task:
        return jsonify({'error': '任务不存在'}), 404
    return jsonify({
        'task_id': task.id,
        'task_type': task.task_type,
        'status': task.status,
        'progress': task.progress,
        'message': task.message,
        'error_detail': task.error_detail,
    })
