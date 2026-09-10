import asyncio
import logging
from typing import Coroutine, Any

logger = logging.getLogger(__name__)


def schedule_guarded(name: str, coro: Coroutine[Any, Any, Any]) -> asyncio.Task:
    """Background task yurituvchisi va uning xatolarini ushlab turuvchi supervisor."""
    async def _runner():
        try:
            await coro
        except asyncio.CancelledError:
            logger.info(f"Task '{name}' bekor qilindi.")
        except Exception as e:
            logger.exception(f"Task '{name}' da kutilmagan xatolik: {e}")

    return asyncio.create_task(_runner(), name=name)
