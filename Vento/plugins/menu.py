from pyrogram import Client, filters, ContinuePropagation
from pyrogram.types import (
    Message, InlineKeyboardMarkup, InlineKeyboardButton,
    CallbackQuery, ReplyKeyboardMarkup, KeyboardButton, WebAppInfo
)
from database import get_user_subscription, is_free_user, register_known_user, get_unread_updates_count, get_update_notification_pref, get_known_user
import os
from config import SUPER_ADMIN_ID, SECOND_ADMIN_ID, SESSIONS_DIR, user_states, login_data, is_admin, MINI_APP_URL
from rate_limiter import check_rate_limit
from login_system import login_service, LoginState
import logging

logger = logging.getLogger(__name__)

PENDING_DIR = os.path.join(SESSIONS_DIR, "pending")

def _is_admin(uid: int) -> bool:
    return is_admin(uid)

def _has_session(uid: int) -> bool:
    """Multi-account: har qanday slotda session fayl bo'lsa True."""
    try:
        from session_manager import has_active_sessions
        return has_active_sessions(uid)
    except Exception:
        return os.path.exists(os.path.join(SESSIONS_DIR, f"user_{uid}.session"))

async def _has_access(uid: int) -> bool:
    if _is_admin(uid):
        return True
    if await is_free_user(uid):
        return True
    return (await get_user_subscription(uid)) > 0

async def get_main_keyboard(uid: int) -> ReplyKeyboardMarkup:
    sess = _has_session(uid)
    acc  = await _has_access(uid)
    adm  = _is_admin(uid)

    # Referral tizimi admin tomonidan o'chirilgan bo'lsa tugma ko'rinmaydi
    try:
        from feature_flags import is_referral_enabled
        referral_on = await is_referral_enabled()
    except Exception:
        referral_on = True

    if sess and acc:
        has_paid_sub = (await get_user_subscription(uid)) > 0
        is_free = await is_free_user(uid)

        rows = [
            [KeyboardButton("🔍 Scraper"),   KeyboardButton("🗂 Bazalar")],
            [KeyboardButton("📨 Mass DM"),   KeyboardButton("🏷 Utag")],
            [KeyboardButton("💬 Chatlar"),   KeyboardButton("🔍 Guruh qidirish")],
        ]
        if adm:
            rows.append([KeyboardButton("🌐 Til"), KeyboardButton("⚙️ Funksiyalar")])
        else:
            rows.append([KeyboardButton("🌐 Til")])
        if is_free and not has_paid_sub and not adm:
            sub_row = [KeyboardButton("⭐️ Obuna sotib olish")]
            if referral_on:
                sub_row.append(KeyboardButton("👥 Takliflar"))
            rows.append(sub_row)
            rows.append([KeyboardButton("👤 Akkaunt")])
        else:
            acc_row = [KeyboardButton("👤 Akkaunt")]
            if referral_on:
                acc_row.insert(0, KeyboardButton("👥 Takliflar"))
            rows.append(acc_row)
        
        if not adm:
            rows.append([KeyboardButton("📞 Bog'lanish")])
        if adm:
            rows.append([KeyboardButton("🛠 Admin Panel")])
            if uid == SUPER_ADMIN_ID:
                rows.append([KeyboardButton("👑 Owner Panel"), KeyboardButton("📣 Yangiliklar")])
            else:
                rows.append([KeyboardButton("📣 Yangiliklar")])
        else:
            rows.append([KeyboardButton("📣 Yangiliklar")])
    elif sess:
        sub_row = [KeyboardButton("⭐️ Obuna sotib olish")]
        if referral_on:
            sub_row.append(KeyboardButton("👥 Takliflar"))
        rows = [
            sub_row,
            [KeyboardButton("👤 Akkaunt")],
            [KeyboardButton("📣 Yangiliklar")],
            [KeyboardButton("🌐 Til")],
        ]
    else:
        obuna_row = [KeyboardButton("⭐️ Obuna haqida")]
        if referral_on:
            obuna_row.append(KeyboardButton("👥 Takliflar"))
        rows = [
            [KeyboardButton("📱 Akkaunt ulash")],
            obuna_row,
        ]
    return ReplyKeyboardMarkup(rows, resize_keyboard=True)

async def get_minimal_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup([[KeyboardButton("🔙 Bosh menyu")]], resize_keyboard=True)

_MENU_TEXTS = {
    "🔍 Scraper", "🗂 Bazalar", "📨 Mass DM", "🏷 Utag",
    "⭐️ Obuna", "⭐️ Obuna sotib olish", "⭐️ Obuna haqida",
    "👤 Akkaunt", "🛠 Admin Panel", "📱 Akkaunt ulash", "🔙 Bosh menyu",
    "📣 Yangiliklar", "📞 Bog'lanish", "💬 Chatlar", "🌐 Til",
    "⚙️ Funksiyalar", "👥 Takliflar",
}

@Client.on_message(filters.private & filters.text, group=-10)
async def state_cleaner(client: Client, message: Message):
    txt = (message.text or "").strip()
    uid = message.from_user.id
    current_state = user_states.get(uid)
    logger.debug(f"[DIAG_STATE_CLEANER] User {uid}, text={txt[:30]}, state={current_state}")
    
    # If user sends a command (like /start) or a menu button, force-reset states to prevent getting trapped
    if txt.startswith("/") or txt in _MENU_TEXTS:
        user_states.pop(uid, None)
        try:
            from login_system import login_service
            await login_service.state_manager.cleanup_session(uid)
            login_service.session_manager.cleanup_pending(uid)
        except Exception:
            pass
        raise ContinuePropagation
    
    # Don't interfere with login states for normal text - let login handlers handle them
    if current_state in ["waiting_for_phone", "waiting_for_code", "waiting_for_password", "waiting_for_admin_approval"]:
        raise ContinuePropagation
    if current_state in ["waiting_contact_subject", "waiting_contact_message", "chat_viewing_chats", "chat_viewing_messages", "chat_sending_message", "chat_searching_user", "group_search_state"]:
        raise ContinuePropagation
    if current_state and current_state.startswith("waiting_for_timer_"):
        raise ContinuePropagation
    raise ContinuePropagation

@Client.on_message(filters.command("start") & filters.private)
async def start_handler(client: Client, message: Message):
    logger.info("[START_TRACE] STEP1: Handler entered")
    logger.info(f"[DIAGNOSTIC] /start received from user {message.from_user.id if message.from_user else 'unknown'}")

    try:
        uid  = message.from_user.id
        name = message.from_user.first_name
        logger.info(f"[START_TRACE] STEP2: Got uid={uid}, name={name}")

        # Referral deep-link capture: /start ref_<referrer_id>
        # Runs before auth checks so the invite is recorded even when the
        # invitee is still unauthenticated / pending approval.
        try:
            from feature_flags import is_referral_enabled
            referral_on = await is_referral_enabled()
        except Exception:
            referral_on = True
        try:
            if referral_on:
                parts = (message.text or "").split()
                if len(parts) > 1 and parts[1].startswith("ref_") and parts[1][4:].isdigit():
                    ref_id = int(parts[1][4:])
                    if ref_id and ref_id != uid:
                        from database import set_user_referrer, apply_referral_bonus, REFERRAL_BONUS_REGISTRATION_DAYS
                        if await set_user_referrer(uid, ref_id):
                            if await apply_referral_bonus(ref_id, REFERRAL_BONUS_REGISTRATION_DAYS):
                                try:
                                    await client.send_message(
                                        ref_id,
                                        f"🎉 **Yangi taklif!**\n\n"
                                        f"{message.from_user.mention} sizning havolangiz orqali botga qo'shildi.\n"
                                        f"🎁 Sizga +{REFERRAL_BONUS_REGISTRATION_DAYS} kun obuna berildi!",
                                    )
                                except Exception:
                                    pass
        except Exception as e:
            logger.warning(f"Referral capture failed for {uid}: {e}")

        # MAJBURIY KANAL OBUNASI GATE - har qanday /start da, login/approvaldan oldin
        # Force join yoqilgan bo'lsa, user kanal(lar)ga a'zo bo'lmaguncha
        # keyingi oqimga (login, menyu, h.k.) o'tkazilmaydi.
        try:
            from plugins.force_join import enforce_force_join
            _fj_ok = await enforce_force_join(client, message)
            logger.info(f"[START_TRACE] STEP2b result: force_join_ok={_fj_ok}")
            if not _fj_ok:
                logger.info("[START_TRACE] STEP2b: Force join gate blocked, returning")
                # user_states'ni tozalamaymiz — user kanalga a'zo bo'lib qaytganda ochiq ekrandan davom etadi
                return
        except Exception as e:
            logger.warning(f"Force join gate failed for {uid}: {e}. Proceeding without it.")

        # MANDATORY: Database-driven authentication check - MUST be first check
        # DB is_active is the ONLY source of truth for authentication status
        # Disk .session files MUST NEVER determine authentication state
        from database_adapter import LoginDatabaseAdapter
        from login_system import LoginState
        logger.info("[START_TRACE] STEP3: Imports done")
        
        # STRICT DB AUTH GUARD: Check if user is authenticated in database
        logger.info("[START_TRACE] STEP4: About to call get_user_active_status")
        is_db_active = await LoginDatabaseAdapter.get_user_active_status(uid)
        logger.info(f"[START_TRACE] STEP5: get_user_active_status returned={is_db_active}")
        
        # CRITICAL: If is_active == 0, user is NOT authenticated regardless of disk files
        if not is_db_active:
            logger.info("[START_TRACE] STEP6: User not authenticated, showing login screen")
            # PENDING APPROVAL GUARD: If the user already completed a Telegram login
            # (session file exists) but has no users row yet, they are simply waiting
            # for admin approval. Do NOT throw them back into the phone/code login
            # loop every time they press /start — just tell them to wait.
            from database import users_row_exists
            if _has_session(uid) and not await users_row_exists(uid):
                logger.info("[START_TRACE] STEP6a: Pending approval, showing waiting message")
                user_states.pop(uid, None)
                # Same "check approval" button as the first login flow, so the user
                # can poll the status without re-logging in.
                from login_system import LoginConstants
                kb_inline = InlineKeyboardMarkup([
                    [InlineKeyboardButton(LoginConstants.BUTTON_CHECK_APPROVAL, callback_data="check_login_approval")]
                ])
                await message.reply_text(
                    f"👋 Salom, **{name}**!\n\n"
                    "⏳ **Akkauntingiz hali tasdiqlanmagan.**\n\n"
                "Admin tasdiqlashini kuting yoki obuna sotib oling "
                "(to'lov ham xavfsizlik tekshiruvidan o'tadi).",
                reply_markup=kb_inline
                )
                kb = await get_main_keyboard(uid)
                await message.reply_text("🏠 **Bosh menyu**", reply_markup=kb)
                return
            # User is logged out or not authenticated - show login screen immediately
            # Clear any existing states
            user_states.pop(uid, None)
            
            # Clean up pending session files
            old_data = login_data.pop(uid, None)
            logger.info(f"[START_TRACE] STEP7: old_data={old_data is not None}")
            if old_data and old_data.get("client"):
                try:
                    await old_data["client"].disconnect()
                    logger.info("[START_TRACE] STEP8: Disconnected old client")
                except:
                    pass

            for ext in (".session", ".session-journal"):
                p = os.path.join(PENDING_DIR, f"user_{uid}{ext}")
                try:
                    if os.path.exists(p):
                        os.remove(p)
                        logger.info(f"[START_TRACE] STEP9: Removed {p}")
                except:
                    pass

            # Set state to waiting for phone
            user_states[uid] = "waiting_for_phone"
            login_data[uid]  = {}
            logger.info("[START_TRACE] STEP10: States set")
            
            # Also set new LoginStateManager state for compatibility
            from login_system import login_service
            logger.info("[START_TRACE] STEP11: About to call login_service.start_login")
            await login_service.start_login(uid)
            logger.info("[START_TRACE] STEP12: login_service.start_login done")
            
            logger.info("[START_TRACE] STEP13: About to send login message")
            await message.reply_text(
                f"👋 Salom, **{name}**!\n\n"
                "**Vento Bot**ga xush kelibsiz.\n\n"
                "Botdan foydalanish uchun avval Telegram akkauntingizni ulashingiz kerak.\n\n"
                "📱 Raqamingizni xalqaro formatda yuboring:\n"
                "`+998901234567`",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("❌ Bekor qilish", callback_data="cancel_login")]
                ])
            )
            logger.info("[START_TRACE] STEP14: Login message sent, returning")
            return
        
        # User is authenticated in DB - proceed with normal flow
        # Clear any existing states
        user_states.pop(uid, None)
        logger.info("[START_TRACE] STEP15: User authenticated, cleared states")

        logger.info("[START_TRACE] STEP16: About to call check_rate_limit")
        allowed, remaining = check_rate_limit(uid, "start")
        logger.info(f"[START_TRACE] STEP17: check_rate_limit returned allowed={allowed}")
        if not allowed:
            await message.reply_text("⏳ Iltimos, biroz kutib turing. /start command tez-tez ishlatilmoqda.")
            return

        logger.info("[START_TRACE] STEP18: About to call register_known_user")
        await register_known_user(uid, message.from_user.username, name)
        logger.info("[START_TRACE] STEP19: register_known_user done")

        # Session file check: Only for session management, NOT authentication
        # Authentication is already verified by DB is_active check above
        logger.info("[START_TRACE] STEP20: About to check _has_session")
        has_session = _has_session(uid)
        logger.info(f"[START_TRACE] STEP21: _has_session returned={has_session}")
        if not has_session:
            logger.info("[START_TRACE] STEP22: No session file, cleaning up")
            # Clean up pending session files (for new users or login retry)
            old_data = login_data.pop(uid, None)
            if old_data and old_data.get("client"):
                try:
                    await old_data["client"].disconnect()
                except:
                    pass

            for ext in (".session", ".session-journal"):
                p = os.path.join(PENDING_DIR, f"user_{uid}{ext}")
                try:
                    if os.path.exists(p):
                        os.remove(p)
                except:
                    pass

            # Set state to waiting for phone (re-login will overwrite existing session)
            user_states[uid] = "waiting_for_phone"
            login_data[uid]  = {}
            
            # Also set new LoginStateManager state for compatibility
            from login_system import login_service, LoginState
            logger.info("[START_TRACE] STEP23: About to call login_service.start_login (second time)")
            await login_service.start_login(uid)
            logger.info("[START_TRACE] STEP24: login_service.start_login done")
            logger.info("[START_TRACE] STEP25: About to send re-login message")
            await message.reply_text(
                f"👋 Salom, **{name}**!\n\n"
                "**Vento Bot**ga xush kelibsiz.\n\n"
                "Botdan foydalanish uchun avval Telegram akkauntingizni ulashingiz kerak.\n\n"
                "📱 Raqamingizni xalqaro formatda yuboring:\n"
                "`+998901234567`",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("❌ Bekor qilish", callback_data="cancel_login")]
                ])
            )
            logger.info("[START_TRACE] STEP26: Re-login message sent, returning")
            return

        logger.info("[START_TRACE] STEP27: About to call _has_access")
        if not await _has_access(uid):
            logger.info("[START_TRACE] STEP28: User doesn't have access")
            kb = await get_main_keyboard(uid)
            await message.reply_text(
                f"👋 Salom, **{name}**!\n\n"
                "⏳ **Akkauntingiz hali tasdiqlanmagan.**\n\n"
                "Admin tasdiqlashini kuting yoki obuna sotib oling "
                "(to'lov ham xavfsizlik tekshiruvidan o'tadi).",
                reply_markup=kb
            )
            return

        logger.info("[START_TRACE] STEP29: About to call get_main_keyboard")
        # (force join gate STEP2b da bajarilgan — bu yerda qayta tekshirish shart emas)
        kb = await get_main_keyboard(uid)
        logger.info("[START_TRACE] STEP30: get_main_keyboard done")
        logger.info("[START_TRACE] STEP31: About to send final welcome message")
        await message.reply_text(
            f"👋 Salom, **{name}**! 🎉\n\n"
            "Quyidagi bo'limlardan birini tanlang:",
            reply_markup=kb
        )
        logger.info("[START_TRACE] STEP32: Final message sent, handler complete")
    except Exception as e:
        logger.error(f"[START_HANDLER_ROOT_CAUSE] Exception in /start handler | uid={uid}")
        logger.exception(f"[START_HANDLER_ROOT_CAUSE] Full traceback:")
        raise  # Re-raise to see the actual exception


async def _check_updates_notification(uid: int) -> str:
    try:
        if not _has_session(uid):
            return ""
        
        notif_disabled = await get_update_notification_pref(uid)
        if notif_disabled:
            return ""
        
        unread = await get_unread_updates_count(uid)
        if unread > 0:
            return (
                f"\n\n📣 **{unread} ta o'qilmagan yangilanish** bor!\n"
                f"Yangiliklarni ko'rish uchun \"📣 Yangiliklar\" tugmasini bosing."
            )
    except Exception:
        pass
    return ""


@Client.on_callback_query(filters.regex("^menu_main$"))
async def menu_main_callback(client: Client, cq: CallbackQuery):
    uid = cq.from_user.id
    user_states.pop(uid, None)
    kb = await get_main_keyboard(uid)
    
    notif_text = await _check_updates_notification(uid)
    main_text = "🏠 **Bosh menyu**" + notif_text
    
    try:
        await cq.message.delete()
    except:
        pass
    await cq.message.reply_text(main_text, reply_markup=kb)
    await cq.answer()


@Client.on_callback_query(filters.regex("^check_menu_approval$"))
async def check_approval_callback(client: Client, cq: CallbackQuery):
    uid = cq.from_user.id
    
    if user_states.get(uid) == "waiting_for_admin_approval":
        await cq.answer("⏳ Hali tasdiqlanmagan. Kuting...", show_alert=True)
        return
        
    if await _has_access(uid):
        kb = await get_main_keyboard(uid)
        try:
            await cq.message.delete()
        except:
            pass
        await cq.message.reply_text(
            "✅ Tasdiqlandi! **Vento Bot**ga xush kelibsiz 🎉",
            reply_markup=kb
        )
        await cq.answer("Tasdiqlandi!", show_alert=True)
    else:
        await cq.answer("⏳ Hali tasdiqlanmagan. Kuting...", show_alert=True)


@Client.on_message(filters.private & filters.text & ~filters.command(["start"]), group=1)
async def menu_button_handler(client: Client, message: Message):
    try:
        uid  = message.from_user.id
        txt  = message.text.strip()
        
        state = user_states.get(uid)
        if state in ["waiting_for_phone", "waiting_for_code", "waiting_for_password", 
                     "waiting_for_scrape_target", "waiting_msg_count", "group_search_state",
                     "waiting_contact_subject", "waiting_contact_message"]:
            raise ContinuePropagation
        
        # Multi-account: akkount nomini o'zgartirish inputi
        if isinstance(state, str) and state.startswith("acc_rename_inp|"):
            try:
                slot = int(state.split("|", 1)[1])
            except (ValueError, IndexError):
                user_states.pop(uid, None)
                raise ContinuePropagation
            user_states.pop(uid, None)
            name = (message.text or "").strip()
            from session_manager import update_account_name
            if not name:
                await message.reply_text("❌ Nom bo'sh bo'lishi mumkin emas. Qaytadan urinib ko'ring.")
                return
            if len(name) > 32:
                await message.reply_text("❌ Nom juda uzun (maks. 32 belgi). Qaytadan yuboring.")
                return
            if update_account_name(uid, slot, name):
                await message.reply_text(f"✅ Akkount nomi o'zgartirildi: **{name}**\n\n(bu nom faqat bot ichida ko'rinadi, real Telegram ismi o'zgarmaydi)")
            else:
                await message.reply_text("❌ Akkount topilmadi.")
            return
        
        sess = _has_session(uid)
        acc  = await _has_access(uid)
        adm  = _is_admin(uid)

        if txt == "📱 Akkaunt ulash":
            if sess:
                await message.reply_text("✅ Akkaunt allaqachon ulangan.")
                return
            user_states[uid] = "waiting_for_phone"
            login_data[uid]  = {}
            await message.reply_text(
                "📱 Telegram raqamingizni xalqaro formatda yuboring:\n`+998901234567`",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("❌ Bekor qilish", callback_data="cancel_login")]
                ])
            )
            return

        if txt == "👥 Takliflar":
            from plugins.referral import handle_referral_menu
            await handle_referral_menu(client, message)
            return

        if txt == "👤 Akkaunt":
            if not sess:
                await message.reply_text("Avval akkauntingizni ulang.")
                return
            from session_manager import get_accounts, get_active_slot, MAX_SESSIONS_PER_USER
            accounts = get_accounts(uid)
            active_slot = get_active_slot(uid)
            active_name = next((a["name"] for a in accounts if a["slot"] == active_slot),
                               accounts[0]["name"] if accounts else "Akkount-1")

            text = (
                "👤 **Akkaunt sozlamalari**\n\n"
                f"🟢 Faol akkaunt: **{active_name}**\n"
                f"👥 Ulangan akkauntlar: **{len(accounts)}/{MAX_SESSIONS_PER_USER}**"
            )
            buttons = [
                [InlineKeyboardButton("📱 Mini App-ni ochish", web_app=WebAppInfo(url=MINI_APP_URL))],
                [InlineKeyboardButton("⚙️ Action Sozlamalari", callback_data="action_status_menu_account")],
            ]
            if len(accounts) < MAX_SESSIONS_PER_USER:
                buttons.append([InlineKeyboardButton("➕ Akkount qo'shish", callback_data="acc_add")])
            if len(accounts) >= 2:
                buttons.append([InlineKeyboardButton("👥 Akkauntni almashtirish", callback_data="acc_list")])
                buttons.append([InlineKeyboardButton("✏️ Akkount nomlash", callback_data="acc_rename")])
                buttons.append([InlineKeyboardButton("🗑 Akkount o'chirish", callback_data="acc_remove")])
            buttons.append([InlineKeyboardButton("🚪 Akkauntni uzish (Logout)", callback_data="logout")])
            buttons.append([InlineKeyboardButton("🔙 Bosh menyu", callback_data="menu_main")])
            await message.reply_text(text, reply_markup=InlineKeyboardMarkup(buttons))
            return

        if txt in {"🔍 Scraper", "🗂 Bazalar", "📨 Mass DM", "🏷 Utag"}:
            if not sess:
                await message.reply_text(
                    "❌ Avval akkauntingizni ulashingiz kerak.",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("📱 Akkaunt ulash", callback_data="do_link_account")]
                    ])
                )
                return
            if not acc:
                await message.reply_text(
                    "⛔️ Bu funksiyadan foydalanish uchun obuna kerak.",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("⭐️ Obuna sotib olish", callback_data="menu_payment")]
                    ])
                )
                return

            if txt == "🔍 Scraper":
                await message.reply_text(
                    "🔍 **Scraper** — Guruhdan odam yig'ish",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("▶️ Boshlash", callback_data="menu_scraper")]
                    ])
                )
            elif txt == "🗂 Bazalar":
                await message.reply_text(
                    "🗂 **Bazalar** — Yig'ilgan ma'lumotlar",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("📋 Barcha bazalar", callback_data="admin_baza")],
                        [InlineKeyboardButton("🔍 ID orqali qidirish", callback_data="baza_search_id")],
                    ])
                )
            elif txt == "📨 Mass DM":
                await message.reply_text(
                    "📨 **Mass DM** — Bazadagi userlarga xabar yuborish",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("▶️ Boshlash", callback_data="menu_massdm")]
                    ])
                )
            elif txt == "🏷 Utag":
                await message.reply_text(
                    "🏷 **Utag** — Guruhda userlarni mention qilish",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("▶️ Boshlash", callback_data="menu_utag")]
                    ])
                )
            return

        if txt in {"⭐️ Obuna", "⭐️ Obuna sotib olish", "⭐️ Obuna haqida"}:
            await message.reply_text(
                "⭐️ **Obuna**\n\nBotdan to'liq foydalanish uchun obuna kerak:",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("⭐️ Obuna sotib olish", callback_data="menu_payment")]
                ])
            )
            return

        if txt == "🛠 Admin Panel":
            if not adm:
                return
            await message.reply_text(
                "⚙️ **Admin Panel**",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("⚙️ Panelni ochish", callback_data="menu_admin")]
                ])
            )
            return

        if txt == "📣 Yangiliklar":
            if not sess:
                await message.reply_text(
                    "❌ Avval akkauntingizni ulashingiz kerak.",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("📱 Akkaunt ulash", callback_data="do_link_account")]
                    ])
                )
                return
            await message.reply_text(
                "📣 **Yangiliklar**",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("📣 Yangiliklarni ko'rish", callback_data="menu_updates")]
                ])
            )
            return

        if txt == "📞 Bog'lanish":
            await message.reply_text(
                "📞 **Admin bilan bog'lanish**\n\n"
                "Quyidagi usullardan birini tanlang:",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("💬 To'g'ridan to'gri bog'lanish", callback_data="contact_direct")],
                    [InlineKeyboardButton("📝 Shablon orqali bog'lanish", callback_data="contact_template")],
                    [InlineKeyboardButton("📖 Tezkor tushuncha", callback_data="menu_guide")],
                    [InlineKeyboardButton("🔙 Bosh menyu", callback_data="menu_main")],
                ])
            )
            return

        if txt == "💬 Chatlar":
            if not sess:
                await message.reply_text("❌ Avval akkauntingizni ulang.")
                return
            await message.reply_text(
                "💬 **Chatlar**",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("💬 Chatlarni ochish", callback_data="menu_chat")]
                ])
            )
            return

        if txt == "🔍 Guruh qidirish":
            if not sess:
                await message.reply_text("❌ Avval akkauntingizni ulang.")
                return
            await message.reply_text(
                "🔍 **Guruh qidirish**",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔍 Qidirishni boshlash", callback_data="menu_group_search")]
                ])
            )
            return

        if txt == "🌐 Til":
            from plugins.language import language_command
            await language_command(client, message)
            return

        if txt == "🔙 Bosh menyu":
            kb = await get_main_keyboard(uid)
            notif_text = await _check_updates_notification(uid)
            main_text = "🏠 **Bosh menyu**" + notif_text
            await message.reply_text(main_text, reply_markup=kb)
            return

        raise ContinuePropagation
    except ContinuePropagation:
        raise
    except Exception as e:
        logger.exception("menu_button_handler xatosi: %s", e)


@Client.on_callback_query(filters.regex("^do_link_account$"))
async def do_link_account_callback(client: Client, cq: CallbackQuery):
    uid = cq.from_user.id
    if _has_session(uid):
        await cq.answer("✅ Akkaunt allaqachon ulangan!", show_alert=True)
        return
    user_states[uid] = "waiting_for_phone"
    login_data[uid]  = {}
    await cq.message.edit_text(
        "📱 Telegram raqamingizni xalqaro formatda yuboring:\n`+998901234567`",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("❌ Bekor qilish", callback_data="cancel_login")]
        ])
    )
    await cq.answer()


@Client.on_callback_query(filters.regex("^contact_direct$"))
async def contact_direct_callback(client: Client, cq: CallbackQuery):
    """To'g'ridan to'gri Owner ga yonaltirish"""
    uid = cq.from_user.id
    user = await get_known_user(uid)
    lang = user.get("language", "uz") if user else "uz"
    
    owner_id = 8513957498
    
    try:
        owner = await client.get_users(owner_id)
        owner_name = owner.first_name
        owner_username = f"@{owner.username}" if owner.username else ""
        
        contact_text = (
            "💬 **To'g'ridan to'gri bog'lanish**\n\n"
            f"Admin: {owner_name} {owner_username}\n"
            f"ID: `{owner_id}`\n\n"
            "Yuqoridagi ma'lumotlardan foydalanib, to'g'ridan to'gri bog'lanishingiz mumkin."
        )
        
        await cq.message.edit_text(
            contact_text,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Bog'lanish bo'limiga qaytish", callback_data="contact_back")]
            ])
        )
        await cq.answer()
    except Exception as e:
        await cq.answer(f"Xatolik: {e}", show_alert=True)

@Client.on_callback_query(filters.regex("^contact_template$"))
async def contact_template_callback(client: Client, cq: CallbackQuery):
    """Shablon orqali bog'lanish - sarlavha va xabar kiritish"""
    uid = cq.from_user.id
    user_states[uid] = "waiting_contact_subject"
    
    await cq.message.edit_text(
        "📝 **Shablon orqali bog'lanish**\n\n"
        "Avval murojaatingizning **sarlavhasini** yuboring:\n"
        "Masalan: `Bot ishlamayapti` yoki `Obuna haqida savol`",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("❌ Bekor qilish", callback_data="contact_back")]
        ])
    )
    await cq.answer()

@Client.on_callback_query(filters.regex("^contact_back$"))
async def contact_back_callback(client: Client, cq: CallbackQuery):
    """Bog'lanish bo'limiga qaytish"""
    uid = cq.from_user.id
    user_states.pop(uid, None)
    
    await cq.message.edit_text(
        "📞 **Admin bilan bog'lanish**\n\n"
        "Quyidagi usullardan birini tanlang:",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("💬 To'g'ridan to'gri bog'lanish", callback_data="contact_direct")],
            [InlineKeyboardButton("📝 Shablon orqali bog'lanish", callback_data="contact_template")],
            [InlineKeyboardButton("📖 Tezkor tushuncha", callback_data="menu_guide")],
            [InlineKeyboardButton("🔙 Bosh menyu", callback_data="menu_main")],
        ])
    )
    await cq.answer()


@Client.on_message(filters.private & (filters.text | filters.photo) & ~filters.command(["start"]), group=-5)
async def contact_message_handler(client: Client, message: Message):
    """Shablon orqali bog'lanish - sarlavha va xabarni qabul qilish"""
    from config import user_states
    from pyrogram import ContinuePropagation
    
    uid = message.from_user.id
    state = user_states.get(uid)
    
    if state and (state.startswith("waiting_for_timer_") or state == "waiting_for_timer_chat" or state.startswith("waiting_for_timer_message_")):
        raise ContinuePropagation
    
    if state == "waiting_contact_subject":
        subject = message.text.strip()
        if len(subject) < 3:
            await message.reply_text(
                "❌ Sarlavha kamida 3 ta belgidan iborat bo'lishi kerak.\n"
                "Qaytadan kiriting:",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("❌ Bekor qilish", callback_data="contact_back")]
                ])
            )
            return
        
        user_states[uid] = "waiting_contact_message"
        user_states[uid + "_subject"] = subject
        
        await message.reply_text(
            f"✅ **Sarlavha:** {subject}\n\n"
            "Endi muammoingizni **batafsil** yozib yuboring:\n"
            "Qanday muammo bor? Qanday yordam kerak?\n\n"
            "💡 **Rasm ham yuborishingiz mumkin!**",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("❌ Bekor qilish", callback_data="contact_back")]
            ])
        )
        return
    
    elif state == "waiting_contact_message":
        subject = user_states.get(uid + "_subject", "Murojaat")
        photo_file_id = None
        msg_text = ""
        
        if message.photo:
            photo_file_id = message.photo.file_id
            msg_text = message.caption or "Rasm yuborildi"
        elif message.text:
            msg_text = message.text.strip()
            if len(msg_text) < 10:
                await message.reply_text(
                    "❌ Xabar kamida 10 ta belgidan iborat bo'lishi kerak.\n"
                    "Batafsilroq yozing:",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("❌ Bekor qilish", callback_data="contact_back")]
                    ])
                )
                return
        else:
            return
        
        from database import add_complaint, get_known_user
        user_info = await get_known_user(uid)
        username = message.from_user.username or ""
        first_name = message.from_user.first_name or ""
        
        complaint_id = await add_complaint(uid, username, first_name, subject, msg_text, photo_file_id)
        
        user_states.pop(uid, None)
        user_states.pop(uid + "_subject", None)
        
        reply_text = (
            "✅ **Murojaat qabul qilindi!**\n\n"
            f"🆔 Shikoyat ID: `{complaint_id}`\n"
            f"📋 Sarlavha: {subject}\n\n"
            "Adminlar tez orada siz bilan bog'lanishadi.\n"
            "Murojaatingiz holatini \"📞 Bog'lanish\" bo'limidan kuzatishingiz mumkin."
        )
        
        if photo_file_id:
            await message.reply_photo(
                photo_file_id,
                caption=reply_text,
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔙 Bosh menyu", callback_data="menu_main")]
                ])
            )
        else:
            await message.reply_text(
                reply_text,
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔙 Bosh menyu", callback_data="menu_main")]
                ])
            )
        
        from config import bot_client
        from database import get_all_admins
        
        admins = await get_all_admins()
        admin_ids = [admin["admin_id"] for admin in admins]
        
        user_mention = f" (@{username})" if username else ""
        
        admin_text = (
            "📩 **Yangi murojaat!**\n\n"
            f"🆔 ID: `{complaint_id}`\n"
            f"👤 Foydalanuvchi: {message.from_user.first_name}{user_mention}\n"
            f"🆔 User ID: `{uid}`\n\n"
            f"📋 **Sarlavha:** {subject}\n"
            f"💬 **Xabar:**\n{msg_text}\n\n"
            "Ko'rish uchun: /admin → Shikoyatlar"
        )
        
        for admin_id in admin_ids:
            try:
                if photo_file_id:
                    await client.send_photo(admin_id, photo_file_id, caption=admin_text)
                else:
                    await client.send_message(admin_id, admin_text)
            except:
                pass
        
        return
    
    raise ContinuePropagation


@Client.on_message(filters.command("start") & filters.group)
async def group_start_handler(client: Client, message: Message):
    """Handle /start command in group chats"""
    if not message.from_user:
        return
    
    uid = message.from_user.id
    user_mention = message.from_user.mention
    
    from database_adapter import LoginDatabaseAdapter
    is_db_active = await LoginDatabaseAdapter.get_user_active_status(uid)
    
    bot_info = client.me or await client.get_me()
    bot_username = bot_info.username if bot_info and bot_info.username else "empire_family_bot"
    bot_url = f"https://t.me/{bot_username}?start=start"
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🤖 Botga o'tish", url=bot_url)]
    ])
    
    if not is_db_active:
        text = (
            f"👋 **Salom, {user_mention}!**\n\n"
            "Hmm, ko'rinishidan botga login qilmagan ko'rinasiz. Ulanishni istaysizmi?"
        )
    else:
        text = (
            f"👋 **Salom, {user_mention}!**\n\n"
            "Siz botga muvaffaqiyatli ulangansiz. Boshqaruv paneli va sozlamalar uchun botimizga o'tishingiz mumkin!"
        )
        
    await message.reply_text(text, reply_markup=keyboard)


# ---------------------------------------------------------------------------
# Multi-account: akkaunt qo'shish / almashtirish / nomlash / o'chirish
# ---------------------------------------------------------------------------

def _next_free_slot(uid: int):
    """Bo'sh slot'ni topadi (2, 3, ...). None = hammasi band."""
    from session_manager import get_accounts, MAX_SESSIONS_PER_USER
    taken = {a["slot"] for a in get_accounts(uid)}
    for s in range(2, MAX_SESSIONS_PER_USER + 1):
        if s not in taken:
            return s
    return None


@Client.on_callback_query(filters.regex("^acc_add$"))
async def acc_add_callback(client: Client, cq: CallbackQuery):
    uid = cq.from_user.id
    if not await _has_access(uid):
        await cq.answer("⛔️ Obuna/tasdiq kerak.", show_alert=True)
        return

    from session_manager import get_accounts, MAX_SESSIONS_PER_USER
    accounts = get_accounts(uid)
    if len(accounts) >= MAX_SESSIONS_PER_USER:
        await cq.answer(f"❌ Maksimal {MAX_SESSIONS_PER_USER} ta akkaunt ulash mumkin!", show_alert=True)
        return
    if not _has_session(uid):
        await cq.answer("❌ Avval asosiy akkauntni ulang (📱 Akkaunt ulash).", show_alert=True)
        return

    slot = _next_free_slot(uid)
    if slot is None:
        await cq.answer("❌ Barcha slotlar band!", show_alert=True)
        return

    # Login jarayonini shu slot'ga yo'naltirish
    login_service.session_manager.set_add_slot(uid, slot)
    user_states[uid] = "waiting_for_phone"
    login_data[uid] = {"add_slot": slot}

    await cq.message.edit_text(
        f"➕ **Akkount-{slot} qo'shish**\n\n"
        "📱 Yangi akkauntning **telefon raqamini** xalqaro formatda yuboring:\n"
        "`+998901234567`\n\n"
        "⚠️ Kod shu yangi akkauntga keladi (Telegram ilovasi yoki SMS).",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("❌ Bekor qilish", callback_data="acc_cancel_add")
        ]])
    )
    await cq.answer()


@Client.on_callback_query(filters.regex("^acc_cancel_add$"))
async def acc_cancel_add_callback(client: Client, cq: CallbackQuery):
    uid = cq.from_user.id
    login_service.session_manager.clear_add_slot(uid)
    user_states.pop(uid, None)
    login_data.pop(uid, None)
    await cq.message.edit_text("❌ Akkount qo'shish bekor qilindi.")
    await cq.answer()


@Client.on_callback_query(filters.regex("^acc_list$"))
async def acc_list_callback(client: Client, cq: CallbackQuery):
    uid = cq.from_user.id
    from session_manager import get_accounts, get_active_slot
    accounts = get_accounts(uid)
    active_slot = get_active_slot(uid)

    lines = [
        "👥 **Akkauntni almashtirish**\n",
        f"🟢 Faol: **{next((a['name'] for a in accounts if a['slot'] == active_slot), '?')}**\n",
    ]
    buttons = []
    for a in accounts:
        mark = "🟢" if a["slot"] == active_slot else "⚪️"
        lines.append(f"{mark} {a['name']}")
        if a["slot"] != active_slot:
            buttons.append([InlineKeyboardButton(
                f"🔄 {a['name']} ga o'tish",
                callback_data=f"acc_switch_{a['slot']}",
            )])
    buttons.append([InlineKeyboardButton("🔙 Orqaga", callback_data="menu_account_back")])

    await cq.message.edit_text("\n".join(lines), reply_markup=InlineKeyboardMarkup(buttons))
    await cq.answer()


@Client.on_callback_query(filters.regex("^acc_rename$"))
async def acc_rename_callback(client: Client, cq: CallbackQuery):
    uid = cq.from_user.id
    from session_manager import get_accounts, get_active_slot
    accounts = get_accounts(uid)
    active_slot = get_active_slot(uid)

    lines = ["✏️ **Akkount nomlash**\n\nQaysi akkauntni nomlaysiz?\n(bu nom faqat bot ichida ko'rinadi)\n"]
    buttons = []
    for a in accounts:
        mark = "🟢" if a["slot"] == active_slot else "⚪️"
        lines.append(f"{mark} {a['name']}")
        buttons.append([InlineKeyboardButton(f"✏️ {a['name']}", callback_data=f"acc_rename_pick_{a['slot']}")])
    buttons.append([InlineKeyboardButton("🔙 Orqaga", callback_data="menu_account_back")])

    await cq.message.edit_text("\n".join(lines), reply_markup=InlineKeyboardMarkup(buttons))
    await cq.answer()


@Client.on_callback_query(filters.regex(r"^acc_rename_pick_(\d+)$"))
async def acc_rename_pick_callback(client: Client, cq: CallbackQuery):
    uid = cq.from_user.id
    slot = int(cq.matches[0].group(1))
    user_states[uid] = f"acc_rename_inp|{slot}"
    await cq.message.edit_text(
        f"✏️ **Akkount-{slot} uchun yangi nom yuboring:**\n\n"
        "Masalan: `Akkount-2`, `Ish akkaunti`, `DimaPlay_Uz.exe`\n\n"
        "💡 Bu nom faqat bot ichida ko'rinadi — real Telegram ismi o'zgarmaydi.\n"
        "❌ Bekor qilish uchun /start bosing.",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🔙 Orqaga", callback_data="acc_rename")
        ]])
    )
    await cq.answer()


@Client.on_callback_query(filters.regex("^acc_remove$"))
async def acc_remove_callback(client: Client, cq: CallbackQuery):
    uid = cq.from_user.id
    from session_manager import get_accounts, get_active_slot
    accounts = get_accounts(uid)
    if len(accounts) < 2:
        await cq.answer("❌ O'chirish uchun kamida 2 ta akkaunt kerak.", show_alert=True)
        return
    active_slot = get_active_slot(uid)

    lines = ["🗑 **Akkount o'chirish**\n\nQaysi akkauntni o'chiramiz?\n\n⚠️ O'chirilgan akkaunt sessiyasi butunlay o'chadi!\n"]
    buttons = []
    for a in accounts:
        mark = "🟢" if a["slot"] == active_slot else "⚪️"
        lines.append(f"{mark} {a['name']}")
        buttons.append([InlineKeyboardButton(f"🗑 {a['name']}", callback_data=f"acc_remove_pick_{a['slot']}")])
    buttons.append([InlineKeyboardButton("🔙 Orqaga", callback_data="menu_account_back")])

    await cq.message.edit_text("\n".join(lines), reply_markup=InlineKeyboardMarkup(buttons))
    await cq.answer()


@Client.on_callback_query(filters.regex(r"^acc_remove_pick_(\d+)$"))
async def acc_remove_pick_callback(client: Client, cq: CallbackQuery):
    uid = cq.from_user.id
    slot = int(cq.matches[0].group(1))
    from session_manager import get_accounts, get_active_slot
    accounts = get_accounts(uid)
    active_slot = get_active_slot(uid)
    acc = next((a for a in accounts if a["slot"] == slot), None)
    if not acc:
        await cq.answer("❌ Akkount topilmadi.", show_alert=True)
        return

    confirm_text = (
        "⚠️ **Tasdiqlash**\n\n"
        "Akkauntni o'chirishni tasdiqlaysizmi?\n\n"
        f"📱 {acc['name']}\n"
        f"🆔 Slot: {slot}\n\n"
    )
    if slot == active_slot:
        confirm_text += "ℹ️ Bu FAOL akkaunt — o'chirilsa, boshqa akkauntga avtomatik o'tiladi.\n\n"
    confirm_text += "O'chirilgach sessiya qayta tiklanmaydi!"

    await cq.message.edit_text(
        confirm_text,
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton("🗑 Ha, o'chirish", callback_data=f"acc_remove_do_{slot}"),
                InlineKeyboardButton("❌ Bekor qilish", callback_data="acc_remove"),
            ]
        ])
    )
    await cq.answer()


@Client.on_callback_query(filters.regex(r"^acc_remove_do_(\d+)$"))
async def acc_remove_do_callback(client: Client, cq: CallbackQuery):
    uid = cq.from_user.id
    slot = int(cq.matches[0].group(1))
    from session_manager import remove_account_slot, get_accounts, get_active_slot

    ok = await remove_account_slot(uid, slot)
    if not ok:
        await cq.answer("❌ O'chirishda xatolik (kamida 1 ta akkaunt qolishi shart).", show_alert=True)
        return

    try:
        from database import log_admin_action
        await log_admin_action(uid, "account_remove_slot", None, str(slot))
    except Exception:
        pass

    remaining = [a["name"] for a in get_accounts(uid)]
    new_active = get_active_slot(uid)
    new_name = next((a["name"] for a in get_accounts(uid) if a["slot"] == new_active), "Akkount-1")

    await cq.answer("🗑 Akkount o'chirildi!", show_alert=True)
    await cq.message.edit_text(
        f"🗑 **Akkount o'chirildi!**\n\n"
        f"🟢 Faol akkaunt endi: **{new_name}**\n"
        f"👥 Qoldi: {len(remaining)} ta ({', '.join(remaining)})",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🔙 Akkaunt sozlamalari", callback_data="menu_account_back")
        ]])
    )


@Client.on_callback_query(filters.regex(r"^acc_switch_(\d+)$"))
async def acc_switch_callback(client: Client, cq: CallbackQuery):
    uid = cq.from_user.id
    slot = int(cq.matches[0].group(1))

    from session_manager import set_active_slot, get_accounts, get_active_slot, close_user_client_slot
    import logging
    logger = logging.getLogger(__name__)

    try:
        logger.info(f"acc_switch_callback: uid={uid}, slot={slot}")
        accounts = get_accounts(uid)
        logger.info(f"acc_switch_callback: accounts={accounts}")
        target = next((a for a in accounts if a["slot"] == slot), None)
        if not target:
            logger.warning(f"acc_switch_callback: target not found for slot {slot}")
            await cq.answer("❌ Akkount topilmadi.", show_alert=True)
            return

        old_slot = get_active_slot(uid)
        logger.info(f"acc_switch_callback: old_slot={old_slot}, target_slot={slot}")
        if await set_active_slot(uid, slot):
            # Avvalgi faol akkaunt clientini yopamiz — keyingi amallar yangi akkauntda
            if old_slot != slot:
                await close_user_client_slot(uid, old_slot)
            await cq.answer(f"✅ {target['name']} ga o'tildi!", show_alert=True)
            cq.data = "menu_account_back"
            await menu_account_back_callback(client, cq)
        else:
            logger.error(f"acc_switch_callback: set_active_slot returned False for slot {slot}")
            await cq.answer("❌ Almashtirishda xatolik.", show_alert=True)
    except Exception as e:
        logger.error(f"acc_switch_callback error: {e}", exc_info=True)
        await cq.answer(f"❌ Xatolik: {e}", show_alert=True)


@Client.on_callback_query(filters.regex("^menu_account_back$"))
async def menu_account_back_callback(client: Client, cq: CallbackQuery):
    """👤 Akkaunt sozlamalari ekrani (inline)."""
    uid = cq.from_user.id
    from session_manager import get_accounts, get_active_slot, MAX_SESSIONS_PER_USER
    accounts = get_accounts(uid)
    active_slot = get_active_slot(uid)
    active_name = next((a["name"] for a in accounts if a["slot"] == active_slot), "Akkount-1")

    lines = [
        "👤 **Akkaunt sozlamalari**\n",
        f"🟢 Faol akkaunt: **{active_name}**",
        f"👥 Ulangan akkauntlar: **{len(accounts)}/{MAX_SESSIONS_PER_USER}**",
    ]
    buttons = [
        [InlineKeyboardButton("📱 Mini App-ni ochish", web_app=WebAppInfo(url=MINI_APP_URL))],
        [InlineKeyboardButton("⚙️ Action Sozlamalari", callback_data="action_status_menu_account")],
    ]
    if len(accounts) < MAX_SESSIONS_PER_USER:
        buttons.append([InlineKeyboardButton("➕ Akkount qo'shish", callback_data="acc_add")])
    if len(accounts) >= 2:
        buttons.append([InlineKeyboardButton("👥 Akkauntni almashtirish", callback_data="acc_list")])
        buttons.append([InlineKeyboardButton("✏️ Akkount nomlash", callback_data="acc_rename")])
        buttons.append([InlineKeyboardButton("🗑 Akkount o'chirish", callback_data="acc_remove")])
    buttons.append([InlineKeyboardButton("🚪 Akkauntni uzish (Logout)", callback_data="logout")])
    buttons.append([InlineKeyboardButton("🔙 Bosh menyu", callback_data="menu_main")])

    await cq.message.edit_text("\n".join(lines), reply_markup=InlineKeyboardMarkup(buttons))
    await cq.answer()
