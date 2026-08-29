from pyrogram import Client, filters
from pyrogram.types import (
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    PreCheckoutQuery,
    Message,
    LabeledPrice,
    WebAppInfo
)
from config import SUPER_ADMIN_ID, SECOND_ADMIN_ID, MINI_APP_URL
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

@Client.on_callback_query(filters.regex("^menu_payment$"))
async def payment_callback(client: Client, cq: CallbackQuery):
    uid = cq.from_user.id

    admin_link = "Admin"
    try:
        info = await client.get_users(SUPER_ADMIN_ID)
        if info.username:
            admin_link = f"@{info.username}"
    except:
        pass

    await cq.message.edit_text(
        "⭐️ **Obuna sotib olish**\n\n"
        "Botdan to'liq foydalanish uchun **1 oylik obuna** xarid qiling.\n\n"
        "💰 Narx: **100 Telegram Stars (XTR)**\n\n"
        "Stars bilan to'lash uchun quyidagi tugmani bosing.\n"
        "Muammo bo'lsa, admin bilan bog'laning.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📱 Mini App orqali to'lash", web_app=WebAppInfo(url=f"{MINI_APP_URL}/subscription"))],
            [InlineKeyboardButton("⭐️ Chatda Stars bilan to'lash", callback_data=f"pay_stars_{uid}")],
            [InlineKeyboardButton("💬 Admin bilan bog'lanish", url=f"https://t.me/{admin_link.replace('@', '')}")],
            [InlineKeyboardButton("🏠 Bosh menyu", callback_data="menu_main")],
        ])
    )
    await cq.answer()


@Client.on_callback_query(filters.regex(r"^pay_stars_(\d+)$"))
async def pay_stars_callback(client: Client, cq: CallbackQuery):
    uid = int(cq.matches[0].group(1))
    caller_id = cq.from_user.id
    
    # Security: check callback target user ID matches the user who clicked it
    if caller_id != uid:
        await cq.answer("⛔️ Ruxsat yo'q!", show_alert=True)
        return
    
    try:
        prices = [LabeledPrice("⭐️ Obuna sotib olish", 100)]
        payload = f"stars_payment_{uid}"
        
        await client.send_invoice(
            chat_id=uid,
            title="⭐️ Obuna sotib olish",
            description="Vento botidan 30 kun to'liq foydalanish uchun Stars orqali to'lov qiling.",
            payload=payload,
            currency="XTR",
            prices=prices
        )
        await cq.answer("To'lov fakturasi yuborildi!")
    except Exception as e:
        logger.error(f"Fakturani yuborishda xatolik user_id={uid}: {e}")
        await cq.answer(f"❌ Xatolik: {e}", show_alert=True)


@Client.on_pre_checkout_query()
async def pre_checkout_handler(client: Client, pcq: PreCheckoutQuery):
    try:
        # Validate payload format
        payload = pcq.invoice_payload
        if not payload or not payload.startswith("stars_payment_"):
            await pcq.answer(ok=False, error_message="Xato to'lov ma'lumoti.")
            return
            
        parts = payload.split("_")
        if len(parts) != 3:
            await pcq.answer(ok=False, error_message="Xato to'lov formati.")
            return
            
        try:
            payload_uid = int(parts[2])
        except ValueError:
            await pcq.answer(ok=False, error_message="Xato foydalanuvchi identifikatori.")
            return
            
        # Security validation
        # 1. user ID matches payload user ID
        if pcq.from_user.id != payload_uid:
            await pcq.answer(ok=False, error_message="Foydalanuvchi mos kelmadi.")
            return
            
        # 2. currency = XTR
        if pcq.currency != "XTR":
            await pcq.answer(ok=False, error_message="Noto'g'ri valyuta.")
            return
            
        # 3. amount = 100
        if pcq.total_amount != 100:
            await pcq.answer(ok=False, error_message="Noto'g'ri to'lov miqdori.")
            return
            
        # Accept the pre-checkout query
        await pcq.answer(ok=True)
    except Exception as e:
        logger.error(f"PreCheckoutQuery xatosi: {e}")
        try:
            await pcq.answer(ok=False, error_message="Tizim xatoligi yuz berdi.")
        except:
            pass


@Client.on_message(filters.successful_payment & filters.private)
async def successful_payment_handler(client: Client, message: Message):
    sp = message.successful_payment
    user_id = message.from_user.id
    
    logger.info(f"Received successful_payment from user_id={user_id}, payload={sp.invoice_payload}")
    
    # Security and parameter validation
    if sp.currency != "XTR":
        logger.warning(f"Payment validation failed for user {user_id}: currency is {sp.currency}, expected XTR")
        return
        
    if sp.total_amount != 100:
        logger.warning(f"Payment validation failed for user {user_id}: amount is {sp.total_amount}, expected 100")
        return
        
    payload = sp.invoice_payload
    if not payload or not payload.startswith("stars_payment_"):
        logger.warning(f"Payment validation failed for user {user_id}: invalid payload {payload}")
        return
        
    parts = payload.split("_")
    if len(parts) != 3:
        logger.warning(f"Payment validation failed for user {user_id}: invalid payload format {payload}")
        return
        
    try:
        payload_uid = int(parts[2])
    except ValueError:
        logger.warning(f"Payment validation failed for user {user_id}: invalid user ID in payload {payload}")
        return
        
    if payload_uid != user_id:
        logger.warning(f"Payment validation failed for user {user_id}: user ID {user_id} does not match payload user ID {payload_uid}")
        return
        
    charge_id = sp.telegram_payment_charge_id
    if not charge_id:
        logger.warning(f"Payment validation failed for user {user_id}: charge_id is missing")
        return
        
    from database import (
        record_payment,
        is_payment_granted,
        grant_subscription,
        mark_payment_granted
    )
    from database_adapter import LoginDatabaseAdapter
    
    # 1. Check duplicate charge ID (Idempotency)
    is_new = await record_payment(
        payment_id=charge_id,
        user_id=user_id,
        amount=sp.total_amount,
        currency=sp.currency,
        invoice_payload=sp.invoice_payload
    )
    
    if not is_new:
        logger.info(f"Duplicate payment received for charge_id {charge_id}. Skipping subscription grant.")
        if await is_payment_granted(charge_id):
            await message.reply_text("✅ To'lovingiz qabul qilingan va obuna allaqachon faollashtirilgan.")
            return
            
    try:
        # 2. Calculate subscription expiry & Grant/extend subscription by 30 days
        new_expiry = await grant_subscription(user_id, days=30)
        
        # 3. Mark payment as granted in DB
        await mark_payment_granted(charge_id, new_expiry)
        
        # 4. Set user active status to True in database
        try:
            await LoginDatabaseAdapter.set_user_active_status(user_id, True)
        except Exception as e:
            logger.error(f"Failed to set user active status in adapter: {e}")
            
        # 5. Automatically complete login if user was waiting for admin approval
        try:
            from login_system.login_handlers import login_service
            from config import user_states
            session = await login_service.state_manager.get_session(user_id)
            if session:
                await login_service.approve_login(user_id)
                user_states.pop(user_id, None)
                logger.info(f"Automatically approved login for user {user_id} on successful payment.")
        except Exception as e:
            logger.error(f"Failed to auto-approve login state for user {user_id}: {e}")
            
        expiry_str = datetime.fromtimestamp(new_expiry).strftime('%d.%m.%Y %H:%M')
        
        # 6. Notify user
        await message.reply_text(
            f"🎉 **To'lov muvaffaqiyatli amalga oshirildi!**\n\n"
            f"Obuna muddati **30 kunga** uzaytirildi.\n"
            f"Amal qilish muddati: **{expiry_str}** gacha.\n\n"
            f"Vento botidan foydalanishda davom etishingiz mumkin!"
        )
        
        # Send main menu
        try:
            from plugins.menu import get_main_keyboard
            kb_reply = await get_main_keyboard(user_id)
            await message.reply_text("🏠 **Bosh menyu**", reply_markup=kb_reply)
        except Exception as e:
            logger.error(f"Failed to send main keyboard to user: {e}")
            
        # 7. Notify admin(s)
        admin_notification = (
            f"💰 **Yangi to'lov qabul qilindi!**\n\n"
            f"Foydalanuvchi: {message.from_user.mention} ([`{user_id}`])\n"
            f"Miqdor: **100 Telegram Stars (XTR)**\n"
            f"Tranzaksiya ID: `{charge_id}`\n"
            f"Obuna muddati: **{expiry_str}** gacha uzaytirildi."
        )
        
        for admin_id in [SUPER_ADMIN_ID, SECOND_ADMIN_ID]:
            try:
                await client.send_message(admin_id, admin_notification)
            except Exception as e:
                logger.error(f"Failed to notify admin {admin_id} about payment: {e}")
                
    except Exception as e:
        logger.error(f"Subscription grant processing failed: {e}")
        await message.reply_text(
            "❌ To'lov qabul qilindi, lekin obunani faollashtirishda xatolik yuz berdi. "
            "Iltimos admin bilan bog'laning va tranzaksiya ID sini ko'rsating:\n"
            f"ID: `{charge_id}`"
        )
