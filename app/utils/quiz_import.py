import json
import pandas as pd
from datetime import datetime, timezone
from flask import current_app
from app import db
from app.models import Subject, Chapter, Question


# 导入数量上限（已解除限制）
MAX_IMPORT_COUNT = 1000000000

# 文件大小上限（10MB）
MAX_FILE_SIZE = 10 * 1024 * 1024

# 题型反向映射
QUESTION_TYPE_REVERSE = {
    '单选': 'single', '多选': 'multiple', '判断': 'judge', '填空': 'fill',
    'single': 'single', 'multiple': 'multiple', 'judge': 'judge', 'fill': 'fill'
}

# 难度反向映射
DIFFICULTY_REVERSE = {
    '简单': 1, '中等': 2, '困难': 3, '极难': 4,
    '1': 1, '2': 2, '3': 3, '4': 4
}


class ValidationResult:
    """校验结果"""
    def __init__(self):
        self.valid_list = []      # 有效题目数据
        self.invalid_list = []    # 无效题目数据 [{'row': int, 'data': dict, 'errors': list}]
        self.conflict_count = 0   # ID冲突数量
        self.conflict_details = []  # ID冲突详情 [{'id': int, 'existing_content': str, 'import_content': str, 'row': int}]
        self.total_count = 0      # 总题目数
        self.subjects = []        # 学科数据
        self.chapters = []        # 章节数据
        self.new_chapters_count = 0  # 将新建的章节数量
        self.warnings = []        # 警告信息列表


class ImportResult:
    """导入结果"""
    def __init__(self):
        self.success = 0          # 成功导入数
        self.skipped = 0          # 跳过数
        self.overwritten = 0      # 覆盖数
        self.failed = 0           # 失败数
        self.failed_details = []  # 失败详情
        self.image_result = None  # 图片处理结果


def validate_import(file_storage, file_format):
    """校验导入文件

    Args:
        file_storage: FileStorage对象
        file_format: str, 'json'或'excel'

    Returns:
        ValidationResult
    """
    result = ValidationResult()

    # 校验文件大小
    file_storage.seek(0, 2)
    file_size = file_storage.tell()
    file_storage.seek(0)

    if file_size > MAX_FILE_SIZE:
        result.invalid_list.append({
            'row': 0,
            'data': {},
            'errors': [f'文件大小({file_size}字节)超过限制({MAX_FILE_SIZE}字节)']
        })
        return result

    try:
        if file_format == 'json':
            _parse_json(file_storage, result)
        elif file_format == 'excel':
            _parse_excel(file_storage, result)
        else:
            result.invalid_list.append({
                'row': 0, 'data': {}, 'errors': [f'不支持的文件格式: {file_format}']
            })
    except json.JSONDecodeError:
        result.invalid_list.append({
            'row': 0, 'data': {}, 'errors': ['JSON文件格式错误，请检查文件内容']
        })
    except Exception as e:
        result.invalid_list.append({
            'row': 0, 'data': {}, 'errors': [f'文件解析失败: {str(e)}']
        })

    return result


def _parse_json(file_storage, result):
    """解析JSON格式导入文件"""
    data = json.load(file_storage)

    # 提取学科和章节数据
    result.subjects = data.get('subjects', [])
    result.chapters = data.get('chapters', [])
    questions_data = data.get('questions', [])

    result.total_count = len(questions_data)

    if result.total_count > MAX_IMPORT_COUNT:
        result.invalid_list.append({
            'row': 0, 'data': {},
            'errors': [f'题目数量({result.total_count})超过上限({MAX_IMPORT_COUNT})']
        })
        return

    # 批量获取现有题目的内容、类型、答案，用于快速查重
    existing_questions = db.session.query(
        Question.content, Question.question_type, Question.correct_answer
    ).all()
    existing_keys = {(c, t, a) for c, t, a in existing_questions}

    batch_seen = set()

    for i, q_data in enumerate(questions_data, 1):
        errors = _validate_question_data(q_data)
        if errors:
            result.invalid_list.append({'row': i, 'data': q_data, 'errors': errors})
        else:
            conflict_reason = None
            q_id = q_data.get('id')
            if q_id and Question.query.get(q_id):
                conflict_reason = 'ID'
                existing = Question.query.get(q_id)
            else:
                content = q_data.get('content', '').strip()
                q_type = q_data.get('question_type')
                answer = q_data.get('correct_answer', '').strip()
                if content:
                    dup_key = (content, q_type, answer)
                    if dup_key in batch_seen:
                        conflict_reason = '批内重复'
                        existing = None
                    elif dup_key in existing_keys:
                        conflict_reason = '内容'
                        # 获取现有题目用于显示详情
                        existing = Question.query.filter_by(content=content, question_type=q_type, correct_answer=answer).first()
                    batch_seen.add(dup_key)
            if conflict_reason:
                result.conflict_count += 1
                result.conflict_details.append({
                    'id': existing.id if existing else None,
                    'existing_content': existing.content[:50] if existing and existing.content else '',
                    'import_content': q_data.get('content', '')[:50],
                    'row': i,
                    'reason': conflict_reason
                })
            result.valid_list.append(q_data)


def _parse_excel(file_storage, result):
    """解析Excel格式导入文件"""
    all_sheets = pd.read_excel(file_storage, sheet_name=None)

    question_sheets = []
    for sheet_name, df in all_sheets.items():
        if '题目内容' in df.columns:
            question_sheets.append(df)

    if not question_sheets:
        result.invalid_list.append({
            'row': 0, 'data': {},
            'errors': ['未找到包含"题目内容"列的工作表，请检查Excel格式']
        })
        return

    df = pd.concat(question_sheets, ignore_index=True)

    result.total_count = len(df)

    if result.total_count > MAX_IMPORT_COUNT:
        result.invalid_list.append({
            'row': 0, 'data': {},
            'errors': [f'题目数量({result.total_count})超过上限({MAX_IMPORT_COUNT})']
        })
        return

    # 批量获取现有题目的内容、类型、答案，用于快速查重
    existing_questions = db.session.query(
        Question.content, Question.question_type, Question.correct_answer
    ).all()
    existing_keys = {(c, t, a) for c, t, a in existing_questions}

    batch_seen = set()

    for i, row in df.iterrows():
        q_data = _excel_row_to_dict(row)
        errors = _validate_question_data(q_data)
        if errors:
            result.invalid_list.append({'row': i + 2, 'data': q_data, 'errors': errors})
        else:
            conflict_reason = None
            q_id = q_data.get('id')
            if q_id and Question.query.get(q_id):
                conflict_reason = 'ID'
                existing = Question.query.get(q_id)
            else:
                content = q_data.get('content', '').strip()
                q_type = q_data.get('question_type')
                answer = q_data.get('correct_answer', '').strip()
                if content:
                    dup_key = (content, q_type, answer)
                    if dup_key in batch_seen:
                        conflict_reason = '批内重复'
                        existing = None
                    elif dup_key in existing_keys:
                        conflict_reason = '内容'
                        # 获取现有题目用于显示详情
                        existing = Question.query.filter_by(content=content, question_type=q_type, correct_answer=answer).first()
                    batch_seen.add(dup_key)
            if conflict_reason:
                result.conflict_count += 1
                result.conflict_details.append({
                    'id': existing.id if existing else None,
                    'existing_content': existing.content[:50] if existing and existing.content else '',
                    'import_content': q_data.get('content', '')[:50],
                    'row': i + 2,
                    'reason': conflict_reason
                })
            result.valid_list.append(q_data)


def _safe_str(val):
    """安全地将单元格值转为字符串，NaN转为空字符串"""
    if pd.isna(val):
        return ''
    if isinstance(val, datetime):
        return val.strftime('%Y-%m-%d %H:%M:%S')
    return str(val).strip()


def _safe_int(val, default=0):
    """安全地将单元格值转为整数，NaN转为默认值"""
    if pd.isna(val):
        return default
    return int(val)


def _excel_row_to_dict(row):
    """将Excel行转为题目字典"""
    q_type_raw = _safe_str(row.get('题型'))
    difficulty_raw = row.get('难度')

    if pd.notna(difficulty_raw):
        difficulty_str = str(int(difficulty_raw)) if isinstance(difficulty_raw, (int, float)) else str(difficulty_raw).strip()
    else:
        difficulty_str = ''

    return {
        'id': _safe_int(row.get('ID'), None) if pd.notna(row.get('ID')) else None,
        'content': _safe_str(row.get('题目内容')),
        'question_type': QUESTION_TYPE_REVERSE.get(q_type_raw, q_type_raw),
        'difficulty': DIFFICULTY_REVERSE.get(difficulty_str),
        'correct_answer': _safe_str(row.get('正确答案')),
        'option_a': _safe_str(row.get('选项A')),
        'option_b': _safe_str(row.get('选项B')),
        'option_c': _safe_str(row.get('选项C')),
        'option_d': _safe_str(row.get('选项D')),
        'option_e': _safe_str(row.get('选项E')),
        'option_f': _safe_str(row.get('选项F')),
        'analysis': _safe_str(row.get('解析')),
        'subject_name': _safe_str(row.get('学科')),
        'chapter_name': _safe_str(row.get('章节')),
        'points': _safe_int(row.get('积分'), 10),
        'time_limit': _safe_int(row.get('时间限制(秒)'), 60),
    }


def _validate_question_data(q_data):
    """校验单条题目数据"""
    errors = []

    if not q_data.get('content'):
        errors.append('题目内容不能为空')

    q_type = q_data.get('question_type', '')
    if q_type not in ('single', 'multiple', 'judge', 'fill'):
        errors.append(f'无效的题型: {q_type}')

    difficulty = q_data.get('difficulty')
    if difficulty not in (1, 2, 3, 4, None):
        errors.append(f'无效的难度: {difficulty}')

    if not q_data.get('correct_answer'):
        errors.append('正确答案不能为空')

    # 选择题至少需要2个选项
    if q_type in ('single', 'multiple'):
        if not q_data.get('option_a') and not q_data.get('option_b'):
            errors.append('选择题至少需要选项A和选项B')

    # 学科校验
    subject_id = q_data.get('subject_id')
    subject_name = q_data.get('subject_name', '')
    if not subject_id and not subject_name:
        errors.append('题目必须指定学科（subject_id 或 subject_name）')

    # 章节路径校验
    chapter_name = q_data.get('chapter_name', '')
    if chapter_name:
        from app.utils.chapter_resolver import parse_chapter_path
        _, path_error, path_subject_name = parse_chapter_path(chapter_name)
        if path_error:
            errors.append(path_error)
        else:
            # 如果路径中没有学科前缀，则必须有学科列或subject_id
            if not path_subject_name and not q_data.get('subject_name') and not q_data.get('subject_id'):
                errors.append('指定章节时必须同时指定学科')

    return errors


def execute_import(valid_data, conflict_strategy='skip', subjects_data=None, chapters_data=None):
    """执行题库导入

    Args:
        valid_data: list, 校验通过的题目数据列表
        conflict_strategy: str, 冲突处理策略 skip/overwrite/append
        subjects_data: list, 学科数据（JSON导入时使用）
        chapters_data: list, 章节数据（JSON导入时使用）

    Returns:
        ImportResult
    """
    result = ImportResult()
    chapter_cache = {}  # 章节缓存，避免同一批次中重复查询

    try:
        # 先导入学科和章节（JSON格式时）
        if subjects_data:
            _import_subjects(subjects_data)
        if chapters_data:
            _import_chapters(chapters_data)

        imported_keys = set()

        for q_data in valid_data:
            try:
                q_id = q_data.get('id')
                existing = Question.query.get(q_id) if q_id else None

                if not existing and conflict_strategy != 'append':
                    content = q_data.get('content', '').strip()
                    q_type = q_data.get('question_type')
                    answer = q_data.get('correct_answer', '').strip()
                    if content:
                        dup_key = (content, q_type, answer)
                        if dup_key in imported_keys:
                            result.skipped += 1
                            continue
                        existing = Question.query.filter_by(content=content, question_type=q_type, correct_answer=answer).first()

                if existing and conflict_strategy == 'skip':
                    result.skipped += 1
                    continue
                elif existing and conflict_strategy == 'overwrite':
                    _update_question(existing, q_data, chapter_cache=chapter_cache)
                    result.overwritten += 1
                else:
                    question = _create_question(q_data, chapter_cache=chapter_cache)
                    db.session.add(question)
                    result.success += 1

                content = q_data.get('content', '').strip()
                q_type = q_data.get('question_type')
                answer = q_data.get('correct_answer', '').strip()
                if content:
                    imported_keys.add((content, q_type, answer))

            except Exception as e:
                result.failed += 1
                result.failed_details.append({
                    'id': q_data.get('id'),
                    'content': q_data.get('content', '')[:50],
                    'error': str(e)
                })

        db.session.commit()

    except Exception as e:
        db.session.rollback()
        result.failed += len(valid_data) - result.success - result.skipped - result.overwritten
        result.failed_details.append({'error': f'导入过程中断: {str(e)}'})

    return result


def _import_subjects(subjects_data):
    """导入学科数据（自动创建不存在的学科）"""
    for s_data in subjects_data:
        existing = Subject.query.get(s_data.get('id'))
        if not existing:
            existing = Subject.query.filter_by(name=s_data.get('name')).first()
        if not existing and s_data.get('name'):
            subject = Subject(
                name=s_data['name'],
                code=s_data.get('code', ''),
                description=s_data.get('description', ''),
                is_active=s_data.get('is_active', True)
            )
            if 'applicable_majors' in s_data:
                subject.set_applicable_majors(s_data['applicable_majors'])
            db.session.add(subject)
            db.session.flush()
        elif existing and 'applicable_majors' in s_data:
            existing.set_applicable_majors(s_data['applicable_majors'])


def _import_chapters(chapters_data):
    """导入章节数据（自动创建不存在的章节）"""
    for c_data in chapters_data:
        existing = Chapter.query.get(c_data.get('id'))
        if not existing and c_data.get('name'):
            chapter = Chapter(
                subject_id=c_data.get('subject_id'),
                parent_id=c_data.get('parent_id'),
                name=c_data['name'],
                level=c_data.get('level', 1),
                order=c_data.get('order', 0),
                description=c_data.get('description', ''),
                is_active=c_data.get('is_active', True)
            )
            db.session.add(chapter)


def _normalize_answer(question_type, answer):
    """标准化答案格式
    
    Args:
        question_type: 题型 (single/multiple/judge/fill)
        answer: 原始答案
    
    Returns:
        标准化后的答案
    """
    if not answer:
        return answer
    
    answer = str(answer).strip()
    
    # 多选题：统一为大写字母+逗号分隔格式
    if question_type == 'multiple':
        # 转大写
        answer = answer.upper()
        # 如果包含逗号，按逗号分割后重新组合
        if ',' in answer:
            parts = [p.strip() for p in answer.split(',') if p.strip()]
            return ','.join(sorted(parts))
        # 否则视为连续字符
        else:
            chars = [c for c in answer if c.isalpha()]
            return ','.join(sorted(chars))
    
    # 单选题和判断题：转大写
    elif question_type in ('single', 'judge'):
        return answer.upper()
    
    # 填空题：保持原样
    return answer


def _create_question(q_data, chapter_cache=None):
    """创建新题目对象"""
    # 处理学科和章节
    subject_id = q_data.get('subject_id')
    chapter_id = q_data.get('chapter_id')

    # 如果没有subject_id但有subject_name，尝试查找或创建
    if not subject_id and q_data.get('subject_name'):
        subject = Subject.query.filter_by(name=q_data['subject_name']).first()
        if not subject:
            subject = Subject(name=q_data['subject_name'], is_active=True)
            db.session.add(subject)
            db.session.flush()
        subject_id = subject.id

    # subject_id 是必填项
    if not subject_id:
        raise ValueError('题目必须指定学科（subject_id 或 subject_name）')

    # 如果没有chapter_id但有chapter_name且有subject_id，尝试查找或创建章节
    if not chapter_id and q_data.get('chapter_name') and subject_id:
        from app.utils.chapter_resolver import resolve_chapter
        chapter_id, _, _ = resolve_chapter(
            q_data['chapter_name'], subject_id, cache=chapter_cache
        )

    # 标准化答案
    question_type = q_data.get('question_type', 'single')
    correct_answer = _normalize_answer(question_type, q_data.get('correct_answer', ''))

    return Question(
        subject_id=subject_id,
        chapter_id=chapter_id,
        question_type=question_type,
        difficulty=q_data.get('difficulty', 2),
        content=q_data.get('content', ''),
        image_url=q_data.get('image_url', ''),
        option_a=q_data.get('option_a', ''),
        option_a_image=q_data.get('option_a_image', ''),
        option_b=q_data.get('option_b', ''),
        option_b_image=q_data.get('option_b_image', ''),
        option_c=q_data.get('option_c', ''),
        option_c_image=q_data.get('option_c_image', ''),
        option_d=q_data.get('option_d', ''),
        option_d_image=q_data.get('option_d_image', ''),
        option_e=q_data.get('option_e', ''),
        option_e_image=q_data.get('option_e_image', ''),
        option_f=q_data.get('option_f', ''),
        option_f_image=q_data.get('option_f_image', ''),
        correct_answer=correct_answer,
        analysis=q_data.get('analysis', ''),
        points=q_data.get('points', 10),
        time_limit=q_data.get('time_limit', 60),
        is_active=q_data.get('is_active', True)
    )


def _update_question(existing, q_data, chapter_cache=None):
    """更新现有题目"""
    if 'content' in q_data and q_data['content']:
        existing.content = q_data['content']
    if 'question_type' in q_data:
        existing.question_type = q_data['question_type']
    if 'difficulty' in q_data and q_data['difficulty'] in (1, 2, 3, 4):
        existing.difficulty = q_data['difficulty']
    if 'correct_answer' in q_data:
        # 标准化答案
        question_type = q_data.get('question_type', existing.question_type)
        existing.correct_answer = _normalize_answer(question_type, q_data['correct_answer'])
    if 'option_a' in q_data:
        existing.option_a = q_data['option_a']
    if 'option_b' in q_data:
        existing.option_b = q_data['option_b']
    if 'option_c' in q_data:
        existing.option_c = q_data['option_c']
    if 'option_d' in q_data:
        existing.option_d = q_data['option_d']
    if 'option_e' in q_data:
        existing.option_e = q_data['option_e']
    if 'option_f' in q_data:
        existing.option_f = q_data['option_f']
    if 'analysis' in q_data:
        existing.analysis = q_data['analysis']
    if 'points' in q_data:
        existing.points = q_data['points']
    if 'time_limit' in q_data:
        existing.time_limit = q_data['time_limit']
    if 'is_active' in q_data:
        existing.is_active = q_data['is_active']
    if 'subject_id' in q_data:
        existing.subject_id = q_data['subject_id']
    if 'chapter_id' in q_data:
        existing.chapter_id = q_data['chapter_id']

    # 学科名称更新
    if 'subject_name' in q_data and q_data['subject_name'] and not q_data.get('subject_id'):
        subject = Subject.query.filter_by(name=q_data['subject_name']).first()
        if subject:
            existing.subject_id = subject.id

    # 章节名称更新
    if 'chapter_name' in q_data and q_data['chapter_name'] and existing.subject_id:
        from app.utils.chapter_resolver import resolve_chapter
        if chapter_cache is None:
            chapter_cache = {}
        chapter_id, _, _ = resolve_chapter(
            q_data['chapter_name'], existing.subject_id, cache=chapter_cache
        )
        if chapter_id:
            existing.chapter_id = chapter_id

    existing.updated_at = datetime.now(timezone.utc)
