from flask import Blueprint, render_template, request, jsonify, redirect, url_for, flash
from flask_login import login_required, current_user
from app import db, csrf
from app.models import RankTier, User, TierPromotionHistory
from app.utils.rank_service import RankService
from app.routes.admin import admin_bp

@admin_bp.route('/rank-tiers/')
@login_required
def rank_tiers_index():
    if not current_user.is_admin:
        flash('无权访问', 'error')
        return redirect(url_for('main.index'))
    
    tiers = RankService.get_all_tiers_ordered()
    distribution = RankService.get_tier_distribution()
    
    dist_map = {d['tier_id']: d['count'] for d in distribution}
    
    return render_template('admin/rank_tiers.html', 
                          tiers=tiers, 
                          distribution=dist_map)

@admin_bp.route('/rank-tiers/api/tiers')
@login_required
def api_get_tiers():
    if not current_user.is_admin:
        return jsonify({'error': '无权操作'}), 403
    
    tiers = RankService.get_all_tiers_ordered()
    return jsonify({
        'tiers': [t.to_dict() for t in tiers],
        'total': len(tiers)
    })

@admin_bp.route('/rank-tiers/api/tiers/<int:tier_id>', methods=['GET'])
@login_required
def api_get_tier(tier_id):
    if not current_user.is_admin:
        return jsonify({'error': '无权操作'}), 403
    
    tier = RankTier.query.get_or_404(tier_id)
    
    user_count = User.query.filter_by(current_tier_id=tier_id).count()
    
    tier_data = tier.to_dict()
    tier_data['user_count'] = user_count
    
    return jsonify(tier_data)

@admin_bp.route('/rank-tiers/api/tiers', methods=['POST'])
@login_required
@csrf.exempt
def api_create_tier():
    if not current_user.is_admin:
        return jsonify({'error': '无权操作'}), 403
    
    data = request.get_json()
    
    existing = RankTier.query.filter_by(
        tier_name=data.get('tier_name'),
        sub_tier=data.get('sub_tier')
    ).first()
    
    if existing:
        return jsonify({'error': '该段位已存在'}), 400
    
    tier = RankTier(
        tier_name=data.get('tier_name'),
        tier_order=int(data.get('tier_order', 1)),
        sub_tier=data.get('sub_tier'),
        min_points=int(data.get('min_points', 0)),
        max_points=int(data.get('max_points')) if data.get('max_points') else None,
        icon=data.get('icon'),
        color=data.get('color'),
        description=data.get('description'),
        is_active=True
    )
    
    db.session.add(tier)
    db.session.commit()
    
    return jsonify({
        'success': True,
        'message': '段位创建成功',
        'tier': tier.to_dict()
    })

@admin_bp.route('/rank-tiers/api/tiers/<int:tier_id>', methods=['PUT'])
@login_required
@csrf.exempt
def api_update_tier(tier_id):
    if not current_user.is_admin:
        return jsonify({'error': '无权操作'}), 403
    
    tier = RankTier.query.get_or_404(tier_id)
    data = request.get_json()
    
    old_min = tier.min_points
    old_max = tier.max_points
    
    if 'tier_name' in data:
        tier.tier_name = data['tier_name']
    if 'tier_order' in data:
        tier.tier_order = int(data['tier_order'])
    if 'sub_tier' in data:
        tier.sub_tier = data['sub_tier']
    if 'min_points' in data:
        tier.min_points = int(data['min_points'])
    if 'max_points' in data:
        tier.max_points = int(data['max_points']) if data['max_points'] else None
    if 'icon' in data:
        tier.icon = data['icon']
    if 'color' in data:
        tier.color = data['color']
    if 'description' in data:
        tier.description = data['description']
    if 'is_active' in data:
        tier.is_active = bool(data['is_active'])
    
    db.session.commit()
    
    needs_recalc = (old_min != tier.min_points or old_max != tier.max_points)
    
    return jsonify({
        'success': True,
        'message': '段位更新成功',
        'recalculate_needed': needs_recalc,
        'tier': tier.to_dict()
    })

@admin_bp.route('/rank-tiers/api/tiers/<int:tier_id>', methods=['DELETE'])
@login_required
@csrf.exempt
def api_delete_tier(tier_id):
    if not current_user.is_admin:
        return jsonify({'error': '无权操作'}), 403
    
    tier = RankTier.query.get_or_404(tier_id)
    
    user_count = User.query.filter_by(current_tier_id=tier_id).count()
    peak_count = User.query.filter_by(peak_tier_id=tier_id).count()
    
    # 将该段位的用户设为未定段
    if user_count > 0:
        User.query.filter_by(current_tier_id=tier_id).update({'current_tier_id': None})
    
    if peak_count > 0:
        User.query.filter_by(peak_tier_id=tier_id).update({'peak_tier_id': None})
    
    db.session.delete(tier)
    db.session.commit()
    
    msg = f'段位"{tier.display_name}"已删除'
    if user_count > 0:
        msg += f'，{user_count} 名用户已变为未定段'
    
    return jsonify({
        'success': True,
        'message': msg
    })

@admin_bp.route('/rank-tiers/api/recalculate', methods=['POST'])
@login_required
@csrf.exempt
def api_recalculate():
    if not current_user.is_admin:
        return jsonify({'error': '无权操作'}), 403
    
    import time
    start_time = time.time()
    
    result = RankService.recalculate_all_users_tiers()
    
    elapsed = time.time() - start_time
    
    return jsonify({
        'success': True,
        'message': f'已完成重算，影响 {result["affected_users"]} 名用户',
        'total_users': result['total_users'],
        'affected_users': result['affected_users'],
        'processing_time': f'{elapsed:.2f}s'
    })

@admin_bp.route('/rank-tiers/api/distribution')
@login_required
def api_distribution():
    if not current_user.is_admin:
        return jsonify({'error': '无权操作'}), 403
    
    distribution = RankService.get_tier_distribution()
    
    total_users = sum(d['count'] for d in distribution)
    
    return jsonify({
        'distribution': distribution,
        'total_users': total_users
    })

@admin_bp.route('/rank-tiers/api/validate')
@login_required
def api_validate():
    if not current_user.is_admin:
        return jsonify({'error': '无权操作'}), 403
    
    errors = RankService.validate_tier_configuration()
    
    return jsonify({
        'valid': len(errors) == 0,
        'errors': errors
    })

@admin_bp.route('/rank-tiers/api/init-default', methods=['POST'])
@login_required
@csrf.exempt
def api_init_default():
    if not current_user.is_admin:
        return jsonify({'error': '无权操作'}), 403
    
    data = request.get_json() or {}
    force = data.get('force', False)
    
    result = RankService.init_default_tiers(force=force)
    
    return jsonify(result)
