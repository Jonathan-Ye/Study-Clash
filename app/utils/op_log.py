from flask import request, current_app
from flask_login import current_user
from app import db
from app.models.admin_log import AdminLog
from datetime import datetime, timedelta, timezone


def log_operation(action_type, target_type, target_id=None, target_name=None,
                 result='success', detail=None):
    """记录管理员操作日志（非阻塞，失败不影响主业务）

    Args:
        action_type: 操作类型 - create/update/delete/export/import/config_change/batch_operation
        target_type: 操作对象类型 - user/subject/chapter/question/setting/announcement/backup/dictionary/rank_tier/leaderboard
        target_id: 操作对象ID（可选，批量操作时可为空）
        target_name: 操作对象名称/描述（可选）
        result: 操作结果 - success/failure
        detail: 操作详情/备注（可选）
    """
    try:
        if not current_user.is_authenticated:
            admin_id = None
            admin_name = 'system'
        else:
            admin_id = current_user.id
            admin_name = current_user.username

        message_parts = [f'操作:{action_type} | 对象:{target_type}']
        if target_name:
            message_parts.append(f'名称:{target_name}')
        if target_id:
            message_parts.append(f'ID:{target_id}')
        if detail:
            message_parts.append(f'详情:{detail}')
        message = ' | '.join(message_parts)

        from app.utils.system_logger import SystemLogger
        log_level = 'info' if result == 'success' else 'error'
        getattr(SystemLogger, log_level)(
            message,
            category='admin',
            user={'id': admin_id, 'username': admin_name} if admin_id else None,
            extra={'result': result}
        )

        log = AdminLog(
            admin_id=admin_id,
            admin_name=admin_name,
            action_type=action_type,
            target_type=target_type,
            target_id=target_id,
            target_name=target_name,
            result=result,
            detail=detail,
            ip_address=request.remote_addr
        )
        db.session.add(log)
        db.session.commit()
    except Exception as e:
        current_app.logger.error(f"操作日志记录失败: {str(e)}")
        try:
            db.session.rollback()
        except Exception:
            pass


def cleanup_old_logs(days=180):
    """清理超过指定天数的操作日志

    Args:
        days: 保留天数，默认180天

    Returns:
        删除的日志数量
    """
    try:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        deleted = AdminLog.query.filter(AdminLog.created_at < cutoff).delete()
        db.session.commit()
        return deleted
    except Exception as e:
        current_app.logger.error(f"操作日志清理失败: {str(e)}")
        try:
            db.session.rollback()
        except Exception:
            pass
        return 0
