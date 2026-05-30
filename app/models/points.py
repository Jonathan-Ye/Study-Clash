from datetime import datetime, date, timezone
from app import db
from sqlalchemy import func

class PointRecord(db.Model):
    __tablename__ = 'point_records'
    
    __table_args__ = (
        db.Index('idx_point_record_user_created', 'user_id', 'created_at'),
        db.Index('idx_point_record_user_reason', 'user_id', 'reason'),
    )
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    points = db.Column(db.Integer, nullable=False)
    reason = db.Column(db.String(100), nullable=False, index=True)
    related_id = db.Column(db.Integer)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    
    REASONS = {
        'single_correct': '单人答题正确',
        'battle_win': '双人对战胜利',
        'four_first': '四人挑战冠军',
        'four_second': '四人挑战亚军',
        'four_third': '四人挑战季军',
        'four_fourth': '四人挑战第四名',
        'review_correct': '错题复习正确',
        'daily_login': '每日登录',
        'streak_bonus': '连续答题奖励',
        'admin_add': '管理员添加',
        'admin_deduct': '管理员扣除'
    }
    
    def to_dict(self):
        return {
            'id': self.id,
            'points': self.points,
            'reason': self.reason,
            'reason_text': self.REASONS.get(self.reason, self.reason),
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M')
        }

class DailyStats(db.Model):
    __tablename__ = 'daily_stats'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    date = db.Column(db.Date, nullable=False, default=date.today, index=True)
    
    questions_answered = db.Column(db.Integer, default=0)
    correct_count = db.Column(db.Integer, default=0)
    wrong_count = db.Column(db.Integer, default=0)
    
    games_played = db.Column(db.Integer, default=0)
    games_won = db.Column(db.Integer, default=0)
    
    points_earned = db.Column(db.Integer, default=0)
    time_spent = db.Column(db.Integer, default=0)
    
    login = db.Column(db.Boolean, default=False)
    
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    
    user = db.relationship('User', backref='daily_stats')
    
    __table_args__ = (
        db.UniqueConstraint('user_id', 'date', name='unique_user_date'),
    )
    
    @property
    def accuracy(self):
        qa = self.questions_answered or 0
        cc = self.correct_count or 0
        if qa == 0:
            return 0
        return round(cc / qa * 100, 1)
    
    @classmethod
    def get_or_create(cls, user_id, date_str=None):
        if date_str:
            target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        else:
            target_date = date.today()
        
        stats = cls.query.filter_by(user_id=user_id, date=target_date).first()
        if not stats:
            stats = cls(user_id=user_id, date=target_date)
            db.session.add(stats)
            try:
                db.session.flush()
            except Exception:
                db.session.rollback()
                # 重新查询，如果仍然不存在则使用刚创建的对象
                stats = cls.query.filter_by(user_id=user_id, date=target_date).first()
                if not stats:
                    # 如果仍然查不到，说明对象未持久化，使用内存中的对象
                    stats = cls(user_id=user_id, date=target_date)
        return stats
    
    def update_answer(self, is_correct, time_spent=0):
        if self.questions_answered is None:
            self.questions_answered = 0
        if self.correct_count is None:
            self.correct_count = 0
        if self.wrong_count is None:
            self.wrong_count = 0
        if self.time_spent is None:
            self.time_spent = 0
        self.questions_answered += 1
        if is_correct:
            self.correct_count += 1
        else:
            self.wrong_count += 1
        self.time_spent += time_spent
        db.session.flush()
    
    def update_game(self, won=False):
        if self.games_played is None:
            self.games_played = 0
        if self.games_won is None:
            self.games_won = 0
        self.games_played += 1
        if won:
            self.games_won += 1
        db.session.flush()

class Leaderboard(db.Model):
    __tablename__ = 'leaderboards'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    period = db.Column(db.String(20), nullable=False)
    category = db.Column(db.String(50), nullable=False)
    
    subject_id = db.Column(db.Integer, db.ForeignKey('subjects.id'), nullable=True)
    game_type = db.Column(db.String(20), nullable=True)
    school = db.Column(db.String(100), nullable=True)
    grade = db.Column(db.String(20), nullable=True)
    class_name = db.Column(db.String(50), nullable=True)
    
    score = db.Column(db.Integer, default=0)
    rank = db.Column(db.Integer, default=0)
    
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    
    user = db.relationship('User', backref='leaderboard_entries')
    subject = db.relationship('Subject', backref='leaderboard_entries')
    
    PERIODS = {
        'daily': '日榜',
        'weekly': '周榜',
        'monthly': '月榜',
        'all_time': '总榜'
    }
    
    CATEGORIES = {
        'total_points': '总积分',
        'correct_rate': '正确率',
        'games_won': '胜场数',
        'streak_days': '连续天数',
        'subject_points': '学科积分',
        'game_type_points': '游戏类型积分',
        'study_time': '学习时长'
    }
    
    __table_args__ = (
        db.UniqueConstraint('user_id', 'period', 'category', 'subject_id', 'game_type', 'school', 'grade', 'class_name', 
                          name='unique_leaderboard_entry'),
        db.Index('idx_leaderboard_period_category', 'period', 'category'),
        db.Index('idx_leaderboard_score', 'score', 'rank'),
    )
    
    @classmethod
    def get_leaderboard(cls, period='all_time', category='total_points', subject_id=None, 
                       game_type=None, school=None, grade=None, class_name=None, page=1, per_page=50):
        query = cls.query.filter_by(period=period, category=category)
        
        if subject_id:
            query = query.filter_by(subject_id=subject_id)
        if game_type:
            query = query.filter_by(game_type=game_type)
        if school:
            query = query.filter_by(school=school)
        if grade:
            query = query.filter_by(grade=grade)
        if class_name:
            query = query.filter_by(class_name=class_name)
        
        return query.order_by(cls.rank).paginate(page=page, per_page=per_page)
