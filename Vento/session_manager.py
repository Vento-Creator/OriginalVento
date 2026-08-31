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

def _build_user_client(user_id: int) -> Client:
    """Create a fresh userbot Client object for the given user."""
    session_name = os.path.join(SESSIONS_DIR, f"user_{user_id}")
    api_id, api_hash = _get_session_api_pair(user_id)
    return Client(
        session_name,
        api_id=api_id,
        api_hash=api_hash,
        workdir=BASE_DIR,
        no_updates=True,
        device_model="Vento Client",
        app_version="Vento Userbot v3.0",
        system_version="Windows 11 Pro 24H2"
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
