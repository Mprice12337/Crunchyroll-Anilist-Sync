"""Base scraper with common functionality"""
import time
import logging
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)


class BaseScraper(ABC):
    """Base class for web scrapers"""

    def __init__(self, headless=True, dev_mode=False):
        self.headless = headless
        self.dev_mode = dev_mode
        self.driver = None

    @abstractmethod
    def setup_driver(self):
        """Setup the WebDriver"""
        try:
            if self.flaresolverr_url:
                # Initialize FlareSolverr client
                from .flaresolverr_client import FlareSolverrClient
                self.flaresolverr_client = FlareSolverrClient(self.flaresolverr_url)
                logger.info("Using FlareSolverr for web scraping")
                
                # Also setup Selenium as fallback
                try:
                    from .driver_manager import DriverManager
                    self.driver = DriverManager.setup_undetected_chrome(self.headless)
                    logger.info("Selenium WebDriver also available as fallback")
                except Exception as e:
                    logger.warning(f"Could not setup Selenium fallback: {e}")
            else:
                # Initialize Selenium WebDriver
                from .driver_manager import DriverManager
                self.driver = DriverManager.setup_undetected_chrome(self.headless)
                logger.info("WebDriver setup completed")
                
        except Exception as e:
            logger.error(f"Failed to setup driver: {e}")
            raise

    @abstractmethod
    def cleanup(self):
        """Clean up resources - must be implemented by subclasses"""
        pass

    def _save_debug_file(self, content, filename):
        """Save debug file to cache directory"""
        import os
        try:
            os.makedirs('_cache', exist_ok=True)
            filepath = os.path.join('_cache', filename)

            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(content)

            logger.info(f"Debug file saved: {filepath}")

        except Exception as e:
            logger.error(f"Failed to save debug file: {e}")

    def __enter__(self):
        """Context manager entry"""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        self.cleanup()