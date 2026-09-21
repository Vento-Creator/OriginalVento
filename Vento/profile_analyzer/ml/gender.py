"""Yuzdan gender klassifikatsiya — transformers ViT modeli (lazy yuklanadi)."""
import logging
import os
import threading
import time

import cv2
import numpy as np

logger = logging.getLogger(__name__)

_DEFAULT_MODEL_ID = "rizvandwiki/gender-classification"


class GenderClassifier:
    """ViT-asosidagi gender klassifikatori.

    Model birinchi chaqiruvda yuklanadi (~40s, 343 MB) va jarayon davomida
    bir marta xotirada saqlanadi. Yuklab bo'lmasa (internet yo'q) —
    ``available`` False qaytaradi va tahlil zaxira yo'lga o'tadi.
    """

    def __init__(self, model_id: str = None, allow_download: bool = None):
        self.model_id = (model_id or os.getenv("PROFILE_GENDER_MODEL_ID") or _DEFAULT_MODEL_ID).strip()
        if allow_download is None:
            allow_download = os.getenv("PROFILE_ML_ALLOW_DOWNLOAD", "true").lower() == "true"
        self.allow_download = allow_download
        self._pipe = None
        self._load_attempted = False
        self._load_failed = False
        self._lock = threading.Lock()
        self._infer_lock = threading.Lock()
        self.last_load_seconds = 0.0

    # ------------------------------------------------------------------ yuklash
    def _local_files_only(self) -> bool:
        return not self.allow_download

    def _ensure_loaded(self) -> bool:
        """Modelni yuklaydi (bir marta). True — foydalanishga tayyor."""
        if self._pipe is not None:
            return True
        if self._load_failed:
            return False

        with self._lock:
            if self._pipe is not None:
                return True
            if self._load_failed:
                return False
            if self._load_attempted and self._pipe is None:
                # Boshqa thread yuklayapti — kutamiz
                return self._pipe is not None
            self._load_attempted = True

            t0 = time.time()
            try:
                # Og'ir importlar faqat shu yerda (bot ishga tushishini sekinlashtirmaslik uchun)
                import torch  # noqa: F401
                from transformers import pipeline

                try:
                    torch.set_num_threads(int(os.getenv("PROFILE_TORCH_THREADS", "2")))
                except Exception:
                    pass

                # NOTE: transformers 5.x pipeline() local_files_only kwarg qabul
                # qilmaydi — offline rejim HF_HUB_OFFLINE env orqali boshqariladi.
                env_backup = os.environ.get("HF_HUB_OFFLINE")
                try:
                    if not self.allow_download:
                        os.environ["HF_HUB_OFFLINE"] = "1"
                    else:
                        os.environ.pop("HF_HUB_OFFLINE", None)
                    self._pipe = pipeline("image-classification", model=self.model_id)
                finally:
                    if env_backup is None:
                        os.environ.pop("HF_HUB_OFFLINE", None)
                    else:
                        os.environ["HF_HUB_OFFLINE"] = env_backup
                self.last_load_seconds = time.time() - t0
                logger.info(
                    "Gender modeli yuklandi: %s (%.1fs)", self.model_id, self.last_load_seconds
                )
                return True
            except Exception as e:
                self._load_failed = True
                logger.warning("Gender modeli yuklanmadi (%s): %s", self.model_id, e)
                return False

    @property
    def available(self) -> bool:
        """Model allaqachon yuklanganmi (yuklashni boshlamaydi)."""
        return self._pipe is not None

    def warmup(self) -> bool:
        """Modelni oldindan yuklash (ixtiyoriy)."""
        return self._ensure_loaded()

    # ---------------------------------------------------------------- inferens
    @staticmethod
    def _to_female_prob(results: list) -> float:
        """pipeline natijasidan 'female' ehtimolini ajratib olish."""
        prob = 0.0
        total = 0.0
        for item in results:
            label = str(item.get("label", "")).lower()
            score = float(item.get("score", 0.0))
            total += score
            if "female" in label or "woman" in label or label in ("f", "2"):
                prob += score
        if total > 0 and prob == 0.0:
            # Model boshqa nomlash ishlatsa — 'male' bo'lmaganini olamiz
            for item in results:
                label = str(item.get("label", "")).lower()
                if "male" not in label and "man" not in label:
                    prob += float(item.get("score", 0.0))
        return max(0.0, min(1.0, prob))

    def classify_face(self, face_bgr: np.ndarray) -> dict:
        """Yuz kesimini (BGR) klassifikatsiya qiladi.

        Returns:
            {"ok": bool, "female_prob": float, "label": str, "raw": [...]}
        """
        if face_bgr is None or face_bgr.size == 0:
            return {"ok": False, "female_prob": 0.0, "label": "unknown", "raw": []}

        if not self._ensure_loaded():
            return {"ok": False, "female_prob": 0.0, "label": "model_unavailable", "raw": []}

        try:
            from PIL import Image
            import torch

            rgb = cv2.cvtColor(face_bgr, cv2.COLOR_BGR2RGB)
            pil = Image.fromarray(rgb)
            with self._infer_lock:
                try:
                    with torch.inference_mode():
                        results = self._pipe(pil, top_k=2)
                except Exception:
                    results = self._pipe(pil, top_k=2)
            prob = self._to_female_prob(results)
            label = "female" if prob >= 0.5 else "male"
            return {"ok": True, "female_prob": prob, "label": label, "raw": results}
        except Exception as e:
            logger.warning("Gender klassifikatsiya xatosi: %s", e)
            return {"ok": False, "female_prob": 0.0, "label": "error", "raw": []}
