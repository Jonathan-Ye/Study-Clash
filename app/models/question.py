from datetime import datetime, timezone
import json
from app import db

class Subject(db.Model):
    __tablename__ = 'subjects'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)
    code = db.Column(db.String(20), unique=True)
    description = db.Column(db.Text)
    icon = db.Column(db.String(100))
    is_active = db.Column(db.Boolean, default=True)
    applicable_majors = db.Column(db.Text, default='[]')
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    
    chapters = db.relationship('Chapter', backref='subject', lazy='dynamic')
    questions = db.relationship('Question', backref='subject', lazy='dynamic')

    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    creator = db.relationship('User', foreign_keys=[created_by])

    def get_applicable_majors(self):
        if not self.applicable_majors:
            return []
        try:
            return json.loads(self.applicable_majors)
        except:
            return []

    def set_applicable_majors(self, majors_list):
        if isinstance(majors_list, list):
            self.applicable_majors = json.dumps(majors_list, ensure_ascii=False)
        else:
            self.applicable_majors = '[]'

    def is_applicable_for_major(self, major):
        if not major:
            return True
        applicable = self.get_applicable_majors()
        if not applicable:
            return True
        return major in applicable

class Chapter(db.Model):
    __tablename__ = 'chapters'

    id = db.Column(db.Integer, primary_key=True)
    subject_id = db.Column(db.Integer, db.ForeignKey('subjects.id'), nullable=False)
    parent_id = db.Column(db.Integer, db.ForeignKey('chapters.id'), nullable=True, default=None)
    name = db.Column(db.String(100), nullable=False)
    level = db.Column(db.Integer, default=1)
    order = db.Column(db.Integer, default=0)
    description = db.Column(db.Text)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    questions = db.relationship('Question', backref='chapter', lazy='dynamic')

    children = db.relationship('Chapter', backref=db.backref('parent', remote_side=[id]), lazy='dynamic')

    def get_full_path(self):
        path = [self.name]
        parent = self.parent
        while parent:
            path.insert(0, parent.name)
            parent = parent.parent
        return ' > '.join(path)

    def get_level_name(self):
        names = {1: '章', 2: '节', 3: '小节'}
        return names.get(self.level, '')

class Question(db.Model):
    __tablename__ = 'questions'
    
    id = db.Column(db.Integer, primary_key=True)
    subject_id = db.Column(db.Integer, db.ForeignKey('subjects.id'), nullable=False, index=True)
    chapter_id = db.Column(db.Integer, db.ForeignKey('chapters.id'), index=True)
    
    question_type = db.Column(db.String(20), nullable=False)
    difficulty = db.Column(db.Integer, default=1, index=True)
    
    content = db.Column(db.Text, nullable=False)
    image_url = db.Column(db.String(256))
    
    option_a = db.Column(db.Text)
    option_a_image = db.Column(db.String(256))
    option_b = db.Column(db.Text)
    option_b_image = db.Column(db.String(256))
    option_c = db.Column(db.Text)
    option_c_image = db.Column(db.String(256))
    option_d = db.Column(db.Text)
    option_d_image = db.Column(db.String(256))
    option_e = db.Column(db.Text)
    option_e_image = db.Column(db.String(256))
    option_f = db.Column(db.Text)
    option_f_image = db.Column(db.String(256))
    
    correct_answer = db.Column(db.String(50), nullable=False)
    analysis = db.Column(db.Text)
    
    points = db.Column(db.Integer, default=10)
    time_limit = db.Column(db.Integer, default=60)
    
    is_active = db.Column(db.Boolean, default=True, index=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    
    __table_args__ = (
        db.Index('idx_questions_subject_active', 'subject_id', 'is_active'),
        db.Index('idx_questions_chapter_active', 'chapter_id', 'is_active'),
        db.Index('idx_questions_subject_chapter_active', 'subject_id', 'chapter_id', 'is_active'),
        db.Index('idx_questions_difficulty_active', 'difficulty', 'is_active'),
    )
    
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    creator = db.relationship('User', foreign_keys=[created_by])
    
    answers = db.relationship('UserAnswer', backref='question', lazy='dynamic')
    wrong_records = db.relationship('WrongQuestion', backref='question', lazy='dynamic')
    
    QUESTION_TYPES = {
        'single': '单选题',
        'multiple': '多选题',
        'judge': '判断题',
        'fill': '填空题'
    }
    
    DIFFICULTY_LEVELS = {
        1: '简单',
        2: '中等',
        3: '困难',
        4: '极难'
    }
    
    def check_answer(self, user_answer):
        if self.question_type == 'single':
            return user_answer.upper() == self.correct_answer.upper()
        elif self.question_type == 'multiple':
            user_set = self._parse_multiple_answer(user_answer)
            correct_set = self._parse_multiple_answer(self.correct_answer)
            return user_set == correct_set
        elif self.question_type == 'judge':
            return user_answer.upper() == self.correct_answer.upper()
        elif self.question_type == 'fill':
            # 填空题：忽略首尾空格，支持多个正确答案（用|分隔）
            user_answer_clean = user_answer.strip()
            correct_answers = [a.strip() for a in self.correct_answer.split('|')]
            return user_answer_clean in correct_answers
        return False
    
    def _parse_multiple_answer(self, answer_str):
        """解析多选题答案，支持多种格式：
        - "A,B,C" (逗号分隔)
        - "A, B, C" (逗号+空格)
        - "ABC" (无分隔符)
        - "A,B,C," (末尾逗号)
        """
        answer_str = answer_str.upper().strip()
        
        # 如果包含逗号，按逗号分割
        if ',' in answer_str:
            return set(a.strip() for a in answer_str.split(',') if a.strip())
        
        # 否则视为连续字符，逐字符分割
        return set(c for c in answer_str if c.isalpha())
    
    def get_options(self):
        options = []
        if self.option_a:
            options.append(('A', self.option_a, self.option_a_image))
        if self.option_b:
            options.append(('B', self.option_b, self.option_b_image))
        if self.option_c:
            options.append(('C', self.option_c, self.option_c_image))
        if self.option_d:
            options.append(('D', self.option_d, self.option_d_image))
        if self.option_e:
            options.append(('E', self.option_e, self.option_e_image))
        if self.option_f:
            options.append(('F', self.option_f, self.option_f_image))
        return options
    
    def to_dict(self, include_answer=False):
        data = {
            'id': self.id,
            'subject_id': self.subject_id,
            'chapter_id': self.chapter_id,
            'question_type': self.question_type,
            'difficulty': self.difficulty,
            'content': self.content,
            'image_url': self.image_url,
            'options': self.get_options(),
            'points': self.points,
            'time_limit': self.time_limit
        }
        if include_answer:
            data['correct_answer'] = self.correct_answer
            data['analysis'] = self.analysis
        return data

class UserAnswer(db.Model):
    __tablename__ = 'user_answers'
    
    __table_args__ = (
        db.Index('idx_user_answer_user_created', 'user_id', 'created_at'),
        db.Index('idx_user_answer_question', 'question_id'),
    )
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    question_id = db.Column(db.Integer, db.ForeignKey('questions.id'), nullable=False, index=True)
    
    user_answer = db.Column(db.String(100), nullable=False)
    is_correct = db.Column(db.Boolean, nullable=False)
    time_spent = db.Column(db.Integer)
    
    game_type = db.Column(db.String(20))
    game_id = db.Column(db.Integer)
    
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
