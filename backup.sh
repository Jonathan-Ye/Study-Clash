#!/bin/bash
set -e

BACKUP_DIR="./backups"
mkdir -p ${BACKUP_DIR}

TIMESTAMP=$(date +%Y%m%d_%H%M%S)

echo "========================================"
echo "  Study Clash 备份脚本"
echo "========================================"
echo ""

# 备份数据库
echo "[1/2] 备份数据库..."
docker exec studyclash-db pg_dump -U postgres studyclash | gzip > ${BACKUP_DIR}/db_${TIMESTAMP}.sql.gz
echo "      数据库备份: ${BACKUP_DIR}/db_${TIMESTAMP}.sql.gz"

# 备份上传文件
echo "[2/2] 备份上传文件..."
docker cp studyclash-app:/app/uploads ${BACKUP_DIR}/uploads_${TIMESTAMP} 2>/dev/null || echo "      无上传文件"
echo "      文件备份: ${BACKUP_DIR}/uploads_${TIMESTAMP}"

# 清理 7 天前的备份
echo ""
echo "清理旧备份..."
find ${BACKUP_DIR} -name "db_*.sql.gz" -mtime +7 -delete 2>/dev/null || true
find ${BACKUP_DIR} -type d -name "uploads_*" -mtime +7 -exec rm -rf {} + 2>/dev/null || true

echo ""
echo "========================================"
echo "  备份完成！"
echo "========================================"
echo "备份位置: ${BACKUP_DIR}"
echo "========================================"
