#!/bin/bash
# ============================================
# Study Clash 自动配置生成器
# 根据服务器配置自动生成最优的 .env 文件
# ============================================

echo "=========================================="
echo "Study Clash 自动配置生成器"
echo "=========================================="
echo ""

# 获取服务器配置
TOTAL_MEM_KB=$(grep MemTotal /proc/meminfo | awk '{print $2}')
TOTAL_MEM_GB=$((TOTAL_MEM_KB / 1024 / 1024))
TOTAL_CPU=$(nproc)

echo "检测到服务器配置："
echo "  CPU 核心数: $TOTAL_CPU"
echo "  内存总量: ${TOTAL_MEM_GB}GB"
echo ""

# 根据配置选择方案
if [ $TOTAL_MEM_GB -le 2 ] && [ $TOTAL_CPU -le 2 ]; then
    # 低配服务器 (2核2G)
    echo "✓ 低配服务器方案 (2核2G)"
    echo "  目标: 支持 ~50 并发用户"
    echo ""
    
    APP_MEMORY_LIMIT="1500M"
    APP_MEMORY_RESERVE="512M"
    APP_CPU_LIMIT="1.5"
    APP_CPU_RESERVE="0.5"
    GUNICORN_WORKERS=5
    DB_MAX_CONN=50
    DB_SHARED_BUFFERS="128MB"
    DB_EFFECTIVE_CACHE="256MB"
    DB_WORK_MEM="4MB"
    REDIS_MAXMEM="256mb"
    POOL_SIZE=3
    POOL_OVERFLOW=5
    
elif [ $TOTAL_MEM_GB -le 4 ] && [ $TOTAL_CPU -le 4 ]; then
    # 中低配服务器 (4核4G)
    echo "✓ 中低配服务器方案 (4核4G)"
    echo "  目标: 支持 ~200 并发用户"
    echo ""
    
    APP_MEMORY_LIMIT="2G"
    APP_MEMORY_RESERVE="512M"
    APP_CPU_LIMIT="2.0"
    APP_CPU_RESERVE="0.5"
    GUNICORN_WORKERS=9
    DB_MAX_CONN=100
    DB_SHARED_BUFFERS="256MB"
    DB_EFFECTIVE_CACHE="768MB"
    DB_WORK_MEM="6MB"
    REDIS_MAXMEM="384mb"
    POOL_SIZE=4
    POOL_OVERFLOW=8
    
elif [ $TOTAL_MEM_GB -le 8 ] && [ $TOTAL_CPU -le 8 ]; then
    # 中配服务器 (8核8G)
    echo "✓ 中配服务器方案 (8核8G)"
    echo "  目标: 支持 ~500 并发用户"
    echo ""
    
    APP_MEMORY_LIMIT="4G"
    APP_MEMORY_RESERVE="1G"
    APP_CPU_LIMIT="4.0"
    APP_CPU_RESERVE="1.0"
    GUNICORN_WORKERS=17
    DB_MAX_CONN=200
    DB_SHARED_BUFFERS="512MB"
    DB_EFFECTIVE_CACHE="1536MB"
    DB_WORK_MEM="8MB"
    REDIS_MAXMEM="512mb"
    POOL_SIZE=5
    POOL_OVERFLOW=10
    
elif [ $TOTAL_MEM_GB -le 16 ] && [ $TOTAL_CPU -le 16 ]; then
    # 高配服务器 (16核16G)
    echo "✓ 高配服务器方案 (16核16G)"
    echo "  目标: 支持 ~1000 并发用户"
    echo ""
    
    APP_MEMORY_LIMIT="8G"
    APP_MEMORY_RESERVE="2G"
    APP_CPU_LIMIT="8.0"
    APP_CPU_RESERVE="2.0"
    GUNICORN_WORKERS=25
    DB_MAX_CONN=300
    DB_SHARED_BUFFERS="1GB"
    DB_EFFECTIVE_CACHE="3GB"
    DB_WORK_MEM="16MB"
    REDIS_MAXMEM="1gb"
    POOL_SIZE=6
    POOL_OVERFLOW=12
    
elif [ $TOTAL_MEM_GB -ge 32 ] || [ $TOTAL_CPU -ge 32 ]; then
    # 超高配服务器 (32核32G+)
    echo "✓ 超高配服务器方案 (32核32G+)"
    echo "  目标: 支持 2000+ 并发用户"
    echo ""
    
    APP_MEMORY_LIMIT="16G"
    APP_MEMORY_RESERVE="4G"
    APP_CPU_LIMIT="16.0"
    APP_CPU_RESERVE="4.0"
    GUNICORN_WORKERS=32
    DB_MAX_CONN=500
    DB_SHARED_BUFFERS="2GB"
    DB_EFFECTIVE_CACHE="6GB"
    DB_WORK_MEM="32MB"
    REDIS_MAXMEM="2gb"
    POOL_SIZE=8
    POOL_OVERFLOW=15
    
else
    # 默认方案
    echo "✓ 默认方案"
    echo "  目标: 支持 ~500 并发用户"
    echo ""
    
    APP_MEMORY_LIMIT="4G"
    APP_MEMORY_RESERVE="1G"
    APP_CPU_LIMIT="4.0"
    APP_CPU_RESERVE="1.0"
    GUNICORN_WORKERS=17
    DB_MAX_CONN=200
    DB_SHARED_BUFFERS="512MB"
    DB_EFFECTIVE_CACHE="1536MB"
    DB_WORK_MEM="8MB"
    REDIS_MAXMEM="512mb"
    POOL_SIZE=5
    POOL_OVERFLOW=10
fi

echo "生成的配置："
echo "  应用内存限制: $APP_MEMORY_LIMIT"
echo "  应用内存预留: $APP_MEMORY_RESERVE"
echo "  应用CPU限制: $APP_CPU_LIMIT"
echo "  Gunicorn Workers: $GUNICORN_WORKERS"
echo "  数据库最大连接: $DB_MAX_CONN"
echo ""

# 生成 .env 文件
cat > .env << EOF
# ============================================
# Study Clash 自动生成的配置文件
# 服务器: ${TOTAL_CPU}核 ${TOTAL_MEM_GB}GB
# 生成时间: $(date)
# ============================================

FLASK_ENV=production
SECRET_KEY=${SECRET_KEY:-$(python3 -c "import secrets; print(secrets.token_hex(32))" 2>/dev/null || echo "CHANGE-THIS-KEY")}

# 数据库配置
POSTGRES_USER=postgres
POSTGRES_PASSWORD=${POSTGRES_PASSWORD:-studyclash_secure_password}
POSTGRES_DB=studyclash

# 应用资源配置
APP_MEMORY_LIMIT=$APP_MEMORY_LIMIT
APP_MEMORY_RESERVE=$APP_MEMORY_RESERVE
APP_CPU_LIMIT=$APP_CPU_LIMIT
APP_CPU_RESERVE=$APP_CPU_RESERVE
GUNICORN_MAX_WORKERS=$GUNICORN_WORKERS

# 数据库连接池配置（每个Worker）
DB_POOL_SIZE=$POOL_SIZE
DB_POOL_OVERFLOW=$POOL_OVERFLOW

# Redis 配置
REDIS_MAXMEM=$REDIS_MAXMEM
EOF

echo "✓ 配置文件已生成: .env"
echo ""

# 生成优化的 docker-compose.yml
cat > docker-compose.custom.yml << EOF
# ============================================
# Study Clash Docker Compose 自定义配置
# 服务器: ${TOTAL_CPU}核 ${TOTAL_MEM_GB}GB
# ============================================

services:
  app:
    build: 
      context: .
    image: studyclash-app:latest
    container_name: studyclash-app
    restart: unless-stopped
    ports:
      - "80:5002"
    environment:
      - FLASK_ENV=production
      - SECRET_KEY=\${SECRET_KEY}
      - DATABASE_URL=postgresql://\${POSTGRES_USER:-postgres}:\${POSTGRES_PASSWORD:-studyclash_db_password}@db:5432/\${POSTGRES_DB:-studyclash}
      - REDIS_URL=redis://redis:6379/0
      - SOCKETIO_MESSAGE_QUEUE=redis://redis:6379/1
      - SOCKETIO_CORS_ALLOWED_ORIGINS=*
      - LOG_DIR=/app/logs
      - LOG_RETENTION_DAYS=30
    volumes:
      - uploads_data:/app/uploads
      - backups_data:/app/backups
      - logs_data:/app/logs
    depends_on:
      db:
        condition: service_healthy
      redis:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:5002/')"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 40s
    networks:
      - studyclash-network
    deploy:
      resources:
        limits:
          cpus: '$APP_CPU_LIMIT'
          memory: $APP_MEMORY_LIMIT
        reservations:
          cpus: '$APP_CPU_RESERVE'
          memory: $APP_MEMORY_RESERVE

  db:
    image: postgres:15-alpine
    container_name: studyclash-db
    restart: unless-stopped
    environment:
      - POSTGRES_USER=\${POSTGRES_USER:-postgres}
      - POSTGRES_PASSWORD=\${POSTGRES_PASSWORD:-studyclash_db_password}
      - POSTGRES_DB=\${POSTGRES_DB:-studyclash}
    command: >
      postgres
      -c max_connections=$DB_MAX_CONN
      -c shared_buffers=$DB_SHARED_BUFFERS
      -c effective_cache_size=$DB_EFFECTIVE_CACHE
      -c work_mem=$DB_WORK_MEM
      -c maintenance_work_mem=128MB
      -c checkpoint_completion_target=0.9
      -c wal_buffers=16MB
      -c default_statistics_target=100
      -c random_page_cost=1.1
      -c effective_io_concurrency=200
    volumes:
      - pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U \${POSTGRES_USER:-postgres} -d \${POSTGRES_DB:-studyclash}"]
      interval: 10s
      timeout: 5s
      retries: 5
      start_period: 30s
    networks:
      - studyclash-network

  redis:
    image: redis:7-alpine
    container_name: studyclash-redis
    restart: unless-stopped
    command: >
      redis-server
      --maxmemory $REDIS_MAXMEM
      --maxmemory-policy allkeys-lru
      --save 900 1
      --save 300 10
      --save 60 10000
      --appendonly yes
      --appendfsync everysec
    volumes:
      - redis_data:/data
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 5s
      retries: 5
      start_period: 10s
    networks:
      - studyclash-network

networks:
  studyclash-network:
    driver: bridge

volumes:
  pgdata:
  uploads_data:
  backups_data:
  logs_data:
  redis_data:
EOF

echo "✓ 自定义 docker-compose 文件已生成: docker-compose.custom.yml"
echo ""

# 更新 Gunicorn 配置
cat > gunicorn.custom.conf.py << EOF
import os
import multiprocessing

# Worker 配置
worker_class = 'eventlet'
workers = $GUNICORN_WORKERS

# 绑定地址
bind = '0.0.0.0:5002'

# 超时配置
timeout = 60
graceful_timeout = 20
keepalive = 5

# 日志配置
accesslog = '-'
errorlog = '-'
loglevel = 'warning'
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %(D)s'

# 进程管理
max_requests = 1000
max_requests_jitter = 50

# Worker 临时文件目录
worker_tmp_dir = '/dev/shm'

# 并发配置
worker_connections = 1000
EOF

echo "✓ 自定义 Gunicorn 配置已生成: gunicorn.custom.conf.py"
echo ""

echo "=========================================="
echo "配置生成完成！"
echo "=========================================="
echo ""
echo "下一步操作："
echo ""
echo "1. 检查生成的配置："
echo "   cat .env"
echo ""
echo "2. 使用自定义配置启动："
echo "   docker compose -f docker-compose.custom.yml up -d"
echo ""
echo "3. 初始化数据库："
echo "   docker exec studyclash-app flask db upgrade"
echo "   docker exec studyclash-app flask create-admin --username admin --email admin@example.com --password YourPassword"
echo ""
echo "4. 应用性能索引："
echo "   docker exec -i studyclash-db psql -U postgres -d studyclash < migrations/performance_indexes.sql"
echo ""
echo "5. 查看服务状态："
echo "   docker compose ps"
echo ""
echo "=========================================="
