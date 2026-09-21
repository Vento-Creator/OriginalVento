"""
MassDM Service — Multi-Account taqsimotli ommaviy xabar yuborish.
Original Vento UI matnlari va xato klassifikatsiyasi bilan.
"""
import asyncio
import logging
import re
import time
import random
from typing import List, Dict, Tuple
from pyrogram import Client
from pyrogram.errors import (
    FloodWait, PeerFlood, UserPrivacyRestricted, RPCError,
    UserIsBlocked, UserDeactivated, PeerIdInvalid, ChatWriteForbidden,
)
from session_manager import get_accounts, get_user_client_slot
from pyrogram.types import MessageEntity
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

# --- Original Vento MassDMConstants xato turlari (kengaytirilgan, „Noma'lum sabab" kamayishi uchun) ---
# 1-muammo (premium emoji): copy_message birlamchi yo'l — forward sarlavhasiz,
# premium emoji/format server tomonidan 100% saqlanadi.
ERROR_BLOCKED = "🚫 Bloklagan (sizni bloklagan)"
ERROR_YOU_BLOCKED = "🚫 Siz bloklagansiz (blokdan chiqaring)"
ERROR_DEACTIVATED = "💀 O'chirilgan akkaunt"
ERROR_DELETED = "🗑 O'chirilgan akkaunt"
ERROR_NOT_FOUND = "❓ Topilmadi (username/ID xato)"
ERROR_USERNAME = "🔎 Username topilmadi"
ERROR_WRITE_FORBIDDEN = "🔒 Yozish taqiq (guruh/kanal)"
ERROR_PRIVACY = "🔐 Maxfiylik (kontakt emas)"
ERROR_MUTUAL = "👥 O'zaro kontakt emas"
ERROR_PREMIUM = "💎 Premium talab"
ERROR_FLOODWAIT = "⏳ Limit (FloodWait)"
ERROR_FLOOD = "🚷 Spam-cheklov (PeerFlood)"
ERROR_LIMITED = "🚷 Spam-cheklov"
ERROR_FORBIDDEN = "⛔ Taqiqlangan (FORBIDDEN)"
ERROR_PAYMENT = "💰 To'lov talab (Stars)"
ERROR_BOT = "🤖 Botga oddiy DM yozib bo'lmaydi"
ERROR_AUTH = "🔑 Sessiya eskirgan (qayta login)"
ERROR_AUTH_REVOKED = "🔑 Sessiya bekor qilingan (qayta login)"
ERROR_FORMAT = "📝 Format xatosi (entity/parse)"
ERROR_NETWORK = "📡 Tarmoq/timeout (qayta urining)"
ERROR_PHONE = "📱 Telefon raqam xatosi"
ERROR_INVITE = "🔗 Invite-havola eskirgan/xato"
ERROR_RIGHTS = "🛡 Admin huquqi yetmaydi"
ERROR_EMOJI = "✨ Premium emoji yuborib bo'lmadi"
ERROR_FILE = "📎 Fayl/media xatosi"
ERROR_SLOWMODE = "🐢 Slowmode (sekin rejim)"
ERROR_INTERDC = "🔀 DC migratsiya (qayta urining)"
ERROR_UNKNOWN = "⚠️ Noma'lum"

def _entity_to_dict(ent) -> dict:
    """MessageEntity ni dict ko'rinishida serialize qilish (copy saqlash uchun)."""
    d = {
        "type": getattr(ent.type, "name", str(ent.type)) if getattr(ent, "type", None) else None,
        "offset": getattr(ent, "offset", 0),
        "length": getattr(ent, "length", 0),
    }
    for attr in ("url", "language", "custom_emoji_id", "date_time_format"):
        val = getattr(ent, attr, None)
        if val is not None:
            if attr == "custom_emoji_id":
                # Premium emoji ID int bo'lishi shart — str bo'lsa emoji oddiyga tushib qoladi
                try:
                    d[attr] = int(val)
                except (ValueError, TypeError):
                    continue
            elif attr == "date_time_format":
                d[attr] = str(val)
            else:
                d[attr] = val
    usr = getattr(ent, "user", None)
    if usr is not None:
        try:
            d["user"] = {"id": usr.id, "is_bot": getattr(usr, "is_bot", False), "first_name": getattr(usr, "first_name", "") or ""}
        except Exception:
            pass
    ut = getattr(ent, "unix_time", None)
    if ut is not None:
        try:
            d["unix_time"] = int(ut)
        except Exception:
            pass
    return d


def _dict_to_entity(d: dict):
    """Serialized dict ni MessageEntity ga aylantirish."""
    from pyrogram.enums import MessageEntityType
    from pyrogram.types import User
    try:
        etype = MessageEntityType[d.get("type", "UNKNOWN")]
    except Exception:
        etype = MessageEntityType.UNKNOWN
    kwargs = {
        "type": etype,
        "offset": int(d.get("offset", 0)),
        "length": int(d.get("length", 0)),
    }
    if d.get("url") is not None:
        kwargs["url"] = d["url"]
    if d.get("language") is not None:
        kwargs["language"] = d["language"]
    if d.get("custom_emoji_id") is not None:
        # custom_emoji_id har doim int bo'lishi kerak (str kelishi mumkin)
        try:
            kwargs["custom_emoji_id"] = int(d["custom_emoji_id"])
        except Exception:
            pass
    if d.get("unix_time") is not None:
        try:
            kwargs["unix_time"] = int(d["unix_time"])
        except Exception:
            pass
    if d.get("date_time_format") is not None:
        kwargs["date_time_format"] = str(d["date_time_format"])
    if isinstance(d.get("user"), dict):
        try:
            ud = d["user"]
            kwargs["user"] = User(
                id=int(ud.get("id", 0)),
                is_bot=bool(ud.get("is_bot", False)),
                first_name=str(ud.get("first_name", "") or "user"),
            )
        except Exception:
            pass
    elif d.get("user_id") is not None:
        # Eski format bilan orqaga moslik
        try:
            kwargs["user"] = User(id=int(d["user_id"]), is_bot=False, first_name="user")
        except Exception:
            pass
    return MessageEntity(**kwargs)


def _entities_have_custom_emoji(entities) -> bool:
    """Serialize qilingan entities dict-listida CUSTOM_EMOJI (premium) bormi?"""
    if not entities:
        return False
    for d in entities:
        try:
            if str(d.get("type", "")).upper() == "CUSTOM_EMOJI":
                return True
        except Exception:
            continue
    return False


def _message_has_custom_emoji(msg) -> bool:
    """Pyrogram Message obyekti entities ichida CUSTOM_EMOJI (premium) bormi?"""
    try:
        for ent in (getattr(msg, "entities", None) or []):
            if getattr(getattr(ent, "type", None), "name", "").upper() == "CUSTOM_EMOJI":
                return True
    except Exception:
        pass
    return False


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
    """Xatoni foydalanuvchiga tushunarli sababga aylantiradi (original uslubda).

    Pyrogram RPCError ko'pincha shunday ko'rinadi: "Telegram says: [400 ...] - ...".
    Shuning uchun ham error nomi, ham xabar matni (pastki registrda) tekshiriladi.
    Hech biriga mos kelmasa — "Noma'lum: <ErrorNomi>" deb qaytariladi, shunda
    logda ham, UI da ham yangi turlarni ko'rib qo'shish mumkin.
    """
    error_name = type(error).__name__
    lower_name = error_name.lower()
    error_msg = str(error).lower()
    blob = f"{lower_name} {error_msg}"

    # Telegram RPC kodini ajratamiz: "[400 PEER_FLOOD]" -> "400", "peer_flood"
    rpc_code = ""
    rpc_id = ""
    try:
        m = re.search(r"\[(\d{3})\s+([A-Z0-9_]+)\]", str(error))
        if m:
            rpc_code = m.group(1)
            rpc_id = m.group(2).lower()
    except Exception:
        pass
    blob = f"{blob} {rpc_code} {rpc_id}".strip()

    # RPC ID bo'yicha to'g'ridan-to'g'ri xaritalash (eng aniq yo'l)
    _RPC_MAP = {
        "userisblocked": ERROR_BLOCKED, "bot_blocked": ERROR_BLOCKED,
        "youblockeduser": ERROR_YOU_BLOCKED, "user_blocked": ERROR_BLOCKED,
        "inputuserdeactivated": ERROR_DEACTIVATED, "user_deactivated": ERROR_DEACTIVATED,
        "inputuserdeleted": ERROR_DELETED, "user_deleted": ERROR_DELETED,
        "peeridinvalid": ERROR_NOT_FOUND, "peer_id_invalid": ERROR_NOT_FOUND,
        "useridinvalid": ERROR_NOT_FOUND, "user_id_invalid": ERROR_NOT_FOUND,
        "usernotparticipant": ERROR_NOT_FOUND, "user_not_participant": ERROR_NOT_FOUND,
        "usernotmutualcontact": ERROR_MUTUAL, "user_not_mutual_contact": ERROR_MUTUAL,
        "userprivacyrestricted": ERROR_PRIVACY, "user_privacy_restricted": ERROR_PRIVACY,
        "userbannedinchannel": ERROR_WRITE_FORBIDDEN, "user_banned_in_channel": ERROR_WRITE_FORBIDDEN,
        "chatwriteforbidden": ERROR_WRITE_FORBIDDEN, "chat_write_forbidden": ERROR_WRITE_FORBIDDEN,
        "chatadminrequired": ERROR_RIGHTS, "chat_admin_required": ERROR_RIGHTS,
        "chatadmininviteonly": ERROR_RIGHTS, "chat_admin_invite_only": ERROR_RIGHTS,
        "adminrankemojiinvalid": ERROR_RIGHTS, "useradmininvalid": ERROR_RIGHTS,
        "usernamenotoccupied": ERROR_USERNAME, "username_not_occupied": ERROR_USERNAME,
        "usernameinvalid": ERROR_USERNAME, "username_invalid": ERROR_USERNAME,
        "usernamenotfound": ERROR_USERNAME, "username_not_found": ERROR_USERNAME,
        "peerflood": ERROR_FLOOD, "peer_flood": ERROR_FLOOD,
        "users_too_much": ERROR_FLOOD, "phonenumbersflood": ERROR_FLOOD,
        "phone_numbers_flood": ERROR_FLOOD, "slowmodewait": ERROR_SLOWMODE,
        "slowmode_wait": ERROR_SLOWMODE,
        "floodwait": ERROR_FLOODWAIT, "flood_wait": ERROR_FLOODWAIT,
        "floodtestphonewait": ERROR_FLOODWAIT, "flood_test_phone_wait": ERROR_FLOODWAIT,
        "directmessagepremiumrequired": ERROR_PREMIUM,
        "direct_message_premium_required": ERROR_PREMIUM,
        "starsfeerequired": ERROR_PAYMENT, "stars_fee_required": ERROR_PAYMENT,
        "paidmediarequired": ERROR_PAYMENT, "paid_media_required": ERROR_PAYMENT,
        "paymentrequired": ERROR_PAYMENT, "botmethodinvalid": ERROR_BOT,
        "bot_method_invalid": ERROR_BOT, "botdomaininvalid": ERROR_BOT,
        "authkeyinvalid": ERROR_AUTH, "auth_key_invalid": ERROR_AUTH,
        "authkeyunregistered": ERROR_AUTH, "auth_key_unregistered": ERROR_AUTH,
        "sessionrevoked": ERROR_AUTH_REVOKED, "session_revoked": ERROR_AUTH_REVOKED,
        "sessionexpired": ERROR_AUTH, "session_expired": ERROR_AUTH,
        "filemigrate": ERROR_INTERDC, "file_migrate": ERROR_INTERDC,
        "networkmigrate": ERROR_INTERDC, "network_migrate": ERROR_INTERDC,
        "phonemigrate": ERROR_INTERDC, "phone_migrate": ERROR_INTERDC,
        "usermigrate": ERROR_INTERDC, "user_migrate": ERROR_INTERDC,
        "filereferenceexpired": ERROR_FILE, "file_reference_expired": ERROR_FILE,
        "filereferenceinvalid": ERROR_FILE, "file_reference_invalid": ERROR_FILE,
        "filetoolarge": ERROR_FILE, "file_too_large": ERROR_FILE,
        "mediasinvalid": ERROR_FILE, "media_invalid": ERROR_FILE,
        "mediagroupedinvalid": ERROR_FILE, "documentinvalid": ERROR_FILE,
        "stickerinvalid": ERROR_FILE, "sticker_invalid": ERROR_FILE,
        "externalurlinvalid": ERROR_FILE, "weblinkinvalid": ERROR_FILE,
        "customemojiinvalid": ERROR_EMOJI, "custom_emoji_invalid": ERROR_EMOJI,
        "emojiinvalid": ERROR_EMOJI, "emoji_invalid": ERROR_EMOJI,
        "messageempty": ERROR_FORMAT, "message_empty": ERROR_FORMAT,
        "messagetoolong": ERROR_FORMAT, "message_too_long": ERROR_FORMAT,
        "entityboundsinvalid": ERROR_FORMAT, "entity_bounds_invalid": ERROR_FORMAT,
        "entitylengthinvalid": ERROR_FORMAT,
        "messagenotmodified": ERROR_FORMAT, "message_not_modified": ERROR_FORMAT,
        "messagesempty": ERROR_FORMAT, "messagedeleted": ERROR_FORMAT,
        "timeout": ERROR_NETWORK, "rpcmcgetfail": ERROR_NETWORK,
        "rpc_call_fail": ERROR_NETWORK,
        "invitehashinvalid": ERROR_INVITE, "invite_hash_invalid": ERROR_INVITE,
        "invitehashexpired": ERROR_INVITE, "invite_hash_expired": ERROR_INVITE,
        "phonenumberinvalid": ERROR_PHONE, "phone_number_invalid": ERROR_PHONE,
        "phonenumberbanned": ERROR_PHONE, "phonecodeinvalid": ERROR_PHONE,
        # --- Qo'shimcha: guruh/kanal va entity bilan bog'liq xatolar ---
        "chatinvalid": ERROR_NOT_FOUND, "chat_id_invalid": ERROR_NOT_FOUND,
        "chatidempty": ERROR_NOT_FOUND, "chat_id_empty": ERROR_NOT_FOUND,
        "chatnotfound": ERROR_NOT_FOUND, "chat_not_found": ERROR_NOT_FOUND,
        "channelprivate": ERROR_NOT_FOUND, "channel_invalid": ERROR_NOT_FOUND,
        "channel_private": ERROR_NOT_FOUND, "user_not_member": ERROR_NOT_FOUND,
        "userbotrequired": ERROR_BOT, "user_is_bot": ERROR_BOT,
        "userisbot": ERROR_BOT, "botnotfound": ERROR_BOT, "botnotallowed": ERROR_BOT,
        "chatlinknotavailable": ERROR_NOT_FOUND, "chat_link_not_available": ERROR_NOT_FOUND,
        "usernotadmin": ERROR_RIGHTS, "user_not_admin": ERROR_RIGHTS,
        "chat_send_media_forbidden": ERROR_WRITE_FORBIDDEN,
        "chat_send_stickers_forbidden": ERROR_WRITE_FORBIDDEN,
        "chat_send_gifs_forbidden": ERROR_WRITE_FORBIDDEN,
        "chat_send_animation_forbidden": ERROR_WRITE_FORBIDDEN,
        "chat_send_photos_forbidden": ERROR_WRITE_FORBIDDEN,
        "chat_send_video_forbidden": ERROR_WRITE_FORBIDDEN,
        "chat_send_docs_forbidden": ERROR_WRITE_FORBIDDEN,
        "chat_send_voice_forbidden": ERROR_WRITE_FORBIDDEN,
        "chat_send_video_note_forbidden": ERROR_WRITE_FORBIDDEN,
        "chat_send_poll_forbidden": ERROR_WRITE_FORBIDDEN,
    }
    if rpc_id and rpc_id in _RPC_MAP:
        return _RPC_MAP[rpc_id]

    if any(kw in blob for kw in ["msg_wait_failed", "wait_failed", "timed out waiting",
                                  "task was destroyed", "event loop is closed",
                                  "cancelled", "cancellederror"]):
        return ERROR_NETWORK
    if "migrate" in blob or "interdc" in blob:
        return ERROR_INTERDC

    if any(kw in blob for kw in ["stars", "paid_media", "payment_required", "stellar"]) or \
       any(kw in error_name for kw in ["StarsFeeRequired", "PaidMediaRequired", "PaymentRequired"]):
        return ERROR_PAYMENT
    if any(kw in blob for kw in ["userisblocked", "user_blocked", "bot_blocked", "bot was blocked", "user blocked", "blocked", "you_blocked_user", "you blocked"]):
        if any(kw in blob for kw in ["you_blocked_user", "you blocked"]):
            return ERROR_YOU_BLOCKED
        return ERROR_BLOCKED
    if any(kw in blob for kw in ["inputuserdeactivated", "user_deactivated", "deactivated", "deleted account", "account deleted"]):
        return ERROR_DEACTIVATED
    if any(kw in blob for kw in ["peerflood", "peer flood", "too many requests", "too much", "slowmode", "slow mode", "phone_number_flood", "users_too_much", "spam"]):
        return ERROR_LIMITED
    if any(kw in blob for kw in ["userprivacyrestricted", "privacy", "can't write", "cannot write", "no mutual", "mutual contact", "not mutual", "mutual"]):
        return ERROR_MUTUAL if "mutual" in blob else ERROR_PRIVACY
    if any(kw in blob for kw in ["premium", "directmessagepremiumrequired", "non-premium"]):
        return ERROR_PREMIUM
    if any(kw in blob for kw in ["username_not_occupied", "username_invalid", "username_not_found", "usernames_empty", "invalid username"]):
        return ERROR_USERNAME
    if any(kw in blob for kw in ["peeridinvalid", "peer_id_invalid", "user not found", "user_id_invalid", "chat not found", "channel_private", "inputuserdeleted", "user_deleted", "deleted account", "account deleted"]):
        return ERROR_DELETED if any(kw in blob for kw in ["inputuserdeleted", "user_deleted", "deleted account", "account deleted"]) else ERROR_NOT_FOUND
    if any(kw in blob for kw in ["phone", "phone_number_invalid", "phone_code", "phone code"]):
        return ERROR_PHONE
    if any(kw in blob for kw in ["custom_emoji", "premium_emoji", "sticker_invalid", "emoji_invalid", "document_invalid"]):
        return ERROR_EMOJI
    if any(kw in blob for kw in ["invite", "invite_hash", "chat_invite"]):
        return ERROR_INVITE
    if any(kw in blob for kw in ["chat_admin_required", "admin_rights", "not enough rights", "chat_write_forbidden"]):
        return ERROR_RIGHTS if "admin" in blob or "rights" in blob else ERROR_WRITE_FORBIDDEN
    if any(kw in blob for kw in ["chatwriteforbidden", "write_forbidden", "write forbidden", "you can't write", "action_forbidden"]):
        return ERROR_WRITE_FORBIDDEN
    if any(kw in blob for kw in ["bot", "bot_method_invalid", "cannot send", "bots can't", "bot can't"]):
        # Faqat bot bilan bog'liq aniq holatlar (yuqoridagilar ushlanmagan bo'lsa)
        if "bot" in blob and ("invalid" in blob or "can't" in blob or "cannot" in blob or "not allowed" in blob):
            return ERROR_BOT
    if any(kw in blob for kw in ["floodwait", "flood_wait", "flood test"]):
        return ERROR_FLOODWAIT
    if any(kw in blob for kw in ["auth", "session_revoked", "session expired", "deactivated session", "unauthorized", "auth_key"]):
        if any(kw in blob for kw in ["session_revoked", "revoked"]):
            return ERROR_AUTH_REVOKED
        return ERROR_AUTH
    if any(kw in blob for kw in ["fileref", "file_reference", "upload", "file too big", "file_too_big", "photo_invalid", "video_invalid", "media_invalid", "webdocument"]):
        return ERROR_FILE
    if any(kw in blob for kw in ["bad request", "message_empty", "message empty", "message_too_long", "message too long", "entity", "parse", "markdown", "html"]):
        return ERROR_FORMAT
    if any(kw in blob for kw in ["timeout", "timed out", "network", "connection", "disconnected", "http", "proxy", "ssl", "socket", "interdc", "fileref"]):
        return ERROR_NETWORK
    if "forbidden" in blob:
        return ERROR_FORBIDDEN

    # RPC kodi bo'yicha umumiy tekshiruv (yuqoridagi aniq turlar topilmagan bo'lsa)
    if rpc_code:
        if rpc_code == "400":
            return ERROR_FORMAT
        if rpc_code == "403":
            return ERROR_FORBIDDEN
        if rpc_code in ("420", "429"):
            return ERROR_LIMITED
        if rpc_code.startswith("5"):
            return ERROR_INTERDC if "migrate" in blob else ERROR_NETWORK

    # Hech biriga mos kelmasa — xato nomini ko'rsatamiz (keyin qo'shish uchun)
    short_raw = str(error).split("\n")[0].strip()
    # "Telegram says: [400 ...] - MSG" ichidan MSG qismini ajratamiz
    short = short_raw
    if " - " in short_raw:
        short = short_raw.rsplit(" - ", 1)[-1].strip()
    short = short[:80]
    if short:
        return f"⚠️ {error_name}: {short}"
    return f"⚠️ {error_name}"


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
        entities: list | None = None,
        from_chat_id: int | None = None,
        source_msg_id: int | None = None,
        members: List[Dict] | None = None,
    ) -> Tuple[bool, str]:
        """Multi-Account MassDMni ishga tushiradi (fonda).

        entities — premium (custom) emoji saqlanishi uchun message entities
        (parse_mode=None bilan yuboriladi). from_chat_id/source_msg_id —
        kelajakdagi copy_message fallback uchun saqlanadi.
        members — qo'lda kiritilgan userlar ro'yxati ({"username": ...} ko'rinishida);
        berilmasa group_id bo'yicha bazadan o'qiladi.
        """
        if is_massdm_running(user_id):
            return False, "⚠️ Sizda allaqachon aktiv MassDM bor!"

        if members is None:
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
                members, text_message, delay, accounts, job,
                entities, from_chat_id, source_msg_id,
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
        entities: list | None = None,
        from_chat_id: int | None = None,
        source_msg_id: int | None = None,
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
            slot = worker["slot"]

            if m.get("username"):
                dest = m["username"]
                display = f"@{m['username']}"
            elif m.get("user_id"):
                dest = m["user_id"]
                display = str(m["user_id"])
            else:
                continue

            # Clientni har yuborishda "tirik" qilamiz — MassDM 30 daqiqadan
            # ortiq davom etsa ham session_manager'dagi idle cleanup bu
            # worker'ni yopib qo'ymasligi shart. get_user_client_slot():
            #  - `_client_last_used` vaqtini yangilaydi (idle hisoblanmaydi)
            #  - biron sabab yopilgan bo'lsa clientni qayta ochadi
            try:
                cli = await get_user_client_slot(user_id, slot)
                worker["client"] = cli
            except Exception as e:
                logger.warning(f"MassDM: Slot {slot} client qayta ochilmadi: {e}")
                verified_clients = [w for w in verified_clients if w["slot"] != slot]
                job["failed"] += 1
                job["errors"].append((display, "🔑 Sessiya eskirgan (qayta login)"))
                client_index += 1
                continue

            # Premium (custom) emoji saqlanishi uchun: entities bor bo'lsa,
            # parse_mode=None + entities bilan yuboramiz. Shunda premium
            # emoji oddiy holga tushib qolmaydi.
            msg_entities = None
            if entities:
                try:
                    built = [_dict_to_entity(d) for d in entities]
                    # UNKNOWN turdagi entity'larni tashlab yuboramiz —
                    # aks holda Telegram "entity" xatosi beradi.
                    built = [e for e in built if getattr(getattr(e, "type", None), "name", "") != "UNKNOWN"]
                    msg_entities = built or None
                except Exception:
                    msg_entities = None

            async def _send_one():
                # 4 pog'onali yuborish zanjiri — xabar HAR QANDAY HOLATDA
                # yetkaziladi, premium format MUMKIN QADAR saqlanadi:
                # 1) copy_message — asl nusxa (premium emoji 100% + forward
                #    sarlavhasiz). Ammo nusxa premium emoji yo'qotib
                #    yuborgani aniqlansa, nieo'chirib keyingi bosqichga o'tamiz.
                # 2) entities bilan send_message (custom emoji biriktirilgan).
                # 3) Oddiy matn (emoji oddiy qolsa ham — baribir boradi).
                # 4) Hammasi muvaffaqiyatsiz bo'lsa — tashqaridagi except'ga tushib,
                #    "Xatolik sababini ko'rish" bo'limiga yoziladi.
                last_err = None
                need_premium = _entities_have_custom_emoji(entities)
                if from_chat_id is not None and source_msg_id is not None:
                    try:
                        sent = await cli.copy_message(
                            chat_id=dest,
                            from_chat_id=from_chat_id,
                            message_id=source_msg_id,
                        )
                        # Premium emoji bor edi-u, nusxada yo'q bo'lsa —
                        # copy muvaffaqiyatsiz chiqdi deb hisoblaymiz (yoki
                        # user akkaunt emoji ko'chirolmagan). Nusxani o'chirib
                        # entities bilan yuborishga o'tamiz.
                        if need_premium and not _message_has_custom_emoji(sent):
                            try:
                                await cli.delete_messages(dest, sent.id)
                            except Exception:
                                pass
                            raise ValueError("copy premium emoji saqlamadi")
                        return sent
                    except Exception as copy_err:
                        last_err = copy_err
                        logger.warning(
                            f"MassDM: Slot {slot} copy_message xato ({dest}): "
                            f"{copy_err}. entities fallback..."
                        )
                if msg_entities:
                    try:
                        return await cli.send_message(
                            dest, text_message,
                            entities=msg_entities, parse_mode=None,
                        )
                    except Exception as ent_err:
                        last_err = ent_err
                        logger.warning(
                            f"MassDM: Slot {slot} entities bilan yuborish xato "
                            f"({dest}): {ent_err}. oddiy matn fallback..."
                        )
                # Entities'lar qurilmasa yoki ular bilan yuborilmasa —
                # oddiy matn bilan (premium emoji yo'qolsa ham yuboriladi).
                try:
                    return await cli.send_message(dest, text_message)
                except Exception as plain_err:
                    # Hatto oddiy matn ham bormasa — bu rostakamiga muammo
                    # (blok/privat/o'chirilgan...), tashqariga uzatamiz.
                    raise plain_err

            try:
                sent = await _send_one()
                job["success"] += 1
                account_stats[slot]["sent"] += 1
                worker["sent"] += 1
                job["sent_msgs"].append((slot, sent.chat.id, sent.id))


            except FloodWait as e:
                # FloodWait RPCError'ning subclass'i — shuning uchun BIRINCHI ushlanadi.
                # UI da ham sabab bilan birga sekund ko'rinsin (keyin statistika uchun).
                logger.warning(f"MassDM: Slot {slot} FloodWait {e.value}s")
                job["errors"].append((display, f"{ERROR_FLOODWAIT} ({e.value}s)"))
                await asyncio.sleep(min(e.value, 10))
                job["failed"] += 1
            except (PeerFlood, UserPrivacyRestricted, RPCError) as e:
                logger.warning(f"MassDM: Slot {slot} send error ({dest}): {e}. SpamBot tekshiruvi...")
                job["failed"] += 1
                job["errors"].append((display, classify_error(e)))

                # Soft block ehtimoli: faqat spam/limitga o'xshash xatolarda
                # SpamBot avto-tekshiruv (blok/privat xatolarda keraksiz urinish yo'q).
                blob1 = f"{type(e).__name__} {e}".lower()
                spam_like = any(
                    k in blob1
                    for k in ["peerflood", "flood", "spam", "slowmode",
                              "too many", "too much", "users_too_much"]
                )
                if spam_like:
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

            except Exception as e:
                logger.error(f"MassDM unexpected error ({dest}): {e}")
                job["errors"].append((display, classify_error(e)))
                job["failed"] += 1

            client_index += 1

            # Har bir xabardan keyin random delay (flooddan himoya, menimcha tezkor)
            rnd_del = random.uniform(MASSDM_DELAY_MIN, MASSDM_DELAY_MAX)
            logger.info(f"MassDM: Slot {slot} -> {display} ga xabar yuborildi. Keyingisi uchun delay {rnd_del:.1f}s")
            await asyncio.sleep(rnd_del)

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

