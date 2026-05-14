import os
from datetime import timedelta, timezone

basedir = os.path.abspath(os.path.dirname(__file__))

from dotenv import load_dotenv
load_dotenv(os.path.join(basedir, '.env'))

# 北京时间时区（UTC+8）
BEIJING_TZ = timezone(timedelta(hours=8))

# 自动检测并生成缺失的环境变量
def _ensure_env_variables():
    """确保必需的环境变量存在，如果缺失则自动生成并提示用户"""
    env_path = os.path.join(basedir, '.env')
    env_modified = False
    env_content = {}
    
    # 读取现有 .env 文件
    if os.path.exists(env_path):
        with open(env_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    env_content[key.strip()] = value.strip()
    
    # 检查并生成 LLM_ENCRYPTION_KEY
    if not os.environ.get('LLM_ENCRYPTION_KEY') and env_content.get('LLM_ENCRYPTION_KEY') == '':
        try:
            from cryptography.fernet import Fernet
            new_key = Fernet.generate_key().decode()
            env_content['LLM_ENCRYPTION_KEY'] = new_key
            env_modified = True
            print('⚠️  检测到 LLM_ENCRYPTION_KEY 缺失，已自动生成')
            print(f'   新密钥: {new_key}')
            print('   ⚠️  请妥善备份此密钥，丢失后已加密的 API Key 将无法解密！')
        except ImportError:
            print('⚠️  未安装 cryptography 库，无法生成 LLM_ENCRYPTION_KEY')
            print('   请运行: pip install cryptography')
            print('   或手动在 .env 中添加: LLM_ENCRYPTION_KEY=<your-key>')
    
    # 检查 SOCKETIO_CORS_ALLOWED_ORIGINS
    if not os.environ.get('SOCKETIO_CORS_ALLOWED_ORIGINS') and 'SOCKETIO_CORS_ALLOWED_ORIGINS' not in env_content:
        env_content['SOCKETIO_CORS_ALLOWED_ORIGINS'] = '*'
        env_modified = True
        print('⚠️  检测到 SOCKETIO_CORS_ALLOWED_ORIGINS 缺失，已设置为 *')
    
    # 检查 LOG_DIR
    if not os.environ.get('LOG_DIR') and 'LOG_DIR' not in env_content:
        env_content['LOG_DIR'] = 'logs'
        env_modified = True
        print('⚠️  检测到 LOG_DIR 缺失，已设置为 logs')
    
    # 检查 LOG_RETENTION_DAYS
    if not os.environ.get('LOG_RETENTION_DAYS') and 'LOG_RETENTION_DAYS' not in env_content:
        env_content['LOG_RETENTION_DAYS'] = '30'
        env_modified = True
        print('⚠️  检测到 LOG_RETENTION_DAYS 缺失，已设置为 30')
    
    # 如果有修改，写回 .env 文件
    if env_modified:
        try:
            with open(env_path, 'a', encoding='utf-8') as f:
                f.write('\n# 自动生成的环境变量\n')
                for key in ['LLM_ENCRYPTION_KEY', 'SOCKETIO_CORS_ALLOWED_ORIGINS', 'LOG_DIR', 'LOG_RETENTION_DAYS']:
                    if key in env_content:
                        f.write(f'{key}={env_content[key]}\n')
            print(f'✅ 已更新 .env 文件: {env_path}')
            
            # 重新加载环境变量
            load_dotenv(env_path, override=True)
        except Exception as e:
            print(f'❌ 无法写入 .env 文件: {e}')
            print('   请手动添加缺失的环境变量')

# 执行自动检测
_ensure_env_variables()
del _ensure_env_variables  # 清理临时函数

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-key-for-testing-only'
    # 检测不安全的默认密钥
    _INSECURE_KEYS = {
        'your-secret-key-change-in-production',
        'dev', 'development', 'secret', 'change-me',
        'flask-secret-key', 'test',
    }
    
    if not SECRET_KEY:
        import secrets
        SECRET_KEY = secrets.token_hex(32)
        _SECRET_KEY_IS_DEFAULT = True
    elif SECRET_KEY in _INSECURE_KEYS:
        _SECRET_KEY_IS_DEFAULT = True
    else:
        _SECRET_KEY_IS_DEFAULT = False
    
    # 数据库配置（仅支持 PostgreSQL）
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL')
    if not SQLALCHEMY_DATABASE_URI:
        raise ValueError(
            'DATABASE_URL 环境变量未设置！\n'
            '请在 .env 文件中配置 PostgreSQL 连接，格式：\n'
            'DATABASE_URL=postgresql://用户名:密码@localhost:5432/数据库名\n'
            '本地开发示例：DATABASE_URL=postgresql://postgres:postgres@localhost:5432/studyclash_dev'
        )
    
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # PostgreSQL 连接池配置
    # 注意：这是每个 Worker 进程的连接池大小
    # Gunicorn 有 32 个 Worker，所以总连接数 = pool_size × workers
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_size': 5,              # 每个 Worker 核心连接数
        'max_overflow': 10,          # 每个 Worker 最大溢出连接
        'pool_pre_ping': True,       # 连接健康检查
        'pool_recycle': 3600,        # 1 小时回收连接
        'pool_timeout': 10,          # 获取连接超时时间（秒）
    }
    
    # Session Cookie 安全配置
    # 默认 False：兼容 HTTP 内网访问和 HTTPS 反向代理
    # 当使用 Caddy/Nginx 时，HTTPS 加密和安全头由反向代理处理，应用层无需干预
    SESSION_COOKIE_SECURE = os.environ.get('SESSION_SECURE', 'false').lower() == 'true'
    SESSION_COOKIE_HTTPONLY = True  # 防止JavaScript访问
    SESSION_COOKIE_SAMESITE = 'Lax'  # 防止CSRF攻击
    
    UPLOAD_FOLDER = os.path.join(basedir, 'uploads')
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024

    LOG_DIR = os.environ.get('LOG_DIR', os.path.join(basedir, 'logs'))
    LOG_RETENTION_DAYS = int(os.environ.get('LOG_RETENTION_DAYS', '30'))

    SOCKETIO_MESSAGE_QUEUE = os.environ.get('SOCKETIO_MESSAGE_QUEUE')
    
    # Redis 缓存配置
    REDIS_URL = os.environ.get('REDIS_URL')
    if REDIS_URL:
        CACHE_TYPE = 'redis'
        CACHE_REDIS_URL = REDIS_URL
    else:
        CACHE_TYPE = 'simple'  # 内存缓存（仅用于开发环境）
    
    SOCKETIO_CORS_ALLOWED_ORIGINS = os.environ.get(
        'SOCKETIO_CORS_ALLOWED_ORIGINS',
        'http://127.0.0.1:5002,http://localhost:5002'
    )
    
    PERMANENT_SESSION_LIFETIME = timedelta(hours=2)
    SESSION_LIFETIME_HOURS = 2
    
    POINTS_CONFIG = {
        'single_correct': 1,
        'battle_win': 10,
        'four_first': 30,
        'four_second': 20,
        'four_third': 10,
        'four_fourth': 5,
        'review_correct': 1,
        'daily_login': 5,
        'streak_bonus': 5,
    }
    
    SINGLE_CHALLENGE_WRONG_CHANCES = 3
    
    ROOM_EXPIRE_MINUTES = 20
    
    WRONG_QUESTION_CONFIG = {
        'consecutive_correct_required': 3,
        'review_points': 5,
        'max_review_per_day': 50,
        'enable_spaced_review': True,
    }

    LLM_ENCRYPTION_KEY = os.environ.get('LLM_ENCRYPTION_KEY', '')

class DevelopmentConfig(Config):
    DEBUG = True

class ProductionConfig(Config):
    DEBUG = False

class TestingConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'

config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
    'default': DevelopmentConfig
}
