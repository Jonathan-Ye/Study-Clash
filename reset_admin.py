import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from app import create_app, db
from app.models import User

app = create_app('development')

with app.app_context():
    # 查找 admin 用户
    admin = User.query.filter_by(username='admin').first()
    
    if admin:
        # 重置密码
        admin.set_password('admin123')
        admin.must_change_password = True
        db.session.commit()
        print('[OK] 管理员 admin 的密码已重置为: admin123')
        print('[OK] 请登录后立即修改密码')
    else:
        # 创建 admin 用户
        admin = User(
            username='admin',
            email='admin@studyclash.com',
            nickname='管理员',
            role='admin',
            must_change_password=True
        )
        admin.set_password('admin123')
        db.session.add(admin)
        db.session.commit()
        print('[OK] 管理员账号已创建')
        print('[OK] 用户名: admin')
        print('[OK] 密码: admin123')
        print('[OK] 请登录后立即修改密码')
