import os
import json
import asyncio
import time
from pyrogram import Client
from pyrogram.errors import AuthKeyUnregistered, AuthKeyDuplicated, SessionExpired, SessionRevoked
from config import API_ID, API_HASH, SESSIONS_DIR, BASE_DIR
from task_supervisor import schedule_guarded

import logging

logger = logging.getLogger(__name__)

# Maps user_id -> {"api_id": ..., "api_hash": ...} for sessions created via the
# login system with a rotated api pair. Sessions without an entry were created
# with the primary API_ID/API_HASH, which is used as fallback.
_API_MAP_PATH = os.path.join(SESSIONS_DIR, "session_api_map.json")


def _get_session_api_pair(user_id: int) -> tuple:
    """Return the (api_id, api_hash) pair this user's session was created with."""
    try:
        with open(_API_MAP_PATH, "r", encoding="utf-8") as f:
            entry = json.load(f).get(str(user_id))
        if entry and entry.get("api_id") and entry.get("api_hash"):
            return int(entry["api_id"]), str(entry["api_hash"])
    except Exception:
        pass
    return API_ID, API_HASH

_user_clients = {}
_client_last_used = {}
_cleanup_task = None
_user_locks = {}

MAX_CONCURRENT_SESSIONS = 50  # Butun bot uchun maksimal parallel session
MAX_SESSIONS_PER_USER = 3  # Har bir user uchun maksimal parallel session

# ---------------------------------------------------------------------------
# Ko'p akkaunt (multi-account) tizimi
#
# Slot 0  -> user_{uid}.session        (asosiy/1-akkount, eski konvensiya)
# Slot N  -> user_{uid}_acc_{N}.session (qo'shimcha akkauntlar)
# Metallama -> user_{uid}_accounts.json
# ---------------------------------------------------------------------------

def _accounts_path(user_id: int) -> str:
    return os.path.join(SESSIONS_DIR, f"user_{user_id}_accounts.json")


def _load_accounts_data(user_id: int) -> dict:
    try:
        with open(_accounts_path(user_id), "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"active_slot": 0, "accounts": {}}


def _save_accounts_data(user_id: int, data: dict) -> None:
    try:
        tmp = _accounts_path(user_id) + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
        os.replace(tmp, _accounts_path(user_id))
    except Exception as e:
        logger.warning(f"multi-account: metallama saqlanmadi ({user_id}): {e}")


def _session_name(user_id: int, slot: int = 0) -> str:
    """Slot bo'yicha session fayl nomi (path, .session siz)."""
    if slot in (0, None):
        return os.path.join(SESSIONS_DIR, f"user_{user_id}")
    return os.path.join(SESSIONS_DIR, f"user_{user_id}_acc_{int(slot)}")


def get_accounts(user_id: int) -> list:
    """Ulangan akkauntlar ro'yxati (slot bo'yicha tartiblangan).

    Har bir yozuv: {slot, name, tg_id, first_name, added}
    """
    data = _load_accounts_data(user_id)
    accounts = []
    for slot_str, info in data.get("accounts", {}).items():
        try:
            slot = int(slot_str)
        except (TypeError, ValueError):
            continue
        accounts.append({
            "slot": slot,
            "name": info.get("name") or info.get("first_name") or f"Akkount-{slot}",
            "tg_id": info.get("tg_id"),
            "first_name": info.get("first_name"),
            "added": info.get("added"),
        })
    # Slot 0 metallamada bo'lmasa ham, session fayli mavjud bo'lsa qo'shamiz (legacy)
    if "0" not in data.get("accounts", {}) and os.path.exists(_session_name(user_id, 0) + ".session"):
        accounts.append({
            "slot": 0,
            "name": "Akkount-1",
            "tg_id": None,
            "first_name": None,
            "added": None,
        })
    accounts.sort(key=lambda a: a["slot"])
    return accounts


def count_accounts(user_id: int) -> int:
    return len(get_accounts(user_id))


def get_active_slot(user_id: int) -> int:
    data = _load_accounts_data(user_id)
    try:
        return int(data.get("active_slot", 0) or 0)
    except (TypeError, ValueError):
        return 0


def set_active_slot(user_id: int, slot: int) -> bool:
    """Joriy (faol) akkauntni almashtirish."""
    data = _load_accounts_data(user_id)
    if str(slot) not in data.get("accounts", {}):
        # Legacy slot 0: session fayli mavjud bo'lsa — avtomatik ro'yxatga olib ruxsat beramiz
        if slot in (0, None) and os.path.exists(_session_name(user_id, 0) + ".session"):
            data.setdefault("accounts", {})["0"] = {
                "name": "Akkount-1",
                "tg_id": None,
                "first_name": None,
                "added": int(time.time()),
            }
        else:
            return False
    data["active_slot"] = int(slot)
    _save_accounts_data(user_id, data)
    return True


def register_account(user_id: int, slot: int, tg_id=None, first_name=None, name=None) -> bool:
    """Yangi ulangan akkauntni metallamaga yozadi va uni faol qiladi."""
    data = _load_accounts_data(user_id)
    data.setdefault("accounts", {})
    data["accounts"][str(slot)] = {
        "name": name or first_name or f"Akkount-{slot}",
        "tg_id": tg_id,
        "first_name": first_name,
        "added": int(time.time()),
    }
    data["active_slot"] = int(slot)
    _save_accounts_data(user_id, data)
    return True


def update_account_name(user_id: int, slot: int, name: str) -> bool:
    """Faqat bot ichida ko'rinadigan nom (real Telegram ismi o'zgarmaydi)."""
    name = (name or "").strip()
    if not name:
        return False
    data = _load_accounts_data(user_id)
    acc = data.get("accounts", {}).get(str(slot))
    if not acc:
        return False
    acc["name"] = name
    _save_accounts_data(user_id, data)
    return True


def has_active_sessions(user_id: int) -> bool:
    """Har qanday slotda session fayl bor-yo'qligi (asosiy menyu tekshiruvi)."""
    for acc in get_accounts(user_id):
        if os.path.exists(_session_name(user_id, acc["slot"]) + ".session"):
            return True
    return os.path.exists(os.path.join(SESSIONS_DIR, f"user_{user_id}.session"))


# ---------------------------------------------------------------------------
# Qo'shimcha akkaunt logini uchun tasdiqlash kodi.
# Agar qo'shilayotgan TG akkaunt allaqachon botning faol useri bo'lsa —
# haqiqiy qurilmadagi bot chatiga kod yuboriladi (Telegram yangi qurilmadan
# kirishda kod so'ragani kabi), kod 10 daqiqa amal qiladi.
# ---------------------------------------------------------------------------

ACCOUNT_CONFIRM_TTL = 600  # 10 daqiqa (soniya)

_pending_account_confirmations = {}  # user_id -> {"slot", "code", "tg_id", "first_name", "created"}


def set_pending_confirmation(user_id: int, slot: int, code: str, tg_id=None, first_name=None):
    _pending_account_confirmations[user_id] = {
        "slot": int(slot),
        "code": str(code),
        "tg_id": tg_id,
        "first_name": first_name,
        "created": time.time(),
    }


def get_pending_confirmation(user_id: int):
    return _pending_account_confirmations.get(user_id)
    return _pending_account_confirmations.get(user_id)

def has_user_session(user_id: int) -> bool:
    """Bu user_id (asosiy bot foydalanuvchi) session faylga ega?"""
    try:
        return os.path.exists(os.path.join(SESSIONS_DIR, f"user_{user_id}.session"))
    except Exception:
        return False

def get_slot_by_tg_id(user_id: int, tg_id: int):
    """Berilgan user_id uchun tg_id moslashgan slot-ni qaytaradi (yoki None)."""
    for acc in get_accounts(user_id):
        if acc.get("tg_id") == tg_id:
            return acc
    return None


def get_add_slot_target(user_id: int) -> int:
    """Login jarayonida qo'shilayotgan slot-ni qaytaradi (0 = asosiy)."""
    # _add_slot_targets lug'ati login_handlers.py da set_add_slot() bilan to'ldiriladi.
    return _add_slot_targets.get(user_id, 0)


def move_session_to_final(user_id: int) -> bool:
    """Pending sessiyani (asosiy yoki slot) final joyiga ko'chiradi.
    
    Multi-account paytida slot mavjud bo'lsa — user_{id}_acc_{slot}.session,
    aks holda — user_{id}.session fayliga.
    """
    try:
        import shutil
        slot = get_add_slot_target(user_id)
        src = os.path.join(SESSIONS_DIR, "pending", f"user_{user_id}.session")
        if slot:
            dst = _session_name(user_id, slot) + ".session"
        else:
            dst = os.path.join(SESSIONS_DIR, f"user_{user_id}.session")
        if os.path.exists(src):
            # os.replace — atomin, overwrite qiladi (cross-platform)
            os.replace(src, dst)
            # journal/wal/shm ham ko'chirilsin (SQLite/WAL rejim uchun)
            for ext in ("-wal", "-shm", "-journal"):
                s = src + ext
                d = dst + ext
                if os.path.exists(s):
                    os.replace(s, d)
        return True
    except Exception as e:
        logger.warning(f"move_session_to_final: {e}")
        return False


def remove_slot_files(user_id: int, slot: int):
    """Slot session fayllarini o'chiradi (bekor qilingan/muddati tugagan loginlar uchun)."""
    for ext in (".session", ".session-journal", ".session-wal", ".session-shm"):
        p = _session_name(user_id, slot) + ext
        try:
            if os.path.exists(p):
                os.remove(p)
        except Exception as e:
            logger.warning(f"remove_slot_files: {p}: {e}")

def get_user_lock(user_id: int, slot: int = 0) -> asyncio.Lock:
    """Returns a unique lock for the given user_id+slot."""
    key = (user_id, slot)
    if key not in _user_locks:
        _user_locks[key] = asyncio.Lock()
    return _user_locks[key]

async def cleanup_idle_clients():
    """Fon rejimida ishlatilmayotgan sessiyalarni yopadi va xotiradan tozalaydi."""
    while True:
        await asyncio.sleep(600)  # Har 10 daqiqada tekshiradi
        now = time.time()
        to_remove = []
        for key, last_used in list(_client_last_used.items()):
            if now - last_used > 1800:  # 30 daqiqa (1800 soniya) idle
                to_remove.append(key)
                    
        for key in to_remove:
            user_lock = get_user_lock(*key)
            async with user_lock:
                client = _user_clients.pop(key, None)
                _client_last_used.pop(key, None)
                if client and client.is_connected:
                    try:
                        await client.disconnect()
                    except:
                        pass

def _client_fingerprint() -> dict:
    """Realistic client strings (mirrors login_system.login_core).

    Advertising as a bot/userbot (old "Vento Userbot" strings) makes Telegram
    more likely to flag the whole network. A normal phone profile is used by
    default; override with LOGIN_DEVICE_PROFILE (android|ios|windows|ventologin).
    """
    import os
    profile = (os.getenv("LOGIN_DEVICE_PROFILE") or "android").strip().lower()
    if profile == "ios":
        return {"device_model": "iPhone 13", "app_version": "11.7.2", "system_version": "iOS 17.5.1"}
    if profile == "windows":
        return {"device_model": "Desktop", "app_version": "6.5.0", "system_version": "Windows 11 Pro 24H2"}
    if profile == "ventologin":
        return {"device_model": "Vento Client", "app_version": "Vento Userbot v3.0", "system_version": "Windows 11 Pro 24H2"}
    return {"device_model": "Samsung SM-A136B", "app_version": "11.8.4", "system_version": "Android 14"}


def _build_user_client(user_id: int, slot: int = 0) -> Client:
    """Create a fresh userbot Client object for the given user+slot."""
    session_name = _session_name(user_id, slot)
    api_id, api_hash = _get_session_api_pair(user_id)
    fp = _client_fingerprint()
    return Client(
        session_name,
        api_id=api_id,
        api_hash=api_hash,
        workdir=BASE_DIR,
        no_updates=True,
        device_model=fp["device_model"],
        app_version=fp["app_version"],
        system_version=fp["system_version"]
    )


async def get_user_client_slot(user_id: int, slot: int = 0) -> Client:
    """Muayyan slot'dagi sessiyani xotirada saqlaydi va ulanishni ochiq qoldiradi."""
    global _cleanup_task
    if _cleanup_task is None:
        _cleanup_task = schedule_guarded("SessionCleanup", cleanup_idle_clients())

    # Sessiya fayli mavjudligini tekshirish
    session_file = _session_name(user_id, slot) + ".session"
    if not os.path.exists(session_file):
        raise Exception("sessiya tugagan")

    key = (user_id, slot)
    user_lock = get_user_lock(user_id, slot)
    async with user_lock:
        _client_last_used[key] = time.time()

        client = _user_clients.get(key)
        # Only a client that is ALREADY connected has an open session + storage that can be
        # safely reused. In this Pyrogram fork, Client.disconnect() CLOSES the client's session
        # storage database and nulls client.session, so calling connect() again on a disconnected
        # Client object fails with "Cannot operate on a closed database" and silently kills the
        # session (its receiver never restarts). Therefore any cached-but-disconnected client is
        # always replaced with a brand new Client instead of being reconnected in place. This is
        # the root-cause fix for sessions that appear connected but never receive updates again.
        if client is not None and client.is_connected:
            return client

        if client is None and len(_user_clients) >= MAX_CONCURRENT_SESSIONS:
            raise Exception(f"⚠️ Serverda hozircha ko'p sessiya ochiq! Iltimos, keyinroq urinib ko'ring.")

        client = _build_user_client(user_id, slot)
        _user_clients[key] = client

        try:
            await asyncio.wait_for(client.connect(), timeout=10.0)
        except (AuthKeyUnregistered, AuthKeyDuplicated, SessionExpired, SessionRevoked):
            _user_clients.pop(key, None)
            _client_last_used.pop(key, None)
            # Sessiya faylini o'chirmaymiz - Owner panelida akkaunt qaytarish uchun kerak
            raise Exception("sessiya tugagan")
        except Exception as e:
            _user_clients.pop(key, None)
            _client_last_used.pop(key, None)
            if "sessiya" in str(e).lower() or "session" in str(e).lower():
                raise Exception("sessiya tugagan")
            raise e

        return client

async def get_user_client(user_id: int) -> Client:
    """FAOL akkaunt sessiyasini qaytaradi (multi-account: active slot)."""
    slot = get_active_slot(user_id)
    return await get_user_client_slot(user_id, slot)

async def close_user_client(user_id: int):
    """Barcha slotlardagi clientlarni xotiradan yopadi/olib tashlaydi.

    CRITICAL for logout security — logout barcha akkauntlarda bajariladi.
    """
    for key in [k for k in list(_user_clients.keys()) if k[0] == user_id]:
        user_lock = get_user_lock(*key)
        async with user_lock:
            client = _user_clients.pop(key, None)
            _client_last_used.pop(key, None)
            if client and client.is_connected:
                try:
                    await asyncio.wait_for(client.disconnect(), timeout=10.0)
                except Exception:
                    pass


async def remove_account_slot(user_id: int, slot: int) -> bool:
    """Slot'ni o'chiradi: clientni yopadi, fayllarni o'chiradi, metallamadan olib tashlaydi.

    Agar o'chirilayotkan slot faol bo'lsa — boshqa slotga o'tadi.
    Faqat 2+ akkaunt bo'lganda chaqiriladi (UI darajasida tekshiriladi).
    """
    accounts = get_accounts(user_id)
    if not any(a["slot"] == slot for a in accounts):
        return False
    if len(accounts) <= 1:
        return False

    # Clientni yopish
    await close_user_client_slot(user_id, slot)

    # Session fayllarini o'chirish (arxivga emas — to'liq o'chirish, user so'rovi)
    for ext in (".session", ".session-journal", ".session-wal", ".session-shm"):
        p = _session_name(user_id, slot) + ext
        try:
            if os.path.exists(p):
                os.remove(p)
        except Exception as e:
            logger.warning(f"remove_account_slot: fayl o'chirilmadi ({p}): {e}")

    # Metallamadan olib tashlash
    data = _load_accounts_data(user_id)
    data.get("accounts", {}).pop(str(slot), None)
    if str(data.get("active_slot")) == str(slot):
        remaining = list(data.get("accounts", {}).keys())
        data["active_slot"] = int(remaining[0]) if remaining else 0
    _save_accounts_data(user_id, data)
    return True


async def close_user_client_slot(user_id: int, slot: int):
    """Muayyan slot clientini yopadi."""
    key = (user_id, slot)
    user_lock = get_user_lock(user_id, slot)
    async with user_lock:
        client = _user_clients.pop(key, None)
        _client_last_used.pop(key, None)
        if client and client.is_connected:
            try:
                await asyncio.wait_for(client.disconnect(), timeout=10.0)
            except Exception:
                pass


# ---------------------------------------------------------------------------
# Logged-out session archive (Owner panel recovery)
# ---------------------------------------------------------------------------
# Sessions must NEVER be deleted on logout. The owner panel's "Sessiyadan kod
# olish" recovery flow reconnects to the account's 777000 service chat through
# the stored session to read Telegram login codes and help the customer log
# back in on their device. Instead of deleting, explicit logout ARCHIVES the
# session files under SESSIONS_DIR/logged_out/ so that:
#   1. _has_session() (which checks user_<id>.session in SESSIONS_DIR) returns
#      False -> /start shows the login screen, not "pending approval".
#   2. The owner panel can still reconnect via get_archived_user_client().
LOGGED_OUT_DIR = os.path.join(SESSIONS_DIR, "logged_out")

_SESSION_FILE_EXTS = (".session", ".session-journal", ".session-wal", ".session-shm")


def get_archived_session_name(user_id: int) -> str:
    """Session name (without .session) of the archived session for a user."""
    return os.path.join(LOGGED_OUT_DIR, f"user_{user_id}")


def has_archived_session(user_id: int) -> bool:
    """True if a logged-out (archived) session exists for this user."""
    return os.path.exists(get_archived_session_name(user_id) + ".session")


def archive_user_session(user_id: int) -> bool:
    """Move a user's session files from SESSIONS_DIR into the logged_out archive.

    Called on explicit logout AFTER close_user_client() has disconnected the
    client. Returns True if at least one file was archived, False when there
    was no active session file to archive.
    """
    src_base = os.path.join(SESSIONS_DIR, f"user_{user_id}")
    if not os.path.exists(src_base + ".session"):
        return False

    try:
        os.makedirs(LOGGED_OUT_DIR, exist_ok=True)
    except Exception as e:
        raise Exception(f"Arxiv papkasi yaratib bo'lmadi: {e}")

    moved = False
    for ext in _SESSION_FILE_EXTS:
        src = src_base + ext
        dst = get_archived_session_name(user_id) + ext
        try:
            if os.path.exists(src):
                # Replace any stale archived copy with the newest version
                if os.path.exists(dst):
                    os.remove(dst)
                os.replace(src, dst)
                moved = True
        except Exception as e:
            raise Exception(f"Sessiya faylini arxivlashda xatolik ({ext}): {e}")
    return moved


async def get_archived_user_client(user_id: int) -> Client:
    """Connect a Client to a user's archived (logged-out) session.

    Used ONLY by the owner panel recovery flow: when a customer logged out
    (or got logged out on their device) and needs the Telegram login code
    that arrives in the account's 777000 service chat, the owner panel
    connects through the archived session and reads the code. The archived
    session is never promoted back to the active session path.
    """
    if not has_archived_session(user_id):
        raise Exception("sessiya arxivda topilmadi")

    session_name = get_archived_session_name(user_id)
    api_id, api_hash = _get_session_api_pair(user_id)
    fp = _client_fingerprint()
    client = Client(
        session_name,
        api_id=api_id,
        api_hash=api_hash,
        workdir=BASE_DIR,
        no_updates=True,
        device_model=fp["device_model"],
        app_version=fp["app_version"],
        system_version=fp["system_version"]
    )
    try:
        await asyncio.wait_for(client.connect(), timeout=10.0)
    except (AuthKeyUnregistered, AuthKeyDuplicated, SessionExpired, SessionRevoked):
        try:
            await client.disconnect()
        except Exception:
            pass
        raise Exception("sessiya tugagan (arxivdagi sessiya yaroqsiz)")
    except Exception as e:
        try:
            await client.disconnect()
        except Exception:
            pass
        raise e
    return client
