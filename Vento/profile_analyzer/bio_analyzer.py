"""
Bio analyzer - rule-based and scikit-learn TF-IDF ML analysis for Telegram bios
"""
import logging
import os
import re
import json
from pathlib import Path
from typing import Optional, List
from .models import AnalyzerResult
from .config import ProfileAnalyzerConfig

logger = logging.getLogger(__name__)


class BioAnalyzer:
    """Analyzer for detecting gender signals from bio text using rules and scikit-learn ML model."""
    
    def __init__(self, config: ProfileAnalyzerConfig):
        self.config = config
        
        # Default keywords that may indicate female profiles
        self.default_keywords = [
            "girl", "lady", "woman", "female", "queen", "princess",
            "miss", "mrs", "sister", "daughter", "mom", "mother",
            "девушка", "женщина", "девочка", "мама", "дочь", "сестра",
            "qiz", "ayol", "onam", "singlim", "opam"
        ]
        
        # Load additional keywords from name database if available
        database_keywords = self._load_database_keywords()
        self.default_keywords.extend(database_keywords)
        
        # Keywords from config or defaults
        self.keywords = config.bio_keywords or self.default_keywords
        
        # Common patterns in female bios
        self.patterns = config.bio_patterns or [
            r"age\s*[:=]\s*\d{2}",           # age: 18-99
            r"born\s*\d{4}",                 # born 199X-200X
            r"\d{2}\s*years?\s*old",        # 18 years old
            r"👸|👩|💁|💃",                    # female emojis
            r"she\/her",                     # pronouns
            r"her\/hers"                     # pronouns
        ]
        
        self._ml_model = None
        self._ml_tried = False

    def _get_ml_model(self):
        """Lazy initialization of TextGenderModel for bio classification."""
        if self._ml_model is None and not self._ml_tried:
            self._ml_tried = True
            try:
                from .ml import TextGenderModel

                threshold = float(os.getenv("PROFILE_BIO_ML_THRESHOLD", "0.60"))
                self._ml_model = TextGenderModel("bio", threshold=threshold)
            except Exception as e:
                logger.debug(f"Failed to initialize bio ML model: {e}")
        return self._ml_model
    
    def _load_database_keywords(self):
        """Load additional keywords from name database."""
        try:
            data_dir = Path(__file__).parent / "data"
            data_file = data_dir / "uzbek_names.json"
            
            if data_file.exists():
                with open(data_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                return data.get("female_keywords", [])
        except Exception as e:
            logger.warning(f"Failed to load database keywords: {e}")
            return []
    
    def normalize_bio(self, bio: Optional[str]) -> Optional[str]:
        """Normalize bio text for analysis with improved Unicode handling."""
        if not bio:
            return None
        
        bio_lower = bio.lower()
        
        try:
            replacements = {
                'а': 'a', 'б': 'b', 'в': 'v', 'г': 'g', 'д': 'd', 'е': 'e',
                'ё': 'e', 'ж': 'zh', 'з': 'z', 'и': 'i', 'й': 'y', 'к': 'k',
                'л': 'l', 'м': 'm', 'н': 'n', 'о': 'o', 'п': 'p', 'р': 'r',
                'с': 's', 'т': 't', 'у': 'u', 'ф': 'f', 'х': 'kh', 'ц': 'ts',
                'ч': 'ch', 'ш': 'sh', 'щ': 'shch', 'ъ': '', 'ы': 'y', 'ь': '',
                'э': 'e', 'ю': 'yu', 'я': 'ya'
            }
            for cyrillic, latin in replacements.items():
                bio_lower = bio_lower.replace(cyrillic, latin)
        except Exception as e:
            logger.warning(f"Unicode normalization failed: {e}")
        
        bio_normalized = re.sub(r'[^\w\s\-\.,;:!?]', ' ', bio_lower)
        bio_normalized = re.sub(r'\s+', ' ', bio_normalized)
        bio_normalized = bio_normalized.strip()
        
        if not bio_normalized:
            return None
        
        return bio_normalized
    
    def analyze(self, bio: Optional[str]) -> AnalyzerResult:
        """Analyze bio text and return gender signal."""
        normalized_bio = self.normalize_bio(bio)
        
        if not normalized_bio:
            return AnalyzerResult(
                signal=0,
                analyzer_name="bio",
                details={"reason": "empty_or_invalid_bio"}
            )
        
        # 1. Check for keyword matches
        for keyword in self.keywords:
            if keyword.lower() in normalized_bio:
                return AnalyzerResult(
                    signal=1,
                    analyzer_name="bio",
                    details={
                        "matched_keyword": keyword,
                        "method": "keyword_match",
                        "bio_length": len(normalized_bio)
                    }
                )
        
        # 2. Check for pattern matches
        for pattern in self.patterns:
            if re.search(pattern, normalized_bio, re.IGNORECASE):
                return AnalyzerResult(
                    signal=1,
                    analyzer_name="bio",
                    details={
                        "matched_pattern": pattern,
                        "method": "pattern_match",
                        "bio_length": len(normalized_bio)
                    }
                )
        
        # 3. ML model analysis (TF-IDF + Logistic Regression)
        try:
            ml_model = self._get_ml_model()
            if ml_model is not None:
                ml_prob = ml_model.predict_female_prob(normalized_bio)
                threshold = float(getattr(ml_model, "threshold", 0.60))
                if ml_prob >= threshold:
                    return AnalyzerResult(
                        signal=1,
                        analyzer_name="bio",
                        details={
                            "method": "ml_classifier",
                            "ml_female_prob": round(ml_prob, 3),
                            "bio_length": len(normalized_bio)
                        }
                    )
        except Exception as e:
            logger.debug(f"Bio ML model inference failed: {e}")
        
        # No match found
        return AnalyzerResult(
            signal=0,
            analyzer_name="bio",
            details={
                "reason": "no_match",
                "bio_length": len(normalized_bio),
                "method": "no_match"
            }
        )