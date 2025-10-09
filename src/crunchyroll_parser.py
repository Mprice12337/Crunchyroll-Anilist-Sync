"""
Crunchyroll API Response Parser
Parses episode data from Crunchyroll API responses with proper season detection.
"""

import logging
from typing import List, Dict, Any

logger = logging.getLogger(__name__)


class CrunchyrollParser:
    """Parser for Crunchyroll API responses"""

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

                is_movie = self._is_movie_or_special_content(episode_metadata)

                if not series_title:
                    skipped += 1
                    continue

                if not is_movie and (not episode_number or episode_number <= 0):
                    skipped += 1
                    continue

                if is_movie and (not episode_number or episode_number <= 0):
                    episode_number = 1

                if not is_movie and self._is_compilation_or_recap_content(season_title, episode_title,
                                                                          episode_metadata):
                    skipped += 1
                    continue

                detected_season = self._extract_correct_season_number(episode_metadata)
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
                    'raw_season_number': raw_season_number,
                    'season_display_number': season_display_number,
                    'date_played': item.get('date_played', ''),
                    'fully_watched': item.get('fully_watched', False),
                    'api_source': True,
                    'is_movie': is_movie
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
        """Detect compilation and recap content that should be skipped (excludes movies)"""
        season_title_lower = season_title.lower() if season_title else ""
        episode_title_lower = episode_title.lower() if episode_title else ""

        compilation_indicators = [
            'compilation', 'recap', 'summary', 'special collection'
        ]

        for indicator in compilation_indicators:
            if indicator in season_title_lower or indicator in episode_title_lower:
                return True

        return False

    def _is_movie_or_special_content(self, episode_metadata: Dict[str, Any]) -> bool:
        """Conservative detection of movie/special content using strong indicators"""
        identifier = episode_metadata.get('identifier', '')
        if identifier and '|M|' in identifier:
            return True

        episode_number = episode_metadata.get('episode_number')
        if episode_number is None:
            return True

        return False

    def _extract_correct_season_number(self, episode_metadata: Dict[str, Any]) -> int:
        """Extract correct season number with conservative movie detection"""
        if self._is_movie_or_special_content(episode_metadata):
            return 0

        season_title = episode_metadata.get('season_title', '')
        if season_title:
            extracted_season = self._extract_season_from_title(season_title)
            if extracted_season > 1:
                return extracted_season

        season_sequence = episode_metadata.get('season_sequence_number', 0)
        if isinstance(season_sequence, int) and 1 <= season_sequence <= 10:
            return season_sequence

        raw_season_number = episode_metadata.get('season_number', 1)
        if isinstance(raw_season_number, int) and 1 <= raw_season_number <= 10:
            return raw_season_number

        return 1

    def _extract_season_from_title(self, season_title: str) -> int:
        """Extract season number from season title string"""
        import re

        season_title_lower = season_title.lower()

        patterns = [
            (r'season\s*(\d+)', 1),
            (r's(\d+)', 1),
            (r'(\d+)(?:st|nd|rd|th)\s*season', 1),
            (r'part\s*(\d+)', 1),
        ]

        for pattern, group in patterns:
            match = re.search(pattern, season_title_lower)
            if match:
                try:
                    season_num = int(match.group(group))
                    if 1 <= season_num <= 20:
                        return season_num
                except (ValueError, IndexError):
                    continue

        return 1

    def _log_api_summary(self, all_episodes: List[Dict[str, Any]]) -> None:
        """Log clean summary of API results"""
        series_counts = {}
        movie_count = 0

        for episode in all_episodes:
            series = episode.get('series_title', 'Unknown')
            season = episode.get('season', 1)
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

        sorted_series = sorted(series_counts.items(), key=lambda x: x[1], reverse=True)

        if len(sorted_series) > 15:
            remaining = len(sorted_series) - 15
            remaining_episodes = sum(count for _, count in sorted_series[15:])
            logger.info(f"... and {remaining} more series ({remaining_episodes} episodes)")

        logger.info("=" * 50)
