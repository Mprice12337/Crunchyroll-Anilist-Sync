#!/usr/bin/env python3
"""
Main entry point for Crunchyroll-AniList Sync
"""

import os
import sys
import logging
import argparse
from datetime import datetime
from typing import Dict, Any, List, Optional

# Load environment variables from .env file
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    # If python-dotenv is not installed, try to install it
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "python-dotenv"])
    from dotenv import load_dotenv
    load_dotenv()

# Add src to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from sync_manager import SyncManager
from history_parser import CrunchyrollHistoryParser
from anilist_client import AniListClient
import src.history_parser


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


def handle_cache_commands(args, logger):
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


def sync_episodes_to_anilist(series_progress, anilist_client, anime_matcher, args):
    """Sync episode progress to AniList"""
    logger = logging.getLogger(__name__)
    
    try:
        # Handle case where series_progress might be a list instead of dict
        if isinstance(series_progress, list):
            logger.warning("Received list instead of dictionary for series_progress. Converting...")
            # Convert list to dictionary format expected by the function
            converted_progress = {}
            for item in series_progress:
                if isinstance(item, dict) and 'series_title' in item:
                    series_title = item['series_title']
                    # Create a basic progress structure
                    converted_progress[series_title] = {
                        'has_episodes': True,
                        'latest_episode': 1,  # Default to episode 1
                        'latest_season': 1,
                        'seasons': {1: 1},
                        'movies': [],
                        'episode_name': item.get('episode_title', '')
                    }
            series_progress = converted_progress
            
        if not isinstance(series_progress, dict):
            logger.error(f"Invalid series_progress format: {type(series_progress)}")
            return False
        
        updated_count = 0
        skipped_count = 0
        error_count = 0
        
        for series_title, progress_info in series_progress.items():
            try:
                logger.info(f"Processing: {series_title}")
                
                # Handle regular episodes
                if progress_info.get('has_episodes', False):
                    success = _sync_series_episodes(series_title, progress_info, anilist_client, anime_matcher, args)
                    if success:
                        updated_count += 1
                    else:
                        error_count += 1
                
                # Handle movies/specials
                movies = progress_info.get('movies', [])
                if movies:
                    movie_success = _sync_series_movies(series_title, movies, anilist_client, anime_matcher, args)
                    if movie_success:
                        logger.info(f"Updated movies/specials for {series_title}")
                    else:
                        logger.warning(f"Failed to update movies/specials for {series_title}")
                
                # If neither episodes nor movies were processed, count as skipped
                if not progress_info.get('has_episodes', False) and not movies:
                    logger.warning(f"No episodes or movies found for {series_title}")
                    skipped_count += 1
                    
            except Exception as e:
                logger.error(f"Error processing {series_title}: {e}")
                error_count += 1
                continue
        
        logger.info(f"Sync completed - Updated: {updated_count}, Skipped: {skipped_count}, Errors: {error_count}")
        return updated_count > 0
        
    except Exception as e:
        logger.error(f"Error during sync: {e}")
        return False

def _sync_series_episodes(series_title, progress_info, anilist_client, anime_matcher, args):
    """Sync regular episode progress for a series"""
    logger = logging.getLogger(__name__)
    
    try:
        latest_episode = progress_info.get('latest_episode', 0)
        latest_season = progress_info.get('latest_season', 1)
        
        if latest_episode <= 0:
            logger.warning(f"No valid episode progress for {series_title}")
            return False
        
        # Search for the anime on AniList
        search_results = anilist_client.search_anime(series_title)
        if not search_results:
            logger.warning(f"No AniList match found for: {series_title}")
            return False
        
        # Use anime matcher to find best match
        match_result = anime_matcher.find_best_match(series_title, search_results)
        if not match_result:
            logger.warning(f"No suitable match found for: {series_title}")
            return False
        
        # Extract anime data and similarity from the tuple
        best_match, similarity = match_result
        anime_id = best_match['id']
        anime_title = best_match.get('title', {}).get('romaji', series_title)
        
        logger.info(f"Matched '{series_title}' to AniList: {anime_title} (ID: {anime_id}, Similarity: {similarity:.2f})")
        
        if args.dry_run:
            logger.info(f"[DRY RUN] Would update {anime_title} to episode {latest_episode}")
            return True
        
        # Update progress on AniList
        success = anilist_client.update_anime_progress(anime_id, latest_episode)
        if success:
            logger.info(f"✅ Updated {anime_title} to episode {latest_episode}")
            return True
        else:
            logger.error(f"❌ Failed to update {anime_title}")
            return False
            
    except Exception as e:
        logger.error(f"Error syncing episodes for {series_title}: {e}")
        return False

def _sync_series_movies(series_title, movies, anilist_client, anime_matcher, args):
    """Sync movies/specials for a series"""
    logger = logging.getLogger(__name__)
    
    try:
        logger.info(f"Processing {len(movies)} movies/specials for {series_title}")
        
        success_count = 0
        
        for movie in movies:
            movie_title = movie.get('title', '')
            if not movie_title:
                continue
                
            logger.info(f"Processing movie/special: {movie_title}")
            
            # Search for the movie/special on AniList
            # Try both the full movie title and the base series title
            search_queries = [movie_title, series_title]
            
            best_match = None
            similarity = 0.0
            
            for query in search_queries:
                search_results = anilist_client.search_anime(query)
                if search_results:
                    # Look for movies/specials specifically
                    movie_results = [
                        result for result in search_results 
                        if result.get('format') in ['MOVIE', 'SPECIAL', 'OVA', 'ONA']
                    ]
                    
                    if movie_results:
                        match_result = anime_matcher.find_best_match(movie_title, movie_results)
                        if match_result:
                            best_match, similarity = match_result
                            break
                    
                    # If no movie format found, try general matching
                    if not best_match:
                        match_result = anime_matcher.find_best_match(movie_title, search_results)
                        if match_result:
                            best_match, similarity = match_result
                            break
            
            if not best_match:
                logger.warning(f"No AniList match found for movie: {movie_title}")
                continue
            
            anime_id = best_match['id']
            anime_title = best_match.get('title', {}).get('romaji', movie_title)
            anime_format = best_match.get('format', 'UNKNOWN')
            total_episodes = best_match.get('episodes', 1) or 1
            
            logger.info(f"Matched '{movie_title}' to AniList: {anime_title} (ID: {anime_id}, Format: {anime_format}, Similarity: {similarity:.2f})")
            
            if args.dry_run:
                logger.info(f"[DRY RUN] Would mark {anime_title} as completed ({total_episodes}/{total_episodes})")
                success_count += 1
                continue
            
            # For movies/specials, mark as completed
            success = anilist_client.update_anime_progress(anime_id, total_episodes, status='COMPLETED')
            if success:
                logger.info(f"✅ Marked {anime_title} as completed")
                success_count += 1
            else:
                logger.error(f"❌ Failed to update {anime_title}")
        
        return success_count > 0
        
    except Exception as e:
        logger.error(f"Error syncing movies for {series_title}: {e}")
        return False


def load_cached_history(cache_file, logger):
    """Load cached history file and parse it"""
    try:
        if not os.path.exists(cache_file):
            logger.error(f"Cache file not found: {cache_file}")
            return {}

        logger.info(f"Loading cached history from: {cache_file}")

        # Parse the cached history file
        parser = CrunchyrollHistoryParser()
        result = src.history_parser.parse_history_file(cache_file)
        
        # The parse_history_file returns a dict with 'series_progress' key
        series_progress = result.get('series_progress', {})
        
        if not series_progress:
            logger.warning("No series progress found in cached file")
            return {}

        logger.info(f"Loaded {len(series_progress)} series from cache")
        
        # Log some sample data for debugging
        for series_title, progress in list(series_progress.items())[:3]:
            logger.debug(f"Sample: {series_title} -> {progress}")
        
        return series_progress

    except Exception as e:
        logger.error(f"Error loading cached history: {e}")
        return {}


def test_anilist_search(anilist_client, logger):
    """Test AniList search functionality with sample titles"""
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


def authenticate_anilist(logger):
    """Authenticate with AniList and return client"""
    logger.info("Authenticating with AniList...")

    anilist_client_id = os.getenv('ANILIST_CLIENT_ID')
    anilist_client_secret = os.getenv('ANILIST_CLIENT_SECRET')

    if not anilist_client_id or not anilist_client_secret:
        logger.error("Missing AniList credentials in environment variables")
        return None

    anilist_client = AniListClient(anilist_client_id, anilist_client_secret)

    if not anilist_client.authenticate():
        logger.error("Failed to authenticate with AniList")
        return None

    logger.info("Successfully authenticated with AniList")
    logger.info(f"User: {anilist_client.user_name} (ID: {anilist_client.user_id})")

    return anilist_client


def handle_cache_development_mode(logger):
    """Handle cache development mode - test with cached history page and AniList auth"""
    logger.info("Running in cache development mode")

    # Load cached history
    cache_file = os.path.join('_cache', 'scraped_history_page.html')
    watched_episodes = load_cached_history(cache_file, logger)

    if not watched_episodes:
        logger.warning("No episodes found in cached history")
        return 1

    logger.info(f"Found {len(watched_episodes)} episodes to process")

    # Authenticate with AniList
    anilist_client = authenticate_anilist(logger)
    if not anilist_client:
        return 1

    # Test search functionality
    test_anilist_search(anilist_client, logger)

    logger.info("🔄 Starting sync process...")

    # Create anime matcher
    from anime_matcher import AnimeMatcher
    anime_matcher = AnimeMatcher()

    # Create a mock args object for cache dev mode
    class MockArgs:
        def __init__(self):
            self.dry_run = False  # Set to True if you want to test without actually updating
            self.cache_dev = True

    args = MockArgs()

    # Sync the episodes
    sync_results = sync_episodes_to_anilist(watched_episodes, anilist_client, anime_matcher, args)

    # Print results
    logger.info("🎯 Sync Results:")
    logger.info(f"  Success: {sync_results}")


def validate_environment_variables(logger):
    """Validate required environment variables"""
    required_vars = [
        'CRUNCHYROLL_EMAIL',
        'CRUNCHYROLL_PASSWORD',
        'ANILIST_CLIENT_ID',
        'ANILIST_CLIENT_SECRET'
    ]

    missing_vars = [var for var in required_vars if not os.getenv(var)]

    if missing_vars:
        logger.error("Missing required environment variables:")
        for var in missing_vars:
            logger.error(f"  - {var}")
        logger.info("Please check your .env file.")
        return False

    return True


def get_headless_mode(args):
    """Determine headless mode from arguments and environment"""
    # Default to headless unless --no-headless is specified
    headless = not args.no_headless

    # Override with environment variable if set
    env_headless = os.getenv('HEADLESS')
    if env_headless is not None:
        headless = env_headless.lower() == 'true'

    return headless


def main():
    """Main entry point"""
    try:
        logger.info("🚀 Starting Crunchyroll-AniList Sync")
        
        # Load environment variables (should now work since we loaded .env)
        crunchyroll_email = os.getenv('CRUNCHYROLL_EMAIL')
        crunchyroll_password = os.getenv('CRUNCHYROLL_PASSWORD')
        anilist_client_id = os.getenv('ANILIST_CLIENT_ID')
        anilist_client_secret = os.getenv('ANILIST_CLIENT_SECRET')
        flaresolverr_url = os.getenv('FLARESOLVERR_URL')
        
        # Debug: Print whether variables are loaded (remove this after testing)
        logger.info(f"Environment check - Email: {'✅' if crunchyroll_email else '❌'}, "
                   f"Password: {'✅' if crunchyroll_password else '❌'}, "
                   f"Client ID: {'✅' if anilist_client_id else '❌'}, "
                   f"Client Secret: {'✅' if anilist_client_secret else '❌'}")
        
        # Validate required environment variables
        if not all([crunchyroll_email, crunchyroll_password, anilist_client_id, anilist_client_secret]):
            missing = []
            if not crunchyroll_email:
                missing.append('CRUNCHYROLL_EMAIL')
            if not crunchyroll_password:
                missing.append('CRUNCHYROLL_PASSWORD')
            if not anilist_client_id:
                missing.append('ANILIST_CLIENT_ID')
            if not anilist_client_secret:
                missing.append('ANILIST_CLIENT_SECRET')
            
            logger.error(f"❌ Missing required environment variables: {', '.join(missing)}")
            logger.error("Please check your .env file and ensure all required variables are set")
            
            # Check if .env file exists
            if os.path.exists('.env'):
                logger.info("✅ .env file found")
                # Show first few characters of each variable for debugging
                with open('.env', 'r') as f:
                    lines = f.readlines()
                    for line in lines:
                        if '=' in line and not line.startswith('#'):
                            key, value = line.split('=', 1)
                            key = key.strip()
                            value = value.strip()
                            if key in ['CRUNCHYROLL_EMAIL', 'CRUNCHYROLL_PASSWORD', 'ANILIST_CLIENT_ID', 'ANILIST_CLIENT_SECRET']:
                                masked_value = value[:3] + '*' * (len(value) - 3) if len(value) > 3 else '*' * len(value)
                                logger.info(f"Found in .env: {key}={masked_value}")
            else:
                logger.error("❌ .env file not found! Please create one based on .env.example")
            
            return
        
        # Development mode check
        dev_mode = os.getenv('DEV_MODE', 'false').lower() == 'true'
        headless = os.getenv('HEADLESS', 'true').lower() == 'true'
        
        # Pagination settings
        max_pages = int(os.getenv('MAX_HISTORY_PAGES', '10'))  # Default to 10 pages
        
        if dev_mode:
            logger.info("🔧 Running in development mode")
            
        logger.info(f"📖 Will scrape up to {max_pages} pages of history")

        # Initialize sync manager with credentials
        from src.sync_manager import SyncManager
        
        sync_manager = SyncManager(
            crunchyroll_email=crunchyroll_email,
            crunchyroll_password=crunchyroll_password,
            anilist_client_id=anilist_client_id,
            anilist_client_secret=anilist_client_secret,
            flaresolverr_url=flaresolverr_url,
            headless=headless,
            dev_mode=dev_mode
        )
        
        # Update scraper with pagination setting
        if hasattr(sync_manager.scraper, 'max_pages'):
            sync_manager.scraper.max_pages = max_pages

        # Run the sync process
        sync_manager.sync()

        logger.info("✅ Sync completed successfully!")

    except KeyboardInterrupt:
        logger.info("⏹️  Process interrupted by user")
    except Exception as e:
        logger.error(f"❌ Sync failed: {e}")
        raise

if __name__ == '__main__':
    logger = logging.getLogger(__name__)
    try:
        setup_logging()
        main()
    except Exception as e:
        logger.error(f"Unhandled exception: {e}", exc_info=True)
        sys.exit(1)
    sys.exit(0)