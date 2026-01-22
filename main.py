#!/usr/bin/env python3
"""
Main entry point for Crunchyroll-AniList Sync with clean logging and fixed imports
"""

import os
import sys
import logging
import argparse
from pathlib import Path

# Version
__version__ = "1.03"

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
    parser.add_argument('--debug-matching', action='store_true',
                        help='Enable detailed matching diagnostics (implies --dry-run)')
    parser.add_argument('--save-changeset', action='store_true',
                        help='Save AniList updates to a changeset file instead of applying them (implies --dry-run)')
    parser.add_argument('--apply-changeset', type=str, metavar='FILE',
                        help='Apply a previously saved changeset file (skips Crunchyroll scraping)')
    parser.add_argument('--no-early-stop', action='store_true',
                        help='Disable early stopping when most items are already synced (useful for full scans)')
    parser.add_argument('--version', action='version', version=f'%(prog)s {__version__}')

    return parser.parse_args()


def validate_environment() -> bool:
    """Validate required environment variables"""
    required_vars = [
        'CRUNCHYROLL_EMAIL',
        'CRUNCHYROLL_PASSWORD',
        'ANILIST_AUTH_CODE'
    ]

    missing_vars = [var for var in required_vars if not os.getenv(var)]

    if missing_vars:
        logging.error("Missing required environment variables:")
        for var in missing_vars:
            logging.error(f"  - {var}")

        if 'ANILIST_AUTH_CODE' in missing_vars:
            logging.error("\n" + "=" * 60)
            logging.error("To get your AniList auth code:")
            logging.error("1. Visit: https://anilist.co/api/v2/oauth/authorize?client_id=21538&response_type=code")
            logging.error("2. Authorize the application")
            logging.error("3. Copy the code from the PIN page")
            logging.error("4. Set ANILIST_AUTH_CODE in your .env file")
            logging.error("=" * 60)

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

        # Handle changeset application mode
        if args.apply_changeset:
            logger.info(f"📂 Applying changeset from: {args.apply_changeset}")

            # Validate environment (still need AniList auth)
            if not validate_environment():
                return 1

            # Load changeset
            from debug_collector import DebugCollector
            try:
                changeset_data = DebugCollector.load_changeset(args.apply_changeset)
            except (FileNotFoundError, ValueError) as e:
                logger.error(f"Failed to load changeset: {e}")
                return 1

            # Apply changeset using sync manager
            config = {
                'crunchyroll_email': None,  # Not needed for changeset apply
                'crunchyroll_password': None,
                'flaresolverr_url': None,
                'headless': True,
                'max_pages': 0,
                'dry_run': False,  # Actually apply the changes
                'clear_cache': False,
                'debug': args.debug,
                'debug_matching': False
            }

            sync_manager = SyncManager(**config)

            if sync_manager.apply_changeset(changeset_data):
                logger.info("✅ Changeset applied successfully!")
                return 0
            else:
                logger.error("❌ Failed to apply changeset")
                return 1

        # Normal sync mode
        # Validate environment
        if not validate_environment():
            return 1

        # Get configuration from environment
        config = {
            'crunchyroll_email': os.getenv('CRUNCHYROLL_EMAIL'),
            'crunchyroll_password': os.getenv('CRUNCHYROLL_PASSWORD'),
            'flaresolverr_url': os.getenv('FLARESOLVERR_URL'),
            'headless': not args.no_headless,
            'max_pages': args.max_pages,
            'dry_run': args.dry_run or args.debug_matching or args.save_changeset,
            'clear_cache': args.clear_cache,
            'debug': args.debug,  # Pass debug flag to components
            'debug_matching': args.debug_matching,
            'save_changeset': args.save_changeset,
            'no_early_stop': args.no_early_stop or args.save_changeset  # Auto-disable early stop for changesets
        }

        logger.info(
            f"Configuration: max_pages={config['max_pages']}, headless={config['headless']}, dry_run={config['dry_run']}")

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
