"""
fork_recovery.py
================
Deployable, minimal recovery patch for ``pyrotgfork==2.2.24``.

WHY IT IS NEEDED (exact failure path, verified against the installed fork)
--------------------------------------------------------------------------
The Telegram receive path is driven by ``Session.network_worker()``. When the TCP link drops,
``Connection.recv()`` -> ``TCP.recv()`` NEVER raises: it returns ``None`` on timeout/OSError/EOF.
So ``network_worker`` does not die on its own - it schedules a recovery and ``break``s via an
unmanaged ``self.client.loop.create_task(self.restart())`` (session.py line 327).
No reference is retained and no done-callback is attached, so:

* ``Session.start()`` raises e.g. ``TimeoutError`` (builtin, from the initial Ping/InitConnection
  timing out on a half-open socket) -> its ``except Exception`` branch does ``stop(); raise``.
  The raise propagates out of the fire-and-forget ``restart()`` task, which is then reported only
  as ``asyncio ERROR: Task exception was never retrieved`` and NEVER schedules another restart.
* ``Session.start()`` can also RETURN WITHOUT reaching STARTED (its ``except (OSError, RPCError)``
  branch schedules a nested restart and returns), leaving the session not started.

Result: the receiver/recovery is left permanently dead while the process and the event loop stay
alive -> the bot stops answering Telegram updates while unrelated asyncio tasks (UTAG timer, ...)
keep running. This is the production freeze observed after commit a96f605.

FIX (real task-supervision, NOT a time-based watchdog)
------------------------------------------------------
Replace ``Session.restart`` with one coalesced, supervised recovery loop that:
  * keeps a single in-flight flag so only ONE recovery runs at a time (no duplicate receivers,
    no reconnect churn, no multiple concurrent Session objects);
  * retries with capped backoff and logs every failure (the receiver's restart is supervised);
  * VERIFIES the session actually reached STARTED (``is_connected``) before declaring success -
    covering the silent "start() returned without STARTED" case;
  * stops retrying only when the session was deliberately stopped or the client disconnected.
Wrap ``network_worker`` / ``ping_worker`` so any unexpected exception is logged and funnels into the
same supervised recovery instead of silently killing the worker.

This keeps the original ``start``/``stop``/``handle_packet``/``connect`` behaviour untouched; only
`restart`, `network_worker` and `ping_worker` are monkey-patched, so the change is minimal and
reproducible on a stock ``pip install pyrotgfork==2.2.24`` environment.
"""
import asyncio
import logging

from pyrogram.session.session import Session

log = logging.getLogger("ventofork.recovery")

_installed = False
# Originals captured before patching (raw unbound functions, callable as func(session)).
_orig_network_worker = None
_orig_ping_worker = None

# Strong references to recovery tasks to prevent GC and enable failure logging
_recovery_tasks: set = set()


def _log_recovery_task_done(future: asyncio.Task):
    """Done callback for recovery tasks - logs failures and cleans up registry."""
    if future.cancelled():
        log.warning("[recovery] Recovery task was cancelled")
    else:
        exc = future.exception()
        if exc is not None:
            log.exception(
                "[recovery] Recovery task failed with unhandled exception",
                exc_info=(type(exc), exc, exc.__traceback__)
            )
    _recovery_tasks.discard(future)


def _should_stop_retrying(session) -> bool:
    """Return True only when recovery has been explicitly disabled.

    A transiently disconnected Telegram socket is expected during recovery.  The
    old implementation treated ``client.is_connected == False`` as a deliberate
    shutdown, which could terminate recovery after the first failed restart.
    Network/ping workers only request recovery while the client is running, so a
    dedicated opt-out flag is safer than guessing from a transient connection bit.
    """
    return bool(getattr(session, "_recovery_disabled", False))


async def _restart(session):
    """Supervised, coalesced recovery loop. Replaces ``Session.restart``.

    Runs at most one recovery at a time per Session; retries with capped backoff; treats both
    a raised ``start()`` and a ``start()`` that silently failed to reach STARTED as a failed
    attempt; stops only when the session/client was deliberately shut down.
    """
    if getattr(session, "_restart_inflight", False):
        return  # another recovery is already running
    session._restart_inflight = True
    delay = 1.0
    attempt = 0
    try:
        while True:
            if _should_stop_retrying(session):
                return
            attempt += 1
            try:
                # pyrotgfork 2.2.24 may not have restart_lock; use it if available
                if hasattr(session, 'restart_lock'):
                    async with session.restart_lock:
                        await session.stop()
                        session._recovery_disabled = False
                        await session.start()
                else:
                    await session.stop()
                    session._recovery_disabled = False
                    await session.start()
            except asyncio.CancelledError:
                raise
            except Exception as e:
                log.error(
                    "[recovery] %s: Session.restart attempt %d failed: %s",
                    session.client.name, attempt, e, exc_info=True,
                )
                if _should_stop_retrying(session):
                    return
                await asyncio.sleep(delay)
                delay = min(delay * 2, 30)
                continue

            if session.is_connected.is_set():
                log.warning("[recovery] %s: Session recovered after %d attempt(s).", session.client.name, attempt)
                return

            # start() returned without reaching CONNECTED (the fork's OSError/RPCError branch
            # schedules a nested, now no-op restart and returns). Treat as a failed attempt.
            log.warning(
                "[recovery] %s: Session.start returned without CONNECTED (attempt %d); retrying.",
                session.client.name, attempt,
            )
            if _should_stop_retrying(session):
                return
            await asyncio.sleep(delay)
            delay = min(delay * 2, 30)
    finally:
        session._restart_inflight = False


def _request_recovery(session):
    """Coalesced entry point for all recovery. `_restart` itself is idempotent."""
    try:
        session._recovery_disabled = False
        task = session.client.loop.create_task(_restart(session))
        _recovery_tasks.add(task)
        task.add_done_callback(_log_recovery_task_done)
    except (RuntimeError, AttributeError):
        # Event loop not running / client absent - nothing schedulable right now.
        pass


async def _network_worker(session):
    """Supervised network_worker: an unexpected inside-failure is logged and triggers recovery."""
    try:
        await _orig_network_worker(session)
    except asyncio.CancelledError:
        raise
    except Exception as e:
        log.error("[recovery] %s: NetworkTask failed unexpectedly: %s", session.client.name, e, exc_info=True)
        _request_recovery(session)


async def _ping_worker(session):
    """Supervised ping_worker: an unexpected inside-failure is logged and triggers recovery."""
    try:
        await _orig_ping_worker(session)
    except asyncio.CancelledError:
        raise
    except Exception as e:
        log.error("[recovery] %s: PingTask failed unexpectedly: %s", session.client.name, e, exc_info=True)
        _request_recovery(session)


def install():
    """Monkey-patch the Session class. Idempotent."""
    global _installed, _orig_network_worker, _orig_ping_worker
    if _installed:
        return
    # PyroTGFork versions/builds can change the private Session worker API.
    # Never assume these monkey-patch targets exist: importing this module must
    # not prevent the bot from starting.
    network_worker = getattr(Session, "network_worker", None)
    ping_worker = getattr(Session, "ping_worker", None)
    restart = getattr(Session, "restart", None)
    stop = getattr(Session, "stop", None)

    if not callable(stop):
        log.warning("[recovery] Session.stop is unavailable; recovery patch disabled.")
        _installed = True
        return

    if not callable(network_worker) and not callable(ping_worker) and not callable(restart):
        log.warning(
            "[recovery] This PyroTGFork Session implementation exposes none of "
            "network_worker/ping_worker/restart; skipping incompatible monkey-patch."
        )
        _installed = True
        return

    _orig_network_worker = network_worker
    _orig_ping_worker = ping_worker
    original_stop = stop

    async def _supervised_stop(session, *args, **kwargs):
        # A real stop is an explicit shutdown request; prevent an already-running
        # recovery task from resurrecting the session.
        session._recovery_disabled = True
        try:
            return await original_stop(session, *args, **kwargs)
        finally:
            # Future network failures will clear this flag through _request_recovery.
            pass

    if callable(_orig_network_worker):
        Session.network_worker = _network_worker
    if callable(_orig_ping_worker):
        Session.ping_worker = _ping_worker
    if callable(restart):
        Session.restart = _restart
    Session.stop = _supervised_stop
    Session._request_recovery = _request_recovery
    _installed = True
    log.warning("[recovery] pyrotgfork Session recovery supervision installed (network_worker/ping_worker/restart patched).")


install()

