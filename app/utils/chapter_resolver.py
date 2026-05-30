"""章节路径解析、查找创建与预览计算模块

用于Excel题目导入时，解析章节路径字符串（如"第一章 > 第一节 > 第一小节"），
逐级查找或自动创建对应的Chapter记录。
"""

import re
from app import db
from app.models import Subject, Chapter


def parse_chapter_path(chapter_name):
    """解析章节路径字符串为层级名称列表

    支持两种格式：
    - 带学科前缀："数学 > 第一章 > 第一节" -> (["第一章", "第一节"], None, "数学")
    - 不带学科前缀："第一章 > 第一节" -> (["第一章", "第一节"], None, None)

    Args:
        chapter_name: 章节路径

    Returns:
        tuple: (层级名称列表, 错误信息, 学科名称)
        - 成功: (["第一章", "第一节"], None, "数学") 或 (["第一章", "第一节"], None, None)
        - 失败: ([], "章节层级不能超过3级", None)
    """
    if not chapter_name or not chapter_name.strip():
        return ([], None, None)

    # 统一分隔符：支持 >、>>、/、| 等多种分隔符
    # 先将各种分隔符统一替换为标准 >
    normalized = chapter_name.strip()
    normalized = re.sub(r'\s*>>\s*', ' > ', normalized)  # >> 替换为 >
    normalized = re.sub(r'\s*/\s*', ' > ', normalized)    # / 替换为 >
    normalized = re.sub(r'\s*\|\s*', ' > ', normalized)   # | 替换为 >
    normalized = re.sub(r'\s*>\s*', ' > ', normalized)    # 规范化 > 前后空格

    # 按 > 分隔，每段strip去除首尾空格，过滤空字符串
    parts = [p.strip() for p in normalized.split('>')]
    parts = [p for p in parts if p]  # 过滤空段

    if not parts:
        return ([], None, None)

    # 尝试识别学科前缀：如果第一段匹配已有学科名称，则视为学科前缀
    subject_name = None
    first_part = parts[0]
    existing_subject = Subject.query.filter_by(name=first_part).first()
    if existing_subject:
        if len(parts) > 1:
            # 第一段是学科名，剩余部分是章节路径
            subject_name = first_part
            parts = parts[1:]
        else:
            # 只有学科名没有章节，相当于未指定章节
            return ([], None, first_part)

    if not parts:
        # 只有学科名没有章节，相当于未指定章节
        return ([], None, subject_name)

    if len(parts) > 3:
        return ([], "章节层级不能超过3级", None)

    return (parts, None, subject_name)


def resolve_chapter(chapter_name, subject_id, cache=None):
    """根据章节路径和学科ID，逐级查找或创建章节

    支持带学科前缀的路径（如"数学 > 第一章 > 第一节"），
    如果路径中的学科名与传入的subject_id对应的学科不一致，以路径中的学科为准并记录警告。

    Args:
        chapter_name: 章节路径字符串
        subject_id: 所属学科ID
        cache: 章节路径缓存 {"subject_id:parent_id:name": chapter_id}，避免重复查询

    Returns:
        tuple: (最末级章节ID, 警告信息列表, 新建章节数量)
        - 成功: (chapter_id, [], 2)
        - 失败: (None, ["错误信息"], 0)
    """
    if cache is None:
        cache = {}

    warnings = []
    new_count = 0

    # 解析路径
    parts, path_error, path_subject_name = parse_chapter_path(chapter_name)
    if path_error:
        return (None, [path_error], 0)
    if not parts:
        return (None, [], 0)

    # 如果路径中包含学科前缀，校验与传入的subject_id是否一致
    if path_subject_name:
        path_subject = Subject.query.filter_by(name=path_subject_name).first()
        if path_subject:
            if subject_id and path_subject.id != subject_id:
                # 章节路径中的学科与题目学科不一致，以路径中的学科为准
                existing_subject = Subject.query.get(subject_id)
                existing_name = existing_subject.name if existing_subject else str(subject_id)
                warnings.append(f'章节所属学科({path_subject_name})与题目学科({existing_name})不一致，以章节学科为准')
            subject_id = path_subject.id

    if not subject_id:
        return (None, ['指定章节时必须同时指定学科'], 0)

    parent_id = None
    chapter_id = None

    for level_index, name in enumerate(parts):
        level = level_index + 1
        cache_key = f"{subject_id}:{parent_id}:{name}"

        # 先查缓存
        if cache_key in cache:
            chapter_id = cache[cache_key]
            parent_id = chapter_id
            continue

        # 查数据库
        chapter = Chapter.query.filter_by(
            subject_id=subject_id,
            parent_id=parent_id,
            name=name
        ).first()

        if not chapter:
            # 自动创建章节
            # 计算order：同级最大order + 1
            max_order_chapter = Chapter.query.filter_by(
                subject_id=subject_id,
                parent_id=parent_id
            ).order_by(Chapter.order.desc()).first()

            new_order = 1
            if max_order_chapter and max_order_chapter.order is not None:
                new_order = max_order_chapter.order + 1

            chapter = Chapter(
                subject_id=subject_id,
                parent_id=parent_id,
                name=name,
                level=level,
                order=new_order,
                is_active=True
            )
            db.session.add(chapter)
            db.session.flush()  # 获取ID
            new_count += 1

        chapter_id = chapter.id
        cache[cache_key] = chapter_id
        parent_id = chapter_id

    return (chapter_id, warnings, new_count)


def preview_new_chapters(valid_data, subject_cache=None):
    """预览本次导入将新建的章节数量（不实际创建）

    Args:
        valid_data: 校验通过的题目数据列表
        subject_cache: 学科名称到ID的映射 {"数学": 1, "语文": 2}

    Returns:
        int: 将新建的章节数量
    """
    if subject_cache is None:
        subject_cache = {}

    # 构建学科名称到ID的映射（如果未提供）
    if not subject_cache:
        subjects = Subject.query.filter_by(is_active=True).all()
        subject_cache = {s.name: s.id for s in subjects}

    # 收集需要检查的章节路径，去重
    # key: (subject_id, chapter_path_string)
    chapter_paths = set()
    for q_data in valid_data:
        chapter_name = q_data.get('chapter_name', '')
        if not chapter_name:
            continue

        # 获取学科ID
        subject_id = q_data.get('subject_id')
        if not subject_id:
            subject_name = q_data.get('subject_name', '')
            subject_id = subject_cache.get(subject_name)
            if not subject_id:
                # 尝试从数据库查找
                subject = Subject.query.filter_by(name=subject_name).first()
                if subject:
                    subject_id = subject.id
                    subject_cache[subject_name] = subject.id

        if not subject_id:
            continue

        chapter_paths.add((subject_id, chapter_name))

    # 逐级检查数据库是否已存在，统计不存在的数量
    new_count = 0
    for subject_id, chapter_name in chapter_paths:
        parts, path_error, path_subject_name = parse_chapter_path(chapter_name)
        if path_error or not parts:
            continue

        # 如果路径中包含学科前缀，使用路径中的学科
        if path_subject_name:
            path_subject = Subject.query.filter_by(name=path_subject_name).first()
            if path_subject:
                subject_id = path_subject.id

        parent_id = None
        for name in parts:
            chapter = Chapter.query.filter_by(
                subject_id=subject_id,
                parent_id=parent_id,
                name=name
            ).first()

            if chapter:
                parent_id = chapter.id
            else:
                # 该级不存在，需要新建；后续级别也必然不存在
                remaining_count = len(parts) - parts.index(name)
                new_count += remaining_count
                break

    return new_count
