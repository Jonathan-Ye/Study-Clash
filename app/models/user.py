from datetime import datetime, timezone
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import UserMixin
from app import db, login_manager

class User(UserMixin, db.Model):
    __tablename__ = 'users'
    
    _backup_exclude = ['password_hash']
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False, index=True)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(256), nullable=False)
    must_change_password = db.Column(db.Boolean, default=False)
    nickname = db.Column(db.String(64))
    avatar = db.Column(db.String(256), default='default.svg')
    
    real_name = db.Column(db.String(64))
    student_id = db.Column(db.String(32))
    phone = db.Column(db.String(20))
    school = db.Column(db.String(100))
    grade = db.Column(db.String(20))
    major = db.Column(db.String(100))
    class_name = db.Column(db.String(50))
    birthday = db.Column(db.Date)
    
    role = db.Column(db.String(20), default='student', nullable=False, index=True)
    is_admin = db.Column(db.Boolean, default=False, index=True)
    is_active = db.Column(db.Boolean, default=True, index=True)
    can_edit_profile = db.Column(db.Boolean, default=True)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    
    # 游戏和排行榜参与设置
    participate_in_games = db.Column(db.Boolean, default=True, index=True)  # 是否参与游戏对决
    show_in_leaderboard = db.Column(db.Boolean, default=True, index=True)   # 是否显示在排行榜
    
    # 教师细粒度权限字段（仅对role=teacher生效）
    can_manage_subjects = db.Column(db.Boolean, default=True)      # 学科管理
    can_manage_chapters = db.Column(db.Boolean, default=True)      # 章节管理
    can_manage_questions = db.Column(db.Boolean, default=True)     # 题目管理
    can_import_questions = db.Column(db.Boolean, default=True)     # 题库导入
    can_export_questions = db.Column(db.Boolean, default=True)     # 题库导出
    can_import_students = db.Column(db.Boolean, default=True)      # 学生导入
    can_view_student_analysis = db.Column(db.Boolean, default=True)  # 学生分析
    can_view_knowledge_analysis = db.Column(db.Boolean, default=True)  # 知识点分析
    total_points = db.Column(db.Integer, default=0, index=True)
    current_tier_id = db.Column(db.Integer, db.ForeignKey('rank_tiers.id'), nullable=True)
    peak_tier_id = db.Column(db.Integer, db.ForeignKey('rank_tiers.id'), nullable=True)
    streak_days = db.Column(db.Integer, default=0)
    last_login = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    
    game_records = db.relationship('GameRecord', backref='user', lazy='dynamic')
    point_records = db.relationship('PointRecord', backref='user', lazy='dynamic')
    wrong_questions = db.relationship('WrongQuestion', backref='user', lazy='dynamic')
    answers = db.relationship('UserAnswer', backref='user', lazy='dynamic')
    current_tier = db.relationship('RankTier', foreign_keys=[current_tier_id])
    peak_tier = db.relationship('RankTier', foreign_keys=[peak_tier_id])
    creator = db.relationship('User', foreign_keys=[created_by], remote_side=[id], backref='created_users')

    # 角色常量
    ROLE_ADMIN = 'admin'
    ROLE_TEACHER = 'teacher'
    ROLE_STUDENT = 'student'
    ROLES = [ROLE_ADMIN, ROLE_TEACHER, ROLE_STUDENT]
    ROLE_LABELS = {ROLE_ADMIN: '管理员', ROLE_TEACHER: '教师', ROLE_STUDENT: '学生'}

    # 教师权限常量
    TEACHER_PERMISSIONS = {
        'can_manage_subjects': {'label': '学科管理', 'icon': 'bi-journal-text', 'group': 'content_mgmt'},
        'can_manage_chapters': {'label': '章节管理', 'icon': 'bi-list-ul', 'group': 'content_mgmt'},
        'can_manage_questions': {'label': '题目管理', 'icon': 'bi-question-circle', 'group': 'content_mgmt'},
        'can_import_questions': {'label': '题库导入', 'icon': 'bi-upload', 'group': 'content_mgmt'},
        'can_export_questions': {'label': '题库导出', 'icon': 'bi-download', 'group': 'content_mgmt'},
        'can_import_students': {'label': '学生导入', 'icon': 'bi-person-plus', 'group': 'user_mgmt'},
        'can_view_student_analysis': {'label': '学生分析', 'icon': 'bi-mortarboard', 'group': 'data_stats'},
        'can_view_knowledge_analysis': {'label': '知识点分析', 'icon': 'bi-graph-up-arrow', 'group': 'data_stats'},
    }

    # is_admin是数据库列，与role自动同步
    # 通过__setattr__确保两者始终一致

    def __setattr__(self, key, value):
        if key == 'role':
            super().__setattr__('role', value)
            # 同步is_admin列
            super().__setattr__('is_admin', value == self.ROLE_ADMIN)
        elif key == 'is_admin':
            super().__setattr__('is_admin', value)
            # 同步role列
            if value and super().__getattribute__('role') != self.ROLE_ADMIN:
                super().__setattr__('role', self.ROLE_ADMIN)
            elif not value and super().__getattribute__('role') == self.ROLE_ADMIN:
                super().__setattr__('role', self.ROLE_STUDENT)
        else:
            super().__setattr__(key, value)
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)
    
    def add_points(self, points, reason):
        if self.total_points is None:
            self.total_points = 0
        self.total_points += points
        self.update_tier()
        from app.models.points import PointRecord
        record = PointRecord(user_id=self.id, points=points, reason=reason)
        db.session.add(record)
    
    def set_points(self, new_points, reason='correction'):
        if self.total_points is None:
            self.total_points = 0
        diff = new_points - self.total_points
        self.total_points = new_points
        self.update_tier()
        from app.models.points import PointRecord
        record = PointRecord(user_id=self.id, points=diff, reason=reason)
        db.session.add(record)
    
    def update_tier(self):
        from app.utils.rank_service import RankService
        new_tier = RankService.calculate_tier_from_points(self.total_points)
        
        if not new_tier:
            return
        
        old_tier_id = self.current_tier_id
        
        if old_tier_id and old_tier_id != new_tier.id:
            self._record_tier_change(old_tier_id, new_tier.id)
        
        self.current_tier_id = new_tier.id
        
        if self.peak_tier_id is None:
            self.peak_tier_id = new_tier.id
        else:
            peak_tier = RankService.get_tier_by_id(self.peak_tier_id)
            if peak_tier and (new_tier.tier_order > peak_tier.tier_order or 
                            (new_tier.tier_order == peak_tier.tier_order and 
                             self._is_higher_sub_tier(new_tier, peak_tier))):
                self.peak_tier_id = new_tier.id
    
    def _is_higher_sub_tier(self, tier1, tier2):
        sub_order = {'III': 1, 'II': 2, 'I': 3}
        return sub_order.get(tier1.sub_tier, 0) > sub_order.get(tier2.sub_tier, 0)
    
    def _record_tier_change(self, from_tier_id, to_tier_id):
        try:
            from app.models.ranks import TierPromotionHistory
            record = TierPromotionHistory(
                user_id=self.id,
                from_tier_id=from_tier_id,
                to_tier_id=to_tier_id,
                points_at_change=self.total_points
            )
            db.session.add(record)
        except Exception as e:
            print(f"记录段位变更失败: {e}")
    
    def get_rank(self):
        pts = self.total_points or 0
        return db.session.query(User.id).filter(
            User.is_active == True,
            User.total_points > pts
        ).count() + 1
    
    def get_avatar_url(self):
        if self.avatar and self.avatar != 'default.png':
            import os
            from flask import current_app
            avatar_path = os.path.join(current_app.root_path, 'static', 'avatars', self.avatar)
            if os.path.exists(avatar_path):
                return f'/static/avatars/{self.avatar}'
        return '/static/avatars/default.png'
    
    def is_profile_complete(self):
        return bool(self.real_name and self.student_id)
    
    def has_permission(self, perm_key):
        """检查教师是否有指定权限。管理员始终有所有权限。"""
        if self.role == 'admin':
            return True
        if self.role != 'teacher':
            return False
        return getattr(self, perm_key, False)
    
    @property
    def level(self):
        if not self.current_tier:
            return 1
        base = {'Bronze': 1, 'Silver': 2, 'Gold': 3, 'Platinum': 4, 
               'Diamond': 5, 'Master': 6, 'King': 7, 'Legend': 8}.get(self.current_tier.tier_name, 1)
        sub_bonus = {'III': 0, 'II': 0.33, 'I': 0.66}.get(self.current_tier.sub_tier, 0)
        return int((base - 1 + sub_bonus) * 3) + 1
    
    def to_dict(self):
        tier_info = None
        if self.current_tier:
            tier_info = {
                'tier_id': self.current_tier.id,
                'tier_name': self.current_tier.tier_name,
                'sub_tier': self.current_tier.sub_tier,
                'display_name': self.current_tier.display_name,
                'icon': self.current_tier.icon,
                'color': self.current_tier.color
            }
        
        peak_info = None
        if self.peak_tier:
            peak_info = {
                'tier_name': self.peak_tier.tier_name,
                'sub_tier': self.peak_tier.sub_tier,
                'display_name': self.peak_tier.display_name
            }
        
        return {
            'id': self.id,
            'username': self.username,
            'nickname': self.nickname or self.username,
            'avatar': self.avatar,
            'real_name': self.real_name,
            'student_id': self.student_id,
            'phone': self.phone,
            'school': self.school,
            'grade': self.grade,
            'major': self.major,
            'class_name': self.class_name,
            'role': self.role,
            'total_points': self.total_points,
            'tier': tier_info,
            'peak_tier': peak_info,
            'streak_days': self.streak_days,
            'rank': self.get_rank()
        }

@login_manager.user_loader
def load_user(id):
    return User.query.get(int(id))
