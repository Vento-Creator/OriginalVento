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
        logger.info(f"Duplicate payment received for charge_id {charge_id}. Skipping.")
        if await is_payment_granted(charge_id):
            await message.reply_text("✅ To'lovingiz qabul qilingan va obuna allaqachon faollashtirilgan.")
        else:
            await message.reply_text("✅ Bu to'lov allaqachon qayd etilgan. Admin tasdiqlashini kuting.")
        return

    # SECURITY (Variant B): a payment alone does NOT grant access.
    # The payment is recorded as 'pending' and an admin must approve it
    # (or refund it), so strangers cannot buy their way into heavy features.
    logger.info(f"Payment {charge_id} recorded as PENDING admin approval for user {user_id}.")

    # 1. Tell the user the payment was received and is awaiting approval
    check_kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 Tasdiqlashni tekshirish", callback_data="check_login_approval")]
    ])
    await message.reply_text(
        "✅ **To'lovingiz qabul qilindi!**\n\n"
        "🔒 Xavfsizlik tekshiruvi uchun to'lov admin tasdiqlashidan o'tishi kerak.\n"
        "Tasdiqlangach sizga xabar yuboramiz.",
        reply_markup=check_kb
    )

    # 2. Ask admins to approve (grant subscription) or reject (refund)
    uname = f"@{message.from_user.username}" if message.from_user.username else "yo'q"

    # Referral info: admin tasdiqlashda kim taklif qilganini ko'rsatish
    referrer_line = ""
    try:
        from database import get_referrer, _get_user_display
        referrer_id = await get_referrer(user_id)
        if referrer_id:
            r_username, r_first_name = await _get_user_display(referrer_id)
            r_label = f"@{r_username}" if r_username else (r_first_name or str(referrer_id))
            referrer_line = f"👥 Taklif qilgan: {r_label} ([`{referrer_id}`])\n"
    except Exception as e:
        logger.warning(f"Failed to resolve referrer for payment card {user_id}: {e}")

    admin_kb = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Tasdiqlash", callback_data=f"payok_{user_id}"),
            InlineKeyboardButton("❌ Rad etish (refund)", callback_data=f"payno_{user_id}"),
        ]
    ])
    admin_text = (
        "💰 **Yangi to'lov — tasdiqlash kutilmoqda!**\n\n"
        f"Foydalanuvchi: {message.from_user.mention} ([`{user_id}`])\n"
        f"Username: {uname}\n"
        f"{referrer_line}"
        f"Miqdor: **{sp.total_amount} {sp.currency}**\n"
        f"Tranzaksiya ID: `{charge_id}`\n\n"
        "✅ Tasdiqlangach 30 kunlik obuna faollashadi.\n"
        "❌ Rad etilsa to'lov avtomatik qaytariladi (refund)."
    )

    for admin_id in [SUPER_ADMIN_ID, SECOND_ADMIN_ID]:
        if not admin_id:
            continue
        try:
            await client.send_message(admin_id, admin_text, reply_markup=admin_kb)
        except Exception as e:
            logger.error(f"Failed to notify admin {admin_id} about pending payment: {e}")


def _payment_admin_filter(_, __, query):
    """Only admins may approve/refund payments."""
    from config import is_admin
    return bool(query and query.from_user and is_admin(query.from_user.id))


_payment_admin_cb_filter = filters.create(_payment_admin_filter)


@Client.on_callback_query(filters.regex(r"^payok_(\d+)$") & _payment_admin_cb_filter)
async def payment_approve_callback(client: Client, cq: CallbackQuery):
    """Admin approves a paid subscription -> activate 30 days."""
    import time as _time
    from config import can_manage_users
    from database import get_latest_pending_payment, claim_pending_payment, grant_subscription, get_db_connection
    from database_adapter import LoginDatabaseAdapter

    admin_id = cq.from_user.id
    if not await can_manage_users(admin_id):
        await cq.answer("❌ Sizda foydalanuvchilarni boshqarish huquqi yo'q!", show_alert=True)
        return

    target_id = int(cq.matches[0].group(1))
    payment = await get_latest_pending_payment(target_id)
    if not payment:
        await cq.answer("❌ Tasdiqlanmagan to'lov topilmadi.", show_alert=True)
        return

    # Atomic claim: if two admins click simultaneously only the first wins.
    payment_id = payment["payment_id"]
    new_expiry = int(_time.time()) + 30 * 86400
    if not await claim_pending_payment(payment_id, "granted", new_expiry):
        await cq.answer("❌ Bu to'lov allaqachon ko'rib chiqilgan.", show_alert=True)
        return

    try:
        await grant_subscription(target_id, days=30)
    except Exception as e:
        logger.error(f"Failed to grant subscription after approval for {target_id}: {e}")
        # Revert the claim so the payment can be processed again
        try:
            async with get_db_connection() as db:
                await db.execute(
                    "UPDATE payments SET grant_status = 'pending', granted_expiry = 0, granted_at = 0 WHERE payment_id = ?",
                    (payment_id,)
                )
                await db.commit()
        except Exception as e2:
            logger.error(f"Failed to revert payment claim {payment_id}: {e2}")
        await cq.answer("❌ Obunani faollashtirishda xatolik. Qaytadan urinib ko'ring.", show_alert=True)
        return

    try:
        await LoginDatabaseAdapter.set_user_active_status(target_id, True)
    except Exception as e:
        logger.error(f"Failed to set active status for {target_id}: {e}")

    # Auto-complete the login state if the user was waiting for approval
    try:
        from login_system.login_handlers import login_service
        from config import user_states
        session = await login_service.state_manager.get_session(target_id)
        if session:
            await login_service.approve_login(target_id)
        user_states.pop(target_id, None)
        logger.info(f"Payment approval completed login state for user {target_id}.")
    except Exception as e:
        logger.error(f"Failed to auto-complete login state for user {target_id}: {e}")

    # Referral bonus: reward the inviter when the referred user's payment is approved
    try:
        from feature_flags import is_referral_enabled
        from database import get_referrer, apply_referral_bonus, REFERRAL_BONUS_PAYMENT_DAYS
        if not await is_referral_enabled():
            return
        referrer_id = await get_referrer(target_id)
        if referrer_id and await apply_referral_bonus(referrer_id, REFERRAL_BONUS_PAYMENT_DAYS):
            try:
                await client.send_message(
                    referrer_id,
                    f"💰 **Taklif bonusi!**\n\n"
                    f"Siz taklif qilgan foydalanuvchi obuna sotib oldi.\n"
                    f"🎁 Sizga +{REFERRAL_BONUS_PAYMENT_DAYS} kun obuna qo'shildi!",
                )
            except Exception:
                pass
    except Exception as e:
        logger.error(f"Referral payment bonus failed for {target_id}: {e}")

    try:
        await cq.message.edit_text(
            f"{cq.message.text}\n\n✅ **Tasdiqlandi!** `{target_id}` uchun 30 kunlik obuna faollashtildi."
        )
    except Exception:
        pass

    try:
        from plugins.menu import get_main_keyboard
        await client.send_message(
            target_id,
            "🎉 **To'lovingiz tasdiqlandi!** Sizga **30 kunlik** obuna berildi.\n\nVento Botga xush kelibsiz!",
        )
        kb_reply = await get_main_keyboard(target_id)
        await client.send_message(target_id, "🏠 **Bosh menyu**", reply_markup=kb_reply)
    except Exception as e:
        logger.error(f"Failed to notify user {target_id} about payment approval: {e}")

    await cq.answer("Tasdiqlandi!")


@Client.on_callback_query(filters.regex(r"^payno_(\d+)$") & _payment_admin_cb_filter)
async def payment_reject_callback(client: Client, cq: CallbackQuery):
    """Admin rejects a paid subscription -> refund the Stars."""
    from config import can_manage_users
    from database import get_latest_pending_payment, claim_pending_payment

    admin_id = cq.from_user.id
    if not await can_manage_users(admin_id):
        await cq.answer("❌ Sizda foydalanuvchilarni boshqarish huquqi yo'q!", show_alert=True)
        return

    target_id = int(cq.matches[0].group(1))
    payment = await get_latest_pending_payment(target_id)
    if not payment:
        await cq.answer("❌ Tasdiqlanmagan to'lov topilmadi.", show_alert=True)
        return

    payment_id = payment["payment_id"]
    if not await claim_pending_payment(payment_id, "rejected"):
        await cq.answer("❌ Bu to'lov allaqachon ko'rib chiqilgan.", show_alert=True)
        return

    # Refund the Stars (best effort)
    try:
        await client.refund_star_payment(target_id, payment_id)
        refund_note = "💰 To'lov foydalanuvchiga qaytarildi (refund)."
    except Exception as e:
        logger.error(f"Refund failed for payment {payment_id} user {target_id}: {e}")
        refund_note = (
            "⚠️ Refund avtomatik amalga oshmadi.\n"
            f"Qo'lda qaytarish uchun charge ID: `{payment_id}`\n"
            f"(User ID: `{target_id}`)"
        )

    try:
        await cq.message.edit_text(f"{cq.message.text}\n\n❌ **Rad etildi!**\n{refund_note}")
    except Exception:
        pass

    try:
        await client.send_message(
            target_id,
            "❌ Afsuski, to'lovingiz xavfsizlik tekshiruvidan o'tmadi va yulduzlar akkauntingizga qaytarildi.\n\n"
            "Savollar bo'lsa, admin bilan bog'lanish tugmasidan yozing.",
        )
    except Exception:
        pass

    await cq.answer("Rad etildi!")
