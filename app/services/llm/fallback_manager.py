from app import db
from app.models.ai_analysis import LLMProvider


class FallbackManager:
    @staticmethod
    def get_provider_chain(task_type: str = None) -> list:
        query = LLMProvider.query.filter_by(is_active=True).order_by(
            LLMProvider.is_primary.desc(),
            LLMProvider.priority.asc()
        )
        providers = query.all()
        if not providers:
            return []
        primary = [p for p in providers if p.is_primary]
        others = [p for p in providers if not p.is_primary]
        return primary + others

    @staticmethod
    def get_primary_provider() -> LLMProvider:
        return LLMProvider.query.filter_by(is_active=True, is_primary=True).first()

    @staticmethod
    def set_primary(provider_id: int) -> bool:
        current_primary = FallbackManager.get_primary_provider()
        if current_primary:
            current_primary.is_primary = False
        new_primary = LLMProvider.query.get(provider_id)
        if new_primary and new_primary.is_active:
            new_primary.is_primary = True
            db.session.commit()
            return True
        db.session.commit()
        return False
