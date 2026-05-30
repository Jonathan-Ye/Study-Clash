import json
import logging
from datetime import datetime, timezone
from app import db
from app.models.ai_analysis import AIAnalysisResult
from app.models.wrong_question import WrongQuestion
from app.models.question import Question, Chapter, Subject
from app.services.llm import LLMServiceOrchestrator, AllProvidersFailedError
from app.services.ai.data_sanitizer import DataSanitizer
from app.services.ai.cache_manager import CacheManager
from app.services.ai.prompt_manager import PromptTemplateManager
from app.services.ai.task_manager import TaskManager

logger = logging.getLogger(__name__)


class AttributionService:
    @staticmethod
    def _aggregate_wrong_data(user_id: int) -> dict:
        wrong_questions = WrongQuestion.query.filter_by(user_id=user_id).all()
        if not wrong_questions:
            return {}

        records = []
        for wq in wrong_questions:
            question = Question.query.get(wq.question_id)
            if not question:
                continue
            chapter = Chapter.query.get(question.chapter_id) if question.chapter_id else None
            subject = Subject.query.get(question.subject_id) if question.subject_id else None
            records.append({
                'question_id': wq.question_id,
                'question_type': question.question_type,
                'difficulty': question.difficulty,
                'chapter': chapter.name if chapter else '未知',
                'subject': subject.name if subject else '未知',
                'wrong_answer': wq.wrong_answer,
                'wrong_count': wq.wrong_count,
                'wrong_reason': wq.wrong_reason,
                'is_mastered': wq.is_mastered,
                'review_count': wq.review_count,
                'consecutive_correct': wq.consecutive_correct,
            })

        from collections import Counter
        chapter_stats = Counter(r['chapter'] for r in records)
        subject_stats = Counter(r['subject'] for r in records)
        reason_stats = Counter(r['wrong_reason'] for r in records if r['wrong_reason'])
        difficulty_stats = Counter(r['difficulty'] for r in records)

        return {
            'total_wrong': len(records),
            'mastered_count': sum(1 for r in records if r['is_mastered']),
            'records': records[:50],
            'chapter_distribution': dict(chapter_stats.most_common(20)),
            'subject_distribution': dict(subject_stats.most_common(10)),
            'reason_distribution': dict(reason_stats),
            'difficulty_distribution': dict(difficulty_stats),
        }

    @staticmethod
    def _parse_attribution_response(content: str) -> dict:
        try:
            text = content.strip()
            if text.startswith('```'):
                lines = text.split('\n')
                text = '\n'.join(lines[1:-1])
            result = json.loads(text)
            return result
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
    def _annotate_confidence(result: dict) -> dict:
        if not result:
            return result
        root_causes = result.get('root_causes', [])
        for cause in root_causes:
            conf = cause.get('confidence', 0.5)
            cause['needs_review'] = conf < 0.7
        mastery = result.get('knowledge_mastery', [])
        for item in mastery:
            score = item.get('score', 50)
            if score < 30:
                item['level'] = '薄弱'
            elif score < 60:
                item['level'] = '待提升'
            elif score < 80:
                item['level'] = '良好'
            else:
                item['level'] = '掌握'
        avg_confidence = 0
        if root_causes:
            avg_confidence = sum(c.get('confidence', 0.5) for c in root_causes) / len(root_causes)
        result['overall_confidence'] = round(avg_confidence, 2)
        result['needs_review'] = avg_confidence < 0.7
        return result

    @staticmethod
    def analyze(user_id: int, task_id: int = None) -> dict:
        try:
            if task_id:
                TaskManager.update_task_progress(task_id, 10, '聚合错题数据')

            data = AttributionService._aggregate_wrong_data(user_id)
            if not data:
                if task_id:
                    TaskManager.complete_task(task_id)
                return {'status': 'no_data', 'message': '暂无错题数据'}

            if task_id:
                TaskManager.update_task_progress(task_id, 30, '检查缓存')

            data_hash = CacheManager.compute_data_hash(data)
            cached = CacheManager.get_analysis(user_id, data_hash)
            if cached:
                if task_id:
                    TaskManager.complete_task(task_id)
                return {'status': 'cached', 'data': cached}

            if task_id:
                TaskManager.update_task_progress(task_id, 40, '数据脱敏')

            sanitized_data = DataSanitizer.sanitize(data)

            if task_id:
                TaskManager.update_task_progress(task_id, 50, '调用大模型分析')

            prompt = PromptTemplateManager.render('attribution_analysis', {
                'data': json.dumps(sanitized_data, ensure_ascii=False, indent=2)
            })

            response = LLMServiceOrchestrator.invoke(
                task_type='attribution',
                system_prompt='你是一位专业的教育数据分析专家，擅长错题归因分析和知识点掌握度评估。',
                user_prompt=prompt,
                user_id=user_id,
            )

            if task_id:
                TaskManager.update_task_progress(task_id, 70, '解析分析结果')

            parsed = AttributionService._parse_attribution_response(response.content)
            if not parsed:
                if task_id:
                    TaskManager.fail_task(task_id, '大模型返回格式异常')
                return {'status': 'error', 'message': '大模型返回格式异常'}

            result = AttributionService._annotate_confidence(parsed)

            if task_id:
                TaskManager.update_task_progress(task_id, 85, '保存分析结果')

            analysis = AIAnalysisResult(
                user_id=user_id,
                data_hash=data_hash,
                root_causes=json.dumps(result.get('root_causes', []), ensure_ascii=False),
                knowledge_mastery=json.dumps(result.get('knowledge_mastery', []), ensure_ascii=False),
                ability_scores=json.dumps(result.get('ability_scores', {}), ensure_ascii=False),
                suggestions=json.dumps(result.get('suggestions', []), ensure_ascii=False),
                confidence=result.get('overall_confidence', 0),
                needs_review=result.get('needs_review', False),
                total_tokens=response.total_tokens,
            )
            db.session.add(analysis)
            db.session.commit()

            CacheManager.save_analysis(user_id, data_hash, result)

            if task_id:
                TaskManager.complete_task(task_id, analysis.id)

            return {'status': 'success', 'data': result, 'analysis_id': analysis.id}

        except AllProvidersFailedError as e:
            if task_id:
                TaskManager.fail_task(task_id, str(e))
            return {'status': 'error', 'message': str(e)}
        except Exception as e:
            logger.error(f'归因分析失败: {e}', exc_info=True)
            if task_id:
                TaskManager.fail_task(task_id, str(e))
            return {'status': 'error', 'message': str(e)}

    @staticmethod
    def get_result(user_id: int) -> dict:
        analysis = AIAnalysisResult.query.filter_by(
            user_id=user_id
        ).order_by(AIAnalysisResult.created_at.desc()).first()
        if not analysis:
            return {'status': 'no_data', 'message': '暂未进行归因分析'}
        return {
            'status': 'success',
            'data': {
                'root_causes': json.loads(analysis.root_causes) if analysis.root_causes else [],
                'knowledge_mastery': json.loads(analysis.knowledge_mastery) if analysis.knowledge_mastery else [],
                'ability_scores': json.loads(analysis.ability_scores) if analysis.ability_scores else {},
                'suggestions': json.loads(analysis.suggestions) if analysis.suggestions else [],
                'confidence': analysis.confidence,
                'needs_review': analysis.needs_review,
                'created_at': analysis.created_at.isoformat() if analysis.created_at else None,
            }
        }
