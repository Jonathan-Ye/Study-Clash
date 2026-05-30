from app import db
from datetime import datetime, timezone


class AdminLog(db.Model):
    """管理员操作日志表"""
    __tablename__ = 'admin_logs'

    id = db.Column(db.Integer, primary_key=True)
    admin_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    admin_name = db.Column(db.String(64), nullable=False)
    action_type = db.Column(db.String(30), nullable=False, index=True)
    # action_type枚举: create, update, delete, export, import, config_change, batch_operation
    target_type = db.Column(db.String(30), nullable=False, index=True)
    # target_type枚举: user, subject, chapter, question, setting, announcement, backup, dictionary, rank_tier, leaderboard
    target_id = db.Column(db.Integer, nullable=True)
    target_name = db.Column(db.String(200), nullable=True)
    result = db.Column(db.String(10), nullable=False)
    # result枚举: success, failure
    detail = db.Column(db.Text, nullable=True)
    ip_address = db.Column(db.String(45), nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), index=True)

    # 复合索引：支持按时间范围+操作类型查询
    __table_args__ = (
        db.Index('idx_admin_log_time_action', 'created_at', 'action_type'),
    )

    def __repr__(self):
        return f'<AdminLog {self.admin_name} {self.action_type} {self.target_type}>'
