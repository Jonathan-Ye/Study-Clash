import json
import logging
from datetime import datetime, timezone, timedelta
from app import db
from app.models.ai_analysis import AIAnalysisResult, AIPredictionResult
from app.models.wrong_question import WrongQuestion
from app.models.question import Question, Chapter, Subject, UserAnswer
from sqlalchemy import func

logger = logging.getLogger(__name__)


class VisualizationService:
    @staticmethod
    def get_distribution_chart_data(user_id: int, dimension: str = 'chapter') -> dict:
        wrong_questions = WrongQuestion.query.filter_by(user_id=user_id).all()
        if not wrong_questions:
            return {'status': 'no_data', 'message': '暂无错题数据'}

        question_ids = [wq.question_id for wq in wrong_questions]
        questions = Question.query.filter(Question.id.in_(question_ids)).all()
        q_map = {q.id: q for q in questions}

        data = {}
        for wq in wrong_questions:
            q = q_map.get(wq.question_id)
            if not q:
                continue
            if dimension == 'chapter':
                chapter = Chapter.query.get(q.chapter_id) if q.chapter_id else None
                key = chapter.name if chapter else '未分类'
            elif dimension == 'error_reason':
                from app.models.wrong_question import WRONG_REASONS
                key = WRONG_REASONS.get(wq.wrong_reason, '未标注')
            elif dimension == 'difficulty':
                key = Question.DIFFICULTY_LEVELS.get(q.difficulty, '未知')
            elif dimension == 'subject':
                subject = Subject.query.get(q.subject_id) if q.subject_id else None
                key = subject.name if subject else '未知'
            else:
                key = '未知'
            data[key] = data.get(key, 0) + 1

        labels = list(data.keys())
        values = list(data.values())
        return {
            'status': 'success',
            'dimension': dimension,
            'labels': labels,
            'values': values,
        }

    @staticmethod
    def get_radar_chart_data(user_id: int) -> dict:
        analysis = AIAnalysisResult.query.filter_by(
            user_id=user_id
        ).order_by(AIAnalysisResult.created_at.desc()).first()
        if not analysis:
            return {'status': 'no_analysis', 'message': '请先完成归因分析'}

        ability_scores = json.loads(analysis.ability_scores) if analysis.ability_scores else {}
        dimensions = [
            {'name': '理解力', 'key': 'understanding'},
            {'name': '计算力', 'key': 'calculation'},
            {'name': '应用力', 'key': 'application'},
            {'name': '推理力', 'key': 'reasoning'},
            {'name': '记忆力', 'key': 'memory'},
        ]
        values = [ability_scores.get(d['key'], 50) for d in dimensions]
        return {
            'status': 'success',
            'indicators': [{'name': d['name'], 'max': 100} for d in dimensions],
            'values': values,
        }

    @staticmethod
    def get_heatmap_data(user_id: int, subject_id: int = None) -> dict:
        analysis = AIAnalysisResult.query.filter_by(
            user_id=user_id
        ).order_by(AIAnalysisResult.created_at.desc()).first()
        if not analysis:
            return {'status': 'no_analysis', 'message': '请先完成归因分析'}

        mastery = json.loads(analysis.knowledge_mastery) if analysis.knowledge_mastery else []
        if not mastery:
            return {'status': 'no_data', 'message': '无掌握度数据'}

        if subject_id:
            items = [{'name': m.get('name', ''), 'score': m.get('score', 0)}
                     for m in mastery]
        else:
            items = [{'name': m.get('name', ''), 'score': m.get('score', 0)}
                     for m in mastery]

        return {
            'status': 'success',
            'level': 'chapter' if subject_id else 'subject',
            'items': items,
        }

    @staticmethod
    def get_trend_chart_data(user_id: int) -> dict:
        now = datetime.now(timezone.utc)
        thirty_days_ago = now - timedelta(days=30)

        daily_stats = db.session.query(
            func.date(WrongQuestion.created_at).label('date'),
            func.count(WrongQuestion.id).label('count'),
        ).filter(
            WrongQuestion.user_id == user_id,
            WrongQuestion.created_at >= thirty_days_ago,
        ).group_by(
            func.date(WrongQuestion.created_at)
        ).order_by('date').all()

        history_dates = [str(s.date) for s in daily_stats]
        history_values = [s.count for s in daily_stats]

        prediction_dates = []
        prediction_values = []
        prediction = AIPredictionResult.query.filter_by(
            user_id=user_id
        ).order_by(AIPredictionResult.created_at.desc()).first()
        if prediction and prediction.expires_at > now:
            for i in range(1, 15):
                future_date = now + timedelta(days=i)
                prediction_dates.append(future_date.strftime('%Y-%m-%d'))
            if history_values:
                avg = sum(history_values[-7:]) / min(len(history_values[-7:]), 7)
                prediction_values = [max(0, int(avg * (1 - i * 0.03))) for i in range(1, 15)]
            else:
                prediction_values = [0] * 14

        return {
            'status': 'success',
            'history': {'dates': history_dates, 'values': history_values},
            'prediction': {'dates': prediction_dates, 'values': prediction_values},
        }
