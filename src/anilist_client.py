"""
Enhanced AniList client - main orchestrating class with rewatch support
"""

import logging
from typing import Optional, Dict, Any, List

from anilist_auth import AniListAuth
from anilist_api import AniListAPI

logger = logging.getLogger(__name__)


class AniListClient:
    """Enhanced AniList client that orchestrates authentication and API operations with rewatch support"""

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

    def get_anime_list_entry(self, anime_id: int) -> Optional[Dict[str, Any]]:
        """Get user's current list entry for an anime"""
        if not self.auth.is_authenticated():
            logger.error("Not authenticated! Call authenticate() first.")
            return None

        return self.api.get_anime_list_entry(anime_id, self.auth.access_token)

    def update_anime_progress(self, anime_id: int, progress: int, status: Optional[str] = None,
                             repeat: Optional[int] = None) -> bool:
        """Update anime progress on AniList with rate limiting and rewatch support"""
        if not self.auth.is_authenticated():
            logger.error("Not authenticated! Call authenticate() first.")
            return False

        return self.api.update_anime_progress(anime_id, progress, self.auth.access_token, status, repeat)

    def update_anime_progress_with_rewatch_logic(self, anime_id: int, progress: int,
                                                total_episodes: Optional[int] = None) -> bool:
        """
        Update anime progress with intelligent rewatch detection

        Args:
            anime_id: The AniList anime ID
            progress: Current episode progress
            total_episodes: Total episodes in the series (if known)

        Returns:
            bool: True if update was successful
        """
        if not self.auth.is_authenticated():
            logger.error("Not authenticated! Call authenticate() first.")
            return False

        try:
            # Get current list entry to check existing status
            existing_entry = self.get_anime_list_entry(anime_id)

            if existing_entry:
                current_status = existing_entry.get('status')
                current_progress = existing_entry.get('progress', 0)
                current_repeat = existing_entry.get('repeat', 0)

                # ADDED: Better debugging information
                logger.debug(f"Anime {anime_id} - Current: {current_status} {current_progress}/{total_episodes or '?'} "
                           f"(repeat: {current_repeat}) → Updating to: {progress}")

                # Determine if this is a rewatch scenario
                is_rewatch = self._is_rewatch_scenario(existing_entry, progress, total_episodes)

                if is_rewatch:
                    return self._handle_rewatch_update(anime_id, progress, existing_entry, total_episodes)
                else:
                    return self._handle_normal_update(anime_id, progress, existing_entry, total_episodes)
            else:
                # No existing entry, treat as new watch
                logger.debug(f"Anime {anime_id} - No existing entry, treating as new watch (episode {progress})")
                return self._handle_new_watch(anime_id, progress, total_episodes)

        except Exception as e:
            logger.error(f"Error in rewatch logic for anime {anime_id}: {e}")
            return False

    def _is_rewatch_scenario(self, existing_entry: Dict[str, Any], new_progress: int,
                           total_episodes: Optional[int]) -> bool:
        """Determine if this update represents a rewatch scenario"""
        current_status = existing_entry.get('status')
        current_progress = existing_entry.get('progress', 0)

        # FIXED: If progress is the same, this is likely just a duplicate update, not a rewatch
        if current_progress == new_progress:
            logger.debug(f"Same progress ({current_progress} == {new_progress}), not a rewatch")
            return False

        # FIXED: If we're making normal forward progress, it's not a rewatch
        if new_progress > current_progress and (new_progress - current_progress) <= 5:
            logger.debug(f"Normal forward progress ({current_progress} → {new_progress}), not a rewatch")
            return False

        # If the user has completed the series and we're updating with episode 1 or early episodes,
        # AND it's a significant step backwards, this is likely a rewatch
        if current_status == 'COMPLETED' and current_progress > 0:
            if new_progress <= 3 and current_progress > 10:  # Must be significant backwards step
                logger.info("🔄 Detected rewatch: completed series, starting from beginning")
                return True

        # If the user has significant progress and we're updating with episode 1,
        # AND it's not just a small adjustment, this might be a rewatch
        if current_progress > 10 and new_progress <= 3:
            logger.info("🔄 Detected potential rewatch: significant progress reset to beginning")
            return True

        # FIXED: Only detect rewatch completion if we're completing AGAIN after already being completed
        # and the progress actually changed backwards first (indicating a rewatch was started)
        if (current_status == 'COMPLETED' and total_episodes and
            new_progress >= total_episodes and current_progress < total_episodes):
            logger.info("🔄 Detected rewatch completion")
            return True

        return False

    def _handle_rewatch_update(self, anime_id: int, progress: int, existing_entry: Dict[str, Any],
                             total_episodes: Optional[int]) -> bool:
        """Handle updates for rewatch scenarios"""
        current_repeat = existing_entry.get('repeat', 0)

        # If we're completing a rewatch, increment the repeat count
        if total_episodes and progress >= total_episodes:
            new_repeat = current_repeat + 1
            status = 'COMPLETED'

            logger.info(f"🏁 Completing rewatch #{new_repeat}")
            return self.update_anime_progress(anime_id, progress, status, new_repeat)
        else:
            # We're in the middle of a rewatch, mark as CURRENT (watching)
            status = 'CURRENT'

            # Don't increment repeat count until completion
            logger.info(f"📺 Continuing rewatch (episode {progress})")
            return self.update_anime_progress(anime_id, progress, status, current_repeat)

    def _handle_normal_update(self, anime_id: int, progress: int, existing_entry: Dict[str, Any],
                            total_episodes: Optional[int]) -> bool:
        """Handle normal progress updates (not rewatches)"""
        current_status = existing_entry.get('status')
        current_progress = existing_entry.get('progress', 0)
        current_repeat = existing_entry.get('repeat', 0)

        # FIXED: Determine status more intelligently
        if total_episodes and progress >= total_episodes:
            # Only mark as completed if we're actually completing it (not already completed)
            if current_status != 'COMPLETED' or current_progress < total_episodes:
                status = 'COMPLETED'
                logger.info(f"🏁 Completing series (episode {progress}/{total_episodes})")
            else:
                # Already completed with same progress - this is likely a duplicate update
                status = current_status  # Keep existing status
                logger.info(f"✅ Series already completed, maintaining status (episode {progress}/{total_episodes})")
        else:
            # FIXED: Better status logic for in-progress updates
            if current_status in ['PLANNING', 'PAUSED']:
                status = 'CURRENT'  # Start watching
                logger.info(f"▶️ Starting to watch (episode {progress})")
            elif current_status == 'COMPLETED':
                # This shouldn't happen in normal updates (would be rewatch)
                status = 'CURRENT'
                logger.info(f"📺 Resuming completed series (episode {progress})")
            else:
                status = 'CURRENT'  # Continue watching
                logger.info(f"📺 Updating progress (episode {progress})")

        # Keep existing repeat count for normal updates
        return self.update_anime_progress(anime_id, progress, status, current_repeat)

    def _handle_new_watch(self, anime_id: int, progress: int, total_episodes: Optional[int]) -> bool:
        """Handle updates for new anime (no existing entry)"""
        # Determine status based on progress
        if total_episodes and progress >= total_episodes:
            status = 'COMPLETED'
            logger.info(f"🏁 Completing new series (episode {progress}/{total_episodes})")
        else:
            status = 'CURRENT'
            logger.info(f"📺 Starting new series (episode {progress})")

        # New watch, so repeat count is 0 (don't need to specify it)
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

    def is_authenticated(self) -> bool:
        """Check if currently authenticated"""
        return self.auth.is_authenticated()