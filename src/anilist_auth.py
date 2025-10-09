"""
AniList Authentication Handler with Static Credentials
"""

import logging
import os
from typing import Optional

import requests

from cache_manager import CacheManager

logger = logging.getLogger(__name__)


class AniListAuth:
    """Handles AniList OAuth authentication with static credentials and env-based auth code"""

    # Static OAuth credentials - these are public client credentials
    # Users authorize at: https://anilist.co/api/v2/oauth/authorize?client_id=30142&response_type=code
    CLIENT_ID = "30142"
    CLIENT_SECRET = "du1WygA46RvEIU2c6G1BA5kKPKzIk1GSFrx1soLh"
    REDIRECT_URI = "https://anilist.co/api/v2/oauth/pin"

    def __init__(self):
        self.access_token = None
        self.user_id = None
        self.user_name = None
        self.cache_manager = CacheManager()

    def authenticate(self) -> bool:
        """Authenticate with AniList using cached token or auth code from environment"""
        logger.info("🔐 Authenticating with AniList...")

        # Try cached authentication first
        if self._try_cached_auth():
            logger.info("✅ Using cached AniList authentication")
            return True

        # Try to use auth code from environment variable
        auth_code = os.getenv('ANILIST_AUTH_CODE')
        if not auth_code:
            logger.error("❌ No cached authentication found and ANILIST_AUTH_CODE not set")
            logger.error("Please visit: https://anilist.co/api/v2/oauth/authorize?client_id=30142&response_type=code")
            logger.error("Then set ANILIST_AUTH_CODE environment variable with the code you receive")
            return False

        logger.info("Using ANILIST_AUTH_CODE from environment...")

        try:
            if not self._exchange_code_for_token(auth_code.strip()):
                logger.error("Failed to exchange auth code for token")
                logger.error("The auth code may be expired or invalid")
                logger.error(
                    "Please get a new code from: https://anilist.co/api/v2/oauth/authorize?client_id=30142&response_type=code")
                return False

            if not self._get_user_info():
                logger.error("Failed to get user information")
                return False

            self._cache_authentication()
            logger.info(f"✅ Successfully authenticated as: {self.user_name}")
            return True

        except Exception as e:
            logger.error(f"AniList authentication failed: {e}")
            return False

    def is_authenticated(self) -> bool:
        """Check if currently authenticated"""
        return bool(self.access_token and self.user_id and self.user_name)

    def _try_cached_auth(self) -> bool:
        """Attempt to use cached authentication credentials"""
        cached_auth = self.cache_manager.load_anilist_auth()
        if not cached_auth:
            return False

        self.access_token = cached_auth.get('access_token')
        self.user_id = cached_auth.get('user_id')
        self.user_name = cached_auth.get('user_name')

        if self._test_authentication():
            return True
        else:
            logger.info("Cached authentication is invalid, clearing cache")
            self.cache_manager.clear_anilist_auth()
            return False

    def _test_authentication(self) -> bool:
        """Verify that current authentication is still valid"""
        try:
            query = """
            query {
                Viewer {
                    id
                    name
                }
            }
            """
            result = self._execute_auth_query(query)
            return result and 'data' in result and 'Viewer' in result['data']

        except Exception:
            return False

    def _exchange_code_for_token(self, auth_code: str) -> bool:
        """Exchange authorization code for access token"""
        try:
            data = {
                'grant_type': 'authorization_code',
                'client_id': self.CLIENT_ID,
                'client_secret': self.CLIENT_SECRET,
                'redirect_uri': self.REDIRECT_URI,
                'code': auth_code,
            }

            response = requests.post(
                'https://anilist.co/api/v2/oauth/token',
                data=data,
                timeout=30
            )

            if response.status_code == 200:
                token_data = response.json()
                self.access_token = token_data.get('access_token')

                if self.access_token:
                    logger.info("🔑 Access token obtained successfully")
                    return True
                else:
                    logger.error("No access token in response")
                    return False
            else:
                logger.error(f"Token exchange failed: {response.status_code}")
                if response.status_code == 400:
                    logger.error("Invalid or expired authorization code")
                logger.debug(f"Response: {response.text}")
                return False

        except Exception as e:
            logger.error(f"Token exchange error: {e}")
            return False

    def _get_user_info(self) -> bool:
        """Retrieve user information using the access token"""
        try:
            query = """
            query {
                Viewer {
                    id
                    name
                }
            }
            """

            result = self._execute_auth_query(query)

            if result and 'data' in result and 'Viewer' in result['data']:
                viewer = result['data']['Viewer']
                self.user_id = viewer.get('id')
                self.user_name = viewer.get('name')

                if self.user_id and self.user_name:
                    logger.info(f"👤 User info retrieved: {self.user_name} (ID: {self.user_id})")
                    return True

            logger.error("Failed to get user info from API")
            return False

        except Exception as e:
            logger.error(f"Error getting user info: {e}")
            return False

    def _cache_authentication(self) -> None:
        """Save current authentication state to cache"""
        try:
            if self.access_token and self.user_id and self.user_name:
                self.cache_manager.save_anilist_auth(
                    access_token=self.access_token,
                    user_id=self.user_id,
                    user_name=self.user_name
                )
                logger.info("💾 Authentication cached for future use")
        except Exception as e:
            logger.error(f"Error caching AniList authentication: {e}")

    def _execute_auth_query(self, query: str) -> Optional[dict]:
        """Execute a GraphQL query for authentication purposes"""
        try:
            headers = {
                'Content-Type': 'application/json',
                'Accept': 'application/json',
            }

            if self.access_token:
                headers['Authorization'] = f'Bearer {self.access_token}'

            payload = {
                'query': query,
                'variables': {}
            }

            response = requests.post(
                'https://graphql.anilist.co',
                headers=headers,
                json=payload,
                timeout=30
            )

            if response.status_code == 200:
                return response.json()
            else:
                return None

        except Exception:
            return None
