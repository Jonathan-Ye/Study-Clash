# Study Clash Ubuntu 直接部署指南（无 Docker）

> **版本**: 1.0 | **技术栈**: Flask + Gunicorn + PostgreSQL + Redis + Socket.IO + Nginx

---

## 系统要求

| 项目 | 最低配置 | 推荐配置 |
|------|---------|---------|
| CPU | 2 核 | 4 核+ |
| 内存 | 4 GB | 8 GB+ |
| 磁盘 | 20 GB | 50 GB SSD |
| 系统 | Ubuntu 20.04+ | Ubuntu 22.04/24.04 |
| Python | 3.10+ | 3.12 |

---

## 步骤 1：安装系统依赖

```bash
# 更新系统包
sudo apt update && sudo apt upgrade -y

# 安装必需的软件包
sudo apt install -y \
    python3.12 \
    python3.12-venv \
    python3-dev \
    postgresql \
    postgresql-contrib \
    redis-server \
    nginx \
    supervisor \
    build-essential \
    libpq-dev \
    git \
    curl

# 验证安装
python3 --version
psql --version
redis-cli --version
nginx -v
```

---

## 步骤 2：配置 PostgreSQL 数据库

```bash
# 启动 PostgreSQL 服务
sudo systemctl start postgresql
sudo systemctl enable postgresql

# 切换到 postgres 用户并创建数据库
sudo -u postgres psql << 'EOF'
CREATE DATABASE studyclash;
CREATE USER studyclash_user WITH PASSWORD '这里替换为强密码';
GRANT ALL PRIVILEGES ON DATABASE studyclash TO studyclash_user;
\c studyclash
GRANT ALL ON SCHEMA public TO studyclash_user;
EOF

# 验证数据库创建
sudo -u postgres psql -l | grep studyclash
```

---

## 步骤 3：配置 Redis

```bash
# 启动 Redis 服务
sudo systemctl start redis-server
sudo systemctl enable redis-server

# 验证 Redis 运行
redis-cli ping
# 应该返回 PONG
```

---

## 步骤 4：部署应用代码

```bash
# 创建应用目录
sudo mkdir -p /var/www/studyclash
sudo chown $USER:$USER /var/www/studyclash
cd /var/www/studyclash

# 克隆项目（或复制代码到此目录）
# git clone https://github.com/your-username/study-clash.git .
# 或直接复制项目文件到 /var/www/studyclash

# 创建 Python 虚拟环境
python3 -m venv .venv
source .venv/bin/activate

# 升级 pip
pip install --upgrade pip

# 安装项目依赖
pip install -r requirements.txt
```

---

## 步骤 5：配置环境变量

```bash
# 创建 .env 文件
cat > /var/www/studyclash/.env << 'EOF'
# 运行模式
FLASK_ENV=production

# 应用密钥（必须生成随机字符串）
# 运行以下命令生成：python3 -c "import secrets; print(secrets.token_hex(32))"
SECRET_KEY=这里替换为生成的64位随机密钥

# 数据库配置
# 格式：postgresql://用户名:密码@主机:端口/数据库名
DATABASE_URL=postgresql://studyclash_user:这里替换为数据库密码@localhost:5432/studyclash

# AI 大模型加密密钥
# 运行以下命令生成：python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
LLM_ENCRYPTION_KEY=这里替换为生成的加密密钥

# WebSocket 跨域设置
SOCKETIO_CORS_ALLOWED_ORIGINS=*

# 日志配置
LOG_DIR=/var/www/studyclash/logs
LOG_RETENTION_DAYS=30
EOF

# 生成 SECRET_KEY
echo "生成 SECRET_KEY..."
python3 -c "import secrets; print('SECRET_KEY=' + secrets.token_hex(32))"

# 生成 LLM_ENCRYPTION_KEY
echo "生成 LLM_ENCRYPTION_KEY..."
python3 -c "from cryptography.fernet import Fernet; print('LLM_ENCRYPTION_KEY=' + Fernet.generate_key().decode())"

# 编辑 .env 文件，将上面生成的密钥填入
nano /var/www/studyclash/.env
```

---

## 步骤 6：初始化数据库

```bash
cd /var/www/studyclash
source .venv/bin/activate

# 执行数据库迁移
flask db upgrade

# 初始化数据和管理员账号
flask init-db

# 创建日志目录
mkdir -p logs
```

**管理员账号信息：**
- 用户名：`admin`
- 密码：`admin123`（首次登录后立即修改）

---

## 步骤 7：配置 Gunicorn + Supervisor

### 7.1 修改 Gunicorn 配置

编辑 `/var/www/studyclash/gunicorn.conf.py`：

```python
import multiprocessing
import os

# Worker 配置
worker_class = 'eventlet'
workers = min(multiprocessing.cpu_count() * 4 + 1, int(os.environ.get('GUNICORN_MAX_WORKERS', '32')))

# 绑定地址
bind = '127.0.0.1:5002'  # 改为只监听本地地址，通过 Nginx 代理

# 超时配置
timeout = 60
graceful_timeout = 20
keepalive = 5

# 日志配置
accesslog = '/var/www/studyclash/logs/gunicorn-access.log'
errorlog = '/var/www/studyclash/logs/gunicorn-error.log'
loglevel = 'info'
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %(D)s'

# 进程管理
max_requests = 1000
max_requests_jquest_jitter = 50

# 并发配置
worker_connections = 1000
```

### 7.2 配置 Supervisor 进程管理

```bash
# 创建 Supervisor 配置文件
sudo tee /etc/supervisor/conf.d/studyclash.conf << 'EOF'
[program:studyclash]
command=/var/www/studyclash/.venv/bin/gunicorn -c gunicorn.conf.py "app:create_app('production')"
directory=/var/www/studyclash
user=www-data
autostart=true
autorestart=true
stopasgroup=true
killasgroup=true
stdout_logfile=/var/www/studyclash/logs/supervisor-stdout.log
stderr_logfile=/var/www/studyclash/logs/supervisor-stderr.log
environment=PATH="/var/www/studyclash/.venv/bin",FLASK_ENV="production"
EOF

# 重新加载 Supervisor 配置
sudo supervisorctl reread
sudo supervisorctl update

# 启动应用
sudo supervisorctl start studyclash

# 查看状态
sudo supervisorctl status studyclash

# 查看日志
sudo tail -f /var/www/studyclash/logs/gunicorn-error.log
```

---

## 步骤 8：配置 Nginx 反向代理

```bash
# 创建 Nginx 配置文件
sudo tee /etc/nginx/sites-available/studyclash << 'EOF'
upstream studyclash_app {
    server 127.0.0.1:5002;
}

server {
    listen 80;
    server_name your-domain.com;  # 改为你的域名或服务器 IP

    # 日志配置
    access_log /var/log/nginx/studyclash-access.log;
    error_log /var/log/nginx/studyclash-error.log;

    # 客户端请求大小限制
    client_max_body_size 10M;

    # 静态文件（如果有）
    location /static/ {
        alias /var/www/studyclash/app/static/;
        expires 30d;
        add_header Cache-Control "public, immutable";
    }

    # WebSocket 支持（重要！）
    location /socket.io/ {
        proxy_pass http://studyclash_app;
        proxy_http_version 1.1;
        
        # WebSocket 升级头
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        
        # 代理头
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # 超时设置
        proxy_read_timeout 86400s;
        proxy_send_timeout 86400s;
        
        # 缓冲设置
        proxy_buffering off;
    }

    # 主应用代理
    location / {
        proxy_pass http://studyclash_app;
        proxy_http_version 1.1;
        
        # 代理头
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # 超时设置
        proxy_connect_timeout 60s;
        proxy_read_timeout 60s;
        proxy_send_timeout 60s;
    }
}
EOF

# 启用站点配置
sudo ln -s /etc/nginx/sites-available/studyclash /etc/nginx/sites-enabled/

# 删除默认站点（如果存在）
sudo rm -f /etc/nginx/sites-enabled/default

# 测试 Nginx 配置
sudo nginx -t

# 重启 Nginx
sudo systemctl restart nginx
sudo systemctl enable nginx
```

---

## 步骤 9：配置防火墙

```bash
# 启用 UFW 防火墙（如果未启用）
sudo ufw allow OpenSSH

# 允许 HTTP 和 HTTPS 流量
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp

# 启用防火墙
sudo ufw enable

# 查看状态
sudo ufw status
```

---

## 步骤 10：配置 HTTPS（推荐）

### 方案 A：使用 Let's Encrypt（免费）

```bash
# 安装 Certbot
sudo apt install -y certbot python3-certbot-nginx

# 获取 SSL 证书并自动配置 Nginx
sudo certbot --nginx -d your-domain.com

# 自动续期测试
sudo certbot renew --dry-run
```

### 方案 B：使用 Cloudflare SSL

如果你有 Cloudflare 账号，可以在 Cloudflare 控制面板启用 SSL/TLS。

---

## 步骤 11：验证部署

```bash
# 1. 检查所有服务状态
sudo systemctl status postgresql
sudo systemctl status redis-server
sudo supervisorctl status studyclash
sudo systemctl status nginx

# 2. 检查应用日志
sudo tail -f /var/www/studyclash/logs/gunicorn-error.log

# 3. 检查 Nginx 日志
sudo tail -f /var/log/nginx/studyclash-access.log
sudo tail -f /var/log/nginx/studyclash-error.log

# 4. 测试访问
curl http://localhost
curl http://your-domain.com

# 5. 检查数据库连接
source /var/www/studyclash/.venv/bin/activate
cd /var/www/studyclash
flask shell
>>> from app import db
>>> from app.models import User
>>> User.query.count()
```

---

## 常用运维命令

### 服务管理

```bash
# 查看应用状态
sudo supervisorctl status studyclash

# 重启应用
sudo supervisorctl restart studyclash

# 停止应用
sudo supervisorctl stop studyclash

# 查看实时日志
sudo tail -f /var/www/studyclash/logs/gunicorn-error.log
sudo tail -f /var/www/studyclash/logs/gunicorn-access.log

# 查看 Supervisor 日志
sudo tail -f /var/log/supervisor/supervisord.log
```

### 数据库操作

```bash
# 进入 PostgreSQL 命令行
sudo -u postgres psql -d studyclash

# 查看数据库大小
sudo -u postgres psql -d studyclash -c "SELECT pg_size_pretty(pg_database_size('studyclash'));"

# 查看表列表
sudo -u postgres psql -d studyclash -c "\dt"

# 查看用户数量
sudo -u postgres psql -d studyclash -c "SELECT count(*) FROM users;"
```

### 数据库迁移

```bash
cd /var/www/studyclash
source .venv/bin/activate

# 查看当前迁移版本
flask db current

# 执行迁移
flask db upgrade

# 生成新迁移（修改模型后）
flask db migrate -m "描述修改内容"
```

---

## 备份与恢复

### 备份数据库

```bash
# 创建备份目录
mkdir -p ~/studyclash_backup

# 备份数据库
sudo -u postgres pg_dump studyclash | gzip > ~/studyclash_backup/db_$(date +%Y%m%d_%H%M%S).sql.gz

# 备份上传文件（如果有）
tar -czf ~/studyclash_backup/uploads_$(date +%Y%m%d).tar.gz /var/www/studyclash/uploads/
```

### 自动备份脚本

```bash
# 创建备份脚本
cat > ~/backup_studyclash.sh << 'EOF'
#!/bin/bash
BACKUP_DIR=~/studyclash_backup
DATE=$(date +%Y%m%d_%H%M%S)
mkdir -p $BACKUP_DIR

# 备份数据库
sudo -u postgres pg_dump studyclash | gzip > $BACKUP_DIR/db_$DATE.sql.gz

# 备份上传文件
if [ -d "/var/www/studyclash/uploads" ]; then
    tar -czf $BACKUP_DIR/uploads_$DATE.tar.gz /var/www/studyclash/uploads/
fi

# 删除 7 天前的备份
find $BACKUP_DIR -name "db_*.sql.gz" -mtime +7 -delete
find $BACKUP_DIR -name "uploads_*.tar.gz" -mtime +7 -delete

echo "备份完成: $(date)"
EOF

chmod +x ~/backup_studyclash.sh

# 添加到 crontab（每天凌晨 2 点执行）
(crontab -l 2>/dev/null; echo "0 2 * * * ~/backup_studyclash.sh") | crontab -
```

### 恢复数据库

```bash
# 停止应用
sudo supervisorctl stop studyclash

# 恢复数据库
gunzip < db_20260519_120000.sql.gz | sudo -u postgres psql -d studyclash

# 启动应用
sudo supervisorctl start studyclash
```

---

## 故障排查

### 应用无法访问

```bash
# 1. 检查服务状态
sudo supervisorctl status studyclash

# 2. 查看应用日志
sudo tail -n 100 /var/www/studyclash/logs/gunicorn-error.log

# 3. 检查端口占用
sudo lsof -i :5002
sudo ss -tlnp | grep 5002

# 4. 检查 Nginx 配置
sudo nginx -t
sudo tail -n 100 /var/log/nginx/studyclash-error.log

# 5. 检查防火墙
sudo ufw status
```

### 数据库连接失败

```bash
# 1. 检查 PostgreSQL 状态
sudo systemctl status postgresql

# 2. 检查数据库连接
sudo -u postgres psql -d studyclash -c "SELECT 1;"

# 3. 验证 .env 配置
cat /var/www/studyclash/.env | grep DATABASE_URL

# 4. 测试数据库连接
source /var/www/studyclash/.venv/bin/activate
cd /var/www/studyclash
python3 -c "from app import create_app; app = create_app('production'); print('DB OK')"
```

### WebSocket 连接失败

```bash
# 1. 检查 Nginx WebSocket 配置
sudo cat /etc/nginx/sites-available/studyclash | grep -A 10 "socket.io"

# 2. 检查应用日志中的 WebSocket 连接信息
sudo grep -i "socket" /var/www/studyclash/logs/gunicorn-error.log

# 3. 测试 WebSocket 连接
# 在浏览器开发者工具中查看 Network 标签，确认 ws:// 或 wss:// 连接成功
```

### Redis 连接失败

```bash
# 1. 检查 Redis 状态
sudo systemctl status redis-server

# 2. 测试 Redis 连接
redis-cli ping

# 3. 检查 Redis 日志
sudo tail -n 100 /var/log/redis/redis-server.log
```

---

## 更新部署

```bash
# 1. 备份数据库
sudo -u postgres pg_dump studyclash | gzip > ~/backup_before_update_$(date +%Y%m%d).sql.gz

# 2. 停止应用
sudo supervisorctl stop studyclash

# 3. 更新代码
cd /var/www/studyclash
git pull  # 或复制新版本代码

# 4. 激活虚拟环境并更新依赖
source .venv/bin/activate
pip install -r requirements.txt

# 5. 执行数据库迁移
flask db upgrade

# 6. 启动应用
sudo supervisorctl start studyclash

# 7. 验证部署
curl http://localhost
sudo tail -n 50 /var/www/studyclash/logs/gunicorn-error.log
```

---

## 性能优化建议

### 1. PostgreSQL 优化

编辑 `/etc/postgresql/15/main/postgresql.conf`：

```ini
shared_buffers = 256MB
effective_cache_size = 1GB
maintenance_work_mem = 64MB
max_connections = 100
work_mem = 4MB
```

重启 PostgreSQL：
```bash
sudo systemctl restart postgresql
```

### 2. Redis 优化

编辑 `/etc/redis/redis.conf`：

```ini
maxmemory 256mb
maxmemory-policy allkeys-lru
```

重启 Redis：
```bash
sudo systemctl restart redis-server
```

### 3. Nginx 优化

在 `/etc/nginx/nginx.conf` 的 `http` 块中添加：

```nginx
worker_processes auto;
worker_connections 1024;
gzip on;
gzip_types text/plain text/css application/json application/javascript text/xml;
```

重启 Nginx：
```bash
sudo systemctl restart nginx
```

---

## 安全建议

1. **定期更新系统**：`sudo apt update && sudo apt upgrade -y`
2. **配置防火墙**：只开放必要端口（80, 443）
3. **使用 HTTPS**：所有生产环境必须启用
4. **定期备份**：至少每天一次数据库备份
5. **监控日志**：定期检查应用和系统日志
6. **修改默认密码**：首次登录后立即修改管理员密码
7. **限制 SSH 访问**：使用密钥登录，禁用密码登录

---

## 监控和告警

### 使用 Supervisor 监控

```bash
# 查看所有进程状态
sudo supervisorctl status

# 配置进程自动重启（已在配置中设置）
# autorestart=true 表示进程崩溃时自动重启
```

### 简单的健康检查脚本

```bash
# 创建健康检查脚本
cat > ~/health_check.sh << 'EOF'
#!/bin/bash
DATE=$(date '+%Y-%m-%d %H:%M:%S')

# 检查应用
if curl -s -o /dev/null -w "%{http_code}" http://localhost | grep -q "200"; then
    echo "$DATE - 应用正常"
else
    echo "$DATE - 应用异常，尝试重启..." | tee -a ~/error.log
    sudo supervisorctl restart studyclash
fi
EOF

chmod +x ~/health_check.sh

# 添加到 crontab（每 5 分钟检查一次）
(crontab -l 2>/dev/null; echo "*/5 * * * * ~/health_check.sh") | crontab -
```

---

## 完整的部署检查清单

- [ ] 系统依赖安装完成（Python, PostgreSQL, Redis, Nginx）
- [ ] PostgreSQL 数据库创建并配置权限
- [ ] Redis 服务正常运行
- [ ] 项目代码部署到 `/var/www/studyclash`
- [ ] Python 虚拟环境创建并安装依赖
- [ ] `.env` 配置文件正确设置（SECRET_KEY, DATABASE_URL, LLM_ENCRYPTION_KEY）
- [ ] 数据库迁移执行成功（`flask db upgrade`）
- [ ] 管理员账号初始化成功（`flask init-db`）
- [ ] Gunicorn 配置正确
- [ ] Supervisor 进程管理配置并启动
- [ ] Nginx 反向代理配置并启用
- [ ] WebSocket 代理配置正确
- [ ] 防火墙配置（只开放 80/443）
- [ ] HTTPS 证书配置（Let's Encrypt 或其他）
- [ ] 备份脚本配置并测试
- [ ] 日志监控配置
- [ ] 应用访问测试（HTTP 和 WebSocket）
- [ ] 数据库连接测试
- [ ] 管理员登录测试

---

**部署完成后访问：** `http://your-domain.com` 或 `http://服务器IP`

**管理员账号：** `admin` / `admin123`（首次登录后立即修改密码）
