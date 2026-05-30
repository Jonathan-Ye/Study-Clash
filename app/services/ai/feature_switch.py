import logging
from app.models.system import SystemSetting

logger = logging.getLogger(__name__)

MODULE_KEYS = {
    'global': 'ai_global_enabled',
    'attribution': 'ai_attribution_enabled',
    'prediction': 'ai_prediction_enabled',
    'strategy': 'ai_strategy_enabled',
    'visualization': 'ai_visualization_enabled',
    'content': 'ai_content_enabled',
    'explanation': 'ai_explanation_enabled',
    'variant': 'ai_variant_enabled',
    'report': 'ai_report_enabled',
    'chat': 'ai_chat_enabled',
    'plan': 'ai_plan_enabled',
}

MODULE_DEFAULTS = {
    'ai_global_enabled': 'true',
    'ai_attribution_enabled': 'true',
    'ai_prediction_enabled': 'true',
    'ai_strategy_enabled': 'true',
    'ai_visualization_enabled': 'true',
    'ai_content_enabled': 'true',
    'ai_explanation_enabled': 'true',
    'ai_variant_enabled': 'true',
    'ai_report_enabled': 'true',
    'ai_chat_enabled': 'true',
    'ai_plan_enabled': 'true',
}

MODULE_LABELS = {
    'ai_global_enabled': 'AI全局开关',
    'ai_attribution_enabled': '归因分析',
    'ai_prediction_enabled': '推理预测',
    'ai_strategy_enabled': '学习策略',
    'ai_visualization_enabled': '数据可视化',
    'ai_content_enabled': '内容生成',
    'ai_explanation_enabled': '错题解析',
    'ai_variant_enabled': '变式题推荐',
    'ai_report_enabled': '学习报告',
    'ai_chat_enabled': 'AI互动问答',
    'ai_plan_enabled': '学习计划',
}


class AIFeatureSwitchService:
    _cache = {}
    _initialized = False

    @classmethod
    def init_defaults(cls):
        if cls._initialized:
            return
        try:
            from app import db
            from sqlalchemy import inspect
            inspector = inspect(db.engine)
            if 'system_settings' not in inspector.get_table_names():
                logger.info('system_settings 表不存在，跳过 AI 功能开关初始化')
                return
            for key, default_val in MODULE_DEFAULTS.items():
                existing = SystemSetting.query.filter_by(key=key).first()
                if not existing:
                    SystemSetting.set(key, default_val, MODULE_LABELS.get(key, key))
            db.session.commit()
            cls.load_all()
            cls._initialized = True
        except Exception as e:
            logger.warning(f'AI功能开关初始化失败（可能是数据库未迁移）: {e}')

    @classmethod
    def load_all(cls):
        for key in MODULE_DEFAULTS:
            val = SystemSetting.get(key, MODULE_DEFAULTS[key])
            cls._cache[key] = val.lower() == 'true'
        logger.info(f'AI功能开关缓存加载: {cls._cache}')

    @classmethod
    def is_global_enabled(cls) -> bool:
        if not cls._cache:
            cls.load_all()
        return cls._cache.get('ai_global_enabled', True)

    @classmethod
    def is_enabled(cls, module: str) -> bool:
        if not cls._cache:
            cls.load_all()
        if not cls.is_global_enabled():
            return False
        key = MODULE_KEYS.get(module)
        if not key:
            return True
        return cls._cache.get(key, True)

    @classmethod
    def update_switch(cls, key: str, value: bool):
        val_str = 'true' if value else 'false'
        SystemSetting.set(key, val_str)
        cls._cache[key] = value
        logger.info(f'AI功能开关更新: {key} = {val_str}')

    @classmethod
    def get_all_switches(cls) -> dict:
        if not cls._cache:
            cls.load_all()
        result = {}
        for key in MODULE_DEFAULTS:
            result[key] = {
                'enabled': cls._cache.get(key, True),
                'label': MODULE_LABELS.get(key, key),
            }
        return result

    @classmethod
    def check_access(cls, module: str) -> tuple:
        if not cls.is_enabled(module):
            if not cls.is_global_enabled():
                return False, 'AI功能维护中，请稍后再试'
            return False, f'{MODULE_LABELS.get(MODULE_KEYS.get(module, ""), module)}功能暂未开放'
        return True, None
