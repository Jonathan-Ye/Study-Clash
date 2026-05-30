-- ============================================
-- Study Clash 数据库索引优化脚本
-- 用于提升 500+ 并发用户场景下的查询性能
-- ============================================

-- 1. 游戏记录表索引
CREATE INDEX IF NOT EXISTS idx_game_records_user_created 
ON game_records(user_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_game_records_room 
ON game_records(room_id);

CREATE INDEX IF NOT EXISTS idx_game_records_score 
ON game_records(score DESC);

-- 2. 每日统计索引
CREATE INDEX IF NOT EXISTS idx_daily_stats_user_date 
ON daily_stats(user_id, date DESC);

CREATE INDEX IF NOT EXISTS idx_daily_stats_date 
ON daily_stats(date DESC);

-- 3. 积分记录索引
CREATE INDEX IF NOT EXISTS idx_point_records_user_created 
ON point_records(user_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_point_records_reason 
ON point_records(reason);

-- 4. 错题本索引
CREATE INDEX IF NOT EXISTS idx_wrong_questions_user_mastered 
ON wrong_questions(user_id, is_mastered);

CREATE INDEX IF NOT EXISTS idx_wrong_questions_user_review 
ON wrong_questions(user_id, next_review_at);

CREATE INDEX IF NOT EXISTS idx_wrong_questions_question 
ON wrong_questions(question_id);

-- 5. 用户答案索引
CREATE INDEX IF NOT EXISTS idx_user_answers_user_created 
ON user_answers(user_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_user_answers_question 
ON user_answers(question_id);

CREATE INDEX IF NOT EXISTS idx_user_answers_correct 
ON user_answers(user_id, is_correct);

-- 6. 游戏房间索引
CREATE INDEX IF NOT EXISTS idx_game_rooms_status_created 
ON game_rooms(status, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_game_rooms_host 
ON game_rooms(created_by);

-- 7. 游戏玩家索引
CREATE INDEX IF NOT EXISTS idx_game_players_room_user 
ON game_players(room_id, user_id);

-- 8. 登录尝试索引
CREATE INDEX IF NOT EXISTS idx_login_attempts_locked 
ON login_attempts(locked_until);

-- 9. 段位历史索引
CREATE INDEX IF NOT EXISTS idx_tier_promotion_user 
ON tier_promotion_history(user_id, changed_at DESC);

-- 10. 排名历史索引
CREATE INDEX IF NOT EXISTS idx_rank_history_user 
ON rank_history(user_id, recorded_at DESC);

-- 11. 排行榜索引（如果使用物化视图）
CREATE INDEX IF NOT EXISTS idx_leaderboards_score 
ON leaderboards(score DESC, period, category);

CREATE INDEX IF NOT EXISTS idx_leaderboards_user 
ON leaderboards(user_id, period);

-- 12. 题目索引
CREATE INDEX IF NOT EXISTS idx_questions_subject_difficulty 
ON questions(subject_id, difficulty, is_active);

CREATE INDEX IF NOT EXISTS idx_questions_chapter 
ON questions(chapter_id, is_active);

-- 13. 章节索引
CREATE INDEX IF NOT EXISTS idx_chapters_subject_level 
ON chapters(subject_id, level, parent_id);

-- 14. 系统公告索引
CREATE INDEX IF NOT EXISTS idx_announcements_active 
ON announcements(is_active, publish_time DESC);

-- 15. 管理员日志索引
CREATE INDEX IF NOT EXISTS idx_admin_logs_time 
ON admin_logs(created_at DESC);

CREATE INDEX IF NOT EXISTS idx_admin_logs_user 
ON admin_logs(user_id, created_at DESC);

-- ============================================
-- 分析统计信息（提升查询规划器准确性）
-- ============================================
ANALYZE;

-- ============================================
-- 验证索引创建情况
-- ============================================
SELECT 
    schemaname,
    tablename,
    indexname,
    indexdef
FROM pg_indexes
WHERE schemaname = 'public'
ORDER BY tablename, indexname;
