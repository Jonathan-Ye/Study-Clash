from app import db
from app.models import User, RankTier, TierPromotionHistory
from sqlalchemy import func, case, or_, and_, desc

class RankService:
    
    @classmethod
    def get_tier_by_id(cls, tier_id):
        return RankTier.query.get(tier_id)
    
    @classmethod
    def calculate_tier_from_points(cls, points):
        if points is None:
            points = 0
        
        sub_tier_order = case(
            (RankTier.sub_tier == 'I', 3),
            (RankTier.sub_tier == 'II', 2),
            (RankTier.sub_tier == 'III', 1),
            else_=0
        )
        
        tier = RankTier.query.filter(
            RankTier.is_active == True,
            RankTier.min_points <= points
        ).filter(
            or_(RankTier.max_points.is_(None),
                RankTier.max_points >= points)
        ).order_by(
            desc(RankTier.tier_order),
            desc(sub_tier_order)
        ).first()
        
        return tier
    
    @classmethod
    def get_user_current_tier(cls, user):
        if not user.current_tier_id:
            return cls.calculate_tier_from_points(user.total_points)
        
        calculated_tier = cls.calculate_tier_from_points(user.total_points)
        
        if calculated_tier and calculated_tier.id != user.current_tier_id:
            return calculated_tier
        
        return user.current_tier
    
    @classmethod
    def get_tier_progress(cls, user):
        tier = cls.get_user_current_tier(user)
        
        if not tier:
            return {
                'progress': 0,
                'current': 0,
                'required_min': 0,
                'required_max': 100,
                'points_to_next': 0,
                'next_tier_name': None
            }
        
        current_points = user.total_points
        min_pts = tier.min_points
        max_pts = tier.max_points if tier.max_points else (min_pts + 50000)
        
        if max_pts == min_pts:
            progress = 100
        else:
            progress = ((current_points - min_pts) / (max_pts - min_pts)) * 100
        
        progress = max(0, min(100, round(progress, 1)))
        
        next_tier = cls._get_next_tier(tier)
        
        return {
            'progress': progress,
            'current': current_points,
            'required_min': min_pts,
            'required_max': max_pts,
            'points_in_tier': max(0, current_points - min_pts),
            'points_to_next': max(0, max_pts - current_points),
            'next_tier': next_tier.to_dict() if next_tier else None
        }
    
    @classmethod
    def _get_next_tier(cls, current_tier):
        sub_tier_order = case(
            (RankTier.sub_tier == 'III', 1),
            (RankTier.sub_tier == 'II', 2),
            (RankTier.sub_tier == 'I', 3),
            else_=0
        )
        
        next_tier = RankTier.query.filter(
            RankTier.is_active == True,
            RankTier.tier_order >= current_tier.tier_order
        ).filter(
            or_(
                RankTier.tier_order > current_tier.tier_order,
                and_(
                    RankTier.tier_order == current_tier.tier_order,
                    sub_tier_order > case(
                        (current_tier.sub_tier == 'III', 1),
                        (current_tier.sub_tier == 'II', 2),
                        (current_tier.sub_tier == 'I', 3),
                        else_=0
                    )
                )
            )
        ).order_by(
            RankTier.tier_order.asc(),
            sub_tier_order.asc()
        ).first()
        
        return next_tier
    
    @classmethod
    def get_all_tiers_ordered(cls):
        sub_tier_order = case(
            (RankTier.sub_tier == 'III', 1),
            (RankTier.sub_tier == 'II', 2),
            (RankTier.sub_tier == 'I', 3),
            else_=0
        )
        
        return RankTier.query.filter_by(is_active=True)\
                   .order_by(RankTier.tier_order.asc(), sub_tier_order.asc())\
                   .all()
    
    @classmethod
    def get_tier_distribution(cls):
        distribution = db.session.query(
            RankTier.id,
            RankTier.tier_name,
            RankTier.sub_tier,
            func.count(User.id).label('count')
        ).outerjoin(User, User.current_tier_id == RankTier.id)\
         .group_by(RankTier.id, RankTier.tier_name, RankTier.sub_tier)\
         .order_by(RankTier.tier_order.asc()).all()
        
        result = []
        for row in distribution:
            result.append({
                'tier_id': row[0],
                'tier_name': row[1],
                'sub_tier': row[2],
                'display_name': f"{row[1]} {row[2]}",
                'count': row[3]
            })
        
        return result
    
    @classmethod
    def recalculate_all_users_tiers(cls):
        users = User.query.filter_by(is_active=True).all()
        updated_count = 0
        
        for user in users:
            old_tier_id = user.current_tier_id
            new_tier = cls.calculate_tier_from_points(user.total_points)
            
            if new_tier:
                user.current_tier_id = new_tier.id
                
                if user.peak_tier_id is None:
                    user.peak_tier_id = new_tier.id
                else:
                    peak_tier = cls.get_tier_by_id(user.peak_tier_id)
                    if peak_tier and (new_tier.tier_order > peak_tier.tier_order or 
                                    (new_tier.tier_order == peak_tier.tier_order and 
                                     cls._compare_sub_tiers(new_tier.sub_tier, peak_tier.sub_tier) > 0)):
                        user.peak_tier_id = new_tier.id
                
                if old_tier_id and old_tier_id != new_tier.id:
                    try:
                        record = TierPromotionHistory(
                            user_id=user.id,
                            from_tier_id=old_tier_id,
                            to_tier_id=new_tier.id,
                            points_at_change=user.total_points
                        )
                        db.session.add(record)
                    except Exception as e:
                        print(f"记录用户 {user.id} 段位变更失败: {e}")
                    
                    updated_count += 1
        
        db.session.commit()
        
        return {
            'total_users': len(users),
            'affected_users': updated_count
        }
    
    @classmethod
    def _compare_sub_tiers(cls, sub1, sub2):
        order = {'III': 1, 'II': 2, 'I': 3}
        return order.get(sub1, 0) - order.get(sub2, 0)
    
    @classmethod
    def get_user_tier_history(cls, user_id, page=1, per_page=20):
        history = TierPromotionHistory.query.filter_by(user_id=user_id)\
                   .order_by(TierPromotionHistory.changed_at.desc())\
                   .paginate(page=page, per_page=per_page)
        
        return history
    
    @classmethod
    def init_default_tiers(cls, force=False):
        # 将 default_tiers 定义提前
        default_tiers = [
            ('青铜', 1, 'III', 0, 99, 'bronze_3.svg', '#CD7F32'),
            ('青铜', 1, 'II', 100, 199, 'bronze_2.svg', '#CD7F32'),
            ('青铜', 1, 'I', 200, 299, 'bronze_1.svg', '#CD7F32'),
            ('白银', 2, 'III', 300, 449, 'silver_3.svg', '#C0C0C0'),
            ('白银', 2, 'II', 450, 599, 'silver_2.svg', '#C0C0C0'),
            ('白银', 2, 'I', 600, 799, 'silver_1.svg', '#C0C0C0'),
            ('黄金', 3, 'III', 800, 1099, 'gold_3.svg', '#FFD700'),
            ('黄金', 3, 'II', 1100, 1399, 'gold_2.svg', '#FFD700'),
            ('黄金', 3, 'I', 1400, 1799, 'gold_1.svg', '#FFD700'),
            ('铂金', 4, 'III', 1800, 2399, 'platinum_3.svg', '#E5E4E2'),
            ('铂金', 4, 'II', 2400, 2999, 'platinum_2.svg', '#E5E4E2'),
            ('铂金', 4, 'I', 3000, 3799, 'platinum_1.svg', '#E5E4E2'),
            ('钻石', 5, 'III', 3800, 4999, 'diamond_3.svg', '#B9F2FF'),
            ('钻石', 5, 'II', 5000, 6199, 'diamond_2.svg', '#B9F2FF'),
            ('钻石', 5, 'I', 6200, 7999, 'diamond_1.svg', '#B9F2FF'),
            ('大师', 6, 'III', 8000, 9999, 'master_3.svg', '#FF6B35'),
            ('大师', 6, 'II', 10000, 12499, 'master_2.svg', '#FF6B35'),
            ('大师', 6, 'I', 12500, 15999, 'master_1.svg', '#FF6B35'),
            ('王者', 7, 'III', 16000, 20999, 'king_3.svg', '#FF0000'),
            ('王者', 7, 'II', 21000, 25999, 'king_2.svg', '#FF0000'),
            ('王者', 7, 'I', 26000, 34999, 'king_1.svg', '#FF0000'),
            ('传奇', 8, 'I', 35000, None, 'legend_1.svg', '#9400D3'),
        ]
        
        # 如果已有段位数据且不强制，直接跳过
        if not force and RankTier.query.first():
            return None
        
        if force:
            # 先检查是否有用户引用这些段位
            users_with_tiers = db.session.execute(
                db.text("SELECT COUNT(*) FROM users WHERE current_tier_id IS NOT NULL OR peak_tier_id IS NOT NULL")
            ).scalar()
            
            if users_with_tiers > 0:
                # 有用户引用，不删除，只更新/插入缺失的段位
                for name, order, sub, min_pt, max_pt, icon, color in default_tiers:
                    existing = RankTier.query.filter_by(tier_order=order, sub_tier=sub).first()
                    if not existing:
                        tier = RankTier(
                            tier_name=name, tier_order=order, sub_tier=sub,
                            min_points=min_pt, max_points=max_pt, icon=icon, color=color
                        )
                        db.session.add(tier)
                        db.session.commit()
                return {'inserted': 0, 'skipped': users_with_tiers}
            else:
                # 没有用户引用，可以安全删除
                RankTier.query.delete()
                db.session.commit()
        
        for name, order, sub, min_pt, max_pt, icon, color in default_tiers:
            tier = RankTier(
                tier_name=name,
                tier_order=order,
                sub_tier=sub,
                min_points=min_pt,
                max_points=max_pt,
                icon=icon,
                color=color,
                is_active=True
            )
            db.session.add(tier)
        
        db.session.commit()
        
        return {
            'status': 'created',
            'message': f'已创建 {len(default_tiers)} 个默认段位配置'
        }
    
    @classmethod
    def validate_tier_configuration(cls):
        tiers = cls.get_all_tiers_ordered()
        errors = []
        
        for i in range(len(tiers) - 1):
            current = tiers[i]
            next_tier = tiers[i + 1]
            
            if current.max_points and next_tier.min_points > current.max_points + 1:
                errors.append(
                    f"间隙：{current.display_name} 结束于 {current.max_points}，"
                    f"但 {next_tier.display_name} 从 {next_tier.min_points} 开始"
                )
            
            if current.max_points and next_tier.min_points < current.min_points:
                errors.append(
                    f"重叠：{current.display_name} 和 {next_tier.display_name}"
                )
        
        tier_groups = {}
        for t in tiers:
            tier_groups.setdefault(t.tier_name, []).append(t.sub_tier)
        
        for name, subs in tier_groups.items():
            if len(subs) not in [1, 3]:
                errors.append(f"段位 {name} 有 {len(subs)} 个子段位，预期1或3个")
        
        return errors
