"""
Service Initializer - Sets up and integrates all modular systems
"""
import asyncio
import logging

logger = logging.getLogger(__name__)

# Global service instances
_massdm_service = None
_login_service = None  
_utag_service = None
_initialized = False

async def initialize_services():
    """Initialize all modular services"""
    global _massdm_service, _login_service, _utag_service, _initialized
    
    if _initialized:
        return True
    
    try:
        # Initialize MassDM service
        from massdm_system import massdm_service
        _massdm_service = massdm_service
        logger.info("MassDM service initialized")
        
        # Initialize Login service
        from login_system import login_service
        _login_service = login_service
        logger.info("Login service initialized")
        
        # Initialize UTAG service
        from utag_system import utag_service
        await utag_service.initialize()
        _utag_service = utag_service
        logger.info("UTAG service initialized")
        
        # Integrate with queue_manager
        from queue_manager import set_massdm_service, set_utag_service, set_login_service, sync_active_tasks_from_services
        set_massdm_service(_massdm_service)
        set_utag_service(_utag_service)
        set_login_service(_login_service)
        await sync_active_tasks_from_services()
        logger.info("Queue manager integration completed")
        
        _initialized = True
        return True
        
    except Exception as e:
        logger.error(f"Service initialization failed: {e}")
        return False

def get_massdm_service():
    """Get MassDM service instance"""
    return _massdm_service

def get_login_service():
    """Get Login service instance"""
    return _login_service

def get_utag_service():
    """Get UTAG service instance"""
    return _utag_service

def is_initialized():
    """Check if services are initialized"""
    return _initialized