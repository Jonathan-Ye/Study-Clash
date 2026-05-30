import logging
from datetime import datetime, timezone
from app import db, socketio
from app.models.ai_analysis import AIAsyncTask

logger = logging.getLogger(__name__)


class TaskManager:
    @staticmethod
    def create_task(task_type: str, user_id: int) -> AIAsyncTask:
        task = AIAsyncTask(
            task_type=task_type,
            user_id=user_id,
            status='running',
            progress=0,
            message='任务执行中',
        )
        db.session.add(task)
        db.session.commit()
        TaskManager._emit_progress(task)
        return task

    @staticmethod
    def update_task_progress(task_id: int, progress: int, message: str = None):
        task = AIAsyncTask.query.get(task_id)
        if task:
            task.progress = min(progress, 100)
            if message:
                task.message = message
            task.updated_at = datetime.now(timezone.utc)
            db.session.commit()
            TaskManager._emit_progress(task)

    @staticmethod
    def complete_task(task_id: int, result_ref_id: int = None):
        task = AIAsyncTask.query.get(task_id)
        if task:
            task.status = 'completed'
            task.progress = 100
            task.message = '任务完成'
            task.result_ref_id = result_ref_id
            task.updated_at = datetime.now(timezone.utc)
            db.session.commit()
            TaskManager._emit_progress(task)
            try:
                from app.services.ai.badge_service import AIBadgeService
                AIBadgeService.check_and_award(task.user_id, task.task_type)
            except Exception:
                pass

    @staticmethod
    def fail_task(task_id: int, error_detail: str = None):
        task = AIAsyncTask.query.get(task_id)
        if task:
            task.status = 'failed'
            task.message = '任务失败'
            task.error_detail = error_detail
            task.updated_at = datetime.now(timezone.utc)
            db.session.commit()
            TaskManager._emit_progress(task)

    @staticmethod
    def get_task(task_id: int) -> AIAsyncTask:
        return AIAsyncTask.query.get(task_id)

    @staticmethod
    def _emit_progress(task: AIAsyncTask):
        try:
            from flask_socketio import emit
            emit('ai_task_progress', {
                'task_id': task.id,
                'task_type': task.task_type,
                'status': task.status,
                'progress': task.progress,
                'message': task.message,
            }, room=f'user_{task.user_id}', namespace='/')
        except Exception as e:
            logger.error(f'推送任务进度失败: {e}')

    @staticmethod
    def recover_pending_tasks():
        pending = AIAsyncTask.query.filter(
            AIAsyncTask.status.in_(['pending', 'running'])
        ).all()
        for task in pending:
            task.status = 'failed'
            task.error_detail = '服务重启，任务中断'
            task.updated_at = datetime.now(timezone.utc)
        if pending:
            db.session.commit()
