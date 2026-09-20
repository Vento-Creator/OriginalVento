"""
Configuration for the profile analyzer system
"""
import os
from typing import Dict, Any, List
import logging

logger = logging.getLogger(__name__)


class ProfileAnalyzerConfig:
    """Configuration for profile analyzer system
    
    All settings are configurable via environment variables or direct configuration.
    """
    
    # Global settings
    enabled: bool = True
    minimum_score: int = 3
    
    # Individual analyzer settings
    analyzers: Dict[str, bool] = {
        "name": True,
        "username": True,
        "bio": True,
        "photo": True,
        "language": False  # Future analyzer
    }
    
    # Name analyzer configuration
    name_positive_labels: List[str] = None
    name_case_sensitive: bool = False
    
    # Username analyzer configuration
    username_keywords: List[str] = None
    username_patterns: List[str] = None
    
    # Bio analyzer configuration
    bio_keywords: List[str] = None
    bio_patterns: List[str] = None
    bio_ml_enabled: bool = False
    bio_model_path: str = None
    
    # Photo analyzer configuration
    photo_enabled: bool = True
    photo_model_path: str = None
    photo_model_version: str = "v1"
    photo_max_resolution: int = 160  # 160x160 for memory efficiency
    photo_cache_enabled: bool = True
    photo_max_memory_safe_mode: bool = True
    
    # Cache configuration
    profile_cache_enabled: bool = True
    profile_cache_ttl: int = 86400  # 24 hours in seconds
    photo_cache_ttl: int = 604800  # 7 days in seconds
    
    # Concurrency settings
    photo_inference_concurrency: int = 1  # Bounded for memory safety
    
    @classmethod
    def from_env(cls) -> 'ProfileAnalyzerConfig':
        """Load configuration from environment variables"""
        config = cls()
        
        # Global settings
        config.enabled = os.getenv("PROFILE_SCORING_ENABLED", "true").lower() == "true"
        config.minimum_score = int(os.getenv("PROFILE_SCORING_MINIMUM_SCORE", "3"))
        
        # Individual analyzers
        config.analyzers["name"] = os.getenv("PROFILE_ANALYZER_NAME", "true").lower() == "true"
        config.analyzers["username"] = os.getenv("PROFILE_ANALYZER_USERNAME", "true").lower() == "true"
        config.analyzers["bio"] = os.getenv("PROFILE_ANALYZER_BIO", "true").lower() == "true"
        config.analyzers["photo"] = os.getenv("PROFILE_ANALYZER_PHOTO", "true").lower() == "true"
        
        # Name analyzer
        config.name_case_sensitive = os.getenv("PROFILE_NAME_CASE_SENSITIVE", "false").lower() == "true"
        
        # Username analyzer (keywords from env if provided)
        username_keywords_env = os.getenv("PROFILE_USERNAME_KEYWORDS", "")
        if username_keywords_env:
            config.username_keywords = [k.strip() for k in username_keywords_env.split(",")]
        
        # Bio analyzer
        config.bio_ml_enabled = os.getenv("PROFILE_BIO_ML_ENABLED", "false").lower() == "true"
        config.bio_model_path = os.getenv("PROFILE_BIO_MODEL_PATH", "")
        
        # Photo analyzer
        config.photo_enabled = os.getenv("PROFILE_PHOTO_ENABLED", "true").lower() == "true"
        config.photo_model_path = os.getenv("PROFILE_PHOTO_MODEL_PATH", "")
        config.photo_max_resolution = int(os.getenv("PROFILE_PHOTO_MAX_RESOLUTION", "160"))
        config.photo_max_memory_safe_mode = os.getenv("PROFILE_PHOTO_MAX_MEMORY_SAFE_MODE", "true").lower() == "true"
        
        # Cache settings
        config.profile_cache_enabled = os.getenv("PROFILE_CACHE_ENABLED", "true").lower() == "true"
        config.profile_cache_ttl = int(os.getenv("PROFILE_CACHE_TTL", "86400"))
        config.photo_cache_ttl = int(os.getenv("PROFILE_PHOTO_CACHE_TTL", "604800"))
        
        # Concurrency
        config.photo_inference_concurrency = int(os.getenv("PROFILE_PHOTO_INFERENCE_CONCURRENCY", "1"))
        
        logger.info(f"Profile analyzer config loaded: enabled={config.enabled}, min_score={config.minimum_score}")
        return config
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert configuration to dictionary"""
        return {
            "enabled": self.enabled,
            "minimum_score": self.minimum_score,
            "analyzers": self.analyzers.copy(),
            "name_positive_labels": self.name_positive_labels,
            "name_case_sensitive": self.name_case_sensitive,
            "username_keywords": self.username_keywords,
            "username_patterns": self.username_patterns,
            "bio_keywords": self.bio_keywords,
            "bio_patterns": self.bio_patterns,
            "bio_ml_enabled": self.bio_ml_enabled,
            "bio_model_path": self.bio_model_path,
            "photo_enabled": self.photo_enabled,
            "photo_model_path": self.photo_model_path,
            "photo_model_version": self.photo_model_version,
            "photo_max_resolution": self.photo_max_resolution,
            "photo_cache_enabled": self.photo_cache_enabled,
            "photo_max_memory_safe_mode": self.photo_max_memory_safe_mode,
            "profile_cache_enabled": self.profile_cache_enabled,
            "profile_cache_ttl": self.profile_cache_ttl,
            "photo_cache_ttl": self.photo_cache_ttl,
            "photo_inference_concurrency": self.photo_inference_concurrency
        }
    
    def update_from_dict(self, data: Dict[str, Any]):
        """Update configuration from dictionary (for admin UI)"""
        if "enabled" in data:
            self.enabled = bool(data["enabled"])
        if "minimum_score" in data:
            self.minimum_score = int(data["minimum_score"])
        if "analyzers" in data:
            for analyzer, enabled in data["analyzers"].items():
                if analyzer in self.analyzers:
                    self.analyzers[analyzer] = bool(enabled)
        # Add other fields as needed for admin UI
        logger.info(f"Profile analyzer config updated from dict")