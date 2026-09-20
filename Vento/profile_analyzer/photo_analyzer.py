"""
Photo analyzer - lightweight profile photo analysis with memory optimization
"""
import logging
import hashlib
import asyncio
from typing import Optional, Dict, Any
from PIL import Image
import io

logger = logging.getLogger(__name__)


class PhotoAnalyzer:
    """Analyzer for profile photos with memory-efficient processing
    
    This is a placeholder implementation. The actual computer vision model
    will be added after benchmarking in Phase 7-8.
    """
    
    def __init__(self, config):
        self.config = config
        self.model = None
        self.model_version = config.photo_model_version
        self.max_resolution = config.photo_max_resolution
        self.cache_enabled = config.photo_cache_enabled
        self.safe_mode = config.photo_max_memory_safe_mode
        
        # Placeholder for model loading
        if config.photo_model_path:
            self._load_model(config.photo_model_path)
    
    def _load_model(self, model_path: str):
        """Load computer vision model (future implementation)
        
        Args:
            model_path: Path to the model file
        """
        try:
            # Placeholder for model loading
            # After benchmarking, this will load the selected lightweight model
            logger.info(f"Photo model loading not yet implemented for path: {model_path}")
        except Exception as e:
            logger.error(f"Failed to load photo model: {e}")
    
    def compute_image_hash(self, image_bytes: bytes) -> str:
        """Compute SHA-256 hash of image bytes for caching
        
        Args:
            image_bytes: Raw image bytes
            
        Returns:
            Hexadecimal hash string
        """
        return hashlib.sha256(image_bytes).hexdigest()
    
    def preprocess_image(self, image_bytes: bytes) -> Optional[Image.Image]:
        """Preprocess image for analysis with memory optimization
        
        This method:
        1. Loads the image
        2. Resizes to target resolution
        3. Converts to RGB
        4. Releases original image buffer
        
        Args:
            image_bytes: Raw image bytes
            
        Returns:
            Preprocessed PIL Image or None if processing fails
        """
        try:
            # Load image from bytes
            image = Image.open(io.BytesIO(image_bytes))
            
            # Convert to RGB if necessary
            if image.mode != 'RGB':
                image = image.convert('RGB')
            
            # Resize to target resolution for memory efficiency
            if image.size[0] > self.max_resolution or image.size[1] > self.max_resolution:
                image.thumbnail((self.max_resolution, self.max_resolution), Image.LANCZOS)
            
            return image
            
        except Exception as e:
            logger.warning(f"Image preprocessing failed: {e}")
            return None
    
    def extract_basic_features(self, image: Image.Image) -> Dict[str, Any]:
        """Extract basic visual features without ML model
        
        Args:
            image: Preprocessed PIL Image
            
        Returns:
            Dictionary of basic features
        """
        features = {
            "width": image.size[0],
            "height": image.size[1],
            "aspect_ratio": image.size[0] / image.size[1] if image.size[1] > 0 else 0,
            "mode": image.mode
        }
        
        # Basic heuristic: portrait orientation (height > width)
        features["portrait_like"] = image.size[1] > image.size[0]
        
        # Basic heuristic: square images might be logos/illustrations
        aspect_diff = abs(image.size[0] - image.size[1]) / max(image.size)
        features["likely_portrait"] = aspect_diff > 0.2
        
        return features
    
    def analyze_with_model(self, image: Image.Image) -> Dict[str, Any]:
        """Analyze image with ML model (placeholder)
        
        Args:
            image: Preprocessed PIL Image
            
        Returns:
            Model analysis results
        """
        # Placeholder for actual model inference
        # After benchmarking, this will use the selected lightweight model
        return {
            "face_detected": False,
            "person_detected": False,
            "confidence": 0.0,
            "method": "placeholder"
        }
    
    async def analyze(self, photo_bytes: Optional[bytes]) -> 'AnalyzerResult':
        """Analyze profile photo and return gender signal
        
        Args:
            photo_bytes: Raw profile photo bytes from Telegram
            
        Returns:
            AnalyzerResult with signal (0 or 1)
        """
        from .models import AnalyzerResult
        
        if not photo_bytes:
            return AnalyzerResult(
                signal=0,
                analyzer_name="photo",
                details={"reason": "no_photo"}
            )
        
        try:
            # Compute hash for caching
            image_hash = self.compute_image_hash(photo_bytes)
            
            # Preprocess image with memory optimization
            image = self.preprocess_image(photo_bytes)
            if not image:
                return AnalyzerResult(
                    signal=0,
                    analyzer_name="photo",
                    details={"reason": "preprocessing_failed", "hash": image_hash}
                )
            
            # Extract basic features
            basic_features = self.extract_basic_features(image)
            
            # If model is available, run inference
            if self.model:
                model_features = self.analyze_with_model(image)
                features = {**basic_features, **model_features}
            else:
                features = basic_features
                features["method"] = "basic_features_only"
            
            # Release image memory immediately
            image.close()
            
            # Basic heuristic: if portrait-like and reasonable aspect ratio, give signal
            # This is a very basic fallback when model is not available
            signal = 0
            if features.get("portrait_like") and features.get("likely_portrait"):
                signal = 1
            
            return AnalyzerResult(
                signal=signal,
                analyzer_name="photo",
                details={
                    **features,
                    "hash": image_hash,
                    "model_version": self.model_version
                }
            )
            
        except Exception as e:
            logger.warning(f"Photo analysis failed: {e}")
            return AnalyzerResult(
                signal=0,
                analyzer_name="photo",
                details={"reason": "analysis_failed", "error": str(e)}
            )
    
    def check_memory_pressure(self) -> bool:
        """Check if system is under memory pressure (future implementation)
        
        Returns:
            True if memory pressure is high and analysis should be skipped
        """
        if not self.safe_mode:
            return False
        
        try:
            import psutil
            memory_percent = psutil.virtual_memory().percent
            return memory_percent > 85  # 85% memory usage threshold
        except Exception:
            return False