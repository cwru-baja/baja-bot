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


class ReviewMessageStorage:
    """Manages database operations for users that need to be messaged"""
    
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
    
    def add_review_message(self, name: str, url: str, action_type: str = "review", extra_data:str = "") -> int:
        """
        Add a review message and return its ID

        Args:
            name: Name of the person to send the review message to
            url: URL of the document to review
            action_type: Action type
            extra_data: Extra data to add to the review message

        Returns:
            The ID of the newly created schedule
        """
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO review_messages
                    (username, url, action_type,
                     extra_data)
                    VALUES (%s, %s, %s, %s)
                    RETURNING id
                """, (name, url, action_type, extra_data))
                msg_id = cur.fetchone()[0]
                conn.commit()
                return msg_id
    
    def get_one_message(self) -> Optional[Dict]:
        """
        Get one unsent message

        Returns:
            Mesage dictionary or None if not found
        """
        with self.get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT * FROM review_messages
                """)
                row = cur.fetchone()
                return dict(row) if row else None
    
    def delete_review_msg(self, msg_id: int):
        """
        Hard delete
        
        Args:
            msg_id: The message ID to delete
        """
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    DELETE FROM review_messages 
                    WHERE id = %s
                """, (msg_id,))
                conn.commit()
