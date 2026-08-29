"""
Global Error Handling System - Centralized error management for all modular systems
Provides consistent error handling, logging, and recovery mechanisms
"""
import asyncio
import logging
import traceback
from typing import Dict, Any, Optional, Callable, List
from datetime import datetime
from enum import Enum

# Import Pyrogram control flow exceptions to re-raise them
from pyrogram import ContinuePropagation, StopPropagation
from pyrogram.errors import SessionPasswordNeeded

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class ErrorSeverity(Enum):
    """Error severity levels"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ErrorCategory(Enum):
    """Error categories for classification"""
    NETWORK = "network"
    DATABASE = "database"
    AUTHENTICATION = "authentication"
    VALIDATION = "validation"
    RATE_LIMIT = "rate_limit"
    SYSTEM = "system"
    USER = "user"
    UNKNOWN = "unknown"


class SystemError:
    """Standardized error representation"""
    
    def __init__(
        self,
        system: str,
        error_type: str,
        message: str,
        severity: ErrorSeverity = ErrorSeverity.MEDIUM,
        category: ErrorCategory = ErrorCategory.UNKNOWN,
        user_id: Optional[int] = None,
        context: Optional[Dict[str, Any]] = None,
        recoverable: bool = True
    ):
        self.system = system
        self.error_type = error_type
        self.message = message
        self.severity = severity
        self.category = category
        self.user_id = user_id
        self.context = context or {}
        self.recoverable = recoverable
        self.timestamp = datetime.now()
        self.traceback = traceback.format_exc()
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert error to dictionary"""
        return {
            "system": self.system,
            "error_type": self.error_type,
            "message": self.message,
            "severity": self.severity.value,
            "category": self.category.value,
            "user_id": self.user_id,
            "context": self.context,
            "recoverable": self.recoverable,
            "timestamp": self.timestamp.isoformat(),
            "traceback": self.traceback
        }


class ErrorClassifier:
    """Classifies errors into categories and severity levels"""
    
    @staticmethod
    def classify_error(error: Exception, system: str = "unknown") -> SystemError:
        """Classify an exception into a SystemError"""
        # Skip Pyrogram control flow exceptions and authentication exceptions
        if isinstance(error, (ContinuePropagation, StopPropagation, SessionPasswordNeeded)):
            raise error
        
        error_name = type(error).__name__
        error_msg = str(error).lower()
        
        # Determine category
        category = ErrorCategory.UNKNOWN
        severity = ErrorSeverity.MEDIUM
        
        # Network errors
        if any(kw in error_name for kw in ["Timeout", "Connection", "Network"]):
            category = ErrorCategory.NETWORK
            severity = ErrorSeverity.HIGH
        
        # Database errors
        elif any(kw in error_name for kw in ["Database", "SQL", "DB"]):
            category = ErrorCategory.DATABASE
            severity = ErrorSeverity.HIGH
        
        # Authentication errors
        elif any(kw in error_name for kw in ["Auth", "Login", "Session", "Phone"]):
            category = ErrorCategory.AUTHENTICATION
            severity = ErrorSeverity.MEDIUM
        
        # Validation errors
        elif any(kw in error_name for kw in ["Validation", "Invalid", "Value"]):
            category = ErrorCategory.VALIDATION
            severity = ErrorSeverity.LOW
        
        # Rate limit errors
        elif "flood" in error_msg or "limit" in error_msg or "rate" in error_msg:
            category = ErrorCategory.RATE_LIMIT
            severity = ErrorSeverity.MEDIUM
        
        # User errors
        elif any(kw in error_name for kw in ["Blocked", "Privacy", "Forbidden"]):
            category = ErrorCategory.USER
            severity = ErrorSeverity.LOW
        
        # System errors
        elif any(kw in error_name for kw in ["System", "Runtime", "Internal"]):
            category = ErrorCategory.SYSTEM
            severity = ErrorSeverity.CRITICAL
        
        return SystemError(
            system=system,
            error_type=error_name,
            message=str(error),
            severity=severity,
            category=category,
            recoverable=category != ErrorCategory.SYSTEM
        )


class ErrorRecoveryStrategy:
    """Error recovery strategies"""
    
    @staticmethod
    async def retry_operation(
        operation: Callable,
        max_retries: int = 3,
        delay: float = 1.0,
        backoff: float = 2.0
    ) -> Any:
        """Retry an operation with exponential backoff"""
        last_error = None
        
        for attempt in range(max_retries):
            try:
                return await operation()
            except Exception as e:
                last_error = e
                if attempt < max_retries - 1:
                    await asyncio.sleep(delay * (backoff ** attempt))
                else:
                    raise
        
        raise last_error
    
    @staticmethod
    async def fallback_operation(
        primary: Callable,
        fallback: Callable,
        error_types: List[type] = None
    ) -> Any:
        """Try primary operation, fallback to alternative on failure"""
        error_types = error_types or [Exception]
        
        try:
            return await primary()
        except tuple(error_types) as e:
            logger.warning(f"Primary operation failed: {e}, trying fallback")
            return await fallback()


class GlobalErrorHandler:
    """Central error handler for all systems"""
    
    def __init__(self):
        self.error_log: List[SystemError] = []
        self.error_callbacks: Dict[str, List[Callable]] = {}
        self._lock = asyncio.Lock()
    
    async def handle_error(
        self,
        error: Exception,
        system: str,
        user_id: Optional[int] = None,
        context: Optional[Dict[str, Any]] = None,
        auto_retry: bool = False
    ) -> SystemError:
        """Handle an error with classification, logging, and optional recovery"""
        # Classify error
        system_error = ErrorClassifier.classify_error(error, system)
        system_error.user_id = user_id
        system_error.context.update(context or {})
        
        # Log error
        await self._log_error(system_error)
        
        # Store in memory
        async with self._lock:
            self.error_log.append(system_error)
            # Keep only last 100 errors
            if len(self.error_log) > 100:
                self.error_log = self.error_log[-100:]
        
        # Log to database
        await self._log_to_database(system_error)
        
        # Trigger callbacks
        await self._trigger_callbacks(system_error)
        
        # Auto-retry for recoverable errors
        if auto_retry and system_error.recoverable:
            logger.info(f"Auto-retry enabled for recoverable error: {system_error.error_type}")
        
        return system_error
    
    async def _log_error(self, error: SystemError):
        """Log error to console/file"""
        log_method = logger.error if error.severity == ErrorSeverity.CRITICAL else \
                     logger.warning if error.severity == ErrorSeverity.HIGH else \
                     logger.info
        
        log_method(
            f"[{error.system}] {error.error_type}: {error.message} "
            f"(Severity: {error.severity.value}, Category: {error.category.value})"
        )
    
    async def _log_to_database(self, error: SystemError):
        """Log error to database for monitoring"""
        try:
            from database_adapter import GlobalErrorLogger
            await GlobalErrorLogger.log_error(
                system=error.system,
                user_id=error.user_id or 0,
                error_type=error.error_type,
                error_message=error.message,
                context=error.context
            )
        except Exception as e:
            logger.error(f"Failed to log error to database: {e}")
    
    async def _trigger_callbacks(self, error: SystemError):
        """Trigger registered error callbacks"""
        callbacks = self.error_callbacks.get(error.system, [])
        for callback in callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(error)
                else:
                    callback(error)
            except Exception as e:
                logger.error(f"Error callback failed: {e}")
    
    def register_callback(self, system: str, callback: Callable):
        """Register error callback for a system"""
        if system not in self.error_callbacks:
            self.error_callbacks[system] = []
        self.error_callbacks[system].append(callback)
    
    def get_recent_errors(
        self,
        system: Optional[str] = None,
        severity: Optional[ErrorSeverity] = None,
        limit: int = 10
    ) -> List[SystemError]:
        """Get recent errors with optional filtering"""
        filtered = self.error_log
        
        if system:
            filtered = [e for e in filtered if e.system == system]
        
        if severity:
            filtered = [e for e in filtered if e.severity == severity]
        
        return filtered[-limit:]
    
    async def get_error_statistics(self) -> Dict[str, Any]:
        """Get error statistics"""
        async with self._lock:
            total_errors = len(self.error_log)
            
            if total_errors == 0:
                return {"total": 0}
            
            by_system = {}
            by_severity = {}
            by_category = {}
            
            for error in self.error_log:
                # By system
                if error.system not in by_system:
                    by_system[error.system] = 0
                by_system[error.system] += 1
                
                # By severity
                severity_key = error.severity.value
                if severity_key not in by_severity:
                    by_severity[severity_key] = 0
                by_severity[severity_key] += 1
                
                # By category
                category_key = error.category.value
                if category_key not in by_category:
                    by_category[category_key] = 0
                by_category[category_key] += 1
            
            return {
                "total": total_errors,
                "by_system": by_system,
                "by_severity": by_severity,
                "by_category": by_category
            }


# Global error handler instance
global_error_handler = GlobalErrorHandler()


# Decorator for automatic error handling
def handle_errors(
    system: str,
    user_id_param: str = "user_id",
    auto_retry: bool = False,
    max_retries: int = 3
):
    """Decorator for automatic error handling in async functions"""
    def decorator(func):
        async def wrapper(*args, **kwargs):
            # Extract user_id if available
            user_id = None
            if user_id_param in kwargs:
                user_id = kwargs[user_id_param]
            else:
                # Try to extract from args (Message or CallbackQuery)
                for arg in args:
                    if hasattr(arg, 'from_user') and hasattr(arg.from_user, 'id'):
                        user_id = arg.from_user.id
                        break
            
            try:
                return await func(*args, **kwargs)
            except (ContinuePropagation, StopPropagation, SessionPasswordNeeded):
                # Re-raise Pyrogram control flow and authentication exceptions immediately
                raise
            except Exception as e:
                # Handle error
                system_error = await global_error_handler.handle_error(
                    error=e,
                    system=system,
                    user_id=user_id,
                    context={"function": func.__name__},
                    auto_retry=auto_retry
                )
                
                # Re-raise if not recoverable
                if not system_error.recoverable:
                    raise
                
                # Return error info for recoverable errors
                return {
                    "success": False,
                    "error": system_error.to_dict()
                }
        
        return wrapper
    return decorator


# Context manager for error handling
class ErrorContext:
    """Context manager for error handling within a block"""
    
    def __init__(self, system: str, user_id: Optional[int] = None):
        self.system = system
        self.user_id = user_id
        self.errors: List[SystemError] = []
    
    async def __aenter__(self):
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None:
            # Re-raise Pyrogram control flow and authentication exceptions immediately
            if exc_type in (ContinuePropagation, StopPropagation, SessionPasswordNeeded):
                return False
            
            error = await global_error_handler.handle_error(
                error=exc_val,
                system=self.system,
                user_id=self.user_id
            )
            self.errors.append(error)
            # Don't suppress exceptions
            return False


# Utility functions
async def safe_execute(
    operation: Callable,
    system: str,
    user_id: Optional[int] = None,
    fallback_value: Any = None
) -> Any:
    """Safely execute an operation with error handling"""
    try:
        return await operation()
    except (ContinuePropagation, StopPropagation, SessionPasswordNeeded):
        # Re-raise Pyrogram control flow and authentication exceptions immediately
        raise
    except Exception as e:
        await global_error_handler.handle_error(
            error=e,
            system=system,
            user_id=user_id
        )
        return fallback_value


async def log_system_event(system: str, user_id: int, event_type: str, details: str):
    """Log a system event"""
    try:
        from database_adapter import GlobalErrorLogger
        await GlobalErrorLogger.log_system_event(system, user_id, event_type, details)
    except Exception as e:
        logger.error(f"Failed to log system event: {e}")
