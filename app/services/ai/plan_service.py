import json
import logging
from datetime import datetime, timezone
from app import db
from app.models.ai_analysis import (
    AIStudyPlan, AIAnalysisResult, AIPredictionResult,
)
from app.models.wrong_question import WrongQuestion
from app.services.llm import LLMServiceOrchestrator, AllProvidersFailedError
from app.services.ai.data_sanitizer import DataSanitizer
from app.services.ai.prompt_manager import PromptTemplateManager
from app.services.ai.task_manager import TaskManager
from app.services.ai.feature_switch import AIFeatureSwitchService

logger = logging.getLogger(__name__)


class PlanService:
    @staticmethod
    def _get_review_data(user_id: int) -> dict:
        pending = WrongQuestion.get_review_needed(user_id, limit=20)
        items = []
        for wq in pending:
            from app.models.question import Question, Chapter
            question = Question.query.get(wq.question_id)
            if not question:
                continue
            chapter = Chapter.query.get(question.chapter_id) if question.chapter_id else None
            items.append({
                'question_id': wq.question_id,
                'chapter': chapter.name if chapter else '未知',
                'wrong_count': wq.wrong_count,
                'review_count': wq.review_count,
                'next_review_at': wq.next_review_at.isoformat() if wq.next_review_at else None,
            })
        return {
            'pending_count': len(items),
            'items': items,
        }

    @staticmethod
    def _parse_plan_response(content: str) -> dict:
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
    def generate_plan(user_id: int, task_id: int = None) -> dict:
        try:
            allowed, msg = AIFeatureSwitchService.check_access('plan')
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

            if not analysis and not prediction:
                if task_id:
                    TaskManager.fail_task(task_id, '请先完成归因分析或推理预测')
                return {'status': 'error', 'message': '请先完成归因分析或推理预测'}

            if task_id:
                TaskManager.update_task_progress(task_id, 30, '获取复习数据')

            review_data = PlanService._get_review_data(user_id)

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

            sanitized_attribution = DataSanitizer.sanitize(attribution_data) if attribution_data else None
            sanitized_prediction = DataSanitizer.sanitize(prediction_data) if prediction_data else None
            sanitized_review = DataSanitizer.sanitize(review_data)

            if task_id:
                TaskManager.update_task_progress(task_id, 50, '调用大模型生成计划')

            prompt = PromptTemplateManager.render('study_plan', {
                'attribution': json.dumps(sanitized_attribution, ensure_ascii=False, indent=2) if sanitized_attribution else '无',
                'prediction': json.dumps(sanitized_prediction, ensure_ascii=False, indent=2) if sanitized_prediction else '无',
                'review_items': json.dumps(sanitized_review, ensure_ascii=False, indent=2),
                'review_schedule': json.dumps(sanitized_review.get('items', []), ensure_ascii=False, indent=2),
            })

            response = LLMServiceOrchestrator.invoke(
                task_type='strategy',
                system_prompt='你是一位学习计划规划专家，擅长基于分析数据和间隔复习安排生成个性化每日学习计划。',
                user_prompt=prompt,
                user_id=user_id,
            )

            if task_id:
                TaskManager.update_task_progress(task_id, 70, '解析计划结果')

            parsed = PlanService._parse_plan_response(response.content)
            if not parsed:
                if task_id:
                    TaskManager.fail_task(task_id, '大模型返回格式异常')
                return {'status': 'error', 'message': '大模型返回格式异常'}

            plan_items = parsed.get('items', [])
            total_minutes = parsed.get('total_minutes', sum(item.get('duration_minutes', 0) for item in plan_items))

            if task_id:
                TaskManager.update_task_progress(task_id, 85, '保存计划')

            plan = AIStudyPlan(
                user_id=user_id,
                plan_date=datetime.now(timezone.utc),
                items=json.dumps(plan_items, ensure_ascii=False),
                total_minutes=total_minutes,
                total_tokens=response.total_tokens,
            )
            db.session.add(plan)
            db.session.commit()

            if task_id:
                TaskManager.complete_task(task_id, plan.id)

            return {
                'status': 'success',
                'data': {
                    'items': plan_items,
                    'total_minutes': total_minutes,
                    'tips': parsed.get('tips', []),
                },
                'plan_id': plan.id,
            }

        except AllProvidersFailedError as e:
            if task_id:
                TaskManager.fail_task(task_id, str(e))
            return {'status': 'error', 'message': str(e)}
        except Exception as e:
            logger.error(f'学习计划生成失败: {e}', exc_info=True)
            if task_id:
                TaskManager.fail_task(task_id, str(e))
            return {'status': 'error', 'message': str(e)}

    @staticmethod
    def get_plan(user_id: int) -> dict:
        plan = AIStudyPlan.query.filter_by(
            user_id=user_id
        ).order_by(AIStudyPlan.created_at.desc()).first()
        if not plan:
            return {'status': 'no_data', 'message': '暂无学习计划'}
        items = json.loads(plan.items) if plan.items else []
        return {
            'status': 'success',
            'data': {
                'plan_id': plan.id,
                'plan_date': plan.plan_date.isoformat() if plan.plan_date else None,
                'items': items,
                'total_minutes': plan.total_minutes,
                'completed_items': plan.completed_items,
                'total_items': len(items),
                'created_at': plan.created_at.isoformat() if plan.created_at else None,
            },
        }

    @staticmethod
    def update_plan_progress(user_id: int, knowledge_point: str, completed: bool = True) -> dict:
        plan = AIStudyPlan.query.filter_by(
            user_id=user_id
        ).order_by(AIStudyPlan.created_at.desc()).first()
        if not plan:
            return {'status': 'error', 'message': '暂无学习计划'}

        items = json.loads(plan.items) if plan.items else []
        updated = False
        for item in items:
            if item.get('knowledge_point') == knowledge_point:
                item['completed'] = completed
                updated = True
                break

        if not updated:
            return {'status': 'error', 'message': f'未找到知识点: {knowledge_point}'}

        plan.items = json.dumps(items, ensure_ascii=False)
        plan.completed_items = sum(1 for item in items if item.get('completed'))

        if completed:
            review_items = WrongQuestion.get_review_needed(user_id)
            for wq in review_items:
                from app.models.question import Question, Chapter
                question = Question.query.get(wq.question_id)
                if question:
                    chapter = Chapter.query.get(question.chapter_id) if question.chapter_id else None
                    chapter_name = chapter.name if chapter else ''
                    if chapter_name == knowledge_point or knowledge_point in chapter_name:
                        wq.mark_reviewed()

        db.session.commit()
        return {
            'status': 'success',
            'completed_items': plan.completed_items,
            'total_items': len(items),
        }
