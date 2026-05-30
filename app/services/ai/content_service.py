import json
import logging
from datetime import datetime, timezone
from app import db
from app.models.ai_analysis import AIGeneratedContent
from app.models.question import Question
from app.services.llm import LLMServiceOrchestrator, AllProvidersFailedError
from app.services.ai.prompt_manager import PromptTemplateManager
from app.services.ai.safety_checker import ContentSafetyChecker
from app.services.ai.task_manager import TaskManager

logger = logging.getLogger(__name__)


class ContentService:
    @staticmethod
    def generate_explanation(question_id: int, user_id: int) -> dict:
        question = Question.query.get(question_id)
        if not question:
            return {'status': 'error', 'message': '题目不存在'}

        existing = AIGeneratedContent.query.filter_by(
            question_id=question_id,
            content_type='explanation',
        ).order_by(AIGeneratedContent.created_at.desc()).first()
        if existing and existing.review_status != 'rejected':
            return {
                'status': 'cached',
                'data': {
                    'content': json.loads(existing.content) if existing.content else {},
                    'content_id': existing.id,
                    'is_ai_generated': True,
                }
            }

        prompt = PromptTemplateManager.render('explanation_generation', {
            'question_type': Question.QUESTION_TYPES.get(question.question_type, '未知'),
            'difficulty': Question.DIFFICULTY_LEVELS.get(question.difficulty, '中等'),
            'content': question.content,
            'correct_answer': question.correct_answer,
            'wrong_answer': '',
        })

        try:
            response = LLMServiceOrchestrator.invoke(
                task_type='explanation',
                system_prompt='你是一位优秀的学科教师，擅长为错题生成详细解析。',
                user_prompt=prompt,
                user_id=user_id,
            )

            text = response.content.strip()
            if text.startswith('```'):
                lines = text.split('\n')
                text = '\n'.join(lines[1:-1])
            parsed = json.loads(text)
        except (json.JSONDecodeError, AllProvidersFailedError) as e:
            return {'status': 'error', 'message': f'生成解析失败: {str(e)}'}

        is_safe, reason = ContentSafetyChecker.check_json_content(parsed)
        if not is_safe:
            return {'status': 'error', 'message': f'内容安全校验未通过: {reason}'}

        content = AIGeneratedContent(
            user_id=user_id,
            content_type='explanation',
            question_id=question_id,
            content=json.dumps(parsed, ensure_ascii=False),
            is_ai_generated=True,
            review_status='not_required',
            total_tokens=response.total_tokens,
        )
        db.session.add(content)
        db.session.commit()

        return {
            'status': 'success',
            'data': {
                'content': parsed,
                'content_id': content.id,
                'is_ai_generated': True,
            }
        }

    @staticmethod
    def generate_variant_questions(question_id: int, user_id: int) -> dict:
        question = Question.query.get(question_id)
        if not question:
            return {'status': 'error', 'message': '题目不存在'}

        from app.models.question import Chapter
        chapter = Chapter.query.get(question.chapter_id) if question.chapter_id else None

        prompt = PromptTemplateManager.render('variant_generation', {
            'question_type': Question.QUESTION_TYPES.get(question.question_type, '未知'),
            'chapter': chapter.name if chapter else '未知',
            'difficulty': Question.DIFFICULTY_LEVELS.get(question.difficulty, '中等'),
            'content': question.content,
            'correct_answer': question.correct_answer,
        })

        try:
            response = LLMServiceOrchestrator.invoke(
                task_type='variant',
                system_prompt='你是一位经验丰富的出题专家。',
                user_prompt=prompt,
                user_id=user_id,
            )

            text = response.content.strip()
            if text.startswith('```'):
                lines = text.split('\n')
                text = '\n'.join(lines[1:-1])
            parsed = json.loads(text)
            if isinstance(parsed, dict) and 'variants' in parsed:
                parsed = parsed['variants']
            if not isinstance(parsed, list):
                parsed = [parsed]
        except (json.JSONDecodeError, AllProvidersFailedError) as e:
            return {'status': 'error', 'message': f'生成变式题失败: {str(e)}'}

        valid_variants = []
        for variant in parsed[:3]:
            if not variant.get('content') or not variant.get('correct_answer'):
                continue
            is_safe, reason = ContentSafetyChecker.check_json_content(variant)
            if not is_safe:
                continue
            valid_variants.append(variant)

        saved = []
        for variant in valid_variants:
            content = AIGeneratedContent(
                user_id=user_id,
                content_type='variant',
                question_id=question_id,
                content=json.dumps(variant, ensure_ascii=False),
                is_ai_generated=True,
                review_status='pending',
                total_tokens=0,
            )
            db.session.add(content)
            saved.append({
                'content_id': content.id,
                'content': variant,
                'review_status': 'pending',
                'is_ai_generated': True,
            })
        db.session.commit()

        return {'status': 'success', 'data': saved}

    @staticmethod
    def generate_practice(knowledge_point: str, user_id: int, difficulty: int = 2) -> dict:
        prompt = PromptTemplateManager.render('practice_generation', {
            'knowledge_point': knowledge_point,
            'chapter': knowledge_point,
            'difficulty': Question.DIFFICULTY_LEVELS.get(difficulty, '中等'),
        })

        try:
            response = LLMServiceOrchestrator.invoke(
                task_type='practice',
                system_prompt='你是一位练习题设计专家。',
                user_prompt=prompt,
                user_id=user_id,
            )

            text = response.content.strip()
            if text.startswith('```'):
                lines = text.split('\n')
                text = '\n'.join(lines[1:-1])
            parsed = json.loads(text)
            if not isinstance(parsed, list):
                parsed = [parsed]
        except (json.JSONDecodeError, AllProvidersFailedError) as e:
            return {'status': 'error', 'message': f'生成练习题失败: {str(e)}'}

        valid = []
        for item in parsed[:5]:
            if not item.get('content') or not item.get('correct_answer'):
                continue
            is_safe, reason = ContentSafetyChecker.check_json_content(item)
            if not is_safe:
                continue
            valid.append(item)

        return {
            'status': 'success',
            'data': valid,
            'is_ai_generated': True,
        }

    @staticmethod
    def review_variant_question(content_id: int, reviewer_id: int, approved: bool) -> dict:
        content = AIGeneratedContent.query.get(content_id)
        if not content:
            return {'status': 'error', 'message': '内容不存在'}
        if content.content_type != 'variant':
            return {'status': 'error', 'message': '仅变式题需要审核'}
        if content.review_status != 'pending':
            return {'status': 'error', 'message': '该内容已审核'}

        content.reviewed_by = reviewer_id
        content.reviewed_at = datetime.now(timezone.utc)
        if approved:
            content.review_status = 'approved'
            variant_data = json.loads(content.content) if content.content else {}
            try:
                question = Question(
                    subject_id=1,
                    content=variant_data.get('content', ''),
                    question_type='single',
                    difficulty=2,
                    correct_answer=variant_data.get('correct_answer', ''),
                    analysis=variant_data.get('analysis', ''),
                    option_a=variant_data.get('option_a', ''),
                    option_b=variant_data.get('option_b', ''),
                    option_c=variant_data.get('option_c', ''),
                    option_d=variant_data.get('option_d', ''),
                    created_by=reviewer_id,
                )
                db.session.add(question)
            except Exception as e:
                logger.error(f'变式题入库失败: {e}')
        else:
            content.review_status = 'rejected'

        db.session.commit()
        return {'status': 'success', 'review_status': content.review_status}
