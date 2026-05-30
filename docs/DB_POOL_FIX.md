# 数据库连接池错误修复指南

## 🔍 问题描述

### 错误信息
```
sqlalchemy.exc.TimeoutError: QueuePool limit of size 10 overflow 20 reached, 
connection timed out, timeout 30.00
```

### 错误位置
```
File "/app/app/models/user.py", line 229, in load_user
    return User.query.get(int(id))
File "/app/app/routes/game.py", line XXX, in game_single
    current_user = LocalProxy(lambda: _get_user())
```

### 问题原因
1. **连接池配置不生效** - 使用了默认的 10 个连接，而不是配置的 60 个
2. **会话未正确清理** - `db.session` 没有调用 `remove()`，导致连接泄漏
3. **连接数不足** - PostgreSQL `max_connections=200` 不足以支撑 32 个 Worker

---

## ✅ 已完成的修复

### 1. 优化连接池配置 (config.py)

**修改前：**
```python
SQLALCHEMY_ENGINE_OPTIONS = {
    'pool_size': 60,      # 太大，会导致连接总数超出
    'max_overflow': 80,
    'pool_timeout': 30,
}
```

**修改后：**
```python
SQLALCHEMY_ENGINE_OPTIONS = {
    'pool_size': 5,       # 每个 Worker 5 个核心连接
    'max_overflow': 10,   # 每个 Worker 最多 15 个连接
    'pool_pre_ping': True,
    'pool_recycle': 3600, # 1 小时回收
    'pool_timeout': 10,   # 10 秒超时
}
```

**计算：**
```
32 Workers × 15 连接 = 480 总连接
PostgreSQL max_connections = 500 ✓
```

### 2. 添加会话自动清理 (app/__init__.py)

**新增：**
```python
@app.teardown_appcontext
def shutdown_session(exception=None):
    db.session.remove()
```

**作用：**
- 每个请求结束后自动清理数据库会话
- 释放连接回连接池
- 防止连接泄漏

### 3. 提升 PostgreSQL 连接数 (docker-compose.yml)

**修改前：**
```yaml
max_connections=200
```

**修改后：**
```yaml
max_connections=500
```

### 4. 创建连接池监控工具 (app/utils/db_monitor.py)

**功能：**
- 实时监控连接池状态
- 查看 PostgreSQL 连接分布
- 清理空闲连接
- CLI 命令：`flask db-pool-status`

---

## 🚀 应用修复（服务器操作）

### 方法 1：使用优化脚本（推荐）

```bash
# 上传优化脚本到服务器
scp scripts/optimize_db_pool.sh user@server:/tmp/

# 在服务器上执行
ssh user@server
cd /tmp
chmod +x optimize_db_pool.sh
sudo ./optimize_db_pool.sh
```

### 方法 2：手动应用

```bash
# 1. 拉取最新代码
cd /path/to/studyclash
git pull

# 2. 停止服务
docker-compose down

# 3. 清理旧数据卷（可选，如果需要重置数据库）
# docker volume rm studyclash_pgdata

# 4. 重新启动
docker-compose up -d

# 5. 查看日志确认正常
docker-compose logs -f app

# 6. 检查连接池状态
docker exec studyclash-app flask db-pool-status
```

### 方法 3：仅重启应用（不停机）

```bash
# 1. 更新代码
git pull

# 2. 重新构建应用镜像
docker-compose build app

# 3. 重启应用容器
docker-compose restart app

# 4. 检查状态
docker-compose ps
docker exec studyclash-app flask db-pool-status
```

---

## 📊 验证修复

### 1. 检查连接池状态

```bash
docker exec studyclash-app flask db-pool-status
```

**正常输出：**
```
=== 数据库连接池状态 ===
连接池大小: 5
已使用连接: 3
空闲连接: 2
溢出连接: 0
总连接数: 5
==============================

=== PostgreSQL 连接状态 ===
active: 3 个连接
idle: 12 个连接
总计: 15 个连接
==============================
```

### 2. 检查 PostgreSQL 连接

```bash
docker exec studyclash-db psql -U postgres -c "
SELECT count(*) as total, state 
FROM pg_stat_activity 
WHERE datname = 'studyclash'
GROUP BY state;
"
```

### 3. 压力测试

```bash
# 使用 Locust 进行负载测试
pip install locust

# 创建测试文件
cat > locustfile.py << 'EOF'
from locust import HttpUser, task, between

class StudyClashUser(HttpUser):
    wait_time = between(1, 3)
    
    @task(3)
    def index(self):
        self.client.get("/")
    
    @task(2)
    def login(self):
        self.client.post("/auth/login", data={
            "username": "testuser",
            "password": "test123"
        })
    
    @task(1)
    def view_games(self):
        self.client.get("/game/single")
EOF

# 运行测试（500 用户）
locust -f locustfile.py --host=http://localhost --headless -u 500 -r 50 --run-time 5m
```

### 4. 监控日志

```bash
# 查看应用日志
docker-compose logs -f app | grep -i "error\|timeout"

# 查看数据库日志
docker-compose logs -f db | grep -i "connection\|too many"
```

---

## 🔧 常见问题

### Q1: 仍然出现连接池错误

**检查项：**
1. 确认代码已更新到最新版本
2. 确认 Docker 容器已重启
3. 检查 Gunicorn Worker 数量

```bash
# 查看 Worker 数量
docker exec studyclash-app ps aux | grep gunicorn | wc -l

# 如果超过 32 个，调整环境变量
echo "GUNICORN_MAX_WORKERS=32" >> .env
docker-compose restart app
```

### Q2: PostgreSQL 连接数过多

**解决方案：**
```bash
# 1. 查看当前连接分布
docker exec studyclash-db psql -U postgres -c "
SELECT client_addr, count(*) 
FROM pg_stat_activity 
WHERE datname = 'studyclash'
GROUP BY client_addr;
"

# 2. 清理空闲连接
docker exec studyclash-db psql -U postgres -d studyclash -c "
SELECT pg_terminate_backend(pid)
FROM pg_stat_activity
WHERE state = 'idle'
  AND pid != pg_backend_pid()
  AND query_start < NOW() - INTERVAL '10 minutes';
"

# 3. 重启数据库（如果必要）
docker-compose restart db
```

### Q3: 内存使用过高

**检查连接池内存：**
```bash
# 查看容器内存使用
docker stats studyclash-app studyclash-db

# 如果内存过高，调整连接池
# 在 config.py 中减小 pool_size
'pool_size': 3,           # 从 5 减小到 3
'max_overflow': 5,        # 从 10 减小到 5
```

---

## 📈 性能预期

| 配置 | Worker 数 | 连接池/Worker | 总连接数 | 支持并发 |
|------|----------|--------------|---------|---------|
| 优化前 | 32 | 10 (默认) | 320 | ❌ 连接耗尽 |
| 优化后 | 32 | 5+10 | 480 | ✅ 500+ 用户 |

---

## 🎯 关键指标

### 正常状态
- ✅ 连接池使用率 < 70%
- ✅ 平均响应时间 < 300ms
- ✅ 无 `TimeoutError` 错误
- ✅ PostgreSQL 活跃连接 < 50

### 警告状态
- ⚠️ 连接池使用率 70-90%
- ⚠️ 平均响应时间 300-500ms
- ⚠️ 偶尔出现慢查询

### 危险状态
- ❌ 连接池使用率 > 90%
- ❌ 频繁出现 `TimeoutError`
- ❌ 响应时间 > 1s
- ❌ 数据库连接 > 400

---

## 📞 技术支持

如问题仍未解决，请提供以下信息：

```bash
# 1. 连接池状态
docker exec studyclash-app flask db-pool-status

# 2. 当前连接数
docker exec studyclash-db psql -U postgres -c "
SELECT count(*) FROM pg_stat_activity WHERE datname = 'studyclash';
"

# 3. 错误日志
docker-compose logs --tail=100 app

# 4. 配置信息
docker exec studyclash-app python -c "
from app import create_app
app = create_app('production')
print('SQLALCHEMY_DATABASE_URI:', app.config['SQLALCHEMY_DATABASE_URI'])
print('ENGINE_OPTIONS:', app.config.get('SQLALCHEMY_ENGINE_OPTIONS'))
"
```

---

## ✅ 修复检查清单

- [ ] 代码已更新到最新版本
- [ ] config.py 包含新的连接池配置
- [ ] app/__init__.py 包含 `db.session.remove()`
- [ ] docker-compose.yml 中 `max_connections=500`
- [ ] 已执行 `docker-compose up -d`
- [ ] 连接池状态正常（`flask db-pool-status`）
- [ ] 无 `TimeoutError` 错误
- [ ] 压力测试通过（500 用户）
- [ ] 监控日志无异常
