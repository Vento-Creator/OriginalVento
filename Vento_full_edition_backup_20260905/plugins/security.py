from pyrogram import Client, filters, ContinuePropagation, StopPropagation
from pyrogram.types import CallbackQuery, Message
from database import get_violation_count
import config
from config import SUPER_ADMIN_ID, SECOND_ADMIN_ID
import time
import logging
from collections import defaultdict

security_logger = logging.getLogger("security")

rate_limits = defaultdict(list)
suspicious_activities = defaultdict(list)

VALID_CALLBACK_PATTERNS = [
    "menu_", "admin_", "baza_", "utag_", "scraper_", "massdm_", "login_",
    "stop_process", "show_laws", "adm_", "baza_confirm_", "baza_cancel_",
    "scrape_", "pg:", "pay_", "cancel_login", "logout", "check_", "do_",
    "approve_", "reject_", "user_", "stop_utag_", "contact_", "complaint_",
    "resend_code", "code_help", "close_help",
    "complaints_", "chat_", "group_search", "guide_", "owner_", "broadcast_retry",
    "bc_", "language", "account_link", "feat|"
]

MAX_BUTTON_ROWS = 10
MAX_BUTTON_COLS = 3
MAX_BUTTON_TEXT_LENGTH = 50

MAX_REQUESTS_PER_MINUTE = 30
MAX_SUSPICIOUS_ACTIONS = 5


def is_valid_callback_data(callback_data: str) -> bool:
    """Check if callback data matches valid patterns"""
    if not callback_data:
        return False
    
    for pattern in VALID_CALLBACK_PATTERNS:
        if callback_data.startswith(pattern):
            return True
    
    return False

def check_rate_limit(user_id: int) -> bool:
    """Check if user is within rate limits"""
    now = time.time()
    user_requests = rate_limits[user_id]
    
    user_requests[:] = [req_time for req_time in user_requests if now - req_time < 60]
    
    if len(user_requests) >= MAX_REQUESTS_PER_MINUTE:
        return False
    
    user_requests.append(now)
    return True

def log_suspicious_activity(user_id: int, activity_type: str, details: str = ""):
    """Log suspicious activity and check if admin should be notified"""
    now = time.time()
    user_activities = suspicious_activities[user_id]
    
    user_activities[:] = [act for act in user_activities if now - act["time"] < 3600]
    
    user_activities.append({
        "time": now,
        "type": activity_type,
        "details": details
    })
    
    security_logger.warning(f"Suspicious activity - User {user_id}: {activity_type} - {details}")
    
    if len(user_activities) >= MAX_SUSPICIOUS_ACTIONS:
        return True
    
    return False

async def notify_admin(client: Client, user_id: int, activity_type: str, details: str = ""):
    """Send security alert to admins"""
    alert_text = (
        f"🚨 **XAVFSIZLIK OGOHLANTIRISHI!**\n\n"
        f"👤 User ID: `{user_id}`\n"
        f"⚠️ Xatti-harakat: {activity_type}\n"
        f"📝 Tafsilotlar: {details}\n\n"
        f"⏰ Vaqt: {time.strftime('%Y-%m-%d %H:%M:%S')}"
    )
    
    for admin_id in config.ADMIN_IDS:
        try:
            await client.send_message(admin_id, alert_text)
        except Exception as e:
            security_logger.error(f"Failed to notify admin {admin_id}: {e}")

def validate_keyboard(keyboard) -> bool:
    """Validate inline keyboard to prevent button injection attacks"""
    if not keyboard or not hasattr(keyboard, 'inline_keyboard'):
        return False
    
    rows = keyboard.inline_keyboard
    
    if len(rows) > MAX_BUTTON_ROWS:
        return False
    
    for row in rows:
        if len(row) > MAX_BUTTON_COLS:
            return False
        
        for button in row:
            if hasattr(button, 'text') and button.text:
                if len(button.text) > MAX_BUTTON_TEXT_LENGTH:
                    return False
            
            if hasattr(button, 'callback_data') and button.callback_data:
                if not is_valid_callback_data(button.callback_data):
                    return False
    
    return True

def secure_keyboard(keyboard):
    """Wrapper to validate keyboard before use"""
    if not validate_keyboard(keyboard):
        security_logger.error("Invalid keyboard detected and rejected")
        from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
        return InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Orqaga", callback_data="menu_main")]])
    return keyboard

@Client.on_message(filters.all & filters.private, group=-1)
async def banned_user_middleware(client: Client, message: Message):
    # DIAGNOSTIC: Log message
    msg_text = message.text[:50] if message.text else ""
    security_logger.debug("[DIAG] MESSAGE_RECEIVED: text=%s user_id=%d", msg_text, message.from_user.id if message.from_user else None)
    
    if not message.from_user:
        security_logger.debug("[DIAG] MESSAGE_BLOCKED: no from_user")
        raise ContinuePropagation

    if config.is_admin(message.from_user.id):
        security_logger.debug("[DIAG] MESSAGE_BYPASS: admin user_id=%d", message.from_user.id)
        raise ContinuePropagation

    count = await get_violation_count(message.from_user.id)
    if count > 0:
        security_logger.warning("[DIAG] MESSAGE_BLOCKED: violation_count=%d user_id=%d", count, message.from_user.id)
        raise StopPropagation

    if not check_rate_limit(message.from_user.id):
        security_logger.warning("[DIAG] MESSAGE_BLOCKED: rate_limit user_id=%d", message.from_user.id)
        await message.reply_text("⚠️ Juda ko'p so'rov! Iltimos, biroz kutib turing.")
        raise StopPropagation
    
    security_logger.debug("[DIAG] MESSAGE_ALLOWED: text=%s user_id=%d", msg_text, message.from_user.id)
    raise ContinuePropagation

@Client.on_callback_query(group=-1)
async def banned_callback_middleware(client: Client, callback_query: CallbackQuery):
    # DIAGNOSTIC: Log callback data
    security_logger.debug("[DIAG] CALLBACK_RECEIVED: data=%s user_id=%d", callback_query.data, callback_query.from_user.id if callback_query.from_user else None)
    
    if not callback_query.from_user:
        security_logger.debug("[DIAG] CALLBACK_BLOCKED: no from_user")
        raise ContinuePropagation

    if config.is_admin(callback_query.from_user.id):
        security_logger.debug("[DIAG] CALLBACK_BYPASS: admin user_id=%d", callback_query.from_user.id)
        raise ContinuePropagation

    if callback_query.data == "show_laws":
        security_logger.debug("[DIAG] CALLBACK_BYPASS: show_laws")
        raise ContinuePropagation # Allow them to read the laws

    count = await get_violation_count(callback_query.from_user.id)
    if count > 0:
        security_logger.warning("[DIAG] CALLBACK_BLOCKED: violation_count=%d user_id=%d", count, callback_query.from_user.id)
        await callback_query.answer("Siz bloklangansiz!", show_alert=True)
        raise StopPropagation

    if not is_valid_callback_data(callback_query.data):
        security_logger.warning("[DIAG] CALLBACK_BLOCKED: invalid_data=%s user_id=%d", callback_query.data, callback_query.from_user.id)
        should_notify = log_suspicious_activity(
            callback_query.from_user.id,
            "invalid_callback_data",
            callback_query.data
        )

        if should_notify:
            await notify_admin(
                client,
                callback_query.from_user.id,
                "Invalid callback data injection attempt",
                callback_query.data
            )

        await callback_query.answer("⛔️ Noto'g'ri amal!", show_alert=True)
        raise StopPropagation

    if not check_rate_limit(callback_query.from_user.id):
        security_logger.warning("[DIAG] CALLBACK_BLOCKED: rate_limit user_id=%d", callback_query.from_user.id)
        await callback_query.answer("⚠️ Juda ko'p so'rov!", show_alert=True)
        raise StopPropagation

    security_logger.debug("[DIAG] CALLBACK_ALLOWED: data=%s user_id=%d", callback_query.data, callback_query.from_user.id)
    raise ContinuePropagation

@Client.on_callback_query(filters.regex("^show_laws$"))
async def show_laws_callback(client: Client, callback_query: CallbackQuery):
    laws_text = (
        "⚖️ **Qonunchilik va Javobgarlik (O'zbekiston Respublikasi Jinoyat Kodeksi)**\n\n"
        "💻 **278-modda. Kompyuter axborotidan qonunga xilof ravishda foydalanish**\n"
        "Shaxsning kompyuter axborotiga, ya'ni axborot-hisoblash tizimlari, tarmoqlari va ularning tarkibiy qismlaridagi "
        "axborotga qonunga xilof ravishda kirishi, xuddi shuningdek axborotni yo'q qilib yuborish, to'sib qo'yish, "
        "modifikatsiyalash, undan nusxa ko'chirish yoki uni o'zlashtirish — bazaviy hisoblash miqdorining yuz "
        "baravaridan uch yuz baravarigacha miqdorda jarima yoki uch yilgacha muayyan huquqdan mahrum qilish yoxud "
        "bir yildan uch yilgacha ozodlikni cheklash yoki uch yilgacha ozodlikdan mahrum qilish bilan jazolanadi.\n\n"
        "🛑 **Botga zarar yetkazish, faoliyatini to'xtatishga urinish, boshqa foydalanuvchilar ishiga xalal berish** "
        "kabi kiber-hujumlar to'g'ridan-to'g'ri ushbu modda bilan jinoiy javobgarlikka tortilishga sabab bo'ladi.\n\n"
        "⚠️ Bizning tizim sizning Telegram akkauntingiz (Userbot) sessiyasiga ega ekanligini unutmang! "
        "Agar zararli xatti-harakatlar davom etsa, nafaqat botga kirishingiz bloklanadi, balki qonuniy choralar ko'riladi."
    )
    
    await callback_query.message.reply_text(laws_text)
    await callback_query.answer()
