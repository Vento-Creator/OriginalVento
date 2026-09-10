import os
import json
import time
import asyncio
import logging
from typing import List, Dict, Optional
from pyrogram import Client
from config import API_ID, API_HASH, SESSIONS_DIR, BASE_DIR, DEVICE_MODEL, APP_VERSION, SYSTEM_VERSION

logger = logging.getLogger(__name__)

_user_clients = {}
_client_last_used = {}
_user_locks = {}

MAX_CONCURRENT_SESSIONS = 50
MAX_SESSIONS_PER_USER = 20  # Har bir user uchun maksimal parallel session


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
        logger.warning(f"session_manager: metallama saqlanmadi ({user_id}): {e}")


def _session_name(user_id: int, slot: int = 0) -> str:
    if slot in (0, None):
        return os.path.join(SESSIONS_DIR, f"user_{user_id}")
    return os.path.join(SESSIONS_DIR, f"user_{user_id}_acc_{int(slot)}")


def get_accounts(user_id: int) -> List[Dict]:
    """Ulangan akkauntlar ro'yxati."""
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
    """FAOL slotni o'zgartirish (SINXRON FUNKSIYA, await ISHLATILMAYDI!)."""
    data = _load_accounts_data(user_id)
    if str(slot) not in data.get("accounts", {}):
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


def get_user_lock(user_id: int, slot: int = 0) -> asyncio.Lock:
    key = (user_id, slot)
    if key not in _user_locks:
        _user_locks[key] = asyncio.Lock()
    return _user_locks[key]


def _build_user_client(user_id: int, slot: int = 0) -> Client:
    session_name = _session_name(user_id, slot)
    return Client(
        session_name,
        api_id=API_ID,
        api_hash=API_HASH,
        workdir=BASE_DIR,
        no_updates=True,
        device_model=DEVICE_MODEL,
        app_version=APP_VERSION,
        system_version=SYSTEM_VERSION
    )


async def get_user_client_slot(user_id: int, slot: int = 0) -> Client:
    session_file = _session_name(user_id, slot) + ".session"
    if not os.path.exists(session_file):
        raise Exception("Sessiya topilmadi yoki tugagan!")

    key = (user_id, slot)
    user_lock = get_user_lock(user_id, slot)
    async with user_lock:
        _client_last_used[key] = time.time()

        client = _user_clients.get(key)
        if client is not None and client.is_connected:
            return client

        client = _build_user_client(user_id, slot)
        _user_clients[key] = client

        try:
            await asyncio.wait_for(client.connect(), timeout=10.0)
        except Exception as e:
            _user_clients.pop(key, None)
            _client_last_used.pop(key, None)
            raise e

        return client


async def get_user_client(user_id: int) -> Client:
    """FAOL (active) slot clientini qaytaradi."""
    slot = get_active_slot(user_id)
    return await get_user_client_slot(user_id, slot)


async def close_user_client_slot(user_id: int, slot: int):
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


async def remove_account_slot(user_id: int, slot: int) -> bool:
    accounts = get_accounts(user_id)
    if not any(a["slot"] == slot for a in accounts):
        return False
    if len(accounts) <= 1:
        return False

    await close_user_client_slot(user_id, slot)

    for ext in (".session", ".session-journal", ".session-wal", ".session-shm"):
        p = _session_name(user_id, slot) + ext
        try:
            if os.path.exists(p):
                os.remove(p)
        except Exception as e:
            logger.warning(f"remove_account_slot: {p}: {e}")

    data = _load_accounts_data(user_id)
    data.get("accounts", {}).pop(str(slot), None)
    if str(data.get("active_slot")) == str(slot):
        remaining = list(data.get("accounts", {}).keys())
        data["active_slot"] = int(remaining[0]) if remaining else 0
    _save_accounts_data(user_id, data)
    return True
