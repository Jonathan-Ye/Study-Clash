import json
import logging
import threading
from datetime import datetime, timezone
from flask import Blueprint, jsonify, request
from flask_login import login_required, current_user
from app import db, socketio
from app.models.ai_analysis import AIAnalysisResult, AIPredictionResult, AIStudyPlan
from app.models.wrong_question import WrongQuestion as WQ
from app.services.llm import LLMServiceOrchestrator, AllProvidersFailedError
from app.services.ai.data_sanitizer import DataSanitizer
from app.services.ai.prompt_manager import PromptTemplateManager
from app.services.ai.task_manager import TaskManager

logger = logging.getLogger(__name__)

ai_plan_bp = Blueprint('ai_plan', __name__)


@ai_plan_bp.route('/generate', methods=['POST'])
@login_required
def generate_plan():
    task = TaskManager.create_task('plan', current_user.id)
    thread = threading.Thread(target=_run_plan, args=(current_user.id, task.id), daemon=True)
    thread.start()
    return jsonify({
        'status': 'started',
        'task_id': task.id,
        'message': '学习计划生成已触发',
    })


def _run_plan(user_id, task_id):
    try:
        with socketio.server.app.app_context():
            TaskManager.update_task_progress(task_id, 5, '学习计划生成启动中')
            try:
                TaskManager.update_task_progress(task_id, 10, '获取分析数据')

                analysis = AIAnalysisResult.query.filter_by(
                    user_id=user_id
                ).order_by(AIAnalysisResult.created_at.desc()).first()
                prediction = AIPredictionResult.query.filter_by(
                    user_id=user_id
                ).order_by(AIPredictionResult.created_at.desc()).first()

                attribution_data = {}
                if analysis:
                    attribution_data = {
                        'root_causes': json.loads(analysis.root_causes) if analysis.root_causes else [],
                        'knowledge_mastery': json.loads(analysis.knowledge_mastery) if analysis.knowledge_mastery else [],
                    }
                prediction_data = {}
                if prediction:
                    prediction_data = {
                        'weak_points': json.loads(prediction.weak_points) if prediction.weak_points else [],
                    }

                TaskManager.update_task_progress(task_id, 30, '获取复习安排')

                pending_reviews = WQ.get_review_needed(user_id)
                review_items = [
                    {
                        'question_id': wq.question_id,
                        'wrong_count': wq.wrong_count,
                    }
                    for wq in pending_reviews[:20]
                ]

                TaskManager.update_task_progress(task_id, 50, '调用大模型生成计划')

                prompt = PromptTemplateManager.render('study_plan', {
                    'attribution': json.dumps(attribution_data, ensure_ascii=False, indent=2),
                    'prediction': json.dumps(prediction_data, ensure_ascii=False, indent=2),
                    'review_items': json.dumps(review_items, ensure_ascii=False, indent=2),
                })

                response = LLMServiceOrchestrator.invoke(
                    task_type='attribution',
                    system_prompt='你是一位学习计划规划专家，擅长为学生制定个性化每日学习计划。',
                    user_prompt=prompt,
                    user_id=user_id,
                )

                TaskManager.update_task_progress(task_id, 70, '解析计划结果')

                try:
                    text = response.content.strip()
                    if text.startswith('```'):
                        lines = text.split('\n')
                        text = '\n'.join(lines[1:-1])
                    result = json.loads(text)
                except json.JSONDecodeError:
                    import re
                    json_match = re.search(r'\{[\s\S]*\}', response.content)
                    result = json.loads(json_match.group()) if json_match else None

                if not result:
                    TaskManager.fail_task(task_id, '大模型返回格式异常')
                    return

                TaskManager.update_task_progress(task_id, 85, '保存计划结果')

                plan = AIStudyPlan(
                    user_id=user_id,
                    plan_date=datetime.now(timezone.utc),
                    items=json.dumps(result.get('items', []), ensure_ascii=False),
                    total_minutes=result.get('total_minutes', 0),
                    total_tokens=response.total_tokens,
                )
                db.session.add(plan)
                db.session.commit()

                TaskManager.complete_task(task_id, plan.id)

            except AllProvidersFailedError as e:
                TaskManager.fail_task(task_id, str(e))
            except Exception as e:
                logger.error(f'学习计划生成失败: {e}', exc_info=True)
                TaskManager.fail_task(task_id, str(e))
    except Exception as e:
        logger.error(f'学习计划后台任务异常: {e}', exc_info=True)
        try:
            with socketio.server.app.app_context():
                TaskManager.fail_task(task_id, str(e))
        except Exception:
            pass


@ai_plan_bp.route('/task-status', methods=['GET'])
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


@ai_plan_bp.route('/result', methods=['GET'])
@login_required
def get_plan_result():
    plan = AIStudyPlan.query.filter_by(
        user_id=current_user.id
    ).order_by(AIStudyPlan.created_at.desc()).first()
    if not plan:
        return jsonify({'status': 'no_data', 'message': '暂未生成学习计划'})
    return jsonify({
        'status': 'success',
        'data': {
            'items': json.loads(plan.items) if plan.items else [],
            'total_minutes': plan.total_minutes,
            'completed_items': plan.completed_items,
            'plan_date': plan.plan_date.isoformat() if plan.plan_date else None,
            'created_at': plan.created_at.isoformat() if plan.created_at else None,
        }
    })


@ai_plan_bp.route('/progress', methods=['PUT'])
@login_required
def update_progress():
    data = request.get_json()
    knowledge_point = data.get('knowledge_point')
    completed = data.get('completed', False)
    if not knowledge_point:
        return jsonify({'error': '缺少knowledge_point'}), 400

    plan = AIStudyPlan.query.filter_by(
        user_id=current_user.id
    ).order_by(AIStudyPlan.created_at.desc()).first()
    if not plan:
        return jsonify({'error': '暂无学习计划'}), 404

    items = json.loads(plan.items) if plan.items else []
    updated = False
    for item in items:
        if item.get('knowledge_point') == knowledge_point:
            item['completed'] = completed
            updated = True
            break

    if updated:
        plan.items = json.dumps(items, ensure_ascii=False)
        plan.completed_items = sum(1 for i in items if i.get('completed'))
        db.session.commit()

    return jsonify({
        'status': 'success',
        'updated': updated,
        'completed_items': plan.completed_items if plan else 0,
    })
