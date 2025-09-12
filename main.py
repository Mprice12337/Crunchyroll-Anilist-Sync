"""Main entry point for Crunchyroll-AniList Sync"""
import os
import sys
import argparse
import logging
from dotenv import load_dotenv

# Add src to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from sync_manager import SyncManager
from history_parser import CrunchyrollHistoryParser
from anilist_client import AniListClient
import src.history_parser

def sync_episodes_to_anilist(watched_episodes, anilist_client, logger):
    """Sync watched episodes to AniList"""
    from src.anime_matcher import AnimeMatcher
    
    results = {
        'success': [],
        'failed': [],
        'skipped': [],
        'stats': {'total': 0, 'matched': 0, 'updated': 0}
    }
    
    results['stats']['total'] = len(watched_episodes)
    matcher = AnimeMatcher()
    
    for episode_data in watched_episodes:
        anime_title = episode_data.get('series_title', '')
        current_episode = episode_data.get('latest_episode', 0)
        
        logger.info(f"🔍 Processing: {anime_title} (Episode {current_episode})")
        
        # Search for anime on AniList
        search_results = anilist_client.search_anime(anime_title)
        if not search_results:
            results['failed'].append({
                'title': anime_title,
                'reason': 'No AniList search results found'
            })
            continue
        
        # Find best match
        match_result = matcher.find_best_match(anime_title, search_results)
        if not match_result:
            results['failed'].append({
                'title': anime_title,
                'reason': 'No suitable match found'
            })
            continue
        
        matched_anime, similarity = match_result
        results['stats']['matched'] += 1
        
        # Determine status and progress
        total_episodes = matched_anime.get('episodes') or 999  # Default for ongoing
        
        if current_episode == 0:
            status = 'PLANNING'
        elif current_episode >= total_episodes:
            status = 'COMPLETED'
        else:
            status = 'CURRENT'
        
        logger.info(f"📝 Updating: {matched_anime.get('title', {}).get('romaji', '')} → {status} ({current_episode}/{total_episodes})")
        
        # Update AniList
        success = anilist_client.update_anime_status(
            anime_id=matched_anime['id'], 
            status=status,
            progress=current_episode
        )
        
        if success:
            results['success'].append({
                'title': anime_title,
                'anilist_title': matched_anime.get('title', {}).get('romaji', ''),
                'episodes': f"{current_episode}/{total_episodes}",
                'status': status
            })
            results['stats']['updated'] += 1
        else:
            results['failed'].append({
                'title': anime_title,
                'reason': 'Failed to update AniList'
            })
    
    return results

def handle_cache_development_mode(logger):
    """Handle cache development mode - test with cached history page and AniList auth"""
    logger.info("Running in cache development mode")
    src.history_parser.parse_history_file(file_path=os.path.join('_cache', 'scraped_history_page.html'))

    # Check for cached history page
    cache_file = os.path.join('_cache', 'scraped_history_page.html')
    if not os.path.exists(cache_file):
        logger.error(f"Cached history page not found at {cache_file}")
        logger.info("Please run the scraper normally first to generate a cached history page")
        return 1
    
    logger.info(f"Using cached history page: {cache_file}")
    
    # Load and analyze cached history
    try:
        with open(cache_file, 'r', encoding='utf-8') as f:
            html_content = f.read()
        
        logger.info("Analyzing cached history page...")
        
        # Parse the HTML using our history parser
        from src.history_parser import CrunchyrollHistoryParser
        parser = CrunchyrollHistoryParser()
        
        # Use get_series_progress instead of parse_history_html for better data structure
        try:
            result = parser.get_series_progress(html_content)
            series_progress = result.get('series_progress', {})
            
            logger.info(f"=== Series Progress Analysis ===")
            logger.info(f"Found {len(series_progress)} series")
            
            for series_title, info in series_progress.items():
                latest_ep = info.get('latest_episode', 0)
                latest_season = info.get('latest_season', 1)
                logger.info(f"📺 {series_title}: S{latest_season}E{latest_ep}")
            
            # Convert to episodes list format if needed for compatibility
            watched_episodes = []
            for series_title, info in series_progress.items():
                watched_episodes.append({
                    'series_title': series_title,
                    'latest_episode': info.get('latest_episode', 0),
                    'latest_season': info.get('latest_season', 1),
                    'episode_name': info.get('episode_name', ''),
                })
            
        except Exception as parse_error:
            logger.error(f"Error with get_series_progress, falling back to parse_history_html: {parse_error}")
            
            # Fallback to the original method
            parsed_data = parser.parse_history_html(html_content)
            watched_episodes = parsed_data.get('episodes', [])
            
        if not watched_episodes:
            logger.warning("No episodes found in cached history")
            return 1
        
        logger.info(f"Found {len(watched_episodes)} episodes to process")
        
    except Exception as e:
        logger.error(f"Failed to load cached history: {e}")
        return 1
    
    # Authenticate with AniList for testing
    try:
        logger.info("Authenticating with AniList...")
        
        # Load environment variables
        anilist_client_id = os.getenv('ANILIST_CLIENT_ID')
        anilist_client_secret = os.getenv('ANILIST_CLIENT_SECRET')
        
        if not anilist_client_id or not anilist_client_secret:
            logger.error("Missing AniList credentials in environment variables")
            return 1
        
        anilist_client = AniListClient(anilist_client_id, anilist_client_secret)
        
        if not anilist_client.authenticate():
            logger.error("Failed to authenticate with AniList")
            return 1
        
        logger.info("Successfully authenticated with AniList")
        logger.info(f"User: {anilist_client.user_name} (ID: {anilist_client.user_id})")
        
        # Test search functionality with a couple of titles
        test_titles = ["The Greatest Demon Lord Is Reborn as a Typical Nobody", "Chainsaw Man"]
        
        for title in test_titles:
            logger.info(f"Testing AniList search with: '{title}'")
            search_results = anilist_client.search_anime(title)
            
            if search_results:
                logger.info(f"  Found {len(search_results)} search results:")
                for i, result in enumerate(search_results[:3], 1):  # Show first 3 results
                    title_info = result.get('title', {})
                    romaji = title_info.get('romaji', 'Unknown')
                    anime_id = result.get('id', 'Unknown')
                    logger.info(f"    {i}. {romaji} (ID: {anime_id})")
            else:
                logger.info(f"  No results found for '{title}'")
        
        logger.info("Cache development mode completed successfully!")
        
        # Test the sync process
        if watched_episodes:
            logger.info("🔄 Starting sync process...")
            
            # Sync the episodes
            sync_results = sync_episodes_to_anilist(watched_episodes, anilist_client, logger)
            
            # Print results
            logger.info("🎯 Sync Results:")
            logger.info(f"  Total: {sync_results['stats']['total']}")
            logger.info(f"  Matched: {sync_results['stats']['matched']}")
            logger.info(f"  Updated: {sync_results['stats']['updated']}")
            
            for success in sync_results['success']:
                logger.info(f"  ✅ {success['title']} → {success['status']} ({success['episodes']})")
            
            for failed in sync_results['failed']:
                logger.info(f"  ❌ {failed['title']}: {failed['reason']}")
        
        return 0
        
    except Exception as e:
        logger.error(f"Error during AniList testing: {e}")
        logger.debug("Exception details:", exc_info=True)
        return 1

def setup_logging(debug: bool = False):
    """Setup logging configuration"""
    log_level = logging.DEBUG if debug else logging.INFO

    # Create logs directory if it doesn't exist
    os.makedirs('logs', exist_ok=True)

    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler('logs/sync.log'),
            logging.StreamHandler()
        ]
    )

def parse_arguments():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(
        description='Sync Crunchyroll watch history with AniList progress',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py                    # Run normally (headless by default)
  python main.py --no-headless      # Run with visible browser
  python main.py --dev              # Run in development mode with debug output
  python main.py --dev --no-headless # Development mode with visible browser
  python main.py --cache-dev        # Development mode using cached history page
  python main.py --clear-cache      # Clear all cached data
  python main.py --show-cache       # Show cache status
"""
    )

    parser.add_argument('--dev', action='store_true',
                       help='Run in development mode with debug output')
    parser.add_argument('--no-headless', action='store_true',
                       help='Run with visible browser (show browser window)')
    parser.add_argument('--cache-dev', action='store_true',
                       help='Development mode: use cached history page and test AniList auth only')

    # Cache management commands
    parser.add_argument('--clear-cache', action='store_true',
                       help='Clear all cached data')
    parser.add_argument('--clear-auth-cache', action='store_true',
                       help='Clear only authentication cache')
    parser.add_argument('--show-cache', action='store_true',
                       help='Show cache status and contents')

    return parser.parse_args()

def handle_cache_commands(args):
    """Handle cache-related commands"""
    from cache_manager import CacheManager
    
    # Check if any cache commands were requested
    if not (args.clear_cache or args.clear_auth_cache or args.show_cache):
        return False
    
    cache_manager = CacheManager()
    
    if args.clear_cache:
        logger.info("Clearing all cache...")
        cache_manager.clear_all_cache()
        return True
    
    if args.clear_auth_cache:
        logger.info("Clearing authentication cache...")
        cache_manager.auth_cache.clear_all_auth()
        return True
    
    if args.show_cache:
        logger.info("Cache status:")
        cache_manager.print_cache_status()
        return True
    
    return False

    # Load environment variables
    load_dotenv()

    # Handle cache development mode
    if args.cache_dev:
        return handle_cache_development_mode(logger)

    return False

def main():
    """Main function"""
    args = parse_arguments()

    # Setup logging
    setup_logging(debug=args.dev or args.cache_dev)
    logger = logging.getLogger(__name__)

    # Handle cache commands
    if handle_cache_commands(args):
        return 0

    # Load environment variables
    load_dotenv()

    # Handle cache development mode
    if args.cache_dev:
        return handle_cache_development_mode(logger)

    # Get configuration from environment
    crunchyroll_email = os.getenv('CRUNCHYROLL_EMAIL')
    crunchyroll_password = os.getenv('CRUNCHYROLL_PASSWORD')
    anilist_client_id = os.getenv('ANILIST_CLIENT_ID')
    anilist_client_secret = os.getenv('ANILIST_CLIENT_SECRET')
    flaresolverr_url = os.getenv('FLARESOLVERR_URL')

    # Validate required environment variables
    if not all([crunchyroll_email, crunchyroll_password, anilist_client_id, anilist_client_secret]):
        logger.error("Missing required environment variables. Please check your .env file.")
        logger.info("Required variables: CRUNCHYROLL_EMAIL, CRUNCHYROLL_PASSWORD, ANILIST_CLIENT_ID, ANILIST_CLIENT_SECRET")
        return 1

    # Determine headless mode
    # Default to headless unless --no-headless is specified
    headless = not args.no_headless

    # Override with environment variable if set
    env_headless = os.getenv('HEADLESS')
    if env_headless is not None:
        headless = env_headless.lower() == 'true'

    # Log configuration
    logger.info("Starting Crunchyroll-AniList Sync")
    logger.info(f"Headless mode: {'Enabled' if headless else 'Disabled'}")
    logger.info(f"Development mode: {'Enabled' if args.dev else 'Disabled'}")
    logger.info(f"FlareSolverr URL: {flaresolverr_url if flaresolverr_url else 'Not configured'}")

    try:
        # Create sync manager
        sync_manager = SyncManager(
            crunchyroll_email=crunchyroll_email,
            crunchyroll_password=crunchyroll_password,
            anilist_client_id=anilist_client_id,
            anilist_client_secret=anilist_client_secret,
            flaresolverr_url=flaresolverr_url,
            headless=headless,
            dev_mode=args.dev
        )

        # Perform sync
        if sync_manager.sync():
            logger.info("🎉 Sync completed successfully!")

            if args.dev:
                logger.info("📁 Debug files saved in _cache/ directory")

            return 0
        else:
            logger.error("❌ Sync failed!")
            return 1

    except KeyboardInterrupt:
        logger.info("⏹️  Sync interrupted by user")
        return 1
    except Exception as e:
        logger.error(f"💥 Unexpected error: {e}")
        if args.debug or args.dev:
            import traceback
            logger.error("Full traceback:")
            logger.error(traceback.format_exc())
        return 1

if __name__ == "__main__":
    sys.exit(main())