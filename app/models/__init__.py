from app.models.user import User
from app.models.question import Subject, Chapter, Question, UserAnswer
from app.models.game import GameRoom, GamePlayer, GameRecord, GameQuestion
from app.models.points import PointRecord, DailyStats, Leaderboard
from app.models.wrong_question import (WrongQuestion, WrongQuestionCollection, WrongQuestionCollectionItem, 
                                        WrongQuestionNote, ChallengeProgress, ReviewStreak, 
                                        WRONG_REASONS, REVIEW_INTERVALS)
from app.models.system import SystemSetting
from app.models.achievements import RankHistory
from app.models.dictionary import DictionaryCategory, DictionaryItem
from app.models.ranks import RankTier, TierPromotionHistory
from app.models.admin_log import AdminLog
from app.models.announcement import Announcement, AnnouncementRead
from app.models.login_security import LoginAttempt
from app.models.ai_analysis import (LLMProvider, LLMCallStrategy, AIAnalysisResult, AIPredictionResult,
                                     AIGeneratedContent, AILearningStrategy, LLMCallLog,
                                     LLMFallbackEvent, AIAsyncTask,
                                     AIChatSession, AIChatMessage, AIStudyReport, AIStudyPlan,
                                     AIComparisonResult, AIUsageQuota, AIConversation,
                                     AILearningReport, AILearningPlan,
                                     AIBadgeDefinition, AIBadgeRecord)
from app.models.question_feedback import QuestionFeedback
from app.models.notification import UserNotification

__all__ = [
    'User',
    'Subject', 'Chapter', 'Question', 'UserAnswer',
    'GameRoom', 'GamePlayer', 'GameRecord', 'GameQuestion',
    'PointRecord', 'DailyStats', 'Leaderboard',
    'WrongQuestion', 'WrongQuestionCollection', 'WrongQuestionCollectionItem', 'WrongQuestionNote',
    'ChallengeProgress', 'ReviewStreak',
    'SystemSetting', 'WRONG_REASONS', 'REVIEW_INTERVALS',
    'RankHistory',
    'DictionaryCategory', 'DictionaryItem',
    'RankTier', 'TierPromotionHistory',
    'AdminLog', 'Announcement', 'AnnouncementRead',
    'LoginAttempt',
    'LLMProvider', 'LLMCallStrategy', 'AIAnalysisResult', 'AIPredictionResult',
    'AIGeneratedContent', 'AILearningStrategy', 'LLMCallLog',
    'LLMFallbackEvent', 'AIAsyncTask',
    'AIChatSession', 'AIChatMessage', 'AIStudyReport', 'AIStudyPlan',
    'AIComparisonResult', 'AIUsageQuota', 'AIConversation',
    'AILearningReport', 'AILearningPlan',
    'AIBadgeDefinition', 'AIBadgeRecord',
    'QuestionFeedback',
    'UserNotification',
]
