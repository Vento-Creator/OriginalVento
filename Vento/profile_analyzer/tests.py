"""
Unit tests for profile analyzer system
"""
import asyncio
from pathlib import Path
import sys

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))


async def run_tests():
    """Run all tests"""
    print("="*60)
    print("PROFILE ANALYZER UNIT TESTS")
    print("="*60)
    
    # Test Name Analyzer
    print("\n--- Name Analyzer Tests ---")
    from profile_analyzer.config import ProfileAnalyzerConfig
    from profile_analyzer.name_analyzer import NameAnalyzer
    
    config = ProfileAnalyzerConfig()
    name_analyzer = NameAnalyzer(config)
    
    # Test female name detection
    result = name_analyzer.analyze("Madina")
    assert result.signal == 1, "Female name should return 1"
    print("✅ Female name detection: PASS")
    
    # Test male name detection
    result = name_analyzer.analyze("Ali")
    assert result.signal == 0, "Male name should return 0"
    print("✅ Male name detection: PASS")
    
    # Test unknown name
    result = name_analyzer.analyze("UnknownName123")
    assert result.signal == 0, "Unknown name should return 0"
    print("✅ Unknown name handling: PASS")
    
    # Test empty name
    result = name_analyzer.analyze(None)
    assert result.signal == 0, "Empty name should return 0"
    print("✅ Empty name handling: PASS")
    
    # Test Scoring Engine
    print("\n--- Scoring Engine Tests ---")
    from profile_analyzer.scoring_engine import ScoringEngine
    
    engine = ScoringEngine()
    
    # Test simple scoring
    signals = {"name": 1, "username": 0, "bio": 1, "photo": 1}
    score = engine.calculate(signals)
    assert score == 3, "Score should be 3"
    print("✅ Simple scoring: PASS")
    
    # Test all zeros
    signals = {"name": 0, "username": 0, "bio": 0, "photo": 0}
    score = engine.calculate(signals)
    assert score == 0, "All zeros should return 0"
    print("✅ All zeros scoring: PASS")
    
    # Test Profile Analysis model
    print("\n--- Profile Analysis Model Tests ---")
    from profile_analyzer.models import ProfileAnalysis
    
    analysis = ProfileAnalysis(
        user_id=123456,
        name_signal=1,
        username_signal=0,
        bio_signal=1,
        photo_signal=1,
        total_score=3,
        max_score=4
    )
    
    assert analysis.user_id == 123456
    assert analysis.total_score == 3
    assert analysis.max_score == 4
    print("✅ ProfileAnalysis creation: PASS")
    
    # Test threshold checking
    assert analysis.passes_threshold(3) == True
    assert analysis.passes_threshold(4) == False
    print("✅ Threshold checking: PASS")
    
    # Test serialization
    data = analysis.to_dict()
    restored = ProfileAnalysis.from_dict(data)
    assert restored.user_id == analysis.user_id
    assert restored.total_score == analysis.total_score
    print("✅ Serialization/Deserialization: PASS")
    
    print("\n" + "="*60)
    print("ALL UNIT TESTS PASSED")
    print("="*60)


if __name__ == "__main__":
    asyncio.run(run_tests())