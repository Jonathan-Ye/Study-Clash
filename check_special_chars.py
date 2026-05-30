"""
检查数据库中包含引号或特殊字符的用户数据
这些字符可能导致JavaScript语法错误
"""
import sys
import io

# 设置标准输出编码为UTF-8
if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from app import create_app, db
from app.models.user import User

def check_special_characters():
    app = create_app()
    
    with app.app_context():
        print("=" * 80)
        print("检查包含特殊字符的用户数据")
        print("=" * 80)
        
        # 查询所有用户
        all_users = User.query.all()
        print(f"\n总用户数: {len(all_users)}")
        
        # 需要检查的特殊字符
        special_chars = {
            'single_quote': "'",
            'double_quote': '"',
            'backslash': '\\',
            'newline': '\n',
            'carriage_return': '\r',
            'tab': '\t',
            'backtick': '`',
            'angle_bracket_open': '<',
            'angle_bracket_close': '>',
            'ampersand': '&',
        }
        
        problematic_users = []
        
        for user in all_users:
            issues = []
            
            # 检查 username
            if user.username:
                for char_name, char in special_chars.items():
                    if char in user.username:
                        issues.append({
                            'field': 'username',
                            'value': user.username,
                            'char': char_name,
                            'char_value': repr(char)
                        })
            
            # 检查 nickname
            if user.nickname:
                for char_name, char in special_chars.items():
                    if char in user.nickname:
                        issues.append({
                            'field': 'nickname',
                            'value': user.nickname,
                            'char': char_name,
                            'char_value': repr(char)
                        })
            
            # 检查 real_name
            if user.real_name:
                for char_name, char in special_chars.items():
                    if char in user.real_name:
                        issues.append({
                            'field': 'real_name',
                            'value': user.real_name,
                            'char': char_name,
                            'char_value': repr(char)
                        })
            
            if issues:
                problematic_users.append({
                    'user_id': user.id,
                    'username': user.username,
                    'nickname': user.nickname,
                    'issues': issues
                })
        
        # 输出结果
        if problematic_users:
            print(f"\n⚠️  发现 {len(problematic_users)} 个用户包含特殊字符:\n")
            print("=" * 80)
            
            for user_data in problematic_users:
                print(f"\n用户ID: {user_data['user_id']}")
                print(f"用户名: {repr(user_data['username'])}")
                print(f"昵称: {repr(user_data['nickname'])}")
                print("-" * 80)
                
                for issue in user_data['issues']:
                    print(f"  字段: {issue['field']}")
                    print(f"  值: {issue['value']}")
                    print(f"  包含特殊字符: {issue['char']} ({issue['char_value']})")
                    print()
        else:
            print("\n✅ 未发现包含特殊字符的用户数据")
        
        # 使用SQL直接查询（更精确的方式）
        print("\n" + "=" * 80)
        print("使用SQL直接查询包含引号的用户")
        print("=" * 80)
        
        # 查询包含单引号的用户
        users_with_single_quote = db.session.execute(
            db.text("SELECT id, username, nickname, real_name FROM users WHERE username LIKE :pattern OR nickname LIKE :pattern OR real_name LIKE :pattern"),
            {"pattern": "%'%"}
        ).fetchall()
        
        if users_with_single_quote:
            print(f"\n发现 {len(users_with_single_quote)} 个用户包含单引号 ('):")
            for row in users_with_single_quote:
                print(f"  ID: {row[0]}, username: {repr(row[1])}, nickname: {repr(row[2])}, real_name: {repr(row[3])}")
        
        # 查询包含双引号的用户
        users_with_double_quote = db.session.execute(
            db.text("SELECT id, username, nickname, real_name FROM users WHERE username LIKE :pattern OR nickname LIKE :pattern OR real_name LIKE :pattern"),
            {"pattern": '%"%'}
        ).fetchall()
        
        if users_with_double_quote:
            print(f"\n发现 {len(users_with_double_quote)} 个用户包含双引号 (\"):")
            for row in users_with_double_quote:
                print(f"  ID: {row[0]}, username: {repr(row[1])}, nickname: {repr(row[2])}, real_name: {repr(row[3])}")
        
        # 查询包含换行符的用户
        users_with_newline = db.session.execute(
            db.text("SELECT id, username, nickname, real_name FROM users WHERE username LIKE :pattern OR nickname LIKE :pattern OR real_name LIKE :pattern"),
            {"pattern": "%" + chr(10) + "%"}
        ).fetchall()
        
        if users_with_newline:
            print(f"\n发现 {len(users_with_newline)} 个用户包含换行符:")
            for row in users_with_newline:
                print(f"  ID: {row[0]}, username: {repr(row[1])}, nickname: {repr(row[2])}, real_name: {repr(row[3])}")
        
        # 统计信息
        print("\n" + "=" * 80)
        print("统计信息")
        print("=" * 80)
        
        stats = db.session.execute(
            db.text("""
                SELECT 
                    COUNT(*) as total_users,
                    COUNT(CASE WHEN nickname IS NOT NULL THEN 1 END) as users_with_nickname,
                    COUNT(CASE WHEN real_name IS NOT NULL THEN 1 END) as users_with_real_name
                FROM users
            """)
        ).fetchone()
        
        print(f"总用户数: {stats[0]}")
        print(f"有昵称的用户数: {stats[1]}")
        print(f"有真实姓名的用户数: {stats[2]}")
        
        print("\n" + "=" * 80)

if __name__ == '__main__':
    try:
        check_special_characters()
    except Exception as e:
        print(f"错误: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
