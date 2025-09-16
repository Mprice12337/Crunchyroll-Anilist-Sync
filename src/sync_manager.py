"""Main sync manager that coordinates Crunchyroll scraping and AniList updates"""
import json
import time
import os
from typing import Dict, Any, List, Optional
from datetime import datetime
import logging

from scrapers import CrunchyrollScraper
from anilist_client import AniListClient
from anime_matcher import AnimeMatcher
from history_parser import CrunchyrollHistoryParser

logger = logging.getLogger(__name__)

class SyncManager:
    def __init__(self, crunchyroll_email: str, crunchyroll_password: str, 
                 anilist_client_id: str, anilist_client_secret: str,
                 flaresolverr_url: Optional[str] = None, headless: bool = True,
                 dev_mode: bool = False):
        
        self.crunchyroll_email = crunchyroll_email
        self.crunchyroll_password = crunchyroll_password
        self.dev_mode = dev_mode
        
        # Initialize scraper with credentials
        self.scraper = CrunchyrollScraper(
            email=crunchyroll_email,
            password=crunchyroll_password,
            flaresolverr_url=flaresolverr_url,
            headless=headless,
            dev_mode=dev_mode
        )
        self.anilist = AniListClient(anilist_client_id, anilist_client_secret)
        self.matcher = AnimeMatcher()
        self.history_parser = CrunchyrollHistoryParser()
        
        self.cache_file = "_cache/sync_cache.json"
        self.cache = self._load_cache()
        
    def _load_cache(self) -> Dict[str, Any]:
        """Load cache from file"""
        try:
            with open(self.cache_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except FileNotFoundError:
            return {
                'last_sync': None,
                'anime_mappings': {},
                'processed_episodes': []
            }
        except Exception as e:
            logger.warning(f"Failed to load cache: {e}")
            return {
                'last_sync': None,
                'anime_mappings': {},
                'processed_episodes': []
            }
    
    def _save_cache(self):
        """Save cache to file"""
        try:
            import os
            os.makedirs('_cache', exist_ok=True)
            
            self.cache['last_sync'] = datetime.now().isoformat()
            
            with open(self.cache_file, 'w', encoding='utf-8') as f:
                json.dump(self.cache, f, indent=2, ensure_ascii=False)
                
        except Exception as e:
            logger.error(f"Failed to save cache: {e}")
    
    def _save_debug_data(self, data: Dict[str, Any], filename: str):
        """Save debug data to file when in dev mode"""
        if not self.dev_mode:
            return
        
        try:
            os.makedirs('_cache', exist_ok=True)
            
            debug_file = f"_cache/{filename}"
            with open(debug_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            
            logger.info(f"📝 Debug data saved to {debug_file}")
            
        except Exception as e:
            logger.error(f"Failed to save debug data: {e}")
    
    def sync(self) -> bool:
        """Perform complete sync operation"""
        try:
            logger.info("Starting Crunchyroll-AniList sync...")
            
            # Step 1: Authenticate with Crunchyroll only
            logger.info("Authenticating with Crunchyroll...")
            if not self.scraper.login(self.crunchyroll_email, self.crunchyroll_password):
                logger.error("Crunchyroll authentication failed")
                return False
            
            # Step 2: Get Crunchyroll watch history and save it immediately
            history_data = self._get_crunchyroll_history()
            if not history_data:
                logger.error("Failed to get Crunchyroll history")
                return False
            
            # Save raw history data in dev mode (this happens immediately after getting the data)
            self._save_debug_data(history_data, "raw_history_data.json")
            logger.info("✅ Crunchyroll data retrieved and saved!")
            
            # Step 3: Now authenticate with AniList (after we have the data saved)
            logger.info("Authenticating with AniList...")
            if not self.anilist.authenticate():
                logger.error("AniList authentication failed")
                # Don't return False here - we still got the Crunchyroll data
                logger.warning("⚠️  Continuing without AniList sync - Crunchyroll data is saved")
                return True  # Return True since we got the main data
            
            # Step 4: Process history and update AniList
            updates_made = self._process_history(history_data)
            
            # Step 5: Save cache
            self._save_cache()
            
            logger.info(f"Sync completed successfully! Made {updates_made} updates.")
            return True
            
        except Exception as e:
            logger.error(f"Sync failed: {e}")
            return False
        
        finally:
            self.scraper.close()

    def _authenticate(self) -> bool:
        """Authenticate with both services - DEPRECATED, now done separately in sync()"""
        # This method is no longer used - authentication is now done separately in sync()
        pass
    
    def _get_crunchyroll_history(self) -> Optional[Dict[str, Any]]:
        """Get watch history from Crunchyroll"""
        # Use pagination by default
        soup = self.scraper.scrape_history_page(use_pagination=True)
        
        if soup:
            logger.info("✅ Successfully scraped history page with pagination")
            
            # Save raw HTML in dev mode
            if self.dev_mode:
                try:
                    html_file = "_cache/scraped_history_page.html"
                    with open(html_file, 'w', encoding='utf-8') as f:
                        f.write(str(soup.prettify()))
                    logger.info(f"📄 Raw HTML saved to {html_file}")
                except Exception as e:
                    logger.error(f"Failed to save HTML debug file: {e}")
            
            # Parse the HTML to extract history data
            try:
                parsed_data = self.history_parser.parse_history_page(soup)
                if parsed_data:
                    logger.info(f"📊 Parsed {len(parsed_data.get('items', []))} history items")
                    return parsed_data
                else:
                    logger.warning("No history data could be parsed")
                    return None
            except Exception as e:
                logger.error(f"Failed to parse history data: {e}")
                return None
        else:
            logger.error("❌ Failed to scrape history page")
            return None
    
    def _process_history(self, history_data: Dict[str, Any]) -> int:
        """Process history data and update AniList"""
        updates_made = 0
        processed_items = []
        failed_items = []
        
        items = history_data.get('items', [])
        if not items:
            logger.info("No history items found")
            return 0
        
        logger.info(f"Processing {len(items)} history items...")
        
        for i, item in enumerate(items, 1):
            try:
                logger.debug(f"Processing item {i}/{len(items)}: {item.get('series_title', 'Unknown')}")
                
                result = self._process_history_item(item)
                
                # Track processing results
                item_result = {
                    **item,
                    'processing_result': 'success' if result else 'failed',
                    'processed_at': datetime.now().isoformat()
                }
                
                if result:
                    updates_made += 1
                    processed_items.append(item_result)
                    logger.info(f"✅ [{i}/{len(items)}] Updated: {item.get('series_title')} - Episode {item.get('episode_number')}")
                else:
                    failed_items.append(item_result)
                    logger.warning(f"❌ [{i}/{len(items)}] Failed: {item.get('series_title')} - Episode {item.get('episode_number')}")
                
                # Add delay to avoid rate limiting
                if i < len(items):  # Don't delay after the last item
                    time.sleep(1)
                
            except Exception as e:
                logger.error(f"Failed to process item {i}/{len(items)} {item}: {e}")
                failed_items.append({
                    **item,
                    'processing_result': 'error',
                    'error': str(e),
                    'processed_at': datetime.now().isoformat()
                })
                continue
        
        # Save processing results in dev mode
        if self.dev_mode:
            processing_summary = {
                'total_items': len(items),
                'successful_updates': len(processed_items),
                'failed_items': len(failed_items),
                'success_rate': f"{(len(processed_items) / len(items) * 100):.1f}%" if items else "0%",
                'processed_items': processed_items,
                'failed_items': failed_items,
                'processing_completed_at': datetime.now().isoformat()
            }
            
            self._save_debug_data(processing_summary, "processing_results.json")
            
            # Log summary
            logger.info("📊 Processing Summary:")
            logger.info(f"  Total items: {processing_summary['total_items']}")
            logger.info(f"  Successful updates: {processing_summary['successful_updates']}")
            logger.info(f"  Failed items: {processing_summary['failed_items']}")
            logger.info(f"  Success rate: {processing_summary['success_rate']}")
        
        return updates_made
    
    def _process_history_item(self, item: Dict[str, Any]) -> bool:
        """Process a single history item"""
        # Extract anime information from the item
        anime_title = item.get('series_title', '')
        episode_title = item.get('episode_title', '')
        episode_number = item.get('episode_number')
        
        if not anime_title:
            logger.debug(f"No anime title found in item: {item}")
            return False
        
        if not episode_number or episode_number <= 0:
            logger.debug(f"No valid episode number found for {anime_title}: {episode_number}")
            return False
        
        # Check if we've already processed this episode
        episode_key = f"{anime_title}:{episode_number}"
        if episode_key in self.cache['processed_episodes']:
            logger.debug(f"Already processed: {episode_key}")
            return False
        
        # Try to find matching anime in AniList
        anilist_anime = self._find_anilist_match(anime_title)
        if not anilist_anime:
            logger.debug(f"No AniList match found for: {anime_title}")
            return False
        
        # Update progress on AniList
        if self._update_anilist_progress(anilist_anime, episode_number):
            self.cache['processed_episodes'].append(episode_key)
            return True
        
        return False
    
    def _find_anilist_match(self, anime_title: str) -> Optional[Dict[str, Any]]:
        """Find matching anime on AniList"""
        # Check cache first
        if anime_title in self.cache['anime_mappings']:
            mapping = self.cache['anime_mappings'][anime_title]
            if mapping:
                return mapping
            else:
                # Previously failed to match
                return None
        
        # Search on AniList
        search_results = self.anilist.search_anime(anime_title)
        if not search_results:
            # Cache the failed match
            self.cache['anime_mappings'][anime_title] = None
            return None
        
        # Save search results in dev mode
        if self.dev_mode:
            search_debug = {
                'query': anime_title,
                'results': search_results,
                'searched_at': datetime.now().isoformat()
            }
            self._save_debug_data(search_debug, f"anilist_search_{anime_title.replace(' ', '_')}.json")
        
        # Find best match
        match_result = self.matcher.find_best_match(anime_title, search_results)
        if match_result:
            matched_anime, similarity = match_result
            # Cache the successful match
            self.cache['anime_mappings'][anime_title] = matched_anime
            
            if self.dev_mode:
                logger.debug(f"🎯 Matched '{anime_title}' to '{matched_anime.get('title', {}).get('romaji', 'Unknown')}' (similarity: {similarity:.2f})")
            
            return matched_anime
        else:
            # Cache the failed match
            self.cache['anime_mappings'][anime_title] = None
            return None
    
    def _update_anilist_progress(self, anime: Dict[str, Any], episode_number: int) -> bool:
        """Update anime progress on AniList"""
        media_id = anime['id']
        
        # Determine status based on episode number and total episodes
        total_episodes = anime.get('episodes', 0)
        status = None
        
        if total_episodes and episode_number >= total_episodes:
            status = 'COMPLETED'
        elif episode_number == 1:
            status = 'CURRENT'  # Started watching
        
        # Update progress
        success = self.anilist.update_anime_progress(media_id, episode_number, status)
        
        if self.dev_mode and success:
            logger.debug(f"📺 Updated AniList: {anime.get('title', {}).get('romaji', 'Unknown')} -> Episode {episode_number}" + 
                        (f" [Status: {status}]" if status else ""))
        
        return success

    # ... existing code ...

def sync_watch_history(self, watched_episodes: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Sync Crunchyroll watch history to AniList"""
    results = {
        'success': [],
        'failed': [],
        'skipped': [],
        'stats': {'total': 0, 'matched': 0, 'updated': 0}
    }

    results['stats']['total'] = len(watched_episodes)

    for episode_data in watched_episodes:
        anime_title = episode_data.get('series_title', '')
        current_episode = episode_data.get('latest_episode', 0)

        # Find AniList match
        anilist_anime = self._find_anilist_match(anime_title)
        if not anilist_anime:
            results['failed'].append({
                'title': anime_title,
                'reason': 'No AniList match found'
            })
            continue

        results['stats']['matched'] += 1

        # Determine status and progress
        total_episodes = anilist_anime.get('episodes') or 999  # Default for ongoing
        watch_status = self._determine_watch_status(current_episode, total_episodes)

        # Update AniList
        success = self._update_anilist_entry(
            anilist_anime['id'],
            current_episode,
            watch_status
        )

        if success:
            results['success'].append({
                'title': anime_title,
                'anilist_title': anilist_anime.get('title', {}).get('romaji', ''),
                'episodes': f"{current_episode}/{total_episodes}",
                'status': watch_status
            })
            results['stats']['updated'] += 1
        else:
            results['failed'].append({
                'title': anime_title,
                'reason': 'Failed to update AniList'
            })

    return results

def _determine_watch_status(self, current_episode: int, total_episodes: int) -> str:
    """Determine AniList watch status based on progress"""
    if current_episode == 0:
        return 'PLANNING'
    elif current_episode >= total_episodes:
        return 'COMPLETED'
    else:
        return 'CURRENT'

def _update_anilist_entry(self, anime_id: int, progress: int, status: str) -> bool:
    """Update anime entry on AniList"""
    try:
        success = self.anilist.update_anime_status(
            anime_id=anime_id,
            status=status,
            progress=progress
        )

        if success:
            logger.info(f"✅ Updated anime {anime_id}: {status} ({progress} episodes)")
        else:
            logger.error(f"❌ Failed to update anime {anime_id}")

        return success

    except Exception as e:
        logger.error(f"❌ Error updating anime {anime_id}: {e}")
        return False