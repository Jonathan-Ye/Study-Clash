import multiprocessing
import os

# Worker 配置
worker_class = 'eventlet'
# 生产环境增加 Worker 数量以支持高并发
# 公式：min(cpu_count * 4 + 1, 32)
workers = min(multiprocessing.cpu_count() * 4 + 1, int(os.environ.get('GUNICORN_MAX_WORKERS', '32')))

# 绑定地址
bind = '0.0.0.0:5002'

# 超时配置
# 减少超时时间以快速释放资源
timeout = 60
graceful_timeout = 20
keepalive = 5

# 日志配置
accesslog = '-'
errorlog = '-'
loglevel = 'info'  # 改为 info 以便排查 Socket.IO 问题
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %(D)s'

# 进程管理
# 每个 Worker 处理 1000 个请求后重启，防止内存泄漏
max_requests = 1000
max_requests_jitter = 50

# Worker 临时文件目录
worker_tmp_dir = '/dev/shm'

# 并发配置
# Eventlet 每个 Worker 可处理 1000+ 并发连接
# 32 workers * 1000 connections = 32000 总并发能力
worker_connections = 1000
