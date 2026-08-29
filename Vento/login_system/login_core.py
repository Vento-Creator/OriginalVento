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
        os.makedirs(self.pending_dir, exist_ok=True)
        os.makedirs(self.sessions_dir, exist_ok=True)
    
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


class AuthManager:
    """Manages authentication operations"""
    
    def __init__(self, api_id: int, api_hash: str, session_manager: SessionManager):
        self.api_id = api_id
        self.api_hash = api_hash
        self.session_manager = session_manager
    
    @staticmethod
    def _delivery_label(value) -> str:
        name = getattr(getattr(value, "__class__", None), "__name__", "") or type(value).__name__
        key = name.lower()
        labels = {
            "sentcodetypeapp": "Telegram ilovasi",
            "sentcodetypesms": "SMS",
            "sentcodetypecall": "telefon qo'ng'irog'i",
            "sentcodetypeflashcall": "flash qo'ng'iroq",
            "sentcodetypemissedcall": "missed call",
            "sentcodetypefragmentsms": "Fragment SMS",
            "sentcodetypesmsword": "SMS (so'z)",
            "sentcodetypesmsphrase": "SMS (ibora)",
            "sentcodetypesetupemailrequired": "email sozlamasi",
            "sentcodetypeemailcode": "email",
        }
        return labels.get(key, name or "Telegram tomonidan tanlangan usul")

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

    async def send_code(self, user_id: int, phone: str, force_sms: bool = False) -> Tuple[Client, str, dict]:
        """
        Send verification code to phone number with hybrid auth fallback
        
        Args:
            user_id: User ID
            phone: Phone number in E.164 format
            force_sms: Force SMS instead of app notification
            
        Returns:
            (client, phone_code_hash)
        """
        session_name = self.session_manager.get_pending_session_path(user_id)
        
        try:
            from pyrogram import Client as PyroClient
            client = PyroClient(
                session_name,
                api_id=self.api_id,
                api_hash=self.api_hash,
                phone_number=phone,
                device_model="Vento Client",
                app_version="Vento Userbot v3.0",
                system_version="Windows 11 Pro 24H2"
            )
            await asyncio.wait_for(client.connect(), timeout=10.0)
            
            # PyroTGFork 2.2.24 does not expose ``force_sms`` as a keyword
            # on Client.send_code().  Passing it there crashes before Telegram
            # can even receive the request.  Keep the login flow compatible with
            # that API and let Telegram choose the delivery method.
            #
            # If this fork supports force_sms on Client construction, it is safe
            # to request it there; otherwise we simply use the normal send_code()
            # path.  This avoids version-specific keyword arguments.
            try:
                if force_sms:
                    try:
                        # Some Pyrogram forks accept force_sms on Client itself.
                        # The already-created client cannot be reconstructed safely
                        # here, so don't retry with an unsupported send_code kwarg.
                        logger.info(
                            "force_sms requested, but using fork-compatible send_code() "
                            "because Client.send_code() does not accept force_sms"
                        )
                    except Exception:
                        pass

                sent = await asyncio.wait_for(
                    client.send_code(phone),
                    timeout=10.0
                )
                delivery = getattr(getattr(sent, "type", None), "__class__", None)
                logger.info(
                    "Code sent successfully to %s (delivery=%s)",
                    self._mask_phone_number(phone),
                    delivery.__name__ if delivery else "unknown"
                )
                return client, sent.phone_code_hash, self._sent_code_metadata(sent)
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
    
    async def resend_code(self, client: Client, phone: str, phone_code_hash: str) -> Tuple[bool, str, Optional[str], dict, int]:
        """Resend using Telegram's auth.resendCode flow and return server metadata."""
        try:
            sent = await asyncio.wait_for(
                client.resend_code(phone, phone_code_hash),
                timeout=10.0
            )
            meta = self._sent_code_metadata(sent)
            wait = max(0, int(meta.get("server_timeout", 0) or 0))
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
            client, phone_code_hash, code_meta = await self.auth_manager.send_code(user_id, phone)
            
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
    
    async def resend_code(self, user_id: int) -> Tuple[bool, str]:
        """
        Resend verification code with alternative methods
        
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
                session.phone_code_hash
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
