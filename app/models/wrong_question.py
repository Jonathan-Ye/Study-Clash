from datetime import datetime, timedelta, timezone
from app import db
import json

WRONG_REASONS = {
    'careless': '粗心大意',
    'knowledge': '知识点不熟悉',
    'understanding': '审题错误',
    'calculation': '计算错误',
    'memory': '记忆模糊',
    'other': '其他原因'
}

REVIEW_INTERVALS = {
    1: 1,
    2: 2,
    3: 4,
    4: 7,
    5: 15,
    6: 30
}

class WrongQuestion(db.Model):
    __tablename__ = 'wrong_questions'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    question_id = db.Column(db.Integer, db.ForeignKey('questions.id'), nullable=False)
    
    wrong_answer = db.Column(db.String(100))
    wrong_count = db.Column(db.Integer, default=1)
    
    is_mastered = db.Column(db.Boolean, default=False, index=True)
    mastered_at = db.Column(db.DateTime)
    
    last_review_at = db.Column(db.DateTime)
    review_count = db.Column(db.Integer, default=0)
    
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    
    wrong_reason = db.Column(db.String(20), index=True)
    game_type = db.Column(db.String(20))
    consecutive_correct = db.Column(db.Integer, default=0)
    next_review_at = db.Column(db.DateTime, index=True)
    last_wrong_answer = db.Column(db.String(100))
    wrong_answers_history = db.Column(db.Text)
    note = db.Column(db.Text)
    is_important = db.Column(db.Boolean, default=False, index=True)
    
    __table_args__ = (
        db.UniqueConstraint('user_id', 'question_id', name='unique_user_question'),
        db.Index('idx_user_mastered', 'user_id', 'is_mastered'),
        db.Index('idx_user_next_review', 'user_id', 'next_review_at'),
    )
    
    def add_wrong(self, wrong_answer, game_type=None):
        if self.wrong_count is None:
            self.wrong_count = 0
        self.wrong_count += 1
        self.wrong_answer = wrong_answer
        self.last_wrong_answer = wrong_answer
        self.consecutive_correct = 0
        self.is_mastered = False
        self.mastered_at = None
        self.updated_at = datetime.now(timezone.utc)
        
        if game_type:
            self.game_type = game_type
        
        history = self.get_wrong_history()
        history.append({
            'answer': wrong_answer,
            'time': datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
        })
        self.wrong_answers_history = json.dumps(history[-10:], ensure_ascii=False)
        self.calculate_next_review()
    
    def mark_reviewed(self):
        if self.review_count is None:
            self.review_count = 0
        self.last_review_at = datetime.now(timezone.utc)
        self.review_count += 1
    
    def mark_mastered(self, consecutive_required=3):
        self.is_mastered = True
        self.mastered_at = datetime.now(timezone.utc)
        self.consecutive_correct = consecutive_required
        self.calculate_next_review()
    
    def mark_correct_in_review(self, consecutive_required=3):
        if self.consecutive_correct is None:
            self.consecutive_correct = 0
        self.consecutive_correct += 1
        self.mark_reviewed()
        
        if self.consecutive_correct >= consecutive_required:
            self.mark_mastered()
            return True
        
        self.calculate_next_review()
        return False
    
    def mark_wrong_in_review(self, wrong_answer):
        self.add_wrong(wrong_answer, 'review')
        self.calculate_next_review()
    
    def calculate_next_review(self):
        """计算下次复习时间（使用动态间隔算法）"""
        consecutive = self.consecutive_correct if self.consecutive_correct is not None else 0
        wrong_cnt = self.wrong_count if self.wrong_count is not None else 0
        difficulty = self.question.difficulty if self.question else 2
        
        # 动态间隔计算（内联实现，避免循环导入）
        base_intervals = {0: 0.5, 1: 1, 2: 3, 3: 7, 4: 14, 5: 30, 6: 60}
        difficulty_coefficients = {1: 1.5, 2: 1.0, 3: 0.7, 4: 0.5}
        mastery_coefficients = {0: 0.5, 1: 0.8, 2: 1.0, 3: 1.2, 4: 1.5}
        
        base_interval = base_intervals.get(min(consecutive + 1, 6), 30)
        difficulty_coeff = difficulty_coefficients.get(difficulty, 1.0)
        mastery_level = min(consecutive, 4)
        mastery_coeff = mastery_coefficients.get(mastery_level, 1.0)
        
        interval_days = base_interval * difficulty_coeff * mastery_coeff
        
        if consecutive == 0 and wrong_cnt >= 5:
            interval_days = max(0.25, interval_days * 0.5)
        
        self.next_review_at = datetime.now(timezone.utc) + timedelta(days=interval_days)
    
    def set_wrong_reason(self, reason):
        if reason in WRONG_REASONS:
            self.wrong_reason = reason
    
    def get_wrong_reason_display(self):
        return WRONG_REASONS.get(self.wrong_reason, '未标注')
    
    def get_wrong_history(self):
        if self.wrong_answers_history:
            try:
                return json.loads(self.wrong_answers_history)
            except (json.JSONDecodeError, ValueError):
                return []
        return []
    
    def toggle_important(self):
        self.is_important = not self.is_important
    
    @staticmethod
    def get_review_needed(user_id, limit=None):
        now = datetime.now(timezone.utc)
        query = WrongQuestion.query.filter_by(
            user_id=user_id,
            is_mastered=False
        ).filter(
            db.or_(
                WrongQuestion.next_review_at.is_(None),
                WrongQuestion.next_review_at <= now
            )
        ).order_by(
            WrongQuestion.is_important.desc(),
            WrongQuestion.wrong_count.desc(),
            WrongQuestion.next_review_at.asc()
        )
        
        if limit:
            query = query.limit(limit)
        
        return query.all()
    
    @staticmethod
    def get_weak_points(user_id, limit=10):
        from app.models import Question, Subject, Chapter
        
        wrong_count_label = db.func.count(WrongQuestion.id).label('wrong_count')
        
        chapter_stats = db.session.query(
            Chapter.id,
            Chapter.name,
            Subject.name.label('subject_name'),
            wrong_count_label,
            db.func.sum(db.case((WrongQuestion.is_mastered == False, 1), else_=0)).label('not_mastered_count')
        ).join(
            Question, Chapter.id == Question.chapter_id
        ).join(
            WrongQuestion, Question.id == WrongQuestion.question_id
        ).join(
            Subject, Chapter.subject_id == Subject.id
        ).filter(
            WrongQuestion.user_id == user_id
        ).group_by(
            Chapter.id,
            Chapter.name,
            Chapter.subject_id,
            Subject.name
        ).order_by(
            wrong_count_label.desc()
        ).limit(limit).all()
        
        return chapter_stats
    
    @staticmethod
    def get_similar_questions(question_id, limit=5, user_id=None):
        from app.models import Question
        
        question = Question.query.get(question_id)
        if not question:
            return []
        
        # 多维度匹配：同学科+同章节+同题型+难度相近
        similar = Question.query.filter(
            Question.id != question_id,
            Question.subject_id == question.subject_id,
            Question.chapter_id == question.chapter_id,
            Question.question_type == question.question_type,
            Question.is_active == True
        ).order_by(
            db.func.abs(Question.difficulty - (question.difficulty or 2))
        ).limit(limit * 2).all()
        
        # 按掌握状态排序：未掌握优先
        if user_id and similar:
            mastered_ids = set(
                wq.question_id for wq in 
                WrongQuestion.query.filter_by(
                    user_id=user_id, is_mastered=True
                ).filter(
                    WrongQuestion.question_id.in_([q.id for q in similar])
                ).all()
            )
            similar.sort(key=lambda q: (0 if q.id in mastered_ids else 1))
        
        return similar[:limit]
    
    def to_dict(self):
        question_data = self.question.to_dict(include_answer=True) if self.question else None
        return {
            'id': self.id,
            'question': question_data,
            'wrong_answer': self.wrong_answer,
            'wrong_count': self.wrong_count,
            'is_mastered': self.is_mastered,
            'review_count': self.review_count,
            'consecutive_correct': self.consecutive_correct,
            'wrong_reason': self.wrong_reason,
            'wrong_reason_display': self.get_wrong_reason_display(),
            'game_type': self.game_type,
            'note': self.note,
            'is_important': self.is_important,
            'next_review_at': self.next_review_at.strftime('%Y-%m-%d %H:%M') if self.next_review_at else None,
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M') if self.created_at else None,
            'wrong_history': self.get_wrong_history()
        }


class WrongQuestionCollection(db.Model):
    __tablename__ = 'wrong_question_collections'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    
    is_public = db.Column(db.Boolean, default=False)
    
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    
    items = db.relationship('WrongQuestionCollectionItem', backref='collection', lazy='dynamic', cascade='all, delete-orphan')
    user = db.relationship('User', backref='collections')


class WrongQuestionCollectionItem(db.Model):
    __tablename__ = 'wrong_question_collection_items'
    
    id = db.Column(db.Integer, primary_key=True)
    collection_id = db.Column(db.Integer, db.ForeignKey('wrong_question_collections.id'), nullable=False)
    wrong_question_id = db.Column(db.Integer, db.ForeignKey('wrong_questions.id'), nullable=False)
    
    note = db.Column(db.Text)
    added_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    
    wrong_question = db.relationship('WrongQuestion', backref='collection_items')
    
    __table_args__ = (
        db.UniqueConstraint('collection_id', 'wrong_question_id', name='unique_collection_question'),
    )


class WrongQuestionNote(db.Model):
    __tablename__ = 'wrong_question_notes'
    
    id = db.Column(db.Integer, primary_key=True)
    wrong_question_id = db.Column(db.Integer, db.ForeignKey('wrong_questions.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    
    wrong_question = db.relationship('WrongQuestion', backref='notes_list')
    user = db.relationship('User', backref='wrong_notes')


class ChallengeProgress(db.Model):
    """闯关模式 - 关卡通关进度"""
    __tablename__ = 'challenge_progress'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    chapter_id = db.Column(db.Integer, db.ForeignKey('chapters.id'), nullable=False)
    is_cleared = db.Column(db.Boolean, default=False)
    cleared_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    
    user = db.relationship('User', backref='challenge_progress')
    chapter = db.relationship('Chapter', backref='challenge_progress_records')
    
    __table_args__ = (
        db.UniqueConstraint('user_id', 'chapter_id', name='unique_user_chapter_progress'),
    )


class ReviewStreak(db.Model):
    """学习打卡记录"""
    __tablename__ = 'review_streaks'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    date = db.Column(db.Date, nullable=False)
    review_count = db.Column(db.Integer, default=1)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    
    user = db.relationship('User', backref='review_streaks')
    
    __table_args__ = (
        db.UniqueConstraint('user_id', 'date', name='unique_user_date_streak'),
        db.Index('idx_streak_user_date', 'user_id', 'date'),
    )
