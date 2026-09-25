from pyrogram import Client, filters, ContinuePropagation
from pyrogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardRemove
from pyrogram.enums import ChatMembersFilter, ChatType, ChatMemberStatus
from config import user_states, stop_flags, SESSIONS_DIR, API_ID, API_HASH
from database import add_scraped_group, add_scraped_member, add_scraped_members_batch, generate_unique_group_id, get_group_id_by_title, update_group_date, log_user_action
from queue_manager import queue_manager
import os
import asyncio
import time
import re
from session_manager import get_user_client
import gender_guesser.detector as gender

# Gender detector initialization
d = gender.Detector(case_sensitive=False)

# Profile analyzer integration
try:
    from profile_analyzer import ProfileAnalyzer, ProfileAnalyzerConfig
    PROFILE_ANALYZER_AVAILABLE = True
    # Initialize global profile analyzer instance
    _profile_analyzer = None
    _profile_analyzer_lock = asyncio.Lock()
except ImportError:
    PROFILE_ANALYZER_AVAILABLE = False
    _profile_analyzer = None


async def get_profile_analyzer():
    """Global profile analyzer obyektini olish yoki yaratish."""
    global _profile_analyzer
    if not PROFILE_ANALYZER_AVAILABLE:
        return None
    
    async with _profile_analyzer_lock:
        if _profile_analyzer is None:
            config = ProfileAnalyzerConfig.from_env()
            _profile_analyzer = ProfileAnalyzer(config)
        return _profile_analyzer

GIRL_NAMES = {
    "nilufar", "gulnora", "malika", "nodira", "zulfiya", "barno", "dilnoza",
    "feruza", "kamola", "lobar", "mohira", "nargiza", "ozoda", "parizod",
    "qunduz", "ra'no", "sabina", "tanzila", "umida", "venera", "xurshida",
    "yulduz", "zilola", "adolat", "bahora", "charos", "dildora", "elnora",
    "fotima", "gavhar", "hamida", "iroda", "jasmin", "komila", "lola",
    "munira", "nasiba", "oydin", "parvin", "rohila", "sabohat", "tabassum",
    "ulmas", "vasila", "xilola", "ziyoda", "madina", "maftuna", "muhabbat",
    "mushtariy", "nafisa", "nozima", "ra'noxon", "rano", "rayhona",
    "robiya", "rukiya", "sabrina", "saida", "salima", "sevara", "shahlo",
    "shahnoza", "shaxlo", "sitora", "saodat", "surayyo", "turgunoy",
    "xayriniso", "yorqinoy", "zarina", "zarnigor", "zuhra", "zulayho",
    "hulkar", "shoira", "oisha", "oysha", "oygul", "oynisa", "oysha",
    "dilorom", "aziza", "anora", "barcha", "binafsha", "chamanara",
    "darmon", "dilfuza", "durona", "farzona", "feruzaxon", "firuza",
    "gulsanam", "gulbahor", "gulchiroy", "gulnoz", "gulyora",
    "hilola", "husniya", "indira", "jamila", "jumagul",
    "kimyoxon", "kumush", "latofat", "manzura", "marguba",
    "marjona", "mavluda", "mohinur", "muazzam", "munavvar",
    "mushkina", "nafosat", "naima", "navbahor", "nigina", "nigora",
    "niso", "nurbonu", "nuriya", "dilafruz", "dilnavoz",
    "shodiya", "shoista", "shohista", "shohsanam", "xadicha",
    "xurmo", "yorkinoy", "yoqutxon", "zebo", "zebi", "zebiniso",
}

def parse_group_identifier(text: str) -> str:
    text = text.strip()
    match = re.match(r'(?:https?://)?(?:t\.me|telegram\.me|telegram\.dog)/(?:joinchat/)?([a-zA-Z0-9_+\-]+)', text)
    if match:
        identifier = match.group(1)
        if 'joinchat/' in text or identifier.startswith('+'):
            return text
        return identifier
    if text.startswith('@'):
        return text[1:]
    return text

def is_likely_girl(first_name: str) -> bool:
    """Ismni qiz ekanligini aniqlash uchun bir qancha metodlardan foydalanadi."""
    if not first_name:
        return False
    
    name = first_name.lower().strip()
    words = name.split()
    if not words:
        return False
        
    first_word = words[0]
    
    # 1. Check Uzbek female name list
    if first_word in GIRL_NAMES:
        return True
        
    # 2. Check Uzbek female suffixes
    female_suffixes = ("xon", "bonu", "niso", "bibi", "begim", "oy", "goy")
    if first_word.endswith(female_suffixes):
        return True
        
    # 3. Use AI/ML model for gender detection
    try:
        detected_gender = d.get_gender(first_word)
        # Consider 'female' or 'mostly_female' as female
        if detected_gender in ('female', 'mostly_female'):
            return True
        # Consider 'male' or 'mostly_male' as male
        if detected_gender in ('male', 'mostly_male'):
            return False
    except:
        pass
        
    # 4. Check Uzbek female prefixes
    if first_word.startswith(("gul", "moh", "oy")):
        return True
        
    # 5. Check Russian female suffixes
    if first_word.endswith(("ova", "eva", "ina", "aya", "skaya")):
        return True
        
    # 6. Check male suffixes (definitely male if present)
    male_suffixes = ("bek", "jon", "boy", "mirzo", "ali", "xoja", "xuja", "iddin", "ulla", "ovich", "evich")
    if first_word.endswith(male_suffixes):
        return False
        
    # 7. If model returns 'andy' (ambiguous), do additional checks
    try:
        detected_gender = d.get_gender(first_word)
        if detected_gender == 'andy':
            # Additional Uzbek rules
            if first_word.startswith(("gul", "moh", "oy", "nur")):
                return True
    except:
        pass
        
    return False

def make_progress_bar(current, total, width=10):
    if total == 0:
        return "░" * width, 0
    pct = int((current / total) * 100)
    filled = int(pct / (100 / width))
    bar = "█" * filled + "░" * (width - filled)
    return bar, pct


SCRAPER_TYPE_ERROR_TEXT = (
    "❌ **Scraper faqat guruhlarda ishlaydi!**\n\n"
    "Kanaldan odam yig'ish uchun ushbu kanalda **admin** bo'lishingiz kerak.\n"
    "A'zolar ro'yxati ochiq bo'lgan guruh havolasini yuboring:\n"
    "Masalan: `@guruh_username` yoki `https://t.me/guruh_username`"
)


def friendly_scrape_error(e: Exception) -> str:
    """Telegram xatolarini tushunarli xabarlarga aylantirish"""
    s = str(e).upper()
    if "CHAT_ADMIN_REQUIRED" in s or "ADMIN_REQUIRED" in s:
        return (
            "Kanalda a'zolar ro'yxati yashiringan (maxfiy). "
            "Kanaldan odam yig'ish uchun admin bo'lishingiz yoki "
            "a'zolar ko'rinadigan guruh havolasini yuboring."
        )
    if "CHANNEL_PRIVATE" in s or "CHAT_FORBIDDEN" in s:
        return "Guruh/kanal topilmadi yoki kirish mumkin emas."
    if "USER_NOT_PARTICIPANT" in s:
        return "Avval ushbu guruh/kanala a'zo bo'lishingiz kerak."
    if "FLOOD" in s:
        return "Tez-tez so'rov yubordingiz. Iltimos, biroz kutib, qayta urinib ko'ring."
    if "AUTH_KEY" in s or "SESSION" in s or "UNAUTHORIZED" in s:
        return f"{e}"
    return f"Xato: {e}"


async def check_scrape_target(user_client: Client, chat, user_id: int):
    """Check if the scrape target is a valid group/channel and if user has permissions.

    Returns error message for user if something is wrong,
    None if everything is okay.
    """
    if chat.type == ChatType.CHANNEL:
        # Channel: member list only visible to admins
        try:
            me = await user_client.get_chat_member(chat.id, user_id)
            if me.status not in (ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER):
                return SCRAPER_TYPE_ERROR_TEXT
        except Exception:
            return SCRAPER_TYPE_ERROR_TEXT
    elif chat.type in (ChatType.PRIVATE, ChatType.BOT):
        return (
            "❌ Scraper faqat **guruhlar** yoki **kanallar**da ishlaydi.\n"
            "Guruh havolasini yuboring: `@guruh_username`"
        )
    return None


async def execute_fast_scrape(user_id: int, target: int, status_msg: Message, client: Client, use_profile_scoring: bool = False):
    """Tezkor scrape — a'zolar ro'yxati orqali yig'ish.
    
    Args:
        user_id: Scrape qilayotgan foydalanuvchi ID
        target: Scrape qilinadigan chat ID
        status_msg: Yangilanuvchi status xabari
        client: Pyrogram client
        use_profile_scoring: Profile score bo'yicha filtrlash
    """
    stop_key = f"scraper_{user_id}_{int(time.time())}"
    stop_flags[stop_key] = False
    
    try:
        user_client = await get_user_client(user_id)
        chat = await user_client.get_chat(target)
        group_title = chat.title or "Nomsiz"
        
        existing_id = await get_group_id_by_title(group_title, owner_id=user_id)
        if existing_id:
            group_id = existing_id
            await update_group_date(group_id, int(time.time()))
        else:
            group_id = await generate_unique_group_id()
            await add_scraped_group(group_id, group_title, int(time.time()), owner_id=user_id)

        count = 0
        filtered_count = 0  # Count of users filtered by profile scoring
        batch = []
        
        # Get profile analyzer if scoring is enabled
        profile_analyzer = None
        if use_profile_scoring and PROFILE_ANALYZER_AVAILABLE:
            profile_analyzer = await get_profile_analyzer()
        
        async for member in user_client.get_chat_members(target):
            if stop_flags.get(stop_key):
                break
            if member.user.is_bot or member.user.is_deleted:
                continue
            if not member.user.username:
                continue

            # Apply profile scoring filter if enabled
            if use_profile_scoring and profile_analyzer:
                try:
                    analysis = await profile_analyzer.analyze(member.user, user_client)
                    if not profile_analyzer.should_include_user(analysis):
                        filtered_count += 1
                        continue
                except Exception as e:
                    # If analysis fails, include the user anyway (graceful degradation)
                    logger.warning(f"Profile analysis failed for user {member.user.id}: {e}")

            batch.append((
                member.user.id,
                member.user.username,
                member.user.first_name,
                group_id
            ))
            
            if len(batch) >= 500:
                await add_scraped_members_batch(batch)
                batch.clear()
            count += 1

            if count % 50 == 0:
                bar, pct = make_progress_bar(count, chat.members_count or count + 100)
                status_text = f"⚡ **Tezkor scrape...**\n\n"
                status_text += f"👥 Yig'ildi: **{count}**\n"
                if use_profile_scoring and filtered_count > 0:
                    status_text += f"🔍 Filtrlangan: **{filtered_count}**\n"
                status_text += f"[{bar}] {pct}%"
                
                try:
                    await status_msg.edit_text(
                        status_text,
                        reply_markup=InlineKeyboardMarkup([
                            [InlineKeyboardButton("🛑 To'xtatish", callback_data=f"stop_scraper_{stop_key}")]
                        ])
                    )
                except:
                    pass
        if batch:
            await add_scraped_members_batch(batch)

        stop_flags.pop(stop_key, None)
        
        # Activity tracking - log scraper statistics
        try:
            from database import record_scraper_activity
            await record_scraper_activity(user_id, count)
        except Exception as e:
            logger.error(f"Scraper activity tracking error: {e}")
        
        action_text = f"Scraper (tez) bajarildi: {count} ta a'zo yig'ildi"
        if use_profile_scoring:
            action_text += f", {filtered_count} ta filtrlangan"
        await log_user_action(user_id, action_text)

        result_text = f"✅ **Muvaffaqiyatli yig'di!**\n\n"
        result_text += f"🏷  Guruh: **{chat.title}**\n"
        result_text += f"👥  Yig'ildi: **{count}**\n"
        if use_profile_scoring and filtered_count > 0:
            result_text += f"🔍  Filtrlangan: **{filtered_count}**\n"
        result_text += f"🗂  Baza ID: `{group_id}`"

        await status_msg.edit_text(
            result_text,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📂 Bazani ochish", callback_data="admin_baza")],
                [InlineKeyboardButton("🔙 Asosiy menyu", callback_data="menu_main")]
            ])
        )
        return True

    except Exception as e:
        stop_flags.pop(stop_key, None)
        await status_msg.edit_text(f"❌ {friendly_scrape_error(e)}")
        return False

async def execute_msg_scrape(user_id: int, target: int, msg_limit: int, status_msg: Message, client: Client):
    """Habarlar orqali scrape — chat tarixidan faol foydalanvchilarni yig'ish."""
    stop_key = f"scraper_{user_id}_{int(time.time())}"
    stop_flags[stop_key] = False
    
    try:
        user_client = await get_user_client(user_id)
        chat = await user_client.get_chat(target)
        group_title = chat.title or "Nomsiz"

        existing_id = await get_group_id_by_title(group_title, owner_id=user_id)
        if existing_id:
            group_id = existing_id
            await update_group_date(group_id, int(time.time()))
        else:
            group_id = await generate_unique_group_id()
            await add_scraped_group(group_id, group_title, int(time.time()), owner_id=user_id)

        seen_ids = set()
        count = 0
        read = 0
        batch = []
        max_seen_ids = 500000

        async for hist_msg in user_client.get_chat_history(target, limit=msg_limit):
            if stop_flags.get(stop_key):
                break
            read += 1

            if hist_msg.from_user and not hist_msg.from_user.is_bot and not hist_msg.from_user.is_deleted:
                if hist_msg.from_user.id not in seen_ids:
                    if not hist_msg.from_user.username:
                        continue
                    seen_ids.add(hist_msg.from_user.id)
                    
                    if len(seen_ids) > max_seen_ids:
                        old_ids = list(seen_ids)[:len(seen_ids) - max_seen_ids]
                        for old_id in old_ids:
                            seen_ids.discard(old_id)
                    
                    batch.append((
                        hist_msg.from_user.id,
                        hist_msg.from_user.username,
                        hist_msg.from_user.first_name,
                        group_id
                    ))
                    
                    if len(batch) >= 500:
                        await add_scraped_members_batch(batch)
                        batch.clear()
                    count += 1

            if read % 500 == 0:
                bar, pct = make_progress_bar(read, msg_limit)
                try:
                    await status_msg.edit_text(
                        f"💬 **Habarlar o'qilmoqda...**\n\n"
                        f"📖 O'qildi: **{read}** / {msg_limit}\n"
                        f"👥 Topildi: **{count}** ta unikal user\n"
                        f"[{bar}] {pct}%",
                        reply_markup=InlineKeyboardMarkup([
                            [InlineKeyboardButton("🛑 To'xtatish", callback_data=f"stop_scraper_{stop_key}")]
                        ])
                    )
                except:
                    pass

        if batch:
            await add_scraped_members_batch(batch)

        stop_flags.pop(stop_key, None)
        
        # Activity tracking - scraper statistikasini yozib qo'yish
        try:
            from database import record_scraper_activity
            await record_scraper_activity(user_id, count)
        except Exception as e:
            logger.error(f"Scraper activity tracking xatosi: {e}")
        
        await log_user_action(user_id, f"Scraper (Xabarlar orqali) ishlatdi: {count} ta a'zo yig'ildi")

        await status_msg.edit_text(
            f"✅ **Habarlar orqali scrape tugadi!**\n\n"
            f"🏷 Guruh: **{chat.title}**\n"
            f"📖 O'qilgan habarlar: **{read}** ta\n"
            f"👥 Topilgan faol userlar: **{count}** ta\n"
            f"🗂 Baza ID: `{group_id}`",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📂 Bazani ochish", callback_data="admin_baza")],
                [InlineKeyboardButton("🔙 Asosiy menyu", callback_data="menu_main")]
            ])
        )
        return True

    except Exception as e:
        stop_flags.pop(stop_key, None)
        await status_msg.edit_text(f"❌ {friendly_scrape_error(e)}")
        return False


@Client.on_callback_query(filters.regex("^menu_scraper$"))
async def scraper_start(client: Client, callback_query: CallbackQuery):
    from feature_flags import gate_feature
    user_id = callback_query.from_user.id
    if not await gate_feature(callback_query, "scraper"):
        return
    
    try:
        del_msg = await callback_query.message.reply_text("⏳", reply_markup=ReplyKeyboardRemove())
        await del_msg.delete()
    except:
        pass

    session_file = os.path.join(SESSIONS_DIR, f"user_{user_id}.session")
    if not os.path.exists(session_file):
        await callback_query.answer("Oldin akkauntingizni ulang!", show_alert=True)
        return

    user_states[user_id] = "waiting_for_scrape_target"
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("❌ Bekor qilish", callback_data="menu_main")]
    ])
    await callback_query.message.edit_text(
        "🔍 **Scraper (Odam yig'ish)**\n\n"
        "Odamlarni yig'ib olmoqchi bo'lgan guruhingizni username yoki havolasini yuboring.\n"
        "Masalan: `@guruh_username` yoki `https://t.me/guruh_username`\n\n"
        "⚠️ Eslatma: Guruhi ochiq va a'zolar ro'yxati ko'rinadigan bo'lishi kerak.",
        reply_markup=keyboard
    )


_scraper_targets = {}

active_scraper_processes = {}  # stop_key -> {"user_id": int, "target": int, "status_msg": Message}

MAX_CONCURRENT_SCRAPERS = 5  # Butun bot uchun maksimal parallel scraper
MAX_SCRAPER_PER_USER = 2  # Har bir user uchun maksimal parallel scraper

@Client.on_message(filters.private & filters.text)
async def scraper_link_handler(client: Client, message: Message):
    user_id = message.from_user.id
    state = user_states.get(user_id)

    if state != "waiting_for_scrape_target":
        raise ContinuePropagation

    target_input = parse_group_identifier(message.text)
    is_invite = (
        target_input.startswith("+")          # +hash
        or "joinchat/" in message.text         # t.me/joinchat/...
    )

    try:
        user_client = await get_user_client(user_id)
        if is_invite:
            try:
                chat = await user_client.join_chat(target_input)
            except Exception as join_err:
                err_name = type(join_err).__name__
                if any(k in err_name for k in ("AuthKey", "Session", "Unauthorized")):
                    raise
                chat = await user_client.get_chat(target_input)
        else:
            chat = await user_client.get_chat(target_input)
    except Exception as e:
        user_states.pop(user_id, None)
        err_str = str(e)
        if "AUTH_KEY_UNREGISTERED" in err_str or "SESSION" in err_str.upper() or "🔑" in err_str:
            await message.reply_text(
                f"{e}",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔗 Akkauntni qayta ulash", callback_data="account_link")],
                    [InlineKeyboardButton("🔙 Bosh menyu", callback_data="menu_main")]
                ])
            )
        else:
            await message.reply_text(
                f"❌ Guruhga ulanib bo'lmadi: {e}\n"
                "(Guruh topilmadi, yopiq, yoki akkauntingiz guruhda yo'q)",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔙 Orqaga", callback_data="menu_main")]
                ])
            )
        return

    type_error = await check_scrape_target(user_client, chat, user_id)
    if type_error:
        user_states.pop(user_id, None)
        await message.reply_text(
            type_error,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Bosh menyu", callback_data="menu_main")]
            ])
        )
        return

    _scraper_targets[user_id] = {"target": chat.id, "stop_key": None}
    user_states.pop(user_id, None)

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("⚡ Odatiy usulda (tez)", callback_data=f"scrape_fast_{user_id}")],
        [InlineKeyboardButton("💬 Habarlar orqali (sekin)", callback_data=f"scrape_msg_{user_id}")],
        [InlineKeyboardButton("👑 Faqat adminlar", callback_data=f"scrape_admin_{user_id}")],
        [InlineKeyboardButton("👩 Faqat qizlar", callback_data=f"scrape_girl_{user_id}")],
        [InlineKeyboardButton("❌ Bekor qilish", callback_data="menu_main")],
    ])

    members_count = chat.members_count or "noma'lum"
    await message.reply_text(
        f"✅ **Guruh topildi!**\n\n"
        f"🏷 **Nomi:** {chat.title}\n"
        f"👥 **A'zolari:** {members_count}\n\n"
        f"📌 Scrape rejimini tanlang:",
        reply_markup=keyboard
    )


@Client.on_callback_query(filters.regex(r"^scrape_fast_(\d+)$"))
async def scrape_fast_callback(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    target_data = _scraper_targets.get(user_id)
    if not target_data:
        await callback_query.answer("Sessiya tugagan, qaytadan bosing. /start", show_alert=True)
        return
    
    target = target_data["target"]
    
    # Check if profile scoring is enabled
    use_profile_scoring = False
    if PROFILE_ANALYZER_AVAILABLE:
        try:
            profile_analyzer = await get_profile_analyzer()
            if profile_analyzer and profile_analyzer.config.enabled:
                use_profile_scoring = True
        except Exception as e:
            logger.warning(f"Failed to check profile analyzer: {e}")
    
    async def scraper_callback(data):
        """Queue processor tomonidan chaqiriladigan callback"""
        from config import bot_client
        status_text = "⚡ **Tezkor scrape boshlandi...**\n\n"
        if use_profile_scoring:
            status_text += "🧠 Profile scoring yoqildi\n"
        status_text += "🔄 A'zolari yig'ilmoqda...\n[░░░░░░░░░░] 0%"
        
        msg = await bot_client.send_message(
            user_id,
            status_text,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🛑 To'xtatish", callback_data="menu_main")]
            ])
        )
        await execute_fast_scrape(user_id, data["target"], msg, client, use_profile_scoring)
    
    operation_size = "medium"  # Oddiy scraper - medium size
    
    queued = await queue_manager.add_to_queue(
        user_id=user_id,
        operation_type="scraper_fast",
        data={"target": target},
        callback=scraper_callback,
        operation_size=operation_size,
        status_msg=callback_query.message
    )
    
    if queued:
        _scraper_targets.pop(user_id, None)
        return
    
    _scraper_targets.pop(user_id, None)
    
    if len(active_scraper_processes) >= MAX_CONCURRENT_SCRAPERS:
        await callback_query.answer(f"⚠️ Serverda hozircha ko'p ishlayapti! Iltimos, keyinroq urinib ko'ring.", show_alert=True)
        return
    
    user_active = sum(1 for p in active_scraper_processes.values() if p["user_id"] == user_id)
    if user_active >= MAX_SCRAPER_PER_USER:
        await callback_query.answer(f"⚠️ Siz bir vaqtda maksimal {MAX_SCRAPER_PER_USER} ta scraper ishlatishingiz mumkin!", show_alert=True)
        return
    
    stop_key = f"scraper_{user_id}_{int(time.time())}"
    stop_flags[stop_key] = False

    status_text = "⚡ **Fast scrape starting...**\n\n"
    if use_profile_scoring:
        status_text += "🧠 Profile scoring enabled\n"
    status_text += "🔄 Collecting members...\n[░░░░░░░░░░] 0%"

    msg = await callback_query.message.edit_text(
        status_text,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🛑 To'xtatish", callback_data=f"stop_scraper_{stop_key}")]
        ])
    )

    active_scraper_processes[stop_key] = {"user_id": user_id, "target": target, "status_msg": msg}

    success = await execute_fast_scrape(user_id, target, msg, client, use_profile_scoring)
    
    stop_flags.pop(stop_key, None)
    active_scraper_processes.pop(stop_key, None)
    
    if not success:
        _scraper_targets.pop(user_id, None)


@Client.on_callback_query(filters.regex(r"^scrape_msg_(\d+)$"))
async def scrape_msg_callback(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    target_data = _scraper_targets.get(user_id)
    if not target_data:
        await callback_query.answer("Sessiya tugagan, qaytadan bosing. /start", show_alert=True)
        return
    
    if len(active_scraper_processes) >= MAX_CONCURRENT_SCRAPERS:
        await callback_query.answer(f"⚠️ Serverda hozircha ko'p ishlayapti! Iltimos, keyinroq urinib ko'ring.", show_alert=True)
        return
    
    user_active = sum(1 for p in active_scraper_processes.values() if p["user_id"] == user_id)
    if user_active >= MAX_SCRAPER_PER_USER:
        await callback_query.answer(f"⚠️ Siz bir vaqtda maksimal {MAX_SCRAPER_PER_USER} ta scraper ishlatishingiz mumkin!", show_alert=True)
        return
    
    user_states[user_id] = f"waiting_msg_count_{user_id}"
    await callback_query.message.edit_text(
        "💬 **Habarlar orqali scrape**\n\n"
        "Nechta habarni o'qishni xohlaysiz?\n"
        "Qancha ko'p habar — shuncha ko'p faol user.\n\n"
        "Raqam kiriting (masalan: `500`, `1000`, `5000`):",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("❌ Bekor qilish", callback_data="menu_main")]
        ])
    )

@Client.on_message(filters.private & filters.text)
async def scrape_msg_count_handler(client: Client, message: Message):
    user_id = message.from_user.id
    state = user_states.get(user_id, "")

    if not isinstance(state, str) or not state.startswith("waiting_msg_count_"):
        raise ContinuePropagation

    target_data = _scraper_targets.pop(user_id, None)
    if not target_data:
        await message.reply_text("❌ Sessiya tugagan, qaytadan bosing. /start")
        user_states.pop(user_id, None)
        return
    target = target_data["target"]

    if not message.text.strip().isdigit():
        _scraper_targets[user_id] = target_data  # qayta saqlaymiz
        await message.reply_text(
            "❌ Faqat raqam kiriting!\n"
            "Masalan: `500`, `1000`, `5000`"
        )
        return

    msg_limit = int(message.text.strip())
    if msg_limit < 10:
        await message.reply_text("❌ Kamida 10 ta habar!")
        return
    if msg_limit > 500000:
        await message.reply_text("❌ Maksimal 500000 ta habar! Xavfsizlik uchun limit qo'yildi.")
        return

    user_states.pop(user_id, None)
    stop_key = f"scraper_{user_id}_{int(time.time())}"
    stop_flags[stop_key] = False

    status_msg = await message.reply_text(
        f"💬 **Habarlar orqali scrape boshlandi...**\n\n"
        f"📖 O'qiladi: **{msg_limit}** ta habar\n"
        f"👥 Topildi: 0 ta\n"
        f"[░░░░░░░░░░] 0%",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🛑 To'xtatish", callback_data=f"stop_scraper_{stop_key}")]
        ])
    )

    active_scraper_processes[stop_key] = {"user_id": user_id, "target": target, "status_msg": status_msg}

    try:
        user_client = await get_user_client(user_id)
        chat = await user_client.get_chat(target)
        group_title = chat.title or "Nomsiz"

        existing_id = await get_group_id_by_title(group_title, owner_id=user_id)
        if existing_id:
            group_id = existing_id
            await update_group_date(group_id, int(time.time()))
        else:
            group_id = await generate_unique_group_id()
            await add_scraped_group(group_id, group_title, int(time.time()), owner_id=user_id)

        seen_ids = set()
        count = 0
        read = 0
        batch = []
        
        max_seen_ids = 500000

        async for hist_msg in user_client.get_chat_history(target, limit=msg_limit):
            if stop_flags.get(stop_key):
                break
            read += 1

            if hist_msg.from_user and not hist_msg.from_user.is_bot and not hist_msg.from_user.is_deleted:
                if hist_msg.from_user.id not in seen_ids:
                    if not hist_msg.from_user.username:
                        continue
                    seen_ids.add(hist_msg.from_user.id)
                    
                    if len(seen_ids) > max_seen_ids:
                        old_ids = list(seen_ids)[:len(seen_ids) - max_seen_ids]
                        for old_id in old_ids:
                            seen_ids.discard(old_id)
                    
                    batch.append((
                        hist_msg.from_user.id,
                        hist_msg.from_user.username,
                        hist_msg.from_user.first_name,
                        group_id
                    ))
                    
                    if len(batch) >= 500:
                        await add_scraped_members_batch(batch)
                        batch.clear()
                    count += 1

            if read % 500 == 0:
                bar, pct = make_progress_bar(read, msg_limit)
                try:
                    await status_msg.edit_text(
                        f"💬 **Habarlar o'qilmoqda...**\n\n"
                        f"📖 O'qildi: **{read}** / {msg_limit}\n"
                        f"👥 Topildi: **{count}** ta unikal user\n"
                        f"[{bar}] {pct}%",
                        reply_markup=InlineKeyboardMarkup([
                            [InlineKeyboardButton("🛑 To'xtatish", callback_data=f"stop_scraper_{stop_key}")]
                        ])
                    )
                except:
                    pass

        if batch:
            await add_scraped_members_batch(batch)

        stop_flags.pop(stop_key, None)
        active_scraper_processes.pop(stop_key, None)

        await log_user_action(user_id, f"Scraper (Xabarlar orqali) ishlatdi: {count} ta a'zo yig'ildi")

        await status_msg.edit_text(
            f"✅ **Habarlar orqali scrape tugadi!**\n\n"
            f"🏷 Guruh: **{chat.title}**\n"
            f"📖 O'qilgan habarlar: **{read}** ta\n"
            f"👥 Topilgan faol userlar: **{count}** ta\n"
            f"🗂 Baza ID: `{group_id}`",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📂 Bazani ochish", callback_data="admin_baza")],
                [InlineKeyboardButton("🔙 Asosiy menyu", callback_data="menu_main")]
            ])
        )

    except Exception as e:
        _scraper_targets.pop(user_id, None)
        stop_flags.pop(stop_key, None)
        active_scraper_processes.pop(stop_key, None)
        await status_msg.edit_text(f"❌ {friendly_scrape_error(e)}")


@Client.on_callback_query(filters.regex(r"^scrape_admin_(\d+)$"))
async def scrape_admin_callback(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    target_data = _scraper_targets.get(user_id)
    if not target_data:
        await callback_query.answer("Sessiya tugagan, qaytadan bosing.", show_alert=True)
        return
    
    target = target_data["target"]
    
    if len(active_scraper_processes) >= MAX_CONCURRENT_SCRAPERS:
        await callback_query.answer(f"⚠️ Serverda hozircha ko'p ishlayapti! Iltimos, keyinroq urinib ko'ring.", show_alert=True)
        return
    
    user_active = sum(1 for p in active_scraper_processes.values() if p["user_id"] == user_id)
    if user_active >= MAX_SCRAPER_PER_USER:
        await callback_query.answer(f"⚠️ Siz bir vaqtda maksimal {MAX_SCRAPER_PER_USER} ta scraper ishlatishingiz mumkin!", show_alert=True)
        return
    
    _scraper_targets.pop(user_id, None)
    stop_key = f"scraper_{user_id}_{int(time.time())}"
    stop_flags[stop_key] = False

    msg = await callback_query.message.edit_text(
        "👑 **Admin scrape boshlandi...**\n\n🔄 Adminlar yig'ilmoqda...",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🛑 To'xtatish", callback_data=f"stop_scraper_{stop_key}")]
        ])
    )

    active_scraper_processes[stop_key] = {"user_id": user_id, "target": target, "status_msg": msg}

    try:
        user_client = await get_user_client(user_id)
        chat = await user_client.get_chat(target)
        group_title = f"{chat.title} (Adminlar)"
        
        existing_id = await get_group_id_by_title(group_title, owner_id=user_id)
        if existing_id:
            group_id = existing_id
            await update_group_date(group_id, int(time.time()))
        else:
            group_id = await generate_unique_group_id()
            await add_scraped_group(group_id, group_title, int(time.time()), owner_id=user_id)

        count = 0
        batch = []
        async for member in user_client.get_chat_members(target, filter=ChatMembersFilter.ADMINISTRATORS):
            if stop_flags.get(stop_key):
                break
            if member.user.is_bot or member.user.is_deleted:
                continue
            if not member.user.username:
                continue

            batch.append((
                member.user.id,
                member.user.username,
                member.user.first_name,
                group_id
            ))
            
            if len(batch) >= 500:
                await add_scraped_members_batch(batch)
                batch.clear()
            count += 1
            
        if batch:
            await add_scraped_members_batch(batch)

        stop_flags.pop(stop_key, None)
        active_scraper_processes.pop(stop_key, None)

        await log_user_action(user_id, f"Scraper (Faqat adminlar) ishlatdi: {count} ta admin yig'ildi")

        await msg.edit_text(
            f"✅ **Admin scrape tugadi!**\n\n"
            f"🏷 Guruh: **{chat.title}**\n"
            f"👑 Topilgan adminlar: **{count}** ta\n"
            f"🗂 Baza ID: `{group_id}`",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📂 Bazani ochish", callback_data="admin_baza")],
                [InlineKeyboardButton("🔙 Asosiy menyu", callback_data="menu_main")]
            ])
        )

    except Exception as e:
        stop_flags.pop(stop_key, None)
        active_scraper_processes.pop(stop_key, None)
        await msg.edit_text(f"❌ {friendly_scrape_error(e)}")


@Client.on_callback_query(filters.regex(r"^scrape_girl_(\d+)$"))
async def scrape_girl_callback(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    target_data = _scraper_targets.get(user_id)
    if not target_data:
        await callback_query.answer("Sessiya tugagan, qaytadan bosing.", show_alert=True)
        return
    
    target = target_data["target"]
    
    if len(active_scraper_processes) >= MAX_CONCURRENT_SCRAPERS:
        await callback_query.answer(f"⚠️ Serverda hozircha ko'p ishlayapti! Iltimos, keyinroq urinib ko'ring.", show_alert=True)
        return
    
    user_active = sum(1 for p in active_scraper_processes.values() if p["user_id"] == user_id)
    if user_active >= MAX_SCRAPER_PER_USER:
        await callback_query.answer(f"⚠️ Siz bir vaqtda maksimal {MAX_SCRAPER_PER_USER} ta scraper ishlatishingiz mumkin!", show_alert=True)
        return
    
    _scraper_targets.pop(user_id, None)
    stop_key = f"scraper_{user_id}_{int(time.time())}"
    stop_flags[stop_key] = False

    msg = await callback_query.message.edit_text(
        "👩 **Qizlar scrape boshlandi...**\n\n"
        "🔄 Ism bo'yicha filter qilinmoqda...\n[░░░░░░░░░░] 0%",
                        reply_markup=InlineKeyboardMarkup([
                            [InlineKeyboardButton("🛑 To'xtatish", callback_data=f"stop_scraper_{stop_key}")]
                        ])
    )

    active_scraper_processes[stop_key] = {"user_id": user_id, "target": target, "status_msg": msg}

    try:
        user_client = await get_user_client(user_id)
        chat = await user_client.get_chat(target)
        group_title = f"{chat.title} (Qizlar)"
        
        existing_id = await get_group_id_by_title(group_title, owner_id=user_id)
        if existing_id:
            group_id = existing_id
            await update_group_date(group_id, int(time.time()))
        else:
            group_id = await generate_unique_group_id()
            await add_scraped_group(group_id, group_title, int(time.time()), owner_id=user_id)

        count = 0
        total_checked = 0
        batch = []

        async for member in user_client.get_chat_members(target):
            if stop_flags.get(stop_key):
                break
            if member.user.is_bot or member.user.is_deleted:
                continue

            total_checked += 1

            if is_likely_girl(member.user.first_name):
                if not member.user.username:
                    continue
                
                batch.append((
                    member.user.id,
                    member.user.username,
                    member.user.first_name,
                    group_id
                ))
                
                if len(batch) >= 500:
                    await add_scraped_members_batch(batch)
                    batch.clear()
                count += 1

            if total_checked % 50 == 0:
                bar, pct = make_progress_bar(total_checked, chat.members_count or total_checked + 100)
                try:
                    await msg.edit_text(
                        f"👩 **Qizlar scrape...**\n\n"
                        f"🔍 Tekshirildi: **{total_checked}**\n"
                        f"👩 Topildi: **{count}** ta qiz\n"
                        f"[{bar}] {pct}%",
                        reply_markup=InlineKeyboardMarkup([
                            [InlineKeyboardButton("🛑 To'xtatish", callback_data=f"stop_scraper_{stop_key}")]
                        ])
                    )
                except:
                    pass

        if batch:
            await add_scraped_members_batch(batch)

        stop_flags.pop(stop_key, None)
        active_scraper_processes.pop(stop_key, None)

        await log_user_action(user_id, f"Scraper (Faqat qizlar) ishlatdi: {count} ta qiz yig'ildi")

        await msg.edit_text(
            f"✅ **Qizlar scrape tugadi!**\n\n"
            f"🏷 Guruh: **{chat.title}**\n"
            f"🔍 Tekshirildi: **{total_checked}** ta\n"
            f"👩 Topilgan qizlar: **{count}** ta\n"
            f"🗂 Baza ID: `{group_id}`",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📂 Bazani ochish", callback_data="admin_baza")],
                [InlineKeyboardButton("🔙 Asosiy menyu", callback_data="menu_main")]
            ])
        )

    except Exception as e:
        stop_flags.pop(stop_key, None)
        active_scraper_processes.pop(stop_key, None)
        await msg.edit_text(f"❌ {friendly_scrape_error(e)}")


@Client.on_message(filters.command("add_to_baza"))
async def add_to_baza_handler(client: Client, message: Message):
    from feature_flags import gate_feature
    if not await gate_feature(message, "scraper"):
        return
    args = message.text.split()
    if len(args) != 3:
        await message.reply_text("Noto'g'ri format! Foydalanish: `/add_to_baza [Baza_ID] [user_id_yoki_username]`")
        return

    baza_id = args[1].strip().upper()
    target = args[2].strip()
    msg = await message.reply_text("🔄 Tekshirilmoqda...")

    user_id = message.from_user.id
    session_name = os.path.join(SESSIONS_DIR, f"user_{user_id}")
    if not os.path.exists(session_name + ".session"):
        await msg.edit_text("Oldin akkauntingizni ulang!")
        return

    try:
        user_client = await get_user_client(user_id)
        try:
            user = await user_client.get_users(target)
            await add_scraped_member(user.id, user.username, user.first_name, baza_id)
            await log_user_action(user_id, f"Yangi user qo'shdi: {user.id} -> Baza: {baza_id}")
            await msg.edit_text(f"✅ **Muvaffaqiyatli qo'shildi!**\\n\\n👤 `{user.first_name}`\\n🗂 Baza ID: `{baza_id}`")
        except Exception as e:
            await msg.edit_text("❌ Foydalanuvchi topilmadi yoki kelib tushirmadi.")
    except Exception as e:
        await msg.edit_text("❌ Sessiya xatosi. Iltimos, akkauntingizni qayta ulang.")


@Client.on_message(filters.private & filters.contact, group=-10)
async def add_contact_to_baza_handler(client: Client, message: Message):
    """Foydalanuvchi kontakt yuborsa, avvalgi bazaga qo'shish imkonini beradi."""
    from config import user_states
    from login_system import LoginState
    user_id = message.from_user.id
    
    # If user is logging in, do NOT intercept contact
    if user_states.get(user_id) in ("waiting_for_phone", "waiting_for_code", "waiting_for_password"):
        raise ContinuePropagation
        
    from feature_flags import gate_feature
    if not await gate_feature(message, "scraper"):
        return
    
    contact = message.contact
    if not contact or not contact.user_id:
        return
    
    user_id = message.from_user.id
    session_name = os.path.join(SESSIONS_DIR, f"user_{user_id}")
    if not os.path.exists(session_name + ".session"):
        await message.reply_text("Oldin akkauntingizni ulang!")
        return
    
    # Baza ID so'rash
    await message.reply_text(
        f"📞 `{contact.phone_number}` raqamli foydalanuvchi bazaga qo'shilishi uchun Baza ID kiriting.\\n"
        f"Masalan: `GR1234567890`",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("❌ Bekor qilish", callback_data="menu_main")]
        ])
    )
    user_states[user_id] = f"waiting_baza_for_contact_{contact.user_id}"



@Client.on_callback_query(filters.regex(r"^stop_scraper_(.+)$"))
async def stop_scraper_callback(client: Client, cq: CallbackQuery):
    stop_key = cq.matches[0].group(1)
    process = active_scraper_processes.get(stop_key)
    
    if process:
        user_id = cq.from_user.id
        if process["user_id"] != user_id:
            await cq.answer("Bu jarayonni faqat boshlagan foydalanuvchi to'xtatishi mumkin", show_alert=True)
            return
        
        stop_flags[stop_key] = True
        await cq.answer("🛑 Scraper to'xtatilmoqda...", show_alert=True)
        try:
            await cq.message.edit_text(
                "🛑 Scraper to'xtatilmoqda...",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Asosiy menyu", callback_data="menu_main")]])
            )
        except:
            pass
        return

    user_id = cq.from_user.id
    removed = await queue_manager.remove_from_queue(user_id)
    if removed:
        await cq.message.edit_text(
            "🛑 **Yig'ish navbati bekor qilindi.**",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Asosiy menyu", callback_data="menu_main")]])
        )
        await cq.answer("Navbat bekor qilindi!", show_alert=True)
        return

    await cq.answer("Jarayon topilmadi", show_alert=True)
