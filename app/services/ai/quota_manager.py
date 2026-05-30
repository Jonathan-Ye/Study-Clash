import logging
from datetime import datetime, timezone, timedelta
from app import db
from app.models.ai_analysis import AIUsageQuota
from app.models.system import SystemSetting

logger = logging.getLogger(__name__)


class QuotaManager:
    @staticmethod
    def check_user_quota(user_id: int, task_type: str = None) -> tuple:
        user_quota = AIUsageQuota.query.filter_by(
            target_type='user', target_id=user_id
        ).first()
        if user_quota and user_quota.daily_call_limit > 0:
            if user_quota.current_daily_calls >= user_quota.daily_call_limit:
                return False, f'个人配额已用完({user_quota.current_daily_calls}/{user_quota.daily_call_limit}次/天)'
        return True, None

    @staticmethod
    def consume_user_quota(user_id: int, tokens: int = 0):
        quota = AIUsageQuota.query.filter_by(
            target_type='user', target_id=user_id
        ).first()
        if not quota:
            default_limit = int(SystemSetting.get('ai_default_daily_calls', '100'))
            default_tokens = int(SystemSetting.get('ai_default_daily_tokens', '50000'))
            quota = AIUsageQuota(
                target_type='user',
                target_id=user_id,
                daily_call_limit=default_limit,
                daily_token_limit=default_tokens,
            )
            db.session.add(quota)
        quota.current_daily_calls += 1
        quota.current_daily_tokens += tokens
        db.session.commit()

    @staticmethod
    def reset_daily_quotas():
        count = AIUsageQuota.query.update({
            'current_daily_calls': 0,
            'current_daily_tokens': 0,
            'reset_at': datetime.now(timezone.utc),
        })
        db.session.commit()
        logger.info(f'每日配额重置完成，影响{count}条记录')

    @staticmethod
    def get_user_quota_info(user_id: int) -> dict:
        quota = AIUsageQuota.query.filter_by(
            target_type='user', target_id=user_id
        ).first()
        if not quota:
            return {
                'has_quota': False,
                'daily_call_limit': int(SystemSetting.get('ai_default_daily_calls', '100')),
                'daily_token_limit': int(SystemSetting.get('ai_default_daily_tokens', '50000')),
                'current_daily_calls': 0,
                'current_daily_tokens': 0,
                'remaining_calls': int(SystemSetting.get('ai_default_daily_calls', '100')),
            }
        return {
            'has_quota': True,
            'daily_call_limit': quota.daily_call_limit,
            'daily_token_limit': quota.daily_token_limit,
            'current_daily_calls': quota.current_daily_calls,
            'current_daily_tokens': quota.current_daily_tokens,
            'remaining_calls': max(0, quota.daily_call_limit - quota.current_daily_calls),
        }

    @staticmethod
    def set_quota(target_type: str, target_id: int, daily_call_limit: int = None,
                  daily_token_limit: int = None):
        quota = AIUsageQuota.query.filter_by(
            target_type=target_type, target_id=target_id
        ).first()
        if not quota:
            quota = AIUsageQuota(target_type=target_type, target_id=target_id)
            db.session.add(quota)
        if daily_call_limit is not None:
            quota.daily_call_limit = daily_call_limit
        if daily_token_limit is not None:
            quota.daily_token_limit = daily_token_limit
        db.session.commit()
        return quota

    @staticmethod
    def delete_quota(quota_id: int) -> bool:
        quota = AIUsageQuota.query.get(quota_id)
        if quota:
            db.session.delete(quota)
            db.session.commit()
            return True
        return False

    @staticmethod
    def list_quotas(target_type: str = None, target_id: int = None):
        query = AIUsageQuota.query
        if target_type:
            query = query.filter_by(target_type=target_type)
        if target_id:
            query = query.filter_by(target_id=target_id)
        return query.all()
