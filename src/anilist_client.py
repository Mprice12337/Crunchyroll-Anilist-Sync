"""AniList API client for OAuth authentication and anime updates using GraphQL"""
import requests
import json
import time
import webbrowser
from typing import Optional, Dict, Any, List
from urllib.parse import urlencode, parse_qs, urlparse
import logging

from auth_cache import AuthCache

logger = logging.getLogger(__name__)

class AniListClient:
    def __init__(self, client_id: str, client_secret: str):
        self.client_id = client_id
        self.client_secret = client_secret
        self.access_token = None
        self.user_id = None
        self.user_name = None
        self.graphql_url = "https://graphql.anilist.co"
        self.auth_cache = AuthCache()

    def authenticate(self) -> bool:
        """Perform OAuth authentication flow with caching"""
        # Try cached authentication first
        if self.try_cached_auth():
            return True
        
        logger.info("Cached AniList auth failed, proceeding with OAuth flow...")
        
        try:
            # Step 1: Get authorization code using Authorization Code Grant
            auth_url = self._get_authorization_url()
            logger.info(f"🔐 Please visit this URL to authorize the application:")
            logger.info(f"📱 {auth_url}")

            # Open browser automatically
            webbrowser.open(auth_url)

            # Get authorization code from user
            auth_code = input("\n📋 Please enter the authorization code from the redirect URL: ").strip()

            if not auth_code:
                logger.error("❌ No authorization code provided")
                return False

            # Step 2: Exchange code for access token
            if self._exchange_code_for_token(auth_code):
                # Step 3: Get user info using GraphQL
                if self._get_user_info_graphql():
                    # Cache successful authentication
                    self._cache_authentication()
                    logger.info(f"✅ Successfully authenticated with AniList as: {self.user_name}")
                    return True

            return False

        except Exception as e:
            logger.error(f"AniList authentication failed: {e}")
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

            response = requests.post('https://anilist.co/api/v2/oauth/token', data=data)
            
            if response.status_code == 200:
                token_data = response.json()
                self.access_token = token_data.get('access_token')
                
                if self.access_token:
                    logger.info("🔑 Successfully obtained access token")
                    return True
                else:
                    logger.error("❌ No access token in response")
                    return False
            else:
                logger.error(f"❌ Token exchange failed: {response.status_code} - {response.text}")
                return False

        except Exception as e:
            logger.error(f"Token exchange error: {e}")
            return False

    def _get_user_info_graphql(self) -> bool:
        """Get user info using GraphQL Viewer query"""
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
                    logger.info(f"👤 Retrieved user info: {self.user_name} (ID: {self.user_id})")
                    return True
            
            logger.error("❌ Failed to get user info from GraphQL")
            return False
            
        except Exception as e:
            logger.error(f"GraphQL user info query failed: {e}")
            return False

    def _execute_query(self, query: str, variables: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        """Execute a GraphQL query"""
        try:
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
            
            response = requests.post(
                self.graphql_url,
                headers=headers,
                json=payload,
                timeout=30
            )
            
            if response.status_code == 200:
                return response.json()
            else:
                logger.error(f"GraphQL query failed: {response.status_code} - {response.text}")
                return None
                
        except Exception as e:
            logger.error(f"GraphQL query error: {e}")
            return None

    def try_cached_auth(self) -> bool:
        """Try to use cached authentication"""
        logger.info("🔍 Checking for cached AniList authentication...")
        
        cached_auth = self.auth_cache.load_anilist_auth()
        if not cached_auth:
            return False
        
        try:
            # Set auth data from cache
            self.access_token = cached_auth.get('access_token')
            self.user_id = cached_auth.get('user_id')
            self.user_name = cached_auth.get('user_name')
            
            # Test if cached auth still works
            if self._test_cached_auth():
                logger.info(f"✅ Successfully authenticated using cached data for: {self.user_name}")
                return True
            else:
                logger.info("⚠️  Cached AniList authentication is no longer valid")
                self.auth_cache.clear_anilist_auth()
                return False
                
        except Exception as e:
            logger.error(f"Failed to use cached AniList auth: {e}")
            return False

    def _test_cached_auth(self) -> bool:
        """Test if cached authentication still works using GraphQL"""
        try:
            # Simple query to test auth
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
                return True
            else:
                return False
                
        except Exception as e:
            logger.error(f"AniList auth test failed: {e}")
            return False

    def _cache_authentication(self):
        """Cache current authentication state"""
        try:
            if self.access_token and self.user_id and self.user_name:
                self.auth_cache.save_anilist_auth(
                    access_token=self.access_token,
                    user_id=self.user_id,
                    user_name=self.user_name
                )
                logger.info(f"💾 Cached AniList authentication for: {self.user_name}")
            else:
                logger.warning("⚠️  Cannot cache incomplete AniList auth data")
        except Exception as e:
            logger.error(f"Failed to cache AniList authentication: {e}")

    def search_anime(self, title: str) -> Optional[List[Dict[str, Any]]]:
        """Search for anime using GraphQL"""
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
                return result['data']['Page']['media']
            
            return None
            
        except Exception as e:
            logger.error(f"Anime search failed: {e}")
            return None

    def update_anime_status(self, anime_id: int, status: str, progress: int) -> bool:
        """Update anime status and progress on AniList"""

        mutation = """
        mutation ($mediaId: Int, $status: MediaListStatus, $progress: Int) {
            SaveMediaListEntry(mediaId: $mediaId, status: $status, progress: $progress) {
                id
                status
                progress
                media {
                    title {
                        romaji
                    }
                }
            }
        }
        """

        variables = {
            'mediaId': anime_id,
            'status': status,
            'progress': progress
        }

        try:
            response = self._execute_query(mutation, variables)

            if response and 'data' in response and 'SaveMediaListEntry' in response['data']:
                entry = response['data']['SaveMediaListEntry']
                media_title = entry.get('media', {}).get('title', {}).get('romaji', 'Unknown')
                logger.info(f"📝 Updated '{media_title}': {status} - {progress} episodes")
                return True
            else:
                logger.error("❌ Failed to update anime status")
                logger.debug(f"Response: {response}")
                return False

        except Exception as e:
            logger.error(f"❌ Error updating anime status: {e}")
            return False

    def update_anime_progress(self, anime_id, progress, status=None):
        """
        Update anime progress on AniList
        
        Args:
            anime_id: The AniList anime ID
            progress: Episode number to update to
            status: Optional status ('CURRENT', 'COMPLETED', 'PAUSED', 'DROPPED', 'PLANNING')
        """
        if not self.access_token:
            logger.error("No access token available")
            return False
        
        # Prepare the mutation variables
        variables = {
            'mediaId': anime_id,
            'progress': progress
        }
        
        # Add status if provided
        if status:
            variables['status'] = status
        
        # Build the mutation query
        mutation_fields = ['id', 'progress']
        variable_fields = ['$mediaId: Int', '$progress: Int']
        
        if status:
            mutation_fields.append('status')
            variable_fields.append('$status: MediaListStatus')
        
        query = f"""
        mutation ({', '.join(variable_fields)}) {{
            SaveMediaListEntry(mediaId: $mediaId, progress: $progress{', status: $status' if status else ''}) {{
                {' '.join(mutation_fields)}
            }}
        }}
        """
        
        try:
            response = requests.post(
                self.graphql_url,  # Changed from self.api_url to self.graphql_url
                json={
                    'query': query,
                    'variables': variables
                },
                headers={
                    'Authorization': f'Bearer {self.access_token}',
                    'Content-Type': 'application/json',
                    'Accept': 'application/json'
                },
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json()
                if 'errors' in data:
                    logger.error(f"AniList API errors: {data['errors']}")
                    return False
                
                entry = data.get('data', {}).get('SaveMediaListEntry', {})
                if entry:
                    updated_progress = entry.get('progress', 0)
                    updated_status = entry.get('status', 'UNKNOWN')
                    logger.info(f"Successfully updated anime {anime_id} - Progress: {updated_progress}, Status: {updated_status}")
                    return True
                else:
                    logger.error("No entry data in response")
                    return False
            else:
                logger.error(f"HTTP error {response.status_code}: {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"Error updating anime progress: {e}")
            return False