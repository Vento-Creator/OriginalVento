"""
Database Adapter Layer - Clean interface for modular systems to interact with database
Provides thread-safe, error-handled database operations for login_system, massdm_system, utag_system
"""
import asyncio
import logging
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime

logger = logging.getLogger(__name__)


class DatabaseAdapterError(Exception):
    """Base database adapter error"""
    pass


class ConnectionError(DatabaseAdapterError):
    """Database connection error"""
    pass


class QueryError(DatabaseAdapterError):
    """Database query error"""
    pass


class MassDMDatabaseAdapter:
    """Database adapter for MassDM system"""
    
    @staticmethod
    async def save_progress(user_id: int, stats: Dict[str, Any]) -> bool:
        """Save MassDM progress to database"""
        try:
            from database import save_massdm_progress
            # Extract group_id and last_index from stats
            # If stats contains total/success/failed, calculate last_index
            total = stats.get("total", 0)
            success = stats.get("success", 0)
            failed = stats.get("failed", 0)
            last_index = success + failed  # Current progress position
            
            # Try to get group_id from stats, otherwise use a default
            group_id = stats.get("group_id", "unknown")
            
            await save_massdm_progress(user_id, group_id, last_index)
            return True
        except Exception as e:
            logger.error(f"Error saving MassDM progress: {e}")
            return False
    
    @staticmethod
    async def get_progress(user_id: int, group_id: str) -> int:
        """Get MassDM progress from database"""
        try:
            from database import get_massdm_progress
            return await get_massdm_progress(user_id, group_id)
        except Exception as e:
            logger.error(f"Error getting MassDM progress: {e}")
            return 0
    
    @staticmethod
    async def reset_progress(user_id: int, group_id: str) -> bool:
        """Reset MassDM progress in database"""
        try:
            from database import reset_massdm_progress
            await reset_massdm_progress(user_id, group_id)
            return True
        except Exception as e:
            logger.error(f"Error resetting MassDM progress: {e}")
            return False
    
    @staticmethod
    async def save_setting(user_id: int, auto_stop_on_high_risk: bool) -> bool:
        """Save MassDM user setting to database"""
        try:
            from database import save_massdm_setting
            await save_massdm_setting(user_id, auto_stop_on_high_risk)
            return True
        except Exception as e:
            logger.error(f"Error saving MassDM setting: {e}")
            return False
    
    @staticmethod
    async def get_setting(user_id: int) -> Dict[str, Any]:
        """Get MassDM user settings from database"""
        try:
            from database import get_massdm_setting
            auto_stop = await get_massdm_setting(user_id)
            return {
                "auto_stop_on_high_risk": auto_stop,
                "resume_after": 0
            }
        except Exception as e:
            logger.error(f"Error getting MassDM setting: {e}")
            return {
                "auto_stop_on_high_risk": True,
                "resume_after": 0
            }
    
    @staticmethod
    async def save_auto_stopped_task(
        stop_key: str, 
        user_id: int, 
        stats: Dict[str, Any], 
        reason: str
    ) -> bool:
        """Save auto-stopped task to database"""
        try:
            from database import save_auto_stopped_task
            # Extract data from stats with fallbacks
            group_id = stats.get("group_id", "unknown")
            resume_after = stats.get("resume_after", 0)
            message_to_copy_id = stats.get("message_to_copy_id", 0)
            delay_hours = stats.get("delay_hours", 0)
            
            await save_auto_stopped_task(
                stop_key, user_id, group_id, resume_after, 
                reason, message_to_copy_id, delay_hours
            )
            return True
        except Exception as e:
            logger.error(f"Error saving auto-stopped task: {e}")
            return False
    
    @staticmethod
    async def get_auto_stopped_task(stop_key: str) -> Optional[Dict[str, Any]]:
        """Get auto-stopped task from database"""
        try:
            from database import get_auto_stopped_task
            task = await get_auto_stopped_task(stop_key)
            if task:
                return {
                    "stop_key": task[0],
                    "user_id": task[1],
                    "group_id": task[2],
                    "resume_after": task[3],
                    "reason": task[4],
                    "message_to_copy_id": task[5],
                    "delay_hours": task[6],
                    "created_at": task[7]
                }
            return None
        except Exception as e:
            logger.error(f"Error getting auto-stopped task: {e}")
            return None
    
    @staticmethod
    async def delete_auto_stopped_task(stop_key: str) -> bool:
        """Delete auto-stopped task from database"""
        try:
            from database import delete_auto_stopped_task
            await delete_auto_stopped_task(stop_key)
            return True
        except Exception as e:
            logger.error(f"Error deleting auto-stopped task: {e}")
            return False
    
    @staticmethod
    async def get_user_auto_stopped_tasks(user_id: int) -> List[Dict[str, Any]]:
        """Get all auto-stopped tasks for user"""
        try:
            from database import get_all_auto_stopped_tasks_for_user
            tasks = await get_all_auto_stopped_tasks_for_user(user_id)
            return [
                {
                    "stop_key": t[0],
                    "user_id": t[1],
                    "group_id": t[2],
                    "resume_after": t[3],
                    "reason": t[4],
                    "message_to_copy_id": t[5],
                    "delay_hours": t[6],
                    "created_at": t[7]
                }
                for t in tasks
            ]
        except Exception as e:
            logger.error(f"Error getting user auto-stopped tasks: {e}")
            return []


class LoginDatabaseAdapter:
    """Database adapter for Login system"""
    
    @staticmethod
    async def save_user_session(user_id: int, phone: str, session_data: Dict[str, Any]) -> bool:
        """Save user login session to database"""
        try:
            from database import add_or_update_user
            # Update user record with phone info
            await add_or_update_user(
                user_id, 
                session_data.get("expiry_date", 0),
                username=session_data.get("username"),
                first_name=session_data.get("first_name")
            )
            return True
        except Exception as e:
            logger.error(f"Error saving user session: {e}")
            return False
    
    @staticmethod
    async def get_user_subscription(user_id: int) -> int:
        """Get user subscription expiry date"""
        try:
            from database import get_user_subscription
            return await get_user_subscription(user_id)
        except Exception as e:
            logger.error(f"Error getting user subscription: {e}")
            return 0
    
    @staticmethod
    async def log_login_attempt(user_id: int, phone: str, success: bool) -> bool:
        """Log login attempt to database"""
        try:
            from database import log_user_action
            action = "login_success" if success else "login_failed"
            await log_user_action(user_id, action)
            return True
        except Exception as e:
            logger.error(f"Error logging login attempt: {e}")
            return False
    
    @staticmethod
    async def get_user_info(user_id: int) -> Optional[Dict[str, Any]]:
        """Get user information from database"""
        try:
            from database import get_user_subscription, get_user_active_status
            expiry = await get_user_subscription(user_id)
            is_active = await get_user_active_status(user_id)
            return {
                "user_id": user_id,
                "expiry_date": expiry,
                "is_active": is_active
            }
        except Exception as e:
            logger.error(f"Error getting user info: {e}")
            return None
    
    @staticmethod
    async def set_user_active_status(user_id: int, is_active: bool) -> bool:
        """Set user active status in database"""
        try:
            from database import set_user_active_status
            await set_user_active_status(user_id, is_active)
            return True
        except Exception as e:
            logger.error(f"Error setting user active status: {e}")
            return False
    
    @staticmethod
    async def get_user_active_status(user_id: int) -> bool:
        """Get user active status from database"""
        try:
            from database import get_user_active_status
            return await get_user_active_status(user_id)
        except Exception as e:
            logger.error(f"Error getting user active status: {e}")
            return False


class UtagDatabaseAdapter:
    """Database adapter for UTAG system"""
    
    @staticmethod
    async def save_timer(
        user_id: int, 
        chat_id: int, 
        message_text: str, 
        interval_minutes: int,
        repeat_count: int = 1,
        repeat_delay: int = 5
    ) -> bool:
        """Save UTAG timer to database"""
        try:
            from database import get_db_connection
            import time
            
            async with get_db_connection() as db:
                await db.execute('''
                    INSERT INTO utag_timers 
                    (user_id, chat_id, message_text, interval_minutes, repeat_count, repeat_delay, is_active, last_sent, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, 1, 0, ?)
                    ON CONFLICT (user_id, chat_id) DO UPDATE SET
                        message_text = EXCLUDED.message_text,
                        interval_minutes = EXCLUDED.interval_minutes,
                        repeat_count = EXCLUDED.repeat_count,
                        repeat_delay = EXCLUDED.repeat_delay,
                        is_active = 1,
                        last_sent = 0,
                        created_at = EXCLUDED.created_at
                ''', (user_id, chat_id, message_text, interval_minutes, repeat_count, repeat_delay, int(time.time())))
                await db.commit()
            return True
        except Exception as e:
            logger.error(f"Error saving UTAG timer: {e}")
            return False
    
    @staticmethod
    async def get_timer(user_id: int, chat_id: int) -> Optional[Dict[str, Any]]:
        """Get UTAG timer from database"""
        try:
            from database import get_db_connection
            
            async with get_db_connection() as db:
                async with db.execute(
                    "SELECT * FROM utag_timers WHERE user_id = ? AND chat_id = ?",
                    (user_id, chat_id)
                ) as cursor:
                    row = await cursor.fetchone()
                    if row:
                        return {
                            "id": row[0],
                            "user_id": row[1],
                            "chat_id": row[2],
                            "message_text": row[3],
                            "interval_minutes": row[4],
                            "repeat_count": row[5],
                            "repeat_delay": row[6],
                            "is_active": bool(row[7]),
                            "last_sent": row[8],
                            "created_at": row[9]
                        }
            return None
        except Exception as e:
            logger.error(f"Error getting UTAG timer: {e}")
            return None
    
    @staticmethod
    async def delete_timer(user_id: int, chat_id: int) -> bool:
        """Delete UTAG timer from database"""
        try:
            from database import get_db_connection
            
            async with get_db_connection() as db:
                await db.execute(
                    "DELETE FROM utag_timers WHERE user_id = ? AND chat_id = ?",
                    (user_id, chat_id)
                )
                await db.commit()
            return True
        except Exception as e:
            logger.error(f"Error deleting UTAG timer: {e}")
            return False
    
    @staticmethod
    async def update_timer_last_sent(user_id: int, chat_id: int, last_sent: int) -> bool:
        """Update timer last sent timestamp"""
        try:
            from database import get_db_connection
            
            async with get_db_connection() as db:
                await db.execute(
                    "UPDATE utag_timers SET last_sent = ? WHERE user_id = ? AND chat_id = ?",
                    (last_sent, user_id, chat_id)
                )
                await db.commit()
            return True
        except Exception as e:
            logger.error(f"Error updating timer last sent: {e}")
            return False
    
    @staticmethod
    async def get_user_timers(user_id: int) -> List[Dict[str, Any]]:
        """Get all UTAG timers for user"""
        try:
            from database import get_db_connection
            
            async with get_db_connection() as db:
                async with db.execute(
                    "SELECT * FROM utag_timers WHERE user_id = ?",
                    (user_id,)
                ) as cursor:
                    rows = await cursor.fetchall()
                    return [
                        {
                            "id": row[0],
                            "user_id": row[1],
                            "chat_id": row[2],
                            "message_text": row[3],
                            "interval_minutes": row[4],
                            "repeat_count": row[5],
                            "repeat_delay": row[6],
                            "is_active": bool(row[7]),
                            "last_sent": row[8],
                            "created_at": row[9]
                        }
                        for row in rows
                    ]
        except Exception as e:
            logger.error(f"Error getting user UTAG timers: {e}")
            return []
    
    @staticmethod
    async def get_all_active_timers() -> List[Dict[str, Any]]:
        """Get all active UTAG timers for background processing"""
        try:
            from database import get_db_connection
            import time
            
            async with get_db_connection() as db:
                async with db.execute(
                    "SELECT * FROM utag_timers WHERE is_active = 1"
                ) as cursor:
                    rows = await cursor.fetchall()
                    return [
                        {
                            "id": row[0],
                            "user_id": row[1],
                            "chat_id": row[2],
                            "message_text": row[3],
                            "interval_minutes": row[4],
                            "repeat_count": row[5],
                            "repeat_delay": row[6],
                            "is_active": bool(row[7]),
                            "last_sent": row[8],
                            "created_at": row[9]
                        }
                        for row in rows
                    ]
        except Exception as e:
            logger.error(f"Error getting all active UTAG timers: {e}")
            return []
    
    @staticmethod
    async def get_user_command_preference(user_id: int, command_type: str) -> str:
        """Get user's custom command preference"""
        try:
            from database import get_db_connection
            
            async with get_db_connection() as db:
                async with db.execute(
                    f"SELECT utag_{command_type}_cmd FROM user_preferences WHERE user_id = ?",
                    (user_id,)
                ) as cursor:
                    row = await cursor.fetchone()
                    if row:
                        return row[0] or f"{command_type}"
            return command_type
        except Exception as e:
            logger.error(f"Error getting user command preference: {e}")
            return command_type
    
    @staticmethod
    async def set_user_command_preference(user_id: int, command_type: str, command: str) -> bool:
        """Set user's custom command preference"""
        try:
            from database import get_db_connection
            
            async with get_db_connection() as db:
                await db.execute(f'''
                    INSERT INTO user_preferences (user_id, utag_{command_type}_cmd)
                    VALUES (?, ?)
                    ON CONFLICT(user_id) DO UPDATE SET utag_{command_type}_cmd = ?
                ''', (user_id, command, command))
                await db.commit()
            return True
        except Exception as e:
            logger.error(f"Error setting user command preference: {e}")
            return False

    @staticmethod
    async def save_custom_command(user_id: int, command: str, message: str) -> bool:
        """Save custom tag command to database"""
        try:
            from database import save_user_custom_command
            import time
            await save_user_custom_command(user_id, command, message, int(time.time()))
            return True
        except Exception as e:
            logger.error(f"Error saving custom command: {e}")
            return False

    @staticmethod
    async def delete_custom_command(user_id: int, command: str) -> bool:
        """Delete custom tag command from database"""
        try:
            from database import delete_user_custom_command
            await delete_user_custom_command(user_id, command)
            return True
        except Exception as e:
            logger.error(f"Error deleting custom command: {e}")
            return False

    @staticmethod
    async def get_user_custom_commands(user_id: int) -> List[Dict[str, Any]]:
        """Get all custom tag commands for user"""
        try:
            from database import get_user_custom_commands
            return await get_user_custom_commands(user_id)
        except Exception as e:
            logger.error(f"Error getting user custom commands: {e}")
            return []

    @staticmethod
    async def get_all_custom_commands() -> List[Dict[str, Any]]:
        """Get all custom tag commands for background cache initialization"""
        try:
            from database import get_all_custom_commands
            return await get_all_custom_commands()
        except Exception as e:
            logger.error(f"Error getting all custom commands: {e}")
            return []


class GlobalErrorLogger:
    """Global error logging system for all modular systems"""
    
    @staticmethod
    async def log_error(
        system: str,
        user_id: int,
        error_type: str,
        error_message: str,
        context: Dict[str, Any] = None
    ) -> bool:
        """Log error to database for monitoring and debugging"""
        try:
            from database import get_db_connection
            import time
            
            context_str = str(context) if context else ""
            
            async with get_db_connection() as db:
                await db.execute('''
                    INSERT INTO admin_logs (admin_id, action, target_id, details, timestamp)
                    VALUES (?, ?, ?, ?, ?)
                ''', (user_id, f"{system}_error", user_id, 
                      f"{error_type}: {error_message} | Context: {context_str}", 
                      int(time.time())))
                await db.commit()
            return True
        except Exception as e:
            logger.error(f"Error logging to database: {e}")
            return False
    
    @staticmethod
    async def log_system_event(
        system: str,
        user_id: int,
        event_type: str,
        details: str
    ) -> bool:
        """Log system event to database"""
        try:
            from database import get_db_connection
            import time
            
            async with get_db_connection() as db:
                await db.execute('''
                    INSERT INTO admin_logs (admin_id, action, target_id, details, timestamp)
                    VALUES (?, ?, ?, ?, ?)
                ''', (user_id, f"{system}_{event_type}", user_id, details, int(time.time())))
                await db.commit()
            return True
        except Exception as e:
            logger.error(f"Error logging system event: {e}")
            return False


# Convenience functions for backward compatibility
async def save_massdm_progress(user_id: int, stats: Dict[str, Any]) -> bool:
    """Convenience function for MassDM progress saving"""
    return await MassDMDatabaseAdapter.save_progress(user_id, stats)


async def get_massdm_progress(user_id: int, group_id: str) -> int:
    """Convenience function for MassDM progress retrieval"""
    return await MassDMDatabaseAdapter.get_progress(user_id, group_id)


async def save_auto_stopped_task(user_id: int, stats: Dict[str, Any], reason: str, stop_key: str = None) -> bool:
    """Convenience function for auto-stopped task saving"""
    if stop_key is None:
        import time
        stop_key = f"{user_id}_{int(time.time())}"
    return await MassDMDatabaseAdapter.save_auto_stopped_task(stop_key, user_id, stats, reason)
