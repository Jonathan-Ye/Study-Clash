import os
import json
import uuid
import pandas as pd
from datetime import datetime
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, current_app, send_file
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
from app import db
from app.models import Subject, Chapter, Question
from app.utils.common import allowed_question_file, allowed_image_file
from app.routes.admin import admin_required

questions_bp = Blueprint('questions', __name__)

@questions_bp.route('/')
@login_required
def index():
    subjects = Subject.query.filter_by(is_active=True).all()
    user_major = getattr(current_user, 'major', None)
    filtered_subjects = [s for s in subjects if s.is_applicable_for_major(user_major)]
    return render_template('questions/index.html', subjects=filtered_subjects)

@questions_bp.route('/import', methods=['GET', 'POST'])
@login_required
def import_questions():
    if request.method == 'POST':
        if 'file' not in request.files:
            flash('请选择要上传的文件', 'error')
            return redirect(request.url)
        
        file = request.files['file']
        if file.filename == '':
            flash('请选择要上传的文件', 'error')
            return redirect(request.url)
        
        if not allowed_question_file(file.filename):
            flash('不支持的文件格式，请上传xlsx、xls、csv或json文件', 'error')
            return redirect(request.url)
        
        subject_id = request.form.get('subject_id')
        chapter_id = request.form.get('chapter_id')
        
        try:
            # 保留原始扩展名，用UUID生成安全文件名（secure_filename会丢失中文）
            original_filename = file.filename or 'upload.xlsx'
            ext = original_filename.rsplit('.', 1)[-1].lower() if '.' in original_filename else 'xlsx'
            filename = f'import_{uuid.uuid4().hex[:8]}.{ext}'
            filepath = os.path.join(current_app.config['UPLOAD_FOLDER'], 'temp', filename)
            os.makedirs(os.path.dirname(filepath), exist_ok=True)
            file.save(filepath)
            
            if filename.endswith('.json'):
                result = import_from_json(filepath, subject_id, chapter_id)
            else:
                result = import_from_excel(filepath, subject_id, chapter_id)
            
            os.remove(filepath)
            
            flash(f'成功导入{result["success"]}道题目，失败{result["failed"]}道，跳过ID冲突{result["skipped"]}道', 'success')
            if result.get('skipped_details'):
                for detail in result['skipped_details']:
                    flash(f'跳过：ID {detail["id"]} 已存在（{detail["content"]}）', 'warning')
            return redirect(url_for('questions.manage'))
        except Exception as e:
            flash(f'导入失败：{str(e)}', 'error')
            return redirect(request.url)
    
    subjects = Subject.query.filter_by(is_active=True).all()
    return render_template('questions/import.html', subjects=subjects)

def import_from_excel(filepath, subject_id, chapter_id):
    if filepath.endswith(('.xlsx', '.xls')):
        df = pd.read_excel(filepath)
    else:
        # CSV文件尝试多种编码
        for encoding in ['utf-8', 'gbk', 'gb2312', 'latin-1']:
            try:
                df = pd.read_csv(filepath, encoding=encoding)
                break
            except (UnicodeDecodeError, UnicodeError):
                continue
        else:
            df = pd.read_csv(filepath, encoding='utf-8', errors='replace')
    
    df.columns = df.columns.str.strip()
    
    required_columns = ['题目内容', '题型', '正确答案']
    for col in required_columns:
        if col not in df.columns:
            raise ValueError(f'缺少必要列：{col}')
    
    success = 0
    failed = 0
    skipped = 0
    skipped_details = []
    chapter_cache = {}  # 章节缓存

    for _, row in df.iterrows():
        try:
            # 跳过空行（题目内容为空或NaN的行）
            if pd.isna(row.get('题目内容')) or not str(row.get('题目内容', '')).strip():
                continue
            if pd.isna(row.get('正确答案')) or not str(row.get('正确答案', '')).strip():
                continue

            # ID冲突检测
            if 'ID' in df.columns and pd.notna(row.get('ID')):
                try:
                    existing_id = int(row['ID'])
                    if Question.query.get(existing_id):
                        skipped += 1
                        skipped_details.append({'id': existing_id, 'content': str(row.get('题目内容', ''))[:50]})
                        continue
                except (ValueError, TypeError):
                    pass

            question = Question()

            # Excel中学科列优先，否则使用表单选择的学科
            if '学科' in df.columns and pd.notna(row.get('学科')):
                subject_name = str(row['学科']).strip()
                if subject_name:
                    subject = Subject.query.filter_by(name=subject_name).first()
                    if not subject:
                        subject = Subject(name=subject_name, is_active=True)
                        db.session.add(subject)
                        db.session.flush()
                    question.subject_id = subject.id
                else:
                    question.subject_id = int(subject_id) if subject_id else None
            else:
                question.subject_id = int(subject_id) if subject_id else None

            # subject_id 不能为空
            if not question.subject_id:
                failed += 1
                continue

            # Excel中章节列优先，否则使用表单选择的章节
            if '章节' in df.columns and pd.notna(row.get('章节')):
                chapter_name = str(row['章节']).strip()
                if chapter_name and question.subject_id:
                    from app.utils.chapter_resolver import resolve_chapter
                    chapter_id_resolved, _, _ = resolve_chapter(
                        chapter_name, question.subject_id, cache=chapter_cache
                    )
                    question.chapter_id = chapter_id_resolved
                else:
                    question.chapter_id = int(chapter_id) if chapter_id else None
            else:
                question.chapter_id = int(chapter_id) if chapter_id else None

            question.content = str(row['题目内容']).strip()
            
            q_type = str(row['题型']).strip()
            type_mapping = {'单选': 'single', '多选': 'multiple', '判断': 'judge', '填空': 'fill'}
            question.question_type = type_mapping.get(q_type, 'single')
            
            question.correct_answer = str(row['正确答案']).strip().upper()
            
            if '选项A' in df.columns and pd.notna(row.get('选项A')):
                question.option_a = str(row['选项A']).strip()
            if '选项B' in df.columns and pd.notna(row.get('选项B')):
                question.option_b = str(row['选项B']).strip()
            if '选项C' in df.columns and pd.notna(row.get('选项C')):
                question.option_c = str(row['选项C']).strip()
            if '选项D' in df.columns and pd.notna(row.get('选项D')):
                question.option_d = str(row['选项D']).strip()
            if '选项E' in df.columns and pd.notna(row.get('选项E')):
                question.option_e = str(row['选项E']).strip()
            if '选项F' in df.columns and pd.notna(row.get('选项F')):
                question.option_f = str(row['选项F']).strip()
            
            if '难度' in df.columns and pd.notna(row.get('难度')):
                question.difficulty = int(row['难度'])
            
            if '解析' in df.columns and pd.notna(row.get('解析')):
                question.analysis = str(row['解析']).strip()
            
            if '图片URL' in df.columns and pd.notna(row.get('图片URL')):
                question.image_url = str(row['图片URL']).strip()
            
            db.session.add(question)
            success += 1
        except Exception as e:
            failed += 1
            continue
    
    db.session.commit()
    return {'success': success, 'failed': failed, 'skipped': skipped, 'skipped_details': skipped_details}

def import_from_json(filepath, subject_id, chapter_id):
    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    if not isinstance(data, list):
        data = [data]
    
    success = 0
    failed = 0
    skipped = 0
    skipped_details = []
    
    for item in data:
        try:
            # ID冲突检测
            item_id = item.get('id')
            if item_id and Question.query.get(item_id):
                skipped += 1
                skipped_details.append({'id': item_id, 'content': str(item.get('content', ''))[:50]})
                continue

            question = Question()
            question.subject_id = item.get('subject_id', subject_id)
            # subject_id 不能为空
            if not question.subject_id:
                failed += 1
                continue
            question.chapter_id = item.get('chapter_id', chapter_id)
            question.content = item['content']
            question.question_type = item.get('question_type', 'single')
            question.correct_answer = item['correct_answer'].upper()
            
            options = item.get('options', {})
            question.option_a = options.get('A')
            question.option_b = options.get('B')
            question.option_c = options.get('C')
            question.option_d = options.get('D')
            question.option_e = options.get('E')
            question.option_f = options.get('F')
            
            question.difficulty = item.get('difficulty', 1)
            question.analysis = item.get('analysis')
            question.points = item.get('points', 10)
            question.time_limit = item.get('time_limit', 60)
            question.image_url = item.get('image_url')
            
            db.session.add(question)
            success += 1
        except Exception as e:
            failed += 1
            continue
    
    db.session.commit()
    return {'success': success, 'failed': failed, 'skipped': skipped, 'skipped_details': skipped_details}

@questions_bp.route('/manage')
@login_required
def manage():
    page = request.args.get('page', 1, type=int)
    subject_id = request.args.get('subject_id', type=int)
    chapter_id = request.args.get('chapter_id', type=int)
    question_type = request.args.get('question_type')
    difficulty = request.args.get('difficulty', type=int)
    
    query = Question.query
    
    if subject_id:
        query = query.filter_by(subject_id=subject_id)
    if chapter_id:
        query = query.filter_by(chapter_id=chapter_id)
    if question_type:
        query = query.filter_by(question_type=question_type)
    if difficulty:
        query = query.filter_by(difficulty=difficulty)
    
    pagination = query.order_by(Question.created_at.desc()).paginate(page=page, per_page=20)
    subjects = Subject.query.filter_by(is_active=True).all()
    
    return render_template('questions/manage.html', 
                          pagination=pagination, 
                          subjects=subjects)

@questions_bp.route('/create', methods=['GET', 'POST'])
@login_required
@admin_required
def create():
    if request.method == 'POST':
        question = Question()
        question.subject_id = request.form.get('subject_id')
        question.chapter_id = request.form.get('chapter_id')
        question.content = request.form.get('content')
        question.question_type = request.form.get('question_type')
        question.difficulty = request.form.get('difficulty', 1, type=int)
        question.correct_answer = request.form.get('correct_answer', '').upper()
        question.analysis = request.form.get('analysis')
        question.points = request.form.get('points', 10, type=int)
        question.time_limit = request.form.get('time_limit', 60, type=int)
        question.image_url = request.form.get('image_url')
        
        question.option_a = request.form.get('option_a')
        question.option_a_image = request.form.get('option_a_image')
        question.option_b = request.form.get('option_b')
        question.option_b_image = request.form.get('option_b_image')
        question.option_c = request.form.get('option_c')
        question.option_c_image = request.form.get('option_c_image')
        question.option_d = request.form.get('option_d')
        question.option_d_image = request.form.get('option_d_image')
        question.option_e = request.form.get('option_e')
        question.option_e_image = request.form.get('option_e_image')
        question.option_f = request.form.get('option_f')
        question.option_f_image = request.form.get('option_f_image')
        
        db.session.add(question)
        db.session.commit()
        
        flash('题目创建成功', 'success')
        return redirect(url_for('questions.manage'))
    
    subjects = Subject.query.filter_by(is_active=True).all()
    return render_template('questions/create.html', subjects=subjects)

@questions_bp.route('/<int:id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def edit(id):
    question = Question.query.get_or_404(id)

    referrer = request.referrer or ''
    from_admin = '/admin/' in referrer

    if request.method == 'POST':
        question.subject_id = request.form.get('subject_id')
        question.chapter_id = request.form.get('chapter_id')
        question.content = request.form.get('content')
        question.question_type = request.form.get('question_type')
        question.difficulty = request.form.get('difficulty', 1, type=int)
        question.correct_answer = request.form.get('correct_answer', '').upper()
        question.analysis = request.form.get('analysis')
        question.points = request.form.get('points', 10, type=int)
        question.time_limit = request.form.get('time_limit', 60, type=int)
        question.image_url = request.form.get('image_url')
        
        question.option_a = request.form.get('option_a')
        question.option_a_image = request.form.get('option_a_image')
        question.option_b = request.form.get('option_b')
        question.option_b_image = request.form.get('option_b_image')
        question.option_c = request.form.get('option_c')
        question.option_c_image = request.form.get('option_c_image')
        question.option_d = request.form.get('option_d')
        question.option_d_image = request.form.get('option_d_image')
        question.option_e = request.form.get('option_e')
        question.option_e_image = request.form.get('option_e_image')
        question.option_f = request.form.get('option_f')
        question.option_f_image = request.form.get('option_f_image')
        
        db.session.commit()

        flash('题目更新成功', 'success')

        if request.form.get('from_admin') == '1':
            return redirect(url_for('admin.questions'))
        return redirect(url_for('questions.manage'))

    subjects = Subject.query.filter_by(is_active=True).all()
    chapters = Chapter.query.filter_by(subject_id=question.subject_id).all() if question.subject_id else []

    return render_template('questions/edit.html', question=question, subjects=subjects, chapters=chapters, from_admin=from_admin)

@questions_bp.route('/<int:id>/delete', methods=['POST'])
@login_required
@admin_required
def delete(id):
    question = Question.query.get_or_404(id)
    db.session.delete(question)
    db.session.commit()
    
    flash('题目删除成功', 'success')
    return redirect(url_for('questions.manage'))

@questions_bp.route('/template')
@login_required
def download_template():
    from app.utils.quiz_template import generate_import_template
    output = generate_import_template()
    return send_file(
        output,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name='题目导入模板.xlsx'
    )

@questions_bp.route('/api/chapters/<int:subject_id>')
@login_required
def get_chapters(subject_id):
    all_chapters = Chapter.query.filter_by(subject_id=subject_id, is_active=True).order_by(Chapter.order).all()
    
    chapter_dict = {c.id: c for c in all_chapters}
    children_map = {}
    root_chapters = []
    
    for chapter in all_chapters:
        if chapter.parent_id is None:
            root_chapters.append(chapter)
        else:
            if chapter.parent_id not in children_map:
                children_map[chapter.parent_id] = []
            children_map[chapter.parent_id].append(chapter)
    
    result = []
    def flatten_tree(chapters, indent=0):
        for chapter in chapters:
            has_children = chapter.id in children_map and len(children_map[chapter.id]) > 0
            chapter_data = {
                'id': chapter.id, 
                'name': chapter.get_full_path(),
                'has_children': has_children,
                'level': chapter.level
            }
            result.append(chapter_data)
            if chapter.id in children_map:
                flatten_tree(children_map[chapter.id], indent + 1)
    
    flatten_tree(root_chapters)
    return jsonify(result)

@questions_bp.route('/api/upload-image', methods=['POST'])
@login_required
def upload_question_image():
    if 'image' not in request.files:
        return jsonify({'success': False, 'message': '没有选择图片'})
    
    file = request.files['image']
    if file.filename == '':
        return jsonify({'success': False, 'message': '没有选择图片'})
    
    ext = file.filename.rsplit('.', 1)[1].lower() if '.' in file.filename else ''
    if ext not in ('png', 'jpg', 'jpeg', 'gif', 'webp'):
        return jsonify({'success': False, 'message': '不支持的图片格式'})
    
    upload_dir = os.path.join(current_app.root_path, 'static', 'questions')
    os.makedirs(upload_dir, exist_ok=True)
    
    filename = f"{datetime.now().strftime('%Y%m%d')}_{uuid.uuid4().hex[:8]}.{ext}"
    filepath = os.path.join(upload_dir, filename)
    file.save(filepath)
    
    image_url = f"/static/questions/{filename}"
    return jsonify({'success': True, 'image_url': image_url})

@questions_bp.route('/api/update-image/<int:id>', methods=['POST'])
@login_required
def update_question_image(id):
    question = Question.query.get_or_404(id)
    data = request.get_json()
    
    field = data.get('field', 'image_url')
    image_url = data.get('image_url', '')
    
    valid_fields = ['image_url', 'option_a_image', 'option_b_image', 
                    'option_c_image', 'option_d_image', 'option_e_image', 'option_f_image']
    
    if field in valid_fields:
        setattr(question, field, image_url if image_url else None)
        db.session.commit()
        return jsonify({'success': True, 'image_url': image_url})
    
    return jsonify({'success': False, 'message': '无效的字段'})

@questions_bp.route('/api/delete-image/<int:id>', methods=['POST'])
@login_required
def delete_question_image(id):
    question = Question.query.get_or_404(id)
    data = request.get_json()
    
    field = data.get('field', 'image_url')
    
    valid_fields = ['image_url', 'option_a_image', 'option_b_image', 
                    'option_c_image', 'option_d_image', 'option_e_image', 'option_f_image']
    
    if field in valid_fields:
        old_image = getattr(question, field, None)
        if old_image and old_image.startswith('/static/questions/'):
            try:
                old_path = os.path.join(current_app.root_path, 'static', 'questions', 
                                       old_image.split('/')[-1])
                if os.path.exists(old_path):
                    os.remove(old_path)
            except:
                pass
        setattr(question, field, None)
        db.session.commit()
        return jsonify({'success': True})
    
    return jsonify({'success': False, 'message': '无效的字段'})
