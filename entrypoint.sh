#!/bin/bash

# 确保数据目录存在
mkdir -p /app/data /app/uploads /app/instance /app/flask_session /app/backups /app/logs

# 修复权限
chown -R appuser:appuser /app/data /app/uploads /app/instance /app/flask_session /app/backups /app/logs 2>/dev/null || \
chmod -R 777 /app/data /app/uploads /app/instance /app/flask_session /app/backups /app/logs

touch /app/logs/system.log 2>/dev/null || chmod 777 /app/logs
chmod 666 /app/logs/*.log 2>/dev/null || true

# 切换到 appuser 并执行命令
# 如果是 gunicorn 启动，先初始化数据库
if [[ "$*" == *"gunicorn"* ]]; then
    echo "初始化数据库..."
    gosu appuser flask shell -c "from app import db; db.create_all()" 2>/dev/null || true
fi

exec gosu appuser "$@"
