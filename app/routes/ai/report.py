import json
import logging
import threading
from datetime import datetime, timezone, timedelta
from flask import Blueprint, jsonify, request, send_file
from flask_login import login_required, current_user
from app import db, socketio
from app.models.ai_analysis import AIAnalysisResult, AIPredictionResult, AILearningStrategy, AIStudyReport
from app.services.llm import LLMServiceOrchestrator, AllProvidersFailedError
from app.services.ai.data_sanitizer import DataSanitizer
from app.services.ai.prompt_manager import PromptTemplateManager
from app.services.ai.task_manager import TaskManager

logger = logging.getLogger(__name__)

ai_report_bp = Blueprint('ai_report', __name__)


@ai_report_bp.route('/generate', methods=['POST'])
@login_required
def generate_report():
    data = request.get_json() or {}
    report_type = data.get('report_type', 'weekly')
    if report_type not in ('weekly', 'monthly'):
        return jsonify({'error': 'report_type必须为weekly或monthly'}), 400

    task = TaskManager.create_task('report', current_user.id)
    thread = threading.Thread(target=_run_report, args=(current_user.id, task.id, report_type), daemon=True)
    thread.start()
    return jsonify({
        'status': 'started',
        'task_id': task.id,
        'message': '学习报告生成已触发',
    })


def _run_report(user_id, task_id, report_type):
    try:
        with socketio.server.app.app_context():
            TaskManager.update_task_progress(task_id, 5, '学习报告生成启动中')
            try:
                TaskManager.update_task_progress(task_id, 10, '获取分析数据')

                analysis = AIAnalysisResult.query.filter_by(
                    user_id=user_id
                ).order_by(AIAnalysisResult.created_at.desc()).first()
                prediction = AIPredictionResult.query.filter_by(
                    user_id=user_id
                ).order_by(AIPredictionResult.created_at.desc()).first()
                strategy = AILearningStrategy.query.filter_by(
                    user_id=user_id
                ).order_by(AILearningStrategy.created_at.desc()).first()

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
                strategy_data = {}
                if strategy:
                    strategy_data = {
                        'learning_path': json.loads(strategy.learning_path) if strategy.learning_path else [],
                        'focus_directions': json.loads(strategy.focus_directions) if strategy.focus_directions else [],
                    }

                now = datetime.now(timezone.utc)
                if report_type == 'weekly':
                    period_start = now - timedelta(days=7)
                else:
                    period_start = now - timedelta(days=30)

                TaskManager.update_task_progress(task_id, 40, '调用大模型生成报告')

                prompt = PromptTemplateManager.render('study_report', {
                    'attribution': json.dumps(attribution_data, ensure_ascii=False, indent=2),
                    'prediction': json.dumps(prediction_data, ensure_ascii=False, indent=2),
                    'strategy': json.dumps(strategy_data, ensure_ascii=False, indent=2),
                    'report_type': report_type,
                    'period_start': period_start.isoformat(),
                    'period_end': now.isoformat(),
                })

                response = LLMServiceOrchestrator.invoke(
                    task_type='attribution',
                    system_prompt='你是一位教育数据分析专家，擅长生成学习报告。',
                    user_prompt=prompt,
                    user_id=user_id,
                )

                TaskManager.update_task_progress(task_id, 70, '解析报告结果')

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

                TaskManager.update_task_progress(task_id, 85, '保存报告结果')

                report = AIStudyReport(
                    user_id=user_id,
                    report_type=report_type,
                    period_start=period_start,
                    period_end=now,
                    summary=result.get('summary', ''),
                    detailed_content=json.dumps(result, ensure_ascii=False),
                    total_tokens=response.total_tokens,
                )
                db.session.add(report)
                db.session.commit()

                TaskManager.complete_task(task_id, report.id)

            except AllProvidersFailedError as e:
                TaskManager.fail_task(task_id, str(e))
            except Exception as e:
                logger.error(f'学习报告生成失败: {e}', exc_info=True)
                TaskManager.fail_task(task_id, str(e))
    except Exception as e:
        logger.error(f'学习报告后台任务异常: {e}', exc_info=True)
        try:
            with socketio.server.app.app_context():
                TaskManager.fail_task(task_id, str(e))
        except Exception:
            pass


@ai_report_bp.route('/task-status', methods=['GET'])
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


@ai_report_bp.route('/result', methods=['GET'])
@login_required
def get_report_result():
    report = AIStudyReport.query.filter_by(
        user_id=current_user.id
    ).order_by(AIStudyReport.created_at.desc()).first()
    if not report:
        return jsonify({'status': 'no_data', 'message': '暂未生成学习报告'})
    detailed = {}
    if report.detailed_content:
        try:
            detailed = json.loads(report.detailed_content)
        except json.JSONDecodeError:
            detailed = {}
    return jsonify({
        'status': 'success',
        'data': {
            'report_type': report.report_type,
            'summary': report.summary,
            'detailed': detailed,
            'period_start': report.period_start.isoformat() if report.period_start else None,
            'period_end': report.period_end.isoformat() if report.period_end else None,
            'created_at': report.created_at.isoformat() if report.created_at else None,
        }
    })


@ai_report_bp.route('/export/<int:report_id>', methods=['GET'])
@login_required
def export_report(report_id):
    report = AIStudyReport.query.filter_by(
        id=report_id, user_id=current_user.id
    ).first()
    if not report:
        return jsonify({'error': '报告不存在'}), 404
    import io
    buffer = io.BytesIO()
    content = f"学习报告 - {report.report_type}\n"
    content += f"周期: {report.period_start} ~ {report.period_end}\n\n"
    content += report.summary or ''
    if report.detailed_content:
        content += '\n\n详细内容:\n' + report.detailed_content
    buffer.write(content.encode('utf-8'))
    buffer.seek(0)
    return send_file(
        buffer,
        as_attachment=True,
        download_name=f'学习报告_{report.report_type}_{datetime.now().strftime("%Y%m%d")}.txt',
        mimetype='text/plain',
    )
