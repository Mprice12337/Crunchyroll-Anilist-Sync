"""
AniList Client - Orchestrates authentication and API operations with rewatch support
"""

import logging
from typing import Optional, Dict, Any, List

from anilist_auth import AniListAuth
from anilist_api import AniListAPI

logger = logging.getLogger(__name__)


class AniListClient:
    """High-level AniList client with intelligent rewatch detection"""

    def __init__(self):
        """Initialize AniList client with static credentials"""
        self.auth = AniListAuth()
        self.api = AniListAPI()

    def authenticate(self) -> bool:
        """Authenticate with AniList using OAuth"""
        return self.auth.authenticate()

    def is_authenticated(self) -> bool:
        """Check if currently authenticated"""
        return self.auth.is_authenticated()

    def search_anime(self, title: str) -> Optional[List[Dict[str, Any]]]:
        """Search for anime by title"""
        if not self.auth.is_authenticated():
            logger.error("Not authenticated! Call authenticate() first.")
            return None

        return self.api.search_anime(title, self.auth.access_token)

    def get_anime_list_entry(self, anime_id: int) -> Optional[Dict[str, Any]]:
        """Get user's current list entry for an anime"""
        if not self.auth.is_authenticated():
            logger.error("Not authenticated! Call authenticate() first.")
            return None

        return self.api.get_anime_list_entry(anime_id, self.auth.access_token)

    def update_anime_progress(self, anime_id: int, progress: int, status: Optional[str] = None,
                              repeat: Optional[int] = None) -> bool:
        """Update anime progress on AniList"""
        if not self.auth.is_authenticated():
            logger.error("Not authenticated! Call authenticate() first.")
            return False

        return self.api.update_anime_progress(anime_id, progress, self.auth.access_token, status, repeat)

    def update_anime_progress_with_rewatch_logic(self, anime_id: int, progress: int,
                                                 total_episodes: Optional[int] = None) -> Dict[str, Any]:
        """
        Update anime progress with intelligent rewatch detection

        Automatically detects when a user is rewatching a completed series and
        handles the progress update appropriately.

        Args:
            anime_id: AniList media ID
            progress: Current episode number
            total_episodes: Total episodes in the series (if known)

        Returns:
            Dictionary with update statistics:
                {
                    'success': bool,
                    'was_rewatch': bool,
                    'was_completion': bool,
                    'was_new_series': bool,
                    'repeat_count': int
                }
        """
        if not self.auth.is_authenticated():
            logger.error("Not authenticated! Call authenticate() first.")
            return {
                'success': False,
                'was_rewatch': False,
                'was_completion': False,
                'was_new_series': False,
                'repeat_count': 0
            }

        result = {
            'success': False,
            'was_rewatch': False,
            'was_completion': False,
            'was_new_series': False,
            'repeat_count': 0
        }

        try:
            existing_entry = self.get_anime_list_entry(anime_id)

            if existing_entry:
                if self._is_rewatch_scenario(existing_entry, progress, total_episodes):
                    result['was_rewatch'] = True
                    result['repeat_count'] = existing_entry.get('repeat', 0)

                    if total_episodes and progress >= total_episodes:
                        result['was_completion'] = True
                        result['repeat_count'] += 1

                    success = self._handle_rewatch_update(anime_id, progress, existing_entry, total_episodes)
                else:
                    current_status = existing_entry.get('status')
                    if current_status in ['PLANNING', None] or existing_entry.get('progress', 0) == 0:
                        result['was_new_series'] = True

                    if total_episodes and progress >= total_episodes:
                        result['was_completion'] = True

                    success = self._handle_normal_update(anime_id, progress, existing_entry, total_episodes)
            else:
                result['was_new_series'] = True
                if total_episodes and progress >= total_episodes:
                    result['was_completion'] = True

                success = self._handle_new_watch(anime_id, progress, total_episodes)

            result['success'] = success
            return result

        except Exception as e:
            logger.error(f"Error in rewatch logic: {e}")
            return result

    def _is_rewatch_scenario(self, existing_entry: Dict[str, Any], progress: int,
                             total_episodes: Optional[int]) -> bool:
        """
        Determine if this is a rewatch scenario

        A rewatch is detected when:
        - repeat > 0 (already in a rewatch, regardless of status)
        - status is REPEATING (user is actively rewatching)

        Note: Initial rewatch detection (COMPLETED → episode 1-3 transition) is handled
        in _handle_normal_update where we set the status to REPEATING and increment repeat.
        """
        current_repeat = existing_entry.get('repeat', 0)
        current_status = existing_entry.get('status')

        # If repeat > 0 or status is REPEATING, we're in rewatch territory
        if current_repeat > 0 or current_status == 'REPEATING':
            logger.debug(f"In rewatch scenario (repeat: {current_repeat}, status: {current_status})")
            return True

        return False

    def _handle_rewatch_update(self, anime_id: int, progress: int, existing_entry: Dict[str, Any],
                               total_episodes: Optional[int]) -> bool:
        """
        Handle progress updates for ongoing rewatches (repeat > 0 or status is REPEATING)

        Uses REPEATING status for rewatches. When transitioning from REPEATING to COMPLETED,
        AniList automatically increments the repeat counter.
        """
        current_repeat = existing_entry.get('repeat', 0)

        if total_episodes and progress >= total_episodes:
            # Completing the rewatch - let AniList auto-increment repeat counter
            status = 'COMPLETED'
            logger.info(f"🏁 Completing rewatch #{current_repeat} (AniList will auto-increment repeat counter)")
            # Don't manually increment repeat - AniList does this when REPEATING → COMPLETED
            return self.update_anime_progress(anime_id, progress, status, None)
        else:
            # Still watching the rewatch - use REPEATING status
            status = 'REPEATING'
            logger.info(f"📺 Continuing rewatch #{current_repeat} (episode {progress})")
            # Don't pass repeat parameter - let AniList manage it
            return self.update_anime_progress(anime_id, progress, status, None)

    def _handle_normal_update(self, anime_id: int, progress: int, existing_entry: Dict[str, Any],
                              total_episodes: Optional[int]) -> bool:
        """
        Handle normal progress updates (not currently in a rewatch)

        KEY LOGIC: If status is COMPLETED and we're changing to CURRENT,
        this is the start of a rewatch - increment repeat counter.
        """
        current_status = existing_entry.get('status')
        current_progress = existing_entry.get('progress', 0)
        current_repeat = existing_entry.get('repeat', 0)

        # Determine new status
        if total_episodes and progress >= total_episodes:
            # Completing the series
            new_status = 'COMPLETED'
            new_repeat = current_repeat

            if current_status != 'COMPLETED' or current_progress < total_episodes:
                logger.info(f"🏁 Completing series (episode {progress}/{total_episodes})")
            else:
                logger.info(f"✅ Series already completed, maintaining status (episode {progress}/{total_episodes})")

        else:
            # Not at the end yet - determine if REPEATING or CURRENT
            # CRITICAL FIX: Only increment rewatch counter if actually rewatching from the beginning
            # Don't increment for old episodes being processed out of order
            if current_status == 'COMPLETED' and progress <= 3:
                # Series was completed, now watching from beginning = REWATCH!
                # Use REPEATING status instead of CURRENT, and increment repeat counter
                new_status = 'REPEATING'
                new_repeat = current_repeat + 1
                logger.info(f"🔄 Starting rewatch #{new_repeat} (series was COMPLETED, now watching episode {progress})")
            elif current_status == 'COMPLETED' and progress > current_progress:
                # Moving forward from COMPLETED status (edge case: episodes added later)
                new_status = 'CURRENT'
                new_repeat = current_repeat
                logger.info(f"📺 Continuing series beyond previous completion (episode {progress})")
            else:
                # Normal progression (PLANNING → CURRENT, or CURRENT → CURRENT)
                new_status = 'CURRENT'
                new_repeat = current_repeat

                if current_status in ['PLANNING', 'PAUSED']:
                    logger.info(f"▶️ Starting to watch (episode {progress})")
                elif current_status == 'COMPLETED':
                    # This shouldn't happen due to _needs_update checks, but just in case
                    logger.info(f"📺 Updating completed series (episode {progress})")
                else:
                    logger.info(f"📺 Updating progress (episode {progress})")

        return self.update_anime_progress(anime_id, progress, new_status, new_repeat)

    def _handle_new_watch(self, anime_id: int, progress: int, total_episodes: Optional[int]) -> bool:
        """Handle updates for new anime (no existing entry)"""
        if total_episodes and progress >= total_episodes:
            status = 'COMPLETED'
            logger.info(f"🏁 Completing new series (episode {progress}/{total_episodes})")
        else:
            status = 'CURRENT'
            logger.info(f"📺 Starting new series (episode {progress})")

        return self.update_anime_progress(anime_id, progress, status)

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
