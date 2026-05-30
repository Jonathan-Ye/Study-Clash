import json
import os
import datetime
import zipfile

# 全局进度和日志跟踪
restore_progress = {
    'status': 'idle',  # idle, running, completed, error
    'current_step': '',
    'total_steps': 0,
    'current_table': '',
    'total_tables': 0,
    'tables_processed': 0,
    'message': ''
}

restore_logs = []

def get_restore_progress():
    return restore_progress.copy()

def get_restore_logs():
    return {
        'logs': restore_logs.copy(),
        'status': restore_progress.get('status', 'idle'),
        'message': restore_progress.get('message', '')
    }

def reset_restore_progress():
    global restore_progress, restore_logs
    restore_progress = {
        'status': 'idle',
        'current_step': '',
        'total_steps': 0,
        'current_table': '',
        'total_tables': 0,
        'tables_processed': 0,
        'message': ''
    }
    restore_logs = []

def update_progress(status, current_step, message='', total_steps=0, current_table='', total_tables=0, tables_processed=0):
    global restore_progress
    restore_progress['status'] = status
    restore_progress['current_step'] = current_step
    restore_progress['message'] = message
    restore_progress['total_steps'] = total_steps
    restore_progress['current_table'] = current_table
    restore_progress['total_tables'] = total_tables
    restore_progress['tables_processed'] = tables_processed

def add_restore_log(message):
    """添加一条恢复日志"""
    global restore_logs
    timestamp = datetime.datetime.now().strftime('%H:%M:%S')
    log_entry = f'[{timestamp}] {message}'
    restore_logs.append(log_entry)
from sqlalchemy import inspect
from flask import current_app
from app import db
from app.models import (
    User, Subject, Chapter, Question, UserAnswer,
    GameRoom, GamePlayer, GameRecord, GameQuestion,
    PointRecord, DailyStats, Leaderboard,
    WrongQuestion, WrongQuestionCollection, WrongQuestionCollectionItem, WrongQuestionNote,
    SystemSetting
)
from app.models.admin_log import AdminLog
from app.models.announcement import Announcement, AnnouncementRead
from app.models.login_security import LoginAttempt
from app.models.notification import UserNotification
from app.models.question_feedback import QuestionFeedback
from app.models.ranks import RankTier, TierPromotionHistory
from app.models.dictionary import DictionaryCategory, DictionaryItem
from app.models.wrong_question import ChallengeProgress, ReviewStreak
from app.models.game import RematchInvitation
from app.models.ai_analysis import (
    LLMProvider, LLMCallStrategy, AIAnalysisResult, AIPredictionResult,
    AIGeneratedContent, AILearningStrategy, LLMCallLog, LLMFallbackEvent,
    AIAsyncTask, AIChatSession, AIChatMessage, AIStudyReport, AIStudyPlan,
    AIComparisonResult, AIUsageQuota, AIConversation, AILearningReport,
    AILearningPlan, AIBadgeDefinition, AIBadgeRecord, AISmartAnalysis
)
from app.utils.common import DEFAULT_SUBJECTS_DATA

BACKUP_VERSION = '1.1.20260509'
BACKUP_DIR = 'backups'

# 模型顺序很重要：
# 1. 恢复时按此顺序插入（基础表先插入）
# 2. 清空时按相反顺序删除（依赖表先删除）
MODEL_ORDER = [
    # 基础配置表（无外键依赖）
    SystemSetting,
    DictionaryCategory,
    DictionaryItem,
    RankTier,
    AIBadgeDefinition,
    LLMProvider,
    LLMCallStrategy,
    
    # 用户相关
    User,
    LoginAttempt,
    AdminLog,
    
    # 学科和题目
    Subject,
    Chapter,
    Question,
    QuestionFeedback,
    UserAnswer,
    
    # 游戏相关
    GameRoom,
    GamePlayer,
    GameQuestion,
    GameRecord,
    RematchInvitation,
    
    # 错题本相关
    WrongQuestionCollection,
    WrongQuestion,
    WrongQuestionCollectionItem,
    WrongQuestionNote,
    ChallengeProgress,
    ReviewStreak,
    
    # 积分和统计
    PointRecord,
    DailyStats,
    Leaderboard,
    
    # 公告和通知
    Announcement,
    AnnouncementRead,
    UserNotification,
    
    # 排行榜晋升历史
    TierPromotionHistory,
    
    # AI 相关
    AIUsageQuota,
    AIAsyncTask,
    AIAnalysisResult,
    AIPredictionResult,
    AIGeneratedContent,
    AILearningStrategy,
    LLMCallLog,
    LLMFallbackEvent,
    AIChatSession,
    AIChatMessage,
    AIStudyReport,
    AIStudyPlan,
    AIComparisonResult,
    AIConversation,
    AILearningReport,
    AILearningPlan,
    AIBadgeRecord,
    AISmartAnalysis,
]


def get_backup_dir():
    backup_dir = os.path.join(current_app.root_path, '..', BACKUP_DIR)
    os.makedirs(backup_dir, exist_ok=True)
    return backup_dir


def model_to_dict(model_instance):
    data = {}
    for column in model_instance.__table__.columns:
        value = getattr(model_instance, column.key)
        if isinstance(value, datetime.datetime):
            data[column.key] = value.isoformat()
        elif isinstance(value, datetime.date):
            data[column.key] = value.isoformat()
        else:
            data[column.key] = value
    return data


def dict_to_model(model_class, data):
    exclude_fields = []
    if hasattr(model_class, '_backup_exclude'):
        exclude_fields = model_class._backup_exclude
    
    filtered_data = {k: v for k, v in data.items() if k not in exclude_fields}
    
    for key, value in filtered_data.items():
        filtered_data[key] = _convert_datetime(value)
    
    # 为 User 模型提供默认密码哈希（如果缺失）
    if model_class.__name__ == 'User' and not filtered_data.get('password_hash'):
        from werkzeug.security import generate_password_hash
        # 使用用户名作为默认密码，并要求首次登录时修改
        default_password = filtered_data.get('username', 'default123')
        filtered_data['password_hash'] = generate_password_hash(default_password)
        filtered_data['must_change_password'] = True
    
    return model_class(**filtered_data)


def _convert_datetime(value):
    if value is None:
        return value
    if isinstance(value, datetime.datetime) or isinstance(value, datetime.date):
        return value
    if isinstance(value, str):
        try:
            return datetime.datetime.fromisoformat(value)
        except (ValueError, TypeError):
            try:
                return datetime.date.fromisoformat(value)
            except (ValueError, TypeError):
                pass
    return value


def create_backup(include_static=False):
    """创建备份
    
    Args:
        include_static: 是否包含静态文件（头像、题目图片等），如果为True则创建zip压缩包
    
    Returns:
        备份文件路径
    """
    timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    
    if include_static:
        return _create_full_backup_zip(timestamp)
    else:
        return _create_database_backup_json(timestamp)


def _create_database_backup_json(timestamp):
    """创建仅包含数据库的JSON备份"""
    backup_data = {
        'version': BACKUP_VERSION,
        'created_at': datetime.datetime.now().isoformat(),
        'tables': {}
    }

    for model in MODEL_ORDER:
        table_name = model.__tablename__
        records = model.query.all()
        backup_data['tables'][table_name] = [model_to_dict(record) for record in records]

    filename = f'backup_{timestamp}.json'
    filepath = os.path.join(get_backup_dir(), filename)

    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(backup_data, f, ensure_ascii=False, indent=2)

    return filepath


def _create_full_backup_zip(timestamp):
    """创建包含数据库和所有静态文件的完整压缩包"""
    from flask import current_app
    
    backup_dir = get_backup_dir()
    filename = f'full_backup_{timestamp}.zip'
    filepath = os.path.join(backup_dir, filename)
    
    static_dir = os.path.join(current_app.root_path, 'static')
    
    with zipfile.ZipFile(filepath, 'w', zipfile.ZIP_DEFLATED) as zipf:
        backup_data = {
            'version': BACKUP_VERSION,
            'created_at': datetime.datetime.now().isoformat(),
            'type': 'full_backup',
            'tables': {}
        }
        
        for model in MODEL_ORDER:
            table_name = model.__tablename__
            records = model.query.all()
            backup_data['tables'][table_name] = [model_to_dict(record) for record in records]
        
        db_json = json.dumps(backup_data, ensure_ascii=False, indent=2)
        zipf.writestr('database_backup.json', db_json)
        
        if os.path.exists(static_dir):
            for root, dirs, files in os.walk(static_dir):
                for file in files:
                    file_path = os.path.join(root, file)
                    arcname = os.path.relpath(file_path, os.path.dirname(static_dir))
                    zipf.write(file_path, arcname)
    
    return filepath


def restore_backup(filepath, clear_exclude_tables=None, db_config=None):
    """
    恢复备份 - 使用 psycopg2 直连避免连接池冲突
    支持JSON数据库备份和ZIP完整备份
    """
    import logging
    logger = logging.getLogger(__name__)
    
    if clear_exclude_tables is None:
        clear_exclude_tables = []

    from app.utils.migration import migrate_backup_data, validate_backup_compatibility, CURRENT_VERSION
    from sqlalchemy import text
    from app import db

    # 重置进度
    reset_restore_progress()
    
    # 检查是否是ZIP完整备份
    is_full_backup = filepath.endswith('.zip')
    
    if is_full_backup:
        return _restore_full_backup(filepath, clear_exclude_tables, db_config)
    else:
        return _restore_database_backup(filepath, clear_exclude_tables, db_config)


def _restore_database_backup(filepath, clear_exclude_tables, db_config):
    """恢复仅包含数据库的JSON备份"""
    import logging
    logger = logging.getLogger(__name__)
    
    from app.utils.migration import migrate_backup_data, validate_backup_compatibility
    from app import db
    
    update_progress('running', '读取备份文件...', '正在读取备份文件...', total_steps=3)
    add_restore_log('INFO: 步骤 1/3: 读取备份文件...')
    logger.info('步骤 1/3: 读取备份文件...')
    
    with open(filepath, 'r', encoding='utf-8') as f:
        backup_data = json.load(f)
    
    return _perform_database_restore(backup_data, clear_exclude_tables, db_config)


def _restore_full_backup(filepath, clear_exclude_tables, db_config):
    """恢复完整系统备份（ZIP格式）"""
    import logging
    logger = logging.getLogger(__name__)
    from flask import current_app
    
    update_progress('running', '解压备份文件...', '正在解压完整备份...', total_steps=4)
    add_restore_log('INFO: 步骤 1/4: 解压完整备份文件...')
    logger.info('步骤 1/4: 解压完整备份文件...')
    
    import tempfile
    import shutil
    
    temp_dir = tempfile.mkdtemp(prefix='backup_restore_')
    
    try:
        with zipfile.ZipFile(filepath, 'r') as zipf:
            zipf.extractall(temp_dir)
        
        db_json_path = os.path.join(temp_dir, 'database_backup.json')
        if not os.path.exists(db_json_path):
            raise RuntimeError('ZIP备份中未找到database_backup.json文件，可能不是有效的完整备份')
        
        with open(db_json_path, 'r', encoding='utf-8') as f:
            backup_data = json.load(f)
        
        add_restore_log('INFO: 备份文件解压成功')
        
        static_dir = os.path.join(current_app.root_path, 'static')
        backup_static_dir = os.path.join(temp_dir, 'static')
        
        if os.path.exists(backup_static_dir):
            update_progress('running', '恢复静态文件...', '正在恢复头像、图片等文件...', total_steps=4)
            add_restore_log('INFO: 步骤 2/4: 恢复静态文件...')
            logger.info('步骤 2/4: 恢复静态文件...')
            
            try:
                if os.path.exists(static_dir):
                    add_restore_log('INFO: 备份前清理现有静态文件...')
                    logger.info('正在清理现有static目录...')
                    shutil.rmtree(static_dir)
                    add_restore_log('INFO: 现有static目录已清理')
                    logger.info('现有static目录已清理')
                
                add_restore_log('INFO: 正在复制静态文件...')
                logger.info('正在复制静态文件...')
                shutil.copytree(backup_static_dir, static_dir)
                
                file_count = sum([len(files) for r, d, files in os.walk(static_dir)])
                add_restore_log(f'INFO: 静态文件恢复成功，共恢复 {file_count} 个文件')
                logger.info(f'静态文件恢复成功，共恢复 {file_count} 个文件')
            except Exception as e:
                add_restore_log(f'ERROR: 恢复静态文件失败: {str(e)}')
                logger.error(f'恢复静态文件失败: {str(e)}')
                raise RuntimeError(f'恢复静态文件失败: {str(e)}')
        else:
            add_restore_log('WARN: ZIP备份中未包含static目录，跳过静态文件恢复')
            logger.warning('ZIP备份中未包含static目录')
        
        update_progress('running', '恢复数据库...', '正在恢复数据库...', total_steps=4)
        add_restore_log('INFO: 步骤 3/4: 恢复数据库...')
        logger.info('步骤 3/4: 恢复数据库...')
        
        restored_count = _perform_database_restore(backup_data, clear_exclude_tables, db_config)
        
        add_restore_log('INFO: 步骤 4/4: 清理临时文件...')
        logger.info('步骤 4/4: 清理临时文件...')
        
    finally:
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)
    
    update_progress('completed', '恢复完成', f'成功恢复数据库和静态文件', total_steps=4)
    add_restore_log('INFO: 完整备份恢复成功！')
    logger.info('完整备份恢复成功！')
    
    return backup_data.get('version', 'unknown'), backup_data.get('version', 'unknown'), restored_count


def _perform_database_restore(backup_data, clear_exclude_tables, db_config):
    """执行数据库恢复的核心逻辑"""
    import logging
    logger = logging.getLogger(__name__)
    from app.utils.migration import migrate_backup_data, validate_backup_compatibility, CURRENT_VERSION
    import psycopg2
    import psycopg2.extras
    from app import db
    
    is_valid, error_msg = validate_backup_compatibility(backup_data, BACKUP_VERSION)
    if not is_valid:
        raise ValueError(error_msg)

    original_version = backup_data.get('version', '0.0.0')
    backup_data = migrate_backup_data(backup_data, BACKUP_VERSION)

    table_names_to_process = []
    for model in MODEL_ORDER:
        if model.__tablename__ not in clear_exclude_tables:
            table_names_to_process.append(model.__tablename__)

    add_restore_log(f'INFO: 清空表数据... (共 {len(table_names_to_process)} 个表)')
    logger.info('清空表数据...')
    update_progress('running', '清空表数据...', '正在清空表...', total_steps=3, total_tables=len(table_names_to_process))
    
    if db_config is None:
        db_url = db.engine.url
        db_config = {
            'dbname': db_url.database,
            'user': db_url.username,
            'password': db_url.password,
            'host': db_url.host or 'localhost',
            'port': db_url.port or 5432
        }
    
    add_restore_log('INFO: 正在连接数据库...')
    logger.info(f'正在连接数据库: {db_config["dbname"]}@{db_config["host"]}:{db_config["port"]}')
    
    conn = psycopg2.connect(
        dbname=db_config['dbname'],
        user=db_config['user'],
        password=db_config['password'],
        host=db_config['host'],
        port=db_config['port'],
        connect_timeout=10
    )
    conn.autocommit = True
    
    add_restore_log('INFO: 数据库连接成功')
    
    cursor = conn.cursor()
    try:
        add_restore_log('INFO: 正在禁用外键约束检查...')
        cursor.execute("SET session_replication_role = 'replica';")
        add_restore_log('INFO: 外键约束检查已禁用')
        
        if table_names_to_process:
            for idx, table_name in enumerate(table_names_to_process, 1):
                log_msg = f'INFO:   清空表: {table_name} ({idx}/{len(table_names_to_process)})'
                add_restore_log(log_msg)
                logger.info(log_msg)
                cursor.execute(f'TRUNCATE TABLE "{table_name}" CASCADE;')
                update_progress('running', '清空表数据...', f'清空表: {table_name}', total_steps=3, total_tables=len(table_names_to_process), tables_processed=idx)
        
        add_restore_log('INFO: 插入数据...')
        logger.info('插入数据...')
        update_progress('running', '插入数据...', '正在恢复数据...', total_steps=3)
        
        restored_count = 0
        
        for model in MODEL_ORDER:
            table_name = model.__tablename__
            if table_name in backup_data.get('tables', {}):
                records_data = backup_data['tables'][table_name]
                if not records_data:
                    continue
                
                record_count = len(records_data)
                log_msg = f'INFO:   插入表 {table_name}: {record_count} 条记录...'
                add_restore_log(log_msg)
                logger.info(log_msg)
                
                processed_records = []
                columns = list(records_data[0].keys())
                for record_data in records_data:
                    processed_record = []
                    for col in columns:
                        processed_record.append(_convert_datetime(record_data[col]))
                    processed_records.append(tuple(processed_record))
                
                columns_str = ', '.join([f'"{col}"' for col in columns])
                placeholders = ', '.join(['%s'] * len(columns))
                insert_sql = f'INSERT INTO "{table_name}" ({columns_str}) VALUES ({placeholders})'
                
                batch_size = 500 if record_count > 10000 else 1000
                batches_completed = 0
                total_batches = (len(processed_records) + batch_size - 1) // batch_size
                
                for i in range(0, len(processed_records), batch_size):
                    batch = processed_records[i:i+batch_size]
                    try:
                        psycopg2.extras.execute_batch(cursor, insert_sql, batch, page_size=100)
                        restored_count += len(batch)
                        batches_completed += 1
                        
                        if batches_completed % 5 == 0 or batches_completed == total_batches:
                            progress_msg = f'INFO:     {table_name}: {restored_count}/{record_count} 条记录 ({batches_completed}/{total_batches} 批次)'
                            add_restore_log(progress_msg)
                            update_progress('running', '插入数据...', f'{table_name}: {restored_count}/{record_count}', total_steps=3)
                    except Exception as batch_error:
                        raise RuntimeError(f'插入表 {table_name} 第 {batches_completed + 1} 批次时失败: {str(batch_error)}')
        
        cursor.execute("SET session_replication_role = 'origin';")
        
        add_restore_log('INFO: 重置表序列...')
        logger.info('重置表序列...')
        _reset_all_sequences(cursor)
        add_restore_log('INFO: 表序列重置完成')
        logger.info('表序列重置完成')
        
        log_msg = f'INFO: 数据库恢复完成！共恢复 {restored_count} 条记录'
        add_restore_log(log_msg)
        logger.info(log_msg)
        
        cursor.close()
        conn.close()
        
        try:
            from flask import current_app
            with current_app.app_context():
                from flask_login import logout_user
                logout_user()
        except:
            pass
        
        return restored_count
        
    except Exception as e:
        logger.error(f'恢复失败: {str(e)}')
        update_progress('error', '恢复失败', str(e), total_steps=3)
        try:
            cursor.close()
            conn.close()
        except:
            pass
        raise RuntimeError(f'恢复失败: {str(e)}')


def _reset_all_sequences(cursor):
    """重置所有表的序列，避免数据恢复后主键冲突"""
    import logging
    logger = logging.getLogger(__name__)
    
    # 获取所有有 id 字段的表
    tables_to_reset = [model.__tablename__ for model in MODEL_ORDER]
    
    reset_count = 0
    error_count = 0
    
    for table_name in tables_to_reset:
        try:
            seq_name = f'{table_name}_id_seq'
            
            # 获取当前最大 ID
            cursor.execute(f'SELECT MAX(id) FROM "{table_name}"')
            result = cursor.fetchone()
            max_id = result[0] if result and result[0] is not None else 0
            
            # 重置序列
            if max_id > 0:
                cursor.execute(f"SELECT setval('{seq_name}', {max_id + 1}, false)")
                reset_count += 1
                logger.info(f'  重置序列: {table_name} (max_id={max_id}, next_val={max_id + 1})')
        except Exception as e:
            error_count += 1
            logger.warning(f'  跳过表 {table_name}: {str(e)[:100]}')
    
    logger.info(f'序列重置完成: 成功 {reset_count} 个，跳过 {error_count} 个')


def list_backups():
    backup_dir = get_backup_dir()
    backups = []
    for filename in os.listdir(backup_dir):
        if filename.endswith('.json') or filename.endswith('.zip'):
            filepath = os.path.join(backup_dir, filename)
            stat = os.stat(filepath)
            is_full_backup = filename.endswith('.zip')
            backups.append({
                'filename': filename,
                'filepath': filepath,
                'size': stat.st_size,
                'created_at': datetime.datetime.fromtimestamp(stat.st_mtime).isoformat(),
                'is_full_backup': is_full_backup
            })
    backups.sort(key=lambda x: x['created_at'], reverse=True)
    return backups


def delete_backup(filename):
    filepath = os.path.join(get_backup_dir(), filename)
    if os.path.exists(filepath) and (filename.endswith('.json') or filename.endswith('.zip')):
        os.remove(filepath)
        return True
    return False


def clear_database_data():
    from app import db
    for model in reversed(MODEL_ORDER):
        model.query.delete()
    db.session.commit()


def reset_system_data():
    from app import db
    from app.models import User
    
    for model in reversed(MODEL_ORDER):
        model.query.delete()
    
    import secrets
    # 生成16字符的强随机密码
    temp_password = secrets.token_urlsafe(12)
    
    admin = User(
        username='admin',
        email='admin@studyclash.com',
        nickname='管理员',
        role='admin',
        must_change_password=True
    )
    admin.set_password(temp_password)
    db.session.add(admin)
    
    db.session.commit()
    
    return temp_password
