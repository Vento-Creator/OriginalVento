"""Yuz aniqlash: OpenCV DNN (res10 SSD) + Haar cascade zaxira."""
import logging
import threading
from dataclasses import dataclass

import cv2
import numpy as np

from .assets import ensure_face_detector

logger = logging.getLogger(__name__)


@dataclass
class FaceBox:
    """Aniqlangan yuz to'rtburchagi (piksel koordinatalari)."""
    x1: int
    y1: int
    x2: int
    y2: int
    confidence: float

    @property
    def width(self) -> int:
        return max(0, self.x2 - self.x1)

    @property
    def height(self) -> int:
        return max(0, self.y2 - self.y1)

    @property
    def area(self) -> int:
        return self.width * self.height

    def expand(self, img_w: int, img_h: int, pad: float = 0.25) -> "FaceBox":
        """Yuz atrofidan kontekst qo'shib kengaytirish (klassifikator uchun)."""
        px = int(self.width * pad)
        py = int(self.height * pad)
        return FaceBox(
            max(0, self.x1 - px),
            max(0, self.y1 - py),
            min(img_w, self.x2 + px),
            min(img_h, self.y2 + py),
            self.confidence,
        )


class FaceDetector:
    """Yuz detektori.

    Asosiy: OpenCV DNN res10 SSD (aniq, ~30-130 ms).
    Zaxira: Haar cascade (opencv bilan birga keladi, model fayl kerak emas).
    """

    def __init__(self, conf_threshold: float = 0.5, min_size: int = 24, allow_download: bool = None):
        self.conf_threshold = float(conf_threshold)
        self.min_size = int(min_size)
        self._net = None
        self._haar_face = None
        self._haar_profile = None
        self._lock = threading.Lock()
        self.method = "none"
        self._init_backends(allow_download)

    def _init_backends(self, allow_download):
        pb, pbtxt = ensure_face_detector(allow_download=allow_download)
        if pb and pbtxt:
            try:
                self._net = cv2.dnn.readNet(pb, pbtxt)
                self.method = "dnn_res10"
            except Exception as e:
                logger.warning("DNN yuz detektori yuklanmadi: %s", e)
                self._net = None

        # Haar zaxira (har doim mavjud)
        try:
            base = cv2.data.haarcascades
            self._haar_face = cv2.CascadeClassifier(base + "haarcascade_frontalface_default.xml")
            self._haar_profile = cv2.CascadeClassifier(base + "haarcascade_profileface.xml")
            if self.method == "none" and not self._haar_face.empty():
                self.method = "haar"
        except Exception as e:
            logger.warning("Haar cascade yuklanmadi: %s", e)

    @property
    def available(self) -> bool:
        return self._net is not None or (
            self._haar_face is not None and not self._haar_face.empty()
        )

    def detect(self, bgr_image: np.ndarray, max_faces: int = 5) -> list:
        """Rasmdagi yuzlarni aniqlaydi (ishonch bo'yicha kamayish tartibida)."""
        if bgr_image is None or bgr_image.size == 0:
            return []

        with self._lock:
            faces = []
            if self._net is not None:
                faces = self._detect_dnn(bgr_image)
            if not faces and self._haar_face is not None and not self._haar_face.empty():
                faces = self._detect_haar(bgr_image)

        faces.sort(key=lambda f: -f.confidence)
        return faces[:max_faces]

    def _detect_dnn(self, img: np.ndarray) -> list:
        try:
            h, w = img.shape[:2]
            blob = cv2.dnn.blobFromImage(
                img, 1.0, (300, 300), [104, 117, 123], swapRB=False, crop=False
            )
            self._net.setInput(blob)
            det = self._net.forward()
            out = []
            for i in range(det.shape[2]):
                c = float(det[0, 0, i, 2])
                if c < self.conf_threshold:
                    continue
                x1 = int(det[0, 0, i, 3] * w)
                y1 = int(det[0, 0, i, 4] * h)
                x2 = int(det[0, 0, i, 5] * w)
                y2 = int(det[0, 0, i, 6] * h)
                box = FaceBox(max(0, x1), max(0, y1), max(0, x2), max(0, y2), c)
                if box.width >= self.min_size and box.height >= self.min_size:
                    out.append(box)
            return out
        except Exception as e:
            logger.warning("DNN yuz aniqlash xatosi: %s", e)
            return []

    def _detect_haar(self, img: np.ndarray) -> list:
        try:
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            gray = cv2.equalizeHist(gray)
            out = []
            for cascade in (self._haar_face, self._haar_profile):
                if cascade is None or cascade.empty():
                    continue
                for (x, y, w, h) in cascade.detectMultiScale(
                    gray, scaleFactor=1.1, minNeighbors=5, minSize=(self.min_size, self.min_size)
                ):
                    out.append(FaceBox(int(x), int(y), int(x + w), int(y + h), 0.6))
            return out
        except Exception as e:
            logger.warning("Haar yuz aniqlash xatosi: %s", e)
            return []
