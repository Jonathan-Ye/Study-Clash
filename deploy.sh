#!/bin/bash
set -e

echo "========================================"
echo "  Study Clash 一键部署脚本"
echo "========================================"
echo ""

# 检查 Docker
if ! command -v docker &> /dev/null; then
    echo "错误: 未检测到 Docker，请先安装"
    echo "安装命令: curl -fsSL https://get.docker.com | sudo bash"
    exit 1
fi

if ! command -v docker compose &> /dev/null; then
    echo "错误: 未检测到 Docker Compose"
    exit 1
fi

# 检查并修复配置文件
if [ ! -f .env ]; then
    echo "[1/4] 生成新配置文件..."
    chmod +x scripts/setup-env.sh
    ./scripts/setup-env.sh
else
    echo "[1/4] 检查配置文件..."
    chmod +x scripts/setup-env.sh
    ./scripts/setup-env.sh
fi

# 启动服务
echo ""
echo "[2/4] 启动服务..."
docker compose up -d

# 等待数据库就绪
echo "[3/4] 等待数据库初始化..."
sleep 15

# 初始化数据库
echo "[4/4] 初始化数据库..."
docker exec studyclash-app flask db upgrade
docker exec studyclash-app flask init-db 2>/dev/null || echo "数据库已初始化"

# 输出结果
echo ""
echo "========================================"
echo "  部署完成！"
echo "========================================"
echo ""
echo "访问地址: http://服务器IP 或 http://localhost"
echo "管理员账号: admin"
echo "管理员密码: admin123"
echo "⚠️  请立即修改默认密码！"
echo ""
echo "查看日志: docker compose logs -f app"
echo "查看状态: docker compose ps"
echo ""
echo "========================================"
