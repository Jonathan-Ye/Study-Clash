import random
import string
import logging
from flask import current_app
from app import db
from app.models import (GameRoom, GamePlayer, GameRecord, GameQuestion,
                        Question, UserAnswer, WrongQuestion, DailyStats)
from app.utils.leaderboard_service import invalidate_leaderboard_cache

logger = logging.getLogger(__name__)


def _get_all_child_chapter_ids(chapter_id):
    """获取章节及其所有子章节的ID列表"""
    from app.models import Chapter
    
    chapter_ids = set()
    to_process = [chapter_id]
    
    while to_process:
        current_id = to_process.pop()
        chapter_ids.add(current_id)
        
        children = Chapter.query.filter_by(parent_id=current_id, is_active=True).all()
        for child in children:
            to_process.append(child.id)
    
    return list(chapter_ids)


def generate_room_code():
    for _ in range(10):
        code = ''.join([str(random.randint(0, 9)) for _ in range(6)])
        if not GameRoom.query.filter_by(room_code=code).first():
            return code
    return ''.join([str(random.randint(0, 9)) for _ in range(6)])


def get_random_questions(subject_id=None, chapter_id=None, count=None, difficulty=None, user_major=None):
    from sqlalchemy import func
    from app.models import Subject
    
    query = Question.query.filter_by(is_active=True)
    
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
        chapter_ids = _get_all_child_chapter_ids(chapter_id)
        query = query.filter(Question.chapter_id.in_(chapter_ids))
    if difficulty:
        query = query.filter_by(difficulty=difficulty)
    
    # 先获取总数
    total_count = query.with_entities(func.count(Question.id)).scalar()
    if total_count == 0:
        return []
    
    # 如果题目数量少于或等于需要的数量，直接返回所有题目（只取ID避免加载大字段）
    if count is None or total_count <= count:
        question_ids = query.with_entities(Question.id).all()
        ids = [q[0] for q in question_ids]
        random.shuffle(ids)
        # 按需分批加载，避免一次性加载大量数据
        batch_size = 100
        questions = []
        for i in range(0, len(ids), batch_size):
            batch_ids = ids[i:i+batch_size]
            questions.extend(Question.query.filter(Question.id.in_(batch_ids)).all())
        return questions
    
    # 使用 ID 范围随机抽样（比 ORDER BY RANDOM() 快 10-100 倍）
    min_max = query.with_entities(func.min(Question.id), func.max(Question.id)).first()
    min_id, max_id = min_max
    
    if max_id is None or min_id is None:
        return []
    
    # 生成随机 ID 集合
    id_range = max_id - min_id + 1
    needed = min(count * 3, id_range)  # 多取一些，过滤掉不匹配的
    random_ids = set()
    attempts = 0
    while len(random_ids) < count and attempts < count * 10:
        rid = random.randint(min_id, max_id)
        random_ids.add(rid)
        attempts += 1
    
    # 用 IN 查询（走主键索引，极快）
    questions = Question.query.filter(
        Question.id.in_(list(random_ids)),
        Question.is_active == True
    ).all()
    
    # 如果过滤后不够，补充随机取
    if len(questions) < count:
        extra = query.filter(
            ~Question.id.in_([q.id for q in questions])
        ).order_by(func.random()).limit(count - len(questions)).all()
        questions.extend(extra)
    
    random.shuffle(questions)
    return questions[:count]


def calculate_game_results(room):
    if room.status == 'finished':
        logger.debug(f'房间 {room.room_code} 已经结束过，直接返回已有结果')
        records = GameRecord.query.filter_by(room_id=room.id).order_by(GameRecord.rank).all()
        results = [{
            'user_id': r.user_id,
            'username': r.user.username,
            'nickname': r.user.nickname or r.user.username,
            'score': r.score,
            'correct_count': r.correct_count,
            'wrong_count': r.wrong_count,
            'total_time': r.total_time,
            'rank': r.rank,
            'points_earned': r.points_earned
        } for r in records]
        return {'status': 'finished', 'results': results}
    
    logger.debug(f'开始计算房间 {room.room_code} 的结果')
    players = GamePlayer.query.filter_by(room_id=room.id).all()
    logger.debug(f'游戏结果计算 - 房间: {room.room_code}, 游戏类型: {room.game_type}, 玩家数量: {len(players)}')
    players = sorted(players, key=lambda p: (-(p.score or 0), p.total_time or 0))
    points_config = current_app.config.get('POINTS_CONFIG', {})
    
    results = []
    
    for i, player in enumerate(players):
        rank = i + 1
        
        points_earned = 0
        reason = ''
        
        logger.debug(f'处理玩家 {player.user_id}, 判断 game_type = \'{room.game_type}\'')
        
        if room.game_type == 'single':
            points_earned = (player.correct_count or 0) * points_config.get('single_correct', 1)
            reason = 'single_correct'
        elif room.game_type == 'battle':
            if rank == 1:
                points_earned = points_config.get('battle_win', 10)
                reason = 'battle_win'
        elif room.game_type == 'four':
            if rank == 1:
                points_earned = points_config.get('four_first', 30)
                reason = 'four_first'
            elif rank == 2:
                points_earned = points_config.get('four_second', 20)
                reason = 'four_second'
            elif rank == 3:
                points_earned = points_config.get('four_third', 10)
                reason = 'four_third'
            elif rank == 4:
                points_earned = points_config.get('four_fourth', 5)
                reason = 'four_fourth'
        else:
            logger.warning(f'game_type \'{room.game_type}\' 不匹配任何分支')
        
        logger.debug(f'玩家 {player.user_id} 最终获得积分: {points_earned}, 原因: {reason}')
        
        record = GameRecord()
        record.user_id = player.user_id
        record.room_id = room.id
        record.game_type = room.game_type
        record.subject_id = room.subject_id
        record.score = player.score
        record.correct_count = player.correct_count
        record.wrong_count = player.wrong_count
        record.total_time = player.total_time
        record.rank = rank
        record.points_earned = points_earned
        
        db.session.add(record)
        
        if points_earned > 0:
            player.user.add_points(points_earned, reason)
        
        stats = DailyStats.get_or_create(player.user_id)
        stats.update_game(won=(rank == 1))
        if stats.points_earned is None:
            stats.points_earned = 0
        stats.points_earned += points_earned
        
        results.append({
            'user_id': player.user_id,
            'username': player.user.username,
            'nickname': player.user.nickname or player.user.username,
            'score': player.score,
            'correct_count': player.correct_count,
            'wrong_count': player.wrong_count,
            'total_time': player.total_time,
            'rank': rank,
            'points_earned': points_earned
        })
    
    room.end_game()
    db.session.commit()
    
    invalidate_leaderboard_cache()
    
    return {
        'status': 'finished',
        'results': results
    }


def process_answer_submission(room, question, player, answer, time_spent):
    try:
        # 初始化可能为None的字段
        if player.score is None:
            player.score = 0
        if player.correct_count is None:
            player.correct_count = 0
        if player.wrong_count is None:
            player.wrong_count = 0
        if player.total_time is None:
            player.total_time = 0
        if player.current_question_index is None:
            player.current_question_index = 0
        if player.wrong_chances_used is None:
            player.wrong_chances_used = 0
        if player.game_over is None:
            player.game_over = False
        
        is_correct = question.check_answer(answer)
        
        user_answer = UserAnswer()
        user_answer.user_id = player.user_id
        user_answer.question_id = question.id
        user_answer.user_answer = answer
        user_answer.is_correct = is_correct
        user_answer.time_spent = time_spent
        user_answer.game_type = room.game_type
        user_answer.game_id = room.id
        
        db.session.add(user_answer)
        
        if is_correct:
            player.score += (question.points or 10)
            player.correct_count += 1
        else:
            player.wrong_count += 1
            
            if room.game_type == 'single':
                player.wrong_chances_used += 1
                max_wrong_chances = current_app.config.get('SINGLE_CHALLENGE_WRONG_CHANCES', 3)
                if player.wrong_chances_used >= max_wrong_chances:
                    player.game_over = True
            
            wrong = WrongQuestion.query.filter_by(
                user_id=player.user_id, 
                question_id=question.id
            ).first()
            if wrong:
                wrong.add_wrong(answer, room.game_type)
            else:
                wrong = WrongQuestion(
                    user_id=player.user_id, 
                    question_id=question.id, 
                    wrong_answer=answer, 
                    game_type=room.game_type
                )
                wrong.calculate_next_review()
                db.session.add(wrong)
        
        player.total_time += time_spent
        player.current_question_index += 1
        
        stats = DailyStats.get_or_create(player.user_id)
        stats.update_answer(is_correct, time_spent)
        
        response = {
            'is_correct': is_correct,
            'correct_answer': question.correct_answer,
            'analysis': question.analysis,
            'current_score': player.score,
            'correct_count': player.correct_count,
            'wrong_count': player.wrong_count
        }
        
        if room.game_type == 'single':
            max_wrong_chances = current_app.config.get('SINGLE_CHALLENGE_WRONG_CHANCES', 3)
            response['wrong_chances_used'] = player.wrong_chances_used
            response['max_wrong_chances'] = max_wrong_chances
            response['remaining_chances'] = max_wrong_chances - player.wrong_chances_used
            response['game_over'] = player.game_over
        
        return response
    except Exception as e:
        import traceback
        current_app.logger.error(f'process_answer_submission 错误: {traceback.format_exc()}')
        raise
