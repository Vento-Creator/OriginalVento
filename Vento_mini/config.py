import os
from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, ".env"))

API_ID = int(os.getenv("API_ID", "0") or "0")
API_HASH = os.getenv("API_HASH", "").strip()
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()

# Admin IDs (comma-separated integers in env)
ADMIN_IDS = [
    int(x.strip())
    for x in os.getenv("ADMIN_IDS", "").split(",")
    if x.strip().isdigit()
]

SESSIONS_DIR = os.path.join(BASE_DIR, "sessions")
DATA_DIR = os.path.join(BASE_DIR, "data")
DB_PATH = os.path.join(DATA_DIR, "vento_mini.db")

# --- MassDM sozlamalari (.env orqali o'zgartiriladi) ---
# Xabarlar orasidagi pauza TASODIFIY [MIN; MAX] sekund oralig'ida tanlanadi —
# shu tarzda Telegram uchun "mashina ritmi" ko'rinmaydi.
# MIN=3, MAX=10 bo'lsa: o'rtacha ≈ 6.5s, maksimal 10s, minimal 3s.
MASSDM_DELAY_MIN = float(os.getenv("MASSDM_DELAY_MIN", "3.0") or "3.0")
MASSDM_DELAY_MAX = float(os.getenv("MASSDM_DELAY_MAX", os.getenv("MASSDM_DELAY", "10.0")) or "10.0")
DEFAULT_DELAY: float = round((MASSDM_DELAY_MIN + MASSDM_DELAY_MAX) / 2, 1)
if MASSDM_DELAY_MAX < MASSDM_DELAY_MIN:
    MASSDM_DELAY_MIN, MASSDM_DELAY_MAX = MASSDM_DELAY_MAX, MASSDM_DELAY_MIN
# Har bir Premium akkauntning 12 soatlik xabar limiti.
MASSDM_PER_ACCOUNT_LIMIT = int(os.getenv("MASSDM_PER_ACCOUNT_LIMIT", "50") or "50")
# O'chirish jarayonida lichkalar orasidagi pauza (sekund).
MASSDM_DELETE_STEP_DELAY = float(os.getenv("MASSDM_DELETE_STEP_DELAY", "0.5") or "0.5")

# --- Akkaunt fingerprinti (Telegram login paytida yuboriladi) ---
DEVICE_MODEL = os.getenv("DEVICE_MODEL", "Samsung SM-A136B")
APP_VERSION = os.getenv("APP_VERSION", "11.8.4")
SYSTEM_VERSION = os.getenv("SYSTEM_VERSION", "Android 14")

os.makedirs(SESSIONS_DIR, exist_ok=True)
os.makedirs(DATA_DIR, exist_ok=True)

# User settings defaults
DEFAULT_USER_SETTINGS = {
    "utag_speed": 0.8,
    "utag_typing": True,
    "utag_auto_stop": False,
    "utag_delete_timer": 0,  # 0 means don't delete
}

user_settings = {}
