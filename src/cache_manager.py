"""Cache management utilities"""
import os
import logging
from typing import Dict, Any
from auth_cache import AuthCache

logger = logging.getLogger(__name__)

class CacheManager:
    def __init__(self, cache_dir: str = "_cache"):
        self.cache_dir = cache_dir
        self.auth_cache = AuthCache(cache_dir)

    def clear_all_cache(self):
        """Clear all cache data"""
        try:
            self.auth_cache.clear_all_auth()

            # Clear other cache files if they exist
            cache_files = ['sync_cache.json', 'auth_cache.json']
            for cache_file in cache_files:
                cache_path = os.path.join(self.cache_dir, cache_file)
                if os.path.exists(cache_path):
                    os.remove(cache_path)
                    logger.info(f"Removed cache file: {cache_file}")

            logger.info("All cache cleared successfully")

        except Exception as e:
            logger.error(f"Failed to clear cache: {e}")

    def get_cache_status(self) -> Dict[str, Any]:
        """Get current cache status"""
        status = {
            'crunchyroll_auth_valid': self.auth_cache.is_crunchyroll_auth_valid(),
            'anilist_auth_valid': self.auth_cache.is_anilist_auth_valid(),
            'cache_files': []
        }

        # Check for cache files
        if os.path.exists(self.cache_dir):
            for file in os.listdir(self.cache_dir):
                if file.endswith('.json'):
                    file_path = os.path.join(self.cache_dir, file)
                    file_size = os.path.getsize(file_path)
                    status['cache_files'].append({
                        'name': file,
                        'size': file_size,
                        'exists': True
                    })

        return status

    def print_cache_status(self):
        """Print current cache status"""
        status = self.get_cache_status()

        print("\n=== Cache Status ===")
        print(f"Crunchyroll Auth Valid: {'✅' if status['crunchyroll_auth_valid'] else '❌'}")
        print(f"AniList Auth Valid: {'✅' if status['anilist_auth_valid'] else '❌'}")

        if status['cache_files']:
            print("\nCache Files:")
            for file_info in status['cache_files']:
                print(f"  - {file_info['name']}: {file_info['size']} bytes")
        else:
            print("\nNo cache files found")
        print("==================\n")

# CLI utility for cache management
if __name__ == "__main__":
    import sys

    cache_manager = CacheManager()

    if len(sys.argv) > 1:
        command = sys.argv[1].lower()

        if command == "status":
            cache_manager.print_cache_status()
        elif command == "clear":
            cache_manager.clear_all_cache()
            print("Cache cleared!")
        else:
            print("Usage: python -m src.cache_manager [status|clear]")
    else:
        cache_manager.print_cache_status()