"""智能题目推送服务

基于学习记忆规律（间隔重复、遗忘曲线、难度自适应）的智能题目推荐系统。
不依赖AI，纯算法实现，确保系统稳定性。
"""

import math
import random
import logging
from datetime import datetime, timedelta, timezone
from collections import defaultdict
from sqlalchemy import func
from app import db
from app.models import Question, WrongQuestion, UserAnswer

logger = logging.getLogger(__name__)


class QuestionRecommender:
    """智能题目推荐引擎"""
    
    def __init__(self):
        self.difficulty_coefficients = {
            1: 1.5,
            2: 1.0,
            3: 0.7,
            4: 0.5
        }
        
        self.mastery_coefficients = {
            0: 0.5,
            1: 0.8,
            2: 1.0,
            3: 1.2,
            4: 1.5
        }
        
        self.base_intervals = {
            0: 0.5,
            1: 1,
            2: 3,
            3: 7,
            4: 14,
            5: 30,
            6: 60
        }
    
    def get_user_accuracy_for_question(self, user_id, question_id):
        """计算用户对某题目的历史正确率"""
        answers = UserAnswer.query.filter_by(
            user_id=user_id,
            question_id=question_id
        ).all()
        
        if not answers:
            return None
        
        correct_count = sum(1 for a in answers if a.is_correct)
        return correct_count / len(answers)
    
    def get_user_accuracy_for_chapter(self, user_id, chapter_id):
        """计算用户对某章节的整体正确率"""
        answers = db.session.query(
            func.count(UserAnswer.id).label('total'),
            func.sum(func.case((UserAnswer.is_correct == True, 1), else_=0)).label('correct')
        ).join(
            Question, UserAnswer.question_id == Question.id
        ).filter(
            UserAnswer.user_id == user_id,
            Question.chapter_id == chapter_id
        ).first()
        
        if not answers or answers.total == 0:
            return None
        
        return answers.correct / answers.total
    
    def calculate_dynamic_interval(self, consecutive_correct, wrong_count, difficulty):
        """动态计算复习间隔（天）
        
        基于：
        1. 连续正确次数
        2. 历史错误次数
        3. 题目难度
        """
        base_interval = self.base_intervals.get(min(consecutive_correct + 1, 6), 30)
        
        difficulty_coeff = self.difficulty_coefficients.get(difficulty, 1.0)
        
        mastery_level = min(consecutive_correct, 4)
        mastery_coeff = self.mastery_coefficients.get(mastery_level, 1.0)
        
        interval = base_interval * difficulty_coeff * mastery_coeff
        
        if consecutive_correct == 0 and wrong_count >= 5:
            interval = max(0.25, interval * 0.5)
        
        return round(interval, 2)
    
    def calculate_urgency_score(self, next_review_at):
        """计算紧急度分数（0-100）"""
        if next_review_at is None:
            return 100
        
        now = datetime.now(timezone.utc)
        diff = (now - next_review_at).total_seconds()
        
        days_overdue = diff / 86400
        
        if days_overdue >= 3:
            return 100
        elif days_overdue >= 1:
            return 80
        elif days_overdue >= 0:
            return 60
        elif days_overdue >= -1:
            return 30
        else:
            return 0
    
    def calculate_weakness_score(self, wrong_count, accuracy):
        """计算薄弱度分数（0-100）"""
        wrong_score = min(wrong_count * 10, 100)
        
        if accuracy is not None:
            if accuracy < 0.3:
                accuracy_score = 100
            elif accuracy < 0.6:
                accuracy_score = 70
            elif accuracy < 0.8:
                accuracy_score = 50
            else:
                accuracy_score = 30
        else:
            accuracy_score = 50
        
        return (wrong_score + accuracy_score) / 2
    
    def calculate_importance_score(self, is_important, is_mastered):
        """计算重要性分数（0-100）"""
        score = 0
        
        if is_important:
            score += 50
        
        if not is_mastered:
            score += 30
        
        return score
    
    def calculate_freshness_score(self, user_id, question_id):
        """计算新鲜度分数（避免重复推送）"""
        last_answer = UserAnswer.query.filter_by(
            user_id=user_id,
            question_id=question_id
        ).order_by(UserAnswer.created_at.desc()).first()
        
        if not last_answer:
            return 100
        
        now = datetime.now(timezone.utc)
        hours_since = (now - last_answer.created_at).total_seconds() / 3600
        
        if hours_since < 1:
            return 20
        elif hours_since < 24:
            return 60
        elif hours_since < 72:
            return 80
        else:
            return 100
    
    def calculate_priority_score(self, user_id, wrong_question):
        """计算综合推送优先级分数"""
        urgency_score = self.calculate_urgency_score(wrong_question.next_review_at)
        
        accuracy = self.get_user_accuracy_for_question(
            user_id, wrong_question.question_id
        )
        weakness_score = self.calculate_weakness_score(
            wrong_question.wrong_count, accuracy
        )
        
        importance_score = self.calculate_importance_score(
            wrong_question.is_important, wrong_question.is_mastered
        )
        
        freshness_score = self.calculate_freshness_score(
            user_id, wrong_question.question_id
        )
        
        total_score = (
            urgency_score * 0.40 +
            weakness_score * 0.30 +
            importance_score * 0.15 +
            freshness_score * 0.15
        )
        
        return total_score
    
    def get_review_questions(self, user_id, limit=20):
        """获取复习模式推荐题目
        
        混合策略：
        - 70% 到期错题
        - 20% 薄弱章节新题
        - 10% 随机巩固题
        """
        review_questions = WrongQuestion.get_review_needed(user_id, limit=int(limit * 0.7))
        
        if review_questions:
            scored_questions = []
            for wq in review_questions:
                score = self.calculate_priority_score(user_id, wq)
                scored_questions.append((score, wq))
            
            scored_questions.sort(key=lambda x: x[0], reverse=True)
            review_questions = [wq for score, wq in scored_questions]
        
        weak_questions = self._get_weak_chapter_questions(user_id, int(limit * 0.2))
        
        existing_ids = set(wq.question_id for wq in review_questions)
        weak_questions = [q for q in weak_questions if q.id not in existing_ids]
        
        all_questions = review_questions + weak_questions
        
        if len(all_questions) < limit:
            random_questions = self._get_random_consolidation(
                user_id, limit - len(all_questions)
            )
            existing_ids = set(q.id for q in all_questions)
            random_questions = [q for q in random_questions if q.id not in existing_ids]
            all_questions.extend(random_questions)
        
        random.shuffle(all_questions[-int(limit*0.1):])
        
        return all_questions[:limit]
    
    def _get_weak_chapter_questions(self, user_id, limit):
        """从薄弱章节获取新题目"""
        weak_chapters = WrongQuestion.get_weak_points(user_id, limit=3)
        
        if not weak_chapters:
            return []
        
        chapter_ids = [ch.id for ch in weak_chapters]
        
        answered_question_ids = db.session.query(
            UserAnswer.question_id
        ).filter(
            UserAnswer.user_id == user_id
        ).distinct().all()
        answered_ids = set(q[0] for q in answered_question_ids)
        
        questions = Question.query.filter(
            Question.chapter_id.in_(chapter_ids),
            Question.is_active == True,
            ~Question.id.in_(answered_ids) if answered_ids else True
        ).order_by(
            func.random()
        ).limit(limit).all()
        
        return questions
    
    def _get_random_consolidation(self, user_id, limit):
        """获取随机巩固题目（历史答对的题目）"""
        correct_answers = db.session.query(
            UserAnswer.question_id
        ).filter(
            UserAnswer.user_id == user_id,
            UserAnswer.is_correct == True
        ).distinct().all()
        
        if not correct_answers:
            return []
        
        correct_ids = [a[0] for a in correct_answers]
        
        questions = Question.query.filter(
            Question.id.in_(correct_ids),
            Question.is_active == True
        ).order_by(
            func.random()
        ).limit(limit).all()
        
        return questions
    
    def get_challenge_questions(self, user_id, subject_id=None, chapter_id=None, 
                                count=10, difficulty=None, user_major=None):
        """获取挑战模式题目（难度自适应）
        
        根据用户当前水平，推送难度递进的题目。
        """
        if difficulty:
            return self._get_questions_by_difficulty(
                subject_id, chapter_id, difficulty, count, user_major
            )
        
        user_avg_difficulty = self._get_user_average_difficulty(user_id, subject_id)
        
        target_difficulty = max(1, min(4, int(round(user_avg_difficulty))))
        
        questions = self._get_questions_by_difficulty(
            subject_id, chapter_id, target_difficulty, count, user_major
        )
        
        if len(questions) < count:
            for diff in [target_difficulty - 1, target_difficulty + 1, 
                        target_difficulty - 2, target_difficulty + 2]:
                if 1 <= diff <= 4:
                    extra = self._get_questions_by_difficulty(
                        subject_id, chapter_id, diff, count - len(questions), user_major
                    )
                    questions.extend(extra)
                    if len(questions) >= count:
                        break
        
        random.shuffle(questions)
        return questions[:count]
    
    def _get_user_average_difficulty(self, user_id, subject_id=None):
        """计算用户平均答题难度"""
        query = db.session.query(
            func.avg(Question.difficulty)
        ).join(
            UserAnswer, Question.id == UserAnswer.question_id
        ).filter(
            UserAnswer.user_id == user_id
        )
        
        if subject_id:
            query = query.filter(Question.subject_id == subject_id)
        
        result = query.first()
        
        if result and result[0]:
            return result[0]
        
        return 2
    
    def _get_questions_by_difficulty(self, subject_id, chapter_id, difficulty, count, user_major=None):
        """按难度获取题目"""
        from sqlalchemy import func
        from app.models import Subject
        
        query = Question.query.filter_by(is_active=True, difficulty=difficulty)
        
        if subject_id:
            query = query.filter_by(subject_id=subject_id)
        else:
            subject_ids = [
                s.id for s in Subject.query.filter_by(is_active=True).all()
                if s.is_applicable_for_major(user_major)
            ]
            if subject_ids:
                query = query.filter(Question.subject_id.in_(subject_ids))
        
        if chapter_id:
            from app.services.game_service import _get_all_child_chapter_ids
            chapter_ids = _get_all_child_chapter_ids(chapter_id)
            query = query.filter(Question.chapter_id.in_(chapter_ids))
        
        total_count = query.with_entities(func.count(Question.id)).scalar()
        if total_count == 0:
            return []
        
        if total_count <= count:
            return query.all()
        
        return query.order_by(func.random()).limit(count).all()
    
    def get_specialized_practice(self, user_id, chapter_id, count=10):
        """获取专项突破题目
        
        同一知识点变式题连续出现，强化训练。
        """
        wrong_in_chapter = WrongQuestion.query.filter_by(
            user_id=user_id,
            is_mastered=False
        ).join(
            Question, WrongQuestion.question_id == Question.id
        ).filter(
            Question.chapter_id == chapter_id
        ).order_by(
            WrongQuestion.wrong_count.desc(),
            WrongQuestion.next_review_at.asc()
        ).limit(count).all()
        
        if wrong_in_chapter:
            return [wq.question for wq in wrong_in_chapter if wq.question]
        
        similar_questions = self._get_similar_questions_in_chapter(
            user_id, chapter_id, count
        )
        
        return similar_questions
    
    def _get_similar_questions_in_chapter(self, user_id, chapter_id, count):
        """获取同章节相似题目"""
        answered_question_ids = db.session.query(
            UserAnswer.question_id
        ).filter(
            UserAnswer.user_id == user_id
        ).distinct().all()
        answered_ids = set(q[0] for q in answered_question_ids)
        
        questions = Question.query.filter(
            Question.chapter_id == chapter_id,
            Question.is_active == True,
            ~Question.id.in_(answered_ids) if answered_ids else True
        ).order_by(
            Question.difficulty.asc(),
            func.random()
        ).limit(count).all()
        
        return questions
    
    def update_next_review_for_wrong_question(self, wrong_question):
        """更新错题的下一次复习时间（使用动态间隔算法）"""
        difficulty = wrong_question.question.difficulty if wrong_question.question else 2
        
        interval = self.calculate_dynamic_interval(
            wrong_question.consecutive_correct or 0,
            wrong_question.wrong_count or 1,
            difficulty
        )
        
        wrong_question.next_review_at = datetime.now(timezone.utc) + timedelta(days=interval)


recommender = QuestionRecommender()


def get_smart_review_questions(user_id, limit=20):
    """智能复习题目推荐（包装函数）"""
    try:
        return recommender.get_review_questions(user_id, limit)
    except Exception as e:
        logger.error(f'智能复习推荐失败，降级为传统推荐: {e}')
        try:
            return WrongQuestion.get_review_needed(user_id, limit)
        except Exception:
            logger.error('传统推荐也失败，返回空列表')
            return []


def get_smart_challenge_questions(user_id, subject_id=None, chapter_id=None, 
                                  count=10, difficulty=None, user_major=None):
    """智能挑战题目推荐（包装函数）"""
    try:
        return recommender.get_challenge_questions(
            user_id, subject_id, chapter_id, count, difficulty, user_major
        )
    except Exception as e:
        logger.error(f'智能挑战推荐失败，降级为随机推荐: {e}')
        try:
            from app.services.game_service import get_random_questions
            return get_random_questions(subject_id, chapter_id, count, difficulty, user_major)
        except Exception:
            logger.error('随机推荐也失败，返回空列表')
            return []


def get_smart_specialized_practice(user_id, chapter_id, count=10):
    """智能专项突破推荐（包装函数）"""
    try:
        return recommender.get_specialized_practice(user_id, chapter_id, count)
    except Exception as e:
        logger.error(f'智能专项推荐失败，降级为错题列表: {e}')
        try:
            wrong_questions = WrongQuestion.query.filter_by(
                user_id=user_id, is_mastered=False
            ).join(
                Question, WrongQuestion.question_id == Question.id
            ).filter(
                Question.chapter_id == chapter_id
            ).order_by(
                WrongQuestion.wrong_count.desc()
            ).limit(count).all()
            return [wq.question for wq in wrong_questions if wq.question]
        except Exception:
            logger.error('错题列表也失败，返回空列表')
            return []
