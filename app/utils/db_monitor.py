"""
数据库连接池监控工具
用于监控和优化数据库连接使用情况
"""
from app import db
from sqlalchemy import text
import logging

logger = logging.getLogger(__name__)


def get_pool_status():
    """获取连接池状态信息"""
    try:
        engine = db.engine
        pool = engine.pool
        
        status = {
            'pool_size': pool.size(),
            'checked_in': pool.checkedin(),
            'checked_out': pool.checkedout(),
            'overflow': pool.overflow() if hasattr(pool, 'overflow') else 0,
            'total_connections': pool.checkedin() + pool.checkedout(),
        }
        return status
    except Exception as e:
        logger.error(f"获取连接池状态失败: {e}")
        return None


def get_postgresql_connections():
    """获取 PostgreSQL 当前连接数（仅 PostgreSQL）"""
    try:
        result = db.session.execute(text("""
            SELECT 
                count(*) as total_connections,
                state,
                count(*) OVER (PARTITION BY state) as state_count
            FROM pg_stat_activity
            WHERE datname = current_database()
            GROUP BY state
        """))
        
        connections = []
        for row in result:
            connections.append({
                'state': row[1],
                'count': row[2]
            })
        
        return connections
    except Exception as e:
        logger.error(f"获取 PostgreSQL 连接状态失败: {e}")
        return []


def cleanup_idle_connections():
    """清理空闲连接（谨慎使用）"""
    try:
        result = db.session.execute(text("""
            SELECT pg_terminate_backend(pid)
            FROM pg_stat_activity
            WHERE state = 'idle'
              AND pid != pg_backend_pid()
              AND query_start < NOW() - INTERVAL '10 minutes'
        """))
        
        terminated = result.scalar()
        logger.info(f"清理了 {terminated} 个空闲连接")
        return terminated
    except Exception as e:
        logger.error(f"清理空闲连接失败: {e}")
        return 0


def log_pool_status():
    """记录连接池状态到日志"""
    status = get_pool_status()
    if status:
        logger.info(f"数据库连接池状态: {status}")
        return status
    return None


# Flask 命令：监控连接池
def init_monitor_commands(app):
    """初始化监控命令"""
    
    @app.cli.command('db-pool-status')
    def db_pool_status():
        """显示数据库连接池状态"""
        with app.app_context():
            status = get_pool_status()
            if status:
                print("\n=== 数据库连接池状态 ===")
                print(f"连接池大小: {status['pool_size']}")
                print(f"已使用连接: {status['checked_out']}")
                print(f"空闲连接: {status['checked_in']}")
                print(f"溢出连接: {status['overflow']}")
                print(f"总连接数: {status['total_connections']}")
                print("=" * 30)
            
            # 如果是 PostgreSQL，显示详细连接信息
            if app.config['SQLALCHEMY_DATABASE_URI'].startswith('postgresql'):
                connections = get_postgresql_connections()
                if connections:
                    print("\n=== PostgreSQL 连接状态 ===")
                    total = 0
                    for conn in connections:
                        print(f"{conn['state']}: {conn['count']} 个连接")
                        total += conn['count']
                    print(f"总计: {total} 个连接")
                    print("=" * 30)
    
    @app.cli.command('db-cleanup-idle')
    def db_cleanup_idle():
        """清理空闲数据库连接"""
        with app.app_context():
            print("清理空闲连接...")
            terminated = cleanup_idle_connections()
            print(f"清理了 {terminated} 个空闲连接")
