import os
import psycopg2
from dotenv import load_dotenv

"""
Database initialization script for scheduled summaries.
Creates the necessary tables and indexes.
Safe to run multiple times (idempotent).
"""

# Load environment variables
load_dotenv()

def get_database_url():
    """Get DATABASE_URL and convert Heroku format if needed"""
    database_url = os.getenv('DATABASE_URL')
    
    if not database_url:
        raise ValueError("DATABASE_URL not found in environment variables")
    
    # Heroku Postgres URLs start with postgres://, but psycopg2 needs postgresql://
    if database_url.startswith('postgres://'):
        database_url = database_url.replace('postgres://', 'postgresql://', 1)
    
    return database_url


def init_database():
    """Initialize database tables and indexes"""
    database_url = get_database_url()
    
    print("Connecting to database...")
    conn = psycopg2.connect(database_url)
    cur = conn.cursor()
    
    try:
        print("Creating scheduled_summaries table...")
        cur.execute("""
            CREATE TABLE IF NOT EXISTS scheduled_summaries (
                id SERIAL PRIMARY KEY,
                guild_id BIGINT NOT NULL,
                channel_ids BIGINT[] NOT NULL,
                target_name VARCHAR(255),
                schedule_type VARCHAR(20) NOT NULL,
                output_channel_id BIGINT NOT NULL,
                start_time TIME NOT NULL,
                interval_hours INTEGER NOT NULL,
                lookback_duration VARCHAR(20) NOT NULL,
                days_of_week INTEGER[],
                created_at TIMESTAMP DEFAULT NOW(),
                created_by_user_id BIGINT,
                active BOOLEAN DEFAULT TRUE,
                last_run TIMESTAMP,
                
                CONSTRAINT valid_schedule_type CHECK (schedule_type IN ('channel', 'category')),
                CONSTRAINT valid_interval CHECK (interval_hours > 0)
            );
        """)
        
        print("Creating guild_settings table...")
        cur.execute("""
            CREATE TABLE IF NOT EXISTS guild_settings (
                guild_id BIGINT PRIMARY KEY,
                timezone VARCHAR(100) DEFAULT 'America/New_York',
                updated_at TIMESTAMP DEFAULT NOW()
            );
        """)
        
        print("Creating thread_subscriptions table...")
        cur.execute("""
            CREATE TABLE IF NOT EXISTS thread_subscriptions (
                id SERIAL PRIMARY KEY,
                guild_id BIGINT NOT NULL,
                user_id BIGINT NOT NULL,
                target_id BIGINT NOT NULL,
                target_type VARCHAR(20) NOT NULL,
                created_at TIMESTAMP DEFAULT NOW(),
                
                CONSTRAINT valid_target_type CHECK (target_type IN ('channel', 'category')),
                CONSTRAINT unique_subscription UNIQUE (guild_id, user_id, target_id, target_type)
            );
        """)

        print("Creating indexes...")
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_active_schedules 
            ON scheduled_summaries(guild_id, active);
        """)
        
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_schedule_lookup 
            ON scheduled_summaries(id, guild_id);
        """)
        
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_subscription_lookup 
            ON thread_subscriptions(guild_id, target_id);
        """)
        
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_user_subscriptions 
            ON thread_subscriptions(guild_id, user_id);
        """)
        
        conn.commit()
        print("✅ Database initialized successfully!")
        print("   - scheduled_summaries table created")
        print("   - guild_settings table created")
        print("   - thread_subscriptions table created")
        print("   - Indexes created")
        
    except Exception as e:
        conn.rollback()
        print(f"❌ Error initializing database: {e}")
        raise
    
    finally:
        cur.close()
        conn.close()
        print("Database connection closed.")


if __name__ == "__main__":
    init_database()
