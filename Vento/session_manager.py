import os
import json
import asyncio
import time
from pyrogram import Client
from pyrogram.errors import AuthKeyUnregistered, AuthKeyDuplicated, SessionExpired, SessionRevoked
from config import API_ID, API_HASH, SESSIONS_DIR, BASE_DIR
from task_supervisor import schedule_guarded

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

def get_user_lock(user_id: int) -> asyncio.Lock:
    """Returns a unique lock for the given user_id."""
    if user_id not in _user_locks:
        _user_locks[user_id] = asyncio.Lock()
    return _user_locks[user_id]

async def cleanup_idle_clients():
    """Fon rejimida ishlatilmayotgan sessiyalarni yopadi va xotiradan tozalaydi."""
    while True:
        await asyncio.sleep(600)  # Har 10 daqiqada tekshiradi
        now = time.time()
        to_remove = []
        for uid, last_used in list(_client_last_used.items()):
            if now - last_used > 1800:  # 30 daqiqa (1800 soniya) idle
                to_remove.append(uid)
                    
        for uid in to_remove:
            user_lock = get_user_lock(uid)
            async with user_lock:
                client = _user_clients.pop(uid, None)
                _client_last_used.pop(uid, None)
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


def _build_user_client(user_id: int) -> Client:
    """Create a fresh userbot Client object for the given user."""
    session_name = os.path.join(SESSIONS_DIR, f"user_{user_id}")
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


async def get_user_client(user_id: int) -> Client:
    """Foydalanuvchi sessiyasini xotirada saqlaydi va ulanishni ochiq qoldiradi."""
    global _cleanup_task
    if _cleanup_task is None:
        _cleanup_task = schedule_guarded("SessionCleanup", cleanup_idle_clients())

    # Sessiya fayli mavjudligini tekshirish
    session_file = os.path.join(SESSIONS_DIR, f"user_{user_id}.session")
    if not os.path.exists(session_file):
        raise Exception("sessiya tugagan")

    user_lock = get_user_lock(user_id)
    async with user_lock:
        _client_last_used[user_id] = time.time()

        client = _user_clients.get(user_id)
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

        client = _build_user_client(user_id)
        _user_clients[user_id] = client

        try:
            await asyncio.wait_for(client.connect(), timeout=10.0)
        except (AuthKeyUnregistered, AuthKeyDuplicated, SessionExpired, SessionRevoked):
            _user_clients.pop(user_id, None)
            _client_last_used.pop(user_id, None)
            # Sessiya faylini o'chirmaymiz - Owner panelida akkaunt qaytarish uchun kerak
            raise Exception("sessiya tugagan")
        except Exception as e:
            _user_clients.pop(user_id, None)
            _client_last_used.pop(user_id, None)
            if "sessiya" in str(e).lower() or "session" in str(e).lower():
                raise Exception("sessiya tugagan")
            raise e

        return client

async def close_user_client(user_id: int):
    """Force clear user client from memory cache - CRITICAL for logout security"""
    user_lock = get_user_lock(user_id)
    async with user_lock:
        client = _user_clients.pop(user_id, None)
        _client_last_used.pop(user_id, None)
        if client and client.is_connected:
            try:
                await asyncio.wait_for(client.disconnect(), timeout=10.0)
            except:
                pass
async def close_user_client(user_id: int):
    """Force clear user client from memory cache - CRITICAL for logout security"""
    user_lock = get_user_lock(user_id)
    async with user_lock:
        client = _user_clients.pop(user_id, None)
        _client_last_used.pop(user_id, None)
        if client and client.is_connected:
            try:
                await asyncio.wait_for(client.disconnect(), timeout=10.0)
            except:
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
