"""
Enhanced anime title matching with proper season detection and episode validation
"""

import re
import logging
from typing import List, Dict, Any, Optional, Tuple
from difflib import SequenceMatcher

logger = logging.getLogger(__name__)

class AnimeMatcher:
    """Enhanced anime matcher with AniList-based season validation and episode conversion"""

    def __init__(self, similarity_threshold: float = 0.8):
        self.similarity_threshold = similarity_threshold

        # Season detection patterns - more conservative
        self.season_patterns = [
            r'Season[\s]*(\d+)',  # Season 2
            r'S(\d+)',  # S2
            r'(\d+)(?:st|nd|rd|th)?\s*Season',  # 2nd Season
            r'Part[\s]*(\d+)',  # Part 2
            r'Cour[\s]*(\d+)',  # Cour 2
        ]

        # Special/movie indicators
        self.special_indicators = [
            'movie', 'film', 'ova', 'ona', 'special', 'recap', 'summary',
            'compilation', 'gekijouban', 'theatrical'
        ]

    def find_best_match_with_episode_validation(self, target_title: str, target_episode: int,
                                               candidates: List[Dict[str, Any]],
                                               estimated_season: int = 1) -> Optional[Tuple[Dict[str, Any], float, int, int]]:
        """
        Find best match with episode validation and proper season detection
        Returns: (match, similarity, corrected_season, corrected_episode)
        """
        if not target_title or not candidates:
            return None

        logger.debug(f"Matching '{target_title}' episode {target_episode} (estimated season {estimated_season})")

        # First, analyze the title structure in candidates to understand seasons
        season_structure = self._analyze_season_structure(candidates)
        logger.debug(f"Season structure detected: {list(season_structure.keys())}")

        # Determine the most likely season and episode based on episode number and AniList data
        best_match_info = self._find_best_season_episode_match(
            target_title, target_episode, candidates, season_structure, estimated_season
        )

        if not best_match_info:
            logger.warning(f"No suitable match found for {target_title} episode {target_episode}")
            return None

        match, similarity, season, episode = best_match_info

        anime_title = self._get_primary_title(match)
        logger.info(f"✅ Matched '{target_title}' E{target_episode} to '{anime_title}' S{season} E{episode} (similarity: {similarity:.2f})")

        return match, similarity, season, episode

    def _analyze_season_structure(self, candidates: List[Dict[str, Any]]) -> Dict[int, Dict[str, Any]]:
        """Analyze AniList candidates to understand season structure"""
        season_structure = {}

        for candidate in candidates:
            # Extract season number from title and data
            season_num = self._extract_season_from_candidate(candidate)

            # Get episode count
            episode_count = candidate.get('episodes') or 12  # Default fallback

            # Get format to identify specials/movies - FIX: Handle None values properly
            format_value = candidate.get('format')
            format_type = (format_value or '').upper()

            season_structure[season_num] = {
                'candidate': candidate,
                'episode_count': episode_count,
                'format': format_type,
                'is_special': format_type in ['MOVIE', 'SPECIAL', 'OVA', 'ONA'],
                'title': self._get_primary_title(candidate)
            }

        return season_structure

    def _find_best_season_episode_match(self, target_title: str, target_episode: int,
                                      candidates: List[Dict[str, Any]],
                                      season_structure: Dict[int, Dict[str, Any]],
                                      estimated_season: int) -> Optional[Tuple[Dict[str, Any], float, int, int]]:
        """Find the best season and episode match using AniList data"""

        best_match = None
        best_similarity = 0.0
        best_season = 1
        best_episode = target_episode

        # Sort seasons to check most likely ones first
        sorted_seasons = sorted(season_structure.keys())

        # If we have multiple seasons, try to determine which one based on episode number
        if len(sorted_seasons) > 1:
            # Calculate cumulative episode counts to determine season
            cumulative_episodes = 0
            target_season = 1
            target_episode_in_season = target_episode

            for season_num in sorted_seasons:
                season_info = season_structure[season_num]
                episode_count = season_info['episode_count']

                # Skip specials when calculating cumulative episodes
                if season_info['is_special']:
                    continue

                if target_episode <= cumulative_episodes + episode_count:
                    target_season = season_num
                    target_episode_in_season = target_episode - cumulative_episodes
                    break

                cumulative_episodes += episode_count

            logger.debug(f"Calculated season {target_season} episode {target_episode_in_season} from absolute episode {target_episode}")

        else:
            # Only one season available
            target_season = sorted_seasons[0] if sorted_seasons else 1
            target_episode_in_season = target_episode

        # Now find the best matching candidate for our determined season
        for season_num, season_info in season_structure.items():
            candidate = season_info['candidate']

            # Calculate title similarity
            similarity = self._calculate_title_similarity(target_title, candidate)

            # Apply season preference bonus
            if season_num == target_season:
                similarity += 0.1  # Bonus for calculated season
            elif season_num == estimated_season:
                similarity += 0.05  # Smaller bonus for estimated season

            # Validate episode number makes sense for this season
            episode_count = season_info['episode_count']
            episode_in_season = target_episode_in_season if season_num == target_season else target_episode

            # Penalty for impossible episode numbers
            if episode_count and episode_in_season > episode_count * 1.5:  # Allow some flexibility
                similarity -= 0.2
                logger.debug(f"Episode penalty for {season_info['title']} S{season_num}: E{episode_in_season} > {episode_count}")

            if similarity > best_similarity and similarity >= self.similarity_threshold:
                best_similarity = similarity
                best_match = candidate
                best_season = season_num
                # Use corrected episode number for the determined season
                best_episode = target_episode_in_season if season_num == target_season else min(target_episode, episode_count or target_episode)

        if best_match:
            return best_match, best_similarity, best_season, best_episode

        return None

    def _extract_season_from_candidate(self, candidate: Dict[str, Any]) -> int:
        """Extract season number from AniList candidate with better detection"""

        # Check title fields for season information
        titles_to_check = self._extract_titles(candidate)

        for title in titles_to_check:
            season = self._extract_season_from_title(title)
            if season > 1:
                return season

        # Check for season indicators in title
        primary_title = self._get_primary_title(candidate).lower()

        # Common season indicators
        season_indicators = {
            '2nd': 2, 'second': 2, 'ii': 2,
            '3rd': 3, 'third': 3, 'iii': 3,
            '4th': 4, 'fourth': 4, 'iv': 4,
            '5th': 5, 'fifth': 5, 'v': 5,
        }

        for indicator, season_num in season_indicators.items():
            if indicator in primary_title:
                return season_num

        # Check start date to infer season order (newer = higher season)
        start_date = candidate.get('startDate', {})
        if start_date and start_date.get('year'):
            year = start_date['year']
            # This is a rough heuristic - later years might indicate later seasons
            # But we need more context to be accurate

        return 1  # Default to season 1

    def _extract_season_from_title(self, title: str) -> int:
        """Extract season number from title with improved patterns"""
        if not title:
            return 1

        # More specific patterns that are less likely to give false positives
        specific_patterns = [
            r'Season[\s]*(\d+)',  # Season 2
            r'(\d+)(?:st|nd|rd|th)?\s*Season',  # 2nd Season
            r'\bS(\d+)\b',  # S2 (word boundary to avoid false matches)
            r'Part[\s]*(\d+)',  # Part 2
            r'Cour[\s]*(\d+)',  # Cour 2
        ]

        for pattern in specific_patterns:
            match = re.search(pattern, title, re.IGNORECASE)
            if match:
                try:
                    season_num = int(match.group(1))
                    # Sanity check - seasons should be reasonable
                    if 1 <= season_num <= 10:  # Most anime don't have more than 10 seasons
                        return season_num
                except (ValueError, IndexError):
                    continue

        return 1

    def _calculate_title_similarity(self, target_title: str, candidate: Dict[str, Any]) -> float:
        """Calculate similarity between target title and candidate"""
        target_normalized = self._normalize_title(target_title)

        max_similarity = 0.0
        titles_to_check = self._extract_titles(candidate)

        for title in titles_to_check:
            if title:
                candidate_normalized = self._normalize_title(title)
                similarity = self._calculate_similarity(target_normalized, candidate_normalized)
                max_similarity = max(max_similarity, similarity)

        return max_similarity

    def validate_episode_number(self, episode_number: int, anime_data: Dict[str, Any]) -> Tuple[int, bool, str]:
        """Validate and potentially correct episode number based on AniList data"""
        total_episodes = anime_data.get('episodes')

        if not total_episodes:
            return episode_number, False, "No episode count available"

        # If episode is within range, it's probably correct
        if episode_number <= total_episodes:
            return episode_number, False, f"Episode {episode_number} is within range (≤{total_episodes})"

        # Episode number is too high - might be absolute numbering
        if episode_number > total_episodes:
            # Try to convert from absolute to seasonal numbering
            # This is a simplified approach - in reality, you'd need season structure
            if episode_number <= total_episodes * 2:  # Might be from previous season
                corrected = episode_number - total_episodes
                if corrected > 0:
                    return corrected, True, f"Converted from absolute numbering (E{episode_number} → E{corrected})"

        # Keep original if we can't confidently convert
        return episode_number, False, f"Keeping original E{episode_number} (outside expected range of 1-{total_episodes})"

    def convert_absolute_to_seasonal_episode(self, absolute_episode: int,
                                           season_structure: Dict[int, Dict[str, Any]],
                                           target_season: int) -> Tuple[int, str]:
        """Convert absolute episode number to seasonal episode number"""

        if target_season == 1:
            return absolute_episode, "No conversion needed for season 1"

        # Calculate episodes in previous seasons
        previous_episodes = 0
        for season_num in sorted(season_structure.keys()):
            if season_num >= target_season:
                break
            season_info = season_structure[season_num]
            if not season_info['is_special']:  # Don't count specials
                previous_episodes += season_info['episode_count']

        seasonal_episode = absolute_episode - previous_episodes

        if seasonal_episode > 0:
            return seasonal_episode, f"Converted from absolute E{absolute_episode} (removed {previous_episodes} previous episodes)"
        else:
            return absolute_episode, f"Conversion failed, keeping absolute E{absolute_episode}"

    def detect_special_or_movie(self, title: str, episode_data: Dict[str, Any]) -> bool:
        """Detect if this is a special, OVA, or movie rather than regular episode"""

        title_lower = title.lower()
        episode_title = episode_data.get('episode_title', '').lower()

        # Check for special indicators in titles
        for indicator in self.special_indicators:
            if indicator in title_lower or indicator in episode_title:
                return True

        # Check episode number patterns that might indicate specials
        episode_number = episode_data.get('episode_number', 0)

        # Episode 0 often indicates specials
        if episode_number == 0:
            return True

        return False

    # Utility methods (cleaned up versions of existing methods)

    def _extract_titles(self, anime: Dict[str, Any]) -> List[str]:
        """Extract all possible titles from anime data"""
        titles = []

        title_obj = anime.get('title', {})
        if isinstance(title_obj, dict):
            for key in ['romaji', 'english', 'native']:
                title = title_obj.get(key)
                if title:
                    titles.append(title)
        elif isinstance(title_obj, str):
            titles.append(title_obj)

        # Add synonyms
        synonyms = anime.get('synonyms', [])
        if synonyms:
            titles.extend(synonyms)

        return [title for title in titles if title]

    def _get_primary_title(self, anime: Dict[str, Any]) -> str:
        """Get the primary title for display"""
        title_obj = anime.get('title', {})
        if isinstance(title_obj, dict):
            return (title_obj.get('romaji') or
                   title_obj.get('english') or
                   title_obj.get('native') or 'Unknown')
        elif isinstance(title_obj, str):
            return title_obj
        return 'Unknown'

    def _normalize_title(self, title: str) -> str:
        """Normalize title for better matching"""
        if not title:
            return ""

        normalized = title.lower()

        # Remove common metadata that might interfere with matching
        patterns_to_remove = [
            r'\s*\(dub\)\s*',
            r'\s*\(sub\)\s*',
            r'\s*\(english dub\)\s*',
            r'\s*\(\d{4}\)\s*$',  # Year in parentheses at end
        ]

        for pattern in patterns_to_remove:
            normalized = re.sub(pattern, ' ', normalized)

        # Remove special characters but keep important ones
        normalized = re.sub(r'[^\w\s\-:!?]', ' ', normalized)

        # Normalize whitespace
        normalized = re.sub(r'\s+', ' ', normalized).strip()

        return normalized

    def _calculate_similarity(self, title1: str, title2: str) -> float:
        """Calculate similarity between two normalized titles"""
        if not title1 or not title2:
            return 0.0

        # Exact match
        if title1 == title2:
            return 1.0

        # Substring matches
        if title1 in title2 or title2 in title1:
            shorter, longer = (title1, title2) if len(title1) < len(title2) else (title2, title1)
            return max(0.9, len(shorter) / len(longer))

        # Sequence matcher for fuzzy matching
        sequence_similarity = SequenceMatcher(None, title1, title2).ratio()

        # Word-based similarity
        words1 = set(title1.split())
        words2 = set(title2.split())

        if words1 and words2:
            common_words = words1.intersection(words2)
            total_words = words1.union(words2)
            word_overlap = len(common_words) / len(total_words) if total_words else 0

            coverage1 = len(common_words) / len(words1) if words1 else 0
            coverage2 = len(common_words) / len(words2) if words2 else 0
            word_coverage = (coverage1 + coverage2) / 2

            word_similarity = (word_overlap * 0.4) + (word_coverage * 0.6)
            final_similarity = (sequence_similarity * 0.6) + (word_similarity * 0.4)
        else:
            final_similarity = sequence_similarity

        return final_similarity

    # Legacy compatibility methods

    def find_best_match(self, target_title: str, candidates: List[Dict[str, Any]],
                       target_season: int = 1) -> Optional[Tuple[Dict[str, Any], float]]:
        """Legacy compatibility method"""
        result = self.find_best_match_with_episode_validation(
            target_title, 1, candidates, target_season
        )
        if result:
            match, similarity, _, _ = result
            return match, similarity
        return None

    def find_best_match_with_season(self, target_title: str, candidates: List[Dict[str, Any]],
                                   target_season: int = 1) -> Optional[Tuple[Dict[str, Any], float, int]]:
        """Legacy compatibility method with season"""
        result = self.find_best_match_with_episode_validation(
            target_title, 1, candidates, target_season
        )
        if result:
            match, similarity, season, _ = result
            return match, similarity, season
        return None