# Study Clash 部署指南

> **版本**: 1.1.20260509 | **技术栈**: Flask + PostgreSQL + Redis + Socket.IO

---

## 目录

- [首次部署](#首次部署)
- [升级更新](#升级更新)
- [备份与恢复](#备份与恢复)
- [故障排查](#故障排查)
- [常用命令](#常用命令)

---

## 本地开发环境

### 方案 1：使用 Docker（推荐，最简单）

**无需安装 PostgreSQL，只需 Docker：**

```bash
# 启动本地 PostgreSQL 容器
docker run -d \
  --name studyclash-db-dev \
  -e POSTGRES_PASSWORD=postgres \
  -p 5432:5432 \
  postgres:15-alpine

# 等待数据库就绪（约 10 秒）
docker logs -f studyclash-db-dev
# 看到 "database system is ready to accept connections" 即可停止
```

**启动服务：**

```bash
cd "c:\Users\Joner\Desktop\Study Clash\Study Clash"

# 激活虚拟环境（Windows）
.venv\Scripts\Activate.ps1

# 初始化数据库
flask db upgrade

# 启动服务
python run.py
```

---

### 方案 2：安装本地 PostgreSQL

1. **安装 PostgreSQL 15+**
   - Windows: https://www.postgresql.org/download/windows/
   - Linux: `sudo apt install postgresql`
   - Mac: `brew install postgresql`

2. **创建数据库：**
```bash
psql -U postgres -c "CREATE DATABASE studyclash_dev;"
```

3. **启动服务：**
```bash
cd "c:\Users\Joner\Desktop\Study Clash\Study Clash"
.venv\Scripts\Activate.ps1
flask db upgrade
python run.py
```

---

访问地址：**http://127.0.0.1:5002**

**关闭本地数据库（Docker 方案）：**
```bash
docker stop studyclash-db-dev
docker rm studyclash-db-dev
```

---

## 首次部署（Linux Docker 生产环境）

### 系统要求

| 项目 | 最低 | 推荐 |
|------|------|------|
| CPU | 2 核 | 4 核+ |
| 内存 | 4 GB | 8 GB+ |
| 磁盘 | 20 GB | 50 GB SSD |
| 系统 | Ubuntu 20.04+ | Ubuntu 22.04/24.04 |

### 步骤 1：安装 Docker

```bash
curl -fsSL https://get.docker.com | sudo bash
sudo usermod -aG docker $USER
newgrp docker
docker --version
docker compose version
```

### 步骤 2：获取项目

```bash
git clone https://github.com/your-username/study-clash.git
cd study-clash
```

### 步骤 3：检查并生成配置文件

```bash
chmod +x scripts/setup-env.sh
./scripts/setup-env.sh
```

脚本会检查配置文件并自动修复：

**首次部署**（.env 不存在）：
- 生成随机 SECRET_KEY
- 生成随机数据库密码
- 生成随机 LLM_ENCRYPTION_KEY
- 设置 FLASK_ENV=production

**升级时**（.env 已存在）：
- 添加新版本需要的配置项
- 修复占位符或不安全的配置
- 保留已有配置（数据库密码、密钥等）

**数据库密码会显示在终端，请妥善保管！**

> 如需自定义配置，可手动编辑生成的 `.env` 文件

### 步骤 4：启动服务

```bash
docker compose up -d
docker compose logs -f app
# 等待看到: Listening at: http://0.0.0.0:5002
```

### 步骤 5：初始化数据库

```bash
# 执行数据库迁移
docker exec studyclash-app flask db upgrade

# 初始化数据和管理员账号
docker exec studyclash-app flask init-db
```

管理员账号：`admin`，默认密码：`admin123`（首次登录后请立即修改）

### 步骤 6：验证部署

```bash
# 检查服务状态（应看到 app、db、redis 都是 Up）
docker compose ps

# 检查数据库表
docker exec studyclash-db psql -U postgres -d studyclash -c "\dt"

# 检查 Redis
docker exec studyclash-redis redis-cli ping
# 应返回 PONG

# 访问网站
curl http://localhost
```

### 步骤 7：配置 HTTPS（推荐）

```bash
# 安装 Caddy
sudo apt install -y debian-keyring debian-archive-keyring apt-transport-https
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | sudo gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | sudo tee /etc/apt/sources.list.d/caddy-stable.list
sudo apt update && sudo apt install caddy

# 配置 Caddy（自动获取 SSL 证书）
echo "your-domain.com { reverse_proxy localhost:80 }" | sudo tee /etc/caddy/Caddyfile
sudo systemctl enable caddy && sudo systemctl start caddy
```

---

## 升级更新

### 更新版本

```bash
cd /path/to/study-clash

# 1. 拉取最新代码
git pull

# 2. 检查并修复配置文件
chmod +x scripts/setup-env.sh
./scripts/setup-env.sh

# 3. 重建并重启服务
docker compose up -d --build

# 4. 执行数据库迁移
docker exec studyclash-app flask db upgrade
```

### 全量复制升级（整个项目复制到服务器）

> 适用于将新版本整个目录覆盖到服务器的场景

```bash
# 1. 备份数据库
docker exec studyclash-db pg_dump -U postgres studyclash | gzip > backup_$(date +%Y%m%d).sql.gz

# 2. 备份上传文件
docker cp studyclash-app:/app/uploads ./uploads_backup_$(date +%Y%m%d)

# 3. 停止服务（绝对不要加 -v 参数！）
docker compose down

# 4. 复制新版本项目到服务器（保留 .env 文件）
# 将新版本项目文件夹复制到服务器
rsync -av --exclude='.env' /path/to/new-version/ /path/to/study-clash/

# 5. 检查并修复配置文件
cd /path/to/study-clash
chmod +x scripts/setup-env.sh
./scripts/setup-env.sh

# 6. 启动新版服务
docker compose up -d --build

# 7. 执行数据库迁移
docker exec studyclash-app flask db upgrade

# 8. 验证数据完整性
docker exec studyclash-db psql -U postgres -d studyclash -c "SELECT count(*) FROM users;"
docker exec studyclash-db psql -U postgres -d studyclash -c "SELECT count(*) FROM game_records;"

# 9. 查看日志确认无错误
docker compose logs --tail=50 app
```

### 版本升级说明

系统使用 Alembic 数据库版本管理，升级过程自动执行：
- 添加新字段（用户角色、游戏参与设置等）
- 创建新表（AI 分析表、等级系统等）
- 创建性能索引
- 数据迁移（旧数据自动转换为新格式）

所有用户数据、游戏记录、错题数据都会完整保留。

---

## 备份与恢复

### 备份数据

```bash
# 备份数据库
docker exec studyclash-db pg_dump -U postgres studyclash | gzip > backup_$(date +%Y%m%d_%H%M%S).sql.gz

# 备份上传文件
docker cp studyclash-app:/app/uploads ./uploads_backup_$(date +%Y%m%d)
```

### 自动备份（每天凌晨 2 点）

```bash
# 创建备份脚本
cat > ~/backup_studyclash.sh << 'EOF'
#!/bin/bash
BACKUP_DIR=~/studyclash_backup
mkdir -p $BACKUP_DIR

# 备份数据库
docker exec studyclash-db pg_dump -U postgres studyclash | gzip > $BACKUP_DIR/db_$(date +%Y%m%d_%H%M%S).sql.gz

# 备份上传文件
docker cp studyclash-app:/app/uploads $BACKUP_DIR/uploads_$(date +%Y%m%d) 2>/dev/null || true

# 删除 7 天前的备份
find $BACKUP_DIR -name "db_*.sql.gz" -mtime +7 -delete
find $BACKUP_DIR -type d -name "uploads_*" -mtime +7 -exec rm -rf {} + 2>/dev/null || true

echo "备份完成: $(date)"
EOF

chmod +x ~/backup_studyclash.sh

# 添加到 crontab（每天凌晨 2 点执行）
(crontab -l 2>/dev/null; echo "0 2 * * * ~/backup_studyclash.sh") | crontab -
```

### 恢复数据库

#### 场景 1：数据卷损坏（紧急恢复）

```bash
# 1. 停止服务
docker compose down

# 2. 删除损坏的数据卷
docker volume rm studyclash_pgdata

# 3. 重新启动（创建新数据库）
docker compose up -d

# 4. 等待数据库初始化（约 10 秒）
sleep 10

# 5. 恢复备份
gunzip < backup_20260508_120000.sql.gz | docker exec -i studyclash-db psql -U postgres studyclash

# 6. 重启应用
docker compose restart app

# 7. 执行数据库迁移
docker exec studyclash-app flask db upgrade

# 8. 验证恢复
docker exec studyclash-db psql -U postgres -d studyclash -c "SELECT count(*) FROM users;"
docker compose ps
```

#### 场景 2：误删除数据

```bash
# 方法 1：PostgreSQL 原生恢复
docker exec -i studyclash-db psql -U postgres -d studyclash << 'EOF'
DROP SCHEMA public CASCADE;
CREATE SCHEMA public;
ALTER SCHEMA public OWNER TO postgres;
EOF

gunzip < backup_20260508.sql.gz | docker exec -i studyclash-db psql -U postgres studyclash

# 方法 2：应用层恢复
docker compose exec app flask restore-db backup_20260508_120000.json

# 恢复后重启
docker compose restart app
```

#### 场景 3：迁移到新服务器

```bash
# 在新服务器上部署系统
git clone https://github.com/your-username/study-clash.git
cd study-clash

# 检查并生成配置文件
chmod +x scripts/setup-env.sh
./scripts/setup-env.sh

# 启动服务
docker compose up -d

# 传输备份文件到新服务器
scp backup_20260508.sql.gz user@新服务器IP:/tmp/

# 清空新数据库
docker exec -i studyclash-db psql -U postgres -d studyclash << 'EOF'
DROP SCHEMA public CASCADE;
CREATE SCHEMA public;
ALTER SCHEMA public OWNER TO postgres;
EOF

# 恢复备份
gunzip < /tmp/backup_20260508.sql.gz | docker exec -i studyclash-db psql -U postgres studyclash

# 恢复上传文件
scp -r uploads_backup_20260508/ user@新服务器IP:/tmp/
docker cp /tmp/uploads_backup_20260508/. studyclash-app:/app/uploads/

# 执行数据库迁移
docker exec studyclash-app flask db upgrade

# 验证恢复
docker exec studyclash-db psql -U postgres -d studyclash -c "SELECT count(*) FROM users;"
```

### 备份上传文件

```bash
# 备份
docker cp studyclash-app:/app/uploads ./uploads_backup_$(date +%Y%m%d)

# 恢复
docker cp ./uploads_backup_20260508/. studyclash-app:/app/uploads/
```

---

## 故障排查

### 服务无法访问

```bash
# 1. 检查服务状态
docker compose ps

# 2. 查看应用日志
docker compose logs --tail=50 app

# 3. 检查端口占用
sudo lsof -i :80

# 4. 检查防火墙
sudo ufw status
sudo ufw allow 80/tcp
```

### 数据库密码认证失败

**错误信息：**
```
FATAL: password authentication failed for user "postgres"
```

**原因：** PostgreSQL 只在首次启动时初始化密码。修改 `.env` 后不会重新初始化。

**解决方法：**

```bash
# 1. 查看 PostgreSQL 实际使用的密码
docker compose exec db env | grep POSTGRES_PASSWORD

# 2. 将 .env 中的密码改为上面显示的密码
nano .env

# 3. 重启应用
docker compose restart app
```

> 如果想使用新密码且不介意丢失数据：
> ```bash
> docker compose down
> docker volume rm studyclash_pgdata
> nano .env  # 修改密码
> docker compose up -d
> docker exec studyclash-app flask db upgrade
> ```

### AI 功能连接失败

```bash
# 1. 检查加密密钥
docker exec studyclash-app env | grep LLM_ENCRYPTION_KEY

# 2. 如果密钥不存在，生成新密钥
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

# 3. 添加到 .env 并重启
echo "LLM_ENCRYPTION_KEY=生成的密钥" >> .env
docker compose restart app

# 4. 在管理后台重新添加 AI 服务商
```

### 忘记管理员密码

```bash
docker compose exec -it app flask reset-admin-password
```

### WebSocket 连接失败

1. 检查 `.env` 中 `SOCKETIO_CORS_ALLOWED_ORIGINS=*`
2. 如果使用 Nginx，确保配置了 WebSocket 代理（Upgrade 和 Connection 头）

### 端口冲突（80 被占用）

编辑 `docker-compose.yml`，修改端口映射：

```yaml
ports:
  - "8080:5002"  # 改为其他端口
```

### 服务异常

```bash
# 停止并重新构建
docker compose down
docker compose up -d --build
docker exec studyclash-app flask db upgrade
```

---

## 常用命令

### 服务管理

```bash
# 启动服务
docker compose up -d

# 停止服务（保留数据）
docker compose down

# 重启服务
docker compose restart
docker compose restart app  # 只重启应用

# 查看服务状态
docker compose ps

# 查看资源使用
docker stats
```

### 日志查看

```bash
# 实时日志
docker compose logs -f app

# 最近 100 行
docker compose logs --tail=100 app

# 数据库日志
docker compose logs -f db

# 容器内日志文件
docker exec studyclash-app tail -100 /app/logs/system.log
docker exec studyclash-app tail -100 /app/logs/error.log
```

### 数据库操作

```bash
# 进入数据库容器
docker exec -it studyclash-db psql -U postgres -d studyclash

# 查看当前迁移版本
docker exec studyclash-app flask db current

# 执行数据库迁移
docker exec studyclash-app flask db upgrade

# 查看数据库连接数
docker exec studyclash-db psql -U postgres -c "SELECT count(*) FROM pg_stat_activity;"

# 查看表数量
docker exec studyclash-db psql -U postgres -d studyclash -c "\dt"
```

### 容器操作

```bash
# 进入应用容器
docker exec -it studyclash-app bash

# 查看容器环境变量
docker exec studyclash-app env

# 复制文件到容器
docker cp ./file.txt studyclash-app:/app/

# 从容器复制文件
docker cp studyclash-app:/app/uploads ./uploads_backup
```

---

## 注意事项

1. **数据安全**：永远不要执行 `docker compose down -v`（会删除所有数据）
2. **密码设置**：首次部署前设置好 `.env`，之后不要随意修改密码
3. **升级顺序**：先拉代码 → 重建镜像 → 执行数据库迁移
4. **备份策略**：生产环境必须配置定时备份
5. **环境变量**：敏感信息（密码、密钥）不要提交到 Git

---

## 离线部署

### 构建离线包（在有网络的机器上）

```bash
chmod +x build-and-export.sh
./build-and-export.sh
```

生成 `studyclash-offline-*.tar.gz` 文件。

### 部署到目标服务器

```bash
# 传输到服务器
scp studyclash-offline-*.tar.gz user@服务器IP:/opt/

# 解压并部署
ssh user@服务器IP
cd /opt
tar -xzf studyclash-offline-*.tar.gz
cd studyclash-offline-*
sudo chmod +x deploy.sh
sudo ./deploy.sh
```
