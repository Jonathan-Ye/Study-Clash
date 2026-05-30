from flask import render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from app import db
from app.models import DictionaryCategory, DictionaryItem
from app.routes.admin import admin_bp, admin_required

@admin_bp.route('/dictionaries')
@login_required
@admin_required
def dictionaries():
    categories = DictionaryCategory.query.order_by(DictionaryCategory.sort_order, DictionaryCategory.name).all()
    return render_template('admin/dictionaries.html', categories=categories, DictionaryItem=DictionaryItem)

@admin_bp.route('/dictionaries/create-category', methods=['POST'])
@login_required
@admin_required
def create_dictionary_category():
    try:
        code = request.form.get('code', '').strip().lower()
        name = request.form.get('name', '').strip()
        icon = request.form.get('icon', '📁').strip() or '📁'
        description = request.form.get('description', '').strip()

        if not code or not name:
            flash('分类代码和名称为必填项', 'error')
            return redirect(url_for('admin.dictionaries'))

        # 检查代码是否已存在
        if DictionaryCategory.query.filter_by(code=code).first():
            flash(f'分类代码 "{code}" 已存在', 'error')
            return redirect(url_for('admin.dictionaries'))

        category = DictionaryCategory(
            code=code,
            name=name,
            icon=icon,
            description=description
        )
        db.session.add(category)
        db.session.commit()

        flash(f'成功创建分类: {name}', 'success')
        return redirect(url_for('admin.dictionaries'))

    except Exception as e:
        db.session.rollback()
        flash(f'创建分类失败: {str(e)}', 'error')
        return redirect(url_for('admin.dictionaries'))

@admin_bp.route('/dictionaries/<int:category_id>/edit-category', methods=['POST'])
@login_required
@admin_required
def edit_dictionary_category(category_id):
    try:
        category = DictionaryCategory.query.get_or_404(category_id)

        category.name = request.form.get('name', '').strip()
        category.description = request.form.get('description', '').strip()
        category.is_active = request.form.get('is_active') == 'on'
        category.sort_order = int(request.form.get('sort_order', 0))

        db.session.commit()

        flash(f'成功更新分类: {category.name}', 'success')

    except Exception as e:
        db.session.rollback()
        flash(f'更新分类失败: {str(e)}', 'error')

    return redirect(url_for('admin.dictionaries'))

@admin_bp.route('/dictionaries/<int:category_id>/delete-category', methods=['POST'])
@login_required
@admin_required
def delete_dictionary_category(category_id):
    try:
        category = DictionaryCategory.query.get_or_404(category_id)
        items_count = category.items.count()
        name = category.name

        # 级联删除：同时删除分类和其下所有选项
        db.session.delete(category)
        db.session.commit()

        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'success': True, 'deleted_items': items_count})

        if items_count > 0:
            flash(f'成功删除分类: {name}（含 {items_count} 个选项）', 'success')
        else:
            flash(f'成功删除分类: {name}', 'success')

    except Exception as e:
        db.session.rollback()
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'success': False, 'error': str(e)}), 400
        flash(f'删除分类失败: {str(e)}', 'error')

    return redirect(url_for('admin.dictionaries'))

@admin_bp.route('/dictionaries/<int:category_id>/create-item', methods=['POST'])
@login_required
@admin_required
def create_dictionary_item(category_id):
    try:
        category = DictionaryCategory.query.get_or_404(category_id)

        value = request.form.get('value', '').strip()
        label = request.form.get('label', '').strip()
        description = request.form.get('description', '').strip()
        parent_id = request.form.get('parent_id')
        sort_order = int(request.form.get('sort_order', 0))

        if not value or not label:
            flash('选项值和标签为必填项', 'error')
            return redirect(url_for('admin.dictionaries'))

        # 检查值是否已存在
        existing = DictionaryItem.query.filter_by(
            category_id=category_id,
            value=value
        ).first()

        if existing:
            flash(f'选项值 "{value}" 在该分类中已存在', 'error')
            return redirect(url_for('admin.dictionaries'))

        item = DictionaryItem(
            category_id=category_id,
            value=value,
            label=label,
            description=description,
            parent_id=int(parent_id) if parent_id else None,
            sort_order=sort_order
        )
        db.session.add(item)
        db.session.commit()

        flash(f'成功添加选项: {label}', 'success')

    except Exception as e:
        db.session.rollback()
        flash(f'添加选项失败: {str(e)}', 'error')

    return redirect(url_for('admin.dictionaries'))

@admin_bp.route('/dictionaries/<int:item_id>/edit-item', methods=['POST'])
@login_required
@admin_required
def edit_dictionary_item(item_id):
    try:
        item = DictionaryItem.query.get_or_404(item_id)

        # 支持部分更新：只更新提交的字段
        if 'value' in request.form:
            item.value = request.form.get('value', '').strip()
        if 'label' in request.form:
            item.label = request.form.get('label', '').strip()
        if 'description' in request.form:
            item.description = request.form.get('description', '').strip()
        if 'parent_id' in request.form:
            pid = request.form.get('parent_id')
            item.parent_id = int(pid) if pid else None
        if 'sort_order' in request.form:
            item.sort_order = int(request.form.get('sort_order', 0))
        if 'is_active' in request.form:
            item.is_active = request.form.get('is_active') == 'on'
        elif 'is_active_toggle' in request.form:
            # AJAX切换状态时使用
            item.is_active = request.form.get('is_active_toggle') == 'true'

        db.session.commit()

        # AJAX请求返回JSON，表单提交则重定向
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or \
           request.accept_mimetypes.best == 'application/json':
            return jsonify({'success': True, 'item': item.to_dict()})

        flash(f'成功更新选项: {item.label}', 'success')

    except Exception as e:
        db.session.rollback()
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'success': False, 'error': str(e)}), 400
        flash(f'更新选项失败: {str(e)}', 'error')

    return redirect(url_for('admin.dictionaries'))

@admin_bp.route('/dictionaries/<int:item_id>/delete-item', methods=['POST'])
@login_required
@admin_required
def delete_dictionary_item(item_id):
    try:
        item = DictionaryItem.query.get_or_404(item_id)

        # 检查是否有子项
        children_count = len(item.children)
        if children_count > 0:
            msg = f'无法删除，该选项下还有 {children_count} 个子选项'
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({'success': False, 'error': msg}), 400
            flash(msg, 'error')
            return redirect(url_for('admin.dictionaries'))

        label = item.label
        db.session.delete(item)
        db.session.commit()

        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'success': True})

        flash(f'成功删除选项: {label}', 'success')

    except Exception as e:
        db.session.rollback()
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'success': False, 'error': str(e)}), 400
        flash(f'删除选项失败: {str(e)}', 'error')

    return redirect(url_for('admin.dictionaries'))

@admin_bp.route('/dictionaries/init-default-data', methods=['POST'])
@login_required
@admin_required
def init_default_dictionary_data():
    """初始化默认字典数据"""
    try:
        DictionaryItem.init_default_data()
        flash('成功初始化默认字典数据！', 'success')
    except Exception as e:
        flash(f'初始化失败: {str(e)}', 'error')

    return redirect(url_for('admin.dictionaries'))


# ==================== API 路由 ====================

@admin_bp.route('/api/dictionary-items/<int:category_id>')
@login_required
@admin_required
def api_get_dictionary_items(category_id):
    """获取指定分类的所有选项（JSON格式）"""
    items = DictionaryItem.query.filter_by(
        category_id=category_id,
        is_active=True
    ).order_by(DictionaryItem.sort_order, DictionaryItem.label).all()
    
    all_items = DictionaryItem.query.filter_by(
        category_id=category_id
    ).order_by(DictionaryItem.sort_order, DictionaryItem.label).all()
    
    return jsonify({
        'items': [{
            'id': item.id,
            'value': item.value,
            'label': item.label,
            'sort_order': item.sort_order,
            'is_active': item.is_active,
            'description': item.description or ''
        } for item in all_items],
        'stats': {
            'total': len(all_items),
            'active': len(items)
        }
    })


@admin_bp.route('/api/move-item', methods=['POST'])
@login_required
@admin_required
def api_move_dictionary_item():
    """移动选项顺序"""
    data = request.get_json()
    
    item_id = data.get('item_id')
    direction = data.get('direction')  # 'up' or 'down'
    
    item = DictionaryItem.query.get_or_404(item_id)
    
    # 获取同分类的所有选项，按排序排列
    all_items = DictionaryItem.query.filter_by(
        category_id=item.category_id
    ).order_by(DictionaryItem.sort_order, DictionaryItem.id).all()
    
    # 找到当前项的索引
    current_index = next((i for i, x in enumerate(all_items) if x.id == item_id), None)
    
    if current_index is None:
        return jsonify({'success': False, 'error': '未找到该选项'}), 404
    
    # 计算目标索引
    if direction == 'up' and current_index > 0:
        target_index = current_index - 1
    elif direction == 'down' and current_index < len(all_items) - 1:
        target_index = current_index + 1
    else:
        return jsonify({'success': False, 'error': '无法移动'})
    
    # 交换排序值
    target_item = all_items[target_index]
    item.sort_order, target_item.sort_order = target_item.sort_order, item.sort_order
    
    db.session.commit()
    
    return jsonify({'success': True})


@admin_bp.route('/api/toggle-all-status', methods=['POST'])
@login_required
@admin_required
def api_toggle_all_status():
    """批量切换所有选项的状态"""
    data = request.get_json()
    
    category_id = data.get('category_id')
    is_active = data.get('is_active', True)
    
    items = DictionaryItem.query.filter_by(category_id=category_id).all()
    
    for item in items:
        item.is_active = is_active
    
    db.session.commit()
    
    return jsonify({
        'success': True,
        'updated': len(items)
    })


@admin_bp.route('/api/import-items', methods=['POST'])
@login_required
@admin_required
def api_import_dictionary_items():
    """批量导入选项"""
    data = request.get_json()
    
    category_id = data.get('category_id')
    items_text = data.get('items', [])
    
    imported = 0
    skipped = 0
    errors = []
    
    for line in items_text:
        line = line.strip()
        if not line:
            continue
        
        # 解析行：支持 "value" 或 "value, label" 或 "value, label, sort"
        parts = [p.strip() for p in line.split(',')]
        
        value = parts[0] if len(parts) > 0 else ''
        label = parts[1] if len(parts) > 1 else value
        sort_order = int(parts[2]) if len(parts) > 2 else 0
        
        if not value:
            continue
        
        # 检查是否已存在
        existing = DictionaryItem.query.filter_by(
            category_id=category_id,
            value=value
        ).first()
        
        if existing:
            skipped += 1
            continue
        
        try:
            item = DictionaryItem(
                category_id=category_id,
                value=value,
                label=label,
                sort_order=sort_order
            )
            db.session.add(item)
            imported += 1
            
        except Exception as e:
            errors.append(f'{value}: {str(e)}')
    
    if imported > 0:
        db.session.commit()
    
    return jsonify({
        'success': True,
        'imported': imported,
        'skipped': skipped,
        'errors': errors
    })


@admin_bp.route('/api/export-items/<int:category_id>')
@login_required
@admin_required
def api_export_dictionary_items(category_id):
    """导出选项为CSV文件"""
    import io
    
    items = DictionaryItem.query.filter_by(
        category_id=category_id
    ).order_by(DictionaryItem.sort_order, DictionaryItem.label).all()
    
    output = io.StringIO()
    output.write('value,label,sort_order,is_active\n')
    
    for item in items:
        output.write(f'{item.value},{item.label},{item.sort_order},{item.is_active}\n')
    
    output.seek(0)
    
    from flask import send_file
    return send_file(
        io.BytesIO(output.getvalue().encode('utf-8-sig')),
        mimetype='text/csv',
        as_attachment=True,
        download_name=f'dictionary_items_{category_id}.csv'
    )
