"""
MassDM Handlers - Telegram message and callback handlers
"""
import logging
import asyncio
from pyrogram import Client, filters, ContinuePropagation
from pyrogram.types import Message, CallbackQuery
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from massdm_system.massdm_config import MassDMSettings, MassDMConstants, default_settings
from massdm_system.massdm_core import MassDMService, MassDMError, RateLimitError
from config import is_admin, user_states
from database import get_all_scraped_groups, get_members_by_group_paginated
from error_handler import handle_errors

logger = logging.getLogger(__name__)


class MassDMHandlers:
    """Telegram MassDM handlers"""
    
    def __init__(self, massdm_service: MassDMService):
        self.massdm_service = massdm_service
        self.settings = default_settings
        self.user_states = user_states
        self.user_data = {}    # user_id -> temporary data
    
    def _is_admin(self, user_id: int) -> bool:
        """Check if user is admin"""
        return is_admin(user_id)
    
    @handle_errors("massdm", "user_id", auto_retry=False)
    async def handle_start_massdm(self, client: Client, message: Message):
        """Handle MassDM start command"""
        user_id = message.from_user.id
        
        # Check access
        if not await self._check_access(user_id):
            await message.reply_text("⛔️ Ruxsat yo'q!")
            return
        
        # Check for active task
        active_task = await self.massdm_service.get_user_task(user_id)
        if active_task:
            await message.reply_text("⚠️ Sizda allaqachon aktiv MassDM bor!")
            return
        
        # Get user's groups
        groups = await get_all_scraped_groups(owner_id=user_id)
        if not groups:
            await message.reply_text(self.settings.messages["no_groups"])
            return
        
        # Show group selection
        keyboard = self._build_group_selection_keyboard(groups)
        await message.reply_text(
            self.settings.messages["select_group"],
            reply_markup=keyboard
        )
        
        # Update state
        self.user_states[user_id] = MassDMConstants.STATE_SETUP_SELECT_GROUP

    async def handle_start_massdm_callback(self, client: Client, callback_query: CallbackQuery):
        """Handle MassDM start via callback query"""
        user_id = callback_query.from_user.id
        
        # Check access
        if not await self._check_access(user_id):
            await callback_query.answer("⛔️ Ruxsat yo'q!", show_alert=True)
            return
        
        # Check for active task
        active_task = await self.massdm_service.get_user_task(user_id)
        if active_task:
            await callback_query.answer("⚠️ Sizda allaqachon aktiv MassDM bor!", show_alert=True)
            return
        
        # Get user's groups
        groups = await get_all_scraped_groups(owner_id=user_id)
        if not groups:
            await callback_query.message.edit_text(self.settings.messages["no_groups"])
            await callback_query.answer()
            return
        
        # Show group selection
        keyboard = self._build_group_selection_keyboard(groups)
        await callback_query.message.edit_text(
            self.settings.messages["select_group"],
            reply_markup=keyboard
        )
        
        # Update state
        self.user_states[user_id] = MassDMConstants.STATE_SETUP_SELECT_GROUP
        await callback_query.answer()
    
    def _build_group_selection_keyboard(self, groups: list) -> InlineKeyboardMarkup:
        """Build group selection keyboard"""
        buttons = []
        for group in groups[:10]:  # Show first 10 groups
            group_id = group["group_id"]
            group_title = group["group_title"][:30]  # Truncate long titles
            buttons.append([
                InlineKeyboardButton(
                    group_title,
                    callback_data=f"{MassDMConstants.CALLBACK_MASSDM_SELECT_GROUP_PREFIX}{group_id}"
                )
            ])
        
        buttons.append([InlineKeyboardButton(MassDMConstants.BUTTON_CANCEL, callback_data=MassDMConstants.CALLBACK_MASSDM_CANCEL)])
        
        return InlineKeyboardMarkup(buttons)
    
    @handle_errors("massdm", "user_id", auto_retry=False)
    async def handle_group_selection(self, client: Client, callback_query: CallbackQuery, group_id: str):
        """Handle group selection"""
        user_id = callback_query.from_user.id
        
        # Store selected group
        self.user_data[user_id] = {"group_id": group_id}
        
        # Update state
        self.user_states[user_id] = MassDMConstants.STATE_SETUP_ENTER_MESSAGE
        
        # Request message
        await callback_query.message.edit_text(
            self.settings.messages["enter_message"],
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(MassDMConstants.BUTTON_CANCEL, callback_data=MassDMConstants.CALLBACK_MASSDM_CANCEL)]
            ])
        )
        
        await callback_query.answer()
    
    async def handle_message_input(self, client: Client, message: Message):
        """Handle message input"""
        user_id = message.from_user.id
        
        if self.user_states.get(user_id) != MassDMConstants.STATE_SETUP_ENTER_MESSAGE:
            raise ContinuePropagation
        
        # Store message
        self.user_data[user_id]["message"] = message.text
        
        # Update state
        self.user_states[user_id] = MassDMConstants.STATE_SETUP_CONFIRM
        
        # Show confirmation
        group_id = self.user_data[user_id]["group_id"]
        message_text = self.user_data[user_id]["message"]
        
        preview = f"📁 Baza: `{group_id}`\n\n✍️ Xabar:\n{message_text[:200]}..."
        
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton(MassDMConstants.BUTTON_CONFIRM, callback_data=MassDMConstants.CALLBACK_MASSDM_CONFIRM),
                InlineKeyboardButton(MassDMConstants.BUTTON_CANCEL, callback_data=MassDMConstants.CALLBACK_MASSDM_CANCEL)
            ]
        ])
        
        await message.reply_text(
            f"{self.settings.messages['confirm_start']}\n\n{preview}",
            reply_markup=keyboard
        )
    
    @handle_errors("massdm", "user_id", auto_retry=False)
    async def handle_confirm_start(self, client: Client, callback_query: CallbackQuery):
        """Handle confirmation and start MassDM"""
        user_id = callback_query.from_user.id
        
        # Get data
        group_id = self.user_data[user_id]["group_id"]
        message_text = self.user_data[user_id]["message"]
        
        # Get group members
        members = await get_members_by_group_paginated(group_id, 0, 1000)
        if not members:
            await callback_query.message.edit_text(self.settings.messages["no_members"])
            await callback_query.answer()
            return
        
        # Get user client
        from session_manager import get_user_client
        try:
            user_client = await get_user_client(user_id)
        except Exception as e:
            logger.error(f"Failed to get user client: {e}")
            await callback_query.message.edit_text(self.settings.messages["session_error"])
            await callback_query.answer()
            return
        
        # Prepare stop flag
        stop_flag = [False]
        
        # Status callback
        async def status_callback(stats):
            try:
                # Check if this is the final update
                if stats.get("auto_stop_reason") or stats.get("progress") >= 100:
                    # Final message - show completed/stopped/auto-stopped with error button
                    if stats.get("auto_stop_reason"):
                        final_text = self.settings.messages["auto_stopped"].format(
                            reason=stats["auto_stop_reason"],
                            success=stats["success"],
                            failed=stats["failed"]
                        )
                    elif stats.get("progress") >= 100:
                        final_text = self.settings.messages["completed"].format(
                            success=stats["success"],
                            failed=stats["failed"],
                            total=stats["total"]
                        )
                    else:
                        final_text = self.settings.messages["stopped"].format(
                            success=stats["success"],
                            failed=stats["failed"],
                            total=stats["total"]
                        )
                    
                    # Add error button if failures exist
                    keyboard = None
                    if stats.get("failed", 0) > 0:
                        keyboard = InlineKeyboardMarkup([
                            [InlineKeyboardButton("❌ Xatolik sababini ko'rish", callback_data="massdm_errors_0")]
                        ])
                    
                    await callback_query.message.edit_text(final_text, reply_markup=keyboard)
                else:
                    # Progress update
                    progress_text = self.settings.messages["progress"].format(
                        success=stats["success"],
                        failed=stats["failed"],
                        progress=int(stats["progress"])
                    )
                    await callback_query.message.edit_text(progress_text)
            except Exception:
                pass
        
        # Start MassDM in background
        import asyncio
        from task_supervisor import schedule_guarded
        task = schedule_guarded("MassDM Task", self.massdm_service.start_massdm(
            user_id,
            user_client,
            members,
            message_text,
            status_callback,
            stop_flag,
        ))
        
        # Update state
        self.user_states[user_id] = MassDMConstants.STATE_RUNNING
        
        # Show control keyboard
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton(MassDMConstants.BUTTON_STOP, callback_data=MassDMConstants.CALLBACK_MASSDM_STOP)
            ]
        ])
        
        await callback_query.message.edit_text(
            "🚀 **MassDM boshlandi!**",
            reply_markup=keyboard
        )
        
        await callback_query.answer()
    
    async def handle_stop(self, client: Client, callback_query: CallbackQuery):
        """Handle stop MassDM"""
        user_id = callback_query.from_user.id
        
        # Try to stop active task
        success = await self.massdm_service.stop_massdm(user_id)
        
        if success:
            self.user_states[user_id] = MassDMConstants.STATE_STOPPED
            
            # Check if there are errors to show
            task = await self.massdm_service.get_user_task(user_id)
            keyboard = None
            if task and "tracker" in task:
                tracker = task["tracker"]
                if tracker.failed > 0:
                    keyboard = InlineKeyboardMarkup([
                        [InlineKeyboardButton("❌ Xatolik sababini ko'rish", callback_data="massdm_errors_0")]
                    ])
            
            await callback_query.message.edit_text(
                self.settings.messages["stopped"],
                reply_markup=keyboard
            )
        else:
            # Check if in queue
            from queue_manager import queue_manager
            removed = await queue_manager.remove_from_queue(user_id)
            if removed:
                await callback_query.message.edit_text(
                    "🛑 **Tarqatish navbati bekor qilindi.**",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Asosiy menyu", callback_data="menu_main")]])
                )
                await callback_query.answer("Navbat bekor qilindi!", show_alert=True)
                return
            else:
                await callback_query.answer("MassDM topilmadi yoki allaqachon yakunlangan.", show_alert=True)
    
    async def handle_cancel(self, client: Client, callback_query: CallbackQuery):
        """Handle cancel MassDM setup"""
        user_id = callback_query.from_user.id
        
        # Cleanup
        self.user_states.pop(user_id, None)
        self.user_data.pop(user_id, None)
        
        await callback_query.message.edit_text("❌ Bekor qilindi.")
        await callback_query.answer()
    
    async def _check_access(self, user_id: int) -> bool:
        """Check if user has access to MassDM"""
        # Add your access check logic here
        return True
    
    async def handle_toggle_autostop(self, client: Client, callback_query: CallbackQuery):
        """Toggle auto-stop on high risk"""
        user_id = callback_query.from_user.id
        
        # Get current settings
        current_settings = await self.massdm_service._get_user_settings(user_id)
        auto_stop = current_settings.get("auto_stop_on_high_risk", True)
        
        # Toggle
        new_setting = not auto_stop
        await self.massdm_service.set_user_settings(user_id, {"auto_stop_on_high_risk": new_setting})
        
        # Update display
        status = "✅ YOQILGAN" if new_setting else "❌ O'CHIRILGAN"
        auto_stop_btn = "✅ Auto-Stop: YOQIQ" if new_setting else "❌ Auto-Stop: O'CHIQ"
        
        await callback_query.message.edit_text(
            f"🛡 **Emergency Auto-Stop rejimi:** {status}\n\n"
            f"**Yoqilganda:** Kritik xavf aniqlansa (SpamBot cheklovi, ketma-ket 5+ xato, "
            f"300+ soniya FloodWait) MassDM jarayoni AVTOMATIK to'xtatiladi va "
            f"kelgan joyidan davom ettirish imkoniyati beriladi.\n\n"
            f"**O'chirilganda:** Jarayon hech qachon avtomatik to'xtatilmaydi — "
            f"faqat ogohlantirish yuboriladi va tezlik sekinlashtiriladi.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(auto_stop_btn, callback_data="massdm_toggle_autostop")],
                [InlineKeyboardButton("🏠 Asosiy menyu", callback_data="menu_main")]
            ])
        )
        await callback_query.answer()
    
    async def handle_view_errors(self, client: Client, callback_query: CallbackQuery, page: int):
        """View MassDM errors with pagination"""
        user_id = callback_query.from_user.id
        
        # Get errors from completed tasks first
        errors = await self.massdm_service.get_completed_task_errors(user_id)
        
        # If not in completed tasks, try active task
        if not errors:
            task = await self.massdm_service.get_user_task(user_id)
            if task and "tracker" in task:
                errors = task["tracker"].errors
        
        if not errors:
            await callback_query.answer("Xato ma'lumotlari topilmadi yoki muddati o'tgan.", show_alert=True)
            return
        
        PER_PAGE = 50
        total = len(errors)
        total_pages = max(1, (total + PER_PAGE - 1) // PER_PAGE)
        page = max(0, min(page, total_pages - 1))
        
        start = page * PER_PAGE
        chunk = errors[start : start + PER_PAGE]
        
        # Count error reasons
        reason_counts = {}
        for _, reason in chunk:
            reason_counts[reason] = reason_counts.get(reason, 0) + 1
        
        summary_lines = [f"  {reason}: <b>{count}</b> ta" for reason, count in sorted(reason_counts.items(), key=lambda x: -x[1])]
        
        header = (
            f"<b>❌ Xato sabablari ({total} ta)</b>\n"
            f"<i>Sahifa {page + 1} / {total_pages}</i>\n\n"
            + "\n".join(summary_lines)
            + "\n\n" + "─" * 20 + "\n"
        )
        
        lines = []
        for i, (display, reason) in enumerate(chunk, start + 1):
            lines.append(f"{i}. {display} — {reason}")
        
        text = header + "\n".join(lines)
        
        if len(text) > 4090:
            text = text[:4087] + "..."
        
        nav = []
        if page > 0:
            nav.append(InlineKeyboardButton("⬅️ Oldingi", callback_data=f"massdm_errors_{page - 1}"))
        if page < total_pages - 1:
            nav.append(InlineKeyboardButton("Keyingi ➡️", callback_data=f"massdm_errors_{page + 1}"))
        
        buttons = []
        if nav:
            buttons.append(nav)
        buttons.append([InlineKeyboardButton("🔙 Orqaga", callback_data="menu_main")])
        
        await callback_query.message.edit_text(
            text,
            parse_mode="html",
            reply_markup=InlineKeyboardMarkup(buttons),
            disable_web_page_preview=True
        )
        await callback_query.answer()
    
    async def handle_delete_options(self, client: Client, callback_query: CallbackQuery):
        """Show message deletion options"""
        user_id = callback_query.from_user.id
        
        # Check if there's history
        task = await self.massdm_service.get_user_task(user_id)
        if not task or "tracker" not in task:
            await callback_query.answer("O'chirish uchun xabarlar topilmadi!", show_alert=True)
            return
        
        await callback_query.message.edit_text(
            "🗑 **Tarqatilgan xabarlarni o'chirish**\n\n"
            "Nimani o'chirmoqchisiz?\n\n"
            "• **Faqat rek habari:** Faqat yuborilgan reklama xabari o'chadi.\n"
            "• **Butun chat:** Shu foydalanuvchilar bilan bo'lgan BARCHA yozishmalar o'chib ketadi.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("1️⃣ Faqat rek habari", callback_data="massdm_del_ad")],
                [InlineKeyboardButton("2️⃣ Butun chat", callback_data="massdm_del_all")],
                [InlineKeyboardButton("🔙 Orqaga", callback_data="menu_main")]
            ])
        )
        await callback_query.answer()
    
    async def handle_delete_ads(self, client: Client, callback_query: CallbackQuery):
        """Delete only advertisement messages"""
        user_id = callback_query.from_user.id
        
        task = await self.massdm_service.get_user_task(user_id)
        if not task or "tracker" not in task:
            await callback_query.answer("Xabarlar topilmadi", show_alert=True)
            return
        
        status_msg = await callback_query.message.edit_text("🗑 Faqat tarqatilgan xabarlar o'chirilmoqda...")
        
        try:
            user_client = await get_user_client(user_id)
            deleted = 0
            
            # Get sent messages from tracker history
            tracker = task.get("tracker")
            history = tracker.history if tracker else {}
            
            for target_user_id, msg_id in history.items():
                if msg_id == 0:  # Skip placeholder entries
                    continue
                try:
                    await user_client.delete_messages(target_user_id, msg_id)
                    deleted += 1
                except Exception:
                    pass
                await asyncio.sleep(0.5)
            
            await status_msg.edit_text(
                f"✅ **Xabarlar o'chirildi!**\n\n🗑 O'chirilgan xabarlar soni: {deleted}",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Asosiy menyu", callback_data="menu_main")]])
            )
        except Exception as e:
            logger.error(f"Delete ads error: {e}")
            await status_msg.edit_text(f"❌ Xatolik: {e}")
        
        await callback_query.answer()
    
    async def handle_delete_all(self, client: Client, callback_query: CallbackQuery):
        """Delete entire chat history"""
        user_id = callback_query.from_user.id
        
        task = await self.massdm_service.get_user_task(user_id)
        if not task or "tracker" not in task:
            await callback_query.answer("Xabarlar topilmadi", show_alert=True)
            return
        
        status_msg = await callback_query.message.edit_text("🗑 Chatlar butunlay tozalanmoqda...")
        
        try:
            user_client = await get_user_client(user_id)
            deleted = 0
            
            # Get sent messages from tracker history
            tracker = task.get("tracker")
            history = tracker.history if tracker else {}
            
            for target_user_id in list(history.keys()):
                try:
                    await user_client.delete_history(target_user_id)
                    deleted += 1
                except Exception:
                    pass
                await asyncio.sleep(0.5)
            
            await status_msg.edit_text(
                f"✅ **Chatlar butunlay tozalandi!**\n\n🗑 Tozalangan chatlar soni: {deleted}",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Asosiy menyu", callback_data="menu_main")]])
            )
        except Exception as e:
            logger.error(f"Delete all error: {e}")
            await status_msg.edit_text(f"❌ Xatolik: {e}")
        
        await callback_query.answer()


# Initialize MassDM service
massdm_service = MassDMService(default_settings)
massdm_handlers = MassDMHandlers(massdm_service)


# Register handlers
@Client.on_message(filters.private & filters.command("massdm"))
@handle_errors("massdm", "user_id", auto_retry=False)
async def massdm_start_command(client: Client, message: Message):
    """Handle /massdm command"""
    await massdm_handlers.handle_start_massdm(client, message)


@Client.on_message(filters.private & filters.text)
@handle_errors("massdm", "user_id", auto_retry=False)
async def massdm_message_handler(client: Client, message: Message):
    """Handle message input for MassDM"""
    await massdm_handlers.handle_message_input(client, message)


@Client.on_callback_query(filters.regex("^massdm_select_(.+)$"))
@handle_errors("massdm", "user_id", auto_retry=False)
async def massdm_select_group_callback(client: Client, callback_query: CallbackQuery):
    """Handle group selection"""
    group_id = callback_query.matches[0].group(1)
    await massdm_handlers.handle_group_selection(client, callback_query, group_id)


@Client.on_callback_query(filters.regex("^massdm_confirm$"))
@handle_errors("massdm", "user_id", auto_retry=False)
async def massdm_confirm_callback(client: Client, callback_query: CallbackQuery):
    """Handle confirmation"""
    await massdm_handlers.handle_confirm_start(client, callback_query)


@Client.on_callback_query(filters.regex("^massdm_stop$"))
@handle_errors("massdm", "user_id", auto_retry=False)
async def massdm_stop_callback(client: Client, callback_query: CallbackQuery):
    """Handle stop"""
    await massdm_handlers.handle_stop(client, callback_query)


@Client.on_callback_query(filters.regex("^massdm_cancel$"))
@handle_errors("massdm", "user_id", auto_retry=False)
async def massdm_cancel_callback(client: Client, callback_query: CallbackQuery):
    """Handle cancel"""
    await massdm_handlers.handle_cancel(client, callback_query)


@Client.on_callback_query(filters.regex("^menu_massdm$"))
@handle_errors("massdm", "user_id", auto_retry=False)
async def massdm_start_callback(client: Client, callback_query: CallbackQuery):
    """Handle MassDM start via callback query"""
    await massdm_handlers.handle_start_massdm_callback(client, callback_query)


# Additional callbacks for restored features
@Client.on_callback_query(filters.regex("^massdm_toggle_autostop$"))
@handle_errors("massdm", "user_id", auto_retry=False)
async def massdm_toggle_autostop_callback(client: Client, callback_query: CallbackQuery):
    """Toggle auto-stop on high risk"""
    await massdm_handlers.handle_toggle_autostop(client, callback_query)


@Client.on_callback_query(filters.regex(r"^massdm_errors_(\d+)$"))
@handle_errors("massdm", "user_id", auto_retry=False)
async def massdm_errors_callback(client: Client, callback_query: CallbackQuery):
    """View errors with pagination"""
    page = int(callback_query.matches[0].group(1))
    await massdm_handlers.handle_view_errors(client, callback_query, page)


@Client.on_callback_query(filters.regex("^massdm_delete_opts$"))
@handle_errors("massdm", "user_id", auto_retry=False)
async def massdm_delete_opts_callback(client: Client, callback_query: CallbackQuery):
    """Show deletion options"""
    await massdm_handlers.handle_delete_options(client, callback_query)


@Client.on_callback_query(filters.regex("^massdm_del_ad$"))
@handle_errors("massdm", "user_id", auto_retry=False)
async def massdm_del_ad_callback(client: Client, callback_query: CallbackQuery):
    """Delete advertisement messages only"""
    await massdm_handlers.handle_delete_ads(client, callback_query)


@Client.on_callback_query(filters.regex("^massdm_del_all$"))
@handle_errors("massdm", "user_id", auto_retry=False)
async def massdm_del_all_callback(client: Client, callback_query: CallbackQuery):
    """Delete entire chat history"""
    await massdm_handlers.handle_delete_all(client, callback_query)
