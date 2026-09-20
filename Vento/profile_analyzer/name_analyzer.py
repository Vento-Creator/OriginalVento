"""
Name analyzer - uses gender-guesser library for name-based gender detection
"""
import logging
import re
import json
from pathlib import Path
from typing import Optional, Set
from .models import AnalyzerResult
from .config import ProfileAnalyzerConfig

logger = logging.getLogger(__name__)

# Initialize gender-guesser detector
try:
    import gender_guesser.detector as gender
    _gender_detector = gender.Detector(case_sensitive=False)
    _GENDER_GUESSER_AVAILABLE = True
except ImportError:
    _GENDER_GUESSER_AVAILABLE = False
    logger.warning("gender-guesser library not available, name analyzer will use fallback")


class NameAnalyzer:
    """Analyzer for detecting gender from first names using gender-guesser"""
    
    def __init__(self, config: ProfileAnalyzerConfig):
        self.config = config
        self.detector = _gender_detector if _GENDER_GUESSER_AVAILABLE else None
        
        # Default positive labels for female detection
        self.positive_labels = config.name_positive_labels or [
            "female",
            "mostly_female"
        ]
        
        # Load external name database
        self.female_names: Set[str] = set()
        self.female_suffixes: Set[str] = set()
        self.male_suffixes: Set[str] = set()
        self.transliteration_map: dict = {}
        
        self._load_name_database()
        
        # Fallback patterns if database load fails
        if not self.female_suffixes:
            self.female_suffixes = {"xon", "bonu", "niso", "bibi", "begim", "oy"}
        
        if not self.male_suffixes:
            self.male_suffixes = {"bek", "jon", "boy", "mirzo", "ali", "xoja", "ovich", "evich"}
    
    def _load_name_database(self):
        """Load name database from external JSON file"""
        try:
            data_dir = Path(__file__).parent / "data"
            data_file = data_dir / "uzbek_names.json"
            
            if data_file.exists():
                with open(data_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                # Load female names
                self.female_names = set(name.lower() for name in data.get("female_names", []))
                
                # Load suffixes
                self.female_suffixes = set(suffix.lower() for suffix in data.get("female_suffixes", []))
                self.male_suffixes = set(suffix.lower() for suffix in data.get("male_suffixes", []))
                
                # Load transliteration map
                self.transliteration_map = data.get("transliteration_map", {})
                
                logger.info(f"Loaded {len(self.female_names)} female names from database")
            else:
                logger.warning(f"Name database file not found: {data_file}")
        except Exception as e:
            logger.warning(f"Failed to load name database: {e}")
    
    def normalize_name(self, name: Optional[str]) -> Optional[str]:
        """Normalize name for analysis with improved transliteration handling
        
        Args:
            name: Raw name string
            
        Returns:
            Normalized name or None if invalid
        """
        if not name:
            return None
        
        # Convert to lowercase if not case-sensitive
        if not self.config.name_case_sensitive:
            name = name.lower()
        
        # Strip whitespace
        name = name.strip()
        
        # Remove apostrophes and other punctuation (but keep letters)
        name = re.sub(r"[^\w\s\-]", '', name)
        
        # Handle multiple spaces and hyphens
        name = re.sub(r'[\s\-]+', ' ', name)
        
        # Apply transliteration map for Uzbek/Cyrillic variants
        for old, new in self.transliteration_map.items():
            name = name.replace(old, new)
        
        # Handle multiple spaces again after transliteration
        name = re.sub(r'\s+', ' ', name)
        
        name = name.strip()
        
        if not name:
            return None
        
        return name
    
    def analyze(self, first_name: Optional[str]) -> AnalyzerResult:
        """Analyze a first name and return gender signal
        
        Args:
            first_name: User's first name from Telegram profile
            
        Returns:
            AnalyzerResult with signal (0 or 1)
        """
        normalized_name = self.normalize_name(first_name)
        
        if not normalized_name:
            return AnalyzerResult(
                signal=0,
                analyzer_name="name",
                details={"reason": "empty_or_invalid_name"}
            )
        
        # Extract first word (handle multi-word names)
        first_word = normalized_name.split()[0]
        
        # Check against female name database first
        if first_word in self.female_names:
            return AnalyzerResult(
                signal=1,
                analyzer_name="name",
                details={
                    "matched_pattern": "database_name",
                    "method": "name_database",
                    "name": first_word
                }
            )
        
        # Try gender-guesser if available
        if self.detector:
            try:
                detected_gender = self.detector.get_gender(first_word)
                
                if detected_gender in self.positive_labels:
                    return AnalyzerResult(
                        signal=1,
                        analyzer_name="name",
                        details={
                            "detected_gender": detected_gender,
                            "method": "gender_guesser",
                            "name": first_word
                        }
                    )
                elif detected_gender in ("male", "mostly_male"):
                    return AnalyzerResult(
                        signal=0,
                        analyzer_name="name",
                        details={
                            "detected_gender": detected_gender,
                            "method": "gender_guesser",
                            "name": first_word
                        }
                    )
                # For "andy" (ambiguous), continue to fallback methods
            except Exception as e:
                logger.warning(f"Gender-guesser error for name '{first_word}': {e}")
        
        # Fallback: Check female suffixes
        for suffix in self.female_suffixes:
            if first_word.endswith(suffix):
                return AnalyzerResult(
                    signal=1,
                    analyzer_name="name",
                    details={
                        "matched_pattern": "female_suffix",
                        "suffix": suffix,
                        "method": "suffix_patterns",
                        "name": first_word
                    }
                )
        
        # Negative signals (male indicators)
        for suffix in self.male_suffixes:
            if first_word.endswith(suffix):
                return AnalyzerResult(
                    signal=0,
                    analyzer_name="name",
                    details={
                        "matched_pattern": "male_suffix",
                        "suffix": suffix,
                        "method": "male_patterns",
                        "name": first_word
                    }
                )
        
        # Unknown name - return 0 (no signal)
        return AnalyzerResult(
            signal=0,
            analyzer_name="name",
            details={
                "reason": "unknown_name",
                "name": first_word,
                "method": "no_match"
            }
        )