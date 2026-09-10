"""
Database Integration - Connects new modular systems with database
"""
import asyncio
from typing import Dict, List, Optional, Any
from database import (
    # User management
    add_or_update_user, get_user_subscription, is_free_user, get_known_user,
    # Login system
    register_known_user,
    # MassDM system  
    get_members_by_group_paginated, save_massdm_progress, get_massdm_progress,
    save_massdm_setting, get_massdm_setting,
    save_auto_stopped_task, get_auto_stopped_task, delete_auto_stopped_task, get_all_auto_stopped_tasks_for_user,
    # UTAG system
    get_user_utag_commands, save_user_utag_command, delete_utag_command,
    add_utag_timer, get_utag_timer, get_user_utag_timers, update_utag_timer_last_sent, set_utag_timer_active, delete_utag_timer
)


class LoginDatabaseIntegration:
    """Integrates login system with database"""
    
    @staticmethod
    async def register_user(user_id: int, username: str, first_name: str) -> bool:
        """Register user in database"""
        try:
            await register_known_user(user_id, username, first_name)
            return True
        except Exception as e:
            print(f"Error registering user: {e}")
            return False
    
    @staticmethod
    async def approve_user(user_id: int, expiry_days: int = 30) -> bool:
        """Approve user and give subscription"""
        try:
            import time
            expiry = int(time.time()) + expiry_days * 24 * 3600
            await add_or_update_user(user_id, expiry)
            return True
        except Exception as e:
            print(f"Error approving user: {e}")
            return False
    
    @staticmethod
    async def reject_user(user_id: int) -> bool:
        """Reject user (remove from database)"""
        try:
            from database import remove_user
            await remove_user(user_id)
            return True
        except Exception as e:
            print(f"Error rejecting user: {e}")
            return False
    
    @staticmethod
    async def check_user_access(user_id: int) -> bool:
        """Check if user has access to bot"""
        try:
            # Check if admin
            from config import is_admin
            if is_admin(user_id):
                return True
            
            # Check if free user
            if await is_free_user(user_id):
                return True
            
            # Check subscription
            subscription = await get_user_subscription(user_id)
            return subscription > 0
        except Exception as e:
            print(f"Error checking user access: {e}")
            return False


class MassDMDatabaseIntegration:
    """Integrates MassDM system with database"""
    
    @staticmethod
    async def get_group_members(group_id: str, offset: int = 0, limit: int = 1000) -> List[Dict[str, Any]]:
        """Get group members from database"""
        try:
            members = await get_members_by_group_paginated(group_id, offset, limit)
            return [
                {
                    "user_id": member["user_id"],
                    "username": member["username"],
                    "first_name": member["first_name"]
                }
                for member in members
            ]
        except Exception as e:
            print(f"Error getting group members: {e}")
            return []
    
    @staticmethod
    async def save_progress(user_id: int, group_id: str, stats: Dict[str, Any]) -> bool:
        """Save MassDM progress to database"""
        try:
            progress_data = {
                "last_index": stats.get("success", 0) + stats.get("failed", 0),
                "timestamp": int(__import__("time").time())
            }
            await save_massdm_progress(user_id, group_id, progress_data)
            return True
        except Exception as e:
            print(f"Error saving progress: {e}")
            return False
    
    @staticmethod
    async def get_progress(user_id: int, group_id: str) -> Optional[Dict[str, Any]]:
        """Get MassDM progress from database"""
        try:
            progress = await get_massdm_progress(user_id, group_id)
            return progress
        except Exception as e:
            print(f"Error getting progress: {e}")
            return None
    
    @staticmethod
    async def save_settings(user_id: int, settings: Dict[str, Any]) -> bool:
        """Save MassDM settings to database"""
        try:
            await save_massdm_setting(user_id, settings)
            return True
        except Exception as e:
            print(f"Error saving settings: {e}")
            return False
    
    @staticmethod
    async def get_settings(user_id: int) -> Dict[str, Any]:
        """Get MassDM settings from database"""
        try:
            settings = await get_massdm_setting(user_id)
            return settings if settings else {"auto_stop_on_high_risk": True}
        except Exception as e:
            print(f"Error getting settings: {e}")
            return {"auto_stop_on_high_risk": True}
    
    @staticmethod
    async def save_auto_stopped_task(stop_key: str, user_id: int, group_id: str, stats: Dict[str, Any], reason: str) -> bool:
        """Save auto-stopped task to database"""
        try:
            task_data = {
                "user_id": user_id,
                "group_id": group_id,
                "last_index": stats.get("success", 0) + stats.get("failed", 0),
                "reason": reason,
                "timestamp": int(__import__("time").time())
            }
            await save_auto_stopped_task(stop_key, task_data)
            return True
        except Exception as e:
            print(f"Error saving auto-stopped task: {e}")
            return False
    
    @staticmethod
    async def get_auto_stopped_tasks(user_id: int) -> List[Dict[str, Any]]:
        """Get user's auto-stopped tasks from database"""
        try:
            tasks = await get_all_auto_stopped_tasks_for_user(user_id)
            return tasks
        except Exception as e:
            print(f"Error getting auto-stopped tasks: {e}")
            return []
    
    @staticmethod
    async def delete_auto_stopped_task(stop_key: str) -> bool:
        """Delete auto-stopped task from database"""
        try:
            await delete_auto_stopped_task(stop_key)
            return True
        except Exception as e:
            print(f"Error deleting auto-stopped task: {e}")
            return False


class UtagDatabaseIntegration:
    """Integrates UTAG system with database"""
    
    @staticmethod
    async def save_command(user_id: int, command: str, message: str) -> bool:
        """Save UTAG command to database"""
        try:
            import time
            command_data = {
                "command": command,
                "message": message,
                "created_at": int(time.time())
            }
            await save_user_utag_command(user_id, command_data)
            return True
        except Exception as e:
            print(f"Error saving command: {e}")
            return False
    
    @staticmethod
    async def get_commands(user_id: int) -> List[Dict[str, Any]]:
        """Get user's UTAG commands from database"""
        try:
            commands = await get_user_utag_commands(user_id)
            return [
                {
                    "command": cmd["command"],
                    "message": cmd["message"],
                    "created_at": cmd.get("created_at", 0)
                }
                for cmd in commands
            ]
        except Exception as e:
            print(f"Error getting commands: {e}")
            return []
    
    @staticmethod
    async def delete_command(user_id: int, command: str) -> bool:
        """Delete UTAG command from database"""
        try:
            await delete_utag_command(user_id, command)
            return True
        except Exception as e:
            print(f"Error deleting command: {e}")
            return False
    
    @staticmethod
    async def save_timer(user_id: int, chat_id: int, interval: int, message: str = None) -> bool:
        """Save UTAG timer to database"""
        try:
            import time
            timer_data = {
                "chat_id": chat_id,
                "interval": interval,
                "message": message,
                "last_sent": 0,
                "is_active": True,
                "created_at": int(time.time())
            }
            await add_utag_timer(user_id, timer_data)
            return True
        except Exception as e:
            print(f"Error saving timer: {e}")
            return False
    
    @staticmethod
    async def get_timers(user_id: int) -> List[Dict[str, Any]]:
        """Get user's UTAG timers from database"""
        try:
            timers = await get_user_utag_timers(user_id)
            return [
                {
                    "chat_id": timer["chat_id"],
                    "interval": timer["interval"],
                    "message": timer.get("message"),
                    "last_sent": timer.get("last_sent", 0),
                    "is_active": timer.get("is_active", True),
                    "created_at": timer.get("created_at", 0)
                }
                for timer in timers
            ]
        except Exception as e:
            print(f"Error getting timers: {e}")
            return []
    
    @staticmethod
    async def update_timer_last_sent(timer_id: int) -> bool:
        """Update timer's last sent time"""
        try:
            import time
            await update_utag_timer_last_sent(timer_id, int(time.time()))
            return True
        except Exception as e:
            print(f"Error updating timer last sent: {e}")
            return False
    
    @staticmethod
    async def set_timer_active(timer_id: int, is_active: bool) -> bool:
        """Set timer active status"""
        try:
            await set_utag_timer_active(timer_id, is_active)
            return True
        except Exception as e:
            print(f"Error setting timer active: {e}")
            return False
    
    @staticmethod
    async def delete_timer(timer_id: int) -> bool:
        """Delete UTAG timer from database"""
        try:
            await delete_utag_timer(timer_id)
            return True
        except Exception as e:
            print(f"Error deleting timer: {e}")
            return False


class DatabaseManager:
    """Central database manager for all systems"""
    
    def __init__(self):
        self.login = LoginDatabaseIntegration()
        self.massdm = MassDMDatabaseIntegration()
        self.utag = UtagDatabaseIntegration()
    
    async def initialize(self):
        """Initialize database connections"""
        try:
            from database import init_db
            await init_db()
            return True
        except Exception as e:
            print(f"Error initializing database: {e}")
            return False


# Global database manager instance
database_manager = DatabaseManager()