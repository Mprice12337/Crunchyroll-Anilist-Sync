"""
AniList API Handler with Rate Limiting
"""

import logging
import time
from typing import Optional, Dict, Any, List

import requests

logger = logging.getLogger(__name__)


class RateLimitTracker:
    """Tracks and manages AniList API rate limits"""

    def __init__(self):
        self.limit = 90
        self.remaining = 90
        self.reset_time = None
        self.last_request_time = 0

    def update_from_headers(self, headers: Dict[str, str]) -> None:
        """Update rate limit information from response headers"""
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
        """
        Determine if request should be delayed to respect rate limits

        Returns:
            Tuple of (should_wait, wait_time_seconds)
        """
        current_time = time.time()

        if self.remaining <= 2:
            if self.reset_time and current_time < self.reset_time:
                wait_time = self.reset_time - current_time
                return True, wait_time

        time_since_last = current_time - self.last_request_time
        if time_since_last < 2.0:
            wait_time = 2.0 - time_since_last
            return True, wait_time

        return False, 0.0

    def get_status_info(self) -> str:
        """Get human-readable rate limit status"""
        if self.reset_time:
            reset_in = max(0, self.reset_time - time.time())
            return f"Rate limit: {self.remaining}/{self.limit} (resets in {reset_in:.0f}s)"
        else:
            return f"Rate limit: {self.remaining}/{self.limit}"


class AniListAPI:
    """Handles GraphQL API interactions with AniList"""

    def __init__(self):
        self.graphql_url = "https://graphql.anilist.co"
        self.rate_limiter = RateLimitTracker()
        self.current_user_id = None

    def search_anime(self, title: str, access_token: str) -> Optional[List[Dict[str, Any]]]:
        """Search for anime by title"""
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
            result = self._execute_query(query, variables, access_token)

            if result and 'data' in result and 'Page' in result['data']:
                media_list = result['data']['Page']['media']
                return media_list

            logger.warning(f"No search results for: {title}")
            return None

        except Exception as e:
            logger.error(f"Search failed for '{title}': {e}")
            return None

    def get_anime_list_entry(self, anime_id: int, access_token: str) -> Optional[Dict[str, Any]]:
        """Get user's list entry for a specific anime"""
        user_id = self._get_current_user_id(access_token)
        if not user_id:
            logger.error("Could not determine current user ID")
            return None

        try:
            query = """
            query ($userId: Int, $mediaId: Int) {
                MediaList(userId: $userId, mediaId: $mediaId) {
                    id
                    progress
                    status
                    repeat
                    score
                    startedAt {
                        year
                        month
                        day
                    }
                    completedAt {
                        year
                        month
                        day
                    }
                    media {
                        id
                        title {
                            romaji
                        }
                        episodes
                    }
                    user {
                        id
                        name
                    }
                }
            }
            """

            variables = {
                'userId': user_id,
                'mediaId': anime_id
            }

            result = self._execute_query(query, variables, access_token)

            if result and 'data' in result:
                entry = result['data'].get('MediaList')
                if entry:
                    user_info = entry.get('user', {})

                    if user_info.get('id') != user_id:
                        logger.error(f"API returned entry for wrong user. Expected {user_id}, got {user_info.get('id')}")
                        return None

                    return entry

            return None

        except Exception as e:
            logger.error(f"Failed to get list entry for anime {anime_id}: {e}")
            return None

    def update_anime_progress(self, anime_id: int, progress: int, access_token: str,
                             status: Optional[str] = None, repeat: Optional[int] = None) -> bool:
        """
        Update anime progress on user's list

        Args:
            anime_id: AniList media ID
            progress: Episode progress
            access_token: User's access token
            status: Optional status (CURRENT, COMPLETED, etc.)
            repeat: Optional rewatch count
        """
        try:
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

            if repeat is not None:
                variables['repeat'] = repeat
                mutation_parts.append('repeat: $repeat')
                variable_parts.append('$repeat: Int')

            mutation = f"""
            mutation ({', '.join(variable_parts)}) {{
                SaveMediaListEntry({', '.join(mutation_parts)}) {{
                    id
                    progress
                    status
                    repeat
                    media {{
                        title {{
                            romaji
                        }}
                        episodes
                    }}
                    user {{
                        id
                        name
                    }}
                }}
            }}
            """

            result = self._execute_query(mutation, variables, access_token)

            if result and 'data' in result and 'SaveMediaListEntry' in result['data']:
                entry = result['data']['SaveMediaListEntry']
                media_title = entry.get('media', {}).get('title', {}).get('romaji', 'Unknown')
                updated_progress = entry.get('progress', progress)
                updated_status = entry.get('status', 'Unknown')
                updated_repeat = entry.get('repeat', 0)

                status_text = f"{updated_progress} episodes ({updated_status})"
                if updated_repeat > 0:
                    status_text += f" [Rewatch #{updated_repeat}]"

                logger.info(f"✅ Updated '{media_title}': {status_text}")
                return True
            else:
                logger.error(f"Failed to update anime {anime_id}")
                if result and 'errors' in result:
                    logger.error(f"GraphQL errors: {result['errors']}")
                return False

        except Exception as e:
            logger.error(f"Error updating anime {anime_id}: {e}")
            return False

    def _get_current_user_id(self, access_token: str) -> Optional[int]:
        """Get and cache the authenticated user's ID"""
        if self.current_user_id:
            return self.current_user_id

        try:
            query = """
            query {
                Viewer {
                    id
                    name
                }
            }
            """

            result = self._execute_query(query, {}, access_token)
            if result and 'data' in result and 'Viewer' in result['data']:
                viewer = result['data']['Viewer']
                self.current_user_id = viewer.get('id')
                user_name = viewer.get('name', 'Unknown')
                logger.info(f"🔍 Authenticated as user: {user_name} (ID: {self.current_user_id})")
                return self.current_user_id

        except Exception as e:
            logger.error(f"Failed to get current user ID: {e}")

        return None

    def _execute_query(self, query: str, variables: Optional[Dict[str, Any]] = None,
                      access_token: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Execute a GraphQL query with automatic retry and rate limiting

        Implements exponential backoff for server errors and respects rate limits.
        """
        max_retries = 3
        retry_count = 0

        while retry_count < max_retries:
            try:
                should_wait, wait_time = self.rate_limiter.should_wait()
                if should_wait:
                    logger.info(f"⏱️ Rate limiting: waiting {wait_time:.1f}s before request")
                    time.sleep(wait_time)

                headers = {
                    'Content-Type': 'application/json',
                    'Accept': 'application/json',
                }

                if access_token:
                    headers['Authorization'] = f'Bearer {access_token}'

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

                self.rate_limiter.update_from_headers(response.headers)

                if response.status_code == 200:
                    result = response.json()

                    if 'errors' in result:
                        logger.warning(f"GraphQL errors in response: {result['errors']}")

                    return result

                elif response.status_code == 429:
                    retry_after = response.headers.get('Retry-After', '60')
                    try:
                        wait_seconds = int(retry_after)
                    except ValueError:
                        wait_seconds = 60

                    logger.warning(f"🚫 Rate limit exceeded. Waiting {wait_seconds} seconds...")
                    time.sleep(wait_seconds)

                    self.rate_limiter.remaining = 0
                    if 'X-RateLimit-Reset' in response.headers:
                        try:
                            self.rate_limiter.reset_time = int(response.headers['X-RateLimit-Reset'])
                        except ValueError:
                            pass

                    retry_count += 1
                    continue

                elif response.status_code in [500, 502, 503, 504]:
                    wait_time = (2 ** retry_count) * 1
                    logger.warning(f"🔧 Server error {response.status_code}, retrying in {wait_time}s...")
                    time.sleep(wait_time)
                    retry_count += 1
                    continue

                else:
                    logger.error(f"GraphQL request failed: {response.status_code} - {response.text}")
                    return None

            except requests.exceptions.Timeout:
                wait_time = (2 ** retry_count) * 2
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