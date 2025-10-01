"""
Authentication Caching Utilities (Legacy)

Note: This file is deprecated. Use CacheManager from cache_manager.py instead.
Kept for backward compatibility with older code.
"""

import json
import os
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)


class AuthCache:
    """Legacy authentication cache handler"""

    def __init__(self, cache_dir: str = "_cache"):
        self.cache_dir = cache_dir
        self.cache_file = os.path.join(cache_dir, "auth_cache.json")
        self._ensure_cache_dir()

    def _ensure_cache_dir(self):
        """Ensure cache directory exists"""
        os.makedirs(self.cache_dir, exist_ok=True)

    def save_crunchyroll_auth(self, cookies: List[Dict[str, Any]],
                              auth_token: Optional[str] = None,
                              user_id: Optional[str] = None) -> bool:
        """Save Crunchyroll authentication data"""
        try:
            cache_data = self._load_cache()

            cache_data['crunchyroll'] = {
                'timestamp': datetime.now().isoformat(),
                'cookies': cookies,
                'auth_token': auth_token,
                'user_id': user_id,
                'expires_at': (datetime.now() + timedelta(days=30)).isoformat()
            }

            self._save_cache(cache_data)
            logger.info("Crunchyroll authentication cached successfully")
            return True

        except Exception as e:
            logger.error(f"Failed to cache Crunchyroll auth: {e}")
            return False

    def load_crunchyroll_auth(self) -> Optional[Dict[str, Any]]:
        """Load cached Crunchyroll authentication data"""
        try:
            cache_data = self._load_cache()
            cr_auth = cache_data.get('crunchyroll')

            if not cr_auth:
                return None

            expires_at_str = cr_auth.get('expires_at', '2000-01-01')
            try:
                expires_at = datetime.fromisoformat(expires_at_str)
                if datetime.now() > expires_at:
                    logger.info("Cached Crunchyroll auth has expired")
                    return None

            except ValueError as e:
                logger.warning(f"Invalid expires_at format: {expires_at_str}")
                return None

            return cr_auth

        except Exception as e:
            logger.error(f"Failed to load Crunchyroll auth: {e}")
            return None

    def save_anilist_auth(self, access_token: str, user_id: int, user_name: str) -> bool:
        """Save AniList authentication data"""
        try:
            cache_data = self._load_cache()

            cache_data['anilist'] = {
                'timestamp': datetime.now().isoformat(),
                'access_token': access_token,
                'user_id': user_id,
                'user_name': user_name,
                'expires_at': (datetime.now() + timedelta(days=365)).isoformat()
            }

            self._save_cache(cache_data)
            logger.info(f"AniList authentication cached for user: {user_name}")
            return True

        except Exception as e:
            logger.error(f"Failed to cache AniList auth: {e}")
            return False

    def load_anilist_auth(self) -> Optional[Dict[str, Any]]:
        """Load cached AniList authentication data"""
        try:
            cache_data = self._load_cache()
            al_auth = cache_data.get('anilist')

            if not al_auth:
                return None

            expires_at = datetime.fromisoformat(al_auth.get('expires_at', '2000-01-01'))
            if datetime.now() > expires_at:
                logger.info("Cached AniList auth has expired")
                self.clear_anilist_auth()
                return None

            logger.info(f"Loaded cached AniList authentication for: {al_auth.get('user_name')}")
            return al_auth

        except Exception as e:
            logger.error(f"Failed to load cached AniList auth: {e}")
            return None

    def clear_crunchyroll_auth(self) -> bool:
        """Clear cached Crunchyroll authentication"""
        try:
            cache_data = self._load_cache()
            if 'crunchyroll' in cache_data:
                del cache_data['crunchyroll']
                self._save_cache(cache_data)
                logger.info("Cleared cached Crunchyroll authentication")
            return True

        except Exception as e:
            logger.error(f"Failed to clear Crunchyroll auth cache: {e}")
            return False

    def clear_anilist_auth(self) -> bool:
        """Clear cached AniList authentication"""
        try:
            cache_data = self._load_cache()
            if 'anilist' in cache_data:
                del cache_data['anilist']
                self._save_cache(cache_data)
                logger.info("Cleared cached AniList authentication")
            return True

        except Exception as e:
            logger.error(f"Failed to clear AniList auth cache: {e}")
            return False

    def clear_all_auth(self) -> bool:
        """Clear all cached authentication data"""
        try:
            cache_data = self._load_cache()
            cache_data.pop('crunchyroll', None)
            cache_data.pop('anilist', None)
            self._save_cache(cache_data)
            logger.info("Cleared all cached authentication data")
            return True

        except Exception as e:
            logger.error(f"Failed to clear auth cache: {e}")
            return False

    def is_crunchyroll_auth_valid(self) -> bool:
        """Check if cached Crunchyroll auth is still valid"""
        auth_data = self.load_crunchyroll_auth()
        return auth_data is not None

    def is_anilist_auth_valid(self) -> bool:
        """Check if cached AniList auth is still valid"""
        auth_data = self.load_anilist_auth()
        return auth_data is not None

    def _load_cache(self) -> Dict[str, Any]:
        """Load cache from file"""
        try:
            if os.path.exists(self.cache_file):
                with open(self.cache_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            else:
                return {}

        except Exception as e:
            logger.warning(f"Failed to load cache file: {e}")
            return {}

    def _save_cache(self, cache_data: Dict[str, Any]):
        """Save cache to file"""
        try:
            with open(self.cache_file, 'w', encoding='utf-8') as f:
                json.dump(cache_data, f, indent=2, ensure_ascii=False)

        except Exception as e:
            logger.error(f"Failed to save cache file: {e}")
            raise