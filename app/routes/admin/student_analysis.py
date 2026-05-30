import io
from flask import render_template, jsonify, request, send_file
from flask_login import login_required
from app.routes.admin import admin_bp, admin_required, role_required, teacher_permission_required
from app.services import student_analysis_service


# ==================== 页面路由 ====================

@admin_bp.route('/student-analysis')
@login_required
@role_required('admin', 'teacher')
@teacher_permission_required('can_view_student_analysis')
def student_analysis():
    """学生分析主页面"""
    return render_template('admin/student_analysis.html')


@admin_bp.route('/student-analysis/class/<class_name>')
@login_required
@role_required('admin', 'teacher')
@teacher_permission_required('can_view_student_analysis')
def student_class_list(class_name):
    """班级内学生列表页面"""
    return render_template('admin/student_list.html', 
                           category='class_name', 
                           category_label='班级',
                           value=class_name)


@admin_bp.route('/student-analysis/major/<major>')
@login_required
@role_required('admin', 'teacher')
@teacher_permission_required('can_view_student_analysis')
def student_major_list(major):
    """专业内学生列表页面"""
    return render_template('admin/student_list.html', 
                           category='major', 
                           category_label='专业',
                           value=major)


@admin_bp.route('/student-analysis/student/<int:user_id>')
@login_required
@role_required('admin', 'teacher')
@teacher_permission_required('can_view_student_analysis')
def student_detail(user_id):
    """学生详细画像页面"""
    return render_template('admin/student_detail.html', user_id=user_id)


# ==================== API路由 ====================

@admin_bp.route('/api/student-analysis/overview')
@login_required
@role_required('admin', 'teacher')
@teacher_permission_required('can_view_student_analysis')
def api_overview():
    """获取分类概览数据"""
    category = request.args.get('category', 'class_name')
    time_range = request.args.get('time_range', 'all')
    sort_by = request.args.get('sort_by', 'student_count')
    
    if category not in ('class_name', 'major'):
        return jsonify({'error': '无效的分类维度'}), 400
    
    try:
        data = student_analysis_service.get_category_overview(category, time_range, sort_by)
        return jsonify(data)
    except Exception as e:
        return jsonify({'error': '数据加载失败，请稍后重试'}), 500


@admin_bp.route('/api/student-analysis/class/<class_name>/students')
@login_required
@role_required('admin', 'teacher')
@teacher_permission_required('can_view_student_analysis')
def api_class_students(class_name):
    """获取班级学生列表"""
    return _api_category_students('class_name', class_name)


@admin_bp.route('/api/student-analysis/major/<major>/students')
@login_required
@role_required('admin', 'teacher')
@teacher_permission_required('can_view_student_analysis')
def api_major_students(major):
    """获取专业学生列表"""
    return _api_category_students('major', major)


def _api_category_students(category, value):
    """分类学生列表通用处理"""
    sort_by = request.args.get('sort_by', 'points')
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    search = request.args.get('search', '')
    time_range = request.args.get('time_range', 'all')
    
    try:
        data = student_analysis_service.get_category_students(
            category, value, sort_by, page, per_page, search or None, time_range
        )
        return jsonify(data)
    except Exception as e:
        return jsonify({'error': '数据加载失败，请稍后重试'}), 500


@admin_bp.route('/api/student-analysis/student/<int:user_id>/profile')
@login_required
@role_required('admin', 'teacher')
@teacher_permission_required('can_view_student_analysis')
def api_student_profile(user_id):
    """获取学生画像数据"""
    time_range = request.args.get('time_range', '30d')
    
    try:
        data = student_analysis_service.get_student_profile(user_id, time_range)
        if data is None:
            return jsonify({'error': '学生不存在'}), 404
        return jsonify(data)
    except Exception as e:
        return jsonify({'error': '数据加载失败，请稍后重试'}), 500


@admin_bp.route('/api/student-analysis/compare')
@login_required
@role_required('admin', 'teacher')
@teacher_permission_required('can_view_student_analysis')
def api_compare():
    """获取对比分析数据"""
    category = request.args.get('category', 'class_name')
    metric = request.args.get('metric', 'avg_accuracy')
    time_range = request.args.get('time_range', 'all')
    
    if category not in ('class_name', 'major'):
        return jsonify({'error': '无效的分类维度'}), 400
    
    valid_metrics = ('avg_accuracy', 'avg_points', 'avg_games', 'active_ratio')
    if metric not in valid_metrics:
        return jsonify({'error': '无效的对比指标'}), 400
    
    try:
        data = student_analysis_service.get_compare_data(category, metric, time_range)
        return jsonify(data)
    except Exception as e:
        return jsonify({'error': '数据加载失败，请稍后重试'}), 500


@admin_bp.route('/api/student-analysis/export')
@login_required
@role_required('admin', 'teacher')
@teacher_permission_required('can_view_student_analysis')
def api_export():
    """导出分析数据"""
    category = request.args.get('category', 'class_name')
    value = request.args.get('value', '')
    time_range = request.args.get('time_range', 'all')
    
    if not value:
        return jsonify({'error': '请指定导出的分类'}), 400
    
    try:
        students = student_analysis_service.export_student_data(category, value, time_range)
        
        if not students:
            return jsonify({'error': '当前无数据可导出'}), 400
        
        # 生成xlsx文件
        import openpyxl
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = '学生分析数据'
        
        # 表头
        headers = ['姓名', '学号', '总积分', '正确率(%)', '游戏场次', '段位', '最近活跃']
        ws.append(headers)
        
        # 数据行
        for s in students:
            ws.append([
                s.get('name', ''),
                s.get('student_id', ''),
                s.get('total_points', 0),
                s.get('accuracy', '--') if s.get('accuracy') is not None else '--',
                s.get('games_played', 0),
                s.get('tier_name', ''),
                s.get('last_active', '')
            ])
        
        # 自动调整列宽
        for col in ws.columns:
            max_length = 0
            column = col[0].column_letter
            for cell in col:
                try:
                    if len(str(cell.value)) > max_length:
                        max_length = len(str(cell.value))
                except:
                    pass
            adjusted_width = min(max_length + 2, 30)
            ws.column_dimensions[column].width = adjusted_width
        
        # 写入内存
        output = io.BytesIO()
        wb.save(output)
        output.seek(0)
        
        category_label = '班级' if category == 'class_name' else '专业'
        filename = f'{category_label}_{value}_学生分析.xlsx'
        
        return send_file(
            output,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name=filename
        )
    except Exception as e:
        return jsonify({'error': '导出失败，请稍后重试'}), 500
