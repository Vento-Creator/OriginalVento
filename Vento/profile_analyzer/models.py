"""
Data models for the profile analyzer system
"""
from dataclasses import dataclass, field
from typing import Dict, Any, Optional
from datetime import datetime
import time


@dataclass
class AnalyzerResult:
    """Result from a single analyzer
    
    Each analyzer returns a signal (0 or 1) and optional diagnostic details.
    """
    signal: int  # 0 or 1
    analyzer_name: str
    details: Dict[str, Any] = field(default_factory=dict)
    model_version: str = "v1"
    timestamp: float = field(default_factory=time.time)
    
    def __post_init__(self):
        """Validate signal is 0 or 1"""
        if self.signal not in (0, 1):
            raise ValueError(f"Signal must be 0 or 1, got {self.signal}")


@dataclass
class ProfileAnalysis:
    """Complete profile analysis result
    
    Contains individual analyzer signals, total score, and diagnostic information.
    """
    user_id: int
    name_signal: int = 0
    username_signal: int = 0
    bio_signal: int = 0
    photo_signal: int = 0
    total_score: int = 0
    max_score: int = 4
    details: Dict[str, Any] = field(default_factory=dict)
    analyzer_version: str = "v1"
    timestamp: float = field(default_factory=time.time)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for storage/transmission"""
        return {
            "user_id": self.user_id,
            "name_signal": self.name_signal,
            "username_signal": self.username_signal,
            "bio_signal": self.bio_signal,
            "photo_signal": self.photo_signal,
            "total_score": self.total_score,
            "max_score": self.max_score,
            "details": self.details,
            "analyzer_version": self.analyzer_version,
            "timestamp": self.timestamp
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ProfileAnalysis':
        """Create from dictionary"""
        return cls(
            user_id=data["user_id"],
            name_signal=data.get("name_signal", 0),
            username_signal=data.get("username_signal", 0),
            bio_signal=data.get("bio_signal", 0),
            photo_signal=data.get("photo_signal", 0),
            total_score=data.get("total_score", 0),
            max_score=data.get("max_score", 4),
            details=data.get("details", {}),
            analyzer_version=data.get("analyzer_version", "v1"),
            timestamp=data.get("timestamp", time.time())
        )
    
    def get_explanation(self) -> str:
        """Generate human-readable explanation of the score"""
        signals = []
        if self.name_signal:
            signals.append("+1 Name signal")
        if self.username_signal:
            signals.append("+1 Username signal")
        if self.bio_signal:
            signals.append("+1 Bio signal")
        if self.photo_signal:
            signals.append("+1 Photo signal")
        
        if not signals:
            signals = ["No signals detected"]
        
        return f"Score: {self.total_score}/{self.max_score}\n\n" + "\n".join(signals)
    
    def passes_threshold(self, minimum_score: int) -> bool:
        """Check if profile meets minimum score requirement"""
        return self.total_score >= minimum_score