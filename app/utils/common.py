import logging
from datetime import datetime, timedelta, timezone
from app import db, socketio
from app.models import GameRoom, GamePlayer, GameQuestion
from config import BEIJING_TZ

logger = logging.getLogger(__name__)


def make_aware(dt):
    if dt is not None and dt.tzinfo is None:
        return dt.replace(tzinfo=BEIJING_TZ)
    return dt


def clean_expired_rooms():
    _clean_waiting_rooms()
    _clean_playing_rooms()
    _clean_finished_rooms()


def _clean_waiting_rooms():
    expired_rooms = GameRoom.query.filter(
        GameRoom.status == 'waiting',
        GameRoom.expires_at <= datetime.now(timezone.utc)
    ).all()
    
    if not expired_rooms:
        return
    
    for room in expired_rooms:
        players = list(room.players)
        for player in players:
            db.session.delete(player)
        
        questions = list(GameQuestion.query.filter_by(room_id=room.id).all())
        for gq in questions:
            db.session.delete(gq)
        
        socketio.emit('room_removed', {'room_code': room.room_code})
        db.session.delete(room)
    
    db.session.commit()
    logger.info(f'已清理 {len(expired_rooms)} 个过期等待中的房间')


def _clean_playing_rooms():
    from flask import current_app
    from app.models import SystemSetting
    
    # 游戏最大时长（用于强制结束超时游戏）
    max_game_minutes = current_app.config.get('ROOM_EXPIRE_MINUTES', 20) * 2
    
    expired_playing = GameRoom.query.filter(
        GameRoom.status == 'playing',
        GameRoom.started_at.isnot(None),
        GameRoom.started_at <= datetime.now(timezone.utc) - timedelta(minutes=max_game_minutes)
    ).all()
    
    if not expired_playing:
        return
    
    for room in expired_playing:
        try:
            from app.services.game_service import calculate_game_results
            calculate_game_results(room)
            logger.info(f'已强制结束超时进行中房间: {room.room_code}')
        except Exception as e:
            logger.error(f'强制结束房间 {room.room_code} 失败: {e}')
            room.status = 'finished'
            room.ended_at = datetime.now(timezone.utc)
            db.session.commit()
    
    db.session.commit()


def _clean_finished_rooms():
    """清理 7 天前的已结束房间，防止数据库膨胀"""
    cutoff = datetime.now(timezone.utc) - timedelta(days=7)
    
    finished_rooms = GameRoom.query.filter(
        GameRoom.status == 'finished',
        GameRoom.ended_at <= cutoff
    ).all()
    
    if not finished_rooms:
        return
    
    room_count = len(finished_rooms)
    
    for room in finished_rooms:
        players = list(room.players)
        for player in players:
            db.session.delete(player)
        
        questions = list(GameQuestion.query.filter_by(room_id=room.id).all())
        for gq in questions:
            db.session.delete(gq)
        
        records = list(room.records)
        for record in records:
            db.session.delete(record)
        
        db.session.delete(room)
    
    db.session.commit()
    logger.info(f'已清理 {room_count} 个过期的已结束房间（7天前）')


def allowed_file(filename, allowed_extensions):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in allowed_extensions


AVATAR_ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
IMAGE_ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
QUESTION_FILE_EXTENSIONS = {'xlsx', 'xls', 'csv', 'json'}


def allowed_avatar_file(filename):
    return allowed_file(filename, AVATAR_ALLOWED_EXTENSIONS)


def allowed_image_file(filename):
    return allowed_file(filename, IMAGE_ALLOWED_EXTENSIONS)


def allowed_question_file(filename):
    return allowed_file(filename, QUESTION_FILE_EXTENSIONS)


DEFAULT_SUBJECTS_DATA = [
    ('语文', 'bi-translate'),
    ('数学', 'bi-calculator'),
    ('英语', 'bi-spell-check'),
    ('物理', 'bi-lightning'),
    ('化学', 'bi-droplet'),
    ('生物', 'bi-tree'),
    ('政治', 'bi-bank'),
    ('历史', 'bi-clock-history'),
    ('地理', 'bi-globe')
]
