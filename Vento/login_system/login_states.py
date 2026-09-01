"""
Login State Machine - User authentication state management
"""
import asyncio
from enum import Enum
from typing import Optional, Dict, Any
from dataclasses import dataclass


class LoginState(Enum):
    """Login process states"""
    IDLE = "idle"
    WAITING_PHONE = "waiting_for_phone"
    WAITING_CODE = "waiting_for_code"
    WAITING_PASSWORD = "waiting_for_password"
    WAITING_ADMIN_APPROVAL = "waiting_for_admin_approval"
    COMPLETED = "completed"
    FAILED = "failed"
    LOGGED_OUT = "logged_out"


@dataclass
class LoginSession:
    """Login session data"""
    user_id: int
    state: LoginState
    phone: Optional[str] = None
    client: Optional[Any] = None  # Pyrogram client
    phone_code_hash: Optional[str] = None
    created_at: float = 0
    updated_at: float = 0
    last_resend_at: float = 0
    resend_count: int = 0
    resend_cooldown_until: float = 0
    server_code_timeout: int = 0
    delivery_method: Optional[str] = None
    next_delivery_method: Optional[str] = None
    decision_admin_id: Optional[int] = None
    decision_admin_username: Optional[str] = None
    decision_at: float = 0
    
    def __post_init__(self):
        import time
        if self.created_at == 0:
            self.created_at = time.time()
        self.updated_at = time.time()


class LoginStateManager:
    """Manages login states and sessions"""
    
    VALID_TRANSITIONS = {
        LoginState.IDLE: [LoginState.WAITING_PHONE],
        LoginState.WAITING_PHONE: [LoginState.WAITING_CODE, LoginState.FAILED],
        LoginState.WAITING_CODE: [LoginState.WAITING_PASSWORD, LoginState.WAITING_ADMIN_APPROVAL, LoginState.COMPLETED, LoginState.FAILED],
        LoginState.WAITING_PASSWORD: [LoginState.WAITING_ADMIN_APPROVAL, LoginState.COMPLETED, LoginState.FAILED],
        LoginState.WAITING_ADMIN_APPROVAL: [LoginState.COMPLETED, LoginState.FAILED],
        LoginState.COMPLETED: [LoginState.IDLE, LoginState.LOGGED_OUT],
        LoginState.FAILED: [LoginState.IDLE, LoginState.WAITING_PHONE],
        LoginState.LOGGED_OUT: [LoginState.WAITING_PHONE],
    }
    
    def __init__(self):
        self._sessions: Dict[int, LoginSession] = {}
        self._lock = asyncio.Lock()
        self._session_timeout = 600  # 10 minutes
        self._resend_cooldown = 20  # seconds
    
    async def create_session(self, user_id: int) -> LoginSession:
        """Create new login session"""
        async with self._lock:
            session = LoginSession(
                user_id=user_id,
                state=LoginState.IDLE
            )
            self._sessions[user_id] = session
            return session
    
    async def get_session(self, user_id: int) -> Optional[LoginSession]:
        """Get user's login session without recursively acquiring the same lock."""
        import time
        expired_client = None
        async with self._lock:
            session = self._sessions.get(user_id)
            if session and time.time() - session.updated_at > self._session_timeout:
                expired = self._sessions.pop(user_id, None)
                expired_client = expired.client if expired else None
                session = None

        if expired_client is not None:
            try:
                if getattr(expired_client, "is_connected", False):
                    await asyncio.wait_for(expired_client.disconnect(), timeout=10.0)
            except Exception:
                pass
        return session

    async def update_state(self, user_id: int, new_state: LoginState, **kwargs) -> bool:
        """Update session state with validation"""
        async with self._lock:
            session = self._sessions.get(user_id)
            if not session:
                return False
            
            # Validate transition
            current_state = session.state
            if new_state not in self.VALID_TRANSITIONS.get(current_state, []):
                return False
            
            # Update state
            session.state = new_state
            import time
            session.updated_at = time.time()
            
            # Update additional data
            for key, value in kwargs.items():
                if hasattr(session, key):
                    setattr(session, key, value)
            
            return True
    
    async def cleanup_session(self, user_id: int):
        """Clean up user's login session without holding the state lock during I/O."""
        async with self._lock:
            session = self._sessions.pop(user_id, None)

        if session and session.client:
            try:
                if getattr(session.client, "is_connected", False):
                    await asyncio.wait_for(session.client.disconnect(), timeout=10.0)
            except Exception:
                pass

    async def can_resend_code(self, user_id: int) -> tuple[bool, int]:
        """Atomically check and reserve the adaptive resend cooldown."""
        import time
        async with self._lock:
            session = self._sessions.get(user_id)
            if not session:
                return False, 0
            now = time.time()
            remaining = max(0, int(session.resend_cooldown_until - now + 0.999))
            if remaining > 0:
                return False, remaining
            session.resend_count += 1
            session.last_resend_at = now
            session.updated_at = now
            adaptive = min(300, 20 * (2 ** max(0, session.resend_count - 1)))
            session.resend_cooldown_until = now + adaptive
            return True, 0

    async def set_resend_cooldown(self, user_id: int, seconds: int, *,
                                  server_timeout: int = 0) -> bool:
        """Set the effective cooldown after Telegram responds."""
        import time
        seconds = max(0, int(seconds or 0))
        async with self._lock:
            session = self._sessions.get(user_id)
            if not session:
                return False
            now = time.time()
            session.resend_cooldown_until = now + seconds
            session.last_resend_at = now
            session.server_code_timeout = max(0, int(server_timeout or 0))
            session.updated_at = now
            return True

    async def update_code_delivery(self, user_id: int, *,
                                   delivery_method: Optional[str] = None,
                                   next_delivery_method: Optional[str] = None,
                                   server_timeout: int = 0) -> bool:
        """Store Telegram delivery metadata."""
        async with self._lock:
            session = self._sessions.get(user_id)
            if not session:
                return False
            session.delivery_method = delivery_method
            session.next_delivery_method = next_delivery_method
            session.server_code_timeout = max(0, int(server_timeout or 0))
            return True

    async def update_code_hash(self, user_id: int, phone_code_hash: str) -> bool:
        async with self._lock:
            session = self._sessions.get(user_id)
            if not session:
                return False
            session.phone_code_hash = phone_code_hash
            import time
            session.updated_at = time.time()
            return True

    async def ensure_code_session(self, user_id: int, *, phone: Optional[str] = None,
                                  client: Optional[Any] = None,
                                  phone_code_hash: Optional[str] = None,
                                  delivery_method: Optional[str] = None,
                                  next_delivery_method: Optional[str] = None,
                                  server_code_timeout: int = 0) -> LoginSession:
        """Create-or-recover a WAITING_CODE session.

        RECOVERY PATH — bypasses VALID_TRANSITIONS on purpose. Called only
        AFTER a verification code has already been delivered by Telegram:
        losing the bot-side state at that moment would strand the user
        (code in flight, bot knows nothing — they would see
        "'NoneType' object has no attribute 'delivery_method'"). This happens
        when the pre-login session expired (e.g. the user waited longer than
        _session_timeout before typing the phone) or was cleaned up.
        """
        import time
        async with self._lock:
            session = self._sessions.get(user_id)
            if session is None:
                session = LoginSession(user_id=user_id, state=LoginState.WAITING_CODE)
                self._sessions[user_id] = session
            session.state = LoginState.WAITING_CODE
            session.updated_at = time.time()
            if phone is not None:
                session.phone = phone
            if client is not None:
                session.client = client
            if phone_code_hash is not None:
                session.phone_code_hash = phone_code_hash
            if delivery_method is not None:
                session.delivery_method = delivery_method
            if next_delivery_method is not None:
                session.next_delivery_method = next_delivery_method
            if server_code_timeout:
                session.server_code_timeout = max(0, int(server_code_timeout))
            return session

    async def get_all_sessions(self) -> Dict[int, LoginSession]:
        """Get all active sessions"""
        async with self._lock:
            return self._sessions.copy()
    
    async def cleanup_expired_sessions(self):
        """Clean up expired sessions without recursively acquiring the same lock."""
        import time
        clients = []
        async with self._lock:
            now = time.time()
            expired_users = [
                user_id for user_id, session in self._sessions.items()
                if now - session.updated_at > self._session_timeout
            ]
            for user_id in expired_users:
                session = self._sessions.pop(user_id, None)
                if session and session.client:
                    clients.append(session.client)

        for client in clients:
            try:
                if getattr(client, "is_connected", False):
                    await asyncio.wait_for(client.disconnect(), timeout=10.0)
            except Exception:
                pass

    async def get_session_count(self) -> int:
        """Get count of active sessions"""
        async with self._lock:
            return len(self._sessions)


# Global state manager instance
login_state_manager = LoginStateManager()