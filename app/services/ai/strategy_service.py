import json
import logging
from datetime import datetime, timezone
from app import db
from app.models.ai_analysis import AILearningStrategy, AIAnalysisResult, AIPredictionResult
from app.models.wrong_question import WrongQuestion
from app.services.llm import LLMServiceOrchestrator, AllProvidersFailedError
from app.services.ai.data_sanitizer import DataSanitizer
from app.services.ai.prompt_manager import PromptTemplateManager
from app.services.ai.task_manager import TaskManager
from app.services.ai.cache_manager import CacheManager

logger = logging.getLogger(__name__)


class PrerequisiteNotMetError(Exception):
    pass


class StrategyService:
    @staticmethod
    def _get_review_plan(user_id: int) -> dict:
        pending_reviews = WrongQuestion.get_review_needed(user_id)
        return {
            'pending_count': len(pending_reviews),
            'items': [
                {
                    'question_id': wq.question_id,
                    'next_review_at': wq.next_review_at.isoformat() if wq.next_review_at else None,
                    'wrong_count': wq.wrong_count,
                }
                for wq in pending_reviews[:20]
            ]
        }

    @staticmethod
    def _resolve_schedule_conflicts(strategy_data: dict, review_plan: dict) -> dict:
        return strategy_data

    @staticmethod
    def _check_strategy_needs_update(user_id: int) -> bool:
        strategy = AILearningStrategy.query.filter_by(
            user_id=user_id
        ).order_by(AILearningStrategy.created_at.desc()).first()
        if not strategy:
            return True
        from datetime import timedelta
        threshold = strategy.created_at
        new_wrong = WrongQuestion.query.filter_by(user_id=user_id).filter(
            WrongQuestion.created_at > threshold
        ).count()
        mastered_changed = WrongQuestion.query.filter_by(user_id=user_id).filter(
            WrongQuestion.mastered_at > threshold
        ).count()
        return new_wrong > 5 or mastered_changed > 3

    @staticmethod
    def generate(user_id: int, task_id: int = None) -> dict:
        try:
            if task_id:
                TaskManager.update_task_progress(task_id, 10, '检查前置依赖')

            analysis = AIAnalysisResult.query.filter_by(
                user_id=user_id
            ).order_by(AIAnalysisResult.created_at.desc()).first()
            prediction = AIPredictionResult.query.filter_by(
                user_id=user_id
            ).order_by(AIPredictionResult.created_at.desc()).first()

            if not analysis:
                if task_id:
                    TaskManager.fail_task(task_id, '请先完成归因分析')
                return {'status': 'error', 'message': '请先完成归因分析'}
            if not prediction:
                if task_id:
                    TaskManager.fail_task(task_id, '请先完成推理预测')
                return {'status': 'error', 'message': '请先完成推理预测'}

            if task_id:
                TaskManager.update_task_progress(task_id, 30, '获取复习计划')

            review_plan = StrategyService._get_review_plan(user_id)
            attribution_data = {
                'root_causes': json.loads(analysis.root_causes) if analysis.root_causes else [],
                'knowledge_mastery': json.loads(analysis.knowledge_mastery) if analysis.knowledge_mastery else [],
            }
            prediction_data = {
                'weak_points': json.loads(prediction.weak_points) if prediction.weak_points else [],
            }

            if task_id:
                TaskManager.update_task_progress(task_id, 50, '调用大模型生成策略')

            prompt = PromptTemplateManager.render('learning_strategy', {
                'attribution': json.dumps(attribution_data, ensure_ascii=False, indent=2),
                'prediction': json.dumps(prediction_data, ensure_ascii=False, indent=2),
                'review_plan': json.dumps(review_plan, ensure_ascii=False, indent=2),
            })

            response = LLMServiceOrchestrator.invoke(
                task_type='strategy',
                system_prompt='你是一位个性化学习策略规划专家。',
                user_prompt=prompt,
                user_id=user_id,
            )

            if task_id:
                TaskManager.update_task_progress(task_id, 70, '解析策略结果')

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
                if task_id:
                    TaskManager.fail_task(task_id, '大模型返回格式异常')
                return {'status': 'error', 'message': '大模型返回格式异常'}

            result = StrategyService._resolve_schedule_conflicts(result, review_plan)

            if task_id:
                TaskManager.update_task_progress(task_id, 85, '保存策略结果')

            needs_update = False
            strategy = AILearningStrategy(
                user_id=user_id,
                learning_path=json.dumps(result.get('learning_path', []), ensure_ascii=False),
                review_suggestions=json.dumps(result.get('review_suggestions', []), ensure_ascii=False),
                focus_directions=json.dumps(result.get('focus_directions', []), ensure_ascii=False),
                needs_update=needs_update,
                total_tokens=response.total_tokens,
            )
            db.session.add(strategy)
            db.session.commit()

            CacheManager.save_strategy(user_id, result)

            if task_id:
                TaskManager.complete_task(task_id, strategy.id)

            return {'status': 'success', 'data': result, 'strategy_id': strategy.id}

        except AllProvidersFailedError as e:
            if task_id:
                TaskManager.fail_task(task_id, str(e))
            return {'status': 'error', 'message': str(e)}
        except Exception as e:
            logger.error(f'策略生成失败: {e}', exc_info=True)
            if task_id:
                TaskManager.fail_task(task_id, str(e))
            return {'status': 'error', 'message': str(e)}

    @staticmethod
    def get_result(user_id: int) -> dict:
        strategy = AILearningStrategy.query.filter_by(
            user_id=user_id
        ).order_by(AILearningStrategy.created_at.desc()).first()
        if not strategy:
            return {'status': 'no_data', 'message': '暂未生成学习策略'}
        needs_update = StrategyService._check_strategy_needs_update(user_id)
        return {
            'status': 'success',
            'data': {
                'learning_path': json.loads(strategy.learning_path) if strategy.learning_path else [],
                'review_suggestions': json.loads(strategy.review_suggestions) if strategy.review_suggestions else [],
                'focus_directions': json.loads(strategy.focus_directions) if strategy.focus_directions else [],
                'needs_update': needs_update,
                'created_at': strategy.created_at.isoformat() if strategy.created_at else None,
            }
        }
