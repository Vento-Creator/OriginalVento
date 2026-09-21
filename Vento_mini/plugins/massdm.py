import asyncio
import logging
from pyrogram import Client, filters, ContinuePropagation
from pyrogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from database import get_all_scraped_groups
from massdm_system.massdm_service import (
    MassDMService,
    stop_user_massdm,
    pause_user_massdm,
    is_massdm_running,
    get_completed_errors,
    get_completed_sent_count,
    MESSAGES as MASSDM_MESSAGES,
)
from plugins.menu import check_account_guard

logger = logging.getLogger(__name__)


def _serialize_entities(entities, trim_offset: int = 0) -> list | None:
    """MessageEntity ro'yxatini dict ko'rinishida saqlash.

    Premium (custom emoji) ham shu entities ichida keladi — uni saqlab
    yuborishda qayta bersak, emoji oddiy holga tushib qolmaydi.
    Bu fallback yo'l uchun (asosiy yo'l: copy_message).

    trim_offset — matn chapidan kesilgan belgilar soni (.lstrip() tufayli);
    entity offset'lar shunga moslab suriladi, aks holda premium emoji
    noto'g'ri joyga tushadi yoki Telegram entity xatosi beradi.
    """
    if not entities:
        return None
    out = []
    for ent in entities:
        try:
            off = getattr(ent, "offset", 0) - trim_offset
            ln = getattr(ent, "length", 0)
            if off < 0:
                # Kesilgan qismga teggan entity — uzunligini qisqartiramiz
                ln = ln + off
                off = 0
            if ln <= 0:
                continue
            d = {
                "type": getattr(ent.type, "name", str(ent.type)) if getattr(ent, "type", None) else None,
                "offset": off,
                "length": ln,
            }
            for attr in ("url", "language", "custom_emoji_id", "date_time_format"):
                val = getattr(ent, attr, None)
                if val is not None:
                    if attr == "custom_emoji_id":
                        # custom_emoji_id int bo'lishi shart (str bo'lsa premium ishlamaydi)
                        try:
                            d[attr] = int(val)
                        except (ValueError, TypeError):
                            continue
                    elif attr == "date_time_format":
                        d[attr] = str(val)
                    else:
                        d[attr] = val
            usr = getattr(ent, "user", None)
            if usr is not None:
                try:
                    d["user"] = {
                        "id": usr.id,
                        "is_bot": getattr(usr, "is_bot", False),
                        "first_name": getattr(usr, "first_name", "") or "user",
                    }
                    d["user_id"] = usr.id  # eski format bilan moslik
                except Exception:
                    pass
            ut = getattr(ent, "unix_time", None)
            if ut is not None:
                try:
                    d["unix_time"] = int(ut)
                except Exception:
                    pass
            out.append(d)
        except Exception:
            continue
    return out or None

# Wizard state: uid -> {"state": "WAIT_MSG"|"CONFIRM", "group_id": str, "message": str,
#   "entities": [...], "from_chat_id": int, "source_msg_id": int}
massdm_states = {}

# Delete wizard state: uid -> {"revoke": bool}
massdm_del_states = {}

# Original Vento MassDMConstants tugmalari
BUTTON_STOP = "⏸️ To'xtatish"
BUTTON_PAUSE = "⏸️ Pauza"
BUTTON_RESUME = "▶️ Davom ettirish"
BUTTON_CANCEL = "❌ Bekor qilish"
BUTTON_CONFIRM = "✅ Tasdiqlash"


@Client.on_callback_query(filters.regex("^(massdm_menu|menu_massdm)$"))
async def massdm_menu_callback(client: Client, cq: CallbackQuery):
    user_id = cq.from_user.id
    if not await check_account_guard(cq):
        return

    if is_massdm_running(user_id):
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton(BUTTON_PAUSE, callback_data="massdm_pause")],
            [InlineKeyboardButton(BUTTON_STOP, callback_data="massdm_stop")],
            [InlineKeyboardButton("🏠 Asosiy menyu", callback_data="menu_main")],
        ])
        await cq.message.edit_text(
            "🚀 **MassDM jarayoni hozirda fonda ishlamoqda!**\n\nBoshqarish uchun tugmalardan foydalaning:",
            reply_markup=kb
        )
        await cq.answer()
        return

    massdm_states.pop(user_id, None)

    groups = await get_all_scraped_groups(owner_id=user_id)

    buttons = []
    for group in groups[:10]:
        gid = group["group_id"]
        title = (group["group_title"] or f"ID: {gid}")[:30]
        buttons.append([
            InlineKeyboardButton(f"📁 {title}", callback_data=f"massdm_select_{gid}")
        ])

    # Bazalar bo'lmasa ham qo'lda user kiritish mumkin (baza yigmasdan MassDM)
    buttons.append([InlineKeyboardButton("👤 Qo'lda user kiritish", callback_data="massdm_manual_users")])
    buttons.append([InlineKeyboardButton(BUTTON_CANCEL, callback_data="massdm_cancel")])

    if not groups:
        menu_text = (
            "📭 **Bazalar yo'q**\n\n"
            "👤 Lekin **Qo'lda user kiritish** orqali username(lar)ni yozib "
            "MassDM yuborishingiz mumkin — baza yigish shart emas."
        )
    else:
        menu_text = MASSDM_MESSAGES["select_group"]

    await cq.message.edit_text(
        menu_text,
        reply_markup=InlineKeyboardMarkup(buttons)
    )
    await cq.answer()


@Client.on_callback_query(filters.regex("^massdm_manual_users$"))
async def massdm_manual_users_callback(client: Client, cq: CallbackQuery):
    user_id = cq.from_user.id

    if is_massdm_running(user_id):
        await cq.answer("⚠️ Sizda allaqachon aktiv MassDM bor!", show_alert=True)
        return

    massdm_states[user_id] = {"state": "WAIT_USERS"}

    await cq.message.edit_text(
        "👤 **Qo'lda user kiritish**\n\n"
        "MassDM yuboriladigan username(lar)ni yuboring:\n\n"
        "_Masalan:_\n"
        "`@username1 @username2 @username3`\n\n"
        "Probel, vergul yoki yangi qator bilan ajratishingiz mumkin.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton(BUTTON_CANCEL, callback_data="massdm_cancel")]
        ])
    )
    await cq.answer()


@Client.on_callback_query(filters.regex(r"^massdm_select_(.+)$"))
async def massdm_select_group_callback(client: Client, cq: CallbackQuery):
    user_id = cq.from_user.id

    if is_massdm_running(user_id):
        await cq.answer("⚠️ Sizda allaqachon aktiv MassDM bor!", show_alert=True)
        return

    gid = cq.matches[0].group(1)
    massdm_states[user_id] = {"state": "WAIT_MSG", "group_id": gid}

    await cq.message.edit_text(
        MASSDM_MESSAGES["enter_message"],
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton(BUTTON_CANCEL, callback_data="massdm_cancel")]
        ])
    )
    await cq.answer()


def _is_valid_username_format(username: str) -> bool:
    """Tezkor username tekshiruvi (get_users chaqirmasdan)."""
    if not username or len(username) < 5:
        return False
    if username.lower().endswith("bot"):  # bot suffix
        return False
    # Channel ID pattern: @cxxxxxxxxxx
    if username.startswith("c") and len(username) >= 10 and username[1:].isdigit():
        return False
    # Faqat harflar, sonlar, _ va . bo'lishi kerak
    if not username.replace("_", "").replace(".", "").isalnum():
        return False
    return True


@Client.on_message(filters.private & filters.text, group=-1)
async def massdm_message_handler(client: Client, message: Message):
    user_id = message.from_user.id
    state_info = massdm_states.get(user_id)

    # Qo'lda user kiritish rejimi
    if state_info and state_info.get("state") == "WAIT_USERS":
        raw = (message.text or "").strip()
        # Buyruqlar (/start va h.k.) username sifatida yutilmasin
        if raw.startswith("/"):
            raise ContinuePropagation
        if not raw:
            await message.reply_text("❌ Username(lar)ni yuboring.")
            return

        targets = [
            t.strip().lstrip("@")
            for t in raw.replace(",", " ").split()
            if t.strip()
        ]
        valid = [t for t in targets if _is_valid_username_format(t)]
        invalid_count = len(targets) - len(valid)

        if not valid:
            await message.reply_text(
                "❌ Hech qanday to'g'ri username topilmadi.\n\n"
                "Format: `@username` (faqat harflar, sonlar, `_`, `.`)"
            )
            return

        manual_members = [{"username": t, "user_id": 0, "first_name": ""} for t in valid]
        massdm_states[user_id] = {
            "state": "WAIT_MSG",
            "group_id": None,
            "manual_members": manual_members,
        }

        note = (
            f"\n⚠️ {invalid_count} ta noto'g'ri formatdagi user tashlab yuborildi."
            if invalid_count
            else ""
        )
        await message.reply_text(
            f"✅ {len(valid)} ta user qabul qilindi.{note}\n\n"
            "📨 Endi ularga yuboriladigan xabarni yozing —\n"
            "xabar yuborishingiz bilan MassDM **avtomatik boshlanadi**.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(BUTTON_CANCEL, callback_data="massdm_cancel")]
            ])
        )
        return

    if not state_info or state_info.get("state") != "WAIT_MSG":
        raise ContinuePropagation

    raw_text = (message.text or "")
    # .strip() offset'larni buzadi (premium emoji noto'g'ri joyga tushadi),
    # shuning uchun chapdagi bo'shliqni hisoblab entity offset'ni to'g'rilaymiz.
    lstripped = raw_text.lstrip()
    ltrim = len(raw_text) - len(lstripped)
    message_text = lstripped.strip()
    # Premium emoji (custom_emoji_id) entities ichida keladi — saqlab qo'yamiz,
    # aks holda yuborishda oddiy emoji bo'lib qoladi.
    entities_keep = _serialize_entities(getattr(message, "entities", None), trim_offset=ltrim)

    # --- Qo'lda kiritilgan userlar: xabar yuborilishi bilan AVTOMATIK boshlanadi ---
    # (baza oqimida esa CONFIRM tasdiqlash bosiladi)
    if state_info.get("manual_members"):
        manual = state_info["manual_members"]
        massdm_states.pop(user_id, None)

        if is_massdm_running(user_id):
            await message.reply_text("⚠️ Sizda allaqachon aktiv MassDM bor!")
            return

        # Status xabari botniki bo'lishi shart — bot faqat o'z xabarini
        # tahrirlab progress ko'rsatadi (user xabarini tahrirlay olmaydi).
        status_msg = await message.reply_text(
            f"🚀 **MassDM boshlanmoqda...**\n\n"
            f"👤 Qo'lda kiritilgan **{len(manual)} ta** userga yuborilmoqda.\n"
            f"✍️ Xabar:\n{message_text[:200]}..."
        )
        ok, err = await MassDMService.start_massdm(
            user_id=user_id,
            bot_client=client,
            chat_id=message.chat.id,
            status_msg_id=status_msg.id,
            group_id=None,
            text_message=message_text,
            entities=entities_keep,
            from_chat_id=message.chat.id,
            source_msg_id=message.id,
            members=manual,
        )
        if not ok:
            await status_msg.edit_text(f"❌ {err}")
            return

        await status_msg.edit_text(
            f"🚀 **MassDM boshlandi!**\n\n"
            f"👤 Qo'lda kiritilgan **{len(manual)} ta** userga yuborilmoqda.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(BUTTON_STOP, callback_data="massdm_stop")]
            ])
        )
        return

    # copy_message manbai — BOT bilan bo'lgan chat (message.chat.id).
    # DM chat id = bot user id bo'ladi, lekin to'g'ridan-to'g'ri
    # message.chat.id olsak ishonchliroq bo'ladi.
    massdm_states[user_id] = {
        "state": "CONFIRM",
        "group_id": state_info["group_id"],
        "manual_members": state_info.get("manual_members"),
        "message": message_text,
        "entities": entities_keep,
        "from_chat_id": message.chat.id,
        "source_msg_id": message.id,
    }

    # Preview: qo'lda kiritilgan userlar yoki baza
    if state_info.get("manual_members"):
        preview = (
            f"👤 Qo'lda kiritilgan userlar: **{len(state_info['manual_members'])} ta**\n\n"
            f"✍️ Xabar:\n{message_text[:200]}..."
        )
    else:
        preview = f"📁 Baza: `{state_info['group_id']}`\n\n✍️ Xabar:\n{message_text[:200]}..."

    await message.reply_text(
        f"{MASSDM_MESSAGES['confirm_start']}\n\n{preview}",
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton(BUTTON_CONFIRM, callback_data="massdm_confirm"),
                InlineKeyboardButton(BUTTON_CANCEL, callback_data="massdm_cancel")
            ]
        ])
    )


@Client.on_callback_query(filters.regex("^massdm_confirm$"))
async def massdm_confirm_callback(client: Client, cq: CallbackQuery):
    user_id = cq.from_user.id
    state_info = massdm_states.pop(user_id, None)

    if not state_info or state_info.get("state") != "CONFIRM":
        await cq.answer("Sessiya tugagan, qaytadan bosing.", show_alert=True)
        return

    if is_massdm_running(user_id):
        await cq.answer("⚠️ Sizda allaqachon aktiv MassDM bor!", show_alert=True)
        return

    group_id = state_info["group_id"]
    message_text = state_info["message"]

    ok, err = await MassDMService.start_massdm(
        user_id=user_id,
        bot_client=client,
        chat_id=cq.message.chat.id,
        status_msg_id=cq.message.id,
        group_id=group_id,
        text_message=message_text,
        entities=state_info.get("entities"),
        from_chat_id=state_info.get("from_chat_id"),
        source_msg_id=state_info.get("source_msg_id"),
        members=state_info.get("manual_members"),
    )

    if not ok:
        await cq.message.edit_text(f"❌ {err}")
        await cq.answer()
        return

    await cq.message.edit_text(
        "🚀 **MassDM boshlandi!**",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton(BUTTON_STOP, callback_data="massdm_stop")]
        ])
    )
    await cq.answer()


@Client.on_callback_query(filters.regex("^massdm_stop$"))
async def massdm_stop_callback(client: Client, cq: CallbackQuery):
    user_id = cq.from_user.id
    stopped = stop_user_massdm(user_id)

    if stopped:
        await cq.answer("🛑 MassDM to'xtatilmoqda...", show_alert=True)
    else:
        await cq.answer("MassDM topilmadi yoki allaqachon yakunlangan.", show_alert=True)


@Client.on_callback_query(filters.regex("^massdm_pause$"))
async def massdm_pause_callback(client: Client, cq: CallbackQuery):
    user_id = cq.from_user.id
    paused = pause_user_massdm(user_id)

    if paused is None or (not paused and not is_massdm_running(user_id)):
        await cq.answer("MassDM topilmadi yoki allaqachon yakunlangan.", show_alert=True)
        return

    status_str = "⏸️ Pauzaga qo'yildi!" if paused else "▶️ Davom ettirilmoqda!"
    await cq.answer(status_str, show_alert=True)


@Client.on_callback_query(filters.regex("^massdm_cancel$"))
async def massdm_cancel_callback(client: Client, cq: CallbackQuery):
    user_id = cq.from_user.id
    massdm_states.pop(user_id, None)

    await cq.message.edit_text("❌ Bekor qilindi.")
    await cq.answer()


@Client.on_callback_query(filters.regex(r"^massdm_errors_(\d+)$"))
async def massdm_errors_callback(client: Client, cq: CallbackQuery):
    user_id = cq.from_user.id
    page = int(cq.matches[0].group(1))

    errors = get_completed_errors(user_id)
    if not errors:
        await cq.answer("Xato ma'lumotlari topilmadi yoki muddati o'tgan.", show_alert=True)
        return

    PER_PAGE = 50
    total = len(errors)
    total_pages = max(1, (total + PER_PAGE - 1) // PER_PAGE)
    page = max(0, min(page, total_pages - 1))

    start = page * PER_PAGE
    chunk = errors[start: start + PER_PAGE]

    # Xato sabablarini sanash
    reason_counts = {}
    for _, reason in chunk:
        reason_counts[reason] = reason_counts.get(reason, 0) + 1

    summary_lines = [
        f"  {reason}: **{count}** ta"
        for reason, count in sorted(reason_counts.items(), key=lambda x: -x[1])
    ]

    header = (
        f"**❌ Xato sabablari ({total} ta)**\n"
        f"_Sahifa {page + 1} / {total_pages}_\n\n"
        + "\n".join(summary_lines)
        + "\n\n" + "─" * 20 + "\n"
    )

    lines = []
    for i, (display, reason) in enumerate(chunk, start + 1):
        lines.append(f"{i}. {display} — {reason}")

    text = header + "\n".join(lines)

    if len(text) > 4090:
        text = text[:4087] + "..."

    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("⬅️ Oldingi", callback_data=f"massdm_errors_{page - 1}"))
    if page < total_pages - 1:
        nav.append(InlineKeyboardButton("Keyingi ➡️", callback_data=f"massdm_errors_{page + 1}"))

    kb = []
    if nav:
        kb.append(nav)
    kb.append([InlineKeyboardButton("🏠 Asosiy menyu", callback_data="menu_main")])

    await cq.message.edit_text(text, reply_markup=InlineKeyboardMarkup(kb))
    await cq.answer()


# --- O'chirish (Delete) wizard: MassDM tugagach, yuborilgan habarlarni tozalash ---

@Client.on_callback_query(filters.regex("^massdm_del_opts$"))
async def massdm_del_opts_callback(client: Client, cq: CallbackQuery):
    user_id = cq.from_user.id

    if get_completed_sent_count(user_id) == 0:
        await cq.answer("O'chirish uchun yuborilgan habarlar topilmadi.", show_alert=True)
        return

    massdm_del_states[user_id] = {}

    await cq.message.edit_text(
        "🗑 **Habararlarni o'chirish**\n\n"
        "**1/2 — Qaysi tomondan o'chirilsin?**",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("👥 Ikkala tomon uchun", callback_data="massdm_del_side_both")],
            [InlineKeyboardButton("🙋 Faqat o'zingiz uchun (1 tomonlama)", callback_data="massdm_del_side_me")],
            [InlineKeyboardButton("❌ Bekor qilish", callback_data="massdm_del_cancel")],
        ])
    )
    await cq.answer()


@Client.on_callback_query(filters.regex(r"^massdm_del_side_(both|me)$"))
async def massdm_del_side_callback(client: Client, cq: CallbackQuery):
    user_id = cq.from_user.id
    side = cq.matches[0].group(1)

    revoke = (side == "both")
    massdm_del_states[user_id] = {"revoke": revoke}
    side_text = "👥 Ikkala tomon uchun" if revoke else "🙋 Faqat o'zingiz uchun"

    await cq.message.edit_text(
        f"🗑 **Habararlarni o'chirish** — {side_text}\n\n"
        "**2/2 — Nima o'chirilsin?**\n\n"
        "⚠️ **Butun lichka** tanlansa, MassDM yuborilgan userlar bilan o'rtangizdagi "
        "**BARCHA** xabarlar o'chiriladi (reklamadan boshqa oddiy suhbatlar ham)!",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🧹 Faqat reklama habari", callback_data="massdm_del_scope_ads")],
            [InlineKeyboardButton("💣 Butun lichka tarixi", callback_data="massdm_del_scope_all")],
            [InlineKeyboardButton("🔙 Orqaga", callback_data="massdm_del_opts")],
        ])
    )
    await cq.answer()


@Client.on_callback_query(filters.regex(r"^massdm_del_scope_(ads|all)$"))
async def massdm_del_scope_callback(client: Client, cq: CallbackQuery):
    user_id = cq.from_user.id
    st = massdm_del_states.pop(user_id, None)

    if not st:
        await cq.answer("Sessiya tugagan, qaytadan bosing.", show_alert=True)
        return

    revoke = st.get("revoke", True)
    full_history = (cq.matches[0].group(1) == "all")

    status = await cq.message.edit_text("🗑 **O'chirilmoqda...**")

    asyncio.create_task(
        MassDMService.run_deletion(
            user_id=user_id,
            bot_client=client,
            chat_id=cq.message.chat.id,
            status_msg_id=status.id,
            revoke=revoke,
            full_history=full_history,
        )
    )
    await cq.answer()


@Client.on_callback_query(filters.regex("^massdm_del_cancel$"))
async def massdm_del_cancel_callback(client: Client, cq: CallbackQuery):
    massdm_del_states.pop(cq.from_user.id, None)
    await cq.message.edit_text("❌ Bekor qilindi.")
    await cq.answer()

