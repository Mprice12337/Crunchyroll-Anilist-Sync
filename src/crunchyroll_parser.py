"""
Crunchyroll API Response Parser
"""

import re
import logging
from typing import List, Dict, Any

logger = logging.getLogger(__name__)


class CrunchyrollParser:
    """Crunchyroll API response parser"""

    def _parse_api_response(self, items: List[Dict]) -> List[Dict[str, Any]]:
        """Parse episodes from API response items with proper season detection"""
        episodes = []
        skipped = 0

        for item in items:
            try:
                panel = item.get('panel', {})
                episode_metadata = panel.get('episode_metadata', {})

                series_title = episode_metadata.get('series_title', '').strip()
                episode_number = episode_metadata.get('episode_number', 0)
                episode_title = panel.get('title', '').strip()
                season_title = episode_metadata.get('season_title', '').strip()

                # Check if this is a movie/special (which may not have episode_number)
                is_movie = self._is_movie_or_special_content(episode_metadata)

                # Skip invalid entries, but allow movies through even without episode_number
                if not series_title:
                    skipped += 1
                    logger.debug(f"Skipping - no series title: {episode_title}")
                    continue

                if not is_movie and (not episode_number or episode_number <= 0):
                    skipped += 1
                    logger.debug(f"Skipping - no valid episode number for non-movie: {series_title} - {episode_title}")
                    continue

                # For movies, set episode_number to 1 if it's None/0 for processing purposes
                if is_movie and (not episode_number or episode_number <= 0):
                    episode_number = 1
                    logger.debug(f"Movie detected, setting episode_number to 1: {series_title} - {episode_title}")

                # FIXED: Check if this is compilation/recap content that should be skipped
                # BUT exclude movies (which should be processed with season 0)
                if not is_movie and self._is_compilation_or_recap_content(season_title, episode_title, episode_metadata):
                    logger.debug(f"Skipping compilation/recap content: {series_title} - {season_title} - {episode_title}")
                    skipped += 1
                    continue

                # Use season_display_number as primary source, fall back to parsing season_title
                detected_season = self._extract_correct_season_number(episode_metadata)

                # Safely handle season_display_number for debugging
                season_display_number = episode_metadata.get('season_display_number', '').strip()
                raw_season_number = None
                if season_display_number and season_display_number.isdigit():
                    try:
                        raw_season_number = int(season_display_number)
                    except ValueError:
                        raw_season_number = None

                episodes.append({
                    'series_title': series_title,
                    'episode_title': episode_title,
                    'episode_number': episode_number,
                    'season': detected_season,
                    'season_title': season_title,
                    'raw_season_number': raw_season_number,  # Keep for debugging, can be None
                    'season_display_number': season_display_number,  # Keep raw string for debugging
                    'date_played': item.get('date_played', ''),
                    'fully_watched': item.get('fully_watched', False),
                    'api_source': True,
                    'is_movie': is_movie  # Add flag to track movies
                })

            except Exception as e:
                logger.debug(f"Error parsing episode item: {e}")
                skipped += 1
                continue

        if skipped > 0:
            logger.debug(f"Skipped {skipped} invalid items from API response")

        return episodes

    def _is_compilation_or_recap_content(self, season_title: str, episode_title: str,
                                         episode_metadata: Dict[str, Any]) -> bool:
        """Detect compilation, recap content that should be skipped (but NOT movies)"""

        # Check season title for compilation indicators
        season_title_lower = season_title.lower() if season_title else ""
        episode_title_lower = episode_title.lower() if episode_title else ""

        # FIXED: Separate compilation indicators from movie indicators
        compilation_indicators = [
            'compilation', 'recap', 'summary', 'special collection'
        ]

        for indicator in compilation_indicators:
            if indicator in season_title_lower or indicator in episode_title_lower:
                return True

        # FIXED: Do NOT check for |M| identifier here anymore
        # Movies with |M| should be processed (with season 0), not skipped as compilation

        # FIXED: Do NOT treat movies as compilation content
        # Movies should be processed normally and assigned season 0 by _extract_correct_season_number

        return False

    def _log_api_summary(self, all_episodes: List[Dict[str, Any]]) -> None:
        """Log clean summary of API results"""
        # Count episodes per series-season using the processed season field
        series_counts = {}
        movie_count = 0

        for episode in all_episodes:
            series = episode.get('series_title', 'Unknown')
            season = episode.get('season', 1)  # Use the processed season field
            is_movie = episode.get('is_movie', False)

            if is_movie:
                movie_count += 1
                key = f"{series} [MOVIE]"
            else:
                key = f"{series} S{season}"
            series_counts[key] = series_counts.get(key, 0) + 1

        logger.info("=" * 50)
        logger.info(f"API RESULTS: {len(all_episodes)} episodes from {len(series_counts)} series-seasons")
        if movie_count > 0:
            logger.info(f"  Including {movie_count} movies/specials")
        logger.info("=" * 50)

        # Show top 15 series
        sorted_series = sorted(series_counts.items(), key=lambda x: x[1], reverse=True)
        for i, (series_season, count) in enumerate(sorted_series[:15], 1):
            logger.info(f"{i:2d}. {series_season}: {count} episodes")

        if len(sorted_series) > 15:
            remaining = len(sorted_series) - 15
            remaining_episodes = sum(count for _, count in sorted_series[15:])
            logger.info(f"... and {remaining} more series ({remaining_episodes} episodes)")

        logger.info("=" * 50)

    def _extract_correct_season_number(self, episode_metadata: Dict[str, Any]) -> int:
        """Extract correct season number using season_display_number as primary source with CONSERVATIVE movie detection"""

        # MUCH MORE CONSERVATIVE: Only treat as movie/special if we have STRONG indicators
        if self._is_movie_or_special_content(episode_metadata):
            logger.debug("Detected movie/special content based on strong indicators")
            return 0  # Use 0 to indicate movie/special

        # Primary: Use season_display_number if available and numeric
        season_display_number = episode_metadata.get('season_display_number', '').strip()
        logger.debug(f"extract_correct_season_number - Input season_display_number: {season_display_number!r}")

        if season_display_number and season_display_number.isdigit():
            try:
                season_num = int(season_display_number)
                if 1 <= season_num <= 20:  # Reasonable range
                    logger.debug(f"Using season_display_number: {season_num}")
                    return season_num
                else:
                    logger.debug(f"season_display_number {season_num} out of reasonable range, falling back")
            except ValueError:
                logger.debug(f"Could not convert season_display_number '{season_display_number}' to int")
        else:
            logger.debug(f"season_display_number is empty or non-numeric: {season_display_number!r}")

        # Secondary: Parse season number from season_title
        season_title = episode_metadata.get('season_title', '')
        if season_title:
            extracted_season = self._extract_season_from_title(season_title)
            if extracted_season > 1:
                logger.debug(f"Using season from title parsing: {extracted_season}")
                return extracted_season

        # Tertiary: Use season_sequence_number if it makes sense
        season_sequence = episode_metadata.get('season_sequence_number', 0)
        if isinstance(season_sequence, int) and 1 <= season_sequence <= 10:
            logger.debug(f"Using season_sequence_number: {season_sequence}")
            return season_sequence

        # Last resort: Use the raw season_number but validate it
        raw_season_number = episode_metadata.get('season_number', 1)
        if isinstance(raw_season_number, int) and 1 <= raw_season_number <= 10:
            logger.debug(f"Using raw season_number: {raw_season_number}")
            return raw_season_number

        # Default to season 1
        logger.debug("Defaulting to season 1")
        return 1

    def _is_movie_or_special_content(self, episode_metadata: Dict[str, Any]) -> bool:
        """CONSERVATIVE detection of movie/special content - only return True for STRONG indicators"""

        # STRONG indicator: Check identifier pattern - 'M' typically indicates movie
        identifier = episode_metadata.get('identifier', '')
        if identifier and '|M|' in identifier:
            logger.debug(f"Movie indicator found in identifier: {identifier}")
            return True

        # STRONG indicator: Check if episode_number is null/missing (common for movies)
        episode_number = episode_metadata.get('episode_number')
        if episode_number is None:
            logger.debug("No episode number - likely movie/special")
            return True

        # STRONG indicator: Check duration - movies are typically much longer
        duration_ms = episode_metadata.get('duration_ms', 0)
        normal_episode_duration = 25 * 60 * 1000  # 25 minutes in milliseconds
        if duration_ms > normal_episode_duration * 2.5:  # More than ~62 minutes
            logger.debug(f"Long duration detected ({duration_ms / 1000 / 60:.1f} min) - likely movie")
            return True

        # STRONG indicator: Check season_number for unusually high values (like 44 for JJK 0)
        season_number = episode_metadata.get('season_number', 1)
        if isinstance(season_number, int) and season_number > 20:
            logger.debug(f"Unusually high season_number ({season_number}) - likely movie/special")
            return True

        # STRONG indicator: Check season_title for explicit movie/special indicators
        season_title = episode_metadata.get('season_title', '').lower()
        movie_indicators = [
            'movie', 'film', '0', 'zero', 'gekijouban',
            'theatrical', 'cinema', 'feature'
        ]

        for indicator in movie_indicators:
            if indicator in season_title:
                logger.debug(f"Movie indicator '{indicator}' found in season_title: {season_title}")
                return True

        # REMOVED: The problematic logic that treated missing season_display_number as movie indicator
        # That was causing regular episodes to be marked as movies

        # Default to NOT a movie/special unless we have strong evidence
        return False

    def _extract_season_from_title(self, title: str) -> int:
        """Extract season number from season title"""
        if not title:
            return 1

        # Look for "Season X" or "Season X" patterns
        season_patterns = [
            r'Season\s+(\d+)',  # "Season 2"
            r'(\d+)(?:st|nd|rd|th)?\s+Season',  # "2nd Season"
            r'Part\s+(\d+)',  # "Part 2"
        ]

        for pattern in season_patterns:
            match = re.search(pattern, title, re.IGNORECASE)
            if match:
                try:
                    season_num = int(match.group(1))
                    if 1 <= season_num <= 20:  # Reasonable range
                        return season_num
                except (ValueError, IndexError):
                    continue

        return 1