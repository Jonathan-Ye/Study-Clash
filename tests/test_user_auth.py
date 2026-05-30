import pytest
from app.models.user import User
from app import db


class TestUserAuth:
    """用户认证测试"""

    def test_user_creation(self, app):
        """测试用户创建"""
        with app.app_context():
            user = User(
                username='testuser',
                email='test@example.com',
                role='student'
            )
            user.set_password('password123')
            db.session.add(user)
            db.session.commit()
            
            assert user.id is not None
            assert user.check_password('password123')
            assert not user.check_password('wrongpassword')

    def test_unique_username(self, app):
        """测试用户名唯一性"""
        with app.app_context():
            user1 = User(username='unique', email='u1@example.com', role='student')
            user1.set_password('pass123')
            db.session.add(user1)
            db.session.commit()
            
            user2 = User(username='unique', email='u2@example.com', role='student')
            user2.set_password('pass123')
            db.session.add(user2)
            
            with pytest.raises(Exception):
                db.session.commit()

    def test_unique_email(self, app):
        """测试邮箱唯一性"""
        with app.app_context():
            user1 = User(username='u1', email='same@example.com', role='student')
            user1.set_password('pass123')
            db.session.add(user1)
            db.session.commit()
            
            user2 = User(username='u2', email='same@example.com', role='student')
            user2.set_password('pass123')
            db.session.add(user2)
            
            with pytest.raises(Exception):
                db.session.commit()

    def test_password_hash_not_stored_plain(self, app):
        """测试密码不以明文存储"""
        with app.app_context():
            user = User(username='hashuser', email='hash@example.com', role='student')
            user.set_password('mypassword')
            db.session.add(user)
            db.session.commit()
            
            assert user.password_hash != 'mypassword'
            assert '$' in user.password_hash

    def test_login_success(self, client, regular_user):
        """测试登录成功"""
        response = client.post('/auth/login', data={
            'username': 'testuser',
            'password': 'test123'
        }, follow_redirects=True)
        
        assert response.status_code == 200

    def test_login_wrong_password(self, client, regular_user):
        """测试密码错误"""
        response = client.post('/auth/login', data={
            'username': 'testuser',
            'password': 'wrongpassword'
        }, follow_redirects=True)
        
        assert response.status_code == 200

    def test_login_nonexistent_user(self, client):
        """测试不存在的用户"""
        response = client.post('/auth/login', data={
            'username': 'nonexistent',
            'password': 'test123'
        })
        
        assert response.status_code in [200, 302]

    def test_logout(self, client, regular_user):
        """测试登出"""
        client.post('/auth/login', data={
            'username': 'testuser',
            'password': 'test123'
        })
        
        response = client.get('/auth/logout')
        assert response.status_code in [200, 302]

    def test_register_user(self, client):
        """测试用户注册"""
        response = client.post('/auth/register', data={
            'username': 'newuser',
            'email': 'newuser@example.com',
            'password': 'newpass123',
            'confirm_password': 'newpass123'
        }, follow_redirects=True)
        
        assert response.status_code == 200
        
        with client.application.app_context():
            user = User.query.filter_by(username='newuser').first()
            assert user is not None
            assert user.email == 'newuser@example.com'

    def test_change_password(self, client, regular_user):
        """测试修改密码"""
        client.post('/auth/login', data={
            'username': 'testuser',
            'password': 'test123'
        })
        
        response = client.post('/auth/change-password', data={
            'old_password': 'test123',
            'new_password': 'newpassword123',
            'confirm_password': 'newpassword123'
        })
        
        assert response.status_code in [200, 302]
        
        with client.application.app_context():
            user = User.query.filter_by(username='testuser').first()
            assert not user.check_password('test123')
            assert user.check_password('newpassword123')

    def test_register_duplicate_username(self, client, regular_user):
        """测试注册重复用户名"""
        response = client.post('/auth/register', data={
            'username': 'testuser',
            'email': 'another@example.com',
            'password': 'pass123',
            'confirm_password': 'pass123'
        }, follow_redirects=True)
        
        assert response.status_code == 200

    def test_register_weak_password(self, client):
        """测试弱密码注册"""
        response = client.post('/auth/register', data={
            'username': 'weakuser',
            'email': 'weak@example.com',
            'password': '123',
            'confirm_password': '123'
        })
        
        assert response.status_code in [200, 302]
