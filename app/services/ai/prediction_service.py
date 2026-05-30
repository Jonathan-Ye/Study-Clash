import json
import logging
from datetime import datetime, timezone, timedelta
from app import db
from app.models.ai_analysis import AIPredictionResult
from app.models.wrong_question import WrongQuestion
from app.services.llm import LLMServiceOrchestrator, AllProvidersFailedError
from app.services.ai.data_sanitizer import DataSanitizer
from app.services.ai.cache_manager import CacheManager
from app.services.ai.prompt_manager import PromptTemplateManager
from app.services.ai.task_manager import TaskManager

logger = logging.getLogger(__name__)


class PredictionService:
    @staticmethod
    def _count_wrong_records(user_id: int) -> int:
        return WrongQuestion.query.filter_by(user_id=user_id).count()

    @staticmethod
    def _aggregate_prediction_data(user_id: int) -> dict:
        wrong_questions = WrongQuestion.query.filter_by(user_id=user_id).order_by(
            WrongQuestion.created_at.desc()
        ).limit(100).all()
        records = []
        for wq in wrong_questions:
            from app.models.question import Question, Chapter, Subject
            question = Question.query.get(wq.question_id)
            if not question:
                continue
            chapter = Chapter.query.get(question.chapter_id) if question.chapter_id else None
            records.append({
                'question_id': wq.question_id,
                'question_type': question.question_type,
                'difficulty': question.difficulty,
                'chapter': chapter.name if chapter else '未知',
                'wrong_count': wq.wrong_count,
                'is_mastered': wq.is_mastered,
                'wrong_reason': wq.wrong_reason,
                'created_at': wq.created_at.isoformat() if wq.created_at else None,
            })
        return {
            'total_count': len(records),
            'records': records,
            'mastered_rate': sum(1 for r in records if r['is_mastered']) / len(records) if records else 0,
        }

    @staticmethod
    def _parse_prediction_response(content: str) -> dict:
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
    def predict(user_id: int, task_id: int = None) -> dict:
        try:
            if task_id:
                TaskManager.update_task_progress(task_id, 10, '检查数据充分性')

            count = PredictionService._count_wrong_records(user_id)
            if count < 5:
                if task_id:
                    TaskManager.complete_task(task_id)
                return {
                    'status': 'insufficient_data',
                    'message': f'错题数据不足（当前{count}条，至少需要5条）',
                }

            if task_id:
                TaskManager.update_task_progress(task_id, 20, '检查缓存时效性')

            cached = CacheManager.get_prediction(user_id)
            if cached:
                existing = AIPredictionResult.query.filter_by(
                    user_id=user_id
                ).order_by(AIPredictionResult.created_at.desc()).first()
                if existing and existing.expires_at > datetime.now(timezone.utc):
                    if task_id:
                        TaskManager.complete_task(task_id)
                    return {'status': 'cached', 'data': cached}

            if task_id:
                TaskManager.update_task_progress(task_id, 40, '聚合数据')

            data = PredictionService._aggregate_prediction_data(user_id)
            sanitized_data = DataSanitizer.sanitize(data)

            if task_id:
                TaskManager.update_task_progress(task_id, 50, '调用大模型预测')

            prompt = PromptTemplateManager.render('weak_point_prediction', {
                'data': json.dumps(sanitized_data, ensure_ascii=False, indent=2),
            })

            response = LLMServiceOrchestrator.invoke(
                task_type='prediction',
                system_prompt='你是一位教育数据预测专家，擅长基于历史学习数据预测薄弱点和出错趋势。',
                user_prompt=prompt,
                user_id=user_id,
            )

            if task_id:
                TaskManager.update_task_progress(task_id, 70, '解析预测结果')

            parsed = PredictionService._parse_prediction_response(response.content)
            if not parsed:
                if task_id:
                    TaskManager.fail_task(task_id, '大模型返回格式异常')
                return {'status': 'error', 'message': '大模型返回格式异常'}

            weak_points = parsed.get('weak_points', [])
            error_predictions = parsed.get('error_predictions', [])

            weak_points.sort(key=lambda x: x.get('probability', 0), reverse=True)
            weak_points = weak_points[:10]
            error_predictions.sort(key=lambda x: x.get('probability', 0), reverse=True)
            error_predictions = error_predictions[:20]

            low_confidence = all(wp.get('probability', 0) < 0.4 for wp in weak_points) if weak_points else True
            expires_at = datetime.now(timezone.utc) + timedelta(days=7)

            if task_id:
                TaskManager.update_task_progress(task_id, 85, '保存预测结果')

            result = AIPredictionResult(
                user_id=user_id,
                weak_points=json.dumps(weak_points, ensure_ascii=False),
                error_predictions=json.dumps(error_predictions, ensure_ascii=False),
                low_confidence=low_confidence,
                is_expired=False,
                expires_at=expires_at,
                total_tokens=response.total_tokens,
            )
            db.session.add(result)
            db.session.commit()

            result_data = {
                'weak_points': weak_points,
                'error_predictions': error_predictions,
                'low_confidence': low_confidence,
                'expires_at': expires_at.isoformat(),
            }
            CacheManager.save_prediction(user_id, result_data)

            if task_id:
                TaskManager.complete_task(task_id, result.id)

            return {'status': 'success', 'data': result_data, 'prediction_id': result.id}

        except AllProvidersFailedError as e:
            if task_id:
                TaskManager.fail_task(task_id, str(e))
            return {'status': 'error', 'message': str(e)}
        except Exception as e:
            logger.error(f'推理预测失败: {e}', exc_info=True)
            if task_id:
                TaskManager.fail_task(task_id, str(e))
            return {'status': 'error', 'message': str(e)}

    @staticmethod
    def get_result(user_id: int) -> dict:
        prediction = AIPredictionResult.query.filter_by(
            user_id=user_id
        ).order_by(AIPredictionResult.created_at.desc()).first()
        if not prediction:
            return {'status': 'no_data', 'message': '暂未进行推理预测'}
        is_expired = prediction.expires_at < datetime.now(timezone.utc)
        return {
            'status': 'success',
            'data': {
                'weak_points': json.loads(prediction.weak_points) if prediction.weak_points else [],
                'error_predictions': json.loads(prediction.error_predictions) if prediction.error_predictions else [],
                'low_confidence': prediction.low_confidence,
                'is_expired': is_expired,
                'expires_at': prediction.expires_at.isoformat(),
                'created_at': prediction.created_at.isoformat() if prediction.created_at else None,
            }
        }
