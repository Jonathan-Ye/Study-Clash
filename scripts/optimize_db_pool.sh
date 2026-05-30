#!/bin/bash
# ============================================
# Study Clash 数据库连接池优化脚本
# 用于修复 QueuePool limit 错误
# ============================================

echo "=========================================="
echo "Study Clash 数据库连接池优化工具"
echo "=========================================="
echo ""

# 检查 Docker 是否运行
if ! command -v docker &> /dev/null; then
    echo "错误: Docker 未安装或未运行"
    exit 1
fi

# 检查容器是否运行
if ! docker ps | grep -q studyclash-db; then
    echo "错误: 数据库容器未运行"
    echo "请先运行: docker-compose up -d"
    exit 1
fi

echo "步骤 1/5: 检查当前连接池配置..."
echo ""

# 检查 PostgreSQL max_connections
MAX_CONN=$(docker exec studyclash-db psql -U postgres -t -c "SHOW max_connections;")
echo "PostgreSQL max_connections: $MAX_CONN"

# 检查当前活跃连接数
ACTIVE_CONN=$(docker exec studyclash-db psql -U postgres -t -c "SELECT count(*) FROM pg_stat_activity WHERE datname = 'studyclash';")
echo "当前活跃连接数: $ACTIVE_CONN"
echo ""

echo "步骤 2/5: 优化 PostgreSQL 配置..."
echo ""

# 如果 max_connections 小于 500，进行调整
if [ "${MAX_CONN// /}" -lt 500 ]; then
    echo "调整 max_connections 从 $MAX_CONN 到 500..."
    docker exec studyclash-db psql -U postgres -c "ALTER SYSTEM SET max_connections = '500';"
    echo "✓ PostgreSQL 配置已更新（需要重启生效）"
else
    echo "✓ max_connections 已经足够 ($MAX_CONN)"
fi
echo ""

echo "步骤 3/5: 清理空闲连接..."
echo ""

# 清理空闲超过 10 分钟的连接
docker exec studyclash-db psql -U postgres -d studyclash -c "
SELECT pg_terminate_backend(pid)
FROM pg_stat_activity
WHERE state = 'idle'
  AND pid != pg_backend_pid()
  AND query_start < NOW() - INTERVAL '10 minutes';
"

echo "✓ 空闲连接已清理"
echo ""

echo "步骤 4/5: 分析数据库表..."
echo ""

# 更新统计信息
docker exec studyclash-db psql -U postgres -d studyclash -c "ANALYZE;"

echo "✓ 表统计信息已更新"
echo ""

echo "步骤 5/5: 创建性能索引（如果不存在）..."
echo ""

# 检查是否已应用索引
docker exec -i studyclash-db psql -U postgres -d studyclash << 'EOF'
CREATE INDEX IF NOT EXISTS idx_game_records_user_created ON game_records(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_game_records_room ON game_records(room_id);
CREATE INDEX IF NOT EXISTS idx_point_records_user_created ON point_records(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_wrong_questions_user_mastered ON wrong_questions(user_id, is_mastered);
CREATE INDEX IF NOT EXISTS idx_wrong_questions_user_review ON wrong_questions(user_id, next_review_at);
CREATE INDEX IF NOT EXISTS idx_user_answers_user_created ON user_answers(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_daily_stats_user_date ON daily_stats(user_id, date DESC);
EOF

echo "✓ 性能索引已创建"
echo ""

echo "=========================================="
echo "优化完成！"
echo "=========================================="
echo ""
echo "重要提示："
echo "1. 请确保已更新代码（包含最新的 config.py 配置）"
echo "2. 重启应用容器以应用新配置:"
echo "   docker-compose restart app"
echo ""
echo "3. 如需重启数据库以应用 max_connections:"
echo "   docker-compose restart db"
echo ""
echo "4. 监控连接池状态:"
echo "   docker exec studyclash-app flask db-pool-status"
echo ""
echo "=========================================="
