"""
Generic scoring engine - calculates total score from analyzer signals
"""
from typing import Dict, Any
import logging

logger = logging.getLogger(__name__)


class ScoringEngine:
    """Generic scoring engine that sums analyzer signals
    
    This engine is intentionally simple - it just receives analyzer results
    and calculates the total. It contains no analyzer-specific logic.
    """
    
    def __init__(self):
        self.weighted_mode = False
        self.weights = {
            "name": 1,
            "username": 1,
            "bio": 1,
            "photo": 1
        }
    
    def calculate(self, signals: Dict[str, int]) -> int:
        """Calculate total score from analyzer signals
        
        Args:
            signals: Dictionary of analyzer_name -> signal (0 or 1)
            
        Returns:
            Total score (sum of all signals)
        """
        if self.weighted_mode:
            total = 0
            for analyzer_name, signal in signals.items():
                weight = self.weights.get(analyzer_name, 1)
                total += signal * weight
            return total
        else:
            # Simple mode: just sum the signals
            return sum(signals.values())
    
    def calculate_max_score(self, enabled_analyzers: Dict[str, bool]) -> int:
        """Calculate maximum possible score given enabled analyzers
        
        Args:
            enabled_analyzers: Dictionary of analyzer_name -> enabled (bool)
            
        Returns:
            Maximum possible score
        """
        if self.weighted_mode:
            total = 0
            for analyzer_name, enabled in enabled_analyzers.items():
                if enabled:
                    total += self.weights.get(analyzer_name, 1)
            return total
        else:
            # Simple mode: each enabled analyzer contributes 1 point
            return sum(1 for enabled in enabled_analyzers.values() if enabled)
    
    def set_weights(self, weights: Dict[str, int]):
        """Set custom weights for weighted mode (future compatibility)
        
        Args:
            weights: Dictionary of analyzer_name -> weight
        """
        self.weights = weights.copy()
        logger.info(f"Scoring engine weights updated: {weights}")
    
    def enable_weighted_mode(self, enabled: bool = True):
        """Enable or disable weighted scoring mode (future compatibility)
        
        Args:
            enabled: Whether to use weighted mode
        """
        self.weighted_mode = enabled
        logger.info(f"Weighted mode {'enabled' if enabled else 'disabled'}")