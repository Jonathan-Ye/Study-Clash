from app import db
from datetime import datetime, timedelta, timezone


class LoginAttempt(db.Model):
    """登录失败记录表，用于登录锁定机制"""
    __tablename__ = 'login_attempts'

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False, index=True)
    fail_count = db.Column(db.Integer, default=0, nullable=False)
    locked_until = db.Column(db.DateTime, nullable=True)
    last_fail_at = db.Column(db.DateTime, nullable=True)

    @staticmethod
    def get_or_create(username):
        """获取或创建登录尝试记录"""
        record = LoginAttempt.query.filter_by(username=username).first()
        if not record:
            record = LoginAttempt(username=username)
            db.session.add(record)
            db.session.commit()
        return record

    @staticmethod
    def record_failure(username):
        """记录一次登录失败，返回更新后的记录"""
        record = LoginAttempt.get_or_create(username)
        record.fail_count += 1
        record.last_fail_at = datetime.now(timezone.utc)
        db.session.commit()
        return record

    @staticmethod
    def lock_account(username, duration_minutes):
        """锁定账户指定分钟数"""
        record = LoginAttempt.get_or_create(username)
        record.locked_until = datetime.now(timezone.utc) + timedelta(minutes=duration_minutes)
        db.session.commit()
        return record

    @staticmethod
    def reset(username):
        """登录成功后重置失败计数"""
        record = LoginAttempt.query.filter_by(username=username).first()
        if record:
            record.fail_count = 0
            record.locked_until = None
            db.session.commit()

    @staticmethod
    def is_locked(username):
        """检查账户是否被锁定，返回 (is_locked, remaining_minutes)"""
        record = LoginAttempt.query.filter_by(username=username).first()
        if not record or not record.locked_until:
            return False, 0
        now = datetime.now(timezone.utc)
        locked_until = record.locked_until
        if locked_until.tzinfo is None:
            locked_until = locked_until.replace(tzinfo=timezone.utc)
        if now >= locked_until:
            record.fail_count = 0
            record.locked_until = None
            db.session.commit()
            return False, 0
        remaining = (locked_until - now).total_seconds() / 60
        return True, int(remaining) + 1

    def __repr__(self):
        return f'<LoginAttempt {self.username} fails={self.fail_count}>'
