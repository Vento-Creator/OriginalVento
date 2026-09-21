"""Model fayllari menejeri: yuklab olish, hajm tekshirish, keshlash."""
import logging
import os
import urllib.request

logger = logging.getLogger(__name__)

# OpenCV res10 SSD yuz detektori (BSD litsenziya, 2.7 MB)
_FACE_PB_URL = (
    "https://github.com/spmallick/learnopencv/raw/master/"
    "AgeGender/opencv_face_detector_uint8.pb"
)
_FACE_PBTXT_URL = (
    "https://raw.githubusercontent.com/spmallick/learnopencv/master/"
    "AgeGender/opencv_face_detector.pbtxt"
)

# Kutilayotgan minimal hajmlar (buzilgan yuklab olishni aniqlash uchun)
_FACE_MIN_SIZES = {
    "opencv_face_detector_uint8.pb": 2_000_000,
    "opencv_face_detector.pbtxt": 20_000,
}

_UA = {"User-Agent": "Mozilla/5.0 (Vento ProfileAnalyzer)"}


def models_dir() -> str:
    """Model papkasi (env PROFILE_ML_MODEL_DIR bilan o'zgartiriladi)."""
    env = (os.getenv("PROFILE_ML_MODEL_DIR") or "").strip()
    if env:
        path = env
    else:
        path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "models")
    os.makedirs(path, exist_ok=True)
    return path


def _looks_valid(path: str, min_size: int) -> bool:
    try:
        return os.path.exists(path) and os.path.getsize(path) >= min_size
    except OSError:
        return False


def _download(url: str, path: str, min_size: int) -> bool:
    """Faylni vaqtinchalik nomga yuklab, muvaffaqiyatli bo'lsa almashtiradi."""
    tmp = path + ".part"
    try:
        req = urllib.request.Request(url, headers=_UA)
        with urllib.request.urlopen(req, timeout=60) as resp, open(tmp, "wb") as f:
            while True:
                chunk = resp.read(1 << 16)
                if not chunk:
                    break
                f.write(chunk)
        if not _looks_valid(tmp, min_size):
            logger.warning("Model fayl hajmi kutilganidan kichik: %s", os.path.basename(path))
            os.remove(tmp)
            return False
        os.replace(tmp, path)
        logger.info("Model yuklab olindi: %s", os.path.basename(path))
        return True
    except Exception as e:
        logger.warning("Model yuklab olishda xato (%s): %s", os.path.basename(path), e)
        try:
            if os.path.exists(tmp):
                os.remove(tmp)
        except OSError:
            pass
        return False


def ensure_face_detector(allow_download: bool = None) -> tuple:
    """Yuz detektori fayllarini tayyorlaydi.

    Returns:
        (pb_path, pbtxt_path) yoki mavjud bo'lmasa (None, None)
    """
    if allow_download is None:
        allow_download = os.getenv("PROFILE_ML_ALLOW_DOWNLOAD", "true").lower() == "true"

    d = models_dir()
    pb = os.path.join(d, "opencv_face_detector_uint8.pb")
    pbtxt = os.path.join(d, "opencv_face_detector.pbtxt")

    if not _looks_valid(pb, _FACE_MIN_SIZES[os.path.basename(pb)]):
        if not (allow_download and _download(_FACE_PB_URL, pb, _FACE_MIN_SIZES[os.path.basename(pb)])):
            pb = None
    if not _looks_valid(pbtxt, _FACE_MIN_SIZES[os.path.basename(pbtxt)]):
        if not (allow_download and _download(_FACE_PBTXT_URL, pbtxt, _FACE_MIN_SIZES[os.path.basename(pbtxt)])):
            pbtxt = None

    return (pb, pbtxt)


def assets_status() -> dict:
    """Modellar holati (diagnostika/UI uchun)."""
    d = models_dir()
    pb = os.path.join(d, "opencv_face_detector_uint8.pb")
    pbtxt = os.path.join(d, "opencv_face_detector.pbtxt")
    text_dir = os.path.join(d, "text_ml")
    return {
        "models_dir": d,
        "face_detector": _looks_valid(pb, _FACE_MIN_SIZES[os.path.basename(pb)])
        and _looks_valid(pbtxt, _FACE_MIN_SIZES[os.path.basename(pbtxt)]),
        "text_models": os.path.isdir(text_dir)
        and any(f.endswith(".joblib") for f in os.listdir(text_dir)),
        "gender_model_id": (os.getenv("PROFILE_GENDER_MODEL_ID") or "rizvandwiki/gender-classification").strip(),
        "allow_download": os.getenv("PROFILE_ML_ALLOW_DOWNLOAD", "true").lower() == "true",
    }
