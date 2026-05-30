import pytest
from app.models.user import User
from app.models.points import PointRecord
from app.models.ranks import RankTier
from app import db


class TestPointsSystem:
    """积分系统测试"""

    def test_add_points(self, app, regular_user):
        """测试增加积分"""
        with app.app_context():
            initial_points = regular_user.total_points
            regular_user.add_points(10, '测试加分')
            db.session.commit()
            
            assert regular_user.total_points == initial_points + 10
            
            record = PointRecord.query.filter_by(
                user_id=regular_user.id,
                points=10
            ).first()
            assert record is not None
            assert record.reason == '测试加分'

    def test_deduct_points(self, app, regular_user):
        """测试扣除积分"""
        with app.app_context():
            initial_points = regular_user.total_points
            regular_user.add_points(-5, '测试扣分')
            db.session.commit()
            
            assert regular_user.total_points == initial_points - 5

    def test_point_record_creation(self, app, regular_user):
        """测试积分记录创建"""
        with app.app_context():
            regular_user.add_points(20, '游戏胜利')
            db.session.commit()
            
            records = PointRecord.query.filter_by(
                user_id=regular_user.id
            ).all()
            
            assert len(records) >= 1
            assert records[-1].points == 20
            assert records[-1].reason == '游戏胜利'

    def test_point_history(self, app, regular_user):
        """测试积分历史查询"""
        with app.app_context():
            regular_user.add_points(10, '记录1')
            regular_user.add_points(20, '记录2')
            regular_user.add_points(-5, '记录3')
            db.session.commit()
            
            history = PointRecord.query.filter_by(
                user_id=regular_user.id
            ).order_by(PointRecord.created_at.desc()).all()
            
            assert len(history) >= 3

    def test_rank_tier_update(self, app, regular_user):
        """测试段位更新"""
        with app.app_context():
            initial_tier = regular_user.current_tier_id
            regular_user.add_points(100, '大量加分')
            regular_user.update_tier()
            db.session.commit()
            
            assert regular_user.total_points >= 100

    def test_total_points_calculation(self, app, regular_user):
        """测试总积分计算"""
        with app.app_context():
            regular_user.add_points(50, '加50')
            regular_user.add_points(30, '加30')
            regular_user.add_points(-10, '减10')
            db.session.commit()
            
            assert regular_user.total_points == 70

    def test_point_record_timestamp(self, app, regular_user):
        """测试积分记录时间戳"""
        with app.app_context():
            regular_user.add_points(15, '时间测试')
            db.session.commit()
            
            record = PointRecord.query.filter_by(
                user_id=regular_user.id,
                points=15
            ).first()
            
            assert record.created_at is not None

    def test_multiple_point_operations(self, app, regular_user):
        """测试多次积分操作"""
        with app.app_context():
            operations = [10, 20, -5, 15, -10, 30]
            
            for points in operations:
                regular_user.add_points(points, f'操作: {points}')
            
            db.session.commit()
            
            expected_total = sum(operations)
            assert regular_user.total_points == expected_total
            
            records = PointRecord.query.filter_by(
                user_id=regular_user.id
            ).all()
            
            assert len(records) >= len(operations)

    def test_point_record_sorting(self, app, regular_user):
        """测试积分记录排序"""
        with app.app_context():
            regular_user.add_points(10, '第一条')
            regular_user.add_points(20, '第二条')
            regular_user.add_points(30, '第三条')
            db.session.commit()
            
            records = PointRecord.query.filter_by(
                user_id=regular_user.id
            ).order_by(PointRecord.created_at.desc()).all()
            
            for i in range(len(records) - 1):
                assert records[i].created_at >= records[i+1].created_at

    def test_point_statistics(self, app, regular_user):
        """测试积分统计"""
        with app.app_context():
            regular_user.add_points(50, '统计测试1')
            regular_user.add_points(30, '统计测试2')
            regular_user.add_points(-20, '统计测试3')
            db.session.commit()
            
            total_earned = db.session.query(
                db.func.sum(PointRecord.points)
            ).filter(
                PointRecord.user_id == regular_user.id,
                PointRecord.points > 0
            ).scalar() or 0
            
            total_spent = db.session.query(
                db.func.sum(PointRecord.points)
            ).filter(
                PointRecord.user_id == regular_user.id,
                PointRecord.points < 0
            ).scalar() or 0
            
            assert total_earned == 80
            assert total_spent == -20
