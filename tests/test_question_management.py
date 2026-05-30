import pytest
from app.models.user import User
from app.models.question import Question, Subject
from app import db


class TestQuestionManagement:
    """题库管理测试"""

    def test_create_question(self, app, admin_user):
        """测试创建题目"""
        with app.app_context():
            subject = Subject(name='测试学科', code='test_q')
            db.session.add(subject)
            db.session.commit()
            
            question = Question(
                content='测试题目',
                question_type='single',
                option_a='选项1',
                option_b='选项2',
                option_c='选项3',
                option_d='选项4',
                correct_answer='A',
                analysis='这是解释',
                subject_id=subject.id,
                difficulty=1
            )
            db.session.add(question)
            db.session.commit()
            
            assert question.id is not None
            assert question.is_active is True

    def test_update_question(self, app, admin_user, question):
        """测试更新题目"""
        with app.app_context():
            question.content = '更新后的题目'
            question.difficulty = 2
            db.session.commit()
            
            updated = Question.query.get(question.id)
            assert updated.content == '更新后的题目'
            assert updated.difficulty == 2

    def test_delete_question(self, app, question):
        """测试删除题目（软删除）"""
        with app.app_context():
            question.is_active = False
            db.session.commit()
            
            q = Question.query.get(question.id)
            assert q.is_active is False

    def test_query_active_questions(self, app):
        """测试查询活跃题目"""
        with app.app_context():
            subject = Subject(name='活跃测试', code='active_t')
            db.session.add(subject)
            db.session.commit()
            
            for i in range(3):
                q = Question(
                    content=f'活跃题目{i}',
                    question_type='single',
                    option_a='1',
                    option_b='2',
                    option_c='3',
                    option_d='4',
                    correct_answer='A',
                    subject_id=subject.id,
                    difficulty=1,
                    is_active=True
                )
                db.session.add(q)
            db.session.commit()
            
            active_questions = Question.query.filter_by(
                subject_id=subject.id,
                is_active=True
            ).all()
            
            assert len(active_questions) >= 3

    def test_search_questions(self, app, question):
        """测试搜索题目"""
        with app.app_context():
            for i in range(5):
                q = Question(
                    content=f'搜索测试题目{i}',
                    question_type='single',
                    option_a='1',
                    option_b='2',
                    option_c='3',
                    option_d='4',
                    correct_answer='A',
                    subject_id=question.subject_id,
                    difficulty=1
                )
                db.session.add(q)
            db.session.commit()
            
            results = Question.query.filter(
                Question.content.contains('搜索测试')
            ).all()
            
            assert len(results) >= 5

    def test_question_by_subject(self, app, subject):
        """测试按学科查询题目"""
        with app.app_context():
            for i in range(3):
                q = Question(
                    content=f'学科题目{i}',
                    question_type='single',
                    option_a='1',
                    option_b='2',
                    option_c='3',
                    option_d='4',
                    correct_answer='A',
                    subject_id=subject.id,
                    difficulty=1
                )
                db.session.add(q)
            db.session.commit()
            
            subject_questions = Question.query.filter_by(
                subject_id=subject.id,
                is_active=True
            ).all()
            
            assert len(subject_questions) >= 3

    def test_question_by_difficulty(self, app, subject):
        """测试按难度查询题目"""
        with app.app_context():
            for diff in [1, 2, 3]:
                q = Question(
                    content=f'难度{diff}题目',
                    question_type='single',
                    option_a='1',
                    option_b='2',
                    option_c='3',
                    option_d='4',
                    correct_answer='A',
                    subject_id=subject.id,
                    difficulty=diff
                )
                db.session.add(q)
            db.session.commit()
            
            easy_questions = Question.query.filter_by(
                difficulty=1,
                is_active=True
            ).all()
            
            assert len(easy_questions) >= 1

    def test_question_validation(self, app, subject):
        """测试题目验证"""
        with app.app_context():
            q = Question(
                content='验证题目',
                question_type='single',
                option_a='1',
                option_b='2',
                correct_answer='A',
                subject_id=subject.id
            )
            db.session.add(q)
            db.session.commit()
            
            assert q.id is not None

    def test_multiple_choice_question(self, app, subject):
        """测试多选题"""
        with app.app_context():
            q = Question(
                content='多选题测试',
                question_type='multiple',
                option_a='选项1',
                option_b='选项2',
                option_c='选项3',
                option_d='选项4',
                correct_answer='A,B',
                subject_id=subject.id,
                difficulty=2
            )
            db.session.add(q)
            db.session.commit()
            
            assert q.question_type == 'multiple'
            assert q.correct_answer == 'A,B'

    def test_question_with_image(self, app, subject):
        """测试带图片的题目"""
        with app.app_context():
            q = Question(
                content='带图片的题目',
                question_type='single',
                option_a='1',
                option_b='2',
                option_c='3',
                option_d='4',
                correct_answer='A',
                subject_id=subject.id,
                image_url='/uploads/test.jpg'
            )
            db.session.add(q)
            db.session.commit()
            
            assert q.image_url is not None

    def test_question_statistics(self, app, question):
        """测试题目统计"""
        with app.app_context():
            total = Question.query.count()
            active = Question.query.filter_by(is_active=True).count()
            
            assert total >= 1
            assert active >= 1

    def test_bulk_delete_questions(self, app, subject):
        """测试批量删除题目"""
        with app.app_context():
            for i in range(10):
                q = Question(
                    content=f'批量题目{i}',
                    question_type='single',
                    option_a='1',
                    option_b='2',
                    option_c='3',
                    option_d='4',
                    correct_answer='A',
                    subject_id=subject.id,
                    difficulty=1
                )
                db.session.add(q)
            db.session.commit()
            
            Question.query.filter_by(subject_id=subject.id).update(
                {'is_active': False},
                synchronize_session=False
            )
            db.session.commit()
            
            active = Question.query.filter_by(
                subject_id=subject.id,
                is_active=True
            ).count()
            
            assert active == 0
