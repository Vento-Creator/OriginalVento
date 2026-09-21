"""
ML modul — profil tahlilining ML qatlami.

Tarkibi:
    assets   — model fayllarini yuklab olish/tekshirish/keshlash
    face     — yuz aniqlash (OpenCV DNN res10 SSD, Haar zaxira)
    gender   — yuzdan gender klassifikatsiya (ViT, transformers)
    text_ml  — ism/bio uchun sklearn matn modellari (offline o'qitiladi)
    datasets — o'qitish uchun belgilangan seed ma'lumotlar
"""

from .assets import models_dir, ensure_face_detector, assets_status
from .face import FaceDetector, FaceBox
from .gender import GenderClassifier
from .text_ml import TextGenderModel

__all__ = [
    "models_dir",
    "ensure_face_detector",
    "assets_status",
    "FaceDetector",
    "FaceBox",
    "GenderClassifier",
    "TextGenderModel",
]
