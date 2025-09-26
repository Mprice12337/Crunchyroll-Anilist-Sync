"""
AniList Authentication Handler
"""

import logging
import webbrowser
from typing import Optional
from urllib.parse import urlencode

import requests

from cache_manager import CacheManager

logger = logging.getLogger(__name__)


class AniListAuth:
    """AniList OAuth authentication handler"""

    def __init__(self, client_id: str, client_secret: str):
        self.client_id = client_id
        self.client_secret = client_secret
        self.access_token = None
        self.user_id = None
        self.user_name = None
        self.cache_manager = CacheManager()

    def authenticate(self) -> bool:
        """Authenticate with AniList using OAuth"""
        logger.info("🔐 Authenticating with AniList...")

        # Try cached authentication first
        if self._try_cached_auth():
            logger.info("✅ Using cached AniList authentication")
            return True

        logger.info("Performing OAuth authentication...")

        try:
            # Step 1: Get authorization code
            auth_url = self._get_authorization_url()
            logger.info(f"🔗 Opening authorization URL: {auth_url}")

            webbrowser.open(auth_url)

            auth_code = input("\n📋 Please enter the authorization code: ").strip()
            if not auth_code:
                logger.error("No authorization code provided")
                return False

            # Step 2: Exchange code for access token
            if not self._exchange_code_for_token(auth_code):
                logger.error("Failed to exchange code for token")
                return False

            # Step 3: Get user information
            if not self._get_user_info():
                logger.error("Failed to get user information")
                return False

            # Step 4: Cache successful authentication
            self._cache_authentication()

            logger.info(f"✅ Successfully authenticated as: {self.user_name}")
            return True

        except Exception as e:
            logger.error(f"AniList authentication failed: {e}")
            return False

    def _try_cached_auth(self) -> bool:
        """Try to use cached authentication"""
        cached_auth = self.cache_manager.load_anilist_auth()
        if not cached_auth:
            return False

        # Set auth data from cache
        self.access_token = cached_auth.get('access_token')
        self.user_id = cached_auth.get('user_id')
        self.user_name = cached_auth.get('user_name')

        # Test if the cached token still works
        if self._test_authentication():
            return True
        else:
            # Clear invalid cache
            self.cache_manager.clear_anilist_auth()
            return False

    def _test_authentication(self) -> bool:
        """Test if current authentication is valid"""
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

        except Exception as e:
            logger.debug(f"Auth test failed: {e}")
            return False

    def _get_authorization_url(self) -> str:
        """Generate OAuth authorization URL"""
        params = {
            'client_id': self.client_id,
            'redirect_uri': 'https://anilist.co/api/v2/oauth/pin',
            'response_type': 'code',
        }
        return f"https://anilist.co/api/v2/oauth/authorize?{urlencode(params)}"

    def _exchange_code_for_token(self, auth_code: str) -> bool:
        """Exchange authorization code for access token"""
        try:
            data = {
                'grant_type': 'authorization_code',
                'client_id': self.client_id,
                'client_secret': self.client_secret,
                'redirect_uri': 'https://anilist.co/api/v2/oauth/pin',
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
                logger.error(f"Token exchange failed: {response.status_code} - {response.text}")
                return False

        except Exception as e:
            logger.error(f"Token exchange error: {e}")
            return False

    def _get_user_info(self) -> bool:
        """Get user information using the access token"""
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
        """Cache current authentication state"""
        try:
            if self.access_token and self.user_id and self.user_name:
                self.cache_manager.save_anilist_auth(
                    access_token=self.access_token,
                    user_id=self.user_id,
                    user_name=self.user_name
                )
                logger.debug("AniList authentication cached successfully")
        except Exception as e:
            logger.error(f"Error caching AniList authentication: {e}")

    def is_authenticated(self) -> bool:
        """Check if currently authenticated"""
        return bool(self.access_token and self.user_id and self.user_name)

    def _execute_auth_query(self, query: str) -> Optional[dict]:
        """Execute a simple GraphQL query for authentication purposes"""
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
                logger.debug(f"Auth query failed: {response.status_code}")
                return None

        except Exception as e:
            logger.debug(f"Error in auth query: {e}")
            return None