"""
Enhanced anime title matching with proper season detection and episode validation
"""

import re
import logging
from typing import List, Dict, Any, Optional, Tuple, Set
from difflib import SequenceMatcher

logger = logging.getLogger(__name__)

class AnimeMatcher:
    """Enhanced anime matcher with robust season detection and episode validation"""

    def __init__(self, similarity_threshold: float = 0.75):
        self.similarity_threshold = similarity_threshold

        # More conservative season patterns - only match clear season indicators
        self.season_patterns = [
            r'\bSeason[\s]*(\d+)\b',  # Season 2
            r'\bS(\d+)\b',  # S2 (but not in middle of words)
            r'\b(\d+)(?:st|nd|rd|th)\s*Season\b',  # 2nd Season
            r':\s*Season\s*(\d+)\b',  # Title: Season 2
            r'-\s*Season\s*(\d+)\b',  # Title - Season 2
        ]

        # Patterns for detecting specials/movies that shouldn't be treated as regular episodes
        self.special_patterns = [
            r'\b(movie|film|ova|ona|special|recap)\b',
            r'\b(prologue|epilogue|extra|side story)\b',
            r'\b(prequel|sequel|spin-?off)\b',
        ]

        # Cache for AniList season data to avoid repeated API calls
        self._anilist_season_cache = {}

    def find_best_match(self, target_title: str, candidates: List[Dict[str, Any]],
                       target_season: int = 1) -> Optional[Tuple[Dict[str, Any], float]]:
        """Find the best matching anime with improved season handling"""
        if not target_title or not candidates:
            return None

        logger.debug(f"🔍 Matching '{target_title}' (S{target_season}) against {len(candidates)} candidates")

        # First pass: Group candidates by base title
        title_groups = self._group_candidates_by_base_title(candidates)

        best_match = None
        best_similarity = 0.0

        normalized_target = self._normalize_title(target_title)
        target_is_special = self._is_special_episode(target_title)

        for base_title, group_candidates in title_groups.items():
            # Find best match within this title group
            group_result = self._find_best_in_group(
                normalized_target, target_season, group_candidates, target_is_special
            )

            if group_result and group_result[1] > best_similarity:
                best_match, best_similarity = group_result

        if best_similarity >= self.similarity_threshold:
            primary_title = self._get_primary_title(best_match)
            actual_season = self._get_actual_season(best_match)
            logger.info(f"✅ Matched '{target_title}' → '{primary_title}' S{actual_season} (similarity: {best_similarity:.2f})")
            return best_match, best_similarity

        logger.warning(f"❌ No suitable match for '{target_title}' (best: {best_similarity:.2f})")
        return None

    def validate_episode_with_anilist_data(self, episode_number: int, anime_data: Dict[str, Any],
                                         series_title: str, target_season: int) -> Tuple[int, bool, str]:
        """Validate and convert episode number using actual AniList data"""
        anilist_episodes = anime_data.get('episodes')
        anilist_format = anime_data.get('format', '').upper()
        anilist_status = anime_data.get('status', '').upper()

        # Handle movies and special formats
        if anilist_format in ['MOVIE', 'SPECIAL', 'OVA', 'ONA']:
            if episode_number > 1:
                logger.info(f"🎬 Converting episode {episode_number} to 1 for {anilist_format}: {series_title}")
                return 1, True, f"Converted to episode 1 for {anilist_format} format"
            return episode_number, False, f"Episode valid for {anilist_format}"

        # Handle TV series
        if not anilist_episodes:
            logger.debug(f"No episode count available for {series_title}, keeping episode {episode_number}")
            return episode_number, False, "No episode count available from AniList"

        # Episode is within expected range - likely correct
        if episode_number <= anilist_episodes:
            return episode_number, False, f"Episode {episode_number} within range (≤{anilist_episodes})"

        # Episode number exceeds AniList episode count - try to convert
        logger.warning(f"⚠️ Episode {episode_number} > AniList count {anilist_episodes} for {series_title}")

        # Try to get season information and convert absolute to per-season numbering
        converted_episode = self._convert_absolute_to_season_episode(
            episode_number, target_season, series_title, anime_data
        )

        if converted_episode != episode_number and 1 <= converted_episode <= anilist_episodes:
            return converted_episode, True, f"Converted from absolute episode (prev seasons: ~{episode_number - converted_episode} eps)"

        # If conversion failed but this might be ongoing anime, allow it
        if anilist_status in ['RELEASING', 'NOT_YET_RELEASED']:
            logger.info(f"📺 Allowing episode {episode_number} for ongoing anime: {series_title}")
            return episode_number, False, "Allowed for ongoing anime"

        # Cap at maximum episodes if conversion failed
        if episode_number > anilist_episodes:
            logger.warning(f"🔒 Capping episode {episode_number} → {anilist_episodes} for {series_title}")
            return anilist_episodes, True, f"Capped at maximum episodes ({anilist_episodes})"

        return episode_number, False, "Kept original episode number"

    def extract_season_from_episode_info(self, episode_info: Dict[str, Any]) -> int:
        """Extract season with conservative detection and validation"""
        # Check explicit season field first
        if 'season' in episode_info:
            try:
                season = int(episode_info['season'])
                if 1 <= season <= 20:  # Reasonable season range
                    return season
            except (ValueError, TypeError):
                pass

        # Check titles for season information (more conservative)
        texts_to_check = [
            episode_info.get('series_title', ''),
            episode_info.get('episode_title', ''),
        ]

        for text in texts_to_check:
            if text:
                season = self._extract_season_from_title_conservative(text)
                if season > 1:  # Only return if clearly a later season
                    logger.debug(f"Detected season {season} from text: '{text}'")
                    return season

        # Check URLs for season information
        for url_key in ['series_url', 'episode_url']:
            url = episode_info.get(url_key, '')
            if url:
                season_match = re.search(r'/season[_-]?(\d+)/', url, re.IGNORECASE)
                if season_match:
                    try:
                        season = int(season_match.group(1))
                        if 1 <= season <= 20:
                            logger.debug(f"Detected season {season} from URL: {url}")
                            return season
                    except ValueError:
                        pass

        return 1  # Default to season 1

    def _group_candidates_by_base_title(self, candidates: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
        """Group candidates by their base title (removing season info)"""
        groups = {}

        for candidate in candidates:
            primary_title = self._get_primary_title(candidate)
            base_title = self._extract_base_title(primary_title)
            base_key = self._normalize_title(base_title)

            if base_key not in groups:
                groups[base_key] = []
            groups[base_key].append(candidate)

        return groups

    def _find_best_in_group(self, normalized_target: str, target_season: int,
                           candidates: List[Dict[str, Any]], target_is_special: bool) -> Optional[Tuple[Dict[str, Any], float]]:
        """Find best match within a group of candidates with same base title"""
        season_matches = []
        general_matches = []

        for candidate in candidates:
            similarity = self._calculate_candidate_similarity(normalized_target, candidate)
            candidate_season = self._get_actual_season(candidate)
            candidate_format = candidate.get('format', '').upper()

            # Handle special episodes - prefer movies/specials for special episodes
            if target_is_special:
                if candidate_format in ['MOVIE', 'SPECIAL', 'OVA', 'ONA']:
                    similarity += 0.2  # Strong bonus for matching special to special
                elif candidate_season == target_season:
                    similarity += 0.1  # Small bonus for season match
                else:
                    similarity -= 0.1  # Penalty for mismatched season on special
            else:
                # Regular episode handling
                if candidate_season == target_season:
                    similarity += 0.15  # Bonus for exact season match
                elif candidate_season == 1 and target_season > 1:
                    similarity -= 0.05  # Small penalty for S1 when looking for later seasons
                elif candidate_format in ['MOVIE', 'SPECIAL', 'OVA', 'ONA']:
                    similarity -= 0.1  # Penalty for matching regular episode to special

            # Categorize matches
            if candidate_season == target_season or (target_is_special and candidate_format in ['MOVIE', 'SPECIAL', 'OVA', 'ONA']):
                season_matches.append((candidate, similarity, candidate_season))
            else:
                general_matches.append((candidate, similarity, candidate_season))

        # Prefer season/format matches, then general matches
        all_matches = season_matches + general_matches

        if not all_matches:
            return None

        # Get best match
        best_candidate, best_similarity, _ = max(all_matches, key=lambda x: x[1])
        return best_candidate, best_similarity

    def _extract_season_from_title_conservative(self, title: str) -> int:
        """Conservative season extraction - only match clear indicators"""
        if not title:
            return 1

        # Remove common false positives before checking
        cleaned_title = re.sub(r'\b(20\d{2}|19\d{2})\b', '', title)  # Remove years
        cleaned_title = re.sub(r'\b(episode|ep|e)\s*\d+\b', '', cleaned_title, flags=re.IGNORECASE)  # Remove episode numbers

        for pattern in self.season_patterns:
            match = re.search(pattern, cleaned_title, re.IGNORECASE)
            if match:
                try:
                    season = int(match.group(1))
                    if 1 <= season <= 20:  # Reasonable season range
                        # Additional validation - make sure it's not just a random number
                        if self._validate_season_context(cleaned_title, match, season):
                            return season
                except (ValueError, IndexError):
                    continue

        return 1

    def _validate_season_context(self, title: str, match: re.Match, season: int) -> bool:
        """Validate that a detected season number makes sense in context"""
        # Get text around the match
        start, end = match.span()
        before = title[:start].lower()
        after = title[end:].lower()

        # Strong indicators this is actually a season
        season_indicators = ['season', 'series', 'part', 'arc']
        if any(indicator in before[-20:] or indicator in after[:20] for indicator in season_indicators):
            return True

        # Check if it's at the end of title (common for seasons)
        if end >= len(title) - 5:  # Near the end
            return True

        # Check for roman numerals or ordinal patterns
        if re.search(r'\b(ii|iii|iv|v|vi|2nd|3rd|4th|5th)\b', title, re.IGNORECASE):
            return True

        # Be more cautious with season 1 (could be episode 1)
        if season == 1:
            return False

        return False

    def _get_actual_season(self, candidate: Dict[str, Any]) -> int:
        """Get the actual season number for a candidate, using multiple sources"""
        # Check if there's explicit season data
        if 'season' in candidate:
            try:
                season = int(candidate['season'])
                if 1 <= season <= 20:
                    return season
            except (ValueError, TypeError):
                pass

        # Extract from titles
        titles = self._extract_titles(candidate)
        for title in titles:
            season = self._extract_season_from_title_conservative(title)
            if season > 1:
                return season

        # Check start date to infer season (rough heuristic)
        start_date = candidate.get('startDate', {})
        if isinstance(start_date, dict) and start_date.get('year'):
            try:
                year = int(start_date['year'])
                # This is a very rough heuristic - would need better data to improve
                # For now, just use title-based detection
            except (ValueError, TypeError):
                pass

        return 1

    def _convert_absolute_to_season_episode(self, absolute_episode: int, target_season: int,
                                          series_title: str, anime_data: Dict[str, Any]) -> int:
        """Convert absolute episode number to per-season episode number"""
        if target_season == 1:
            return absolute_episode

        # Try to estimate episodes in previous seasons
        # This is a rough heuristic - ideally we'd query all seasons from AniList
        episodes_per_season = anime_data.get('episodes', 12)  # Use current season as estimate

        # Conservative estimate for previous seasons
        if episodes_per_season:
            estimated_prev_episodes = (target_season - 1) * episodes_per_season
            converted = absolute_episode - estimated_prev_episodes

            if 1 <= converted <= episodes_per_season * 2:  # Allow some flexibility
                logger.debug(f"Converted absolute ep {absolute_episode} → S{target_season} ep {converted}")
                return converted

        # Fallback: try common anime episode counts (12, 13, 24, 25)
        for eps_per_season in [12, 13, 24, 25]:
            estimated_prev_episodes = (target_season - 1) * eps_per_season
            converted = absolute_episode - estimated_prev_episodes

            if 1 <= converted <= eps_per_season + 5:  # Allow some flexibility
                logger.debug(f"Fallback converted absolute ep {absolute_episode} → S{target_season} ep {converted} (assumed {eps_per_season} eps/season)")
                return converted

        return absolute_episode

    def _is_special_episode(self, title: str) -> bool:
        """Check if this appears to be a special episode, movie, or OVA"""
        if not title:
            return False

        title_lower = title.lower()
        return any(re.search(pattern, title_lower) for pattern in self.special_patterns)

    def _extract_base_title(self, title: str) -> str:
        """Extract base title, removing season and other metadata"""
        if not title:
            return ""

        base_title = title

        # Remove season patterns more conservatively
        for pattern in self.season_patterns:
            # Only remove if it's clearly at the end or with clear separators
            pattern_with_context = pattern.replace(r'\b', r'(?:^|\s|:|-)')
            base_title = re.sub(pattern_with_context + r'(?:\s|$)', '', base_title, flags=re.IGNORECASE)

        # Remove year in parentheses at end
        base_title = re.sub(r'\s*\(\d{4}\)\s*$', '', base_title)

        # Remove common metadata at end
        metadata_patterns = [
            r'\s*-\s*Part\s*\d+\s*$',
            r'\s*:\s*Part\s*\d+\s*$',
            r'\s*\(.*(?:dub|sub|english)\).*$',
        ]

        for pattern in metadata_patterns:
            base_title = re.sub(pattern, '', base_title, flags=re.IGNORECASE)

        return base_title.strip()

    def _calculate_candidate_similarity(self, normalized_target: str, candidate: Dict[str, Any]) -> float:
        """Calculate similarity between target and candidate using all available titles"""
        max_similarity = 0.0

        titles = self._extract_titles(candidate)
        target_words = set(normalized_target.split())

        for title in titles:
            if title:
                normalized_candidate = self._normalize_title(title)
                similarity = self._calculate_similarity(normalized_target, normalized_candidate)

                # Bonus for word overlap
                candidate_words = set(normalized_candidate.split())
                if target_words and candidate_words:
                    word_overlap = len(target_words.intersection(candidate_words)) / len(target_words.union(candidate_words))
                    similarity = max(similarity, word_overlap * 0.9)

                max_similarity = max(max_similarity, similarity)

        return max_similarity

    def _extract_titles(self, anime: Dict[str, Any]) -> List[str]:
        """Extract all possible titles from anime data"""
        titles = []

        # Main titles
        title_obj = anime.get('title', {})
        if isinstance(title_obj, dict):
            for key in ['romaji', 'english', 'native']:
                title = title_obj.get(key)
                if title and title.strip():
                    titles.append(title.strip())
        elif isinstance(title_obj, str) and title_obj.strip():
            titles.append(title_obj.strip())

        # Synonyms
        synonyms = anime.get('synonyms', [])
        if synonyms:
            titles.extend([s.strip() for s in synonyms if s and s.strip()])

        return titles

    def _get_primary_title(self, anime: Dict[str, Any]) -> str:
        """Get the primary title for display purposes"""
        title_obj = anime.get('title', {})
        if isinstance(title_obj, dict):
            return (title_obj.get('romaji') or
                   title_obj.get('english') or
                   title_obj.get('native') or 'Unknown').strip()
        elif isinstance(title_obj, str):
            return title_obj.strip()
        return 'Unknown'

    def _normalize_title(self, title: str) -> str:
        """Normalize title for better matching"""
        if not title:
            return ""

        # Convert to lowercase
        normalized = title.lower()

        # Remove metadata patterns that don't affect matching
        patterns_to_remove = [
            r'\s*\((?:dub|sub|english dub|japanese)\)\s*',
            r'\s*\[(?:dub|sub|eng|jp)\]\s*',
        ]

        for pattern in patterns_to_remove:
            normalized = re.sub(pattern, ' ', normalized)

        # Normalize punctuation but keep meaningful separators
        normalized = re.sub(r'[^\w\s\-:!?]', ' ', normalized)

        # Normalize whitespace
        normalized = re.sub(r'\s+', ' ', normalized)

        return normalized.strip()

    def _calculate_similarity(self, title1: str, title2: str) -> float:
        """Calculate similarity between two normalized titles"""
        if not title1 or not title2:
            return 0.0

        # Exact match
        if title1 == title2:
            return 1.0

        # Check for substring relationships
        shorter, longer = (title1, title2) if len(title1) < len(title2) else (title2, title1)
        if shorter in longer:
            # High score for substring matches, but not perfect
            return 0.95 * (len(shorter) / len(longer))

        # Sequence similarity
        sequence_similarity = SequenceMatcher(None, title1, title2).ratio()

        # Word-based similarity for better handling of word order differences
        words1 = set(title1.split())
        words2 = set(title2.split())

        if words1 and words2:
            common_words = words1.intersection(words2)
            total_words = words1.union(words2)

            word_overlap = len(common_words) / len(total_words)
            word_coverage1 = len(common_words) / len(words1)
            word_coverage2 = len(common_words) / len(words2)

            # Average coverage of both titles
            word_coverage = (word_coverage1 + word_coverage2) / 2

            # Combine metrics
            word_similarity = (word_overlap * 0.3) + (word_coverage * 0.7)
            final_similarity = (sequence_similarity * 0.4) + (word_similarity * 0.6)
        else:
            final_similarity = sequence_similarity

        return final_similarity

    def extract_episode_number(self, episode_title: str) -> Optional[int]:
        """Extract episode number from episode title"""
        if not episode_title:
            return None

        # Patterns ordered by specificity
        patterns = [
            r'(?:episode|ep\.?)\s*(\d+)',
            r'^(\d+)\s*[-:]',  # Number at start with separator
            r'^\s*(\d+)\s*$',  # Just a number
            r'#(\d+)',
            r'\be(\d+)\b',
            r'\b(\d+)(?:\s*$|\s*[-:])',  # Number at end or with separator
        ]

        title_lower = episode_title.lower().strip()

        for pattern in patterns:
            match = re.search(pattern, title_lower)
            if match:
                try:
                    episode_num = int(match.group(1))
                    if 1 <= episode_num <= 9999:  # Reasonable range
                        return episode_num
                except ValueError:
                    continue

        return None

    def normalize_for_comparison(self, title: str) -> str:
        """Normalize title specifically for comparison purposes"""
        return self._normalize_title(title)