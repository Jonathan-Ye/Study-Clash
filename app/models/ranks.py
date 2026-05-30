from datetime import datetime, timezone
from app import db

class RankTier(db.Model):
    __tablename__ = 'rank_tiers'
    
    id = db.Column(db.Integer, primary_key=True)
    tier_name = db.Column(db.String(50), nullable=False)
    tier_order = db.Column(db.Integer, nullable=False)
    sub_tier = db.Column(db.String(10), nullable=False)
    min_points = db.Column(db.Integer, nullable=False)
    max_points = db.Column(db.Integer, nullable=True)
    icon = db.Column(db.String(256))
    color = db.Column(db.String(20))
    badge_icon = db.Column(db.String(256))
    description = db.Column(db.Text)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    
    __table_args__ = (
        db.UniqueConstraint('tier_name', 'sub_tier', name='unique_tier_sub'),
        db.Index('idx_tier_order', 'tier_order'),
        db.Index('idx_points_range', 'min_points', 'max_points'),
    )
    
    @property
    def display_name(self):
        return f"{self.tier_name} {self.sub_tier}"
    
    @property
    def tier_key(self):
        return f"{self.tier_name}_{self.sub_tier}".lower()
    
    def to_dict(self):
        return {
            'id': self.id,
            'tier_name': self.tier_name,
            'tier_order': self.tier_order,
            'sub_tier': self.sub_tier,
            'display_name': self.display_name,
            'tier_key': self.tier_key,
            'min_points': self.min_points,
            'max_points': self.max_points,
            'icon': self.icon,
            'color': self.color,
            'badge_icon': self.badge_icon,
            'description': self.description,
            'is_active': self.is_active
        }


class TierPromotionHistory(db.Model):
    __tablename__ = 'tier_promotion_history'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    from_tier_id = db.Column(db.Integer, db.ForeignKey('rank_tiers.id'), nullable=False)
    to_tier_id = db.Column(db.Integer, db.ForeignKey('rank_tiers.id'), nullable=False)
    points_at_change = db.Column(db.Integer, nullable=False)
    changed_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    
    user = db.relationship('User', backref='tier_history')
    from_tier = db.relationship('RankTier', foreign_keys=[from_tier_id])
    to_tier = db.relationship('RankTier', foreign_keys=[to_tier_id])
    
    __table_args__ = (
        db.Index('idx_user_tier_history', 'user_id', 'changed_at'),
    )
    
    def to_dict(self):
        return {
            'id': self.id,
            'from_tier': self.from_tier.to_dict() if self.from_tier else None,
            'to_tier': self.to_tier.to_dict() if self.to_tier else None,
            'points_at_change': self.points_at_change,
            'changed_at': self.changed_at.strftime('%Y-%m-%d %H:%M') if self.changed_at else None
        }
