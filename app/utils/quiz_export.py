import json
import pandas as pd
from datetime import datetime, timezone
from io import BytesIO
from flask import current_app
from app import db
from app.models import Subject, Chapter, Question


# 导出数量上限（已解除限制）
MAX_EXPORT_COUNT = 1000000000

# 题型映射
QUESTION_TYPE_MAP = {
    'single': '单选', 'multiple': '多选', 'judge': '判断', 'fill': '填空'
}

# 难度映射
DIFFICULTY_MAP = {
    1: '简单', 2: '中等', 3: '困难', 4: '极难'
}


def build_query(filters):
    """根据筛选条件构建查询

    Args:
        filters: dict, 筛选条件
            - subject_id: int
            - chapter_id: int
            - question_type: str
            - difficulty: int
            - status: str ('active'/'inactive')
            - keyword: str

    Returns:
        SQLAlchemy query对象
    """
    query = Question.query

    if filters.get('subject_id'):
        query = query.filter_by(subject_id=filters['subject_id'])
    if filters.get('chapter_id'):
        query = query.filter_by(chapter_id=filters['chapter_id'])
    if filters.get('question_type'):
        query = query.filter_by(question_type=filters['question_type'])
    if filters.get('difficulty'):
        query = query.filter_by(difficulty=filters['difficulty'])
    if filters.get('status'):
        query = query.filter_by(is_active=(filters['status'] == 'active'))
    if filters.get('keyword'):
        query = query.filter(Question.content.contains(filters['keyword']))

    return query


def export_questions_json(filters, exported_by='admin'):
    """导出题库为JSON格式

    Args:
        filters: dict, 筛选条件
        exported_by: str, 导出人用户名

    Returns:
        tuple: (json_bytesio, report)
        - json_bytesio: BytesIO对象包含JSON数据
        - report: dict, 导出报告 {'total_count', 'image_count', 'missing_images'}
    """
    query = build_query(filters)
    questions = query.order_by(Question.id.asc()).all()

    if not questions:
        return None, {'error': '当前筛选条件下无题目数据'}

    if len(questions) > MAX_EXPORT_COUNT:
        return None, {'error': f'导出数量({len(questions)})超过上限({MAX_EXPORT_COUNT})，请缩小筛选范围'}

    # 收集涉及的学科和章节
    subject_ids = set(q.subject_id for q in questions if q.subject_id)
    chapter_ids = set(q.chapter_id for q in questions if q.chapter_id)

    subjects = Subject.query.filter(Subject.id.in_(subject_ids)).all() if subject_ids else []
    chapters = Chapter.query.filter(Chapter.id.in_(chapter_ids)).all() if chapter_ids else []

    # 构建JSON结构
    export_data = {
        'metadata': {
            'export_version': '1.0',
            'export_time': datetime.now(timezone.utc).isoformat(),
            'exported_by': exported_by,
            'filter_conditions': {k: v for k, v in filters.items() if v},
            'total_count': len(questions),
            'image_count': 0,
            'missing_images': []
        },
        'subjects': [{
            'id': s.id,
            'name': s.name,
            'code': s.code or '',
            'description': s.description or '',
            'is_active': s.is_active,
            'applicable_majors': s.get_applicable_majors()
        } for s in subjects],
        'chapters': [{
            'id': c.id,
            'subject_id': c.subject_id,
            'parent_id': c.parent_id,
            'name': c.name,
            'level': c.level,
            'order': c.order,
            'description': c.description or '',
            'is_active': c.is_active
        } for c in chapters],
        'questions': []
    }

    # 统计图片数量
    image_fields = ['image_url', 'option_a_image', 'option_b_image', 'option_c_image',
                     'option_d_image', 'option_e_image', 'option_f_image']

    for q in questions:
        q_data = {
            'id': q.id,
            'subject_id': q.subject_id,
            'chapter_id': q.chapter_id,
            'question_type': q.question_type,
            'difficulty': q.difficulty,
            'content': q.content or '',
            'image_url': q.image_url or '',
            'option_a': q.option_a or '',
            'option_a_image': q.option_a_image or '',
            'option_b': q.option_b or '',
            'option_b_image': q.option_b_image or '',
            'option_c': q.option_c or '',
            'option_c_image': q.option_c_image or '',
            'option_d': q.option_d or '',
            'option_d_image': q.option_d_image or '',
            'option_e': q.option_e or '',
            'option_e_image': q.option_e_image or '',
            'option_f': q.option_f or '',
            'option_f_image': q.option_f_image or '',
            'correct_answer': q.correct_answer or '',
            'analysis': q.analysis or '',
            'points': q.points or 10,
            'time_limit': q.time_limit or 60,
            'is_active': q.is_active,
            'created_at': q.created_at.isoformat() if q.created_at else None,
            'updated_at': q.updated_at.isoformat() if q.updated_at else None
        }

        # 统计图片
        for field in image_fields:
            val = getattr(q, field, None)
            if val:
                export_data['metadata']['image_count'] += 1

        export_data['questions'].append(q_data)

    # 生成JSON文件
    json_str = json.dumps(export_data, ensure_ascii=False, indent=2)
    json_buffer = BytesIO(json_str.encode('utf-8'))
    json_buffer.seek(0)

    report = {
        'total_count': export_data['metadata']['total_count'],
        'image_count': export_data['metadata']['image_count'],
        'missing_images': export_data['metadata']['missing_images']
    }

    return json_buffer, report


def export_questions_excel(filters, exported_by='admin'):
    """导出题库为Excel格式（按学科分工作表）

    Args:
        filters: dict, 筛选条件
        exported_by: str, 导出人用户名

    Returns:
        tuple: (excel_bytesio, report)
        - excel_bytesio: BytesIO对象包含Excel数据
        - report: dict, 导出报告
    """
    query = build_query(filters)
    questions = query.order_by(Question.id.asc()).all()

    if not questions:
        return None, {'error': '当前筛选条件下无题目数据'}

    if len(questions) > MAX_EXPORT_COUNT:
        return None, {'error': f'导出数量({len(questions)})超过上限({MAX_EXPORT_COUNT})，请缩小筛选范围'}

    # 收集涉及的学科和章节
    subject_ids = set(q.subject_id for q in questions if q.subject_id)
    chapter_ids = set(q.chapter_id for q in questions if q.chapter_id)

    subjects = Subject.query.filter(Subject.id.in_(subject_ids)).all() if subject_ids else []
    chapters = Chapter.query.filter(Chapter.id.in_(chapter_ids)).all() if chapter_ids else []

    image_count = 0
    image_fields = ['image_url', 'option_a_image', 'option_b_image', 'option_c_image',
                     'option_d_image', 'option_e_image', 'option_f_image']

    output = BytesIO()

    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        # 学科工作表
        if subjects:
            subject_data = [{
                'ID': s.id, '名称': s.name, '代码': s.code or '',
                '描述': s.description or '', '启用': '是' if s.is_active else '否',
                '适用专业': ','.join(s.get_applicable_majors()) if s.get_applicable_majors() else '全部'
            } for s in subjects]
            pd.DataFrame(subject_data).to_excel(writer, index=False, sheet_name='学科')

        # 章节工作表
        if chapters:
            chapter_data = [{
                'ID': c.id, '学科ID': c.subject_id, '父章节ID': c.parent_id or '',
                '名称': c.name, '层级': c.level, '排序': c.order,
                '描述': c.description or '', '启用': '是' if c.is_active else '否'
            } for c in chapters]
            pd.DataFrame(chapter_data).to_excel(writer, index=False, sheet_name='章节')

        # 按学科分工作表写入题目
        questions_by_subject = {}
        for q in questions:
            sname = q.subject.name if q.subject else '未分类'
            if sname not in questions_by_subject:
                questions_by_subject[sname] = []
            questions_by_subject[sname].append(q)

            for field in image_fields:
                if getattr(q, field, None):
                    image_count += 1

        for sname, qs in questions_by_subject.items():
            # 工作表名最长31字符
            sheet_name = sname[:31]
            data = []
            for q in qs:
                data.append({
                    'ID': q.id,
                    '题目内容': q.content or '',
                    '题型': QUESTION_TYPE_MAP.get(q.question_type, q.question_type),
                    '难度': DIFFICULTY_MAP.get(q.difficulty, q.difficulty),
                    '正确答案': q.correct_answer or '',
                    '选项A': q.option_a or '',
                    '选项A图片': q.option_a_image or '',
                    '选项B': q.option_b or '',
                    '选项B图片': q.option_b_image or '',
                    '选项C': q.option_c or '',
                    '选项C图片': q.option_c_image or '',
                    '选项D': q.option_d or '',
                    '选项D图片': q.option_d_image or '',
                    '选项E': q.option_e or '',
                    '选项E图片': q.option_e_image or '',
                    '选项F': q.option_f or '',
                    '选项F图片': q.option_f_image or '',
                    '题目图片': q.image_url or '',
                    '解析': q.analysis or '',
                    '积分': q.points or 10,
                    '时间限制(秒)': q.time_limit or 60,
                    '章节': q.chapter.get_full_path() if q.chapter else '',
                    '状态': '启用' if q.is_active else '禁用',
                    '创建时间': q.created_at.strftime('%Y-%m-%d %H:%M') if q.created_at else '',
                    '更新时间': q.updated_at.strftime('%Y-%m-%d %H:%M') if q.updated_at else ''
                })
            pd.DataFrame(data).to_excel(writer, index=False, sheet_name=sheet_name)

    output.seek(0)

    report = {
        'total_count': len(questions),
        'image_count': image_count,
        'missing_images': []
    }

    return output, report
