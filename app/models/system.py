from app import db
from datetime import datetime, timezone


class SystemSetting(db.Model):
    """系统设置表"""
    __tablename__ = 'system_settings'
    
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(50), unique=True, nullable=False)
    value = db.Column(db.Text, nullable=True)
    description = db.Column(db.String(200), nullable=True)
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    
    @staticmethod
    def get(key, default=None):
        """获取设置值"""
        setting = SystemSetting.query.filter_by(key=key).first()
        return setting.value if setting else default
    
    @staticmethod
    def set(key, value, description=None):
        """设置值"""
        setting = SystemSetting.query.filter_by(key=key).first()
        if setting:
            setting.value = value
        else:
            setting = SystemSetting(key=key, value=value, description=description)
            db.session.add(setting)
        db.session.commit()
    
    @staticmethod
    def get_logo_url():
        """获取Logo URL"""
        logo = SystemSetting.get('site_logo')
        if logo:
            return f'/static/images/{logo}'
        return '/static/images/logo-small.png'
