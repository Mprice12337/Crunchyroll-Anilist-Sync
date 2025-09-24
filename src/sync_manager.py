"""
Enhanced sync manager with improved movie/special handling
"""

import logging
import time
from typing import Dict, List, Any, Optional, Tuple
from pathlib import Path

from crunchyroll_scraper import CrunchyrollScraper
from anilist_client import AniListClient
from anime_matcher import AnimeMatcher
from cache_manager import CacheManager

logger = logging.getLogger(__name__)

class SyncManager:
    """Enhanced sync manager with improved season handling and progress tracking"""

    def __init__(self, **config):
        self.config = config
        self.cache_manager = CacheManager()

        # Initialize components with enhanced configuration
        self.crunchyroll_scraper = CrunchyrollScraper(
            email=config['crunchyroll_email'],
            password=config['crunchyroll_password'],
            headless=config.get('headless', True),
            flaresolverr_url=config.get('flaresolverr_url')
        )

        self.anilist_client = AniListClient(
            client_id=config['anilist_client_id'],
            client_secret=config['anilist_client_secret']
        )

        # Enhanced anime matcher with better similarity threshold
        self.anime_matcher = AnimeMatcher(similarity_threshold=0.75)

        # Enhanced state tracking
        self.watch_history: List[Dict[str, Any]] = []
        self.sync_results = {
            'total_episodes': 0,
            'successful_updates': 0,
            'failed_updates': 0,
            'skipped_episodes': 0,
            'season_matches': 0,
            'season_mismatches': 0,
            'no_matches_found': 0,
            'movies_skipped': 0  # New counter for skipped movies
        }

    def run_sync(self) -> bool:
        """Execute the enhanced sync process"""
        try:
            logger.info("🚀 Starting enhanced Crunchyroll-AniList sync...")

            # Clear cache if requested
            if self.config.get('clear_cache'):
                logger.info("🧹 Clearing cache...")
                self.cache_manager.clear_all_cache()

            # Step 1: Authenticate with services
            if not self._authenticate_services():
                return False

            # Step 2: Scrape Crunchyroll history
            if not self._scrape_crunchyroll_history():
                return False

            # Step 3: Process and update AniList with season awareness
            if not self._update_anilist_progress_with_seasons():
                return False

            # Step 4: Report enhanced results
            self._report_enhanced_results()

            return True

        except KeyboardInterrupt:
            logger.info("⏹️ Process interrupted by user")
            return False
        except Exception as e:
            logger.error(f"❌ Sync process failed: {e}", exc_info=True)
            return False
        finally:
            self._cleanup()

    def _authenticate_services(self) -> bool:
        """Add timing information to see the improvement"""
        logger.info("🔐 Authenticating with services...")
        start_time = time.time()

        # Crunchyroll auth (should be fast now)
        cr_start = time.time()
        if not self.crunchyroll_scraper.authenticate():
            return False
        cr_time = time.time() - cr_start
        logger.info(f"⚡ Crunchyroll auth: {cr_time:.1f}s")

        # AniList auth
        al_start = time.time()
        if not self.anilist_client.authenticate():
            return False
        al_time = time.time() - al_start
        logger.info(f"⚡ AniList auth: {al_time:.1f}s")

        total_time = time.time() - start_time
        logger.info(f"✅ Total authentication: {total_time:.1f}s")
        return True

    def _scrape_crunchyroll_history(self) -> bool:
        """Scrape watch history from Crunchyroll"""
        logger.info("📚 Scraping Crunchyroll watch history...")

        try:
            self.watch_history = self.crunchyroll_scraper.get_watch_history(
                max_pages=self.config.get('max_pages', 10)
            )

            if not self.watch_history:
                logger.warning("⚠️ No watch history found")
                return True  # Not necessarily an error

            # Enhanced debug data saving
            if self.config.get('debug'):
                self._save_enhanced_debug_data('watch_history.json', self.watch_history)

            # Log sample of what was found for user verification
            self._log_sample_episodes()

            return True

        except Exception as e:
            logger.error(f"Failed to scrape Crunchyroll history: {e}")
            return False

    def _log_sample_episodes(self) -> None:
        """Log a sample of episodes for user verification with improved detail"""
        if not self.watch_history:
            return

    def _update_anilist_progress_with_seasons(self) -> bool:
        """Enhanced progress update with season awareness and improved logging"""
        logger.info("🎯 Updating AniList progress with season awareness...")

        if not self.watch_history:
            logger.info("No episodes to process")
            return True

        # Group episodes by series and season to get latest progress
        series_progress = self._group_episodes_by_series_and_season_improved(self.watch_history)

        logger.info(f"Processing {len(series_progress)} unique series-season combinations...")

        for i, ((series_title, season), latest_episode) in enumerate(series_progress.items(), 1):
            try:
                # FIXED: Better logging for movies vs seasons
                season_display = "Movie" if season == 0 else f"Season {season}"
                logger.info(f"[{i}/{len(series_progress)}] Processing: {series_title} ({season_display}) - Episode {latest_episode}")

                if self._update_series_season_progress(series_title, season, latest_episode):
                    self.sync_results['successful_updates'] += 1
                else:
                    self.sync_results['failed_updates'] += 1

                # Rate limiting
                time.sleep(1.5)

            except Exception as e:
                logger.error(f"Error processing {series_title} Season {season}: {e}")
                self.sync_results['failed_updates'] += 1
                continue

        return True

    def _group_episodes_by_series_and_season_improved(self, episodes: List[Dict]) -> Dict[tuple, int]:
        """Group episodes by series and season with improved validation and debugging"""
        series_season_progress = {}
        processed_count = 0
        skipped_count = 0
        conversion_count = 0

        logger.info("🗂️ Grouping episodes by series and season...")

        # Track what we're seeing
        series_episode_counts = {}  # Track episodes per series for debugging

        for episode in episodes:
            series_title = episode.get('series_title', '').strip()
            episode_number = episode.get('episode_number', 0)
            season = episode.get('season', 1)
            raw_episode_data = episode.get('raw_text', '')[:100]  # For debugging

            if not series_title:
                logger.debug(f"Skipping episode - no series title: {episode}")
                skipped_count += 1
                continue

            if not episode_number or episode_number <= 0:
                logger.warning(
                    f"Skipping episode - no/invalid episode number: {series_title} S{season} - Raw: {raw_episode_data}")
                skipped_count += 1
                continue

            processed_count += 1

            # Track episodes per series for debugging
            season_display = "Movie" if season == 0 else f"S{season}"
            series_key = f"{series_title} {season_display}"
            if series_key not in series_episode_counts:
                series_episode_counts[series_key] = []
            series_episode_counts[series_key].append(episode_number)

            # Create key for series-season combination
            key = (series_title, season)

            # Keep track of the highest episode number for each series-season
            if key not in series_season_progress:
                series_season_progress[key] = episode_number
                season_display = "Movie" if season == 0 else f"S{season}"
                logger.debug(f"New series-season: {series_title} {season_display} E{episode_number}")
            else:
                old_episode = series_season_progress[key]
                if episode_number > old_episode:
                    series_season_progress[key] = episode_number
                    season_display = "Movie" if season == 0 else f"S{season}"
                    logger.debug(f"Updated progress: {series_title} {season_display} E{old_episode} → E{episode_number}")

        self.sync_results['total_episodes'] = len(episodes)
        self.sync_results['skipped_episodes'] = skipped_count

        logger.info(f"✅ Processed {processed_count} episodes, skipped {skipped_count}, converted {conversion_count}")

        return series_season_progress

    def _update_series_season_progress(self, series_title: str, season: int, episode_number: int) -> bool:
        """Enhanced method with special movie/special handling"""
        try:
            # FIXED: Handle movies (season 0) differently
            if season == 0:
                return self._update_movie_progress(series_title, episode_number)
            else:
                return self._update_regular_season_progress(series_title, season, episode_number)

        except Exception as e:
            logger.error(f"❌ Error updating {series_title} Season {season}: {e}", exc_info=True)
            return False

    def _update_movie_progress(self, series_title: str, episode_number: int) -> bool:
        """Handle movie/special updates with improved search and matching"""
        try:
            logger.info(f"🎬 Processing movie/special: {series_title}")

            # FIXED: Search for movies with better titles
            movie_search_queries = [
                f"{series_title} 0",  # e.g., "JUJUTSU KAISEN 0"
                f"{series_title} Movie",  # e.g., "JUJUTSU KAISEN Movie"
                f"{series_title}",  # Fallback to base title
            ]

            best_match_result = None
            best_similarity = 0.0

            # Try different search queries for movies
            for search_query in movie_search_queries:
                logger.info(f"🔍 Searching AniList for movie: {search_query}")

                search_results = self.anilist_client.search_anime(search_query)
                if not search_results:
                    continue

                logger.info(f"📚 Found {len(search_results)} results for '{search_query}'")

                # FIXED: Use movie-specific matching with higher threshold
                for result in search_results:
                    # Check if this is actually a movie/special
                    format_type = (result.get('format', '') or '').upper()
                    if format_type in ['MOVIE', 'SPECIAL', 'OVA', 'ONA']:
                        # Calculate similarity for movies
                        similarity = self._calculate_movie_similarity(series_title, result)

                        if similarity > best_similarity and similarity >= 0.8:  # Higher threshold for movies
                            best_match_result = (result, similarity, search_query)
                            best_similarity = similarity

                # If we found a good movie match, stop searching
                if best_match_result and best_similarity >= 0.9:
                    break

            if not best_match_result:
                logger.warning(f"🎬 No suitable movie match found for: {series_title}")
                logger.info(f"💡 This might be a compilation or special not available on AniList")
                self.sync_results['movies_skipped'] += 1
                return False  # Don't count as failure, just skip

            best_match, similarity, used_query = best_match_result
            anime_id = best_match['id']
            anime_title = best_match.get('title', {}).get('romaji', series_title)
            format_type = best_match.get('format', 'Unknown')

            logger.info(f"🎬 Found movie match: '{anime_title}' ({format_type}) - similarity: {similarity:.2f}")

            # Dry run check
            if self.config.get('dry_run'):
                logger.info(f"[DRY RUN] Would update movie {anime_title} to episode {episode_number}")
                return True

            # Update progress for movie
            logger.info(f"🔄 Updating AniList progress for movie: {anime_title}")
            success = self.anilist_client.update_anime_progress(
                anime_id=anime_id,
                progress=episode_number,
                status='COMPLETED'  # Movies are usually completed when watched
            )

            if success:
                logger.info(f"✅ Successfully updated movie {anime_title} to episode {episode_number}")
                return True
            else:
                logger.error(f"❌ Failed to update movie {anime_title} on AniList")
                return False

        except Exception as e:
            logger.error(f"❌ Error updating movie {series_title}: {e}", exc_info=True)
            return False

    def _calculate_movie_similarity(self, target_title: str, candidate: Dict[str, Any]) -> float:
        """Calculate similarity specifically for movies"""
        try:
            target_normalized = self._normalize_title(target_title)

            # Get all possible titles from the candidate
            titles_to_check = []

            title_obj = candidate.get('title', {})
            if isinstance(title_obj, dict):
                for key in ['romaji', 'english', 'native']:
                    title = title_obj.get(key)
                    if title:
                        titles_to_check.append(title)

            # Add synonyms
            synonyms = candidate.get('synonyms', [])
            if synonyms:
                titles_to_check.extend(synonyms)

            max_similarity = 0.0
            for title in titles_to_check:
                if title:
                    candidate_normalized = self._normalize_title(title)
                    similarity = self._calculate_similarity(target_normalized, candidate_normalized)
                    max_similarity = max(max_similarity, similarity)

            return max_similarity

        except Exception as e:
            logger.debug(f"Error calculating movie similarity: {e}")
            return 0.0

    def _normalize_title(self, title: str) -> str:
        """Normalize title for better matching"""
        if not title:
            return ""

        import re
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

        from difflib import SequenceMatcher

        # Exact match
        if title1 == title2:
            return 1.0

        # Substring matches
        if title1 in title2 or title2 in title1:
            shorter, longer = (title1, title2) if len(title1) < len(title2) else (title2, title1)
            return max(0.9, len(shorter) / len(longer))

        # Sequence matcher for fuzzy matching
        return SequenceMatcher(None, title1, title2).ratio()

    def _update_regular_season_progress(self, series_title: str, season: int, episode_number: int) -> bool:
        """Handle regular season updates (existing logic)"""
        try:
            logger.info(f"🔍 Searching AniList for: {series_title} (Season {season})")

            # Search for anime on AniList FIRST
            search_results = self.anilist_client.search_anime(series_title)
            if not search_results:
                logger.warning(f"❌ No AniList results found for: {series_title}")
                self.sync_results['no_matches_found'] += 1
                return False

            logger.info(f"📚 Found {len(search_results)} AniList results for matching")

            # Enhanced matching with season awareness
            match_result = self.anime_matcher.find_best_match_with_season(
                series_title, search_results, season
            )

            if not match_result:
                logger.warning(f"❌ No suitable match found for: {series_title} (Season {season})")
                self.sync_results['no_matches_found'] += 1
                return False

            best_match, similarity, matched_season = match_result
            anime_id = best_match['id']
            anime_title = best_match.get('title', {}).get('romaji', series_title)
            total_episodes = best_match.get('episodes')

            # CRITICAL: Validate episode number with AniList data
            validated_episode, was_adjusted, adjustment_reason = self._validate_episode_with_anilist(
                episode_number, total_episodes, series_title, matched_season
            )

            if was_adjusted:
                logger.info(
                    f"📊 Episode validation: {series_title} S{matched_season} E{episode_number} → E{validated_episode}")
                logger.info(f"   Reason: {adjustment_reason}")
                episode_number = validated_episode

            # Check if season matches
            if matched_season == season:
                self.sync_results['season_matches'] += 1
                logger.info(f"✅ Perfect season match: {anime_title} Season {matched_season} (similarity: {similarity:.2f})")
            else:
                self.sync_results['season_mismatches'] += 1
                logger.warning(f"⚠️ Season mismatch: Expected S{season}, matched S{matched_season} for {anime_title}")

            # Determine status based on episode count
            status = None
            if total_episodes and episode_number >= total_episodes:
                status = 'COMPLETED'
                logger.info(f"🏁 Will mark as completed ({episode_number}/{total_episodes})")
            else:
                logger.info(f"📈 Will update progress to {episode_number}/{total_episodes or '?'}")

            # Dry run check
            if self.config.get('dry_run'):
                logger.info(f"[DRY RUN] Would update {anime_title} Season {matched_season} to episode {episode_number}")
                if status:
                    logger.info(f"[DRY RUN] Would mark as {status}")
                return True

            # Update progress
            logger.info(f"🔄 Updating AniList progress for: {anime_title}")
            success = self.anilist_client.update_anime_progress(
                anime_id=anime_id,
                progress=episode_number,
                status=status
            )

            if success:
                logger.info(f"✅ Successfully updated {anime_title} Season {matched_season} to episode {episode_number}")

                # Cache successful mapping
                self.cache_manager.save_anime_mapping(series_title, {
                    'anilist_id': anime_id,
                    'anilist_title': anime_title,
                    'season': matched_season,
                    'similarity': similarity
                })

                return True
            else:
                logger.error(f"❌ Failed to update {anime_title} on AniList")
                return False

        except Exception as e:
            logger.error(f"❌ Error updating {series_title} Season {season}: {e}", exc_info=True)
            return False

    def _report_enhanced_results(self) -> None:
        """Report enhanced sync results with movie information"""
        results = self.sync_results

        logger.info("=" * 60)
        logger.info("📊 Enhanced Sync Results:")
        logger.info("=" * 60)
        logger.info(f"  📺 Total episodes found: {results['total_episodes']}")
        logger.info(f"  ✅ Successful updates: {results['successful_updates']}")
        logger.info(f"  ❌ Failed updates: {results['failed_updates']}")
        logger.info(f"  ⏭️ Skipped episodes: {results['skipped_episodes']}")
        logger.info(f"  🎯 Season matches: {results['season_matches']}")
        logger.info(f"  ⚠️ Season mismatches: {results['season_mismatches']}")
        logger.info(f"  🔍 No matches found: {results['no_matches_found']}")
        logger.info(f"  🎬 Movies/specials skipped: {results['movies_skipped']}")  # NEW

        if results['successful_updates'] > 0:
            total_attempts = results['successful_updates'] + results['failed_updates']
            success_rate = (results['successful_updates'] / total_attempts) * 100
            logger.info(f"  📈 Success rate: {success_rate:.1f}%")

        if results['season_matches'] > 0 or results['season_mismatches'] > 0:
            total_season_attempts = results['season_matches'] + results['season_mismatches']
            season_accuracy = (results['season_matches'] / total_season_attempts) * 100
            logger.info(f"  🎭 Season accuracy: {season_accuracy:.1f}%")

        logger.info("=" * 60)

        # Provide actionable feedback
        if results['skipped_episodes'] > 0:
            logger.info("💡 Tip: Skipped episodes may be movies, specials, or episodes without clear numbering")

        if results['season_mismatches'] > 0:
            logger.info("💡 Tip: Season mismatches may occur when anime titles don't clearly indicate seasons")

        if results['no_matches_found'] > 0:
            logger.info("💡 Tip: No matches may indicate very new anime or title differences between services")

        if results['movies_skipped'] > 0:  # NEW
            logger.info("💡 Tip: Movies/specials were skipped - they may be compilations not listed on AniList")

    def _validate_episode_with_anilist(self, episode_number: int, total_episodes: Optional[int],
                                       series_title: str, season: int) -> Tuple[int, bool, str]:
        """Validate episode number against AniList data"""

        if not total_episodes:
            return episode_number, False, "No episode count available from AniList"

        # If episode number is within expected range, it's probably correct
        if episode_number <= total_episodes:
            return episode_number, False, f"Episode {episode_number} is within expected range (≤{total_episodes})"

        # Episode number is higher than expected - might need conversion
        logger.warning(
            f"Episode {episode_number} is higher than expected {total_episodes} for {series_title} S{season}")

        # Try to convert from absolute to per-season
        if season > 1:
            # Conservative estimate: assume ~12-13 episodes per previous season
            estimated_prev_episodes = (season - 1) * 12
            converted_episode = episode_number - estimated_prev_episodes

            if 1 <= converted_episode <= total_episodes:
                return converted_episode, True, f"Converted from absolute episode (estimated {estimated_prev_episodes} previous episodes)"

        # If we can't convert confidently, keep original but warn
        logger.warning(f"Keeping original episode {episode_number} - conversion not confident")
        return episode_number, False, "Kept original - conversion not confident"

    def _save_enhanced_debug_data(self, filename: str, data: Any) -> None:
        """Save enhanced debug data with better formatting"""
        try:
            import json
            cache_dir = Path('_cache')
            cache_dir.mkdir(exist_ok=True)

            filepath = cache_dir / filename

            # Enhanced JSON formatting for better readability
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False, default=str)

            # Also save a summary for easier review
            if isinstance(data, list) and data and isinstance(data[0], dict):
                summary_file = cache_dir / f"summary_{filename}"
                summary = []

                for item in data:
                    summary.append({
                        'series_title': item.get('series_title', 'Unknown'),
                        'episode_number': item.get('episode_number', 'Unknown'),
                        'season': item.get('season', 1),
                        'episode_title': item.get('episode_title', ''),
                        'source': item.get('source', 'unknown')
                    })

                with open(summary_file, 'w', encoding='utf-8') as f:
                    json.dump(summary, f, indent=2, ensure_ascii=False)

        except Exception as e:
            logger.error(f"Failed to save enhanced debug data: {e}")

    def _cleanup(self) -> None:
        """Clean up resources"""
        try:
            if hasattr(self.crunchyroll_scraper, 'cleanup'):
                self.crunchyroll_scraper.cleanup()

            logger.info("🧹 Cleanup completed")

        except Exception as e:
            logger.error(f"Error during cleanup: {e}")