"""
Enhanced sync manager with fixes for movie matching and series search
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
    """Enhanced sync manager with dynamic AniList validation"""

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
            'episode_conversions': 0  # Track when we convert episode numbers
        }

        # Cache for anime season structures (temporary, per run)
        self.season_structure_cache = {}

        # Store original episode data for movie processing
        self.episode_data_cache = {}

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

            # Step 3: Process and update AniList with dynamic validation
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
        """Scrape watch history from Crunchyroll"""
        logger.info("📚 Scraping Crunchyroll watch history...")

        try:
            self.watch_history = self.crunchyroll_scraper.get_watch_history(
                max_pages=self.config.get('max_pages', 10)
            )

            if not self.watch_history:
                logger.warning("⚠️ No watch history found")
                return True

            if self.config.get('debug'):
                self._save_debug_data('watch_history.json', self.watch_history)

            return True

        except Exception as e:
            logger.error(f"Failed to scrape Crunchyroll history: {e}")
            return False

    def _update_anilist_progress_with_validation(self) -> bool:
        """Update AniList progress with dynamic validation"""
        logger.info("🎯 Updating AniList progress with dynamic validation...")

        if not self.watch_history:
            logger.info("No episodes to process")
            return True

        # Group episodes by series and season, but keep original episode data
        series_progress = self._group_episodes_by_series_and_season(self.watch_history)

        logger.info(f"Processing {len(series_progress)} unique series-season combinations...")

        for i, ((series_title, cr_season), latest_episode) in enumerate(series_progress.items(), 1):
            try:
                season_display = "Movie" if cr_season == 0 else f"Season {cr_season}"
                logger.info(f"[{i}/{len(series_progress)}] Processing: {series_title} ({season_display}) - Episode {latest_episode}")

                if self._process_series_entry(series_title, cr_season, latest_episode):
                    self.sync_results['successful_updates'] += 1
                else:
                    self.sync_results['failed_updates'] += 1

                time.sleep(1.5)  # Rate limiting

            except Exception as e:
                logger.error(f"Error processing {series_title} Season {cr_season}: {e}")
                self.sync_results['failed_updates'] += 1
                continue

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
        """Process a single series entry with dynamic AniList validation"""

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

            # Determine status
            status = None
            if total_episodes and actual_episode >= total_episodes:
                status = 'COMPLETED'
                logger.info(f"🏁 Will mark as completed ({actual_episode}/{total_episodes})")

            # Update on AniList (or dry run)
            if self.config.get('dry_run'):
                logger.info(f"[DRY RUN] Would update {anime_title} to episode {actual_episode}")
                if status:
                    logger.info(f"[DRY RUN] Would mark as {status}")
                return True

            # Actual update
            success = self.anilist_client.update_anime_progress(
                anime_id=anime_id,
                progress=actual_episode,
                status=status
            )

            if success:
                logger.info(f"✅ Successfully updated {anime_title} to episode {actual_episode}")
            else:
                logger.error(f"❌ Failed to update {anime_title}")

            return success

        except Exception as e:
            logger.error(f"Error processing {series_title}: {e}")
            return False

    def _search_anime_comprehensive(self, series_title: str) -> List[Dict]:
        """Search AniList and get all related entries (all seasons)"""

        # Clean the title for better searching
        clean_title = self._clean_title_for_search(series_title)

        # Search with the clean title
        results = self.anilist_client.search_anime(clean_title)

        if not results:
            # Try with original title if clean title didn't work
            results = self.anilist_client.search_anime(series_title)

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

        # First pass: collect all TV series with their metadata
        tv_series = []
        for result in search_results:
            # Skip movies/specials for regular season structure
            format_type = (result.get('format', '') or '').upper()
            if format_type in ['MOVIE', 'SPECIAL', 'OVA', 'ONA']:
                continue

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
                'has_explicit_season': self._has_explicit_season_number(result)
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
                                            cr_episode: int, season_structure: Dict) -> Tuple[Optional[Dict], int, int]:
        """Determine the correct AniList entry and episode number"""

        # First, check if the Crunchyroll season/episode makes sense as-is
        if cr_season in season_structure:
            season_data = season_structure[cr_season]
            max_episodes = season_data['episodes']

            # If episode number is valid for this season, use it directly
            if max_episodes and cr_episode <= max_episodes:
                logger.info(f"✅ Episode {cr_episode} is valid for season {cr_season} (max: {max_episodes})")
                return season_data['entry'], cr_season, cr_episode
            else:
                logger.info(f"⚠️ Episode {cr_episode} exceeds season {cr_season} max ({max_episodes}), checking if absolute numbering...")

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

    def _process_movie(self, series_title: str, episode_data: Dict = None) -> bool:
        """Process movie entries with better title matching"""
        try:
            logger.info(f"🎬 Processing movie: {series_title}")

            # FIX 2: Use episode_title and season_title for better movie matching
            search_queries = []

            # If we have episode data, use the more specific titles
            if episode_data:
                episode_title = episode_data.get('episode_title', '').strip()
                season_title = episode_data.get('season_title', '').strip()

                # Add specific titles first for better matching
                if episode_title:
                    # Clean up the episode title
                    clean_episode_title = episode_title.replace(' - ', ' ').strip()
                    search_queries.append(clean_episode_title)

                if season_title:
                    # Clean up the season title
                    clean_season_title = season_title.replace(' - ', ' ').strip()
                    if clean_season_title not in search_queries:
                        search_queries.append(clean_season_title)

            # Then add the generic searches as fallback
            clean_title = series_title.replace(' - ', ' ').strip()
            search_queries.extend([
                f"{clean_title} 0",
                f"{clean_title} Movie",
                clean_title
            ])

            best_match = None
            best_similarity = 0

            for query in search_queries:
                logger.debug(f"🔍 Searching for movie with: {query}")
                results = self.anilist_client.search_anime(query)
                if not results:
                    continue

                for result in results:
                    format_type = (result.get('format', '') or '').upper()
                    if format_type not in ['MOVIE', 'SPECIAL', 'OVA']:
                        continue

                    # Calculate similarity with the query
                    similarity = self.anime_matcher._calculate_title_similarity(query, result)

                    # If we have episode data, also check similarity with episode/season title
                    if episode_data:
                        if episode_title:
                            ep_similarity = self.anime_matcher._calculate_title_similarity(episode_title, result)
                            similarity = max(similarity, ep_similarity)
                        if season_title:
                            season_similarity = self.anime_matcher._calculate_title_similarity(season_title, result)
                            similarity = max(similarity, season_similarity)

                    if similarity > best_similarity and similarity >= 0.85:
                        best_match = result
                        best_similarity = similarity
                        logger.debug(f"   Found potential match: {self._get_anime_title(result)} (similarity: {similarity:.2f})")

                # If we found a very good match with specific titles, use it
                if best_match and best_similarity >= 0.9:
                    break

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

            if self.config.get('dry_run'):
                logger.info(f"[DRY RUN] Would mark movie {anime_title} as COMPLETED")
                return True

            success = self.anilist_client.update_anime_progress(
                anime_id=anime_id,
                progress=1,
                status='COMPLETED'
            )

            if success:
                logger.info(f"✅ Marked movie {anime_title} as COMPLETED")
                self.sync_results['movies_completed'] += 1

            return success

        except Exception as e:
            logger.error(f"Error processing movie {series_title}: {e}")
            return False

    def _get_anime_title(self, anime_data: Dict) -> str:
        """Get the primary title from anime data"""
        title_obj = anime_data.get('title', {})
        if isinstance(title_obj, dict):
            return title_obj.get('romaji', title_obj.get('english', 'Unknown'))
        return str(title_obj) if title_obj else 'Unknown'

    def _report_enhanced_results(self) -> None:
        """Report sync results"""
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

        if results['successful_updates'] > 0:
            total_attempts = results['successful_updates'] + results['failed_updates']
            success_rate = (results['successful_updates'] / total_attempts) * 100
            logger.info(f"  📈 Success rate: {success_rate:.1f}%")

        logger.info("=" * 60)

        if results['episode_conversions'] > 0:
            logger.info("💡 Episode numbers were automatically converted from absolute to per-season numbering")

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

    def _cleanup(self) -> None:
        """Clean up resources"""
        try:
            if hasattr(self.crunchyroll_scraper, 'cleanup'):
                self.crunchyroll_scraper.cleanup()
            logger.info("🧹 Cleanup completed")
        except Exception as e:
            logger.error(f"Error during cleanup: {e}")