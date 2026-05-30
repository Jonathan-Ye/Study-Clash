"""教师知识点分析路由"""
from flask import render_template, jsonify, request
from flask_login import login_required
from app.routes.admin import admin_bp, role_required, teacher_permission_required
from app.services import knowledge_analysis_service
from app.models import Subject


# ==================== 页面路由 ====================

@admin_bp.route('/knowledge-analysis')
@login_required
@role_required('admin', 'teacher')
@teacher_permission_required('can_view_knowledge_analysis')
def knowledge_analysis():
    """知识点分析主页面"""
    subjects = Subject.query.filter_by(is_active=True).order_by(Subject.name).all()
    return render_template('admin/knowledge_analysis.html', subjects=subjects)


@admin_bp.route('/knowledge-analysis/chapter/<int:chapter_id>')
@login_required
@role_required('admin', 'teacher')
@teacher_permission_required('can_view_knowledge_analysis')
def chapter_detail(chapter_id):
    """章节钻取详情页"""
    subjects = Subject.query.filter_by(is_active=True).order_by(Subject.name).all()
    return render_template('admin/chapter_detail.html', 
                           chapter_id=chapter_id, subjects=subjects)


@admin_bp.route('/knowledge-analysis/comparison')
@login_required
@role_required('admin', 'teacher')
@teacher_permission_required('can_view_knowledge_analysis')
def knowledge_comparison():
    """对比分析页"""
    subjects = Subject.query.filter_by(is_active=True).order_by(Subject.name).all()
    return render_template('admin/knowledge_analysis_comparison.html', subjects=subjects)


# ==================== API路由 ====================

@admin_bp.route('/api/knowledge-analysis/overview')
@login_required
@role_required('admin', 'teacher')
@teacher_permission_required('can_view_knowledge_analysis')
def api_knowledge_overview():
    """获取知识点概览数据"""
    category = request.args.get('category', 'class_name')
    value = request.args.get('value', '')
    subject_id = request.args.get('subject_id', 0, type=int)
    time_range = request.args.get('time_range', '30d')
    
    if category not in ('class_name', 'major'):
        return jsonify({'success': False, 'error': '无效的分类维度'}), 400
    if not value:
        return jsonify({'success': False, 'error': '请选择具体的班级或专业'}), 400
    if not subject_id:
        return jsonify({'success': False, 'error': '请选择学科'}), 400
    
    try:
        data = knowledge_analysis_service.get_knowledge_overview(
            category, value, subject_id, time_range
        )
        if 'error' in data:
            return jsonify({'success': False, 'error': data['error']}), 400
        return jsonify({'success': True, 'data': data})
    except Exception as e:
        return jsonify({'success': False, 'error': f'数据加载失败: {str(e)}'}), 500


@admin_bp.route('/api/knowledge-analysis/chapter/<int:chapter_id>/detail')
@login_required
@role_required('admin', 'teacher')
@teacher_permission_required('can_view_knowledge_analysis')
def api_chapter_detail(chapter_id):
    """获取章节详情数据"""
    category = request.args.get('category', 'class_name')
    value = request.args.get('value', '')
    time_range = request.args.get('time_range', '30d')
    
    if not value:
        return jsonify({'success': False, 'error': '请选择具体的班级或专业'}), 400
    
    try:
        data = knowledge_analysis_service.get_chapter_detail(
            chapter_id, category, value, time_range
        )
        if 'error' in data:
            return jsonify({'success': False, 'error': data['error']}), 400
        return jsonify({'success': True, 'data': data})
    except Exception as e:
        return jsonify({'success': False, 'error': f'数据加载失败: {str(e)}'}), 500


@admin_bp.route('/api/knowledge-analysis/comparison')
@login_required
@role_required('admin', 'teacher')
@teacher_permission_required('can_view_knowledge_analysis')
def api_knowledge_comparison():
    """获取对比分析数据"""
    category = request.args.get('category', 'class_name')
    subject_id = request.args.get('subject_id', 0, type=int)
    time_range = request.args.get('time_range', '30d')
    
    if category not in ('class_name', 'major'):
        return jsonify({'success': False, 'error': '无效的分类维度'}), 400
    if not subject_id:
        return jsonify({'success': False, 'error': '请选择学科'}), 400
    
    try:
        data = knowledge_analysis_service.get_comparison_data(
            category, subject_id, time_range
        )
        if 'error' in data:
            return jsonify({'success': False, 'error': data['error']}), 400
        return jsonify({'success': True, 'data': data})
    except Exception as e:
        return jsonify({'success': False, 'error': f'数据加载失败: {str(e)}'}), 500


@admin_bp.route('/api/knowledge-analysis/weak-chapters')
@login_required
@role_required('admin', 'teacher')
@teacher_permission_required('can_view_knowledge_analysis')
def api_weak_chapters():
    """获取薄弱章节预警数据"""
    category = request.args.get('category', 'class_name')
    value = request.args.get('value', '')
    subject_id = request.args.get('subject_id', 0, type=int)
    time_range = request.args.get('time_range', '30d')
    
    if not value or not subject_id:
        return jsonify({'success': False, 'error': '参数不完整'}), 400
    
    try:
        data = knowledge_analysis_service.get_weak_chapters(
            category, value, subject_id, time_range
        )
        if 'error' in data:
            return jsonify({'success': False, 'error': data['error']}), 400
        return jsonify({'success': True, 'data': data})
    except Exception as e:
        return jsonify({'success': False, 'error': f'数据加载失败: {str(e)}'}), 500


@admin_bp.route('/api/knowledge-analysis/suggestions')
@login_required
@role_required('admin', 'teacher')
@teacher_permission_required('can_view_knowledge_analysis')
def api_suggestions():
    """获取教学建议数据"""
    category = request.args.get('category', 'class_name')
    value = request.args.get('value', '')
    subject_id = request.args.get('subject_id', 0, type=int)
    time_range = request.args.get('time_range', '30d')
    
    if not value or not subject_id:
        return jsonify({'success': False, 'error': '参数不完整'}), 400
    
    try:
        # 先获取概览（包含建议）
        overview = knowledge_analysis_service.get_knowledge_overview(
            category, value, subject_id, time_range
        )
        if 'error' in overview:
            return jsonify({'success': False, 'error': overview['error']}), 400
        return jsonify({'success': True, 'data': {'suggestions': overview.get('suggestions', [])}})
    except Exception as e:
        return jsonify({'success': False, 'error': f'数据加载失败: {str(e)}'}), 500


@admin_bp.route('/api/knowledge-analysis/category-options')
@login_required
@role_required('admin', 'teacher')
@teacher_permission_required('can_view_knowledge_analysis')
def api_category_options():
    """获取分类选项列表"""
    category = request.args.get('category', 'class_name')
    
    if category not in ('class_name', 'major'):
        return jsonify({'success': False, 'error': '无效的分类维度'}), 400
    
    try:
        options = knowledge_analysis_service._get_category_options(category)
        return jsonify({'success': True, 'data': {'options': options}})
    except Exception as e:
        return jsonify({'success': False, 'error': f'数据加载失败: {str(e)}'}), 500
