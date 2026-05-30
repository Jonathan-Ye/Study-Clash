"""
添加游戏参与和排行榜显示字段迁移脚本
==================

功能：
1. 给 users 表添加 participate_in_games 字段（默认值 True）
2. 给 users 表添加 show_in_leaderboard 字段（默认值 True）

使用方法：
    python -m migrations.add_game_participation_fields
    或在 Flask shell 中执行:
    from migrations.add_game_participation_fields import run_migration
    run_migration()

回滚方法（如需回滚）：
    python -m migrations.add_game_participation_fields --rollback
"""

import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app, db


def run_migration():
    app = create_app()
    with app.app_context():
        print("开始游戏参与字段迁移...")
        
        # 检查是否已经迁移
        inspector = db.inspect(db.engine)
        
        # 获取 users 表的现有列
        users_columns = [col['name'] for col in inspector.get_columns('users')]
        
        # 1. users 表添加 participate_in_games 字段
        if 'participate_in_games' not in users_columns:
            print("  添加 users.participate_in_games 字段...")
            db.session.execute(db.text(
                "ALTER TABLE users ADD COLUMN participate_in_games BOOLEAN DEFAULT 1"
            ))
            db.session.commit()
            print("  users.participate_in_games 字段添加成功")
        else:
            print("  users.participate_in_games 字段已存在，跳过")
        
        # 2. users 表添加 show_in_leaderboard 字段
        if 'show_in_leaderboard' not in users_columns:
            print("  添加 users.show_in_leaderboard 字段...")
            db.session.execute(db.text(
                "ALTER TABLE users ADD COLUMN show_in_leaderboard BOOLEAN DEFAULT 1"
            ))
            db.session.commit()
            print("  users.show_in_leaderboard 字段添加成功")
        else:
            print("  users.show_in_leaderboard 字段已存在，跳过")
        
        # 3. 创建索引
        try:
            print("  创建索引...")
            db.session.execute(db.text(
                "CREATE INDEX IF NOT EXISTS ix_users_participate_in_games ON users (participate_in_games)"
            ))
            db.session.execute(db.text(
                "CREATE INDEX IF NOT EXISTS ix_users_show_in_leaderboard ON users (show_in_leaderboard)"
            ))
            db.session.commit()
            print("  索引创建成功")
        except Exception as e:
            print(f"  索引创建跳过（可能已存在）: {e}")
        
        # 验证
        print("\n验证迁移结果:")
        total_count = db.session.execute(db.text(
            "SELECT COUNT(*) FROM users"
        )).scalar()
        
        participate_count = db.session.execute(db.text(
            "SELECT COUNT(*) FROM users WHERE participate_in_games = 1"
        )).scalar()
        
        leaderboard_count = db.session.execute(db.text(
            "SELECT COUNT(*) FROM users WHERE show_in_leaderboard = 1"
        )).scalar()
        
        print(f"  总用户数: {total_count}")
        print(f"  参与游戏: {participate_count}")
        print(f"  显示在排行榜: {leaderboard_count}")
        
        print("\n迁移成功完成！")


def rollback():
    app = create_app()
    with app.app_context():
        print("开始回滚游戏参与字段迁移...")
        
        inspector = db.inspect(db.engine)
        users_columns = [col['name'] for col in inspector.get_columns('users')]
        
        if 'participate_in_games' in users_columns:
            print("  删除 users.participate_in_games 字段...")
            db.session.execute(db.text("ALTER TABLE users DROP COLUMN participate_in_games"))
            db.session.commit()
            print("  users.participate_in_games 字段删除成功")
        
        if 'show_in_leaderboard' in users_columns:
            print("  删除 users.show_in_leaderboard 字段...")
            db.session.execute(db.text("ALTER TABLE users DROP COLUMN show_in_leaderboard"))
            db.session.commit()
            print("  users.show_in_leaderboard 字段删除成功")
        
        print("回滚完成！")


if __name__ == '__main__':
    if '--rollback' in sys.argv:
        rollback()
    else:
        run_migration()
