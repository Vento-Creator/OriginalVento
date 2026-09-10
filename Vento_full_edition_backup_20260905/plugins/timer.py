"""
Vento command timer
-------------------
User command:
    .taymer <seconds>
    .taymer <seconds> <message>
    .taymer <seconds> <message> [repeat_count]

Examples:
    .taymer 20
        -> shows a live 20..0 countdown, then removes it.

    .taymer 20 salom
        -> shows 20..0, sends "salom" as a separate new message at 0,
           then removes the countdown message.

    .taymer 20 salom 5
        -> repeats the countdown + separate "salom" message 5 times.

    .taymer 20
        -> one countdown only.

Countdown and final messages are sent through the user's linked account
(session_manager) whenever possible, because Telegram bots never receive
messages authored by other bots -- a final message like "/game@SomeBot"
only works if it comes from a human account. If no linked session exists
(or the account cannot post), the bot client is used as fallback.

    .cancel
        -> cancels the caller's active timer in the current chat.

This is intentionally separate from UTag's existing configuration timer.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Dict, Tuple

from pyrogram import Client, filters, ContinuePropagation
from pyrogram.errors import FloodWait

from error_handler import handle_errors
import session_manager

logger = logging.getLogger(__name__)

TIMER_COMMAND = "taymer"
CANCEL_COMMAND = "cancel"

# The first argument is the total countdown duration, in seconds.
MIN_SECONDS = 1
MAX_SECONDS = 86400
MAX_REPEAT = 1000

_tasks: Dict[Tuple[int, int], asyncio.Task] = {}
_lock = asyncio.Lock()


@dataclass(frozen=True)
class TimerSpec:
    user_id: int
    chat_id: int
    seconds: int
    text: str | None
    repeat_count: int | None  # None = infinite when text is supplied


def _parse_timer(text: str) -> TimerSpec | None:
    """Parse .taymer <seconds> [message] [repeat_count].

    The final token is treated as repeat_count only when it is an integer
    and there is at least one message token before it. This preserves
    `.taymer 20 5` as a 20-second countdown with no final message, rather
    than interpreting 5 as a repeat count.
    """
    parts = text.strip().split()
    if len(parts) < 2:
        return None

    try:
        seconds = int(parts[1])
    except (ValueError, TypeError):
        return None

    if not (MIN_SECONDS <= seconds <= MAX_SECONDS):
        return None

    message_parts = parts[2:]
    repeat_count: int | None = 1

    if message_parts and len(message_parts) >= 2:
        try:
            candidate = int(message_parts[-1])
        except ValueError:
            candidate = None
        if candidate is not None:
            if candidate < 1 or candidate > MAX_REPEAT:
                return None
            repeat_count = candidate
            message_parts = message_parts[:-1]
            # A repeat count only makes sense when a final message exists.
            if not message_parts:
                return None

    timer_text = " ".join(message_parts).strip() or None

    # Without a final message, a countdown is inherently one-shot.
    # With a message but no explicit count, repeat forever.
    if timer_text is not None and len(parts) >= 3:
        if repeat_count == 1 and not (len(parts) >= 4 and parts[-1].isdigit()):
            repeat_count = None

    return TimerSpec(
        user_id=0,
        chat_id=0,
        seconds=seconds,
        text=timer_text,
        repeat_count=repeat_count,
    )


def _countdown_text(seconds: int) -> str:
    return f"⏳ `{seconds}`"


async def _safe_edit(message, seconds: int) -> None:
    try:
        await message.edit_text(_countdown_text(seconds))
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        # Editing can fail if the message was manually deleted or Telegram
        # briefly rejects an update. The timer itself should not die silently.
        logger.warning("[TIMER] countdown edit failed: %s", exc)


async def _safe_delete(message) -> None:
    try:
        await message.delete()
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        # "Already deleted" and transient Telegram errors are non-fatal.
        logger.debug("[TIMER] countdown delete failed: %s", exc)


async def _resolve_sender(user_id: int, bot_client: Client) -> Client:
    """Return the client used to post countdown/final messages.

    Telegram bots NEVER receive messages authored by other bots, so a timer
    whose final message drives another bot's command (e.g. ``/game@SomeBot``)
    must be sent from the user's own linked account. Falls back to the bot
    client when the user has no linked session or it cannot be opened.
    """
    try:
        return await session_manager.get_user_client(user_id)
    except Exception as exc:
        logger.debug(
            "[TIMER] no user session for %s (%s); bot client will send",
            user_id,
            exc,
        )
        return bot_client


async def _send_final_message(
    sender: Client,
    bot_client: Client,
    chat_id: int,
    text: str,
) -> None:
    while True:
        try:
            await sender.send_message(chat_id, text)
            return
        except FloodWait as exc:
            wait = max(1, int(getattr(exc, "value", 1)))
            logger.warning(
                "[TIMER] FloodWait user_chat=%s wait=%ss",
                chat_id,
                wait,
            )
            await asyncio.sleep(wait)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            # The user account may be unable to post here (not a member,
            # muted, etc.). Fall back to the bot client once.
            logger.warning("[TIMER] final message send failed chat=%s: %s", chat_id, exc)
            if bot_client is not None and bot_client is not sender:
                try:
                    await bot_client.send_message(chat_id, text)
                except Exception as bot_exc:
                    logger.warning(
                        "[TIMER] bot fallback send also failed chat=%s: %s",
                        chat_id,
                        bot_exc,
                    )
            await asyncio.sleep(1)
            return


async def _send_countdown_start(sender: Client, bot_client: Client, spec: TimerSpec):
    """Send the initial countdown message, retrying through FloodWait.

    Returns the sent message, or None when neither the user account nor the
    bot client can post in the chat (the timer keeps running without a
    visible countdown instead of dying silently).
    """
    while True:
        try:
            return await sender.send_message(
                spec.chat_id,
                _countdown_text(spec.seconds),
            )
        except FloodWait as exc:
            wait = max(1, int(getattr(exc, "value", 1)))
            logger.warning(
                "[TIMER] countdown start FloodWait chat=%s wait=%ss",
                spec.chat_id,
                wait,
            )
            await asyncio.sleep(wait)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            if bot_client is not None and bot_client is not sender:
                try:
                    return await bot_client.send_message(
                        spec.chat_id,
                        _countdown_text(spec.seconds),
                    )
                except Exception as bot_exc:
                    logger.warning(
                        "[TIMER] countdown start failed chat=%s (user: %s / bot: %s)",
                        spec.chat_id,
                        exc,
                        bot_exc,
                    )
                    return None
            logger.warning("[TIMER] countdown start failed chat=%s: %s", spec.chat_id, exc)
            return None


async def _run_countdown(sender: Client, bot_client: Client, spec: TimerSpec) -> None:
    """Run one countdown cycle and optionally send its final message."""
    countdown_message = await _send_countdown_start(sender, bot_client, spec)

    try:
        if countdown_message is None:
            # No visible countdown is possible in this chat; still wait out
            # the full duration so the final message timing stays correct.
            await asyncio.sleep(spec.seconds)
        else:
            for remaining in range(spec.seconds - 1, -1, -1):
                await asyncio.sleep(1)
                await _safe_edit(countdown_message, remaining)

        if spec.text:
            # Deliberately send as a NEW message. Never edit the countdown
            # into the final text.
            await _send_final_message(sender, bot_client, spec.chat_id, spec.text)
    finally:
        if countdown_message is not None:
            await _safe_delete(countdown_message)


async def _remove_task(
    key: Tuple[int, int],
    task: asyncio.Task | None = None,
) -> None:
    async with _lock:
        current = _tasks.get(key)
        if task is None or current is task:
            _tasks.pop(key, None)


async def _timer_worker(client: Client, spec: TimerSpec) -> None:
    key = (spec.user_id, spec.chat_id)
    completed = 0

    try:
        while spec.repeat_count is None or completed < spec.repeat_count:
            # Re-resolve per cycle: the linked account can be re-linked or the
            # cached session cleaned up while a long timer is running.
            sender = await _resolve_sender(spec.user_id, client)
            await _run_countdown(sender, client, spec)
            completed += 1
    except asyncio.CancelledError:
        logger.info("[TIMER] cancelled user=%s chat=%s", spec.user_id, spec.chat_id)
        raise
    finally:
        await _remove_task(key, asyncio.current_task())


async def _start_timer(client: Client, message) -> str:
    parsed = _parse_timer(message.text or "")
    if parsed is None:
        return (
            "❌ Format noto'g'ri.\n\n"
            "Misol:\n"
            "`.taymer 20`\n"
            "`.taymer 20 salom`\n"
            "`.taymer 20 salom 5`\n\n"
            f"Vaqt: {MIN_SECONDS}-{MAX_SECONDS} sekund\n"
            f"Takrorlash: xabar berilsa 1-{MAX_REPEAT} marta yoki cheksiz.\n"
            "Faqat vaqt berilsa countdown bir marta ishlaydi."
        )

    user_id = message.from_user.id
    chat_id = message.chat.id
    key = (user_id, chat_id)

    spec = TimerSpec(
        user_id=user_id,
        chat_id=chat_id,
        seconds=parsed.seconds,
        text=parsed.text,
        repeat_count=parsed.repeat_count,
    )

    async with _lock:
        existing = _tasks.get(key)
        if existing and not existing.done():
            return "⚠️ Bu chatda sizda allaqachon faol taymer bor. Avval `.cancel` yozing."

        task = asyncio.create_task(_timer_worker(client, spec))
        _tasks[key] = task

    if spec.text is None:
        return f"⏱️ **Countdown:** `{spec.seconds}` sekund"

    count_text = "cheksiz" if spec.repeat_count is None else f"x{spec.repeat_count}"
    return (
        f"⏱️ **Taymer:** `{spec.seconds}` sekund\n"
        f"📨 Yakuniy xabar: `{spec.text}` ({count_text})\n"
        f"🛑 Bekor qilish: `.cancel`"
    )


async def _cancel_timer(message) -> str:
    key = (message.from_user.id, message.chat.id)
    async with _lock:
        task = _tasks.pop(key, None)

    if task and not task.done():
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        return "🛑 **Taymer bekor qilindi.**"

    return "⚠️ Bu chatda sizda faol taymer yo'q."


@Client.on_message(
    (filters.group | filters.private) & filters.text,
    group=-4,
)
@handle_errors("timer", "user_id", auto_retry=False)
async def command_timer_handler(client, message):
    """Handle the reserved .taymer and .cancel commands."""
    if not message.from_user or not message.chat:
        raise ContinuePropagation

    # Ignore messages authored by bots. Do NOT reject ``is_self`` here:
    # this application receives commands from the user's own Telegram account
    # in group chats, so ``.taymer`` / ``.cancel`` are legitimately self-authored.
    # Generated timer messages are not dot-commands and therefore cannot recurse.
    if getattr(message.from_user, "is_bot", False):
        raise ContinuePropagation

    text = (message.text or "").strip()
    # Accept both ``.`` and ``/`` prefixes. ``/`` is required for group delivery under
    # Telegram's Bot privacy mode (dot-prefixed text is never delivered to non-admin
    # bots), but ``.`` is kept for backward compatibility in private chats.
    if not (text.startswith(".") or text.startswith("/")):
        raise ContinuePropagation

    # Strip a trailing ``@botusername``: in groups Telegram delivers slash commands as
    # ``/taymer@MyBot`` (a user typing plain ``/taymer`` is sent to all bots this way),
    # and both forms must be accepted.
    command = text[1:].split(maxsplit=1)[0].lower() if text[1:].strip() else ""
    command = command.split("@", 1)[0]

    # Run the command inside a local try/except. The outer ``handle_errors`` decorator otherwise
    # swallows *every* runtime exception and turns a failed .taymer/.cancel into a silent no-op
    # (the user sees nothing, no error reply, nothing logged to their chat). By catching here we
    # guarantee the caller always gets a visible reply, and we keep ContinuePropagation so the
    # handler chain still behaves exactly as before on success.
    try:
        if command == TIMER_COMMAND:
            await message.reply_text(await _start_timer(client, message))
            raise ContinuePropagation
        if command == CANCEL_COMMAND:
            await message.reply_text(await _cancel_timer(message))
            raise ContinuePropagation
    except ContinuePropagation:
        raise
    except Exception as exc:
        logger.exception("[TIMER] command=%r failed: %s", command, exc)
        try:
            await message.reply_text(f"❌ Taymerda xatolik yuz berdi: {exc}")
        except Exception:
            logger.debug("[TIMER] could not deliver error reply", exc_info=True)
        raise ContinuePropagation

    raise ContinuePropagation


async def shutdown_timers() -> None:
    """Cancel all command timers during a clean application shutdown."""
    async with _lock:
        tasks = list(_tasks.values())
        _tasks.clear()

    for task in tasks:
        if not task.done():
            task.cancel()
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)
