#!/usr/bin/env python3
"""
Main entry point for Crunchyroll-AniList Sync with clean logging and fixed imports
"""

import os
import sys
import logging
import argparse
from pathlib import Path

# Add src to Python path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from dotenv import load_dotenv
from sync_manager import SyncManager

# Load environment variables
load_dotenv()


def setup_logging(debug: bool = False) -> None:
    """Setup logging configuration with clean output"""
    log_level = logging.DEBUG if debug else logging.INFO

    # Create logs directory
    Path("logs").mkdir(exist_ok=True)

    # Configure main logging
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler('logs/sync.log'),
            logging.StreamHandler()
        ]
    )

    # **SUPPRESS SELENIUM/URLLIB3 HTML LOGGING**
    # These loggers output massive HTML content that clutters logs
    logging.getLogger('selenium.webdriver.remote.remote_connection').setLevel(logging.WARNING)
    logging.getLogger('selenium.webdriver.common.service').setLevel(logging.WARNING)
    logging.getLogger('urllib3.connectionpool').setLevel(logging.WARNING)
    logging.getLogger('undetected_chromedriver').setLevel(logging.WARNING)

    # Keep our application debug logs but suppress third-party noise
    if debug:
        # Set debug level for our modules
        for module in ['sync_manager', 'crunchyroll_scraper', 'anilist_client', 'anime_matcher', '__main__']:
            logging.getLogger(module).setLevel(logging.DEBUG)

        # But keep Selenium quiet even in debug mode
        logging.getLogger('selenium').setLevel(logging.INFO)
        logging.getLogger('urllib3').setLevel(logging.INFO)


def parse_arguments() -> argparse.Namespace:
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(
        description='Sync Crunchyroll watch history with AniList progress'
    )

    parser.add_argument('--debug', action='store_true',
                        help='Enable debug logging (but suppress HTML spam)')
    parser.add_argument('--headless', action='store_true', default=True,
                        help='Run browser in headless mode (default)')
    parser.add_argument('--no-headless', action='store_true',
                        help='Run with visible browser')
    parser.add_argument('--dry-run', action='store_true',
                        help='Show what would be updated without making changes')
    parser.add_argument('--max-pages', type=int, default=10,
                        help='Maximum number of history pages to scrape (default: 10)')
    parser.add_argument('--clear-cache', action='store_true',
                        help='Clear all cached data before running')

    return parser.parse_args()


def validate_environment() -> bool:
    """Validate required environment variables"""
    required_vars = [
        'CRUNCHYROLL_EMAIL',
        'CRUNCHYROLL_PASSWORD',
        'ANILIST_CLIENT_ID',
        'ANILIST_CLIENT_SECRET'
    ]

    missing_vars = [var for var in required_vars if not os.getenv(var)]

    if missing_vars:
        logging.error("Missing required environment variables:")
        for var in missing_vars:
            logging.error(f"  - {var}")
        logging.error("Please check your .env file.")
        return False

    return True


def main() -> int:
    """Main entry point"""
    args = parse_arguments()

    # Setup clean logging (suppress Selenium HTML spam)
    setup_logging(args.debug)
    logger = logging.getLogger(__name__)

    try:
        logger.info("🚀 Starting Crunchyroll-AniList Sync")

        # Validate environment
        if not validate_environment():
            return 1

        # Get configuration from environment
        config = {
            'crunchyroll_email': os.getenv('CRUNCHYROLL_EMAIL'),
            'crunchyroll_password': os.getenv('CRUNCHYROLL_PASSWORD'),
            'anilist_client_id': os.getenv('ANILIST_CLIENT_ID'),
            'anilist_client_secret': os.getenv('ANILIST_CLIENT_SECRET'),
            'flaresolverr_url': os.getenv('FLARESOLVERR_URL'),
            'headless': not args.no_headless,
            'max_pages': args.max_pages,
            'dry_run': args.dry_run,
            'clear_cache': args.clear_cache,
            'debug': args.debug  # Pass debug flag to components
        }

        logger.info(f"Configuration: max_pages={config['max_pages']}, headless={config['headless']}, dry_run={config['dry_run']}")

        # Initialize and run sync manager
        sync_manager = SyncManager(**config)

        if sync_manager.run_sync():
            logger.info("✅ Sync completed successfully!")
            return 0
        else:
            logger.error("❌ Sync failed")
            return 1

    except KeyboardInterrupt:
        logger.info("⏹️ Process interrupted by user")
        return 1
    except Exception as e:
        logger.error(f"❌ Unhandled error: {e}", exc_info=True)
        return 1


if __name__ == '__main__':
    sys.exit(main())