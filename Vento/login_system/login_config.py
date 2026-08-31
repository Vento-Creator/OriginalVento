"""
Login Configuration - System settings and constants
"""
from dataclasses import dataclass
from typing import Optional


@dataclass
class LoginSettings:
    """Login system settings"""
    
    # Session settings
    session_timeout: int = 600  # 10 minutes
    max_concurrent_logins: int = 50
    max_login_attempts: int = 5
    
    # Phone validation
    phone_min_length: int = 8
    phone_max_length: int = 15
    require_country_code: bool = True
    
    # Code validation
    code_length: int = 6
    code_retry_limit: int = 3
    
    # Password validation
    password_min_length: int = 1
    password_retry_limit: int = 3
    
    # Admin approval
    require_admin_approval: bool = True
    auto_approve_admins: bool = True
    
    # Security
    cleanup_pending_on_failure: bool = True
    cleanup_pending_on_cancel: bool = True
    
    # Messages
    messages: dict = None
    
    def __post_init__(self):
        if self.messages is None:
            self.messages = {
                "welcome": "👋 Xush kelibsiz! Botdan foydalanish uchun akkauntni ulang.",
                "phone_request": "📱 Telefon raqamingizni xalqaro formatda kiriting:\nMasalan: +998901234567",
                "phone_invalid": "❌ Noto'g'ri format. Xalqaro formatda kiriting:\n`+998901234567`",
                "code_sent": "📨 **Kod yuborildi!**\n\n{delivery_info}\n\nKodni yuboring. Kodni `1 2 3 4 5 6`, `1.2.3.4.5.6` yoki boshqa ajratgichlar bilan ham kiritishingiz mumkin:",
                "code_invalid": "❌ Kod noto'g'ri yoki muddati o'tgan.\n\nQaytadan kodni kiriting:",
                "password_request": "🔐 **Ikki bosqichli tekshiruv (2FA) yoqilgan!**\n\nParolni yuboring:",
                "password_invalid": "❌ Parol xato.\n\nQaytadan parol kiriting:",
                "login_success": "✅ **Muvaffaqiyatli login qilindi!**\n\n⏳ Admin tasdiqlashini kuting.",
                "login_success_admin": "✅ **Admin, muvaffaqiyatli kirdingiz!**\n\nAkkauntingiz botga ulandi.",
                "session_error": "❌ Sessiya tugagan, qaytadan bosing. /start",
                "session_move_error": "❌ Sessiya faylini ko'chirishda xatolik. Qaytadan /start bosing.",
                "generic_error": "❌ Xatolik yuz berdi. Qaytadan /start bosing.",
                "cancelled": "❌ Bekor qilindi. Qaytadan boshlash uchun `/start` yuboring.",
                "approved": "🎉 **Tabriklaymiz!**\n\nAkkauntingiz admin tomonidan tasdiqlandi.\nBotdan foydalanish uchun /start bosing.",
                "rejected": "❌ Sizning so'rovingiz admin tomonidan rad etildi.\n\nBatafsil ma'lumot uchun admin bilan bog'laning.",
                # Enhanced error messages
                "phone_number_invalid": "❌ **Telefon raqami noto'g'ri**\n\nRaqam xalqaro formatda bo'lishi kerak:\n• O'zbekiston: +998901234567\n• Xalqaro: +1234567890",
                "phone_number_banned": "❌ **Telefon raqami bloklangan**\n\nBu raqam Telegram tomonidan cheklangan.\nIltimos, boshqa raqam bilan urinib ko'ring yoki Telegram qo'llab-quvvatlashiga murojaat qiling.",
                "flood_wait": "⏳ **Ko'p urinishlar**\n\nTelegram tomonidan vaqtinchalik cheklov qo'yildi.\nIltimos, {wait_time} soniya kutib qaytadan urinib ko'ring.",
                "sms_blocked": "❌ **SMS yuborish bloklangan**\n\nTelegram SMS xizmatidan foydalanish imkonsiz.\n\nTavsiyalar:\n• VPN yoqib o'chirib ko'ring\n• Boshqa usulni tanlang (qo'ng'iroq)\n• Keyinroq qaytadan urinib ko'ring",
                "phone_password_flood": "❌ **Parol xato urinishlari ko'p**\n\nXavfsizlik sababli vaqtinchalik cheklov qo'yildi.\nIltimos, 15-30 daqiqadan keyin qaytadan urinib ko'ring.",
                "api_id_invalid": "❌ **API xatosi**\n\nBot konfiguratsiyasida xatolik bor.\nIltimos, admin bilan bog'laning.",
                "code_not_received": "❓ **Kod kelmadi?**\n\n⚠️ **Muhim:** Kod ko'p hollarda SMS bilan emas, **Telegram ilovasi ichiga** yuboriladi!\n\n1️⃣ **Telegram ilovasini oching**\n   • Rasmiy **\"Telegram\"** chatini (xizmat xabarlari) tekshiring\n   • Kod o'sha chatga kelgan bo'ladi\n   • Agar boshqa qurilmada Telegram akkauntingiz ochiq bo'lsa — kod o'sha qurilmaga keladi\n\n2️⃣ **2-3 daqiqa kuting**\n   • Ba'zan kod kechikib yetib boradi\n\n3️⃣ **\"Kodni qayta yuborish\" tugmasini bosing**\n   • Keyingi urinish odatda **SMS** orqali yuboriladi\n\n4️⃣ **Tez-tez urinmang**\n   • Ko'p marta so'ralsa Telegram vaqtincha cheklaydi\n   • 10-15 daqiqa kuting va qayta urinib ko'ring",
                "code_resend_success": "🔄 **Kod qayta yuborildi**\n\n{delivery_info}\n{cooldown_info}",
                "code_resend_failed": "❌ **Qayta yuborishda xatolik**\n\nIltimos, biroz vaqtdan keyin qaytadan urinib ko'ring yoki admin bilan bog'laning.",
            }


class LoginConstants:
    """Login system constants"""
    
    # States
    STATE_IDLE = "idle"
    STATE_WAITING_PHONE = "waiting_for_phone"
    STATE_WAITING_CODE = "waiting_for_code"
    STATE_WAITING_PASSWORD = "waiting_for_password"
    STATE_WAITING_ADMIN_APPROVAL = "waiting_for_admin_approval"
    STATE_COMPLETED = "completed"
    STATE_FAILED = "failed"
    
    # Callback data
    CALLBACK_CANCEL_LOGIN = "cancel_login"
    CALLBACK_ADMIN_APPROVE_PREFIX = "admin_approve_"
    CALLBACK_ADMIN_REJECT_PREFIX = "admin_reject_"
    CALLBACK_ADMIN_INVOICE_PREFIX = "admin_invoice_"
    CALLBACK_CHECK_APPROVAL = "check_admin_approval"
    CALLBACK_RESEND_CODE = "resend_code"
    CALLBACK_CODE_HELP = "code_help"
    
    # Buttons
    BUTTON_CANCEL = "❌ Bekor qilish"
    BUTTON_APPROVE = "✅ Tasdiqlash"
    BUTTON_REJECT = "❌ Rad etish"
    BUTTON_INVOICE = "💳 To'lov fakturasini yuborish"
    BUTTON_CHECK_APPROVAL = "🔄 Tasdiqlashni tekshirish"
    BUTTON_RESEND_CODE = "🔄 Kodni qayta yuborish"
    BUTTON_CODE_HELP = "❓ Kod kelmadimi?"
    
    # Time limits
    CODE_EXPIRY_MINUTES = 5
    SESSION_EXPIRY_MINUTES = 10
    APPROVAL_TIMEOUT_HOURS = 24


# Default settings instance
default_settings = LoginSettings()