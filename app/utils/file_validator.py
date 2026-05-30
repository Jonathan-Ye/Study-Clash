import re
from flask import current_app


# 文件Magic Bytes签名表
MAGIC_SIGNATURES = {
    'png': [b'\x89PNG'],
    'jpg': [b'\xff\xd8\xff'],
    'jpeg': [b'\xff\xd8\xff'],
    'gif': [b'GIF8'],
}

# SVG危险模式
SVG_DANGEROUS_PATTERNS = [
    re.compile(r'<\s*script', re.IGNORECASE),
    re.compile(r'on\w+\s*=', re.IGNORECASE),  # onclick=, onerror=, onload= etc.
    re.compile(r'<\s*iframe', re.IGNORECASE),
    re.compile(r'<\s*object', re.IGNORECASE),
    re.compile(r'<\s*embed', re.IGNORECASE),
    re.compile(r'javascript\s*:', re.IGNORECASE),
    re.compile(r'<\s*link[^>]+href', re.IGNORECASE),
]


def get_file_magic_type(file_storage):
    """读取文件头部Magic Bytes并判断实际类型

    Args:
        file_storage: Flask FileStorage对象

    Returns:
        str or None: 检测到的文件类型（png/jpg/gif），无法识别返回None
    """
    try:
        # 保存当前读取位置
        pos = file_storage.tell()
        file_storage.seek(0)
        header = file_storage.read(8)
        file_storage.seek(pos)

        if not header:
            return None

        for file_type, signatures in MAGIC_SIGNATURES.items():
            for sig in signatures:
                if header[:len(sig)] == sig:
                    return file_type

        return None
    except Exception:
        return None


def validate_image_file(file_storage, allowed_extensions):
    """验证上传的图片文件：扩展名白名单 + Magic Bytes一致性

    Args:
        file_storage: Flask FileStorage对象
        allowed_extensions: 允许的扩展名集合，如 {'png', 'jpg', 'jpeg', 'gif', 'svg'}

    Returns:
        tuple: (is_valid, error_message)
    """
    if not file_storage or not file_storage.filename:
        return False, '未选择文件'

    # 获取扩展名
    if '.' not in file_storage.filename:
        return False, '文件缺少扩展名'

    file_ext = file_storage.filename.rsplit('.', 1)[1].lower()

    # 检查扩展名白名单
    if file_ext not in allowed_extensions:
        return False, f'不支持的文件格式，仅允许 {", ".join(sorted(allowed_extensions))}'

    # SVG特殊处理
    if file_ext == 'svg':
        return validate_svg_file(file_storage)

    # 非图片文件（如xlsx/csv）不做Magic Bytes校验
    non_image_extensions = {'xlsx', 'xls', 'csv', 'json', 'zip'}
    if file_ext in non_image_extensions:
        return True, None

    # Magic Bytes校验
    detected_type = get_file_magic_type(file_storage)
    if detected_type is None:
        return False, '文件内容无法识别，请检查文件是否完整'

    # 检查Magic Bytes与扩展名是否一致
    # jpg和jpeg视为同一类型
    expected_types = {file_ext}
    if file_ext == 'jpeg':
        expected_types.add('jpg')
    elif file_ext == 'jpg':
        expected_types.add('jpeg')

    if detected_type not in expected_types:
        return False, '文件内容与声明类型不匹配，可能存在安全风险'

    return True, None


def validate_svg_file(file_storage):
    """验证SVG文件安全性：检查是否包含危险内容

    Args:
        file_storage: Flask FileStorage对象

    Returns:
        tuple: (is_valid, error_message)
    """
    try:
        pos = file_storage.tell()
        file_storage.seek(0)
        content = file_storage.read().decode('utf-8', errors='ignore')
        file_storage.seek(pos)

        for pattern in SVG_DANGEROUS_PATTERNS:
            if pattern.search(content):
                return False, 'SVG文件包含不安全内容（如script标签或事件处理器），已被拒绝'

        return True, None
    except Exception as e:
        return False, f'SVG文件验证失败: {str(e)}'
