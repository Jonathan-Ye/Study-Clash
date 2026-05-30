# Study Clash 服务器配置方案

## 📊 自动配置方案

### 使用方法

```bash
# 在服务器上运行自动配置脚本
chmod +x scripts/auto_config.sh
./scripts/auto_config.sh

# 使用生成的配置启动
docker compose -f docker-compose.custom.yml up -d
```

---

## 🎯 不同服务器配置方案

### 方案 1：低配服务器 (2核2G)

**适用场景：** 小型测试、个人使用

**目标：** 支持 ~50 并发用户

```yaml
# 资源分配
应用容器:
  内存限制: 1.5GB
  内存预留: 512MB
  CPU 限制: 1.5 核
  Workers: 5

PostgreSQL:
  最大连接: 50
  shared_buffers: 128MB
  work_mem: 4MB

Redis:
  最大内存: 256MB
```

**环境变量：**
```env
APP_MEMORY_LIMIT=1500M
APP_MEMORY_RESERVE=512M
APP_CPU_LIMIT=1.5
GUNICORN_MAX_WORKERS=5
DB_POOL_SIZE=3
DB_POOL_OVERFLOW=5
```

---

### 方案 2：中低配服务器 (4核4G)

**适用场景：** 小型学校、班级使用

**目标：** 支持 ~200 并发用户

```yaml
# 资源分配
应用容器:
  内存限制: 2GB
  内存预留: 512MB
  CPU 限制: 2 核
  Workers: 9

PostgreSQL:
  最大连接: 100
  shared_buffers: 256MB
  work_mem: 6MB

Redis:
  最大内存: 384MB
```

**环境变量：**
```env
APP_MEMORY_LIMIT=2G
APP_MEMORY_RESERVE=512M
APP_CPU_LIMIT=2.0
GUNICORN_MAX_WORKERS=9
DB_POOL_SIZE=4
DB_POOL_OVERFLOW=8
```

---

### 方案 3：中配服务器 (8核8G) ⭐ 推荐

**适用场景：** 中型学校、年级使用

**目标：** 支持 ~500 并发用户

```yaml
# 资源分配
应用容器:
  内存限制: 4GB
  内存预留: 1GB
  CPU 限制: 4 核
  Workers: 17

PostgreSQL:
  最大连接: 200
  shared_buffers: 512MB
  work_mem: 8MB

Redis:
  最大内存: 512MB
```

**环境变量：**
```env
APP_MEMORY_LIMIT=4G
APP_MEMORY_RESERVE=1G
APP_CPU_LIMIT=4.0
GUNICORN_MAX_WORKERS=17
DB_POOL_SIZE=5
DB_POOL_OVERFLOW=10
```

---

### 方案 4：高配服务器 (16核16G)

**适用场景：** 大型学校、多校区使用

**目标：** 支持 ~1000 并发用户

```yaml
# 资源分配
应用容器:
  内存限制: 8GB
  内存预留: 2GB
  CPU 限制: 8 核
  Workers: 25

PostgreSQL:
  最大连接: 300
  shared_buffers: 1GB
  work_mem: 16MB

Redis:
  最大内存: 1GB
```

**环境变量：**
```env
APP_MEMORY_LIMIT=8G
APP_MEMORY_RESERVE=2G
APP_CPU_LIMIT=8.0
GUNICORN_MAX_WORKERS=25
DB_POOL_SIZE=6
DB_POOL_OVERFLOW=12
```

---

### 方案 5：超高配服务器 (32核32G+)

**适用场景：** 教育局、区域平台

**目标：** 支持 2000+ 并发用户

```yaml
# 资源分配
应用容器:
  内存限制: 16GB
  内存预留: 4GB
  CPU 限制: 16 核
  Workers: 32

PostgreSQL:
  最大连接: 500
  shared_buffers: 2GB
  work_mem: 32MB

Redis:
  最大内存: 2GB
```

**环境变量：**
```env
APP_MEMORY_LIMIT=16G
APP_MEMORY_RESERVE=4G
APP_CPU_LIMIT=16.0
GUNICORN_MAX_WORKERS=32
DB_POOL_SIZE=8
DB_POOL_OVERFLOW=15
```

---

## 📐 配置计算公式

### Gunicorn Workers 数量

```python
workers = min(cpu_count * 2 + 1, 32)

# 示例：
# 2 核  → min(2*2+1, 32) = 5
# 4 核  → min(4*2+1, 32) = 9
# 8 核  → min(8*2+1, 32) = 17
# 16 核 → min(16*2+1, 32) = 32 (上限)
# 32 核 → min(32*2+1, 32) = 32 (上限)
```

### 内存分配

```
总内存分配原则：
- 应用容器: 50% 内存
- PostgreSQL: 25% 内存
- Redis: 10% 内存
- 系统预留: 15% 内存

示例 (8GB 服务器):
- 应用: 4GB (50%)
- 数据库: 2GB (25%)
- Redis: 512MB (~6%)
- 系统: 1.5GB (~19%)
```

### 数据库连接池

```
每个 Worker 连接池:
- pool_size: 基础连接数 (3-8)
- max_overflow: 溢出连接数 (5-15)

总连接数计算:
总连接 = workers × (pool_size + max_overflow)

示例 (8核服务器):
- workers: 17
- pool_size: 5
- max_overflow: 10
- 总连接: 17 × 15 = 255
- PostgreSQL max_connections: 200 (需要调整)
```

---

## 🔧 手动配置

### 方法 1：使用环境变量

```bash
# 创建 .env 文件
cat > .env << EOF
APP_MEMORY_LIMIT=4G
APP_MEMORY_RESERVE=1G
APP_CPU_LIMIT=4.0
APP_CPU_RESERVE=1.0
GUNICORN_MAX_WORKERS=17
EOF

# 启动服务
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

### 方法 2：修改 docker-compose.yml

```yaml
services:
  app:
    deploy:
      resources:
        limits:
          memory: 8G      # 根据你的服务器调整
          cpus: '8.0'
        reservations:
          memory: 2G
          cpus: '2.0'
```

### 方法 3：使用自动配置脚本

```bash
# 一键生成最优配置
chmod +x scripts/auto_config.sh
./scripts/auto_config.sh

# 使用生成的配置
docker compose -f docker-compose.custom.yml up -d
```

---

## 📊 性能对比

| 配置 | Workers | 内存限制 | 并发用户 | 响应时间 |
|------|---------|---------|---------|---------|
| 2核2G | 5 | 1.5GB | ~50 | < 800ms |
| 4核4G | 9 | 2GB | ~200 | < 500ms |
| **8核8G** | **17** | **4GB** | **~500** | **< 300ms** |
| 16核16G | 25 | 8GB | ~1000 | < 200ms |
| 32核32G | 32 | 16GB | 2000+ | < 100ms |

---

## ⚠️ 注意事项

### 1. 不要超过服务器总资源

```yaml
# ❌ 错误：超过服务器总内存
limits:
  memory: 10G  # 服务器只有 8GB

# ✓ 正确：留有余量
limits:
  memory: 4G   # 使用 50% 内存
```

### 2. 数据库连接数要匹配

```yaml
# 计算总连接数
workers × (pool_size + max_overflow) < max_connections

# ❌ 错误：连接数超出
# 17 workers × 15 = 255 连接
# max_connections = 200  # 不够！

# ✓ 正确：调整连接池
# 17 workers × 10 = 170 连接
# max_connections = 200  # 足够
```

### 3. Redis 内存不要太大

```yaml
# ❌ 错误：Redis 占用太多内存
--maxmemory 2gb  # 总共只有 4GB 内存

# ✓ 正确：合理分配
--maxmemory 512mb  # 使用 10-15% 内存
```

---

## 🎯 快速选择指南

### 问题 1：你的用户规模？

- **< 100 人** → 2核2G 或 4核4G
- **100-500 人** → 8核8G ⭐ 推荐
- **500-1000 人** → 16核16G
- **> 1000 人** → 32核32G+

### 问题 2：你的预算？

- **低预算** → 4核4G (~¥200/月)
- **中预算** → 8核8G (~¥400/月) ⭐ 推荐
- **高预算** → 16核16G (~¥800/月)

### 问题 3：你的使用场景？

- **个人/测试** → 2核2G
- **班级/小组** → 4核4G
- **学校/年级** → 8核8G ⭐ 推荐
- **多校区** → 16核16G
- **区域平台** → 32核32G+

---

## 📞 技术支持

### 检查配置是否生效

```bash
# 查看应用资源限制
docker inspect studyclash-app | grep -A 10 "Memory"

# 查看实际资源使用
docker stats

# 查看 Workers 数量
docker exec studyclash-app ps aux | grep gunicorn | wc -l

# 查看连接池状态
docker exec studyclash-app flask db-pool-status
```

### 调整配置

```bash
# 1. 修改 .env 文件
nano .env

# 2. 重启服务
docker compose restart app

# 3. 或者重新构建
docker compose up -d --build
```
