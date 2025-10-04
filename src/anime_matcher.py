"""
Anime Title Matching with Season Detection
"""

import re
import logging
from typing import List, Dict, Any, Optional, Tuple
from difflib import SequenceMatcher

logger = logging.getLogger(__name__)


class AnimeMatcher:
    """Matches anime titles between Crunchyroll and AniList with season awareness"""

    def __init__(self, similarity_threshold: float = 0.8):
        self.similarity_threshold = similarity_threshold
        self.movie_formats = ['MOVIE', 'SPECIAL', 'OVA', 'ONA']

    def find_best_match_with_season(self, target_title: str, candidates: List[Dict[str, Any]],
                                    target_season: int = 1) -> Optional[Tuple[Dict[str, Any], float, int]]:
        """
        Find best anime match with season awareness

        Args:
            target_title: Title to search for
            candidates: List of AniList entries to match against
            target_season: Expected season number (0 for movies)

        Returns:
            Tuple of (matched_entry, similarity_score, detected_season) or None
        """
        if not target_title or not candidates:
            return None

        if target_season == 0:
            return self._find_best_movie_match(target_title, candidates)

        best_match = None
        best_similarity = 0.0
        best_season = target_season

        for candidate in candidates:
            format_type = (candidate.get('format', '') or '').upper()
            if format_type in self.movie_formats:
                continue

            similarity = self._calculate_title_similarity(target_title, candidate)
            detected_season = self._detect_season_from_entry(candidate)

            if detected_season == target_season:
                similarity += 0.1

            if similarity > best_similarity and similarity >= self.similarity_threshold:
                best_similarity = similarity
                best_match = candidate
                best_season = detected_season

        if best_match:
            anime_title = self._get_primary_title(best_match)
            logger.info(
                f"✅ Matched '{target_title}' to '{anime_title}' S{best_season} (similarity: {best_similarity:.2f})")
            return best_match, best_similarity, best_season

        return None

    def find_best_match(self, target_title: str, candidates: List[Dict[str, Any]],
                        target_season: int = 1) -> Optional[Tuple[Dict[str, Any], float]]:
        """Legacy compatibility method without season return"""
        result = self.find_best_match_with_season(target_title, candidates, target_season)
        if result:
            match, similarity, _ = result
            return match, similarity
        return None

    def find_best_match_with_episode_validation(self, target_title: str, target_episode: int,
                                                candidates: List[Dict[str, Any]],
                                                estimated_season: int = 1) -> Optional[
        Tuple[Dict[str, Any], float, int, int]]:
        """Legacy compatibility with episode validation"""
        result = self.find_best_match_with_season(target_title, candidates, estimated_season)
        if result:
            match, similarity, season = result
            return match, similarity, season, target_episode
        return None

    def _find_best_movie_match(self, target_title: str, candidates: List[Dict[str, Any]]) -> Optional[
        Tuple[Dict[str, Any], float, int]]:
        """Find best match for movies and specials"""
        clean_target = re.sub(r'\s*-?\s*movie\s*', '', target_title, flags=re.IGNORECASE)
        clean_target = re.sub(r'\s*-?\s*0\s*$', '', clean_target)

        best_match = None
        best_similarity = 0.0

        for candidate in candidates:
            format_type = (candidate.get('format', '') or '').upper()
            if format_type not in self.movie_formats:
                continue

            # Skip obvious commercials/promotional content
            title_obj = candidate.get('title', {})
            all_titles = ' '.join([
                title_obj.get('romaji', ''),
                title_obj.get('english', ''),
                title_obj.get('native', '')
            ]).lower()

            commercial_indicators = ['cm', 'commercial', 'pv', 'promotional', 'advertisement', 'ad']
            if any(indicator in all_titles for indicator in commercial_indicators):
                continue

            similarity = self._calculate_title_similarity(clean_target, candidate)

            # Strongly prefer MOVIE format over SPECIAL/OVA/ONA
            if format_type == 'MOVIE':
                similarity += 0.15

            if similarity > best_similarity and similarity >= 0.75:
                best_similarity = similarity
                best_match = candidate

        if best_match:
            anime_title = self._get_primary_title(best_match)
            format_type = best_match.get('format', 'Unknown')
            logger.info(f"🎬 Found movie match: '{anime_title}' ({format_type}) - similarity: {best_similarity:.2f}")
            return best_match, best_similarity, 0

        return None

    def _detect_season_from_entry(self, entry: Dict) -> int:
        """Detect season number from AniList entry title"""
        title_obj = entry.get('title', {})
        romaji = title_obj.get('romaji', '')
        english = title_obj.get('english', '')

        for title in [romaji, english]:
            if not title:
                continue

            patterns = [
                (r'(\d+)(?:st|nd|rd|th)\s+Season', lambda m: int(m.group(1))),
                (r'Season\s+(\d+)', lambda m: int(m.group(1))),
                (r'\bPart\s+(\d+)', lambda m: int(m.group(1))),
                (r'\b(II|III|IV|V|VI)\b', self._roman_to_int),
            ]

            for pattern, extractor in patterns:
                match = re.search(pattern, title, re.IGNORECASE)
                if match:
                    season = extractor(match)
                    if 1 <= season <= 10:
                        return season

        return 1

    def _roman_to_int(self, match) -> int:
        """Convert Roman numerals to integers"""
        roman_map = {'II': 2, 'III': 3, 'IV': 4, 'V': 5, 'VI': 6}
        return roman_map.get(match.group(1), 1)

    def _extract_base_title(self, title: str) -> str:
        """Extract base title without season indicators"""
        base = title

        patterns_to_remove = [
            r'Season\s*\d+',
            r'\d+(?:st|nd|rd|th)?\s*Season',
            r'\bS\d+\b',
            r'Part\s*\d+',
            r'\b(?:II|III|IV|V|VI)\b',
            r'\s+\d+$',
        ]

        for pattern in patterns_to_remove:
            base = re.sub(pattern, '', base, flags=re.IGNORECASE)

        return base.strip()

    def _calculate_title_similarity(self, target_title: str, candidate: Dict[str, Any]) -> float:
        """Calculate similarity score between target and candidate titles"""
        target_normalized = self._normalize_title(target_title)
        target_base = self._extract_base_title(target_normalized)
        target_no_space = target_normalized.replace(' ', '')

        max_similarity = 0.0
        titles_to_check = self._extract_titles(candidate)

        for title in titles_to_check:
            if title:
                candidate_normalized = self._normalize_title(title)
                candidate_base = self._extract_base_title(candidate_normalized)
                candidate_no_space = candidate_normalized.replace(' ', '')

                full_similarity = self._calculate_string_similarity(target_normalized, candidate_normalized)
                base_similarity = self._calculate_string_similarity(target_base, candidate_base)

                space_removed_similarity = 0.0
                if target_no_space != target_normalized or candidate_no_space != candidate_normalized:
                    space_removed_similarity = self._calculate_string_similarity(target_no_space, candidate_no_space)

                    if space_removed_similarity >= 0.95:
                        space_removed_similarity = 1.0

                combined_similarity = max(
                    (base_similarity * 0.7) + (full_similarity * 0.3),
                    space_removed_similarity
                )

                max_similarity = max(max_similarity, combined_similarity)

        return max_similarity

    def _calculate_string_similarity(self, str1: str, str2: str) -> float:
        """Calculate similarity between two strings using multiple methods"""
        if not str1 or not str2:
            return 0.0

        if str1 == str2:
            return 1.0

        if str1 in str2 or str2 in str1:
            shorter, longer = (str1, str2) if len(str1) < len(str2) else (str2, str1)
            return max(0.9, len(shorter) / len(longer))

        sequence_similarity = SequenceMatcher(None, str1, str2).ratio()

        words1 = set(str1.split())
        words2 = set(str2.split())

        if words1 and words2:
            common_words = words1.intersection(words2)
            total_words = words1.union(words2)

            if total_words:
                word_overlap = len(common_words) / len(total_words)
                coverage1 = len(common_words) / len(words1)
                coverage2 = len(common_words) / len(words2)
                word_coverage = (coverage1 + coverage2) / 2

                word_similarity = (word_overlap * 0.4) + (word_coverage * 0.6)
                final_similarity = (sequence_similarity * 0.6) + (word_similarity * 0.4)
            else:
                final_similarity = sequence_similarity
        else:
            final_similarity = sequence_similarity

        return final_similarity

    def _extract_titles(self, anime: Dict[str, Any]) -> List[str]:
        """Extract all possible titles from anime entry"""
        titles = []

        title_obj = anime.get('title', {})
        if isinstance(title_obj, dict):
            for key in ['romaji', 'english', 'native']:
                title = title_obj.get(key)
                if title:
                    titles.append(title)
        elif isinstance(title_obj, str):
            titles.append(title_obj)

        synonyms = anime.get('synonyms', [])
        if synonyms:
            titles.extend(synonyms)

        return [title for title in titles if title]

    def _get_primary_title(self, anime: Dict[str, Any]) -> str:
        """Get the primary display title"""
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

        patterns_to_remove = [
            r'\s*\(dub\)\s*',
            r'\s*\(sub\)\s*',
            r'\s*\(\d{4}\)\s*$',
            r'[^\w\s\-:!?]',
        ]

        for pattern in patterns_to_remove:
            normalized = re.sub(pattern, ' ', normalized)

        normalized = re.sub(r'\s+', ' ', normalized).strip()

        return normalized