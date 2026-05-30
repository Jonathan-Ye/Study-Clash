from datetime import datetime, timedelta, timezone
from flask import request, current_app
from flask_login import current_user
from flask_socketio import emit, join_room, leave_room
from app import socketio, db
from app.models import GameRoom, GamePlayer, GameQuestion, User
from app.models.game import RematchInvitation
from app.utils.common import clean_expired_rooms as clean_expired_rooms_socket
from config import BEIJING_TZ
import json

# 在线用户追踪: {user_id: {'sids': set(session_ids), 'user_info': dict}}
online_users = {}

def _get_authenticated_user():
    """从Flask-Login获取已认证用户，未登录返回None"""
    if current_user.is_authenticated:
        return current_user
    return None

def _cache_user_info(user):
    """缓存用户信息到字典中，避免依赖current_user"""
    return {
        'id': user.id,
        'username': user.username,
        'nickname': user.nickname or user.username,
        'avatar': user.avatar,
        'class_name': user.class_name,
        'participate_in_games': user.participate_in_games
    }

def _get_user_from_cache(user_id):
    """从数据库获取用户信息并更新缓存"""
    user = User.query.get(user_id)
    if user:
        return _cache_user_info(user)
    return None

@socketio.on('connect')
def handle_connect():
    if not current_user.is_authenticated:
        return False
    
    user_id = current_user.id
    sid = request.sid
    
    join_room(f'user_{user_id}')
    
    # 初始化或更新在线用户记录
    if user_id not in online_users:
        online_users[user_id] = {
            'sids': set(),
            'user_info': _cache_user_info(current_user)
        }
    online_users[user_id]['sids'].add(sid)
    
    # 广播上线通知
    emit('user_online_status', {
        'user_id': user_id,
        'status': 'online'
    }, broadcast=True, include_self=False)

@socketio.on('disconnect')
def handle_disconnect():
    if not current_user.is_authenticated:
        return
    
    user_id = current_user.id
    sid = request.sid
    
    if user_id in online_users:
        online_users[user_id]['sids'].discard(sid)
        
        # 如果该用户所有连接都断开，才移除
        if len(online_users[user_id]['sids']) == 0:
            del online_users[user_id]
            # 广播下线通知
            emit('user_online_status', {
                'user_id': user_id,
                'status': 'offline'
            }, broadcast=True, include_self=False)

@socketio.on('get_rooms')
def on_get_rooms(data):
    game_type = data.get('game_type')
    
    # 清理所有过期房间
    clean_expired_rooms_socket()
    
    # 获取房间（不使用expires_at过滤，因为有时区问题）
    rooms = GameRoom.query.filter_by(
        status='waiting',
        game_type=game_type
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
    
    emit('rooms_list', {'rooms': rooms_data})

@socketio.on('join_game')
def on_join_game(data):
    user = _get_authenticated_user()
    if not user:
        emit('error', {'message': '请先登录'})
        return
    
    if not user.participate_in_games:
        emit('error', {'message': '您已关闭游戏功能'})
        return
    
    room_code = data.get('room_code')
    user_id = user.id
    
    room = GameRoom.query.filter_by(room_code=room_code).first()
    if not room:
        emit('error', {'message': '房间不存在'})
        return
    
    if room.is_expired():
        emit('error', {'message': '房间已过期'})
        return
    
    join_room(room_code)
    
    from app.utils.system_logger import SystemLogger
    SystemLogger.info(f'SocketIO 加入游戏房间 | room={room_code}', category='game',
                     user={'id': user_id, 'username': user.username})

    players = GamePlayer.query.filter_by(room_id=room.id).all()
    players_data = [{
        'user_id': p.user_id,
        'username': p.user.username,
        'nickname': p.user.nickname or p.user.username,
        'avatar_url': p.user.get_avatar_url(),
        'is_ready': p.is_ready,
        'score': p.score
    } for p in players]
    
    emit('player_joined', {
        'user_id': user_id,
        'players': players_data,
        'current_players': room.current_players,
        'max_players': room.max_players
    }, room=room_code)

@socketio.on('leave_game')
def on_leave_game(data):
    user = _get_authenticated_user()
    if not user:
        return
    
    room_code = data.get('room_code')
    user_id = user.id
    
    room = GameRoom.query.filter_by(room_code=room_code).first()
    if room and room.status == 'waiting':
        player = GamePlayer.query.filter_by(room_id=room.id, user_id=user_id).first()
        if player:
            db.session.delete(player)
            if room.current_players is None:
                room.current_players = 0
            room.current_players -= 1
            
            if room.current_players <= 0:
                room.current_players = 0
            
            db.session.commit()
            
            leave_room(room_code)
            
            emit('player_left', {
                'user_id': user_id,
                'current_players': room.current_players
            }, room=room_code)
            
            if room.current_players <= 0:
                from app.utils.system_logger import SystemLogger
                SystemLogger.info(f'房间无人，自动清理 | room={room_code}', category='game')
                emit('room_removed', {
                    'room_code': room_code
                }, broadcast=True)

@socketio.on('player_ready')
def on_player_ready(data):
    user = _get_authenticated_user()
    if not user:
        return
    
    room_code = data.get('room_code')
    user_id = user.id
    
    room = GameRoom.query.filter_by(room_code=room_code).first()
    if room and room.status == 'waiting':
        player = GamePlayer.query.filter_by(room_id=room.id, user_id=user_id).first()
        if player:
            player.is_ready = not player.is_ready
            db.session.commit()
            
            emit('player_ready_status', {
                'user_id': user_id,
                'is_ready': player.is_ready
            }, room=room_code)
            
            all_ready = all(p.is_ready for p in room.players)
            is_full = (room.current_players or 0) == (room.max_players or 0)
            
            if all_ready and is_full:
                room.start_game()
                db.session.commit()
                
                emit('game_started', {
                    'room_code': room_code,
                    'start_time': datetime.now(timezone.utc).isoformat()
                }, room=room_code)

@socketio.on('start_game')
def on_start_game(data):
    user = _get_authenticated_user()
    if not user:
        return
    
    room_code = data.get('room_code')
    
    room = GameRoom.query.filter_by(room_code=room_code).first()
    if room:
        all_ready = all(p.is_ready for p in room.players)
        if all_ready or room.game_type == 'single':
            room.start_game()
            db.session.commit()
            
            emit('game_started', {
                'room_code': room_code,
                'start_time': datetime.now(timezone.utc).isoformat()
            }, room=room_code)

@socketio.on('submit_answer')
def on_submit_answer(data):
    user = _get_authenticated_user()
    if not user:
        return
    
    room_code = data.get('room_code')
    user_id = user.id
    username = user.username
    question_index = data.get('question_index')
    is_correct = data.get('is_correct')
    score = data.get('score')
    
    emit('player_answered', {
        'user_id': user_id,
        'username': username,
        'question_index': question_index,
        'is_correct': is_correct,
        'score': score
    }, room=room_code)

@socketio.on('player_finished')
def on_player_finished(data):
    user = _get_authenticated_user()
    if not user:
        return
    
    room_code = data.get('room_code')
    user_id = user.id
    
    room = GameRoom.query.filter_by(room_code=room_code).first()
    if room:
        player = GamePlayer.query.filter_by(room_id=room.id, user_id=user_id).first()
        if player:
            if not player.finished:
                player.finished = True
                db.session.commit()
            
            db.session.refresh(room)
            players = GamePlayer.query.filter_by(room_id=room.id).all()
            all_finished = all(p.finished for p in players)
            
            emit('player_finished_notification', {
                'user_id': user_id
            }, room=room_code)
            
            if all_finished:
                emit('game_results_ready', {
                    'room_code': room_code
                }, room=room_code)

@socketio.on('next_question')
def on_next_question(data):
    room_code = data.get('room_code')
    question_index = data.get('question_index')
    
    emit('go_to_next_question', {
        'question_index': question_index
    }, room=room_code)

@socketio.on('time_up')
def on_time_up(data):
    room_code = data.get('room_code')
    question_index = data.get('question_index')
    
    emit('question_time_up', {
        'question_index': question_index
    }, room=room_code)

@socketio.on('chat_message')
def on_chat_message(data):
    user = _get_authenticated_user()
    if not user:
        return
    
    room_code = data.get('room_code')
    user_id = user.id
    username = user.username
    message = data.get('message', '').strip()
    
    if not message:
        return
    
    # 对消息进行HTML转义防止XSS
    from markupsafe import escape
    safe_message = str(escape(message))
    
    emit('chat_message', {
        'user_id': user_id,
        'username': username,
        'message': safe_message
    }, room=room_code)


# ========== 再来一局邀约逻辑 ==========
# 使用数据库持久化存储邀约状态（RematchInvitation 模型）


@socketio.on('rematch_request')
def on_rematch_request(data):
    """发起再来一局邀约"""
    user = _get_authenticated_user()
    if not user:
        return
    
    room_code = data.get('room_code')
    user_id = user.id
    nickname = user.nickname or user.username
    
    room = GameRoom.query.filter_by(room_code=room_code).first()
    if not room:
        emit('rematch_error', {'message': '房间不存在'})
        return
    
    # 获取原房间所有玩家
    players = GamePlayer.query.filter_by(room_id=room.id).all()
    all_player_ids = [p.user_id for p in players]
    
    if user_id not in all_player_ids:
        emit('rematch_error', {'message': '你不在此房间中'})
        return
    
    # 如果已有邀约进行中，提示等待
    existing = RematchInvitation.query.filter_by(room_code=room_code).first()
    if existing and not existing.is_expired():
        emit('rematch_error', {'message': '已有再来一局邀约进行中'})
        return
    elif existing:
        # 清理过期邀约
        db.session.delete(existing)
        db.session.commit()
    
    # 创建邀约记录（发起者自动同意）
    invitation = RematchInvitation(
        room_code=room_code,
        requester_id=user_id,
        requester_name=nickname,
        all_player_ids=json.dumps(all_player_ids),
        accepted_ids=json.dumps([user_id]),
        declined_ids=json.dumps([]),
        expires_at=datetime.now(timezone.utc) + timedelta(seconds=15)
    )
    db.session.add(invitation)
    db.session.commit()
    
    # 向房间内所有其他玩家广播邀约
    emit('rematch_invitation', {
        'requester_id': user_id,
        'requester_name': nickname,
        'room_code': room_code,
        'timeout': 15
    }, room=room_code)
    
    # 通知发起者：邀约已发出，等待其他人响应
    emit('rematch_waiting', {
        'room_code': room_code,
        'accepted_count': 1,
        'total_count': len(all_player_ids)
    })


@socketio.on('rematch_accept')
def on_rematch_accept(data):
    """同意再来一局"""
    user = _get_authenticated_user()
    if not user:
        return
    
    room_code = data.get('room_code')
    user_id = user.id
    
    invitation = RematchInvitation.query.filter_by(room_code=room_code).first()
    if not invitation or invitation.is_expired():
        emit('rematch_error', {'message': '没有进行中的邀约'})
        return
    
    all_player_ids = invitation.get_all_player_ids()
    
    if user_id not in all_player_ids:
        emit('rematch_error', {'message': '你不在此房间中'})
        return
    
    if user_id in invitation.get_declined_ids():
        return
    
    invitation.add_accepted(user_id)
    db.session.commit()
    
    accepted = invitation.get_accepted_ids()
    
    # 广播同意状态更新
    emit('rematch_status_update', {
        'room_code': room_code,
        'accepted_count': len(accepted),
        'total_count': len(all_player_ids),
        'last_accepted_id': user_id
    }, room=room_code)
    
    # 检查是否全部同意
    if invitation.is_all_accepted():
        _execute_rematch(room_code)


@socketio.on('rematch_decline')
def on_rematch_decline(data):
    """拒绝再来一局"""
    user = _get_authenticated_user()
    if not user:
        return
    
    room_code = data.get('room_code')
    user_id = user.id
    nickname = user.nickname or user.username
    
    invitation = RematchInvitation.query.filter_by(room_code=room_code).first()
    if not invitation or invitation.is_expired():
        emit('rematch_error', {'message': '没有进行中的邀约'})
        return
    
    invitation.add_declined(user_id)
    db.session.commit()
    
    # 通知所有人：XX 拒绝了再来一局
    emit('rematch_declined', {
        'room_code': room_code,
        'decliner_name': nickname
    }, room=room_code)
    
    # 删除邀约记录
    db.session.delete(invitation)
    db.session.commit()


@socketio.on('rematch_cancel')
def on_rematch_cancel(data):
    """取消再来一局邀约（仅发起人可取消）"""
    user = _get_authenticated_user()
    if not user:
        return
    
    room_code = data.get('room_code')
    user_id = user.id
    
    invitation = RematchInvitation.query.filter_by(room_code=room_code).first()
    if not invitation:
        emit('rematch_error', {'message': '没有进行中的邀约'})
        return
    
    # 只有发起人才能取消
    if invitation.requester_id != user_id:
        emit('rematch_error', {'message': '只有发起人才能取消邀约'})
        return
    
    # 通知所有人：发起人取消了再来一局
    emit('rematch_cancelled', {
        'room_code': room_code,
        'message': '发起人取消了再来一局'
    }, room=room_code)
    
    # 删除邀约记录
    db.session.delete(invitation)
    db.session.commit()


def _execute_rematch(room_code):
    """所有人同意后，创建新房间并通知跳转"""
    from app.services.game_service import generate_room_code, get_random_questions
    from app.models import GameQuestion
    
    invitation = RematchInvitation.query.filter_by(room_code=room_code).first()
    if not invitation:
        return
    
    all_player_ids = invitation.get_all_player_ids()
    requester_id = invitation.requester_id
    
    # 删除邀约记录
    db.session.delete(invitation)
    db.session.commit()
    
    old_room = GameRoom.query.filter_by(room_code=room_code).first()
    if not old_room:
        emit('rematch_error', {'message': '原房间不存在'}, room=room_code)
        return
    
    from flask_login import current_user
    from app.models import User
    requester = User.query.get(requester_id)
    requester_major = getattr(requester, 'major', None) if requester else None
    
    questions = get_random_questions(old_room.subject_id, old_room.chapter_id, old_room.question_count, user_major=requester_major)
    if not questions:
        emit('rematch_error', {'message': '没有找到符合条件的题目'}, room=room_code)
        return
    
    # 创建新房间
    new_room = GameRoom()
    new_room.room_code = generate_room_code()
    new_room.game_type = old_room.game_type
    new_room.subject_id = old_room.subject_id
    new_room.chapter_id = old_room.chapter_id
    new_room.max_players = old_room.max_players
    new_room.question_count = len(questions)
    new_room.created_by = requester_id
    db.session.add(new_room)
    db.session.commit()
    
    for i, q in enumerate(questions):
        gq = GameQuestion(room_id=new_room.id, question_id=q.id, order=i+1)
        db.session.add(gq)
    
    # 所有原房间玩家加入新房间（未准备状态，需手动确认准备）
    for player_id in all_player_ids:
        player = GamePlayer(room_id=new_room.id, user_id=player_id, is_ready=False)
        db.session.add(player)
    
    new_room.current_players = len(all_player_ids)
    db.session.commit()
    
    # 通知所有人跳转到新房间
    socketio.emit('rematch_ready', {
        'new_room_code': new_room.room_code,
        'old_room_code': room_code
    }, room=room_code)


# ========== 邀请在线队友逻辑 ==========

@socketio.on('get_online_players')
def on_get_online_players(data):
    """获取在线用户列表，同班级优先（支持分页和限制）"""
    user = _get_authenticated_user()
    if not user:
        emit('error', {'message': '请先登录'})
        return
    
    current_user_id = user.id
    current_user_class = user.class_name
    
    # 分页参数
    page = data.get('page', 1)
    page_size = data.get('page_size', 50)  # 每页最多50人
    max_total = 200  # 最多返回200人，避免性能问题
    
    # 分离同班级和其他班级的用户
    same_class_players = []
    other_class_players = []
    
    for uid, info in online_users.items():
        if uid == current_user_id:
            continue  # 排除自己
        
        user_info = info['user_info']
        
        # 排除关闭游戏功能的用户
        if not user_info.get('participate_in_games', False):
            continue
        
        u_class = user_info.get('class_name') or '未分班'
        is_same_class = (u_class == current_user_class) if current_user_class else False
        
        player_data = {
            'id': user_info['id'],
            'username': user_info['username'],
            'nickname': user_info['nickname'],
            'avatar_url': f"/static/avatars/{user_info['avatar']}" if user_info['avatar'] else '/static/avatars/default.png',
            'class_name': u_class,
            'is_same_class': is_same_class
        }
        
        if is_same_class:
            same_class_players.append(player_data)
        else:
            other_class_players.append(player_data)
        
        # 限制总数
        if len(same_class_players) + len(other_class_players) >= max_total:
            break
    
    # 分别排序
    same_class_players.sort(key=lambda p: (p['class_name'], p['nickname']))
    other_class_players.sort(key=lambda p: (p['class_name'], p['nickname']))
    
    # 合并：同班级在前
    all_players = same_class_players + other_class_players
    total_count = len(all_players)
    
    # 分页
    start_idx = (page - 1) * page_size
    end_idx = start_idx + page_size
    paginated_players = all_players[start_idx:end_idx]
    
    emit('online_players_list', {
        'players': paginated_players,
        'total': total_count,
        'same_class_count': len(same_class_players),
        'page': page,
        'page_size': page_size,
        'has_more': end_idx < total_count
    })


@socketio.on('invite_player')
def on_invite_player(data):
    """邀请玩家加入房间"""
    user = _get_authenticated_user()
    if not user:
        emit('error', {'message': '请先登录'})
        return
    
    room_code = data.get('room_code')
    target_user_id = data.get('target_user_id')
    
    if not room_code or not target_user_id:
        emit('error', {'message': '参数不完整'})
        return
    
    # 检查房间是否存在
    room = GameRoom.query.filter_by(room_code=room_code).first()
    if not room:
        emit('error', {'message': '房间不存在'})
        return
    
    # 检查房间状态
    if room.status != 'waiting':
        emit('error', {'message': '游戏已经开始或结束'})
        return
    
    if room.is_expired():
        emit('error', {'message': '房间已过期'})
        return
    
    if room.is_full():
        emit('error', {'message': '房间已满'})
        return
    
    # 检查邀请者是否在房间中
    inviter_player = GamePlayer.query.filter_by(room_id=room.id, user_id=user.id).first()
    if not inviter_player:
        emit('error', {'message': '您不在此房间中'})
        return
    
    # 检查目标用户是否在线
    if target_user_id not in online_users:
        emit('error', {'message': '该用户不在线'})
        return
    
    # 检查目标用户是否已经在房间中
    existing_player = GamePlayer.query.filter_by(room_id=room.id, user_id=target_user_id).first()
    if existing_player:
        emit('error', {'message': '该用户已在房间中'})
        return
    
    # 发送邀请通知给目标用户
    target_user = User.query.get(target_user_id)
    if not target_user:
        emit('error', {'message': '用户不存在'})
        return
    
    # 获取邀请者信息
    inviter_name = user.nickname or user.username
    subject_name = room.subject.name if room.subject else '综合'
    
    # 获取目标用户的所有sid
    target_sids = online_users[target_user_id]['sids']
    
    # 调试日志
    from flask import current_app
    current_app.logger.info(f'发送邀请 | inviter={user.id}({inviter_name}) -> target={target_user_id}({target_user.username}), room={room_code}')
    current_app.logger.info(f'目标用户在线状态: {target_user_id in online_users}')
    current_app.logger.info(f'目标用户sids: {target_sids}')
    current_app.logger.info(f'当前online_users.keys(): {list(online_users.keys())}')
    
    # 发送给目标用户的每个连接
    invitation_data = {
        'inviter_id': user.id,
        'inviter_name': inviter_name,
        'inviter_avatar': user.get_avatar_url(),
        'room_code': room_code,
        'game_type': room.game_type,
        'subject_name': subject_name,
        'current_players': room.current_players,
        'max_players': room.max_players
    }
    
    current_app.logger.info(f'邀请数据: {invitation_data}')
    
    for sid in target_sids:
        current_app.logger.info(f'尝试发送到sid: {sid}')
        socketio.emit('game_invitation', invitation_data, to=sid)
        current_app.logger.info(f'已发送到sid: {sid}')
    
    # 通知邀请者：邀请已发送
    emit('invitation_sent', {
        'target_user_id': target_user_id,
        'target_user_name': target_user.nickname or target_user.username,
        'room_code': room_code
    })


@socketio.on('accept_invitation')
def on_accept_invitation(data):
    """接受邀请，加入房间"""
    user = _get_authenticated_user()
    if not user:
        emit('error', {'message': '请先登录'})
        return
    
    room_code = data.get('room_code')
    
    if not room_code:
        emit('error', {'message': '参数不完整'})
        return
    
    room = GameRoom.query.filter_by(room_code=room_code).first()
    if not room:
        emit('error', {'message': '房间不存在'})
        return
    
    if room.is_expired():
        emit('error', {'message': '房间已过期'})
        return
    
    if room.status != 'waiting':
        emit('error', {'message': '游戏已经开始或结束'})
        return
    
    if room.is_full():
        emit('error', {'message': '房间已满'})
        return
    
    # 检查用户是否已经在房间中
    existing_player = GamePlayer.query.filter_by(room_id=room.id, user_id=user.id).first()
    if existing_player:
        emit('error', {'message': '您已在房间中'})
        return
    
    # 加入房间
    join_room(room_code)
    
    player = GamePlayer(room_id=room.id, user_id=user.id)
    db.session.add(player)
    if room.current_players is None:
        room.current_players = 0
    room.current_players += 1
    db.session.commit()
    
    # 通知房间内所有玩家
    players = GamePlayer.query.filter_by(room_id=room.id).all()
    players_data = [{
        'user_id': p.user_id,
        'username': p.user.username,
        'nickname': p.user.nickname or p.user.username,
        'avatar_url': p.user.get_avatar_url(),
        'is_ready': p.is_ready,
        'score': p.score
    } for p in players]
    
    emit('player_joined', {
        'user_id': user.id,
        'players': players_data,
        'current_players': room.current_players,
        'max_players': room.max_players
    }, room=room_code)
    
    # 通知邀请列表更新
    socketio.emit('room_updated', {
        'room': {
            'room_code': room.room_code,
            'current_players': room.current_players,
            'max_players': room.max_players
        }
    })
    
    # 通知接受者：加入成功
    emit('invitation_accepted', {
        'room_code': room_code,
        'redirect_url': f'/game/room/{room_code}'
    })


@socketio.on('decline_invitation')
def on_decline_invitation(data):
    """拒绝邀请"""
    user = _get_authenticated_user()
    if not user:
        return
    
    inviter_id = data.get('inviter_id')
    room_code = data.get('room_code')
    
    if inviter_id and inviter_id in online_users:
        # 通知邀请者：邀请被拒绝
        invite_sids = online_users[inviter_id]['sids']
        for sid in invite_sids:
            socketio.emit('invitation_declined', {
                'target_user_id': user.id,
                'target_user_name': user.nickname or user.username,
                'room_code': room_code
            }, to=sid)
