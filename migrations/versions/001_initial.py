"""initial database schema

Revision ID: 001_initial
Revises: 
Create Date: 2026-05-06 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '001_initial'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # 如果表已存在，使用 IF NOT EXISTS
    op.execute(sa.text("""
        -- Users table
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username VARCHAR(80) UNIQUE NOT NULL,
            email VARCHAR(120) UNIQUE NOT NULL,
            password_hash VARCHAR(255),
            nickname VARCHAR(80),
            avatar VARCHAR(255),
            real_name VARCHAR(80),
            student_id VARCHAR(50),
            phone VARCHAR(20),
            school VARCHAR(100),
            grade VARCHAR(50),
            major VARCHAR(100),
            class_name VARCHAR(50),
            birthday DATE,
            role VARCHAR(20) DEFAULT 'student',
            is_admin BOOLEAN DEFAULT 0,
            total_points INTEGER DEFAULT 0,
            current_tier_id INTEGER,
            peak_tier_id INTEGER,
            streak_days INTEGER DEFAULT 0,
            last_login DATETIME,
            participate_in_games BOOLEAN DEFAULT 1,
            show_in_leaderboard BOOLEAN DEFAULT 1,
            creator_id INTEGER,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (creator_id) REFERENCES users(id)
        );
        
        -- Subjects table
        CREATE TABLE IF NOT EXISTS subjects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name VARCHAR(100) NOT NULL,
            code VARCHAR(50) UNIQUE NOT NULL,
            description TEXT,
            icon VARCHAR(255),
            is_active BOOLEAN DEFAULT 1,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            created_by INTEGER,
            FOREIGN KEY (created_by) REFERENCES users(id)
        );
        
        -- Questions table
        CREATE TABLE IF NOT EXISTS questions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            subject_id INTEGER,
            chapter_id INTEGER,
            question_type VARCHAR(20) NOT NULL,
            difficulty INTEGER DEFAULT 1,
            content TEXT NOT NULL,
            image_url VARCHAR(255),
            option_a TEXT,
            option_b TEXT,
            option_c TEXT,
            option_d TEXT,
            option_e TEXT,
            option_f TEXT,
            correct_answer VARCHAR(50),
            analysis TEXT,
            points INTEGER DEFAULT 10,
            time_limit INTEGER DEFAULT 60,
            is_active BOOLEAN DEFAULT 1,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (subject_id) REFERENCES subjects(id)
        );
        
        -- Game rooms table
        CREATE TABLE IF NOT EXISTS game_rooms (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            room_code VARCHAR(10) UNIQUE NOT NULL,
            game_type VARCHAR(20) NOT NULL,
            subject_id INTEGER,
            chapter_id INTEGER,
            max_players INTEGER DEFAULT 2,
            current_players INTEGER DEFAULT 0,
            status VARCHAR(20) DEFAULT 'waiting',
            question_count INTEGER DEFAULT 10,
            time_per_question INTEGER DEFAULT 30,
            created_by INTEGER,
            started_at DATETIME,
            ended_at DATETIME,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            expires_at DATETIME,
            FOREIGN KEY (subject_id) REFERENCES subjects(id),
            FOREIGN KEY (created_by) REFERENCES users(id)
        );
        
        -- Game players table
        CREATE TABLE IF NOT EXISTS game_players (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            room_id INTEGER,
            user_id INTEGER,
            score INTEGER DEFAULT 0,
            correct_count INTEGER DEFAULT 0,
            wrong_count INTEGER DEFAULT 0,
            total_time REAL DEFAULT 0,
            wrong_chances_used INTEGER DEFAULT 0,
            current_question_index INTEGER DEFAULT 0,
            is_ready BOOLEAN DEFAULT 0,
            finished BOOLEAN DEFAULT 0,
            game_over BOOLEAN DEFAULT 0,
            joined_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            finished_at DATETIME,
            FOREIGN KEY (room_id) REFERENCES game_rooms(id),
            FOREIGN KEY (user_id) REFERENCES users(id)
        );
        
        -- Game records table
        CREATE TABLE IF NOT EXISTS game_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            room_id INTEGER,
            game_type VARCHAR(20),
            subject_id INTEGER,
            score INTEGER DEFAULT 0,
            correct_count INTEGER DEFAULT 0,
            wrong_count INTEGER DEFAULT 0,
            total_time REAL DEFAULT 0,
            rank INTEGER,
            points_earned INTEGER DEFAULT 0,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id),
            FOREIGN KEY (room_id) REFERENCES game_rooms(id),
            FOREIGN KEY (subject_id) REFERENCES subjects(id)
        );
        
        -- Point records table
        CREATE TABLE IF NOT EXISTS point_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            points INTEGER NOT NULL,
            reason VARCHAR(100),
            related_id INTEGER,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        );
        
        -- Wrong questions table
        CREATE TABLE IF NOT EXISTS wrong_questions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            question_id INTEGER,
            wrong_answer TEXT,
            wrong_count INTEGER DEFAULT 1,
            wrong_reason VARCHAR(50),
            game_type VARCHAR(20),
            is_mastered BOOLEAN DEFAULT 0,
            mastered_at DATETIME,
            consecutive_correct INTEGER DEFAULT 0,
            last_review_at DATETIME,
            review_count INTEGER DEFAULT 0,
            next_review_at DATETIME,
            wrong_answers_history TEXT,
            last_wrong_answer TEXT,
            note TEXT,
            is_important BOOLEAN DEFAULT 0,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id),
            FOREIGN KEY (question_id) REFERENCES questions(id)
        );
        
        -- System settings table
        CREATE TABLE IF NOT EXISTS system_settings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            key VARCHAR(100) UNIQUE NOT NULL,
            value TEXT,
            description TEXT,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );
        
        -- Login attempts table
        CREATE TABLE IF NOT EXISTS login_attempts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username VARCHAR(80) UNIQUE NOT NULL,
            fail_count INTEGER DEFAULT 0,
            locked_until DATETIME,
            last_fail_at DATETIME
        );
    """)


def downgrade():
    # 不执行降级，避免误删数据
    pass
