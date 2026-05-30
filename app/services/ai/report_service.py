import json
import logging
from datetime import datetime, timezone, timedelta
from app import db
from app.models.ai_analysis import (
    AIStudyReport, AIAnalysisResult, AIPredictionResult, AILearningStrategy,
)
from app.services.llm import LLMServiceOrchestrator, AllProvidersFailedError
from app.services.ai.data_sanitizer import DataSanitizer
from app.services.ai.prompt_manager import PromptTemplateManager
from app.services.ai.task_manager import TaskManager
from app.services.ai.feature_switch import AIFeatureSwitchService

logger = logging.getLogger(__name__)


class ReportService:
    @staticmethod
    def _get_period(report_type: str) -> tuple:
        now = datetime.now(timezone.utc)
        if report_type == 'monthly':
            start = now - timedelta(days=30)
        else:
            start = now - timedelta(days=7)
        return start, now

    @staticmethod
    def _parse_report_response(content: str) -> dict:
        try:
            text = content.strip()
            if text.startswith('```'):
                lines = text.split('\n')
                text = '\n'.join(lines[1:-1])
            return json.loads(text)
        except json.JSONDecodeError:
            try:
                import re
                json_match = re.search(r'\{[\s\S]*\}', content)
                if json_match:
                    return json.loads(json_match.group())
            except Exception:
                pass
            return None

    @staticmethod
    def _render_html(report_data: dict, report_type: str) -> str:
        def _sugg(r):
            p = r.get('priority', '')
            cls = 'high' if p == '高' else 'mid' if p == '中' else 'low'
            return f'<div class="item"><span class="priority-{cls}">[{p}]</span> {r.get("description","")}</div>'
        summary = report_data.get('summary', '')
        strengths = report_data.get('strengths', [])
        weaknesses = report_data.get('weaknesses', [])
        recommendations = report_data.get('recommendations', [])
        next_focus = report_data.get('next_focus', [])

        html = f"""<html><head><meta charset="utf-8"><style>
body{{font-family:sans-serif;max-width:800px;margin:0 auto;padding:20px;}}
h1{{color:#333;}}h2{{color:#555;border-bottom:1px solid #ddd;padding-bottom:5px;}}
.item{{margin:5px 0;padding:5px;background:#f9f9f9;border-radius:3px;}}
.priority-high{{color:#e74c3c;}}.priority-mid{{color:#f39c12;}}.priority-low{{color:#27ae60;}}
</style></head><body>
<h1>{'周报' if report_type == 'weekly' else '月报'}</h1>
<h2>学习概要</h2><p>{summary}</p>
<h2>进步与亮点</h2>{''.join(f'<div class="item">{s.get("description","")}</div>' for s in strengths)}
<h2>不足与问题</h2>{''.join(f'<div class="item">{w.get("description","")} ({w.get("knowledge_point","")})</div>' for w in weaknesses)}
<h2>改进建议</h2>{''.join(_sugg(r) for r in recommendations)}
<h2>下阶段重点</h2>{''.join(f'<div class="item">{f.get("knowledge_point","")} - {f.get("reason","")}</div>' for f in next_focus)}
</body></html>"""
        return html

    @staticmethod
    def generate_report(user_id: int, report_type: str = 'weekly', task_id: int = None) -> dict:
        try:
            allowed, msg = AIFeatureSwitchService.check_access('report')
            if not allowed:
                return {'status': 'error', 'message': msg}

            if task_id:
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

            if not analysis and not prediction:
                if task_id:
                    TaskManager.fail_task(task_id, '请先完成归因分析或推理预测')
                return {'status': 'error', 'message': '请先完成归因分析或推理预测'}

            if task_id:
                TaskManager.update_task_progress(task_id, 30, '准备数据')

            period_start, period_end = ReportService._get_period(report_type)

            attribution_data = None
            if analysis:
                attribution_data = {
                    'root_causes': json.loads(analysis.root_causes) if analysis.root_causes else [],
                    'knowledge_mastery': json.loads(analysis.knowledge_mastery) if analysis.knowledge_mastery else [],
                }

            prediction_data = None
            if prediction:
                prediction_data = {
                    'weak_points': json.loads(prediction.weak_points) if prediction.weak_points else [],
                }

            strategy_data = None
            if strategy:
                strategy_data = {
                    'learning_path': json.loads(strategy.learning_path) if strategy.learning_path else [],
                    'focus_directions': json.loads(strategy.focus_directions) if strategy.focus_directions else [],
                }

            sanitized_attribution = DataSanitizer.sanitize(attribution_data) if attribution_data else None
            sanitized_prediction = DataSanitizer.sanitize(prediction_data) if prediction_data else None
            sanitized_strategy = DataSanitizer.sanitize(strategy_data) if strategy_data else None

            if task_id:
                TaskManager.update_task_progress(task_id, 50, '调用大模型生成报告')

            prompt = PromptTemplateManager.render('study_report', {
                'attribution': json.dumps(sanitized_attribution, ensure_ascii=False, indent=2) if sanitized_attribution else '无',
                'prediction': json.dumps(sanitized_prediction, ensure_ascii=False, indent=2) if sanitized_prediction else '无',
                'strategy': json.dumps(sanitized_strategy, ensure_ascii=False, indent=2) if sanitized_strategy else '无',
                'report_type': report_type,
                'period_start': period_start.strftime('%Y-%m-%d'),
                'period_end': period_end.strftime('%Y-%m-%d'),
            })

            response = LLMServiceOrchestrator.invoke(
                task_type='strategy',
                system_prompt='你是一位教育数据分析专家，擅长综合分析学生学习数据并生成结构化学习报告。',
                user_prompt=prompt,
                user_id=user_id,
            )

            if task_id:
                TaskManager.update_task_progress(task_id, 70, '解析报告结果')

            parsed = ReportService._parse_report_response(response.content)
            if not parsed:
                if task_id:
                    TaskManager.fail_task(task_id, '大模型返回格式异常')
                return {'status': 'error', 'message': '大模型返回格式异常'}

            if task_id:
                TaskManager.update_task_progress(task_id, 85, '保存报告')

            summary = parsed.get('summary', '')
            report = AIStudyReport(
                user_id=user_id,
                report_type=report_type,
                period_start=period_start,
                period_end=period_end,
                summary=summary,
                detailed_content=json.dumps(parsed, ensure_ascii=False),
                total_tokens=response.total_tokens,
            )
            db.session.add(report)
            db.session.commit()

            if task_id:
                TaskManager.complete_task(task_id, report.id)

            return {
                'status': 'success',
                'data': parsed,
                'report_id': report.id,
            }

        except AllProvidersFailedError as e:
            if task_id:
                TaskManager.fail_task(task_id, str(e))
            return {'status': 'error', 'message': str(e)}
        except Exception as e:
            logger.error(f'学习报告生成失败: {e}', exc_info=True)
            if task_id:
                TaskManager.fail_task(task_id, str(e))
            return {'status': 'error', 'message': str(e)}

    @staticmethod
    def get_report(user_id: int, report_type: str = None) -> dict:
        query = AIStudyReport.query.filter_by(user_id=user_id)
        if report_type:
            query = query.filter_by(report_type=report_type)
        report = query.order_by(AIStudyReport.created_at.desc()).first()
        if not report:
            return {'status': 'no_data', 'message': '暂无学习报告'}
        return {
            'status': 'success',
            'data': {
                'report_id': report.id,
                'report_type': report.report_type,
                'summary': report.summary,
                'detailed_content': json.loads(report.detailed_content) if report.detailed_content else {},
                'period_start': report.period_start.isoformat() if report.period_start else None,
                'period_end': report.period_end.isoformat() if report.period_end else None,
                'created_at': report.created_at.isoformat() if report.created_at else None,
            },
        }

    @staticmethod
    def export_pdf(report_id: int) -> dict:
        report = AIStudyReport.query.get(report_id)
        if not report:
            return {'status': 'error', 'message': '报告不存在'}

        report_data = json.loads(report.detailed_content) if report.detailed_content else {}
        html_content = ReportService._render_html(report_data, report.report_type)

        try:
            from weasyprint import HTML
            pdf_bytes = HTML(string=html_content).write_pdf()
            return {'status': 'success', 'pdf': pdf_bytes, 'format': 'pdf'}
        except ImportError:
            try:
                from html2pdf import HTML2PDF
                pdf_bytes = HTML2PDF(html_content).render()
                return {'status': 'success', 'pdf': pdf_bytes, 'format': 'pdf'}
            except ImportError:
                return {'status': 'success', 'html': html_content, 'format': 'html'}
