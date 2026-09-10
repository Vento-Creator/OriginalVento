import os
import asyncio
import logging
from pyrogram import Client
from pyrogram.errors import PhoneCodeInvalid, PhoneCodeExpired, SessionPasswordNeeded, PasswordHashInvalid
from config import API_ID, API_HASH, SESSIONS_DIR, DEVICE_MODEL, APP_VERSION, SYSTEM_VERSION

logger = logging.getLogger(__name__)

# State cache: user_id -> {"client": Client, "phone_code_hash": str, "phone": str, "slot": int}
_pending_logins = {}


def get_pending_login(user_id: int) -> dict:
    return _pending_logins.get(user_id)


def clear_pending_login(user_id: int):
    login_data = _pending_logins.pop(user_id, None)
    if login_data and login_data.get("client"):
        try:
            asyncio.create_task(login_data["client"].disconnect())
        except Exception:
            pass


async def start_login_phone(user_id: int, phone: str, slot: int = 0) -> dict:
    """Telefon raqamiga kod yuborish."""
    clear_pending_login(user_id)

    session_name = f"pending_user_{user_id}_slot_{slot}"
    pending_path = os.path.join(SESSIONS_DIR, session_name)

    # Remove existing pending session files if any
    for ext in (".session", ".session-journal", ".session-wal", ".session-shm"):
        p = pending_path + ext
        if os.path.exists(p):
            try:
                os.remove(p)
            except Exception:
                pass

    client = Client(
        session_name,
        api_id=API_ID,
        api_hash=API_HASH,
        workdir=SESSIONS_DIR,
        device_model=DEVICE_MODEL,
        app_version=APP_VERSION,
        system_version=SYSTEM_VERSION
    )

    await client.connect()
    sent_code = await client.send_code(phone)

    _pending_logins[user_id] = {
        "client": client,
        "phone_code_hash": sent_code.phone_code_hash,
        "phone": phone,
        "slot": slot,
        "pending_path": pending_path
    }
    return {"status": "code_sent"}


async def submit_login_code(user_id: int, code: str) -> dict:
    """Kodni kiritish."""
    data = get_pending_login(user_id)
    if not data or not data.get("client"):
        raise Exception("Login seans vaqti tugagan. Qaytadan telefon raqamingizni yuboring.")

    client: Client = data["client"]
    phone = data["phone"]
    phone_code_hash = data["phone_code_hash"]

    try:
        signed_in = await client.sign_in(phone, phone_code_hash, code)
        return {"status": "success", "user": signed_in}
    except SessionPasswordNeeded:
        return {"status": "2fa_required"}
    except (PhoneCodeInvalid, PhoneCodeExpired) as e:
        raise Exception("❌ Tasdiqlash kodi noto'g'ri yoki muddati o'tgan!")


async def submit_2fa_password(user_id: int, password: str) -> dict:
    """2FA parolni kiritish."""
    data = get_pending_login(user_id)
    if not data or not data.get("client"):
        raise Exception("Login seans vaqti tugagan. Qaytadan telefon raqamingizni yuboring.")

    client: Client = data["client"]
    try:
        signed_in = await client.check_password(password)
        return {"status": "success", "user": signed_in}
    except PasswordHashInvalid:
        raise Exception("❌ 2FA paroli noto'g'ri!")


async def finalize_login_session(user_id: int, slot: int = 0) -> str:
    """Login muvaffaqiyatli yakunlangach session faylini joyiga ko'chirish."""
    data = get_pending_login(user_id)
    if not data or not data.get("client"):
        return ""

    client: Client = data["client"]
    try:
        await client.disconnect()
    except Exception:
        pass

    pending_path = data["pending_path"]
    from session_manager import _session_name
    final_path = _session_name(user_id, slot)

    for ext in ("", "-journal", "-wal", "-shm"):
        src = pending_path + ".session" + ext if ext else pending_path + ".session"
        dst = final_path + ".session" + ext if ext else final_path + ".session"
        if os.path.exists(src):
            os.replace(src, dst)

    _pending_logins.pop(user_id, None)
    return final_path
