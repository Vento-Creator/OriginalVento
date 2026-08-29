"""
MassDM Configuration - System settings and constants
"""
from dataclasses import dataclass
from typing import Dict, List


@dataclass
class MassDMSettings:
    """MassDM system settings"""
    
    # Rate limiting
    max_concurrent_massdm: int = 5
    max_massdm_per_user: int = 1
    default_delay: float = 2.0
    min_delay: float = 1.0
    max_delay: float = 5.0
    
    # Auto-stop settings
    floodwait_auto_stop_threshold: int = 300  # seconds
    consecutive_failures_auto_stop: int = 5
    daily_limit_warning: int = 35
    auto_stop_on_high_risk: bool = True  # Enable auto-stop on SpamBot restriction
    
    # SpamBot settings
    spambot_check_interval: int = 10  # check every 10 messages
    spambot_check_milestones: List[int] = None
    spambot_timeout: float = 5.0
    
    # Auto-delete settings
    auto_delete_enabled: bool = False
    auto_delete_delay: int = 60  # seconds
    
    # Messages
    messages: Dict[str, str] = None
    
    def __post_init__(self):
        if self.spambot_check_milestones is None:
            self.spambot_check_milestones = [10, 35, 50, 100]
        
        if self.messages is None:
            self.messages = {
                "setup_welcome": "📨 **MassDM Sozlamalari**\n\nXabar yuborish uchun bazani va xabarni tanlang.",
                "select_group": "📁 **Bazani tanlang**\n\nQaysi bazadan userlarga xabar yuborasiz?",
                "enter_message": "✍️ **Xabarni kiriting**\n\nYubormoqchi bo'lgan xabaringizni yozing:",
                "confirm_start": "🚀 **Tasdiqlash**\n\nXabar yuborishni boshlaysizmi?",
                "progress": "📊 **Yuborilmoqda**\n\n✅ Muvaffaqiyat: {success}\n❌ Xatolar: {failed}\n⏳ Progress: {progress}%",
                "completed": "✅ **Tugatildi**\n\n✅ Muvaffaqiyat: {success}\n❌ Xatolar: {failed}\n📊 Jami: {total}",
                "stopped": "⏸️ **To'xtatildi**\n\n✅ Muvaffaqiyat: {success}\n❌ Xatolar: {failed}\n📊 Jami: {total}",
                "auto_stopped": "🚫 **Avtomatik to'xtatildi**\n\nSabab: {reason}\n✅ Muvaffaqiyat: {success}\n❌ Xatolar: {failed}",
                "error": "❌ **Xatolik**\n\n{error}",
                "no_groups": "📭 **Bazalar yo'q**\n\nAvval bazani yig'ish kerak.",
                "no_members": "📭 **A'zolar yo'q**\n\nBu bazada a'zolar yo'q.",
                "limit_reached": "⚠️ **Limit reached**\n\nKunlik xabar limitiga yetdingiz.",
                "session_error": "🔑 **Sessiya xatosi**\n\nIltimos, qaytadan login qiling.",
            }


class MassDMConstants:
    """MassDM system constants"""
    
    # States
    STATE_IDLE = "idle"
    STATE_SETUP_SELECT_GROUP = "setup_select_group"
    STATE_SETUP_ENTER_MESSAGE = "setup_enter_message"
    STATE_SETUP_CONFIRM = "setup_confirm"
    STATE_RUNNING = "running"
    STATE_PAUSED = "paused"
    STATE_STOPPED = "stopped"
    STATE_COMPLETED = "completed"
    
    # Callback data
    CALLBACK_MASSDM_START = "massdm_start"
    CALLBACK_MASSDM_STOP = "massdm_stop"
    CALLBACK_MASSDM_PAUSE = "massdm_pause"
    CALLBACK_MASSDM_RESUME = "massdm_resume"
    CALLBACK_MASSDM_SELECT_GROUP_PREFIX = "massdm_select_"
    CALLBACK_MASSDM_CONFIRM = "massdm_confirm"
    CALLBACK_MASSDM_CANCEL = "massdm_cancel"
    
    # Buttons
    BUTTON_START = "🚀 Boshlash"
    BUTTON_STOP = "⏸️ To'xtatish"
    BUTTON_PAUSE = "⏸️ Pauza"
    BUTTON_RESUME = "▶️ Davom ettirish"
    BUTTON_CANCEL = "❌ Bekor qilish"
    BUTTON_CONFIRM = "✅ Tasdiqlash"
    BUTTON_BACK = "🔙 Orqaga"
    
    # Error types
    ERROR_BLOCKED = "🚫 Blok"
    ERROR_DEACTIVATED = "💀 O'chirilgan"
    ERROR_NOT_FOUND = "❓ Topilmadi"
    ERROR_WRITE_FORBIDDEN = "🔒 Yozish taqiq"
    ERROR_PRIVACY = "🔐 Maxfiylik"
    ERROR_PREMIUM = "💎 Premium talab"
    ERROR_FLOODWAIT = "⏳ Limit"
    ERROR_FORBIDDEN = "⛔ Taqiqlangan"
    ERROR_PAYMENT = "💰 To'lov talab"
    ERROR_UNKNOWN = "⚠️ Noma'lum"


# SpamBot keywords
SPAMBOT_UNLOCK_KEYWORDS = ["qush", "bird", "erkin", "free", "premium", "unlimited", "no limits"]
SPAMBOT_RESTRICTION_KEYWORDS = ["limited", "cheklov", "restricted", "spam", "blocked", "ban"]


# Default settings instance
default_settings = MassDMSettings()