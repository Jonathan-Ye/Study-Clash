import os
import json
import time
import pandas as pd
from datetime import datetime, timezone
from io import BytesIO
from flask import render_template, request, redirect, url_for, flash, jsonify, current_app, send_file, session
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
from app import db
from app.models import Subject, Chapter, Question
from app.routes.admin import admin_bp, admin_required, role_required, teacher_permission_required
from app.utils.quiz_export import export_questions_json, export_questions_excel
from app.utils.quiz_import import validate_import, execute_import, MAX_FILE_SIZE
from app.utils.image_pack import pack_images, unpack_images
from app.utils.op_log import log_operation
from app.utils.chapter_export import export_chapters_json, export_chapters_excel
from app.utils.chapter_import import validate_chapter_import, execute_chapter_import, MAX_FILE_SIZE as CHAPTER_MAX_FILE_SIZE

@admin_bp.route('/subjects')
@login_required
@role_required('admin', 'teacher')
@teacher_permission_required('can_manage_subjects')
def subjects():
    subjects_list = Subject.query.all()
    return render_template('admin/subjects.html', subjects=subjects_list)

@admin_bp.route('/subjects/create', methods=['GET', 'POST'])
@login_required
@role_required('admin', 'teacher')
@teacher_permission_required('can_manage_subjects')
def create_subject():
    if request.method == 'POST':
        name = request.form.get('name')
        code = request.form.get('code')
        description = request.form.get('description')
        icon = request.form.get('icon')
        is_active = request.form.get('is_active') == 'on'
        applicable_majors = request.form.getlist('applicable_majors')
        
        if name:
            subject = Subject(name=name, code=code, description=description, icon=icon, is_active=is_active, created_by=current_user.id)
            subject.set_applicable_majors(applicable_majors)
            db.session.add(subject)
            db.session.commit()
            flash('科目创建成功', 'success')
            return redirect(url_for('admin.subjects'))
    
    from app.models import DictionaryItem
    majors = DictionaryItem.get_options('major')
    return render_template('admin/create_subject.html', majors=majors)

@admin_bp.route('/subjects/<int:id>/edit', methods=['GET', 'POST'])
@login_required
@role_required('admin', 'teacher')
@teacher_permission_required('can_manage_subjects')
def edit_subject(id):
    subject = Subject.query.get_or_404(id)
    
    if request.method == 'POST':
        subject.name = request.form.get('name')
        subject.code = request.form.get('code')
        subject.description = request.form.get('description')
        subject.icon = request.form.get('icon')
        subject.is_active = request.form.get('is_active') == 'on'
        applicable_majors = request.form.getlist('applicable_majors')
        subject.set_applicable_majors(applicable_majors)
        db.session.commit()
        flash('科目更新成功', 'success')
        return redirect(url_for('admin.subjects'))
    
    from app.models import DictionaryItem
    majors = DictionaryItem.get_options('major')
    return render_template('admin/edit_subject.html', subject=subject, majors=majors)

@admin_bp.route('/subjects/<int:id>/delete', methods=['POST'])
@login_required
@role_required('admin', 'teacher')
@teacher_permission_required('can_manage_subjects')
def delete_subject(id):
    subject = Subject.query.get_or_404(id)
    db.session.delete(subject)
    db.session.commit()
    flash('科目删除成功', 'success')
    return redirect(url_for('admin.subjects'))

@admin_bp.route('/chapters')
@login_required
@role_required('admin', 'teacher')
@teacher_permission_required('can_manage_chapters')
def chapters():
    subject_id = request.args.get('subject_id', type=int)
    subjects_list = Subject.query.all()
    
    if subject_id:
        chapters = Chapter.query.filter_by(subject_id=subject_id).order_by(Chapter.order.asc()).all()
        subject = Subject.query.get(subject_id)
        chapters_by_subject = {
            subject_id: {
                'subject': subject,
                'chapters': [c for c in chapters if c.level == 1 or c.level is None],
                'all_chapters': chapters
            }
        } if subject else {}
    else:
        all_chapters = Chapter.query.order_by(Chapter.order.asc()).all()
        chapters_by_subject = {}
        for chapter in all_chapters:
            sid = chapter.subject_id
            if sid not in chapters_by_subject:
                subject = Subject.query.get(sid)
                chapters_by_subject[sid] = {
                    'subject': subject,
                    'chapters': [],
                    'all_chapters': []
                }
            chapters_by_subject[sid]['all_chapters'].append(chapter)
            if chapter.level == 1 or chapter.level is None:
                chapters_by_subject[sid]['chapters'].append(chapter)
    
    return render_template('admin/chapters.html', chapters_by_subject=chapters_by_subject, subjects=subjects_list, selected_subject_id=subject_id)

@admin_bp.route('/chapters/create', methods=['GET', 'POST'])
@login_required
@role_required('admin', 'teacher')
@teacher_permission_required('can_manage_chapters')
def create_chapter():
    if request.method == 'POST':
        name = request.form.get('name')
        subject_id = request.form.get('subject_id', type=int)
        parent_id = request.form.get('parent_id', type=int)
        order = request.form.get('order', type=int)
        if order is None:
            # 自动计算order：同级章节最大order + 1
            max_order_chapter = Chapter.query.filter_by(
                subject_id=subject_id,
                parent_id=parent_id if parent_id else None
            ).order_by(Chapter.order.desc()).first()
            order = (max_order_chapter.order + 1) if max_order_chapter else 0
        description = request.form.get('description', '')
        is_active = request.form.get('is_active') == 'on'

        if not name or not subject_id:
            flash('请填写章节名称并选择学科', 'error')
            return redirect(url_for('admin.chapters'))

        subject = Subject.query.get(subject_id)
        if not subject:
            flash('请选择有效的学科', 'error')
            return redirect(url_for('admin.chapters'))

        level = 1
        if parent_id:
            parent = Chapter.query.get(parent_id)
            if parent and parent.subject_id == subject_id:
                level = parent.level + 1
                if level > 3:
                    flash('最多只能创建3级章节', 'error')
                    return redirect(url_for('admin.chapters'))
            else:
                flash('无效的父章节', 'error')
                return redirect(url_for('admin.chapters'))

        chapter = Chapter(
            name=name,
            subject_id=subject_id,
            parent_id=parent_id if parent_id else None,
            level=level,
            order=order,
            description=description,
            is_active=is_active
        )
        db.session.add(chapter)
        db.session.commit()
        flash('章节创建成功', 'success')
        return redirect(url_for('admin.chapters', subject_id=subject_id))

    return redirect(url_for('admin.chapters'))

@admin_bp.route('/chapters/api/get-chapters')
@login_required
@role_required('admin', 'teacher')
@teacher_permission_required('can_manage_chapters')
def get_chapters_api():
    subject_id = request.args.get('subject_id', type=int)
    parent_id = request.args.get('parent_id', type=int)

    query = Chapter.query
    if subject_id:
        query = query.filter_by(subject_id=subject_id)
    if parent_id:
        query = query.filter_by(parent_id=parent_id)
    else:
        query = query.filter_by(parent_id=None)

    chapters = query.order_by(Chapter.order.asc()).all()
    return jsonify([{
        'id': c.id,
        'name': c.name,
        'level': c.level,
        'order': c.order,
        'parent_id': c.parent_id,
        'is_active': c.is_active,
        'children_count': c.children.count()
    } for c in chapters])

@admin_bp.route('/chapters/reorder', methods=['POST'])
@login_required
@role_required('admin', 'teacher')
@teacher_permission_required('can_manage_chapters')
def reorder_chapters():
    try:
        data = request.get_json()
        chapters_data = data.get('chapters', [])

        if not chapters_data:
            return jsonify({'success': False, 'error': '没有章节数据'})

        for item in chapters_data:
            chapter_id = item.get('id')
            order = item.get('order')
            parent_id = item.get('parent_id')
            if chapter_id and order is not None:
                chapter = Chapter.query.get(chapter_id)
                if chapter:
                    chapter.order = order
                    if parent_id is not None:
                        chapter.parent_id = parent_id if parent_id > 0 else None

        db.session.commit()
        return jsonify({'success': True})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)})

@admin_bp.route('/chapters/<int:id>/edit', methods=['GET', 'POST'])
@login_required
@role_required('admin', 'teacher')
@teacher_permission_required('can_manage_chapters')
def edit_chapter(id):
    chapter = Chapter.query.get_or_404(id)

    if request.method == 'POST':
        name = request.form.get('name')
        subject_id = request.form.get('subject_id', type=int)
        parent_id = request.form.get('parent_id', type=int)
        order = request.form.get('order', type=int) or 0
        description = request.form.get('description', '')
        is_active = request.form.get('is_active') == 'on'

        if not name or not subject_id:
            flash('请填写章节名称并选择学科', 'error')
            all_chapters = Chapter.query.filter_by(subject_id=chapter.subject_id).order_by(Chapter.order.asc()).all() if chapter.subject_id else []
            return render_template('admin/edit_chapter.html', chapter=chapter, subjects=Subject.query.all(), all_chapters=all_chapters)

        subject = Subject.query.get(subject_id)
        if not subject:
            flash('请选择有效的学科', 'error')
            all_chapters = Chapter.query.filter_by(subject_id=chapter.subject_id).order_by(Chapter.order.asc()).all() if chapter.subject_id else []
            return render_template('admin/edit_chapter.html', chapter=chapter, subjects=Subject.query.all(), all_chapters=all_chapters)

        if parent_id:
            parent = Chapter.query.get(parent_id)
            if parent and parent.subject_id == subject_id:
                new_level = parent.level + 1
                if new_level > 3:
                    flash('最多只能创建3级章节', 'error')
                    all_chapters = Chapter.query.filter_by(subject_id=chapter.subject_id).order_by(Chapter.order.asc()).all() if chapter.subject_id else []
                    return render_template('admin/edit_chapter.html', chapter=chapter, subjects=Subject.query.all(), all_chapters=all_chapters)
                if parent_id == id:
                    flash('不能将自己设为父章节', 'error')
                    all_chapters = Chapter.query.filter_by(subject_id=chapter.subject_id).order_by(Chapter.order.asc()).all() if chapter.subject_id else []
                    return render_template('admin/edit_chapter.html', chapter=chapter, subjects=Subject.query.all(), all_chapters=all_chapters)
                chapter.parent_id = parent_id
                chapter.level = new_level
            else:
                flash('无效的父章节', 'error')
                all_chapters = Chapter.query.filter_by(subject_id=chapter.subject_id).order_by(Chapter.order.asc()).all() if chapter.subject_id else []
                return render_template('admin/edit_chapter.html', chapter=chapter, subjects=Subject.query.all(), all_chapters=all_chapters)
        else:
            chapter.parent_id = None
            chapter.level = 1

        chapter.name = name
        chapter.subject_id = subject_id
        chapter.order = order
        chapter.description = description
        chapter.is_active = is_active
        db.session.commit()
        flash('章节更新成功', 'success')
        return redirect(url_for('admin.chapters', subject_id=subject_id))

    subjects_list = Subject.query.all()
    all_chapters = Chapter.query.filter_by(subject_id=chapter.subject_id).order_by(Chapter.order.asc()).all()
    return render_template('admin/edit_chapter.html', chapter=chapter, subjects=subjects_list, all_chapters=all_chapters)

@admin_bp.route('/chapters/<int:id>/delete', methods=['POST'])
@login_required
@role_required('admin', 'teacher')
@teacher_permission_required('can_manage_chapters')
def delete_chapter(id):
    chapter = Chapter.query.get_or_404(id)

    # 递归删除所有子章节
    def delete_children(parent_id):
        children = Chapter.query.filter_by(parent_id=parent_id).all()
        for child in children:
            delete_children(child.id)
            db.session.delete(child)

    delete_children(id)
    db.session.delete(chapter)
    db.session.commit()
    flash('章节删除成功', 'success')
    return redirect(url_for('admin.chapters'))

@admin_bp.route('/questions')
@login_required
@role_required('admin', 'teacher')
@teacher_permission_required('can_manage_questions')
def questions():
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    if per_page not in (10, 20, 50, 100, 200):
        per_page = 20
    subject_id = request.args.get('subject_id', type=int)
    chapter_id = request.args.get('chapter_id', type=int)
    question_type = request.args.get('question_type')
    difficulty = request.args.get('difficulty', type=int)
    status = request.args.get('status')
    keyword = request.args.get('keyword', '').strip()
    question_id = request.args.get('id', type=int)
    chapter_id_str = request.args.get('chapter_id', '')
    if chapter_id_str == 'uncategorized':
        uncategorized = True
        chapter_id = None
    else:
        uncategorized = False
        chapter_id = request.args.get('chapter_id', type=int)
    
    query = Question.query
    
    if question_id:
        query = query.filter_by(id=question_id)
    else:
        if uncategorized:
            query = query.filter(Question.chapter_id.is_(None))
        else:
            if subject_id:
                query = query.filter_by(subject_id=subject_id)
            if chapter_id:
                query = query.filter_by(chapter_id=chapter_id)
        if question_type:
            query = query.filter_by(question_type=question_type)
        if difficulty:
            query = query.filter_by(difficulty=difficulty)
        if status:
            is_active = status == 'active'
            query = query.filter_by(is_active=is_active)
        if keyword:
            query = query.filter(Question.content.contains(keyword))
    
    pagination = query.order_by(Question.created_at.desc()).paginate(page=page, per_page=per_page)
    subjects_list = Subject.query.filter_by(is_active=True).all()
    
    chapters = []
    if subject_id:
        chapters = Chapter.query.filter_by(subject_id=subject_id, is_active=True).order_by(Chapter.level, Chapter.order).all()
    
    total_count = query.count()
    type_stats = db.session.query(
        Question.question_type, 
        db.func.count(Question.id)
    ).group_by(Question.question_type).all()
    difficulty_stats = db.session.query(
        Question.difficulty, 
        db.func.count(Question.id)
    ).group_by(Question.difficulty).all()
    
    return render_template('admin/questions.html', 
                          pagination=pagination, 
                          subjects=subjects_list,
                          chapters=chapters,
                          total_count=total_count,
                          type_stats=dict(type_stats),
                          difficulty_stats=dict(difficulty_stats),
                          is_teacher=current_user.role == 'teacher',
                          current_user_id=current_user.id,
                          per_page=per_page)

@admin_bp.route('/questions/batch-action', methods=['POST'])
@login_required
@role_required('admin', 'teacher')
@teacher_permission_required('can_manage_questions')
def questions_batch_action():
    action = request.form.get('action')
    question_ids_str = request.form.get('question_ids', '')
    
    if not question_ids_str:
        return jsonify({'success': False, 'message': '请选择要操作的题目'})
    
    try:
        question_ids = [int(id) for id in question_ids_str.split(',')]
    except ValueError:
        return jsonify({'success': False, 'message': '题目ID格式错误'})
    
    questions = Question.query.filter(Question.id.in_(question_ids)).all()
    
    # 教师只能操作自己创建的题目
    if current_user.role == 'teacher':
        questions = [q for q in questions if q.created_by == current_user.id]
        if not questions:
            return jsonify({'success': False, 'message': '您只能操作自己创建的题目'})
    
    if action == 'delete':
        from app.models import UserAnswer, GameQuestion, WrongQuestion
        for q in questions:
            UserAnswer.query.filter_by(question_id=q.id).delete()
            GameQuestion.query.filter_by(question_id=q.id).delete()
            WrongQuestion.query.filter_by(question_id=q.id).delete()
            db.session.delete(q)
        db.session.commit()
        return jsonify({'success': True, 'message': f'成功删除 {len(questions)} 道题目'})
    
    elif action == 'enable':
        for q in questions:
            q.is_active = True
        db.session.commit()
        return jsonify({'success': True, 'message': f'成功启用 {len(questions)} 道题目'})
    
    elif action == 'disable':
        for q in questions:
            q.is_active = False
        db.session.commit()
        return jsonify({'success': True, 'message': f'成功禁用 {len(questions)} 道题目'})
    
    elif action == 'set_difficulty':
        difficulty = request.form.get('difficulty', type=int)
        if not difficulty or difficulty not in [1, 2, 3, 4]:
            return jsonify({'success': False, 'message': '请选择有效的难度'})
        for q in questions:
            q.difficulty = difficulty
        db.session.commit()
        return jsonify({'success': True, 'message': f'成功修改 {len(questions)} 道题目的难度'})
    
    elif action == 'set_points':
        points = request.form.get('points', type=int)
        if points is None or points < 0:
            return jsonify({'success': False, 'message': '请输入有效的积分值'})
        for q in questions:
            q.points = points
        db.session.commit()
        return jsonify({'success': True, 'message': f'成功修改 {len(questions)} 道题目的积分'})
    
    elif action == 'set_time_limit':
        time_limit = request.form.get('time_limit', type=int)
        if time_limit is None or time_limit < 5:
            return jsonify({'success': False, 'message': '请输入有效的时间限制(至少5秒)'})
        for q in questions:
            q.time_limit = time_limit
        db.session.commit()
        return jsonify({'success': True, 'message': f'成功修改 {len(questions)} 道题目的时间限制'})
    
    return jsonify({'success': False, 'message': '未知操作'})

@admin_bp.route('/questions/toggle-status/<int:id>', methods=['POST'])
@login_required
@role_required('admin', 'teacher')
@teacher_permission_required('can_manage_questions')
def question_toggle_status(id):
    question = Question.query.get_or_404(id)
    # 教师只能操作自己创建的题目
    if current_user.role == 'teacher' and question.created_by != current_user.id:
        return jsonify({'success': False, 'message': '您只能操作自己创建的题目'})
    question.is_active = not question.is_active
    db.session.commit()
    return jsonify({'success': True, 'is_active': question.is_active})

@admin_bp.route('/questions/delete/<int:id>', methods=['POST'])
@login_required
@role_required('admin', 'teacher')
@teacher_permission_required('can_manage_questions')
def question_delete(id):
    question = Question.query.get_or_404(id)
    if current_user.role == 'teacher' and question.created_by != current_user.id:
        return jsonify({'success': False, 'message': '您只能删除自己创建的题目'})
    from app.models import UserAnswer, GameQuestion, WrongQuestion
    UserAnswer.query.filter_by(question_id=id).delete()
    GameQuestion.query.filter_by(question_id=id).delete()
    WrongQuestion.query.filter_by(question_id=id).delete()
    db.session.delete(question)
    db.session.commit()
    return jsonify({'success': True})

@admin_bp.route('/questions/detail/<int:id>')
@login_required
@role_required('admin', 'teacher')
@teacher_permission_required('can_manage_questions')
def question_detail(id):
    question = Question.query.get_or_404(id)
    
    def fix_image_url(url):
        """将数据库中的图片路径转为可访问的静态文件URL"""
        if not url:
            return None
        if url.startswith(('http://', 'https://', '/static/')):
            return url
        return '/static/images/questions/' + url
    
    return jsonify({
        'id': question.id,
        'content': question.content,
        'image_url': fix_image_url(question.image_url),
        'question_type': question.question_type,
        'difficulty': question.difficulty,
        'option_a': question.option_a,
        'option_a_image': fix_image_url(question.option_a_image),
        'option_b': question.option_b,
        'option_b_image': fix_image_url(question.option_b_image),
        'option_c': question.option_c,
        'option_c_image': fix_image_url(question.option_c_image),
        'option_d': question.option_d,
        'option_d_image': fix_image_url(question.option_d_image),
        'option_e': question.option_e,
        'option_e_image': fix_image_url(question.option_e_image),
        'option_f': question.option_f,
        'option_f_image': fix_image_url(question.option_f_image),
        'correct_answer': question.correct_answer,
        'analysis': question.analysis,
        'subject_name': question.subject.name if question.subject else None,
        'chapter_name': question.chapter.get_full_path() if question.chapter else None,
        'is_active': question.is_active,
        'created_at': question.created_at.strftime('%Y-%m-%d %H:%M') if question.created_at else None
    })

@admin_bp.route('/questions/export')
@login_required
@role_required('admin', 'teacher')
@teacher_permission_required('can_manage_questions')
def questions_export():
    question_ids = request.args.get('ids', '')
    subject_id = request.args.get('subject_id', type=int)
    chapter_id = request.args.get('chapter_id', type=int)
    question_type = request.args.get('question_type')
    difficulty = request.args.get('difficulty', type=int)
    status = request.args.get('status')
    keyword = request.args.get('keyword', '').strip()
    chapter_id_str = request.args.get('chapter_id', '')
    if chapter_id_str == 'uncategorized':
        uncategorized = True
        chapter_id = None
    else:
        uncategorized = False
        chapter_id = request.args.get('chapter_id', type=int)
    
    query = Question.query
    
    if question_ids:
        ids = [int(id) for id in question_ids.split(',')]
        query = query.filter(Question.id.in_(ids))
    else:
        if uncategorized:
            query = query.filter(Question.chapter_id.is_(None))
        else:
            if subject_id:
                query = query.filter_by(subject_id=subject_id)
            if chapter_id:
                query = query.filter_by(chapter_id=chapter_id)
        if question_type:
            query = query.filter_by(question_type=question_type)
        if difficulty:
            query = query.filter_by(difficulty=difficulty)
        if status:
            query = query.filter_by(is_active=(status == 'active'))
        if keyword:
            query = query.filter(Question.content.contains(keyword))
    
    questions = query.all()
    
    data = []
    for q in questions:
        data.append({
            'ID': q.id,
            '题目内容': q.content,
            '题型': {'single': '单选', 'multiple': '多选', 'judge': '判断', 'fill': '填空'}.get(q.question_type, q.question_type),
            '正确答案': q.correct_answer,
            '选项A': q.option_a,
            '选项B': q.option_b,
            '选项C': q.option_c,
            '选项D': q.option_d,
            '选项E': q.option_e,
            '选项F': q.option_f,
            '难度': q.difficulty,
            '解析': q.analysis,
            '学科': q.subject.name if q.subject else '',
            '章节': q.chapter.get_full_path() if q.chapter else '',
            '状态': '启用' if q.is_active else '禁用'
        })
    
    df = pd.DataFrame(data)
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='题目列表')
    output.seek(0)
    
    return send_file(
        output,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name=f'题目导出_{pd.Timestamp.now().strftime("%Y%m%d_%H%M%S")}.xlsx'
    )

@admin_bp.route('/questions/move-chapter', methods=['POST'])
@login_required
@role_required('admin', 'teacher')
@teacher_permission_required('can_manage_questions')
def move_questions_to_chapter():
    question_ids_str = request.form.get('question_ids', '')
    subject_id = request.form.get('subject_id', type=int)
    chapter_id = request.form.get('chapter_id', type=int)
    
    if not question_ids_str:
        return jsonify({'success': False, 'message': '请选择要迁移的题目'})
    
    try:
        question_ids = [int(id) for id in question_ids_str.split(',')]
    except ValueError:
        return jsonify({'success': False, 'message': '题目ID格式错误'})
    
    if not subject_id:
        return jsonify({'success': False, 'message': '请选择学科'})
    
    questions = Question.query.filter(Question.id.in_(question_ids)).all()
    
    # 教师只能迁移自己创建的题目
    if current_user.role == 'teacher':
        questions = [q for q in questions if q.created_by == current_user.id]
    
    for question in questions:
        question.subject_id = subject_id
        question.chapter_id = chapter_id if chapter_id else None
    
    db.session.commit()
    
    return jsonify({'success': True, 'message': f'成功迁移 {len(questions)} 道题目'})


# ========== 题库导出/导入路由 ==========

@admin_bp.route('/quiz-export')
@login_required
@role_required('admin', 'teacher')
@teacher_permission_required('can_export_questions')
def quiz_export():
    """题库导出页面"""
    subjects_list = Subject.query.filter_by(is_active=True).all()
    breadcrumb = [
        {'label': '内容管理'},
        {'label': '题库导出'}
    ]
    return render_template('admin/quiz_export.html',
                          subjects=subjects_list,
                          breadcrumb=breadcrumb)


@admin_bp.route('/quiz-export/download')
@login_required
@role_required('admin', 'teacher')
@teacher_permission_required('can_export_questions')
def quiz_export_download():
    """执行题库导出"""
    filters = {
        'subject_id': request.args.get('subject_id', type=int),
        'chapter_id': request.args.get('chapter_id', type=int),
        'question_type': request.args.get('question_type'),
        'difficulty': request.args.get('difficulty', type=int),
        'status': request.args.get('status'),
        'keyword': request.args.get('keyword', '').strip()
    }
    export_format = request.args.get('format', 'json')
    image_mode = request.args.get('image_mode', 'url_only')

    # 清理空值
    filters = {k: v for k, v in filters.items() if v}

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

    if export_format == 'json':
        data_buffer, report = export_questions_json(filters, current_user.username)
        if data_buffer is None:
            flash(report.get('error', '导出失败'), 'error')
            return redirect(url_for('admin.quiz_export'))

        filename = f'题库导出_{timestamp}.json'

        # 处理图片
        image_zip_buffer = None
        if image_mode == 'with_images':
            query = Question.query
            for k, v in filters.items():
                if k == 'subject_id':
                    query = query.filter_by(subject_id=v)
                elif k == 'chapter_id':
                    query = query.filter_by(chapter_id=v)
                elif k == 'question_type':
                    query = query.filter_by(question_type=v)
                elif k == 'difficulty':
                    query = query.filter_by(difficulty=v)
                elif k == 'status':
                    query = query.filter_by(is_active=(v == 'active'))
                elif k == 'keyword':
                    query = query.filter(Question.content.contains(v))
            questions_list = query.order_by(Question.id.asc()).all()

            app_static_dir = os.path.join(current_app.root_path, 'static')
            image_zip_buffer, missing_images, image_count = pack_images(questions_list, app_static_dir)

            if missing_images:
                flash(f'有{len(missing_images)}个图片文件缺失，详情请查看导出数据中的missing_images', 'warning')

        log_operation('export', 'question', detail=f'导出{report["total_count"]}道题目(JSON格式)')

        # 如果有图片ZIP，存入session供单独下载
        if image_zip_buffer:
            session['quiz_export_image_zip_ready'] = True
            session['quiz_export_image_zip_name'] = f'题库图片_{timestamp}.zip'
            # 将图片ZIP数据存入临时文件
            import tempfile
            tmp_dir = os.path.join(current_app.instance_path, 'tmp')
            os.makedirs(tmp_dir, exist_ok=True)
            tmp_path = os.path.join(tmp_dir, f'export_images_{timestamp}.zip')
            with open(tmp_path, 'wb') as f:
                f.write(image_zip_buffer.getvalue())
            session['quiz_export_image_zip_path'] = tmp_path
            flash(f'成功导出{report["total_count"]}道题目，图片资源包已生成可单独下载', 'success')
        else:
            if image_mode == 'url_only' and report.get('image_count', 0) > 0:
                flash(f'成功导出{report["total_count"]}道题目。提示：本导出不含图片文件，导入时需确保图片路径可访问', 'success')
            else:
                flash(f'成功导出{report["total_count"]}道题目', 'success')

        return send_file(
            data_buffer,
            mimetype='application/json',
            as_attachment=True,
            download_name=filename
        )

    else:  # excel
        data_buffer, report = export_questions_excel(filters, current_user.username)
        if data_buffer is None:
            flash(report.get('error', '导出失败'), 'error')
            return redirect(url_for('admin.quiz_export'))

        filename = f'题库导出_{timestamp}.xlsx'

        # 处理图片
        if image_mode == 'with_images':
            query = Question.query
            for k, v in filters.items():
                if k == 'subject_id':
                    query = query.filter_by(subject_id=v)
                elif k == 'chapter_id':
                    query = query.filter_by(chapter_id=v)
                elif k == 'question_type':
                    query = query.filter_by(question_type=v)
                elif k == 'difficulty':
                    query = query.filter_by(difficulty=v)
                elif k == 'status':
                    query = query.filter_by(is_active=(v == 'active'))
                elif k == 'keyword':
                    query = query.filter(Question.content.contains(v))
            questions_list = query.order_by(Question.id.asc()).all()

            app_static_dir = os.path.join(current_app.root_path, 'static')
            image_zip_buffer, missing_images, image_count = pack_images(questions_list, app_static_dir)

            if image_zip_buffer:
                import tempfile
                tmp_dir = os.path.join(current_app.instance_path, 'tmp')
                os.makedirs(tmp_dir, exist_ok=True)
                tmp_path = os.path.join(tmp_dir, f'export_images_{timestamp}.zip')
                with open(tmp_path, 'wb') as f:
                    f.write(image_zip_buffer.getvalue())
                session['quiz_export_image_zip_ready'] = True
                session['quiz_export_image_zip_name'] = f'题库图片_{timestamp}.zip'
                session['quiz_export_image_zip_path'] = tmp_path

        log_operation('export', 'question', detail=f'导出{report["total_count"]}道题目(Excel格式)')
        flash(f'成功导出{report["total_count"]}道题目', 'success')

        return send_file(
            data_buffer,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name=filename
        )


@admin_bp.route('/quiz-export/download-images')
@login_required
@role_required('admin', 'teacher')
@teacher_permission_required('can_export_questions')
def quiz_export_download_images():
    """下载导出的图片资源包"""
    zip_path = session.get('quiz_export_image_zip_path')
    zip_name = session.get('quiz_export_image_zip_name', 'images.zip')

    if not zip_path or not os.path.exists(zip_path):
        flash('图片资源包不存在或已过期，请重新导出', 'error')
        return redirect(url_for('admin.quiz_export'))

    return send_file(
        zip_path,
        mimetype='application/zip',
        as_attachment=True,
        download_name=zip_name
    )


@admin_bp.route('/quiz-backup')
@login_required
@role_required('admin', 'teacher')
@teacher_permission_required('can_import_questions')
def quiz_backup():
    """题库备份页面（导出+导入合并）"""
    subjects = Subject.query.filter_by(is_active=True).all()
    breadcrumb = [
        {'label': '系统管理'},
        {'label': '题库备份'}
    ]
    return render_template('admin/quiz_backup.html',
                          breadcrumb=breadcrumb,
                          subjects=subjects)


@admin_bp.route('/quiz-import')
@login_required
@role_required('admin', 'teacher')
@teacher_permission_required('can_import_questions')
def quiz_import():
    """题库导入页面（日常批量导入题目）"""
    breadcrumb = [
        {'label': '内容管理'},
        {'label': '题目管理'},
        {'label': '导入题目'}
    ]
    return render_template('admin/quiz_import.html',
                          breadcrumb=breadcrumb,
                          max_file_size=MAX_FILE_SIZE)


@admin_bp.route('/quiz-import/template')
@login_required
@role_required('admin', 'teacher')
@teacher_permission_required('can_import_questions')
def quiz_import_template():
    """动态生成并下载题目导入模板"""
    from app.utils.quiz_template import generate_import_template
    output = generate_import_template()
    return send_file(
        output,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name='题目导入模板.xlsx'
    )


def _cleanup_old_import_files(tmp_dir, max_age_seconds=7200):
    if not os.path.exists(tmp_dir):
        return
    now = time.time()
    for filename in os.listdir(tmp_dir):
        if filename.startswith('import_') and filename.endswith('.json'):
            filepath = os.path.join(tmp_dir, filename)
            try:
                if now - os.path.getmtime(filepath) > max_age_seconds:
                    os.remove(filepath)
            except Exception:
                pass

@admin_bp.route('/quiz-import/validate', methods=['POST'])
@login_required
@role_required('admin', 'teacher')
@teacher_permission_required('can_import_questions')
def quiz_import_validate():
    """校验导入文件"""
    data_file = request.files.get('data_file')
    conflict_strategy = request.form.get('conflict_strategy', 'skip')

    if not data_file:
        flash('请选择要导入的文件', 'error')
        return redirect(url_for('admin.quiz_import'))

    # 判断文件格式
    filename = data_file.filename or ''
    if filename.endswith('.json'):
        file_format = 'json'
    elif filename.endswith(('.xlsx', '.xls')):
        file_format = 'excel'
    else:
        flash('不支持的文件格式，请上传JSON或Excel文件', 'error')
        return redirect(url_for('admin.quiz_import'))

    # 校验文件
    data_file.seek(0)
    validation = validate_import(data_file, file_format)

    if not validation.valid_list:
        if validation.invalid_list:
            errors = validation.invalid_list
            if len(errors) == 1 and errors[0]['row'] == 0:
                flash(f'文件中没有有效的题目数据：{errors[0]["errors"][0]}', 'error')
            else:
                flash(f'文件中没有有效的题目数据，共{len(errors)}项校验失败。首个错误（第{errors[0]["row"]}行）：{errors[0]["errors"][0]}', 'error')
        else:
            flash('文件中没有有效的题目数据', 'error')
        return redirect(url_for('admin.quiz_import'))

    import secrets as secrets_module
    import_id = secrets_module.token_hex(16)
    tmp_dir = os.path.join(current_app.instance_path, 'tmp', 'imports')
    os.makedirs(tmp_dir, exist_ok=True)
    tmp_path = os.path.join(tmp_dir, f'import_{import_id}.json')
    import json as json_module
    with open(tmp_path, 'w', encoding='utf-8') as f:
        json_module.dump({
            'valid_data': [q for q in validation.valid_list],
            'subjects': validation.subjects,
            'chapters': validation.chapters
        }, f, ensure_ascii=False)

    _cleanup_old_import_files(tmp_dir)

    session['quiz_import_id'] = import_id
    session['quiz_import_conflict_strategy'] = conflict_strategy
    session['quiz_import_file_format'] = file_format

    # 处理图片ZIP
    image_zip = request.files.get('image_zip')
    has_image_zip = False
    if image_zip and image_zip.filename:
        import tempfile
        tmp_dir = os.path.join(current_app.instance_path, 'tmp')
        os.makedirs(tmp_dir, exist_ok=True)
        tmp_path = os.path.join(tmp_dir, f'import_images_{datetime.now().strftime("%Y%m%d_%H%M%S")}.zip')
        image_zip.save(tmp_path)
        session['quiz_import_image_zip_path'] = tmp_path
        has_image_zip = True
    else:
        session.pop('quiz_import_image_zip_path', None)

    breadcrumb = [
        {'label': '内容管理'},
        {'label': '题库导入'},
        {'label': '导入预览'}
    ]

    # 计算将新建的章节数量
    from app.utils.chapter_resolver import preview_new_chapters
    new_chapters_count = preview_new_chapters(validation.valid_list)

    # 获取学科和章节列表供预览页面下拉选择使用
    all_subjects = Subject.query.filter_by(is_active=True).all()
    all_chapters = Chapter.query.filter_by(is_active=True)\
        .join(Subject)\
        .order_by(Subject.name, Chapter.level, Chapter.order)\
        .all()
    existing_chapter_paths = set(c.get_full_path() for c in all_chapters)
    
    # 转换为字典供前端JSON使用
    all_subjects_data = [s.name for s in all_subjects]
    all_chapters_data = [{'path': c.get_full_path(), 'subject': c.subject.name if c.subject else ''} for c in all_chapters]

    return render_template('admin/quiz_import.html',
                          breadcrumb=breadcrumb,
                          step='preview',
                          valid_count=len(validation.valid_list),
                          valid_list=validation.valid_list,
                          invalid_list=validation.invalid_list,
                          conflict_count=validation.conflict_count,
                          conflict_details=validation.conflict_details,
                          total_count=validation.total_count,
                          conflict_strategy=conflict_strategy,
                          has_image_zip=has_image_zip,
                          new_chapters_count=new_chapters_count,
                          all_subjects=all_subjects,
                          all_subjects_data=all_subjects_data,
                          all_chapters=all_chapters,
                          all_chapters_data=all_chapters_data,
                          existing_chapter_paths=existing_chapter_paths)


@admin_bp.route('/quiz-import/execute', methods=['POST'])
@login_required
@role_required('admin', 'teacher')
@teacher_permission_required('can_import_questions')
def quiz_import_execute():
    """执行导入"""
    import_id = session.get('quiz_import_id')
    conflict_strategy = session.get('quiz_import_conflict_strategy', 'skip')
    image_zip_path = session.get('quiz_import_image_zip_path')

    valid_data = []
    subjects_data = []
    chapters_data = []

    if import_id:
        import json as json_module
        tmp_path = os.path.join(current_app.instance_path, 'tmp', 'imports', f'import_{import_id}.json')
        if os.path.exists(tmp_path):
            try:
                with open(tmp_path, 'r', encoding='utf-8') as f:
                    import_file_data = json_module.load(f)
                valid_data = import_file_data.get('valid_data', [])
                subjects_data = import_file_data.get('subjects', [])
                chapters_data = import_file_data.get('chapters', [])
            except (json_module.JSONDecodeError, IOError):
                pass
            try:
                os.remove(tmp_path)
            except Exception:
                pass
        session.pop('quiz_import_id', None)

    if not valid_data:
        flash('导入数据已过期，请重新上传文件', 'error')
        return redirect(url_for('admin.quiz_import'))

    # 从预览页面编辑后的数据更新valid_data
    import json as json_module
    edited_data = request.form.get('edited_data')
    if edited_data:
        try:
            edits = json_module.loads(edited_data)
            for idx_str, edits_for_item in edits.items():
                idx = int(idx_str)
                if 0 <= idx < len(valid_data):
                    for key, value in edits_for_item.items():
                        valid_data[idx][key] = value
        except (ValueError, json_module.JSONDecodeError):
            pass

    # 执行导入
    import_result = execute_import(valid_data, conflict_strategy, subjects_data, chapters_data)
    
    # 设置导入题目的创建者
    if import_result.success > 0:
        imported_questions = Question.query.filter(
            Question.created_by.is_(None),
            Question.created_at >= datetime.now(timezone.utc)
        ).order_by(Question.id.desc()).limit(import_result.success).all()
        for q in imported_questions:
            q.created_by = current_user.id
        db.session.commit()

    # 处理图片资源包
    if image_zip_path and os.path.exists(image_zip_path):
        from werkzeug.datastructures import FileStorage
        # 图片应该解压到 static/questions/ 目录，而不是 static/images/questions/
        target_dir = os.path.join(current_app.root_path, 'static', 'questions')
        os.makedirs(target_dir, exist_ok=True)

        with open(image_zip_path, 'rb') as f:
            from io import BytesIO
            zip_buffer = BytesIO(f.read())

        class FakeStorage:
            def __init__(self, buf):
                self._buf = buf
            def seek(self, *args):
                self._buf.seek(*args)
            def tell(self):
                return self._buf.tell()
            def read(self, *args):
                return self._buf.read(*args)

        path_mapping, skipped, errors = unpack_images(FakeStorage(zip_buffer), target_dir)
        import_result.image_result = {
            'mapped': len(path_mapping),
            'skipped': len(skipped),
            'errors': errors
        }

        # 更新题目中的图片URL
        # 改进的匹配逻辑：不依赖题目ID，通过题目内容精确匹配
        if path_mapping:
            import re
            
            # 构建文件名到URL的映射
            filename_to_url = {}
            for zip_path, url_path in path_mapping.items():
                # 从ZIP路径提取文件名
                # 新格式：images/4534_image_url/20260514_45622681.jpg
                # 旧格式：images/4534/20260514_45622681.jpg
                filename_match = re.search(r'images/\d+(_\w+)?/(.+)$', zip_path)
                if filename_match:
                    filename = filename_match.group(2)
                    # 保留第一个匹配（如果文件名唯一）
                    if filename not in filename_to_url:
                        filename_to_url[filename] = {
                            'url': url_path,
                            'zip_path': zip_path
                        }
            
            # 统计每个文件名出现的次数
            filename_count = {}
            for info in filename_to_url.values():
                filename = os.path.basename(info['zip_path'])
                filename_count[filename] = filename_count.get(filename, 0) + 1
            
            # 按导入数据匹配（不依赖数据库中的题目ID）
            for q_data in valid_data:
                # 使用导入数据中的图片URL进行匹配
                for field in ['image_url', 'option_a_image', 'option_b_image',
                              'option_c_image', 'option_d_image', 'option_e_image',
                              'option_f_image']:
                    val = q_data.get(field)
                    if val:
                        # 从URL中提取文件名
                        # URL可能是：/static/questions/20260514_45622681.jpg
                        # 或：images/4534/20260514_45622681.jpg
                        filename_match = re.search(r'[/\\]([^/\\]+)$', val)
                        if filename_match:
                            filename = filename_match.group(1)
                            # 检查文件名是否唯一
                            if filename_count.get(filename, 0) == 1:
                                # 文件名唯一，安全匹配
                                if filename in filename_to_url:
                                    q_data[field] = filename_to_url[filename]['url']
                            else:
                                # 文件名重复，尝试通过完整路径匹配
                                for zip_path, info in filename_to_url.items():
                                    if zip_path.endswith('/' + filename):
                                        q_data[field] = info['url']
                                        break
            
            # 现在更新数据库中的题目
            # 需要通过内容匹配找到对应的数据库题目
            for q_data in valid_data:
                q_id = q_data.get('id')
                question = None
                
                # 策略1：通过ID查找（如果是覆盖/跳过策略）
                if q_id:
                    question = Question.query.get(q_id)
                
                # 策略2：通过内容+题型+答案匹配（适用于追加策略或ID变化）
                if not question:
                    content = q_data.get('content', '').strip()
                    q_type = q_data.get('question_type')
                    answer = q_data.get('correct_answer', '').strip()
                    if content:
                        question = Question.query.filter_by(
                            content=content,
                            question_type=q_type,
                            correct_answer=answer
                        ).first()
                
                # 更新找到的题目的图片URL
                if question:
                    for field in ['image_url', 'option_a_image', 'option_b_image',
                                  'option_c_image', 'option_d_image', 'option_e_image',
                                  'option_f_image']:
                        if q_data.get(field):
                            setattr(question, field, q_data[field])
            
            db.session.commit()

        # 清理临时文件
        try:
            os.remove(image_zip_path)
        except Exception:
            pass

    # 清理session
    for key in ['quiz_import_conflict_strategy', 'quiz_import_file_format', 'quiz_import_image_zip_path']:
        session.pop(key, None)

    log_operation('import', 'question',
                  detail=f'导入{import_result.success}道题目(跳过{import_result.skipped}覆盖{import_result.overwritten}失败{import_result.failed})')

    breadcrumb = [
        {'label': '内容管理'},
        {'label': '题库导入'},
        {'label': '导入结果'}
    ]

    return render_template('admin/quiz_import.html',
                          breadcrumb=breadcrumb,
                          step='result',
                          import_result=import_result)


# ========== 章节导出/导入路由 ==========

@admin_bp.route('/chapter-export')
@login_required
@role_required('admin', 'teacher')
@teacher_permission_required('can_manage_chapters')
def chapter_export():
    """章节导出页面"""
    subjects_list = Subject.query.filter_by(is_active=True).all()
    breadcrumb = [
        {'label': '内容管理'},
        {'label': '章节导入导出'},
        {'label': '章节导出'}
    ]
    return render_template('admin/chapter_export.html',
                          subjects=subjects_list,
                          breadcrumb=breadcrumb)


@admin_bp.route('/chapter-export/download')
@login_required
@role_required('admin', 'teacher')
@teacher_permission_required('can_manage_chapters')
def chapter_export_download():
    """执行章节导出"""
    subject_id = request.args.get('subject_id', type=int)
    export_format = request.args.get('format', 'json')
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

    if export_format == 'json':
        data_buffer, report = export_chapters_json(subject_id, current_user.username)
        if data_buffer is None:
            flash(report.get('error', '导出失败'), 'error')
            return redirect(url_for('admin.chapter_export'))

        log_operation('export', 'chapter', detail=f'导出{report["total_count"]}个章节(JSON格式)')
        flash(f'成功导出{report["total_count"]}个章节（{report["subject_count"]}个学科）', 'success')
        return send_file(
            data_buffer,
            mimetype='application/json',
            as_attachment=True,
            download_name=f'章节导出_{timestamp}.json'
        )
    else:  # excel
        data_buffer, report = export_chapters_excel(subject_id, current_user.username)
        if data_buffer is None:
            flash(report.get('error', '导出失败'), 'error')
            return redirect(url_for('admin.chapter_export'))

        log_operation('export', 'chapter', detail=f'导出{report["total_count"]}个章节(Excel格式)')
        flash(f'成功导出{report["total_count"]}个章节（{report["subject_count"]}个学科）', 'success')
        return send_file(
            data_buffer,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name=f'章节导出_{timestamp}.xlsx'
        )


@admin_bp.route('/chapter-import')
@login_required
@role_required('admin', 'teacher')
@teacher_permission_required('can_manage_chapters')
def chapter_import():
    """章节导入页面"""
    breadcrumb = [
        {'label': '内容管理'},
        {'label': '章节导入导出'},
        {'label': '章节导入'}
    ]
    return render_template('admin/chapter_import.html',
                          breadcrumb=breadcrumb,
                          max_file_size=CHAPTER_MAX_FILE_SIZE)


@admin_bp.route('/chapter-import/template')
@login_required
@role_required('admin', 'teacher')
@teacher_permission_required('can_manage_chapters')
def chapter_import_template():
    """下载章节导入模板"""
    from app.utils.chapter_import_template import generate_chapter_import_template
    output = generate_chapter_import_template()
    return send_file(
        output,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name='章节导入模板.xlsx'
    )


@admin_bp.route('/chapter-import/validate', methods=['POST'])
@login_required
@role_required('admin', 'teacher')
@teacher_permission_required('can_manage_chapters')
def chapter_import_validate():
    """校验章节导入文件"""
    data_file = request.files.get('data_file')
    conflict_strategy = request.form.get('conflict_strategy', 'skip')

    if not data_file:
        flash('请选择要导入的文件', 'error')
        return redirect(url_for('admin.chapter_import'))

    # 判断文件格式
    filename = data_file.filename or ''
    if filename.endswith('.json'):
        file_format = 'json'
    elif filename.endswith(('.xlsx', '.xls')):
        file_format = 'excel'
    else:
        flash('不支持的文件格式，请上传JSON或Excel文件', 'error')
        return redirect(url_for('admin.chapter_import'))

    # 校验文件
    data_file.seek(0)
    validation = validate_chapter_import(data_file, file_format)

    if validation.total_count == 0 and not validation.valid_list:
        flash('文件中没有有效的章节数据', 'error')
        return redirect(url_for('admin.chapter_import'))

    # 将校验数据存入session
    session['chapter_import_valid_data'] = [c for c in validation.valid_list]
    session['chapter_import_subjects'] = validation.subjects
    session['chapter_import_conflict_strategy'] = conflict_strategy
    session['chapter_import_file_format'] = file_format

    breadcrumb = [
        {'label': '内容管理'},
        {'label': '章节导入导出'},
        {'label': '章节导入'},
        {'label': '导入预览'}
    ]

    return render_template('admin/chapter_import.html',
                          breadcrumb=breadcrumb,
                          step='preview',
                          valid_count=len(validation.valid_list),
                          valid_list=validation.valid_list,
                          invalid_list=validation.invalid_list,
                          conflict_count=validation.conflict_count,
                          total_count=validation.total_count,
                          conflict_strategy=conflict_strategy)


@admin_bp.route('/chapter-import/execute', methods=['POST'])
@login_required
@role_required('admin', 'teacher')
@teacher_permission_required('can_manage_chapters')
def chapter_import_execute():
    """执行章节导入"""
    valid_data = session.get('chapter_import_valid_data', [])
    subjects_data = session.get('chapter_import_subjects', [])
    conflict_strategy = session.get('chapter_import_conflict_strategy', 'skip')

    if not valid_data:
        flash('没有可导入的数据，请重新上传文件', 'error')
        return redirect(url_for('admin.chapter_import'))

    # 执行导入
    import_result = execute_chapter_import(valid_data, conflict_strategy, subjects_data)

    # 清理session
    for key in ['chapter_import_valid_data', 'chapter_import_subjects',
                'chapter_import_conflict_strategy', 'chapter_import_file_format']:
        session.pop(key, None)

    log_operation('import', 'chapter',
                  detail=f'导入{import_result.success}个章节(跳过{import_result.skipped}覆盖{import_result.overwritten}失败{import_result.failed})')

    breadcrumb = [
        {'label': '内容管理'},
        {'label': '章节导入导出'},
        {'label': '章节导入'},
        {'label': '导入结果'}
    ]

    return render_template('admin/chapter_import.html',
                          breadcrumb=breadcrumb,
                          step='result',
                          import_result=import_result)
