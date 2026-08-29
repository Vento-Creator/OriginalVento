"""
MassDM Core - Business logic for mass messaging with full anti-spam protection
"""
import asyncio
import random
import time
import logging
from typing import Dict, List, Optional, Tuple, Any
from pyrogram import Client
from pyrogram.errors import (
    FloodWait, UserDeactivated, UserIsBlocked, PeerIdInvalid, 
    ChatWriteForbidden, UserPrivacyRestricted
)

from massdm_system.massdm_config import MassDMSettings, MassDMConstants, SPAMBOT_UNLOCK_KEYWORDS, SPAMBOT_RESTRICTION_KEYWORDS

logger = logging.getLogger(__name__)


class MassDMError(Exception):
    """Base MassDM error"""
    pass


class SessionError(MassDMError):
    """Session related error"""
    pass


class RateLimitError(MassDMError):
    """Rate limit error"""
    pass


class ValidationError(MassDMError):
    """Validation error"""
    pass


class SpamBotRestrictedError(MassDMError):
    """SpamBot restriction detected"""
    pass


class ErrorClassifier:
    """Classifies Telegram errors into user-friendly messages"""
    
    @classmethod
    def classify(cls, error: Exception) -> str:
        """Classify error into user-friendly message"""
        error_name = type(error).__name__
        error_msg = str(error).lower()
        
        # Check for payment related
        if any(kw in error_msg for kw in ["stars", "paid_media", "payment_required", "stellar"]) or \
           any(kw in error_name for kw in ["StarsFeeRequired", "PaidMediaRequired", "PaymentRequired"]):
            return MassDMConstants.ERROR_PAYMENT
        
        # Check for blocked
        if "blocked" in error_msg or "UserIsBlocked" in error_name:
            return MassDMConstants.ERROR_BLOCKED
        
        # Check for deactivated
        if "deactivated" in error_msg or "InputUserDeactivated" in error_name:
            return MassDMConstants.ERROR_DEACTIVATED
        
        # Check for privacy
        if "privacy" in error_msg or "UserPrivacyRestricted" in error_name:
            return MassDMConstants.ERROR_PRIVACY
        
        # Check for not found
        if "not found" in error_msg or "PeerIdInvalid" in error_name:
            return MassDMConstants.ERROR_NOT_FOUND
        
        # Check for write forbidden
        if "write_forbidden" in error_msg or "ChatWriteForbidden" in error_name:
            return MassDMConstants.ERROR_WRITE_FORBIDDEN
        
        # Check for premium
        if "premium" in error_msg or "DirectMessagePremiumRequired" in error_name:
            return MassDMConstants.ERROR_PREMIUM
        
        # Check for floodwait
        if "FloodWait" in error_name:
            return MassDMConstants.ERROR_FLOODWAIT
        
        # Check for forbidden
        if "forbidden" in error_msg or "Forbidden" in error_name:
            return MassDMConstants.ERROR_FORBIDDEN
        
        return MassDMConstants.ERROR_UNKNOWN


class SpamBotChecker:
    """Advanced SpamBot status checker with full anti-spam logic"""
    
    def __init__(self, timeout: float = 5.0):
        self.timeout = timeout
        self.unlock_keywords = SPAMBOT_UNLOCK_KEYWORDS
        self.restriction_keywords = SPAMBOT_RESTRICTION_KEYWORDS
    
    async def send_start(self, client: Client) -> str:
        """
        Send /start to @SpamBot and analyze response
        
        Returns:
            "clear", "restricted", or "unknown"
        """
        try:
            await asyncio.wait_for(
                client.send_message("spambot", "/start"), 
                timeout=self.timeout
            )
            await asyncio.sleep(1)
            
            async for message in client.get_chat_history("spambot", limit=3):
                if message.from_user and message.from_user.username == "SpamBot":
                    if message.text:
                        text = message.text.lower()
                        if any(kw in text for kw in self.unlock_keywords):
                            return "clear"
                        if any(kw in text for kw in self.restriction_keywords):
                            return "restricted"
            return "unknown"
            
        except asyncio.TimeoutError:
            return "unknown"
        except Exception:
            return "unknown"
    
    async def double_start(self, client: Client) -> str:
        """
        Pre-DM Initialization: Send /start TWICE to @SpamBot
        Light spam flag clearing with 1-2 second delay
        
        Returns:
            "clear", "restricted", or "unknown"
        """
        status1 = await self.send_start(client)
        await asyncio.sleep(random.uniform(1.0, 2.0))
        status2 = await self.send_start(client)
        
        if status1 == "clear" or status2 == "clear":
            return "clear"
        if status1 == "restricted" or status2 == "restricted":
            return "restricted"
        return "unknown"
    
    async def milestone_check(self, client: Client) -> str:
        """
        Milestone-based check: called at specific intervals
        Every 10 messages, at 35th message, and at completion
        
        Returns:
            "clear", "restricted", or "unknown"
        """
        return await self.send_start(client)
    
    async def failure_restart(self, client: Client) -> str:
        """
        Failure-Triggered Restart: Called on 3+ consecutive failures
        Resets session and rechecks restriction status
        
        Returns:
            "clear", "restricted", or "unknown"
        """
        return await self.send_start(client)


class MessageSender:
    """Handles message sending with full anti-spam protection and rate limiting"""
    
    def __init__(self, settings: MassDMSettings):
        self.settings = settings
        self.error_classifier = ErrorClassifier()
        self.spambot_checker = SpamBotChecker(settings.spambot_timeout)
    
    async def initialize_session(self, client: Client) -> str:
        """
        Pre-DM initialization with double /start
        Clears light spam flags before starting MassDM
        
        Returns:
            "clear", "restricted", or "unknown"
        """
        return await self.spambot_checker.double_start(client)
    
    async def send_message(
        self, 
        client: Client, 
        user_id: int, 
        message: str,
        delay: Optional[float] = None
    ) -> Tuple[bool, str, Optional[int]]:
        """
        Send message to user with error handling
        
        Returns:
            (success, error_message, sent_message_id)
        """
        if delay is None:
            delay = random.uniform(self.settings.min_delay, self.settings.max_delay)
        
        try:
            await asyncio.sleep(delay)
            sent_msg = await client.send_message(user_id, message)
            return True, "", sent_msg.id
            
        except FloodWait as e:
            wait_time = e.value
            if wait_time > self.settings.floodwait_auto_stop_threshold:
                return False, f"FloodWait: {wait_time}s", None
            
            # Wait and retry
            await asyncio.sleep(wait_time + 1)
            try:
                sent_msg = await client.send_message(user_id, message)
                return True, "", sent_msg.id
            except Exception as e:
                return False, self.error_classifier.classify(e), None
                
        except Exception as e:
            return False, self.error_classifier.classify(e), None
    
    async def check_spambot_milestone(self, client: Client) -> str:
        """Check SpamBot status at milestone points"""
        return await self.spambot_checker.milestone_check(client)
    
    async def check_spambot_failure(self, client: Client) -> str:
        """Check SpamBot status on consecutive failures"""
        return await self.spambot_checker.failure_restart(client)


class ProgressTracker:
    """Tracks MassDM progress and statistics with anti-spam monitoring"""
    
    def __init__(self, total: int, settings: MassDMSettings):
        self.total = total
        self.success = 0
        self.failed = 0
        self.consecutive_failures = 0
        self.errors: List[Tuple[str, str]] = []  # (user_display, error)
        self.history: Dict[int, int] = {}  # chat_id -> message_id (for deletion)
        self.start_time = time.time()
        self.last_update = time.time()
        self.settings = settings
        
        # Anti-spam tracking
        self.spambot_status = "unknown"
        self.spambot_checked = False
        self.last_spambot_check = 0
        self.auto_stop_reason = None
    
    def add_success(self):
        """Add successful send"""
        self.success += 1
        self.consecutive_failures = 0
        self.last_update = time.time()
    
    def add_failure(self, user_display: str, error: str):
        """Add failed send"""
        self.failed += 1
        self.consecutive_failures += 1
        self.errors.append((user_display, error))
        self.last_update = time.time()
    
    def should_check_spambot_milestone(self) -> bool:
        """Check if we should do milestone SpamBot check"""
        current_total = self.success + self.failed
        
        # Check at 10, 35, 50, 100 messages
        milestones = self.settings.spambot_check_milestones
        return current_total in milestones
    
    def should_stop_on_consecutive_failures(self) -> bool:
        """Check if we should auto-stop on consecutive failures"""
        return self.consecutive_failures >= self.settings.consecutive_failures_auto_stop
    
    def should_stop_on_spambot_restriction(self) -> bool:
        """Check if we should auto-stop on SpamBot restriction"""
        if self.spambot_checked and "restricted" in self.spambot_status.lower():
            return self.consecutive_failures >= 3
        return False
    
    def update_spambot_status(self, status: str):
        """Update SpamBot status"""
        self.spambot_status = f"✅ clear" if status == "clear" else f"⚠️ restricted" if status == "restricted" else "❓ unknown"
        self.spambot_checked = True
        self.last_spambot_check = time.time()
    
    def get_progress(self) -> float:
        """Get progress percentage"""
        if self.total == 0:
            return 0.0
        return ((self.success + self.failed) / self.total) * 100
    
    def get_elapsed_time(self) -> float:
        """Get elapsed time in seconds"""
        return time.time() - self.start_time
    
    def get_stats(self) -> Dict[str, Any]:
        """Get current statistics"""
        return {
            "total": self.total,
            "success": self.success,
            "failed": self.failed,
            "consecutive_failures": self.consecutive_failures,
            "progress": self.get_progress(),
            "elapsed_time": self.get_elapsed_time(),
            "errors": self.errors[-10:],  # Last 10 errors
            "spambot_status": self.spambot_status,
            "spambot_checked": self.spambot_checked,
            "auto_stop_reason": self.auto_stop_reason
        }


class MassDMService:
    """Main MassDM service with full anti-spam protection and thread-safe operations"""
    
    def __init__(self, settings: MassDMSettings):
        self.settings = settings
        self.message_sender = MessageSender(settings)
        self.active_tasks: Dict[int, Dict[str, Any]] = {}  # user_id -> task_info
        self.massdm_settings: Dict[int, Dict[str, Any]] = {}  # user_id -> settings
        self.auto_stopped_tasks: Dict[str, Dict[str, Any]] = {}  # stop_key -> task_info
        self.completed_tasks: Dict[int, Dict[str, Any]] = {}  # user_id -> {"errors": [...], "timestamp": ...}
        self._lock = asyncio.Lock()
    
    async def start_massdm(
        self,
        user_id: int,
        client: Client,
        target_users: List[Dict[str, Any]],
        message: str,
        status_callback,
        stop_flag: Dict[str, bool]
    ) -> Dict[str, Any]:
        """
        Start MassDM process with full anti-spam protection
        
        Args:
            user_id: User ID
            client: Telegram client
            target_users: List of target users {user_id, username, first_name}
            message: Message to send
            status_callback: Callback for status updates
            stop_flag: Flag to stop process
        
        Returns:
            Final statistics
        """
        # Check concurrent limit
        async with self._lock:
            if len(self.active_tasks) >= self.settings.max_concurrent_massdm:
                raise RateLimitError("Maximum concurrent MassDM reached")
            
            if user_id in self.active_tasks:
                raise RateLimitError("User already has active MassDM")
        
        # Get user settings
        user_settings = await self._get_user_settings(user_id)
        
        # Pre-DM initialization
        if user_settings.get("auto_stop_on_high_risk", True):
            init_status = await self.message_sender.initialize_session(client)
            if init_status == "restricted":
                raise SpamBotRestrictedError("SpamBot restriction detected during initialization")
        
        # Initialize tracker
        tracker = ProgressTracker(len(target_users), self.settings)
        
        # Register task
        stop_key = f"{user_id}_{int(time.time())}"
        async with self._lock:
            self.active_tasks[user_id] = {
                "tracker": tracker,
                "stop_flag": stop_flag,
                "stop_key": stop_key,
                "start_time": time.time()
            }
        
        try:
            # Process each user
            for i, user in enumerate(target_users):
                if stop_flag[0]:
                    break
                
                target_id = user.get("user_id", 0)
                display_name = user.get("username", user.get("first_name", str(target_id)))
                
                # Send message
                success, error, sent_msg_id = await self.message_sender.send_message(
                    client, target_id, message
                )
                
                if success:
                    tracker.add_success()
                    # Store sent message ID for deletion feature
                    if sent_msg_id:
                        tracker.history[target_id] = sent_msg_id
                else:
                    tracker.add_failure(display_name, error)
                    
                    # Check consecutive failures
                    if tracker.should_stop_on_consecutive_failures():
                        # Try SpamBot failure restart
                        if user_settings.get("auto_stop_on_high_risk", True):
                            spambot_status = await self.message_sender.check_spambot_failure(client)
                            tracker.update_spambot_status(spambot_status)
                            
                            if tracker.should_stop_on_spambot_restriction():
                                tracker.auto_stop_reason = "🚫 SpamBot restriction confirmed"
                                break
                
                # Milestone SpamBot checks
                if tracker.should_check_spambot_milestone() and user_settings.get("auto_stop_on_high_risk", True):
                    spambot_status = await self.message_sender.check_spambot_milestone(client)
                    tracker.update_spambot_status(spambot_status)
                    
                    if spambot_status == "restricted":
                        tracker.auto_stop_reason = "🚫 SpamBot restriction detected at milestone"
                        break
                
                # Update status
                if i % 5 == 0:  # Update every 5 messages
                    await status_callback(tracker.get_stats())
                
                # Check for auto-stop
                if tracker.auto_stop_reason:
                    break
            
            # Final status update
            await status_callback(tracker.get_stats())
            
            # Save progress to database (thread-safe)
            await self._save_progress(user_id, tracker.get_stats())
            
            return tracker.get_stats()
            
        except SpamBotRestrictedError as e:
            tracker.auto_stop_reason = str(e)
            await status_callback(tracker.get_stats())
            await self._save_auto_stopped_task(stop_key, user_id, tracker.get_stats(), str(e))
            return tracker.get_stats()
            
        finally:
            # Save errors before cleanup
            if user_id in self.active_tasks:
                task = self.active_tasks[user_id]
                if "tracker" in task:
                    tracker = task["tracker"]
                    if tracker.errors:
                        async with self._lock:
                            self.completed_tasks[user_id] = {
                                "errors": tracker.errors.copy(),
                                "timestamp": time.time()
                            }
            
            # Cleanup
            async with self._lock:
                self.active_tasks.pop(user_id, None)
    
    async def stop_massdm(self, user_id: int) -> bool:
        """Stop MassDM for user"""
        async with self._lock:
            if user_id in self.active_tasks:
                task_info = self.active_tasks[user_id]
                task_info["stop_flag"][0] = True
                return True
            return False
    
    async def _get_user_settings(self, user_id: int) -> Dict[str, Any]:
        """Get user's MassDM settings (thread-safe)"""
        async with self._lock:
            # Try to get from database first
            try:
                from database_adapter import MassDMDatabaseAdapter
                db_settings = await MassDMDatabaseAdapter.get_setting(user_id)
                # Cache in memory
                self.massdm_settings[user_id] = db_settings
                return db_settings
            except Exception:
                # Fallback to default
                return self.massdm_settings.get(user_id, {
                    "auto_stop_on_high_risk": True,
                    "resume_after": 0
                })
    
    async def set_user_settings(self, user_id: int, settings: Dict[str, Any]):
        """Set user's MassDM settings (thread-safe)"""
        async with self._lock:
            self.massdm_settings[user_id] = settings
            # Save to database
            try:
                from database_adapter import MassDMDatabaseAdapter
                auto_stop = settings.get("auto_stop_on_high_risk", True)
                await MassDMDatabaseAdapter.save_setting(user_id, auto_stop)
            except Exception as e:
                logger.warning("Error saving settings to database: %s", e)
    
    async def _save_progress(self, user_id: int, stats: Dict[str, Any]):
        """Save progress to database (thread-safe)"""
        try:
            from database_adapter import MassDMDatabaseAdapter
            await MassDMDatabaseAdapter.save_progress(user_id, stats)
        except Exception as e:
            logger.warning("Error saving progress: %s", e)
    
    async def _save_auto_stopped_task(self, stop_key: str, user_id: int, stats: Dict[str, Any], reason: str):
        """Save auto-stopped task to database (thread-safe)"""
        try:
            from database_adapter import MassDMDatabaseAdapter
            await MassDMDatabaseAdapter.save_auto_stopped_task(stop_key, user_id, stats, reason)
        except Exception as e:
            logger.warning("Error saving auto-stopped task: %s", e)
    
    async def get_active_tasks(self) -> Dict[int, Dict[str, Any]]:
        """Get all active tasks (thread-safe)"""
        async with self._lock:
            return self.active_tasks.copy()
    
    async def get_user_task(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Get user's active task (thread-safe)"""
        async with self._lock:
            return self.active_tasks.get(user_id)
    
    async def get_completed_task_errors(self, user_id: int) -> Optional[List[Tuple[str, str]]]:
        """Get errors from completed MassDM task"""
        async with self._lock:
            completed = self.completed_tasks.get(user_id)
            if completed:
                return completed.get("errors")
        return None
    
    async def get_auto_stopped_tasks(self, user_id: int) -> List[Dict[str, Any]]:
        """Get user's auto-stopped tasks (thread-safe)"""
        try:
            from database import get_all_auto_stopped_tasks_for_user
            return await get_all_auto_stopped_tasks_for_user(user_id)
        except Exception as e:
            logger.warning("Error getting auto-stopped tasks: %s", e)
            return []