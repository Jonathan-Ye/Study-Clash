import logging
import threading
from flask import Blueprint, jsonify, request
from flask_login import login_required, current_user
from app import socketio
from app.services.ai.comparison_service import ComparisonService
from app.services.ai.task_manager import TaskManager

logger = logging.getLogger(__name__)
ai_comparison_bp = Blueprint('ai_comparison', __name__)


@ai_comparison_bp.route('/trigger', methods=['POST'])
@login_required
def trigger_comparison():
    task = TaskManager.create_task('comparison', current_user.id)
    thread = threading.Thread(target=_run_comparison, args=(current_user.id, task.id), daemon=True)
    thread.start()
    return jsonify({
        'status': 'started',
        'task_id': task.id,
        'message': '错题对比分析已触发',
    })


def _run_comparison(user_id, task_id):
    try:
        with socketio.server.app.app_context():
            TaskManager.update_task_progress(task_id, 5, '错题对比分析启动中')
            ComparisonService.compare_similar(user_id, task_id)
    except Exception as e:
        logger.error(f'错题对比分析后台任务异常: {e}', exc_info=True)
        try:
            with socketio.server.app.app_context():
                TaskManager.fail_task(task_id, str(e))
        except Exception:
            pass


@ai_comparison_bp.route('/task-status', methods=['GET'])
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


@ai_comparison_bp.route('/result', methods=['GET'])
@login_required
def get_comparison_result():
    result = ComparisonService.get_result(current_user.id)
    return jsonify(result)
