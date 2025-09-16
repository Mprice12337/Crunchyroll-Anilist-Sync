"""WebDriver management utilities"""
import time
import logging
from selenium.webdriver.common.action_chains import ActionChains
import undetected_chromedriver as uc

logger = logging.getLogger(__name__)


class DriverManager:
    """Manages WebDriver setup and interactions"""

    @staticmethod
    def setup_undetected_chrome(headless=True):
        """Setup undetected Chrome driver"""
        try:
            logger.info("Setting up undetected Chrome driver...")

            options = uc.ChromeOptions()

            if headless:
                options.add_argument('--headless=new')
                logger.info("Running in headless mode")
            else:
                logger.info("Running with visible browser")

            # Additional options for better detection evasion
            options.add_argument('--no-sandbox')
            options.add_argument('--disable-dev-shm-usage')
            options.add_argument('--disable-blink-features=AutomationControlled')
            options.add_experimental_option("excludeSwitches", ["enable-automation"])
            options.add_experimental_option('useAutomationExtension', False)

            # User agent and window size
            options.add_argument(
                '--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
            options.add_argument('--window-size=1920,1080')

            # Performance and stability options
            options.add_argument('--disable-extensions')
            options.add_argument('--disable-plugins')
            options.add_argument('--disable-images')
            options.add_argument('--disable-javascript')
            options.add_argument('--disable-gpu')
            options.add_argument('--no-first-run')
            options.add_argument('--disable-default-apps')

            # Create the driver
            driver = uc.Chrome(options=options, version_main=None)

            # Execute script to hide webdriver property
            driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

            logger.info("Undetected Chrome driver setup completed")
            return driver

        except Exception as e:
            logger.error(f"Failed to setup undetected Chrome driver: {e}")
            return None

    @staticmethod
    def human_mouse_movement(driver, element):
        """Simulate human-like mouse movement"""
        try:
            actions = ActionChains(driver)
            actions.move_to_element(element)
            actions.perform()
            time.sleep(0.1 + (time.time() % 0.3))  # Random delay
        except Exception as e:
            logger.debug(f"Mouse movement failed: {e}")

    @staticmethod
    def human_typing(element, text):
        """Simulate human-like typing"""
        element.clear()
        for char in text:
            element.send_keys(char)
            time.sleep(0.05 + (time.time() % 0.1))  # Random typing speed