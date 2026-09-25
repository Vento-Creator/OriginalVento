"""
Login System Integration - Plugin Handlers for Pyrogram Plugin Loader
"""
import logging
from pyrogram import Client, filters, ContinuePropagation
from pyrogram.types import Message, CallbackQuery
from config import user_states, is_admin
from error_handler import handle_errors

from login_system import (
    login_service, 
    login_handlers, 
    LoginState,
    LoginConstants
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Message & Callback Handlers for Pyrogram Plugin System
# ---------------------------------------------------------------------------

@Client.on_message(filters.private & (filters.text | filters.contact), group=-12)
async def login_phone_handler(client: Client, message: Message):
    """Handle phone number input"""
    user_id = message.from_user.id
    
    old_state = user_states.get(user_id)
    old_state_str = old_state.value if hasattr(old_state, "value") else str(old_state or "")
    
    session = await login_service.state_manager.get_session(user_id)
    new_state = session.state if session else None
    new_state_str = new_state.value if hasattr(new_state, "value") else str(new_state or "")
    
    logger.info(f"[LOGIN_PHONE_TRACE] User {user_id} input received, old_state={old_state_str}, new_state={new_state_str}")
    
    is_phone_state = (old_state_str == "waiting_for_phone" or new_state_str == "waiting_for_phone")
    is_own_contact = message.contact is not None and message.contact.user_id == user_id
    
    # If user sent a contact card or phone-like text while state wasn't explicitly set, auto-start login
    if not is_phone_state and not is_own_contact:
        txt = (message.text or "").strip()
        digits = "".join(c for c in txt if c.isdigit())
        if not old_state_str and (txt.startswith("+") or (len(digits) in (9, 12) and digits.startswith("9"))):
            logger.info(f"[LOGIN_PHONE_TRACE] User {user_id} sent phone number without active state. Auto-starting login.")
            try:
                user_states[user_id] = "waiting_for_phone"
                await login_service.start_login(user_id)
                is_phone_state = True
            except Exception as e:
                logger.error(f"Failed to auto-start login for {user_id}: {e}")
    
    if not is_phone_state and not is_own_contact:
        raise ContinuePropagation
    
    try:
        await login_handlers.handle_phone_input(client, message)
    except (ContinuePropagation, StopPropagation):
        raise
    except Exception as e:
        logger.error(f"[LOGIN_PHONE_ERROR] User {user_id} error: {e}", exc_info=True)
        try:
            await message.reply_text(f"❌ Xatolik yuz berdi: {e}\n\nIltimos, qaytadan `/start` bosing.")
        except Exception:
            pass


@Client.on_message(filters.private & filters.text, group=-12)
@handle_errors("login", "user_id", auto_retry=False)
async def login_code_handler(client: Client, message: Message):
    """Handle verification code input"""
    user_id = message.from_user.id
    
    old_state = user_states.get(user_id)
    old_state_str = old_state.value if hasattr(old_state, "value") else str(old_state or "")
    
    session = await login_service.state_manager.get_session(user_id)
    new_state = session.state if session else None
    new_state_str = new_state.value if hasattr(new_state, "value") else str(new_state or "")
    
    if old_state_str != "waiting_for_code" and new_state_str != "waiting_for_code":
        raise ContinuePropagation
    
    await login_handlers.handle_code_input(client, message)


@Client.on_message(filters.private & filters.text, group=-12)
@handle_errors("login", "user_id", auto_retry=False)
async def login_password_handler(client: Client, message: Message):
    """Handle 2FA password input"""
    user_id = message.from_user.id
    
    old_state = user_states.get(user_id)
    old_state_str = old_state.value if hasattr(old_state, "value") else str(old_state or "")
    
    session = await login_service.state_manager.get_session(user_id)
    new_state = session.state if session else None
    new_state_str = new_state.value if hasattr(new_state, "value") else str(new_state or "")
    
    if old_state_str != "waiting_for_password" and new_state_str != "waiting_for_password":
        raise ContinuePropagation
    
    await login_handlers.handle_password_input(client, message)


@Client.on_callback_query(filters.regex("^cancel_login$"))
@handle_errors("login", "user_id", auto_retry=False)
async def cancel_login_callback(client: Client, callback_query: CallbackQuery):
    """Handle login cancellation"""
    await login_handlers.handle_cancel_callback(client, callback_query)


@Client.on_callback_query(filters.regex(r"^admin_approve_(\d+)$"))
@handle_errors("login", "user_id", auto_retry=False)
async def admin_approve_callback(client: Client, callback_query: CallbackQuery):
    """Handle admin approval"""
    await login_handlers.handle_admin_approve_callback(client, callback_query)


@Client.on_callback_query(filters.regex(r"^admin_reject_(\d+)$"))
@handle_errors("login", "user_id", auto_retry=False)
async def admin_reject_callback(client: Client, callback_query: CallbackQuery):
    """Handle admin rejection"""
    await login_handlers.handle_admin_reject_callback(client, callback_query)


@Client.on_callback_query(filters.regex("^check_login_approval$"))
@handle_errors("login", "user_id", auto_retry=False)
async def check_approval_callback(client: Client, callback_query: CallbackQuery):
    """Handle approval check button"""
    await login_handlers.handle_check_approval_callback(client, callback_query)


@Client.on_callback_query(filters.regex("^logout$"))
async def logout_callback(client: Client, callback_query: CallbackQuery):
    """Handle logout - CRITICAL: Force clear memory and update DB state"""
    from session_manager import close_user_client
    from database_adapter import LoginDatabaseAdapter
    
    user_id = callback_query.from_user.id
    
    await close_user_client(user_id)
    
    try:
        await LoginDatabaseAdapter.set_user_active_status(user_id, False)
    except Exception as e:
        logger.error("CRITICAL: Failed to set user inactive in DB on logout: %s", e)
    
    user_states.pop(user_id, None)
    user_states[user_id] = LoginState.LOGGED_OUT.value

    try:
        await login_service.state_manager.cleanup_session(user_id)
        login_service.session_manager.cleanup_pending(user_id)
        logger.info("Logout: Cleaned up login state manager session for user %s", user_id)
    except Exception as e:
        logger.warning("Failed to clear LoginStateManager state: %s", e)
    
    try:
        from session_manager import archive_user_session
        if archive_user_session(user_id):
            logger.info("Logout: Session files archived to logged_out/ for user %s", user_id)
    except Exception as e:
        logger.warning("Failed to archive session files on logout: %s", e)

    try:
        from database import remove_pending_approval
        await remove_pending_approval(user_id)
    except Exception as e:
        logger.warning("Failed to remove pending approval on logout: %s", e)
    
    await callback_query.message.edit_text(
        "👋 Akkaunt botdan uzildi.\n\nQaytadan ulash uchun `/start` yuboring."
    )
    await callback_query.answer("Chiqildi.", show_alert=True)


async def start_login_process(user_id: int):
    """Start login process - backward compatibility wrapper"""
    session = await login_service.start_login(user_id)
    user_states[user_id] = LoginState.WAITING_PHONE.value
    return session


async def get_login_state(user_id: int):
    """Get login state - backward compatibility wrapper"""
    session = await login_service.state_manager.get_session(user_id)
    if session:
        return session.state.value
    return None


async def get_login_session(user_id: int):
    """Get login session - compatibility wrapper"""
    return await login_service.state_manager.get_session(user_id)


async def cancel_user_login(user_id: int) -> bool:
    """Cancel user login - compatibility wrapper"""
    await login_service.cancel_login(user_id)
    return True