"""
Sync manager orchestrating Crunchyroll to AniList synchronization.
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
    """Orchestrates synchronization between Crunchyroll and AniList with rewatch support."""

    def __init__(self, **config):
        self.config = config
        self.cache_manager = CacheManager()

        self.crunchyroll_scraper = CrunchyrollScraper(
            email=config['crunchyroll_email'],
            password=config['crunchyroll_password'],
            headless=config.get('headless', True),
            flaresolverr_url=config.get('flaresolverr_url')
        )

        # AniList client now uses static credentials internally
        self.anilist_client = AniListClient()

        self.anime_matcher = AnimeMatcher(similarity_threshold=0.75)

        self.watch_history: List[Dict[str, Any]] = []
        self.sync_results = {
            'total_episodes': 0,
            'successful_updates': 0,
            'failed_updates': 0,
            'skipped_episodes': 0,
            'season_matches': 0,
            'season_mismatches': 0,
            'no_matches_found': 0,
            'movies_completed': 0,
            'movies_skipped': 0,
            'episode_conversions': 0,
            'rewatches_detected': 0,
            'rewatches_completed': 0,
            'new_series_started': 0,
        }

        self.season_structure_cache = {}
        self.episode_data_cache = {}
        # Track processed anime IDs globally to prevent duplicate processing across pages
        self.processed_anime_entries = {}  # Key: anime_id, Value: highest_progress_processed

    def run_sync(self) -> bool:
        """Execute the complete synchronization process."""
        try:
            logger.info("🚀 Starting Crunchyroll-AniList sync with rewatch support...")

            if self.config.get('clear_cache'):
                logger.info("🧹 Clearing cache...")
                self.cache_manager.clear_all_cache()

            if not self._authenticate_services():
                return False

            if not self._scrape_crunchyroll_history():
                return False

            if not self._update_anilist_progress_with_validation():
                return False

            self._report_results()

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
        """Authenticate with both Crunchyroll and AniList."""
        logger.info("🔐 Authenticating with services...")

        if not self.crunchyroll_scraper.authenticate():
            return False

        if not self.anilist_client.authenticate():
            return False

        logger.info("✅ Authentication successful")
        return True

    def _scrape_crunchyroll_history(self) -> bool:
        """Initialize Crunchyroll watch history scraping."""
        logger.info("📚 Scraping Crunchyroll watch history with smart pagination...")

        try:
            self.watch_history = []
            return True

        except Exception as e:
            logger.error(f"Failed to initialize Crunchyroll scraping: {e}")
            return False

    def _update_anilist_progress_with_validation(self) -> bool:
        """Update AniList progress using smart pagination with aggressive early stopping."""
        logger.info("🎯 Updating AniList with smart pagination...")

        self.watch_history = []

        max_pages = self.config.get('max_pages', 10)
        page_num = 0
        total_processed = 0
        consecutive_high_skip_pages = 0

        while page_num < max_pages:
            try:
                page_num += 1
                logger.info(f"📄 Processing page {page_num}...")

                episodes = self.crunchyroll_scraper.get_watch_history_page(page_num)

                if not episodes:
                    logger.info("No more episodes to process")
                    break

                page_stats = self._process_page_episodes(episodes)
                total_processed += len(episodes)

                # Calculate ACTUAL skip ratio based on processed unique series-season combinations
                total_processed_items = (page_stats['successful_updates'] +
                                         page_stats['failed_updates'] +
                                         page_stats['skipped_episodes'])

                skip_ratio = page_stats['skipped_episodes'] / max(total_processed_items,
                                                                  1) if total_processed_items > 0 else 0

                logger.info(f"Page {page_num} stats: {page_stats['successful_updates']} updates, "
                            f"{page_stats['skipped_episodes']} skipped, "
                            f"{page_stats['failed_updates']} failed "
                            f"({skip_ratio * 100:.0f}% skip ratio)")

                # AGGRESSIVE EARLY STOP: If page 1 has high skip ratio and few updates
                if page_num == 1:
                    if skip_ratio >= 0.7 and page_stats['successful_updates'] <= 3:
                        logger.info(
                            f"✅ Stopping early - Page 1 had {page_stats['skipped_episodes']}/{total_processed_items} items skipped "
                            f"({skip_ratio * 100:.0f}%) with only {page_stats['successful_updates']} updates")
                        logger.info("   Your recent history is already synced!")
                        break

                # Consecutive high-skip page detection
                if skip_ratio >= 0.7:
                    consecutive_high_skip_pages += 1
                    logger.info(f"   High skip ratio detected ({consecutive_high_skip_pages}/2 consecutive pages)")

                    if consecutive_high_skip_pages >= 2:
                        logger.info("✅ Stopping early - 2 consecutive pages with >70% items already synced")
                        break
                else:
                    consecutive_high_skip_pages = 0

                time.sleep(0.5)

            except Exception as e:
                logger.error(f"Error processing page {page_num}: {e}")
                break

        logger.info(f"📊 Processed {total_processed} total episodes across {page_num} pages")
        return True

    def _group_episodes_by_series_and_season(self, episodes: List[Dict]) -> Dict[tuple, int]:
        """Group episodes by series and season, tracking the latest episode for each."""
        series_season_progress = {}

        for episode in episodes:
            series_title = episode.get('series_title', '').strip()
            episode_number = episode.get('episode_number', 0)
            season = episode.get('season', 1)
            is_movie = episode.get('is_movie', False)

            if not series_title:
                continue

            if is_movie:
                key = (series_title, 0)
                series_season_progress[key] = 1
                self.episode_data_cache[key] = episode
            elif episode_number > 0:
                key = (series_title, season)
                if key not in series_season_progress or episode_number > series_season_progress[key]:
                    series_season_progress[key] = episode_number

        self.sync_results['total_episodes'] = len(episodes)
        return series_season_progress

    def _process_series_entry(self, series_title: str, cr_season: int, cr_episode: int) -> bool:
        """Process a single series entry with dynamic AniList validation and rewatch support."""
        if cr_season == 0:
            episode_data = self.episode_data_cache.get((series_title, 0), {})
            return self._process_movie(series_title, episode_data)

        try:
            logger.info(f"🔍 Searching AniList for: {series_title}")

            search_with_season = f"{series_title} season {cr_season}" if cr_season > 1 else series_title
            specific_results = self._search_anime_comprehensive(search_with_season)
            all_results = self._search_anime_comprehensive(series_title)

            search_results = []
            seen_ids = set()

            if specific_results:
                for result in specific_results:
                    if result['id'] not in seen_ids:
                        search_results.append(result)
                        seen_ids.add(result['id'])

            if all_results:
                for result in all_results:
                    if result['id'] not in seen_ids:
                        search_results.append(result)
                        seen_ids.add(result['id'])

            if not search_results:
                logger.warning(f"❌ No AniList results found for: {series_title}")
                self.sync_results['no_matches_found'] += 1
                return False

            logger.info(f"📚 Found {len(search_results)} AniList entries")

            season_structure = self._build_season_structure_from_anilist(search_results, series_title)

            matched_entry, actual_season, actual_episode = self._determine_correct_entry_and_episode(
                series_title, cr_season, cr_episode, season_structure
            )

            if not matched_entry:
                logger.warning(f"❌ Could not determine correct AniList entry for {series_title}")
                self.sync_results['no_matches_found'] += 1
                return False

            anime_id = matched_entry['id']

            # Check if we've already processed this anime at a higher episode in this sync session
            if anime_id in self.processed_anime_entries:
                previous_progress = self.processed_anime_entries[anime_id]
                if actual_episode <= previous_progress:
                    logger.debug(f"✓ {series_title} S{actual_season}E{actual_episode} already processed at higher episode {previous_progress}, skipping")
                    self.sync_results['skipped_episodes'] += 1
                    return False

            if not self._needs_update(anime_id, actual_episode):
                logger.debug(f"✓ {series_title} S{actual_season}E{actual_episode} already synced, skipping")
                self.sync_results['skipped_episodes'] += 1
                return False

            anime_title = self._get_anime_title(matched_entry)
            total_episodes = matched_entry.get('episodes')

            if actual_season == cr_season and actual_episode == cr_episode:
                logger.info(f"✅ Direct match: {anime_title} S{actual_season}E{actual_episode}")
                self.sync_results['season_matches'] += 1
            else:
                logger.info(
                    f"📊 Converted: {series_title} S{cr_season}E{cr_episode} → {anime_title} S{actual_season}E{actual_episode}")
                self.sync_results['episode_conversions'] += 1
                if actual_season != cr_season:
                    self.sync_results['season_mismatches'] += 1

            if self.config.get('dry_run'):
                logger.info(f"[DRY RUN] Would update {anime_title} to episode {actual_episode}")

                existing_entry = self.anilist_client.get_anime_list_entry(anime_id)
                if existing_entry:
                    is_rewatch = self.anilist_client._is_rewatch_scenario(existing_entry, actual_episode,
                                                                          total_episodes)
                    if is_rewatch:
                        logger.info("[DRY RUN] Rewatch would be detected")
                        self.sync_results['rewatches_detected'] += 1

                        if total_episodes and actual_episode >= total_episodes:
                            current_repeat = existing_entry.get('repeat', 0)
                            logger.info(f"[DRY RUN] Would complete rewatch (new repeat count: {current_repeat + 1})")
                            self.sync_results['rewatches_completed'] += 1
                    else:
                        current_progress = existing_entry.get('progress', 0)
                        current_status = existing_entry.get('status')
                        if current_status == 'PLANNING' or current_progress == 0:
                            logger.info("[DRY RUN] Would start new series")
                            self.sync_results['new_series_started'] += 1
                        else:
                            logger.info("[DRY RUN] Would continue normal progress")
                else:
                    logger.info("[DRY RUN] Would start completely new series")
                    self.sync_results['new_series_started'] += 1

                # Track this as processed to prevent duplicate processing of older episodes
                self.processed_anime_entries[anime_id] = actual_episode
                return True

            update_result = self.anilist_client.update_anime_progress_with_rewatch_logic(
                anime_id=anime_id,
                progress=actual_episode,
                total_episodes=total_episodes
            )

            if update_result['success']:
                logger.info(f"✅ Successfully updated {anime_title} to episode {actual_episode}")

                if update_result['was_rewatch']:
                    self.sync_results['rewatches_detected'] += 1
                    if update_result['was_completion']:
                        self.sync_results['rewatches_completed'] += 1
                elif update_result['was_new_series']:
                    self.sync_results['new_series_started'] += 1

                # Track this as processed to prevent duplicate processing of older episodes
                self.processed_anime_entries[anime_id] = actual_episode
            else:
                logger.error(f"❌ Failed to update {anime_title}")

            return update_result['success']

        except Exception as e:
            logger.error(f"Error processing {series_title}: {e}")
            return False

    def _process_page_episodes(self, episodes: List[Dict]) -> Dict[str, int]:
        """Process episodes from a single page and return statistics."""
        page_stats = {
            'successful_updates': 0,
            'failed_updates': 0,
            'skipped_episodes': 0
        }

        series_progress = self._group_episodes_by_series_and_season(episodes)

        for (series_title, cr_season), latest_episode in series_progress.items():
            try:
                season_display = "Movie" if cr_season == 0 else f"Season {cr_season}"
                logger.debug(f"Processing: {series_title} ({season_display}) - Episode {latest_episode}")

                if self._process_series_entry(series_title, cr_season, latest_episode):
                    page_stats['successful_updates'] += 1
                else:
                    page_stats['skipped_episodes'] += 1

                self._intelligent_delay()

            except Exception as e:
                logger.error(f"Error processing {series_title}: {e}")
                page_stats['failed_updates'] += 1

        self.sync_results['successful_updates'] += page_stats['successful_updates']
        self.sync_results['failed_updates'] += page_stats['failed_updates']
        self.sync_results['skipped_episodes'] += page_stats['skipped_episodes']

        return page_stats

    def _search_anime_comprehensive(self, series_title: str) -> List[Dict]:
        """Search AniList for all related entries of an anime series."""
        clean_title = self._clean_title_for_search(series_title)
        results = self.anilist_client.search_anime(series_title)

        if not results:
            results = self.anilist_client.search_anime(series_title)

        if not results or len(results) < 3:
            no_space_title = series_title.replace(' ', '')
            if no_space_title != series_title:
                space_removed_results = self.anilist_client.search_anime(no_space_title)
                if space_removed_results:
                    logger.debug(f"Found results by removing spaces: {no_space_title}")

                    seen_ids = {r['id'] for r in results} if results else set()
                    for result in space_removed_results:
                        if result['id'] not in seen_ids:
                            results.insert(0, result)
                            seen_ids.add(result['id'])

        return results

    def _clean_title_for_search(self, title: str) -> str:
        """Clean title for better AniList searching."""
        import re

        clean = re.sub(r'\s*-?\s*Season\s*\d+', '', title, flags=re.IGNORECASE)
        clean = re.sub(r'\s*-?\s*S\d+', '', clean, flags=re.IGNORECASE)
        clean = re.sub(r'\s*-?\s*Part\s*\d+', '', clean, flags=re.IGNORECASE)
        clean = re.sub(r'\s*-?\s*\d+(?:st|nd|rd|th)\s*Season', '', clean, flags=re.IGNORECASE)

        return clean.strip()

    def _build_season_structure_from_anilist(self, search_results: List[Dict], series_title: str) -> Dict:
        """Build complete season structure from AniList search results."""
        season_structure = {}
        base_title = self._clean_title_for_search(series_title)
        no_space_title = series_title.replace(' ', '').lower()

        series_groups = {}

        for result in search_results:
            format_type = (result.get('format', '') or '').upper()
            if format_type in ['MOVIE', 'SPECIAL', 'OVA', 'ONA']:
                continue

            result_title = self._get_anime_title(result)
            result_base = self._extract_base_series_title(result_title)

            is_primary_match = (
                    no_space_title in result_title.lower().replace(' ', '') or
                    base_title.lower() in result_base.lower()
            )

            if result_base not in series_groups:
                series_groups[result_base] = {
                    'entries': [],
                    'is_primary': is_primary_match
                }

            series_groups[result_base]['entries'].append(result)

            if is_primary_match:
                series_groups[result_base]['is_primary'] = True

        primary_group = None
        for group_name, group_data in series_groups.items():
            if group_data['is_primary']:
                primary_group = group_data['entries']
                logger.debug(f"Found primary series group: {group_name}")
                break

        if not primary_group:
            primary_group = search_results

        tv_series = []
        for result in primary_group:
            format_type = (result.get('format', '') or '').upper()
            if format_type in ['MOVIE', 'SPECIAL', 'OVA', 'ONA']:
                continue

            result_title = self._get_anime_title(result).lower()
            is_space_removed_match = no_space_title != series_title.lower() and no_space_title in result_title.replace(
                ' ', '')

            start_date = result.get('startDate', {}) or {}
            year = start_date.get('year') if start_date.get('year') is not None else 9999
            month = start_date.get('month') if start_date.get('month') is not None else 12
            day = start_date.get('day') if start_date.get('day') is not None else 31
            release_order = year * 10000 + month * 100 + day

            tv_series.append({
                'entry': result,
                'release_order': release_order,
                'title': self._get_anime_title(result),
                'episodes': result.get('episodes', 0),
                'has_explicit_season': self._has_explicit_season_number(result),
                'is_space_removed_match': is_space_removed_match
            })

        tv_series.sort(key=lambda x: x['release_order'])

        season_num = 1
        for series_data in tv_series:
            result = series_data['entry']

            detected_season = self._detect_season_from_anilist_entry(result, base_title)

            if series_data['has_explicit_season'] and detected_season > 1:
                actual_season = detected_season
            else:
                actual_season = season_num
                season_num += 1

            similarity = self.anime_matcher._calculate_title_similarity(series_title, result)

            if series_data['is_space_removed_match']:
                similarity += 0.3

            if actual_season not in season_structure:
                season_structure[actual_season] = {
                    'entry': result,
                    'episodes': series_data['episodes'],
                    'title': series_data['title'],
                    'similarity': similarity,
                    'id': result['id'],
                    'release_order': series_data['release_order']
                }

                logger.debug(f"  Season {actual_season}: {series_data['title']} ({series_data['episodes']} episodes)")

        return season_structure

    def _has_explicit_season_number(self, entry: Dict) -> bool:
        """Check if entry has explicit season number in title."""
        import re

        title_obj = entry.get('title', {})
        romaji = title_obj.get('romaji', '')
        english = title_obj.get('english', '')

        patterns = [
            r'(\d+)(?:st|nd|rd|th)\s+Season',
            r'Season\s+(\d+)',
            r'\bPart\s+(\d+)',
            r'\b(?:II|III|IV|V|VI)\b'
        ]

        for title in [romaji, english]:
            if title:
                for pattern in patterns:
                    if re.search(pattern, title, re.IGNORECASE):
                        return True

        return False

    def _detect_season_from_anilist_entry(self, entry: Dict, base_title: str) -> int:
        """Detect which season number this AniList entry represents."""
        import re

        title_obj = entry.get('title', {})
        romaji = title_obj.get('romaji', '')
        english = title_obj.get('english', '')

        for title in [romaji, english]:
            if not title:
                continue

            patterns = [
                (r'(\d+)(?:st|nd|rd|th)\s+Season', 1),
                (r'Season\s+(\d+)', 1),
                (r'\bPart\s+(\d+)', 1),
                (r'\b(?:II|III|IV|V|VI)\b', 0),
            ]

            for pattern, group in patterns:
                match = re.search(pattern, title, re.IGNORECASE)
                if match:
                    if group == 0:
                        roman_map = {'II': 2, 'III': 3, 'IV': 4, 'V': 5, 'VI': 6}
                        return roman_map.get(match.group(0), 1)
                    else:
                        return int(match.group(group))

        base_clean = base_title.lower().strip()
        title_clean = romaji.lower().strip()

        if base_clean in title_clean and title_clean == base_clean:
            return 1

        return 1

    def _determine_correct_entry_and_episode(self, series_title: str, cr_season: int,
                                             cr_episode: int, season_structure: Dict) -> Tuple[
        Optional[Dict], int, int]:
        """Determine the correct AniList entry and episode number."""
        if cr_season > 1 and season_structure:
            base_title_normalized = series_title.lower().replace(' ', '')

            best_entry = None
            best_similarity = 0
            best_season_num = cr_season

            for season_num, season_data in season_structure.items():
                entry_title = season_data['title'].lower().replace(' ', '')

                if base_title_normalized in entry_title or entry_title in base_title_normalized:
                    similarity = season_data.get('similarity', 0)
                    max_episodes = season_data['episodes'] or 999

                    if season_num == 1 and cr_episode > max_episodes:
                        continue

                    if similarity > best_similarity:
                        best_similarity = similarity
                        best_entry = season_data['entry']
                        best_season_num = season_num

                        if cr_episode <= max_episodes:
                            logger.info(
                                f"✅ Found matching series: {season_data['title']} - using as season {season_num}")
                            return best_entry, season_num, cr_episode

            # Always try cumulative episode conversion when cr_season > 1
            # This handles absolute episode numbers (e.g., episode 45 -> Season 2 Episode 21)
            if best_entry:
                cumulative_episodes = 0
                sorted_seasons = sorted(season_structure.keys())

                for season_num in sorted_seasons:
                    season_data = season_structure[season_num]
                    season_episodes = season_data['episodes'] or 0

                    if cr_episode <= cumulative_episodes + season_episodes:
                        episode_in_season = cr_episode - cumulative_episodes

                        if episode_in_season > 0:
                            logger.info(
                                f"📊 Episode {cr_episode} maps to Season {season_num} Episode {episode_in_season}")
                            logger.info(
                                f"   (Cumulative: {cumulative_episodes}, Season has {season_episodes} episodes)")
                            return season_data['entry'], season_num, episode_in_season

                    cumulative_episodes += season_episodes

        if cr_season in season_structure:
            season_data = season_structure[cr_season]
            max_episodes = season_data['episodes'] or cr_episode
            capped_episode = min(cr_episode, max_episodes)
            logger.warning(f"⚠️ Could not map episode {cr_episode}, using S{cr_season}E{capped_episode}")
            return season_data['entry'], cr_season, capped_episode

        if 1 in season_structure:
            season_data = season_structure[1]
            logger.warning(f"⚠️ Falling back to Season 1 for {series_title}")
            return season_data['entry'], 1, cr_episode

        return None, 0, 0

    def _extract_base_series_title(self, title: str) -> str:
        """Extract the base series name without season/part indicators."""
        import re

        base = title
        patterns = [
            r'\s*[-:]\s*.*(?:Season|Part)\s*\d+.*$',
            r'\s+(?:Season|Part)\s*\d+.*$',
            r'\s+\d+(?:st|nd|rd|th)\s+Season.*$',
            r'\s+(?:II|III|IV|V|VI)(?:\s|$).*$',
            r'\s*[-:]\s*.*(?:Cour|Arc)\s*\d+.*$',
        ]

        for pattern in patterns:
            base = re.sub(pattern, '', base, flags=re.IGNORECASE)

        if ':' in base:
            parts = base.split(':', 1)
            if len(parts) > 1 and re.search(r'(?:Season|Part)\s*\d+', parts[1], re.IGNORECASE):
                base = parts[0]

        return base.strip()

    def _process_movie(self, series_title: str, episode_data: Dict = None) -> bool:
        """Process movie entries with skip detection."""
        try:
            logger.info(f"🎬 Processing movie: {series_title}")

            if episode_data:
                episode_title = episode_data.get('episode_title', '').strip()
                season_title = episode_data.get('season_title', '').strip()

                skip_indicators = ['compilation', 'recap', 'summary', 'highlight', 'digest']
                combined_title = f"{episode_title} {season_title}".lower()

                for indicator in skip_indicators:
                    if indicator in combined_title:
                        logger.info(f"⏭️ Skipping compilation/recap content: {series_title} - {season_title}")
                        self.sync_results['movies_skipped'] += 1
                        return False

            search_queries = [
                series_title,
                f"{series_title} movie",
                self._clean_title_for_search(series_title),
            ]

            best_match = None
            best_similarity = 0

            for query in search_queries:
                results = self.anilist_client.search_anime(query)
                if results:
                    for result in results:
                        format_type = (result.get('format', '') or '').upper()
                        if format_type not in ['MOVIE', 'SPECIAL']:
                            continue

                        similarity = self.anime_matcher._calculate_title_similarity(series_title, result)

                        if similarity > best_similarity:
                            best_similarity = similarity
                            best_match = result

            if not best_match:
                logger.warning(f"🎬 No movie match found for: {series_title}")
                if episode_data:
                    logger.debug(f"   Episode title: {episode_data.get('episode_title')}")
                    logger.debug(f"   Season title: {episode_data.get('season_title')}")
                self.sync_results['movies_skipped'] += 1
                return False

            anime_title = self._get_anime_title(best_match)
            anime_id = best_match['id']

            logger.info(f"🎬 Found movie: {anime_title} (similarity: {best_similarity:.2f})")

            # Check if we've already processed this movie in this sync session
            if anime_id in self.processed_anime_entries:
                logger.debug(f"✓ Movie {anime_title} already processed in this session, skipping")
                self.sync_results['movies_skipped'] += 1
                return False

            if not self._needs_update(anime_id, 1):
                logger.info(f"✅ Movie {anime_title} already completed, skipping")
                self.sync_results['movies_skipped'] += 1
                return False

            if self.config.get('dry_run'):
                logger.info(f"[DRY RUN] Would mark movie {anime_title} as COMPLETED")

                existing_entry = self.anilist_client.get_anime_list_entry(anime_id)
                if existing_entry:
                    is_rewatch = self.anilist_client._is_rewatch_scenario(existing_entry, 1, 1)
                    if is_rewatch:
                        current_repeat = existing_entry.get('repeat', 0)
                        logger.info(
                            f"[DRY RUN] Movie rewatch would be detected (new repeat count: {current_repeat + 1})")
                        self.sync_results['rewatches_detected'] += 1
                        self.sync_results['rewatches_completed'] += 1
                    else:
                        current_status = existing_entry.get('status')
                        if current_status in ['PLANNING', None] or existing_entry.get('progress', 0) == 0:
                            logger.info("[DRY RUN] Would mark new movie as completed")
                        else:
                            logger.info("[DRY RUN] Would update existing movie entry")
                else:
                    logger.info("[DRY RUN] Would add new movie as completed")

                # Track this movie as processed
                self.processed_anime_entries[anime_id] = 1
                return True

            update_result = self.anilist_client.update_anime_progress_with_rewatch_logic(
                anime_id=anime_id,
                progress=1,
                total_episodes=1
            )

            if update_result['success']:
                logger.info(f"✅ Updated movie {anime_title}")
                self.sync_results['movies_completed'] += 1

                if update_result['was_rewatch']:
                    self.sync_results['rewatches_detected'] += 1
                    if update_result['was_completion']:
                        self.sync_results['rewatches_completed'] += 1

                # Track this movie as processed
                self.processed_anime_entries[anime_id] = 1
            else:
                logger.error(f"❌ Failed to update movie {anime_title}")

            return update_result['success']

        except Exception as e:
            logger.error(f"Error processing movie {series_title}: {e}")

    def _get_anime_title(self, anime_data: Dict) -> str:
        """Get the primary title from anime data."""
        title_obj = anime_data.get('title', {})
        if isinstance(title_obj, dict):
            return title_obj.get('romaji', title_obj.get('english', 'Unknown'))
        return str(title_obj) if title_obj else 'Unknown'

    def _report_results(self) -> None:
        """Report sync results with rewatch statistics."""
        results = self.sync_results

        logger.info("=" * 60)
        logger.info("📊 Sync Results:")
        logger.info("=" * 60)
        logger.info(f"  📺 Total episodes found: {results['total_episodes']}")
        logger.info(f"  ✅ Successful updates: {results['successful_updates']}")
        logger.info(f"  ❌ Failed updates: {results['failed_updates']}")
        logger.info(f"  ⏭️ Skipped episodes: {results['skipped_episodes']}")
        logger.info(f"  🎯 Direct matches: {results['season_matches']}")
        logger.info(f"  📊 Episode conversions: {results['episode_conversions']}")
        logger.info(f"  ⚠️ Season corrections: {results['season_mismatches']}")
        logger.info(f"  🔍 No matches found: {results['no_matches_found']}")
        logger.info(f"  🎬 Movies completed: {results['movies_completed']}")
        logger.info(f"  🎬 Movies skipped: {results['movies_skipped']}")

        logger.info("  " + "─" * 30)
        logger.info(f"  🔄 Rewatches detected: {results['rewatches_detected']}")
        logger.info(f"  🏁 Rewatches completed: {results['rewatches_completed']}")
        logger.info(f"  🆕 New series started: {results['new_series_started']}")

        if hasattr(self.anilist_client, 'rate_limiter'):
            rate_info = self.anilist_client.rate_limiter.get_status_info()
            logger.info(f"  ⏱️ Final {rate_info}")

        if results['successful_updates'] > 0:
            total_attempts = results['successful_updates'] + results['failed_updates']
            success_rate = (results['successful_updates'] / total_attempts) * 100
            logger.info(f"  📈 Success rate: {success_rate:.1f}%")

        logger.info("=" * 60)

        if results['episode_conversions'] > 0:
            logger.info("💡 Episode numbers were automatically converted from absolute to per-season numbering")

        if results['rewatches_detected'] > 0:
            logger.info("🔄 Rewatch detection is active - completed series are marked as 'watching' when rewatched")

        if results['rewatches_completed'] > 0:
            logger.info(
                f"🏁 {results['rewatches_completed']} rewatch(es) were completed and rewatch count was incremented")

    def _save_debug_data(self, filename: str, data: Any) -> None:
        """Save debug data for troubleshooting."""
        try:
            import json
            cache_dir = Path('_cache')
            cache_dir.mkdir(exist_ok=True)

            filepath = cache_dir / filename
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False, default=str)

        except Exception as e:
            logger.error(f"Failed to save debug data: {e}")

    def _intelligent_delay(self) -> None:
        """Smart delay between operations based on rate limiting status."""
        try:
            if hasattr(self.anilist_client, 'rate_limiter'):
                rate_limiter = self.anilist_client.rate_limiter

                if rate_limiter.remaining > 10:
                    delay = 0.5
                elif rate_limiter.remaining > 5:
                    delay = 1.0
                else:
                    delay = 2.0

                logger.debug(f"Using {delay}s delay ({rate_limiter.get_status_info()})")
                time.sleep(delay)
            else:
                time.sleep(1.0)

        except Exception as e:
            logger.debug(f"Error in intelligent delay: {e}")
            time.sleep(1.0)

    def _needs_update(self, anime_id: int, target_progress: int) -> bool:
        """Check if an anime entry needs to be updated, accounting for rewatches."""
        try:
            existing_entry = self.anilist_client.get_anime_list_entry(anime_id)

            if not existing_entry:
                return True

            current_progress = existing_entry.get('progress', 0)
            current_status = existing_entry.get('status')

            # CRITICAL FIX: If already at the exact same progress and status, skip
            # This prevents infinite rewatch detection loops
            if current_progress == target_progress:
                if current_status == 'COMPLETED':
                    # Already completed at this episode, no need to update
                    logger.debug(f"Anime {anime_id} already completed at episode {target_progress} - skipping")
                    return False
                elif current_status == 'CURRENT':
                    # Already watching at this exact episode, no need to update
                    logger.debug(f"Anime {anime_id} already at episode {target_progress} (CURRENT) - skipping")
                    return False

            # FIXED: Skip processing old episodes instead of treating them as rewatches
            # Old episodes from pagination should not overwrite newer progress
            # Only consider it a rewatch if:
            # 1. Series is COMPLETED
            # 2. Target progress is episode 1, 2, or 3 (indicating user started over)
            if current_status == 'COMPLETED' and target_progress < current_progress:
                if target_progress <= 3:
                    logger.debug(f"Anime {anime_id} rewatch detected: COMPLETED at {current_progress}, "
                                 f"now watching episode {target_progress} - needs update")
                    return True
                else:
                    # Old episode from pagination, skip it
                    logger.debug(f"Anime {anime_id} skipping old episode {target_progress} "
                                 f"(already at {current_progress}, status: {current_status})")
                    return False

            # Normal progress check: skip if already at or past this episode
            if current_progress >= target_progress:
                logger.debug(f"Anime {anime_id} already at episode {current_progress} "
                             f"(target: {target_progress}) - skipping")
                return False

            return True

        except Exception as e:
            logger.debug(f"Error checking update need: {e}")
            return True

    def _cleanup(self) -> None:
        """Clean up resources."""
        try:
            if hasattr(self.crunchyroll_scraper, 'cleanup'):
                self.crunchyroll_scraper.cleanup()
            logger.info("🧹 Cleanup completed")
        except Exception as e:
            logger.error(f"Error during cleanup: {e}")
