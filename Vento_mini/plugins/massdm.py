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

# Wizard state: uid -> {"state": "WAIT_MSG"|"CONFIRM", "group_id": str, "message": str}
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
    if not groups:
        await cq.message.edit_text(MASSDM_MESSAGES["no_groups"])
        await cq.answer()
        return

    buttons = []
    for group in groups[:10]:
        gid = group["group_id"]
        title = (group["group_title"] or f"ID: {gid}")[:30]
        buttons.append([
            InlineKeyboardButton(f"📁 {title}", callback_data=f"massdm_select_{gid}")
        ])

    buttons.append([InlineKeyboardButton(BUTTON_CANCEL, callback_data="massdm_cancel")])

    await cq.message.edit_text(
        MASSDM_MESSAGES["select_group"],
        reply_markup=InlineKeyboardMarkup(buttons)
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


@Client.on_message(filters.private & filters.text, group=-1)
async def massdm_message_handler(client: Client, message: Message):
    user_id = message.from_user.id
    state_info = massdm_states.get(user_id)

    if not state_info or state_info.get("state") != "WAIT_MSG":
        raise ContinuePropagation

    message_text = (message.text or "").strip()
    massdm_states[user_id] = {
        "state": "CONFIRM",
        "group_id": state_info["group_id"],
        "message": message_text,
    }

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

