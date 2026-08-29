"""
vento_supervision.py
==================
Diagnostic supervision for critical Pyrogram Telegram update path.

This module provides non-invasive instrumentation to identify where Telegram updates
stop reaching Vento handlers. It does NOT modify Pyrogram's behavior, only observes it.

Phase: DIAGNOSTIC (no automatic recovery, no monkey-patching of execution model)

IMPORTANT: This module does NOT patch Session.network_worker, Session.ping_worker, or
Session.restart. Those are handled by fork_recovery.py and must remain untouched.
"""
import asyncio
import logging
import time
from typing import Dict, Set, Optional
from datetime import datetime, timedelta

log = logging.getLogger("vento.supervision")

# Installation marker to prevent double-patching
_installed = False


# Task Registry
class TaskRegistry:
    """Registry for supervised Pyrogram tasks with lifecycle tracking."""
    
    def __init__(self):
        self._tasks: Set[asyncio.Task] = set()
        self._task_info: Dict[int, Dict] = {}
        self._next_id = 0
    
    def add_task(self, task: asyncio.Task, name: str, category: str) -> int:
        """Add a task to the registry with metadata."""
        task_id = self._next_id
        self._next_id += 1
        
        self._tasks.add(task)
        self._task_info[task_id] = {
            "name": name,
            "category": category,
            "created_at": time.time(),
            "task": task
        }
        
        # Attach done callback
        task.add_done_callback(lambda t: self._on_task_done(t, task_id))
        
        return task_id
    
    def _on_task_done(self, task: asyncio.Task, task_id: int):
        """Handle task completion - logs and cleans up. Exception-safe."""
        info = self._task_info.get(task_id)
        if not info:
            return
        
        try:
            if task.cancelled():
                try:
                    log.warning(
                        "[VENTO_SUPERVISION] Task cancelled: %s (category: %s)",
                        info["name"], info["category"]
                    )
                except Exception:
                    pass  # Ignore logging failures
            else:
                exc = task.exception()
                if exc is not None:
                    try:
                        log.exception(
                            "[VENTO_SUPERVISION] Task failed: %s (category: %s)",
                            info["name"], info["category"],
                            exc_info=(type(exc), exc, exc.__traceback__)
                        )
                    except Exception:
                        pass  # Ignore logging failures
        finally:
            # Cleanup must happen regardless of logging failures
            self._tasks.discard(task)
            self._task_info.pop(task_id, None)
    
    def get_task_count(self, category: Optional[str] = None) -> int:
        """Get count of active tasks, optionally filtered by category."""
        if category is None:
            return len(self._tasks)
        
        return sum(1 for info in self._task_info.values() if info["category"] == category)
    
    def get_category_counts(self) -> Dict[str, int]:
        """Get count of active tasks per category."""
        counts: Dict[str, int] = {}
        for info in self._task_info.values():
            cat = info["category"]
            counts[cat] = counts.get(cat, 0) + 1
        return counts


# Global registry
_registry = TaskRegistry()


# Metrics Trackers
class Metrics:
    """In-memory counters for critical path metrics (cumulative totals)."""
    
    def __init__(self):
        self._counters: Dict[str, int] = {}
    
    def increment(self, name: str):
        """Increment a counter."""
        self._counters[name] = self._counters.get(name, 0) + 1
    
    def get_count(self, name: str) -> int:
        """Get current counter value (cumulative total)."""
        return self._counters.get(name, 0)
    
    def get_all_counts(self) -> Dict[str, int]:
        """Get all counter values (cumulative totals)."""
        return self._counters.copy()


_metrics = Metrics()


# Health State Tracking
class HealthState:
    """Track health state for queue stall detection with lifecycle protection."""
    
    def __init__(self):
        self._queue_depth_history: list = []
        self._execution_count_history: list = []
        self._max_history = 5
        self._stall_start_time: Optional[float] = None
        self._stall_logged = False
        self._startup_time: Optional[float] = None
        self._startup_grace_period = 60  # seconds
    
    def mark_startup(self):
        """Mark the start of the application (for grace period)."""
        self._startup_time = time.time()
    
    def record_snapshot(self, queue_depth: int, execution_count: int, is_stable: bool):
        """Record a snapshot of queue depth and execution count.
        
        Args:
            queue_depth: Current dispatcher queue depth
            execution_count: Handler executions in current period
            is_stable: Whether the system is in a stable running state
        """
        now = time.time()
        self._queue_depth_history.append((now, queue_depth))
        self._execution_count_history.append((now, execution_count))
        
        # Keep only recent history
        if len(self._queue_depth_history) > self._max_history:
            self._queue_depth_history.pop(0)
        if len(self._execution_count_history) > self._max_history:
            self._execution_count_history.pop(0)
        
        # Skip stall detection during startup grace period or unstable state
        if not is_stable:
            self._stall_start_time = None
            self._stall_logged = False
            return False
        
        if self._startup_time and (now - self._startup_time) < self._startup_grace_period:
            # Still in startup grace period
            return False
        
        # Check for stall condition
        if queue_depth > 0 and execution_count == 0:
            if self._stall_start_time is None:
                self._stall_start_time = now
            elif not self._stall_logged and (now - self._stall_start_time) >= 30:
                self._stall_logged = True
                return True  # Stall detected
        else:
            # Condition no longer true, reset stall detection
            self._stall_start_time = None
            self._stall_logged = False
        
        return False
    
    def reset_stall_detection(self):
        """Reset stall detection state."""
        self._stall_start_time = None
        self._stall_logged = False


_health_state = HealthState()


# Instrumentation Functions

def track_handle_packet():
    """Track that handle_packet was invoked."""
    _metrics.increment("handle_packet_invocations")


def track_handle_updates():
    """Track that handle_updates was invoked."""
    _metrics.increment("handle_updates_invocations")


def track_updates_processed():
    """Track that updates were successfully processed by handle_updates."""
    _metrics.increment("updates_processed")


def track_handler_failure():
    """Track that a handler execution failed."""
    _metrics.increment("handler_failures")


def track_critical_task_failure():
    """Track that a critical task failed."""
    _metrics.increment("critical_task_failures")


# Pyrogram Instrumentation (non-invasive wrappers)

def instrument_session_class():
    """Instrument Session class for monitoring.
    
    NOTE: Does NOT patch network_worker, ping_worker, or restart.
    Those are handled by fork_recovery.py and must remain untouched.
    
    This patches the class level so all Session instances inherit the instrumentation.
    """
    from pyrogram.session.session import Session
    
    original_handle_packet = Session.handle_packet
    
    async def instrumented_handle_packet(self, packet):
        track_handle_packet()
        # DIAGNOSTIC: Log packet type
        packet_type = type(packet).__name__
        log.debug("[DIAG] handle_packet called: packet_type=%s", packet_type)
        try:
            return await original_handle_packet(self, packet)
        except Exception as e:
            log.error("[VENTO_SUPERVISION] handle_packet failed: %s", e, exc_info=True)
            track_critical_task_failure()
            raise
    
    Session.handle_packet = instrumented_handle_packet


def instrument_client_class():
    """Instrument Client class for monitoring.
    
    This patches the class level so all Client instances inherit the instrumentation.
    """
    from pyrogram import Client
    
    original_handle_updates = Client.handle_updates
    
    async def instrumented_handle_updates(self, updates):
        track_handle_updates()
        # DIAGNOSTIC: Log updates batch info
        update_count = len(updates.updates) if hasattr(updates, 'updates') else 1
        log.debug("[DIAG] handle_updates called: update_count=%d", update_count)
        try:
            result = await original_handle_updates(self, updates)
            # Track successfully processed updates
            for _ in range(update_count):
                track_updates_processed()
            log.debug("[DIAG] handle_updates completed: update_count=%d", update_count)
            return result
        except Exception as e:
            log.error("[VENTO_SUPERVISION] handle_updates failed: %s", e, exc_info=True)
            track_critical_task_failure()
            raise
    
    Client.handle_updates = instrumented_handle_updates


def instrument_dispatcher(dispatcher):
    """Instrument Dispatcher for monitoring.
    
    NOTE: This wraps handler_worker to log failures and timing, but does NOT count individual
    handler executions because that requires instrumenting inside the worker loop which is
    complex and risky without modifying Pyrogram's internal logic.
    """
    import time
    
    original_handler_worker = dispatcher.handler_worker
    
    async def timed_handler_worker(lock):
        worker_id = id(lock)
        log.debug("[DIAG] handler_worker started: worker_id=%d", worker_id)
        start_time = time.time()
        try:
            await original_handler_worker(lock)
            duration_ms = (time.time() - start_time) * 1000
            log.debug("[DIAG] handler_worker completed: worker_id=%d duration_ms=%.2f", worker_id, duration_ms)
            if duration_ms > 10000:
                log.warning("[DIAG] HANDLER_HUNG_SUSPECT: worker_id=%d duration_ms=%.2f", worker_id, duration_ms)
            elif duration_ms > 2000:
                log.warning("[DIAG] HANDLER_SLOW: worker_id=%d duration_ms=%.2f", worker_id, duration_ms)
        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            log.error("[VENTO_SUPERVISION] handler_worker failed: %s worker_id=%d duration_ms=%.2f", e, worker_id, duration_ms, exc_info=True)
            track_handler_failure()
            raise
    
    dispatcher.handler_worker = timed_handler_worker


def instrument_initialize(client):
    """Instrument Client.initialize to monitor updates watchdog."""
    original_initialize = client.initialize
    
    async def instrumented_initialize():
        result = await original_initialize()
        
        # Monitor updates watchdog task
        if hasattr(client, 'updates_watchdog_task') and client.updates_watchdog_task:
            _registry.add_task(
                client.updates_watchdog_task,
                "updates_watchdog",
                "watchdog"
            )
        
        return result
    
    client.initialize = instrumented_initialize


# Health Snapshot Logging
_health_recovery_lock = asyncio.Lock()
_health_recovery_inflight = False
_health_last_updates = 0
_health_last_packets = 0

async def _recover_update_path(client, alive_workers: int, expected_workers: int, queue_depth: int):
    """Recover a dead Telegram update path without restarting the whole process."""
    global _health_recovery_inflight
    if _health_recovery_inflight:
        return
    async with _health_recovery_lock:
        if _health_recovery_inflight:
            return
        _health_recovery_inflight = True
        try:
            session = getattr(client, "session", None)
            connected_event = getattr(session, "is_connected", None) if session else None
            session_connected = bool(connected_event and connected_event.is_set())
            if not session_connected:
                request = getattr(session, "_request_recovery", None)
                if request:
                    log.warning("[VENTO_RECOVERY] Bot session disconnected; requesting supervised session recovery.")
                    request()
                return
            dispatcher = getattr(client, "dispatcher", None)
            if dispatcher is not None and hasattr(dispatcher, "start"):
                log.warning(
                    "[VENTO_RECOVERY] Restarting dispatcher workers alive=%d expected=%d queue=%d",
                    alive_workers, expected_workers, queue_depth,
                )
                result = dispatcher.start()
                if asyncio.iscoroutine(result):
                    await result
        except Exception:
            log.exception("[VENTO_RECOVERY] Update-path recovery failed.")
        finally:
            _health_recovery_inflight = False


async def health_snapshot_task(client):
    """Periodic health snapshot logging."""
    while True:
        try:
            await asyncio.sleep(60)  # Every 60 seconds
            
            # Collect metrics
            client_connected = getattr(client, 'is_connected', None)
            # pyrotgfork 2.2.24 Session has no `is_connected` event; fall back safely
            session_obj = getattr(client, 'session', None)
            if session_obj is None:
                session_connected = False
            elif hasattr(session_obj, 'is_connected'):
                ic = session_obj.is_connected
                session_connected = ic.is_set() if hasattr(ic, 'is_set') else bool(ic)
            else:
                session_connected = bool(getattr(session_obj, 'is_started', False))
            expected_workers = client.workers if hasattr(client, 'workers') else 0
            
            # Get dispatcher (may not exist during startup)
            dispatcher = getattr(client, 'dispatcher', None)
            
            # Calculate alive workers correctly
            alive_workers = 0
            if dispatcher and hasattr(dispatcher, 'handler_worker_tasks'):
                alive_workers = sum(
                    1 for task in dispatcher.handler_worker_tasks
                    if not task.done() and not task.cancelled()
                )
            
            queue_depth = dispatcher.updates_queue.qsize() if dispatcher else 0
            
            all_counts = _metrics.get_all_counts()
            task_failures = _metrics.get_count("critical_task_failures")

            global _health_last_updates, _health_last_packets
            current_updates = all_counts.get("updates_processed", 0)
            current_packets = all_counts.get("handle_packet_invocations", 0)
            recent_activity = current_updates > _health_last_updates
            _health_last_updates = current_updates
            _health_last_packets = current_packets
            
            # Determine if system is stable (for stall detection)
            is_stable = (
                client_connected is True and
                session_connected and
                alive_workers == expected_workers and
                alive_workers > 0
            )
            
            snapshot = (
                f"[VENTO_HEALTH]\n"
                f"client_connected={client_connected}\n"
                f"session_connected={session_connected}\n"
                f"handler_workers_alive={alive_workers}\n"
                f"handler_workers_expected={expected_workers}\n"
                f"dispatcher_queue_depth={queue_depth}\n"
                f"handle_packet_total={all_counts.get('handle_packet_invocations', 0)}\n"
                f"handle_updates_total={all_counts.get('handle_updates_invocations', 0)}\n"
                f"updates_processed_total={all_counts.get('updates_processed', 0)}\n"
                f"handler_failures_total={all_counts.get('handler_failures', 0)}\n"
                f"critical_task_failures={task_failures}"
            )
            
            log.info(snapshot)
            
            # Check for worker count drop
            if alive_workers < expected_workers:
                log.warning(
                    "[VENTO_SUPERVISION] Handler worker count dropped: %d/%d",
                    alive_workers, expected_workers
                )
                if alive_workers == 0 and expected_workers > 0:
                    await _recover_update_path(client, alive_workers, expected_workers, queue_depth)
            
            # Check for queue stall using activity deltas, not cumulative totals.
            is_stalled = _health_state.record_snapshot(
                queue_depth,
                1 if recent_activity else 0,  # 1 = activity, 0 = no activity
                is_stable
            )
            if is_stalled:
                log.warning(
                    "[VENTO_STALL] Dispatcher queue appears stalled\n"
                    f"queue_depth={queue_depth}\n"
                    f"alive_workers={alive_workers}\n"
                    f"client_connected={client_connected}\n"
                    f"session_connected={session_connected}\n"
                    f"handle_packet_total={all_counts.get('handle_packet_invocations', 0)}\n"
                    f"handle_updates_total={all_counts.get('handle_updates_invocations', 0)}"
                )
                await _recover_update_path(client, alive_workers, expected_workers, queue_depth)
            
        except Exception as e:
            log.error("[VENTO_SUPERVISION] Health snapshot failed: %s", e, exc_info=True)


# Initialization

def install_vento_supervision(client):
    """Install Vento supervision instrumentation. Idempotent - safe to call once.
    
    This patches Pyrogram classes at the class level so all instances inherit instrumentation.
    Must be called BEFORE Client.start() to ensure dispatcher workers are instrumented.
    """
    global _installed
    
    if _installed:
        log.warning("[VENTO_SUPERVISION] Already installed, skipping")
        return
    
    log.info("[VENTO_SUPERVISION] Installing diagnostic supervision")
    
    # Mark startup time for stall detection grace period
    _health_state.mark_startup()
    
    # Instrument Pyrogram classes (class-level patching)
    instrument_session_class()
    instrument_client_class()
    
    # Instrument Dispatcher (instance-level because Dispatcher is created per Client)
    if client.dispatcher:
        instrument_dispatcher(client.dispatcher)
    
    # Start health snapshot task
    if client.loop:
        health_task = client.loop.create_task(health_snapshot_task(client))
        _registry.add_task(health_task, "health_snapshot", "diagnostic")
    
    _installed = True
    log.info("[VENTO_SUPERVISION] Diagnostic supervision installed")
