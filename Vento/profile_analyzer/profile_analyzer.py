"""
Main profile analyzer - coordinates all analyzers and provides unified interface
"""
import logging
import asyncio
from typing import Optional, Dict, Any
from pathlib import Path
from pyrogram.types import User

from .config import ProfileAnalyzerConfig
from .models import ProfileAnalysis, AnalyzerResult
from .scoring_engine import ScoringEngine
from .name_analyzer import NameAnalyzer
from .username_analyzer import UsernameAnalyzer
from .bio_analyzer import BioAnalyzer
from .photo_analyzer import PhotoAnalyzer
from .cache import PhotoHashCache, ProfileResultCache

logger = logging.getLogger(__name__)


class ProfileAnalyzer:
    """Main profile analyzer that coordinates all individual analyzers
    
    This class provides a unified interface for profile analysis and manages
    the pipeline of analyzers, caching, and scoring.
    """
    
    def __init__(self, config: Optional[ProfileAnalyzerConfig] = None, cache_dir: Optional[str] = None):
        """Initialize profile analyzer
        
        Args:
            config: Analyzer configuration (uses defaults if None)
            cache_dir: Directory for cache files (uses data/profile_cache if None)
        """
        self.config = config or ProfileAnalyzerConfig.from_env()
        
        # Initialize cache directory
        if cache_dir is None:
            from config import DATA_DIR
            cache_dir = str(Path(DATA_DIR) / "profile_cache")
        
        # Initialize scoring engine
        self.scoring_engine = ScoringEngine()
        
        # Initialize individual analyzers
        self.name_analyzer = NameAnalyzer(self.config)
        self.username_analyzer = UsernameAnalyzer(self.config)
        self.bio_analyzer = BioAnalyzer(self.config)
        self.photo_analyzer = PhotoAnalyzer(self.config)
        
        # Initialize caches
        self.photo_cache = PhotoHashCache(
            cache_dir=str(Path(cache_dir) / "photo_cache"),
            ttl=self.config.photo_cache_ttl
        ) if self.config.photo_cache_enabled else None
        
        self.profile_cache = ProfileResultCache(
            cache_dir=str(Path(cache_dir) / "profile_cache"),
            ttl=self.config.profile_cache_ttl
        ) if self.config.profile_cache_enabled else None
        
        # Photo analysis semaphore for concurrency control
        self.photo_semaphore = asyncio.Semaphore(self.config.photo_inference_concurrency)
        
        logger.info(f"Profile analyzer initialized: enabled={self.config.enabled}, min_score={self.config.minimum_score}")
    
    async def download_profile_photo(self, client, user_id: int) -> Optional[bytes]:
        """Download user's profile photo
        
        Args:
            client: Pyrogram client
            user_id: Telegram user ID
            
        Returns:
            Photo bytes or None if download fails
        """
        try:
            photos = await client.get_profile_photos(user_id, limit=1)
            if not photos:
                return None
            
            # Download the photo
            photo = await client.download_media(photos[0], in_memory=True)
            return photo
            
        except Exception as e:
            logger.warning(f"Failed to download profile photo for user {user_id}: {e}")
            return None
    
    async def analyze(self, user: User, client, profile_photo_bytes: Optional[bytes] = None) -> ProfileAnalysis:
        """Analyze a Telegram user profile
        
        Args:
            user: Pyrogram User object
            client: Pyrogram client for downloading photos
            profile_photo_bytes: Optional pre-downloaded photo bytes
            
        Returns:
            ProfileAnalysis with all analyzer signals and total score
        """
        if not self.config.enabled:
            # Return default analysis if disabled
            return ProfileAnalysis(
                user_id=user.id,
                total_score=0,
                max_score=0,
                details={"reason": "analyzer_disabled"}
            )
        
        # Extract profile data
        name = user.first_name or ""
        username = user.username or ""
        bio = user.bio or ""
        
        # Download photo if photo analyzer is enabled and photo bytes not provided
        if profile_photo_bytes is None and client and self.config.analyzers.get("photo", True) and self.config.photo_enabled:
            try:
                profile_photo_bytes = await self.download_profile_photo(client, user.id)
            except Exception as e:
                logger.warning(f"Failed to download profile photo for user {user.id}: {e}")
                profile_photo_bytes = None

        # Compute photo hash if photo bytes provided
        photo_hash = ""
        if profile_photo_bytes:
            photo_hash = self.photo_analyzer.compute_image_hash(profile_photo_bytes)
        
        # Check profile cache first
        if self.profile_cache:
            cached_result = await self.profile_cache.get(
                user_id=user.id,
                name=name,
                username=username,
                bio=bio,
                photo_hash=photo_hash,
                analyzer_version="v1"
            )
            if cached_result:
                logger.debug(f"Profile cache hit for user {user.id}")
                return ProfileAnalysis.from_dict(cached_result)
        
        # Run analyzers in order: cheap to expensive
        signals = {}
        details = {}
        
        # Name analyzer (cheap)
        if self.config.analyzers.get("name", True):
            try:
                name_result = self.name_analyzer.analyze(name)
                signals["name"] = name_result.signal
                details["name_analysis"] = name_result.details
            except Exception as e:
                logger.warning(f"Name analyzer failed for user {user.id}: {e}")
                signals["name"] = 0
        
        # Username analyzer (cheap)
        if self.config.analyzers.get("username", True):
            try:
                username_result = self.username_analyzer.analyze(username)
                signals["username"] = username_result.signal
                details["username_analysis"] = username_result.details
            except Exception as e:
                logger.warning(f"Username analyzer failed for user {user.id}: {e}")
                signals["username"] = 0
        
        # Bio analyzer (cheap)
        if self.config.analyzers.get("bio", True):
            try:
                bio_result = self.bio_analyzer.analyze(bio)
                signals["bio"] = bio_result.signal
                details["bio_analysis"] = bio_result.details
            except Exception as e:
                logger.warning(f"Bio analyzer failed for user {user.id}: {e}")
                signals["bio"] = 0
        
        # Photo analyzer (expensive - bounded concurrency)
        if self.config.analyzers.get("photo", True) and self.config.photo_enabled:
            try:
                async with self.photo_semaphore:
                    cached_photo_result = None
                    if self.photo_cache and photo_hash:
                        cached_photo_result = await self.photo_cache.get(photo_hash, self.config.photo_model_version)
                    
                    if cached_photo_result:
                        logger.debug(f"Photo cache hit for user {user.id}")
                        signals["photo"] = cached_photo_result.get("signal", 0)
                        details["photo_analysis"] = cached_photo_result.get("details", {})
                    elif profile_photo_bytes:
                        photo_result = await self.photo_analyzer.analyze(profile_photo_bytes)
                        signals["photo"] = photo_result.signal
                        details["photo_analysis"] = photo_result.details
                        
                        if self.photo_cache and photo_hash:
                            await self.photo_cache.set(
                                photo_hash,
                                {
                                    "signal": photo_result.signal,
                                    "details": photo_result.details
                                },
                                self.config.photo_model_version
                            )
                    else:
                        signals["photo"] = 0
                        details["photo_analysis"] = {"reason": "no_photo"}
            except Exception as e:
                logger.warning(f"Photo analyzer failed for user {user.id}: {e}")
                signals["photo"] = 0
        
        # Calculate total score
        total_score = self.scoring_engine.calculate(signals)
        
        # Calculate max score based on enabled analyzers
        max_score = self.scoring_engine.calculate_max_score(self.config.analyzers)
        
        # Create profile analysis result
        analysis = ProfileAnalysis(
            user_id=user.id,
            name_signal=signals.get("name", 0),
            username_signal=signals.get("username", 0),
            bio_signal=signals.get("bio", 0),
            photo_signal=signals.get("photo", 0),
            total_score=total_score,
            max_score=max_score,
            details=details,
            analyzer_version="v1"
        )
        
        # Cache profile result
        if self.profile_cache:
            await self.profile_cache.set(
                user_id=user.id,
                name=name,
                username=username,
                bio=bio,
                photo_hash=photo_hash,
                data=analysis.to_dict(),
                analyzer_version="v1"
            )
        
        return analysis
    
    def should_include_user(self, analysis: ProfileAnalysis) -> bool:
        """Check if user should be included based on score threshold
        
        Args:
            analysis: Profile analysis result
            
        Returns:
            True if user meets minimum score requirement
        """
        return analysis.passes_threshold(self.config.minimum_score)
    
    async def clear_caches(self):
        """Clear all caches"""
        if self.photo_cache:
            await self.photo_cache.clear()
        if self.profile_cache:
            await self.profile_cache.clear()
        logger.info("Profile analyzer caches cleared")