"""
Bio analyzer - lightweight text analysis for Telegram bios
"""
import logging
import re
import json
from pathlib import Path
from typing import Optional, List
from .models import AnalyzerResult
from .config import ProfileAnalyzerConfig

logger = logging.getLogger(__name__)


class BioAnalyzer:
    """Analyzer for detecting gender signals from bio text
    
    Initial implementation is rule-based. ML model can be added later.
    """
    
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
        
        # ML model placeholder (can be loaded later)
        self.ml_model = None
        if config.bio_ml_enabled and config.bio_model_path:
            self._load_ml_model(config.bio_model_path)
    
    def _load_database_keywords(self):
        """Load additional keywords from name database
        
        Returns:
            List of additional keywords
        """
        try:
            data_dir = Path(__file__).parent / "data"
            data_file = data_dir / "uzbek_names.json"
            
            if data_file.exists():
                with open(data_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                # Extract female keywords from database
                return data.get("female_keywords", [])
        except Exception as e:
            logger.warning(f"Failed to load database keywords: {e}")
            return []
    
    def _load_ml_model(self, model_path: str):
        """Load ML model for bio classification (future implementation)
        
        Args:
            model_path: Path to the trained model file
        """
        try:
            # Placeholder for ML model loading
            # In future: self.ml_model = joblib.load(model_path)
            logger.info(f"ML model loading not yet implemented for path: {model_path}")
        except Exception as e:
            logger.error(f"Failed to load ML model: {e}")
    
    def normalize_bio(self, bio: Optional[str]) -> Optional[str]:
        """Normalize bio text for analysis with improved Unicode handling
        
        Args:
            bio: Raw bio text from Telegram profile
            
        Returns:
            Normalized bio or None if invalid
        """
        if not bio:
            return None
        
        # Convert to lowercase for keyword matching
        bio_lower = bio.lower()
        
        # Normalize Unicode characters (Cyrillic/Latin variants)
        try:
            # Simple normalization: handle common Cyrillic-Latin confusion
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
        
        # Remove excessive punctuation but keep basic structure
        bio_normalized = re.sub(r'[^\w\s\-\.,;:!?]', ' ', bio_lower)
        
        # Normalize whitespace: multiple spaces/tabs/newlines to single space
        bio_normalized = re.sub(r'\s+', ' ', bio_normalized)
        
        # Strip whitespace
        bio_normalized = bio_normalized.strip()
        
        if not bio_normalized:
            return None
        
        return bio_normalized
    
    def analyze(self, bio: Optional[str]) -> AnalyzerResult:
        """Analyze bio text and return gender signal
        
        Args:
            bio: User's bio text from Telegram profile
            
        Returns:
            AnalyzerResult with signal (0 or 1)
        """
        normalized_bio = self.normalize_bio(bio)
        
        if not normalized_bio:
            return AnalyzerResult(
                signal=0,
                analyzer_name="bio",
                details={"reason": "empty_or_invalid_bio"}
            )
        
        # Check for keyword matches
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
        
        # Check for pattern matches
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
        
        # ML model analysis (if available)
        if self.ml_model:
            try:
                # Placeholder for ML inference
                # prediction = self.ml_model.predict([normalized_bio])[0]
                # if prediction == 1:
                #     return AnalyzerResult(signal=1, analyzer_name="bio", details={"method": "ml_model"})
                pass
            except Exception as e:
                logger.warning(f"ML model inference failed: {e}")
        
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