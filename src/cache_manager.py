"""
Simplified cache management for authentication and data
"""

import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, Optional, List

logger = logging.getLogger(__name__)

class CacheManager:
    """Manages caching for authentication and application data"""

    def __init__(self, cache_dir: str = "_cache"):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(exist_ok=True)

        # Cache files
        self.auth_cache_file = self.cache_dir / "auth_cache.json"
        self.data_cache_file = self.cache_dir / "data_cache.json"

    def clear_all_cache(self) -> None:
        """Clear all cache files"""
        try:
            cache_files = [
                self.auth_cache_file,
                self.data_cache_file
            ]

            for cache_file in cache_files:
                if cache_file.exists():
                    cache_file.unlink()
                    logger.info(f"Cleared cache file: {cache_file.name}")

            logger.info("All cache cleared successfully")

        except Exception as e:
            logger.error(f"Error clearing cache: {e}")

    def save_crunchyroll_auth(self, cookies: List[Dict], **kwargs) -> bool:
        """Save Crunchyroll authentication data"""
        try:
            auth_data = self._load_auth_cache()

            auth_data['crunchyroll'] = {
                'cookies': cookies,
                'timestamp': datetime.now().isoformat(),
                'expires_at': (datetime.now() + timedelta(days=30)).isoformat(),
                **kwargs
            }

            return self._save_auth_cache(auth_data)

        except Exception as e:
            logger.error(f"Error saving Crunchyroll auth: {e}")
            return False

    def load_crunchyroll_auth(self) -> Optional[Dict[str, Any]]:
        """Load Crunchyroll authentication data"""
        try:
            auth_data = self._load_auth_cache()
            cr_auth = auth_data.get('crunchyroll')

            if not cr_auth:
                return None

            # Check expiration
            expires_at = datetime.fromisoformat(cr_auth.get('expires_at', '2000-01-01'))
            if datetime.now() > expires_at:
                logger.info("Crunchyroll auth cache expired")
                self.clear_crunchyroll_auth()
                return None

            return cr_auth

        except Exception as e:
            logger.error(f"Error loading Crunchyroll auth: {e}")
            return None

    def clear_crunchyroll_auth(self) -> bool:
        """Clear Crunchyroll authentication cache"""
        try:
            auth_data = self._load_auth_cache()
            auth_data.pop('crunchyroll', None)
            return self._save_auth_cache(auth_data)

        except Exception as e:
            logger.error(f"Error clearing Crunchyroll auth: {e}")
            return False

    def save_anilist_auth(self, access_token: str, user_id: int, user_name: str) -> bool:
        """Save AniList authentication data"""
        try:
            auth_data = self._load_auth_cache()

            auth_data['anilist'] = {
                'access_token': access_token,
                'user_id': user_id,
                'user_name': user_name,
                'timestamp': datetime.now().isoformat(),
                'expires_at': (datetime.now() + timedelta(days=365)).isoformat(),
            }

            return self._save_auth_cache(auth_data)

        except Exception as e:
            logger.error(f"Error saving AniList auth: {e}")
            return False

    def load_anilist_auth(self) -> Optional[Dict[str, Any]]:
        """Load AniList authentication data"""
        try:
            auth_data = self._load_auth_cache()
            al_auth = auth_data.get('anilist')

            if not al_auth:
                return None

            # Check expiration
            expires_at = datetime.fromisoformat(al_auth.get('expires_at', '2000-01-01'))
            if datetime.now() > expires_at:
                logger.info("AniList auth cache expired")
                self.clear_anilist_auth()
                return None

            return al_auth

        except Exception as e:
            logger.error(f"Error loading AniList auth: {e}")
            return None

    def clear_anilist_auth(self) -> bool:
        """Clear AniList authentication cache"""
        try:
            auth_data = self._load_auth_cache()
            auth_data.pop('anilist', None)
            return self._save_auth_cache(auth_data)

        except Exception as e:
            logger.error(f"Error clearing AniList auth: {e}")
            return False

    def save_anime_mapping(self, crunchyroll_title: str, anilist_data: Dict) -> None:
        """Save anime title mapping"""
        try:
            data_cache = self._load_data_cache()

            if 'anime_mappings' not in data_cache:
                data_cache['anime_mappings'] = {}

            data_cache['anime_mappings'][crunchyroll_title] = {
                'anilist_data': anilist_data,
                'timestamp': datetime.now().isoformat()
            }

            self._save_data_cache(data_cache)

        except Exception as e:
            logger.error(f"Error saving anime mapping: {e}")

    def get_anime_mapping(self, crunchyroll_title: str) -> Optional[Dict]:
        """Get cached anime mapping"""
        try:
            data_cache = self._load_data_cache()
            mappings = data_cache.get('anime_mappings', {})

            mapping = mappings.get(crunchyroll_title)
            if mapping:
                # Check if mapping is recent (30 days)
                timestamp = datetime.fromisoformat(mapping.get('timestamp', '2000-01-01'))
                if datetime.now() - timestamp < timedelta(days=30):
                    return mapping.get('anilist_data')

            return None

        except Exception as e:
            logger.error(f"Error getting anime mapping: {e}")
            return None

    def _load_auth_cache(self) -> Dict[str, Any]:
        """Load authentication cache from file"""
        try:
            if self.auth_cache_file.exists():
                with open(self.auth_cache_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            return {}

        except Exception as e:
            logger.warning(f"Error loading auth cache: {e}")
            return {}

    def _save_auth_cache(self, data: Dict[str, Any]) -> bool:
        """Save authentication cache to file"""
        try:
            with open(self.auth_cache_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            return True

        except Exception as e:
            logger.error(f"Error saving auth cache: {e}")
            return False

    def _load_data_cache(self) -> Dict[str, Any]:
        """Load data cache from file"""
        try:
            if self.data_cache_file.exists():
                with open(self.data_cache_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            return {}

        except Exception as e:
            logger.warning(f"Error loading data cache: {e}")
            return {}

    def _save_data_cache(self, data: Dict[str, Any]) -> bool:
        """Save data cache to file"""
        try:
            with open(self.data_cache_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            return True

        except Exception as e:
            logger.error(f"Error saving data cache: {e}")
            return False

class AuthCache:
    """Compatibility wrapper for the old AuthCache interface"""

    def __init__(self, cache_dir: str = "_cache"):
        self._cache_manager = CacheManager(cache_dir)

    def save_crunchyroll_auth(self, cookies: List[Dict], **kwargs) -> bool:
        return self._cache_manager.save_crunchyroll_auth(cookies, **kwargs)

    def load_crunchyroll_auth(self) -> Optional[Dict[str, Any]]:
        return self._cache_manager.load_crunchyroll_auth()

    def clear_crunchyroll_auth(self) -> bool:
        return self._cache_manager.clear_crunchyroll_auth()

    def save_anilist_auth(self, access_token: str, user_id: int, user_name: str) -> bool:
        return self._cache_manager.save_anilist_auth(access_token, user_id, user_name)

    def load_anilist_auth(self) -> Optional[Dict[str, Any]]:
        return self._cache_manager.load_anilist_auth()

    def clear_anilist_auth(self) -> bool:
        return self._cache_manager.clear_anilist_auth()

    def clear_all_auth(self) -> bool:
        self._cache_manager.clear_all_cache()
        return True