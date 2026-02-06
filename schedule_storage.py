import os
import psycopg2
from psycopg2.extras import RealDictCursor
from typing import List, Dict, Optional
from datetime import time as dt_time
from dotenv import load_dotenv

"""
Database storage manager for scheduled summaries.
Handles all database operations for schedule management.
"""

load_dotenv()


class ScheduleStorage:
    """Manages database operations for scheduled summaries"""
    
    def __init__(self):
        database_url = os.getenv('DATABASE_URL')
        
        if not database_url:
            raise ValueError("DATABASE_URL not found in environment variables")
        
        # Fix Heroku URL format if needed
        if database_url.startswith('postgres://'):
            database_url = database_url.replace('postgres://', 'postgresql://', 1)
        
        self.database_url = database_url
    
    def get_connection(self):
        """Get a database connection"""
        return psycopg2.connect(self.database_url)
    
    def get_all_active_schedules(self, guild_id: Optional[int] = None) -> List[Dict]:
        """
        Get all active schedules, optionally filtered by guild
        
        Args:
            guild_id: Optional Discord server ID to filter by
            
        Returns:
            List of schedule dictionaries
        """
        with self.get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                if guild_id:
                    cur.execute("""
                        SELECT * FROM scheduled_summaries 
                        WHERE active = TRUE AND guild_id = %s
                        ORDER BY start_time
                    """, (guild_id,))
                else:
                    cur.execute("""
                        SELECT * FROM scheduled_summaries 
                        WHERE active = TRUE
                        ORDER BY guild_id, start_time
                    """)
                return [dict(row) for row in cur.fetchall()]
    
    def add_schedule(self, guild_id: int, channel_ids: List[int], 
                     target_name: str, schedule_type: str,
                     output_channel_id: int, start_time: dt_time, 
                     interval_hours: int, lookback_duration: str, 
                     created_by_user_id: int) -> int:
        """
        Add a new schedule and return its ID
        
        Args:
            guild_id: Discord server ID
            channel_ids: List of channel IDs to summarize
            target_name: Display name (channel or category name)
            schedule_type: 'channel' or 'category'
            output_channel_id: Channel ID where summaries are posted
            start_time: Time of day to start (in server timezone)
            interval_hours: How often to repeat (in hours)
            lookback_duration: How far back to look for messages (e.g., '24h')
            created_by_user_id: Discord user ID who created the schedule
            
        Returns:
            The ID of the newly created schedule
        """
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO scheduled_summaries 
                    (guild_id, channel_ids, target_name, schedule_type, 
                     output_channel_id, start_time, interval_hours, 
                     lookback_duration, created_by_user_id)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id
                """, (guild_id, channel_ids, target_name, schedule_type, 
                      output_channel_id, start_time, interval_hours, 
                      lookback_duration, created_by_user_id))
                schedule_id = cur.fetchone()[0]
                conn.commit()
                return schedule_id
    
    def get_schedule(self, schedule_id: int) -> Optional[Dict]:
        """
        Get a specific schedule by ID
        
        Args:
            schedule_id: The schedule ID
            
        Returns:
            Schedule dictionary or None if not found
        """
        with self.get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT * FROM scheduled_summaries WHERE id = %s
                """, (schedule_id,))
                row = cur.fetchone()
                return dict(row) if row else None
    
    def delete_schedule(self, schedule_id: int):
        """
        Soft delete - mark schedule as inactive
        
        Args:
            schedule_id: The schedule ID to delete
        """
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE scheduled_summaries 
                    SET active = FALSE 
                    WHERE id = %s
                """, (schedule_id,))
                conn.commit()
    
    def update_last_run(self, schedule_id: int):
        """
        Update the last_run timestamp to now
        
        Args:
            schedule_id: The schedule ID
        """
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE scheduled_summaries 
                    SET last_run = NOW() 
                    WHERE id = %s
                """, (schedule_id,))
                conn.commit()
    
    def get_guild_timezone(self, guild_id: int) -> str:
        """
        Get the timezone for a guild
        
        Args:
            guild_id: Discord server ID
            
        Returns:
            Timezone string (defaults to 'America/New_York' if not set)
        """
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT timezone FROM guild_settings WHERE guild_id = %s
                """, (guild_id,))
                row = cur.fetchone()
                return row[0] if row else 'America/New_York'
    
    def set_guild_timezone(self, guild_id: int, timezone: str):
        """
        Set or update the timezone for a guild
        
        Args:
            guild_id: Discord server ID
            timezone: Timezone string (e.g., 'America/New_York')
        """
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO guild_settings (guild_id, timezone, updated_at)
                    VALUES (%s, %s, NOW())
                    ON CONFLICT (guild_id) 
                    DO UPDATE SET timezone = EXCLUDED.timezone, updated_at = NOW()
                """, (guild_id, timezone))
                conn.commit()
