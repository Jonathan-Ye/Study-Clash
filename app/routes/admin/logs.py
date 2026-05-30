import os
import glob
from datetime import datetime
from flask import render_template, request, send_file, flash, redirect, url_for, current_app
from flask_login import login_required
from app.routes.admin import admin_bp, admin_required


@admin_bp.route('/logs')
@login_required
@admin_required
def logs():
    """系统日志查看页面"""
    log_type = request.args.get('type', 'system')
    search = request.args.get('search', '').strip()
    date_start = request.args.get('date_start', '').strip()
    date_end = request.args.get('date_end', '').strip()
    max_lines = request.args.get('max_lines', 2000, type=int)

    if log_type not in ('system', 'access', 'error'):
        log_type = 'system'

    log_dir = current_app.config.get('LOG_DIR')
    log_text = ''
    line_count = 0
    file_list = []

    if log_dir and os.path.isdir(log_dir):
        all_files = _get_log_files_sorted(log_dir, log_type)
        file_list = [_file_info(f) for f in all_files]

        lines = []
        count = 0

        for filepath in all_files:
            if count >= max_lines:
                break
            try:
                with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
                    for line in f:
                        if count >= max_lines:
                            break
                        line = line.rstrip('\n\r')
                        if not line:
                            continue
                        if date_start or date_end:
                            line_time = _extract_timestamp(line)
                            if line_time:
                                if date_start and line_time < date_start:
                                    continue
                                if date_end and line_time > date_end:
                                    continue
                            elif date_start and date_end:
                                continue
                        if search and search not in line:
                            continue
                        lines.append(line)
                        count += 1
            except (IOError, OSError):
                continue

        log_text = '\n'.join(reversed(lines))
        line_count = count

    breadcrumb = [
        {'label': '系统管理'},
        {'label': '系统日志'}
    ]

    return render_template('admin/logs.html',
                           breadcrumb=breadcrumb,
                           log_type=log_type,
                           log_text=log_text,
                           line_count=line_count,
                           max_lines=max_lines,
                           search=search,
                           date_start=date_start,
                           date_end=date_end,
                           files=file_list)


@admin_bp.route('/logs/download')
@login_required
@admin_required
def logs_download():
    """下载日志文件"""
    filename = request.args.get('file', '')
    log_dir = current_app.config.get('LOG_DIR', '')

    if not filename or '..' in filename:
        flash('非法文件名', 'error')
        return redirect(url_for('admin.logs'))

    base_name = os.path.basename(filename)
    filepath = os.path.join(log_dir, base_name)

    if not os.path.exists(filepath):
        flash('文件不存在', 'error')
        return redirect(url_for('admin.logs'))

    if not filepath.startswith(os.path.abspath(log_dir)):
        flash('非法路径', 'error')
        return redirect(url_for('admin.logs'))

    return send_file(filepath, as_attachment=True, download_name=base_name)


@admin_bp.route('/logs/clear', methods=['POST'])
@login_required
@admin_required
def logs_clear():
    """清理过期日志"""
    from app.utils.system_logger import run_cleanup
    run_cleanup()
    flash('已清理过期日志', 'success')
    return redirect(url_for('admin.logs'))


def _get_log_files_sorted(log_dir, log_type):
    """获取按时间排序的日志文件列表（旧到新）"""
    pattern = os.path.join(log_dir, f'{log_type}.log*')
    files = glob.glob(pattern)
    files.sort(key=lambda f: os.path.getmtime(f))
    return files


def _file_info(filepath):
    """将文件路径转为包含 name/size/mtime 的字典"""
    return {
        'name': filepath,
        'size': os.path.getsize(filepath),
        'mtime': _format_time(os.path.getmtime(filepath)),
        'basename': os.path.basename(filepath)
    }


def _extract_timestamp(line):
    """从日志行提取时间字符串 YYYY-MM-DD HH:MM:SS"""
    if len(line) >= 19 and line[0:4].isdigit() and line[4] == '-':
        return line[0:19]
    return None


def _format_time(timestamp):
    """格式化时间戳"""
    return datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d %H:%M:%S')
