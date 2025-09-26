"""
Enhanced AniList client - main orchestrating class
"""

import logging
from typing import Optional, Dict, Any, List

from anilist_auth import AniListAuth
from anilist_api import AniListAPI

logger = logging.getLogger(__name__)


class AniListClient:
    """Enhanced AniList client that orchestrates authentication and API operations"""

    def __init__(self, client_id: str, client_secret: str):
        self.client_id = client_id
        self.client_secret = client_secret

        # Initialize components
        self.auth = AniListAuth(client_id, client_secret)
        self.api = AniListAPI()

    def authenticate(self) -> bool:
        """Authenticate with AniList using OAuth"""
        return self.auth.authenticate()

    def search_anime(self, title: str) -> Optional[List[Dict[str, Any]]]:
        """Search for anime by title with rate limiting"""
        if not self.auth.is_authenticated():
            logger.error("Not authenticated! Call authenticate() first.")
            return None

        return self.api.search_anime(title, self.auth.access_token)

    def update_anime_progress(self, anime_id: int, progress: int, status: Optional[str] = None) -> bool:
        """Update anime progress on AniList with rate limiting"""
        if not self.auth.is_authenticated():
            logger.error("Not authenticated! Call authenticate() first.")
            return False

        return self.api.update_anime_progress(anime_id, progress, self.auth.access_token, status)

    @property
    def access_token(self) -> Optional[str]:
        """Get current access token"""
        return self.auth.access_token

    @property
    def user_id(self) -> Optional[int]:
        """Get current user ID"""
        return self.auth.user_id

    @property
    def user_name(self) -> Optional[str]:
        """Get current user name"""
        return self.auth.user_name

    @property
    def rate_limiter(self):
        """Access to rate limiter for status reporting"""
        return self.api.rate_limiter

    def is_authenticated(self) -> bool:
        """Check if currently authenticated"""
        return self.auth.is_authenticated()