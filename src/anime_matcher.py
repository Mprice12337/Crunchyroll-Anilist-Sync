"""
Enhanced anime title matching with season support and improved fuzzy matching
"""

import re
import logging
from typing import List, Dict, Any, Optional, Tuple
from difflib import SequenceMatcher

logger = logging.getLogger(__name__)

class AnimeMatcher:
    """Enhanced anime matcher with season support and better title matching"""

    def __init__(self, similarity_threshold: float = 0.8):
        self.similarity_threshold = similarity_threshold

        # Season patterns for better detection
        self.season_patterns = [
            r'Season[\s]*(\d+)',  # Season 2
            r'S(\d+)',  # S2
            r'(\d+)(?:st|nd|rd|th)?\s*Season',  # 2nd Season
            r'Part[\s]*(\d+)',  # Part 2
            r'Cour[\s]*(\d+)',  # Cour 2
        ]

    def find_best_match(self, target_title: str, candidates: List[Dict[str, Any]],
                       target_season: int = 1) -> Optional[Tuple[Dict[str, Any], float]]:
        """Find the best matching anime from candidates with season consideration"""
        if not target_title or not candidates:
            return None

        best_match = None
        best_similarity = 0.0

        normalized_target = self._normalize_title(target_title)

        logger.debug(f"Matching '{target_title}' (season {target_season}) against {len(candidates)} candidates")

        for candidate in candidates:
            max_similarity = 0.0

            # Get all possible titles for this candidate
            titles_to_check = self._extract_titles(candidate)

            # Calculate similarity for each title
            for title in titles_to_check:
                if title:
                    normalized_candidate = self._normalize_title(title)
                    similarity = self._calculate_similarity(normalized_target, normalized_candidate)

                    # Apply season bonus if seasons match
                    similarity = self._apply_season_bonus(similarity, candidate, target_season)

                    max_similarity = max(max_similarity, similarity)

            # Update best match if this is better
            if max_similarity > best_similarity:
                best_similarity = max_similarity
                best_match = candidate

        # Only return if similarity meets threshold
        if best_similarity >= self.similarity_threshold:
            primary_title = self._get_primary_title(best_match)
            logger.info(f"✅ Matched '{target_title}' to '{primary_title}' (similarity: {best_similarity:.2f})")
            return best_match, best_similarity

        logger.warning(f"❌ No good match found for '{target_title}' (best similarity: {best_similarity:.2f})")
        return None

    def find_best_match_with_season(self, target_title: str, candidates: List[Dict[str, Any]],
                                   target_season: int = 1) -> Optional[Tuple[Dict[str, Any], float, int]]:
        """Enhanced matching that returns the matched season as well"""
        if not target_title or not candidates:
            return None

        best_match = None
        best_similarity = 0.0
        matched_season = target_season

        normalized_target = self._normalize_title(target_title)

        logger.debug(f"Season-aware matching '{target_title}' (season {target_season})")

        # Group candidates by base title to handle multiple seasons
        title_groups = self._group_candidates_by_base_title(candidates)

        for base_title, season_candidates in title_groups.items():
            # Find best match within this title group
            group_match, group_similarity, group_season = self._match_within_title_group(
                normalized_target, season_candidates, target_season
            )

            if group_similarity > best_similarity:
                best_similarity = group_similarity
                best_match = group_match
                matched_season = group_season

        if best_similarity >= self.similarity_threshold:
            primary_title = self._get_primary_title(best_match)
            logger.info(f"✅ Season-matched '{target_title}' to '{primary_title}' season {matched_season} (similarity: {best_similarity:.2f})")
            return best_match, best_similarity, matched_season

        logger.warning(f"❌ No season match found for '{target_title}' (best similarity: {best_similarity:.2f})")
        return None

    def _group_candidates_by_base_title(self, candidates: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
        """Group candidates by their base title (without season info)"""
        groups = {}

        for candidate in candidates:
            primary_title = self._get_primary_title(candidate)
            base_title = self._extract_base_title(primary_title)

            if base_title not in groups:
                groups[base_title] = []
            groups[base_title].append(candidate)

        return groups

    def _match_within_title_group(self, normalized_target: str, candidates: List[Dict[str, Any]],
                                 target_season: int) -> Tuple[Optional[Dict[str, Any]], float, int]:
        """Match within a group of candidates with the same base title"""
        best_match = None
        best_similarity = 0.0
        best_season = target_season

        # First, try to find exact season match
        season_matches = []
        general_matches = []

        for candidate in candidates:
            candidate_season = self._extract_candidate_season(candidate)
            similarity = self._calculate_candidate_similarity(normalized_target, candidate)

            if candidate_season == target_season:
                season_matches.append((candidate, similarity, candidate_season))
            else:
                general_matches.append((candidate, similarity, candidate_season))

        # Prefer season matches
        all_matches = season_matches + general_matches

        for candidate, similarity, season in all_matches:
            # Apply season bonus
            if season == target_season:
                similarity += 0.1  # Bonus for matching season

            if similarity > best_similarity:
                best_similarity = similarity
                best_match = candidate
                best_season = season

        return best_match, best_similarity, best_season

    def _extract_candidate_season(self, candidate: Dict[str, Any]) -> int:
        """Extract season number from a candidate anime"""
        # Check various title fields for season information
        titles_to_check = self._extract_titles(candidate)

        for title in titles_to_check:
            season = self._extract_season_from_title(title)
            if season > 1:
                return season

        # Check if there's a season field in the data
        if 'season' in candidate:
            try:
                return int(candidate['season'])
            except (ValueError, TypeError):
                pass

        # Default to season 1
        return 1

    def _extract_season_from_title(self, title: str) -> int:
        """Extract season number from a title"""
        if not title:
            return 1

        for pattern in self.season_patterns:
            match = re.search(pattern, title, re.IGNORECASE)
            if match:
                try:
                    return int(match.group(1))
                except (ValueError, IndexError):
                    continue

        return 1

    def _extract_base_title(self, title: str) -> str:
        """Extract base title without season information"""
        if not title:
            return ""

        base_title = title

        # Remove season patterns
        for pattern in self.season_patterns:
            base_title = re.sub(pattern, '', base_title, flags=re.IGNORECASE)

        # Remove common season suffixes
        season_suffixes = [
            r'\s*-\s*Season\s*\d+',
            r'\s*:\s*Season\s*\d+',
            r'\s*\(\d{4}\)',  # Year
            r'\s*Part\s*\d+',
            r'\s*Cour\s*\d+',
        ]

        for suffix in season_suffixes:
            base_title = re.sub(suffix, '', base_title, flags=re.IGNORECASE)

        return base_title.strip()

    def _calculate_candidate_similarity(self, normalized_target: str, candidate: Dict[str, Any]) -> float:
        """Calculate similarity between target and candidate"""
        max_similarity = 0.0

        titles_to_check = self._extract_titles(candidate)

        for title in titles_to_check:
            if title:
                normalized_candidate = self._normalize_title(title)
                similarity = self._calculate_similarity(normalized_target, normalized_candidate)
                max_similarity = max(max_similarity, similarity)

        return max_similarity

    def _apply_season_bonus(self, base_similarity: float, candidate: Dict[str, Any],
                          target_season: int) -> float:
        """Apply bonus for season matching"""
        candidate_season = self._extract_candidate_season(candidate)

        if candidate_season == target_season:
            # Bonus for exact season match
            return min(1.0, base_similarity + 0.1)
        elif candidate_season == 1 and target_season > 1:
            # Small penalty for season 1 when looking for later seasons
            return max(0.0, base_similarity - 0.05)
        else:
            # Small penalty for wrong season
            return max(0.0, base_similarity - 0.1)

    def _extract_titles(self, anime: Dict[str, Any]) -> List[str]:
        """Extract all possible titles from anime data"""
        titles = []

        # Main titles
        title_obj = anime.get('title', {})
        if isinstance(title_obj, dict):
            for key in ['romaji', 'english', 'native']:
                title = title_obj.get(key)
                if title:
                    titles.append(title)
        elif isinstance(title_obj, str):
            titles.append(title_obj)

        # Synonyms
        synonyms = anime.get('synonyms', [])
        if synonyms:
            titles.extend(synonyms)

        return [title for title in titles if title]

    def _get_primary_title(self, anime: Dict[str, Any]) -> str:
        """Get the primary title for display purposes"""
        title_obj = anime.get('title', {})
        if isinstance(title_obj, dict):
            return title_obj.get('romaji') or title_obj.get('english') or title_obj.get('native') or 'Unknown'
        elif isinstance(title_obj, str):
            return title_obj
        return 'Unknown'

    def _normalize_title(self, title: str) -> str:
        """Enhanced title normalization for better matching"""
        if not title:
            return ""

        # Convert to lowercase
        normalized = title.lower()

        # Remove common anime suffixes/prefixes but be more selective
        patterns_to_remove = [
            r'\s*\(dub\)\s*',
            r'\s*\(sub\)\s*',
            r'\s*\(english dub\)\s*',
            r'\s*\(japanese\)\s*',
            # Be more careful with season removal - only remove if it's clearly metadata
            r'\s*-\s*season\s+\d+\s*$',
            r'\s*:\s*season\s+\d+\s*$',
            r'\s*part\s+\d+\s*$',
            r'\s*cour\s+\d+\s*$',
            # Remove years in parentheses at the end
            r'\s*\(\d{4}\)\s*$',
        ]

        for pattern in patterns_to_remove:
            normalized = re.sub(pattern, ' ', normalized)

        # Remove special characters but keep important ones
        # Keep hyphens and colons as they're often significant in anime titles
        normalized = re.sub(r'[^\w\s\-:!?]', ' ', normalized)

        # Normalize whitespace
        normalized = re.sub(r'\s+', ' ', normalized)
        normalized = normalized.strip()

        return normalized

    def _calculate_similarity(self, title1: str, title2: str) -> float:
        """Enhanced similarity calculation with multiple approaches"""
        if not title1 or not title2:
            return 0.0

        # Exact match after normalization
        if title1 == title2:
            return 1.0

        # Check for substring matches with better scoring
        if title1 in title2 or title2 in title1:
            shorter, longer = (title1, title2) if len(title1) < len(title2) else (title2, title1)
            substring_score = len(shorter) / len(longer)
            # Give high score for substring matches
            return max(0.9, substring_score)

        # Use sequence matcher for fuzzy matching
        sequence_similarity = SequenceMatcher(None, title1, title2).ratio()

        # Word-based similarity
        words1 = set(title1.split())
        words2 = set(title2.split())

        if words1 and words2:
            # Calculate word overlap
            common_words = words1.intersection(words2)
            total_words = words1.union(words2)
            word_overlap = len(common_words) / len(total_words) if total_words else 0

            # Calculate word coverage (how much of each title is covered)
            coverage1 = len(common_words) / len(words1) if words1 else 0
            coverage2 = len(common_words) / len(words2) if words2 else 0
            word_coverage = (coverage1 + coverage2) / 2

            # Combine word-based metrics
            word_similarity = (word_overlap * 0.4) + (word_coverage * 0.6)

            # Combine sequence and word similarities
            final_similarity = (sequence_similarity * 0.6) + (word_similarity * 0.4)
        else:
            final_similarity = sequence_similarity

        return final_similarity

    def extract_episode_number(self, episode_title: str) -> Optional[int]:
        """Extract episode number from episode title"""
        if not episode_title:
            return None

        # Enhanced patterns for episode numbers
        patterns = [
            r'episode\s+(\d+)',
            r'ep\.?\s*(\d+)',
            r'e(\d+)',
            r'^(\d+)\s*[-:]',  # Number at the beginning
            r'#(\d+)',
            r'\b(\d+)\b',  # Any standalone number (last resort)
        ]

        for pattern in patterns:
            match = re.search(pattern, episode_title.lower())
            if match:
                try:
                    return int(match.group(1))
                except ValueError:
                    continue

        return None

    def extract_season_from_episode_info(self, episode_info: Dict[str, Any]) -> int:
        """Extract season from episode information"""
        # Check if season is explicitly provided
        if 'season' in episode_info:
            try:
                return int(episode_info['season'])
            except (ValueError, TypeError):
                pass

        # Check episode title for season information
        episode_title = episode_info.get('episode_title', '')
        series_title = episode_info.get('series_title', '')

        for text in [episode_title, series_title]:
            season = self._extract_season_from_title(text)
            if season > 1:
                return season

        # Check URLs for season information
        for url_key in ['series_url', 'episode_url']:
            url = episode_info.get(url_key, '')
            if url:
                season_match = re.search(r'season[-_](\d+)', url, re.IGNORECASE)
                if season_match:
                    try:
                        return int(season_match.group(1))
                    except ValueError:
                        pass

        return 1

    def normalize_for_comparison(self, title: str) -> str:
        """Normalize title specifically for comparison purposes"""
        return self._normalize_title(title)