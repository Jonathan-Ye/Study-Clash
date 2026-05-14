#!/bin/bash
set -e

VERSION="1.0.$(date +%Y%m%d)"
IMAGE_NAME="studyclash-app"
PG_IMAGE="postgres:15-alpine"
OUTPUT_DIR="studyclash-offline-${VERSION}"
PACKAGE_NAME="${OUTPUT_DIR}.tar.gz"

echo "========================================"
echo " Study Clash 离线部署包构建工具"
echo "========================================"
echo ""
echo "版本: ${VERSION}"
echo "镜像名: ${IMAGE_NAME}"
echo "输出: ${PACKAGE_NAME}"
echo ""

echo "[1/5] 创建临时目录 ..."
mkdir -p "${OUTPUT_DIR}"

echo "[2/5] 构建应用镜像: ${IMAGE_NAME} ..."
docker build -t "${IMAGE_NAME}" .

echo "[3/5] 导出应用镜像 ..."
docker save -o "${OUTPUT_DIR}/app-image.tar" "${IMAGE_NAME}"

echo "[4/5] 导出 PostgreSQL 镜像 ..."
echo "      正在拉取 postgres:15-alpine ..."
docker pull ${PG_IMAGE}
docker save -o "${OUTPUT_DIR}/db-image.tar" ${PG_IMAGE}

echo "[5/5] 创建一键部署脚本 ..."
cat > "${OUTPUT_DIR}/deploy.sh" << 'DEPLOY_SCRIPT'
#!/bin/bash
set -e

echo "========================================="
echo " Study Clash 一键部署脚本"
echo "========================================="
echo ""

# 检查 Docker
if ! command -v docker &> /dev/null; then
    echo "错误: 未检测到 Docker，请先安装 Docker"
    exit 1
fi

if ! command -v docker compose &> /dev/null; then
    echo "错误: 未检测到 Docker Compose，请先安装"
    exit 1
fi

# 加载镜像
echo "[1/6] 加载数据库镜像 ..."
docker load -i db-image.tar

echo "[2/6] 加载应用镜像 ..."
docker load -i app-image.tar

# 创建目录（仅用于配置文件）
echo "[3/6] 创建工作目录 ..."
sudo mkdir -p /opt/studyclash

# 生成配置
echo "[4/6] 生成配置文件 ..."
cd /opt/studyclash

if [ ! -f .env ]; then
    echo "      生成随机密钥和密码..."
    SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_hex(32))" 2>/dev/null || openssl rand -hex 32)
    # 注意：密码不含 $ 符号，避免 .env 文件变量解析问题
    DB_PASSWORD=$(python3 -c 'import secrets, string; chars = string.ascii_letters + string.digits + "!#%^&*"; print("".join(secrets.choice(chars) for _ in range(20)))' 2>/dev/null || openssl rand -hex 10)
    
    cat > .env << EOF
FLASK_ENV=production
SECRET_KEY=${SECRET_KEY}
POSTGRES_USER=postgres
POSTGRES_PASSWORD=${DB_PASSWORD}
POSTGRES_DB=studyclash
SOCKETIO_CORS_ALLOWED_ORIGINS=*
LOG_DIR=logs
LOG_RETENTION_DAYS=30
EOF
    echo "      配置文件已生成: /opt/studyclash/.env"
    echo "      数据库密码: ${DB_PASSWORD}（请妥善保管）"
else
    echo "      配置文件已存在，跳过生成"
fi

# 创建 docker-compose.yml
echo "[5/6] 创建 docker-compose.yml ..."
cat > /opt/studyclash/docker-compose.yml << 'EOF'
services:
  app:
    image: studyclash-app
    container_name: studyclash-app
    restart: unless-stopped
    ports:
      - "80:5002"
    env_file:
      - .env
    environment:
      - DATABASE_URL=postgresql://${POSTGRES_USER:-postgres}:${POSTGRES_PASSWORD:-studyclash_db_password}@db:5432/${POSTGRES_DB:-studyclash}
    volumes:
      - uploads_data:/app/uploads
      - backups_data:/app/backups
      - logs_data:/app/logs
    depends_on:
      db:
        condition: service_healthy
    networks:
      - studyclash-network

  db:
    image: postgres:15-alpine
    container_name: studyclash-db
    restart: unless-stopped
    env_file:
      - .env
    volumes:
      - pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER:-postgres} -d ${POSTGRES_DB:-studyclash}"]
      interval: 10s
      timeout: 5s
      retries: 5
      start_period: 30s
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
EOF

# 启动服务
echo "[6/6] 启动服务 ..."
cd /opt/studyclash
docker compose up -d

echo ""
echo "等待数据库就绪..."
sleep 15

# 初始化数据库
echo "初始化数据库 ..."
docker compose exec app flask --app run.py init-db

echo ""
echo "========================================="
echo " 部署完成！"
echo "========================================="
echo "  访问地址: http://服务器IP"
echo "  管理员账号: admin"
echo "  默认密码: admin123"
echo "  配置文件: /opt/studyclash/.env"
echo "========================================="
DEPLOY_SCRIPT

chmod +x "${OUTPUT_DIR}/deploy.sh"

# 打包
echo ""
echo "========================================"
echo " 打包离线部署包 ..."
echo "========================================"
tar -czf "${PACKAGE_NAME}" "${OUTPUT_DIR}"

# 清理临时目录
rm -rf "${OUTPUT_DIR}"

TOTAL_SIZE=$(du -h "${PACKAGE_NAME}" | cut -f1)

echo ""
echo "========================================"
echo " 构建完成！"
echo "========================================"
echo "  部署包: ${PACKAGE_NAME}"
echo "  大小: ${TOTAL_SIZE}"
echo ""
echo "========================================"
echo " 部署到目标服务器（3步）"
echo "========================================"
echo ""
echo "  Step 1 - 传输部署包到服务器:"
echo "    scp ${PACKAGE_NAME} user@服务器IP:/opt/"
echo ""
echo "  Step 2 - SSH 到服务器并解压:"
echo "    ssh user@服务器IP"
echo "    cd /opt"
echo "    tar -xzf ${PACKAGE_NAME}"
echo "    cd ${OUTPUT_DIR}"
echo ""
echo "  Step 3 - 运行一键部署:"
echo "    sudo ./deploy.sh"
echo ""
echo "========================================"
