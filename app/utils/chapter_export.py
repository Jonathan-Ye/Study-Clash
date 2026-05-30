import json
import pandas as pd
from datetime import datetime, timezone
from io import BytesIO
from flask import current_app
from app import db
from app.models import Subject, Chapter


# 导出数量上限
MAX_EXPORT_COUNT = 5000


def export_chapters_json(subject_id=None, exported_by='admin'):
    """导出章节为JSON格式

    Args:
        subject_id: 学科ID，为None时导出全部
        exported_by: 导出人用户名

    Returns:
        tuple: (json_bytesio, report)
        - 成功: (BytesIO, {'total_count': int, 'subject_count': int})
        - 失败: (None, {'error': str})
    """
    query = Chapter.query
    if subject_id:
        query = query.filter_by(subject_id=subject_id)

    chapters = query.order_by(Chapter.subject_id, Chapter.level, Chapter.order).all()

    if not chapters:
        return None, {'error': '当前筛选条件下无章节数据'}

    if len(chapters) > MAX_EXPORT_COUNT:
        return None, {'error': f'导出数量({len(chapters)})超过上限({MAX_EXPORT_COUNT})，请缩小筛选范围'}

    # 收集涉及的学科
    subject_ids = set(c.subject_id for c in chapters if c.subject_id)
    subjects = Subject.query.filter(Subject.id.in_(subject_ids)).all() if subject_ids else []

    # 构建JSON结构
    export_data = {
        'metadata': {
            'export_version': '1.0',
            'export_time': datetime.now(timezone.utc).isoformat(),
            'exported_by': exported_by,
            'total_count': len(chapters),
            'subject_count': len(subjects)
        },
        'subjects': [{
            'id': s.id,
            'name': s.name,
            'code': s.code or '',
            'description': s.description or '',
            'is_active': s.is_active
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
        } for c in chapters]
    }

    # 生成JSON文件
    json_str = json.dumps(export_data, ensure_ascii=False, indent=2)
    json_buffer = BytesIO(json_str.encode('utf-8'))
    json_buffer.seek(0)

    report = {
        'total_count': len(chapters),
        'subject_count': len(subjects)
    }

    return json_buffer, report


def export_chapters_excel(subject_id=None, exported_by='admin'):
    """导出章节为Excel格式

    Args:
        subject_id: 学科ID，为None时导出全部
        exported_by: 导出人用户名

    Returns:
        tuple: (excel_bytesio, report)
        - 成功: (BytesIO, {'total_count': int, 'subject_count': int})
        - 失败: (None, {'error': str})
    """
    query = Chapter.query
    if subject_id:
        query = query.filter_by(subject_id=subject_id)

    chapters = query.order_by(Chapter.subject_id, Chapter.level, Chapter.order).all()

    if not chapters:
        return None, {'error': '当前筛选条件下无章节数据'}

    if len(chapters) > MAX_EXPORT_COUNT:
        return None, {'error': f'导出数量({len(chapters)})超过上限({MAX_EXPORT_COUNT})，请缩小筛选范围'}

    # 收集涉及的学科
    subject_ids = set(c.subject_id for c in chapters if c.subject_id)
    subjects = Subject.query.filter(Subject.id.in_(subject_ids)).all() if subject_ids else []

    output = BytesIO()

    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        # 学科工作表
        if subjects:
            subject_data = [{
                'ID': s.id,
                '名称': s.name,
                '代码': s.code or '',
                '描述': s.description or '',
                '启用': '是' if s.is_active else '否'
            } for s in subjects]
            pd.DataFrame(subject_data).to_excel(writer, index=False, sheet_name='学科')

        # 章节工作表
        chapter_data = [{
            'ID': c.id,
            '学科名称': c.subject.name if c.subject else '',
            '父章节ID': c.parent_id or '',
            '名称': c.name,
            '层级': c.level,
            '排序': c.order,
            '描述': c.description or '',
            '启用': '是' if c.is_active else '否'
        } for c in chapters]
        pd.DataFrame(chapter_data).to_excel(writer, index=False, sheet_name='章节')

    output.seek(0)

    report = {
        'total_count': len(chapters),
        'subject_count': len(subjects)
    }

    return output, report
