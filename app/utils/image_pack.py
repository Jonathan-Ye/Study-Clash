import os
import zipfile
import shutil
import tempfile
from io import BytesIO
from flask import current_app


# 允许的图片文件扩展名
ALLOWED_IMAGE_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'svg'}

# 单个图片文件最大大小（5MB）
MAX_IMAGE_SIZE = 5 * 1024 * 1024

# 图片资源包最大大小（50MB）
MAX_ZIP_SIZE = 50 * 1024 * 1024


def _get_image_fields():
    """返回题目中所有图片相关字段名"""
    return ['image_url', 'option_a_image', 'option_b_image', 'option_c_image',
            'option_d_image', 'option_e_image', 'option_f_image']


def _resolve_image_path(image_url, app_static_dir):
    """将图片URL解析为文件系统绝对路径

    Args:
        image_url: 图片URL（如 /static/images/questions/xxx.png）
        app_static_dir: 应用static目录的绝对路径

    Returns:
        文件绝对路径，如果无法解析则返回None
    """
    if not image_url:
        return None

    # 去除URL前缀，获取相对路径
    url = image_url
    if url.startswith('/static/'):
        relative = url[len('/static/'):]
    elif url.startswith('static/'):
        relative = url[len('static/'):]
    else:
        # 可能已经是相对路径或其他格式
        relative = url

    full_path = os.path.join(app_static_dir, relative)
    if os.path.isfile(full_path):
        return full_path
    return None


def pack_images(questions, app_static_dir):
    """导出时打包题目图片为ZIP资源包

    Args:
        questions: 题目对象列表
        app_static_dir: 应用static目录的绝对路径

    Returns:
        tuple: (zip_bytesio, missing_images, image_count)
        - zip_bytesio: BytesIO对象包含ZIP数据，若无图片则为None
        - missing_images: 缺失图片列表 [{'question_id': int, 'field': str, 'path': str}]
        - image_count: 成功打包的图片数量
    """
    image_fields = _get_image_fields()
    missing_images = []
    image_count = 0
    image_files = {}  # {zip内路径: 文件系统路径}

    for q in questions:
        for field in image_fields:
            image_url = getattr(q, field, None)
            if not image_url:
                continue

            file_path = _resolve_image_path(image_url, app_static_dir)
            if file_path:
                filename = os.path.basename(file_path)
                # ZIP路径包含题目ID，便于精确匹配：images/{题目ID}_{字段名}/{文件名}
                # 例如：images/4534_image_url/20260514_45622681.jpg
                zip_path = f"images/{q.id}_{field}/{filename}"
                image_files[zip_path] = file_path
                image_count += 1
            else:
                missing_images.append({
                    'question_id': q.id,
                    'field': field,
                    'path': image_url
                })

    if not image_files:
        return None, missing_images, 0

    zip_buffer = BytesIO()
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
        for zip_path, file_path in image_files.items():
            zf.write(file_path, zip_path)

    zip_buffer.seek(0)
    return zip_buffer, missing_images, image_count


def unpack_images(image_zip_storage, target_dir):
    """导入时解包图片资源包

    Args:
        image_zip_storage: FileStorage对象（上传的ZIP文件）
        target_dir: 目标目录（通常是app/static/images/questions/）

    Returns:
        tuple: (path_mapping, skipped_files, error_messages)
        - path_mapping: 路径映射表 {相对路径: 系统绝对URL路径}
        - skipped_files: 跳过的文件列表
        - error_messages: 错误消息列表
    """
    path_mapping = {}
    skipped_files = []
    error_messages = []

    # 校验ZIP文件大小
    image_zip_storage.seek(0, os.SEEK_END)
    file_size = image_zip_storage.tell()
    image_zip_storage.seek(0)

    if file_size > MAX_ZIP_SIZE:
        error_messages.append(f"图片资源包大小({file_size}字节)超过限制({MAX_ZIP_SIZE}字节)")
        return path_mapping, skipped_files, error_messages

    try:
        zip_buffer = BytesIO(image_zip_storage.read())
        with zipfile.ZipFile(zip_buffer, 'r') as zf:
            for info in zf.infolist():
                # 跳过目录
                if info.is_dir():
                    continue

                filename = os.path.basename(info.filename)
                if not filename:
                    continue

                # 校验文件扩展名
                ext = filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''
                if ext not in ALLOWED_IMAGE_EXTENSIONS:
                    skipped_files.append(info.filename)
                    error_messages.append(f"跳过非法文件: {info.filename} (不允许的扩展名: {ext})")
                    continue

                # 校验单个文件大小
                if info.file_size > MAX_IMAGE_SIZE:
                    skipped_files.append(info.filename)
                    error_messages.append(f"图片文件过大: {info.filename} ({info.file_size}字节)")
                    continue

                # 安全检查：防止路径遍历
                safe_path = os.path.normpath(info.filename)
                if safe_path.startswith('..') or os.path.isabs(safe_path):
                    skipped_files.append(info.filename)
                    error_messages.append(f"跳过不安全路径: {info.filename}")
                    continue

                # 提取文件名，忽略ZIP中的目录结构
                # ZIP路径格式：images/101_image_url/question.png 或 images/101/question.png
                # 我们只需要文件名：question.png
                filename = os.path.basename(safe_path)
                dest_path = os.path.join(target_dir, filename)

                # 解压文件到目标目录根目录
                with zf.open(info) as src, open(dest_path, 'wb') as dst:
                    shutil.copyfileobj(src, dst)

                # 构建路径映射：ZIP内路径 -> 系统URL路径
                # 保留完整路径信息用于精确匹配
                url_path = f"/static/questions/{filename}"
                path_mapping[safe_path] = url_path

    except zipfile.BadZipFile:
        error_messages.append("上传的文件不是有效的ZIP格式")
    except Exception as e:
        error_messages.append(f"解压图片资源包失败: {str(e)}")

    return path_mapping, skipped_files, error_messages
