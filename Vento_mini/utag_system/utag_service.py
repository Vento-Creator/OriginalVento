import asyncio
import logging
import time
from typing import List, Dict, Tuple
from pyrogram import Client
from pyrogram.enums import ChatAction
from pyrogram.errors import FloodWait, RPCError

logger = logging.getLogger(__name__)

# Active tag jobs: user_id -> {"stop": bool, "task": Task, "chat_id": int}
_active_utag_jobs = {}


def stop_user_utag(user_id: int) -> bool:
    job = _active_utag_jobs.get(user_id)
    if job:
        job["stop"] = True
        return True
    return False


def is_utag_running(user_id: int) -> bool:
    job = _active_utag_jobs.get(user_id)
    return bool(job and not job.get("stop", False))


class UtagService:
    @staticmethod
    async def start_tagging(
        user_id: int,
        chat_id: int,
        bot_client: Client,
        user_client: Client,
        members: List[str],
        tag_text: str = "",
        settings: Dict = None
    ) -> Tuple[bool, str]:
        if is_utag_running(user_id):
            return False, "⚠️ Sizda allaqachon UTAG jarayoni ketmoqda! Uni to'xtatish uchun /stop bosing."

        if not members:
            return False, "📭 Tag qilinadigan a'zolar topilmadi."

        settings = settings or {}
        speed = float(settings.get("utag_speed", 1.5))
        typing_sim = bool(settings.get("utag_typing", True))
        delete_timer = int(settings.get("utag_delete_timer", 0))

        job = {"stop": False, "chat_id": chat_id}
        _active_utag_jobs[user_id] = job

        # Run tagging in background task
        task = asyncio.create_task(
            UtagService._tag_loop(
                user_id, chat_id, bot_client, user_client, members, tag_text, speed, typing_sim, delete_timer, job
            )
        )
        job["task"] = task
        return True, "🚀 **UTAG boshlandi!**"

    @staticmethod
    async def _tag_loop(
        user_id: int,
        chat_id: int,
        bot_client: Client,
        user_client: Client,
        members: List[str],
        tag_text: str,
        speed: float,
        typing_sim: bool,
        delete_timer: int,
        job: Dict
    ):
        tagged_count = 0
        batch_size = 5  # Tag 5 users per message

        try:
            for i in range(0, len(members), batch_size):
                if job.get("stop", False):
                    await bot_client.send_message(user_id, f"🛑 **UTAG to'xtatildi!** Jami: {tagged_count} ta tag qilindi.")
                    break

                chunk = members[i:i + batch_size]
                mentions = " ".join([f"@{u}" if not u.startswith("@") else u for u in chunk])
                text = f"{tag_text}\n\n{mentions}".strip() if tag_text else mentions

                if typing_sim:
                    try:
                        await user_client.send_chat_action(chat_id, ChatAction.TYPING)
                    except Exception:
                        pass
                    await asyncio.sleep(0.8)

                try:
                    msg = await user_client.send_message(chat_id, text)
                    tagged_count += len(chunk)

                    # Auto delete message timer if enabled
                    if delete_timer > 0 and msg:
                        asyncio.create_task(UtagService._auto_delete_msg(user_client, chat_id, msg.id, delete_timer))

                except FloodWait as e:
                    logger.warning(f"UTAG FloodWait: {e.value} seconds")
                    await asyncio.sleep(e.value + 1)
                except RPCError as e:
                    logger.error(f"UTAG RPCError: {e}")
                    await bot_client.send_message(user_id, f"❌ UTAG to'xtadi (Xatolik: {e})")
                    break
                except Exception as e:
                    logger.error(f"UTAG unexpected error: {e}")
                    break

                await asyncio.sleep(speed)

            if not job.get("stop", False):
                await bot_client.send_message(user_id, f"✅ **UTAG muvaffaqiyatli yakunlandi!**\n\n🎯 Jami tag qilindi: {tagged_count} ta.")

        finally:
            _active_utag_jobs.pop(user_id, None)

    @staticmethod
    async def _auto_delete_msg(client: Client, chat_id: int, msg_id: int, delay: int):
        await asyncio.sleep(delay)
        try:
            await client.delete_messages(chat_id, msg_id)
        except Exception:
            pass
