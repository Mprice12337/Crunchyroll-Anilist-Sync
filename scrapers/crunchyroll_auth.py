"""Crunchyroll authentication handling"""
import time
import logging
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from .driver_manager import DriverManager
import requests
from .cloudflare_handler import CloudflareHandler

logger = logging.getLogger(__name__)


class CrunchyrollAuth:
    """Handles Crunchyroll authentication"""

    def __init__(self, email, password, auth_cache):
        self.email = email
        self.password = password
        self.auth_cache = auth_cache
        self.auth_token = None
        self.user_id = None

    def try_cached_auth(self):
        """Try to use cached authentication"""
        logger.info("🔍 Checking for cached authentication...")
        
        cached_auth = self.auth_cache.load_crunchyroll_auth()
        if not cached_auth:
            logger.info("No cached authentication found")
            return False

        logger.info("Found cached authentication, testing validity...")
        
        # Add more detailed logging for debugging
        auth_token = cached_auth.get('auth_token')
        user_id = cached_auth.get('user_id')
        expires_at = cached_auth.get('expires_at')
        
        logger.debug(f"Cached auth token: {auth_token[:20] if auth_token else 'None'}...")
        logger.debug(f"Cached user ID: {user_id}")
        logger.debug(f"Cached expires at: {expires_at}")

        # Try browser-based validation first, then API validation
        if self._test_cached_auth_with_browser(cached_auth):
            self.auth_token = cached_auth.get('auth_token')
            self.user_id = cached_auth.get('user_id')
            logger.info("✅ Cached authentication is valid (browser test)")
            return True
        elif self._test_cached_auth(cached_auth):
            self.auth_token = cached_auth.get('auth_token')
            self.user_id = cached_auth.get('user_id')
            logger.info("✅ Cached authentication is valid (API test)")
            return True
        else:
            logger.info("❌ Cached authentication is invalid, clearing cache")
            self.auth_cache.clear_crunchyroll_auth()
            return False

    def _test_cached_auth_with_browser(self, cached_auth):
        """Test cached auth by setting up browser with cached cookies"""
        try:
            logger.debug("Testing cached auth with browser session...")
            
            # Setup browser if not already done
            if not self.driver:
                self.setup_driver()
            
            # Navigate to a simple Crunchyroll page
            self.driver.get("https://www.crunchyroll.com")
            time.sleep(2)
            
            # Load cached cookies into browser
            cached_cookies = cached_auth.get('cookies', [])
            if cached_cookies:
                logger.debug(f"Loading {len(cached_cookies)} cached cookies")
                
                for cookie in cached_cookies:
                    try:
                        # Clean up cookie data for Selenium
                        cookie_data = {
                            'name': cookie.get('name'),
                            'value': cookie.get('value'),
                            'domain': cookie.get('domain', '.crunchyroll.com'),
                            'path': cookie.get('path', '/'),
                        }
                        
                        # Add optional fields if they exist
                        if cookie.get('secure') is not None:
                            cookie_data['secure'] = cookie.get('secure')
                        if cookie.get('httpOnly') is not None:
                            cookie_data['httpOnly'] = cookie.get('httpOnly')
                        
                        self.driver.add_cookie(cookie_data)
                    except Exception as e:
                        logger.debug(f"Failed to add cookie {cookie.get('name', 'unknown')}: {e}")
                        continue
            
            # Navigate to a page that requires authentication
            self.driver.get("https://www.crunchyroll.com/history")
            time.sleep(3)
            
            # Check if we're logged in by looking for user indicators
            current_url = self.driver.current_url.lower()
            page_source = self.driver.page_source.lower()
            
            # If we're redirected to login, auth failed
            if 'login' in current_url:
                logger.debug("Browser test: redirected to login page")
                return False
            
            # Look for logged-in indicators
            logged_in_indicators = [
                'history',
                'watchlist',
                'account',
                'profile',
                'logout'
            ]
            
            is_logged_in = any(indicator in page_source for indicator in logged_in_indicators)
            
            if is_logged_in:
                logger.debug("Browser test: found logged-in indicators")
                return True
            else:
                logger.debug("Browser test: no logged-in indicators found")
                return False
                
        except Exception as e:
            logger.debug(f"Browser auth test failed: {e}")
            return False

    def _test_cached_auth(self, cached_auth):
        """Test if cached authentication is still valid with API calls"""
        try:
            auth_token = cached_auth.get('auth_token')
            user_id = cached_auth.get('user_id')

            if not auth_token or not user_id:
                logger.debug("Missing auth token or user ID in cache")
                return False

            # Test with a simple request that should work with valid auth
            test_urls = [
                "https://www.crunchyroll.com/content/v2/discover/browse",
                "https://www.crunchyroll.com/content/v2/cms/discover/browse",
                "https://www.crunchyroll.com/content/v2/categories"
            ]
            
            headers = {
                'authorization': f'Bearer {auth_token}',
                'user-agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'accept': 'application/json',
                'accept-language': 'en-US,en;q=0.9'
            }
            
            # Try multiple endpoints to verify auth
            for test_url in test_urls:
                try:
                    logger.debug(f"Testing auth with URL: {test_url}")
                    response = requests.get(test_url, headers=headers, timeout=10)
                    logger.debug(f"Auth test response: {response.status_code}")
                    
                    if response.status_code == 200:
                        logger.debug("✅ API authentication validated successfully")
                        return True
                    elif response.status_code == 401:
                        logger.debug("❌ Auth token is invalid (401 Unauthorized)")
                        return False
                    elif response.status_code == 403:
                        logger.debug("❌ Auth token is forbidden (403)")
                        return False
                    else:
                        logger.debug(f"Auth test returned {response.status_code}, trying next endpoint")
                        continue
                        
                except requests.exceptions.RequestException as e:
                    logger.debug(f"Auth test request failed: {e}")
                    continue
            
            # If all endpoints failed, consider auth invalid for API but might work for browser
            logger.debug("❌ All API auth validation endpoints failed")
            return False

        except Exception as e:
            logger.debug(f"Error testing cached auth: {e}")
            return False

    def login_with_selenium(self, driver):
        """Login using Selenium WebDriver"""
        try:
            if not driver:
                logger.error("No WebDriver provided for Selenium login")
                return False
                
            logger.info("Attempting login with Selenium...")

            # Navigate to login page
            logger.info("Navigating to Crunchyroll login page...")
            driver.get("https://www.crunchyroll.com/login")

            # Wait for Cloudflare if present
            from .cloudflare_handler import CloudflareHandler
            if not CloudflareHandler.wait_for_challenge_completion(driver):
                logger.error("Failed to pass Cloudflare protection")
                return False

            # Find and fill email field
            email_element = self._find_login_element(driver, "email")
            if not email_element:
                return False

            logger.info("Entering email...")
            from .driver_manager import DriverManager
            DriverManager.human_mouse_movement(driver, email_element)
            DriverManager.human_typing(email_element, self.email)

            # Find and fill password field
            password_element = self._find_login_element(driver, "password")
            if not password_element:
                return False

            logger.info("Entering password...")
            DriverManager.human_mouse_movement(driver, password_element)
            DriverManager.human_typing(password_element, self.password)

            # Find and click login button
            login_button = self._find_login_element(driver, "submit")
            if not login_button:
                return False

            logger.info("Clicking login button...")
            DriverManager.human_mouse_movement(driver, login_button)
            login_button.click()

            # Wait for login to complete
            time.sleep(5)

            # Check if login was successful
            if "login" not in driver.current_url.lower():
                logger.info("Login appears successful - redirected away from login page")
                
                # Extract authentication data
                auth_token = self._extract_auth_token(driver)
                user_id = self._extract_user_id(driver)
                
                if auth_token and user_id:
                    self.auth_token = auth_token
                    self.user_id = user_id
                    
                    # Cache the authentication
                    cookies = driver.get_cookies()
                    self._cache_authentication(cookies, auth_token, user_id)
                    
                    logger.info("Authentication successful and cached")
                    return True
                else:
                    logger.warning("Login successful but could not extract auth data")
                    return False
            else:
                logger.error("Login failed - still on login page")
                return False

        except Exception as e:
            logger.error(f"Selenium login failed: {e}")
            return False

    def _find_login_element(self, driver, element_type):
        """Find login form elements with multiple selectors"""
        selectors = {
            "email": [
                "input[type='email']",
                "input[name='email']",
                "#email",
                "input[placeholder*='email']"
            ],
            "password": [
                "input[type='password']",
                "input[name='password']",
                "#password"
            ],
            "submit": [
                "button[type='submit']",
                "input[type='submit']",
                "button[contains(text(), 'Sign In')]",
                ".login-button"
            ]
        }

        for selector in selectors.get(element_type, []):
            try:
                element = WebDriverWait(driver, 5).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                )
                if element.is_displayed():
                    return element
            except:
                continue

        logger.error(f"Could not find {element_type} element")
        return None

    def _extract_auth_token(self, driver):
        """Extract authentication token from cookies or page"""
        try:
            # Try to get from cookies first
            cookies = driver.get_cookies()
            for cookie in cookies:
                if cookie['name'] in ['etp_rt', 'auth_token', 'session_token']:
                    logger.debug(f"Found auth token in cookie: {cookie['name']}")
                    return cookie['value']

            # Try to extract from page source/localStorage
            try:
                auth_token = driver.execute_script(
                    "return localStorage.getItem('auth_token') || "
                    "localStorage.getItem('etp_rt') || "
                    "document.cookie.match(/etp_rt=([^;]+)/) && document.cookie.match(/etp_rt=([^;]+)/)[1]"
                )
                if auth_token:
                    logger.debug("Found auth token in localStorage/cookie")
                    return auth_token
            except Exception as e:
                logger.debug(f"Error extracting from localStorage: {e}")

            logger.warning("Could not extract auth token")
            return None

        except Exception as e:
            logger.error(f"Error extracting auth token: {e}")
            return None

    def _extract_user_id(self, driver):
        """Extract user ID from page URL or content"""
        try:
            # Try to extract from current URL
            current_url = driver.current_url
            if "/user/" in current_url:
                user_id = current_url.split("/user/")[1].split("/")[0]
                if user_id and user_id.isdigit():
                    logger.debug(f"Extracted user ID from URL: {user_id}")
                    return user_id

            # Try to find user profile link or data
            try:
                profile_links = driver.find_elements(By.CSS_SELECTOR, "a[href*='/user/']")
                for link in profile_links:
                    href = link.get_attribute('href')
                    if "/user/" in href:
                        user_id = href.split("/user/")[1].split("/")[0]
                        if user_id and user_id.isdigit():
                            logger.debug(f"Extracted user ID from profile link: {user_id}")
                            return user_id
            except Exception as e:
                logger.debug(f"Error finding profile links: {e}")

            logger.warning("Could not extract user ID")
            return None

        except Exception as e:
            logger.error(f"Error extracting user ID: {e}")
            return None

    def _cache_authentication(self, cookies, auth_token, user_id):
        """Cache authentication data for future use"""
        try:
            success = self.auth_cache.save_crunchyroll_auth(
                cookies=cookies,
                auth_token=auth_token,
                user_id=user_id
            )
            
            if success:
                logger.info("Authentication cached successfully")
            else:
                logger.warning("Failed to cache authentication")
                
        except Exception as e:
            logger.error(f"Error caching authentication: {e}")