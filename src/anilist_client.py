"""
Enhanced AniList API client with proper rate limiting implementation
"""

import json
import logging
import time
import webbrowser
from typing import Optional, Dict, Any, List
from urllib.parse import urlencode

import requests

from cache_manager import CacheManager

logger = logging.getLogger(__name__)

class RateLimitTracker:
    """Track rate limit information from AniList API responses"""

    def __init__(self):
        self.limit = 90  # Default limit, will be updated from headers
        self.remaining = 90
        self.reset_time = None
        self.last_request_time = 0

    def update_from_headers(self, headers: Dict[str, str]) -> None:
        """Update rate limit info from response headers"""
        try:
            if 'X-RateLimit-Limit' in headers:
                self.limit = int(headers['X-RateLimit-Limit'])

            if 'X-RateLimit-Remaining' in headers:
                self.remaining = int(headers['X-RateLimit-Remaining'])

            if 'X-RateLimit-Reset' in headers:
                self.reset_time = int(headers['X-RateLimit-Reset'])

            self.last_request_time = time.time()

        except (ValueError, TypeError) as e:
            logger.debug(f"Error parsing rate limit headers: {e}")

    def should_wait(self) -> tuple[bool, float]:
        """Check if we should wait before making a request"""
        current_time = time.time()

        # If we have very few requests remaining, be conservative
        if self.remaining <= 2:
            if self.reset_time and current_time < self.reset_time:
                wait_time = self.reset_time - current_time
                return True, wait_time

        # Implement basic pacing - don't make requests faster than 1 per 2 seconds
        # This helps avoid burst limits
        time_since_last = current_time - self.last_request_time
        if time_since_last < 2.0:
            wait_time = 2.0 - time_since_last
            return True, wait_time

        return False, 0.0

    def get_status_info(self) -> str:
        """Get human-readable status info"""
        if self.reset_time:
            reset_in = max(0, self.reset_time - time.time())
            return f"Rate limit: {self.remaining}/{self.limit} (resets in {reset_in:.0f}s)"
        else:
            return f"Rate limit: {self.remaining}/{self.limit}"


class AniListClient:
    """Enhanced AniList API client with proper rate limiting"""

    def __init__(self, client_id: str, client_secret: str):
        self.client_id = client_id
        self.client_secret = client_secret
        self.access_token = None
        self.user_id = None
        self.user_name = None
        self.graphql_url = "https://graphql.anilist.co"
        self.cache_manager = CacheManager()

        # Rate limiting tracker
        self.rate_limiter = RateLimitTracker()

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

    def search_anime(self, title: str) -> Optional[List[Dict[str, Any]]]:
        """Search for anime by title with rate limiting"""
        try:
            query = """
            query ($search: String) {
                Page(perPage: 10) {
                    media(search: $search, type: ANIME) {
                        id
                        title {
                            romaji
                            english
                            native
                        }
                        synonyms
                        episodes
                        status
                        format
                        startDate {
                            year
                            month
                            day
                        }
                    }
                }
            }
            """

            variables = {'search': title}
            result = self._execute_query(query, variables)

            if result and 'data' in result and 'Page' in result['data']:
                media_list = result['data']['Page']['media']
                logger.debug(f"Found {len(media_list)} results for '{title}'")
                return media_list

            logger.warning(f"No search results for: {title}")
            return None

        except Exception as e:
            logger.error(f"Search failed for '{title}': {e}")
            return None

    def update_anime_progress(self, anime_id: int, progress: int, status: Optional[str] = None) -> bool:
        """Update anime progress on AniList with rate limiting"""
        try:
            # Build mutation based on what we're updating
            variables = {
                'mediaId': anime_id,
                'progress': progress
            }

            mutation_parts = ['mediaId: $mediaId', 'progress: $progress']
            variable_parts = ['$mediaId: Int', '$progress: Int']

            if status:
                variables['status'] = status
                mutation_parts.append('status: $status')
                variable_parts.append('$status: MediaListStatus')

            mutation = f"""
            mutation ({', '.join(variable_parts)}) {{
                SaveMediaListEntry({', '.join(mutation_parts)}) {{
                    id
                    progress
                    status
                    media {{
                        title {{
                            romaji
                        }}
                    }}
                }}
            }}
            """

            result = self._execute_query(mutation, variables)

            if result and 'data' in result and 'SaveMediaListEntry' in result['data']:
                entry = result['data']['SaveMediaListEntry']
                media_title = entry.get('media', {}).get('title', {}).get('romaji', 'Unknown')
                updated_progress = entry.get('progress', progress)
                updated_status = entry.get('status', 'Unknown')

                logger.info(f"✅ Updated '{media_title}': {updated_progress} episodes ({updated_status})")
                return True
            else:
                logger.error(f"Failed to update anime {anime_id}")
                if result and 'errors' in result:
                    logger.error(f"GraphQL errors: {result['errors']}")
                return False

        except Exception as e:
            logger.error(f"Error updating anime {anime_id}: {e}")
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

            result = self._execute_query(query)
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

            result = self._execute_query(query)

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

    def _execute_query(self, query: str, variables: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        """Execute a GraphQL query with enhanced rate limiting"""
        max_retries = 3
        retry_count = 0

        while retry_count < max_retries:
            try:
                # Check if we should wait before making the request
                should_wait, wait_time = self.rate_limiter.should_wait()
                if should_wait:
                    logger.info(f"⏱️ Rate limiting: waiting {wait_time:.1f}s before request")
                    logger.debug(self.rate_limiter.get_status_info())
                    time.sleep(wait_time)

                headers = {
                    'Content-Type': 'application/json',
                    'Accept': 'application/json',
                }

                if self.access_token:
                    headers['Authorization'] = f'Bearer {self.access_token}'

                payload = {
                    'query': query,
                    'variables': variables or {}
                }

                logger.debug(f"Making AniList API request (attempt {retry_count + 1}/{max_retries})")

                response = requests.post(
                    self.graphql_url,
                    headers=headers,
                    json=payload,
                    timeout=30
                )

                # Update rate limit tracking from response headers
                self.rate_limiter.update_from_headers(response.headers)

                if response.status_code == 200:
                    result = response.json()

                    # Check for GraphQL errors
                    if 'errors' in result:
                        logger.warning(f"GraphQL errors in response: {result['errors']}")

                    # Log current rate limit status
                    if logger.isEnabledFor(logging.DEBUG):
                        logger.debug(self.rate_limiter.get_status_info())

                    return result

                elif response.status_code == 429:
                    # Rate limit exceeded - handle according to AniList documentation
                    retry_after = response.headers.get('Retry-After', '60')
                    try:
                        wait_seconds = int(retry_after)
                    except ValueError:
                        wait_seconds = 60  # Default to 1 minute

                    logger.warning(f"🚫 Rate limit exceeded! Waiting {wait_seconds} seconds...")
                    logger.info(f"Rate limit status: {self.rate_limiter.get_status_info()}")

                    time.sleep(wait_seconds)

                    # Update our rate limiter with the fact that we hit the limit
                    self.rate_limiter.remaining = 0
                    if 'X-RateLimit-Reset' in response.headers:
                        try:
                            self.rate_limiter.reset_time = int(response.headers['X-RateLimit-Reset'])
                        except ValueError:
                            pass

                    retry_count += 1
                    continue

                elif response.status_code in [500, 502, 503, 504]:
                    # Server errors - retry with exponential backoff
                    wait_time = (2 ** retry_count) * 1  # 1s, 2s, 4s
                    logger.warning(f"🔧 Server error {response.status_code}, retrying in {wait_time}s...")
                    time.sleep(wait_time)
                    retry_count += 1
                    continue

                else:
                    logger.error(f"GraphQL request failed: {response.status_code} - {response.text}")
                    return None

            except requests.exceptions.Timeout:
                wait_time = (2 ** retry_count) * 2  # 2s, 4s, 8s
                logger.warning(f"⏰ Request timeout, retrying in {wait_time}s...")
                time.sleep(wait_time)
                retry_count += 1
                continue

            except requests.exceptions.RequestException as e:
                wait_time = (2 ** retry_count) * 2
                logger.warning(f"🔌 Network error: {e}, retrying in {wait_time}s...")
                time.sleep(wait_time)
                retry_count += 1
                continue

            except Exception as e:
                logger.error(f"Unexpected error in GraphQL query: {e}")
                return None

        logger.error(f"GraphQL request failed after {max_retries} retries")
        return None

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