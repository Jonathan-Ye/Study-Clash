import logging
from datetime import datetime, timezone, timedelta
from app import db
from app.models.ai_analysis import LLMCallLog, LLMFallbackEvent

logger = logging.getLogger(__name__)


class AuditService:
    @staticmethod
    def log_call(provider_id: int, user_id: int, task_type: str,
                 model_name: str, request_tokens: int, response_tokens: int,
                 total_tokens: int, status: str, error_message: str = None,
                 duration_ms: int = 0):
        try:
            log = LLMCallLog(
                provider_id=provider_id,
                user_id=user_id,
                task_type=task_type,
                model_name=model_name,
                request_tokens=request_tokens,
                response_tokens=response_tokens,
                total_tokens=total_tokens,
                status=status,
                error_message=error_message,
                duration_ms=duration_ms,
            )
            db.session.add(log)
            db.session.commit()
        except Exception as e:
            logger.error(f'写入审计日志失败: {e}')

    @staticmethod
    def log_fallback(from_provider_id: int, to_provider_id: int,
                     task_type: str, reason: str = None):
        try:
            event = LLMFallbackEvent(
                from_provider_id=from_provider_id,
                to_provider_id=to_provider_id,
                task_type=task_type,
                reason=reason,
            )
            db.session.add(event)
            db.session.commit()
        except Exception as e:
            logger.error(f'写入降级事件失败: {e}')

    @staticmethod
    def get_token_statistics(time_range: str = '7d') -> dict:
        now = datetime.now(timezone.utc)
        if time_range == '1d':
            start = now - timedelta(days=1)
        elif time_range == '30d':
            start = now - timedelta(days=30)
        else:
            start = now - timedelta(days=7)

        logs = LLMCallLog.query.filter(
            LLMCallLog.created_at >= start,
            LLMCallLog.status == 'success',
        ).all()

        total_tokens = sum(log.total_tokens for log in logs)
        by_provider = {}
        for log in logs:
            pid = log.provider_id
            if pid not in by_provider:
                by_provider[pid] = {'total_tokens': 0, 'call_count': 0}
            by_provider[pid]['total_tokens'] += log.total_tokens
            by_provider[pid]['call_count'] += 1

        return {
            'time_range': time_range,
            'total_tokens': total_tokens,
            'total_calls': len(logs),
            'by_provider': by_provider,
        }

    @staticmethod
    def get_logs(page: int = 1, per_page: int = 20,
                 task_type: str = None, status: str = None) -> dict:
        query = LLMCallLog.query
        if task_type:
            query = query.filter_by(task_type=task_type)
        if status:
            query = query.filter_by(status=status)
        pagination = query.order_by(LLMCallLog.created_at.desc()).paginate(
            page=page, per_page=per_page, error_out=False
        )
        return {
            'logs': [{
                'id': log.id,
                'provider_id': log.provider_id,
                'task_type': log.task_type,
                'model_name': log.model_name,
                'total_tokens': log.total_tokens,
                'status': log.status,
                'duration_ms': log.duration_ms,
                'created_at': log.created_at.isoformat() if log.created_at else None,
            } for log in pagination.items],
            'total': pagination.total,
            'page': page,
            'per_page': per_page,
        }

    @staticmethod
    def get_fallback_events() -> list:
        events = LLMFallbackEvent.query.order_by(
            LLMFallbackEvent.created_at.desc()
        ).limit(50).all()
        return [{
            'id': e.id,
            'from_provider_id': e.from_provider_id,
            'to_provider_id': e.to_provider_id,
            'task_type': e.task_type,
            'reason': e.reason,
            'created_at': e.created_at.isoformat() if e.created_at else None,
        } for e in events]

    @staticmethod
    def cleanup_old_logs(retention_days: int = 90):
        cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
        deleted = LLMCallLog.query.filter(LLMCallLog.created_at < cutoff).delete()
        LLMFallbackEvent.query.filter(LLMFallbackEvent.created_at < cutoff).delete()
        db.session.commit()
        return deleted
