"""Admin: foydalanuvchilarni to'liq boshqarish"""
from pyrogram import Client, filters, ContinuePropagation
from pyrogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from config import is_admin, SESSIONS_DIR, user_states, can_manage_users
from database import (
    get_all_registered_user_ids, search_users, get_user_full_profile,
    get_admin_stats, get_all_banned_users,
    add_or_update_user, remove_user, add_free_user, remove_free_user,
    add_violation, remove_ban, delete_user_databases, delete_scraped_group,
    get_group_member_count, get_members_by_group_paginated, get_group_info,
    register_known_user, get_user_recent_actions,
)
import os
import time
from datetime import datetime

USERS_PER_PAGE = 10
MEMBERS_PER_PAGE = 30


def _admin_cb_filter(_, __, query: CallbackQuery):
    return query.from_user and is_admin(query.from_user.id)

def _admin_msg_filter(_, __, message: Message):
    return message.from_user and is_admin(message.from_user.id)

is_admin_cb = filters.create(_admin_cb_filter)
is_admin_msg = filters.create(_admin_msg_filter)


def _user_label(profile: dict) -> str:
    if profile.get("username"):
        return f"@{profile['username']}"
    if profile.get("first_name"):
        return profile["first_name"]
    return f"ID: {profile['user_id']}"


def _fmt_ts(ts):
    if not ts:
        return "—"
    return datetime.fromtimestamp(ts).strftime("%d.%m.%Y %H:%M")


def _has_session(uid: int) -> bool:
    return os.path.exists(os.path.join(SESSIONS_DIR, f"user_{uid}.session"))


async def _build_profile_text(profile: dict) -> str:
    uid = profile["user_id"]
    now = int(time.time())
    expiry = profile["expiry_date"]
    remaining = (expiry - now) // 86400 if expiry > now else 0

    if is_admin(uid):
        access = "👑 Admin"
    elif profile["is_free"]:
        access = "🆓 Bepul (VIP)"
    elif expiry > now:
        access = f"✅ Obunali ({remaining} kun qoldi)"
    elif expiry > 0:
        access = "❌ Obuna tugagan"
    else:
        access = "⏳ Obunasiz"

    ban = profile["violation_count"]
    ban_str = f"🚫 Bloklangan ({ban} marta)" if ban > 0 else "✅ Blok yo'q"
    session_str = "🔗 Sessiya ulangan" if _has_session(uid) else "❌ Sessiya yo'q"

    lines = [
        f"👤 **Foydalanuvchi profili**\n",
        f"🆔 ID: `{uid}`",
        f"📛 Ism: **{profile.get('first_name') or '—'}**",
        f"🔗 Username: @{profile['username']}" if profile.get("username") else "🔗 Username: yo'q",
        f"📅 Botga qo'shilgan: {_fmt_ts(profile.get('joined_date'))}",
        f"👁 Oxirgi faollik: {_fmt_ts(profile.get('last_seen'))}",
        f"🔐 Kirish: {access}",
        f"⚖️ Holat: {ban_str}",
        f"📱 {session_str}",
        f"\n🗂 **Bazalar:** {profile['database_count']} ta",
        f"👥 **Jami yig'ilgan a'zolar:** {profile['total_members']} ta",
    ]

    if expiry > 0:
        lines.append(f"📆 Obuna muddati: {_fmt_ts(expiry)}")

    if profile["groups"]:
        lines.append("\n📁 **Bazalar ro'yxati:**")
        for g in profile["groups"][:5]:
            cnt = await get_group_member_count(g["group_id"])
            lines.append(f"  • {g['group_title']} — {cnt} ta (`{g['group_id']}`)")
        if len(profile["groups"]) > 5:
            lines.append(f"  ... va yana {len(profile['groups']) - 5} ta")

    return "\n".join(lines)


def _profile_keyboard(uid: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("➕ 7 kun", callback_data=f"adm_sub_{uid}_7"),
            InlineKeyboardButton("➕ 30 kun", callback_data=f"adm_sub_{uid}_30"),
            InlineKeyboardButton("➕ 90 kun", callback_data=f"adm_sub_{uid}_90"),
        ],
        [
            InlineKeyboardButton("➖ Obunani olib tashlash", callback_data=f"adm_unsub_{uid}"),
        ],
        [
            InlineKeyboardButton("🆓 VIP berish", callback_data=f"adm_free_{uid}"),
            InlineKeyboardButton("🔓 VIP olib tashlash", callback_data=f"adm_unfree_{uid}"),
        ],
        [
            InlineKeyboardButton("⚠️ Jazo (ban)", callback_data=f"adm_ban_{uid}"),
            InlineKeyboardButton("✅ Mukofot (unban)", callback_data=f"adm_unban_{uid}"),
        ],
        [
            InlineKeyboardButton("📁 Bazalarini ko'rish", callback_data=f"adm_dbs_{uid}"),
            InlineKeyboardButton("🧹 Bazalarini tozalash", callback_data=f"adm_clear_dbs_{uid}"),
        ],
        [
            InlineKeyboardButton("🗑 Sessiyani o'chirish", callback_data=f"adm_del_sess_{uid}"),
            InlineKeyboardButton("📨 Xabar yuborish", callback_data=f"adm_msg_{uid}"),
        ],
        [
            InlineKeyboardButton("📜 Oxirgi amallar", callback_data=f"adm_acts_{uid}"),
        ],
        [
            InlineKeyboardButton("🔄 Yangilash", callback_data=f"adm_user_{uid}"),
            InlineKeyboardButton("🔙 Foydalanuvchilar", callback_data="adm_users_0"),
        ],
    ])



@Client.on_callback_query(filters.regex("^admin_stats$") & is_admin_cb)
async def admin_stats_callback(client: Client, cq: CallbackQuery):
    if not await can_manage_users(cq.from_user.id):
        await cq.answer("❌ Sizda bu amallni bajarish uchun Foydalanuvchilarni boshqarish yo'q!", show_alert=True)
        return
    stats = await get_admin_stats()
    text = (
        "📊 **Admin Statistika**\n\n"
        f"👥 Jami ma'lum foydalanuvchilar: **{stats['total_known']}** ta\n"
        f"✅ Faol obunalar: **{stats['active_subs']}** ta\n"
        f"📋 Obuna yozuvlari: **{stats['subscribed']}** ta\n"
        f"🆓 Bepul (VIP): **{stats['free']}** ta\n"
        f"🚫 Bloklangan: **{stats['banned']}** ta\n"
        f"🗂 Jami bazalar: **{stats['databases']}** ta\n"
        f"👥 Jami scrape a'zolar: **{stats['total_scraped_members']}** ta"
    )
    await cq.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🔙 Admin panel", callback_data="menu_admin")
        ]])
    )
    await cq.answer()



@Client.on_callback_query(filters.regex(r"^adm_users_(\d+)$") & is_admin_cb)
async def admin_users_list_callback(client: Client, cq: CallbackQuery):
    if not await can_manage_users(cq.from_user.id):
        await cq.answer("❌ Sizda foydalanuvchilarni boshqarish huquqi yo'q!", show_alert=True)
        return
    
    page = int(cq.matches[0].group(1))
    all_ids = await get_all_registered_user_ids()
    total = len(all_ids)

    if not all_ids:
        await cq.message.edit_text(
            "👥 **Foydalanuvchilar**\n\n📭 Hozircha foydalanuvchi yo'q.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Admin panel", callback_data="menu_admin")
            ]])
        )
        await cq.answer()
        return

    start = page * USERS_PER_PAGE
    page_ids = all_ids[start:start + USERS_PER_PAGE]

    lines = [f"👥 **Barcha foydalanuvchilar** (sahifa {page + 1})\n"]
    buttons = []

    for uid in page_ids:
        profile = await get_user_full_profile(uid)
        label = _user_label(profile)
        status = "👑" if is_admin(uid) else ("🆓" if profile["is_free"] else ("🚫" if profile["violation_count"] else "👤"))
        lines.append(f"{status} {label} — `{uid}`")
        buttons.append([InlineKeyboardButton(
            f"{status} {label[:30]}", callback_data=f"adm_user_{uid}"
        )])

    lines.append(f"\n**Jami: {total} ta**")

    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("⬅️", callback_data=f"adm_users_{page - 1}"))
    if start + USERS_PER_PAGE < total:
        nav.append(InlineKeyboardButton("➡️", callback_data=f"adm_users_{page + 1}"))

    kb = buttons
    if nav:
        kb.append(nav)
    kb.append([
        InlineKeyboardButton("🔍 Qidirish", callback_data="adm_search"),
        InlineKeyboardButton("🚫 Bloklanganlar", callback_data="adm_bans"),
    ])
    kb.append([InlineKeyboardButton("🔙 Admin panel", callback_data="menu_admin")])

    await cq.message.edit_text("\n".join(lines), reply_markup=InlineKeyboardMarkup(kb))
    await cq.answer()



@Client.on_callback_query(filters.regex("^adm_search$") & is_admin_cb)
async def admin_search_callback(client: Client, cq: CallbackQuery):
    if not await can_manage_users(cq.from_user.id):
        await cq.answer("❌ Sizda foydalanuvchilarni boshqarish huquqi yo'q!", show_alert=True)
        return
    
    user_states[cq.from_user.id] = "admin_search_user"
    await cq.message.edit_text(
        "🔍 **Foydalanuvchi qidirish**\n\n"
        "User ID yoki @username yuboring:\n"
        "Masalan: `123456789` yoki `@username`",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("❌ Bekor qilish", callback_data="adm_users_0")
        ]])
    )
    await cq.answer()


@Client.on_message(filters.private & filters.text & is_admin_msg)
async def admin_search_handler(client: Client, message: Message):
    uid = message.from_user.id
    state = user_states.get(uid)

    if state == "admin_search_user":
        if not await can_manage_users(uid):
            user_states.pop(uid, None)
            await message.reply_text("❌ Sizda foydalanuvchilarni boshqarish huquqi yo'q!")
            return
        user_states.pop(uid, None)
        query = message.text.strip()
        results = await search_users(query)

        if not results:
            await message.reply_text(
                f"❌ `{query}` bo'yicha hech narsa topilmadi.",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔍 Qayta qidirish", callback_data="adm_search"),
                    InlineKeyboardButton("🔙 Ro'yxat", callback_data="adm_users_0"),
                ]])
            )
            return

        if len(results) == 1:
            profile = await get_user_full_profile(results[0])
            await message.reply_text(
                await _build_profile_text(profile),
                reply_markup=_profile_keyboard(results[0])
            )
            return

        buttons = []
        for ruid in results[:20]:
            profile = await get_user_full_profile(ruid)
            buttons.append([InlineKeyboardButton(
                _user_label(profile), callback_data=f"adm_user_{ruid}"
            )])
        buttons.append([InlineKeyboardButton("🔙 Ro'yxat", callback_data="adm_users_0")])
        await message.reply_text(
            f"🔍 **{len(results)} ta natija topildi:**",
            reply_markup=InlineKeyboardMarkup(buttons)
        )
        return

    state_str = state if isinstance(state, str) else (state.get("state") if isinstance(state, dict) else "")
    if state_str and state_str.startswith("admin_msg_to|"):
        target_id = int(state_str.replace("admin_msg_to|", ""))
        user_states.pop(uid, None)
        try:
            await client.send_message(target_id, f"📨 **Admin xabari:**\n\n{message.text}")
            await message.reply_text(f"✅ Xabar `{target_id}` ga yuborildi.")
        except Exception as e:
            await message.reply_text(f"❌ Xabar yuborib bo'lmadi: {e}")
        return

    raise ContinuePropagation



@Client.on_callback_query(filters.regex(r"^adm_user_(\d+)$") & is_admin_cb)
async def admin_user_profile_callback(client: Client, cq: CallbackQuery):
    if not await can_manage_users(cq.from_user.id):
        await cq.answer("❌ Sizda foydalanuvchilarni boshqarish huquqi yo'q!", show_alert=True)
        return
    
    target_id = int(cq.matches[0].group(1))
    profile = await get_user_full_profile(target_id)

    try:
        tg_user = await client.get_users(target_id)
        if tg_user.username:
            profile["username"] = tg_user.username
        if tg_user.first_name:
            profile["first_name"] = tg_user.first_name
        await register_known_user(target_id, tg_user.username, tg_user.first_name)
    except Exception:
        pass

    await cq.message.edit_text(
        await _build_profile_text(profile),
        reply_markup=_profile_keyboard(target_id)
    )
    await cq.answer()



@Client.on_callback_query(filters.regex("^adm_bans$") & is_admin_cb)
async def admin_bans_callback(client: Client, cq: CallbackQuery):
    if not await can_manage_users(cq.from_user.id):
        await cq.answer("❌ Sizda foydalanuvchilarni boshqarish huquqi yo'q!", show_alert=True)
        return
    
    banned = await get_all_banned_users()

    if not banned:
        await cq.message.edit_text(
            "🚫 **Bloklangan foydalanuvchilar**\n\n📭 Hozircha bloklangan user yo'q.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Foydalanuvchilar", callback_data="adm_users_0")
            ]])
        )
        await cq.answer()
        return

    lines = ["🚫 **Bloklangan foydalanuvchilar:**\n"]
    buttons = []
    for b in banned:
        profile = await get_user_full_profile(b["user_id"])
        label = _user_label(profile)
        lines.append(f"• {label} — {b['violation_count']} marta (`{b['user_id']}`)")
        buttons.append([InlineKeyboardButton(
            f"👤 {label[:25]} ({b['violation_count']}x)", callback_data=f"adm_user_{b['user_id']}"
        )])

    buttons.append([InlineKeyboardButton("🔙 Foydalanuvchilar", callback_data="adm_users_0")])
    await cq.message.edit_text("\n".join(lines), reply_markup=InlineKeyboardMarkup(buttons))
    await cq.answer()



@Client.on_callback_query(filters.regex(r"^adm_sub_(\d+)_(\d+)$") & is_admin_cb)
async def admin_give_sub_callback(client: Client, cq: CallbackQuery):
    if not await can_manage_users(cq.from_user.id):
        await cq.answer("❌ Sizda foydalanuvchilarni boshqarish huquqi yo'q!", show_alert=True)
        return
    
    target_id = int(cq.matches[0].group(1))
    days = int(cq.matches[0].group(2))
    expiry = int(time.time()) + days * 86400

    username = first_name = None
    try:
        u = await client.get_users(target_id)
        username, first_name = u.username, u.first_name
    except Exception:
        pass

    await add_or_update_user(target_id, expiry, username, first_name)
    await cq.answer(f"✅ {days} kunlik obuna berildi!", show_alert=True)

    try:
        await client.send_message(
            target_id,
            f"🎉 **Mukofot!** Sizga admin tomonidan **{days} kunlik obuna** berildi!\n/start"
        )
    except Exception:
        pass

    profile = await get_user_full_profile(target_id)
    await cq.message.edit_text(
        await _build_profile_text(profile),
        reply_markup=_profile_keyboard(target_id)
    )


@Client.on_callback_query(filters.regex(r"^adm_unsub_(\d+)$") & is_admin_cb)
async def admin_remove_sub_callback(client: Client, cq: CallbackQuery):
    if not await can_manage_users(cq.from_user.id):
        await cq.answer("❌ Sizda foydalanuvchilarni boshqarish huquqi yo'q!", show_alert=True)
        return
    
    target_id = int(cq.matches[0].group(1))
    await remove_user(target_id)
    await cq.answer("Obuna olib tashlandi!", show_alert=True)
    try:
        await client.send_message(target_id, "❌ Obunangiz admin tomonidan o'chirildi.")
    except Exception:
        pass
    profile = await get_user_full_profile(target_id)
    await cq.message.edit_text(
        await _build_profile_text(profile),
        reply_markup=_profile_keyboard(target_id)
    )



@Client.on_callback_query(filters.regex(r"^adm_free_(\d+)$") & is_admin_cb)
async def admin_free_callback(client: Client, cq: CallbackQuery):
    if not await can_manage_users(cq.from_user.id):
        await cq.answer("❌ Sizda foydalanuvchilarni boshqarish huquqi yo'q!", show_alert=True)
        return
    
    target_id = int(cq.matches[0].group(1))
    await add_free_user(target_id)
    await cq.answer("VIP berildi!", show_alert=True)
    try:
        await client.send_message(
            target_id,
            "🎉 **Mukofot!** Siz admin tomonidan bepul (VIP) foydalanuvchi qilindingiz!\n/start"
        )
    except Exception:
        pass
    profile = await get_user_full_profile(target_id)
    await cq.message.edit_text(
        await _build_profile_text(profile),
        reply_markup=_profile_keyboard(target_id)
    )


@Client.on_callback_query(filters.regex(r"^adm_unfree_(\d+)$") & is_admin_cb)
async def admin_unfree_callback(client: Client, cq: CallbackQuery):
    if not await can_manage_users(cq.from_user.id):
        await cq.answer("❌ Sizda foydalanuvchilarni boshqarish huquqi yo'q!", show_alert=True)
        return
    
    target_id = int(cq.matches[0].group(1))
    await remove_free_user(target_id)
    await cq.answer("VIP olib tashlandi!", show_alert=True)
    profile = await get_user_full_profile(target_id)
    await cq.message.edit_text(
        await _build_profile_text(profile),
        reply_markup=_profile_keyboard(target_id)
    )



@Client.on_callback_query(filters.regex(r"^adm_ban_(\d+)$") & is_admin_cb)
async def admin_ban_callback(client: Client, cq: CallbackQuery):
    if not await can_manage_users(cq.from_user.id):
        await cq.answer("❌ Sizda foydalanuvchilarni boshqarish huquqi yo'q!", show_alert=True)
        return
    
    target_id = int(cq.matches[0].group(1))
    count = await add_violation(target_id)
    await cq.answer(f"Jazo berildi! ({count} marta)", show_alert=True)
    try:
        if count == 1:
            await client.send_message(target_id, "⚠️ **Jazo:** Siz bot qoidalarini buzdingiz!")
        else:
            await client.send_message(
                target_id,
                "🚨 **QATTIQ JAZO!** Qoidabuzarliklar davom etmoqda!",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("⚖️ Qonunchilik", callback_data="show_laws")
                ]])
            )
    except Exception:
        pass
    profile = await get_user_full_profile(target_id)
    await cq.message.edit_text(
        await _build_profile_text(profile),
        reply_markup=_profile_keyboard(target_id)
    )


@Client.on_callback_query(filters.regex(r"^adm_unban_(\d+)$") & is_admin_cb)
async def admin_unban_callback(client: Client, cq: CallbackQuery):
    if not await can_manage_users(cq.from_user.id):
        await cq.answer("❌ Sizda foydalanuvchilarni boshqarish huquqi yo'q!", show_alert=True)
        return
    
    target_id = int(cq.matches[0].group(1))
    await remove_ban(target_id)
    await cq.answer("Mukofot: blokdan chiqarildi!", show_alert=True)
    try:
        await client.send_message(
            target_id,
            "✅ **Mukofot!** Blokdan chiqarildingiz. Botdan foydalanishni davom ettiring."
        )
    except Exception:
        pass
    profile = await get_user_full_profile(target_id)
    await cq.message.edit_text(
        await _build_profile_text(profile),
        reply_markup=_profile_keyboard(target_id)
    )



@Client.on_callback_query(filters.regex(r"^adm_dbs_(\d+)$") & is_admin_cb)
async def admin_user_dbs_callback(client: Client, cq: CallbackQuery):
    if not await can_manage_users(cq.from_user.id):
        await cq.answer("❌ Sizda foydalanuvchilarni boshqarish huquqi yo'q!", show_alert=True)
        return
    
    target_id = int(cq.matches[0].group(1))
    profile = await get_user_full_profile(target_id)

    if not profile["groups"]:
        await cq.answer("Bu foydalanuvchida baza yo'q!", show_alert=True)
        return

    lines = [f"🗂 **{_user_label(profile)} bazalari:**\n"]
    buttons = []
    for g in profile["groups"]:
        cnt = await get_group_member_count(g["group_id"])
        date_str = _fmt_ts(g["date_scraped"])
        lines.append(f"📁 **{g['group_title']}** — {cnt} ta · {date_str} · `{g['group_id']}`")
        buttons.append([
            InlineKeyboardButton(f"📋 {g['group_title'][:20]}", callback_data=f"adm_db_list_{g['group_id']}_0"),
            InlineKeyboardButton("🗑", callback_data=f"adm_db_del_{g['group_id']}_{target_id}"),
        ])

    buttons.append([InlineKeyboardButton("🔙 Profil", callback_data=f"adm_user_{target_id}")])
    await cq.message.edit_text("\n".join(lines), reply_markup=InlineKeyboardMarkup(buttons))
    await cq.answer()


@Client.on_callback_query(filters.regex(r"^adm_db_list_(.+)_(\d+)$") & is_admin_cb)
async def admin_db_members_callback(client: Client, cq: CallbackQuery):
    if not await can_manage_users(cq.from_user.id):
        await cq.answer("❌ Sizda foydalanuvchilarni boshqarish huquqi yo'q!", show_alert=True)
        return
    
    gid = cq.matches[0].group(1)
    page = int(cq.matches[0].group(2))
    group = await get_group_info(gid)
    if not group:
        await cq.answer("Baza topilmadi!", show_alert=True)
        return

    offset = page * MEMBERS_PER_PAGE
    members = await get_members_by_group_paginated(gid, offset, MEMBERS_PER_PAGE)
    total = await get_group_member_count(gid)

    lines = [f"📋 **{group['group_title']}** — a'zolar ({total} ta)\n"]
    for i, m in enumerate(members, start=offset + 1):
        uname = f"@{m['username']}" if m.get("username") else "—"
        fname = m.get("first_name") or "—"
        lines.append(f"{i}. {fname} · {uname} · `{m['user_id']}`")

    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("⬅️", callback_data=f"adm_db_list_{gid}_{page - 1}"))
    if offset + MEMBERS_PER_PAGE < total:
        nav.append(InlineKeyboardButton("➡️", callback_data=f"adm_db_list_{gid}_{page + 1}"))

    kb = []
    if nav:
        kb.append(nav)
    kb.append([InlineKeyboardButton("🔙 Orqaga", callback_data=f"adm_dbs_{group.get('owner_id', 0)}")])
    await cq.message.edit_text("\n".join(lines), reply_markup=InlineKeyboardMarkup(kb))
    await cq.answer()


@Client.on_callback_query(filters.regex(r"^adm_db_del_(.+)_(\d+)$") & is_admin_cb)
async def admin_db_del_callback(client: Client, cq: CallbackQuery):
    if not await can_manage_users(cq.from_user.id):
        await cq.answer("❌ Sizda foydalanuvchilarni boshqarish huquqi yo'q!", show_alert=True)
        return
    
    gid = cq.matches[0].group(1)
    target_id = int(cq.matches[0].group(2))
    group = await get_group_info(gid)
    if not group:
        await cq.answer("Baza topilmadi!", show_alert=True)
        return

    await delete_scraped_group(gid)
    await cq.answer(f"'{group['group_title']}' o'chirildi!", show_alert=True)

    profile = await get_user_full_profile(target_id)
    if not profile["groups"]:
        await cq.message.edit_text(
            await _build_profile_text(profile),
            reply_markup=_profile_keyboard(target_id)
        )
        return

    lines = [f"🗂 **{_user_label(profile)} bazalari:**\n"]
    buttons = []
    for g in profile["groups"]:
        cnt = await get_group_member_count(g["group_id"])
        lines.append(f"📁 **{g['group_title']}** — {cnt} ta · `{g['group_id']}`")
        buttons.append([
            InlineKeyboardButton(f"📋 {g['group_title'][:20]}", callback_data=f"adm_db_list_{g['group_id']}_0"),
            InlineKeyboardButton("🗑", callback_data=f"adm_db_del_{g['group_id']}_{target_id}"),
        ])
    buttons.append([InlineKeyboardButton("🔙 Profil", callback_data=f"adm_user_{target_id}")])
    await cq.message.edit_text("\n".join(lines), reply_markup=InlineKeyboardMarkup(buttons))


@Client.on_callback_query(filters.regex(r"^adm_clear_dbs_(\d+)$") & is_admin_cb)
async def admin_clear_dbs_confirm_callback(client: Client, cq: CallbackQuery):
    if not await can_manage_users(cq.from_user.id):
        await cq.answer("❌ Sizda foydalanuvchilarni boshqarish huquqi yo'q!", show_alert=True)
        return
    
    target_id = int(cq.matches[0].group(1))
    profile = await get_user_full_profile(target_id)
    await cq.message.edit_text(
        f"⚠️ **{_user_label(profile)}** ning **{profile['database_count']}** ta bazasini o'chirishni tasdiqlaysizmi?\n"
        f"Jami **{profile['total_members']}** ta a'zo o'chiriladi!",
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton("✅ Ha, tozalash", callback_data=f"adm_clear_do_{target_id}"),
                InlineKeyboardButton("❌ Yo'q", callback_data=f"adm_user_{target_id}"),
            ]
        ])
    )
    await cq.answer()


@Client.on_callback_query(filters.regex(r"^adm_clear_do_(\d+)$") & is_admin_cb)
async def admin_clear_dbs_do_callback(client: Client, cq: CallbackQuery):
    if not await can_manage_users(cq.from_user.id):
        await cq.answer("❌ Sizda foydalanuvchilarni boshqarish huquqi yo'q!", show_alert=True)
        return
    
    target_id = int(cq.matches[0].group(1))
    deleted = await delete_user_databases(target_id)
    await cq.answer(f"{deleted} ta baza o'chirildi!", show_alert=True)
    profile = await get_user_full_profile(target_id)
    await cq.message.edit_text(
        await _build_profile_text(profile),
        reply_markup=_profile_keyboard(target_id)
    )



@Client.on_callback_query(filters.regex(r"^adm_del_sess_(\d+)$") & is_admin_cb)
async def admin_del_session_callback(client: Client, cq: CallbackQuery):
    if not await can_manage_users(cq.from_user.id):
        await cq.answer("❌ Sizda foydalanuvchilarni boshqarish huquqi yo'q!", show_alert=True)
        return
    
    target_id = int(cq.matches[0].group(1))
    # Sessiya faylini o'chirmaymiz - Owner panelida akkaunt qaytarish uchun kerak
    # Faqat xotiradagi clientni yopamiz
    from session_manager import close_user_client
    await close_user_client(target_id)

    await cq.answer("Sessiya xotiradan yopildi!", show_alert=True)
    profile = await get_user_full_profile(target_id)
    await cq.message.edit_text(
        await _build_profile_text(profile),
        reply_markup=_profile_keyboard(target_id)
    )



@Client.on_message(filters.command("user") & is_admin_msg)
async def admin_user_command(client: Client, message: Message):
    if not await can_manage_users(message.from_user.id):
        await message.reply_text("❌ Sizda foydalanuvchilarni boshqarish huquqi yo'q!")
        return
    
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.reply_text("Format: `/user [user_id yoki @username]`")
        return

    results = await search_users(args[1])
    if not results:
        await message.reply_text(f"❌ `{args[1]}` topilmadi.")
        return

    target_id = results[0]
    profile = await get_user_full_profile(target_id)
    try:
        tg_user = await client.get_users(target_id)
        profile["username"] = tg_user.username or profile.get("username")
        profile["first_name"] = tg_user.first_name or profile.get("first_name")
    except Exception:
        pass

    await message.reply_text(
        await _build_profile_text(profile),
        reply_markup=_profile_keyboard(target_id)
    )


@Client.on_callback_query(filters.regex(r"^adm_msg_(\d+)$") & is_admin_cb)
async def admin_msg_callback(client: Client, cq: CallbackQuery):
    if not await can_manage_users(cq.from_user.id):
        await cq.answer("❌ Sizda foydalanuvchilarni boshqarish huquqi yo'q!", show_alert=True)
        return
    
    target_id = int(cq.matches[0].group(1))
    user_states[cq.from_user.id] = f"admin_msg_to|{target_id}"
    await cq.message.edit_text(
        f"📨 **Xabar yuborish** — `{target_id}`\n\n"
        "Yubormoqchi bo'lgan xabaringizni yozing:",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("❌ Bekor qilish", callback_data=f"adm_user_{target_id}")
        ]])
    )
    await cq.answer()


@Client.on_callback_query(filters.regex(r"^adm_acts_(\d+)(?:_(list|profile))?$") & is_admin_cb)
async def admin_user_actions_callback(client: Client, cq: CallbackQuery):
    if not await can_manage_users(cq.from_user.id):
        await cq.answer("❌ Sizda foydalanuvchilarni boshqarish huquqi yo'q!", show_alert=True)
        return
    
    target_id = int(cq.matches[0].group(1))
    source = cq.matches[0].group(2) or "profile"
    
    actions = await get_user_recent_actions(target_id, limit=10)
    
    if not actions:
        await cq.answer("Foydalanuvchining oxirgi amallari topilmadi.", show_alert=True)
        return
        
    profile = await get_user_full_profile(target_id)
    lines = [f"📜 **{_user_label(profile)}** ning oxirgi amallari:\n"]
    
    for i, act in enumerate(actions, 1):
        date_str = _fmt_ts(act["timestamp"])
        lines.append(f"{i}) {act['action']} • {date_str}")
        
    if source == "list":
        back_btn = InlineKeyboardButton("🔙 Ro'yxatga qaytish", callback_data="adm_acts_list_0")
    else:
        back_btn = InlineKeyboardButton("🔙 Profilga qaytish", callback_data=f"adm_user_{target_id}")
        
    await cq.message.edit_text(
        "\n".join(lines),
        reply_markup=InlineKeyboardMarkup([[back_btn]])
    )
    await cq.answer()


@Client.on_callback_query(filters.regex(r"^adm_acts_list_(\d+)$") & is_admin_cb)
async def admin_acts_list_callback(client: Client, cq: CallbackQuery):
    if not await can_manage_users(cq.from_user.id):
        await cq.answer("❌ Sizda foydalanuvchilarni boshqarish huquqi yo'q!", show_alert=True)
        return
    
    page = int(cq.matches[0].group(1))
    all_ids = await get_all_registered_user_ids()
    total = len(all_ids)

    if not all_ids:
        await cq.message.edit_text(
            "📜 **Oxirgi harakatlar**\n\n📭 Hozircha foydalanuvchi yo'q.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Admin panel", callback_data="menu_admin")
            ]])
        )
        await cq.answer()
        return

    start = page * USERS_PER_PAGE
    page_ids = all_ids[start:start + USERS_PER_PAGE]

    lines = [f"📜 **Oxirgi harakatlarni ko'rish** (sahifa {page + 1})\n\nQaysi foydalanuvchining amallarini ko'rmoqchisiz?"]
    buttons = []

    for uid in page_ids:
        profile = await get_user_full_profile(uid)
        label = _user_label(profile)
        buttons.append([InlineKeyboardButton(
            f"👤 {label[:30]}", callback_data=f"adm_acts_{uid}_list"
        )])

    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("⬅️", callback_data=f"adm_acts_list_{page - 1}"))
    if start + USERS_PER_PAGE < total:
        nav.append(InlineKeyboardButton("➡️", callback_data=f"adm_acts_list_{page + 1}"))

    kb = buttons
    if nav:
        kb.append(nav)
    kb.append([InlineKeyboardButton("🔙 Admin panel", callback_data="menu_admin")])

    await cq.message.edit_text("\n".join(lines), reply_markup=InlineKeyboardMarkup(kb))
    await cq.answer()
