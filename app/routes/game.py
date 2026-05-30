import logging
from datetime import datetime, timezone, timedelta
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, current_app
from flask_login import login_required, current_user
from sqlalchemy.orm import joinedload
from app import db, socketio, api_login_required
from app.models import (Question, Subject, Chapter, GameRoom, GamePlayer,
                        GameRecord, GameQuestion, UserAnswer)
from app.models.game import _make_aware_utc
from app.utils.common import clean_expired_rooms
from app.services.game_service import (
    generate_room_code,
    get_random_questions,
    calculate_game_results as calc_results,
    process_answer_submission
)
from config import BEIJING_TZ

logger = logging.getLogger(__name__)

game_bp = Blueprint('game', __name__)

@game_bp.route('/')
@login_required
def index():
    from app.models import SystemSetting
    from datetime import datetime, timezone, timedelta
    
    subjects = Subject.query.filter_by(is_active=True).all()
    user_major = getattr(current_user, 'major', None)
    filtered_subjects = [s for s in subjects if s.is_applicable_for_major(user_major)]
    active_game = GamePlayer.query.filter_by(
        user_id=current_user.id, finished=False
    ).join(GameRoom).filter(
        GameRoom.status == 'playing'
    ).first()
    
    active_game_timeout_minutes = 30  # 默认30分钟
    
    if active_game:
        room = GameRoom.query.get(active_game.room_id)
        active_game_timeout_minutes = int(SystemSetting.get('active_game_timeout', '30'))
        
        # 从房间开始时间计算超时
        if room.started_at:
            timeout_threshold = datetime.now(timezone.utc) - timedelta(minutes=active_game_timeout_minutes)
            
            if _make_aware_utc(room.started_at) < timeout_threshold:
                # 超时了，结束游戏
                try:
                    from app.services.game_service import calculate_game_results
                    calculate_game_results(room)
                    logger.info(f'超时结束游戏: {room.room_code}')
                except Exception as e:
                    logger.error(f'结束超时游戏失败: {e}')
                    room.status = 'finished'
                    room.ended_at = datetime.now(timezone.utc)
                    db.session.commit()
                
                active_game = None
    
    return render_template('game/index.html', subjects=filtered_subjects, active_game=active_game, active_game_timeout_minutes=active_game_timeout_minutes)

@game_bp.route('/api/active-game')
@login_required
def api_active_game():
    """返回当前用户进行中的游戏信息，用于掉线重连"""
    from app.models import SystemSetting
    from datetime import datetime, timezone, timedelta
    
    active_player = GamePlayer.query.filter_by(
        user_id=current_user.id, finished=False
    ).join(GameRoom).filter(
        GameRoom.status == 'playing'
    ).order_by(GameRoom.started_at.desc()).first()
    
    if active_player:
        room = GameRoom.query.get(active_player.room_id)
        if room:
            timeout_minutes = int(SystemSetting.get('active_game_timeout', '30'))
            
            # 从房间开始时间计算超时
            if room.started_at:
                timeout_threshold = datetime.now(timezone.utc) - timedelta(minutes=timeout_minutes)
                
                if _make_aware_utc(room.started_at) < timeout_threshold:
                    # 超时了，结束游戏
                    try:
                        from app.services.game_service import calculate_game_results
                        calculate_game_results(room)
                        logger.info(f'超时结束游戏: {room.room_code}')
                    except Exception as e:
                        logger.error(f'结束超时游戏失败: {e}')
                        room.status = 'finished'
                        room.ended_at = datetime.now(timezone.utc)
                        db.session.commit()
                    
                    return jsonify({'has_active_game': False})
            
            return jsonify({
                'has_active_game': True,
                'room_code': room.room_code,
                'game_type': room.game_type,
                'timeout_minutes': timeout_minutes,
                'started_at': room.started_at.isoformat() if room.started_at else None
            })
    return jsonify({'has_active_game': False})

@game_bp.route('/api/answered-questions/<room_code>')
@login_required
def api_answered_questions(room_code):
    """返回当前用户在指定房间中已答题目的信息，用于断点续答"""
    room = GameRoom.query.filter_by(room_code=room_code).first_or_404()
    player = GamePlayer.query.filter_by(room_id=room.id, user_id=current_user.id).first()
    if not player:
        return jsonify({'answers': []})
    
    # 获取该玩家在该房间的所有答题记录
    user_answers = UserAnswer.query.filter_by(
        user_id=current_user.id, game_id=room.id
    ).all()
    
    # 获取房间的题目列表（有序）
    game_questions = GameQuestion.query.filter_by(room_id=room.id).order_by(GameQuestion.order).all()
    question_id_to_index = {gq.question_id: gq.order for gq in game_questions}
    question_id_to_correct = {gq.question_id: gq.question.correct_answer for gq in game_questions}
    
    answers = []
    for ua in user_answers:
        q_index = question_id_to_index.get(ua.question_id)
        correct_answer = question_id_to_correct.get(ua.question_id)
        if q_index:
            answers.append({
                'question_index': q_index,
                'user_answer': ua.user_answer,
                'is_correct': ua.is_correct,
                'correct_answer': correct_answer
            })
    
    answers.sort(key=lambda x: x['question_index'])
    return jsonify({'answers': answers})

@game_bp.route('/single', methods=['GET', 'POST'])
@login_required
def single():
    if not current_user.participate_in_games:
        flash('您已关闭游戏功能，无法参与游戏对决', 'warning')
        return redirect(url_for('main.index'))
    
    if request.method == 'POST':
        subject_id = request.form.get('subject_id', type=int)
        chapter_id = request.form.get('chapter_id', type=int)
        
        user_major = getattr(current_user, 'major', None)
        
        from app.services.question_recommendation import get_smart_challenge_questions
        questions = get_smart_challenge_questions(
            current_user.id, subject_id, chapter_id, count=20, user_major=user_major
        )
        
        if not questions:
            if request.headers.get('Accept') == 'application/json' or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({'error': '没有找到符合条件的题目'}), 400
            flash('没有找到符合条件的题目', 'error')
            return redirect(url_for('game.single'))
        
        room = GameRoom()
        room.room_code = generate_room_code()
        room.game_type = 'single'
        room.subject_id = subject_id
        room.chapter_id = chapter_id
        room.max_players = 1
        room.question_count = len(questions)
        room.created_by = current_user.id
        
        db.session.add(room)
        db.session.commit()
        
        for i, q in enumerate(questions):
            gq = GameQuestion(room_id=room.id, question_id=q.id, order=i+1)
            db.session.add(gq)
        
        player = GamePlayer(room_id=room.id, user_id=current_user.id)
        db.session.add(player)
        room.current_players = 1
        room.status = 'playing'
        room.started_at = datetime.now(timezone.utc)
        db.session.commit()
        
        if request.headers.get('Accept') == 'application/json' or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'room_code': room.room_code})
        
        return redirect(url_for('game.play', room_code=room.room_code))
    
    subjects = Subject.query.filter_by(is_active=True).all()
    user_major = getattr(current_user, 'major', None)
    filtered_subjects = [s for s in subjects if s.is_applicable_for_major(user_major)]
    single_wrong_chances = current_app.config.get('SINGLE_CHALLENGE_WRONG_CHANCES', 3)
    return render_template('game/single.html', subjects=filtered_subjects, single_wrong_chances=single_wrong_chances)

@game_bp.route('/battle')
@login_required
def battle():
    subjects = Subject.query.filter_by(is_active=True).all()
    user_major = getattr(current_user, 'major', None)
    filtered_subjects = [s for s in subjects if s.is_applicable_for_major(user_major)]
    return render_template('game/battle.html', subjects=filtered_subjects)

@game_bp.route('/four')
@login_required
def four():
    subjects = Subject.query.filter_by(is_active=True).all()
    user_major = getattr(current_user, 'major', None)
    filtered_subjects = [s for s in subjects if s.is_applicable_for_major(user_major)]
    return render_template('game/four.html', subjects=filtered_subjects)

@game_bp.route('/api/rooms/<game_type>')
@login_required
def api_rooms(game_type):
    clean_expired_rooms()
    
    # 获取房间（不使用expires_at过滤，因为有时区问题）
    rooms = GameRoom.query.filter(
        GameRoom.status == 'waiting',
        GameRoom.game_type == game_type
    ).all()
    
    # 在Python层面过滤过期房间
    rooms = [r for r in rooms if not r.is_expired()]
    
    rooms_data = []
    for room in rooms:
        chapter_name = '综合'
        if room.chapter:
            chapter_name = room.chapter.get_full_path()
        elif room.subject:
            chapter_name = room.subject.name + ' - 综合'
        
        rooms_data.append({
            'room_code': room.room_code,
            'subject_name': room.subject.name if room.subject else '综合',
            'chapter_name': chapter_name,
            'current_players': room.current_players,
            'max_players': room.max_players,
            'created_at': room.created_at.strftime('%Y-%m-%d %H:%M'),
            'remaining_seconds': room.get_remaining_seconds()
        })
    
    return jsonify({'rooms': rooms_data})


@game_bp.route('/create-room', methods=['POST'])
@login_required
def create_room():
    if not current_user.participate_in_games:
        return jsonify({'error': '您已关闭游戏功能'}), 403
    
    game_type = request.form.get('game_type')
    subject_id = request.form.get('subject_id', type=int)
    chapter_id = request.form.get('chapter_id', type=int)
    difficulty = request.form.get('difficulty', type=int)
    question_count = request.form.get('question_count', 10, type=int)
    
    user_major = getattr(current_user, 'major', None)
    max_players = 2 if game_type == 'battle' else 4
    
    from app.services.question_recommendation import get_smart_challenge_questions
    questions = get_smart_challenge_questions(
        current_user.id, subject_id, chapter_id, question_count, difficulty, user_major
    )
    
    if not questions:
        return jsonify({'error': '没有找到符合条件的题目'}), 400
    
    room = GameRoom()
    room.room_code = generate_room_code()
    room.game_type = game_type
    room.subject_id = subject_id
    room.chapter_id = chapter_id
    room.max_players = max_players
    room.question_count = len(questions)
    room.created_by = current_user.id
    
    db.session.add(room)
    db.session.commit()
    
    for i, q in enumerate(questions):
        gq = GameQuestion(room_id=room.id, question_id=q.id, order=i+1)
        db.session.add(gq)
    
    player = GamePlayer(room_id=room.id, user_id=current_user.id, is_ready=True)
    db.session.add(player)
    room.current_players = 1
    db.session.commit()
    
    from app.utils.system_logger import SystemLogger
    subject_name = room.subject.name if room.subject else '综合'
    SystemLogger.info(f'创建游戏房间 | room={room.room_code} | type={game_type} | subject={subject_name}',
                     category='game', user={'id': current_user.id, 'username': current_user.username})
    
    socketio.emit('room_created', {
        'room': {
            'room_code': room.room_code,
            'subject_name': room.subject.name if room.subject else '综合',
            'current_players': room.current_players,
            'max_players': room.max_players,
            'remaining_seconds': room.get_remaining_seconds()
        }
    })
    
    return jsonify({
        'room_code': room.room_code,
        'room_id': room.id
    })

@game_bp.route('/join-room', methods=['POST'])
@login_required
def join_room():
    if not current_user.participate_in_games:
        return jsonify({'error': '您已关闭游戏功能'}), 403
    
    room_code = request.form.get('room_code')
    room = GameRoom.query.filter_by(room_code=room_code).first()
    
    if not room:
        return jsonify({'error': '房间不存在'}), 404
    
    if room.is_expired():
        return jsonify({'error': '房间已过期'}), 400
    
    if room.status != 'waiting':
        return jsonify({'error': '游戏已经开始或结束'}), 400
    
    if room.is_full():
        return jsonify({'error': '房间已满'}), 400
    
    existing_player = GamePlayer.query.filter_by(room_id=room.id, user_id=current_user.id).first()
    if existing_player:
        return jsonify({'room_code': room.room_code, 'room_id': room.id})
    
    player = GamePlayer(room_id=room.id, user_id=current_user.id)
    db.session.add(player)
    if room.current_players is None:
        room.current_players = 0
    room.current_players += 1
    db.session.commit()
    
    from app.utils.system_logger import SystemLogger
    SystemLogger.info(f'玩家加入房间 | room={room.room_code} | players={room.current_players}/{room.max_players}',
                     category='game', user={'id': current_user.id, 'username': current_user.username})
    
    socketio.emit('room_updated', {
        'room': {
            'room_code': room.room_code,
            'current_players': room.current_players,
            'max_players': room.max_players
        }
    })
    
    return jsonify({
        'room_code': room.room_code,
        'room_id': room.id
    })

@game_bp.route('/room/<room_code>')
@login_required
def room(room_code):
    room = GameRoom.query.filter_by(room_code=room_code).first_or_404()
    player = GamePlayer.query.filter_by(room_id=room.id, user_id=current_user.id).first()
    
    if not player:
        flash('您不在该房间中', 'error')
        return redirect(url_for('game.index'))
    
    if room.status == 'finished':
        return redirect(url_for('game.results', room_code=room_code))
    
    if room.status == 'playing':
        return redirect(url_for('game.play', room_code=room_code))
    
    players = GamePlayer.query.filter_by(room_id=room.id).all()
    
    return render_template('game/room.html', room=room, players=players)

@game_bp.route('/play/<room_code>')
@login_required
def play(room_code):
    room = GameRoom.query.filter_by(room_code=room_code).first_or_404()
    player = GamePlayer.query.filter_by(room_id=room.id, user_id=current_user.id).first()
    
    if not player:
        flash('您不在该房间中', 'error')
        return redirect(url_for('game.index'))
    
    if room.status == 'finished':
        return redirect(url_for('game.results', room_code=room_code))
    
    if room.status == 'waiting':
        return redirect(url_for('game.room', room_code=room_code))
    
    # 如果玩家已完成但房间还在进行中（等待其他人），显示等待页
    if player.finished:
        game_questions = GameQuestion.query.filter_by(room_id=room.id).order_by(GameQuestion.order).all()
        question_ids = [gq.question_id for gq in game_questions]
        questions = Question.query.filter(Question.id.in_(question_ids)).all()
        # 按原顺序排列
        questions.sort(key=lambda q: question_ids.index(q.id))
        single_wrong_chances = current_app.config.get('SINGLE_CHALLENGE_WRONG_CHANCES', 3)
        resume_data = {
            'current_question_index': len(questions) + 1,  # 超出范围，触发完成状态
            'score': player.score or 0,
            'correct_count': player.correct_count or 0,
            'wrong_count': player.wrong_count or 0,
            'total_time': player.total_time or 0,
        }
        return render_template('game/play.html', room=room, questions=questions,
                              player=player, single_wrong_chances=single_wrong_chances,
                              resume_data=resume_data)
    
    game_questions = GameQuestion.query.filter_by(room_id=room.id).order_by(GameQuestion.order).all()
    question_ids = [gq.question_id for gq in game_questions]
    questions = Question.query.filter(Question.id.in_(question_ids)).all()
    # 按原顺序排列
    questions.sort(key=lambda q: question_ids.index(q.id))
    
    single_wrong_chances = current_app.config.get('SINGLE_CHALLENGE_WRONG_CHANCES', 3)
    
    # 断点续答：基于已答题记录数恢复进度
    # 优先使用 answered_count，确保网络异常时用户回到正确的题目
    answered_count = UserAnswer.query.filter_by(
        user_id=current_user.id, game_id=room.id
    ).count()
    current_q_index = answered_count + 1
    
    resume_data = {
        'current_question_index': current_q_index,
        'score': player.score or 0,
        'correct_count': player.correct_count or 0,
        'wrong_count': player.wrong_count or 0,
        'total_time': player.total_time or 0,
    }
    
    return render_template('game/play.html', room=room, questions=questions, 
                          player=player, single_wrong_chances=single_wrong_chances,
                          resume_data=resume_data)

@game_bp.route('/submit-answer', methods=['POST'])
@api_login_required
def submit_answer():
    room_id = None
    question_id = None
    answer = None
    try:
        data = request.get_json()
        room_id = data.get('room_id')
        question_id = data.get('question_id')
        answer = data.get('answer')
        time_spent = data.get('time_spent', 0)
        
        room = GameRoom.query.get(room_id)
        question = Question.query.get(question_id)
        player = GamePlayer.query.filter_by(room_id=room_id, user_id=current_user.id).first()
        
        if not room or not question or not player:
            return jsonify({'error': '无效请求'}), 400
        
        if player.game_over:
            return jsonify({'error': '游戏已结束', 'game_over': True}), 400
        
        game_question = GameQuestion.query.filter_by(
            room_id=room.id, question_id=question.id
        ).first()
        if not game_question:
            return jsonify({'error': '该题目不属于当前游戏'}), 400
        
        # 检查是否已作答（支持网络异常后的重复提交，返回之前的结果）
        existing_answer = UserAnswer.query.filter_by(
            user_id=current_user.id, question_id=question.id, game_id=room.id
        ).first()
        if existing_answer:
            # 网络异常后重新提交，返回之前保存的结果
            return jsonify({
                'is_correct': existing_answer.is_correct,
                'correct_answer': question.correct_answer,
                'analysis': question.analysis,
                'current_score': player.score or 0,
                'correct_count': player.correct_count or 0,
                'wrong_count': player.wrong_count or 0,
                'already_answered': True
            })
        
        response = process_answer_submission(room, question, player, answer, time_spent)
        db.session.commit()
        
        return jsonify(response)
    except Exception as e:
        db.session.rollback()
        import traceback
        error_detail = traceback.format_exc()
        current_app.logger.error(f'提交答案异常: {error_detail}')
        current_app.logger.error(f'请求数据: room_id={room_id}, question_id={question_id}, answer={answer}')
        return jsonify({'error': f'服务器错误: {str(e)}'}), 500

@game_bp.route('/finish-game/<room_code>', methods=['POST'])
@login_required
def finish_game(room_code):
    room = GameRoom.query.filter_by(room_code=room_code).first_or_404()
    player = GamePlayer.query.filter_by(room_id=room.id, user_id=current_user.id).first()
    
    if not player:
        return jsonify({'error': '无效请求'}), 400
    
    if room.status == 'finished':
        result = calc_results(room)
        return jsonify(result)
    
    if room.game_type == 'single' and player.game_over:
        player.finished = True
        player.finished_at = datetime.now(timezone.utc)
        db.session.commit()
        result = calc_results(room)
        return jsonify(result)
    
    if not player.finished:
        player.finished = True
        player.finished_at = datetime.now(timezone.utc)
        db.session.commit()
    
    db.session.refresh(room)
    players = GamePlayer.query.filter_by(room_id=room.id).all()
    all_finished = all(p.finished for p in players)
    
    if all_finished or room.game_type == 'single':
        result = calc_results(room)

        from app.utils.system_logger import SystemLogger
        SystemLogger.info(f'游戏结束 | room={room.room_code} | type={room.game_type} | players={room.current_players}',
                         category='game', user={'id': current_user.id, 'username': current_user.username})

        return jsonify(result)
    
    return jsonify({'status': 'waiting', 'message': '等待其他玩家完成'})

@game_bp.route('/results/<room_code>')
@login_required
def results(room_code):
    room = GameRoom.query.filter_by(room_code=room_code).first_or_404()
    records = GameRecord.query.filter_by(room_id=room.id).order_by(GameRecord.rank).all()
    
    return render_template('game/results.html', room=room, records=records)

@game_bp.route('/history')
@login_required
def history():
    page = request.args.get('page', 1, type=int)
    records = GameRecord.query.filter_by(user_id=current_user.id)\
        .order_by(GameRecord.created_at.desc()).paginate(page=page, per_page=10)
    
    return render_template('game/history.html', records=records)


@game_bp.route('/rematch/<room_code>', methods=['POST'])
@login_required
def rematch(room_code):
    """再来一局：单人模式直接开始新局；对战模式由 Socket.IO 邀约流程处理"""
    old_room = GameRoom.query.filter_by(room_code=room_code).first_or_404()
    
    if old_room.game_type == 'single':
        from app.services.question_recommendation import get_smart_challenge_questions
        user_major = getattr(current_user, 'major', None)
        questions = get_smart_challenge_questions(
            current_user.id, old_room.subject_id, old_room.chapter_id, old_room.question_count, user_major=user_major
        )
        if not questions:
            return jsonify({'error': '没有找到符合条件的题目'}), 400
        
        room = GameRoom()
        room.room_code = generate_room_code()
        room.game_type = 'single'
        room.subject_id = old_room.subject_id
        room.chapter_id = old_room.chapter_id
        room.max_players = 1
        room.question_count = len(questions)
        room.created_by = current_user.id
        db.session.add(room)
        db.session.commit()
        
        for i, q in enumerate(questions):
            gq = GameQuestion(room_id=room.id, question_id=q.id, order=i+1)
            db.session.add(gq)
        
        player = GamePlayer(room_id=room.id, user_id=current_user.id)
        db.session.add(player)
        room.current_players = 1
        room.status = 'playing'
        room.started_at = datetime.now(timezone.utc)
        db.session.commit()
        
        return jsonify({'room_code': room.room_code, 'game_type': 'single'})
    
    else:
        # 对战模式：由前端通过 Socket.IO 发起邀约，此处仅返回提示
        return jsonify({'use_socket': True, 'message': '邀约已通过实时通信发出'})


@game_bp.route('/change-opponent/<room_code>', methods=['POST'])
@login_required
def change_opponent(room_code):
    """换个对手：用相同参数创建新等待房间，跳转到等待页"""
    old_room = GameRoom.query.filter_by(room_code=room_code).first_or_404()
    
    if old_room.game_type == 'single':
        return jsonify({'error': '单人模式不支持换对手'}), 400
    
    from app.services.question_recommendation import get_smart_challenge_questions
    user_major = getattr(current_user, 'major', None)
    questions = get_smart_challenge_questions(
        current_user.id, old_room.subject_id, old_room.chapter_id, old_room.question_count, user_major=user_major
    )
    if not questions:
        return jsonify({'error': '没有找到符合条件的题目'}), 400
    
    room = GameRoom()
    room.room_code = generate_room_code()
    room.game_type = old_room.game_type
    room.subject_id = old_room.subject_id
    room.chapter_id = old_room.chapter_id
    room.max_players = old_room.max_players
    room.question_count = len(questions)
    room.created_by = current_user.id
    db.session.add(room)
    db.session.commit()
    
    for i, q in enumerate(questions):
        gq = GameQuestion(room_id=room.id, question_id=q.id, order=i+1)
        db.session.add(gq)
    
    player = GamePlayer(room_id=room.id, user_id=current_user.id, is_ready=True)
    db.session.add(player)
    room.current_players = 1
    db.session.commit()
    
    socketio.emit('room_created', {
        'room': {
            'room_code': room.room_code,
            'subject_name': room.subject.name if room.subject else '综合',
            'current_players': room.current_players,
            'max_players': room.max_players,
            'remaining_seconds': room.get_remaining_seconds()
        }
    })
    
    return jsonify({'room_code': room.room_code, 'game_type': old_room.game_type})
