import json
import pandas as pd
from datetime import datetime
from flask import current_app
from app import db
from app.models import Subject, Chapter


# 导入数量上限
MAX_IMPORT_COUNT = 1000

# 文件大小上限（10MB）
MAX_FILE_SIZE = 10 * 1024 * 1024


class ChapterValidationResult:
    """章节导入校验结果"""
    def __init__(self):
        self.valid_list = []      # 有效章节数据
        self.invalid_list = []    # 无效章节数据 [{'row': int, 'data': dict, 'errors': list}]
        self.conflict_count = 0   # 冲突数量（同名同位置）
        self.total_count = 0      # 总章节数
        self.subjects = []        # 学科数据（JSON导入时）
        self.warnings = []        # 警告信息列表


class ChapterImportResult:
    """章节导入执行结果"""
    def __init__(self):
        self.success = 0          # 成功导入数
        self.skipped = 0          # 跳过数
        self.overwritten = 0      # 覆盖数
        self.failed = 0           # 失败数
        self.failed_details = []  # 失败详情


def validate_chapter_import(file_storage, file_format):
    """校验章节导入文件

    Args:
        file_storage: FileStorage对象
        file_format: 'json'或'excel'

    Returns:
        ChapterValidationResult
    """
    result = ChapterValidationResult()

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
            _parse_chapters_json(file_storage, result)
        elif file_format == 'excel':
            _parse_chapters_excel(file_storage, result)
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


def _parse_chapters_json(file_storage, result):
    """解析JSON格式章节导入文件"""
    data = json.load(file_storage)

    # 提取学科和章节数据
    result.subjects = data.get('subjects', [])
    chapters_data = data.get('chapters', [])

    result.total_count = len(chapters_data)

    if result.total_count > MAX_IMPORT_COUNT:
        result.invalid_list.append({
            'row': 0, 'data': {},
            'errors': [f'章节数量({result.total_count})超过上限({MAX_IMPORT_COUNT})']
        })
        return

    for i, c_data in enumerate(chapters_data, 1):
        errors = _validate_chapter_data(c_data)
        if errors:
            result.invalid_list.append({'row': i, 'data': c_data, 'errors': errors})
        else:
            # 检查冲突（同名同位置）
            c_id = c_data.get('id')
            subject_id = c_data.get('subject_id')
            parent_id = c_data.get('parent_id')
            name = c_data.get('name', '')

            if c_id and Chapter.query.get(c_id):
                result.conflict_count += 1
            elif subject_id and name:
                existing = Chapter.query.filter_by(
                    subject_id=subject_id,
                    parent_id=parent_id if parent_id else None,
                    name=name
                ).first()
                if existing:
                    result.conflict_count += 1

            result.valid_list.append(c_data)


def _parse_chapters_excel(file_storage, result):
    """解析Excel格式章节导入文件"""
    # 智能识别工作表：优先读取"章节"工作表，否则读取包含章节关键字段的工作表
    xls = pd.ExcelFile(file_storage)
    target_sheet = None

    # 优先按名称查找
    for name in xls.sheet_names:
        if name.strip() == '章节':
            target_sheet = name
            break

    # 若未找到"章节"工作表，查找包含章节关键字段的工作表
    if target_sheet is None:
        chapter_keywords = ['章节名称', '名称', '层级', '学科名称']
        for name in xls.sheet_names:
            df_check = pd.read_excel(xls, sheet_name=name, nrows=0)
            cols = list(df_check.columns)
            match_count = sum(1 for kw in chapter_keywords if kw in cols)
            if match_count >= 2:
                target_sheet = name
                break

    # 兜底：使用第一个工作表
    if target_sheet is None:
        target_sheet = xls.sheet_names[0]

    df = pd.read_excel(xls, sheet_name=target_sheet)

    result.total_count = len(df)

    if result.total_count > MAX_IMPORT_COUNT:
        result.invalid_list.append({
            'row': 0, 'data': {},
            'errors': [f'章节数量({result.total_count})超过上限({MAX_IMPORT_COUNT})']
        })
        return

    for i, row in df.iterrows():
        c_data = _excel_row_to_dict(row)
        errors = _validate_chapter_data(c_data)
        if errors:
            result.invalid_list.append({'row': i + 2, 'data': c_data, 'errors': errors})
        else:
            # 检查冲突
            subject_name = c_data.get('subject_name', '')
            name = c_data.get('name', '')
            parent_name = c_data.get('parent_name', '')
            subject_id = c_data.get('subject_id')
            parent_id = c_data.get('parent_id')

            if name and (subject_name or subject_id):
                # 解析学科ID
                if not subject_id and subject_name:
                    subject = Subject.query.filter_by(name=subject_name).first()
                    if subject:
                        subject_id = subject.id

                if subject_id:
                    # 解析父章节ID
                    if not parent_id and parent_name:
                        parent = Chapter.query.filter_by(
                            subject_id=subject_id, name=parent_name
                        ).order_by(Chapter.level.desc()).first()
                        if parent:
                            parent_id = parent.id

                    existing = Chapter.query.filter_by(
                        subject_id=subject_id,
                        parent_id=parent_id if parent_id else None,
                        name=name
                    ).first()
                    if existing:
                        result.conflict_count += 1

            result.valid_list.append(c_data)


def _safe_str(val):
    """安全地将单元格值转为字符串，NaN转为空字符串"""
    if pd.isna(val):
        return ''
    return str(val).strip()


def _safe_int(val, default=0):
    """安全地将单元格值转为整数，NaN转为默认值"""
    if pd.isna(val):
        return default
    return int(val)


def _excel_row_to_dict(row):
    """将Excel行转为章节字典，兼容导入模板格式和导出Excel格式"""
    is_active_raw = _safe_str(row.get('启用'))

    name_val = row.get('章节名称', row.get('名称', ''))
    name = _safe_str(name_val)

    parent_name_val = row.get('父章节名称', '')
    parent_name = _safe_str(parent_name_val)
    parent_id_val = row.get('父章节ID', '')
    parent_id_from_excel = int(parent_id_val) if pd.notna(parent_id_val) and str(parent_id_val).strip() else None

    subject_id_val = row.get('学科ID', '')
    subject_id_from_excel = int(subject_id_val) if pd.notna(subject_id_val) and str(subject_id_val).strip() else None

    id_val = row.get('ID', '')
    id_from_excel = int(id_val) if pd.notna(id_val) and str(id_val).strip() else None

    result = {
        'subject_name': _safe_str(row.get('学科名称')),
        'name': name,
        'level': int(row.get('层级', 1)) if pd.notna(row.get('层级')) else 1,
        'parent_name': parent_name,
        'order': int(row.get('排序', 0)) if pd.notna(row.get('排序')) else 0,
        'description': _safe_str(row.get('描述')),
        'is_active': is_active_raw != '否' if is_active_raw else True
    }

    # 附加导出格式的字段
    if id_from_excel:
        result['id'] = id_from_excel
    if subject_id_from_excel:
        result['subject_id'] = subject_id_from_excel
    if parent_id_from_excel:
        result['parent_id'] = parent_id_from_excel

    return result


def _validate_chapter_data(c_data):
    """校验单条章节数据，返回错误列表"""
    errors = []

    # 章节名称不能为空
    if not c_data.get('name'):
        errors.append('章节名称不能为空')

    # 层级必须为1-3
    level = c_data.get('level')
    if level not in (1, 2, 3):
        errors.append(f'章节层级不能超过3级（当前值: {level}）')

    # 学科关联校验
    subject_name = c_data.get('subject_name', '')
    subject_id = c_data.get('subject_id')
    if not subject_name and not subject_id:
        errors.append('必须指定学科（学科名称或学科ID）')

    # 若有subject_id，检查学科是否存在
    if subject_id and not Subject.query.get(subject_id):
        errors.append('关联的学科不存在')

    # level=1时不应有父章节
    if level == 1 and (c_data.get('parent_name') or c_data.get('parent_id')):
        errors.append('顶级章节（层级1）不应指定父章节')

    # level>1时应有父章节
    if level and level > 1 and not c_data.get('parent_name') and not c_data.get('parent_id'):
        errors.append(f'层级{level}的章节必须指定父章节')

    # 循环引用检查
    c_id = c_data.get('id')
    parent_id = c_data.get('parent_id')
    if c_id and parent_id and c_id == parent_id:
        errors.append('父章节不能指向自身')

    return errors


def execute_chapter_import(valid_data, conflict_strategy='skip', subjects_data=None):
    """执行章节导入

    Args:
        valid_data: 校验通过的章节数据列表
        conflict_strategy: 'skip'/'overwrite'/'append'
        subjects_data: 学科数据（JSON导入时使用）

    Returns:
        ChapterImportResult
    """
    result = ChapterImportResult()

    try:
        # 先导入学科（JSON格式时）
        if subjects_data:
            _import_subjects(subjects_data)

        # 按level升序排序，确保父章节先于子章节创建
        sorted_data = sorted(valid_data, key=lambda x: x.get('level', 1))

        # ID映射：导入前的ID → 导入后的ID（用于parent_id引用）
        id_mapping = {}

        for c_data in sorted_data:
            try:
                # 解析学科
                subject_id = c_data.get('subject_id')
                subject_name = c_data.get('subject_name', '')

                if not subject_id and subject_name:
                    subject = Subject.query.filter_by(name=subject_name).first()
                    if not subject:
                        subject = Subject(name=subject_name, is_active=True)
                        db.session.add(subject)
                        db.session.flush()
                    subject_id = subject.id

                if not subject_id:
                    result.failed += 1
                    result.failed_details.append({
                        'name': c_data.get('name', ''),
                        'error': '无法确定学科'
                    })
                    continue

                # 解析父章节
                parent_id = c_data.get('parent_id')
                parent_name = c_data.get('parent_name', '')
                level = c_data.get('level', 1)

                # 处理parent_id的ID映射
                if parent_id and parent_id in id_mapping:
                    parent_id = id_mapping[parent_id]

                if not parent_id and parent_name and subject_id:
                    # 按名称查找父章节，优先匹配level=当前level-1
                    parent = Chapter.query.filter_by(
                        subject_id=subject_id, name=parent_name
                    ).order_by(Chapter.level.desc()).first()
                    if parent:
                        parent_id = parent.id

                # 检测冲突：同名同位置
                existing = Chapter.query.filter_by(
                    subject_id=subject_id,
                    parent_id=parent_id if parent_id else None,
                    name=c_data.get('name', '')
                ).first()

                if existing and conflict_strategy == 'skip':
                    # 记录ID映射
                    c_id = c_data.get('id')
                    if c_id:
                        id_mapping[c_id] = existing.id
                    result.skipped += 1
                    continue
                elif existing and conflict_strategy == 'overwrite':
                    # 更新现有章节
                    if 'description' in c_data:
                        existing.description = c_data['description']
                    if 'order' in c_data and c_data['order']:
                        existing.order = c_data['order']
                    if 'is_active' in c_data:
                        existing.is_active = c_data['is_active']
                    # 记录ID映射
                    c_id = c_data.get('id')
                    if c_id:
                        id_mapping[c_id] = existing.id
                    result.overwritten += 1
                else:
                    # append策略或新增章节
                    order = c_data.get('order', 0)
                    if not order:
                        # 自动计算order
                        max_order_chapter = Chapter.query.filter_by(
                            subject_id=subject_id,
                            parent_id=parent_id if parent_id else None
                        ).order_by(Chapter.order.desc()).first()
                        order = (max_order_chapter.order + 1) if max_order_chapter else 1

                    chapter = Chapter(
                        subject_id=subject_id,
                        parent_id=parent_id if parent_id else None,
                        name=c_data.get('name', ''),
                        level=level,
                        order=order,
                        description=c_data.get('description', ''),
                        is_active=c_data.get('is_active', True)
                    )
                    db.session.add(chapter)
                    db.session.flush()

                    # 记录ID映射
                    c_id = c_data.get('id')
                    if c_id:
                        id_mapping[c_id] = chapter.id

                    result.success += 1

            except Exception as e:
                result.failed += 1
                result.failed_details.append({
                    'name': c_data.get('name', ''),
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
            db.session.add(subject)
            db.session.flush()
