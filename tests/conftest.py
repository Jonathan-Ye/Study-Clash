import pytest
import os
import tempfile
from app import create_app, db
from app.models.user import User
from app.models.question import Question, Subject
from app.models.game import GameRecord
from app.models.points import PointRecord


@pytest.fixture(scope='session')
def test_app_instance():
    """创建会话级别的测试应用实例"""
    db_fd, db_path = tempfile.mkstemp()
    log_dir = os.path.join(tempfile.gettempdir(), 'studyclash_test_logs')
    os.makedirs(log_dir, exist_ok=True)
    
    os.environ['FLASK_ENV'] = 'testing'
    os.environ['SECRET_KEY'] = 'test-secret-key-for-testing'
    os.environ['DATABASE_URL'] = f'sqlite:///{db_path}'
    os.environ['LOG_DIR'] = log_dir
    
    app = create_app('testing')
    app.config['WTF_CSRF_ENABLED'] = False
    app.config['TESTING'] = True
    
    app.db_path = db_path
    app.db_fd = db_fd
    
    with app.app_context():
        db.create_all()
    
    yield app
    
    with app.app_context():
        db.drop_all()
    
    try:
        os.close(db_fd)
    except:
        pass
    try:
        os.unlink(db_path)
    except:
        pass


@pytest.fixture
def app(test_app_instance):
    """为每个测试创建应用上下文"""
    with test_app_instance.app_context():
        for table in reversed(db.metadata.sorted_tables):
            db.session.execute(table.delete())
        db.session.commit()
        
        yield test_app_instance


@pytest.fixture
def client(app):
    """创建测试客户端"""
    return app.test_client()


@pytest.fixture
def runner(app):
    """创建测试命令运行器"""
    return app.test_cli_runner()


@pytest.fixture
def db_session(app):
    """创建数据库会话"""
    with app.app_context():
        yield db


@pytest.fixture
def admin_user(app):
    """创建管理员用户"""
    user = User(
        username='admin',
        email='admin@test.com',
        role='admin'
    )
    user.set_password('admin123')
    db.session.add(user)
    db.session.commit()
    db.session.refresh(user)
    return user


@pytest.fixture
def regular_user(app):
    """创建普通用户"""
    user = User(
        username='testuser',
        email='test@test.com',
        role='student'
    )
    user.set_password('test123')
    db.session.add(user)
    db.session.commit()
    db.session.refresh(user)
    return user


@pytest.fixture
def teacher_user(app):
    """创建教师用户"""
    user = User(
        username='teacher',
        email='teacher@test.com',
        role='teacher'
    )
    user.set_password('teacher123')
    db.session.add(user)
    db.session.commit()
    db.session.refresh(user)
    return user


@pytest.fixture
def subject(app):
    """创建学科"""
    subj = Subject(name='数学', code='math')
    db.session.add(subj)
    db.session.commit()
    db.session.refresh(subj)
    return subj


@pytest.fixture
def question(app, subject):
    """创建题目"""
    q = Question(
        content='1+1=?',
        question_type='single',
        option_a='1',
        option_b='2',
        option_c='3',
        option_d='4',
        correct_answer='B',
        analysis='1+1=2',
        subject_id=subject.id,
        difficulty=1
    )
    db.session.add(q)
    db.session.commit()
    db.session.refresh(q)
    return q


@pytest.fixture
def multiple_questions(app, subject):
    """创建多道题目"""
    questions = []
    for i in range(10):
        q = Question(
            content=f'测试题目{i}',
            question_type='single',
            option_a='选项1',
            option_b='选项2',
            option_c='选项3',
            option_d='选项4',
            correct_answer='A',
            subject_id=subject.id,
            difficulty=(i % 3) + 1
        )
        db.session.add(q)
        questions.append(q)
    db.session.commit()
    return questions


@pytest.fixture
def logged_in_client(client, regular_user):
    """创建已登录的测试客户端"""
    client.post('/auth/login', data={
        'username': 'testuser',
        'password': 'test123'
    }, follow_redirects=True)
    return client


@pytest.fixture
def admin_client(client, admin_user):
    """创建管理员测试客户端"""
    client.post('/auth/login', data={
        'username': 'admin',
        'password': 'admin123'
    }, follow_redirects=True)
    return client


@pytest.fixture
def game_room(app, regular_user):
    """创建游戏房间"""
    from app.models.game import GameRoom
    room = GameRoom(
        room_code='TEST01',
        game_type='single',
        host_id=regular_user.id
    )
    db.session.add(room)
    db.session.commit()
    db.session.refresh(room)
    return room
