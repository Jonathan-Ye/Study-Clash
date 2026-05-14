import eventlet
eventlet.monkey_patch()

import os
import sys
import getpass

env = os.environ.get('FLASK_ENV', 'development')

from app import create_app, db, socketio
from app.models import User, Subject, Chapter, Question
from app.utils.common import DEFAULT_SUBJECTS_DATA
from sqlalchemy import text

app = create_app(env)

@app.shell_context_processor
def make_shell_context():
    return {
        'db': db,
        'User': User,
        'Subject': Subject,
        'Chapter': Chapter,
        'Question': Question
    }

@app.cli.command('init-db')
def init_db():
    with app.app_context():
        db.create_all()
        
        admin = User.query.filter_by(username='admin').first()
        if not admin:
            admin = User(
                username='admin',
                email='admin@studyclash.com',
                nickname='管理员',
                role='admin',
                must_change_password=True
            )
            admin.set_password('admin123')
            db.session.add(admin)
            print('管理员账号创建成功！')
        else:
            print('管理员账号已存在，跳过...')
        
        for name, icon in DEFAULT_SUBJECTS_DATA:
            if not Subject.query.filter_by(name=name).first():
                subject = Subject(name=name, icon=icon)
                db.session.add(subject)
        
        from app.models.system import SystemSetting
        default_settings = [
            ('registration_enabled', 'true', '允许用户注册'),
            ('password_policy_enabled', 'false', '启用密码复杂度策略'),
            ('password_min_length', '8', '最小密码长度'),
            ('password_require_uppercase', 'true', '密码要求大写字母'),
            ('password_require_lowercase', 'true', '密码要求小写字母'),
            ('password_require_digit', 'true', '密码要求数字'),
            ('password_require_special', 'true', '密码要求特殊字符'),
            ('max_login_attempts', '5', '最大登录尝试次数'),
            ('lockout_duration', '30', '锁定时长（分钟）'),
            ('session_lifetime_hours', '2', '用户会话有效时长（小时）'),
            ('wrong_consecutive_correct', '3', '错题掌握需要连续正确次数'),
            ('wrong_review_points', '5', '错题复习正确获得积分'),
            ('wrong_max_review_per_day', '50', '每日最大复习数量'),
            ('wrong_enable_spaced_review', 'true', '是否启用间隔复习'),
        ]
        
        for key, value, desc in default_settings:
            if not SystemSetting.query.filter_by(key=key).first():
                setting = SystemSetting(key=key, value=value, description=desc)
                db.session.add(setting)
        
        db.session.commit()
        print('数据库初始化完成！')
        print('管理员账号: admin (请登录后立即修改密码)')

@app.cli.command('migrate-db')
def migrate_db():
    with app.app_context():
        try:
            db.session.execute(text('ALTER TABLE game_rooms ADD COLUMN expires_at DATETIME'))
            db.session.commit()
            print('数据库迁移完成：添加 expires_at 字段')
        except Exception as e:
            if 'duplicate column' in str(e).lower() or 'already exists' in str(e).lower():
                print('expires_at 字段已存在，跳过迁移')
            else:
                print(f'迁移错误: {e}')
        
        try:
            db.session.execute(text('ALTER TABLE game_players ADD COLUMN wrong_chances_used INTEGER DEFAULT 0'))
            db.session.commit()
            print('数据库迁移完成：添加 wrong_chances_used 字段')
        except Exception as e:
            if 'duplicate column' in str(e).lower() or 'already exists' in str(e).lower():
                print('wrong_chances_used 字段已存在，跳过迁移')
            else:
                print(f'迁移错误: {e}')
        
        try:
            db.session.execute(text('ALTER TABLE game_players ADD COLUMN game_over BOOLEAN DEFAULT 0'))
            db.session.commit()
            print('数据库迁移完成：添加 game_over 字段')
        except Exception as e:
            if 'duplicate column' in str(e).lower() or 'already exists' in str(e).lower():
                print('game_over 字段已存在，跳过迁移')
            else:
                print(f'迁移错误: {e}')
        
        try:
            db.session.execute(text('ALTER TABLE users ADD COLUMN must_change_password BOOLEAN DEFAULT 0'))
            db.session.commit()
            print('数据库迁移完成：添加 must_change_password 字段')
        except Exception as e:
            if 'duplicate column' in str(e).lower() or 'already exists' in str(e).lower():
                print('must_change_password 字段已存在，跳过迁移')
            else:
                print(f'迁移错误: {e}')
        
        try:
            db.session.execute(text('ALTER TABLE users ADD COLUMN participate_in_games BOOLEAN DEFAULT 1'))
            db.session.commit()
            print('数据库迁移完成：添加 participate_in_games 字段')
        except Exception as e:
            if 'duplicate column' in str(e).lower() or 'already exists' in str(e).lower():
                print('participate_in_games 字段已存在，跳过迁移')
            else:
                print(f'迁移错误: {e}')
        
        try:
            db.session.execute(text('ALTER TABLE users ADD COLUMN show_in_leaderboard BOOLEAN DEFAULT 1'))
            db.session.commit()
            print('数据库迁移完成：添加 show_in_leaderboard 字段')
        except Exception as e:
            if 'duplicate column' in str(e).lower() or 'already exists' in str(e).lower():
                print('show_in_leaderboard 字段已存在，跳过迁移')
            else:
                print(f'迁移错误: {e}')
        
        # 添加性能优化索引
        indexes = [
            ("idx_questions_subject_active", "CREATE INDEX CONCURRENTLY idx_questions_subject_active ON questions(subject_id, is_active)"),
            ("idx_questions_chapter_active", "CREATE INDEX CONCURRENTLY idx_questions_chapter_active ON questions(chapter_id, is_active)"),
            ("idx_questions_subject_chapter_active", "CREATE INDEX CONCURRENTLY idx_questions_subject_chapter_active ON questions(subject_id, chapter_id, is_active)"),
            ("idx_questions_difficulty_active", "CREATE INDEX CONCURRENTLY idx_questions_difficulty_active ON questions(difficulty, is_active)"),
            ("idx_game_rooms_status_expires", "CREATE INDEX CONCURRENTLY idx_game_rooms_status_expires ON game_rooms(status, expires_at)"),
            ("idx_game_rooms_status_created", "CREATE INDEX CONCURRENTLY idx_game_rooms_status_created ON game_rooms(status, created_at)"),
            ("idx_game_rooms_status_ended", "CREATE INDEX CONCURRENTLY idx_game_rooms_status_ended ON game_rooms(status, ended_at)"),
        ]
        
        # PostgreSQL 使用 CONCURRENTLY，SQLite 不支持
        is_pg = app.config['SQLALCHEMY_DATABASE_URI'].startswith('postgresql')
        
        for idx_name, sql in indexes:
            try:
                if is_pg:
                    db.session.execute(text(sql))
                else:
                    clean_sql = sql.replace('CONCURRENTLY ', '')
                    db.session.execute(text(f"CREATE INDEX IF NOT EXISTS {idx_name} ON {clean_sql.split(f'{idx_name} ON ')[1]}"))
                db.session.commit()
                print(f'索引创建成功：{idx_name}')
            except Exception as e:
                if 'already exists' in str(e).lower() or 'duplicate' in str(e).lower():
                    print(f'索引已存在：{idx_name}')
                else:
                    print(f'索引创建跳过 {idx_name}: {e}')
        
        db.session.commit()

@app.cli.command('backup-db')
def backup_db():
    from app.utils.backup import create_backup
    with app.app_context():
        filepath = create_backup()
        print(f'数据库备份成功！备份文件: {filepath}')


@app.cli.command('restore-db')
def restore_db():
    from app.utils.backup import restore_backup, list_backups
    
    if len(sys.argv) < 3:
        print('用法: flask restore-db <备份文件名>')
        print('\n可用的备份文件:')
        with app.app_context():
            backups = list_backups()
            for backup in backups:
                print(f'  - {backup["filename"]}')
        return
    
    filename = sys.argv[2]
    with app.app_context():
        from app.utils.backup import get_backup_dir
        filepath = os.path.join(get_backup_dir(), filename)
        
        if not os.path.exists(filepath):
            print(f'错误: 备份文件 {filename} 不存在！')
            return
        
        confirm = input('警告: 此操作将覆盖当前数据库！确认继续? (yes/no): ')
        if confirm.lower() != 'yes':
            print('操作已取消')
            return
        
        try:
            new_version, original_version = restore_backup(filepath)
            if new_version != original_version:
                print(f'数据库恢复成功！数据已从版本 {original_version} 迁移到 {new_version}')
            else:
                print(f'数据库恢复成功！备份版本: {new_version}')
        except Exception as e:
            print(f'恢复失败: {e}')


@app.cli.command('list-backups')
def list_backups_cmd():
    from app.utils.backup import list_backups
    with app.app_context():
        backups = list_backups()
        if not backups:
            print('没有找到备份文件')
            return
        
        print(f'找到 {len(backups)} 个备份文件:')
        for i, backup in enumerate(backups, 1):
            size_mb = backup['size'] / (1024 * 1024)
            print(f'{i}. {backup["filename"]}')
            print(f'   大小: {size_mb:.2f} MB')
            print(f'   创建时间: {backup["created_at"]}')
            print()


@app.cli.command('delete-backup')
def delete_backup_cmd():
    if len(sys.argv) < 3:
        print('用法: flask delete-backup <备份文件名>')
        return
    
    filename = sys.argv[2]
    with app.app_context():
        from app.utils.backup import delete_backup
        if delete_backup(filename):
            print(f'备份文件 {filename} 已删除')
        else:
            print(f'错误: 备份文件 {filename} 不存在')


@app.cli.command('reset-admin-password')
def reset_admin_password():
    """交互式重置管理员密码"""
    with app.app_context():
        print('=== 管理员密码重置 ===')
        username = input('请输入管理员用户名: ').strip()
        if not username:
            print('错误: 用户名不能为空')
            return

        user = User.query.filter_by(username=username).first()
        if not user:
            print('错误: 用户不存在')
            return
        if user.role != 'admin':
            print('错误: 该用户不是管理员')
            return

        print(f'找到管理员: {user.username} (邮箱: {user.email})')
        new_password = getpass.getpass('请输入新密码: ')
        if not new_password:
            print('错误: 密码不能为空')
            return

        confirm_password = getpass.getpass('请确认新密码: ')
        if new_password != confirm_password:
            print('错误: 两次输入的密码不一致')
            return

        from app.utils.security import validate_password
        is_valid, errors = validate_password(new_password)
        if not is_valid:
            print('密码不符合策略要求:')
            for err in errors:
                print(f'  - {err}')
            return

        user.set_password(new_password)
        user.must_change_password = True
        db.session.commit()

        try:
            from app.utils.op_log import log_operation
            log_operation('reset_password', 'security', target_name=username,
                          detail='通过CLI命令重置管理员密码')
        except Exception:
            pass

        print(f'管理员 {username} 的密码已重置成功！')
        print('首次登录后将强制修改密码。')


def main():
    is_production = env == 'production'
    
    print('=' * 50)
    mode_name = '生产' if is_production else '开发'
    print(f'Study Clash {mode_name}服务器启动中...')
    print('=' * 50)
    print(f'环境模式: {env}')
    print(f'访问地址: http://127.0.0.1:5002')
    print('=' * 50)
    
    socketio.run(
        app,
        host='0.0.0.0',
        port=5002,
        debug=not is_production,
        use_reloader=True,
        allow_unsafe_werkzeug=True
    )


if __name__ == '__main__':
    main()
