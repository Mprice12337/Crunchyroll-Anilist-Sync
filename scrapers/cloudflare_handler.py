"""Cloudflare challenge detection and handling"""
import time
import logging
from selenium.webdriver.common.by import By

logger = logging.getLogger(__name__)


class CloudflareHandler:
    """Handles Cloudflare challenge detection and waiting"""

    @staticmethod
    def wait_for_challenge_completion(driver, max_wait_time=120):
        """Wait for Cloudflare challenge to complete with advanced detection"""
        logger.info("Waiting for Cloudflare challenge to complete...")
        start_time = time.time()

        cloudflare_indicators = [
            "ray id", "cloudflare", "checking your browser",
            "ddos protection", "security check", "please wait",
            "cf-browser-verification", "cf-challenge"
        ]

        success_indicators = [
            "crunchyroll", "sign in", "email", "password",
            "home", "anime", "drama"
        ]

        while time.time() - start_time < max_wait_time:
            try:
                current_url = driver.current_url.lower()
                page_source = driver.page_source.lower()
                page_title = driver.title.lower()

                # Check if we're past Cloudflare
                if any(indicator in page_source for indicator in success_indicators):
                    if not any(indicator in page_source for indicator in cloudflare_indicators):
                        logger.info("Cloudflare challenge completed successfully")
                        return True

                # Check for Cloudflare error or block
                if "access denied" in page_source or "blocked" in page_source:
                    logger.error("Access denied by Cloudflare")
                    return False

                # Check for specific Cloudflare elements
                if not CloudflareHandler._check_cloudflare_elements(driver) and "crunchyroll" in page_source:
                    logger.info("Cloudflare challenge appears to be completed")
                    time.sleep(2)  # Give a moment for full page load
                    return True

                # Progressive wait with status updates
                elapsed = time.time() - start_time
                if elapsed % 10 < 1:  # Log every ~10 seconds
                    logger.info(f"Still waiting for Cloudflare... ({elapsed:.0f}s/{max_wait_time}s)")

                time.sleep(1)

            except Exception as e:
                logger.debug(f"Error during Cloudflare wait: {e}")
                time.sleep(2)

        logger.warning(f"Cloudflare wait timeout after {max_wait_time} seconds")
        return False

    @staticmethod
    def _check_cloudflare_elements(driver):
        """Check for Cloudflare challenge elements"""
        try:
            cf_elements = [
                "//div[contains(@class, 'cf-')]",
                "//*[contains(text(), 'Checking your browser')]",
                "//*[contains(text(), 'DDoS protection')]",
                "//div[@id='cf-wrapper']"
            ]

            for xpath in cf_elements:
                elements = driver.find_elements(By.XPATH, xpath)
                if elements:
                    return True

            return False

        except Exception as e:
            logger.debug(f"Error checking Cloudflare elements: {e}")
            return False