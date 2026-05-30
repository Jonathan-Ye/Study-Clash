import json
import logging
from datetime import datetime, timezone
from app import db, socketio
from app.models.ai_analysis import AIChatSession, AIChatMessage
from app.services.llm import LLMServiceOrchestrator, AllProvidersFailedError
from app.services.ai.data_sanitizer import DataSanitizer
from app.services.ai.prompt_manager import PromptTemplateManager
from app.services.ai.safety_checker import ContentSafetyChecker
from app.services.ai.feature_switch import AIFeatureSwitchService

logger = logging.getLogger(__name__)

MAX_INPUT_LENGTH = 500
CONTEXT_ROUNDS = 10


class ChatService:
    @staticmethod
    def create_session(user_id: int) -> dict:
        allowed, msg = AIFeatureSwitchService.check_access('chat')
        if not allowed:
            return {'status': 'error', 'message': msg}

        session = AIChatSession(
            user_id=user_id,
            title='AI对话',
            status='active',
        )
        db.session.add(session)
        db.session.commit()
        return {
            'status': 'success',
            'session_id': session.id,
            'title': session.title,
        }

    @staticmethod
    def send_message(session_id: int, user_message: str) -> dict:
        try:
            allowed, msg = AIFeatureSwitchService.check_access('chat')
            if not allowed:
                return {'status': 'error', 'message': msg}

            session = AIChatSession.query.get(session_id)
            if not session or session.status != 'active':
                return {'status': 'error', 'message': '会话不存在或已关闭'}

            if not user_message or not user_message.strip():
                return {'status': 'error', 'message': '消息不能为空'}

            if len(user_message) > MAX_INPUT_LENGTH:
                return {'status': 'error', 'message': f'消息长度不能超过{MAX_INPUT_LENGTH}字'}

            is_safe, safety_reason = ContentSafetyChecker.is_safe(user_message)
            if not is_safe:
                return {'status': 'error', 'message': safety_reason}

            sanitized_msg = DataSanitizer.sanitize({'content': user_message}).get('content', user_message)

            user_msg_record = AIChatMessage(
                session_id=session_id,
                role='user',
                content=sanitized_msg,
            )
            db.session.add(user_msg_record)
            db.session.commit()

            history_messages = AIChatMessage.query.filter_by(
                session_id=session_id
            ).order_by(AIChatMessage.created_at.desc()).limit(CONTEXT_ROUNDS * 2).all()
            history_messages.reverse()

            history_lines = []
            for msg in history_messages:
                role_label = '学生' if msg.role == 'user' else 'AI助手'
                history_lines.append(f'{role_label}: {msg.content}')
            history_text = '\n'.join(history_lines)

            prompt = PromptTemplateManager.render('chat_assistant', {
                'history': history_text,
                'question': sanitized_msg,
            })

            response = LLMServiceOrchestrator.invoke(
                task_type='attribution',
                system_prompt='你是一位专业的教育AI助手，擅长解答学习问题、分析错题原因、提供学习建议。',
                user_prompt=prompt,
                user_id=session.user_id,
            )

            ai_content = response.content

            ai_msg_record = AIChatMessage(
                session_id=session_id,
                role='assistant',
                content=ai_content,
                tokens=response.total_tokens,
            )
            db.session.add(ai_msg_record)

            session.updated_at = datetime.now(timezone.utc)
            db.session.commit()

            ChatService._stream_response(session.user_id, session_id, ai_content)

            return {
                'status': 'success',
                'message': ai_content,
                'tokens': response.total_tokens,
            }

        except AllProvidersFailedError as e:
            return {'status': 'error', 'message': str(e)}
        except Exception as e:
            logger.error(f'AI对话消息处理失败: {e}', exc_info=True)
            return {'status': 'error', 'message': str(e)}

    @staticmethod
    def _stream_response(user_id: int, session_id: int, content: str):
        try:
            chunk_size = 5
            for i in range(0, len(content), chunk_size):
                chunk = content[i:i + chunk_size]
                is_last = (i + chunk_size) >= len(content)
                socketio.emit('ai_chat_chunk', {
                    'session_id': session_id,
                    'chunk': chunk,
                    'is_last': is_last,
                }, room=f'user_{user_id}')
        except Exception as e:
            logger.error(f'流式推送失败: {e}')

    @staticmethod
    def get_history(session_id: int, limit: int = 20) -> dict:
        session = AIChatSession.query.get(session_id)
        if not session:
            return {'status': 'error', 'message': '会话不存在'}

        messages = AIChatMessage.query.filter_by(
            session_id=session_id
        ).order_by(AIChatMessage.created_at.desc()).limit(limit).all()
        messages.reverse()

        return {
            'status': 'success',
            'messages': [
                {
                    'id': msg.id,
                    'role': msg.role,
                    'content': msg.content,
                    'tokens': msg.tokens,
                    'created_at': msg.created_at.isoformat() if msg.created_at else None,
                }
                for msg in messages
            ],
        }

    @staticmethod
    def close_session(session_id: int) -> dict:
        session = AIChatSession.query.get(session_id)
        if not session:
            return {'status': 'error', 'message': '会话不存在'}

        session.status = 'closed'
        session.updated_at = datetime.now(timezone.utc)
        db.session.commit()
        return {'status': 'success', 'message': '会话已关闭'}
