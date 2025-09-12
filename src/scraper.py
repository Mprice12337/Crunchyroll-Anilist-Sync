"""Enhanced scraper with FlareSolverr support and API data fetching"""
import time
import random
import json
import requests
from typing import Optional, Dict, Any, List
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.action_chains import ActionChains
from selenium.common.exceptions import TimeoutException, NoSuchElementException
import undetected_chromedriver as uc
from bs4 import BeautifulSoup
import os
from dotenv import load_dotenv
import logging

from auth_cache import AuthCache

logger = logging.getLogger(__name__)

class CrunchyrollScraper:
    def __init__(self, headless: bool = False, flaresolverr_url: Optional[str] = None):
        self.driver = None
        self.flaresolverr_url = flaresolverr_url
        self.session_id = None
        self.auth_token = None
        self.user_id = None
        self.auth_cache = AuthCache()
        
        # Store credentials for re-authentication if needed
        self.crunchyroll_email = None
        self.crunchyroll_password = None
        
        self.setup_driver(headless)

    def setup_driver(self, headless: bool = False):
        """Setup Chrome driver with optional FlareSolverr integration"""
        if self.flaresolverr_url:
            logger.info(f"Using FlareSolverr at {self.flaresolverr_url}")
            return self.setup_flaresolverr(headless)

        logger.info("Using direct Chrome driver")
        return self.setup_undetected_driver(headless)

    def setup_flaresolverr(self, headless: bool = False):
        """Setup FlareSolverr session"""
        try:
            # Create FlareSolverr session
            response = requests.post(f"{self.flaresolverr_url}/v1", json={
                "cmd": "sessions.create"
            })

            if response.status_code == 200:
                self.session_id = response.json().get("session")
                logger.info(f"FlareSolverr session created: {self.session_id}")
                # Still create a fallback driver for form interaction
                self.setup_undetected_driver(headless=headless)
                return True
            else:
                logger.error(f"Failed to create FlareSolverr session: {response.text}")
                # Fallback to direct Chrome driver
                return self.setup_undetected_driver(headless)

        except Exception as e:
            logger.error(f"FlareSolverr setup failed: {e}")
            return self.setup_undetected_driver(headless)

    def setup_undetected_driver(self, headless: bool = False):
        """Setup undetected Chrome driver"""
        options = uc.ChromeOptions()

        # Basic options
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-blink-features=AutomationControlled")

        # Additional stealth options
        options.add_argument("--disable-extensions")
        options.add_argument("--disable-plugins-discovery")
        options.add_argument("--disable-web-security")
        options.add_argument("--disable-features=VizDisplayCompositor")
        options.add_argument("--disable-ipc-flooding-protection")

        if headless:
            options.add_argument("--headless=new")

        # Use undetected-chromedriver
        self.driver = uc.Chrome(options=options, version_main=None)

        # Additional stealth JavaScript
        stealth_js = """
        Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
        Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
        Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en']});
        window.chrome = {runtime: {}};
        Object.defineProperty(navigator, 'permissions', {get: () => ({query: () => Promise.resolve({state: 'granted'})})});
        """
        self.driver.execute_cdp_cmd('Runtime.addBinding', {'name': 'stealth'})
        self.driver.execute_script(stealth_js)

        # Set realistic window size
        self.driver.set_window_size(1920, 1080)
        return True

    def try_cached_auth(self) -> bool:
        """Try to use cached authentication"""
        logger.info("Attempting to use cached authentication...")
        
        cached_auth = self.auth_cache.load_crunchyroll_auth()
        if not cached_auth:
            return False
        
        try:
            # Test if cached auth still works
            if self._test_cached_auth(cached_auth):
                self.auth_token = cached_auth.get('auth_token')
                self.user_id = cached_auth.get('user_id')
                logger.info("Successfully authenticated using cached data")
                return True
            else:
                logger.info("Cached authentication is no longer valid")
                self.auth_cache.clear_crunchyroll_auth()
                return False
                
        except Exception as e:
            logger.error(f"Failed to use cached auth: {e}")
            return False
    
    def _test_cached_auth(self, cached_auth: Dict[str, Any]) -> bool:
        """Test if cached authentication still works"""
        try:
            # Try a simple API call to test auth
            cookies_dict = {cookie['name']: cookie['value'] 
                           for cookie in cached_auth.get('cookies', [])}
            
            headers = {
                'Accept': 'application/json, text/plain, */*',
                'Accept-Language': 'en-US,en;q=0.9',
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36'
            }
            
            if cached_auth.get('auth_token'):
                headers['Authorization'] = f"Bearer {cached_auth['auth_token']}"
            
            # Test with a simple API endpoint
            test_url = "https://www.crunchyroll.com/content/v2/discover/dynamic_home"
            response = requests.get(test_url, headers=headers, cookies=cookies_dict, timeout=10)
            
            if response.status_code == 200:
                return True
            elif response.status_code == 401:
                logger.info("Cached auth returned 401 - authentication expired")
                return False
            else:
                logger.warning(f"Auth test returned {response.status_code}, assuming valid")
                return True
                
        except Exception as e:
            logger.error(f"Auth test failed: {e}")
            return False

    def solve_with_flaresolverr(self, url: str, max_wait: int = 120) -> Optional[requests.Response]:
        """Use FlareSolverr to solve challenges and get page content"""
        if not self.flaresolverr_url or not self.session_id:
            return None

        try:
            response = requests.post(f"{self.flaresolverr_url}/v1", json={
                "cmd": "request.get",
                "url": url,
                "session": self.session_id,
                "maxTimeout": max_wait * 1000
            })

            if response.status_code == 200:
                result = response.json()
                if result.get("status") == "ok":
                    # Extract cookies for future requests
                    cookies = {cookie["name"]: cookie["value"]
                               for cookie in result.get("solution", {}).get("cookies", [])}

                    # Create a requests response-like object
                    class FlareSolverrResponse:
                        def __init__(self, data):
                            self.text = data.get("solution", {}).get("response", "")
                            self.cookies = cookies
                            self.status_code = data.get("solution", {}).get("status", 200)
                            self.url = data.get("solution", {}).get("url", url)

                    return FlareSolverrResponse(result)

            logger.error(f"FlareSolverr request failed: {response.text}")
            return None

        except Exception as e:
            logger.error(f"FlareSolverr request error: {e}")
            return None

    def human_mouse_movement(self, element):
        """Simulate human-like mouse movement to element"""
        if not self.driver:
            return

        actions = ActionChains(self.driver)

        # Get element location
        location = element.location
        size = element.size

        # Random offset within element
        x_offset = random.randint(-size['width']//4, size['width']//4)
        y_offset = random.randint(-size['height']//4, size['height']//4)

        # Move to element with slight randomness
        actions.move_to_element_with_offset(element, x_offset, y_offset)
        actions.pause(random.uniform(0.1, 0.3))
        actions.perform()

    def human_typing(self, element, text: str):
        """Type text with human-like timing"""
        element.clear()
        time.sleep(random.uniform(0.5, 1.0))

        for char in text:
            element.send_keys(char)
            # Random typing speed
            time.sleep(random.uniform(0.05, 0.25))

    def wait_for_cloudflare_advanced(self, max_wait: int = 60) -> bool:
        """Advanced Cloudflare detection and waiting - Fixed to avoid infinite loops"""
        if not self.driver:
            return True  # Assume FlareSolverr handled it

        logger.info("Checking for Cloudflare protection...")

        start_time = time.time()
        last_title_check = ""

        while time.time() - start_time < max_wait:
            try:
                # Check current URL and title
                current_url = self.driver.current_url
                page_title = self.driver.title.lower()

                # Log progress occasionally to show we're not stuck
                elapsed = time.time() - start_time
                if elapsed > 10 and int(elapsed) % 10 == 0 and page_title != last_title_check:
                    logger.info(f"⏳ Still waiting for Cloudflare... ({elapsed:.0f}s elapsed, title: '{page_title}')")
                    last_title_check = page_title

                # Cloudflare indicators
                cf_indicators = [
                    'just a moment',
                    'checking your browser',
                    'ddos protection',
                    'cloudflare',
                    'please wait'
                ]

                # Check if we're on Cloudflare page
                is_cloudflare = any(indicator in page_title for indicator in cf_indicators)

                if is_cloudflare:
                    # Try to find and click checkbox only once per page load
                    try:
                        checkbox = self.driver.find_element(By.CSS_SELECTOR, "input[type='checkbox']")
                        if checkbox.is_displayed() and checkbox.is_enabled():
                            logger.info("Found Cloudflare checkbox, attempting to click...")
                            self.human_mouse_movement(checkbox)
                            time.sleep(random.uniform(0.5, 1.5))
                            checkbox.click()
                            logger.info("Clicked Cloudflare checkbox, waiting for verification...")
                            time.sleep(random.uniform(3, 5))
                    except NoSuchElementException:
                        # No checkbox found, just wait
                        pass

                    # Wait a bit before checking again
                    time.sleep(5)  # Longer wait between checks
                    
                    # Check if we've moved past Cloudflare
                    new_title = self.driver.title.lower()
                    if not any(indicator in new_title for indicator in cf_indicators):
                        logger.info("✅ Cloudflare challenge appears to be completed!")
                        time.sleep(random.uniform(2, 4))
                        return True

                else:
                    logger.info("✅ No Cloudflare protection detected")
                    return True

            except Exception as e:
                logger.error(f"Error during Cloudflare check: {e}")
                # Don't continue looping on errors
                break

        # Timeout reached
        logger.warning(f"⏰ Cloudflare challenge timed out after {max_wait}s")
        
        # Check one more time if we're actually past Cloudflare despite timeout
        try:
            final_title = self.driver.title.lower()
            cf_indicators = ['just a moment', 'checking your browser', 'ddos protection', 'cloudflare']
            if not any(indicator in final_title for indicator in cf_indicators):
                logger.info("✅ Actually, we seem to have passed Cloudflare after all!")
                return True
        except:
            pass
        
        return False

    def login(self, username: str, password: str) -> bool:
        """Login to Crunchyroll with caching and FlareSolverr support"""
        # First try cached authentication
        if self.try_cached_auth():
            return True
        
        logger.info("Cached auth failed, proceeding with fresh login...")
        
        login_url = "https://sso.crunchyroll.com/login"

        # Try FlareSolverr first if available
        if self.flaresolverr_url and self.session_id:
            success = self._login_with_flaresolverr(login_url, username, password)
        else:
            # Fallback to direct Selenium login
            success = self._login_with_selenium(login_url, username, password)
        
        # Cache successful authentication
        if success:
            self._cache_authentication()
        
        return success

    def _cache_authentication(self):
        """Cache current authentication state"""
        try:
            if not self.driver:
                logger.warning("No driver available for caching auth")
                return
            
            # Get cookies from browser
            cookies = self.driver.get_cookies()
            
            # Extract any additional auth info
            self._extract_auth_token()
            self._extract_user_id()
            
            # Cache the authentication data
            self.auth_cache.save_crunchyroll_auth(
                cookies=cookies,
                auth_token=self.auth_token,
                user_id=self.user_id
            )
            
        except Exception as e:
            logger.error(f"Failed to cache authentication: {e}")

    def _login_with_flaresolverr(self, login_url: str, username: str, password: str) -> bool:
        """Login using FlareSolverr for challenge solving"""
        try:
            # Get login page first
            response = self.solve_with_flaresolverr(login_url)
            if not response:
                logger.warning("FlareSolverr failed to get login page, falling back to Selenium")
                return self._login_with_selenium(login_url, username, password)

            # Parse login form from the response
            soup = BeautifulSoup(response.text, 'html.parser')

            # For now, we'll still need Selenium for form interaction
            # FlareSolverr is mainly for challenge solving
            return self._login_with_selenium(login_url, username, password)

        except Exception as e:
            logger.error(f"FlareSolverr login failed: {e}")
            logger.warning("Falling back to direct Selenium login")
            return self._login_with_selenium(login_url, username, password)

    def _login_with_selenium(self, login_url: str, username: str, password: str) -> bool:
        """Direct Selenium login"""
        try:
            logger.info(f"Navigating to: {login_url}")
            self.driver.get(login_url)

            # Wait for Cloudflare
            if not self.wait_for_cloudflare_advanced():
                raise Exception("Failed to pass Cloudflare protection")

            # Wait for page to stabilize
            time.sleep(random.uniform(3, 6))

            # Find login form elements
            username_element = self._find_login_element([
                "input[name='username']",
                "input[id='username']",
                "input[type='email']",
                "input[type='text'][name*='user']",
                "input[type='text'][name*='email']"
            ])

            if not username_element:
                raise Exception("Username field not found")

            password_element = self._find_login_element([
                "input[name='password']",
                "input[id='password']",
                "input[type='password']"
            ])

            if not password_element:
                raise Exception("Password field not found")

            # Human-like interaction
            logger.info("Filling login form...")

            # Fill username
            self.human_mouse_movement(username_element)
            username_element.click()
            time.sleep(random.uniform(0.5, 1.5))
            self.human_typing(username_element, username)
            time.sleep(random.uniform(1, 2))

            # Fill password
            self.human_mouse_movement(password_element)
            password_element.click()
            time.sleep(random.uniform(0.5, 1.5))
            self.human_typing(password_element, password)
            time.sleep(random.uniform(1, 3))

            # Find and click submit button
            submit_button = self._find_login_element([
                "button[type='submit']",
                "input[type='submit']",
                "button[name='submit']",
                ".login-button",
                ".submit-button"
            ])

            if submit_button:
                logger.info("Clicking login button...")
                self.human_mouse_movement(submit_button)
                time.sleep(random.uniform(0.5, 1.5))
                submit_button.click()
            else:
                password_element.submit()

            # Wait for login to process
            time.sleep(random.uniform(3, 7))

            # Check for successful login by looking for auth token or redirect
            if "history" in self.driver.current_url or "dashboard" in self.driver.current_url:
                logger.info("Login successful!")
                return True

            # Additional check - try to extract auth token
            self._extract_auth_token()
            if self.auth_token:
                logger.info("Login appears successful (auth token found)!")
                return True

            # Check if we're still on login page
            if "login" in self.driver.current_url:
                logger.error("Still on login page - login may have failed")
                return False

            logger.info("Login process completed!")
            return True

        except Exception as e:
            logger.error(f"Login failed: {str(e)}")
            return False

    def _find_login_element(self, selectors: List[str]):
        """Find login element using multiple selectors"""
        for selector in selectors:
            try:
                element = self.driver.find_element(By.CSS_SELECTOR, selector)
                if element.is_displayed():
                    return element
            except:
                continue
        return None

    def _extract_auth_token(self):
        """Extract authentication token from browser for API calls"""
        try:
            # Get all cookies
            cookies = self.driver.get_cookies()

            # Look for session cookies or tokens
            for cookie in cookies:
                if 'token' in cookie['name'].lower() or 'session' in cookie['name'].lower():
                    logger.info(f"Found potential auth cookie: {cookie['name']}")

            # Try to extract bearer token from localStorage or network requests
            token_script = """
            return localStorage.getItem('auth_token') || 
                   localStorage.getItem('access_token') || 
                   sessionStorage.getItem('auth_token') ||
                   sessionStorage.getItem('access_token');
            """

            token = self.driver.execute_script(token_script)
            if token:
                self.auth_token = token
                logger.info("Auth token extracted from storage")

        except Exception as e:
            logger.error(f"Failed to extract auth token: {e}")

    def _extract_user_id(self):
        """Extract user ID from browser"""
        try:
            # Try to extract user ID from various sources
            user_id_script = """
            return localStorage.getItem('user_id') || 
                   sessionStorage.getItem('user_id') ||
                   (window.crunchyrollUser && window.crunchyrollUser.id);
            """

            user_id = self.driver.execute_script(user_id_script)
            if user_id:
                self.user_id = str(user_id)
                logger.info(f"User ID extracted: {self.user_id}")

        except Exception as e:
            logger.error(f"Failed to extract user ID: {e}")

    def scrape_history_page(self, max_retries: int = 3) -> Optional[BeautifulSoup]:
        """Scrape the history page directly with retry logic similar to test.py"""
        history_url = "https://www.crunchyroll.com/history"

        for attempt in range(max_retries):
            try:
                logger.info(f"📡 History scraping attempt {attempt + 1}/{max_retries}")

                # Try FlareSolverr first
                if self.flaresolverr_url and self.session_id:
                    logger.info("Using FlareSolverr to get history page...")
                    response = self.solve_with_flaresolverr(history_url)
                    if response and response.text:
                        soup = BeautifulSoup(response.text, 'html.parser')
                        
                        # Verify we got the right page
                        page_title = soup.find('title')
                        if page_title and 'history' in page_title.get_text().lower():
                            logger.info("✅ Got correct history page via FlareSolverr")
                            return soup
                        else:
                            logger.warning(f"⚠️  FlareSolverr returned wrong page: {page_title.get_text() if page_title else 'No title'}")

                # Fallback to direct Selenium (similar to test.py approach)
                if self.driver:
                    logger.info(f"🌐 Navigating to history page: {history_url}")
                    self.driver.get(history_url)

                    # Wait for Cloudflare with shorter timeout (60s instead of 120s)
                    if not self.wait_for_cloudflare_advanced(max_wait=60):
                        if attempt < max_retries - 1:
                            logger.warning("⚠️  Cloudflare challenge failed/timed out, retrying...")
                            time.sleep(random.uniform(10, 20))
                            continue
                        else:
                            logger.error("❌ Failed to pass Cloudflare after all retries")
                            return None

                    # Rest of the method remains the same...
                    logger.info("⏳ Waiting for page to load...")
                    time.sleep(random.uniform(3, 6))

                    current_url = self.driver.current_url
                    page_title = self.driver.title
                    
                    logger.info(f"📍 Current URL: {current_url}")
                    logger.info(f"📝 Page title: {page_title}")

                    # Check if we're redirected to login or homepage
                    if "login" in current_url.lower():
                        logger.error("❌ Redirected to login page - authentication failed")
                        return None
                    
                    # Check if we got the homepage instead of history
                    if "history" not in page_title.lower() and "history" not in current_url.lower():
                        logger.warning(f"⚠️  Wrong page detected. Title: '{page_title}'")
                        
                        if attempt < max_retries - 1:
                            logger.info("🔄 Retrying navigation to history page...")
                            time.sleep(random.uniform(5, 10))
                            continue
                        else:
                            logger.error("❌ Failed to reach history page after all attempts")
                            return None

                    # Wait for dynamic content
                    logger.info("⏳ Waiting for dynamic content...")
                    time.sleep(random.uniform(5, 8))

                    # Get final page source
                    page_source = self.driver.page_source
                    soup = BeautifulSoup(page_source, 'html.parser')
                    
                    # Verify we got the right page
                    title_tag = soup.find('title')
                    if title_tag:
                        title_text = title_tag.get_text().strip()
                        logger.info(f"📋 Final page title: '{title_text}'")
                        
                        if 'history' in title_text.lower():
                            logger.info("✅ Successfully scraped correct history page!")
                            return soup
                        else:
                            logger.warning(f"⚠️  Still wrong page: '{title_text}'")

                    return soup

            except Exception as e:
                logger.error(f"❌ History scraping attempt {attempt + 1} failed: {str(e)}")
                if attempt < max_retries - 1:
                    sleep_time = random.uniform(5, 10)  # Shorter sleep between retries
                    logger.info(f"⏳ Waiting {sleep_time:.1f}s before retry...")
                    time.sleep(sleep_time)

        return None

    def login(self, username: str, password: str) -> bool:
        """Login to Crunchyroll with caching and FlareSolverr support"""
        # Store credentials for potential re-authentication
        self.crunchyroll_email = username
        self.crunchyroll_password = password
        
        # First try cached authentication
        if self.try_cached_auth():
            return True
        
        logger.info("Cached auth failed, proceeding with fresh login...")
        
        login_url = "https://sso.crunchyroll.com/login"

        # Try FlareSolverr first if available
        if self.flaresolverr_url and self.session_id:
            success = self._login_with_flaresolverr(login_url, username, password)
        else:
            # Fallback to direct Selenium login
            success = self._login_with_selenium(login_url, username, password)
        
        # Cache successful authentication
        if success:
            self._cache_authentication()
        
        return success

        if self.flaresolverr_url and self.session_id:
            try:
                requests.post(f"{self.flaresolverr_url}/v1", json={
                    "cmd": "sessions.destroy",
                    "session": self.session_id
                })
                logger.info("FlareSolverr session destroyed")
            except Exception as e:
                logger.error(f"Failed to destroy FlareSolverr session: {e}")