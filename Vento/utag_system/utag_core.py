"""
UTAG Core - Business logic for tag commands and timers
"""
import asyncio
import random
import time
import logging
from typing import Dict, List, Optional, Any
from utag_system.action_engine import ActionEngine
from utag_system.utag_helpers import (
    get_utag_speed_seconds,
    send_completion_notification,
    ProgressThrottler,
    UTAG_SPEED_DEFAULT,
)
from pyrogram import Client
from pyrogram.errors import FloodWait, ChatWriteForbidden, UserBannedInChannel

from utag_system.utag_config import UtagSettings, UtagConstants, DEFAULT_TAG_MESSAGES

logger = logging.getLogger(__name__)


class UtagError(Exception):
    """Base UTAG error"""
    pass


class ValidationError(UtagError):
    """Validation error"""
    pass


class RateLimitError(UtagError):
    """Rate limit error"""
    pass


class CommandValidator:
    """Validates UTAG commands"""
    
    def __init__(self, settings: UtagSettings):
        self.settings = settings
    
    def validate_command(self, command: str) -> tuple[bool, str]:
        """
        Validate tag command
        
        Returns:
            (is_valid, error_message)
        """
        command = command.strip()
        
        if not command:
            return False, "Komanda bo'sh bo'lishi mumkin emas"
        
        if len(command) > self.settings.max_command_length:
            return False, f"Komanda juda uzun (max {self.settings.max_command_length} ta belgi)"
        
        if not command.startswith("/"):
            return False, "Komanda / bilan boshlanishi kerak"
        
        return True, ""
    
    def validate_timer_interval(self, interval: int) -> tuple[bool, str]:
        """
        Validate timer interval
        
        Returns:
            (is_valid, error_message)
        """
        if interval < 60:
            return False, "Interval kamida 60 sekund bo'lishi kerak"
        
        if interval > 86400:  # 24 hours
            return False, "Interval ko'pi bilan 24 soat bo'lishi mumkin"
        
        return True, ""


class TagMessageSelector:
    """Selects random tag messages"""
    
    def __init__(self, messages: Dict[int, str] = None):
        self.messages = messages or DEFAULT_TAG_MESSAGES
    
    def get_random_message(self) -> str:
        """Get random tag message"""
        if not self.messages:
            return "Salom! 👋"
        
        return random.choice(list(self.messages.values()))
    
    def get_message_by_id(self, message_id: int) -> Optional[str]:
        """Get specific message by ID"""
        return self.messages.get(message_id)


class TagCommand:
    """Represents a custom tag command"""
    
    def __init__(self, user_id: int, command: str, message: str, created_at: float = 0):
        self.user_id = user_id
        self.command = command
        self.message = message
        self.created_at = created_at if created_at > 0 else time.time()
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "user_id": self.user_id,
            "command": self.command,
            "message": self.message,
            "created_at": self.created_at
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'TagCommand':
        """Create from dictionary"""
        return cls(
            data["user_id"],
            data["command"],
            data["message"],
            data.get("created_at", time.time())
        )


class TimerTask:
    """Represents a scheduled UTAG timer"""
    
    def __init__(self, user_id: int, chat_id: int, interval: int, message: str = None, repeat_count: int = 1, repeat_delay: int = 5):
        self.user_id = user_id
        self.chat_id = chat_id
        self.interval = interval
        self.message = message
        self.repeat_count = repeat_count
        self.repeat_delay = repeat_delay
        self.last_sent = 0
        self.is_active = True
        self.created_at = time.time()
    
    def should_send(self) -> bool:
        """Check if timer should send now"""
        if not self.is_active:
            return False
        
        return time.time() - self.last_sent >= self.interval
    
    def mark_sent(self):
        """Mark timer as sent"""
        self.last_sent = time.time()
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "user_id": self.user_id,
            "chat_id": self.chat_id,
            "interval": self.interval,
            "message": self.message,
            "repeat_count": self.repeat_count,
            "repeat_delay": self.repeat_delay,
            "last_sent": self.last_sent,
            "is_active": self.is_active,
            "created_at": self.created_at
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'TimerTask':
        """Create from dictionary"""
        timer = cls(
            data["user_id"],
            data["chat_id"],
            data["interval"],
            data.get("message"),
            data.get("repeat_count", 1),
            data.get("repeat_delay", 5)
        )
        timer.last_sent = data.get("last_sent", 0)
        timer.is_active = data.get("is_active", True)
        timer.created_at = data.get("created_at", time.time())
        return timer


class CommandManager:
    """Manages custom tag commands"""
    
    def __init__(self, settings: UtagSettings):
        self.settings = settings
        self.commands: Dict[int, Dict[str, TagCommand]] = {}  # user_id -> {command: TagCommand}
        self._lock = asyncio.Lock()
    
    async def add_command(self, user_id: int, command: str, message: str) -> bool:
        """Add custom command"""
        async with self._lock:
            # Check limit
            user_commands = self.commands.get(user_id, {})
            if len(user_commands) >= self.settings.max_custom_commands:
                return False
            
            # Save to database
            try:
                from database_adapter import UtagDatabaseAdapter
                db_success = await UtagDatabaseAdapter.save_custom_command(user_id, command, message)
                if not db_success:
                    return False
                logger.info(f"[DB] Saved custom command '{command}' for user {user_id}")
            except Exception as e:
                logger.error(f"Error saving custom command to database: {e}")
                return False
            
            # Add command to memory cache
            if user_id not in self.commands:
                self.commands[user_id] = {}
            
            self.commands[user_id][command] = TagCommand(user_id, command, message)
            return True
    
    async def remove_command(self, user_id: int, command: str) -> bool:
        """Remove custom command"""
        async with self._lock:
            if user_id in self.commands and command in self.commands[user_id]:
                # Delete from database
                try:
                    from database_adapter import UtagDatabaseAdapter
                    db_success = await UtagDatabaseAdapter.delete_custom_command(user_id, command)
                    if not db_success:
                        return False
                    logger.info(f"[DB] Deleted custom command '{command}' for user {user_id}")
                except Exception as e:
                    logger.error(f"Error deleting custom command from database: {e}")
                    return False
                
                # Delete from cache
                del self.commands[user_id][command]
                return True
            return False
    
    async def get_user_commands(self, user_id: int) -> List[TagCommand]:
        """Get user's commands"""
        async with self._lock:
            return list(self.commands.get(user_id, {}).values())
    
    async def get_command(self, user_id: int, command: str) -> Optional[TagCommand]:
        """Get specific command"""
        async with self._lock:
            return self.commands.get(user_id, {}).get(command)
    
    async def command_exists(self, user_id: int, command: str) -> bool:
        """Check if command exists"""
        async with self._lock:
            return command in self.commands.get(user_id, {})


class TimerManager:
    """Manages UTAG timers"""
    
    def __init__(self, settings: UtagSettings):
        self.settings = settings
        self.timers: Dict[int, List[TimerTask]] = {}  # user_id -> [TimerTask]
        self._lock = asyncio.Lock()
    
    async def add_timer(self, user_id: int, chat_id: int, interval: int, message: str = None) -> TimerTask:
        """Add timer"""
        async with self._lock:
            timer = TimerTask(user_id, chat_id, interval, message)
            
            if user_id not in self.timers:
                self.timers[user_id] = []
            
            self.timers[user_id].append(timer)
            
            # Save to database
            try:
                from database_adapter import UtagDatabaseAdapter
                await UtagDatabaseAdapter.save_timer(
                    user_id, chat_id, message or "", interval, 
                    timer.repeat_count, timer.repeat_delay
                )
            except Exception as e:
                logger.warning("Error saving timer to database: %s", e)
            
            return timer
    
    async def remove_timer(self, user_id: int, chat_id: int) -> bool:
        """Remove timer"""
        async with self._lock:
            if user_id in self.timers:
                self.timers[user_id] = [
                    t for t in self.timers[user_id] 
                    if t.chat_id != chat_id
                ]
                
                # Remove from database
                try:
                    from database_adapter import UtagDatabaseAdapter
                    await UtagDatabaseAdapter.delete_timer(user_id, chat_id)
                except Exception as e:
                    logger.warning("Error deleting timer from database: %s", e)
                
                return True
            return False
    
    async def get_user_timers(self, user_id: int) -> List[TimerTask]:
        """Get user's timers"""
        async with self._lock:
            return self.timers.get(user_id, []).copy()
    
    async def get_due_timers(self) -> List[TimerTask]:
        """Get timers that should send now"""
        async with self._lock:
            due_timers = []
            for user_id, timers in self.timers.items():
                for timer in timers:
                    if timer.should_send():
                        due_timers.append(timer)
            return due_timers
    
    async def load_timers_from_database(self):
        """Load timers from database on startup"""
        try:
            from database_adapter import UtagDatabaseAdapter
            all_timers = await UtagDatabaseAdapter.get_all_active_timers()
            
            async with self._lock:
                for timer_data in all_timers:
                    user_id = timer_data["user_id"]
                    chat_id = timer_data["chat_id"]
                    
                    if user_id not in self.timers:
                        self.timers[user_id] = []
                    
                    # Check if timer already exists
                    existing = any(t.chat_id == chat_id for t in self.timers[user_id])
                    if not existing:
                        timer = TimerTask.from_dict(timer_data)
                        self.timers[user_id].append(timer)
            
            logger.info("Loaded %d timers from database", len(all_timers))
        except Exception as e:
            logger.warning("Error loading timers from database: %s", e)
    
    async def update_timer_last_sent(self, user_id: int, chat_id: int):
        """Update timer last sent timestamp in memory and database"""
        async with self._lock:
            if user_id in self.timers:
                for timer in self.timers[user_id]:
                    if timer.chat_id == chat_id:
                        timer.mark_sent()
                        
                        # Update in database
                        try:
                            from database_adapter import UtagDatabaseAdapter
                            await UtagDatabaseAdapter.update_timer_last_sent(
                                user_id, chat_id, int(timer.last_sent)
                            )
                        except Exception as e:
                            logger.warning("Error updating timer in database: %s", e)
                        break
    
    async def mark_timer_sent(self, timer: TimerTask):
        """Mark timer as sent"""
        await self.update_timer_last_sent(timer.user_id, timer.chat_id)


class UtagService:
    """Main UTAG service coordinating all components"""
    
    def __init__(self, settings: UtagSettings):
        self.settings = settings
        self.validator = CommandValidator(settings)
        self.message_selector = TagMessageSelector()
        self.command_manager = CommandManager(settings)
        self.timer_manager = TimerManager(settings)
        self.active_tasks: Dict[int, Dict[str, Any]] = {}  # user_id -> task_info
        self._lock = asyncio.Lock()
        self._initialized = False
        self.user_commands: Dict[int, Dict[str, str]] = {}  # user_id -> {command_type: custom_command}
    
    async def initialize(self):
        """Initialize service by loading data from database"""
        if not self._initialized:
            # Load timers
            await self.timer_manager.load_timers_from_database()
            
            # Load custom tag commands
            try:
                from database_adapter import UtagDatabaseAdapter
                all_cmds = await UtagDatabaseAdapter.get_all_custom_commands()
                for cmd_data in all_cmds:
                    u_id = cmd_data["user_id"]
                    cmd = cmd_data["command"]
                    msg = cmd_data["message"]
                    created = cmd_data.get("created_at", 0)
                    
                    if u_id not in self.command_manager.commands:
                        self.command_manager.commands[u_id] = {}
                    
                    self.command_manager.commands[u_id][cmd] = TagCommand(u_id, cmd, msg, created)
                logger.info(f"Loaded {len(all_cmds)} custom tag commands from database.")
            except Exception as e:
                logger.error(f"Error loading custom tag commands from database: {e}")
                
            self._initialized = True
    
    async def get_user_command(self, user_id: int, command_type: str) -> str:
        """Get user's custom command for a type"""
        # Check memory cache
        if user_id in self.user_commands and command_type in self.user_commands[user_id]:
            return self.user_commands[user_id][command_type]
        
        # Load from database
        try:
            from database_adapter import UtagDatabaseAdapter
            custom_cmd = await UtagDatabaseAdapter.get_user_command_preference(user_id, command_type)
            
            # Cache in memory
            if user_id not in self.user_commands:
                self.user_commands[user_id] = {}
            self.user_commands[user_id][command_type] = custom_cmd
            
            return custom_cmd
        except Exception as e:
            logger.warning("Error getting user command preference: %s", e)
            return command_type  # Fallback to default
    
    async def set_user_command(self, user_id: int, command_type: str, custom_command: str) -> bool:
        """Set user's custom command for a type"""
        try:
            from database_adapter import UtagDatabaseAdapter
            success = await UtagDatabaseAdapter.set_user_command_preference(user_id, command_type, custom_command)
            
            if success:
                # Update memory cache
                if user_id not in self.user_commands:
                    self.user_commands[user_id] = {}
                self.user_commands[user_id][command_type] = custom_command
            
            return success
        except Exception as e:
            logger.warning("Error setting user command preference: %s", e)
            return False
    
    async def add_custom_command(self, user_id: int, command: str, message: str) -> tuple[bool, str]:
        """Add custom command"""
        # Validate command
        is_valid, error = self.validator.validate_command(command)
        if not is_valid:
            return False, error
        
        # Check if command already exists
        exists = await self.command_manager.command_exists(user_id, command)
        if exists:
            return False, "Komanda allaqachon mavjud"
        
        # Add command
        success = await self.command_manager.add_command(user_id, command, message)
        if success:
            return True, self.settings.messages["command_added"]
        else:
            return False, self.settings.messages["error_limit"]
    
    async def remove_custom_command(self, user_id: int, command: str) -> tuple[bool, str]:
        """Remove custom command"""
        success = await self.command_manager.remove_command(user_id, command)
        if success:
            return True, self.settings.messages["command_removed"]
        else:
            return False, self.settings.messages["error_not_found"]
    
    async def get_user_commands(self, user_id: int) -> List[TagCommand]:
        """Get user's commands"""
        return await self.command_manager.get_user_commands(user_id)
    
    async def execute_command(self, user_id: int, command: str) -> Optional[str]:
        """Execute tag command and return message"""
        tag_command = await self.command_manager.get_command(user_id, command)
        if tag_command:
            return tag_command.message
        return None
    
    async def add_timer(self, user_id: int, chat_id: int, interval: int, message: str = None) -> tuple[bool, str]:
        """Add timer"""
        # Validate interval
        is_valid, error = self.validator.validate_timer_interval(interval)
        if not is_valid:
            return False, error
        
        # Add timer
        await self.timer_manager.add_timer(user_id, chat_id, interval, message)
        return True, self.settings.messages["timer_set"]
    
    async def remove_timer(self, user_id: int, chat_id: int) -> tuple[bool, str]:
        """Remove timer"""
        success = await self.timer_manager.remove_timer(user_id, chat_id)
        if success:
            return True, self.settings.messages["timer_removed"]
        else:
            return False, self.settings.messages["error_not_found"]
    
    async def get_user_timers(self, user_id: int) -> List[TimerTask]:
        """Get user's timers"""
        return await self.timer_manager.get_user_timers(user_id)
    
    async def process_due_timers(self, client: Client) -> List[tuple[TimerTask, bool]]:
        """
        Process due timers and send messages
        
        Returns:
            List of (timer, success) tuples
        """
        due_timers = await self.timer_manager.get_due_timers()
        results = []
        
        for timer in due_timers:
            try:
                message = timer.message or self.message_selector.get_random_message()
                
                await client.send_message(timer.chat_id, message)
                await self.timer_manager.mark_timer_sent(timer)
                results.append((timer, True))
                
            except FloodWait as e:
                await asyncio.sleep(e.value + 1)
                try:
                    await client.send_message(timer.chat_id, timer.message or self.message_selector.get_random_message())
                    await self.timer_manager.mark_timer_sent(timer)
                    results.append((timer, True))
                except:
                    results.append((timer, False))
            except Exception:
                results.append((timer, False))
        
        return results

    async def get_active_tagging_count(self, user_id: int) -> int:
        """Get active tagging tasks count for user"""
        async with self._lock:
            return sum(1 for k, v in self.active_tasks.items() if v["user_id"] == user_id)

    async def get_active_tagging_processes(self, user_id: int) -> list:
        """Get active tagging tasks list for user"""
        async with self._lock:
            return [v for k, v in self.active_tasks.items() if v["user_id"] == user_id]

    async def stop_tagging(self, user_id: int, chat_id: int) -> bool:
        """Stop tagging process"""
        process_key = f"{user_id}_{chat_id}"
        async with self._lock:
            if process_key in self.active_tasks:
                self.active_tasks[process_key]["stop_flag"][0] = True
                logger.info(f"[UTAG] Requested stop tagging for user {user_id} in chat {chat_id}")
                return True
            return False

    async def stop_all_tagging(self, user_id: int) -> int:
        """Stop all tagging processes for user"""
        async with self._lock:
            count = 0
            for k, v in self.active_tasks.items():
                if v["user_id"] == user_id:
                    v["stop_flag"][0] = True
                    count += 1
            if count > 0:
                logger.info(f"[UTAG] Requested stop for all ({count}) tagging tasks of user {user_id}")
            return count

    async def pause_tagging(self, user_id: int, chat_id: int) -> bool:
        """Pause tagging process"""
        process_key = f"{user_id}_{chat_id}"
        async with self._lock:
            if process_key in self.active_tasks:
                self.active_tasks[process_key]["pause_flag"][0] = True
                logger.info(f"[UTAG] Paused tagging for user {user_id} in chat {chat_id}")
                return True
            return False

    async def resume_tagging(self, user_id: int, chat_id: int) -> bool:
        """Resume tagging process"""
        process_key = f"{user_id}_{chat_id}"
        async with self._lock:
            if process_key in self.active_tasks:
                self.active_tasks[process_key]["pause_flag"][0] = False
                logger.info(f"[UTAG] Resumed tagging for user {user_id} in chat {chat_id}")
                return True
            return False

    async def start_tagging(
        self,
        user_id: int,
        chat_id: int,
        client: Client,
        user_client: Client,
        members: List[str],
        tag_message: str,
        use_random_messages: bool,
        settings: dict,
        command: str
    ) -> tuple[bool, str]:
        """Start background tagging process"""
        process_key = f"{user_id}_{chat_id}"
        
        # 1. Prevent duplicate active tasks per user/group
        async with self._lock:
            if process_key in self.active_tasks:
                return False, "Siz allaqachon bu guruhda utag ishlatyapsiz!"
            
            # Check parallel limit
            active_count = sum(1 for k, v in self.active_tasks.items() if v["user_id"] == user_id)
            if active_count >= self.settings.max_parallel_utag:
                return False, f"Maksimal parallel utag limiti ({self.settings.max_parallel_utag}) ga yetdingiz."
            
            stop_flag = [False]
            pause_flag = [False]
            
            # Create task representation
            self.active_tasks[process_key] = {
                "user_id": user_id,
                "chat_id": chat_id,
                "stop_flag": stop_flag,
                "pause_flag": pause_flag,
                "tagged": 0,
                "failed": 0,
                "total": len(members),
                "start_time": time.time(),
                "last_message_id": None,
                "consecutive_deletions": 0,
                "consecutive_failures": 0
            }
            
                        # Start background tagging loop
            from task_supervisor import schedule_guarded
            task = schedule_guarded("UTAG Tagging Task", self._run_tagging_process(
                    user_id, chat_id, client, user_client, members, 
                    tag_message, use_random_messages, settings, stop_flag, pause_flag
                )
            )
            
            self.active_tasks[process_key]["task"] = task
            logger.info(f"[UTAG] Started tagging task for user {user_id} in chat {chat_id} with {len(members)} members.")
            
        return True, "Boshlandi"

    async def _run_tagging_process(
        self,
        user_id: int,
        chat_id: int,
        client: Client,
        user_client: Client,
        members: List[str],
        tag_message: str,
        use_random_messages: bool,
        settings: dict,
        stop_flag: List[bool],
        pause_flag: List[bool]
    ):
        """Background tagging execution loop"""
        process_key = f"{user_id}_{chat_id}"
        
        # [STEP 1] Task started
        logger.info(f"[STEP 1] Task started: user_id={user_id}, chat_id={chat_id}, members_count={len(members)}, use_random={use_random_messages}")
        logger.info(f"[DEBUG UTAG] Task Execution Started: user_id={user_id}, chat_id={chat_id}, members_count={len(members)}, use_random={use_random_messages}")
        
        try:
            # Integrate with queue_manager
            logger.info("[STEP 2] About to import queue_manager functions")
            from queue_manager import queue_manager, register_active_task, update_task_progress, unregister_active_task
            logger.info("[STEP 2a] queue_manager functions imported successfully")
            
            logger.info("[STEP 2b] About to call asyncio.current_task()")
            background_task = asyncio.current_task()
            logger.info(f"[STEP 2b] Got current task: {background_task}")
            
            logger.info("[STEP 2c] About to call register_active_task()")
            logger.info(f"[STEP 2c1] Calling with user_id={user_id}, task_type=utag, target=Chat {chat_id}")
            await register_active_task(
                user_id=user_id,
                task_type="utag",
                target=f"Chat {chat_id}",
                stop_flag=stop_flag,
                task_object=background_task
            )
            logger.info("[STEP 2d] register_active_task() completed")
            
            # Speed delays settings
            logger.info("[STEP 3] About to parse settings")
            speed_seconds = get_utag_speed_seconds(settings)
            show_completion = settings.get("utag_completion_msg", True)
            typing_status = settings.get("utag_typing_status", True)
            auto_stop_on_delete = settings.get("utag_auto_stop_on_delete", True)
            delete_timer = settings.get("utag_delete_timer", 2)

            logger.info(
                f"[STEP 3a] Config parsed: speed={speed_seconds}s, show_completion={show_completion}, "
                f"typing={typing_status}, auto_stop={auto_stop_on_delete}"
            )
            used_messages = []
            progress_throttler = ProgressThrottler(speed_seconds)

            # [STEP 4] Check flags before loop
            logger.info(f"[STEP 4] Pre-loop flag check: stop_flag={stop_flag[0]}, pause_flag={pause_flag[0]}, process_key in active_tasks={process_key in self.active_tasks}")
            logger.info(f"[FLAG CHECK] stop_flag[0]={stop_flag[0]}, pause_flag[0]={pause_flag[0]}, process_key={process_key}, in_active_tasks={process_key in self.active_tasks}")
            
            # [STEP 5] About to enter member loop
            logger.info(f"[STEP 5] About to enter member loop with {len(members)} members")
            logger.info(f"[LOOP START] Entering for loop with {len(members)} members")
            
            for idx, username in enumerate(members, 1):
                # [STEP 6] First iteration check
                logger.info(f"[STEP 6] Loop iteration {idx} starting")
                if idx == 1:
                    logger.info(f"[STEP 6] First iteration: idx={idx}, username={username}")
                    logger.info(f"[DEBUG UTAG] First iteration started: idx={idx}, username={username}")
                
                # Check cancellation/stop flags
                logger.info(f"[STEP 7] Iteration {idx}: Checking stop_flag={stop_flag[0]}, process_key in active_tasks={process_key in self.active_tasks}")
                logger.info(f"[FLAG CHECK 2] stop_flag={stop_flag[0]}, process_key_exists={process_key in self.active_tasks}")
                if stop_flag[0] or process_key not in self.active_tasks:
                    logger.info(f"[DEBUG UTAG] Task stop flag is active or process key removed. Breaking loop.")
                    logger.info(f"[BREAK 1] Stop flag or missing process_key: stop_flag={stop_flag[0]}, in_active_tasks={process_key in self.active_tasks}")
                    break
                
                # Check pause flag
                logger.info(f"[STEP 8] Iteration {idx}: Checking pause_flag={pause_flag[0]}")
                if pause_flag[0]:
                    logger.info(f"[DEBUG UTAG] Task is paused. Waiting for resume...")
                while pause_flag[0]:
                    logger.info(f"[PAUSE LOOP] Iteration {idx}: In pause loop, checking flags")
                    if stop_flag[0] or process_key not in self.active_tasks:
                        logger.info(f"[BREAK 2] Stop flag triggered in pause loop")
                        break
                    await asyncio.sleep(1)
                
                if stop_flag[0] or process_key not in self.active_tasks:
                    logger.info(f"[DEBUG UTAG] Task stop flag is active after pause. Breaking loop.")
                    logger.info(f"[BREAK 3] Stop flag after pause: stop_flag={stop_flag[0]}, in_active_tasks={process_key in self.active_tasks}")
                    break
                
                # Get current stats
                logger.info(f"[STEP 9] Iteration {idx}: Getting process stats")
                async with self._lock:
                    process_info = self.active_tasks.get(process_key)
                    if not process_info:
                        logger.info(f"[DEBUG UTAG] Process info not found for {process_key}. Breaking loop.")
                        logger.info(f"[BREAK 4] Process info not found")
                        break
                    consecutive_deletions = process_info.get("consecutive_deletions", 0)
                    consecutive_failures = process_info.get("consecutive_failures", 0)
                    last_message_id = process_info.get("last_message_id")
                logger.info(f"[STEP 9a] Stats retrieved: consecutive_deletions={consecutive_deletions}, consecutive_failures={consecutive_failures}, last_message_id={last_message_id}")
                
                # Check if the previous message was deleted by admins (auto-stop guard)
                logger.info(f"[STEP 10] Iteration {idx}: Checking auto-stop on delete")
                if last_message_id and auto_stop_on_delete:
                    try:
                        msg = await user_client.get_messages(chat_id, last_message_id)
                        if msg is None or msg.empty:
                            consecutive_deletions += 1
                            logger.info(f"[DEBUG UTAG] Last tag message {last_message_id} was deleted. Consecutive deletions: {consecutive_deletions}")
                            async with self._lock:
                                if process_key in self.active_tasks:
                                    self.active_tasks[process_key]["consecutive_deletions"] = consecutive_deletions
                            
                            if consecutive_deletions >= 5:
                                logger.warning(f"[UTAG] Auto-stopped for user {user_id} in chat {chat_id} due to {consecutive_deletions} consecutive deletions by admins.")
                                logger.info(f"[BREAK 5] Auto-stop on delete: consecutive_deletions={consecutive_deletions}")
                                break
                        else:
                            consecutive_deletions = 0
                            async with self._lock:
                                if process_key in self.active_tasks:
                                    self.active_tasks[process_key]["consecutive_deletions"] = 0
                    except Exception as e:
                        logger.error(f"[UTAG] Error checking deleted message: {e}")
                
                # Select tagging text
                logger.info(f"[STEP 11] Iteration {idx}: Selecting message text")
                if use_random_messages:
                    available = [k for k in DEFAULT_TAG_MESSAGES.keys() if k not in used_messages]
                    if not available:
                        used_messages.clear()
                        available = list(DEFAULT_TAG_MESSAGES.keys())
                    random_id = random.choice(available)
                    used_messages.append(random_id)
                    message_text = f"@{username} {DEFAULT_TAG_MESSAGES[random_id]}"
                elif tag_message:
                    message_text = f"@{username} {tag_message}"
                else:
                    message_text = f"@{username}"
                logger.info(f"[STEP 11a] Message text selected: {message_text[:50]}...")
                
                await ActionEngine.apply_dispatch_suppression(user_client, chat_id, settings, settings)

                # Choose parse_mode: only use 'html' when tg-emoji is present, otherwise omit to avoid parsing issues
                use_html_parse = "<tg-emoji" in message_text or "tg://emoji" in message_text
                
                # Send the tag message
                logger.info(f"[STEP 13] Iteration {idx}: About to send message")
                logger.info(f"[DEBUG UTAG] [{idx}/{len(members)}] Sending tag message to {chat_id}: '{message_text}' (parse_mode={'html' if use_html_parse else 'None/omitted'})")
                try:
                    if use_html_parse:
                        sent_msg = await user_client.send_message(chat_id, message_text, parse_mode="html")
                    else:
                        sent_msg = await user_client.send_message(chat_id, message_text)
                    logger.info(f"[STEP 14] Iteration {idx}: Message sent successfully. msg_id={sent_msg.id}")
                    logger.info(f"[DEBUG UTAG] [{idx}/{len(members)}] Tag sent successfully. msg_id={sent_msg.id}")
                    
                    async with self._lock:
                        if process_key in self.active_tasks:
                            self.active_tasks[process_key]["tagged"] += 1
                            self.active_tasks[process_key]["consecutive_failures"] = 0
                            self.active_tasks[process_key]["last_message_id"] = sent_msg.id
                            
                            # Sync progress to queue_manager
                            progress_pct = int((self.active_tasks[process_key]["tagged"] / len(members)) * 100)
                            if progress_throttler.should_update():
                                logger.info(f"[STEP 15] Iteration {idx}: Updating queue_manager progress to {progress_pct}%")
                                await update_task_progress(user_id, progress_pct)
                                logger.info(f"[STEP 15a] Iteration {idx}: queue_manager progress updated")
                
                except FloodWait as e:
                    logger.warning(f"[UTAG] FloodWait {e.value}s encountered for user {user_id}. Waiting...")
                    await asyncio.sleep(e.value + 3)
                    try:
                        if use_html_parse:
                            sent_msg = await user_client.send_message(chat_id, message_text, parse_mode="html")
                        else:
                            sent_msg = await user_client.send_message(chat_id, message_text)
                        logger.info(f"[DEBUG UTAG] Tag sent successfully after FloodWait. msg_id={sent_msg.id}")
                        logger.info(f"[STEP 16] Iteration {idx}: Message sent after FloodWait")
                        async with self._lock:
                            if process_key in self.active_tasks:
                                self.active_tasks[process_key]["tagged"] += 1
                                self.active_tasks[process_key]["consecutive_failures"] = 0
                                self.active_tasks[process_key]["last_message_id"] = sent_msg.id
                    except Exception as ex:
                        logger.error(f"[DEBUG UTAG] Exception sending tag after FloodWait: {ex}", exc_info=True)
                        async with self._lock:
                            if process_key in self.active_tasks:
                                self.active_tasks[process_key]["failed"] += 1
                                self.active_tasks[process_key]["consecutive_failures"] += 1
                
                except (ChatWriteForbidden, UserBannedInChannel) as e:
                    logger.warning(f"[UTAG] Terminating task because user {user_id} was restricted/banned in chat {chat_id}: {e}")
                    logger.info(f"[BREAK 6] ChatWriteForbidden/UserBannedInChannel: {e}")
                    break
                
                except Exception as e:
                    logger.error(f"[DEBUG UTAG] Exception caught while sending tag message: {e}", exc_info=True)
                    async with self._lock:
                        if process_key in self.active_tasks:
                            self.active_tasks[process_key]["failed"] += 1
                            self.active_tasks[process_key]["consecutive_failures"] += 1
                            consecutive_failures = self.active_tasks[process_key]["consecutive_failures"]
                    
                    if consecutive_failures >= 5:
                        logger.warning(f"[UTAG] Terminating tagging task for user {user_id} due to 5 consecutive failures.")
                        logger.info(f"[BREAK 7] 5 consecutive failures")
                        break
                
                # Apply delay between tagging messages
                logger.info(f"[STEP 17] Iteration {idx}: Applying delay")
                logger.info(f"[DEBUG UTAG] Sleeping for {speed_seconds:.2f}s before next tag.")
                await asyncio.sleep(speed_seconds)
                logger.info(f"[STEP 18] Iteration {idx}: Delay complete, continuing to next iteration")
            
            # [STEP 19] Loop finished
            logger.info(f"[STEP 19] Member loop finished. Total iterations: {idx if 'idx' in locals() else 0}")
            
            # Send completion notification in group chat
            logger.info(f"[STEP 20] Checking completion report: show_completion={show_completion}")
            if show_completion:
                async with self._lock:
                    tagged = 0
                    if process_key in self.active_tasks:
                        tagged = self.active_tasks[process_key]["tagged"]
                await send_completion_notification(
                    user_client, chat_id, tagged, delete_timer, show_completion=True
                )
                logger.info(f"[STEP 21] Completion notification sent: tagged={tagged}")
                    
        except Exception as e:
            # [UNCAUGHT EXCEPTION] Full traceback for any unhandled exception
            logger.exception(f"[UNCAUGHT EXCEPTION] Unhandled exception in _run_tagging_process: {e}")
            logger.info(f"[FATAL] Task terminated due to uncaught exception")
            import traceback
            logger.info(f"[FATAL TRACEBACK]\n{traceback.format_exc()}")
        finally:
            # [STEP 22] Cleanup
            logger.info(f"[STEP 22] Entering finally block for cleanup")
            # Cleanup active task completely
            async with self._lock:
                self.active_tasks.pop(process_key, None)
            
            # Unregister task from queue manager
            logger.info(f"[STEP 23] About to unregister from queue_manager")
            await unregister_active_task(user_id)
            logger.info(f"[STEP 24] Unregistered from queue_manager")
            logger.info(f"[STEP 25] Task Execution Completed & Cleaned Up: user_id={user_id}, chat_id={chat_id}")
            logger.info(f"[DEBUG UTAG] Task Execution Completed & Cleaned Up: user_id={user_id}, chat_id={chat_id}")
