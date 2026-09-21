"""
Photo analyzer - OpenCV DNN Face Detection + HuggingFace ViT Gender Classification
"""
import logging
import hashlib
import asyncio
import io
from typing import Optional, Dict, Any
from PIL import Image
import cv2
import numpy as np

logger = logging.getLogger(__name__)


class PhotoAnalyzer:
    """Analyzer for profile photos using OpenCV DNN face detection and ViT gender classification."""
    
    def __init__(self, config):
        self.config = config
        self.model_version = config.photo_model_version
        self.max_resolution = config.photo_max_resolution
        self.cache_enabled = config.photo_cache_enabled
        self.safe_mode = config.photo_max_memory_safe_mode
        
        self._face_detector = None
        self._gender_classifier = None
        self._ml_init_attempted = False

    def _get_ml_models(self):
        """Lazy initialization of FaceDetector and GenderClassifier."""
        if not self._ml_init_attempted:
            self._ml_init_attempted = True
            try:
                from .ml import FaceDetector, GenderClassifier
                self._face_detector = FaceDetector()
                self._gender_classifier = GenderClassifier()
            except Exception as e:
                logger.warning(f"Failed to initialize photo ML models: {e}")
        return self._face_detector, self._gender_classifier

    def compute_image_hash(self, image_bytes: bytes) -> str:
        """Compute SHA-256 hash of image bytes for caching."""
        return hashlib.sha256(image_bytes).hexdigest()

    def analyze_photo_bytes(self, photo_bytes: bytes) -> Dict[str, Any]:
        """Perform Computer Vision face detection and gender classification on photo bytes."""
        try:
            face_det, gender_clf = self._get_ml_models()
            
            # Decode image bytes to OpenCV BGR matrix
            nparr = np.frombuffer(photo_bytes, np.uint8)
            bgr_img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            
            if bgr_img is None or bgr_img.size == 0:
                return {"ok": False, "reason": "image_decode_failed"}

            h, w = bgr_img.shape[:2]
            
            # Resize large images to conserve memory
            if max(h, w) > 1600:
                scale = 1600 / max(h, w)
                bgr_img = cv2.resize(bgr_img, None, fx=scale, fy=scale)
                h, w = bgr_img.shape[:2]

            # 1. Detect faces
            faces = face_det.detect(bgr_img, max_faces=5) if face_det else []
            
            if not faces:
                return {
                    "ok": True,
                    "face_detected": False,
                    "face_count": 0,
                    "female_prob": 0.0,
                    "gender_label": "no_face",
                    "method": "ml_cv_detector"
                }

            # Top face (highest confidence)
            primary_face = faces[0]
            expanded_box = primary_face.expand(w, h, pad=0.25)
            
            # Crop face area
            face_crop = bgr_img[expanded_box.y1:expanded_box.y2, expanded_box.x1:expanded_box.x2]
            
            if face_crop.size == 0:
                return {
                    "ok": True,
                    "face_detected": True,
                    "face_count": len(faces),
                    "female_prob": 0.0,
                    "gender_label": "invalid_crop",
                    "method": "ml_cv_detector"
                }

            # 2. Classify gender from face crop
            if gender_clf:
                clf_result = gender_clf.classify_face(face_crop)
                female_prob = clf_result.get("female_prob", 0.0)
                gender_label = clf_result.get("label", "unknown")
                is_female = female_prob >= 0.5
            else:
                female_prob = 0.0
                gender_label = "model_unavailable"
                is_female = False

            return {
                "ok": True,
                "face_detected": True,
                "face_count": len(faces),
                "face_confidence": round(float(primary_face.confidence), 3),
                "female_prob": round(float(female_prob), 3),
                "gender_label": gender_label,
                "is_female": is_female,
                "method": "ml_cv_vit"
            }

        except Exception as e:
            logger.warning(f"Photo ML inference failed: {e}")
            return {"ok": False, "reason": str(e)}

    async def analyze(self, photo_bytes: Optional[bytes]) -> 'AnalyzerResult':
        """Analyze profile photo and return gender signal."""
        from .models import AnalyzerResult

        if not photo_bytes:
            return AnalyzerResult(
                signal=0,
                analyzer_name="photo",
                details={"reason": "no_photo"}
            )

        try:
            image_hash = self.compute_image_hash(photo_bytes)
            
            # Check memory pressure in safe mode
            if self.check_memory_pressure():
                logger.warning("Memory pressure high (>85%), skipping photo ML analysis")
                return AnalyzerResult(
                    signal=0,
                    analyzer_name="photo",
                    details={"reason": "memory_pressure_skip", "hash": image_hash}
                )

            ml_res = self.analyze_photo_bytes(photo_bytes)
            
            signal = 0
            if ml_res.get("ok"):
                if ml_res.get("face_detected") and ml_res.get("female_prob", 0.0) >= 0.5:
                    signal = 1

            return AnalyzerResult(
                signal=signal,
                analyzer_name="photo",
                details={
                    **ml_res,
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
        """Check if system is under memory pressure (>85% RSS)."""
        if not self.safe_mode:
            return False

        try:
            import psutil
            return psutil.virtual_memory().percent > 85
        except Exception:
            return False