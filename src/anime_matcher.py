"""Anime title matching utilities with fuzzy matching"""
import re
from typing import List, Dict, Any, Optional, Tuple
from difflib import SequenceMatcher
import logging

logger = logging.getLogger(__name__)

class AnimeMatcher:
    def __init__(self, similarity_threshold: float = 0.8):
        self.similarity_threshold = similarity_threshold

    def normalize_title(self, title: str) -> str:
        """Normalize anime title for better matching"""
        if not title:
            return ""

        # Convert to lowercase
        title = title.lower()

        # Remove common anime suffixes/prefixes
        title = re.sub(r'\s*\(dub\)\s*', '', title)
        title = re.sub(r'\s*\(sub\)\s*', '', title)
        title = re.sub(r'\s*\(english dub\)\s*', '', title)
        title = re.sub(r'\s*\(japanese\)\s*', '', title)

        # Remove season/episode indicators
        title = re.sub(r'\s+season\s+\d+', '', title)
        title = re.sub(r'\s+s\d+', '', title)
        title = re.sub(r'\s+\d+nd season', '', title)
        title = re.sub(r'\s+\d+rd season', '', title)
        title = re.sub(r'\s+\d+th season', '', title)
        title = re.sub(r'\s+second season', '', title)
        title = re.sub(r'\s+third season', '', title)
        title = re.sub(r'\s+final season', '', title)

        # Remove special characters and extra spaces
        title = re.sub(r'[^\w\s]', '', title)
        title = re.sub(r'\s+', ' ', title).strip()

        return title

    def calculate_similarity(self, title1: str, title2: str) -> float:
        """Calculate similarity between two titles"""
        norm1 = self.normalize_title(title1)
        norm2 = self.normalize_title(title2)

        if not norm1 or not norm2:
            return 0.0

        # Use SequenceMatcher for similarity
        similarity = SequenceMatcher(None, norm1, norm2).ratio()

        # Bonus points for exact matches after normalization
        if norm1 == norm2:
            similarity = 1.0

        # Check for substring matches
        elif norm1 in norm2 or norm2 in norm1:
            similarity = max(similarity, 0.9)

        return similarity

    def find_best_match(self, target_title: str, anime_list: List[Dict[str, Any]]) -> Optional[Tuple[Dict[str, Any], float]]:
        """Find best matching anime from AniList search results"""
        best_match = None
        best_similarity = 0.0

        for anime in anime_list:
            # Get all possible titles to check
            titles_to_check = []

            # Add main titles
            title_obj = anime.get('title', {})
            if title_obj.get('romaji'):
                titles_to_check.append(title_obj['romaji'])
            if title_obj.get('english'):
                titles_to_check.append(title_obj['english'])
            if title_obj.get('native'):
                titles_to_check.append(title_obj['native'])

            # Add synonyms
            synonyms = anime.get('synonyms', [])
            if synonyms:
                titles_to_check.extend(synonyms)

            # Calculate similarity for each title
            max_similarity = 0.0
            for title in titles_to_check:
                if title:
                    similarity = self.calculate_similarity(target_title, title)
                    max_similarity = max(max_similarity, similarity)

            # Update best match if this is better
            if max_similarity > best_similarity:
                best_similarity = max_similarity
                best_match = anime

        # Only return if similarity meets threshold
        if best_similarity >= self.similarity_threshold:
            logger.info(f"Found match: {target_title} -> {best_match.get('title', {}).get('romaji', 'Unknown')} (similarity: {best_similarity:.2f})")
            return best_match, best_similarity

        logger.warning(f"No good match found for: {target_title} (best similarity: {best_similarity:.2f})")
        return None

    def extract_episode_number(self, episode_title: str) -> Optional[int]:
        """Extract episode number from episode title"""
        if not episode_title:
            return None

        # Try various patterns for episode numbers
        patterns = [
            r'episode\s+(\d+)',
            r'ep\.?\s*(\d+)',
            r'e(\d+)',
            r'^(\d+)\s*[-:]',  # Episode number at the beginning
            r'#(\d+)',
        ]

        for pattern in patterns:
            match = re.search(pattern, episode_title.lower())
            if match:
                try:
                    return int(match.group(1))
                except ValueError:
                    continue

        # If no pattern matches, try to find any number
        numbers = re.findall(r'\d+', episode_title)
        if numbers:
            # Return the first number found
            try:
                return int(numbers[0])
            except ValueError:
                pass

        return None