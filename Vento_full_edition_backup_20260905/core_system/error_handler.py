"""
Global Error Handling System - Centralized error management for all systems
"""
import asyncio
import logging
import traceback
from typing import Dict, Any, Optional, Callable
from datetime import datetime
from enum import Enum


class ErrorSeverity(Enum):
    """Error severity levels"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ErrorCategory(Enum):
    """Error categories"""
    SESSION = "session"
    AUTHENTICATION = "authentication"
    DATABASE = "database"
    NETWORK = "network"
    RATE_LIMIT = "rate_limit"
    VALIDATION = "validation"
    PERMISSION = "permission"
    SYSTEM = "system"
    UNKNOWN = "unknown"


class SystemError(Exception):
    """Base system error"""
    def __init__(
        self,
        message: str,
        category: ErrorCategory = ErrorCategory.UNKNOWN,
        severity: ErrorSeverity = ErrorSeverity.MEDIUM,
        user_id: Optional[int] = None,
        context: Optional[Dict[str, Any]] = None
    ):
        self.message = message
        self.category = category
        self.severity = severity
        self.user_id = user_id
        self.context = context or {}
        self.timestamp = datetime.now()
        super().__init__(self.message)


class ErrorHandler:
    """Centralized error handler for all systems"""
    
    def __init__(self):
        self.error_log: Dict[str, Dict[str, Any]] = {}  # error_id -> error_data
        self.error_callbacks: Dict[ErrorCategory, list] = {}  # category -> callbacks
        self.user_error_counts: Dict[int, Dict[ErrorCategory, int]] = {}  # user_id -> {category: count}
        self._lock = asyncio.Lock()
        self.logger = logging.getLogger(__name__)
    
    async def handle_error(
        self,
        error: Exception,
        user_id: Optional[int] = None,
        context: Optional[Dict[str, Any]] = None,
        notify_user: bool = True
    ) -> Dict[str, Any]:
        """
        Handle error with logging, categorization, and user notification
        
        Args:
            error: The exception that occurred
            user_id: User ID who experienced the error
            context: Additional context about the error
            notify_user: Whether to notify the user about the error
        
        Returns:
            Error handling result
        """
        # Categorize error
        category = self._categorize_error(error)
        severity = self._determine_severity(error, category)
        
        # Create error ID
        error_id = f"{category.value}_{int(datetime.now().timestamp())}"
        
        # Build error data
        error_data = {
            "error_id": error_id,
            "error_type": type(error).__name__,
            "error_message": str(error),
            "category": category.value,
            "severity": severity.value,
            "user_id": user_id,
            "context": context or {},
            "timestamp": datetime.now().isoformat(),
            "traceback": traceback.format_exc()
        }
        
        # Log error
        await self._log_error(error_data)
        
        # Update user error counts
        if user_id:
            await self._update_user_error_count(user_id, category)
        
        # Store error
        async with self._lock:
            self.error_log[error_id] = error_data
        
        # Trigger category-specific callbacks
        await self._trigger_callbacks(category, error_data)
        
        # Check if user should be blocked
        should_block = await self._should_block_user(user_id, category)
        
        return {
            "error_id": error_id,
            "category": category.value,
            "severity": severity.value,
            "user_message": self._get_user_message(category, severity),
            "should_block": should_block,
            "logged": True
        }
    
    def _categorize_error(self, error: Exception) -> ErrorCategory:
        """Categorize error based on type and message"""
        error_name = type(error).__name__
        error_msg = str(error).lower()
        
        # Session errors
        if any(kw in error_name for kw in ["Session", "AuthKey", "Login"]):
            return ErrorCategory.SESSION
        
        # Authentication errors
        if any(kw in error_name for kw in ["Auth", "Password", "Code"]):
            return ErrorCategory.AUTHENTICATION
        
        # Database errors
        if any(kw in error_name for kw in ["Database", "DB", "SQL"]) or "database" in error_msg:
            return ErrorCategory.DATABASE
        
        # Network errors
        if any(kw in error_name for kw in ["Connection", "Timeout", "Network"]) or "timeout" in error_msg:
            return ErrorCategory.NETWORK
        
        # Rate limit errors
        if "FloodWait" in error_name or "rate" in error_msg or "limit" in error_msg:
            return ErrorCategory.RATE_LIMIT
        
        # Validation errors
        if "Validation" in error_name or "invalid" in error_msg:
            return ErrorCategory.VALIDATION
        
        # Permission errors
        if any(kw in error_name for kw in ["Permission", "Forbidden", "Access"]) or "permission" in error_msg:
            return ErrorCategory.PERMISSION
        
        return ErrorCategory.UNKNOWN
    
    def _determine_severity(self, error: Exception, category: ErrorCategory) -> ErrorSeverity:
        """Determine error severity based on category and error type"""
        error_name = type(error).__name__
        
        # Critical errors
        if category in [ErrorCategory.SESSION, ErrorCategory.DATABASE]:
            return ErrorSeverity.CRITICAL
        
        # High severity
        if category in [ErrorCategory.AUTHENTICATION, ErrorCategory.PERMISSION]:
            return ErrorSeverity.HIGH
        
        # Medium severity
        if category in [ErrorCategory.RATE_LIMIT, ErrorCategory.NETWORK]:
            return ErrorSeverity.MEDIUM
        
        # Low severity
        if category == ErrorCategory.VALIDATION:
            return ErrorSeverity.LOW
        
        return ErrorSeverity.MEDIUM
    
    async def _log_error(self, error_data: Dict[str, Any]):
        """Log error to appropriate channels"""
        severity = error_data["severity"]
        
        if severity == ErrorSeverity.CRITICAL.value:
            self.logger.critical(f"CRITICAL ERROR: {error_data}")
        elif severity == ErrorSeverity.HIGH.value:
            self.logger.error(f"HIGH ERROR: {error_data}")
        elif severity == ErrorSeverity.MEDIUM.value:
            self.logger.warning(f"MEDIUM ERROR: {error_data}")
        else:
            self.logger.info(f"LOW ERROR: {error_data}")
    
    async def _update_user_error_count(self, user_id: int, category: ErrorCategory):
        """Update user's error count for category"""
        async with self._lock:
            if user_id not in self.user_error_counts:
                self.user_error_counts[user_id] = {}
            
            self.user_error_counts[user_id][category] = \
                self.user_error_counts[user_id].get(category, 0) + 1
    
    async def _trigger_callbacks(self, category: ErrorCategory, error_data: Dict[str, Any]):
        """Trigger registered callbacks for error category"""
        callbacks = self.error_callbacks.get(category, [])
        
        for callback in callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(error_data)
                else:
                    callback(error_data)
            except Exception as e:
                self.logger.error(f"Error in callback: {e}")
    
    async def _should_block_user(self, user_id: Optional[int], category: ErrorCategory) -> bool:
        """Check if user should be blocked based on error history"""
        if not user_id:
            return False
        
        async with self._lock:
            user_counts = self.user_error_counts.get(user_id, {})
            
            # Block if too many critical errors
            critical_count = user_counts.get(ErrorCategory.CRITICAL, 0)
            if critical_count >= 3:
                return True
            
            # Block if too many authentication errors
            auth_count = user_counts.get(ErrorCategory.AUTHENTICATION, 0)
            if auth_count >= 5:
                return True
            
            return False
    
    def _get_user_message(self, category: ErrorCategory, severity: ErrorSeverity) -> str:
        """Get user-friendly error message"""
        messages = {
            ErrorCategory.SESSION: "🔑 Sessiya xatosi. Iltimos, qaytadan login qiling.",
            ErrorCategory.AUTHENTICATION: "🔐 Autentifikatsiya xatosi. Ma'lumotlaringizni tekshiring.",
            ErrorCategory.DATABASE: "🗄 Ma'lumotlar bazasi xatosi. Iltimos, keyinroq urinib ko'ring.",
            ErrorCategory.NETWORK: "🌐 Tarmoq xatosi. Internet ulanishingizni tekshiring.",
            ErrorCategory.RATE_LIMIT: "⏳ Limitga yetdingiz. Iltimos, kutib turing.",
            ErrorCategory.VALIDATION: "❌ Noto'g'ri ma'lumot kiritdingiz.",
            ErrorCategory.PERMISSION: "⛔ Ruxsat yo'q. Admin bilan bog'laning.",
            ErrorCategory.UNKNOWN: "❌ Xatolik yuz berdi. Iltimos, qaytadan urinib ko'ring."
        }
        
        base_message = messages.get(category, messages[ErrorCategory.UNKNOWN])
        
        if severity == ErrorSeverity.CRITICAL:
            return f"🚨 {base_message}\n\nBu jiddiy xatolik. Admin bilan bog'laning."
        
        return base_message
    
    def register_callback(self, category: ErrorCategory, callback: Callable):
        """Register callback for error category"""
        if category not in self.error_callbacks:
            self.error_callbacks[category] = []
        
        self.error_callbacks[category].append(callback)
    
    async def get_user_errors(self, user_id: int) -> Dict[str, int]:
        """Get user's error counts by category"""
        async with self._lock:
            return self.user_error_counts.get(user_id, {}).copy()
    
    async def clear_user_errors(self, user_id: int):
        """Clear user's error history"""
        async with self._lock:
            if user_id in self.user_error_counts:
                del self.user_error_counts[user_id]
    
    async def get_error_log(self, limit: int = 100) -> list:
        """Get recent error log"""
        async with self._lock:
            errors = list(self.error_log.values())
            errors.sort(key=lambda x: x["timestamp"], reverse=True)
            return errors[:limit]


# Global error handler instance
error_handler = ErrorHandler()


# Convenience decorators
def handle_errors(category: ErrorCategory = ErrorCategory.UNKNOWN, notify_user: bool = True):
    """Decorator to automatically handle errors in functions"""
    def decorator(func):
        async def wrapper(*args, **kwargs):
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                # Extract user_id from kwargs if available
                user_id = kwargs.get('user_id') or (args[1] if len(args) > 1 else None)
                context = {
                    "function": func.__name__,
                    "args": str(args),
                    "kwargs": str(kwargs)
                }
                
                result = await error_handler.handle_error(
                    error=e,
                    user_id=user_id,
                    context=context,
                    notify_user=notify_user
                )
                
                # Re-raise if critical
                if result["severity"] == ErrorSeverity.CRITICAL.value:
                    raise SystemError(result["user_message"]) from e
                
                # Return error result
                return {"error": result}
        
        return wrapper
    return decorator