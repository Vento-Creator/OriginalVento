"""
Dinamik Queue System - Server load asosida avtomatik navbat tashkil qiladi
"""
import asyncio
import time
import psutil
from typing import Dict, List, Optional, Callable, Any
from dataclasses import dataclass, field
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

import asyncio
from typing import Dict, Any

active_user_tasks: Dict[int, Dict[str, Any]] = {}  # {user_id: {task_type, target, progress, stop_flag, task_object, start_time}}
active_tasks_lock = asyncio.Lock()  # Protects active_user_tasks

# Integration with new modular systems
_massdm_service = None
_utag_service = None
_login_service = None

def set_massdm_service(service):
    """Set MassDM service for integration"""
    global _massdm_service
    _massdm_service = service

def set_utag_service(service):
    """Set UTAG service for integration"""
    global _utag_service
    _utag_service = service

def set_login_service(service):
    """Set Login service for integration"""
    global _login_service
    _login_service = service

async def sync_active_tasks_from_services():
    """Sync active tasks from new modular systems"""
    global active_user_tasks
    
    try:
        # Sync MassDM tasks
        if _massdm_service:
            massdm_tasks = await _massdm_service.get_active_tasks()
            for user_id, task_info in massdm_tasks.items():
                if "tracker" in task_info:
                    tracker = task_info["tracker"]
                    async with active_tasks_lock:
                        if user_id not in active_user_tasks:
                            active_user_tasks[user_id] = {
                                "task_type": "massdm",
                                "target": "Unknown",
                                "progress": tracker.get_progress(),
                                "stop_flag": task_info.get("stop_flag", [False]),
                                "task_object": None,
                                "start_time": task_info.get("start_time", time.time()),
                                "status": "running"
                            }
        
        # Sync UTAG tasks  
        if _utag_service:
            utag_tasks = await _utag_service.timer_manager.get_due_timers()
            for timer in utag_tasks:
                user_id = timer.user_id
                async with active_tasks_lock:
                    if user_id not in active_user_tasks:
                        active_user_tasks[user_id] = {
                            "task_type": "utag",
                            "target": f"Chat {timer.chat_id}",
                            "progress": 0,
                            "stop_flag": [False],
                            "task_object": None,
                            "start_time": timer.created_at,
                            "status": "running"
                        }
        
        logger.info(f"Synced {len(active_user_tasks)} active tasks from modular systems")
    except Exception as e:
        logger.error(f"Error syncing active tasks: {e}")

async def register_active_task(user_id: int, task_type: str, target: str, stop_flag: dict, task_object: asyncio.Task):
    """Register a new active task for admin monitoring"""
    async with active_tasks_lock:
        active_user_tasks[user_id] = {
            "task_type": task_type,
            "target": target,
            "progress": 0,
            "stop_flag": stop_flag,
            "task_object": task_object,
            "start_time": time.time(),
            "status": "running"
        }

async def update_task_progress(user_id: int, progress: int):
    """Update task progress"""
    async with active_tasks_lock:
        if user_id in active_user_tasks:
            active_user_tasks[user_id]["progress"] = progress

async def unregister_active_task(user_id: int):
    """Remove task from registry"""
    async with active_tasks_lock:
        active_user_tasks.pop(user_id, None)

async def get_all_active_tasks() -> Dict[int, Dict[str, Any]]:
    """Get snapshot of all active tasks"""
    async with active_tasks_lock:
        return active_user_tasks.copy()

async def terminate_user_task(user_id: int, ban_user: bool = False) -> bool:
    """Terminate user's active task and optionally ban them"""
    async with active_tasks_lock:
        if user_id not in active_user_tasks:
            return False
        
        task_info = active_user_tasks[user_id]
        
        if task_info.get("stop_flag"):
            task_info["stop_flag"][0] = True
        
        task_obj = task_info.get("task_object")
        if task_obj and not task_obj.done():
            task_obj.cancel()
        
        if ban_user:
            try:
                from database import add_violation
                await add_violation(user_id, reason="Admin tomonidan task bekor qilindi")
            except Exception as e:
                logger.error(f"Ban xatosi: {e}")
        
        active_user_tasks.pop(user_id, None)
        return True

LOAD_THRESHOLDS = {
    "cpu_low": 50,        # CPU < 50% - low load
    "cpu_high": 80,       # CPU > 80% - high load
    "memory_low": 70,     # Memory < 70% - low load  
    "memory_high": 90,    # Memory > 90% - high load
    "processes_low": 10,  # Active processes < 10 - low load
    "processes_high": 25, # Active processes > 25 - high load
}

@dataclass
class QueueItem:
    user_id: int
    operation_type: str  # "scraper", "massdm", "utag"
    data: Dict[str, Any]
    callback: Callable
    timestamp: float = field(default_factory=time.time)
    priority: int = 0  # Higher = more important
    status_msg: Optional[Any] = None  # Telegram message object for updates
    
    def __lt__(self, other):
        if self.priority != other.priority:
            return self.priority > other.priority
        return self.timestamp < other.timestamp

class LoadMonitor:
    def __init__(self):
        self.cpu_usage = 0.0
        self.memory_usage = 0.0
        self.active_processes = 0
        self.last_update = 0
        self.update_interval = 5  # Update every 5 seconds
    
    def update(self):
        """Load ma'lumotlarini yangilash"""
        now = time.time()
        if now - self.last_update < self.update_interval:
            return
        
        try:
            self.cpu_usage = psutil.cpu_percent(interval=0.5)
            self.memory_usage = psutil.virtual_memory().percent
            self.active_processes = len(psutil.Process().children(recursive=True))
            self.last_update = now
        except Exception as e:
            logger.error(f"Load monitor xatosi: {e}")
    
    def get_load_level(self) -> str:
        """Hozirgi load level ni qaytarish: 'low', 'medium', 'high'"""
        self.update()
        
        high_load_count = 0
        medium_load_count = 0
        
        if self.cpu_usage > LOAD_THRESHOLDS["cpu_high"]:
            high_load_count += 1
        elif self.cpu_usage > LOAD_THRESHOLDS["cpu_low"]:
            medium_load_count += 1
        
        if self.memory_usage > LOAD_THRESHOLDS["memory_high"]:
            high_load_count += 1
        elif self.memory_usage > LOAD_THRESHOLDS["memory_low"]:
            medium_load_count += 1
        
        if self.active_processes > LOAD_THRESHOLDS["processes_high"]:
            high_load_count += 1
        elif self.active_processes > LOAD_THRESHOLDS["processes_low"]:
            medium_load_count += 1
        
        if high_load_count >= 2:
            return "high"
        elif medium_load_count >= 2 or high_load_count >= 1:
            return "medium"
        else:
            return "low"
    
    def should_queue(self, operation_size: str = "medium") -> bool:
        """
        Berilgan operatsiyani queue ga qo'yish kerakmi?
        
        operation_size: "small", "medium", "large"
        - small: Oddiy operatsiyalar (masalan, adminlar scrape)
        - medium: O'rtacha operatsiyalar (masalan, oddiy scraper)
        - large: Katta operatsiyalar (masalan, 10000+ xabar scrape, massdm)
        """
        load_level = self.get_load_level()
        
        if load_level == "high":
            return True
        elif load_level == "medium":
            return operation_size in ("medium", "large")
        else:
            return False
    
    def get_status(self) -> Dict[str, Any]:
        """Load status ma'lumotlari"""
        self.update()
        return {
            "cpu": self.cpu_usage,
            "memory": self.memory_usage,
            "processes": self.active_processes,
            "level": self.get_load_level()
        }

class QueueManager:
    def __init__(self):
        self.queue: List[QueueItem] = []
        self.processing: List[QueueItem] = []
        self.completed: List[Dict] = []
        self.load_monitor = LoadMonitor()
        self.max_concurrent = 3  # Queue processor concurrent limit
        self.processor_task = None
        self._lock = asyncio.Lock()
    
    async def start(self):
        """Queue processor ni boshlash"""
        if self.processor_task is None:
            self.processor_task = asyncio.create_task(self._process_queue())
            logger.info("Queue processor boshlandi")
    
    async def stop(self):
        """Queue processor ni to'xtatish"""
        if self.processor_task:
            self.processor_task.cancel()
            try:
                await self.processor_task
            except asyncio.CancelledError:
                pass
            self.processor_task = None
            logger.info("Queue processor to'xtatildi")
    
    async def add_to_queue(
        self,
        user_id: int,
        operation_type: str,
        data: Dict[str, Any],
        callback: Callable,
        operation_size: str = "medium",
        priority: int = 0,
        status_msg: Optional[Any] = None
    ) -> bool:
        """
        Operatsiyani queue ga qo'shish
        
        Returns:
            True - queue ga qo'shildi
            False - darhol bajariladi (queue ga kerak emas)
        """
        async with self._lock:
            if not self.load_monitor.should_queue(operation_size):
                logger.info(f"User {user_id} operatsiyasi darhol bajariladi (load: {self.load_monitor.get_load_level()})")
                return False
            
            item = QueueItem(
                user_id=user_id,
                operation_type=operation_type,
                data=data,
                callback=callback,
                priority=priority,
                status_msg=status_msg
            )
            
            self.queue.append(item)
            self.queue.sort()  # Priority va timestamp bo'yicha sort
            
            position = len(self.queue)
            logger.info(f"User {user_id} operatsiyasi queue ga qo'shildi. Position: {position}")
            
            if status_msg:
                try:
                    await status_msg.edit_text(
                        f"⏳ **Siz navbatga qo'yildingiz**\n\n"
                        f"📊 Tartib raqamingiz: **{position}** / {position}\n"
                        f"⚙️ Server load: {self.load_monitor.get_load_level()}\n\n"
                        f"⏱️ Taxminiy kutish vaqti: ~{position * 2} daqiqa",
                        reply_markup=status_msg.reply_markup
                    )
                except Exception as e:
                    logger.error(f"Notification xatosi: {e}")
            
            return True
    
    async def _process_queue(self):
        """Background task - queue ni qayta ishlash"""
        async def run_callback_wrapper(qi: QueueItem):
            try:
                await qi.callback(qi.data)
            except Exception as ex:
                logger.error(f"Queue item callback xatosi: {ex}")
            finally:
                async with self._lock:
                    if qi in self.processing:
                        self.processing.remove(qi)
                    self.completed.append({
                        "user_id": qi.user_id,
                        "operation_type": qi.operation_type,
                        "completed_at": time.time()
                    })
                    
                    if len(self.completed) > 100:
                        self.completed = self.completed[-100:]
                    
                    await self._update_queue_positions()

        while True:
            try:
                await asyncio.sleep(2)  # Har 2 sekundda tekshirish
                
                async with self._lock:
                    if not self.queue or len(self.processing) >= self.max_concurrent:
                        continue
                    
                    if self.load_monitor.get_load_level() == "high":
                        continue
                    
                    item = self.queue.pop(0)
                    self.processing.append(item)
                    
                    await self._update_queue_positions()
                
                from task_supervisor import schedule_guarded
                schedule_guarded("Queue Callback", run_callback_wrapper(item))
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Queue processor xatosi: {e}")
                await asyncio.sleep(5)
    
    async def _update_queue_positions(self):
        """Barcha queue itemlar uchun position update"""
        for i, item in enumerate(self.queue):
            if item.status_msg:
                try:
                    total = len(self.queue)
                    position = i + 1
                    await item.status_msg.edit_text(
                        f"⏳ **Siz navbatda**\n\n"
                        f"📊 Tartib raqamingiz: **{position}** / {total}\n"
                        f"⚙️ Server load: {self.load_monitor.get_load_level()}\n\n"
                        f"⏱️ Taxminiy kutish vaqti: ~{position * 2} daqiqa",
                        reply_markup=item.status_msg.reply_markup
                    )
                except Exception as e:
                    logger.error(f"Position update xatosi: {e}")
    
    def get_queue_status(self) -> Dict[str, Any]:
        """Queue status ma'lumotlari"""
        return {
            "queue_length": len(self.queue),
            "processing_count": len(self.processing),
            "completed_count": len(self.completed),
            "load_status": self.load_monitor.get_status()
        }
    
    def get_user_position(self, user_id: int) -> Optional[int]:
        """Foydalanuvchining queue dagi position ini qaytarish"""
        for i, item in enumerate(self.queue):
            if item.user_id == user_id:
                return i + 1
        return None
    
    async def remove_from_queue(self, user_id: int) -> bool:
        """Foydalanuvchining queue dagi itemini o'chirish"""
        async with self._lock:
            for i, item in enumerate(self.queue):
                if item.user_id == user_id:
                    self.queue.pop(i)
                    await self._update_queue_positions()
                    return True
        return False

queue_manager = QueueManager()
