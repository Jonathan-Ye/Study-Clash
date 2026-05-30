import pytest
from app.models.user import User
from app.models.question import Question, Subject
from app.models.game import GameRoom, GameRecord, GamePlayer
from app import db


class TestGameLogic:
    """游戏逻辑测试"""

    def test_create_game_room(self, client, regular_user):
        """测试创建游戏房间"""
        client.post('/auth/login', data={
            'username': 'testuser',
            'password': 'test123'
        }, follow_redirects=True)
        
        subject_id = None
        with client.application.app_context():
            subject = Subject(name='测试学科', code='test_game')
            db.session.add(subject)
            db.session.commit()
            subject_id = subject.id
            
            for i in range(10):
                q = Question(
                    content=f'测试题目{i}',
                    question_type='single',
                    option_a='选项1',
                    option_b='选项2',
                    option_c='选项3',
                    option_d='选项4',
                    correct_answer='A',
                    subject_id=subject_id,
                    difficulty=1
                )
                db.session.add(q)
            db.session.commit()
        
        response = client.post('/game/create-room', json={
            'game_type': 'single',
            'subject_id': subject_id,
            'question_count': 5,
            'difficulty': 1
        }, follow_redirects=True)
        
        assert response.status_code in [200, 302]

    def test_join_game_room(self, client, regular_user):
        """测试加入游戏房间"""
        client.post('/auth/login', data={
            'username': 'testuser',
            'password': 'test123'
        }, follow_redirects=True)
        
        room_code = None
        with client.application.app_context():
            subject = Subject(name='加入测试', code='join_t')
            db.session.add(subject)
            db.session.commit()
            
            room = GameRoom(
                room_code='TJOIN',
                game_type='single',
                subject_id=subject.id,
                host_id=regular_user.id
            )
            db.session.add(room)
            db.session.commit()
            room_code = room.room_code
        
        response = client.post('/game/join-room', json={
            'room_code': room_code
        }, follow_redirects=True)
        
        assert response.status_code in [200, 302]

    def test_submit_answer(self, client, regular_user, question):
        """测试提交答案"""
        client.post('/auth/login', data={
            'username': 'testuser',
            'password': 'test123'
        }, follow_redirects=True)
        
        room_code = 'TANSWR'
        with client.application.app_context():
            subject = Subject(name='答题测试', code='ans_t')
            db.session.add(subject)
            db.session.commit()
            
            room = GameRoom(
                room_code=room_code,
                game_type='single',
                subject_id=subject.id,
                host_id=regular_user.id
            )
            db.session.add(room)
            db.session.commit()
            
            player = GamePlayer(
                room_id=room.id,
                user_id=regular_user.id
            )
            db.session.add(player)
            db.session.commit()
        
        response = client.post('/game/submit-answer', json={
            'room_code': room_code,
            'question_id': question.id,
            'answer': 'B',
            'time_spent': 10
        })
        
        assert response.status_code == 200
        data = response.get_json()
        assert 'is_correct' in data

    def test_correct_answer(self, client, regular_user, question):
        """测试正确答案"""
        client.post('/auth/login', data={
            'username': 'testuser',
            'password': 'test123'
        }, follow_redirects=True)
        
        room_code = 'TCORRCT'
        with client.application.app_context():
            subject = Subject(name='正确测试', code='corr_t')
            db.session.add(subject)
            db.session.commit()
            
            room = GameRoom(
                room_code=room_code,
                game_type='single',
                subject_id=subject.id,
                host_id=regular_user.id
            )
            db.session.add(room)
            db.session.commit()
            
            player = GamePlayer(
                room_id=room.id,
                user_id=regular_user.id
            )
            db.session.add(player)
            db.session.commit()
        
        response = client.post('/game/submit-answer', json={
            'room_code': room_code,
            'question_id': question.id,
            'answer': question.correct_answer,
            'time_spent': 10
        })
        
        data = response.get_json()
        assert data['is_correct'] is True

    def test_wrong_answer(self, client, regular_user, question):
        """测试错误答案"""
        client.post('/auth/login', data={
            'username': 'testuser',
            'password': 'test123'
        }, follow_redirects=True)
        
        room_code = 'TWRONG'
        with client.application.app_context():
            subject = Subject(name='错误测试', code='wrong_t')
            db.session.add(subject)
            db.session.commit()
            
            room = GameRoom(
                room_code=room_code,
                game_type='single',
                subject_id=subject.id,
                host_id=regular_user.id
            )
            db.session.add(room)
            db.session.commit()
            
            player = GamePlayer(
                room_id=room.id,
                user_id=regular_user.id
            )
            db.session.add(player)
            db.session.commit()
        
        wrong_answer = 'A' if question.correct_answer != 'A' else 'B'
        response = client.post('/game/submit-answer', json={
            'room_code': room_code,
            'question_id': question.id,
            'answer': wrong_answer,
            'time_spent': 10
        })
        
        data = response.get_json()
        assert data['is_correct'] is False

    def test_game_record_creation(self, client, regular_user, question):
        """测试游戏记录创建"""
        client.post('/auth/login', data={
            'username': 'testuser',
            'password': 'test123'
        }, follow_redirects=True)
        
        room_code = 'TRECORD'
        with client.application.app_context():
            subject = Subject(name='记录测试', code='rec_t')
            db.session.add(subject)
            db.session.commit()
            
            room = GameRoom(
                room_code=room_code,
                game_type='single',
                subject_id=subject.id,
                host_id=regular_user.id
            )
            db.session.add(room)
            db.session.commit()
            
            player = GamePlayer(
                room_id=room.id,
                user_id=regular_user.id
            )
            db.session.add(player)
            db.session.commit()
            
            response = client.post('/game/submit-answer', json={
                'room_code': room_code,
                'question_id': question.id,
                'answer': question.correct_answer,
                'time_spent': 10
            })
        
        with client.application.app_context():
            record = GameRecord.query.filter_by(user_id=regular_user.id).first()
            assert record is not None

    def test_single_mode_game(self, client, regular_user):
        """测试单人模式游戏"""
        client.post('/auth/login', data={
            'username': 'testuser',
            'password': 'test123'
        }, follow_redirects=True)
        
        subject_id = None
        with client.application.app_context():
            subject = Subject(name='单人测试', code='single_test')
            db.session.add(subject)
            db.session.commit()
            subject_id = subject.id
            
            for i in range(5):
                q = Question(
                    content=f'单人题目{i}',
                    question_type='single',
                    option_a='1',
                    option_b='2',
                    option_c='3',
                    option_d='4',
                    correct_answer='A',
                    subject_id=subject_id,
                    difficulty=1
                )
                db.session.add(q)
            db.session.commit()
        
        response = client.post('/game/create-room', json={
            'game_type': 'single',
            'subject_id': subject_id,
            'question_count': 3,
            'difficulty': 1
        }, follow_redirects=True)
        
        assert response.status_code in [200, 302]

    def test_room_code_generation(self, client, regular_user):
        """测试房间码生成"""
        client.post('/auth/login', data={
            'username': 'testuser',
            'password': 'test123'
        }, follow_redirects=True)
        
        subject_id = None
        with client.application.app_context():
            subject = Subject(name='房间码测试', code='room_test')
            db.session.add(subject)
            db.session.commit()
            subject_id = subject.id
        
        response = client.post('/game/create-room', json={
            'game_type': 'single',
            'subject_id': subject_id,
            'question_count': 5,
            'difficulty': 1
        }, follow_redirects=True)
        
        with client.application.app_context():
            room = GameRoom.query.filter_by(host_id=regular_user.id).order_by(GameRoom.created_at.desc()).first()
            assert room is not None
            assert room.room_code is not None
            assert len(room.room_code) >= 4
