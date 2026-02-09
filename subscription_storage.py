import os
import psycopg2
from psycopg2.extras import RealDictCursor
from typing import List, Dict, Optional
from dotenv import load_dotenv

"""
Database storage manager for thread subscriptions.
Handles all database operations for user subscriptions to channels and categories.
"""

load_dotenv()


class SubscriptionStorage:
    """Manages database operations for thread subscriptions"""
    
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
    
    def add_subscription(self, guild_id: int, user_id: int, target_id: int, target_type: str) -> bool:
        """
        Add a new subscription
        
        Args:
            guild_id: Discord server ID
            user_id: Discord user ID
            target_id: Channel or Category ID
            target_type: 'channel' or 'category'
            
        Returns:
            True if added, False if already exists
        """
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        INSERT INTO thread_subscriptions 
                        (guild_id, user_id, target_id, target_type)
                        VALUES (%s, %s, %s, %s)
                        ON CONFLICT (guild_id, user_id, target_id, target_type) DO NOTHING
                        RETURNING id
                    """, (guild_id, user_id, target_id, target_type))
                    result = cur.fetchone()
                    conn.commit()
                    return result is not None
        except Exception as e:
            print(f"Error adding subscription: {e}")
            return False
    
    def remove_subscription(self, guild_id: int, user_id: int, target_id: int, target_type: str) -> bool:
        """
        Remove a subscription
        
        Args:
            guild_id: Discord server ID
            user_id: Discord user ID
            target_id: Channel or Category ID
            target_type: 'channel' or 'category'
            
        Returns:
            True if removed, False if not found
        """
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    DELETE FROM thread_subscriptions 
                    WHERE guild_id = %s AND user_id = %s AND target_id = %s AND target_type = %s
                    RETURNING id
                """, (guild_id, user_id, target_id, target_type))
                result = cur.fetchone()
                conn.commit()
                return result is not None
    
    def get_user_subscriptions(self, guild_id: int, user_id: int) -> List[Dict]:
        """
        Get all subscriptions for a user
        
        Args:
            guild_id: Discord server ID
            user_id: Discord user ID
            
        Returns:
            List of subscription dictionaries
        """
        with self.get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT * FROM thread_subscriptions 
                    WHERE guild_id = %s AND user_id = %s
                    ORDER BY created_at DESC
                """, (guild_id, user_id))
                return [dict(row) for row in cur.fetchall()]

    def get_subscribers(self, guild_id: int, target_id: int, target_type: str) -> List[int]:
        """
        Get all user IDs subscribed to a target
        
        Args:
            guild_id: Discord server ID
            target_id: Channel or Category ID
            target_type: 'channel' or 'category'
            
        Returns:
            List of user IDs
        """
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT user_id FROM thread_subscriptions 
                    WHERE guild_id = %s AND target_id = %s AND target_type = %s
                """, (guild_id, target_id, target_type))
                return [row[0] for row in cur.fetchall()]
