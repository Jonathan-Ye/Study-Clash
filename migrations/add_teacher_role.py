"""
教师角色权限系统数据迁移脚本
==================

功能：
1. 给 users 表添加 role 字段（默认值 'student'）
2. 给 users 表添加 created_by 字段
3. 给 questions 表添加 created_by 字段
4. 给 subjects 表添加 created_by 字段
5. 将现有 is_admin=True 的用户更新为 role='admin'
6. 验证数据完整性

使用方法：
    python -m migrations.add_teacher_role
    或在 Flask shell 中执行:
    from migrations.add_teacher_role import run_migration
    run_migration()

回滚方法（如需回滚）：
    python -m migrations.add_teacher_role --rollback
"""

import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app, db


def run_migration():
    app = create_app()
    with app.app_context():
        print("开始教师角色权限系统迁移...")
        
        # 检查是否已经迁移
        inspector = db.inspect(db.engine)
        
        # 1. users 表添加 role 字段
        users_columns = [col['name'] for col in inspector.get_columns('users')]
        if 'role' not in users_columns:
            print("  添加 users.role 字段...")
            db.session.execute(db.text(
                "ALTER TABLE users ADD COLUMN role VARCHAR(20) DEFAULT 'student' NOT NULL"
            ))
            db.session.commit()
            print("  users.role 字段添加成功")
        else:
            print("  users.role 字段已存在，跳过")
        
        # 2. users 表添加 created_by 字段
        if 'created_by' not in users_columns:
            print("  添加 users.created_by 字段...")
            db.session.execute(db.text(
                "ALTER TABLE users ADD COLUMN created_by INTEGER REFERENCES users(id)"
            ))
            db.session.commit()
            print("  users.created_by 字段添加成功")
        else:
            print("  users.created_by 字段已存在，跳过")
        
        # 3. questions 表添加 created_by 字段
        questions_columns = [col['name'] for col in inspector.get_columns('questions')]
        if 'created_by' not in questions_columns:
            print("  添加 questions.created_by 字段...")
            db.session.execute(db.text(
                "ALTER TABLE questions ADD COLUMN created_by INTEGER REFERENCES users(id)"
            ))
            db.session.commit()
            print("  questions.created_by 字段添加成功")
        else:
            print("  questions.created_by 字段已存在，跳过")
        
        # 4. subjects 表添加 created_by 字段
        subjects_columns = [col['name'] for col in inspector.get_columns('subjects')]
        if 'created_by' not in subjects_columns:
            print("  添加 subjects.created_by 字段...")
            db.session.execute(db.text(
                "ALTER TABLE subjects ADD COLUMN created_by INTEGER REFERENCES users(id)"
            ))
            db.session.commit()
            print("  subjects.created_by 字段添加成功")
        else:
            print("  subjects.created_by 字段已存在，跳过")
        
        # 5. 迁移现有数据：将 is_admin=True 的用户更新为 role='admin'
        print("  迁移现有管理员数据...")
        result = db.session.execute(db.text(
            "UPDATE users SET role = 'admin' WHERE is_admin = 1"
        ))
        db.session.commit()
        print(f"  已将 {result.rowcount} 个管理员用户的 role 更新为 'admin'")
        
        # 6. 创建索引
        try:
            print("  创建索引...")
            db.session.execute(db.text(
                "CREATE INDEX IF NOT EXISTS ix_users_role ON users (role)"
            ))
            db.session.commit()
            print("  索引创建成功")
        except Exception as e:
            print(f"  索引创建跳过（可能已存在）: {e}")
        
        # 验证
        print("\n验证迁移结果:")
        admin_count = db.session.execute(db.text(
            "SELECT COUNT(*) FROM users WHERE role = 'admin'"
        )).scalar()
        teacher_count = db.session.execute(db.text(
            "SELECT COUNT(*) FROM users WHERE role = 'teacher'"
        )).scalar()
        student_count = db.session.execute(db.text(
            "SELECT COUNT(*) FROM users WHERE role = 'student'"
        )).scalar()
        total_count = db.session.execute(db.text(
            "SELECT COUNT(*) FROM users"
        )).scalar()
        
        print(f"  总用户数: {total_count}")
        print(f"  管理员: {admin_count}")
        print(f"  教师: {teacher_count}")
        print(f"  学生: {student_count}")
        
        if admin_count + teacher_count + student_count == total_count:
            print("\n迁移成功完成！")
        else:
            print("\n警告：角色数量与总用户数不匹配，请检查！")


def rollback():
    app = create_app()
    with app.app_context():
        print("开始回滚教师角色权限系统迁移...")
        
        inspector = db.inspect(db.engine)
        users_columns = [col['name'] for col in inspector.get_columns('users')]
        questions_columns = [col['name'] for col in inspector.get_columns('questions')]
        subjects_columns = [col['name'] for col in inspector.get_columns('subjects')]
        
        if 'role' in users_columns:
            print("  删除 users.role 字段...")
            db.session.execute(db.text("ALTER TABLE users DROP COLUMN role"))
            db.session.commit()
        
        if 'created_by' in users_columns:
            print("  删除 users.created_by 字段...")
            db.session.execute(db.text("ALTER TABLE users DROP COLUMN created_by"))
            db.session.commit()
        
        if 'created_by' in questions_columns:
            print("  删除 questions.created_by 字段...")
            db.session.execute(db.text("ALTER TABLE questions DROP COLUMN created_by"))
            db.session.commit()
        
        if 'created_by' in subjects_columns:
            print("  删除 subjects.created_by 字段...")
            db.session.execute(db.text("ALTER TABLE subjects DROP COLUMN created_by"))
            db.session.commit()
        
        print("回滚完成！")


if __name__ == '__main__':
    if '--rollback' in sys.argv:
        rollback()
    else:
        run_migration()
