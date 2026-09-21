"""Ism va bio uchun ML klassifikatorlar (scikit-learn, offline o'qitiladi).

TF-IDF (belgi n-gramlari) + LogisticRegression — belgilangan namunlardan
o'rganadi va 'ayol' ehtimolini qaytaradi. Model birinchi ishlatishda
o'qitiladi va diskka keshlanadi (joblib).
"""
import hashlib
import logging
import os
import re
import threading

from . import datasets as ds
from .assets import models_dir

logger = logging.getLogger(__name__)

_TRAIN_LOCK = threading.Lock()
_MODEL_CACHE = {}

_CYR = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "yo", "ж": "j",
    "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m", "н": "n", "о": "o",
    "п": "p", "р": "r", "с": "s", "т": "t", "у": "u", "ф": "f", "х": "kh", "ц": "ts",
    "ч": "ch", "ш": "sh", "щ": "sh", "ъ": "", "ы": "i", "ь": "", "э": "e", "ю": "yu",
    "я": "ya", "ў": "o", "қ": "q", "ғ": "g", "ҳ": "h",
}


def _translit(text: str) -> str:
    """Kirill va o'zbek apostrof belgilarini soddalashtirish."""
    s = "".join(_CYR.get(ch, ch) for ch in text.lower())
    for a, b in (("o'", "o"), ("g'", "g"), ("o`", "o"), ("g`", "g"), ("ʻ", ""), ("ʼ", "")):
        s = s.replace(a, b)
    return s


def normalize_text(text: str, for_name: bool = False) -> str:
    """Matnni normallashtirish: kichik harf, ortiqcha belgilarni tozalash."""
    if not text:
        return ""
    s = _translit(str(text))
    if for_name:
        s = re.split(r"[\s|,._\-]+", s.strip())[0]
        s = re.sub(r"[^a-z']+", "", s)
    else:
        s = re.sub(r"\s+", " ", s).strip()
    return s


def _dataset_fingerprint(kind: str) -> str:
    """Dataset o'zgarganini aniqlash uchun hash."""
    if kind == "name":
        payload = "|".join(
            [f"F:{n}" for n in ds.FEMALE_NAMES] + [f"M:{n}" for n in ds.MALE_NAMES]
        )
    else:
        payload = "|".join(
            [f"F:{b}" for b in ds.FEMALE_BIOS] + [f"N:{b}" for b in ds.NONFEMALE_BIOS]
        )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


class TextGenderModel:
    """Ism yoki bio matnidan 'ayol' ehtimolini hisoblaydigan ML model."""

    VERSION = "v2"

    def __init__(self, kind: str, threshold: float = 0.6, force_retrain: bool = False):
        if kind not in ("name", "bio"):
            raise ValueError("kind 'name' yoki 'bio' bo'lishi kerak")
        self.kind = kind
        self.threshold = float(threshold)
        self.force_retrain = force_retrain
        self._model = None
        self._ready = False
        self.source = "untrained"

    # ------------------------------------------------------------------ o'qitish
    def _build_samples(self):
        if self.kind == "name":
            texts = list(ds.FEMALE_NAMES) + list(ds.MALE_NAMES)
            labels = [1] * len(ds.FEMALE_NAMES) + [0] * len(ds.MALE_NAMES)
            return [normalize_text(t, for_name=True) for t in texts], labels
        texts = list(ds.FEMALE_BIOS) + list(ds.NONFEMALE_BIOS)
        labels = [1] * len(ds.FEMALE_BIOS) + [0] * len(ds.NONFEMALE_BIOS)
        return [normalize_text(t) for t in texts], labels

    def _cache_path(self) -> str:
        d = os.path.join(models_dir(), "text_ml")
        os.makedirs(d, exist_ok=True)
        return os.path.join(d, f"{self.kind}_{self.VERSION}.joblib")

    def _train(self) -> bool:
        try:
            import joblib
            from sklearn.feature_extraction.text import TfidfVectorizer
            from sklearn.linear_model import LogisticRegression
            from sklearn.pipeline import Pipeline

            X, y = self._build_samples()
            ngram = (2, 4) if self.kind == "name" else (2, 5)
            pipe = Pipeline([
                ("vec", TfidfVectorizer(analyzer="char_wb", ngram_range=ngram,
                                        min_df=1, sublinear_tf=True, lowercase=True)),
                ("clf", LogisticRegression(max_iter=2000, C=4.0, class_weight="balanced")),
            ])
            pipe.fit(X, y)

            bundle = {"pipeline": pipe, "fingerprint": _dataset_fingerprint(self.kind),
                      "kind": self.kind, "version": self.VERSION}
            try:
                joblib.dump(bundle, self._cache_path())
            except Exception as e:
                logger.warning("Matn modelini keshlash xatosi: %s", e)

            self._model = pipe
            self._ready = True
            self.source = "trained"
            logger.info("ML matn modeli o'qitildi: kind=%s, namunalar=%s", self.kind, len(X))
            return True
        except Exception as e:
            logger.warning("ML matn modelini o'qitish xatosi: %s", e)
            self._ready = False
            return False

    def _load_cached(self) -> bool:
        path = self._cache_path()
        if self.force_retrain or not os.path.exists(path):
            return False
        try:
            import joblib
            bundle = joblib.load(path)
            if bundle.get("fingerprint") != _dataset_fingerprint(self.kind):
                logger.info("Matn modeli eskirgan, qayta o'qitiladi: %s", self.kind)
                return False
            self._model = bundle.get("pipeline")
            self._ready = self._model is not None
            self.source = "cache"
            return self._ready
        except Exception as e:
            logger.warning("Matn modelini yuklash xatosi: %s", e)
            return False

    def ensure_ready(self) -> bool:
        """Modelni keshdan yuklaydi yoki o'qitadi (bir marta)."""
        if self._ready:
            return True
        key = f"{self.kind}:{self.VERSION}:{self.force_retrain}"
        with _TRAIN_LOCK:
            if self._ready:
                return True
            shared = _MODEL_CACHE.get(key)
            if shared is not None:
                self._model = shared
                self._ready = True
                self.source = "shared"
                return True
            if self._load_cached() or self._train():
                _MODEL_CACHE[key] = self._model
                return True
            return False

    @property
    def available(self) -> bool:
        return self.ensure_ready()

    # ----------------------------------------------------------------- inferens
    def predict_female_prob(self, text: str) -> float:
        """'Ayol' bo'lish ehtimoli (0..1). Model tayyor bo'lmasa 0.0."""
        if not text or not str(text).strip():
            return 0.0
        if not self.ensure_ready():
            return 0.0
        try:
            norm = normalize_text(str(text), for_name=(self.kind == "name"))
            if not norm:
                return 0.0
            proba = self._model.predict_proba([norm])[0]
            classes = list(self._model.named_steps["clf"].classes_)
            idx = classes.index(1) if 1 in classes else -1
            return float(proba[idx])
        except Exception as e:
            logger.debug("Matn ML inferens xatosi (%s): %s", self.kind, e)
            return 0.0
