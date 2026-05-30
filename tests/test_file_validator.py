import pytest
import io
from app.utils.file_validator import validate_image_file, validate_svg_file


def _make_file_storage(content, filename):
    """创建模拟的FileStorage对象"""
    from werkzeug.datastructures import FileStorage
    if isinstance(content, str):
        stream = io.BytesIO(content.encode('utf-8'))
    else:
        stream = io.BytesIO(content)
    return FileStorage(stream=stream, filename=filename)


class TestFileValidator:
    """文件验证器测试"""

    def test_png_file_passes(self, app):
        """PNG文件通过验证"""
        with app.app_context():
            png_header = b'\x89PNG\r\n\x1a\n' + b'\x00' * 100
            fs = _make_file_storage(png_header, 'test.png')
            is_valid, error = validate_image_file(fs, {'png', 'jpg', 'jpeg', 'gif', 'svg'})
            assert is_valid is True
            assert error is None

    def test_jpeg_file_passes(self, app):
        """JPEG文件通过验证"""
        with app.app_context():
            jpeg_header = b'\xff\xd8\xff\xe0' + b'\x00' * 100
            fs = _make_file_storage(jpeg_header, 'test.jpg')
            is_valid, error = validate_image_file(fs, {'png', 'jpg', 'jpeg', 'gif', 'svg'})
            assert is_valid is True
            assert error is None

    def test_gif_file_passes(self, app):
        """GIF文件通过验证"""
        with app.app_context():
            gif_header = b'GIF89a' + b'\x00' * 100
            fs = _make_file_storage(gif_header, 'test.gif')
            is_valid, error = validate_image_file(fs, {'png', 'jpg', 'jpeg', 'gif', 'svg'})
            assert is_valid is True
            assert error is None

    def test_mismatched_extension_fails(self, app):
        """扩展名与内容不匹配时失败（PNG内容存为.jpg）"""
        with app.app_context():
            png_header = b'\x89PNG\r\n\x1a\n' + b'\x00' * 100
            fs = _make_file_storage(png_header, 'test.jpg')
            is_valid, error = validate_image_file(fs, {'png', 'jpg', 'jpeg', 'gif', 'svg'})
            assert is_valid is False
            assert '不匹配' in error

    def test_svg_with_script_tag_fails(self, app):
        """包含script标签的SVG文件被拒绝"""
        with app.app_context():
            svg_content = '<?xml version="1.0"?><svg xmlns="http://www.w3.org/2000/svg"><script>alert("xss")</script></svg>'
            fs = _make_file_storage(svg_content, 'test.svg')
            is_valid, error = validate_image_file(fs, {'png', 'jpg', 'jpeg', 'gif', 'svg'})
            assert is_valid is False
            assert '不安全' in error

    def test_clean_svg_passes(self, app):
        """干净的SVG文件通过验证"""
        with app.app_context():
            svg_content = '<?xml version="1.0"?><svg xmlns="http://www.w3.org/2000/svg"><circle cx="50" cy="50" r="40"/></svg>'
            fs = _make_file_storage(svg_content, 'test.svg')
            is_valid, error = validate_image_file(fs, {'png', 'jpg', 'jpeg', 'gif', 'svg'})
            assert is_valid is True
            assert error is None
