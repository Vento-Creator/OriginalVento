"""
Benchmark script for profile analyzer - tests resource usage and performance
"""
import asyncio
import time
import psutil
import os
import sys
from pathlib import Path
from typing import Dict, Any, List
import logging

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ProfileAnalyzerBenchmark:
    """Benchmark suite for profile analyzer components"""
    
    def __init__(self):
        self.results = {}
        self.process = psutil.Process()
    
    def get_memory_usage(self) -> float:
        """Get current memory usage in MB"""
        return self.process.memory_info().rss / 1024 / 1024
    
    def get_cpu_usage(self) -> float:
        """Get current CPU usage percentage"""
        return self.process.cpu_percent()
    
    def benchmark_startup(self) -> Dict[str, Any]:
        """Benchmark startup time and memory"""
        logger.info("Benchmarking startup...")
        
        start_memory = self.get_memory_usage()
        start_time = time.time()
        
        # Import and initialize components
        from profile_analyzer.config import ProfileAnalyzerConfig
        from profile_analyzer.profile_analyzer import ProfileAnalyzer
        
        config = ProfileAnalyzerConfig.from_env()
        analyzer = ProfileAnalyzer(config)
        
        end_time = time.time()
        end_memory = self.get_memory_usage()
        
        result = {
            "startup_time": end_time - start_time,
            "startup_memory": end_memory - start_memory,
            "total_memory": end_memory
        }
        
        logger.info(f"Startup benchmark: {result}")
        return result
    
    def benchmark_name_analyzer(self) -> Dict[str, Any]:
        """Benchmark name analyzer performance"""
        logger.info("Benchmarking name analyzer...")
        
        from profile_analyzer.name_analyzer import NameAnalyzer
        from profile_analyzer.config import ProfileAnalyzerConfig
        
        config = ProfileAnalyzerConfig.from_env()
        analyzer = NameAnalyzer(config)
        
        test_names = [
            "Madina", "Sevinch", "Ali", "John", "unknown_name",
            "Gulnora", "Bobur", "Nilufar", "Jamshid", "Dilnoza"
        ]
        
        start_time = time.time()
        start_memory = self.get_memory_usage()
        
        results = []
        for name in test_names:
            result = analyzer.analyze(name)
            results.append(result)
        
        end_time = time.time()
        end_memory = self.get_memory_usage()
        
        avg_time = (end_time - start_time) / len(test_names)
        
        result = {
            "total_names": len(test_names),
            "total_time": end_time - start_time,
            "avg_time_per_name": avg_time,
            "memory_used": end_memory - start_memory,
            "results_summary": sum(1 for r in results if r.signal == 1)
        }
        
        logger.info(f"Name analyzer benchmark: {result}")
        return result
    
    def benchmark_username_analyzer(self) -> Dict[str, Any]:
        """Benchmark username analyzer performance"""
        logger.info("Benchmarking username analyzer...")
        
        from profile_analyzer.username_analyzer import UsernameAnalyzer
        from profile_analyzer.config import ProfileAnalyzerConfig
        
        config = ProfileAnalyzerConfig.from_env()
        analyzer = UsernameAnalyzer(config)
        
        test_usernames = [
            "madina_2008", "sevinch01", "ali_khan", "john_doe",
            "gulnora_x", "bobur_uz", "nilufar_girl", "jamshid_tashkent"
        ]
        
        start_time = time.time()
        start_memory = self.get_memory_usage()
        
        results = []
        for username in test_usernames:
            result = analyzer.analyze(username)
            results.append(result)
        
        end_time = time.time()
        end_memory = self.get_memory_usage()
        
        avg_time = (end_time - start_time) / len(test_usernames)
        
        result = {
            "total_usernames": len(test_usernames),
            "total_time": end_time - start_time,
            "avg_time_per_username": avg_time,
            "memory_used": end_memory - start_memory,
            "results_summary": sum(1 for r in results if r.signal == 1)
        }
        
        logger.info(f"Username analyzer benchmark: {result}")
        return result
    
    def benchmark_bio_analyzer(self) -> Dict[str, Any]:
        """Benchmark bio analyzer performance"""
        logger.info("Benchmarking bio analyzer...")
        
        from profile_analyzer.bio_analyzer import BioAnalyzer
        from profile_analyzer.config import ProfileAnalyzerConfig
        
        config = ProfileAnalyzerConfig.from_env()
        analyzer = BioAnalyzer(config)
        
        test_bios = [
            "👸 19 years old | Tashkent",
            "Software engineer | 25 years old",
            "Student | born 2005",
            "Just a regular person",
            "🌸 20 | female | UZ"
        ]
        
        start_time = time.time()
        start_memory = self.get_memory_usage()
        
        results = []
        for bio in test_bios:
            result = analyzer.analyze(bio)
            results.append(result)
        
        end_time = time.time()
        end_memory = self.get_memory_usage()
        
        avg_time = (end_time - start_time) / len(test_bios)
        
        result = {
            "total_bios": len(test_bios),
            "total_time": end_time - start_time,
            "avg_time_per_bio": avg_time,
            "memory_used": end_memory - start_memory,
            "results_summary": sum(1 for r in results if r.signal == 1)
        }
        
        logger.info(f"Bio analyzer benchmark: {result}")
        return result
    
    def benchmark_photo_analyzer_basic(self) -> Dict[str, Any]:
        """Benchmark photo analyzer with basic features (no ML)"""
        logger.info("Benchmarking photo analyzer (basic features)...")
        
        from profile_analyzer.photo_analyzer import PhotoAnalyzer
        from profile_analyzer.config import ProfileAnalyzerConfig
        
        config = ProfileAnalyzerConfig.from_env()
        analyzer = PhotoAnalyzer(config)
        
        # Create a dummy image for testing
        from PIL import Image
        import io
        
        # Create test images of different sizes
        test_images = []
        for size in [(100, 100), (200, 200), (400, 400)]:
            img = Image.new('RGB', size, color='red')
            img_bytes = io.BytesIO()
            img.save(img_bytes, format='JPEG')
            img_bytes.seek(0)
            test_images.append(img_bytes.read())
        
        start_time = time.time()
        start_memory = self.get_memory_usage()
        
        results = []
        for img_bytes in test_images:
            result = asyncio.run(analyzer.analyze(img_bytes))
            results.append(result)
        
        end_time = time.time()
        end_memory = self.get_memory_usage()
        
        avg_time = (end_time - start_time) / len(test_images)
        
        result = {
            "total_images": len(test_images),
            "total_time": end_time - start_time,
            "avg_time_per_image": avg_time,
            "memory_used": end_memory - start_memory,
            "results_summary": sum(1 for r in results if r.signal == 1)
        }
        
        logger.info(f"Photo analyzer benchmark (basic): {result}")
        return result
    
    def benchmark_full_pipeline(self) -> Dict[str, Any]:
        """Benchmark full profile analysis pipeline"""
        logger.info("Benchmarking full pipeline...")
        
        from profile_analyzer.profile_analyzer import ProfileAnalyzer
        from profile_analyzer.config import ProfileAnalyzerConfig
        
        config = ProfileAnalyzerConfig.from_env()
        analyzer = ProfileAnalyzer(config)
        
        # Create simple mock user objects
        class MockUser:
            def __init__(self, user_id, first_name, username, bio):
                self.id = user_id
                self.first_name = first_name
                self.username = username
                self.bio = bio
        
        mock_users = [
            MockUser(123456, "Madina", "madina_2008", "👸 19 years old"),
            MockUser(123457, "Ali", "ali_khan", "Software engineer")
        ]
        
        # Mock client that returns None for photos
        class MockClient:
            async def get_profile_photos(self, user_id, limit=1):
                return []
            async def download_media(self, photo, in_memory=False):
                return None
        
        start_time = time.time()
        start_memory = self.get_memory_usage()
        
        results = []
        for user in mock_users:
            mock_client = MockClient()
            result = asyncio.run(analyzer.analyze(user, mock_client))
            results.append(result)
        
        end_time = time.time()
        end_memory = self.get_memory_usage()
        
        avg_time = (end_time - start_time) / len(mock_users)
        
        result = {
            "total_users": len(mock_users),
            "total_time": end_time - start_time,
            "avg_time_per_user": avg_time,
            "memory_used": end_memory - start_memory,
            "results_summary": [r.total_score for r in results]
        }
        
        logger.info(f"Full pipeline benchmark: {result}")
        return result
    
    def run_all_benchmarks(self) -> Dict[str, Any]:
        """Run all benchmarks and return combined results"""
        logger.info("Starting comprehensive benchmark suite...")
        
        results = {
            "startup": self.benchmark_startup(),
            "name_analyzer": self.benchmark_name_analyzer(),
            "username_analyzer": self.benchmark_username_analyzer(),
            "bio_analyzer": self.benchmark_bio_analyzer(),
            "photo_analyzer_basic": self.benchmark_photo_analyzer_basic(),
            "full_pipeline": self.benchmark_full_pipeline()
        }
        
        # System info
        results["system_info"] = {
            "cpu_count": psutil.cpu_count(),
            "memory_total_gb": psutil.virtual_memory().total / 1024 / 1024 / 1024,
            "memory_available_gb": psutil.virtual_memory().available / 1024 / 1024 / 1024
        }
        
        logger.info("Benchmark suite completed. Results:")
        for benchmark_name, benchmark_result in results.items():
            logger.info(f"{benchmark_name}: {benchmark_result}")
        
        return results


def main():
    """Main benchmark entry point"""
    logger.info("Profile Analyzer Benchmark Suite")
    logger.info("=" * 50)
    
    benchmark = ProfileAnalyzerBenchmark()
    results = benchmark.run_all_benchmarks()
    
    # Save results to file
    from pathlib import Path
    import json
    
    results_path = Path(__file__).parent.parent / "data" / "benchmark_results.json"
    results_path.parent.mkdir(exist_ok=True)
    
    with open(results_path, 'w') as f:
        json.dump(results, f, indent=2)
    
    logger.info(f"Benchmark results saved to {results_path}")
    
    # Print summary
    print("\n" + "=" * 50)
    print("BENCHMARK SUMMARY")
    print("=" * 50)
    print(f"Startup Time: {results['startup']['startup_time']:.3f}s")
    print(f"Startup Memory: {results['startup']['startup_memory']:.2f}MB")
    print(f"Name Analyzer (avg): {results['name_analyzer']['avg_time_per_name']*1000:.2f}ms")
    print(f"Username Analyzer (avg): {results['username_analyzer']['avg_time_per_username']*1000:.2f}ms")
    print(f"Bio Analyzer (avg): {results['bio_analyzer']['avg_time_per_bio']*1000:.2f}ms")
    print(f"Photo Analyzer (avg): {results['photo_analyzer_basic']['avg_time_per_image']*1000:.2f}ms")
    print(f"Full Pipeline (avg): {results['full_pipeline']['avg_time_per_user']*1000:.2f}ms")
    print("=" * 50)


if __name__ == "__main__":
    main()