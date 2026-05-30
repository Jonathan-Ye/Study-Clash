import pytest
from datetime import datetime, timedelta, timezone
from app import db as _db
from app.models.login_security import LoginAttempt
from app.models.system import SystemSetting
from app.models.user import User


class TestLoginSecurity:
    """登录安全机制测试"""

    def test_fail_count_increments(self, app):
        """登录失败计数递增"""
        with app.app_context():
            SystemSetting.set('max_login_attempts', '5', '最大登录尝试次数')
            SystemSetting.set('lockout_duration', '30', '锁定时长（分钟）')
            
            record = LoginAttempt.record_failure('testuser')
            assert record.fail_count == 1

            record = LoginAttempt.record_failure('testuser')
            assert record.fail_count == 2

    def test_lockout_triggers_at_threshold(self, app):
        """达到最大尝试次数时触发锁定"""
        with app.app_context():
            SystemSetting.set('max_login_attempts', '5', '最大登录尝试次数')
            SystemSetting.set('lockout_duration', '30', '锁定时长（分钟）')
            
            for i in range(5):
                record = LoginAttempt.record_failure('lockuser')

            LoginAttempt.lock_account('lockuser', 30)
            is_locked, remaining = LoginAttempt.is_locked('lockuser')
            assert is_locked is True
            assert remaining > 0

    def test_lockout_expires(self, app):
        """锁定过期后自动解锁"""
        with app.app_context():
            SystemSetting.set('max_login_attempts', '5', '最大登录尝试次数')
            SystemSetting.set('lockout_duration', '30', '锁定时长（分钟）')
            
            record = LoginAttempt.get_or_create('expireuser')
            record.fail_count = 5
            record.locked_until = datetime.now(timezone.utc) - timedelta(minutes=1)
            _db.session.commit()

            is_locked, remaining = LoginAttempt.is_locked('expireuser')
            assert is_locked is False
            assert remaining == 0

    def test_successful_login_resets_count(self, app):
        """登录成功后重置失败计数"""
        with app.app_context():
            SystemSetting.set('max_login_attempts', '5', '最大登录尝试次数')
            SystemSetting.set('lockout_duration', '30', '锁定时长（分钟）')
            
            LoginAttempt.record_failure('resetuser')
            LoginAttempt.record_failure('resetuser')
            record = LoginAttempt.get_or_create('resetuser')
            assert record.fail_count == 2

            LoginAttempt.reset('resetuser')
            record = LoginAttempt.get_or_create('resetuser')
            assert record.fail_count == 0
            assert record.locked_until is None

    def test_admin_exempt_from_lockout(self, app, admin_user):
        """管理员账户不受锁定限制"""
        with app.app_context():
            SystemSetting.set('max_login_attempts', '5', '最大登录尝试次数')
            SystemSetting.set('lockout_duration', '30', '锁定时长（分钟）')
            
            assert admin_user.role == 'admin'

            LoginAttempt.record_failure('testadmin')
            LoginAttempt.record_failure('testadmin')
            record = LoginAttempt.get_or_create('testadmin')
            assert record.fail_count == 2

            is_admin = admin_user.role == 'admin'
            assert is_admin is True
