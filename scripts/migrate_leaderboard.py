from app import create_app, db
from app.models import Leaderboard, Achievement, UserAchievement, RankHistory
from sqlalchemy import inspect

def migrate_database():
    app = create_app()
    
    with app.app_context():
        inspector = inspect(db.engine)
        
        print("Starting database migration...")
        
        # Check leaderboards table
        if 'leaderboards' in inspector.get_table_names():
            columns = [col['name'] for col in inspector.get_columns('leaderboards')]
            
            # Add new columns
            new_columns = {
                'subject_id': 'INTEGER',
                'game_type': 'VARCHAR(20)',
                'school': 'VARCHAR(100)',
                'grade': 'VARCHAR(20)',
                'class_name': 'VARCHAR(50)'
            }
            
            for col_name, col_type in new_columns.items():
                if col_name not in columns:
                    print(f"Adding column: leaderboards.{col_name}")
                    try:
                        with db.engine.connect() as conn:
                            conn.execute(db.text(f'ALTER TABLE leaderboards ADD COLUMN {col_name} {col_type}'))
                            conn.commit()
                        print(f"  Success: Added column {col_name}")
                    except Exception as e:
                        print(f"  Failed to add column: {e}")
        else:
            print("leaderboards table does not exist, will be created on next startup")
        
        # Check and create new tables
        print("\nCreating new tables...")
        try:
            db.create_all()
            print("  Success: New tables created")
        except Exception as e:
            print(f"  Failed to create tables: {e}")
        
        print("\nDatabase migration complete!")

if __name__ == '__main__':
    migrate_database()
