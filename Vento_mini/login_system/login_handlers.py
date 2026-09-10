import logging
from pyrogram import Client, filters
from pyrogram.types import (
    Message, CallbackQuery,
    InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardRemove,
)
from pyrogram.errors import RPCError
from login_system.login_core import (
    start_login_phone,
    submit_login_code,
    submit_2fa_password,
    finalize_login_session,
    clear_pending_login
)
from session_manager import register_account, set_active_slot, get_accounts

logger = logging.getLogger(__name__)

# Memory state management: user_id -> {"state": str, "slot": int}
_user_login_states = {}


def get_user_login_state(user_id: int):
    return _user_login_states.get(user_id)


def set_user_login_state(user_id: int, state: str, slot: int = 0):
    _user_login_states[user_id] = {"state": state, "slot": slot}


def clear_user_login_state(user_id: int):
    _user_login_states.pop(user_id, None)


async def process_login_contact_input(client: Client, message: Message) -> bool:
    """Kontakt (📞 Nomerni yuborish tugmasi) orqali yuborilgan nomerni login oqimiga kiritish.

    Qaytaradi: True (agar xabar ushbu login oqimiga tegishli bo'lsa), aks holda False.
    """
    contact = getattr(message, "contact", None)
    if not contact or not getattr(contact, "phone_number", None):
        return False

    user_id = message.from_user.id
    st_info = get_user_login_state(user_id)
    if not st_info or st_info.get("state") != "WAIT_PHONE":
        return False

    # Faqat o'z kontaktini qabul qilamiz (boshqa odamning nomerini ulab bo'lmaydi)
    if getattr(contact, "user_id", None) and contact.user_id != user_id:
        await message.reply_text("❌ Iltimos, faqat o'z raqamingizni yuboring!")
        return True

    slot = st_info.get("slot", 0)
    phone = contact.phone_number.strip().replace(" ", "").replace("-", "")
    if not phone.startswith("+"):
        phone = "+" + phone

    from session_manager import count_accounts
    from pyrogram.types import ReplyKeyboardRemove
    # Nomer qabul qilindi — 📞/📱 reply-tugmalarini ekrandan olib tashlaymiz (kod kiritishda kerak emas)
    await message.reply_text("📲 Kod yuborilmoqda, kuting...", reply_markup=ReplyKeyboardRemove())
    try:
        res = await start_login_phone(user_id, phone, slot)
        logger.info(f"[LOGIN_DEBUG] start_login_phone via contact SUCCESS: uid={user_id}, phone={phone}, res={res}")
        set_user_login_state(user_id, "WAIT_CODE", slot)
        acc_cnt = count_accounts(user_id)
        mode_prefix = "📎 Qo'shimcha akkaunt ulash\n\n" if acc_cnt > 0 else ""
        await message.reply_text(
            f"{mode_prefix}📲 **{phone}** raqamiga Telegram orqali tasdiqlash kodi yuborildi!\n\n"
            f"Kodni quyidagi formatda kiriting (masalan: `12345` yoki `1 2 3 4 5`):"
        )
    except Exception as e:
        logger.error(f"[LOGIN_DEBUG] start_login_phone via contact ERROR: {e}", exc_info=True)
        clear_user_login_state(user_id)
        await message.reply_text(f"❌ Xatolik: {e}\n\nQayta urinish uchun /start yuboring.")
    return True


def _normalize_phone_input(text: str) -> str:
    """Qo'lda yozilgan nomerni normallashtirish: bo'shliq/tirelarni tozalash, + qo'shish."""
    phone = (text or "").strip().replace(" ", "").replace("-", "")
    if phone and not phone.startswith("+"):
        phone = "+" + phone
    return phone


async def process_login_text_input(client: Client, message: Message) -> bool:
    """Shtatli matnli xabarlarni tutish (Phone / Code / 2FA).
    
    Qaytaradi: True (agar xabar ushbu login oqimiga tegishli bo'lsa), aks holda False.
    """
    user_id = message.from_user.id
    st_info = get_user_login_state(user_id)
    text = (message.text or "").strip()
    logger.info(f"[LOGIN_DEBUG] process_login_text_input: uid={user_id}, text='{text}', st_info={st_info}")

    if text.startswith("/"):
        clear_user_login_state(user_id)
        clear_pending_login(user_id)
        return False

    # Auto-detect phone number input if user sends phone number
    if not st_info:
        clean_p = text.replace(" ", "").replace("-", "")
        logger.info(f"[LOGIN_DEBUG] Auto-detect check: clean_p='{clean_p}'")
        if clean_p.startswith("+") or (clean_p.isdigit() and len(clean_p) >= 9):
            from session_manager import count_accounts
            acc_cnt = count_accounts(user_id)
            logger.info(f"[LOGIN_DEBUG] count_accounts={acc_cnt}")
            if acc_cnt == 0 or clean_p.startswith("+"):
                set_user_login_state(user_id, "WAIT_PHONE", 0)
                st_info = get_user_login_state(user_id)
                logger.info(f"[LOGIN_DEBUG] Auto-set WAIT_PHONE for uid={user_id}")
            else:
                return False
        else:
            return False

    state = st_info["state"]
    slot = st_info.get("slot", 0)
    logger.info(f"[LOGIN_DEBUG] Processing state='{state}', slot={slot}")

    if state == "WAIT_PHONE":
        phone = text.replace(" ", "").replace("-", "")
        if not phone.startswith("+"):
            if phone.isdigit() and len(phone) == 12:
                phone = "+" + phone
            else:
                logger.info(f"[LOGIN_DEBUG] Invalid phone format: '{phone}'")
                await message.reply_text("❌ Telefon raqam xalqaro formatda bo'lishi kerak! Masalan: `+998901234567`")
                return True

        logger.info(f"[LOGIN_DEBUG] Attempting start_login_phone: uid={user_id}, phone={phone}, slot={slot}")
        await message.reply_text("📲 Kod yuborilmoqda, kuting...")
        try:
            res = await start_login_phone(user_id, phone, slot)
            logger.info(f"[LOGIN_DEBUG] start_login_phone SUCCESS: res={res}")
            set_user_login_state(user_id, "WAIT_CODE", slot)
            # Kontakt klaviaturasi endi keraksiz — uni darhol yopamiz (pastda Scraper/Bazalar chiqadi keyinroq).
            await message.reply_text(
                f"📲 **{phone}** raqamiga Telegram orqali tasdiqlash kodi yuborildi!\n\n"
                f"Kodni quyidagi formatda kiriting (masalan: `12345` yoki `1 2 3 4 5`):"
            )
            try:
                await message.reply_text("⌨️", reply_markup=ReplyKeyboardRemove())
            except Exception:
                pass
        except Exception as e:
            logger.error(f"[LOGIN_DEBUG] start_login_phone ERROR: {e}", exc_info=True)
            clear_user_login_state(user_id)
            await message.reply_text(f"❌ Xatolik: {e}\n\nQayta urinish uchun /start yuboring.")
        return True

    elif state == "WAIT_CODE":
        code = text.replace(" ", "").replace("-", "")
        msg = await message.reply_text("🔑 Kod tekshirilmoqda...")
        try:
            res = await submit_login_code(user_id, code)
            if res.get("status") == "2fa_required":
                set_user_login_state(user_id, "WAIT_2FA", slot)
                await msg.edit_text("🔐 **2FA (Ikki bosqichli tasdiqlash) paroli o'rnatilgan!**\n\nIltimos, parolingizni kiriting:")
                return True

            # Success
            tg_user = res.get("user")
            await _complete_login(client, message, msg, user_id, slot, tg_user)
        except Exception as e:
            logger.error(f"submit_login_code error: {e}")
            await msg.edit_text(f"❌ Xatolik: {e}\n\nKodni qayta kiriting:")
        return True

    elif state == "WAIT_2FA":
        password = text
        msg = await message.reply_text("🔐 2FA parol tekshirilmoqda...")
        try:
            res = await submit_2fa_password(user_id, password)
            tg_user = res.get("user")
            await _complete_login(client, message, msg, user_id, slot, tg_user)
        except Exception as e:
            logger.error(f"submit_2fa_password error: {e}")
            await msg.edit_text(f"❌ Xatolik: {e}\n\nParol noto'g'ri, qayta kiriting:")
        return True

    return False


async def _complete_login(client: Client, message: Message, msg: Message, user_id: int, slot: int, tg_user):
    tg_id = tg_user.id if tg_user else None
    first_name = tg_user.first_name if tg_user else None

    # Check duplicate account
    if tg_id:
        accs = get_accounts(user_id)
        dup = next((a for a in accs if a.get("tg_id") == tg_id), None)
        if dup:
            clear_user_login_state(user_id)
            clear_pending_login(user_id)
            await msg.edit_text(
                f"❌ **Bu Telegram akkaunt allaqachon ulangan!**\n\n"
                f"📱 Akkaunt: {dup['name']} (Slot {dup['slot']})\n\n"
                f"Bir xil akkauntni qayta ulash mumkin emas."
            )
            return

    await finalize_login_session(user_id, slot)
    register_account(user_id, slot, tg_id=tg_id, first_name=first_name, name=None)
    set_active_slot(user_id, slot)  # SYNCHRONOUS call!

    clear_user_login_state(user_id)

    name_display = first_name or f"Akkount-{slot}"
    await msg.edit_text(
        f"🎉 **Akkaunt muvaffaqiyatli ulandi!**\n\n"
        f"👤 Nomi: **{name_display}**\n"
        f"🟢 Faol slot: **Slot {slot}**\n\n"
        f"Barcha amallar va buyruqlar endi ushbu akkaunt nomidan bajariladi.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📱 Akkauntlar sozlamasi", callback_data="menu_account_back")],
            [InlineKeyboardButton("🏠 Asosiy menyu", callback_data="menu_main")]
        ])
    )
    # Login tugadi — pastda asosiy Reply-klaviaturani chiqaramiz (Scraper/Bazalar/MassDM).
    # (menu.py dan import qilsak circular import bo'ladi, shuning uchun shu yerda yasaymiz)
    try:
        from pyrogram.types import ReplyKeyboardMarkup as _RKM, KeyboardButton as _KB
        await message.reply_text(
            "🏠 **Bosh menyu**",
            reply_markup=_RKM(
                [[_KB("🔍 Scraper"), _KB("🗂 Bazalar")], [_KB("📨 Mass DM"), _KB("👤 Akkaunt")]],
                resize_keyboard=True,
            ),
        )
    except Exception:
        pass
