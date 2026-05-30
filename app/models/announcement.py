from app import db
from datetime import datetime, timezone


def _make_aware(dt):
    if dt is not None and dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


class Announcement(db.Model):
    """系统公告表"""
    __tablename__ = 'announcements'

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    content = db.Column(db.Text, nullable=False)
    priority = db.Column(db.String(10), default='normal')
    # priority枚举: normal, important, urgent
    display_position = db.Column(db.String(20), default='top_banner')
    # display_position枚举: top_banner, home_popup, admin_only
    status = db.Column(db.String(20), default='draft')
    # status枚举: draft, pending, published, expired
    publish_at = db.Column(db.DateTime, nullable=True)
    expire_at = db.Column(db.DateTime, nullable=True)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    @staticmethod
    def get_effective_status(announcement):
        now = datetime.now(timezone.utc)
        if announcement.expire_at and now > _make_aware(announcement.expire_at):
            return 'expired'
        if announcement.publish_at and now < _make_aware(announcement.publish_at):
            return 'pending'
        return 'published'

    def __repr__(self):
        return f'<Announcement {self.title}>'


class AnnouncementRead(db.Model):
    """公告已读记录表"""
    __tablename__ = 'announcement_reads'

    id = db.Column(db.Integer, primary_key=True)
    announcement_id = db.Column(db.Integer, db.ForeignKey('announcements.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    read_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    __table_args__ = (
        db.UniqueConstraint('announcement_id', 'user_id', name='uq_announcement_user_read'),
    )

    @staticmethod
    def mark_read(announcement_id, user_id):
        """标记公告为已读，已读则跳过"""
        existing = AnnouncementRead.query.filter_by(
            announcement_id=announcement_id,
            user_id=user_id
        ).first()
        if not existing:
            record = AnnouncementRead(
                announcement_id=announcement_id,
                user_id=user_id
            )
            db.session.add(record)
            db.session.commit()
        return not existing  # 返回是否为新记录

    def __repr__(self):
        return f'<AnnouncementRead ann={self.announcement_id} user={self.user_id}>'
