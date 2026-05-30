import pytest
from datetime import datetime, timezone, timedelta
from app.models.user import User
from app.models.question import Question, Subject
from app.models.wrong_question import WrongQuestion
from app import db


class TestWrongQuestions:
    """错题本测试"""

    def test_add_wrong_question(self, app, regular_user, question):
        """测试添加错题"""
        with app.app_context():
            wrong = WrongQuestion(
                user_id=regular_user.id,
                question_id=question.id,
                wrong_count=1
            )
            wrong.calculate_next_review()
            db.session.add(wrong)
            db.session.commit()
            
            assert wrong.id is not None
            assert wrong.wrong_count == 1
            assert wrong.next_review_at is not None

    def test_increment_wrong_count(self, app, regular_user, question):
        """测试错误次数递增"""
        with app.app_context():
            wrong = WrongQuestion(
                user_id=regular_user.id,
                question_id=question.id,
                wrong_count=1
            )
            wrong.calculate_next_review()
            db.session.add(wrong)
            db.session.commit()
            
            wrong.wrong_count += 1
            wrong.calculate_next_review()
            db.session.commit()
            
            assert wrong.wrong_count == 2

    def test_master_wrong_question(self, app, regular_user, question):
        """测试标记错题为已掌握"""
        with app.app_context():
            wrong = WrongQuestion(
                user_id=regular_user.id,
                question_id=question.id,
                wrong_count=1,
                is_mastered=False
            )
            wrong.calculate_next_review()
            db.session.add(wrong)
            db.session.commit()
            
            wrong.is_mastered = True
            db.session.commit()
            
            assert wrong.is_mastered is True

    def test_query_wrong_questions(self, app, regular_user, question):
        """测试查询错题"""
        with app.app_context():
            wrong = WrongQuestion(
                user_id=regular_user.id,
                question_id=question.id,
                wrong_count=2
            )
            wrong.calculate_next_review()
            db.session.add(wrong)
            db.session.commit()
            
            user_wrongs = WrongQuestion.query.filter_by(
                user_id=regular_user.id
            ).all()
            
            assert len(user_wrongs) >= 1

    def test_review_schedule(self, app, regular_user, question):
        """测试复习计划"""
        with app.app_context():
            wrong = WrongQuestion(
                user_id=regular_user.id,
                question_id=question.id,
                wrong_count=1
            )
            wrong.calculate_next_review()
            db.session.add(wrong)
            db.session.commit()
            
            from datetime import datetime, timezone
            assert wrong.next_review_at > datetime.now(timezone.utc)

    def test_due_for_review(self, app, regular_user, question):
        """测试到期复习查询"""
        with app.app_context():
            wrong = WrongQuestion(
                user_id=regular_user.id,
                question_id=question.id,
                wrong_count=1,
                is_mastered=False
            )
            wrong.calculate_next_review()
            db.session.add(wrong)
            db.session.commit()
            
            due_wrongs = WrongQuestion.query.filter(
                WrongQuestion.user_id == regular_user.id,
                WrongQuestion.is_mastered == False,
                WrongQuestion.next_review_at <= datetime.now(timezone.utc)
            ).all()
            
            assert len(due_wrongs) == 0

    def test_wrong_statistics(self, app, regular_user, question):
        """测试错题统计"""
        with app.app_context():
            wrong = WrongQuestion(
                user_id=regular_user.id,
                question_id=question.id,
                wrong_count=3
            )
            wrong.calculate_next_review()
            db.session.add(wrong)
            db.session.commit()
            
            total_wrong = WrongQuestion.query.filter_by(
                user_id=regular_user.id
            ).count()
            
            mastered = WrongQuestion.query.filter_by(
                user_id=regular_user.id,
                is_mastered=True
            ).count()
            
            assert total_wrong >= 1
            assert mastered == 0

    def test_high_frequency_wrong(self, app, regular_user, question):
        """测试高频错题"""
        with app.app_context():
            wrong = WrongQuestion(
                user_id=regular_user.id,
                question_id=question.id,
                wrong_count=10
            )
            wrong.calculate_next_review()
            db.session.add(wrong)
            db.session.commit()
            
            high_freq = WrongQuestion.query.filter(
                WrongQuestion.user_id == regular_user.id,
                WrongQuestion.wrong_count >= 5
            ).all()
            
            assert len(high_freq) >= 1

    def test_delete_wrong_question(self, app, regular_user, question):
        """测试删除错题记录"""
        with app.app_context():
            wrong = WrongQuestion(
                user_id=regular_user.id,
                question_id=question.id,
                wrong_count=1
            )
            wrong.calculate_next_review()
            db.session.add(wrong)
            db.session.commit()
            
            db.session.delete(wrong)
            db.session.commit()
            
            deleted = WrongQuestion.query.filter_by(
                user_id=regular_user.id,
                question_id=question.id
            ).first()
            
            assert deleted is None

    def test_multiple_wrong_questions(self, app, regular_user, subject):
        """测试多道错题"""
        with app.app_context():
            questions = []
            for i in range(5):
                q = Question(
                    content=f'错题{i}',
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
                questions.append(q)
            db.session.commit()
            
            for q in questions:
                wrong = WrongQuestion(
                    user_id=regular_user.id,
                    question_id=q.id,
                    wrong_count=1
                )
                wrong.calculate_next_review()
                db.session.add(wrong)
            db.session.commit()
            
            user_wrongs = WrongQuestion.query.filter_by(
                user_id=regular_user.id
            ).all()
            
            assert len(user_wrongs) >= 5

    def test_consecutive_correct(self, app, regular_user, question):
        """测试连续答对次数"""
        with app.app_context():
            wrong = WrongQuestion(
                user_id=regular_user.id,
                question_id=question.id,
                wrong_count=1,
                consecutive_correct=0
            )
            wrong.calculate_next_review()
            db.session.add(wrong)
            db.session.commit()
            
            wrong.consecutive_correct = 3
            wrong.calculate_next_review()
            db.session.commit()
            
            assert wrong.consecutive_correct == 3

    def test_wrong_reason(self, app, regular_user, question):
        """测试错误原因"""
        with app.app_context():
            wrong = WrongQuestion(
                user_id=regular_user.id,
                question_id=question.id,
                wrong_count=1,
                wrong_reason='概念不清'
            )
            wrong.calculate_next_review()
            db.session.add(wrong)
            db.session.commit()
            
            assert wrong.wrong_reason == '概念不清'
