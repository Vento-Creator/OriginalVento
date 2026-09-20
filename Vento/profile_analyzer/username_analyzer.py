"""
Username analyzer - lightweight heuristic analysis of Telegram usernames
"""
import logging
import re
from typing import Optional, List
from .models import AnalyzerResult
from .config import ProfileAnalyzerConfig

logger = logging.getLogger(__name__)


class UsernameAnalyzer:
    """Analyzer for detecting gender signals from usernames"""
    
    def __init__(self, config: ProfileAnalyzerConfig):
        self.config = config
        
        # Default Uzbek female name keywords for username matching
        self.default_keywords = [
            "madina", "sevinch", "malika", "nilufar", "gulnora", "dilnoza",
            "nargiza", "zilola", "kamola", "mohira", "nodira", "sabina",
            "jamila", "aziza", "anora", "barno", "dildora", "elnora",
            "feruza", "gulbahor", "hilola", "jasmin", "komila", "lola",
            "munira", "nasiba", "parvin", "rohila", "shahnoza", "sitora",
            "surayyo", "xurshida", "yulduz", "zalola", "madina", "sevara",
            "shahlo", "shaxlo", "xayriniso", "yorqinoy", "zarina", "zuhra"
        ]
        
        # Keywords from config or defaults
        self.keywords = config.username_keywords or self.default_keywords
        
        # Common patterns in female usernames
        self.patterns = config.username_patterns or [
            r".*_?girl\d*",           # ends with "girl" + numbers
            r".*_?lady\d*",           # ends with "lady" + numbers  
            r".*_?queen\d*",         # ends with "queen" + numbers
            r".*_?princess\d*",      # ends with "princess" + numbers
            r".*women\d*",           # contains "women" + numbers
            r"[a-z]+_?200[0-9]",     # common birth year pattern
            r"[a-z]+_?200[0-9]{2}"   # alternative birth year pattern
        ]
    
    def normalize_username(self, username: Optional[str]) -> Optional[str]:
        """Normalize username for analysis with improved handling
        
        Args:
            username: Raw username string (without @)
            
        Returns:
            Normalized username or None if invalid
        """
        if not username:
            return None
        
        # Remove @ if present
        username = username.lstrip('@')
        
        # Convert to lowercase
        username = username.lower()
        
        # Strip whitespace
        username = username.strip()
        
        # Normalize separators: replace repeated underscores, dots, hyphens with single underscore
        username = re.sub(r'[_\.\-]+', '_', username)
        
        # Remove trailing/leading underscores
        username = username.strip('_')
        
        # Remove trailing numbers (common birth years)
        username = re.sub(r'_?\d{4}$', '', username)
        
        # Remove single trailing digits
        username = re.sub(r'_?\d$', '', username)
        
        if not username:
            return None
        
        return username
    
    def analyze(self, username: Optional[str]) -> AnalyzerResult:
        """Analyze a username and return gender signal
        
        Args:
            username: User's username from Telegram profile
            
        Returns:
            AnalyzerResult with signal (0 or 1)
        """
        normalized_username = self.normalize_username(username)
        
        if not normalized_username:
            return AnalyzerResult(
                signal=0,
                analyzer_name="username",
                details={"reason": "empty_or_invalid_username"}
            )
        
        # Check for keyword matches
        for keyword in self.keywords:
            if keyword.lower() in normalized_username:
                return AnalyzerResult(
                    signal=1,
                    analyzer_name="username",
                    details={
                        "matched_keyword": keyword,
                        "method": "keyword_match",
                        "username": normalized_username
                    }
                )
        
        # Check for pattern matches
        for pattern in self.patterns:
            if re.search(pattern, normalized_username, re.IGNORECASE):
                return AnalyzerResult(
                    signal=1,
                    analyzer_name="username",
                    details={
                        "matched_pattern": pattern,
                        "method": "pattern_match",
                        "username": normalized_username
                    }
                )
        
        # No match found
        return AnalyzerResult(
            signal=0,
            analyzer_name="username",
            details={
                "reason": "no_match",
                "username": normalized_username,
                "method": "no_match"
            }
        )