import pytest
from app.models.system import SystemSetting
from app.utils.security import validate_password


class TestPasswordPolicyDisabled:
    """密码策略禁用时的测试"""

    def test_long_password_passes_when_disabled(self, app):
        """策略禁用时，6位以上密码通过"""
        with app.app_context():
            SystemSetting.set('password_policy_enabled', 'false', '启用密码复杂度策略')
            is_valid, errors = validate_password('abcdef')
            assert is_valid is True
            assert len(errors) == 0

    def test_short_password_fails_when_disabled(self, app):
        """策略禁用时，少于6位密码仍然失败"""
        with app.app_context():
            SystemSetting.set('password_policy_enabled', 'false', '启用密码复杂度策略')
            is_valid, errors = validate_password('abc')
            assert is_valid is False
            assert len(errors) > 0


class TestPasswordPolicyEnabled:
    """密码策略启用时的测试"""

    def _setup_policy(self):
        """启用策略并设置默认规则"""
        SystemSetting.set('password_policy_enabled', 'true', '启用密码复杂度策略')
        SystemSetting.set('password_min_length', '8', '最小密码长度')
        SystemSetting.set('password_require_uppercase', 'true', '密码要求大写字母')
        SystemSetting.set('password_require_lowercase', 'true', '密码要求小写字母')
        SystemSetting.set('password_require_digit', 'true', '密码要求数字')
        SystemSetting.set('password_require_special', 'true', '密码要求特殊字符')

    def test_valid_password_passes(self, app):
        """符合所有规则的密码通过"""
        with app.app_context():
            self._setup_policy()
            is_valid, errors = validate_password('Test123!')
            assert is_valid is True
            assert len(errors) == 0

    def test_no_uppercase_fails(self, app):
        """缺少大写字母时失败"""
        with app.app_context():
            self._setup_policy()
            is_valid, errors = validate_password('test123!')
            assert is_valid is False
            assert any('大写' in e for e in errors)

    def test_no_lowercase_fails(self, app):
        """缺少小写字母时失败"""
        with app.app_context():
            self._setup_policy()
            is_valid, errors = validate_password('TEST123!')
            assert is_valid is False
            assert any('小写' in e for e in errors)

    def test_no_digit_fails(self, app):
        """缺少数字时失败"""
        with app.app_context():
            self._setup_policy()
            is_valid, errors = validate_password('TestTest!')
            assert is_valid is False
            assert any('数字' in e for e in errors)

    def test_no_special_char_fails(self, app):
        """缺少特殊字符时失败"""
        with app.app_context():
            self._setup_policy()
            is_valid, errors = validate_password('Test1234')
            assert is_valid is False
            assert any('特殊' in e for e in errors)

    def test_too_short_fails(self, app):
        """密码长度不足时失败"""
        with app.app_context():
            self._setup_policy()
            is_valid, errors = validate_password('Ab1!')
            assert is_valid is False
            assert any('字符' in e for e in errors)
