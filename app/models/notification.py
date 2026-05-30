from datetime import datetime, timezone
from app import db

class UserNotification(db.Model):
    __tablename__ = 'user_notifications'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    
    notification_type = db.Column(db.String(50), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    content = db.Column(db.Text, nullable=False)
    
    related_id = db.Column(db.Integer)
    related_type = db.Column(db.String(50))
    
    is_read = db.Column(db.Boolean, default=False, index=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    read_at = db.Column(db.DateTime)
    
    user = db.relationship('User', foreign_keys=[user_id], backref='notifications', lazy='joined')
    
    NOTIFICATION_TYPES = {
        'feedback_resolved': '反馈已处理',
        'feedback_rejected': '反馈未通过',
        'points_reward': '积分奖励',
        'system': '系统通知'
    }
