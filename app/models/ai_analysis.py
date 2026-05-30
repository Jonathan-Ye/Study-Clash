from datetime import datetime, timezone
from app import db


class LLMProvider(db.Model):
    __tablename__ = 'llm_providers'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    provider_type = db.Column(db.String(30), nullable=False)
    api_base_url = db.Column(db.String(500))
    api_key_encrypted = db.Column(db.Text)
    model_name = db.Column(db.String(100), nullable=False)
    is_active = db.Column(db.Boolean, default=True, index=True)
    is_primary = db.Column(db.Boolean, default=False, index=True)
    priority = db.Column(db.Integer, default=0)
    max_tokens = db.Column(db.Integer, default=8192)
    temperature = db.Column(db.Float, default=0.7)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    strategies = db.relationship('LLMCallStrategy', backref='provider', lazy='dynamic', cascade='all, delete-orphan')
    call_logs = db.relationship('LLMCallLog', backref='provider', lazy='dynamic')

    PROVIDER_TYPES = {
        'local': '本地部署',
        'zhipuai': '智谱AI',
        'baidu': '百度千帆',
        'alibaba': '阿里百炼',
        'openai_compatible': 'OpenAI兼容',
    }

    __table_args__ = (
        db.Index('idx_provider_type_active', 'provider_type', 'is_active'),
    )


class LLMCallStrategy(db.Model):
    __tablename__ = 'llm_call_strategies'

    id = db.Column(db.Integer, primary_key=True)
    provider_id = db.Column(db.Integer, db.ForeignKey('llm_providers.id'), nullable=False, index=True)
    task_type = db.Column(db.String(50), nullable=False)
    timeout_seconds = db.Column(db.Integer, default=30)
    max_retries = db.Column(db.Integer, default=2)
    retry_delay_seconds = db.Column(db.Integer, default=3)
    token_limit = db.Column(db.Integer, default=8192)
    daily_token_budget = db.Column(db.Integer, default=100000)
    temperature_override = db.Column(db.Float)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    TASK_TYPES = {
        'attribution': '归因分析',
        'prediction': '推理预测',
        'strategy': '策略辅助',
        'explanation': '解析生成',
        'variant': '变式题生成',
        'practice': '练习生成',
    }

    __table_args__ = (
        db.UniqueConstraint('provider_id', 'task_type', name='unique_provider_task_type'),
    )


class AIAnalysisResult(db.Model):
    __tablename__ = 'ai_analysis_results'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    data_hash = db.Column(db.String(64), nullable=False, index=True)
    root_causes = db.Column(db.Text)
    knowledge_mastery = db.Column(db.Text)
    ability_scores = db.Column(db.Text)
    suggestions = db.Column(db.Text)
    confidence = db.Column(db.Float, default=0.0)
    needs_review = db.Column(db.Boolean, default=False)
    provider_id = db.Column(db.Integer, db.ForeignKey('llm_providers.id'))
    total_tokens = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    user = db.relationship('User', backref='ai_analysis_results')

    __table_args__ = (
        db.Index('idx_analysis_user_hash', 'user_id', 'data_hash'),
    )


class AIPredictionResult(db.Model):
    __tablename__ = 'ai_prediction_results'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    weak_points = db.Column(db.Text)
    error_predictions = db.Column(db.Text)
    low_confidence = db.Column(db.Boolean, default=False)
    is_expired = db.Column(db.Boolean, default=False)
    expires_at = db.Column(db.DateTime, nullable=False, index=True)
    provider_id = db.Column(db.Integer, db.ForeignKey('llm_providers.id'))
    total_tokens = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    user = db.relationship('User', backref='ai_prediction_results')


class AIGeneratedContent(db.Model):
    __tablename__ = 'ai_generated_contents'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    content_type = db.Column(db.String(30), nullable=False, index=True)
    question_id = db.Column(db.Integer, db.ForeignKey('questions.id'), nullable=True)
    knowledge_point_id = db.Column(db.Integer, nullable=True)
    content = db.Column(db.Text, nullable=False)
    is_ai_generated = db.Column(db.Boolean, default=True)
    review_status = db.Column(db.String(20), default='not_required', index=True)
    reviewed_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    reviewed_at = db.Column(db.DateTime)
    provider_id = db.Column(db.Integer, db.ForeignKey('llm_providers.id'))
    total_tokens = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    CONTENT_TYPES = {
        'explanation': '错题解析',
        'variant': '变式题',
        'practice': '巩固练习',
    }

    REVIEW_STATUSES = {
        'not_required': '无需审核',
        'pending': '待审核',
        'approved': '审核通过',
        'rejected': '审核不通过',
    }

    question = db.relationship('Question', backref='ai_contents')


class AILearningStrategy(db.Model):
    __tablename__ = 'ai_learning_strategies'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    learning_path = db.Column(db.Text)
    review_suggestions = db.Column(db.Text)
    focus_directions = db.Column(db.Text)
    needs_update = db.Column(db.Boolean, default=False)
    provider_id = db.Column(db.Integer, db.ForeignKey('llm_providers.id'))
    total_tokens = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    user = db.relationship('User', backref='ai_learning_strategies')


class LLMCallLog(db.Model):
    __tablename__ = 'llm_call_logs'

    id = db.Column(db.Integer, primary_key=True)
    provider_id = db.Column(db.Integer, db.ForeignKey('llm_providers.id'), nullable=False, index=True)
    user_id = db.Column(db.Integer, nullable=True, index=True)
    task_type = db.Column(db.String(50), nullable=False, index=True)
    model_name = db.Column(db.String(100))
    request_tokens = db.Column(db.Integer, default=0)
    response_tokens = db.Column(db.Integer, default=0)
    total_tokens = db.Column(db.Integer, default=0)
    status = db.Column(db.String(20), nullable=False, index=True)
    error_message = db.Column(db.Text)
    duration_ms = db.Column(db.Integer)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), index=True)

    STATUSES = {
        'success': '成功',
        'failed': '失败',
        'timeout': '超时',
        'budget_exceeded': '预算超限',
    }

    __table_args__ = (
        db.Index('idx_call_log_created_type', 'created_at', 'task_type'),
    )


class LLMFallbackEvent(db.Model):
    __tablename__ = 'llm_fallback_events'

    id = db.Column(db.Integer, primary_key=True)
    from_provider_id = db.Column(db.Integer, nullable=False, index=True)
    to_provider_id = db.Column(db.Integer, nullable=False)
    task_type = db.Column(db.String(50), nullable=False)
    reason = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), index=True)


class AIAsyncTask(db.Model):
    __tablename__ = 'ai_async_tasks'

    id = db.Column(db.Integer, primary_key=True)
    task_type = db.Column(db.String(50), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    status = db.Column(db.String(20), default='pending', index=True)
    progress = db.Column(db.Integer, default=0)
    message = db.Column(db.String(200))
    result_ref_id = db.Column(db.Integer, nullable=True)
    error_detail = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    TASK_STATUSES = {
        'pending': '等待中',
        'running': '执行中',
        'completed': '已完成',
        'failed': '失败',
    }

    user = db.relationship('User', backref='ai_async_tasks')


class AIChatSession(db.Model):
    __tablename__ = 'ai_chat_sessions'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    title = db.Column(db.String(200), default='AI对话')
    status = db.Column(db.String(20), default='active')
    context_summary = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


class AIChatMessage(db.Model):
    __tablename__ = 'ai_chat_messages'
    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey('ai_chat_sessions.id'), nullable=False)
    role = db.Column(db.String(20), nullable=False)
    content = db.Column(db.Text, nullable=False)
    tokens = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))


class AIStudyReport(db.Model):
    __tablename__ = 'ai_study_reports'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    report_type = db.Column(db.String(20), default='weekly')
    period_start = db.Column(db.DateTime)
    period_end = db.Column(db.DateTime)
    summary = db.Column(db.Text)
    detailed_content = db.Column(db.Text)
    total_tokens = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))


class AIStudyPlan(db.Model):
    __tablename__ = 'ai_study_plans'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    plan_date = db.Column(db.DateTime)
    items = db.Column(db.Text)
    total_minutes = db.Column(db.Integer, default=0)
    completed_items = db.Column(db.Integer, default=0)
    total_tokens = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))


class AIComparisonResult(db.Model):
    __tablename__ = 'ai_comparison_results'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    comparison_groups = db.Column(db.Text)
    common_patterns = db.Column(db.Text)
    suggestions = db.Column(db.Text)
    total_tokens = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))


class AIUsageQuota(db.Model):
    __tablename__ = 'ai_usage_quotas'
    id = db.Column(db.Integer, primary_key=True)
    target_type = db.Column(db.String(20), nullable=False)
    target_id = db.Column(db.Integer, nullable=False)
    daily_call_limit = db.Column(db.Integer, default=100)
    daily_token_limit = db.Column(db.Integer, default=50000)
    current_daily_calls = db.Column(db.Integer, default=0)
    current_daily_tokens = db.Column(db.Integer, default=0)
    reset_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        db.UniqueConstraint('target_type', 'target_id', name='unique_quota_target'),
    )


class AIConversation(db.Model):
    __tablename__ = 'ai_conversations'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    context_type = db.Column(db.String(30))
    context_id = db.Column(db.Integer)
    context_summary = db.Column(db.Text)
    messages = db.Column(db.Text, default='[]')
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        db.Index('idx_conversation_context', 'context_type', 'context_id'),
    )


class AILearningReport(db.Model):
    __tablename__ = 'ai_learning_reports'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    report_type = db.Column(db.String(20), default='weekly')
    period_start = db.Column(db.DateTime)
    period_end = db.Column(db.DateTime)
    progress_curve = db.Column(db.Text)
    weak_point_changes = db.Column(db.Text)
    learning_suggestions = db.Column(db.Text)
    ai_usage_summary = db.Column(db.Text)
    data_hash = db.Column(db.String(64))
    generated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        db.Index('idx_report_user_type', 'user_id', 'report_type'),
    )


class AILearningPlan(db.Model):
    __tablename__ = 'ai_learning_plans'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    plan_date = db.Column(db.DateTime)
    tasks = db.Column(db.Text)
    total_estimated_minutes = db.Column(db.Integer, default=0)
    spaced_review_items = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        db.UniqueConstraint('user_id', 'plan_date', name='unique_user_plan_date'),
    )


class AIBadgeDefinition(db.Model):
    __tablename__ = 'ai_badge_definitions'
    id = db.Column(db.Integer, primary_key=True)
    badge_key = db.Column(db.String(50), unique=True, nullable=False)
    badge_name = db.Column(db.String(100), nullable=False)
    badge_description = db.Column(db.String(200))
    badge_icon = db.Column(db.String(50))
    trigger_condition = db.Column(db.String(100))
    is_active = db.Column(db.Boolean, default=True)


class AIBadgeRecord(db.Model):
    __tablename__ = 'ai_badge_records'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    badge_key = db.Column(db.String(50), nullable=False)
    earned_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    trigger_context = db.Column(db.Text)

    __table_args__ = (
        db.UniqueConstraint('user_id', 'badge_key', name='unique_user_badge'),
    )


class AISmartAnalysis(db.Model):
    __tablename__ = 'ai_smart_analysis'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    analysis_data = db.Column(db.JSON, nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), index=True)
