"""
UTAG Handlers - Telegram message and callback handlers
"""
from pyrogram import Client, filters, ContinuePropagation
from pyrogram.types import Message, CallbackQuery
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from utag_system.utag_config import UtagSettings, UtagConstants, default_settings
from utag_system.utag_core import UtagService, UtagError, ValidationError
from config import is_admin, user_states
from error_handler import handle_errors
import logging

logger = logging.getLogger(__name__)


class UtagHandlers:
    """Telegram UTAG handlers"""
    
    def __init__(self, utag_service: UtagService):
        self.utag_service = utag_service
        self.settings = default_settings
        self.user_states = user_states
        self.user_data = {}    # user_id -> temporary data
    
    def _is_admin(self, user_id: int) -> bool:
        """Check if user is admin"""
        return is_admin(user_id)
    
    @handle_errors("utag", "user_id", auto_retry=False)
    async def handle_utag_start(self, client: Client, message: Message):
        """Handle UTAG start command"""
        user_id = message.from_user.id
        
        # Show main menu
        keyboard = self._build_main_keyboard()
        await message.reply_text(
            self.settings.messages["setup_welcome"],
            reply_markup=keyboard
        )
        
        self.user_states[user_id] = UtagConstants.STATE_IDLE

    async def handle_utag_start_callback(self, client: Client, callback_query: CallbackQuery):
        """Handle UTAG start via callback query"""
        user_id = callback_query.from_user.id
        
        # Show main menu by editing message
        keyboard = self._build_main_keyboard()
        try:
            await callback_query.message.edit_text(
                self.settings.messages["setup_welcome"],
                reply_markup=keyboard
            )
        except Exception:
            try:
                await callback_query.message.reply_text(
                    self.settings.messages["setup_welcome"],
                    reply_markup=keyboard
                )
            except:
                pass
                
        self.user_states[user_id] = UtagConstants.STATE_IDLE
        await callback_query.answer()
    
    def _build_main_keyboard(self) -> InlineKeyboardMarkup:
        """Build main UTAG keyboard"""
        return InlineKeyboardMarkup([
            [
                InlineKeyboardButton(UtagConstants.BUTTON_ADD_COMMAND, callback_data=UtagConstants.CALLBACK_UTAG_ADD_COMMAND),
                InlineKeyboardButton(UtagConstants.BUTTON_REMOVE_COMMAND, callback_data=UtagConstants.CALLBACK_UTAG_REMOVE_COMMAND)
            ],
            [
                InlineKeyboardButton(UtagConstants.BUTTON_LIST_COMMANDS, callback_data=UtagConstants.CALLBACK_UTAG_LIST_COMMANDS),
                InlineKeyboardButton(UtagConstants.BUTTON_SET_TIMER, callback_data=UtagConstants.CALLBACK_UTAG_SET_TIMER)
            ],
            [InlineKeyboardButton(UtagConstants.BUTTON_CANCEL, callback_data=UtagConstants.CALLBACK_UTAG_CANCEL)]
        ])
    
    async def handle_add_command(self, client: Client, callback_query: CallbackQuery):
        """Handle add command request"""
        user_id = callback_query.from_user.id
        
        self.user_states[user_id] = UtagConstants.STATE_SETUP_COMMAND
        
        await callback_query.message.edit_text(
            "➕ **Komanda qo'shish**\n\nKomandani kiriting (masalan: /salom):",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(UtagConstants.BUTTON_CANCEL, callback_data=UtagConstants.CALLBACK_UTAG_CANCEL)]
            ])
        )
        
        await callback_query.answer()
    
    async def handle_message_input(self, client: Client, message: Message):
        """Handle message input for command (both command name and message text phases)"""
        user_id = message.from_user.id
        state = self.user_states.get(user_id)
        
        if state == UtagConstants.STATE_SETUP_COMMAND:
            # Phase 1: Command name input
            command = message.text.strip()
            
            # Validate command format
            is_valid, err_msg = self.utag_service.validator.validate_command(command)
            if not is_valid:
                await message.reply_text(f"❌ {err_msg}\n\nQaytadan kiriting (masalan: /salom):")
                return
            
            # Check if command already exists
            exists = await self.utag_service.command_manager.command_exists(user_id, command)
            if exists:
                await message.reply_text("❌ Bu komanda allaqachon mavjud.\n\nQaytadan kiriting:")
                return
            
            # Store command and transition state
            self.user_data[user_id] = {"command": command}
            self.user_states[user_id] = UtagConstants.STATE_SETUP_COMMAND_MESSAGE
            
            # Request message text
            await message.reply_text(
                "✍️ **Xabarni kiriting**\n\nTag xabarni yozing:",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton(UtagConstants.BUTTON_CANCEL, callback_data=UtagConstants.CALLBACK_UTAG_CANCEL)]
                ])
            )
            return
            
        elif state == UtagConstants.STATE_SETUP_COMMAND_MESSAGE:
            # Phase 2: Message body input
            if user_id not in self.user_data or "command" not in self.user_data[user_id]:
                self.user_states[user_id] = UtagConstants.STATE_IDLE
                raise ContinuePropagation
            
            command = self.user_data[user_id]["command"]
            message_text = message.text
            
            # Add command
            success, result = await self.utag_service.add_custom_command(user_id, command, message_text)
            if success:
                logger.info(f"User {user_id} created custom tag command '{command}' -> '{message_text[:30]}'")
            
            # Cleanup
            self.user_states[user_id] = UtagConstants.STATE_IDLE
            self.user_data.pop(user_id, None)
            
            await message.reply_text(result)
            return
            
        else:
            # Check if this is a custom command execution
            command = message.text.strip()
            if command.startswith("/"):
                await self._execute_custom_command(client, message, user_id, command)
            raise ContinuePropagation
            
    async def _execute_custom_command(self, client: Client, message: Message, user_id: int, command: str):
        """Execute custom tag command"""
        message_text = await self.utag_service.execute_command(user_id, command)
        
        if message_text:
            await message.reply_text(message_text)
        else:
            raise ContinuePropagation
    
    async def handle_list_commands(self, client: Client, callback_query: CallbackQuery):
        """Handle list commands request"""
        user_id = callback_query.from_user.id
        
        commands = await self.utag_service.get_user_commands(user_id)
        
        if not commands:
            await callback_query.message.edit_text("📭 Komandalar yo'q.")
            await callback_query.answer()
            return
        
        # Build command list
        command_list = "\n".join([f"{cmd.command} -> {cmd.message[:30]}..." for cmd in commands])
        
        await callback_query.message.edit_text(
            self.settings.messages["command_list"].format(commands=command_list),
            reply_markup=self._build_main_keyboard()
        )
        
        await callback_query.answer()
    
    async def handle_remove_command(self, client: Client, callback_query: CallbackQuery):
        """Handle remove command request"""
        user_id = callback_query.from_user.id
        
        commands = await self.utag_service.get_user_commands(user_id)
        
        if not commands:
            await callback_query.message.edit_text("📭 Komandalar yo'q.")
            await callback_query.answer()
            return
        
        # Build command selection keyboard
        buttons = []
        for cmd in commands:
            buttons.append([
                InlineKeyboardButton(
                    cmd.command,
                    callback_data=f"utag_remove_{cmd.command}"
                )
            ])
        
        buttons.append([InlineKeyboardButton(UtagConstants.BUTTON_BACK, callback_data=UtagConstants.CALLBACK_UTAG_START)])
        
        await callback_query.message.edit_text(
            "🗑 **Komandani tanlang**",
            reply_markup=InlineKeyboardMarkup(buttons)
        )
        
        await callback_query.answer()
    
    async def handle_command_removal(self, client: Client, callback_query: CallbackQuery, command: str):
        """Handle specific command removal"""
        user_id = callback_query.from_user.id
        
        success, result = await self.utag_service.remove_custom_command(user_id, command)
        
        await callback_query.message.edit_text(
            result,
            reply_markup=self._build_main_keyboard()
        )
        
        await callback_query.answer()
    
    async def handle_cancel(self, client: Client, callback_query: CallbackQuery):
        """Handle cancel"""
        user_id = callback_query.from_user.id
        
        self.user_states.pop(user_id, None)
        self.user_data.pop(user_id, None)
        
        await callback_query.message.edit_text("❌ Bekor qilindi.")
        await callback_query.answer()

    async def handle_group_message(self, client: Client, message: Message):
        """Handle group tag commands (.atag, .stop, .pause, .resume and custom tag command triggers)"""
        if not message.from_user or not message.chat:
            return
        user_id = message.from_user.id
        chat_id = message.chat.id
        
        text = message.text.strip()
        
        # Check command formats
        is_custom_shortcut = False
        target_message_content = ""
        use_random_messages = False
        
        # 1. Custom tag shortcut commands: starting with /
        if text.startswith("/"):
            # Check if this is a registered custom tag shortcut command
            parts = text.split(maxsplit=1)
            # Strip a trailing ``@botusername``: Telegram delivers slash commands in
            # groups as ``/mytag@MyBot``, and the registered shortcut is stored bare.
            cmd = parts[0].split("@", 1)[0]
            tag_command = await self.utag_service.command_manager.get_command(user_id, cmd)
            if tag_command:
                is_custom_shortcut = True
                target_message_content = tag_command.message
                # Support text after custom command as additional tagging message
                if len(parts) > 1:
                    target_message_content = f"{target_message_content} {parts[1]}"
            else:
                raise ContinuePropagation
        
        # 2. Dot-prefixed built-in commands are handled by plugins/utag.py.
        # Keep one authoritative implementation for .atag/.stop/.pause/.resume so the
        # plugin's process tracking, speed settings and reserved-command logic are used.
        elif text.startswith("."):
            raise ContinuePropagation
        else:
            raise ContinuePropagation

        # Start group tagging process
        # Check permissions & subscription
        from plugins.menu import _has_access
        if not await _has_access(user_id):
            await message.reply_text("❌ Botdan foydalanish uchun obuna sotib oling yoki admin ruxsatini kuting!")
            return
            
        # Get user client
        from session_manager import get_user_client
        try:
            user_client = await get_user_client(user_id)
            if not user_client:
                await message.reply_text("❌ Akkauntingiz botga ulanmagan! Raqamingizni ulab qayta bosing.")
                return
        except Exception as e:
            await message.reply_text(f"❌ Akkauntga ulanishda xatolik: {e}")
            return
            
        # Fetch group members
        members = []
        try:
            async for member in user_client.get_chat_members(chat_id):
                u = member.user
                if u and not u.is_bot and u.username:
                    members.append(u.username)
        except Exception as e:
            logger.error(f"[UTAG] Failed to fetch members for chat {chat_id} using user {user_id}: {e}")
            await message.reply_text("❌ Guruh a'zolarini o'qib bo'lmadi. Bot guruhda adminligini yoki a'zolar yopiq emasligini tekshiring.")
            return
            
        if not members:
            await message.reply_text("📭 Guruhda tag qilinadigan a'zolar topilmadi.")
            return

        # Load user configuration settings
        from config import user_settings
        settings = user_settings.get(user_id, {})
        
        # Start tagging task
        success, err_msg = await self.utag_service.start_tagging(
            user_id, chat_id, client, user_client, members,
            target_message_content, use_random_messages, settings, text
        )
        
        if success:
            logger.info(f"User {user_id} started tagging task in chat {chat_id}.")
            try:
                await message.reply_text("🚀 **VentoTag boshlandi!**\nTo'xtatish: `.stop` | Pauza: `.pause` | Davom: `.resume`")
            except:
                pass
        else:
            await message.reply_text(f"❌ {err_msg}")


# Initialize UTAG service
utag_service = UtagService(default_settings)
utag_handlers = UtagHandlers(utag_service)


# Register handlers
@Client.on_message(filters.private & filters.command("utag"))
@handle_errors("utag", "user_id", auto_retry=False)
async def utag_start_command(client: Client, message: Message):
    """Handle /utag command"""
    await utag_handlers.handle_utag_start(client, message)


@Client.on_message(filters.private & filters.text)
@handle_errors("utag", "user_id", auto_retry=False)
async def utag_message_handler(client: Client, message: Message):
    """Handle message input for UTAG"""
    await utag_handlers.handle_message_input(client, message)


@Client.on_callback_query(filters.regex("^(menu_utag|utag_start)$"))
@handle_errors("utag", "user_id", auto_retry=False)
async def utag_start_callback(client: Client, callback_query: CallbackQuery):
    """Handle UTAG start"""
    await utag_handlers.handle_utag_start_callback(client, callback_query)


@Client.on_callback_query(filters.regex("^utag_add_command$"))
@handle_errors("utag", "user_id", auto_retry=False)
async def utag_add_command_callback(client: Client, callback_query: CallbackQuery):
    """Handle add command"""
    await utag_handlers.handle_add_command(client, callback_query)


@Client.on_callback_query(filters.regex("^utag_list_commands$"))
@handle_errors("utag", "user_id", auto_retry=False)
async def utag_list_commands_callback(client: Client, callback_query: CallbackQuery):
    """Handle list commands"""
    await utag_handlers.handle_list_commands(client, callback_query)


@Client.on_callback_query(filters.regex("^utag_remove_command$"))
@handle_errors("utag", "user_id", auto_retry=False)
async def utag_remove_command_callback(client: Client, callback_query: CallbackQuery):
    """Handle remove command"""
    await utag_handlers.handle_remove_command(client, callback_query)


@Client.on_callback_query(filters.regex("^utag_remove_(.+)$"))
@handle_errors("utag", "user_id", auto_retry=False)
async def utag_remove_specific_callback(client: Client, callback_query: CallbackQuery):
    """Handle specific command removal"""
    command = callback_query.matches[0].group(1)
    await utag_handlers.handle_command_removal(client, callback_query, command)


@Client.on_callback_query(filters.regex("^utag_cancel$"))
@handle_errors("utag", "user_id", auto_retry=False)
async def utag_cancel_callback(client: Client, callback_query: CallbackQuery):
    """Handle cancel"""
    await utag_handlers.handle_cancel(client, callback_query)


@Client.on_message(filters.text & filters.group)
@handle_errors("utag", "user_id", auto_retry=False)
async def group_utag_message_handler(client: Client, message: Message):
    """Handle Utag commands in group chats"""
    await utag_handlers.handle_group_message(client, message)


@Client.on_callback_query(filters.regex(r"^stop_utag_(\d+)$"))
@handle_errors("utag", "user_id", auto_retry=False)
async def stop_utag_callback(client: Client, callback_query: CallbackQuery):
    """Handle stop tagging from inline button"""
    chat_id = int(callback_query.matches[0].group(1))
    user_id = callback_query.from_user.id
    success = await utag_service.stop_tagging(user_id, chat_id)
    if success:
        await callback_query.answer("🛑 Jarayon to'xtatildi!", show_alert=True)
        try:
            await callback_query.message.edit_text("🛑 Jarayon to'xtatildi!")
        except:
            pass
    else:
        await callback_query.answer("⚠️ Faol jarayon topilmadi", show_alert=True)