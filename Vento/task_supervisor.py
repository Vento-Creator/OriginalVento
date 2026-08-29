"""
task_supervisor.py
==================
Importable, circular-import-safe home of the background-task supervision mechanism that
``main.py`` defines as ``_spawn_guarded`` (commit a96f605).

Why this module exists
----------------------
``main.py`` supervises its own 3 long-running fire-and-forget tasks with ``_spawn_guarded``
(``asyncio.create_task`` + a strong reference in a module set + a done-callback that logs
failures). The plugin/system modules (utag, massdm, database_ui, updates, queue_manager) CANNOT
``from main import _spawn_guarded`` because ``main`` imports those modules -> circular import.

This module therefore provides the *same* mechanism importable by any module, so the same
"Task exception was never retrieved" / silent-subsystem-death class of bug that killed the
receiver is also eliminated for app-layer background tasks: every fire-and-forget task is
retained (no GC-while-pending) and any unhandled exception is logged with a full traceback
instead of being swallowed.

Two entry points (identical behaviour):
    * spawn_guarded(name, coroutine)    -> async, returns the Task (use with ``await``).
    * schedule_guarded(name, coroutine) -> sync, fire-and-forget drop-in for bare
      ``asyncio.create_task(...)``; retains the task and logs any failure on completion.
"""
import asyncio
import logging

logger = logging.getLogger("task_supervisor")

# Strong references to every supervised task so they are never garbage-collected (which would
# raise "Task was destroyed but it is pending!" and lose pending work) and so completion is
# always observable.
_background_tasks: set = set()


def _log_task_failure(future: asyncio.Task) -> None:
    if future.cancelled():
        logger.warning("[BACKGROUND] A background task was cancelled.")
        _background_tasks.discard(future)
        return
    exc = future.exception()
    if exc is not None:
        logger.exception(
            "[BACKGROUND] A background task died with an unhandled exception. "
            "The affected subsystem is no longer running: %r", exc,
            exc_info=(type(exc), exc, exc.__traceback__),
        )
    _background_tasks.discard(future)


def _register(name: str, coroutine) -> asyncio.Task:
    task = asyncio.create_task(coroutine)
    _background_tasks.add(task)
    task.add_done_callback(_log_task_failure)
    logger.info("Background task started: %s", name)
    return task


async def spawn_guarded(name: str, coroutine) -> asyncio.Task:
    """Async variant: use with ``await spawn_guarded(name, coro)`` (mirrors main.py's _spawn_guarded)."""
    return _register(name, coroutine)


def schedule_guarded(name: str, coroutine) -> asyncio.Task:
    """Sync fire-and-forget variant: drop-in replacement for ``asyncio.create_task(coro)``.

    Keeps a strong reference and a done-callback so the task is never silently lost and any
    failure is logged with a traceback.
    """
    return _register(name, coroutine)
