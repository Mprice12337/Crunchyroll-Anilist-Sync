"""
Enhanced sync manager with better season handling and improved logging
"""

import logging
import time
from typing import Dict, List, Any, Optional
from pathlib import Path

from crunchyroll_scraper import CrunchyrollScraper
from anilist_client import AniListClient
from anime_matcher import AnimeMatcher
from cache_manager import CacheManager

logger = logging.getLogger(__name__)

class SyncManager:
    """Enhanced sync manager with season support and better progress tracking"""

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
            'no_matches_found': 0
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
        """Authenticate with both Crunchyroll and AniList"""
        logger.info("🔐 Authenticating with services...")

        # Authenticate with Crunchyroll
        logger.info("Authenticating with Crunchyroll...")
        if not self.crunchyroll_scraper.authenticate():
            logger.error("Failed to authenticate with Crunchyroll")
            return False

        # Authenticate with AniList
        logger.info("Authenticating with AniList...")
        if not self.anilist_client.authenticate():
            logger.error("Failed to authenticate with AniList")
            return False

        logger.info("✅ Authentication successful")
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

            logger.info(f"✅ Found {len(self.watch_history)} episodes in watch history")

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
        """Log a sample of episodes for user verification"""
        if not self.watch_history:
            return

        logger.info("📋 Sample of detected episodes:")
        sample_size = min(5, len(self.watch_history))

        for i, episode in enumerate(self.watch_history[:sample_size]):
            series_title = episode.get('series_title', 'Unknown')
            episode_number = episode.get('episode_number', 'Unknown')
            season = episode.get('season', 1)
            source = episode.get('source', 'unknown')

            logger.info(f"  {i+1}. {series_title} - Episode {episode_number} (Season {season}) [{source}]")

        if len(self.watch_history) > sample_size:
            logger.info(f"  ... and {len(self.watch_history) - sample_size} more episodes")

    def _update_anilist_progress_with_seasons(self) -> bool:
        """Enhanced progress update with season awareness"""
        logger.info("🎯 Updating AniList progress with season awareness...")

        if not self.watch_history:
            logger.info("No episodes to process")
            return True

        # Group episodes by series and season to get latest progress
        series_progress = self._group_episodes_by_series_and_season(self.watch_history)

        logger.info(f"Processing {len(series_progress)} unique series-season combinations...")

        for i, ((series_title, season), latest_episode) in enumerate(series_progress.items(), 1):
            try:
                logger.info(f"[{i}/{len(series_progress)}] Processing: {series_title} (Season {season})")

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

    def _group_episodes_by_series_and_season(self, episodes: List[Dict]) -> Dict[tuple, int]:
        """Group episodes by series and season, finding the latest episode for each"""
        series_season_progress = {}

        for episode in episodes:
            series_title = episode.get('series_title')
            episode_number = episode.get('episode_number')
            season = episode.get('season', 1)

            if not series_title or not episode_number:
                self.sync_results['skipped_episodes'] += 1
                continue

            # Create key for series-season combination
            key = (series_title, season)

            # Keep track of the highest episode number for each series-season
            if key not in series_season_progress:
                series_season_progress[key] = episode_number
            else:
                series_season_progress[key] = max(series_season_progress[key], episode_number)

        self.sync_results['total_episodes'] = len(episodes)

        logger.info(f"Grouped into {len(series_season_progress)} series-season combinations")
        return series_season_progress

    def _update_series_season_progress(self, series_title: str, season: int, episode_number: int) -> bool:
        """Update progress for a specific series and season on AniList"""
        try:
            # Search for anime on AniList
            search_results = self.anilist_client.search_anime(series_title)
            if not search_results:
                logger.warning(f"No AniList results found for: {series_title}")
                self.sync_results['no_matches_found'] += 1
                return False

            # Enhanced matching with season awareness
            match_result = self.anime_matcher.find_best_match_with_season(
                series_title, search_results, season
            )

            if not match_result:
                logger.warning(f"No suitable match found for: {series_title} (Season {season})")
                self.sync_results['no_matches_found'] += 1
                return False

            best_match, similarity, matched_season = match_result
            anime_id = best_match['id']
            anime_title = best_match.get('title', {}).get('romaji', series_title)
            total_episodes = best_match.get('episodes')

            # Check if season matches
            if matched_season == season:
                self.sync_results['season_matches'] += 1
                logger.info(f"✅ Season match: {anime_title} Season {matched_season} (similarity: {similarity:.2f})")
            else:
                self.sync_results['season_mismatches'] += 1
                logger.warning(f"⚠️ Season mismatch: Found Season {matched_season}, expected Season {season}")

            # Determine status based on episode count
            status = None
            if total_episodes and episode_number >= total_episodes:
                status = 'COMPLETED'
                logger.info(f"🏁 Marking as completed ({episode_number}/{total_episodes})")

            # Dry run check
            if self.config.get('dry_run'):
                logger.info(f"[DRY RUN] Would update {anime_title} Season {matched_season} to episode {episode_number}")
                return True

            # Update progress
            success = self.anilist_client.update_anime_progress(
                anime_id=anime_id,
                progress=episode_number,
                status=status
            )

            if success:
                logger.info(f"✅ Updated {anime_title} Season {matched_season} to episode {episode_number}")

                # Cache successful mapping
                self.cache_manager.save_anime_mapping(series_title, {
                    'anilist_id': anime_id,
                    'anilist_title': anime_title,
                    'season': matched_season,
                    'similarity': similarity
                })

                return True
            else:
                logger.error(f"❌ Failed to update {anime_title}")
                return False

        except Exception as e:
            logger.error(f"Error updating {series_title} Season {season}: {e}")
            return False

    def _report_enhanced_results(self) -> None:
        """Report enhanced sync results with season information"""
        results = self.sync_results

        logger.info("📊 Enhanced Sync Results:")
        logger.info(f"  📺 Total episodes found: {results['total_episodes']}")
        logger.info(f"  ✅ Successful updates: {results['successful_updates']}")
        logger.info(f"  ❌ Failed updates: {results['failed_updates']}")
        logger.info(f"  ⏭️ Skipped episodes: {results['skipped_episodes']}")
        logger.info(f"  🎯 Season matches: {results['season_matches']}")
        logger.info(f"  ⚠️ Season mismatches: {results['season_mismatches']}")
        logger.info(f"  🔍 No matches found: {results['no_matches_found']}")

        if results['successful_updates'] > 0:
            total_attempts = results['successful_updates'] + results['failed_updates']
            success_rate = (results['successful_updates'] / total_attempts) * 100
            logger.info(f"  📈 Success rate: {success_rate:.1f}%")

        if results['season_matches'] > 0 or results['season_mismatches'] > 0:
            total_season_attempts = results['season_matches'] + results['season_mismatches']
            season_accuracy = (results['season_matches'] / total_season_attempts) * 100
            logger.info(f"  🎭 Season accuracy: {season_accuracy:.1f}%")

        # Provide actionable feedback
        if results['season_mismatches'] > 0:
            logger.info("💡 Tip: Season mismatches may occur when anime titles don't clearly indicate seasons")

        if results['no_matches_found'] > 0:
            logger.info("💡 Tip: No matches may indicate very new anime or title differences between services")

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

            logger.debug(f"💾 Enhanced debug data saved: {filepath}")

            # Also save a summary for easier review
            if isinstance(data, list) and data and isinstance(data[0], dict):
                summary_file = cache_dir / f"summary_{filename}"
                summary = []

                for item in data:
                    summary.append({
                        'series_title': item.get('series_title', 'Unknown'),
                        'episode_number': item.get('episode_number', 'Unknown'),
                        'season': item.get('season', 1),
                        'source': item.get('source', 'unknown')
                    })

                with open(summary_file, 'w', encoding='utf-8') as f:
                    json.dump(summary, f, indent=2, ensure_ascii=False)

                logger.debug(f"📋 Summary saved: {summary_file}")

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