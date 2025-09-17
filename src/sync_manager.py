"""
Simplified sync manager that coordinates Crunchyroll scraping and AniList updates
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
    """Manages the complete sync process between Crunchyroll and AniList"""

    def __init__(self, **config):
        self.config = config
        self.cache_manager = CacheManager()

        # Initialize components
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

        self.anime_matcher = AnimeMatcher()

        # State tracking
        self.watch_history: List[Dict[str, Any]] = []
        self.sync_results = {
            'total_episodes': 0,
            'successful_updates': 0,
            'failed_updates': 0,
            'skipped_episodes': 0
        }

    def run_sync(self) -> bool:
        """Execute the complete sync process"""
        try:
            logger.info("Starting sync process...")

            # Clear cache if requested
            if self.config.get('clear_cache'):
                logger.info("Clearing cache...")
                self.cache_manager.clear_all_cache()

            # Step 1: Authenticate with services
            if not self._authenticate_services():
                return False

            # Step 2: Scrape Crunchyroll history
            if not self._scrape_crunchyroll_history():
                return False

            # Step 3: Process and update AniList
            if not self._update_anilist_progress():
                return False

            # Step 4: Report results
            self._report_results()

            return True

        except Exception as e:
            logger.error(f"Sync process failed: {e}")
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
                logger.warning("No watch history found")
                return True  # Not necessarily an error

            logger.info(f"Found {len(self.watch_history)} episodes in watch history")

            # Save debug data if requested
            if self.config.get('debug'):
                self._save_debug_data('watch_history.json', self.watch_history)

            return True

        except Exception as e:
            logger.error(f"Failed to scrape Crunchyroll history: {e}")
            return False

    def _update_anilist_progress(self) -> bool:
        """Process watch history and update AniList progress"""
        logger.info("🎯 Updating AniList progress...")

        if not self.watch_history:
            logger.info("No episodes to process")
            return True

        # Group episodes by series to get latest progress
        series_progress = self._group_episodes_by_series(self.watch_history)

        logger.info(f"Processing {len(series_progress)} unique series...")

        for i, (series_title, latest_episode) in enumerate(series_progress.items(), 1):
            try:
                logger.info(f"[{i}/{len(series_progress)}] Processing: {series_title}")

                if self._update_series_progress(series_title, latest_episode):
                    self.sync_results['successful_updates'] += 1
                else:
                    self.sync_results['failed_updates'] += 1

                # Rate limiting
                time.sleep(1)

            except Exception as e:
                logger.error(f"Error processing {series_title}: {e}")
                self.sync_results['failed_updates'] += 1
                continue

        return True

    def _group_episodes_by_series(self, episodes: List[Dict]) -> Dict[str, int]:
        """Group episodes by series and find the latest episode for each"""
        series_progress = {}

        for episode in episodes:
            series_title = episode.get('series_title')
            episode_number = episode.get('episode_number')

            if not series_title or not episode_number:
                self.sync_results['skipped_episodes'] += 1
                continue

            # Keep track of the highest episode number for each series
            if series_title not in series_progress:
                series_progress[series_title] = episode_number
            else:
                series_progress[series_title] = max(series_progress[series_title], episode_number)

        self.sync_results['total_episodes'] = len(episodes)

        return series_progress

    def _update_series_progress(self, series_title: str, episode_number: int) -> bool:
        """Update progress for a specific series on AniList"""
        try:
            # Search for anime on AniList
            search_results = self.anilist_client.search_anime(series_title)
            if not search_results:
                logger.warning(f"No AniList results found for: {series_title}")
                return False

            # Find best match
            match_result = self.anime_matcher.find_best_match(series_title, search_results)
            if not match_result:
                logger.warning(f"No suitable match found for: {series_title}")
                return False

            best_match, similarity = match_result
            anime_id = best_match['id']
            anime_title = best_match.get('title', {}).get('romaji', series_title)
            total_episodes = best_match.get('episodes')

            logger.info(f"Matched to: {anime_title} (ID: {anime_id}, similarity: {similarity:.2f})")

            # Determine status
            status = None
            if total_episodes and episode_number >= total_episodes:
                status = 'COMPLETED'
                logger.info(f"Marking as completed ({episode_number}/{total_episodes})")

            # Dry run check
            if self.config.get('dry_run'):
                logger.info(f"[DRY RUN] Would update {anime_title} to episode {episode_number}")
                return True

            # Update progress
            success = self.anilist_client.update_anime_progress(
                anime_id=anime_id,
                progress=episode_number,
                status=status
            )

            if success:
                logger.info(f"✅ Updated {anime_title} to episode {episode_number}")
                return True
            else:
                logger.error(f"❌ Failed to update {anime_title}")
                return False

        except Exception as e:
            logger.error(f"Error updating {series_title}: {e}")
            return False

    def _report_results(self) -> None:
        """Report sync results"""
        results = self.sync_results

        logger.info("📊 Sync Results:")
        logger.info(f"  Total episodes found: {results['total_episodes']}")
        logger.info(f"  Successful updates: {results['successful_updates']}")
        logger.info(f"  Failed updates: {results['failed_updates']}")
        logger.info(f"  Skipped episodes: {results['skipped_episodes']}")

        if results['successful_updates'] > 0:
            success_rate = (results['successful_updates'] /
                          (results['successful_updates'] + results['failed_updates'])) * 100
            logger.info(f"  Success rate: {success_rate:.1f}%")

    def _save_debug_data(self, filename: str, data: Any) -> None:
        """Save debug data to cache directory"""
        try:
            import json
            cache_dir = Path('_cache')
            cache_dir.mkdir(exist_ok=True)

            filepath = cache_dir / filename
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)

            logger.debug(f"Debug data saved: {filepath}")

        except Exception as e:
            logger.error(f"Failed to save debug data: {e}")

    def _cleanup(self) -> None:
        """Clean up resources"""
        try:
            if hasattr(self.crunchyroll_scraper, 'cleanup'):
                self.crunchyroll_scraper.cleanup()
        except Exception as e:
            logger.error(f"Error during cleanup: {e}")