from datetime import datetime, timezone
from app import db

class RankHistory(db.Model):
    __tablename__ = 'rank_history'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    period = db.Column(db.String(20), nullable=False)
    category = db.Column(db.String(50), nullable=False)
    rank = db.Column(db.Integer, nullable=False)
    score = db.Column(db.Integer, nullable=False)
    recorded_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    
    user = db.relationship('User', backref='rank_history')
    
    __table_args__ = (
        db.Index('idx_rank_period_category', 'period', 'category', 'recorded_at'),
    )
