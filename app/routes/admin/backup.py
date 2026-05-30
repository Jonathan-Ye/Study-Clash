import os
import zipfile
from flask import render_template, request, redirect, url_for, flash, send_file
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
from app import db
from app.routes.admin import admin_bp, admin_required, sizeof_fmt

@admin_bp.route('/backup')
@login_required
@admin_required
def backup():
    from app.utils.backup import list_backups, BACKUP_VERSION
    backups = list_backups()
    
    for bk in backups:
        bk['size_formatted'] = sizeof_fmt(bk['size'])
    
    return render_template('admin/backup.html', backups=backups, current_version=BACKUP_VERSION)

@admin_bp.route('/backup/create', methods=['POST'])
@login_required
@admin_required
def create_backup_route():
    from app.utils.backup import create_backup
    try:
        backup_type = request.form.get('backup_type', 'database')
        
        if backup_type == 'full':
            filepath = create_backup(include_static=True)
            from app.utils.system_logger import SystemLogger
            SystemLogger.info(f'手动创建完整系统备份 | file={os.path.basename(filepath)}', category='backup',
                             user={'id': current_user.id, 'username': current_user.username})
            flash(f'完整系统备份创建成功！包含数据库和所有静态文件', 'success')
        else:
            filepath = create_backup()
            from app.utils.system_logger import SystemLogger
            SystemLogger.info(f'手动备份创建成功 | file={os.path.basename(filepath)}', category='backup',
                             user={'id': current_user.id, 'username': current_user.username})
            flash(f'数据库备份成功！备份文件已保存', 'success')
    except Exception as e:
        from app.utils.system_logger import SystemLogger
        SystemLogger.error(f'手动备份创建失败 | error={str(e)}', category='backup',
                          user={'id': current_user.id, 'username': current_user.username})
        flash(f'备份失败: {str(e)}', 'error')
    return redirect(url_for('admin.backup'))

@admin_bp.route('/backup/restore-progress', methods=['GET'])
@login_required
@admin_required
def restore_progress_api():
    from app.utils.backup import get_restore_progress
    return get_restore_progress()

@admin_bp.route('/backup/restore-logs', methods=['GET'])
@login_required
@admin_required
def restore_logs_api():
    from app.utils.backup import get_restore_logs
    return get_restore_logs()

@admin_bp.route('/backup/download/<filename>')
@login_required
@admin_required
def download_backup(filename):
    from app.utils.backup import get_backup_dir
    safe_filename = secure_filename(filename)
    backup_dir = get_backup_dir()
    filepath = os.path.join(backup_dir, safe_filename)
    
    # 验证路径是否在备份目录内（防止路径遍历）
    if not os.path.abspath(filepath).startswith(os.path.abspath(backup_dir)):
        flash('非法的文件路径', 'error')
        return redirect(url_for('admin.backup'))
    
    if not os.path.exists(filepath):
        flash('备份文件不存在', 'error')
        return redirect(url_for('admin.backup'))
    
    return send_file(filepath, as_attachment=True, download_name=safe_filename)

@admin_bp.route('/backup/restore/<filename>', methods=['POST'])
@login_required
@admin_required
def restore_backup_route(filename):
    import threading
    import time
    
    from app.utils.backup import restore_backup, get_backup_dir, reset_restore_progress
    from app.utils.system_logger import SystemLogger
    import logging
    logger = logging.getLogger(__name__)
    
    # 在删除数据前保存当前用户信息
    current_user_id = current_user.id
    current_username = current_user.username
    
    safe_filename = secure_filename(filename)
    backup_dir = get_backup_dir()
    filepath = os.path.join(backup_dir, safe_filename)
    
    # 验证路径
    if not os.path.abspath(filepath).startswith(os.path.abspath(backup_dir)):
        flash('非法的文件路径', 'error')
        return redirect(url_for('admin.backup'))
    
    if not os.path.exists(filepath):
        flash('备份文件不存在', 'error')
        return redirect(url_for('admin.backup'))
    
    # 重置进度
    reset_restore_progress()
    
    # 获取数据库连接信息（在启动线程前获取）
    from app import db
    db_url = db.engine.url
    db_config = {
        'dbname': db_url.database,
        'user': db_url.username,
        'password': db_url.password,
        'host': db_url.host or 'localhost',
        'port': db_url.port or 5432
    }
    
    # 获取app实例（在线程启动前获取，避免循环导入）
    from flask import current_app
    app_instance = current_app._get_current_object()
    
    # 在后台线程中执行恢复
    def run_restore(app):
        with app.app_context():
            try:
                logger.info(f'开始恢复备份: {safe_filename}')
                
                new_version, original_version, restored_count = restore_backup(filepath, db_config=db_config)
                
                logger.info(f'备份恢复成功: {restored_count} 条记录')
                
                SystemLogger.info(f'备份恢复成功 | file={safe_filename} | version={original_version}→{new_version} | records={restored_count}',
                                 category='backup', user={'id': current_user_id, 'username': current_username})
            except Exception as e:
                logger.error(f'备份恢复失败: {str(e)}')
                import traceback
                logger.error(f'备份恢复失败详细错误: {traceback.format_exc()}')
                SystemLogger.error(f'备份恢复失败 | file={safe_filename} | error={str(e)}',
                                  category='backup', user={'id': current_user_id, 'username': current_username})
    
    # 启动后台线程
    restore_thread = threading.Thread(target=run_restore, args=(app_instance,), daemon=True)
    restore_thread.start()
    
    # 立即返回，让前端轮询进度
    return '恢复已开始', 202

@admin_bp.route('/backup/delete/<filename>', methods=['POST'])
@login_required
@admin_required
def delete_backup_route(filename):
    from app.utils.backup import delete_backup, get_backup_dir
    safe_filename = secure_filename(filename)
    backup_dir = get_backup_dir()
    filepath = os.path.join(backup_dir, safe_filename)
    
    # 验证路径
    if not os.path.abspath(filepath).startswith(os.path.abspath(backup_dir)):
        flash('非法的文件路径', 'error')
        return redirect(url_for('admin.backup'))
    
    if delete_backup(safe_filename):
        flash('备份文件已删除', 'success')
    else:
        flash('删除失败', 'error')
    return redirect(url_for('admin.backup'))

@admin_bp.route('/backup/upload', methods=['POST'])
@login_required
@admin_required
def upload_backup():
    from app.utils.backup import get_backup_dir
    
    if 'backup_file' not in request.files:
        flash('没有选择文件', 'error')
        return redirect(url_for('admin.backup'))
    
    file = request.files['backup_file']
    if file.filename == '':
        flash('没有选择文件', 'error')
        return redirect(url_for('admin.backup'))
    
    if not (file.filename.endswith('.json') or file.filename.endswith('.zip')):
        flash('只允许上传 .json 或 .zip 格式的备份文件', 'error')
        return redirect(url_for('admin.backup'))
    
    try:
        safe_filename = secure_filename(file.filename)
        filepath = os.path.join(get_backup_dir(), safe_filename)
        file.save(filepath)
        flash('备份文件上传成功', 'success')
    except Exception as e:
        flash(f'上传失败: {str(e)}', 'error')
    
    return redirect(url_for('admin.backup'))

@admin_bp.route('/backup/reset-system', methods=['POST'])
@login_required
@admin_required
def reset_system():
    from app.utils.backup import reset_system_data
    
    confirm_text = request.form.get('confirm_text', '')
    if confirm_text != 'RESET_SYSTEM':
        flash('确认文本不正确，请输入 RESET_SYSTEM', 'error')
        return redirect(url_for('admin.backup'))
    
    try:
        temp_password = reset_system_data()
        from app.utils.system_logger import SystemLogger
        SystemLogger.warning('系统数据被重置', category='backup',
                            user={'id': current_user.id, 'username': current_user.username})
        flash(f'系统已重置！管理员账号: admin，请使用临时密码登录并立即修改', 'warning')
    except Exception as e:
        flash(f'重置失败: {str(e)}', 'error')
    
    return redirect(url_for('admin.backup'))
