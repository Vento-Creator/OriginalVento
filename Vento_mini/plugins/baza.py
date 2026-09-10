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
    add_scraped_member,
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


# uid -> "waiting_baza_search_id" / "waiting_baza_clear_id" /
#        "waiting_baza_add|{gid}" / "waiting_baza_name_for_users" / "waiting_users_for_baza|{title}"
_baza_states = {}


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
                    [InlineKeyboardButton("➕ Yangi user(lar) qo'shish", callback_data="baza_new_users_start")],
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
    buttons.append([InlineKeyboardButton("➕ Yangi user(lar) qo'shish", callback_data="baza_new_users_start")])
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
                        "➕ User qo'shish", callback_data=f"baza_add_{gid}"
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
    page = int(cq.matches[0].group(2))
    limit = 50
    offset = page * limit

    members = await get_members_by_group_paginated(gid, offset, limit)
    total = await get_group_member_count(gid)
    group = await get_group_info(gid)

    if not members:
        await cq.answer("Bu sahifada a'zo yo'q.", show_alert=True)
        return

    lines = [
        f"({offset + 1}-{offset + len(members)})\n"
    ]
    for m in members:
        if m["username"]:
            u = f"@{m['username']}"
        else:
            u = f"[{m['user_id']}](tg://user?id={m['user_id']})"
        lines.append(u)

    nav = []
    if page > 0:
        nav.append(
            InlineKeyboardButton(
                "⬅️ Oldingi", callback_data=f"baza_list_{gid}_{page - 1}"
            )
        )
    if offset + limit < total:
        nav.append(
            InlineKeyboardButton(
                "Keyingi ➡️", callback_data=f"baza_list_{gid}_{page + 1}"
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


@Client.on_callback_query(filters.regex(r"^baza_add_(.+)$"))
async def baza_add_callback(client: Client, cq: CallbackQuery):
    uid = cq.from_user.id
    gid = cq.matches[0].group(1)

    group = await get_group_info(gid)
    if not group or group.get("owner_id") != uid:
        await cq.answer("⛔️ Ruxsat yo'q!", show_alert=True)
        return

    _baza_states[uid] = f"waiting_baza_add|{gid}"
    await cq.message.edit_text(
        "➕ **User qo'shish**\n\n"
        "Username yoki ID larni yuboring (har birini yangi qatorga):\n\n"
        "Masalan:\n`@username1\n@username2\n123456789`",
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

    # MassDM wizard'ni shu baza bilan boshlaymiz
    from plugins.massdm import massdm_states, MASSDM_MESSAGES
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
                        "✅ Ha, o'chirish", callback_data=f"baza_del_do_{gid}"
                    ),
                    InlineKeyboardButton(
                        "❌ Yo'q, orqaga", callback_data=f"baza_open_{gid}"
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
                        "✅ Ha, tozalash", callback_data=f"baza_del_do_{gid}"
                    ),
                    InlineKeyboardButton(
                        "❌ Yo'q, orqaga", callback_data="baza_clear_menu"
                    ),
                ]
            ]
        ),
    )
    await cq.answer()


@Client.on_callback_query(filters.regex("^baza_new_users_start$"))
async def baza_new_users_start_callback(client: Client, cq: CallbackQuery):
    uid = cq.from_user.id
    _baza_states[uid] = "waiting_baza_name_for_users"
    await cq.message.edit_text(
        "➕ **Yangi user(lar) qo'shish**\n\n"
        "Yangi bazaning nomini yuboring:",
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("❌ Bekor qilish", callback_data="admin_baza")]]
        ),
    )
    await cq.answer()


@Client.on_message(filters.private & filters.text, group=-2)
async def baza_state_handler(client: Client, message: Message):
    uid = message.from_user.id
    state = _baza_states.get(uid)

    if not state:
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
                            "✅ Ha, tozalash", callback_data=f"baza_del_do_{gid}"
                        ),
                        InlineKeyboardButton(
                            "❌ Yo'q, orqaga", callback_data="baza_clear_menu"
                        ),
                    ]
                ]
            ),
        )
        return

    if state.startswith("waiting_baza_add|"):
        gid = state.replace("waiting_baza_add|", "")
        group = await get_group_info(gid)
        if not group or group.get("owner_id") != uid:
            await message.reply_text("❌ Ruxsat yo'q!")
            return
        _baza_states.pop(uid, None)
        lines = message.text.strip().split()
        targets = [l.strip().lstrip("@") for l in lines if l.strip()]

        msg = await message.reply_text(f"🔄 {len(targets)} ta user tekshirilmoqda...")

        added = 0
        failed = 0

        try:
            from pyrogram.errors import FloodWait

            user_client = await get_user_client_or_none(uid)
            if not user_client:
                await msg.edit_text("❌ Akkauntingiz ulanmagan. Avval /start bosing.")
                return

            for i, username in enumerate(targets, 1):
                try:
                    u = await user_client.get_users(username)
                    await add_scraped_member(u.id, u.username, u.first_name, gid)
                    added += 1
                except FloodWait as e:
                    await asyncio.sleep(e.value + 1)
                    try:
                        u = await user_client.get_users(username)
                        await add_scraped_member(u.id, u.username, u.first_name, gid)
                        added += 1
                    except Exception:
                        failed += 1
                except Exception:
                    failed += 1

                await asyncio.sleep(0.3)
                if i % 10 == 0:
                    try:
                        await msg.edit_text(
                            f"🔄 {i} / {len(targets)} ta user tekshirilmoqda...\nIltimos kuting..."
                        )
                    except Exception:
                        pass
                    await asyncio.sleep(2)
        except Exception as e:
            await msg.edit_text(f"❌ Xatolik: {e}")
            return

        await msg.edit_text(
            f"✅ Natija:\n\n✔️ Qo'shildi: **{added}** ta\n❌ Xato: **{failed}** ta",
            reply_markup=InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            "📂 Bazani ko'rish", callback_data=f"baza_open_{gid}"
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            "🏠 Bosh menyu", callback_data="menu_main"
                        )
                    ],
                ]
            ),
        )
        return


    if state == "waiting_baza_name_for_users":
        title = message.text.strip().split("\n")[0].strip()[:40]
        if not title:
            await message.reply_text("❌ Baza nomi bo'sh bo'lishi mumkin emas!")
            return
        _baza_states[uid] = f"waiting_users_for_baza|{title}"
        await message.reply_text(
            f"📁 **Baza nomi: {title}**\n\n"
            "Endi qo'shmoqchi bo'lgan userlarni yuboring.\n\n"
            "Formatlar:\n"
            "• Matn: `@username1\n@username2\n@username3`\n"
            "• Forward: Forward xabar yuboring\n\n"
            "Faqat @username bo'lgan userlarni yuboring!",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("❌ Bekor qilish", callback_data="admin_baza")]]
            ),
        )
        return

    if state.startswith("waiting_users_for_baza|") and message.text:
        title = state.replace("waiting_users_for_baza|", "")
        targets = [
            t.strip().lstrip("@")
            for t in message.text.replace(",", " ").split()
            if t.strip()
        ]
        if not targets:
            await message.reply_text(
                "Faqat @username formatida kiriting (masalan: @username1)",
                reply_markup=InlineKeyboardMarkup(
                    [[InlineKeyboardButton("❌ Bekor qilish", callback_data="admin_baza")]]
                ),
            )
            return
        _baza_states[uid] = f"confirm_users|||{title}|||{len(targets)}|||{'|'.join(targets)}"
        await message.reply_text(
            f"📋 **{len(targets)} ta user**\n\n"
            f"**{len(targets)} ta userni bazaga qo'shmoqchimisz?**",
            reply_markup=InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton("✅ Ha, tasdiqlayman!", callback_data="baza_confirm_add_yes"),
                        InlineKeyboardButton("❌ Yo'q, adashdim!", callback_data="baza_confirm_add_no")
                    ]
                ]
            )
        )
        return

    raise ContinuePropagation


def _parse_confirm_users_state(state_str: str):
    """confirm_users|||title|||count|||targets holatini parse qiladi."""
    if not isinstance(state_str, str) or not state_str.startswith("confirm_users"):
        return None
    if "|||" not in state_str:
        return None
    parts = state_str.split("|||")
    if len(parts) < 4:
        return None
    title = parts[1]
    try:
        count = int(parts[2])
    except ValueError:
        return None
    targets_str = parts[3]
    targets = targets_str.split("|") if "|" in targets_str else [targets_str]
    return {"title": title, "count": count, "targets": targets}


async def get_user_client_or_none(uid: int):
    try:
        return await get_user_client(uid)
    except Exception:
        return None


@Client.on_callback_query(filters.regex("^baza_confirm_add_yes$"))
async def baza_confirm_add_yes_callback(client: Client, cq: CallbackQuery):
    uid = cq.from_user.id
    state = _baza_states.get(uid)
    parsed = _parse_confirm_users_state(state)
    if not parsed:
        await cq.answer("Sessiya tugagan, qaytadan bosing.", show_alert=True)
        return

    await cq.answer()

    title = parsed["title"]
    user_list = parsed["targets"]

    gid = await generate_unique_group_id()
    await add_scraped_group(gid, title, int(time.time()), owner_id=uid)
    added = 0
    failed = 0

    user_client = await get_user_client_or_none(uid)
    if user_client:
        from pyrogram.errors import FloodWait

        try:
            try:
                await cq.message.edit_text(f"🔄 0 / {len(user_list)} ta user tekshirilmoqda...\nIltimos kuting...")
            except Exception:
                pass

            for i, username in enumerate(user_list, 1):
                try:
                    u = await user_client.get_users(username)
                    await add_scraped_member(u.id, u.username, u.first_name, gid)
                    added += 1
                except FloodWait as e:
                    await asyncio.sleep(e.value + 1)
                    try:
                        u = await user_client.get_users(username)
                        await add_scraped_member(u.id, u.username, u.first_name, gid)
                        added += 1
                    except Exception:
                        failed += 1
                except Exception:
                    failed += 1

                await asyncio.sleep(0.3)
                if i % 10 == 0:
                    try:
                        await cq.message.edit_text(f"🔄 {i} / {len(user_list)} ta user tekshirilmoqda...\nIltimos kuting...")
                    except Exception:
                        pass
                    await asyncio.sleep(2)
        except Exception as e:
            await cq.message.edit_text(f"❌ Xatolik: {e}")
            _baza_states.pop(uid, None)
            return
    else:
        for username in user_list:
            try:
                await add_scraped_member(0, username, "", gid)
                added += 1
            except Exception:
                failed += 1

    _baza_states.pop(uid, None)
    await cq.message.edit_text(
        f"✅ **Baza yaratildi va userlar qo'shildi!**\n\n"
        f"📁 Baza nomi: **{title}**\n"
        f"🆔 Baza ID: `{gid}`\n"
        f"✅ Qo'shildi: **{added}** ta\n"
        f"❌ Xato: **{failed}** ta",
        reply_markup=InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton("📂 Bazani ochish", callback_data=f"baza_open_{gid}"),
                    InlineKeyboardButton("📋 Barcha bazalar", callback_data="admin_baza")
                ]
            ]
        )
    )


@Client.on_callback_query(filters.regex("^baza_confirm_add_no$"))
async def baza_confirm_add_no_callback(client: Client, cq: CallbackQuery):
    uid = cq.from_user.id
    state = _baza_states.get(uid)
    parsed = _parse_confirm_users_state(state)
    if not parsed:
        await cq.answer("Sessiya tugagan, qaytadan bosing.", show_alert=True)
        return

    await cq.message.edit_text(
        "⚠️ **Amal bekor qilinyabdi!**\n\n"
        "Kiritgan userlaringiz yo'qolib ketadi. Tasdiqlaysizmi?",
        reply_markup=InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton("🗑 Tushunaman, bajarish!", callback_data="baza_cancel_confirm_yes"),
                    InlineKeyboardButton("🔄 Davom etish", callback_data="baza_cancel_confirm_no")
                ]
            ]
        )
    )
    await cq.answer()


@Client.on_callback_query(filters.regex("^baza_cancel_confirm_yes$"))
async def baza_cancel_confirm_yes_callback(client: Client, cq: CallbackQuery):
    uid = cq.from_user.id
    _baza_states.pop(uid, None)
    await cq.message.edit_text(
        "❌ **Amal bekor qilindi.**\n\n"
        "Kiritgan userlaringiz o'chirildi.",
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("📋 Barcha bazalar", callback_data="admin_baza")]]
        )
    )
    await cq.answer()


@Client.on_callback_query(filters.regex("^baza_cancel_confirm_no$"))
async def baza_cancel_confirm_no_callback(client: Client, cq: CallbackQuery):
    uid = cq.from_user.id
    state = _baza_states.get(uid)
    parsed = _parse_confirm_users_state(state)
    if not parsed:
        await cq.answer("Sessiya tugagan, qaytadan bosing.", show_alert=True)
        return

    title = parsed["title"]
    count = parsed["count"]

    await cq.message.edit_text(
        f"📋 **{count} ta user**\n\n"
        f"**{count} ta userni bazaga qo'shmoqchimisz?**",
        reply_markup=InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton("✅ Ha, tasdiqlayman!", callback_data="baza_confirm_add_yes"),
                    InlineKeyboardButton("❌ Yo'q, adashdim!", callback_data="baza_confirm_add_no")
                ]
            ]
        )
    )
    await cq.answer()







