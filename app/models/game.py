from datetime import datetime, timedelta, timezone
from app import db, socketio
from config import BEIJING_TZ
import json


def _make_aware(dt):
    """将 naive datetime 转换为北京时间（向后兼容）"""
    if dt is not None and dt.tzinfo is None:
        return dt.replace(tzinfo=BEIJING_TZ)
    return dt


def _make_aware_utc(dt):
    """将 naive datetime 转换为 UTC 时间
    
    注意：所有新创建的房间时间都使用 UTC 存储。
    对于旧数据（使用北京时间的 naive datetime），
    应用重启后会被自动清理。
    """
    if dt is not None and dt.tzinfo is None:
        # 假设旧数据是北京时间（UTC+8），转换为UTC
        from datetime import timedelta
        beijing_offset = timedelta(hours=8)
        # 先标记为北京时间，然后转换为UTC
        dt_beijing = dt.replace(tzinfo=timezone(beijing_offset))
        return dt_beijing.astimezone(timezone.utc)
    return dt

class GameRoom(db.Model):
    __tablename__ = 'game_rooms'
    
    id = db.Column(db.Integer, primary_key=True)
    room_code = db.Column(db.String(10), unique=True, nullable=False, index=True)
    game_type = db.Column(db.String(20), nullable=False, index=True)
    subject_id = db.Column(db.Integer, db.ForeignKey('subjects.id'))
    chapter_id = db.Column(db.Integer, db.ForeignKey('chapters.id'))
    
    max_players = db.Column(db.Integer, default=2)
    current_players = db.Column(db.Integer, default=0)
    
    status = db.Column(db.String(20), default='waiting', index=True)
    
    question_count = db.Column(db.Integer, default=10)
    time_per_question = db.Column(db.Integer, default=30)
    
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    started_at = db.Column(db.DateTime, index=True)
    ended_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    expires_at = db.Column(db.DateTime, index=True)
    
    players = db.relationship('GamePlayer', backref='room', lazy='dynamic')
    records = db.relationship('GameRecord', backref='room', lazy='dynamic')
    subject = db.relationship('Subject', backref='game_rooms')
    chapter = db.relationship('Chapter', backref='game_rooms')
    
    __table_args__ = (
        db.Index('idx_game_rooms_status_expires', 'status', 'expires_at'),
        db.Index('idx_game_rooms_status_created', 'status', 'created_at'),
        db.Index('idx_game_rooms_status_ended', 'status', 'ended_at'),
    )
    
    GAME_TYPES = {
        'single': '单人挑战',
        'battle': '双人对战',
        'four': '四人挑战'
    }
    
    STATUSES = {
        'waiting': '等待中',
        'playing': '进行中',
        'finished': '已结束'
    }
    
    def __init__(self, **kwargs):
        super(GameRoom, self).__init__(**kwargs)
        if not self.expires_at:
            from flask import current_app
            expire_minutes = current_app.config.get('ROOM_EXPIRE_MINUTES', 20)
            # 使用 UTC 时间存储，避免时区问题
            self.expires_at = datetime.now(timezone.utc) + timedelta(minutes=expire_minutes)
    
    def is_expired(self):
        if self.status != 'waiting':
            return False
        return datetime.now(timezone.utc) > _make_aware_utc(self.expires_at)
    
    def get_remaining_seconds(self):
        if self.status != 'waiting':
            return 0
        remaining = (_make_aware_utc(self.expires_at) - datetime.now(timezone.utc)).total_seconds()
        return max(0, int(remaining))
    
    def is_full(self):
        cp = self.current_players or 0
        mp = self.max_players or 0
        return cp >= mp
    
    def is_empty(self):
        return (self.current_players or 0) == 0
    
    def add_player(self, user):
        if self.is_full():
            return False
        player = GamePlayer(room_id=self.id, user_id=user.id)
        db.session.add(player)
        if self.current_players is None:
            self.current_players = 0
        self.current_players += 1
        db.session.commit()
        return True
    
    def remove_player(self, user):
        player = GamePlayer.query.filter_by(room_id=self.id, user_id=user.id).first()
        if player:
            db.session.delete(player)
            if self.current_players is None:
                self.current_players = 0
            self.current_players -= 1
            db.session.commit()
            return True
        return False
    
    def start_game(self):
        self.status = 'playing'
        self.started_at = datetime.now(timezone.utc)
        db.session.commit()
    
    def end_game(self):
        self.status = 'finished'
        self.ended_at = datetime.now(timezone.utc)
        db.session.commit()

class GamePlayer(db.Model):
    __tablename__ = 'game_players'
    
    __table_args__ = (
        db.Index('idx_game_player_room_user', 'room_id', 'user_id'),
    )
    
    id = db.Column(db.Integer, primary_key=True)
    room_id = db.Column(db.Integer, db.ForeignKey('game_rooms.id'), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    
    score = db.Column(db.Integer, default=0)
    correct_count = db.Column(db.Integer, default=0)
    wrong_count = db.Column(db.Integer, default=0)
    total_time = db.Column(db.Integer, default=0)
    
    wrong_chances_used = db.Column(db.Integer, default=0)

    current_question_index = db.Column(db.Integer, default=1)

    is_ready = db.Column(db.Boolean, default=False)
    finished = db.Column(db.Boolean, default=False)
    game_over = db.Column(db.Boolean, default=False)
    
    joined_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    finished_at = db.Column(db.DateTime)
    
    user = db.relationship('User', backref='game_players')

class GameRecord(db.Model):
    __tablename__ = 'game_records'
    
    __table_args__ = (
        db.Index('idx_game_record_user_created', 'user_id', 'created_at'),
    )
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    room_id = db.Column(db.Integer, db.ForeignKey('game_rooms.id'), index=True)
    
    game_type = db.Column(db.String(20), nullable=False, index=True)
    subject_id = db.Column(db.Integer, db.ForeignKey('subjects.id'))
    
    score = db.Column(db.Integer, default=0)
    correct_count = db.Column(db.Integer, default=0)
    wrong_count = db.Column(db.Integer, default=0)
    total_time = db.Column(db.Integer, default=0)
    
    rank = db.Column(db.Integer)
    points_earned = db.Column(db.Integer, default=0)
    
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    
    subject = db.relationship('Subject', backref='game_records')
    
    def to_dict(self):
        return {
            'id': self.id,
            'game_type': self.game_type,
            'subject': self.subject.name if self.subject else None,
            'score': self.score,
            'correct_count': self.correct_count,
            'wrong_count': self.wrong_count,
            'total_time': self.total_time,
            'rank': self.rank,
            'points_earned': self.points_earned,
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M')
        }

class GameQuestion(db.Model):
    __tablename__ = 'game_questions'
    
    __table_args__ = (
        db.Index('idx_game_question_room', 'room_id'),
        db.Index('idx_game_question_question', 'question_id'),
    )
    
    id = db.Column(db.Integer, primary_key=True)
    room_id = db.Column(db.Integer, db.ForeignKey('game_rooms.id'), nullable=False, index=True)
    question_id = db.Column(db.Integer, db.ForeignKey('questions.id'), nullable=False, index=True)
    order = db.Column(db.Integer, nullable=False)
    
    question = db.relationship('Question', backref='game_questions')


class RematchInvitation(db.Model):
    """再来一局邀约记录（持久化存储）"""
    __tablename__ = 'rematch_invitations'
    
    id = db.Column(db.Integer, primary_key=True)
    room_code = db.Column(db.String(20), nullable=False, index=True)
    requester_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    requester_name = db.Column(db.String(64), nullable=False)
    all_player_ids = db.Column(db.Text, nullable=False)  # JSON 序列化
    accepted_ids = db.Column(db.Text, default='[]')       # JSON 序列化
    declined_ids = db.Column(db.Text, default='[]')       # JSON 序列化
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    expires_at = db.Column(db.DateTime, nullable=False)   # 15 秒超时
    
    __table_args__ = (
        db.Index('idx_rematch_room', 'room_code'),
    )
    
    def get_all_player_ids(self):
        return json.loads(self.all_player_ids)
    
    def get_accepted_ids(self):
        return set(json.loads(self.accepted_ids))
    
    def get_declined_ids(self):
        return set(json.loads(self.declined_ids))
    
    def add_accepted(self, user_id):
        accepted = self.get_accepted_ids()
        accepted.add(user_id)
        self.accepted_ids = json.dumps(list(accepted))
    
    def add_declined(self, user_id):
        declined = self.get_declined_ids()
        declined.add(user_id)
        self.declined_ids = json.dumps(list(declined))
    
    def is_all_accepted(self):
        return self.get_accepted_ids() == set(self.get_all_player_ids())
    
    def is_expired(self):
        return datetime.now(timezone.utc) > _make_aware_utc(self.expires_at)

    @staticmethod
    def clean_expired():
        now = datetime.now(timezone.utc)
        RematchInvitation.query.filter(RematchInvitation.expires_at < now).delete()
        db.session.commit()
