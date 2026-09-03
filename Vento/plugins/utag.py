"""

UTAG System - Original interface restored with new backend integration

Maintains all original features while using the improved utag_system backend

"""

from pyrogram import Client, filters, ContinuePropagation

from pyrogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardRemove

from pyrogram.errors import FloodWait, ChatWriteForbidden, UserBannedInChannel, PeerIdInvalid

from pyrogram.enums import ParseMode, MessageEntityType

import asyncio
import html
import os
import random
import logging

import time

import re

from config import user_states, stop_flags, pause_flags, SESSIONS_DIR, user_settings, user_custom_commands

from session_manager import get_user_client

from database import get_user_utag_commands, save_user_utag_command, add_utag_timer, get_utag_timer, get_user_utag_timers, update_utag_timer_last_sent, set_utag_timer_active, delete_utag_timer, get_all_active_utag_timers

from utag_system import utag_service
from utag_system.action_engine import ActionEngine
from utag_system.utag_helpers import (
    UTAG_SPEED_MIN,
    UTAG_SPEED_MAX,
    UTAG_SPEED_DEFAULT,
    SPEED_WARNING,
    get_utag_speed_seconds,
    format_speed_label,
    is_high_speed_risk,
    edit_and_auto_delete,
    send_completion_notification,
)



logger = logging.getLogger(__name__)

MAX_COMMAND_LENGTH = 15
MAX_PARALLEL_UTAG = utag_service.settings.max_parallel_utag
RESERVED_CORE_COMMANDS = {"taymer", "cancel"}
UTAG_COMMAND_TYPES = ("atag", "stop", "pause", "resume")


# Backward compatibility
TAG_MESSAGES = utag_service.message_selector.messages if hasattr(utag_service, 'message_selector') else {}

# Legacy process tracking for UI compatibility
active_utag_processes = {}
user_utag_processes = {}
utag_process_tasks = {}


def _is_group_chat(cq) -> bool:
    """Check if the callback query's message is in a group/supergroup chat."""
    chat = getattr(cq.message, "chat", None)
    if chat is None:
        return False
    return getattr(chat, "type", "") in ("group", "supergroup")


def _edit_cq(cq, text: str, buttons=None):
    """Edit a callback query message.

    Inline keyboards are only attached in private chats.
    In groups/supergroups the message is edited with plain text only.
    """
    if _is_group_chat(cq) or buttons is None:
        return cq.message.edit_text(text)
    return cq.message.edit_text(text, reply_markup=InlineKeyboardMarkup(buttons))


def format_member_mention(member: dict, plain: bool = False) -> str:
    """Format a member dict into a safe mention string.

    Rules:
    - username available -> @username
    - no username -> Telegram HTML mention using tg://user?id=
    - missing first_name -> "User"

    Args:
        member: Member dict with keys: type, username, id, first_name.
        plain: If True, return a plain-text name (no HTML) for fallback sends.
    """
    if not isinstance(member, dict):
        member = {}
    username = member.get("username")
    if username:
        return f"@{username}"
    user_id = member.get("id")
    first_name = str(member.get("first_name") or "User")
    if plain or user_id is None:
        return html.escape(first_name)
    return f'<a href="tg://user?id={user_id}">{html.escape(first_name)}</a>'


def _extract_tag_custom_emoji(text: str, entities, tag_message: str):

    """Return list of (utf16_offset_in_tag, utf16_length, custom_emoji_id) for CUSTOM_EMOJI

    entities that lie fully within the tag_message portion of `text`.



    Entity offsets are UTF-16 code units (Telegram convention). The text before the

    tag message (the ".command" token) is ASCII, so its Python index equals its

    UTF-16 offset, letting us map the tag location directly.

    """

    out = []

    if not tag_message or not entities:

        return out

    tag_start = text.find(tag_message)

    if tag_start < 0:

        return out

    tag_u16_len = len(tag_message.encode("utf-16-le")) // 2

    for ent in entities:

        try:

            if ent.type != MessageEntityType.CUSTOM_EMOJI:

                continue

            o, ln = ent.offset, ent.length

            if o >= tag_start and o + ln <= tag_start + tag_u16_len:

                out.append((o - tag_start, ln, ent.custom_emoji_id))

        except Exception:

            continue

    return out





def _build_tag_html(tag_text: str, emoji_info):

    """Build HTML for the tag message preserving Telegram Custom Emoji entities.



    emoji_info: list of (utf16_offset, utf16_length, custom_emoji_id) relative to

    tag_text (UTF-16 code units). Segments are sliced via utf-16-le bytes so that

    surrogate-pair characters (non-BMP emoji) are handled exactly per Telegram's

    UTF-16 convention.

    """

    if not emoji_info:

        return html.escape(tag_text)

    u16 = tag_text.encode("utf-16-le")

    parts = []

    cursor = 0

    for off, ln, doc_id in sorted(emoji_info):

        seg = u16[cursor * 2: off * 2].decode("utf-16-le")

        emoji_chars = u16[off * 2: (off + ln) * 2].decode("utf-16-le")

        if seg:

            parts.append(html.escape(seg))

        parts.append(f'<tg-emoji emoji-id="{doc_id}">{html.escape(emoji_chars)}</tg-emoji>')

        cursor = off + ln

    tail = u16[cursor * 2:].decode("utf-16-le")

    if tail:

        parts.append(html.escape(tail))

    return "".join(parts)





def _get_custom_cmds(user_id: int) -> dict:
    """Foydalanuvchi komandalarini olish (default: atag/stop)"""

    return user_custom_commands.get(user_id, {"atag": "atag", "stop": "stop"})





async def _load_custom_cmds(user_id: int) -> dict:
    """Load and normalize the user's UTAG commands.

    Older releases could leave a leading ``.`` or mixed case in the database.
    Telegram messages are parsed without the leading dot, so normalize here at
    the single read boundary. Reserved command names are never allowed to
    shadow ``.taymer`` / ``.cancel``.
    """
    if user_id not in user_custom_commands:
        user_custom_commands[user_id] = await get_user_utag_commands(user_id)

    cmds = user_custom_commands[user_id]
    defaults = {"atag": "atag", "stop": "stop", "pause": "pause", "resume": "resume"}

    for key, default in defaults.items():
        raw = cmds.get(key, default)
        value = str(raw if raw is not None else default).strip().lstrip(".").lower()
        if not value or value in RESERVED_CORE_COMMANDS:
            value = default
        cmds[key] = value

    return cmds


def _clear_command_change_state(user_id: int):

    """Komanda o'zgartirish holatini tozalash"""

    state = user_states.get(user_id)

    if state in ("waiting_for_new_atag_command", "waiting_for_new_stop_command"):

        user_states.pop(user_id, None)

    if isinstance(state, str) and (

        state.startswith("confirming_atag|") or state.startswith("confirming_stop|")

    ):

        user_states.pop(user_id, None)





def _get_user_active_processes(user_id: int) -> list:

    """Foydalanuvchining faol utag jarayonlari soni va ro'yxati"""

    return user_utag_processes.get(user_id, [])



def _count_user_processes(user_id: int) -> int:

    return len(_get_user_active_processes(user_id))



def _register_process(user_id: int, chat_id: int):

    """Yangi utag jarayonini ro'yxatdan o'tkazish"""

    if user_id not in user_utag_processes:

        user_utag_processes[user_id] = []

    if chat_id not in user_utag_processes[user_id]:

        user_utag_processes[user_id].append(chat_id)



def _unregister_process(user_id: int, chat_id: int):

    """Utag jarayonini ro'yxatdan o'chirish"""

    if user_id in user_utag_processes:

        user_utag_processes[user_id] = [c for c in user_utag_processes[user_id] if c != chat_id]

        if not user_utag_processes[user_id]:

            del user_utag_processes[user_id]



async def _stop_all_user_processes(user_id: int):
    """Foydalanuvchining barcha utag jarayonlarini to'xtatish"""
    processes = _get_user_active_processes(user_id)
    for chat_id in processes:
        process_key = f"{user_id}_{chat_id}"
        process = active_utag_processes.get(process_key)
        if process and process.get("stop_key"):
            stop_flags[process["stop_key"]] = True
        task = utag_process_tasks.pop(process_key, None)
        if task and not task.done():
            task.cancel()
        active_utag_processes.pop(process_key, None)
    user_utag_processes.pop(user_id, None)

    # Also deactivate all timers for this user so the global timer scheduler ignores them
    timers = await get_user_utag_timers(user_id)
    for timer in timers:
        if timer.get("is_active"):
            await set_utag_timer_active(timer["id"], False)


def cancel_utag_process(process_key: str):
    """Gracefully cancel a running utag process task (shutdown helper)."""
    task = utag_process_tasks.pop(process_key, None)
    if task and not task.done():
        task.cancel()


async def _list_active_processes(user_id: int) -> str:

    """Foydalanuvchining faol utag jarayonlari haqida matn qaytarish"""

    processes = _get_user_active_processes(user_id)

    if not processes:

        return "📭 Hozircha faol utag jarayonlari yo'q."

    

    lines = [f"📊 **Faol utag jarayonlari ({len(processes)}/{MAX_PARALLEL_UTAG}):**\n"]

    for i, chat_id in enumerate(processes, 1):

        process_key = f"{user_id}_{chat_id}"

        process = active_utag_processes.get(process_key)

        if process:

            tagged = process.get("tagged", 0)

            total = len(process.get("members", []))

            failed = process.get("failed", 0)

            lines.append(f"{i}. 🏷 {tagged}/{total} ta | ❌ {failed} ta | 🆔 `{chat_id}`")

        else:

            lines.append(f"{i}. 🆔 `{chat_id}` (tugagan)")

    return "\n".join(lines)





@Client.on_message(filters.text & filters.private & ~filters.command(["start", "cancel"]), group=-3)
async def private_group_command_warning_handler(client: Client, message: Message):
    """Notify user when a group-only command is sent in private chat"""
    if not message.from_user:
        raise ContinuePropagation
    
    user_id = message.from_user.id
    text = message.text.strip()
    
    if not (text.startswith(".") or text.startswith("/")):
        raise ContinuePropagation
        
    parts = text[1:].split()
    if not parts:
        raise ContinuePropagation
        
    cmd = parts[0].lstrip('.').lower().split("@", 1)[0]
    if cmd.endswith("+fun"):
        cmd = cmd[:-4]
        
    default_group_cmds = {"atag", "stop", "pause", "resume", "taymer", "game"}
    
    custom_cmds = await _load_custom_cmds(user_id)
    user_cmds = set(custom_cmds.values()) | default_group_cmds
    
    if cmd in user_cmds:
        await message.reply_text(
            "⚠️ **Ushbu buyruq faqat guruhlarda ishlashga mo'ljallangan!**\n\n"
            "Iltimos, ushbu buyruqni guruh chatida yuboring."
        )
        raise StopPropagation
        
    raise ContinuePropagation


@Client.on_message(filters.text & filters.group, group=-3)
async def custom_utag_command_handler(client: Client, message: Message):

    """Guruh ichida custom atag va stop komandalari"""
    if not message.from_user or not message.chat:
        logger.warning("[UTAG_DEBUG] STEP 1: RETURN - no from_user or no chat")
        raise ContinuePropagation
    user_id = message.from_user.id
    chat_id = message.chat.id
    
    text = message.text.strip()
    logger.debug(f"[UTAG_DEBUG] STEP 1: handler entered | user_id={user_id} chat_id={chat_id} text={message.text!r}")
    # Accept both ``.`` and ``/`` prefixes (``/`` required for group delivery under
    # Telegram Bot privacy mode; ``.`` kept for backward compatibility).
    if not (text.startswith(".") or text.startswith("/")):
        logger.debug(f"[UTAG_DEBUG] STEP 1: RETURN - text does not start with prefix: {text!r}")
        raise ContinuePropagation
    
    parts = text[1:].split()
    if not parts:
        logger.info("[UTAG_DEBUG] STEP 2: RETURN - no command parts")
        raise ContinuePropagation
    
    # Strip a trailing ``@botusername``: in groups Telegram delivers slash commands as
    # ``/atag@MyBot`` (a user typing plain ``/atag`` is sent to all bots this way),
    # and both forms must be accepted.
    cmd = parts[0].lstrip('.').lower().split("@", 1)[0]
    logger.info(f"[UTAG_DEBUG] STEP 2: parsed command cmd={cmd!r}")
    custom_cmds = await _load_custom_cmds(user_id)
    logger.info(f"[UTAG_DEBUG] STEP 3: loaded custom commands custom_cmds={custom_cmds!r}")
    atag_cmd = custom_cmds.get("atag", "atag")

    stop_cmd = custom_cmds.get("stop", "stop")

    pause_cmd = custom_cmds.get("pause", "pause")

    resume_cmd = custom_cmds.get("resume", "resume")

    

    use_random_messages = cmd.endswith("+fun")

    if use_random_messages:

        cmd = cmd[:-4]

    # Feature flag: faqat boshlash (atag) urinishi tekshiriladi
    if cmd == atag_cmd:
        from feature_flags import gate_feature
        if not await gate_feature(message, "utag"):
            raise ContinuePropagation

    parts = text[1:].split(maxsplit=1)

    tag_message = parts[1] if len(parts) > 1 else ""

    tag_emoji_info = _extract_tag_custom_emoji(message.text, message.entities, tag_message)

    

    if cmd == stop_cmd:
        logger.info(f"[UTAG_DEBUG] stop branch entered cmd={cmd!r}")
        process_key = f"{user_id}_{chat_id}"
        process = active_utag_processes.get(process_key)
        if not process:
            logger.info("[UTAG_DEBUG] stop: RETURN - no active process")
            await message.reply_text("⚠️ Hozircha hech qanday jarayon ishlamayapti.")
            raise ContinuePropagation
        
        if process["user_id"] != user_id:
            logger.info(f"[UTAG_DEBUG] stop: RETURN - process belongs to different user process_user={process['user_id']}")
            await message.reply_text("❌ Bu jarayonni faqat boshlagan foydalanuvchi to'xtatishi mumkin.")
            raise ContinuePropagation
        

        stop_key = process["stop_key"]

        # Deactivate timer for this chat so global scheduler ignores it

        timer = await get_utag_timer(user_id, chat_id)

        if timer and timer.get("is_active"):

            await set_utag_timer_active(timer["id"], False)

        stop_flags[stop_key] = True

        settings = user_settings.get(user_id, {})

        delete_timer = settings.get("utag_delete_timer", 2)

        

        try:
            _uc = await get_user_client(user_id)
            await edit_and_auto_delete(_uc, chat_id, message.id, "VentoTag faolsizlantirilmoqda...", delete_timer)
        except Exception:
            logger.exception("[UTAG_DEBUG] stop: exception while editing/deleting stop message")
            try:
                await message.delete()
            except:
                pass
        logger.info("[UTAG_DEBUG] stop: RETURN - stop processed")
        raise ContinuePropagation
    
    if cmd in (pause_cmd, resume_cmd):
        logger.info(f"[UTAG_DEBUG] pause/resume branch entered cmd={cmd!r}")
        process_key = f"{user_id}_{chat_id}"
        process = active_utag_processes.get(process_key)
        if not process:
            logger.info("[UTAG_DEBUG] pause/resume: RETURN - no active process")
            await message.reply_text("⚠️ Hozircha hech qanday jarayon ishlamayapti.")
            raise ContinuePropagation
            
        if process["user_id"] != user_id:
            logger.info(f"[UTAG_DEBUG] pause/resume: RETURN - process belongs to different user process_user={process['user_id']}")
            await message.reply_text("❌ Bu jarayonni faqat boshlagan foydalanuvchi boshqara oladi.")
            raise ContinuePropagation
            

        stop_key = process["stop_key"]

        settings = user_settings.get(user_id, {})

        delete_timer = settings.get("utag_delete_timer", 2)

        

        if cmd == pause_cmd:

            pause_flags[stop_key] = True

            msg_text = "VentoTag to'xtatib turildi (pause)..."

        else:

            pause_flags[stop_key] = False

            msg_text = "VentoTag davom ettirilmoqda (resume)..."

            

        try:
            _uc = await get_user_client(user_id)
            await edit_and_auto_delete(_uc, chat_id, message.id, msg_text, delete_timer)
        except Exception:
            logger.exception("[UTAG_DEBUG] pause/resume: exception while editing/deleting message")
            try:
                await message.delete()
            except:
                pass
        logger.info("[UTAG_DEBUG] pause/resume: RETURN - pause/resume processed")
        raise ContinuePropagation
    
    if cmd != atag_cmd:
        logger.info(f"[UTAG_DEBUG] STEP 4: RETURN - command not matched cmd={cmd!r} atag_cmd={atag_cmd!r}")
        raise ContinuePropagation
    

    logger.info(f"[UTAG_DEBUG] STEP 4: command matched cmd={cmd!r} atag_cmd={atag_cmd!r}")
    session_file = os.path.join(SESSIONS_DIR, f"user_{user_id}.session")
    logger.info(f"[UTAG_DEBUG] STEP 5: checking session file session_file={session_file!r}")
    if not os.path.exists(session_file):
        logger.info("[UTAG_DEBUG] STEP 5: RETURN - session file does not exist")
        await message.reply_text("❌ Avval akkauntingizni botda ulang!")
        raise ContinuePropagation
    logger.info("[UTAG_DEBUG] STEP 5: session file exists")
    
    active_count = _count_user_processes(user_id)
    if active_count >= MAX_PARALLEL_UTAG:
        logger.info(f"[UTAG_DEBUG] RETURN - parallel limit reached active_count={active_count} MAX_PARALLEL_UTAG={MAX_PARALLEL_UTAG}")
        await message.reply_text(
            f"⚠️ **Limit!** Siz bir vaqtda maksimal **{MAX_PARALLEL_UTAG} ta** guruhda utag "
            f"ishlatishingiz mumkin.\n\n"
            f"📊 Hozir {active_count} ta guruhda utag ishlamoqda.\n"
            "Avval birini tugating yoki barchasini to'xtating."
        )
        raise ContinuePropagation
    
    process_key = f"{user_id}_{chat_id}"
    if process_key in active_utag_processes:
        logger.info(f"[UTAG_DEBUG] RETURN - process already active process_key={process_key}")
        stop_cmd = (await _load_custom_cmds(user_id)).get("stop", "stop")
        await message.reply_text(
            f"⚠️ Siz allaqachon bu guruhda utag ishlamoqdasiz! To'xtatish uchun `.{stop_cmd}` yozing."
        )
        raise ContinuePropagation
    
    logger.info("[UTAG_DEBUG] STEP 6: before get_user_client()")
    try:
        user_client = await get_user_client(user_id)
    except Exception as e:
        logger.exception(f"[UTAG_DEBUG] STEP 7: get_user_client FAILED - RETURN | error={e}")
        await message.reply_text(f"❌ Akkauntga ulanishda xatolik: {e}")
        raise ContinuePropagation
    logger.info("[UTAG_DEBUG] STEP 7: after get_user_client() - user_client obtained")
    
    # Note: Peer resolution is attempted as optimization in actual API calls
    # No pre-check here to avoid blocking operations
    
    settings = user_settings.get(user_id, {})
    delete_timer = settings.get("utag_delete_timer", 2)
    
    try:
        await edit_and_auto_delete(user_client, chat_id, message.id, "VentoTag boshlandi...", delete_timer)
    except Exception:
        logger.exception("[UTAG_DEBUG] exception while editing/deleting start message")
        try:
            await message.delete()
        except:
            pass
    
    members = []
    logger.info("[UTAG_DEBUG] STEP 8: before get_chat_members()")
    
    # Try to resolve peer (non-blocking optimization)
    try:
        await user_client.resolve_peer(chat_id)
        logger.info(f"[UTAG_DEBUG] STEP 8.5: peer resolved for chat_id={chat_id}")
    except Exception as e:
        logger.debug(f"[UTAG_DEBUG] STEP 8.5: peer resolution skipped for chat_id={chat_id}: {e}")
        # Continue anyway - let get_chat_members handle it
    
    try:
        member_count = 0
        bots_count = 0
        no_username_count = 0
        sample_logged = False
        
        async for member in user_client.get_chat_members(chat_id):
            member_count += 1
            u = member.user
            
            # Log sample member structure (first 3 only)
            if not sample_logged and member_count <= 3 and u:
                logger.debug(
                    f"[UTAG_DIAG] Sample member {member_count} | "
                    f"id={u.id} | "
                    f"username={u.username} | "
                    f"first_name={u.first_name} | "
                    f"is_bot={u.is_bot}"
                )
                if member_count == 3:
                    sample_logged = True
            
            # Skip bots and invalid users
            if not u or u.is_bot or not u.first_name:
                if u and u.is_bot:
                    bots_count += 1
                continue
            
            # Store user data for mention generation
            if u.username:
                members.append({"type": "username", "username": u.username, "id": u.id, "first_name": u.first_name})
            else:
                no_username_count += 1
                members.append({"type": "html_mention", "id": u.id, "first_name": u.first_name})
        
        # Log detailed statistics
        logger.info(
            f"[UTAG_DIAG] Member statistics | "
            f"total={member_count} | "
            f"with_username={sum(1 for m in members if m['type'] == 'username')} | "
            f"without_username={no_username_count} | "
            f"bots={bots_count} | "
            f"chat_id={chat_id}"
        )
        
    except (KeyError, ValueError) as e:
        # Log the FULL traceback to see the actual root cause
        logger.error(f"[UTAG_ROOT_CAUSE] KeyError/ValueError in get_chat_members | chat_id={chat_id}")
        logger.exception(f"[UTAG_ROOT_CAUSE] Full traceback:")
        raise  # Re-raise to see the actual exception
    except Exception as e:
        # Log the FULL traceback to see the actual root cause
        logger.error(f"[UTAG_ROOT_CAUSE] Exception in get_chat_members | chat_id={chat_id}")
        logger.exception(f"[UTAG_ROOT_CAUSE] Full traceback:")
        raise  # Re-raise to see the actual exception
    
    logger.info(f"[UTAG_DEBUG] STEP 9: members loaded count={len(members)}")
    
    if not members:
        logger.info("[UTAG_DEBUG] STEP 9: RETURN - no members found")
        await message.reply_text(
            "⚠️ Guruhda tag qilinadigan a'zolar topilmadi.\n\n"
            "Guruhda faqat botlar bo'lishi mumkin yoki a'zolarning username'lari yo'q."
        )
        raise ContinuePropagation
    

    settings = user_settings.get(user_id, {})

    speed_seconds = get_utag_speed_seconds(settings)
    show_completion = settings.get("utag_completion_msg", True)
    typing_status = settings.get("utag_typing_status", True)

    stop_key = f"utag_{user_id}_{chat_id}"

    stop_flags[stop_key] = False

    

    active_utag_processes[process_key] = {
        "user_id": user_id,
        "chat_id": chat_id,
        "members": members,
        "tag_message": tag_message,

        "tag_emoji_info": tag_emoji_info,
        "use_random_messages": use_random_messages,
        "used_messages": [],
        "tagged": 0,
        "failed": 0,
        "last_message_id": None,
        "consecutive_deletions": 0,
        "settings": {
            "speed_seconds": speed_seconds,
            "show_completion": show_completion,
            "typing_status": typing_status,
        },
        "speed_seconds": speed_seconds,
        "status_msg": None,
        "stop_key": stop_key
    }
    _register_process(user_id, chat_id)
    
    logger.info(f"[UTAG_DEBUG] STEP 10: before asyncio.create_task(run_utag_process) process_key={process_key} members={len(members)}")
    from task_supervisor import schedule_guarded
    utag_process_tasks[process_key] = schedule_guarded("UTAG Process", run_utag_process(client, process_key, user_client))




async def run_utag_process(client: Client, process_key: str, user_client: Client):
    """Background task - utag jarayonini bajarish"""
    process = active_utag_processes.get(process_key)
    if not process:
        return
    
    user_id = process["user_id"]
    chat_id = process["chat_id"]
    members = process["members"]
    tag_message = process.get("tag_message", "")

    tag_emoji_info = process.get("tag_emoji_info") or []
    use_random_messages = process.get("use_random_messages", False)
    used_messages = process.get("used_messages", [])
    speed_seconds = process.get("speed_seconds", UTAG_SPEED_DEFAULT)
    show_completion = process["settings"]["show_completion"]
    stop_key = process["stop_key"]
    delete_timer = user_settings.get(user_id, {}).get("utag_delete_timer", 2)

    def _settings() -> dict:
        return user_settings.get(user_id, {})

    try:
        for member in members:
            if process_key not in active_utag_processes:
                break

            if stop_flags.get(stop_key):
                break

            while pause_flags.get(stop_key):
                if stop_flags.get(stop_key) or process_key not in active_utag_processes:
                    break
                await asyncio.sleep(1)

            if stop_flags.get(stop_key) or process_key not in active_utag_processes:
                break

            last_message_id = process.get("last_message_id")
            auto_stop_on_delete = user_settings.get(user_id, {}).get("utag_auto_stop_on_delete", True)
            if last_message_id and auto_stop_on_delete:
                try:
                    msg = await user_client.get_messages(chat_id, last_message_id)
                    if msg is None or msg.empty:
                        consecutive_deletions = process.get("consecutive_deletions", 0) + 1
                        if process_key in active_utag_processes:
                            active_utag_processes[process_key]["consecutive_deletions"] = consecutive_deletions
                            process["consecutive_deletions"] = consecutive_deletions
                        if consecutive_deletions >= 5:
                            logger.warning(
                                f"[UTAG] Stopped due to {consecutive_deletions} consecutive deleted messages"
                            )
                            break
                    else:
                        if process_key in active_utag_processes:
                            active_utag_processes[process_key]["consecutive_deletions"] = 0
                            process["consecutive_deletions"] = 0
                except KeyError as e:
                    logger.error(
                        f"[UTAG] Peer not resolved during message check | "
                        f"process_key={process_key} chat_id={chat_id} error={e}"
                    )
                    continue
                except ValueError as e:
                    logger.error(
                        f"[UTAG] Invalid peer during message check | "
                        f"process_key={process_key} chat_id={chat_id} error={e}"
                    )
                    continue
                except Exception as e:
                    logger.error(f"[UTAG] Error checking message deletion: {e}")

            mention = format_member_mention(member)
            plain_mention = format_member_mention(member, plain=True)

            if use_random_messages:
                available_messages = [msg_id for msg_id in TAG_MESSAGES.keys() if msg_id not in used_messages]
                if not available_messages:
                    used_messages.clear()
                    available_messages = list(TAG_MESSAGES.keys())
                random_msg_id = random.choice(available_messages)
                message_text = f"{mention} {TAG_MESSAGES[random_msg_id]}"
                plain_message_text = f"{plain_mention} {TAG_MESSAGES[random_msg_id]}"
                used_messages.append(random_msg_id)
                active_utag_processes[process_key]["used_messages"] = used_messages
            elif tag_message:
                if tag_emoji_info:
                    safe_tag_message = _build_tag_html(tag_message, tag_emoji_info)
                else:
                    safe_tag_message = (
                        html.escape(tag_message)
                        if "<" in tag_message or ">" in tag_message or "&" in tag_message
                        else tag_message
                    )
                message_text = f"{mention} {safe_tag_message}"
                plain_message_text = f"{plain_mention} {tag_message}"
            else:
                message_text = mention
                plain_message_text = plain_mention

            settings = _settings()
            await ActionEngine.apply_dispatch_suppression(user_client, chat_id, settings, settings)
            parse_mode = (
                ParseMode.HTML
                if "tg://user?id=" in message_text or "<tg-emoji" in message_text or "tg://emoji" in message_text
                else None
            )
            try:
                logger.info(f"[UTAG] Sending message with parse_mode={parse_mode}, text={message_text[:50]}...")
                if parse_mode is ParseMode.HTML:
                    try:
                        sent_msg = await user_client.send_message(chat_id, message_text, parse_mode=parse_mode)
                    except Exception as e:
                        if "tg://user?id=" in message_text:
                            logger.error(f"[UTAG] HTML message failed: {e}, trying plain text")
                            sent_msg = await user_client.send_message(chat_id, plain_message_text, parse_mode=None)
                        else:
                            logger.error(f"[UTAG] Premium emoji failed: {e}, trying without parse_mode")
                            sent_msg = await user_client.send_message(chat_id, message_text, parse_mode=None)
                else:
                    sent_msg = await user_client.send_message(chat_id, message_text, parse_mode=parse_mode)

                if process_key in active_utag_processes:
                    active_utag_processes[process_key]["tagged"] = process.get("tagged", 0) + 1
                    active_utag_processes[process_key]["consecutive_failures"] = 0
                    active_utag_processes[process_key]["last_message_id"] = sent_msg.id
                    process["tagged"] = active_utag_processes[process_key]["tagged"]
                    process["consecutive_failures"] = 0
                    process["last_message_id"] = sent_msg.id

            except FloodWait as e:
                await asyncio.sleep(e.value + 3)
                try:
                    retry_parse = (
                        ParseMode.HTML
                        if "tg://user?id=" in message_text or "<tg-emoji" in message_text or "tg://emoji" in message_text
                        else None
                    )
                    sent_msg = await user_client.send_message(chat_id, message_text, parse_mode=retry_parse)
                    if process_key in active_utag_processes:
                        active_utag_processes[process_key]["tagged"] = process.get("tagged", 0) + 1
                        active_utag_processes[process_key]["consecutive_failures"] = 0
                        active_utag_processes[process_key]["last_message_id"] = sent_msg.id
                        process["tagged"] = active_utag_processes[process_key]["tagged"]
                        process["consecutive_failures"] = 0
                        process["last_message_id"] = sent_msg.id
                except Exception:
                    if process_key in active_utag_processes:
                        active_utag_processes[process_key]["failed"] = process.get("failed", 0) + 1
                        active_utag_processes[process_key]["consecutive_failures"] = process.get("consecutive_failures", 0) + 1
                        process["failed"] = active_utag_processes[process_key]["failed"]
                        process["consecutive_failures"] = active_utag_processes[process_key]["consecutive_failures"]
            except (ChatWriteForbidden, UserBannedInChannel):
                logger.error(
                    f"[UTAG] Chat write forbidden or user banned | "
                    f"process_key={process_key} chat_id={chat_id}"
                )
                break
            except KeyError as e:
                logger.error(
                    f"[UTAG] Peer not resolved during send | "
                    f"process_key={process_key} chat_id={chat_id} error={e}"
                )
                if process_key in active_utag_processes:
                    active_utag_processes[process_key]["failed"] = process.get("failed", 0) + 1
                    active_utag_processes[process_key]["consecutive_failures"] = process.get("consecutive_failures", 0) + 1
                    process["failed"] = active_utag_processes[process_key]["failed"]
                    process["consecutive_failures"] = active_utag_processes[process_key]["consecutive_failures"]
            except ValueError as e:
                logger.error(
                    f"[UTAG] Invalid peer during send | "
                    f"process_key={process_key} chat_id={chat_id} error={e}"
                )
                if process_key in active_utag_processes:
                    active_utag_processes[process_key]["failed"] = process.get("failed", 0) + 1
                    active_utag_processes[process_key]["consecutive_failures"] = process.get("consecutive_failures", 0) + 1
                    process["failed"] = active_utag_processes[process_key]["failed"]
                    process["consecutive_failures"] = active_utag_processes[process_key]["consecutive_failures"]
            except Exception as e:
                if process_key in active_utag_processes:
                    active_utag_processes[process_key]["failed"] = process.get("failed", 0) + 1
                    active_utag_processes[process_key]["consecutive_failures"] = process.get("consecutive_failures", 0) + 1
                    process["failed"] = active_utag_processes[process_key]["failed"]
                    process["consecutive_failures"] = active_utag_processes[process_key]["consecutive_failures"]
                if process.get("consecutive_failures", 0) >= 5:
                    logger.warning(
                        f"[UTAG] Stopped due to {process['consecutive_failures']} consecutive failures: {e}"
                    )
                    break

            await asyncio.sleep(speed_seconds)

        tagged_count = process.get("tagged", 0)
        await send_completion_notification(
            user_client, chat_id, tagged_count, delete_timer, show_completion
        )
    finally:
        stop_flags.pop(stop_key, None)
        utag_process_tasks.pop(process_key, None)
        active_utag_processes.pop(process_key, None)
        _unregister_process(user_id, chat_id)




@Client.on_callback_query(filters.regex(r"^stop_utag_(\d+)$"))

async def stop_utag_callback(client: Client, callback_query: CallbackQuery):

    if not callback_query.from_user:

        return

    try:

        chat_id = int(callback_query.matches[0].group(1))

    except (ValueError, IndexError, AttributeError):

        await callback_query.answer("Xatolik", show_alert=True)

        return

    user_id = callback_query.from_user.id



    process_key = f"{user_id}_{chat_id}"

    process = active_utag_processes.get(process_key)

    if not process:

        await callback_query.answer("Jarayon topilmadi", show_alert=True)

        return



    if process["user_id"] != user_id:

        await callback_query.answer("Bu jarayonni faqat boshlagan foydalanuvchi to'xtatishi mumkin", show_alert=True)

        return



    stop_key = process["stop_key"]

    stop_flags[stop_key] = True



    # Deactivate timer for this chat so global scheduler ignores it

    timer = await get_utag_timer(user_id, chat_id)

    if timer and timer.get("is_active"):

        await set_utag_timer_active(timer["id"], False)

    await callback_query.answer("🛑 To'xtatilmoqda...")

    try:
        active_text = f"\n📊 Qolgan faol: {_count_user_processes(user_id) - 1}/{MAX_PARALLEL_UTAG}"
        await _edit_cq(
            callback_query,
            "🛑 Utag to'xtatilmoqda..." + active_text,
            [[InlineKeyboardButton("🏠 Bosh menyu", callback_data="menu_main")]]
        )
    except:
        pass


@Client.on_callback_query(filters.regex("^stop_process$"))

async def stop_process_callback(client: Client, callback_query: CallbackQuery):

    """Eski usuldagi stop tugmasi - faqat shu guruhdagi utagni to'xtatish"""

    if not callback_query.from_user:

        return

    user_id = callback_query.from_user.id



    

    message_text = callback_query.message.text if callback_query.message else ""

    target_chat = None

    

    active_processes = _get_user_active_processes(user_id)

    if not active_processes:

        await callback_query.answer("Faol jarayonlar yo'q!", show_alert=True)

        return

    

    if len(active_processes) == 1:

        chat_id = active_processes[0]

        process_key = f"{user_id}_{chat_id}"

        process = active_utag_processes.get(process_key)

        if process and process.get("stop_key"):

            stop_flags[process["stop_key"]] = True

            await callback_query.answer("🛑 To'xtatilmoqda...", show_alert=True)

            try:
                active_text = f"\n📊 Qolgan faol: {_count_user_processes(user_id) - 1}/{MAX_PARALLEL_UTAG}"
                await _edit_cq(
                    callback_query,
                    "🛑 Utag to'xtatilmoqda..." + active_text,
                    [[InlineKeyboardButton("🏠 Bosh menyu", callback_data="menu_main")]]
                )
            except:
                pass
        return
    

    await _stop_all_user_processes(user_id)

    await callback_query.answer("🛑 Barchasi to'xtatildi!", show_alert=True)

    try:
        await _edit_cq(
            callback_query,
            "🛑 Barcha utag jarayonlari to'xtatildi!",
            [[InlineKeyboardButton("🏠 Bosh menyu", callback_data="menu_main")]]
        )
    except:
        pass




@Client.on_callback_query(filters.regex("^menu_utag$"))
async def utag_start(client: Client, callback_query: CallbackQuery):
    if not callback_query.from_user:
        return
    user_id = callback_query.from_user.id

    if _is_group_chat(callback_query):
        await callback_query.answer()
        return

    try:
        del_msg = await callback_query.message.reply_text("⏳", reply_markup=ReplyKeyboardRemove())
        await del_msg.delete()
    except:
        pass


    session_file = os.path.join(SESSIONS_DIR, f"user_{user_id}.session")

    if not os.path.exists(session_file):

        await callback_query.answer("Oldin akkauntingizni ulang! (Akkaunt ulash)", show_alert=True)

        return



    active_count = _count_user_processes(user_id)

    active_processes = _get_user_active_processes(user_id)



    if active_count > 0:

        active_list = await _list_active_processes(user_id)

        

        buttons = []

        buttons.append([InlineKeyboardButton("🛑 Barchasini stop qilish", callback_data="utag_stop_all")])

        buttons.append([InlineKeyboardButton("🔄 Holatni yangilash", callback_data="menu_utag")])

        buttons.append([InlineKeyboardButton("🔙 Bosh menyu", callback_data="menu_main")])

        

        await _edit_cq(
            callback_query,
            f"🏷 **Ommaviy Belgilash (Utag)**\n\n"
            f"⚠️ **Boshqa guruh(lar)da allaqachon utag boshlangan.**\n\n"
            f"{active_list}\n\n"
            f"**Nima qilamiz?**",
            buttons
        )
        await callback_query.answer()

        return



    await _show_utag_main_menu(callback_query, user_id)



async def _show_utag_main_menu(cq: CallbackQuery, user_id: int):

    """Utag asosiy menyusini ko'rsatish"""

    settings = user_settings.get(user_id, {})

    custom_cmds = await _load_custom_cmds(user_id)

    atag_cmd = custom_cmds.get("atag", "atag")

    stop_cmd = custom_cmds.get("stop", "stop")

    speed_seconds = get_utag_speed_seconds(settings)
    show_completion = settings.get("utag_completion_msg", True)
    typing_status = settings.get("utag_typing_status", True)

    completion_label = "✅ Yoqilgan" if show_completion else "❌ O'chirilgan"
    typing_label = "✅ Yoqilgan" if typing_status else "❌ O'chirilgan"

    await _edit_cq(
        cq,
        "🏷 **Ommaviy Belgilash (Utag)**\n\n"
        f"🆕 **Yangi usul:** Guruh ichida `.{atag_cmd}` komandasini yozing va tagging boshlanadi.\n"
        f"To'xtatish uchun `.{stop_cmd}` yozing.\n\n"
        "💡 **Bir nechta guruhda bir vaqtda ishlatishingiz mumkin!**\n"
        f"📊 Maksimal: **{MAX_PARALLEL_UTAG} ta** parallel guruh\n\n"
        f"⚙️ Sozlamalar: {format_speed_label(speed_seconds)} tezlik | "
        f"Yakun habari: {completion_label} | Typing: {typing_label}",
        [
            [InlineKeyboardButton("⚙️ Sozlamalar", callback_data="utag_settings")],
            [InlineKeyboardButton("❌ Bekor qilish", callback_data="menu_main")],
        ]
    )
    await cq.answer()





@Client.on_callback_query(filters.regex("^utag_stop_all$"))

async def utag_stop_all_callback(client: Client, cq: CallbackQuery):

    if not cq.from_user:

        return

    user_id = cq.from_user.id

    active_count = _count_user_processes(user_id)

    

    if active_count == 0:

        await cq.answer("Faol jarayonlar yo'q!", show_alert=True)

        return

    

    await _edit_cq(
        cq,
        f"⚠️ **Ishonchingiz komilmi?**\n\n"
        f"Sizning **{active_count} ta** guruhdagi utag jarayonlaringizni to'xtatmoqchisiz.\n\n"
        "Bu amalni ortga qaytarib bo'lmaydi!",
        [
            [
                InlineKeyboardButton("✅ Ha, to'xtatish", callback_data="utag_stop_all_confirm"),
                InlineKeyboardButton("❌ Yo'q, orqaga", callback_data="menu_utag"),
            ]
        ]
    )
    await cq.answer()



@Client.on_callback_query(filters.regex("^utag_stop_all_confirm$"))

async def utag_stop_all_confirm_callback(client: Client, cq: CallbackQuery):

    if not cq.from_user:

        return

    user_id = cq.from_user.id

    active_processes = _get_user_active_processes(user_id)

    count = len(active_processes)

    

    if count == 0:

        await cq.answer("Faol jarayonlar yo'q!", show_alert=True)

        return

    

    await _stop_all_user_processes(user_id)

    

    await _edit_cq(
        cq,
        f"🛑 **Barcha utag jarayonlari to'xtatildi!**\n\n"
        f"🗑 {count} ta guruhdagi utag yakunlandi.\n\n"
        f"Qaytadan boshlash uchun menyudan foydalaning.",
        [[InlineKeyboardButton("🏠 Bosh menyu", callback_data="menu_main")]]
    )
    await cq.answer("Barchasi to'xtatildi!", show_alert=True)





@Client.on_callback_query(filters.regex("^utag_settings$"))

async def utag_settings_callback(client: Client, cq: CallbackQuery):

    if not cq.from_user:

        return

    user_id = cq.from_user.id

    settings = user_settings.get(user_id, {})

    custom_cmds = await _load_custom_cmds(user_id)

    speed_seconds = get_utag_speed_seconds(settings)
    show_completion = settings.get("utag_completion_msg", True)
    typing_status = settings.get("utag_typing_status", True)
    delete_timer = settings.get("utag_delete_timer", 2)
    auto_stop_on_delete = settings.get("utag_auto_stop_on_delete", True)

    completion_label = "✅ Yoqilgan" if show_completion else "❌ O'chirilgan"
    typing_label = "✅ Yoqilgan" if typing_status else "❌ O'chirilgan"
    auto_stop_label = "✅ Yoqilgan" if auto_stop_on_delete else "❌ O'chirilgan"
    if delete_timer == 0:
        timer_label = "⏱️ Hech qachon"
    else:
        timer_label = f"⏱️ {delete_timer} sekund"

    atag_cmd = custom_cmds.get("atag", "atag")
    stop_cmd = custom_cmds.get("stop", "stop")

    speed_warning = f"\n\n{SPEED_WARNING}" if is_high_speed_risk(speed_seconds) else ""

    await _edit_cq(
        cq,
        "⚙️ **Utag Sozlamalari**\n\n"
        f"🚀 Tezlik: {format_speed_label(speed_seconds)}\n"
        f"📢 Yakunlangan habari: {completion_label}\n"
        f"⌨️ Typing status: {typing_label}\n"
        f"⏱️ Xabar o'chish taymeri: {timer_label}\n"
        f"🗑 O'chishda avtostop: {auto_stop_label}\n"
        f"🔤 Boshlash komandasi: .{atag_cmd}\n"
        f"🛑 To'xtatish komandasi: .{stop_cmd}"
        f"{speed_warning}\n\n"
        "Sozlamoqchi bo'lgan parametrni tanlang:",
        [
            [
                InlineKeyboardButton("🚀 Tezlik", callback_data="utag_speed"),
                InlineKeyboardButton("📢 Yakun habari", callback_data="utag_completion")
            ],
            [
                InlineKeyboardButton("⌨️ Typing status", callback_data="utag_typing"),
                InlineKeyboardButton("⏱️ O'chish taymeri", callback_data="utag_delete_timer")
            ],
            [
                InlineKeyboardButton("🗑 O'chishda avtostop", callback_data="utag_auto_stop_delete"),
                InlineKeyboardButton("🔤 Komandalar", callback_data="utag_commands")
            ],
            [
                InlineKeyboardButton("⏰ Taymerli habar", callback_data="utag_timer_menu"),
                InlineKeyboardButton("⚙️ Action Sozlamalari", callback_data="action_status_menu")
            ],
            [
                InlineKeyboardButton("🔙 Orqaga", callback_data="menu_utag")
            ]
        ]
    )
    await cq.answer()





@Client.on_callback_query(filters.regex("^utag_commands$"))

async def utag_commands_callback(client: Client, cq: CallbackQuery):

    if not cq.from_user:

        return

    user_id = cq.from_user.id

    _clear_command_change_state(user_id)

    custom_cmds = await _load_custom_cmds(user_id)

    atag_cmd = custom_cmds.get("atag", "atag")

    stop_cmd = custom_cmds.get("stop", "stop")



    await _edit_cq(
        cq,
        "🔤 **Komandalarni O'zgartirish**\n\n"
        f"🚀 Boshlash komandasi: .{atag_cmd}\n"
        f"🛑 To'xtatish komandasi: .{stop_cmd}\n"
        f"⏸️ Pauza komandasi: .{custom_cmds.get('pause', 'pause')}\n"
        f"▶️ Davom etish komandasi: .{custom_cmds.get('resume', 'resume')}\n\n"
        "Qaysi komandani o'zgartirmoqchisiz?",
        [
            [
                InlineKeyboardButton("🚀 Boshlash", callback_data="utag_change_atag"),
                InlineKeyboardButton("🛑 To'xtatish", callback_data="utag_change_stop")
            ],
            [
                InlineKeyboardButton("⏸️ Pauza", callback_data="utag_change_pause"),
                InlineKeyboardButton("▶️ Davom etish", callback_data="utag_change_resume")
            ],
            [InlineKeyboardButton("🔙 Orqaga", callback_data="utag_settings")]
        ]
    )
    await cq.answer()





@Client.on_callback_query(filters.regex("^utag_change_atag$"))

async def utag_change_atag_callback(client: Client, cq: CallbackQuery):

    if not cq.from_user:

        return

    user_id = cq.from_user.id

    custom_cmds = await _load_custom_cmds(user_id)

    current_cmd = custom_cmds.get("atag", "atag")



    await _edit_cq(
        cq,
        f"🚀 **Boshlash Komandasini O'zgartirish**\n\n"
        f"Sizning joriy komandangiz: .{current_cmd}\n\n"
        "Uni almashtirmoqchimisiz?",
        [
            [
                InlineKeyboardButton("✅ Ha!", callback_data="utag_confirm_change_atag"),
                InlineKeyboardButton("❌ Yo'q", callback_data="utag_commands")
            ]
        ]
    )
    await cq.answer()





@Client.on_callback_query(filters.regex("^utag_change_stop$"))

async def utag_change_stop_callback(client: Client, cq: CallbackQuery):

    if not cq.from_user:

        return

    user_id = cq.from_user.id

    custom_cmds = await _load_custom_cmds(user_id)

    current_cmd = custom_cmds.get("stop", "stop")



    await _edit_cq(
        cq,
        f"🛑 **To'xtatish Komandasini O'zgartirish**\n\n"
        f"Sizning joriy komandangiz: .{current_cmd}\n\n"
        "Uni almashtirmoqchimisiz?",
        [
            [
                InlineKeyboardButton("✅ Ha!", callback_data="utag_confirm_change_stop"),
                InlineKeyboardButton("❌ Yo'q", callback_data="utag_commands")
            ]
        ]
    )
    await cq.answer()





@Client.on_callback_query(filters.regex("^utag_confirm_change_atag$"))

async def utag_confirm_change_atag_callback(client: Client, cq: CallbackQuery):

    if not cq.from_user:

        return

    user_id = cq.from_user.id

    user_states[user_id] = "waiting_for_new_atag_command"



    await _edit_cq(
        cq,
        "✍️ **Yangi komandani yuboring**\n\n"
        "⚠️ **Qoidalar:**\n"
        "• Maksimal uzunlik: 15 ta harf (nuqtadan tashqari)\n"
        "• Ruscha harflar taqiqlanadi\n"
        "• Faqat lotin harflari, raqamlar va _ belgisi\n"
        "• Nuqta bilan boshlash shart emas (bot ozi qo'yadi)",
        [[InlineKeyboardButton("❌ Bekor qilish", callback_data="utag_commands")]]
    )
    await cq.answer()


@Client.on_callback_query(filters.regex("^utag_confirm_change_stop$"))
async def utag_confirm_change_stop_callback(client: Client, cq: CallbackQuery):
    if not cq.from_user:
        return
    user_id = cq.from_user.id
    user_states[user_id] = "waiting_for_new_stop_command"

    await _edit_cq(
        cq,
        "✍️ **Yangi komandani yuboring**\n\n"
        "⚠️ **Qoidalar:**\n"
        "• Maksimal uzunlik: 15 ta harf (nuqtadan tashqari)\n"
        "• Ruscha harflar taqiqlanadi\n"
        "• Faqat lotin harflari, raqamlar va _ belgisi\n"
        "• Nuqta bilan boshlash shart emas (bot ozi qo'yadi)",
        [[InlineKeyboardButton("❌ Bekor qilish", callback_data="utag_commands")]]
    )
    await cq.answer()







@Client.on_callback_query(filters.regex("^utag_change_pause$"))

async def utag_change_pause_callback(client: Client, cq: CallbackQuery):

    if not cq.from_user: return

    user_id = cq.from_user.id

    custom_cmds = await _load_custom_cmds(user_id)

    current_cmd = custom_cmds.get("pause", "pause")

    await _edit_cq(
        cq,
        f"⏸️ **Pauza Komandasini O'zgartirish**\n\nSizning joriy komandangiz: .{current_cmd}\n\nUni almashtirmoqchimisiz?",
        [[InlineKeyboardButton("✅ Ha!", callback_data="utag_confirm_change_pause"), InlineKeyboardButton("❌ Yo'q", callback_data="utag_commands")]]
    )
    await cq.answer()



@Client.on_callback_query(filters.regex("^utag_confirm_change_pause$"))

async def utag_confirm_change_pause_callback(client: Client, cq: CallbackQuery):

    if not cq.from_user: return

    user_id = cq.from_user.id

    user_states[user_id] = "waiting_for_new_pause_command"

    await _edit_cq(
        cq,
        "✍️ **Yangi komandani yuboring**\n\n⚠️ **Qoidalar:**\n• Maksimal uzunlik: 15 ta harf (nuqtadan tashqari)\n• Ruscha harflar taqiqlanadi\n• Faqat lotin harflari, raqamlar va _ belgisi\n• Nuqta bilan boshlash shart emas (bot ozi qo'yadi)",
        [[InlineKeyboardButton("❌ Bekor qilish", callback_data="utag_commands")]]
    )
    await cq.answer()

@Client.on_callback_query(filters.regex("^utag_change_resume$"))
async def utag_change_resume_callback(client: Client, cq: CallbackQuery):
    if not cq.from_user: return
    user_id = cq.from_user.id
    custom_cmds = await _load_custom_cmds(user_id)
    current_cmd = custom_cmds.get("resume", "resume")
    await _edit_cq(
        cq,
        f"▶️ **Davom Etish Komandasini O'zgartirish**\n\nSizning joriy komandangiz: .{current_cmd}\n\nUni almashtirmoqchimisiz?",
        [[InlineKeyboardButton("✅ Ha!", callback_data="utag_confirm_change_resume"), InlineKeyboardButton("❌ Yo'q", callback_data="utag_commands")]]
    )
    await cq.answer()

@Client.on_callback_query(filters.regex("^utag_confirm_change_resume$"))
async def utag_confirm_change_resume_callback(client: Client, cq: CallbackQuery):
    if not cq.from_user: return
    user_id = cq.from_user.id
    user_states[user_id] = "waiting_for_new_resume_command"
    await _edit_cq(
        cq,
        "✍️ **Yangi komandani yuboring**\n\n⚠️ **Qoidalar:**\n• Maksimal uzunlik: 15 ta harf (nuqtadan tashqari)\n• Ruscha harflar taqiqlanadi\n• Faqat lotin harflari, raqamlar va _ belgisi\n• Nuqta bilan boshlash shart emas (bot ozi qo'yadi)",
        [[InlineKeyboardButton("❌ Bekor qilish", callback_data="utag_commands")]]
    )
    await cq.answer()


@Client.on_callback_query(filters.regex("^utag_speed$"))
async def utag_speed_callback(client: Client, cq: CallbackQuery):
    if not cq.from_user:
        return
    user_id = cq.from_user.id
    settings = user_settings.get(user_id, {})
    current_speed = get_utag_speed_seconds(settings)

    await _edit_cq(
        cq,
        "🚀 **Tezlikni tanlang**\n\n"
        f"Hozirgi: {format_speed_label(current_speed)}\n"
        f"Oraliq: {UTAG_SPEED_MIN}s — {UTAG_SPEED_MAX}s\n\n"
        f"{SPEED_WARNING}",
        [
            [
                InlineKeyboardButton("0.5s", callback_data="utag_set_speed_0.5"),
                InlineKeyboardButton("0.8s ✓", callback_data="utag_set_speed_0.8"),
                InlineKeyboardButton("1.5s", callback_data="utag_set_speed_1.5"),
            ],
            [
                InlineKeyboardButton("3.0s", callback_data="utag_set_speed_3.0"),
                InlineKeyboardButton("5.0s", callback_data="utag_set_speed_5.0"),
            ],
            [InlineKeyboardButton("✏️ Boshqa qiymat", callback_data="utag_speed_custom")],
            [InlineKeyboardButton("🔙 Orqaga", callback_data="utag_settings")],
        ]
    )
    await cq.answer()


@Client.on_callback_query(filters.regex("^utag_speed_custom$"))
async def utag_speed_custom_callback(client: Client, cq: CallbackQuery):
    if not cq.from_user:
        return
    user_id = cq.from_user.id
    user_states[user_id] = "waiting_for_utag_speed"
    await _edit_cq(
        cq,
        f"✏️ **Maxsus tezlik**\n\n"
        f"{UTAG_SPEED_MIN}s dan {UTAG_SPEED_MAX}s gacha raqam yuboring.\n"
        f"Masalan: `0.8` yoki `2.5`\n\n"
        f"{SPEED_WARNING}",
        [[InlineKeyboardButton("❌ Bekor qilish", callback_data="utag_speed")]],
    )
    await cq.answer()


@Client.on_callback_query(filters.regex("^utag_set_speed_(.+)$"))
async def utag_set_speed_callback(client: Client, cq: CallbackQuery):
    if not cq.from_user:
        return
    user_id = cq.from_user.id
    try:
        speed = float(cq.matches[0].group(1))
    except (IndexError, AttributeError, ValueError):
        await cq.answer("Xatolik", show_alert=True)
        return

    speed = max(UTAG_SPEED_MIN, min(UTAG_SPEED_MAX, round(speed, 1)))
    if user_id not in user_settings:
        user_settings[user_id] = {}
    user_settings[user_id]["utag_speed_seconds"] = speed

    warning = f"\n\n{SPEED_WARNING}" if is_high_speed_risk(speed) else ""
    await _edit_cq(
        cq,
        f"✅ **Tezlik o'zgartirildi!**\n\nYangi tezlik: {format_speed_label(speed)}{warning}",
        [[InlineKeyboardButton("🔙 Orqaga", callback_data="utag_settings")]],
    )
    await cq.answer()





@Client.on_callback_query(filters.regex("^utag_completion$"))

async def utag_completion_callback(client: Client, cq: CallbackQuery):

    if not cq.from_user:

        return

    user_id = cq.from_user.id

    settings = user_settings.get(user_id, {})

    current = settings.get("utag_completion_msg", True)

    status = "✅ Yoqilgan" if current else "❌ O'chirilgan"



    await _edit_cq(
        cq,
        "📢 **Yakunlangan habari**\n\n"
        f"Hozirgi: {status}\n\n"
        "Utag yakunlanganda xabar chiqsinmi?",
        [
            [
                InlineKeyboardButton("✅ Yoqish", callback_data="utag_set_completion_on"),
                InlineKeyboardButton("❌ O'chirish", callback_data="utag_set_completion_off")
            ],
            [InlineKeyboardButton("🔙 Orqaga", callback_data="utag_settings")]
        ]
    )
    await cq.answer()





@Client.on_callback_query(filters.regex("^utag_set_completion_(.+)$"))

async def utag_set_completion_callback(client: Client, cq: CallbackQuery):

    if not cq.from_user:

        return

    user_id = cq.from_user.id

    try:

        action = cq.matches[0].group(1)

    except (IndexError, AttributeError):

        await cq.answer("Xatolik", show_alert=True)

        return

    if user_id not in user_settings:

        user_settings[user_id] = {}

    user_settings[user_id]["utag_completion_msg"] = (action == "on")

    status = "✅ Yoqilgan" if (action == "on") else "❌ O'chirilgan"



    await _edit_cq(
        cq,
        f"✅ **Sozlama o'zgartirildi!**\n\nYakun habari: {status}",
        [[InlineKeyboardButton("🔙 Orqaga", callback_data="utag_settings")]]
    )
    await cq.answer()





@Client.on_callback_query(filters.regex("^utag_typing$"))

async def utag_typing_callback(client: Client, cq: CallbackQuery):

    if not cq.from_user:

        return

    user_id = cq.from_user.id

    settings = user_settings.get(user_id, {})

    current = settings.get("utag_typing_status", True)

    status = "✅ Yoqilgan" if current else "❌ O'chirilgan"



    await _edit_cq(
        cq,
        "⌨️ **Typing status (Utag)**\n\n"
        f"Hozirgi: {status}\n\n"
        "Utag paytida guruhda 'typing...' (yozmoqda) statusi chiqsinmi?\n"
        "Bu faqat tagging jarayoniga tegishli.",
        [
            [
                InlineKeyboardButton("✅ Yoqish", callback_data="utag_set_typing_on"),
                InlineKeyboardButton("❌ O'chirish", callback_data="utag_set_typing_off")
            ],
            [InlineKeyboardButton("🔙 Orqaga", callback_data="utag_settings")]
        ]
    )
    await cq.answer()





@Client.on_callback_query(filters.regex("^utag_set_typing_(.+)$"))

async def utag_set_typing_callback(client: Client, cq: CallbackQuery):

    if not cq.from_user:

        return

    user_id = cq.from_user.id

    try:

        action = cq.matches[0].group(1)

    except (IndexError, AttributeError):

        await cq.answer("Xatolik", show_alert=True)

        return

    if user_id not in user_settings:

        user_settings[user_id] = {}

    user_settings[user_id]["utag_typing_status"] = (action == "on")

    status = "✅ Yoqilgan" if (action == "on") else "❌ O'chirilgan"



    await _edit_cq(
        cq,
        f"✅ **Sozlama o'zgartirildi!**\n\nTyping status: {status}",
        [[InlineKeyboardButton("🔙 Orqaga", callback_data="utag_settings")]]
    )
    await cq.answer()




@Client.on_callback_query(filters.regex("^utag_auto_stop_delete$"))

async def utag_auto_stop_delete_callback(client: Client, cq: CallbackQuery):

    if not cq.from_user:

        return

    user_id = cq.from_user.id

    settings = user_settings.get(user_id, {})

    current = settings.get("utag_auto_stop_on_delete", True)

    status = "✅ Yoqilgan" if current else "❌ O'chirilgan"



    await _edit_cq(
        cq,
        "🗑 **O'chishda Avtostop**\n\n"
        f"Hozirgi holat: {status}\n\n"
        "Utag paytida yuborilgan **oxirgi 5 ta xabar** ketma-ket o'chirib tashlansa, "
        "utag avtomatik to'xtatilsinmi?\n\n"
        "⚠️ Faqat **eng oxirgi** 5 ta xabar o'chirilsa ishlaydi. "
        "Boshidan yoki o'rtadan o'chirilsa ta'sir qilmaydi.",
        [
            [
                InlineKeyboardButton("✅ Yoqish", callback_data="utag_set_auto_stop_on"),
                InlineKeyboardButton("❌ O'chirish", callback_data="utag_set_auto_stop_off")
            ],
            [InlineKeyboardButton("🔙 Orqaga", callback_data="utag_settings")]
        ]
    )
    await cq.answer()





@Client.on_callback_query(filters.regex("^utag_set_auto_stop_(on|off)$"))

async def utag_set_auto_stop_callback(client: Client, cq: CallbackQuery):

    if not cq.from_user:

        return

    user_id = cq.from_user.id

    try:

        action = cq.matches[0].group(1)

    except (IndexError, AttributeError):

        await cq.answer("Xatolik", show_alert=True)

        return

    if user_id not in user_settings:

        user_settings[user_id] = {}

    user_settings[user_id]["utag_auto_stop_on_delete"] = (action == "on")

    status = "✅ Yoqilgan" if (action == "on") else "❌ O'chirilgan"



    await _edit_cq(
        cq,
        f"✅ **Sozlama o'zgartirildi!**\n\nO'chishda avtostop: {status}",
        [[InlineKeyboardButton("🔙 Orqaga", callback_data="utag_settings")]]
    )
    await cq.answer()





@Client.on_callback_query(filters.regex("^utag_delete_timer$"))

async def utag_delete_timer_callback(client: Client, cq: CallbackQuery):

    if not cq.from_user:

        return

    user_id = cq.from_user.id

    settings = user_settings.get(user_id, {})

    current = settings.get("utag_delete_timer", 2)

    if current == 0:

        current_label = "Hech qachon"

    else:

        current_label = f"{current} sekund"



    await _edit_cq(
        cq,
        "⏱️ **Xabar O'chish Taymeri**\n\n"
        f"Hozirgi: {current_label}\n\n"
        "Boshlash/to'xtatish xabari qancha vaqtdan keyin o'chsin?",
        [
            [
                InlineKeyboardButton("Hech qachon", callback_data="utag_set_timer_0"),
                InlineKeyboardButton("2 sekund", callback_data="utag_set_timer_2")
            ],
            [
                InlineKeyboardButton("5 sekund", callback_data="utag_set_timer_5"),
                InlineKeyboardButton("7 sekund", callback_data="utag_set_timer_7")
            ],
            [
                InlineKeyboardButton("10 sekund", callback_data="utag_set_timer_10"),
                InlineKeyboardButton("Custom", callback_data="utag_timer_custom")
            ],
            [InlineKeyboardButton("🔙 Orqaga", callback_data="utag_settings")]
        ]
    )
    await cq.answer()





@Client.on_callback_query(filters.regex("^utag_set_timer_(.+)$"))

async def utag_set_timer_callback(client: Client, cq: CallbackQuery):

    if not cq.from_user:

        return

    user_id = cq.from_user.id

    try:

        timer_value = int(cq.matches[0].group(1))

    except (IndexError, AttributeError, ValueError):

        await cq.answer("Xatolik", show_alert=True)

        return

    if user_id not in user_settings:

        user_settings[user_id] = {}

    user_settings[user_id]["utag_delete_timer"] = timer_value

    

    if timer_value == 0:

        timer_label = "Hech qachon"

    else:

        timer_label = f"{timer_value} sekund"



    await _edit_cq(
        cq,
        f"✅ **Sozlama o'zgartirildi!**\n\nXabar o'chish taymeri: {timer_label}",
        [[InlineKeyboardButton("🔙 Orqaga", callback_data="utag_settings")]]
    )
    await cq.answer()





@Client.on_callback_query(filters.regex("^utag_timer_custom$"))

async def utag_timer_custom_callback(client: Client, cq: CallbackQuery):

    if not cq.from_user:

        return

    user_id = cq.from_user.id

    user_states[user_id] = "waiting_for_custom_timer"



    await _edit_cq(
        cq,
        "⏱️ **Custom Taymer**\n\n"
        "1-30 soniya orasida taymer kiriting:\n"
        "Masalan: 15",
        [[InlineKeyboardButton("❌ Bekor qilish", callback_data="utag_delete_timer")]]
    )
    await cq.answer()







@Client.on_callback_query(filters.regex("^utag_timer_menu$"))

async def utag_timer_menu_callback(client: Client, cq: CallbackQuery):

    """Taymerli habar yuborish menyusi"""

    if not cq.from_user:

        return

    user_id = cq.from_user.id

    

    timers = await get_user_utag_timers(user_id)

    

    text = "⏰ **Taymerli Habar Yuborish**\n\n"

    text += "Bu funksiya guruhlarda avtomatik ravishda xabar yuboradi.\n"

    text += "O'yin tugaganda admin o'rniga bot avtomatik yangi o'yin boshlaydi.\n\n"

    text += "📝 Istalgan xabar yuborishingiz mumkin:\n"

    text += "• /game@BotUsername\n"

    text += "• Qo'shilinglar! Yangi o'yin boshlandi 🎮\n"

    text += "• Har qanday custom xabar\n\n"

    

    if timers:

        text += f"📊 Sizda {len(timers)} ta faol taymer:\n\n"

        for i, timer in enumerate(timers, 1):

            status = "✅ Yoqilgan" if timer["is_active"] else "❌ O'chirilgan"

            text += f"{i}. 🆔 `{timer['chat_id']}`\n"

            text += f"   💬 Xabar: `{timer['message_text'][:50]}{'...' if len(timer['message_text']) > 50 else ''}`\n"

            text += f"   ⏱️ Interval: {timer['interval_minutes']} daqiqa\n"

            text += f"   🔁 Takrorlash: {timer['repeat_count']} marta (har {timer['repeat_delay']} sekund)\n"

            text += f"   📌 Holat: {status}\n\n"

    else:

        text += "⚠️ Hozircha hech qanday taymer yo'q.\n\n"

    

    text += "Nima qilmoqchisiz?"

    

    buttons = []

    if timers:

        buttons.append([InlineKeyboardButton("➕ Yangi taymer qo'shish", callback_data="utag_timer_add")])

        buttons.append([InlineKeyboardButton("📋 Taymerlarni boshqarish", callback_data="utag_timer_manage")])

    else:

        buttons.append([InlineKeyboardButton("➕ Taymer qo'shish", callback_data="utag_timer_add")])

    

    buttons.append([InlineKeyboardButton("🔙 Orqaga", callback_data="utag_settings")])

    

    await _edit_cq(cq, text, buttons)
    await cq.answer()




@Client.on_callback_query(filters.regex("^utag_timer_add$"))

async def utag_timer_add_callback(client: Client, cq: CallbackQuery):

    """Yangi taymer qo'shish"""

    if not cq.from_user:

        return

    user_id = cq.from_user.id

    user_states[user_id] = "waiting_for_timer_chat"

    

    await _edit_cq(
        cq,
        "⏰ **Yangi Taymer Qo'shish**\n\n"
        "Avval guruh username yoki havolasini yuboring:\n"
        "Masalan: `@guruhim` yoki `https://t.me/guruhim`\n\n"
        "⚠️ Bot ushbu guruhda admin bo'lishi kerak!",
        [[InlineKeyboardButton("❌ Bekor qilish", callback_data="utag_timer_menu")]]
    )
    await cq.answer()





@Client.on_callback_query(filters.regex(r"^utag_timer_view_(\d+)$"))

async def utag_timer_view_callback(client: Client, cq: CallbackQuery):

    """Taymer tafsilotlarini ko'rish"""

    if not cq.from_user:

        return

    user_id = cq.from_user.id

    try:

        timer_id = int(cq.matches[0].group(1))

    except (ValueError, IndexError, AttributeError):

        await cq.answer("Xatolik", show_alert=True)

        return

    

    timers = await get_user_utag_timers(user_id)

    timer = next((t for t in timers if t["id"] == timer_id), None)

    

    if not timer:

        await cq.answer("Taymer topilmadi!", show_alert=True)

        return

    

    status = "✅ Yoqilgan" if timer["is_active"] else "❌ O'chirilgan"

    

    await _edit_cq(
        cq,
        f"⏰ **Taymer #{timer_id}**\n\n"
        f"🆔 Guruh: `{timer['chat_id']}`\n"
        f"💬 Xabar: `{timer['message_text'][:100]}{'...' if len(timer['message_text']) > 100 else ''}`\n"
        f"⏱️ Interval: {timer['interval_minutes']} daqiqa\n"
        f"🔁 Takrorlash: {timer['repeat_count']} marta\n"
        f"⏳ Takrorlash oralig'i: {timer['repeat_delay']} sekund\n"
        f"📌 Holat: {status}\n\n"
        "Nima qilmoqchisiz?",
        [
            [
                InlineKeyboardButton(
                    "🔄 Yoqish/O'chirish",
                    callback_data=f"utag_timer_toggle_{timer_id}"
                )
            ],
            [
                InlineKeyboardButton("✏️ O'zgartirish", callback_data=f"utag_timer_edit_{timer_id}"),
                InlineKeyboardButton("🗑 O'chirish", callback_data=f"utag_timer_delete_{timer_id}")
            ],
            [InlineKeyboardButton("🔙 Orqaga", callback_data="utag_timer_manage")]
        ]
    )
    await cq.answer()





@Client.on_callback_query(filters.regex("^utag_timer_manage$"))

async def utag_timer_manage_callback(client: Client, cq: CallbackQuery):

    """Taymerlarni boshqarish"""

    if not cq.from_user:

        return

    user_id = cq.from_user.id

    timers = await get_user_utag_timers(user_id)

    

    if not timers:

        await cq.answer("Taymerlar yo'q!", show_alert=True)

        return

    

    buttons = []

    for timer in timers:

        status_emoji = "✅" if timer["is_active"] else "❌"

        buttons.append([

            InlineKeyboardButton(

                f"{status_emoji} {timer['chat_id']}",

                callback_data=f"utag_timer_view_{timer['id']}"

            )

        ])

    

    buttons.append([InlineKeyboardButton("🔙 Orqaga", callback_data="utag_timer_menu")])

    

    await _edit_cq(
        cq,
        "📋 **Taymerlarni Boshqarish**\n\n"
        "Qaysi taymerni boshqarmoqchisiz?",
        buttons
    )
    await cq.answer()





@Client.on_callback_query(filters.regex(r"^utag_timer_toggle_(\d+)$"))

async def utag_timer_toggle_callback(client: Client, cq: CallbackQuery):

    """Taymer yoqish/o'chirish"""

    if not cq.from_user:

        return

    user_id = cq.from_user.id

    try:

        timer_id = int(cq.matches[0].group(1))

    except (ValueError, IndexError, AttributeError):

        await cq.answer("Xatolik", show_alert=True)

        return

    

    timers = await get_user_utag_timers(user_id)

    timer = next((t for t in timers if t["id"] == timer_id), None)

    

    if not timer:

        await cq.answer("Taymer topilmadi!", show_alert=True)

        return

    

    new_status = not timer["is_active"]

    await set_utag_timer_active(timer_id, new_status)

    

    status_text = "yoqildi" if new_status else "o'chirildi"

    await cq.answer(f"Taymer {status_text}!", show_alert=True)

    

    await utag_timer_view_callback(client, cq)





@Client.on_callback_query(filters.regex(r"^utag_timer_delete_(\d+)$"))

async def utag_timer_delete_callback(client: Client, cq: CallbackQuery):

    """Taymerni o'chirish"""

    if not cq.from_user:

        return

    user_id = cq.from_user.id

    try:

        timer_id = int(cq.matches[0].group(1))

    except (ValueError, IndexError, AttributeError):

        await cq.answer("Xatolik", show_alert=True)

        return

    

    timers = await get_user_utag_timers(user_id)

    timer = next((t for t in timers if t["id"] == timer_id), None)

    

    if not timer:

        await cq.answer("Taymer topilmadi!", show_alert=True)

        return

    

    await delete_utag_timer(user_id, timer["chat_id"])

    

    await cq.answer("Taymer o'chirildi!", show_alert=True)

    await _edit_cq(
        cq,
        "✅ **Taymer o'chirildi!**\n\n"
        "Boshqa taymerlarni boshqarish uchun menyudan foydalaning.",
        [
            [InlineKeyboardButton("📋 Taymerlar", callback_data="utag_timer_manage")],
            [InlineKeyboardButton("🔙 Orqaga", callback_data="utag_timer_menu")]
        ]
    )




@Client.on_callback_query(filters.regex(r"^utag_timer_edit_(\d+)$"))

async def utag_timer_edit_callback(client: Client, cq: CallbackQuery):

    """Taymerni o'zgartirish"""

    if not cq.from_user:

        return

    user_id = cq.from_user.id

    try:

        timer_id = int(cq.matches[0].group(1))

    except (ValueError, IndexError, AttributeError):

        await cq.answer("Xatolik", show_alert=True)

        return

    

    user_states[user_id] = f"editing_timer_{timer_id}"

    

    await _edit_cq(
        cq,
        "✏️ **Taymerni O'zgartirish**\n\n"
        "Yangi qiymatlarni kiriting:\n\n"
        "Format: `guruh_id|game_command|interval_minutes`\n"
        "Masalan: `-100123456789|/game@Game_bot|60`\n\n"
        "📝 Izoh:\n"
        "• `guruh_id` - Guruh ID raqami\n"
        "• `game_command` - O'yin buyrug'i (masalan: /game@BotUsername)\n"
        "• `interval_minutes` - Necha daqiqada bir yuborish (masalan: 60)",
        [[InlineKeyboardButton("❌ Bekor qilish", callback_data=f"utag_timer_view_{timer_id}")]]
    )
    await cq.answer()







async def handle_timer_chat_input(client: Client, message: Message, user_id: int):

    """Taymer uchun guruh ID sini qabul qilish"""

    user_states.pop(user_id, None)

    

    target_chat = message.text.strip()

    

    if "t.me/" in target_chat:

        import re

        m = re.search(r't\.me/([a-zA-Z0-9_]+)', target_chat)

        if m:

            target_chat = "@" + m.group(1)

        else:

            await message.reply_text("❌ Noto'g'ri link formati!")

            return

    elif not target_chat.startswith("@"):

        target_chat = "@" + target_chat

    

    try:

        user_client = await get_user_client(user_id)

        chat = await user_client.get_chat(target_chat)

        chat_id = chat.id

    except Exception as e:

        await message.reply_text(

            f"❌ Guruh topilmadi yoki kirish imkoni yo'q:\n`{e}`",

            reply_markup=InlineKeyboardMarkup([

                [InlineKeyboardButton("❌ Bekor qilish", callback_data="utag_timer_menu")]

            ])

        )

        return

    

    user_states[user_id] = f"waiting_for_timer_message|{chat_id}"

    

    await message.reply_text(

        f"✅ Guruh topildi: `{chat.title}`\n\n"

        "Endi yuboriladigan xabarni kiriting:\n"

        "Masalan:\n"

        "• `/game@Game_bot`\n"

        "• `Qo'shilinglar! Yangi o'yin boshlandi 🎮`\n"

        "• `@username1 @username2 Kelinglar o'ynaymiz!`\n\n"

        "📝 Izoh:\n"

        "• Istalgan matn yozishingiz mumkin\n"

        "• @username lar avtomatik mention qilinadi\n"

        "• Emoji va formatlash ishlatishingiz mumkin",

        reply_markup=InlineKeyboardMarkup([

            [InlineKeyboardButton("❌ Bekor qilish", callback_data="utag_timer_menu")]

        ])

    )





async def handle_timer_message_input(client: Client, message: Message, user_id: int):

    """Taymer uchun xabar matnini qabul qilish"""

    state = user_states.get(user_id, "")

    if not (state.startswith("waiting_for_timer_message|") or state.startswith("waiting_for_timer_message_")):

        return

    

    try:

        if state.startswith("waiting_for_timer_message|"):

            chat_id = int(state.replace("waiting_for_timer_message|", ""))

        else:

            chat_id = int(state.replace("waiting_for_timer_message_", ""))

    except ValueError:

        user_states.pop(user_id, None)

        await message.reply_text("❌ Xatolik yuz berdi. Qaytadan urinib ko'ring.")

        return

    

    message_text = message.text.strip()

    

    if not message_text:

        await message.reply_text(

            "❌ Xabar bo'sh bo'lishi mumkin emas!",

            reply_markup=InlineKeyboardMarkup([

                [InlineKeyboardButton("❌ Bekor qilish", callback_data="utag_timer_menu")]

            ])

        )

        return

    

    user_states[user_id] = f"waiting_for_timer_interval|{chat_id}|{message_text}"

    

    await message.reply_text(

        f"✅ Xabar: `{message_text[:100]}{'...' if len(message_text) > 100 else ''}`\n\n"

        "Endi intervalni kiriting (necha daqiqada bir yuborish):\n"

        "Masalan: 60 (1 soat), 30 (30 daqiqa), 120 (2 soat)\n\n"

        "📝 Izoh:\n"

        "• Kamida 1 daqiqa\n"

        "• Maksimal 1440 daqiqa (24 soat)",

        reply_markup=InlineKeyboardMarkup([

            [InlineKeyboardButton("❌ Bekor qilish", callback_data="utag_timer_menu")]

        ])

    )





async def handle_timer_interval_input(client: Client, message: Message, user_id: int):

    """Taymer uchun interval ni qabul qilish"""

    state = user_states.get(user_id, "")

    if not (state.startswith("waiting_for_timer_interval|") or state.startswith("waiting_for_timer_interval_")):

        return

    

    try:

        if state.startswith("waiting_for_timer_interval|"):

            parts = state.replace("waiting_for_timer_interval|", "").split("|", 1)

            chat_id = int(parts[0])

            message_text = parts[1] if len(parts) > 1 else ""

        else:

            parts = state.replace("waiting_for_timer_interval_", "").split("_", 1)

            chat_id = int(parts[0])

            message_text = parts[1] if len(parts) > 1 else ""

        

        interval_minutes = int(message.text.strip())

        

        if interval_minutes < 1:

            await message.reply_text("❌ Interval kamida 1 daqiqa bo'lishi kerak!")

            return

        

        if interval_minutes > 1440:

            await message.reply_text("❌ Interval maksimal 1440 daqiqa (24 soat) bo'lishi mumkin!")

            return

    except ValueError:

        await message.reply_text(

            "❌ Faqat raqam kiriting!\n\n"

            "Masalan: 60",

            reply_markup=InlineKeyboardMarkup([

                [InlineKeyboardButton("❌ Bekor qilish", callback_data="utag_timer_menu")]

            ])

        )

        return

    

    user_states[user_id] = f"waiting_for_timer_repeat|{chat_id}|{message_text}|{interval_minutes}"

    

    await message.reply_text(

        f"✅ Interval: {interval_minutes} daqiqa\n\n"

        "Xabar nechi marta takrorlansin?\n"

        "Masalan: 1 (bir marta), 5 (5 marta), 0 (cheksiz takrorlash)\n\n"

        "📝 Izoh:\n"

        "• 0 = cheksiz takrorlash\n"

        "• 1-99 = ma'lum miqdorda takrorlash\n"

        "• Har bir takrorlash orasida necha sekund kutish kerak?",

        reply_markup=InlineKeyboardMarkup([

            [InlineKeyboardButton("❌ Bekor qilish", callback_data="utag_timer_menu")]

        ])

    )





async def handle_timer_repeat_input(client: Client, message: Message, user_id: int):

    """Taymer uchun takrorlash sozlamalarini qabul qilish"""

    state = user_states.get(user_id, "")

    if not state.startswith("waiting_for_timer_repeat|"):

        return

    

    try:

        parts = state.replace("waiting_for_timer_repeat|", "").split("|")

        if len(parts) < 3:

            raise ValueError("Not enough parts")

        chat_id = int(parts[0])

        message_text = parts[1]

        interval_minutes = int(parts[2])

    except (ValueError, IndexError):

        user_states.pop(user_id, None)

        await message.reply_text("❌ Xatolik yuz berdi. Qaytadan urinib ko'ring.")

        return

    

    try:

        repeat_count = int(message.text.strip())

        

        if repeat_count < 0:

            await message.reply_text("❌ Takrorlash soni 0 yoki undan katta bo'lishi kerak!")

            return

        

        if repeat_count > 99:

            await message.reply_text("❌ Maksimal 99 marta takrorlash mumkin!")

            return

    except ValueError:

        await message.reply_text(

            "❌ Faqat raqam kiriting!\n\n"

            "Masalan: 5",

            reply_markup=InlineKeyboardMarkup([

                [InlineKeyboardButton("❌ Bekor qilish", callback_data="utag_timer_menu")]

            ])

        )

        return

    

    if repeat_count == 0:

        repeat_count = 999999  # Cheksiz

    

    # Auto-calculate repeat_delay: interval_seconds / repeat_count

    if repeat_count == 999999:

        repeat_delay = 0  # Not used for infinite repeat

    else:

        interval_seconds = interval_minutes * 60

        repeat_delay = interval_seconds // repeat_count

        if repeat_delay < 1:

            repeat_delay = 1

    

    user_states.pop(user_id, None)

    

    await add_utag_timer(user_id, chat_id, message_text, interval_minutes, repeat_count, repeat_delay)

    

    repeat_label = "cheksiz" if repeat_count == 999999 else str(repeat_count)

    

    await message.reply_text(

        f"✅ **Taymer muvaffaqiyatli qo'shildi!**\n\n"

        f"🆔 Guruh: `{chat_id}`\n"

        f"💬 Xabar: `{message_text[:100]}{'...' if len(message_text) > 100 else ''}`\n"

        f"⏱️ Interval: {interval_minutes} daqiqa\n"

        f"🔁 Takrorlash: {repeat_label} marta\n"

        f"⏳ Takrorlash oralig'i: {repeat_delay} sekund (avtomatik hisoblangan)\n\n"

        "Taymer ishga tushdi!",

        reply_markup=InlineKeyboardMarkup([

            [InlineKeyboardButton("📋 Taymerlar", callback_data="utag_timer_manage")],

            [InlineKeyboardButton("🔙 Orqaga", callback_data="utag_timer_menu")]

        ])

    )





async def handle_timer_repeat_delay_input(client: Client, message: Message, user_id: int):

    """Taymer uchun takrorlash oralig'ini qabul qilish"""

    state = user_states.get(user_id, "")

    if not state.startswith("waiting_for_timer_repeat_delay|"):

        return

    

    try:

        parts = state.replace("waiting_for_timer_repeat_delay|", "").split("|")

        if len(parts) < 4:

            raise ValueError("Not enough parts")

        chat_id = int(parts[0])

        message_text = parts[1]

        interval_minutes = int(parts[2])

        repeat_count = int(parts[3])

    except (ValueError, IndexError):

        user_states.pop(user_id, None)

        await message.reply_text("❌ Xatolik yuz berdi. Qaytadan urinib ko'ring.")

        return

    

    try:

        repeat_delay = int(message.text.strip())

        

        if repeat_delay < 1:

            await message.reply_text("❌ Takrorlash oralig'i kamida 1 sekund bo'lishi kerak!")

            return

        

        if repeat_delay > 300:

            await message.reply_text("❌ Takrorlash oralig'i maksimal 300 sekund (5 daqiqa) bo'lishi mumkin!")

            return

    except ValueError:

        await message.reply_text(

            "❌ Faqat raqam kiriting!\n\n"

            "Masalan: 5",

            reply_markup=InlineKeyboardMarkup([

                [InlineKeyboardButton("❌ Bekor qilish", callback_data="utag_timer_menu")]

            ])

        )

        return

    

    user_states.pop(user_id, None)

    

    await add_utag_timer(user_id, chat_id, message_text, interval_minutes, repeat_count, repeat_delay)

    

    repeat_label = "cheksiz" if repeat_count == 999999 else str(repeat_count)

    

    await message.reply_text(

        f"✅ **Taymer muvaffaqiyatli qo'shildi!**\n\n"

        f"🆔 Guruh: `{chat_id}`\n"

        f"💬 Xabar: `{message_text[:100]}{'...' if len(message_text) > 100 else ''}`\n"

        f"⏱️ Interval: {interval_minutes} daqiqa\n"

        f"🔁 Takrorlash: {repeat_label} marta\n"

        f"⏳ Takrorlash oralig'i: {repeat_delay} sekund\n\n"

        "Taymer ishga tushdi!",

        reply_markup=InlineKeyboardMarkup([

            [InlineKeyboardButton("📋 Taymerlar", callback_data="utag_timer_manage")],

            [InlineKeyboardButton("🔙 Orqaga", callback_data="utag_timer_menu")]

        ])

    )





async def handle_timer_edit_input(client: Client, message: Message, user_id: int):

    """Taymerni o'zgartirish uchun input"""

    state = user_states.get(user_id, "")

    if not state.startswith("editing_timer_"):

        return

    

    try:

        timer_id = int(state.replace("editing_timer_", ""))

    except ValueError:

        user_states.pop(user_id, None)

        await message.reply_text("❌ Xatolik yuz berdi. Qaytadan urinib ko'ring.")

        return

    

    user_states.pop(user_id, None)

    

    try:

        parts = message.text.strip().split("|")

        if len(parts) != 4:

            raise ValueError("Noto'g'ri format")

        

        chat_id = int(parts[0].strip())

        message_text = parts[1].strip()

        interval_minutes = int(parts[2].strip())

        repeat_count = int(parts[3].strip())

        

        if interval_minutes < 5:

            await message.reply_text("❌ Interval kamida 5 daqiqa bo'lishi kerak!")

            return

        

        if repeat_count < 0 or repeat_count > 99:

            await message.reply_text("❌ Takrorlash soni 0-99 oralig'ida bo'lishi kerak!")

            return

        

        # Auto-calculate repeat_delay: interval_seconds / repeat_count

        if repeat_count == 0:

            repeat_count = 999999

            repeat_delay = 0

        else:

            interval_seconds = interval_minutes * 60

            repeat_delay = interval_seconds // repeat_count

            if repeat_delay < 1:

                repeat_delay = 1

    except (ValueError, IndexError):

        await message.reply_text(

            "❌ Noto'g'ri format!\n\n"

            "Format: `guruh_id|xabar_matni|interval_minutes|takrorlash_soni`\n"

            "Masalan: `-100123456789|/game@Game_bot|60|5`\n\n"

            "📝 Izoh: Takrorlash oralig'i avtomatik hisoblanadi (interval / takrorlash soni)",

            reply_markup=InlineKeyboardMarkup([

                [InlineKeyboardButton("❌ Bekor qilish", callback_data=f"utag_timer_view_{timer_id}")]

            ])

        )

        return

    

    timers = await get_user_utag_timers(user_id)

    timer = next((t for t in timers if t["id"] == timer_id), None)

    

    if not timer:

        await message.reply_text("❌ Taymer topilmadi!")

        return

    

    await add_utag_timer(user_id, chat_id, message_text, interval_minutes, repeat_count, repeat_delay)

    

    repeat_label = "cheksiz" if repeat_count == 999999 else str(repeat_count)

    

    await message.reply_text(

        f"✅ **Taymer yangilandi!**\n\n"

        f"🆔 Guruh: `{chat_id}`\n"

        f"💬 Xabar: `{message_text[:100]}{'...' if len(message_text) > 100 else ''}`\n"

        f"⏱️ Interval: {interval_minutes} daqiqa\n"

        f"🔁 Takrorlash: {repeat_label} marta\n"

        f"⏳ Takrorlash oralig'i: {repeat_delay} sekund (avtomatik)",

        reply_markup=InlineKeyboardMarkup([

            [InlineKeyboardButton("📋 Taymerlar", callback_data="utag_timer_manage")]

        ])

    )







async def utag_timer_background_task(client: Client):

    """Background task - barcha faol taymerlarni tekshirish va xabar yuborish"""

    while True:

        try:

            await asyncio.sleep(60)  # Har 1 daqiqada tekshirish

            

            timers = await get_all_active_utag_timers()

            current_time = int(time.time())

            logger.info(f"[UTAG_TIMER] Check started at {current_time}, active timers: {len(timers)}")

            

            for timer in timers:

                interval_seconds = timer["interval_minutes"] * 60

                time_since_last = current_time - timer["last_sent"]

                

                if time_since_last >= interval_seconds:

                    logger.info(f"[UTAG_TIMER] Timer {timer['id']} is due: interval={interval_seconds}s, elapsed={time_since_last}s")

                    try:

                        current_timer = await get_utag_timer(timer["user_id"], timer["chat_id"])

                        if not current_timer or not current_timer.get("is_active"):

                            logger.info(f"[UTAG_TIMER] Timer {timer['id']} is no longer active, skipping")

                            continue

                        

                        repeat_count = timer.get("repeat_count", 1)

                        repeat_delay = timer.get("repeat_delay", 5)

                        message_text = timer.get("message_text", "")

                        

                        # Get USERBOT client for this timer's owner

                        try:

                            user_client = await get_user_client(timer["user_id"])

                        except Exception as e:

                            logger.error(f"[UTAG_TIMER] Cannot get userbot for user {timer['user_id']}: {e}")

                            continue

                        

                        if repeat_count == 999999:
                            # Diagnostic: log timer message destination
                            is_group = timer["chat_id"] < 0 if isinstance(timer["chat_id"], int) else False
                            logger.debug(
                                f"[UTAG_TIMER_DIAG] Sending timer message | "
                                f"chat_id={timer['chat_id']} | "
                                f"is_group={is_group} | "
                                f"msg_len={len(message_text)}"
                            )
                            
                            try:
                                logger.info(f"[UTAG_TIMER] Sending via USERBOT user={timer['user_id']} chat_id={timer['chat_id']}")
                                await user_client.send_message(
                                    timer["chat_id"],
                                    message_text
                                )
                                await update_utag_timer_last_sent(timer["id"], current_time)
                                logger.info(f"[UTAG_TIMER] Successfully sent message to {timer['chat_id']}: {message_text[:50]}")
                            except FloodWait as e:
                                logger.error(f"[UTAG_TIMER] USERBOT FloodWait {e.value}s for user {timer['user_id']} chat {timer['chat_id']}")
                            except ChatWriteForbidden as e:
                                logger.error(f"[UTAG_TIMER] USERBOT ChatWriteForbidden for user {timer['user_id']} chat {timer['chat_id']}: {e}")
                            except PeerIdInvalid as e:
                                logger.error(f"[UTAG_TIMER] USERBOT PeerIdInvalid for user {timer['user_id']} chat {timer['chat_id']}: {e}")
                            except Exception as e:
                                logger.error(f"[UTAG_TIMER] USERBOT send failed for user {timer['user_id']} chat {timer['chat_id']}: {type(e).__name__}: {e}")
                        else:

                            for i in range(repeat_count):

                                current_timer = await get_utag_timer(timer["user_id"], timer["chat_id"])

                                if not current_timer or not current_timer.get("is_active"):

                                    logger.info(f"[UTAG_TIMER] Timer {timer['id']} stopped during repeat {i+1}/{repeat_count}")

                                    break

                                

                                if i > 0:

                                    await asyncio.sleep(repeat_delay)

                                

                                try:

                                    logger.info(f"[UTAG_TIMER] Sending message {i+1}/{repeat_count} to {timer['chat_id']}: {message_text[:50]}")

                                    await user_client.send_message(

                                        timer["chat_id"],

                                        message_text

                                    )

                                    logger.info(f"[UTAG_TIMER] Successfully sent message {i+1}/{repeat_count} to {timer['chat_id']}")

                                except FloodWait as e:

                                    logger.error(f"[UTAG_TIMER] USERBOT FloodWait {e.value}s for user {timer['user_id']} repeat {i+1}")

                                    break

                                except ChatWriteForbidden as e:

                                    logger.error(f"[UTAG_TIMER] USERBOT ChatWriteForbidden for user {timer['user_id']} repeat {i+1}: {e}")

                                    break

                                except PeerIdInvalid as e:

                                    logger.error(f"[UTAG_TIMER] USERBOT PeerIdInvalid for user {timer['user_id']} repeat {i+1}: {e}")

                                    break

                                except Exception as e:

                                    logger.error(f"[UTAG_TIMER] USERBOT send failed for user {timer['user_id']} repeat {i+1} chat {timer['chat_id']}: {type(e).__name__}: {e}")

                                    break

                            

                            await update_utag_timer_last_sent(timer["id"], current_time)

                        

                    except Exception as e:

                        logger.error(f"[UTAG_TIMER] Failed to send to {timer['chat_id']}: {e}")

                        await set_utag_timer_active(timer["id"], False)

        

        except Exception as e:

            logger.error(f"[UTAG_TIMER] Background task error: {e}")







def validate_command(command: str) -> tuple[bool, str]:

    """Validatsiya: max 15 harf, ruscha harfsiz, faqat lotin harflari, raqamlar va _"""

    cmd = command.strip().lstrip('.').split()[0] if command.strip() else ""

    

    if not cmd:

        return False, "Komanda bo'sh bo'lishi mumkin emas!"

    

    if len(cmd) > MAX_COMMAND_LENGTH:

        return False, f"Komanda juda uzun! Maksimal {MAX_COMMAND_LENGTH} ta harf. Siz kiritganningiz: {len(cmd)} ta"

    

    russian_chars = set('абвгдеёжзийклмнопрстуфхцчшщъыьэюяАБВГДЕЁЖЗИЙКЛМНОПРСТУФХЦЧШЩЪЫЬЭЮЯ')

    if any(char in russian_chars for char in cmd):

        return False, "Ruscha harflar taqiqlanadi! Faqat lotin harflari, raqamlar va _ belgisi."

    

    allowed_chars = set('abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_')

    if not all(char in allowed_chars for char in cmd):

        return False, "Faqat lotin harflari, raqamlar va _ belgisi ruxsat etiladi!"

    

    return True, cmd





def _normalize_command(command: str) -> str:

    """Komandani nuqtasiz, faqat birinchi so'z ko'rinishida qaytarish"""

    return command.strip().lstrip('.').split()[0]


def _reserved_or_conflicting_command(custom_cmds: dict, command: str, command_type: str):
    """Return a conflict reason, or None when the command is safe."""
    command = command.strip().lstrip(".").lower()
    if command in RESERVED_CORE_COMMANDS:
        return f".{command} Vento'ning rezerv komandasi va Utag uchun ishlatilishi mumkin emas."
    labels = {"atag": "boshlash", "stop": "to'xtatish", "pause": "pauza", "resume": "davom etish"}
    for other_type in UTAG_COMMAND_TYPES:
        if other_type == command_type:
            continue
        other = str(custom_cmds.get(other_type, other_type)).strip().lstrip(".").lower()
        if command == other:
            return f".{command} Utag'dagi {labels[other_type]} komandasi bilan bir xil bo'lishi mumkin emas."
    return None






async def handle_new_atag_command(client: Client, message: Message, user_id: int):

    """Yangi atag komandasini qabul qilish va validatsiya"""

    is_valid, result = validate_command(message.text)

    if not is_valid:

        await message.reply_text(

            f"❌ {result}\n\nQayta yuboring yoki bekor qiling.",

            reply_markup=InlineKeyboardMarkup([

                [InlineKeyboardButton("❌ Bekor qilish", callback_data="utag_commands")]

            ])

        )

        return

    

    new_cmd = _normalize_command(message.text)

    custom_cmds = await _load_custom_cmds(user_id)

    old_cmd = custom_cmds.get("atag", "atag")

    other_cmd = custom_cmds.get("stop", "stop")

    conflict = _reserved_or_conflicting_command(custom_cmds, new_cmd, "atag")
    if conflict:
        await message.reply_text(
            f"❌ {conflict}",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Bekor qilish", callback_data="utag_commands")]])
        )
        return


    

    if new_cmd == other_cmd:

        await message.reply_text(

            f"❌ Bu komanda to'xtatish komandasi (.{other_cmd}) bilan bir xil bo'lishi mumkin emas!",

            reply_markup=InlineKeyboardMarkup([

                [InlineKeyboardButton("❌ Bekor qilish", callback_data="utag_commands")]

            ])

        )

        return

    

    user_states[user_id] = f"confirming_atag|{new_cmd}"

    

    await message.reply_text(

        f"🔤 **Boshlash Komandasini O'zgartirish**\n\n"

        f"Joriy komanda: `.{old_cmd}`\n"

        f"Yangi komanda: `.{new_cmd}`\n\n"

        f"Tasdiqlaysizmi?",

        reply_markup=InlineKeyboardMarkup([

            [

                InlineKeyboardButton("✅ Ha", callback_data="utag_save_atag"),

                InlineKeyboardButton("❌ Yo'q", callback_data="utag_commands")

            ]

        ])

    )





async def handle_new_stop_command(client: Client, message: Message, user_id: int):

    """Yangi stop komandasini qabul qilish va validatsiya"""

    is_valid, result = validate_command(message.text)

    if not is_valid:

        await message.reply_text(

            f"❌ {result}\n\nQayta yuboring yoki bekor qiling.",

            reply_markup=InlineKeyboardMarkup([

                [InlineKeyboardButton("❌ Bekor qilish", callback_data="utag_commands")]

            ])

        )

        return

    

    new_cmd = _normalize_command(message.text)

    custom_cmds = await _load_custom_cmds(user_id)

    old_cmd = custom_cmds.get("stop", "stop")

    other_cmd = custom_cmds.get("atag", "atag")

    conflict = _reserved_or_conflicting_command(custom_cmds, new_cmd, "stop")
    if conflict:
        await message.reply_text(
            f"❌ {conflict}",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Bekor qilish", callback_data="utag_commands")]])
        )
        return


    

    if new_cmd == other_cmd:

        await message.reply_text(

            f"❌ Bu komanda boshlash komandasi (.{other_cmd}) bilan bir xil bo'lishi mumkin emas!",

            reply_markup=InlineKeyboardMarkup([

                [InlineKeyboardButton("❌ Bekor qilish", callback_data="utag_commands")]

            ])

        )

        return

    

    user_states[user_id] = f"confirming_stop|{new_cmd}"

    

    await message.reply_text(

        f"🛑 **To'xtatish Komandasini O'zgartirish**\n\n"

        f"Joriy komanda: `.{old_cmd}`\n"

        f"Yangi komanda: `.{new_cmd}`\n\n"

        f"Tasdiqlaysizmi?",

        reply_markup=InlineKeyboardMarkup([

            [

                InlineKeyboardButton("✅ Ha", callback_data="utag_save_stop"),

                InlineKeyboardButton("❌ Yo'q", callback_data="utag_commands")

            ]

        ])

    )







async def handle_new_pause_command(client: Client, message: Message, user_id: int):

    """Yangi pause komandasini qabul qilish va validatsiya"""

    is_valid, result = validate_command(message.text)

    if not is_valid:

        await message.reply_text(f"❌ {result}\n\nQayta yuboring yoki bekor qiling.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Bekor qilish", callback_data="utag_commands")]]))

        return

    

    new_cmd = _normalize_command(message.text)

    custom_cmds = await _load_custom_cmds(user_id)

    old_cmd = custom_cmds.get("pause", "pause")

    conflict = _reserved_or_conflicting_command(custom_cmds, new_cmd, "pause")
    if conflict:
        await message.reply_text(
            f"❌ {conflict}",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Bekor qilish", callback_data="utag_commands")]])
        )
        return


    

    user_states[user_id] = f"confirming_pause|{new_cmd}"

    await message.reply_text(f"⏸️ **Pauza Komandasini O'zgartirish**\n\nJoriy komanda: `.{old_cmd}`\nYangi komanda: `.{new_cmd}`\n\nTasdiqlaysizmi?", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("✅ Ha", callback_data="utag_save_pause"), InlineKeyboardButton("❌ Yo'q", callback_data="utag_commands")]]))



async def handle_new_resume_command(client: Client, message: Message, user_id: int):

    """Yangi resume komandasini qabul qilish va validatsiya"""

    is_valid, result = validate_command(message.text)

    if not is_valid:

        await message.reply_text(f"❌ {result}\n\nQayta yuboring yoki bekor qiling.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Bekor qilish", callback_data="utag_commands")]]))

        return

    

    new_cmd = _normalize_command(message.text)

    custom_cmds = await _load_custom_cmds(user_id)

    old_cmd = custom_cmds.get("resume", "resume")

    conflict = _reserved_or_conflicting_command(custom_cmds, new_cmd, "resume")
    if conflict:
        await message.reply_text(
            f"❌ {conflict}",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Bekor qilish", callback_data="utag_commands")]])
        )
        return


    

    user_states[user_id] = f"confirming_resume|{new_cmd}"

    await message.reply_text(f"▶️ **Davom Etish Komandasini O'zgartirish**\n\nJoriy komanda: `.{old_cmd}`\nYangi komanda: `.{new_cmd}`\n\nTasdiqlaysizmi?", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("✅ Ha", callback_data="utag_save_resume"), InlineKeyboardButton("❌ Yo'q", callback_data="utag_commands")]]))



async def handle_custom_utag_speed(client: Client, message: Message, user_id: int):
    """Custom UTag tezligi qiymatini qabul qilish."""
    raw = message.text.strip().replace(",", ".")
    try:
        speed = round(float(raw), 1)
    except ValueError:
        await message.reply_text(
            f"❌ Noto'g'ri format! {UTAG_SPEED_MIN}s — {UTAG_SPEED_MAX}s orasida raqam yuboring.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Bekor qilish", callback_data="utag_speed")]]),
        )
        return

    if speed < UTAG_SPEED_MIN or speed > UTAG_SPEED_MAX:
        await message.reply_text(
            f"❌ Tezlik {UTAG_SPEED_MIN}s dan {UTAG_SPEED_MAX}s gacha bo'lishi kerak!",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Bekor qilish", callback_data="utag_speed")]]),
        )
        return

    user_states.pop(user_id, None)
    if user_id not in user_settings:
        user_settings[user_id] = {}
    user_settings[user_id]["utag_speed_seconds"] = speed

    warning = f"\n\n{SPEED_WARNING}" if is_high_speed_risk(speed) else ""
    await message.reply_text(
        f"✅ **Tezlik o'zgartirildi!**\n\nYangi tezlik: {format_speed_label(speed)}{warning}",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Orqaga", callback_data="utag_settings")]]),
    )


async def handle_custom_timer(client: Client, message: Message, user_id: int):

    """Custom taymer qiymatini qabul qilish va validatsiya"""

    try:

        timer_value = int(message.text.strip())

    except ValueError:

        await message.reply_text(

            "❌ Faqat raqam kiriting!\n\n1-30 soniya orasida taymer kiriting:",

            reply_markup=InlineKeyboardMarkup([

                [InlineKeyboardButton("❌ Bekor qilish", callback_data="utag_delete_timer")]

            ])

        )

        return

    

    if timer_value < 1 or timer_value > 30:

        await message.reply_text(

            "❌ Taymer 1-30 soniya orasida bo'lishi kerak!\n\nQayta kiriting:",

            reply_markup=InlineKeyboardMarkup([

                [InlineKeyboardButton("❌ Bekor qilish", callback_data="utag_delete_timer")]

            ])

        )

        return

    

    user_states.pop(user_id, None)

    if user_id not in user_settings:

        user_settings[user_id] = {}

    user_settings[user_id]["utag_delete_timer"] = timer_value

    

    await message.reply_text(

        f"✅ **Sozlama o'zgartirildi!**\n\nXabar o'chish taymeri: {timer_value} sekund",

        reply_markup=InlineKeyboardMarkup([

            [InlineKeyboardButton("🔙 Orqaga", callback_data="utag_settings")]

        ])

    )







@Client.on_callback_query(filters.regex("^utag_save_atag$"))

async def utag_save_atag_callback(client: Client, cq: CallbackQuery):

    if not cq.from_user:

        return

    user_id = cq.from_user.id

    state = user_states.get(user_id, "")

    

    if state.startswith("confirming_atag|"):

        new_cmd = state.replace("confirming_atag|", "", 1).strip().lstrip(".").lower()

    else:

        await cq.answer("Xatolik", show_alert=True)

        return

    

    user_states.pop(user_id, None)

    

    if user_id not in user_custom_commands:

        user_custom_commands[user_id] = await get_user_utag_commands(user_id)

    user_custom_commands[user_id]["atag"] = new_cmd

    await save_user_utag_command(user_id, "atag", new_cmd)

    

    await _edit_cq(
        cq,
        f"✅ **Komanda muvaffaqiyatli o'zgartirildi!**\n\n"
        f"Yangi boshlash komandasi: .{new_cmd}",
        [[InlineKeyboardButton("🔙 Orqaga", callback_data="utag_commands")]]
    )
    await cq.answer()





@Client.on_callback_query(filters.regex("^utag_save_stop$"))

async def utag_save_stop_callback(client: Client, cq: CallbackQuery):

    if not cq.from_user:

        return

    user_id = cq.from_user.id

    state = user_states.get(user_id, "")

    

    if state.startswith("confirming_stop|"):

        new_cmd = state.replace("confirming_stop|", "", 1).strip().lstrip(".").lower()

    else:

        await cq.answer("Xatolik", show_alert=True)

        return

    

    user_states.pop(user_id, None)

    

    if user_id not in user_custom_commands:

        user_custom_commands[user_id] = await get_user_utag_commands(user_id)

    user_custom_commands[user_id]["stop"] = new_cmd

    await save_user_utag_command(user_id, "stop", new_cmd)

    

    await _edit_cq(
        cq,
        f"✅ **Komanda muvaffaqiyatli o'zgartirildi!**\n\n"
        f"Yangi to'xtatish komandasi: .{new_cmd}",
        [[InlineKeyboardButton("🔙 Orqaga", callback_data="utag_commands")]]
    )
    await cq.answer()







@Client.on_callback_query(filters.regex("^utag_save_pause$"))

async def utag_save_pause_callback(client: Client, cq: CallbackQuery):

    if not cq.from_user: return

    user_id = cq.from_user.id

    state = user_states.get(user_id, "")

    if state.startswith("confirming_pause|"):

        new_cmd = state.replace("confirming_pause|", "", 1).strip().lstrip(".").lower()

    else:

        await cq.answer("Xatolik", show_alert=True)

        return

    user_states.pop(user_id, None)

    if user_id not in user_custom_commands:

        user_custom_commands[user_id] = await get_user_utag_commands(user_id)

    user_custom_commands[user_id]["pause"] = new_cmd

    await save_user_utag_command(user_id, "pause", new_cmd)

    await _edit_cq(cq, f"✅ **Komanda muvaffaqiyatli o'zgartirildi!**\n\nYangi pauza komandasi: .{new_cmd}", [[InlineKeyboardButton("🔙 Orqaga", callback_data="utag_commands")]])
    await cq.answer()



@Client.on_callback_query(filters.regex("^utag_save_resume$"))

async def utag_save_resume_callback(client: Client, cq: CallbackQuery):

    if not cq.from_user: return

    user_id = cq.from_user.id

    state = user_states.get(user_id, "")

    if state.startswith("confirming_resume|"):

        new_cmd = state.replace("confirming_resume|", "", 1).strip().lstrip(".").lower()

    else:

        await cq.answer("Xatolik", show_alert=True)

        return

    user_states.pop(user_id, None)

    if user_id not in user_custom_commands:

        user_custom_commands[user_id] = await get_user_utag_commands(user_id)

    user_custom_commands[user_id]["resume"] = new_cmd

    await save_user_utag_command(user_id, "resume", new_cmd)

    await _edit_cq(cq, f"✅ **Komanda muvaffaqiyatli o'zgartirildi!**\n\nYangi davom etish komandasi: .{new_cmd}", [[InlineKeyboardButton("🔙 Orqaga", callback_data="utag_commands")]])
    await cq.answer()





@Client.on_message(filters.private & filters.text & ~filters.command(["start", "cancel"]), group=-6)

async def utag_state_handler(client: Client, message: Message):

    if not message.from_user:

        raise ContinuePropagation

    user_id = message.from_user.id

    state = user_states.get(user_id)



    if state == "waiting_for_new_atag_command":

        await handle_new_atag_command(client, message, user_id)

        return



    if state == "waiting_for_new_stop_command":

        await handle_new_stop_command(client, message, user_id)

        return



    if state == "waiting_for_new_pause_command":

        await handle_new_pause_command(client, message, user_id)

        return



    if state == "waiting_for_new_resume_command":

        await handle_new_resume_command(client, message, user_id)

        return



    if state == "waiting_for_custom_timer":

        await handle_custom_timer(client, message, user_id)

        return



    if state == "waiting_for_utag_speed":

        await handle_custom_utag_speed(client, message, user_id)

        return



    if state == "waiting_for_timer_chat":

        await handle_timer_chat_input(client, message, user_id)

        return

    

    if state and state.startswith("waiting_for_timer_message|"):

        await handle_timer_message_input(client, message, user_id)

        return

    

    if state and state.startswith("waiting_for_timer_interval|"):

        await handle_timer_interval_input(client, message, user_id)

        return

    

    if state and state.startswith("waiting_for_timer_repeat|"):

        await handle_timer_repeat_input(client, message, user_id)

        return

    

    # Legacy state handling - users with stale state will be reset

    if state and state.startswith("waiting_for_timer_repeat_delay|"):

        user_states.pop(user_id, None)

        await message.reply_text(

            "⚠️ Eski taymer sozlamasi aniqlandi. Iltimos, yangi taymerni qayta yarating.",

            reply_markup=InlineKeyboardMarkup([

                [InlineKeyboardButton("⏰ Taymer menyusi", callback_data="utag_timer_menu")]

            ])

        )

        return

    

    if state and state.startswith("editing_timer_"):

        await handle_timer_edit_input(client, message, user_id)

        return



    if state and (state.startswith("confirming_atag|") or state.startswith("confirming_stop|")):

        await message.reply_text(

            "⬆️ Iltimos, yuqoridagi **Ha** yoki **Yo'q** tugmasini bosing."

        )

        return



    raise ContinuePropagation