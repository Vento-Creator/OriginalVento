"""
Cache system for profile analyzer - photo hash cache and profile result cache
"""
import logging
import time
import hashlib
import json
from typing import Optional, Dict, Any
from pathlib import Path
import asyncio

logger = logging.getLogger(__name__)


class PhotoHashCache:
    """Cache for photo analysis results keyed by image hash
    
    This prevents redundant analysis of identical profile photos.
    """
    
    def __init__(self, cache_dir: str, ttl: int = 604800):
        """Initialize photo hash cache
        
        Args:
            cache_dir: Directory to store cache files
            ttl: Time-to-live for cache entries in seconds (default: 7 days)
        """
        self.cache_dir = Path(cache_dir)
        self.ttl = ttl
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._memory_cache: Dict[str, Dict[str, Any]] = {}
        self._lock = asyncio.Lock()
    
    def _get_cache_path(self, image_hash: str) -> Path:
        """Get file path for a cache entry"""
        return self.cache_dir / f"{image_hash}.json"
    
    def _is_expired(self, entry: Dict[str, Any]) -> bool:
        """Check if cache entry is expired"""
        return time.time() - entry.get("timestamp", 0) > self.ttl
    
    async def get(self, image_hash: str, model_version: str = "v1") -> Optional[Dict[str, Any]]:
        """Get cached photo analysis result
        
        Args:
            image_hash: SHA-256 hash of the image
            model_version: Model version to check compatibility
            
        Returns:
            Cached analysis result or None if not found/expired
        """
        async with self._lock:
            # Check memory cache first
            if image_hash in self._memory_cache:
                entry = self._memory_cache[image_hash]
                if not self._is_expired(entry) and entry.get("model_version") == model_version:
                    return entry["data"]
                else:
                    del self._memory_cache[image_hash]
            
            # Check disk cache
            cache_path = self._get_cache_path(image_hash)
            if cache_path.exists():
                try:
                    with open(cache_path, 'r', encoding='utf-8') as f:
                        entry = json.load(f)
                    
                    if not self._is_expired(entry) and entry.get("model_version") == model_version:
                        # Populate memory cache
                        self._memory_cache[image_hash] = entry
                        return entry["data"]
                    else:
                        # Remove expired cache file
                        cache_path.unlink()
                except Exception as e:
                    logger.warning(f"Failed to read photo cache file: {e}")
            
            return None
    
    async def set(self, image_hash: str, data: Dict[str, Any], model_version: str = "v1"):
        """Cache photo analysis result
        
        Args:
            image_hash: SHA-256 hash of the image
            data: Analysis result to cache
            model_version: Model version for cache invalidation
        """
        async with self._lock:
            entry = {
                "data": data,
                "timestamp": time.time(),
                "model_version": model_version
            }
            
            # Store in memory cache
            self._memory_cache[image_hash] = entry
            
            # Store in disk cache
            cache_path = self._get_cache_path(image_hash)
            try:
                with open(cache_path, 'w', encoding='utf-8') as f:
                    json.dump(entry, f)
            except Exception as e:
                logger.warning(f"Failed to write photo cache file: {e}")
    
    async def clear(self):
        """Clear all cache entries"""
        async with self._lock:
            self._memory_cache.clear()
            for cache_file in self.cache_dir.glob("*.json"):
                try:
                    cache_file.unlink()
                except Exception as e:
                    logger.warning(f"Failed to delete cache file {cache_file}: {e}")


class ProfileResultCache:
    """Cache for complete profile analysis results
    
    This prevents redundant analysis when profile data hasn't changed.
    """
    
    def __init__(self, cache_dir: str, ttl: int = 86400):
        """Initialize profile result cache
        
        Args:
            cache_dir: Directory to store cache files
            ttl: Time-to-live for cache entries in seconds (default: 24 hours)
        """
        self.cache_dir = Path(cache_dir)
        self.ttl = ttl
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._memory_cache: Dict[str, Dict[str, Any]] = {}
        self._lock = asyncio.Lock()
    
    def _compute_profile_hash(self, user_id: int, name: str, username: str, bio: str, photo_hash: str) -> str:
        """Compute hash of profile data for cache key"""
        profile_data = f"{user_id}|{name}|{username}|{bio}|{photo_hash}"
        return hashlib.sha256(profile_data.encode()).hexdigest()
    
    def _get_cache_path(self, profile_hash: str) -> Path:
        """Get file path for a cache entry"""
        return self.cache_dir / f"{profile_hash}.json"
    
    def _is_expired(self, entry: Dict[str, Any]) -> bool:
        """Check if cache entry is expired"""
        return time.time() - entry.get("timestamp", 0) > self.ttl
    
    async def get(self, user_id: int, name: str, username: str, bio: str, photo_hash: str, analyzer_version: str = "v1") -> Optional[Dict[str, Any]]:
        """Get cached profile analysis result
        
        Args:
            user_id: Telegram user ID
            name: First name
            username: Username
            bio: Bio text
            photo_hash: Hash of profile photo
            analyzer_version: Analyzer version for compatibility check
            
        Returns:
            Cached analysis result or None if not found/expired
        """
        profile_hash = self._compute_profile_hash(user_id, name, username, bio, photo_hash)
        
        async with self._lock:
            # Check memory cache first
            if profile_hash in self._memory_cache:
                entry = self._memory_cache[profile_hash]
                if not self._is_expired(entry) and entry.get("analyzer_version") == analyzer_version:
                    return entry["data"]
                else:
                    del self._memory_cache[profile_hash]
            
            # Check disk cache
            cache_path = self._get_cache_path(profile_hash)
            if cache_path.exists():
                try:
                    with open(cache_path, 'r', encoding='utf-8') as f:
                        entry = json.load(f)
                    
                    if not self._is_expired(entry) and entry.get("analyzer_version") == analyzer_version:
                        # Populate memory cache
                        self._memory_cache[profile_hash] = entry
                        return entry["data"]
                    else:
                        # Remove expired cache file
                        cache_path.unlink()
                except Exception as e:
                    logger.warning(f"Failed to read profile cache file: {e}")
            
            return None
    
    async def set(self, user_id: int, name: str, username: str, bio: str, photo_hash: str, data: Dict[str, Any], analyzer_version: str = "v1"):
        """Cache profile analysis result
        
        Args:
            user_id: Telegram user ID
            name: First name
            username: Username
            bio: Bio text
            photo_hash: Hash of profile photo
            data: Analysis result to cache
            analyzer_version: Analyzer version for cache invalidation
        """
        profile_hash = self._compute_profile_hash(user_id, name, username, bio, photo_hash)
        
        async with self._lock:
            entry = {
                "data": data,
                "timestamp": time.time(),
                "analyzer_version": analyzer_version
            }
            
            # Store in memory cache
            self._memory_cache[profile_hash] = entry
            
            # Store in disk cache
            cache_path = self._get_cache_path(profile_hash)
            try:
                with open(cache_path, 'w', encoding='utf-8') as f:
                    json.dump(entry, f)
            except Exception as e:
                logger.warning(f"Failed to write profile cache file: {e}")
    
    async def clear(self):
        """Clear all cache entries"""
        async with self._lock:
            self._memory_cache.clear()
            for cache_file in self.cache_dir.glob("*.json"):
                try:
                    cache_file.unlink()
                except Exception as e:
                    logger.warning(f"Failed to delete cache file {cache_file}: {e}")