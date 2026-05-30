import json
import logging
from app import db, socketio
from app.models.ai_analysis import AIBadgeDefinition, AIBadgeRecord

logger = logging.getLogger(__name__)

DEFAULT_BADGES = [
    {'badge_key': 'first_attribution', 'badge_name': '初次归因', 'badge_description': '首次完成AI归因分析', 'badge_icon': 'bi-search-heart', 'trigger_condition': 'attribution_count >= 1'},
    {'badge_key': 'first_prediction', 'badge_name': '预见未来', 'badge_description': '首次完成推理预测', 'badge_icon': 'bi-lightbulb', 'trigger_condition': 'prediction_count >= 1'},
    {'badge_key': 'first_strategy', 'badge_name': '策略大师', 'badge_description': '首次生成学习策略', 'badge_icon': 'bi-map', 'trigger_condition': 'strategy_count >= 1'},
    {'badge_key': 'ai_explorer', 'badge_name': 'AI探索者', 'badge_description': '使用全部4个AI分析功能', 'badge_icon': 'bi-rocket-takeoff', 'trigger_condition': 'unique_modules >= 4'},
    {'badge_key': 'week_streak', 'badge_name': '坚持一周', 'badge_description': '连续7天使用AI分析', 'badge_icon': 'bi-calendar-check', 'trigger_condition': 'consecutive_days >= 7'},
    {'badge_key': 'chat_master', 'badge_name': '好问善思', 'badge_description': 'AI问答超过20轮', 'badge_icon': 'bi-chat-dots', 'trigger_condition': 'chat_count >= 20'},
]


class AIBadgeService:
    _initialized = False

    @classmethod
    def init_defaults(cls):
        if cls._initialized:
            return
        try:
            from sqlalchemy import inspect
            inspector = inspect(db.engine)
            if 'ai_badge_definitions' not in inspector.get_table_names():
                logger.info('ai_badge_definitions 表不存在，跳过徽章初始化')
                return
            for badge_def in DEFAULT_BADGES:
                existing = AIBadgeDefinition.query.filter_by(badge_key=badge_def['badge_key']).first()
                if not existing:
                    bd = AIBadgeDefinition(**badge_def)
                    db.session.add(bd)
            db.session.commit()
            cls._initialized = True
        except Exception as e:
            logger.warning(f'AI徽章初始化失败（可能是数据库未迁移）: {e}')

    @classmethod
    def check_and_award(cls, user_id: int, trigger_type: str, context: dict = None):
        from app.models.ai_analysis import AIAsyncTask, AIChatMessage, AIChatSession
        today = context or {}
        badges_awarded = []

        if trigger_type == 'attribution':
            count = AIAsyncTask.query.filter_by(user_id=user_id, task_type='attribution', status='completed').count()
            today['attribution_count'] = count
        if trigger_type == 'prediction':
            count = AIAsyncTask.query.filter_by(user_id=user_id, task_type='prediction', status='completed').count()
            today['prediction_count'] = count
        if trigger_type == 'strategy':
            count = AIAsyncTask.query.filter_by(user_id=user_id, task_type='strategy', status='completed').count()
            today['strategy_count'] = count

        unique_modules = set()
        for t in ['attribution', 'prediction', 'strategy']:
            if AIAsyncTask.query.filter_by(user_id=user_id, task_type=t, status='completed').first():
                unique_modules.add(t)
        today['unique_modules'] = len(unique_modules)

        sessions = AIChatSession.query.filter_by(user_id=user_id, status='active').all()
        chat_count = sum(AIChatMessage.query.filter_by(session_id=s.id, role='user').count() for s in sessions)
        today['chat_count'] = chat_count

        consecutive = cls._calc_consecutive_days(user_id)
        today['consecutive_days'] = consecutive

        all_defs = AIBadgeDefinition.query.filter_by(is_active=True).all()
        for bd in all_defs:
            existing = AIBadgeRecord.query.filter_by(user_id=user_id, badge_key=bd.badge_key).first()
            if existing:
                continue
            if cls._evaluate_condition(bd.trigger_condition, today):
                record = AIBadgeRecord(
                    user_id=user_id,
                    badge_key=bd.badge_key,
                    trigger_context=json.dumps(today, ensure_ascii=False),
                )
                db.session.add(record)
                badges_awarded.append({'key': bd.badge_key, 'name': bd.badge_name, 'icon': bd.badge_icon, 'description': bd.badge_description})
                try:
                    socketio.emit('badge_earned', {
                        'badge_key': bd.badge_key,
                        'badge_name': bd.badge_name,
                        'badge_icon': bd.badge_icon,
                        'badge_description': bd.badge_description,
                    }, room=f'user_{user_id}')
                except Exception:
                    pass

        if badges_awarded:
            db.session.commit()
        return badges_awarded

    @classmethod
    def _calc_consecutive_days(cls, user_id: int) -> int:
        from app.models.ai_analysis import AIAsyncTask
        from sqlalchemy import func
        dates = db.session.query(func.date(AIAsyncTask.created_at)).filter(
            AIAsyncTask.user_id == user_id,
            AIAsyncTask.status == 'completed'
        ).distinct().order_by(func.date(AIAsyncTask.created_at).desc()).all()
        if not dates:
            return 0
        from datetime import date, timedelta as td
        today = date.today()
        streak = 0
        for i, (d,) in enumerate(dates):
            expected = today - td(days=i)
            if d == expected:
                streak += 1
            else:
                break
        return streak

    @classmethod
    def _evaluate_condition(cls, condition: str, context: dict) -> bool:
        if not condition:
            return False
        try:
            return eval(condition, {"__builtins__": {}}, context)
        except Exception:
            return False

    @classmethod
    def get_user_badges(cls, user_id: int) -> list:
        records = AIBadgeRecord.query.filter_by(user_id=user_id).all()
        result = []
        for r in records:
            defn = AIBadgeDefinition.query.filter_by(badge_key=r.badge_key).first()
            result.append({
                'badge_key': r.badge_key,
                'badge_name': defn.badge_name if defn else r.badge_key,
                'badge_icon': defn.badge_icon if defn else 'bi-award',
                'badge_description': defn.badge_description if defn else '',
                'earned_at': r.earned_at.isoformat() if r.earned_at else None,
            })
        return result
