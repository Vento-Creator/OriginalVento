"""
Admin API diagnostics plugin.

Helps diagnose "kod kelmadi" (code not delivered) issues:
  /apidiag          - show per-credential sendCode volume of the API pool
  /apitest <phone>  - perform a REAL sendCode through the login system and
                      report which api pair was used and which delivery
                      method Telegram chose. No login is completed; the
                      pending session is cleaned up immediately.
"""
from pyrogram import Client, filters
from pyrogram.types import Message
from config import is_admin
from login_system import login_service

import logging

logger = logging.getLogger(__name__)


@Client.on_message(filters.private & filters.command("apidiag"))
async def api_diag_command(client: Client, message: Message):
    uid = message.from_user.id
    if not is_admin(uid):
        return

    pool = login_service.auth_manager.credential_pool
    stats = pool.stats()
    lines = [
        "🔧 **API Credential Pool holati**",
        "",
    ]
    for i, s in enumerate(stats, start=1):
        load_bar = "▓" * min(s["hourly_sends"], 20) or "—"
        lines.append(
            f"**{i}.** `{s['api_id']}` ({s['label']}): **{s['hourly_sends']}** ta/soat {load_bar}"
        )
    lines += [
        "",
        "Kod yetkazib bo'lmaganda quyidagilarni tekshiring:",
        "• `/apitest +998901234567` — Telegram qaysi usulni tanlaganini ko'rsatadi",
        "• `/apitest +998901234567 sms` — SMS'ni majburan test qiladi (current_number=False)",
        "• `/apitest +998901234567 2 sms` — 2-juftlik orqali SMS test",
        "• Agar usul **Telegram ilovasi** bo'lsa va foydalanuvchida ilova bo'lmasa —",
        "  `LOGIN_FORCE_SMS=true` env o'zgaruvchisini yoqing (barcha loginlar SMS majburiy)",
    ]
    await message.reply_text("\n".join(lines))


@Client.on_message(filters.private & filters.command("apitest"))
async def api_test_command(client: Client, message: Message):
    uid = message.from_user.id
    if not is_admin(uid):
        return

    parts = (message.text or "").split()
    if len(parts) < 2:
        await message.reply_text(
            "📱 Foydalanish:\n"
            "`/apitest +998901234567` — eng bo'sh juftlik orqali test\n"
            "`/apitest +998901234567 2` — aynan 2-juftlik orqali test\n\n"
            "Bu haqiqiy kod so'rovini yuboradi (login tugatilmaydi) va Telegram "
            "tanlagan yetkazish usulini ko'rsatadi."
        )
        return

    phone = login_service.phone_validator.normalize_phone(parts[1])
    if not phone:
        await message.reply_text("❌ Raqam noto'g'ri formatda. Masalan: `/apitest +998901234567`")
        return

    pair_index = None
    force_sms = False
    for tok in parts[2:]:
        tl = tok.strip().lower()
        if tl in ("sms", "force", "forcesms", "force_sms"):
            force_sms = True
        elif tok.isdigit():
            pool_len = len(login_service.auth_manager.credential_pool)
            if not 1 <= int(tok) <= pool_len:
                await message.reply_text(
                    f"❌ Juftlik raqami 1..{pool_len} oralig'ida bo'lishi kerak "
                    f"(hozirda {pool_len} ta juftlik yuklangan — `/apidiag` bilan ko'ring)."
                )
                return
            pair_index = int(tok)
        else:
            await message.reply_text(
                "❌ Noma'lum parametr. Foydalanish:\n"
                "`/apitest +998901234567` — eng bo'sh juftlik\n"
                "`/apitest +998901234567 2` — 2-juftlik\n"
                "`/apitest +998901234567 sms` — SMS'ni majburan test qilish\n"
                "`/apitest +998901234567 2 sms` — 2-juftlik + SMS"
            )
            return

    msg = await message.reply_text(
        f"🔄 `{phone}` uchun test kod so'rovi yuborilmoqda..."
        + (f" (juftlik #{pair_index})" if pair_index else "")
        + (" (SMS majburiy)" if force_sms else "")
    )
    auth = login_service.auth_manager

    try:
        test_uid = uid  # pending session keyed by admin id; never completed
        client_obj, phone_code_hash, meta = await auth.send_code(
            test_uid, phone, force_sms=force_sms, pair_index=pair_index
        )

        delivery = meta.get("delivery_method") or "noma'lum"
        next_delivery = meta.get("next_delivery_method")
        server_timeout = meta.get("server_timeout", 0)
        api_id = meta.get("api_id", "?")

        # Clean up the test session immediately (no login is completed)
        try:
            if client_obj and client_obj.is_connected:
                await client_obj.disconnect()
        except Exception:
            pass
        login_service.session_manager.cleanup_pending(test_uid)
        try:
            await login_service.state_manager.cleanup_session(test_uid)
        except Exception:
            pass

        warning = ""
        if force_sms and "ilovasi" in delivery.lower():
            warning = (
                "\n\n⚠️ **Telegram force_sms'ni inobatga olmadi** — hali ham ilovaga yubordi. "
                "Bu raqamda aktiv/sahifa sessiya bor, Telegram uni afzal ko'ryapti. "
                "Boshqa juftlik bilan yoki boshqa raqam bilan sinab ko'ring."
            )
        elif "ilovasi" in delivery.lower():
            warning = (
                "\n\n⚠️ Telegram kodni **Telegram ilovasi ichiga** yubordi (SMS emas). "
                "Agar shu raqamdagi qurilmada Telegram ilovasi ulanmagan bo'lsa — kod hech qayerga "
                "yetib bormaydi. `SMS majburiy` uchun `/apitest {phone} sms` bosing."
            )
        elif "sms" not in delivery.lower() and "qo'ng'iroq" not in delivery.lower():
            warning = f"\n\n⚠️ Odatdagi usul emas: **{delivery}**"

        sms_note = " (SMS majburiy)" if force_sms else ""

        await msg.edit_text(
            f"✅ **sendCode muvaffaqiyatli** (Telegram so'rovni qabul qildi){sms_note}\n\n"
            f"📱 Raqam: `{phone}`\n"
            f"🔑 Ishlatilgan api_id: `{api_id}`\n"
            f"📨 Yetkazish usuli: **{delivery}**\n"
            f"⏭ Keyingi usul (resend): {next_delivery or '—'}\n"
            f"⏱ Server timeout: {server_timeout}s"
            f"{warning}\n\n"
            f"❗️Agar barchasi OK ko'rinsa lekin kod baribir kelmasa — Telegram ushbu raqam "
            f"yoki api_id uchun yetkazishni yashirin cheklagan. Boshqa raqam bilan test qiling."
        )
        logger.info(
            "[API_TEST] admin=%s phone=***%s api_id=%s delivery=%s",
            uid, phone[-4:], api_id, delivery,
        )
    except Exception as e:
        try:
            login_service.session_manager.cleanup_pending(uid)
        except Exception:
            pass
        await msg.edit_text(
            f"❌ **sendCode xatolik berdi:** `{type(e).__name__}: {e}`\n\n"
            f"Bu Telegram ushbu so'rovni umuman qabul qilmaganini bildiradi "
            f"(masalan: FloodWait, PHONE_NUMBER_FLOOD, ApiIdInvalid)."
        )
        logger.error("[API_TEST] admin=%s failed: %s: %s", uid, type(e).__name__, e)
