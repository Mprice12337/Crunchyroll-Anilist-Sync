"""
Simplified anime title matching with fuzzy matching
"""

import re
import logging
from typing import List, Dict, Any, Optional, Tuple
from difflib import SequenceMatcher

logger = logging.getLogger(__name__)

class AnimeMatcher:
    """Matches anime titles between Crunchyroll and AniList"""

    def __init__(self, similarity_threshold: float = 0.8):
        self.similarity_threshold = similarity_threshold

    def find_best_match(self, target_title: str, candidates: List[Dict[str, Any]]) -> Optional[Tuple[Dict[str, Any], float]]:
        """Find the best matching anime from candidates"""
        if not target_title or not candidates:
            return None

        best_match = None
        best_similarity = 0.0

        normalized_target = self._normalize_title(target_title)

        for candidate in candidates:
            max_similarity = 0.0

            # Get all possible titles for this candidate
            titles_to_check = self._extract_titles(candidate)

            # Calculate similarity for each title
            for title in titles_to_check:
                if title:
                    normalized_candidate = self._normalize_title(title)
                    similarity = self._calculate_similarity(normalized_target, normalized_candidate)
                    max_similarity = max(max_similarity, similarity)

            # Update best match if this is better
            if max_similarity > best_similarity:
                best_similarity = max_similarity
                best_match = candidate

        # Only return if similarity meets threshold
        if best_similarity >= self.similarity_threshold:
            logger.debug(f"Matched '{target_title}' to '{self._get_primary_title(best_match)}' (similarity: {best_similarity:.2f})")
            return best_match, best_similarity

        logger.debug(f"No good match found for '{target_title}' (best similarity: {best_similarity:.2f})")
        return None

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
        """Normalize title for better matching"""
        if not title:
            return ""

        # Convert to lowercase
        normalized = title.lower()

        # Remove common anime suffixes/prefixes
        patterns_to_remove = [
            r'\s*\(dub\)\s*',
            r'\s*\(sub\)\s*',
            r'\s*\(english dub\)\s*',
            r'\s*\(japanese\)\s*',
            r'\s*season\s+\d+\s*',
            r'\s*s\d+\s*',
            r'\s*\d+nd season\s*',
            r'\s*\d+rd season\s*',
            r'\s*\d+th season\s*',
            r'\s*second season\s*',
            r'\s*third season\s*',
            r'\s*final season\s*',
            r'\s*part\s+\d+\s*',
            r'\s*cour\s+\d+\s*',
        ]

        for pattern in patterns_to_remove:
            normalized = re.sub(pattern, ' ', normalized)

        # Remove special characters and extra spaces
        normalized = re.sub(r'[^\w\s]', ' ', normalized)
        normalized = re.sub(r'\s+', ' ', normalized)
        normalized = normalized.strip()

        return normalized

    def _calculate_similarity(self, title1: str, title2: str) -> float:
        """Calculate similarity between two normalized titles"""
        if not title1 or not title2:
            return 0.0

        # Exact match after normalization
        if title1 == title2:
            return 1.0

        # Check for substring matches (high bonus)
        if title1 in title2 or title2 in title1:
            # Calculate how much of the shorter string is in the longer one
            shorter, longer = (title1, title2) if len(title1) < len(title2) else (title2, title1)
            return max(0.9, len(shorter) / len(longer))

        # Use sequence matcher for fuzzy matching
        similarity = SequenceMatcher(None, title1, title2).ratio()

        # Bonus for word overlap
        words1 = set(title1.split())
        words2 = set(title2.split())

        if words1 and words2:
            word_overlap = len(words1.intersection(words2)) / max(len(words1), len(words2))
            # Combine similarities with word overlap getting some weight
            similarity = (similarity * 0.7) + (word_overlap * 0.3)

        return similarity

    def extract_episode_number(self, episode_title: str) -> Optional[int]:
        """Extract episode number from episode title"""
        if not episode_title:
            return None

        # Common patterns for episode numbers
        patterns = [
            r'episode\s+(\d+)',
            r'ep\.?\s*(\d+)',
            r'e(\d+)',
            r'^(\d+)\s*[-:]',  # Number at the beginning
            r'#(\d+)',
            r'\b(\d+)\b',  # Any standalone number
        ]

        for pattern in patterns:
            match = re.search(pattern, episode_title.lower())
            if match:
                try:
                    return int(match.group(1))
                except ValueError:
                    continue

        return None