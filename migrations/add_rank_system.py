"""
段位系统数据迁移脚本
==================

功能：
1. 创建 rank_tiers 和 tier_promotion_history 表
2. 插入默认的24个段位配置
3. 给 users 表添加 current_tier_id 和 peak_tier_id 字段
4. 根据现有 total_points 初始化所有用户的段位
5. 验证数据完整性

使用方法：
    python -m migrations.add_rank_system
    或在 Flask shell 中执行:
    from migrations.add_rank_system import run_migration
    run_migration()

回滚方法（如需回滚）：
    python -m migrations/add_rank_system --rollback
"""

import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app, db
from app.models import User, RankTier, TierPromotionHistory
from app.utils.rank_service import RankService


def create_tables():
    """创建新表和字段"""
    print("\n[1/5] Creating database tables and columns...")
    
    try:
        db.create_all()
        print("   [OK] New tables created successfully")
        
        # 检查并添加 users 表的新字段
        from sqlalchemy import inspect
        inspector = inspect(db.engine)
        
        # 获取 users 表的现有列
        existing_columns = [col['name'] for col in inspector.get_columns('users')]
        
        if 'current_tier_id' not in existing_columns:
            print("   [INFO] Adding column: users.current_tier_id...")
            db.session.execute(db.text('ALTER TABLE users ADD COLUMN current_tier_id INTEGER'))
            print("   [OK] Column current_tier_id added")
        else:
            print("   [SKIP] Column current_tier_id already exists")
            
        if 'peak_tier_id' not in existing_columns:
            print("   [INFO] Adding column: users.peak_tier_id...")
            db.session.execute(db.text('ALTER TABLE users ADD COLUMN peak_tier_id INTEGER'))
            print("   [OK] Column peak_tier_id added")
        else:
            print("   [SKIP] Column peak_tier_id already exists")
        
        # 可选：删除旧的 level 和 experience 字段（如果存在）
        if 'level' in existing_columns:
            print("   [INFO] Removing old column: users.level (replaced by tier system)...")
            try:
                db.session.execute(db.text('ALTER TABLE users DROP COLUMN level'))
                print("   [OK] Old column 'level' removed")
            except Exception as e:
                print(f"   [WARN] Could not remove 'level': {e}")
                
        if 'experience' in existing_columns:
            print("   [INFO] Removing old column: users.experience (replaced by tier system)...")
            try:
                db.session.execute(db.text('ALTER TABLE users DROP COLUMN experience'))
                print("   [OK] Old column 'experience' removed")
            except Exception as e:
                print(f"   [WARN] Could not remove 'experience': {e}")
        
        db.session.commit()
        return True
        
    except Exception as e:
        print(f"   [ERROR] Failed to update schema: {e}")
        import traceback
        traceback.print_exc()
        return False


def init_default_tiers():
    """初始化默认段位配置"""
    print("\n[2/5] Initializing default tier configurations...")
    
    try:
        result = RankService.init_default_tiers()
        
        if result['status'] == 'exists':
            print(f"   [WARN] {result['message']}")
            return True
        
        print(f"   [OK] {result['message']}")
        return True
    except Exception as e:
        print(f"   [ERROR] Failed to initialize tiers: {e}")
        return False


def migrate_user_data():
    """迁移用户数据"""
    print("\n[3/5] Migrating user tier data...")
    
    try:
        users = User.query.filter_by(is_active=True).all()
        
        if not users:
            print("   [WARN] No active users found")
            return True
        
        updated = 0
        no_tier = 0
        
        for user in users:
            tier = RankService.calculate_tier_from_points(user.total_points)
            
            if tier:
                user.current_tier_id = tier.id
                user.peak_tier_id = tier.id
                updated += 1
            else:
                no_tier += 1
        
        db.session.commit()
        
        print(f"   [OK] User tier initialization completed")
        print(f"      - Total users: {len(users)}")
        print(f"      - Assigned tiers: {updated}")
        print(f"      - No match: {no_tier}")
        
        return True
    except Exception as e:
        print(f"   [ERROR] Failed to migrate user data: {e}")
        db.session.rollback()
        return False


def verify_data():
    """验证数据完整性"""
    print("\n[4/5] Verifying data integrity...")
    
    try:
        errors = []
        
        # 检查1：段位配置数量
        tier_count = RankTier.query.filter_by(is_active=True).count()
        if tier_count == 0:
            errors.append("No active tier configurations found")
        else:
            print(f"   [OK] Tier configurations count: {tier_count}")
        
        # 检查2：用户段位分配情况
        users_with_tier = User.query.filter(
            User.is_active == True,
            User.current_tier_id.isnot(None)
        ).count()
        
        total_users = User.query.filter_by(is_active=True).count()
        
        print(f"   [OK] Users with tier assigned: {users_with_tier}/{total_users}")
        
        # 检查3：段位配置有效性
        config_errors = RankService.validate_tier_configuration()
        if config_errors:
            errors.extend(config_errors)
            for err in config_errors:
                print(f"   [WARN] Config warning: {err}")
        else:
            print("   [OK] Tier configuration validation passed")
        
        # 检查4：显示段位分布统计
        distribution = RankService.get_tier_distribution()
        
        print("\n   [STATS] Tier distribution:")
        for item in distribution[:8]:  # 只显示前8个
            bar = '#' * min(item['count'] // 10 + 1, 20)
            print(f"      {item['display_name']:12s} | {bar:<22} | {item['count']:>4} users")
        
        if len(distribution) > 8:
            print(f"      ... Total {len(distribution)} tiers")
        
        if errors:
            print(f"\n   [WARN] Found {len(errors)} issue(s)")
            return False
        
        return True
    except Exception as e:
        print(f"   [ERROR] Verification failed: {e}")
        return False


def show_summary():
    """显示迁移总结"""
    print("\n" + "="*60)
    print("[SUCCESS] Rank System Migration Completed!")
    print("="*60)
    
    print("\n[NEXT STEPS]")
    print("   1. Visit admin panel at /admin/rank-tiers/")
    print("   2. Check tier card on user profile page")
    print("   3. View tier distribution on leaderboard")
    
    print("\n[TIPS]")
    print("   - You can adjust point ranges for each tier via admin panel")
    print("   - Click 'Recalculate' after modifying tier configuration")
    print("   - Tiers update in real-time with points (peak tier only goes up)")


def run_migration():
    """运行完整迁移流程"""
    print("="*60)
    print("Study Clash Rank System - Migration Tool")
    print("="*60)
    print(f"\n[TIME] Start time: {__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    app = create_app()
    
    with app.app_context():
        steps = [
            ("Create database tables", create_tables),
            ("Initialize tier configurations", init_default_tiers),
            ("Migrate user data", migrate_user_data),
            ("Verify data integrity", verify_data),
        ]
        
        results = []
        for step_name, step_func in steps:
            success = step_func()
            results.append((step_name, success))
            
            if not success:
                print(f"\n[FAILED] Migration stopped at step: {step_name}")
                print("Please check error messages and fix issues before retrying")
                return False
        
        show_summary()
        return True


def rollback():
    """回滚迁移"""
    print("="*60)
    print("[ROLLBACK] Rank System Migration - Rollback Operation")
    print("="*60)
    
    confirm = input("\n[CONFIRM] Are you sure you want to rollback? This will DELETE all rank-related data! (yes/no): ")
    
    if confirm.lower() != 'yes':
        print("[CANCELLED] Rollback cancelled")
        return False
    
    app = create_app()
    
    with app.app_context():
        try:
            print("\n[CLEANUP] Removing tier promotion history records...")
            count = TierPromotionHistory.query.delete()
            print(f"   Deleted {count} records")
            
            print("\n[CLEANUP] Removing tier configurations...")
            count = RankTier.query.delete()
            print(f"   Deleted {count} tier configurations")
            
            print("\n[RESET] Resetting user tier fields...")
            User.query.update({
                User.current_tier_id: None,
                User.peak_tier_id: None
            })
            
            db.session.commit()
            
            print("\n[SUCCESS] Rollback completed!")
            return True
        except Exception as e:
            print(f"\n[ERROR] Rollback failed: {e}")
            db.session.rollback()
            return False


if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == '--rollback':
        rollback()
    else:
        run_migration()
