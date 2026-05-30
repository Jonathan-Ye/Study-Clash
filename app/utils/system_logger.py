import os
import logging
import logging.handlers
import glob
import time
from datetime import datetime, timedelta

_loggers_initialized = False
_log_dir = None
_log_retention_days = 30

SYSTEM_LOG = None
ACCESS_LOG = None
ERROR_LOG = None


class DailyRotatingFileHandler(logging.handlers.TimedRotatingFileHandler):
    """按天轮转的日志处理器，自动创建目录"""

    def __init__(self, log_dir, log_name, retention_days=30):
        os.makedirs(log_dir, exist_ok=True)
        filename = os.path.join(log_dir, f'{log_name}.log')
        super().__init__(
            filename=filename,
            when='midnight',
            interval=1,
            backupCount=retention_days,
            encoding='utf-8'
        )
        self.suffix = '%Y-%m-%d'
        self.extMatch = None
        self.log_dir = log_dir
        self.log_name = log_name
        self.retention_days = retention_days

    def doRollover(self):
        super().doRollover()
        self._cleanup_old_logs()

    def _cleanup_old_logs(self):
        cutoff = datetime.now() - timedelta(days=self.retention_days)
        pattern = os.path.join(self.log_dir, f'{self.log_name}.log.*')
        for log_file in glob.glob(pattern):
            try:
                mtime = os.path.getmtime(log_file)
                if datetime.fromtimestamp(mtime) < cutoff:
                    os.remove(log_file)
            except OSError:
                pass


class SystemLogger:
    """系统日志记录器"""

    @staticmethod
    def log(level, message, category='system', user=None, extra=None):
        if not _loggers_initialized:
            _ensure_initialized()

        log_entry = _format_log_entry(level, message, category, user, extra)

        if category in ('auth', 'admin', 'import', 'backup', 'config'):
            target = SYSTEM_LOG
        elif category in ('game', 'answer'):
            target = ACCESS_LOG
        elif category in ('error', 'exception'):
            target = ERROR_LOG
        else:
            target = SYSTEM_LOG

        target.log(level, log_entry)

        if category in ('error', 'exception'):
            ERROR_LOG.log(level, log_entry)

    @staticmethod
    def info(message, category='system', user=None, extra=None):
        SystemLogger.log(logging.INFO, message, category, user, extra)

    @staticmethod
    def warning(message, category='system', user=None, extra=None):
        SystemLogger.log(logging.WARNING, message, category, user, extra)

    @staticmethod
    def error(message, category='system', user=None, extra=None):
        SystemLogger.log(logging.ERROR, message, category, user, extra)

    @staticmethod
    def debug(message, category='system', user=None, extra=None):
        SystemLogger.log(logging.DEBUG, message, category, user, extra)


def _format_log_entry(level, message, category, user, extra):
    parts = [f'[{category}]']

    if user:
        if isinstance(user, dict):
            uid = user.get('id', '?')
            uname = user.get('username', '?')
            parts.append(f'[user={uname}(id={uid})]')
        else:
            parts.append(f'[user={user}]')

    if extra:
        if isinstance(extra, dict):
            extra_str = ' '.join(f'{k}={v}' for k, v in extra.items())
            parts.append(f'[{extra_str}]')
        else:
            parts.append(f'[{extra}]')

    parts.append(message)
    return ' '.join(parts)


def _ensure_initialized():
    global _loggers_initialized
    if _loggers_initialized:
        return
    init_logging()
    _loggers_initialized = True


def init_logging(app=None):
    global _loggers_initialized, SYSTEM_LOG, ACCESS_LOG, ERROR_LOG, _log_dir, _log_retention_days

    if _loggers_initialized:
        return

    if app:
        _log_dir = app.config.get('LOG_DIR', os.path.join(app.root_path, '..', 'logs'))
        _log_retention_days = int(app.config.get('LOG_RETENTION_DAYS', 30))
    else:
        _log_dir = os.environ.get('LOG_DIR', os.path.join(os.path.dirname(__file__), '..', '..', 'logs'))
        _log_retention_days = int(os.environ.get('LOG_RETENTION_DAYS', 30))

    os.makedirs(_log_dir, exist_ok=True)

    log_format = logging.Formatter(
        '%(asctime)s | %(levelname)-7s | %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    SYSTEM_LOG = _create_logger('system', _log_dir, _log_retention_days, log_format)
    ACCESS_LOG = _create_logger('access', _log_dir, _log_retention_days, log_format)
    ERROR_LOG = _create_logger('error', _log_dir, _log_retention_days, log_format)

    _loggers_initialized = True

    SystemLogger.info(f'日志系统已启动 | 目录={_log_dir} | 保留天数={_log_retention_days}', category='config')


def _create_logger(name, log_dir, retention_days, fmt):
    logger = logging.getLogger(f'studyclash.{name}')
    logger.setLevel(logging.DEBUG)
    logger.propagate = False

    if logger.handlers:
        logger.handlers.clear()

    handler = DailyRotatingFileHandler(log_dir, name, retention_days)
    handler.setLevel(logging.DEBUG)
    handler.setFormatter(fmt)
    logger.addHandler(handler)

    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.WARNING)
    console_handler.setFormatter(fmt)
    logger.addHandler(console_handler)

    return logger


def log_request(app, request, response=None):
    if not _loggers_initialized:
        return

    try:
        user_info = None
        try:
            from flask_login import current_user
            if current_user and current_user.is_authenticated:
                user_info = {'id': current_user.id, 'username': current_user.username}
        except Exception:
            pass

        status = getattr(response, 'status_code', '???') if response else '???'

        ACCESS_LOG.info(
            _format_log_entry(
                logging.INFO,
                f'{request.method} {request.path} → {status}',
                'request',
                user_info,
                {'ip': request.remote_addr or 'unknown'}
            )
        )
    except Exception:
        pass


def log_exception(app, exception, request=None):
    if not _loggers_initialized:
        return

    try:
        context = {'exception': type(exception).__name__, 'message': str(exception)[:200]}
        if request:
            context['path'] = request.path
            context['method'] = request.method
            context['ip'] = request.remote_addr or 'unknown'

        ERROR_LOG.error(
            _format_log_entry(
                logging.ERROR,
                f'未处理异常: {type(exception).__name__}: {str(exception)[:200]}',
                'exception',
                None,
                context
            ),
            exc_info=True
        )
    except Exception:
        pass


def get_log_dir():
    return _log_dir


def get_log_files():
    if not _log_dir or not os.path.isdir(_log_dir):
        return []

    files = []
    for name in ('system', 'access', 'error'):
        for f in sorted(glob.glob(os.path.join(_log_dir, f'{name}.log*'))):
            files.append({
                'name': f,
                'size': os.path.getsize(f),
                'mtime': datetime.fromtimestamp(os.path.getmtime(f)).strftime('%Y-%m-%d %H:%M:%S')
            })
    return files


def run_cleanup():
    if not _log_dir or not os.path.isdir(_log_dir):
        return

    cutoff = datetime.now() - timedelta(days=_log_retention_days)
    for name in ('system', 'access', 'error'):
        pattern = os.path.join(_log_dir, f'{name}.log.*')
        for log_file in glob.glob(pattern):
            try:
                mtime = os.path.getmtime(log_file)
                if datetime.fromtimestamp(mtime) < cutoff:
                    os.remove(log_file)
            except OSError:
                pass
