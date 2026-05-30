import json
import logging
from datetime import datetime, timezone
from collections import defaultdict
from app import db
from app.models.ai_analysis import AIComparisonResult
from app.models.wrong_question import WrongQuestion
from app.models.question import Question, Chapter
from app.services.llm import LLMServiceOrchestrator, AllProvidersFailedError
from app.services.ai.data_sanitizer import DataSanitizer
from app.services.ai.prompt_manager import PromptTemplateManager
from app.services.ai.task_manager import TaskManager

logger = logging.getLogger(__name__)


class ComparisonService:
    @staticmethod
    def _group_similar_wrong_questions(user_id: int, task_id: int = None) -> dict:
        wrong_questions = WrongQuestion.query.filter_by(user_id=user_id).all()
        if not wrong_questions:
            return {}

        records_by_chapter = defaultdict(list)
        records_by_type = defaultdict(list)

        for wq in wrong_questions:
            question = Question.query.get(wq.question_id)
            if not question:
                continue
            chapter = Chapter.query.get(question.chapter_id) if question.chapter_id else None
            record = {
                'question_id': wq.question_id,
                'question_type': question.question_type,
                'difficulty': question.difficulty,
                'chapter': chapter.name if chapter else '未知',
                'chapter_id': question.chapter_id,
                'wrong_answer': wq.wrong_answer,
                'wrong_count': wq.wrong_count,
                'wrong_reason': wq.wrong_reason,
                'is_mastered': wq.is_mastered,
            }
            chapter_key = chapter.name if chapter else '未知'
            records_by_chapter[chapter_key].append(record)
            records_by_type[question.question_type].append(record)

        groups = {}
        for chapter_name, items in records_by_chapter.items():
            if len(items) >= 2:
                groups[f'chapter:{chapter_name}'] = {
                    'group_type': 'chapter',
                    'group_name': chapter_name,
                    'count': len(items),
                    'records': items[:30],
                }
        for q_type, items in records_by_type.items():
            if len(items) >= 2:
                groups[f'type:{q_type}'] = {
                    'group_type': 'question_type',
                    'group_name': q_type,
                    'count': len(items),
                    'records': items[:30],
                }

        return groups

    @staticmethod
    def _parse_comparison_response(content: str) -> dict:
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
    def compare_similar(user_id: int, task_id: int = None) -> dict:
        try:
            if task_id:
                TaskManager.update_task_progress(task_id, 10, '聚合同类错题数据')

            groups = ComparisonService._group_similar_wrong_questions(user_id)
            if not groups:
                if task_id:
                    TaskManager.complete_task(task_id)
                return {'status': 'no_data', 'message': '暂无足够同类错题进行对比'}

            if task_id:
                TaskManager.update_task_progress(task_id, 30, '数据脱敏')

            sanitized_groups = {}
            for key, group in groups.items():
                sanitized_records = DataSanitizer.sanitize({'records': group['records']})
                sanitized_groups[key] = {
                    'group_type': group['group_type'],
                    'group_name': group['group_name'],
                    'count': group['count'],
                    'records': sanitized_records.get('records', group['records']),
                }

            if task_id:
                TaskManager.update_task_progress(task_id, 50, '调用大模型分析共性模式')

            prompt = PromptTemplateManager.render('comparison_analysis', {
                'groups': json.dumps(sanitized_groups, ensure_ascii=False, indent=2)
            })

            response = LLMServiceOrchestrator.invoke(
                task_type='attribution',
                system_prompt='你是一位教育错题分析专家，擅长横向对比同类错题，发现共性错误模式。',
                user_prompt=prompt,
                user_id=user_id,
            )

            if task_id:
                TaskManager.update_task_progress(task_id, 70, '解析对比结果')

            parsed = ComparisonService._parse_comparison_response(response.content)
            if not parsed:
                if task_id:
                    TaskManager.fail_task(task_id, '大模型返回格式异常')
                return {'status': 'error', 'message': '大模型返回格式异常'}

            if task_id:
                TaskManager.update_task_progress(task_id, 85, '保存对比结果')

            comparison = AIComparisonResult(
                user_id=user_id,
                comparison_groups=json.dumps(groups, ensure_ascii=False),
                common_patterns=json.dumps(parsed.get('common_patterns', []), ensure_ascii=False),
                suggestions=json.dumps(parsed.get('suggestions', []), ensure_ascii=False),
                total_tokens=response.total_tokens,
            )
            db.session.add(comparison)
            db.session.commit()

            if task_id:
                TaskManager.complete_task(task_id, comparison.id)

            return {
                'status': 'success',
                'data': {
                    'comparison_groups': groups,
                    'common_patterns': parsed.get('common_patterns', []),
                    'suggestions': parsed.get('suggestions', []),
                },
                'comparison_id': comparison.id,
            }

        except AllProvidersFailedError as e:
            if task_id:
                TaskManager.fail_task(task_id, str(e))
            return {'status': 'error', 'message': str(e)}
        except Exception as e:
            logger.error(f'错题对比分析失败: {e}', exc_info=True)
            if task_id:
                TaskManager.fail_task(task_id, str(e))
            return {'status': 'error', 'message': str(e)}

    @staticmethod
    def get_result(user_id: int) -> dict:
        comparison = AIComparisonResult.query.filter_by(
            user_id=user_id
        ).order_by(AIComparisonResult.created_at.desc()).first()
        if not comparison:
            return {'status': 'no_data', 'message': '暂未进行错题对比分析'}
        return {
            'status': 'success',
            'data': {
                'comparison_groups': json.loads(comparison.comparison_groups) if comparison.comparison_groups else {},
                'common_patterns': json.loads(comparison.common_patterns) if comparison.common_patterns else [],
                'suggestions': json.loads(comparison.suggestions) if comparison.suggestions else [],
                'created_at': comparison.created_at.isoformat() if comparison.created_at else None,
            }
        }
