from datetime import datetime, timezone
from app import db

class QuestionFeedback(db.Model):
    __tablename__ = 'question_feedbacks'
    
    id = db.Column(db.Integer, primary_key=True)
    question_id = db.Column(db.Integer, db.ForeignKey('questions.id'), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    
    feedback_type = db.Column(db.String(20), nullable=False, default='error')
    content = db.Column(db.Text, nullable=False)
    
    status = db.Column(db.String(20), nullable=False, default='pending', index=True)
    admin_reply = db.Column(db.Text)
    points_awarded = db.Column(db.Integer, default=0)
    
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    resolved_at = db.Column(db.DateTime)
    resolved_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    
    question = db.relationship('Question', backref='feedbacks', lazy='joined')
    user = db.relationship('User', foreign_keys=[user_id], backref='submitted_feedbacks', lazy='joined')
    resolver = db.relationship('User', foreign_keys=[resolved_by], lazy='joined')
    
    FEEDBACK_TYPES = {
        'error': '题目错误',
        'answer_error': '答案错误',
        'analysis_error': '解析错误',
        'suggestion': '改进建议',
        'other': '其他'
    }
    
    STATUS_LABELS = {
        'pending': '待处理',
        'processing': '处理中',
        'resolved': '已解决',
        'rejected': '已拒绝'
    }
    
    __table_args__ = (
        db.Index('idx_feedback_question_status', 'question_id', 'status'),
        db.Index('idx_feedback_user_created', 'user_id', 'created_at'),
    )
