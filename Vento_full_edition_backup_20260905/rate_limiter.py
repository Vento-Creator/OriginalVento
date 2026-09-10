import time
from collections import defaultdict

RATE_LIMITS = {
    "default": {"max_requests": 30, "window": 60},  # 30 requests per minute
    "admin": {"max_requests": 60, "window": 60},     # 60 requests per minute for admins
    "broadcast": {"max_requests": 1, "window": 300},  # 1 broadcast per 5 minutes
    "ban": {"max_requests": 10, "window": 60},        # 10 bans per minute
    "start": {"max_requests": 3, "window": 10},      # 3 /start commands per 10 seconds
}

rate_limit_store = defaultdict(dict)

def check_rate_limit(user_id: int, action_type: str = "default"):
    """
    Check if user exceeded rate limit
    
    Args:
        user_id: User ID to check
        action_type: Type of action (default, admin, broadcast, ban, etc.)
    
    Returns:
        (allowed: bool, remaining_requests: int)
    """
    limit_config = RATE_LIMITS.get(action_type, RATE_LIMITS["default"])
    max_requests = limit_config["max_requests"]
    window = limit_config["window"]
    
    current_time = time.time()
    user_data = rate_limit_store[user_id]
    
    action_data = user_data.get(action_type)
    
    if action_data is None:
        user_data[action_type] = {"count": 1, "window_start": current_time}
        return True, max_requests - 1
    
    if current_time - action_data["window_start"] > window:
        user_data[action_type] = {"count": 1, "window_start": current_time}
        return True, max_requests - 1
    
    if action_data["count"] >= max_requests:
        return False, 0
    
    action_data["count"] += 1
    remaining = max_requests - action_data["count"]
    return True, remaining

def reset_rate_limit(user_id: int, action_type: str = None):
    """
    Reset rate limit for a user
    
    Args:
        user_id: User ID to reset
        action_type: Specific action type to reset (None for all)
    """
    if action_type is None:
        rate_limit_store[user_id].clear()
    elif action_type in rate_limit_store[user_id]:
        del rate_limit_store[user_id][action_type]

def get_rate_limit_status(user_id: int, action_type: str = "default") -> dict:
    """
    Get current rate limit status for a user
    
    Args:
        user_id: User ID to check
        action_type: Type of action
    
    Returns:
        Dict with count, window_start, remaining, reset_time
    """
    limit_config = RATE_LIMITS.get(action_type, RATE_LIMITS["default"])
    max_requests = limit_config["max_requests"]
    window = limit_config["window"]
    
    user_data = rate_limit_store[user_id]
    action_data = user_data.get(action_type)
    
    if action_data is None:
        return {
            "count": 0,
            "max_requests": max_requests,
            "window": window,
            "remaining": max_requests,
            "reset_time": 0
        }
    
    current_time = time.time()
    if current_time - action_data["window_start"] > window:
        return {
            "count": 0,
            "max_requests": max_requests,
            "window": window,
            "remaining": max_requests,
            "reset_time": 0
        }
    
    remaining = max(0, max_requests - action_data["count"])
    reset_time = action_data["window_start"] + window
    
    return {
        "count": action_data["count"],
        "max_requests": max_requests,
        "window": window,
        "remaining": remaining,
        "reset_time": reset_time
    }
