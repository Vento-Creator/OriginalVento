"""
MassDM System Integration - Old massdm handlers replaced with new system
This file maintains backward compatibility while using the new massdm system
"""
from pyrogram import Client, filters, ContinuePropagation
from pyrogram.types import Message, CallbackQuery
from config import user_states, stop_flags
from massdm_system import (
    massdm_service,
    massdm_handlers,
    MassDMConstants
)

# Export the new system handlers for backward compatibility
from massdm_system.massdm_handlers import (
    massdm_start_command,
    massdm_message_handler,
    massdm_select_group_callback,
    massdm_confirm_callback,
    massdm_stop_callback,
    massdm_cancel_callback,
    massdm_start_callback,
    massdm_toggle_autostop_callback,
    massdm_errors_callback,
    massdm_delete_opts_callback,
    massdm_del_ad_callback,
    massdm_del_all_callback
)

# Maintain backward compatibility with global variables
# This allows other parts of the system to continue working
massdm_lock = massdm_service._lock
massdm_progress = {}  # Will be populated from service
massdm_errors = {}   # Will be populated from service

# Additional compatibility functions for queue_manager integration
async def get_massdm_progress_for_user(user_id: int) -> dict:
    """Get MassDM progress for user - compatibility wrapper"""
    task = await massdm_service.get_user_task(user_id)
    if task and "tracker" in task:
        return task["tracker"].get_stats()
    return {}

async def stop_user_massdm(user_id: int) -> bool:
    """Stop user's MassDM - compatibility wrapper"""
    return await massdm_service.stop_massdm(user_id)

# Export for backward compatibility
__all__ = [
    'massdm_start_command',
    'massdm_message_handler',
    'massdm_select_group_callback',
    'massdm_confirm_callback',
    'massdm_stop_callback',
    'massdm_cancel_callback',
    'massdm_start_callback',
    'massdm_lock',
    'massdm_progress',
    'massdm_errors',
    'get_massdm_progress_for_user',
    'stop_user_massdm',
]