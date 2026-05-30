#!/bin/bash
set -e

echo "========================================"
echo "  Study Clash 修复脚本"
echo "========================================"
echo ""

# 停止服务
echo "[1/3] 停止服务..."
docker compose down

# 清理旧镜像
echo "[2/3] 清理旧镜像..."
docker image prune -f

# 重新构建启动
echo "[3/3] 重新构建并启动..."
docker compose up -d --build

# 等待启动
echo "等待服务启动..."
sleep 10

# 检查状态
echo ""
echo "服务状态:"
docker compose ps

echo ""
echo "最近日志:"
docker compose logs --tail=20 app

echo ""
echo "========================================"
echo "  修复完成！"
echo "========================================"
echo ""
echo "查看完整日志: docker compose logs -f app"
echo "========================================"
