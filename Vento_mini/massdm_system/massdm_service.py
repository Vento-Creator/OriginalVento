"""
MassDM Service — Multi-Account taqsimotli ommaviy xabar yuborish.
Original Vento UI matnlari va xato klassifikatsiyasi bilan.
"""
import asyncio
import logging
import time
import random
from typing import List, Dict, Tuple
from pyrogram import Client
from pyrogram.errors import (
    FloodWait, PeerFlood, UserPrivacyRestricted, RPCError,
    UserIsBlocked, UserDeactivated, PeerIdInvalid, ChatWriteForbidden,
)
from session_manager import get_accounts, get_user_client_slot
from spambot_unlock import send_and_check_unlock
from database import get_members_by_group_paginated
from config import (
    DEFAULT_DELAY,
    MASSDM_DELAY_MIN,
    MASSDM_DELAY_MAX,
    MASSDM_PER_ACCOUNT_LIMIT,
    MASSDM_DELETE_STEP_DELAY,
)

logger = logging.getLogger(__name__)

# Active MassDM jobs: user_id -> {"stop": bool, "paused": bool, "task": Task, ...}
_active_massdm_jobs = {}
# Completed MassDM tasks: user_id -> {"errors": [(display, reason), ...]}
_completed_tasks = {}

PER_ACCOUNT_LIMIT = MASSDM_PER_ACCOUNT_LIMIT  # Telegram Premium: ~50 DM / 12h / account
DELETE_STEP_DELAY = MASSDM_DELETE_STEP_DELAY  # O'chirishda lichkalar orasidagi pauza

# --- Original Vento MassDMConstants xato turlari ---
ERROR_BLOCKED = "🚫 Blok"
ERROR_DEACTIVATED = "💀 O'chirilgan"
ERROR_NOT_FOUND = "❓ Topilmadi"
ERROR_WRITE_FORBIDDEN = "🔒 Yozish taqiq"
ERROR_PRIVACY = "🔐 Maxfiylik"
ERROR_PREMIUM = "💎 Premium talab"
ERROR_FLOODWAIT = "⏳ Limit"
ERROR_FORBIDDEN = "⛔ Taqiqlangan"
ERROR_PAYMENT = "💰 To'lov talab"
ERROR_UNKNOWN = "⚠️ Noma'lum"

# --- Original Vento MassDMSettings.messages ---
MESSAGES = {
    "select_group": "📁 **Bazani tanlang**\n\nQaysi bazadan userlarga xabar yuborasiz?",
    "enter_message": "✍️ **Xabarni kiriting**\n\nYubormoqchi bo'lgan xabaringizni yozing:",
    "confirm_start": "🚀 **Tasdiqlash**\n\nXabar yuborishni boshlaysizmi?",
    "progress": "📊 **Yuborilmoqda**\n\n✅ Muvaffaqiyat: {success}\n❌ Xatolar: {failed}\n⏳ Progress: {progress}%",
    "completed": "✅ **Tugatildi**\n\n✅ Muvaffaqiyat: {success}\n❌ Xatolar: {failed}\n📊 Jami: {total}{remaining}",
    "stopped": "⏸️ **To'xtatildi**\n\n✅ Muvaffaqiyat: {success}\n❌ Xatolar: {failed}\n📊 Jami: {total}{remaining}",
    "no_groups": "📭 **Bazalar yo'q**\n\nAvval bazani yig'ish kerak.",
    "no_members": "📭 **A'zolar yo'q**\n\nBu bazada a'zolar yo'q.",
    "session_error": "🔑 **Sessiya xatosi**\n\nIltimos, qaytadan login qiling.",
}


def classify_error(error: Exception) -> str:
    """Xatoni foydalanuvchiga tushunarli sababga aylantiradi (original uslubda)."""
    error_name = type(error).__name__
    error_msg = str(error).lower()

    if any(kw in error_msg for kw in ["stars", "paid_media", "payment_required", "stellar"]) or \
       any(kw in error_name for kw in ["StarsFeeRequired", "PaidMediaRequired", "PaymentRequired"]):
        return ERROR_PAYMENT
    if "blocked" in error_msg or "UserIsBlocked" in error_name:
        return ERROR_BLOCKED
    if "deactivated" in error_msg or "InputUserDeactivated" in error_name:
        return ERROR_DEACTIVATED
    if "privacy" in error_msg or "UserPrivacyRestricted" in error_name:
        return ERROR_PRIVACY
    if "premium" in error_msg or "DirectMessagePremiumRequired" in error_name:
        return ERROR_PREMIUM
    if "not found" in error_msg or "PeerIdInvalid" in error_name:
        return ERROR_NOT_FOUND
    if "write_forbidden" in error_msg or "ChatWriteForbidden" in error_name:
        return ERROR_WRITE_FORBIDDEN
    if "FloodWait" in error_name:
        return ERROR_FLOODWAIT
    if "forbidden" in error_msg or "Forbidden" in error_name:
        return ERROR_FORBIDDEN
    return ERROR_UNKNOWN


def stop_user_massdm(user_id: int) -> bool:
    job = _active_massdm_jobs.get(user_id)
    if job:
        job["stop"] = True
        return True
    return False


def pause_user_massdm(user_id: int) -> bool:
    """Pauzani toggle qiladi. Qaytaradi: True = pauzada, False = ishlayapti."""
    job = _active_massdm_jobs.get(user_id)
    if job:
        job["paused"] = not job.get("paused", False)
        return job["paused"]
    return False


def is_massdm_running(user_id: int) -> bool:
    job = _active_massdm_jobs.get(user_id)
    return bool(job and not job.get("stop", False))


def get_completed_errors(user_id: int):
    completed = _completed_tasks.get(user_id)
    if completed:
        return completed.get("errors")
    job = _active_massdm_jobs.get(user_id)
    if job:
        return job.get("errors", [])
    return None


def get_completed_sent_count(user_id: int) -> int:
    """O'chirish uchun saqlangan yuborilgan habarlar soni."""
    completed = _completed_tasks.get(user_id)
    if completed:
        return len(completed.get("sent_msgs") or [])
    return 0


class MassDMService:
    @staticmethod
    async def start_massdm(
        user_id: int,
        bot_client: Client,
        chat_id: int,
        status_msg_id: int,
        group_id: str,
        text_message: str,
        delay: float = DEFAULT_DELAY,
    ) -> Tuple[bool, str]:
        """Multi-Account MassDMni ishga tushiradi (fonda)."""
        if is_massdm_running(user_id):
            return False, "⚠️ Sizda allaqachon aktiv MassDM bor!"

        members = await get_members_by_group_paginated(group_id, 0, 10000)
        if not members:
            return False, MESSAGES["no_members"]

        accounts = get_accounts(user_id)
        if not accounts:
            return False, "❌ Botga ulangan akkauntlar topilmadi. Avval akkaunt ulang."

        job = {
            "stop": False,
            "paused": False,
            "errors": [],
            "sent_msgs": [],   # (slot, peer_id, message_id) — o'chirish uchun
            "success": 0,
            "failed": 0,
            "total": len(members),
            "group_id": group_id,
        }
        _active_massdm_jobs[user_id] = job

        task = asyncio.create_task(
            MassDMService._distribute_massdm(
                user_id, bot_client, chat_id, status_msg_id,
                members, text_message, delay, accounts, job
            )
        )
        job["task"] = task
        return True, "🚀 **MassDM boshlandi!**"

    @staticmethod
    async def _distribute_massdm(
        user_id: int,
        bot_client: Client,
        chat_id: int,
        status_msg_id: int,
        members: List[Dict],
        text_message: str,
        delay: float,
        accounts: List[Dict],
        job: Dict,
    ):
        total = job["total"]

        # Barcha akkauntlar klientlarini tayyorlash
        verified_clients = []
        for acc in accounts:
            slot = acc["slot"]
            try:
                cli = await get_user_client_slot(user_id, slot)
                if cli and cli.is_connected:
                    verified_clients.append({
                        "slot": slot,
                        "client": cli,
                        "name": acc["name"],
                        "sent": 0,
                        "spam_checks": 0,
                    })
            except Exception as e:
                logger.warning(f"MassDM: Slot {slot} client olinmadi: {e}")

        account_stats = {
            w["slot"]: {"name": w["name"], "sent": 0, "status": "▶️ Faol"}
            for w in verified_clients
        }
        for acc in accounts:
            if acc["slot"] not in account_stats:
                account_stats[acc["slot"]] = {
                    "name": acc["name"], "sent": 0, "status": "⛔️ Sessiya xato"
                }

        last_update_time = 0.0
        client_index = 0

        for m in members:
            # Pauza tekshiruvi
            while job.get("paused") and not job.get("stop"):
                await asyncio.sleep(1.0)

            if job.get("stop"):
                break

            if not verified_clients:
                logger.error("MassDM: faol klient qolmadi, to'xtatildi")
                break

            # Limitga yetgan klientlarni chiqarib tashlash
            verified_clients = [
                w for w in verified_clients
                if account_stats[w["slot"]]["sent"] < PER_ACCOUNT_LIMIT
            ]
            if not verified_clients:
                remaining = total - job["success"] - job["failed"]
                logger.warning(f"MassDM: barcha akkauntlar limitga yetdi, {remaining} ta user qoldi")
                # Qolgan userlar haqida job'ga yozish
                job["remaining"] = remaining
                break

            worker = verified_clients[client_index % len(verified_clients)]
            cli = worker["client"]
            slot = worker["slot"]

            if m.get("username"):
                dest = m["username"]
                display = f"@{m['username']}"
            elif m.get("user_id"):
                dest = m["user_id"]
                display = str(m["user_id"])
            else:
                continue

            try:
                sent = await cli.send_message(dest, text_message)
                job["success"] += 1
                account_stats[slot]["sent"] += 1
                worker["sent"] += 1
                job["sent_msgs"].append((slot, sent.chat.id, sent.id))


            except (PeerFlood, UserPrivacyRestricted, RPCError) as e:
                logger.warning(f"MassDM: Slot {slot} send error ({dest}): {e}. SpamBot tekshiruvi...")
                job["failed"] += 1
                job["errors"].append((display, classify_error(e)))

                # Soft block ehtimoli: SpamBot avto-tekshiruv (2 marta)
                unlocked = await send_and_check_unlock(cli, max_attempts=2)
                if not unlocked:
                    worker["spam_checks"] += 1
                    if worker["spam_checks"] >= 2:
                        account_stats[slot]["status"] = "⛔️ Spam (Cheklangan)"
                        account_stats[slot]["sent"] = PER_ACCOUNT_LIMIT  # slotni chiqarish
                    else:
                        account_stats[slot]["status"] = "🔄 SpamBot Tekshirilmoqda"
                else:
                    account_stats[slot]["status"] = "✅ Toza (Qayta tiklandi)"

            except FloodWait as e:
                logger.warning(f"MassDM: Slot {slot} FloodWait {e.value}s")
                job["errors"].append((display, ERROR_FLOODWAIT))
                await asyncio.sleep(min(e.value, 10))
                job["failed"] += 1
            except Exception as e:
                logger.error(f"MassDM unexpected error ({dest}): {e}")
                job["errors"].append((display, classify_error(e)))
                job["failed"] += 1

            client_index += 1

            # Har 4 soniyada live UI yangilash (original format)
            if time.time() - last_update_time > 4.0:
                last_update_time = time.time()
                done = job["success"] + job["failed"]
                percent = int((done / total) * 100) if total > 0 else 0
                # Har birakkauntning holatini qo'shish
                account_lines = []
                for slot in sorted(account_stats.keys()):
                    st = account_stats[slot]
                    account_lines.append(f"  {st['status']} {st['name']}: {st['sent']}/{PER_ACCOUNT_LIMIT}")
                accounts_text = "\n".join(account_lines)
                try:
                    await bot_client.edit_message_text(
                        chat_id, status_msg_id,
                        MESSAGES["progress"].format(
                            success=job["success"],
                            failed=job["failed"],
                            progress=percent,
                        )
                        + f"\n\n📱 **Akkauntlar:**\n{accounts_text}",
                    )
                except Exception:
                    pass

            await asyncio.sleep(delay + random.uniform(0, 1.0))

        # Yakuniy SpamBot pulse tekshiruvi
        for worker in verified_clients:
            asyncio.create_task(send_and_check_unlock(worker["client"], max_attempts=1))

        _active_massdm_jobs.pop(user_id, None)
        _completed_tasks[user_id] = {
            "errors": job["errors"],
            "sent_msgs": job.get("sent_msgs", []),
        }

        remaining_count = job.get("remaining", 0)
        remaining_warn = f"\n\n⚠️ **{remaining_count} ta userga xabar yuborilmadi!** Chunki barcha akkauntlar limitga yetdi." if remaining_count > 0 else ""

        if job.get("stop"):
            final_text = MESSAGES["stopped"].format(
                success=job["success"], failed=job["failed"], total=total, remaining=remaining_warn
            )
        else:
            final_text = MESSAGES["completed"].format(
                success=job["success"], failed=job["failed"], total=total, remaining=remaining_warn
            )

        from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
        final_rows = []
        if job.get("sent_msgs"):
            final_rows.append([InlineKeyboardButton("🗑 Habarlarni o'chirish", callback_data="massdm_del_opts")])
        if job["failed"] > 0:
            final_rows.append([InlineKeyboardButton("❌ Xatolik sababini ko'rish", callback_data="massdm_errors_0")])
        final_kb = InlineKeyboardMarkup(final_rows) if final_rows else None

        try:
            await bot_client.edit_message_text(
                chat_id, status_msg_id, final_text, reply_markup=final_kb
            )
        except Exception:
            await bot_client.send_message(chat_id, final_text, reply_markup=final_kb)

    @staticmethod
    async def run_deletion(
        user_id: int,
        bot_client: Client,
        chat_id: int,
        status_msg_id: int,
        revoke: bool,
        full_history: bool,
    ):
        """MassDM orqali yuborilgan habarlarni o'chirish.

        revoke=True  -> ikkala tomon uchun o'chirish
        revoke=False -> faqat o'zingiz uchun o'chirish
        full_history -> butun lichka tarixini o'chirish (delete_history)
        """
        completed = _completed_tasks.get(user_id)
        sent_msgs = list((completed or {}).get("sent_msgs") or [])

        if not sent_msgs:
            try:
                await bot_client.edit_message_text(
                    chat_id, status_msg_id,
                    "📭 O'chirish uchun yuborilgan habarlar topilmadi.",
                )
            except Exception:
                pass
            return

        # slot -> peer_id -> {msg_ids}
        per_account: Dict[int, Dict[int, set]] = {}
        for slot, peer, mid in sent_msgs:
            per_account.setdefault(slot, {}).setdefault(peer, set()).add(mid)

        total_peers = sum(len(peers) for peers in per_account.values())
        done = 0
        errors = 0

        try:
            for slot, peers in per_account.items():
                try:
                    cli = await get_user_client_slot(user_id, slot)
                except Exception as e:
                    logger.warning(f"Delete: slot {slot} client olinmadi: {e}")
                    done += len(peers)
                    errors += len(peers)
                    continue

                for peer, mids in peers.items():
                    try:
                        if full_history:
                            await cli.delete_chat_history(peer, revoke=revoke)
                        else:
                            ids = sorted(mids)
                            for i in range(0, len(ids), 100):
                                await cli.delete_messages(peer, ids[i:i + 100], revoke=revoke)
                    except FloodWait as e:
                        logger.warning(f"Delete: FloodWait {e.value}s")
                        await asyncio.sleep(min(e.value, 30))
                    except Exception as e:
                        logger.warning(f"Delete error slot {slot} peer {peer}: {e}")
                        errors += 1

                    done += 1
                    try:
                        await bot_client.edit_message_text(
                            chat_id, status_msg_id,
                            f"🗑 **O'chirilmoqda...**\n\n"
                            f"🗂 Tozalangan lichkalar: {done} / {total_peers}",
                        )
                    except Exception:
                        pass
                    await asyncio.sleep(DELETE_STEP_DELAY)
        finally:
            # Qayta o'chirilmasligi uchun ro'yxatni tozalaymiz
            if completed is not None:
                completed["sent_msgs"] = []

        side_text = "👥 Ikkala tomon uchun" if revoke else "🙋 Faqat o'zingiz uchun"
        scope_text = "💣 Butun lichka tarixi" if full_history else "🧹 Faqat reklama habari"

        final_text = (
            "✅ **Habarlar o'chirildi!**\n\n"
            f"🗑 Usul: {side_text} · {scope_text}\n"
            f"🗂 Tozalangan lichkalar: {done} ta\n"
            f"❌ Xatoliklar: {errors} ta"
        )
        try:
            await bot_client.edit_message_text(chat_id, status_msg_id, final_text)
        except Exception:
            pass

