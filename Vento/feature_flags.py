"""
Vento — universal feature flags tizimi.

- `user_feature_flags` jadvali: foydalanuvchi bo'yicha toggle (yozuv yo'q = yoqilgan).
- `bot_settings` jadvali: global toggle (admin boshqaradi, hamma uchun).
- Anti-flood: cheklangan funksiyani 30 soniyada 3 martadan ko'p ishlatishga
  urinsa, bot 30 daqiqa davomida o'sha foydalanuvchiga umuman javob bermaydi
  (mute holati xotirada saqlanadi, DB yuklamasiz).

Unumdorlik: flaglar keshlanadi (user: 60s, global: 30s TTL), shuning uchun
komanda bajarilishida DB so'rovi bo'lmaydi. DB xatosida fail-open (funckiya
yoqilgan deb hisoblanadi) — bot ishlashi buzilmaydi.
"""

import logging
import time
from typing import Dict, Optional, Tuple

from config import is_admin, SUPER_ADMIN_ID
from database import get_db_connection
from pyrogram.types import CallbackQuery, Message

logger = logging.getLogger(__name__)

# ------------------------- Funksiyalar ro'yxati -------------------------

FEATURES = {
    "utag": "🏷 Utag",
    "scraper": "🔍 Scraper",
    "massdm": "📨 Mass DM",
    "chat": "💬 Anonim chat",
}

# ------------------------- Anti-flood sozlamalari -------------------------

WARN_WINDOW_SECONDS = 30      # oyna davomiyligi
MAX_WARNINGS_PER_WINDOW = 3   # oyna ichida ko'rsatiladigan ogohlantirish limiti
MUTE_SECONDS = 1800           # limit oshsa — yarim soatga jim

# ------------------------- Kesh sozlamalari -------------------------

USER_FLAG_CACHE_TTL = 60.0
GLOBAL_FLAG_CACHE_TTL = 30.0
MANAGER_CACHE_TTL = 30.0

_user_flag_cache: Dict[Tuple[int, str], Tuple[bool, float]] = {}
_global_flag_cache: Dict[str, Tuple[bool, float]] = {}
_manager_cache: Dict[int, Tuple[bool, float]] = {}
_flood_state: Dict[int, dict] = {}
_tables_ready = False

# ------------------------- DB -------------------------

async def _ensure_tables() -> None:
    """Jadvallarni birinchi kerak bo'lganda yaratadi (lazy)."""
    global _tables_ready
    if _tables_ready:
        return
    try:
        async with get_db_connection() as db:
            await db.execute('''
                CREATE TABLE IF NOT EXISTS user_feature_flags (
                    user_id BIGINT NOT NULL,
                    feature TEXT NOT NULL,
                    enabled INTEGER NOT NULL DEFAULT 1,
                    updated_at BIGINT,
                    PRIMARY KEY (user_id, feature)
                )
            ''')
            await db.execute('''
                CREATE TABLE IF NOT EXISTS bot_settings (
                    key TEXT PRIMARY KEY,
                    value TEXT
                )
            ''')
        _tables_ready = True
    except Exception as e:
        logger.error(f"feature_flags: jadvallar yaratilmadi: {e}")


def _global_settings_key(feature: str) -> str:
    return f"feature_enabled_{feature}"


async def get_global_flag(feature: str) -> Optional[bool]:
    """Global flag qiymati. None = DB'da yozuv yo'q (default: yoqilgan)."""
    now = time.time()
    cached = _global_flag_cache.get(feature)
    if cached and now - cached[1] < GLOBAL_FLAG_CACHE_TTL:
        return cached[0]

    try:
        await _ensure_tables()
        async with get_db_connection() as db:
            row = await db.fetchrow(
                "SELECT value FROM bot_settings WHERE key = $1",
                _global_settings_key(feature),
            )
    except Exception as e:
        logger.error(f"feature_flags: global flag o'qilmadi ({feature}): {e}")
        return None  # fail-open

    value: Optional[bool]
    if row is None:
        value = None
    else:
        value = str(row["value"]) == "1"

    _global_flag_cache[feature] = (value, now)
    return value


async def get_user_flag(user_id: int, feature: str) -> Optional[bool]:
    """Foydalanuvchi flagi. None = yozuv yo'q (default: yoqilgan)."""
    key = (user_id, feature)
    now = time.time()
    cached = _user_flag_cache.get(key)
    if cached and now - cached[1] < USER_FLAG_CACHE_TTL:
        return cached[0]

    try:
        await _ensure_tables()
        async with get_db_connection() as db:
            row = await db.fetchrow(
                "SELECT enabled FROM user_feature_flags WHERE user_id = $1 AND feature = $2",
                user_id, feature,
            )
    except Exception as e:
        logger.error(f"feature_flags: user flag o'qilmadi ({user_id}/{feature}): {e}")
        return None  # fail-open

    value: Optional[bool]
    if row is None:
        value = None
    else:
        value = bool(row["enabled"])

    _user_flag_cache[key] = (value, now)
    return value


async def is_feature_enabled(user_id: int, feature: str) -> bool:
    """Global VA user flaglari bo'yicha yakuniy holat (xatoda True)."""
    g = await get_global_flag(feature)
    if g is False:
        return False
    u = await get_user_flag(user_id, feature)
    return u is not False


async def set_user_feature(user_id: int, feature: str, enabled: bool) -> bool:
    try:
        await _ensure_tables()
        async with get_db_connection() as db:
            await db.execute('''
                INSERT INTO user_feature_flags (user_id, feature, enabled, updated_at)
                VALUES ($1, $2, $3, $4)
                ON CONFLICT (user_id, feature)
                DO UPDATE SET enabled = $3, updated_at = $4
            ''', (user_id, feature, 1 if enabled else 0, int(time.time())))
    except Exception as e:
        logger.error(f"feature_flags: user flag yozilmadi ({user_id}/{feature}): {e}")
        return False
    _user_flag_cache.pop((user_id, feature), None)  # darhol kuchga kirsin
    return True


async def set_global_feature(feature: str, enabled: bool) -> bool:
    try:
        await _ensure_tables()
        async with get_db_connection() as db:
            await db.execute('''
                INSERT INTO bot_settings (key, value) VALUES ($1, $2)
                ON CONFLICT (key) DO UPDATE SET value = $2
            ''', (_global_settings_key(feature), "1" if enabled else "0"))
    except Exception as e:
        logger.error(f"feature_flags: global flag yozilmadi ({feature}): {e}")
        return False
    _global_flag_cache.pop(feature, None)  # darhol kuchga kirsin
    return True


async def get_user_features(user_id: int) -> Dict[str, bool]:
    """UI uchun: barcha funksiyalarning user bo'yicha holati (1 so'rov)."""
    flags = {f: True for f in FEATURES}
    try:
        await _ensure_tables()
        async with get_db_connection() as db:
            rows = await db.fetch(
                "SELECT feature, enabled FROM user_feature_flags WHERE user_id = $1",
                user_id,
            )
    except Exception as e:
        logger.error(f"feature_flags: user flags o'qilmadi ({user_id}): {e}")
        return flags
    for row in rows:
        if row["feature"] in flags:
            flags[row["feature"]] = bool(row["enabled"])
    return flags


async def get_global_features() -> Dict[str, bool]:
    """Admin panel uchun: barcha global flaglar holati (1 so'rov)."""
    flags = {f: True for f in FEATURES}
    try:
        await _ensure_tables()
        async with get_db_connection() as db:
            rows = await db.fetch(
                "SELECT key, value FROM bot_settings WHERE key LIKE 'feature_enabled_%'"
            )
    except Exception as e:
        logger.error(f"feature_flags: global flags o'qilmadi: {e}")
        return flags
    for row in rows:
        feature = str(row["key"]).replace("feature_enabled_", "", 1)
        if feature in flags:
            flags[feature] = str(row["value"]) == "1"
    return flags

# ------------------------- Umumiy bot sozlamalari -------------------------

# Admin panel'dan boshqariladigan umumiy sozlamalar (key -> default):
#   referral_enabled   — taklif tizimi yoqilganmi ("1"/"0")
# Kelgusi: sub_price_stars, force_channels (JSON), ...
_SETTING_DEFAULTS: Dict[str, str] = {
    "referral_enabled": "1",
    "force_join_enabled": "0",
    # force_channels — JSON ro'yxat (plugins/force_join.py boshqaradi)
}

_setting_cache: Dict[str, Tuple[str, float]] = {}
SETTING_CACHE_TTL = 30.0


async def get_bot_setting(key: str, default: Optional[str] = None) -> str:
    """bot_settings'dan string qiymat o'qiydi (kesh bilan).

    Yozuv yo'q bo'lsa _SETTING_DEFAULTS (yoki berilgan default) qaytadi.
    DB xatosida default qaytadi (fail-open).
    """
    if default is None:
        default = _SETTING_DEFAULTS.get(key, "")
    now = time.time()
    cached = _setting_cache.get(key)
    if cached and now - cached[1] < SETTING_CACHE_TTL:
        return cached[0]
    try:
        await _ensure_tables()
        async with get_db_connection() as db:
            row = await db.fetchrow(
                "SELECT value FROM bot_settings WHERE key = $1",
                key,
            )
    except Exception as e:
        logger.error(f"feature_flags: sozlama o'qilmadi ({key}): {e}")
        return default
    value = str(row["value"]) if row is not None and row["value"] is not None else default
    _setting_cache[key] = (value, now)
    return value


async def set_bot_setting(key: str, value: str) -> bool:
    """bot_settings'ga string qiymat yozadi (kesh darhol tozalanadi)."""
    try:
        await _ensure_tables()
        async with get_db_connection() as db:
            await db.execute('''
                INSERT INTO bot_settings (key, value) VALUES ($1, $2)
                ON CONFLICT (key) DO UPDATE SET value = $2
            ''', (key, str(value)))
    except Exception as e:
        logger.error(f"feature_flags: sozlama yozilmadi ({key}): {e}")
        return False
    _setting_cache.pop(key, None)  # darhol kuchga kirsin
    return True


async def is_referral_enabled() -> bool:
    """Taklif tizimi yoqilganmi? (default: yoq)"""
    return (await get_bot_setting("referral_enabled")) != "0"


# ------------------------- Boshqaruv ruxsatnomasi -------------------------

def is_owner(user_id: int) -> bool:
    """Owner (SUPER_ADMIN_ID) — hamma narsani boshqara oladi, o'z flaglaridan tashqari."""
    return user_id == SUPER_ADMIN_ID


def _manager_key(user_id: int) -> str:
    return f"feature_manager_{user_id}"


async def can_manage_features(user_id: int) -> bool:
    """Funksiyalarni boshqarish ruxsatnomasi: owner yoki owner bergan admin."""
    if is_owner(user_id):
        return True

    now = time.time()
    cached = _manager_cache.get(user_id)
    if cached and now - cached[1] < MANAGER_CACHE_TTL:
        return cached[0]

    try:
        await _ensure_tables()
        async with get_db_connection() as db:
            row = await db.fetchrow(
                "SELECT value FROM bot_settings WHERE key = $1",
                _manager_key(user_id),
            )
    except Exception as e:
        logger.error(f"feature_flags: manager ruxsat o'qilmadi ({user_id}): {e}")
        return False  # fail-closed — ruxsatsizlar boshqarmasin

    allowed = row is not None and str(row["value"]) == "1"
    _manager_cache[user_id] = (allowed, now)
    return allowed


async def set_feature_manager(user_id: int, allowed: bool) -> bool:
    """Owner admin'ga funksiyalarni boshqarish ruxsatnomasini beradi/oladi."""
    try:
        await _ensure_tables()
        async with get_db_connection() as db:
            await db.execute('''
                INSERT INTO bot_settings (key, value) VALUES ($1, $2)
                ON CONFLICT (key) DO UPDATE SET value = $2
            ''', (_manager_key(user_id), "1" if allowed else "0"))
    except Exception as e:
        logger.error(f"feature_flags: manager ruxsat yozilmadi ({user_id}): {e}")
        return False
    _manager_cache.pop(user_id, None)
    return True


async def get_feature_managers() -> Dict[int, bool]:
    """Ruxsatnoma bergan adminlar ro'yxati."""
    result: Dict[int, bool] = {}
    try:
        await _ensure_tables()
        async with get_db_connection() as db:
            rows = await db.fetch(
                "SELECT key, value FROM bot_settings WHERE key LIKE 'feature_manager_%'"
            )
    except Exception as e:
        logger.error(f"feature_flags: managerlar o'qilmadi: {e}")
        return result
    for row in rows:
        try:
            uid = int(str(row["key"]).replace("feature_manager_", "", 1))
            result[uid] = str(row["value"]) == "1"
        except ValueError:
            continue
    return result

# ------------------------- Anti-flood -------------------------

def _flood_check(user_id: int) -> str:
    """
    Cheklangan funksiyaga urinishni qayd etadi.
    'warn'   — ogohlantirish ko'rsatish mumkin (limit ichida)
    'silent' — jim qolish kerak (mute yoki ogohlantirish limiti tugagan)
    """
    now = time.time()
    st = _flood_state.get(user_id)
    if st is None:
        st = {"window_start": now, "warns": 0, "muted_until": 0.0}
        _flood_state[user_id] = st

    if now < st["muted_until"]:
        return "silent"

    if now - st["window_start"] >= WARN_WINDOW_SECONDS:
        st["window_start"] = now
        st["warns"] = 0

    st["warns"] += 1
    if st["warns"] > MAX_WARNINGS_PER_WINDOW:
        st["muted_until"] = now + MUTE_SECONDS
        st["warns"] = 0
        logger.info(f"feature_flags: user {user_id} {MUTE_SECONDS}s ga mute bo'ldi (flood)")
        return "silent"

    return "warn"

# ------------------------- Gate -------------------------

async def gate_feature(event, feature: str) -> bool:
    """
    Handler'lar boshida chaqiriladi. True = ishga ruxsat, False = cheklangan
    (kerak bo'lsa '🚫 cheklangan' xabari yuboriladi, flood bo'lsa jim).

    Faqat OWNER (SUPER_ADMIN_ID) cheklovlardan mustasno — adminlar va oddiy
    userlarning funksiyalari owner tomonidan boshqariladi (flaglar orqali).
    """
    if feature not in FEATURES:
        return True

    try:
        user_id = event.from_user.id
    except Exception:
        return True

    if is_owner(user_id):
        return True

    try:
        g = await get_global_flag(feature)
        if g is False:
            reason = "global"
        else:
            u = await get_user_flag(user_id, feature)
            if u is False:
                reason = "user"
            else:
                return True
    except Exception as e:
        logger.error(f"feature_flags: gate xatosi ({feature}): {e}")
        return True  # fail-open — bot ishlashi buzilmasin

    if _flood_check(user_id) == "silent":
        return False

    if reason == "global":
        text = (
            f"🚫 <b>{FEATURES[feature]}</b> funksiyasi hamma uchun cheklangan.\n"
            f"Admin bilan bog'laning."
        )
    else:
        text = (
            f"🚫 <b>{FEATURES[feature]}</b> funksiyasi siz uchun cheklangan.\n"
            f"Admin bilan bog'laning."
        )

    try:
        if isinstance(event, CallbackQuery):
            await event.answer(text, show_alert=True)
        elif isinstance(event, Message):
            await event.reply_text(text)
    except Exception as e:
        logger.warning(f"feature_flags: cheklov xabari yuborilmadi: {e}")

    return False

# ------------------------- Test uchun -------------------------

def _reset_state_for_tests() -> None:
    """Faqat testlar uchun: barcha xotira holatini tozalaydi."""
    _user_flag_cache.clear()
    _global_flag_cache.clear()
    _manager_cache.clear()
    _flood_state.clear()
    global _tables_ready
    _tables_ready = False
