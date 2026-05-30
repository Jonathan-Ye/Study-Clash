"""
智能学习分析路由 - 异步版
支持后台分析，切换页面不丢失状态
"""
import logging
import threading
from flask import Blueprint, jsonify, request
from flask_login import login_required, current_user
from app import db, socketio
from app.models.ai_analysis import AISmartAnalysis, AIAsyncTask
from app.services.ai.smart_analysis_service import SmartAnalysisService
from app.services.ai.task_manager import TaskManager

logger = logging.getLogger(__name__)

smart_analysis_bp = Blueprint('smart_analysis', __name__)


@smart_analysis_bp.route('/analyze', methods=['POST'])
@login_required
def trigger_analyze():
    """触发AI智能分析（异步）"""
    try:
        # 检查是否已有正在进行的任务
        running_task = AIAsyncTask.query.filter_by(
            user_id=current_user.id,
            task_type='smart_analysis',
            status='running'
        ).first()
        
        if running_task:
            return jsonify({
                'status': 'running',
                'task_id': running_task.id,
                'message': '已有分析任务正在进行中'
            })
        
        # 创建新任务
        task = TaskManager.create_task('smart_analysis', current_user.id)
        TaskManager.update_task_progress(task.id, 0, '准备开始AI智能分析...')
        
        # 启动后台线程
        thread = threading.Thread(
            target=_run_analysis,
            args=(current_user.id, task.id),
            daemon=True
        )
        thread.start()
        
        return jsonify({
            'status': 'started',
            'task_id': task.id,
            'message': 'AI分析已启动'
        })
    except Exception as e:
        logger.error(f'触发分析失败: {e}', exc_info=True)
        return jsonify({
            'status': 'error',
            'message': f'触发失败: {str(e)}'
        }), 500


def _run_analysis(user_id, task_id):
    """后台执行AI分析"""
    from app import create_app
    app = create_app()
    
    try:
        with app.app_context():
            TaskManager.update_task_progress(task_id, 10, '正在分析你的学习数据...')
            
            # 执行分析
            result = SmartAnalysisService.analyze_student(user_id, use_ai=True)
            
            TaskManager.update_task_progress(task_id, 90, '分析完成，保存结果...')
            
            if result['status'] == 'success':
                # 保存到数据库
                record = AISmartAnalysis(
                    user_id=user_id,
                    analysis_data=result['analysis']
                )
                db.session.add(record)
                db.session.commit()
            
            TaskManager.update_task_progress(task_id, 100, 'AI分析完成！')
            TaskManager.complete_task(task_id, result)
            
    except Exception as e:
        logger.error(f'AI分析任务失败: {e}', exc_info=True)
        try:
            with app.app_context():
                TaskManager.fail_task(task_id, str(e))
        except Exception:
            pass


@smart_analysis_bp.route('/analyze/status', methods=['GET'])
@login_required
def check_status():
    """
    查询分析任务状态
    """
    try:
        # 查询最新的任务
        task = AIAsyncTask.query.filter_by(
            user_id=current_user.id,
            task_type='smart_analysis'
        ).order_by(AIAsyncTask.created_at.desc()).first()
        
        if not task:
            return jsonify({
                'status': 'no_task',
                'message': '暂无分析任务'
            })
        
        return jsonify({
            'status': task.status,
            'progress': task.progress,
            'message': task.message,
            'task_id': task.id,
            'error_detail': task.error_detail,
            'created_at': task.created_at.isoformat()
        })
    except Exception as e:
        logger.error(f'查询任务状态失败: {e}', exc_info=True)
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500


@smart_analysis_bp.route('/analyze/result', methods=['GET'])
@login_required
def get_result():
    """
    获取最新的分析结果（从数据库）
    """
    try:
        record = AISmartAnalysis.query.filter_by(
            user_id=current_user.id
        ).order_by(AISmartAnalysis.created_at.desc()).first()
        
        if record:
            return jsonify({
                'status': 'completed',
                'result': {
                    'status': 'success',
                    'analysis': record.analysis_data,
                    'created_at': record.created_at.isoformat()
                }
            })
        else:
            return jsonify({
                'status': 'no_data',
                'message': '暂无分析结果'
            })
    except Exception as e:
        logger.error(f'获取分析结果失败: {e}', exc_info=True)
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500


@smart_analysis_bp.route('/report', methods=['GET'])
@login_required
def report():
    """获取学习报告"""
    try:
        report_type = request.args.get('report_type', 'weekly')
        if report_type not in ('weekly', 'monthly'):
            return jsonify({
                'status': 'error',
                'message': 'report_type必须为weekly或monthly'
            }), 400
        
        result = SmartAnalysisService.get_learning_report(current_user.id, report_type)
        return jsonify(result)
    except Exception as e:
        logger.error(f'学习报告生成失败: {e}', exc_info=True)
        return jsonify({
            'status': 'error',
            'message': f'报告生成失败: {str(e)}',
            'report': None
        }), 500

