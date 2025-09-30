"""
Enhanced sync manager with fixes for movie matching and series search + rewatch support
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
    """Enhanced sync manager with dynamic AniList validation and rewatch support"""

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
            'movies_completed': 0,
            'movies_skipped': 0,
            'episode_conversions': 0,  # Track when we convert episode numbers
            'rewatches_detected': 0,   # NEW: Track rewatch detection
            'rewatches_completed': 0,  # NEW: Track completed rewatches
            'new_series_started': 0,   # NEW: Track new series
        }

        # Cache for anime season structures (temporary, per run)
        self.season_structure_cache = {}

        # Store original episode data for movie processing
        self.episode_data_cache = {}

    def run_sync(self) -> bool:
        """Execute the enhanced sync process"""
        try:
            logger.info("🚀 Starting enhanced Crunchyroll-AniList sync with rewatch support...")

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

            # Step 3: Process and update AniList with dynamic validation and rewatch support
            if not self._update_anilist_progress_with_validation():
                return False

            # Step 4: Report results
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
        """Authenticate with both services"""
        logger.info("🔐 Authenticating with services...")

        if not self.crunchyroll_scraper.authenticate():
            return False

        if not self.anilist_client.authenticate():
            return False

        logger.info("✅ Authentication successful")
        return True

    def _scrape_crunchyroll_history(self) -> bool:
        """Scrape watch history from Crunchyroll with smart pagination"""
        logger.info("📚 Scraping Crunchyroll watch history with smart pagination...")

        try:
            # Don't fetch all pages upfront - we'll fetch page by page
            # and stop when we hit entries that don't need updates
            self.watch_history = []  # Initialize empty
            return True

        except Exception as e:
            logger.error(f"Failed to initialize Crunchyroll scraping: {e}")
            return False

    def _update_anilist_progress_with_validation(self) -> bool:
        """Update AniList progress with smart pagination - fetch and process page by page"""
        logger.info("🎯 Updating AniList with smart pagination...")

        max_pages = self.config.get('max_pages', 10)
        page_num = 0
        total_processed = 0
        consecutive_no_update_pages = 0

        while page_num < max_pages:
            page_num += 1

            # Fetch one page at a time
            logger.info(f"📄 Fetching and processing page {page_num}/{max_pages}...")

            page_episodes = self.crunchyroll_scraper.get_watch_history_page(page_num)

            if not page_episodes:
                logger.info(f"No more episodes on page {page_num}, stopping")
                break

            logger.info(f"Found {len(page_episodes)} episodes on page {page_num}")

            # Process this page
            page_updates = self._process_page_episodes(page_episodes)
            total_processed += len(page_episodes)

            # Track if we made any updates on this page
            updates_made = page_updates['successful_updates'] + page_updates['failed_updates']

            logger.info(f"Page {page_num}: {updates_made} updates needed, "
                        f"{page_updates['skipped_episodes']} already up-to-date")

            # Smart stopping logic
            if updates_made == 0:
                consecutive_no_update_pages += 1
                logger.info(f"✨ No updates needed on page {page_num} "
                            f"({consecutive_no_update_pages} consecutive)")

                # If we have 2 consecutive pages with no updates, we can safely stop
                if consecutive_no_update_pages >= 2:
                    logger.info("✅ Found 2 consecutive pages with no updates - "
                                "watch history is already synced!")
                    break
            else:
                # Reset counter if we found updates
                consecutive_no_update_pages = 0

            # Small delay between pages
            time.sleep(0.5)

        logger.info(f"📊 Processed {total_processed} total episodes across {page_num} pages")
        return True

    def _group_episodes_by_series_and_season(self, episodes: List[Dict]) -> Dict[tuple, int]:
        """Group episodes by series and season"""
        series_season_progress = {}

        for episode in episodes:
            series_title = episode.get('series_title', '').strip()
            episode_number = episode.get('episode_number', 0)
            season = episode.get('season', 1)
            is_movie = episode.get('is_movie', False)

            if not series_title:
                continue

            # Movies are always season 0, episode 1
            if is_movie:
                key = (series_title, 0)
                series_season_progress[key] = 1
                # Store the full episode data for movies
                self.episode_data_cache[key] = episode
            elif episode_number > 0:
                key = (series_title, season)
                # Keep highest episode for each series-season
                if key not in series_season_progress or episode_number > series_season_progress[key]:
                    series_season_progress[key] = episode_number

        self.sync_results['total_episodes'] = len(episodes)
        return series_season_progress

    def _process_series_entry(self, series_title: str, cr_season: int, cr_episode: int) -> bool:
        """Process a single series entry with dynamic AniList validation and rewatch support"""

        # Handle movies separately
        if cr_season == 0:
            # Get the full episode data for this movie
            episode_data = self.episode_data_cache.get((series_title, 0), {})
            return self._process_movie(series_title, episode_data)

        try:
            # FIX 1: Try with season info first for better matching
            logger.info(f"🔍 Searching AniList for: {series_title}")

            # First try with season information for specific match
            search_with_season = f"{series_title} season {cr_season}" if cr_season > 1 else series_title
            specific_results = self._search_anime_comprehensive(search_with_season)

            # Also get all related entries without season
            all_results = self._search_anime_comprehensive(series_title)

            # Combine results, prioritizing specific matches
            search_results = []
            seen_ids = set()

            # Add specific results first
            if specific_results:
                for result in specific_results:
                    if result['id'] not in seen_ids:
                        search_results.append(result)
                        seen_ids.add(result['id'])

            # Add remaining results
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

            # Build complete season structure from AniList
            season_structure = self._build_season_structure_from_anilist(search_results, series_title)

            # Determine if episode needs conversion and find correct match
            matched_entry, actual_season, actual_episode = self._determine_correct_entry_and_episode(
                series_title, cr_season, cr_episode, season_structure
            )

            if not matched_entry:
                logger.warning(f"❌ Could not determine correct AniList entry for {series_title}")
                self.sync_results['no_matches_found'] += 1
                return False

            if matched_entry:  # After we've found the matched entry
                anime_id = matched_entry['id']

                if not self._needs_update(anime_id, actual_episode):
                    logger.debug(f"✓ {series_title} S{actual_season}E{actual_episode} already synced, skipping")
                    self.sync_results['skipped_episodes'] += 1
                    return False

            # Log the matching result
            anime_id = matched_entry['id']
            anime_title = self._get_anime_title(matched_entry)
            total_episodes = matched_entry.get('episodes')

            if actual_season == cr_season and actual_episode == cr_episode:
                logger.info(f"✅ Direct match: {anime_title} S{actual_season}E{actual_episode}")
                self.sync_results['season_matches'] += 1
            else:
                logger.info(f"📊 Converted: {series_title} S{cr_season}E{cr_episode} → {anime_title} S{actual_season}E{actual_episode}")
                self.sync_results['episode_conversions'] += 1
                if actual_season != cr_season:
                    self.sync_results['season_mismatches'] += 1

            # NEW: Use rewatch-aware update method
            if self.config.get('dry_run'):
                logger.info(f"[DRY RUN] Would update {anime_title} to episode {actual_episode} with rewatch detection")

                # For dry run, simulate the rewatch detection logic
                existing_entry = self.anilist_client.get_anime_list_entry(anime_id)
                if existing_entry:
                    # FIXED: Use the actual rewatch detection logic, not just check status
                    is_rewatch = self.anilist_client._is_rewatch_scenario(existing_entry, actual_episode, total_episodes)
                    if is_rewatch:
                        logger.info(f"[DRY RUN] Would be detected as rewatch")
                        self.sync_results['rewatches_detected'] += 1

                        # Check if it would be a completion
                        if total_episodes and actual_episode >= total_episodes:
                            current_repeat = existing_entry.get('repeat', 0)
                            logger.info(f"[DRY RUN] Would complete rewatch (new repeat count: {current_repeat + 1})")
                            self.sync_results['rewatches_completed'] += 1
                    else:
                        # Check if this would be a new series
                        current_progress = existing_entry.get('progress', 0)
                        current_status = existing_entry.get('status')
                        if current_status == 'PLANNING' or current_progress == 0:
                            logger.info(f"[DRY RUN] Would start new series")
                            self.sync_results['new_series_started'] += 1
                        else:
                            logger.info(f"[DRY RUN] Would continue normal progress")
                else:
                    logger.info(f"[DRY RUN] Would start completely new series")
                    self.sync_results['new_series_started'] += 1

                return True

            # Actual update with rewatch logic
            update_result = self.anilist_client.update_anime_progress_with_rewatch_logic(
                anime_id=anime_id,
                progress=actual_episode,
                total_episodes=total_episodes
            )

            if update_result['success']:
                logger.info(f"✅ Successfully updated {anime_title} to episode {actual_episode}")

                # Track statistics from the update result (no redundant API call!)
                if update_result['was_rewatch']:
                    self.sync_results['rewatches_detected'] += 1
                    if update_result['was_completion']:
                        self.sync_results['rewatches_completed'] += 1
                elif update_result['was_new_series']:
                    self.sync_results['new_series_started'] += 1
            else:
                logger.error(f"❌ Failed to update {anime_title}")

            return update_result['success']

        except Exception as e:
            logger.error(f"Error processing {series_title}: {e}")
            return False

    def _process_page_episodes(self, episodes: List[Dict]) -> Dict[str, int]:
        """Process episodes from a single page and return statistics"""
        page_stats = {
            'successful_updates': 0,
            'failed_updates': 0,
            'skipped_episodes': 0
        }

        # Group episodes by series-season
        series_progress = self._group_episodes_by_series_and_season(episodes)

        for (series_title, cr_season), latest_episode in series_progress.items():
            try:
                season_display = "Movie" if cr_season == 0 else f"Season {cr_season}"
                logger.debug(f"Processing: {series_title} ({season_display}) - Episode {latest_episode}")

                if self._process_series_entry(series_title, cr_season, latest_episode):
                    page_stats['successful_updates'] += 1
                else:
                    # Check if it was skipped or failed
                    # If the entry already exists with same/higher progress, count as skipped
                    page_stats['skipped_episodes'] += 1

                # Intelligent delay
                self._intelligent_delay()

            except Exception as e:
                logger.error(f"Error processing {series_title}: {e}")
                page_stats['failed_updates'] += 1

        # Update global stats
        self.sync_results['successful_updates'] += page_stats['successful_updates']
        self.sync_results['failed_updates'] += page_stats['failed_updates']
        self.sync_results['skipped_episodes'] += page_stats['skipped_episodes']

        return page_stats

    def _search_anime_comprehensive(self, series_title: str) -> List[Dict]:
        """Search AniList and get all related entries (all seasons)"""

        # Clean the title for better searching
        clean_title = self._clean_title_for_search(series_title)

        # Search with the clean title
        results = self.anilist_client.search_anime(series_title)

        if not results:
            # Try with original title if clean title didn't work
            results = self.anilist_client.search_anime(series_title)

        # FIX for DAN DA DAN: Try removing spaces if no results
        space_removed_results = []
        if not results or len(results) < 3:  # Also try if we have very few results
            # Try with spaces removed (e.g., "DAN DA DAN" -> "DANDADAN")
            no_space_title = series_title.replace(' ', '')
            if no_space_title != series_title:
                space_removed_results = self.anilist_client.search_anime(no_space_title)
                if space_removed_results:
                    logger.debug(f"Found results by removing spaces: {no_space_title}")

                    # If we found results with space removal, prioritize them
                    # by adding them to the beginning of the results list
                    seen_ids = {r['id'] for r in results} if results else set()
                    for result in space_removed_results:
                        if result['id'] not in seen_ids:
                            results.insert(0, result)  # Add to beginning for priority
                            seen_ids.add(result['id'])

        return results

    def _clean_title_for_search(self, title: str) -> str:
        """Clean title for better AniList searching"""
        import re

        # Remove season indicators for broader search
        clean = re.sub(r'\s*-?\s*Season\s*\d+', '', title, flags=re.IGNORECASE)
        clean = re.sub(r'\s*-?\s*S\d+', '', clean, flags=re.IGNORECASE)
        clean = re.sub(r'\s*-?\s*Part\s*\d+', '', clean, flags=re.IGNORECASE)
        clean = re.sub(r'\s*-?\s*\d+(?:st|nd|rd|th)\s*Season', '', clean, flags=re.IGNORECASE)

        return clean.strip()

    def _build_season_structure_from_anilist(self, search_results: List[Dict], series_title: str) -> Dict:
        """Build complete season structure from AniList search results"""

        season_structure = {}
        base_title = self._clean_title_for_search(series_title)

        # Special handling for titles where space removal gives better results
        no_space_title = series_title.replace(' ', '').lower()

        # Group results by base series first
        series_groups = {}

        for result in search_results:
            # Skip movies/specials for regular season structure
            format_type = (result.get('format', '') or '').upper()
            if format_type in ['MOVIE', 'SPECIAL', 'OVA', 'ONA']:
                continue

            # Try to identify which base series this belongs to
            result_title = self._get_anime_title(result)
            result_base = self._extract_base_series_title(result_title)

            # Check if this matches our search better with spaces removed
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

            # Update primary status if this group contains a primary match
            if is_primary_match:
                series_groups[result_base]['is_primary'] = True

        # Process only the primary series group if found
        primary_group = None
        for group_name, group_data in series_groups.items():
            if group_data['is_primary']:
                primary_group = group_data['entries']
                logger.debug(f"Found primary series group: {group_name}")
                break

        # If no primary group found, use all results
        if not primary_group:
            primary_group = search_results

        # First pass: collect all TV series with their metadata from primary group
        tv_series = []
        for result in primary_group:
            # Skip movies/specials for regular season structure
            format_type = (result.get('format', '') or '').upper()
            if format_type in ['MOVIE', 'SPECIAL', 'OVA', 'ONA']:
                continue

            # Check if this result matches the no-space version better
            result_title = self._get_anime_title(result).lower()
            is_space_removed_match = no_space_title != series_title.lower() and no_space_title in result_title.replace(
                ' ', '')

            # Get release date for ordering (handle None values)
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

        # Sort by release date
        tv_series.sort(key=lambda x: x['release_order'])

        # Second pass: assign season numbers
        season_num = 1
        for series_data in tv_series:
            result = series_data['entry']

            # Check if this has an explicit season number
            detected_season = self._detect_season_from_anilist_entry(result, base_title)

            # If it has explicit season number > 1, use it
            if series_data['has_explicit_season'] and detected_season > 1:
                actual_season = detected_season
            else:
                # For series without explicit season numbers, use chronological order
                actual_season = season_num
                season_num += 1

            # Calculate similarity to original search
            similarity = self.anime_matcher._calculate_title_similarity(series_title, result)

            # Boost similarity for space-removed matches
            if series_data['is_space_removed_match']:
                similarity += 0.3  # Even bigger boost

            # Store in structure (prefer first chronological entry for duplicate season numbers)
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
        """Check if entry has explicit season number in title"""
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
        """Detect which season number this AniList entry represents"""

        import re

        title_obj = entry.get('title', {})
        romaji = title_obj.get('romaji', '')
        english = title_obj.get('english', '')

        # Check both titles for season indicators
        for title in [romaji, english]:
            if not title:
                continue

            # Look for explicit season numbers
            patterns = [
                (r'(\d+)(?:st|nd|rd|th)\s+Season', 1),  # "2nd Season"
                (r'Season\s+(\d+)', 1),  # "Season 2"
                (r'\bPart\s+(\d+)', 1),  # "Part 2"
                (r'\b(?:II|III|IV|V|VI)\b', 0),  # Roman numerals (special handling)
            ]

            for pattern, group in patterns:
                match = re.search(pattern, title, re.IGNORECASE)
                if match:
                    if group == 0:  # Roman numeral
                        roman_map = {'II': 2, 'III': 3, 'IV': 4, 'V': 5, 'VI': 6}
                        return roman_map.get(match.group(0), 1)
                    else:
                        return int(match.group(group))

        # Check if this is a sequel based on subtitle differences
        # If the title has a subtitle that the base doesn't, it's likely a sequel
        base_clean = base_title.lower().strip()
        title_clean = romaji.lower().strip()

        # If title exactly matches base, it's season 1
        if base_clean in title_clean and title_clean == base_clean:
            return 1

        # If title has additional subtitle beyond base title, could be a sequel
        # But we can't determine exact season number without more info
        # Use release date to infer (handled in build_season_structure)

        # Default to season 1 if no indicators found
        return 1

    def _determine_correct_entry_and_episode(self, series_title: str, cr_season: int,
                                             cr_episode: int, season_structure: Dict) -> Tuple[
        Optional[Dict], int, int]:
        """Determine the correct AniList entry and episode number"""

        # Special handling for better base title matching
        # If we're looking for a specific season but the matches don't seem right,
        # try to find entries that actually match the base title better

        if cr_season > 1 and season_structure:
            # Check if the current season mapping makes sense
            base_title_normalized = series_title.lower().replace(' ', '')

            # Find the best matching entry based on base title similarity
            best_entry = None
            best_similarity = 0
            best_season_num = cr_season

            for season_num, season_data in season_structure.items():
                entry_title = season_data['title'].lower().replace(' ', '')

                # Calculate how well this entry matches our base title
                # For "DAN DA DAN" we want "Dandadan" not "Da Capo"
                if base_title_normalized in entry_title or entry_title in base_title_normalized:
                    # This is likely the correct series
                    similarity = season_data.get('similarity', 0)

                    # Check if this entry can handle our episode number
                    max_episodes = season_data['episodes'] or 999

                    # If this is season 1 and our episode exceeds it, it might be absolute numbering
                    if season_num == 1 and cr_episode > max_episodes:
                        # This might be the right series but wrong season
                        # Keep searching for the right season
                        continue

                    if similarity > best_similarity:
                        best_similarity = similarity
                        best_entry = season_data['entry']
                        best_season_num = season_num

                        # If episode fits within this season, use it
                        if cr_episode <= max_episodes:
                            logger.info(
                                f"✅ Found matching series: {season_data['title']} - using as season {season_num}")
                            return best_entry, season_num, cr_episode

            # If we found a matching series but episode doesn't fit any season,
            # it might be using absolute numbering
            if best_entry and best_season_num == 1:
                # Try to map absolute episode to correct season
                cumulative_episodes = 0
                sorted_seasons = sorted(season_structure.keys())

                for season_num in sorted_seasons:
                    season_data = season_structure[season_num]

                    # Only consider seasons from the same series
                    entry_title = season_data['title'].lower().replace(' ', '')
                    if not (base_title_normalized in entry_title or entry_title in base_title_normalized):
                        continue

                    season_episodes = season_data['episodes'] or 0

                    # Check if episode falls within this season's range
                    if cr_episode <= cumulative_episodes + season_episodes:
                        episode_in_season = cr_episode - cumulative_episodes
                        if episode_in_season > 0:
                            logger.info(
                                f"📊 Mapped absolute episode {cr_episode} to Season {season_num} Episode {episode_in_season}")
                            return season_data['entry'], season_num, episode_in_season

                    cumulative_episodes += season_episodes

        # Original logic as fallback
        # First, check if the Crunchyroll season/episode makes sense as-is
        if cr_season in season_structure:
            season_data = season_structure[cr_season]
            max_episodes = season_data['episodes']

            # If episode number is valid for this season, use it directly
            if max_episodes and cr_episode <= max_episodes:
                logger.info(f"✅ Episode {cr_episode} is valid for season {cr_season} (max: {max_episodes})")
                return season_data['entry'], cr_season, cr_episode
            else:
                logger.info(
                    f"⚠️ Episode {cr_episode} exceeds season {cr_season} max ({max_episodes}), checking if absolute numbering...")

        # Episode might be using absolute numbering, need to find correct season
        cumulative_episodes = 0
        sorted_seasons = sorted(season_structure.keys())

        for season_num in sorted_seasons:
            season_data = season_structure[season_num]
            season_episodes = season_data['episodes'] or 0

            # Check if episode falls within this season's range
            if cr_episode <= cumulative_episodes + season_episodes:
                # Calculate episode within this season
                episode_in_season = cr_episode - cumulative_episodes

                if episode_in_season > 0:
                    logger.info(f"📊 Episode {cr_episode} maps to Season {season_num} Episode {episode_in_season}")
                    logger.info(f"   (Cumulative: {cumulative_episodes}, Season has {season_episodes} episodes)")
                    return season_data['entry'], season_num, episode_in_season

            cumulative_episodes += season_episodes

        # If we couldn't map it, try to use the best match based on similarity
        if cr_season in season_structure:
            # Use the stated season but cap at max episodes if needed
            season_data = season_structure[cr_season]
            max_episodes = season_data['episodes'] or cr_episode
            capped_episode = min(cr_episode, max_episodes)
            logger.warning(f"⚠️ Could not map episode {cr_episode}, using S{cr_season}E{capped_episode}")
            return season_data['entry'], cr_season, capped_episode

        # Fall back to season 1 if nothing else works
        if 1 in season_structure:
            season_data = season_structure[1]
            logger.warning(f"⚠️ Falling back to Season 1 for {series_title}")
            return season_data['entry'], 1, cr_episode

        return None, 0, 0

    def _extract_base_series_title(self, title: str) -> str:
        """Extract the base series name without season/part indicators"""
        import re

        # Remove common season/part indicators
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

        # Also try to extract base from subtitle patterns
        # e.g., "Title: Subtitle" -> "Title"
        if ':' in base:
            parts = base.split(':', 1)
            # Check if the part after colon contains season indicators
            if len(parts) > 1 and re.search(r'(?:Season|Part)\s*\d+', parts[1], re.IGNORECASE):
                base = parts[0]

        return base.strip()

    def _process_movie(self, series_title: str, episode_data: Dict = None) -> bool:
        """Process movie entries with skip detection"""
        try:
            logger.info(f"🎬 Processing movie: {series_title}")

            # FIX: Skip compilation/recap content entirely
            if episode_data:
                episode_title = episode_data.get('episode_title', '').strip()
                season_title = episode_data.get('season_title', '').strip()

                # Check if this is compilation/recap content that should be skipped
                skip_indicators = ['compilation', 'recap', 'summary', 'highlight', 'digest']
                combined_title = f"{episode_title} {season_title}".lower()

                for indicator in skip_indicators:
                    if indicator in combined_title:
                        logger.info(f"⏭️ Skipping compilation/recap content: {series_title} - {season_title}")
                        self.sync_results['movies_skipped'] += 1
                        return False

            # ... existing search logic ...
            # (keep all the search_queries logic as-is)

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

            # NEW: Check if already complete BEFORE attempting update
            if not self._needs_update(anime_id, 1):  # Movies are always "episode 1"
                logger.info(f"✅ Movie {anime_title} already completed, skipping")
                self.sync_results['movies_skipped'] += 1
                return False  # False = skipped (not failed)

            if self.config.get('dry_run'):
                logger.info(f"[DRY RUN] Would mark movie {anime_title} as COMPLETED with rewatch detection")

                # For dry run, simulate the rewatch detection for movies
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
                            logger.info(f"[DRY RUN] Would mark new movie as completed")
                        else:
                            logger.info(f"[DRY RUN] Would update existing movie entry")
                else:
                    logger.info(f"[DRY RUN] Would add new movie as completed")

                return True

            # Use rewatch-aware update for movies - NOW with statistics return
            update_result = self.anilist_client.update_anime_progress_with_rewatch_logic(
                anime_id=anime_id,
                progress=1,
                total_episodes=1  # Movies have 1 "episode"
            )

            if update_result['success']:
                logger.info(f"✅ Updated movie {anime_title}")
                self.sync_results['movies_completed'] += 1

                # Track rewatch statistics from returned data (no redundant API call!)
                if update_result['was_rewatch']:
                    self.sync_results['rewatches_detected'] += 1
                    if update_result['was_completion']:
                        self.sync_results['rewatches_completed'] += 1
            else:
                logger.error(f"❌ Failed to update movie {anime_title}")

            return update_result['success']

        except Exception as e:
            logger.error(f"Error processing movie {series_title}: {e}")

    def _get_anime_title(self, anime_data: Dict) -> str:
        """Get the primary title from anime data"""
        title_obj = anime_data.get('title', {})
        if isinstance(title_obj, dict):
            return title_obj.get('romaji', title_obj.get('english', 'Unknown'))
        return str(title_obj) if title_obj else 'Unknown'

    def _report_enhanced_results(self) -> None:
        """Report sync results with rewatch statistics"""
        results = self.sync_results

        logger.info("=" * 60)
        logger.info("📊 Enhanced Sync Results with Rewatch Support:")
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

        # NEW: Rewatch statistics
        logger.info("  " + "─" * 30)
        logger.info(f"  🔄 Rewatches detected: {results['rewatches_detected']}")
        logger.info(f"  🏁 Rewatches completed: {results['rewatches_completed']}")
        logger.info(f"  🆕 New series started: {results['new_series_started']}")

        # Add rate limiting information
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
            logger.info(f"🏁 {results['rewatches_completed']} rewatch(es) were completed and rewatch count was incremented")

    def _save_debug_data(self, filename: str, data: Any) -> None:
        """Save debug data"""
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
        """Smart delay between operations based on rate limiting status"""
        try:
            # Check if we have rate limit info from the AniList client
            if hasattr(self.anilist_client, 'rate_limiter'):
                rate_limiter = self.anilist_client.rate_limiter

                # If we have plenty of requests remaining, use shorter delay
                if rate_limiter.remaining > 10:
                    delay = 0.5
                # If we're getting low on requests, use longer delay
                elif rate_limiter.remaining > 5:
                    delay = 1.0
                # If we're very low, use even longer delay
                else:
                    delay = 2.0

                logger.debug(f"Using {delay}s delay ({rate_limiter.get_status_info()})")
                time.sleep(delay)
            else:
                # Fallback to fixed delay if rate limiter not available
                time.sleep(1.0)

        except Exception as e:
            logger.debug(f"Error in intelligent delay: {e}")
            time.sleep(1.0)  # Safe fallback

    def _needs_update(self, anime_id: int, target_progress: int) -> bool:
        """
        Check if an anime entry needs to be updated

        Returns:
            True if update is needed, False if already up-to-date
        """
        try:
            existing_entry = self.anilist_client.get_anime_list_entry(anime_id)

            if not existing_entry:
                # No entry exists, definitely needs update
                return True

            current_progress = existing_entry.get('progress', 0)

            # If current progress is already >= target, no update needed
            if current_progress >= target_progress:
                logger.debug(f"Anime {anime_id} already at episode {current_progress} "
                             f"(target: {target_progress}) - skipping")
                return False

            # Progress is behind, needs update
            return True

        except Exception as e:
            logger.debug(f"Error checking update need: {e}")
            # On error, assume update is needed to be safe
            return True

    def _cleanup(self) -> None:
        """Clean up resources"""
        try:
            if hasattr(self.crunchyroll_scraper, 'cleanup'):
                self.crunchyroll_scraper.cleanup()
            logger.info("🧹 Cleanup completed")
        except Exception as e:
            logger.error(f"Error during cleanup: {e}")