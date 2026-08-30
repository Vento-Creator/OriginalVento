import os

# WARNING: this file is committed to git and MUST stay secrets-free.
# All credentials come from environment variables (Railway Variables / .env).

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    # Deployment environments may inject environment variables directly.
    pass

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.getenv("VENTO_DATA_DIR", os.path.join(BASE_DIR, "data"))
SESSIONS_DIR = os.path.join(DATA_DIR, "sessions")
DATABASE_DIR = os.path.join(DATA_DIR, "database")
DB_PATH = os.path.join(DATABASE_DIR, "bot_database.db")

os.makedirs(SESSIONS_DIR, exist_ok=True)
os.makedirs(DATABASE_DIR, exist_ok=True)


def _required_env(name: str) -> str:
    value = os.getenv(name)
    if value is None or not value.strip():
        raise RuntimeError(
            f"Vento konfiguratsiyasi yetishmayapti: {name}. "
            f".env fayliga yoki deployment secretlariga kiriting."
        )
    return value.strip()


def _int_env(name: str, required: bool = True, default: int = 0) -> int:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        if required:
            raise RuntimeError(f"Vento konfiguratsiyasi yetishmayapti: {name}.")
        return default
    try:
        return int(raw.strip())
    except ValueError as exc:
        raise RuntimeError(f"{name} butun son bo'lishi kerak.") from exc


API_ID = _int_env("API_ID")
API_HASH = _required_env("API_HASH")
BOT_TOKEN = _required_env("BOT_TOKEN")
SUPER_ADMIN_ID = _int_env("SUPER_ADMIN_ID")
SECOND_ADMIN_ID = _int_env("SECOND_ADMIN_ID", required=False, default=0)
ADMIN_REPORT_CHAT_ID = _int_env("ADMIN_REPORT_CHAT_ID", required=False, default=0)
OWNER_ID = SUPER_ADMIN_ID
ADMIN_IDS = [SUPER_ADMIN_ID] + ([SECOND_ADMIN_ID] if SECOND_ADMIN_ID else [])
MINI_APP_URL = os.getenv("MINI_APP_URL", "https://vento-webapp.netlify.app")

# Backward-compatible config object. It intentionally contains no secrets written to disk.
config = {
    "API_ID": API_ID,
    "API_HASH": API_HASH,
    "BOT_TOKEN": BOT_TOKEN,
    "SUPER_ADMIN_ID": SUPER_ADMIN_ID,
    "SECOND_ADMIN_ID": SECOND_ADMIN_ID,
    "ADMIN_REPORT_CHAT_ID": ADMIN_REPORT_CHAT_ID,
}

# ---------------------------------------------------------------------------
# Debug / development admin bypass
# ---------------------------------------------------------------------------
# DEBUG_MODE=true — DEBUG_ADMIN_IDS ga kiritilgan ID lar ham owner sifatida
# ish olib boradi (barcha ruxsatlar beriladi). DEBUG_ADMIN_IDS ga kiritilgan
# ID lar har doim admin sifatida qabul qilinadi (masalan, shaxsiy Telegram
# ID ADMIN_IDS/DB ro'yxatiga tushmasa ham admin panelni ochish uchun).
#
# Namuna:
#   DEBUG_MODE: "true"
#   DEBUG_ADMIN_IDS: "123456789,987654321"
# yoki:
#   DEBUG_MODE=true
#   DEBUG_ADMIN_IDS=123456789,987654321


def _debug_flag(key: str, default: bool = False) -> bool:
    raw = os.getenv(key)
    if raw is not None:
        return raw.strip().lower() in ("1", "true", "yes", "on")
    value = config.get(key, default)
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in ("1", "true", "yes", "on")


def _parse_id_list(raw) -> list:
    ids = []
    if not raw:
        return ids
    if isinstance(raw, (list, tuple, set)):
        parts = raw
    else:
        parts = str(raw).replace(";", ",").split(",")
    for part in parts:
        part = str(part).strip().lstrip("@")
        try:
            val = int(part)
        except (ValueError, TypeError):
            continue
        if val > 0 and val not in ids:
            ids.append(val)
    return ids


DEBUG_ADMIN_IDS = _parse_id_list(os.getenv("DEBUG_ADMIN_IDS"))
DEBUG_ADMIN_IDS += [
    x for x in _parse_id_list(config.get("DEBUG_ADMIN_IDS")) if x not in DEBUG_ADMIN_IDS
]
DEBUG_MODE = _debug_flag("DEBUG_MODE")

async def load_admin_ids_from_db():
    """Bazadan admin ID larini yuklash"""
    global ADMIN_IDS
    from database import get_all_admins
    admins = await get_all_admins()
    db_ids = [admin["admin_id"] for admin in admins]
    for default_id in [SUPER_ADMIN_ID, SECOND_ADMIN_ID] + DEBUG_ADMIN_IDS:
        if default_id not in db_ids:
            db_ids.append(default_id)
    ADMIN_IDS.clear()
    ADMIN_IDS.extend(db_ids)
    return ADMIN_IDS

def is_admin(user_id: int) -> bool:
    if user_id in ADMIN_IDS:
        return True
    # Debug paytida qo'shimcha admin ID lar ham ishlatiladi
    return user_id in DEBUG_ADMIN_IDS

def is_owner(user_id: int) -> bool:
    if user_id == OWNER_ID:
        return True
    # Debug rejimida debug admin lar ham owner huquqiga ega
    if DEBUG_MODE and user_id in DEBUG_ADMIN_IDS:
        return True
    return False


async def has_permission(user_id: int, permission: str) -> bool:
    """Adminning ma'lum huquqiga ega ekanligini tekshirish"""
    if not is_admin(user_id):
        return False
    if is_owner(user_id):
        return True  # Owner har doim barcha huquqlarga ega
    from database import get_admin_info
    admin_info = await get_admin_info(user_id)
    if not admin_info:
        return False
    return admin_info.get(permission, False)

async def can_broadcast(user_id: int) -> bool:
    """Broadcast huquqini tekshirish"""
    return await has_permission(user_id, "can_broadcast")

async def can_ban(user_id: int) -> bool:
    """Ban huquqini tekshirish"""
    return await has_permission(user_id, "can_ban")

async def can_clear_db(user_id: int) -> bool:
    """DB tozalash huquqini tekshirish"""
    return await has_permission(user_id, "can_clear_db")

async def can_manage_users(user_id: int) -> bool:
    """User boshqarish huquqini tekshirish"""
    return await has_permission(user_id, "can_manage_users")

async def can_add_admin(user_id: int) -> bool:
    """Admin qo'shish huquqini tekshirish"""
    return await has_permission(user_id, "can_add_admin")

user_states = {}
login_data = {}
user_clients = {}
stop_flags = {}
pause_flags = {}
user_settings = {}
user_custom_commands = {}
bot_client = None
