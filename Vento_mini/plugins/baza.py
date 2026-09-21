import os
import time
import asyncio
import logging
from datetime import datetime
from pyrogram import Client, filters, ContinuePropagation
from pyrogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from database import (
    get_all_scraped_groups,
    get_group_info,
    get_group_member_count,
    delete_scraped_group,
    generate_unique_group_id,
    add_scraped_group,
    get_members_by_group_paginated,
    get_member_by_index,
    delete_scraped_member_by_row_id,
    add_manual_member,
)
from session_manager import get_user_client
from plugins.menu import check_account_guard

logger = logging.getLogger(__name__)

PAGE_SIZE = 10


def _back_btn(label="🔙 Orqaga", data="admin_baza"):
    return InlineKeyboardButton(label, callback_data=data)


def _home_btn():
    return InlineKeyboardButton("🏠 Bosh menyu", callback_data="menu_main")


def _safe_title(group_title, group_id):
    """Nomsiz yoki noto'g'ri nomli bazalar uchun ID ko'rsatish."""
    if not group_title or not group_title.strip():
        return f"ID: {group_id}"
    first_line = group_title.split("\n")[0].strip()[:40]
    if not first_line or first_line == "." or first_line.startswith("(") and first_line.endswith(")"):
        return f"ID: {group_id}"
    return first_line


# uid -> "waiting_baza_search_id" / "waiting_baza_clear_id" / "waiting_baza_edit|{gid}"
_baza_states = {}

# Tahrirlash oqimi uchun vaqtinchalik holatlar
_baza_edit_add: dict = {}  # uid -> {"gid": ..., "targets": [...]}
_baza_edit_del: dict = {}  # uid -> {"gid": ..., "username": ..., "index": ..., "display": ...}


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


@Client.on_callback_query(filters.regex("^(admin_baza|baza_menu)$"))
async def admin_baza_callback(client: Client, cq: CallbackQuery):
    uid = cq.from_user.id
    if not await check_account_guard(cq):
        return
    await _show_baza_page(cq, uid, 0)
    await cq.answer()


@Client.on_callback_query(filters.regex(r"^admin_baza_page_(\d+)$"))
async def admin_baza_page_callback(client: Client, cq: CallbackQuery):
    uid = cq.from_user.id
    if not await check_account_guard(cq):
        return
    try:
        page = int(cq.matches[0].group(1))
    except (ValueError, IndexError, AttributeError):
        await cq.answer("❌ Sahifa raqami noto'g'ri!", show_alert=True)
        return
    await _show_baza_page(cq, uid, page)
    await cq.answer()


async def _show_baza_page(cq: CallbackQuery, uid: int, page: int):
    """Bazalar ro'yxatini sahifa ko'rinishida ko'rsatish."""
    groups = await get_all_scraped_groups(owner_id=uid)

    if not groups:
        await cq.message.edit_text(
            "🗂 **Bazalar**\n\n📭 Hech qanday baza yo'q.\nScraper orqali yig'ing.",
            reply_markup=InlineKeyboardMarkup(
                [
                    [InlineKeyboardButton("🔍 Scraperni ochish", callback_data="menu_scraper")],
                    [_home_btn()],
                ]
            ),
        )
        return

    total = len(groups)
    total_pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
    page = max(0, min(page, total_pages - 1))
    slice_start = page * PAGE_SIZE
    page_groups = groups[slice_start: slice_start + PAGE_SIZE]

    lines = [f"🗂 **Bazalar ro'yxati** ({total} ta) — {page + 1}/{total_pages}:\n"]
    buttons = []

    for g in page_groups:
        cnt = await get_group_member_count(g["group_id"])
        date_str = datetime.fromtimestamp(g["date_scraped"]).strftime("%d.%m.%Y %H:%M")
        title = _safe_title(g["group_title"], g["group_id"])
        lines.append(
            f"📁 **{title}**\n"
            f"   🆔 `{g['group_id']}` · 👥 {cnt} ta · 📅 {date_str}\n"
        )
        btn_label = f"📁 {title[:28]} ({cnt} ta)"
        buttons.append(
            [InlineKeyboardButton(btn_label, callback_data=f"baza_open_{g['group_id']}")]
        )

    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("⬅️ Oldingi", callback_data=f"admin_baza_page_{page - 1}"))
    if page < total_pages - 1:
        nav.append(InlineKeyboardButton("Keyingi ➡️", callback_data=f"admin_baza_page_{page + 1}"))
    if nav:
        buttons.append(nav)

    buttons.append([InlineKeyboardButton("🔍 ID orqali qidirish", callback_data="baza_search_id")])
    buttons.append([InlineKeyboardButton("🧹 Bazani tozalash", callback_data="baza_clear_menu")])
    buttons.append([_home_btn()])

    await cq.message.edit_text(
        "\n".join(lines), reply_markup=InlineKeyboardMarkup(buttons)
    )


@Client.on_callback_query(filters.regex(r"^baza_open_(.+)$"))
async def baza_open_callback(client: Client, cq: CallbackQuery):
    uid = cq.from_user.id
    gid = cq.matches[0].group(1)

    group = await get_group_info(gid)
    if not group:
        await cq.answer("Baza topilmadi!", show_alert=True)
        return
    if group.get("owner_id") != uid:
        await cq.answer("⛔️ Ruxsat yo'q!", show_alert=True)
        return

    cnt = await get_group_member_count(gid)
    date_str = datetime.fromtimestamp(group["date_scraped"]).strftime("%d.%m.%Y %H:%M")
    safe_title = _safe_title(group['group_title'], gid)

    await cq.message.edit_text(
        f"📁 **{safe_title}**\n\n"
        f"🆔 Baza ID: `{gid}`\n"
        f"👥 A'zolar soni: **{cnt} ta**\n"
        f"📅 Oxirgi yangilanish: {date_str}\n\n"
        "Quyidagi amallardan birini tanlang:",
        reply_markup=InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "📋 Ro'yxatni ko'rish", callback_data=f"baza_list_{gid}_0"
                    )
                ],
                [
                    InlineKeyboardButton(
                        "✏️ Bazani tahrirlash", callback_data=f"baza_edit_{gid}"
                    )
                ],
                [
                    InlineKeyboardButton(
                        "📨 Xabar yuborish", callback_data=f"baza_send_{gid}"
                    )
                ],
                [
                    InlineKeyboardButton(
                        "🗑 Bazani o'chirish", callback_data=f"baza_del_confirm_{gid}"
                    )
                ],
                [_back_btn("🔙 Bazalar ro'yxati", "admin_baza"), _home_btn()],
            ]
        ),
    )
    await cq.answer()


@Client.on_callback_query(filters.regex(r"^baza_list_(.+)_(\d+)$"))
async def baza_list_callback(client: Client, cq: CallbackQuery):
    uid = cq.from_user.id
    gid = cq.matches[0].group(1)
    offset = int(cq.matches[0].group(2))
    limit = 50

    total = await get_group_member_count(gid)
    group = await get_group_info(gid)

    if total == 0:
        await cq.answer("Bazada a'zo yo'q.", show_alert=True)
        return

    # Telegram xabar limiti 4096 harf — belgilarga ham hisobga olib sahifalaymiz.
    MAX_CHARS = 3900
    header = f"👥 **Ro'yxat** (jami {total} ta)\n\n"
    body = []
    cur_len = len(header)
    shown = 0
    next_offset = offset

    while next_offset < total and shown < limit:
        batch = await get_members_by_group_paginated(gid, next_offset, limit)
        if not batch:
            break
        page_done = False
        for m in batch:
            if m["username"]:
                line = f"{next_offset + 1}. @{m['username']}"
            else:
                line = f"{next_offset + 1}. [ID: {m['user_id']}](tg://user?id={m['user_id']})"
            if cur_len + len(line) + 1 > MAX_CHARS and shown > 0:
                page_done = True
                break
            body.append(line)
            cur_len += len(line) + 1
            shown += 1
            next_offset += 1
        if page_done or len(batch) < limit:
            break

    if not body:
        await cq.answer("Bu sahifada a'zo yo'q.", show_alert=True)
        return

    lines = [
        header
        + "\n".join(body)
        + f"\n\n📊 Ko'rsatildi: {offset + 1}-{next_offset} / {total}"
        + "\nℹ️ O'chirish uchun tahrirlashda tartib raqamini yuboring."
    ]

    nav = []
    if offset > 0:
        prev_offset = max(0, offset - limit)
        nav.append(
            InlineKeyboardButton(
                "⬅️ Oldingi", callback_data=f"baza_list_{gid}_{prev_offset}"
            )
        )
    if next_offset < total:
        nav.append(
            InlineKeyboardButton(
                "Keyingi ➡️", callback_data=f"baza_list_{gid}_{next_offset}"
            )
        )

    kb = []
    if nav:
        kb.append(nav)
    kb.append(
        [_back_btn(f"🔙 {group['group_title'][:30]}", f"baza_open_{gid}"), _home_btn()]
    )

    await cq.message.edit_text("\n".join(lines), reply_markup=InlineKeyboardMarkup(kb))
    await cq.answer()


@Client.on_callback_query(filters.regex(r"^baza_edit_(.+)$"))
async def baza_edit_callback(client: Client, cq: CallbackQuery):
    uid = cq.from_user.id
    gid = cq.matches[0].group(1)

    group = await get_group_info(gid)
    if not group or group.get("owner_id") != uid:
        await cq.answer("⛔️ Ruxsat yo'q!", show_alert=True)
        return

    _baza_states[uid] = f"waiting_baza_edit|{gid}"
    await cq.message.edit_text(
        "✏️ **Bazani tahrirlash**\n\n"
        "**1️⃣ User O'CHIRISH:**\n"
        "O'chirmoqchi bo'lgan userning **tartib raqamini** yuboring.\n"
        "_Masalan: `5` — 5-turdagi user o'chiriladi_\n\n"
        "**2️⃣ User QO'SHISH:**\n"
        "Yangi username(lar)ni yuboring (probel yoki yangi qator bilan).\n"
        "_Masalan: `@username1 @username2`_\n\n"
        "⚠️ Notog'ri formatdagi userlar qabul qilinmaydi.",
        reply_markup=InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "❌ Bekor qilish", callback_data=f"baza_open_{gid}"
                    )
                ]
            ]
        ),
    )
    await cq.answer()


@Client.on_callback_query(filters.regex(r"^baza_send_(.+)$"))
async def baza_send_callback(client: Client, cq: CallbackQuery):
    uid = cq.from_user.id
    gid = cq.matches[0].group(1)

    group = await get_group_info(gid)
    if not group or group.get("owner_id") != uid:
        await cq.answer("⛔️ Ruxsat yo'q!", show_alert=True)
        return

    cnt = await get_group_member_count(gid)
    await cq.message.edit_text(
        f"📨 **Xabar yuborish**\n\n"
        f"**{group['group_title']}** bazasidagi **{cnt} ta** foydalanuvchiga xabar yuboriladi.\n\n"
        f"❓ Tasdiqlaysizmi?",
        reply_markup=InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "✅ Ha, tasdiqlayman!", callback_data=f"baza_send_ok_{gid}"
                    ),
                    InlineKeyboardButton(
                        "❌ Yo'q! Adashdim", callback_data=f"baza_open_{gid}"
                    ),
                ]
            ]
        ),
    )
    await cq.answer()


@Client.on_callback_query(filters.regex(r"^baza_send_ok_(.+)$"))
async def baza_send_ok_callback(client: Client, cq: CallbackQuery):
    uid = cq.from_user.id
    gid = cq.matches[0].group(1)

    group = await get_group_info(gid)
    if not group or group.get("owner_id") != uid:
        await cq.answer("⛔️ Ruxsat yo'q!", show_alert=True)
        return

    # MassDM wizard'ni shu baza bilan boshlaymiz
    from plugins.massdm import massdm_states
    massdm_states[uid] = {"state": "WAIT_MSG", "group_id": gid}

    await cq.message.edit_text(
        "📨 **Xabar yuborish**\n\n"
        "Bazadagi barcha foydalanuvchilarga yuboriladigan xabarni yozing:\n\n"
        "_(Matn, rasm yoki video bo'lishi mumkin)_",
        reply_markup=InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "❌ Bekor qilish", callback_data="massdm_cancel"
                    )
                ]
            ]
        ),
    )
    await cq.answer()


@Client.on_callback_query(filters.regex(r"^baza_del_confirm_(.+)$"))
async def baza_del_confirm_callback(client: Client, cq: CallbackQuery):
    uid = cq.from_user.id
    gid = cq.matches[0].group(1)

    group = await get_group_info(gid)
    if not group:
        await cq.answer("Baza topilmadi!", show_alert=True)
        return

    await cq.message.edit_text(
        f"⚠️ **Ishonchingiz komilmi?**\n\n"
        f"**{group['group_title']}** bazasini va undagi barcha a'zolarni o'chirmoqchisiz?",
        reply_markup=InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "✅ Ha, davom etish", callback_data=f"baza_del_final_{gid}"
                    ),
                    InlineKeyboardButton(
                        "❌ Yo'q, orqaga", callback_data=f"baza_open_{gid}"
                    ),
                ]
            ]
        ),
    )
    await cq.answer()


@Client.on_callback_query(filters.regex(r"^baza_del_final_(.+)$"))
async def baza_del_final_callback(client: Client, cq: CallbackQuery):
    uid = cq.from_user.id
    gid = cq.matches[0].group(1)

    group = await get_group_info(gid)
    if not group:
        await cq.answer("Baza topilmadi!", show_alert=True)
        return

    cnt = await get_group_member_count(gid)
    await cq.message.edit_text(
        f"🚨 **OXIRGI TASDIQLASH!**\n\n"
        f"**{group['group_title']}** bazasi va undagi **{cnt} ta** a'zo butunlay o'chiriladi.\n\n"
        f"⛔️ **Bu amalni QAYTARIB BO'LMAYDI!**\n\n"
        f"Rostdan ham o'chirasizmi?",
        reply_markup=InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "🗑 Tushundim, o'chirish!", callback_data=f"baza_del_do_{gid}"
                    ),
                    InlineKeyboardButton(
                        "❌ Yo'q, bekor qilish", callback_data=f"baza_open_{gid}"
                    ),
                ]
            ]
        ),
    )
    await cq.answer()


@Client.on_callback_query(filters.regex(r"^baza_del_do_(.+)$"))
async def baza_del_do_callback(client: Client, cq: CallbackQuery):
    uid = cq.from_user.id
    gid = cq.matches[0].group(1)

    group = await get_group_info(gid)
    if not group or group.get("owner_id") != uid:
        await cq.answer("⛔️ Ruxsat yo'q!", show_alert=True)
        return

    await delete_scraped_group(gid)
    await cq.message.edit_text(
        "🗑 Baza muvaffaqiyatli o'chirildi.",
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("📋 Bazalar ro'yxati", callback_data="admin_baza")]]
        ),
    )
    await cq.answer("O'chirildi!", show_alert=True)


@Client.on_callback_query(filters.regex("^baza_search_id$"))
async def baza_search_id_callback(client: Client, cq: CallbackQuery):
    uid = cq.from_user.id
    groups = await get_all_scraped_groups(owner_id=uid)
    if not groups:
        await cq.answer("Baza bo'sh!", show_alert=True)
        return

    _baza_states[uid] = "waiting_baza_search_id"

    lines = ["🔍 **Baza qidirish / Ochish**\n", "Mavjud bazalar:\n"]
    buttons = []

    for g in groups[:10]:
        cnt = await get_group_member_count(g["group_id"])
        date_str = datetime.fromtimestamp(g["date_scraped"]).strftime("%d.%m.%Y %H:%M")
        lines.append(
            f"📁 **Guruh nomi:** {g['group_title']}\n"
            f"👥 **Yig'ilgan userlari:** {cnt} ta\n"
            f"📅 **Oxirgi yig'ilgan sana:** {date_str}\n"
            f"🆔 **ID:** `{g['group_id']}`\n"
        )
        buttons.append(
            [
                InlineKeyboardButton(
                    f"📁 {g['group_title'][:28]} ({cnt} ta)",
                    callback_data=f"baza_open_{g['group_id']}",
                )
            ]
        )

    lines.append("Bazalardan birini tanlang yoki ID sini kiriting:")

    buttons.append(
        [InlineKeyboardButton("❌ Bekor qilish", callback_data="admin_baza")]
    )

    await cq.message.edit_text(
        "\n".join(lines), reply_markup=InlineKeyboardMarkup(buttons)
    )
    await cq.answer()


@Client.on_callback_query(filters.regex("^baza_clear_menu$"))
async def baza_clear_menu_callback(client: Client, cq: CallbackQuery):
    uid = cq.from_user.id
    groups = await get_all_scraped_groups(owner_id=uid)
    if not groups:
        await cq.answer("Baza bo'sh!", show_alert=True)
        return

    _baza_states[uid] = "waiting_baza_clear_id"

    lines = ["🧹 **Bazani tozalash**\n", "Mavjud bazalar:\n"]
    buttons = []

    for g in groups[:10]:
        cnt = await get_group_member_count(g["group_id"])
        date_str = datetime.fromtimestamp(g["date_scraped"]).strftime("%d.%m.%Y %H:%M")
        lines.append(
            f"📁 **Guruh nomi:** {g['group_title']}\n"
            f"👥 **Yig'ilgan userlari:** {cnt} ta\n"
            f"📅 **Oxirgi yig'ilgan sana:** {date_str}\n"
            f"🆔 **ID:** `{g['group_id']}`\n"
        )
        buttons.append(
            [
                InlineKeyboardButton(
                    f"🗑 {g['group_title'][:28]} ({cnt} ta)",
                    callback_data=f"baza_clear_select_{g['group_id']}",
                )
            ]
        )

    lines.append("Tozalash uchun bazalardan birini tanlang yoki ID sini yozing:")
    buttons.append([_back_btn("🔙 Orqaga", "admin_baza")])

    await cq.message.edit_text(
        "\n".join(lines), reply_markup=InlineKeyboardMarkup(buttons)
    )
    await cq.answer()


@Client.on_callback_query(filters.regex(r"^baza_clear_select_(.+)$"))
async def baza_clear_select_callback(client: Client, cq: CallbackQuery):
    uid = cq.from_user.id
    gid = cq.matches[0].group(1)

    group = await get_group_info(gid)
    if not group or group.get("owner_id") != uid:
        await cq.answer("⛔️ Ruxsat yo'q!", show_alert=True)
        return

    _baza_states.pop(uid, None)
    await cq.message.edit_text(
        f"⚠️ **Ishonchingiz komilmi?**\n\n"
        f"**{group['group_title']}** bazasini va undagi barcha a'zolarni o'chirmoqchisiz?",
        reply_markup=InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "✅ Ha, davom etish", callback_data=f"baza_del_final_{gid}"
                    ),
                    InlineKeyboardButton(
                        "❌ Yo'q, orqaga", callback_data="baza_clear_menu"
                    ),
                ]
            ]
        ),
    )
    await cq.answer()


@Client.on_message(filters.private & filters.text, group=-2)
async def baza_state_handler(client: Client, message: Message):
    uid = message.from_user.id
    state = _baza_states.get(uid)

    if not state:
        raise ContinuePropagation

    # Buyruqlar (/start, /menu va h.k.) hech qachon baza holati sifatida yutilmasin
    if (message.text or "").strip().startswith("/"):
        raise ContinuePropagation

    if state == "waiting_baza_search_id":
        gid = message.text.strip().upper()
        group = await get_group_info(gid)
        if group and group.get("owner_id") != uid:
            group = None
        _baza_states.pop(uid, None)
        if not group:
            await message.reply_text(
                f"❌ `{gid}` ID li baza topilmadi.",
                reply_markup=InlineKeyboardMarkup(
                    [
                        [
                            InlineKeyboardButton(
                                "🔍 Qayta qidirish", callback_data="baza_search_id"
                            )
                        ],
                        [
                            InlineKeyboardButton(
                                "📋 Barcha bazalar", callback_data="admin_baza"
                            )
                        ],
                    ]
                ),
            )
        else:
            cnt = await get_group_member_count(gid)
            date_str = datetime.fromtimestamp(group["date_scraped"]).strftime(
                "%d.%m.%Y %H:%M"
            )
            await message.reply_text(
                f"✅ **Baza topildi!**\n\n"
                f"📁 {group['group_title']}\n"
                f"🆔 `{gid}` · 👥 {cnt} ta · 📅 {date_str}",
                reply_markup=InlineKeyboardMarkup(
                    [
                        [
                            InlineKeyboardButton(
                                "📂 Bazani ochish", callback_data=f"baza_open_{gid}"
                            )
                        ],
                        [
                            InlineKeyboardButton(
                                "📋 Barcha bazalar", callback_data="admin_baza"
                            )
                        ],
                    ]
                ),
            )
        return

    if state == "waiting_baza_clear_id":
        gid = message.text.strip().upper()
        group = await get_group_info(gid)
        if not group or group.get("owner_id") != uid:
            await message.reply_text("❌ Baza topilmadi. Boshqa ID kiriting:")
            return

        _baza_states.pop(uid, None)
        await message.reply_text(
            f"⚠️ **Ishonchingiz komilmi?**\n\n"
            f"**{group['group_title']}** bazasini va undagi barcha a'zolarni o'chirmoqchisiz?",
            reply_markup=InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            "✅ Ha, davom etish", callback_data=f"baza_del_final_{gid}"
                        ),
                        InlineKeyboardButton(
                            "❌ Yo'q, orqaga", callback_data="baza_clear_menu"
                        ),
                    ]
                ]
            ),
        )
        return

    if state.startswith("waiting_baza_edit|"):
        gid = state.replace("waiting_baza_edit|", "")
        group = await get_group_info(gid)
        if not group or group.get("owner_id") != uid:
            await message.reply_text("❌ Ruxsat yo'q!")
            return

        raw = (message.text or "").strip()
        if not raw:
            await message.reply_text("❌ Tartib raqam yoki username yuboring.")
            return

        # 1) Raqam kiritilsa — o'sha tartib raqamdagi user O'CHIRILADI
        if raw.isdigit():
            idx = int(raw)
            total = await get_group_member_count(gid)
            if idx < 1 or idx > total:
                await message.reply_text(
                    f"❌ Tartib raqam **1..{total}** oralig'ida bo'lishi kerak."
                )
                return
            m = await get_member_by_index(gid, idx)
            if not m:
                await message.reply_text("❌ Bu raqamdagi user topilmadi.")
                return

            display = (
                f"@{m['username']}" if m["username"] else f"ID: {m['user_id']}"
            )
            _baza_states.pop(uid, None)
            _baza_edit_del[uid] = {
                "gid": gid,
                "row_id": m["id"],
                "display": display,
            }
            await message.reply_text(
                f"🗑 **O'chirish tasdiqlashi**\n\n"
                f"**{idx}**-tartib raqamdagi user: **{display}**\n\n"
                f"O'sha user bazadan o'chirilsinmi?",
                reply_markup=InlineKeyboardMarkup(
                    [
                        [
                            InlineKeyboardButton(
                                "✅ Ha, o'chirish!", callback_data="baza_edit_del_yes"
                            ),
                            InlineKeyboardButton(
                                "❌ Yo'q, bekor qilish", callback_data="baza_edit_del_no"
                            ),
                        ]
                    ]
                ),
            )
            return

        # 2) Username(lar) kiritilsa — format tekshiruvidan so'ng QO'SHILADI
        targets = [
            t.strip().lstrip("@")
            for t in raw.replace(",", " ").split()
            if t.strip()
        ]
        valid = [t for t in targets if _is_valid_username_format(t)]
        invalid_count = len(targets) - len(valid)

        # Kiritilgan ro'yxat ichidagi takrorlarni olib tashlaymiz (katta-kichik harfdan qat'i nazar)
        seen = set()
        unique = []
        for t in valid:
            if t.lower() not in seen:
                seen.add(t.lower())
                unique.append(t)
        dup_in_input = len(valid) - len(unique)
        valid = unique

        if not valid:
            await message.reply_text(
                "❌ Hech qanday to'g'ri username topilmadi.\n\n"
                "Format: `@username` yoki `username` (faqat harflar, sonlar, `_`, `.`)"
            )
            return

        _baza_states.pop(uid, None)
        _baza_edit_add[uid] = {"gid": gid, "targets": valid}

        note = ""
        if invalid_count:
            note += f"\n⚠️ **{invalid_count} ta** noto'g'ri formatdagi user tashlab yuborildi."
        if dup_in_input:
            note += f"\nℹ️ Kiritilgan ro'yxatda **{dup_in_input} ta** takror olib tashlandi."
        await message.reply_text(
            f"➕ **Yangi user(lar) qo'shish tasdiqlashi**\n\n"
            f"Quyidagi **{len(valid)} ta** userni bazaga qo'shmoqchimisiz?\n\n"
            + "\n".join(f"• @{t}" for t in valid[:20])
            + (f"\n• ...va yana {len(valid) - 20} ta" if len(valid) > 20 else "")
            + note,
            reply_markup=InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            "✅ Ha, qo'shish!", callback_data="baza_edit_add_yes"
                        ),
                        InlineKeyboardButton(
                            "❌ Yo'q, bekor qilish", callback_data="baza_edit_add_no"
                        ),
                    ]
                ]
            ),
        )
        return

    raise ContinuePropagation


async def get_user_client_or_none(uid: int):
    try:
        return await get_user_client(uid)
    except Exception:
        return None


@Client.on_callback_query(filters.regex("^baza_edit_add_yes$"))
async def baza_edit_add_yes_callback(client: Client, cq: CallbackQuery):
    uid = cq.from_user.id
    info = _baza_edit_add.pop(uid, None)
    if not info:
        await cq.answer("Sessiya tugagan, qaytadan bosing.", show_alert=True)
        return

    await cq.answer()
    gid = info["gid"]
    targets = info["targets"]

    added = 0
    skipped = 0
    failed = 0
    for username in targets:
        try:
            # add_manual_member: bazada bo'lsa qo'shmaydi (False qaytaradi)
            if await add_manual_member(gid, username):
                added += 1
            else:
                skipped += 1
        except Exception:
            failed += 1

    result_lines = [f"✅ **Qo'shish yakunlandi!**\n", f"✔️ Qo'shildi: **{added}** ta"]
    if skipped:
        result_lines.append(f"⏭️ Allaqachon bazada bor: **{skipped}** ta")
    if failed:
        result_lines.append(f"❌ Xato: **{failed}** ta")

    await cq.message.edit_text(
        "\n".join(result_lines),
        reply_markup=InlineKeyboardMarkup(
            [
                [InlineKeyboardButton("📂 Bazani ochish", callback_data=f"baza_open_{gid}")],
                [InlineKeyboardButton("🏠 Bosh menyu", callback_data="menu_main")],
            ]
        ),
    )


@Client.on_callback_query(filters.regex("^baza_edit_add_no$"))
async def baza_edit_add_no_callback(client: Client, cq: CallbackQuery):
    uid = cq.from_user.id
    info = _baza_edit_add.pop(uid, None)
    gid = info["gid"] if info else None
    _baza_states.pop(uid, None)
    await cq.message.edit_text(
        "❌ **Amal bekor qilindi.**\n\nHech narsa qo'shilmadi.",
        reply_markup=InlineKeyboardMarkup(
            (
                [[InlineKeyboardButton("📂 Bazani ochish", callback_data=f"baza_open_{gid}")]]
                if gid
                else [[InlineKeyboardButton("📋 Barcha bazalar", callback_data="admin_baza")]]
            )
        ),
    )
    await cq.answer()


@Client.on_callback_query(filters.regex("^baza_edit_del_yes$"))
async def baza_edit_del_yes_callback(client: Client, cq: CallbackQuery):
    uid = cq.from_user.id
    info = _baza_edit_del.pop(uid, None)
    if not info:
        await cq.answer("Sessiya tugagan, qaytadan bosing.", show_alert=True)
        return

    await cq.answer()
    gid = info["gid"]
    display = info["display"]

    deleted = await delete_scraped_member_by_row_id(gid, info["row_id"])
    await cq.message.edit_text(
        (
            f"🗑 **User o'chirildi!**\n\n{display} bazadan o'chirildi."
            if deleted
            else f"❌ **O'chirish amalga oshmadi.**\n\n{display} bazada topilmadi."
        ),
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("📂 Bazani ochish", callback_data=f"baza_open_{gid}")]]
        ),
    )


@Client.on_callback_query(filters.regex("^baza_edit_del_no$"))
async def baza_edit_del_no_callback(client: Client, cq: CallbackQuery):
    uid = cq.from_user.id
    info = _baza_edit_del.pop(uid, None)
    gid = info["gid"] if info else None
    _baza_states.pop(uid, None)
    await cq.message.edit_text(
        "❌ **Amal bekor qilindi.**\n\nHech narsa o'chirilmadi.",
        reply_markup=InlineKeyboardMarkup(
            (
                [[InlineKeyboardButton("📂 Bazani ochish", callback_data=f"baza_open_{gid}")]]
                if gid
                else [[InlineKeyboardButton("📋 Barcha bazalar", callback_data="admin_baza")]]
            )
        ),
    )
    await cq.answer()







