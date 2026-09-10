import logging
from pyrogram import Client, filters
from pyrogram.types import (
    Message, CallbackQuery,
    InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardMarkup, KeyboardButton,
)
from database import (
    register_user,
    is_admin,
    add_admin_db,
    remove_admin_db,
    get_all_admins_db
)
from session_manager import (
    get_accounts,
    get_active_slot,
    set_active_slot,
    remove_account_slot,
    update_account_name,
    close_user_client_slot,
    count_accounts
)
from pyrogram.types import ReplyKeyboardRemove
from login_system.login_handlers import (
    set_user_login_state,
    clear_user_login_state,
    process_login_text_input,
    process_login_contact_input,
)

logger = logging.getLogger(__name__)

# State management for rename and admin input
_rename_states = {}
_admin_input_states = {}


async def get_main_reply_keyboard(user_id: int = None) -> ReplyKeyboardMarkup:
    """Original Vento ko'rinishidagi pastki Reply-klaviatura (faqat kerakli 3 funksiya + Akkaunt).
    Admin Panel tugmasi faqat adminlarga ko'rsatiladi."""
    rows = [
        [KeyboardButton("🔍 Scraper"), KeyboardButton("🗂 Bazalar")],
        [KeyboardButton("📨 Mass DM"), KeyboardButton("👤 Akkaunt")],
    ]
    # Admin Panel faqat adminlarga ko'rsatiladi
    if user_id:
        from database import is_admin
        try:
            if await is_admin(user_id):
                rows.append([KeyboardButton("👑 Admin Panel")])
        except Exception:
            pass
    return ReplyKeyboardMarkup(rows, resize_keyboard=True)


async def get_phone_share_reply_keyboard() -> ReplyKeyboardMarkup:
    """Nomer-so'rash paytida pastda chiqadigan reply-knopka.

    Bitta tugma: 📞 Nomerni yuborish (request_contact) — 1 bosishda kontakt yuboriladi.
    """
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton("📞 Nomerni yuborish", request_contact=True)],
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


async def get_no_account_reply_keyboard():
    """Eski 📱 Akkaunt ulash tugmasi olib tashlandi (oraliq qadam keraksiz).
    /start paytida pastda to'g'ridan-to'g'ri 📞 Nomerni yuborish chiqadi."""
    return await get_phone_share_reply_keyboard()


async def build_main_keyboard(user_id: int):
    """Akkaunt yo'q bo'lsa: /start oqimi uchun pastda 📞 Nomerni yuborish (tezkor kontakt)."""
    if count_accounts(user_id) == 0:
        return await get_phone_share_reply_keyboard()
    return await get_main_reply_keyboard(user_id)


async def check_account_guard(cq: CallbackQuery) -> bool:
    """Tekshiruv: kamida 1 ta akkaunt ulanmagan bo'lsa, menyuga kirishni to'sadi."""
    user_id = cq.from_user.id
    if count_accounts(user_id) == 0:
        set_user_login_state(user_id, "WAIT_PHONE", 0)
        await cq.message.edit_text(
            "⚠️ **Sizda hali ulangan Telegram akkaunt mavjud emas!**\n\n"
            "Botdan foydalanish uchun avval Telegram akkauntingizni ulashingiz kerak.\n\n"
            "📱 Raqamingizni xalqaro formatda yuboring:\n"
            "`+998901234567`",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("❌ Bekor qilish", callback_data="cancel_login")],
            ]),
        )
        return False
    return True


@Client.on_message(filters.command(["start", "menu"]) & filters.private)
async def start_command(client: Client, message: Message):
    user_id = message.from_user.id
    username = message.from_user.username
    first_name = message.from_user.first_name or "Foydalanuvchi"

    await register_user(user_id, username, first_name)
    clear_user_login_state(user_id)
    _admin_input_states.pop(user_id, None)
    _rename_states.pop(user_id, None)

    accounts = get_accounts(user_id)
    active_slot = get_active_slot(user_id)
    active_acc = next((a for a in accounts if a["slot"] == active_slot), None)

    if not accounts:
        # /start -> nomer -> login (tezkor kontakt tugmasi bilan): pastda 📞 Nomerni yuborish.
        set_user_login_state(user_id, "WAIT_PHONE", 0)
        text = (
            f"👋 Salom, **{first_name}**!\n\n"
            "**Vento Mini**ga xush kelibsiz.\n\n"
            "Botdan foydalanish uchun avval Telegram akkauntingizni ulashingiz kerak.\n\n"
            "📱 Pastdagi **📞 Nomerni yuborish** tugmasini bosing yoki raqamingizni qo'lda yozing:\n"
            "`+998901234567`"
        )
    else:
        acc_info = f"🟢 **{active_acc['name']}**" if active_acc else "⚠️ **Ulanmagan**"
        text = (
            f"👋 Salom, **{first_name}**!\n\n"
            f"**Vento Mini**ga xush kelibsiz.\n\n"
            f"📱 Faol Akkaunt: {acc_info}\n"
            f"👥 Ulangan akkauntlar soni: {len(accounts)} ta\n\n"
            f"Quyidagi bo'limlardan birini tanlang:"
        )

    kb = await build_main_keyboard(user_id)
    if not accounts:
        # /start -> nomer -> login: BITTA xabar + pastda 📞 Nomerni yuborish (1 bosishda kontakt).
        await message.reply_text(
            text,
            reply_markup=kb,
        )
    else:
        await message.reply_text(text, reply_markup=kb)


@Client.on_callback_query(filters.regex("^cancel_login$"))
async def cancel_login_callback(client: Client, cq: CallbackQuery):
    """❌ Bekor qilish -> state tozalanadi, pastdagi 📞 reply-knopka olib tashlanadi."""
    user_id = cq.from_user.id
    try:
        clear_user_login_state(user_id)
        try:
            from login_system.login_core import clear_pending_login
            clear_pending_login(user_id)
        except Exception:
            pass
    except Exception:
        pass
    try:
        await cq.message.edit_text(
            "❌ Akkaunt ulash bekor qilindi.\n\nQaytadan boshlash uchun /start yuboring.",
        )
    except Exception:
        pass
    try:
        await cq.message.reply_text(
            "⌨️ Klaviatura yopildi.",
            reply_markup=ReplyKeyboardRemove(),
        )
    except Exception:
        pass
    await cq.answer()


@Client.on_callback_query(filters.regex("^menu_main$"))
async def menu_main_callback(client: Client, cq: CallbackQuery):
    user_id = cq.from_user.id
    accounts = get_accounts(user_id)
    active_slot = get_active_slot(user_id)
    active_acc = next((a for a in accounts if a["slot"] == active_slot), None)

    if not accounts:
        text = (
            f"👋 **Asosiy menyu**\n\n"
            f"⚠️ Botdan foydalanish uchun avval Telegram akkauntingizni ulang!\n\n"
            "Telefon raqamingizni xalqaro formatda yuboring:\n"
            "`+998901234567`"
        )
    else:
        acc_info = f"🟢 **{active_acc['name']}**" if active_acc else "⚠️ **Ulanmagan**"
        text = (
            f"👋 **Asosiy menyu**\n\n"
            f"📱 Faol Akkaunt: {acc_info}\n"
            f"👥 Ulangan akkauntlar soni: {len(accounts)} ta\n\n"
            f"Quyidagi bo'limlardan birini tanlang:"
        )

    kb = await build_main_keyboard(user_id)
    try:
        if isinstance(kb, InlineKeyboardMarkup):
            await cq.message.edit_text(text, reply_markup=kb)
            await cq.answer()
            return
    except Exception:
        pass
    await cq.message.reply_text(text, reply_markup=kb)
    await cq.answer()


async def _require_account_for_text(client: Client, message: Message) -> bool:
    """Reply-tugma bosilganda akkaunt bo'lmasa — nomer so'rash + 📞 tezkor tugma (bitta xabar)."""
    user_id = message.from_user.id
    if count_accounts(user_id) == 0:
        set_user_login_state(user_id, "WAIT_PHONE", 0)
        await message.reply_text(
            f"👋 Salom, **{message.from_user.first_name or 'Foydalanuvchi'}**!\n\n"
            "**Vento Mini**ga xush kelibsiz.\n\n"
            "Botdan foydalanish uchun avval Telegram akkauntingizni ulashingiz kerak.\n\n"
            "📱 Pastdagi **📞 Nomerni yuborish** tugmasini bosing yoki raqamingizni qo'lda yozing:\n"
            "`+998901234567`",
            reply_markup=await get_phone_share_reply_keyboard(),
        )
        return False
    return True


async def _open_scraper_from_text(client: Client, message: Message):
    from plugins.scraper import _scraper_states
    _scraper_states[message.from_user.id] = "waiting_for_scrape_target"
    await message.reply_text(
        "🔍 **Scraper (Odam yig'ish)**\n\n"
        "Odamlarni yig'ib olmoqchi bo'lgan guruhingizni username yoki havolasini yuboring.\n"
        "Masalan: `@guruh_username` yoki `https://t.me/guruh_username`\n\n"
        "⚠️ Eslatma: Guruhi ochiq va a'zolar ro'yxati ko'rinadigan bo'lishi kerak.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("❌ Bekor qilish", callback_data="menu_main")]
        ]),
    )


async def _open_massdm_from_text(client: Client, message: Message):
    from database import get_all_scraped_groups
    from massdm_system.massdm_service import is_massdm_running, MESSAGES as MASSDM_MESSAGES
    from plugins.massdm import massdm_states, BUTTON_CANCEL

    user_id = message.from_user.id
    if is_massdm_running(user_id):
        await message.reply_text("🚀 **MassDM jarayoni hozirda fonda ishlamoqda!**")
        return
    massdm_states.pop(user_id, None)
    groups = await get_all_scraped_groups(owner_id=user_id)
    if not groups:
        await message.reply_text(MASSDM_MESSAGES["no_groups"])
        return
    buttons = []
    for group in groups[:10]:
        gid = group["group_id"]
        title = (group["group_title"] or f"ID: {gid}")[:30]
        buttons.append([InlineKeyboardButton(f"📁 {title}", callback_data=f"massdm_select_{gid}")])
    buttons.append([InlineKeyboardButton(BUTTON_CANCEL, callback_data="massdm_cancel")])
    await message.reply_text(MASSDM_MESSAGES["select_group"], reply_markup=InlineKeyboardMarkup(buttons))


async def _open_baza_from_text(client: Client, message: Message):
    from plugins.baza import _show_baza_page

    class _FakeCQ:
        def __init__(self, msg):
            self.message = msg
            self.from_user = msg.from_user

        async def answer(self, *a, **k):
            return None

    status = await message.reply_text("⏳ Bazalar yuklanmoqda...")
    await _show_baza_page(_FakeCQ(status), message.from_user.id, 0)


async def _open_account_from_text(client: Client, message: Message):
    user_id = message.from_user.id
    accounts = get_accounts(user_id)
    active_slot = get_active_slot(user_id)
    lines = ["📱 **Ulangan Akkauntlar Ro'yxati:**\n"]
    buttons = []
    if not accounts:
        lines.append("⚠️ Hozircha hech qanday akkaunt ulanmagan.")
    else:
        for acc in accounts:
            slot = acc["slot"]
            name = acc["name"]
            is_active = (slot == active_slot)
            icon = "🟢 (FAOL)" if is_active else "⚪"
            lines.append(f"{icon} **Slot {slot}:** {name}")
            row = []
            if not is_active:
                row.append(InlineKeyboardButton(f"🔄 Slot {slot} ga o'tish", callback_data=f"acc_switch_{slot}"))
            row.append(InlineKeyboardButton("✏️ Nomlash", callback_data=f"acc_rename_{slot}"))
            if len(accounts) > 1:
                row.append(InlineKeyboardButton("🗑 O'chirish", callback_data=f"acc_remove_do_{slot}"))
            buttons.append(row)
    existing_slots = [a["slot"] for a in accounts]
    next_slot = 0
    while next_slot in existing_slots:
        next_slot += 1
    buttons.append([InlineKeyboardButton("➕ Yangi Akkaunt Qo'shish", callback_data=f"acc_add_{next_slot}")])
    buttons.append([InlineKeyboardButton("🏠 Asosiy Menyuga Qaytish", callback_data="menu_main")])
    await message.reply_text("\n".join(lines), reply_markup=InlineKeyboardMarkup(buttons))


# --- Akkauntlar sozlamasi ---

@Client.on_callback_query(filters.regex("^menu_account_back$"))
async def menu_account_back_callback(client: Client, cq: CallbackQuery):
    user_id = cq.from_user.id
    accounts = get_accounts(user_id)
    active_slot = get_active_slot(user_id)

    from session_manager import MAX_SESSIONS_PER_USER
    lines = [f"📱 **Ulangan Akkauntlar Ro'yxati:** ({len(accounts)}/{MAX_SESSIONS_PER_USER})\n"]
    buttons = []

    if not accounts:
        lines.append("⚠️ Hozircha hech qanday akkaunt ulanmagan.")
    else:
        for acc in accounts:
            slot = acc["slot"]
            name = acc["name"]
            is_active = (slot == active_slot)
            icon = "🟢 (FAOL)" if is_active else "⚪"
            lines.append(f"{icon} **Slot {slot}:** {name}")

            row = []
            if not is_active:
                row.append(InlineKeyboardButton(f"🔄 Slot {slot} ga o'tish", callback_data=f"acc_switch_{slot}"))
            row.append(InlineKeyboardButton(f"✏️ Nomlash", callback_data=f"acc_rename_{slot}"))
            if len(accounts) > 1:
                row.append(InlineKeyboardButton(f"🗑 O'chirish", callback_data=f"acc_remove_do_{slot}"))
            buttons.append(row)

    existing_slots = [a["slot"] for a in accounts]
    next_slot = 0
    while next_slot in existing_slots:
        next_slot += 1

    from session_manager import MAX_SESSIONS_PER_USER
    if len(accounts) < MAX_SESSIONS_PER_USER:
        buttons.append([InlineKeyboardButton("➕ Yangi Akkaunt Qo'shish", callback_data=f"acc_add_{next_slot}")])
    buttons.append([InlineKeyboardButton("🏠 Asosiy Menyuga Qaytish", callback_data="menu_main")])

    await cq.message.edit_text(
        "\n".join(lines),
        reply_markup=InlineKeyboardMarkup(buttons)
    )
    await cq.answer()


@Client.on_callback_query(filters.regex(r"^acc_switch_(\d+)$"))
async def acc_switch_callback(client: Client, cq: CallbackQuery):
    user_id = cq.from_user.id
    slot = int(cq.matches[0].group(1))

    old_slot = get_active_slot(user_id)
    if set_active_slot(user_id, slot):
        if old_slot != slot:
            await close_user_client_slot(user_id, old_slot)
        await cq.answer(f"✅ Slot {slot} ga o'tildi!", show_alert=True)
        await menu_account_back_callback(client, cq)
    else:
        await cq.answer("❌ Slotni almashtirishda xatolik.", show_alert=True)


@Client.on_callback_query(filters.regex(r"^acc_add_(\d+)$"))
async def acc_add_callback(client: Client, cq: CallbackQuery):
    user_id = cq.from_user.id
    slot = int(cq.matches[0].group(1))

    from session_manager import MAX_SESSIONS_PER_USER
    if len(accounts) >= MAX_SESSIONS_PER_USER:
        await cq.answer(f"❌ Maksimal {MAX_SESSIONS_PER_USER} ta akkaunt ulash mumkin!", show_alert=True)
        return

    set_user_login_state(user_id, "WAIT_PHONE", slot)
    # reply_markup qo'yib bo'lmaydi (callback xabarini edit qilamiz) — nomerni pastdagi 📞
    # tugma orqali yoki qo'lda yozishni eslatamiz.
    await cq.message.edit_text(
        f"📲 **Yangi akkaunt qo'shish (Slot {slot})**\n\n"
        f"Iltimos, Telegram raqamingizni xalqaro formatda kiriting:\n"
        f"Masalan: `+998901234567`\n\n"
        f"Pastdagi **📞 Nomerni yuborish** tugmasi orqali ham 1 bosishda yuborishingiz mumkin.\n\n"
        f"*(Bekor qilish uchun /start yuboring)*"
    )
    try:
        from plugins.menu import get_phone_share_reply_keyboard
        await cq.message.reply_text(
            "👇 Nomerni yuborish uchun tugmani bosing:",
            reply_markup=await get_phone_share_reply_keyboard(),
        )
    except Exception:
        pass
    await cq.answer()


@Client.on_callback_query(filters.regex(r"^acc_rename_(\d+)$"))
async def acc_rename_callback(client: Client, cq: CallbackQuery):
    user_id = cq.from_user.id
    slot = int(cq.matches[0].group(1))
    _rename_states[user_id] = {"slot": slot}

    await cq.message.edit_text(
        f"✏️ **Slot {slot} uchun yangi nom kiriting:**\n\n"
        f"*(Masalan: 'Asosiy Akkount', 'Work Acc' va h.k.)*"
    )
    await cq.answer()


@Client.on_callback_query(filters.regex(r"^acc_remove_do_(\d+)$"))
async def acc_remove_do_callback(client: Client, cq: CallbackQuery):
    user_id = cq.from_user.id
    slot = int(cq.matches[0].group(1))

    ok = await remove_account_slot(user_id, slot)
    if not ok:
        await cq.answer("❌ O'chirib bo'lmadi (kamida 1 ta akkaunt qolishi shart).", show_alert=True)
        return

    await cq.answer("🗑 Akkaunt o'chirildi!", show_alert=True)
    await menu_account_back_callback(client, cq)


# --- 👑 Adminlar Boshqaruvi ---

@Client.on_callback_query(filters.regex("^admin_menu$"))
async def admin_menu_callback(client: Client, cq: CallbackQuery):
    user_id = cq.from_user.id
    if not await is_admin(user_id):
        await cq.answer("❌ Siz admin emassiz!", show_alert=True)
        return

    admins = await get_all_admins_db()
    lines = ["👑 **Bot Adminlari Ro'yxati:**\n"]
    buttons = []

    for a in admins:
        aid = a["user_id"]
        is_env = a.get("is_env", False)
        status_tag = " (Asosiy .env)" if is_env else ""
        lines.append(f"• `ID: {aid}`{status_tag}")

        if not is_env:
            buttons.append([InlineKeyboardButton(f"🗑 O'chirish (ID: {aid})", callback_data=f"admin_del_{aid}")])

    buttons.append([InlineKeyboardButton("➕ Yangi Admin Qo'shish", callback_data="admin_add")])
    buttons.append([InlineKeyboardButton("🏠 Asosiy Menyuga Qaytish", callback_data="menu_main")])

    await cq.message.edit_text(
        "\n".join(lines),
        reply_markup=InlineKeyboardMarkup(buttons)
    )
    await cq.answer()


@Client.on_callback_query(filters.regex("^admin_add$"))
async def admin_add_callback(client: Client, cq: CallbackQuery):
    user_id = cq.from_user.id
    if not await is_admin(user_id):
        await cq.answer("❌ Ruxsat yo'q!", show_alert=True)
        return

    _admin_input_states[user_id] = "WAIT_ADMIN_ID"
    await cq.message.edit_text(
        "➕ **Yangi Admin Qo'shish**\n\n"
        "Iltimos, yangi admin qilmoqchi bo'lgan foydalanuvchining **Telegram ID** sini yuboring:\n"
        "*(Masalan: `987654321`)*\n\n"
        "*(Bekor qilish uchun /start yuboring)*"
    )
    await cq.answer()


@Client.on_callback_query(filters.regex(r"^admin_del_(\d+)$"))
async def admin_del_callback(client: Client, cq: CallbackQuery):
    user_id = cq.from_user.id
    if not await is_admin(user_id):
        await cq.answer("❌ Ruxsat yo'q!", show_alert=True)
        return

    target_id = int(cq.matches[0].group(1))
    await remove_admin_db(target_id)
    await cq.answer("🗑 Admin ro'yxatdan olib tashlandi!", show_alert=True)
    await admin_menu_callback(client, cq)


from pyrogram import ContinuePropagation

# Kontakt (📞 Nomerni yuborish tugmasi) orqali kelgan nomer — login oqimiga uzatiladi
@Client.on_message(filters.private & filters.contact, group=-6)
async def handle_login_contact(client: Client, message: Message):
    if await process_login_contact_input(client, message):
        return
    raise ContinuePropagation


# State handling for rename, admin input, and login text input
@Client.on_message(filters.private & filters.text & ~filters.command(["start", "menu"]), group=-5)
async def handle_private_text(client: Client, message: Message):
    user_id = message.from_user.id
    txt = (message.text or "").strip()
    # Reply-klaviatura tugmalari shu yerga tushmasligi uchun keyingi handler'ga o'tkazamiz
    if txt in {"🔍 Scraper", "🗂 Bazalar", "📨 Mass DM", "👤 Akkaunt", "👑 Admin Panel"}:
        raise ContinuePropagation
    logger.info(f"[MENU_GROUP_-5] Received text from {user_id}: '{message.text}'")

    # 1. Login flow state
    if await process_login_text_input(client, message):
        return

    # 2. Add Admin state
    if user_id in _admin_input_states:
        _admin_input_states.pop(user_id, None)
        text = message.text.strip()
        if not text.isdigit():
            await message.reply_text("❌ Telegram ID faqat raqamlardan iborat bo'lishi kerak! Qayta kiriting.")
            return

        target_id = int(text)
        await add_admin_db(target_id, added_by=user_id)
        await message.reply_text(
            f"✅ **Yangi admin muvaffaqiyatli qo'shildi!**\n👤 Telegram ID: `{target_id}`",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("👑 Adminlar Menyusi", callback_data="admin_menu")]])
        )
        return

    # 3. Rename state
    if user_id in _rename_states:
        slot = _rename_states.pop(user_id)["slot"]
        new_name = message.text.strip()
        if update_account_name(user_id, slot, new_name):
            await message.reply_text(
                f"✅ **Akkaunt nomi o'zgartirildi:** {new_name}",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("📱 Akkauntlar", callback_data="menu_account_back")]])
            )
        else:
            await message.reply_text("❌ Nomni o'zgartirishda xatolik.")
        return

    raise ContinuePropagation


@Client.on_message(filters.private & filters.text & ~filters.command(["start", "menu"]), group=2)
async def handle_main_reply_buttons(client: Client, message: Message):
    txt = (message.text or "").strip()
    if txt not in {"🔍 Scraper", "🗂 Bazalar", "📨 Mass DM", "👤 Akkaunt", "👑 Admin Panel"}:
        raise ContinuePropagation
    if txt == "👑 Admin Panel":
        # Admin panel'ga yo'naltirish - to'g'ridan-to'g'ri xabar yuborish
        from database import get_admin_stats, is_admin
        if not await is_admin(message.from_user.id):
            await message.reply_text("❌ Siz admin emassiz!")
            return
        stats = await get_admin_stats()
        text = (
            "👑 **Admin Panel**\n\n"
            f"👥 Jami foydalanuvchilar: **{stats['total_users']}** ta\n"
            f"🚫 Ban qilinganlar: **{stats['banned']}** ta\n"
            f"👑 Adminlar: **{stats['admins']}** ta\n"
            f"🗂 Bazalar: **{stats['bazas']}** ta\n\n"
            "Quyidagi bo'limlardan birini tanlang:"
        )
        buttons = [
            [InlineKeyboardButton("👥 Foydalanuvchilar ro'yxati", callback_data="admin_users_list:0")],
            [InlineKeyboardButton("🔍 Foydalanuvchi qidirish", callback_data="admin_search_user")],
            [InlineKeyboardButton("🚫 Ban qilinganlar ro'yxati", callback_data="admin_bans_list:0")],
            [InlineKeyboardButton("➕ Ban qilish (ID)", callback_data="admin_ban_id")],
            [InlineKeyboardButton("🏠 Asosiy Menyuga Qaytish", callback_data="menu_main")],
        ]
        await message.reply_text(text, reply_markup=InlineKeyboardMarkup(buttons))
        return
    if not await _require_account_for_text(client, message):
        return
    if txt == "🔍 Scraper":
        await _open_scraper_from_text(client, message)
    elif txt == "🗂 Bazalar":
        await _open_baza_from_text(client, message)
    elif txt == "📨 Mass DM":
        await _open_massdm_from_text(client, message)
    elif txt == "👤 Akkaunt":
        await _open_account_from_text(client, message)
