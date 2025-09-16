"""Crunchyroll scraper with authentication and history extraction"""

import os
import time
import json
import logging
import random
import requests as re
import undetected_chromedriver as uc
from typing import Dict, List, Optional, Any
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from bs4 import BeautifulSoup

from scrapers.base_scraper import BaseScraper

logger = logging.getLogger(__name__)

class CrunchyrollScraper(BaseScraper):
    """Main Crunchyroll scraper class"""

    def __init__(self, email, password, flaresolverr_url=None, headless=True, dev_mode=False):
        """Initialize the scraper"""
        super().__init__(headless, dev_mode)

        self.driver = None
        self.session_id = None
        self.auth_token = None
        self.user_id = None

        self.crunchyroll_email = email
        self.crunchyroll_password = password
        self.flaresolverr_url = flaresolverr_url

        # Cache manager for authentication
        from cache_manager import CacheManager
        self.auth_cache = CacheManager().auth_cache

        # History tracking
        self.last_watched_log = "_cache/last_watched.json"
        self.last_watched_episodes = self._load_last_watched()

    def setup_driver(self):
        """Setup undetected Chrome driver"""
        try:
            logger.info("Setting up undetected Chrome driver...")

            options = uc.ChromeOptions()

            if self.headless:
                options.add_argument('--headless=new')
                logger.info("Running in headless mode")
            else:
                logger.info("Running with visible browser")

            # Basic options for better detection evasion
            options.add_argument('--no-sandbox')
            options.add_argument('--disable-dev-shm-usage')
            options.add_argument('--disable-blink-features=AutomationControlled')

            # User agent and window size
            options.add_argument(
                '--user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
            options.add_argument('--window-size=1920,1080')

            # Create driver
            self.driver = uc.Chrome(options=options, version_main=None)

            # Execute stealth scripts
            stealth_js = """
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined,
            });
            
            Object.defineProperty(navigator, 'plugins', {
                get: () => [1, 2, 3, 4, 5],
            });
            
            Object.defineProperty(navigator, 'languages', {
                get: () => ['en-US', 'en'],
            });
            """

            self.driver.execute_script(stealth_js)

            logger.info("✅ Undetected Chrome driver setup successful")

        except Exception as e:
            logger.error(f"Failed to setup undetected Chrome driver: {e}")
            raise

    def cleanup(self):
        """Clean up resources"""
        try:
            if self.driver:
                logger.info("Closing WebDriver...")
                self.driver.quit()
                self.driver = None
        except Exception as e:
            logger.error(f"Error during cleanup: {e}")

    def close(self):
        """Alias for cleanup method for backwards compatibility"""
        self.cleanup()

    def try_cached_auth(self):
        """Try to use cached authentication"""
        logger.info("🔍 Checking for cached authentication...")
        
        # The auth_cache.load_crunchyroll_auth() already checks expiration
        cached_auth = self.auth_cache.load_crunchyroll_auth()
        if cached_auth:
            logger.info("✅ Found valid cached authentication")
            
            # Set the cached data
            self.auth_token = cached_auth.get('auth_token')
            self.user_id = cached_auth.get('user_id')
            self.session_id = cached_auth.get('session_id')
            
            # Store cookies for browser session if needed
            self._cached_cookies = cached_auth.get('cookies', [])
            
            # Test the cached authentication with an API call if we have an auth token
            if self.auth_token:
                if self._test_cached_auth():
                    logger.info("✅ Cached authentication test successful")
                    return True
                else:
                    logger.info("⚠️  Cached authentication test failed, will use fresh login")
                    return False
            else:
                # If no auth token, we'll rely on cookies during browser session
                logger.info("✅ Using cached session data (no auth token to test)")
                return True
        else:
            logger.info("No valid cached authentication found")
            return False

    def authenticate(self):
        """Authenticate with Crunchyroll using cached credentials or login"""
        logger.info("🔐 Attempting Crunchyroll login...")
        
        # Try cached authentication first
        if self.try_cached_auth():
            return True
        
        # If cached auth failed, proceed with fresh login
        logger.info("Proceeding with fresh authentication...")
        
        # Try FlareSolverr first if available
        if self.flaresolverr_url:
            try:
                if self._login_with_flaresolverr():
                    return True
            except Exception as e:
                logger.error(f"FlareSolverr login failed: {e}")
                logger.warning("FlareSolverr login failed, falling back to Selenium...")
        
        # Fallback to Selenium
        try:
            return self._login_with_selenium()
        except Exception as e:
            logger.error(f"Selenium login failed: {e}")
            return False
        try:
            element.clear()

            for char in text:
                element.send_keys(char)
                time.sleep(random.uniform(0.05, 0.15))

        except Exception as e:
            logger.error(f"Typing error: {e}")

    def _test_cached_auth_with_browser(self, cached_cookies):
        """Test cached authentication by setting up browser with cached cookies"""
        try:
            logger.debug("Testing cached auth with browser session...")
            
            # Setup browser if not already done
            if not self.driver:
                self.setup_driver()
            
            # Navigate to a simple Crunchyroll page
            self.driver.get("https://www.crunchyroll.com")
            time.sleep(2)
            
            # Load cached cookies into browser
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

    def _test_cached_auth(self):
        """Try to use cached authentication"""
        logger.info("🔍 Checking for cached authentication...")
        
        # The auth_cache.load_crunchyroll_auth() already checks expiration
        cached_auth = self.auth_cache.load_crunchyroll_auth()
        if cached_auth:
            logger.info("✅ Found valid cached authentication")
            
            # Set the cached data
            self.auth_token = cached_auth.get('auth_token')
            self.user_id = cached_auth.get('user_id')
            self.session_id = cached_auth.get('session_id')
            cached_cookies = cached_auth.get('cookies', [])
            
            # Store cookies for browser session if needed
            self._cached_cookies = cached_cookies
            
            # Test the cached authentication
            if self.auth_token and self._test_cached_auth():
                logger.info("✅ Cached authentication test successful")
                return True
            elif cached_cookies and self._test_cached_auth_with_browser(cached_cookies):
                logger.info("✅ Cached session cookies test successful")
                return True
            else:
                logger.info("⚠️  Cached authentication test failed, will use fresh login")
                return False
        else:
            logger.info("No valid cached authentication found")
            return False

    def login(self, email: str, password: str) -> bool:
        """Login to Crunchyroll"""
        try:
            logger.info("🔐 Attempting Crunchyroll login...")

            # Try cached authentication first
            if self.try_cached_auth():
                return True

            # Try FlareSolverr first for Cloudflare bypass
            if self.flaresolverr_url:
                logger.info("Attempting login with FlareSolverr...")
                success = self._login_with_flaresolverr()
                if success:
                    return True
                logger.warning("FlareSolverr login failed, falling back to Selenium...")

            # Fallback to Selenium
            logger.info("Attempting login with Selenium...")
            return self._login_with_selenium()

        except Exception as e:
            logger.error(f"Login failed: {e}")
            return False

    def _login_with_flaresolverr(self) -> bool:
        """Use FlareSolverr for login"""
        try:
            from .flaresolverr_client import FlareSolverrClient

            flaresolverr_client = FlareSolverrClient(self.flaresolverr_url)

            if not flaresolverr_client.create_session():
                logger.error("Failed to create FlareSolverr session")
                return False

            # Get login page
            logger.info("Getting login page via FlareSolverr...")
            login_url = "https://www.crunchyroll.com/login"
            response = flaresolverr_client.solve_challenge(login_url)

            if not response:
                logger.error("Failed to get login page via FlareSolverr")
                return False

            # Extract form data
            html_content = response.get('response', '')
            form_data = self._extract_form_data(html_content)

            if not form_data:
                logger.error("Could not extract form data from login page")
                return False

            # Add credentials
            form_data['email'] = self.crunchyroll_email
            form_data['password'] = self.crunchyroll_password

            # Submit form
            initial_cookies = response.get('cookies', [])
            form_action_url = form_data.pop('action_url', login_url)

            form_response = flaresolverr_client.solve_challenge(
                url=form_action_url,
                cookies=initial_cookies,
                post_data=form_data
            )

            if form_response:
                response_url = form_response.get('url', '')
                if 'login' not in response_url.lower():
                    logger.info("Login appears successful via FlareSolverr")

                    cookies = form_response.get('cookies', [])
                    auth_token = self._extract_auth_token_from_cookies(cookies)
                    user_id = self._extract_user_id_from_html(form_response.get('response', ''))

                    if auth_token:
                        self.auth_token = auth_token
                        self.user_id = user_id or "flaresolverr_user"

                        self._cache_authentication(cookies, auth_token, self.user_id)

                        logger.info("✅ FlareSolverr login successful")
                        return True
                    else:
                        logger.warning("Login successful but no auth token found")
                        return False
                else:
                    logger.error("Login failed - still on login page")
                    return False
            else:
                logger.error("No response from FlareSolverr form submission")
                return False

        except Exception as e:
            logger.error(f"FlareSolverr login failed: {e}")
            return False

    def _login_with_selenium(self):
        """Login using Selenium WebDriver"""
        try:
            logger.info("Attempting login with Selenium...")
            
            # Setup driver
            self.setup_driver()
            
            logger.info("Navigating to Crunchyroll login page...")
            self.driver.get("https://www.crunchyroll.com/login")
            
            # Wait for page to load
            logger.info("Waiting for login page to load...")
            wait = WebDriverWait(self.driver, 20)
            
            # Check if already logged in
            try:
                wait.until(lambda d: d.execute_script("return document.readyState") == "complete")
                
                # Check for login form or if already logged in
                if "login" not in self.driver.current_url and "/login" not in self.driver.current_url:
                    logger.info("Already logged in")
                    # Still try to cache current session
                    self._cache_authentication(self.driver)
                    return True
                    
            except Exception as e:
                logger.debug(f"Page check failed: {e}")
            
            # Wait for login form
            try:
                email_field = wait.until(EC.presence_of_element_located((By.ID, "email")))
                password_field = self.driver.find_element(By.ID, "password")
                
                logger.info("Filling login form...")
                
                # Clear and fill email
                email_field.clear()
                email_field.send_keys(self.crunchyroll_email)
                
                # Wait a bit between fields
                time.sleep(1)
                
                # Clear and fill password  
                password_field.clear()
                password_field.send_keys(self.crunchyroll_password)
                
                # Wait a bit before submitting
                time.sleep(2)
                
                logger.info("Submitting login form...")
                
                # Find and click submit button
                submit_button = self.driver.find_element(By.CSS_SELECTOR, "button[type='submit']")
                submit_button.click()
                
                # Wait for login to complete
                wait.until(lambda d: "login" not in d.current_url)
                
                # Additional wait for page to fully load
                time.sleep(3)
                
                # Verify login success
                if "login" not in self.driver.current_url:
                    logger.info("Login appears successful")
                    
                    # Cache authentication data
                    cache_success = self._cache_authentication(self.driver)
                    if cache_success:
                        logger.info("✅ Authentication successful and cached")
                        return True
                    else:
                        logger.warning("⚠️  Login successful but caching failed")
                        return True
                else:
                    logger.error("Login failed - still on login page")
                    return False
                    
            except TimeoutException:
                logger.error("Login form not found or timed out")
                return False
                
        except Exception as e:
            logger.error(f"Selenium login failed: {e}")
            return False

    def _wait_for_login_page(self, max_wait=60) -> bool:
        """Wait for login page to be ready"""
        start_time = time.time()

        while time.time() - start_time < max_wait:
            try:
                current_url = self.driver.current_url.lower()
                page_source = self.driver.page_source.lower()

                # Check for Cloudflare
                if any(indicator in page_source for indicator in [
                    'checking your browser', 'cloudflare', 'please wait'
                ]):
                    logger.debug("Cloudflare detected, waiting...")
                    time.sleep(3)
                    continue

                # Check for login form
                try:
                    email_field = self.driver.find_element(By.CSS_SELECTOR,
                                                           "input[type='email'], input[name='email']")
                    password_field = self.driver.find_element(By.CSS_SELECTOR,
                                                              "input[type='password'], input[name='password']")

                    if email_field.is_displayed() and password_field.is_displayed():
                        logger.info("✅ Login form is ready")
                        return True

                except:
                    pass

                # Check if already logged in
                if 'login' not in current_url and 'crunchyroll.com' in current_url:
                    logger.info("Already logged in")
                    return True

                time.sleep(2)

            except Exception as e:
                logger.debug(f"Error waiting for page: {e}")
                time.sleep(2)

        logger.warning("Login page wait timeout")
        return False

    def _fill_and_submit_form(self) -> bool:
        """Fill and submit the login form"""
        try:
            # Find email field
            email_element = self._find_element_by_selectors([
                "input[type='email']",
                "input[name='email']",
                "#email"
            ])

            if not email_element:
                logger.error("Email field not found")
                return False

            # Find password field
            password_element = self._find_element_by_selectors([
                "input[type='password']",
                "input[name='password']",
                "#password"
            ])

            if not password_element:
                logger.error("Password field not found")
                return False

            # Fill form
            logger.info("Filling login form...")
            self.human_mouse_movement(email_element)
            self.human_typing(email_element, self.crunchyroll_email)

            time.sleep(1)

            self.human_mouse_movement(password_element)
            self.human_typing(password_element, self.crunchyroll_password)

            time.sleep(1)

            # Find and click submit button
            submit_button = self._find_element_by_selectors([
                "button[type='submit']",
                "input[type='submit']",
                "button:contains('Sign In')",
                ".login-button"
            ])

            if not submit_button:
                logger.error("Submit button not found")
                return False

            logger.info("Submitting login form...")
            self.human_mouse_movement(submit_button)
            submit_button.click()

            # Wait for login to complete
            time.sleep(5)

            # Check if login was successful
            current_url = self.driver.current_url.lower()
            if "login" not in current_url:
                logger.info("Login appears successful")

                # Extract auth data
                auth_token = self._extract_auth_token()
                user_id = self._extract_user_id()

                if auth_token:
                    self.auth_token = auth_token
                    self.user_id = user_id or "selenium_user"

                    cookies = self.driver.get_cookies()
                    self._cache_authentication(cookies, auth_token, self.user_id)

                    logger.info("✅ Authentication successful")
                    return True
                else:
                    logger.warning("Login successful but no auth token found")
                    return False
            else:
                logger.error("Login failed - still on login page")
                return False

        except Exception as e:
            logger.error(f"Error filling/submitting form: {e}")
            return False

    def _find_element_by_selectors(self, selectors: List[str]):
        """Find element using multiple selectors"""
        for selector in selectors:
            try:
                element = WebDriverWait(self.driver, 2).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                )
                if element.is_displayed():
                    return element
            except:
                continue
        return None

    def _extract_form_data(self, html_content: str) -> Dict[str, str]:
        """Extract form data from HTML"""
        try:
            soup = BeautifulSoup(html_content, 'html.parser')
            form = soup.find('form')

            if not form:
                return {}

            action = form.get('action', '/login')
            if action.startswith('/'):
                action_url = f"https://www.crunchyroll.com{action}"
            else:
                action_url = action

            form_data = {'action_url': action_url}

            for hidden_input in form.find_all('input', {'type': 'hidden'}):
                name = hidden_input.get('name')
                value = hidden_input.get('value', '')
                if name:
                    form_data[name] = value

            return form_data

        except Exception as e:
            logger.error(f"Error extracting form data: {e}")
            return {}

    def _extract_auth_token_from_cookies(self, cookies: List[Dict]) -> Optional[str]:
        """Extract auth token from cookies"""
        for cookie in cookies:
            if cookie.get('name') in ['etp_rt', 'auth_token', 'session_token']:
                return cookie.get('value')
        return None

    def _extract_auth_token(self):
        """Extract auth token from browser"""
        try:
            cookies = self.driver.get_cookies()
            for cookie in cookies:
                if cookie['name'] in ['etp_rt', 'auth_token', 'session_token']:
                    return cookie['value']

            # Try localStorage
            try:
                auth_token = self.driver.execute_script(
                    "return localStorage.getItem('auth_token') || localStorage.getItem('etp_rt')"
                )
                if auth_token:
                    return auth_token
            except:
                pass

            return None
        except Exception as e:
            logger.error(f"Error extracting auth token: {e}")
            return None

    def _extract_user_id(self):
        """Extract user ID"""
        try:
            current_url = self.driver.current_url
            if '/user/' in current_url:
                import re
                match = re.search(r'/user/([^/\s"]+)', current_url)
                if match:
                    return match.group(1)

            # Try extracting from page
            try:
                user_id = self.driver.execute_script(
                    "return window.user_id || window.userId || localStorage.getItem('user_id')"
                )
                if user_id:
                    return str(user_id)
            except:
                pass

            return "authenticated_user"
        except Exception as e:
            logger.error(f"Error extracting user ID: {e}")
            return "authenticated_user"

    def _extract_user_id_from_html(self, html_content: str) -> Optional[str]:
        """Extract user ID from HTML"""
        try:
            import re
            patterns = [
                r'"user_id"[:\s]*"([^"]+)"',
                r'"userId"[:\s]*"([^"]+)"',
                r'/user/([^/\s"]+)'
            ]

            for pattern in patterns:
                match = re.search(pattern, html_content)
                if match:
                    return match.group(1)

            return None
        except Exception as e:
            logger.error(f"Error extracting user ID from HTML: {e}")
            return None

    def _cache_authentication(self, driver):
        """Extract and cache authentication data from the browser session"""
        try:
            if not driver:
                logger.error("No driver available for caching authentication")
                return False

            # Get cookies from the current session
            cookies = driver.get_cookies()
            logger.debug(f"Extracted {len(cookies)} cookies from browser session")

            # Try to extract auth token from browser storage or requests
            auth_token = None
            user_id = None

            try:
                # Try to get auth data from local storage
                auth_token = driver.execute_script("return localStorage.getItem('auth_token');")
                user_id = driver.execute_script("return localStorage.getItem('user_id');")

                # If not in localStorage, try sessionStorage
                if not auth_token:
                    auth_token = driver.execute_script("return sessionStorage.getItem('auth_token');")
                if not user_id:
                    user_id = driver.execute_script("return sessionStorage.getItem('user_id');")

                logger.debug(f"Extracted auth_token: {bool(auth_token)}, user_id: {bool(user_id)}")

            except Exception as e:
                logger.debug(f"Could not extract auth data from browser storage: {e}")

            # Cache the authentication data using the correct method
            success = self.auth_cache.save_crunchyroll_auth(
                cookies=cookies,
                auth_token=auth_token,
                user_id=user_id
            )

            if success:
                # Set instance variables
                self.auth_token = auth_token
                self.user_id = user_id
                # Extract session_id from cookies if available
                for cookie in cookies:
                    if cookie['name'] == 'session_id':
                        self.session_id = cookie['value']
                        break

                logger.info("✅ Authentication cached successfully")
                return True
            else:
                logger.error("Failed to cache authentication data")
                return False

        except Exception as e:
            logger.error(f"Error caching authentication: {e}")
            return False

    def _is_valid_cached_auth(self, cached_auth):
        """Check if cached authentication data is complete and valid"""
        if not cached_auth:
            return False
            
        # Since the auth_cache.load_crunchyroll_auth() already checks expiration,
        # we just need to check if we have the required fields
        auth_token = cached_auth.get('auth_token')
        user_id = cached_auth.get('user_id')
        
        # At minimum we need either an auth_token or some session data
        has_auth_token = bool(auth_token)
        has_cookies = bool(cached_auth.get('cookies'))
        
        if not (has_auth_token or has_cookies):
            logger.debug("Cached auth missing both auth_token and cookies")
            return False
        
        logger.debug(f"Cached auth validation - has_auth_token: {has_auth_token}, has_cookies: {has_cookies}")
        return True

    # History methods
    def _load_last_watched(self) -> Dict[str, Any]:
        """Load last watched episodes from cache"""
        try:
            if os.path.exists(self.last_watched_log):
                with open(self.last_watched_log, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception as e:
            logger.error(f"Failed to load last watched episodes: {e}")
        return {}

    def _save_last_watched(self, episodes: List[Dict[str, Any]]):
        """Save last watched episodes to cache"""
        try:
            os.makedirs('_cache', exist_ok=True)
            recent_episodes = {
                'timestamp': time.time(),
                'episodes': episodes[:50]
            }
            with open(self.last_watched_log, 'w', encoding='utf-8') as f:
                json.dump(recent_episodes, f, indent=2, ensure_ascii=False)
            logger.info(f"Saved {len(episodes[:50])} recent episodes to cache")
        except Exception as e:
            logger.error(f"Failed to save last watched episodes: {e}")

    def scrape_history_page(self, use_pagination: bool = True) -> Optional[Any]:
        """Main method to scrape history"""
        try:
            if not self.auth_token:
                logger.error("No authentication token available")
                return None

            if use_pagination:
                episodes = self.scrape_history_with_pagination()
                if episodes:
                    logger.info(f"API pagination returned {len(episodes)} episodes")
                    mock_html = self._create_mock_html_from_episodes(episodes)
                    if mock_html:
                        return BeautifulSoup(mock_html, 'html.parser')
                    else:
                        logger.error("Failed to create mock HTML from episodes")
                        return None
                else:
                    logger.warning("API pagination returned 0 episodes, trying HTML fallback")
                    
            # If API pagination failed or wasn't used, try HTML fallback
            fallback_episodes = self._scrape_html_history_fallback()
            if fallback_episodes:
                logger.info(f"HTML fallback returned {len(fallback_episodes)} episodes")
                mock_html = self._create_mock_html_from_episodes(fallback_episodes)
                if mock_html:
                    return BeautifulSoup(mock_html, 'html.parser')
                else:
                    logger.error("Failed to create mock HTML from fallback episodes")
                    return None
            else:
                logger.error("Both API pagination and HTML fallback failed")
                return None

        except Exception as e:
            logger.error(f"Error scraping history page: {e}")
            return None

    def _create_mock_html_from_episodes(self, episodes: List[Dict[str, Any]]) -> Optional[str]:
        """Create mock HTML structure from episode data for compatibility with existing parsers"""
        try:
            if not episodes:
                logger.warning("No episodes provided to create mock HTML")
                return None

            logger.debug(f"Creating mock HTML from {len(episodes)} episodes")
            logger.debug(f"Sample episode data: {episodes[0] if episodes else 'None'}")

            # Create a simple HTML structure that mimics the expected format
            html_parts = ['<!DOCTYPE html><html><body><div class="history-container">']

            for i, episode in enumerate(episodes):
                series_title = episode.get('series_title', '')
                episode_title = episode.get('episode_title', '')
                episode_number = episode.get('episode_number', '')
                watch_date = episode.get('watch_date', '')

                logger.debug(
                    f"Episode {i + 1}: title='{series_title}', ep_num='{episode_number}', ep_title='{episode_title}'")

                # Create a div structure similar to what the parser expects
                episode_html = f'''
                <div class="history-item" data-testid="history-item">
                    <div class="series-title">{series_title}</div>
                    <div class="episode-info">Episode {episode_number}</div>
                    <div class="episode-title">{episode_title}</div>
                    <div class="watch-date">{watch_date}</div>
                </div>
                '''
                html_parts.append(episode_html)

            html_parts.append('</div></body></html>')

            mock_html = ''.join(html_parts)
            logger.debug(f"Created mock HTML with {len(html_parts) - 2} episodes")

            return mock_html

        except Exception as e:
            logger.error(f"Error creating mock HTML from episodes: {e}")
            return None

    def scrape_history_with_pagination(self, max_pages: int = 50) -> List[Dict[str, Any]]:
        """Scrape history with pagination using browser session"""
        all_episodes = []
        page = 1
        
        logger.info(f"Starting paginated history scraping (max {max_pages} pages)")
        
        # Use the browser session instead of direct API calls
        if not self.driver:
            logger.error("No browser session available for history scraping")
            return []
        
        # First, get the correct API endpoint by visiting the history page
        history_api_url = self._discover_history_api_endpoint()
        if not history_api_url:
            logger.warning("Could not discover history API endpoint, using HTML fallback")
            return self._scrape_html_history_fallback()
        
        while page <= max_pages:
            logger.info(f"Scraping history page {page}")
            
            try:
                # Build the URL with pagination parameters
                params = {
                    'locale': 'en-US',
                    'page_size': '100',
                    'preferred_audio_language': 'ja-JP',
                    'page': str(page)
                }
                
                # Add parameters to the discovered API URL
                separator = '&' if '?' in history_api_url else '?'
                url_params = '&'.join([f"{k}={v}" for k, v in params.items()])
                full_url = f"{history_api_url}{separator}{url_params}"
                
                # Navigate to the API endpoint in the browser to leverage the session
                logger.debug(f"Navigating to: {full_url}")
                self.driver.get(full_url)
                
                # Wait a moment for the page to load
                time.sleep(2)
                
                # Get the page source which should contain the JSON response
                page_source = self.driver.page_source
                
                # Check if we got JSON data
                if page_source.strip().startswith('{') or '<pre>' in page_source.lower():
                    # Extract JSON from the page
                    json_data = self._extract_json_from_page(page_source)
                    
                    if json_data:
                        page_episodes = self._parse_api_response(json_data)
                        
                        if not page_episodes:
                            logger.info(f"No episodes found on page {page}, stopping pagination")
                            break
                            
                        logger.info(f"Found {len(page_episodes)} episodes on page {page}")
                        all_episodes.extend(page_episodes)
                        
                        if len(page_episodes) < int(params['page_size']):
                            logger.info(f"Page {page} returned fewer episodes than page_size, reached end")
                            break
                    else:
                        logger.error(f"Failed to parse JSON from page {page}")
                        break
                else:
                    # We might have been redirected or blocked
                    logger.error(f"Page {page} did not return JSON data")
                    
                    # Try the fallback method
                    if page == 1:
                        logger.info("Falling back to HTML history page scraping")
                        return self._scrape_html_history_fallback()
                    else:
                        break
                
            except Exception as e:
                logger.error(f"Error fetching page {page}: {e}")
                
                # For the first page, try fallback method
                if page == 1:
                    logger.info("Falling back to HTML history page scraping")
                    return self._scrape_html_history_fallback()
                else:
                    break
                
            page += 1
            time.sleep(2)  # Be respectful
        
        logger.info(f"Completed pagination scraping: {len(all_episodes)} total episodes")
        
        if all_episodes:
            self._save_last_watched(all_episodes)
        
        return all_episodes

    def _discover_history_api_endpoint(self) -> Optional[str]:
        """Discover the correct history API endpoint from the browser session"""
        try:
            logger.info("Discovering history API endpoint...")
            
            # Navigate to the regular history page first
            self.driver.get("https://www.crunchyroll.com/history")
            time.sleep(3)
            
            # Check if we need to handle Cloudflare
            page_source = self.driver.page_source.lower()
            if any(indicator in page_source for indicator in [
                'checking your browser', 'cloudflare', 'please wait'
            ]):
                logger.warning("Encountered Cloudflare on history page, waiting...")
                time.sleep(10)
            
            # Method 1: Look for API endpoints in the page source
            page_source = self.driver.page_source
            api_url = self._extract_api_url_from_page(page_source)
            if api_url:
                logger.info(f"Found API endpoint in page source: {api_url}")
                return api_url
            
            # Method 2: Use browser developer tools to intercept network requests
            api_url = self._capture_api_endpoint_from_network()
            if api_url:
                logger.info(f"Captured API endpoint from network: {api_url}")
                return api_url
            
            # Method 3: Try to construct the URL from user information
            api_url = self._construct_api_url_from_user_data()
            if api_url:
                logger.info(f"Constructed API endpoint from user data: {api_url}")
                return api_url
            
            logger.warning("Could not discover history API endpoint")
            return None
            
        except Exception as e:
            logger.error(f"Error discovering history API endpoint: {e}")
            return None

    def _extract_api_url_from_page(self, page_source: str) -> Optional[str]:
        """Extract API URL from page source"""
        try:
            import re
            
            # Look for API endpoints in JavaScript
            patterns = [
                r'["\']https://www\.crunchyroll\.com/content/v2/([^"\']+)/watch-history["\']',
                r'["\']https://www\.crunchyroll\.com/content/([^"\']+)/watch-history["\']',
                r'watchHistoryUrl["\']?\s*[:=]\s*["\']([^"\']+)["\']',
                r'api["\']?\s*[:=]\s*["\']([^"\']*watch-history[^"\']*)["\']',
                r'endpoint["\']?\s*[:=]\s*["\']([^"\']*watch-history[^"\']*)["\']'
            ]
            
            for pattern in patterns:
                matches = re.findall(pattern, page_source)
                for match in matches:
                    # If it's a full URL, return it
                    if match.startswith('http'):
                        return match
                    # If it's a path, construct the full URL
                    elif match.startswith('/'):
                        return f"https://www.crunchyroll.com{match}"
                    # If it's just an ID, construct the URL
                    else:
                        return f"https://www.crunchyroll.com/content/v2/{match}/watch-history"
            
            return None
            
        except Exception as e:
            logger.error(f"Error extracting API URL from page: {e}")
            return None

    def _capture_api_endpoint_from_network(self) -> Optional[str]:
        """Capture API endpoint by monitoring network requests"""
        try:
            # Enable performance logging to capture network requests
            from selenium.webdriver.common.desired_capabilities import DesiredCapabilities
            
            # Get the browser logs (this might contain network requests)
            try:
                logs = self.driver.get_log('performance')
                for log in logs:
                    message = json.loads(log['message'])
                    if message.get('method') == 'Network.responseReceived':
                        url = message.get('params', {}).get('response', {}).get('url', '')
                        if 'watch-history' in url:
                            logger.info(f"Found API endpoint in network logs: {url}")
                            # Remove query parameters to get base URL
                            base_url = url.split('?')[0]
                            return base_url
            except Exception as e:
                logger.debug(f"Could not get performance logs: {e}")
            
            # Alternative: Trigger a small scroll or interaction to generate network requests
            try:
                self.driver.execute_script("window.scrollTo(0, 100);")
                time.sleep(2)
                
                # Check for any XHR requests that might have been made
                xhr_urls = self.driver.execute_script("""
                    return Array.from(performance.getEntriesByType('resource'))
                        .filter(entry => entry.name.includes('watch-history'))
                        .map(entry => entry.name);
                """)
                
                if xhr_urls:
                    for url in xhr_urls:
                        if 'watch-history' in url:
                            base_url = url.split('?')[0]
                            logger.info(f"Found API endpoint from performance entries: {base_url}")
                            return base_url
                            
            except Exception as e:
                logger.debug(f"Could not capture network requests: {e}")
            
            return None
            
        except Exception as e:
            logger.error(f"Error capturing API endpoint from network: {e}")
            return None

    def _construct_api_url_from_user_data(self) -> Optional[str]:
        """Construct API URL using user ID or other session data"""
        try:
            # Try to get user ID from various sources
            user_identifier = None
            
            # Method 1: Try to get from our stored user_id
            if self.user_id and self.user_id != "authenticated_user":
                user_identifier = self.user_id
                logger.debug(f"Using stored user ID: {user_identifier}")
            
            # Method 2: Try to extract from current URL or page
            if not user_identifier:
                current_url = self.driver.current_url
                import re
                
                # Look for user ID patterns in URL
                id_patterns = [
                    r'/user/([^/\s"]+)',
                    r'userId[=:]([^&\s"]+)',
                    r'user_id[=:]([^&\s"]+)'
                ]
                
                for pattern in id_patterns:
                    match = re.search(pattern, current_url)
                    if match:
                        user_identifier = match.group(1)
                        logger.debug(f"Extracted user ID from URL: {user_identifier}")
                        break
            
            # Method 3: Try to get from localStorage or sessionStorage
            if not user_identifier:
                try:
                    user_identifier = self.driver.execute_script("""
                        return localStorage.getItem('user_id') || 
                               localStorage.getItem('userId') ||
                               sessionStorage.getItem('user_id') ||
                               sessionStorage.getItem('userId');
                    """)
                    if user_identifier:
                        logger.debug(f"Found user ID in storage: {user_identifier}")
                except:
                    pass
            
            # Method 4: Try to get from page source
            if not user_identifier:
                page_source = self.driver.page_source
                patterns = [
                    r'"user_id"[:\s]*"([^"]+)"',
                    r'"userId"[:\s]*"([^"]+)"',
                    r'data-user-id="([^"]+)"'
                ]
                
                for pattern in patterns:
                    match = re.search(pattern, page_source)
                    if match:
                        user_identifier = match.group(1)
                        logger.debug(f"Found user ID in page source: {user_identifier}")
                        break
            
            if user_identifier:
                # Construct the API URL using the user identifier
                api_url = f"https://www.crunchyroll.com/content/v2/{user_identifier}/watch-history"
                logger.info(f"Constructed API URL: {api_url}")
                return api_url
            else:
                logger.warning("Could not find user identifier to construct API URL")
                return None
                
        except Exception as e:
            logger.error(f"Error constructing API URL from user data: {e}")
            return None

    def _extract_json_from_page(self, page_source: str) -> Optional[Dict]:
        """Extract JSON data from page source"""
        try:
            import re
            
            # If the page is wrapped in <pre> tags (common for JSON responses)
            if '<pre>' in page_source.lower():
                # Extract content between <pre> tags
                match = re.search(r'<pre[^>]*>(.*?)</pre>', page_source, re.DOTALL | re.IGNORECASE)
                if match:
                    json_text = match.group(1).strip()
                    # Decode HTML entities
                    import html
                    json_text = html.unescape(json_text)
                    return json.loads(json_text)
            
            # If the entire page is JSON (starts with { or [)
            clean_source = page_source.strip()
            if clean_source.startswith('{') or clean_source.startswith('['):
                return json.loads(clean_source)
            
            # Try to find JSON in script tags or other containers
            json_patterns = [
                r'<script[^>]*>.*?(\{.*?"data".*?\}).*?</script>',
                r'window\.__INITIAL_STATE__\s*=\s*(\{.*?\});',
                r'(\{.*?"data".*?\})',
            ]
            
            for pattern in json_patterns:
                matches = re.findall(pattern, page_source, re.DOTALL)
                for match in matches:
                    try:
                        return json.loads(match)
                    except:
                        continue
            
            return None
            
        except Exception as e:
            logger.error(f"Error extracting JSON from page: {e}")
            return None

    def _scrape_html_history_fallback(self):
        """Fallback method to scrape history from HTML when API fails"""
        try:
            logger.info("Using HTML history page as fallback")

            # Setup driver if not already done
            if not self.driver:
                self.setup_driver()

            # Navigate to history page
            self.driver.get("https://www.crunchyroll.com/history")
            time.sleep(5)

            # Scroll to load more content
            logger.info("Scrolling to load more history content...")
            last_height = self.driver.execute_script("return document.body.scrollHeight")
            scroll_attempts = 0
            max_scrolls = 10  # Limit scrolling to prevent infinite loops

            while scroll_attempts < max_scrolls:
                # Scroll down to bottom
                self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(2)

                # Calculate new scroll height and compare to last height
                new_height = self.driver.execute_script("return document.body.scrollHeight")
                if new_height == last_height:
                    break

                last_height = new_height
                scroll_attempts += 1

            # Get page source and extract episodes
            page_source = self.driver.page_source
            soup = BeautifulSoup(page_source, 'html.parser')

            # Extract episodes from the HTML
            episodes = []

            # Look for history items with various selectors
            history_selectors = [
                '[data-testid*="history"]',
                '.history-item',
                '.watch-history-item',
                '.episode-card',
                '.content-card'
            ]

            history_items = []
            for selector in history_selectors:
                items = soup.select(selector)
                if items:
                    history_items.extend(items)
                    break
            
            # If no specific history items found, look for any episode-like elements
            if not history_items:
                # Look for elements that might contain episode information
                potential_items = soup.find_all(['div', 'article'])
                for item in potential_items:
                    # Check if the element has classes that suggest it's a content card
                    class_names = item.get('class', [])
                    class_string = ' '.join(class_names).lower()
                    
                    if any(keyword in class_string for keyword in ['card', 'item', 'episode', 'content', 'media']):
                        history_items.append(item)
            
            logger.debug(f"Found {len(history_items)} potential history items")
            
            for item in history_items:
                episode_data = self._extract_episode_from_html(item)
                if episode_data and episode_data.get('series_title'):
                    episodes.append(episode_data)
            
            logger.info(f"Extracted {len(episodes)} episodes from HTML fallback")
            return episodes
            
        except Exception as e:
            logger.error(f"HTML fallback scraping failed: {e}")
            return []

    def _parse_html_history(self, html_content: str) -> List[Dict[str, Any]]:
        """Parse episode data from HTML history page"""
        episodes = []
        
        try:
            soup = BeautifulSoup(html_content, 'html.parser')
            
            # Look for common history item patterns
            history_selectors = [
                '.history-item',
                '.watchlist-item',
                '.card',
                '[data-testid*="history"]',
                '.grid-item',
                '.content-card',
                '.episode-card'
            ]
            
            history_items = []
            for selector in history_selectors:
                items = soup.select(selector)
                if items:
                    history_items = items
                    logger.debug(f"Found {len(items)} items with selector: {selector}")
                    break
            
            if not history_items:
                # Try to find any containers with episode-like content
                history_items = soup.find_all(['div', 'article'], class_=lambda x: x and any(
                    keyword in x.lower() for keyword in ['episode', 'watch', 'history', 'card']
                ))
                logger.debug(f"Found {len(history_items)} items with fallback search")
            
            for item in history_items[:100]:  # Limit to first 100 items
                try:
                    episode_data = self._extract_episode_from_html(item)
                    if episode_data and episode_data.get('series_title'):
                        episodes.append(episode_data)
                except Exception as e:
                    logger.debug(f"Error extracting episode data: {e}")
                    continue
            
        except Exception as e:
            logger.error(f"Error parsing HTML history: {e}")
        
        return episodes

    def _extract_episode_from_html(self, item) -> Optional[Dict[str, Any]]:
        """Extract episode data from HTML element"""
        try:
            # Try to find series title
            series_title = ""
            title_selectors = [
                '.series-title', '.show-title', '.title', 'h2', 'h3', 'h4',
                '[data-testid*="title"]', '.series-name', '.content-title'
            ]
            
            for selector in title_selectors:
                title_elem = item.select_one(selector)
                if title_elem and title_elem.get_text(strip=True):
                    series_title = title_elem.get_text(strip=True)
                    break
            
            # If no title found with selectors, try all text content
            if not series_title:
                all_text = item.get_text(strip=True)
                lines = [line.strip() for line in all_text.split('\n') if line.strip()]
                if lines:
                    # First meaningful line is likely the title
                    series_title = lines[0]
            
            # Try to find episode info
            episode_info = ""
            episode_selectors = [
                '.episode-title', '.episode-info', '.subtitle', 
                '[data-testid*="episode"]', '.episode-number'
            ]
            
            for selector in episode_selectors:
                ep_elem = item.select_one(selector)
                if ep_elem and ep_elem.get_text(strip=True):
                    episode_info = ep_elem.get_text(strip=True)
                    break
            
            # Extract episode number
            episode_number = None
            if episode_info:
                import re
                ep_match = re.search(r'episode\s*(\d+)', episode_info.lower())
                if ep_match:
                    episode_number = int(ep_match.group(1))
                else:
                    # Try to find any number in the episode info
                    num_match = re.search(r'(\d+)', episode_info)
                    if num_match:
                        episode_number = int(num_match.group(1))
            
            # Try to find date
            watch_date = ""
            date_selectors = [
                '.date', '.watch-date', '.timestamp', 
                '[data-testid*="date"]', 'time'
            ]
            
            for selector in date_selectors:
                date_elem = item.select_one(selector)
                if date_elem and date_elem.get_text(strip=True):
                    watch_date = date_elem.get_text(strip=True)
                    break
            
            # Find links
            series_url = ""
            episode_url = ""
            
            links = item.find_all('a', href=True)
            for link in links:
                href = link['href']
                if '/series/' in href:
                    series_url = href if href.startswith('http') else f"https://www.crunchyroll.com{href}"
                elif '/watch/' in href:
                    episode_url = href if href.startswith('http') else f"https://www.crunchyroll.com{href}"
            
            if series_title:
                return {
                    'series_title': series_title,
                    'episode_title': episode_info,
                    'episode_number': episode_number,
                    'watch_date': watch_date,
                    'series_url': series_url,
                    'episode_url': episode_url
                }
            
            return None
            
        except Exception as e:
            logger.debug(f"Error extracting episode from HTML: {e}")
            return None

    def _save_debug_file(self, content, filename):
        """Save debug content to file"""
        try:
            import os
            os.makedirs('_cache', exist_ok=True)
            filepath = os.path.join('_cache', filename)
            
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(content)
            
            logger.info(f"Debug file saved: {filepath}")
            
        except Exception as e:
            logger.error(f"Failed to save debug file: {e}")

    def _parse_api_response(self, data: Dict) -> List[Dict[str, Any]]:
        """Parse API response to extract episode data"""
        episodes = []
        
        try:
            logger.debug(f"Parsing API response with keys: {list(data.keys())}")
            
            # Try different possible data structures
            items = []
            
            # Format 1: data.data (most common)
            if 'data' in data and isinstance(data['data'], list):
                items = data['data']
                logger.debug(f"Found {len(items)} items in data.data")
            
            # Format 2: data.items
            elif 'items' in data and isinstance(data['items'], list):
                items = data['items']
                logger.debug(f"Found {len(items)} items in data.items")
            
            # Format 3: direct list
            elif isinstance(data, list):
                items = data
                logger.debug(f"Found {len(items)} items in direct list")
            
            # Format 4: data.results
            elif 'results' in data and isinstance(data['results'], list):
                items = data['results']
                logger.debug(f"Found {len(items)} items in data.results")
            
            else:
                logger.warning(f"Unrecognized API response format: {list(data.keys())}")
                return []
            
            for i, item in enumerate(items):
                try:
                    episode = self._extract_episode_from_api_item(item)
                    if episode and episode.get('series_title'):
                        episodes.append(episode)
                        logger.debug(f"Extracted episode: {episode.get('series_title')} - {episode.get('episode_number')}")
                    else:
                        logger.debug(f"Skipped item {i}: {list(item.keys()) if isinstance(item, dict) else type(item)}")
                except Exception as e:
                    logger.debug(f"Error extracting episode from item {i}: {e}")
                    continue
                    
        except Exception as e:
            logger.error(f"Error parsing API response: {e}")
            
        logger.info(f"Parsed {len(episodes)} episodes from API response")
        return episodes

    def parse_history_html(self, html_content):
        """Parse Crunchyroll history page HTML and extract viewing history"""
        try:
            if isinstance(html_content, str):
                soup = BeautifulSoup(html_content, 'html.parser')
            else:
                soup = html_content

            # Check if this is our mock HTML structure
            if soup.select('.history-container .history-item'):
                logger.debug("Detected mock HTML structure, using specialized parser")
                return self._parse_mock_history_structure(soup)

            # ... existing code for regular HTML parsing ...
        except Exception as e:
            logger.error(f"Failed to parse history HTML: {e}")
            return []

    def _parse_mock_history_structure(self, soup):
        """Parse the mock HTML structure created by the scraper"""
        history_items = []

        try:
            # Find all history items in our mock structure
            mock_items = soup.select('.history-container .history-item')
            logger.debug(f"Found {len(mock_items)} items in mock structure")

            if not mock_items:
                logger.warning("No .history-item elements found in mock structure")
                # Debug: check what's actually in the HTML
                container = soup.select_one('.history-container')
                if container:
                    logger.debug(
                        f"Container found, children: {[child.name for child in container.children if child.name]}")
                    logger.debug(f"Container HTML sample: {str(container)[:500]}...")
                else:
                    logger.warning("No .history-container found")
                return []

            for i, item in enumerate(mock_items):
                try:
                    # Extract data from our known mock structure
                    series_title_elem = item.select_one('.series-title')
                    episode_info_elem = item.select_one('.episode-info')
                    episode_title_elem = item.select_one('.episode-title')
                    watch_date_elem = item.select_one('.watch-date')

                    series_title = series_title_elem.get_text(strip=True) if series_title_elem else ""
                    episode_info = episode_info_elem.get_text(strip=True) if episode_info_elem else ""
                    episode_title = episode_title_elem.get_text(strip=True) if episode_title_elem else ""
                    watch_date = watch_date_elem.get_text(strip=True) if watch_date_elem else ""

                    logger.debug(
                        f"Mock item {i + 1}: series='{series_title}', info='{episode_info}', title='{episode_title}'")

                    # Extract episode number from episode info
                    episode_number = None
                    if episode_info:
                        ep_match = self.episode_pattern.search(episode_info)
                        if ep_match:
                            episode_number = int(ep_match.group(1))
                        else:
                            logger.debug(f"Could not extract episode number from: '{episode_info}'")

                    if series_title and episode_number:
                        history_item = {
                            'series_title': series_title,
                            'episode_title': episode_title,
                            'episode_number': episode_number,
                            'watch_date': watch_date,
                            'season': 1  # Default season
                        }

                        history_items.append(history_item)
                        logger.debug(f"Successfully parsed mock item: {series_title} Episode {episode_number}")
                    else:
                        logger.debug(
                            f"Skipping mock item {i + 1}: missing series_title='{series_title}' or episode_number={episode_number}")

                except Exception as e:
                    logger.debug(f"Error parsing mock history item {i + 1}: {e}")
                    continue

            logger.info(f"Successfully parsed {len(history_items)} items from mock structure")
            return {
                'items': history_items,
                'total_count': len(history_items)
            }

        except Exception as e:
            logger.error(f"Error parsing mock history structure: {e}")
            return []

    def _extract_episode_from_api_item(self, item: Dict) -> Optional[Dict[str, Any]]:
        """Extract episode data from a single API item"""
        try:
            # Try different possible structures
            episode_data = {}
            
            # Method 1: Original structure (panel.episode_metadata)
            panel = item.get('panel', {})
            if panel:
                episode_metadata = panel.get('episode_metadata', {})
                series_metadata = episode_metadata.get('series_metadata', {})
                
                if series_metadata.get('title'):
                    episode_data = {
                        'series_title': series_metadata.get('title', ''),
                        'episode_title': episode_metadata.get('title', ''),
                        'episode_number': episode_metadata.get('episode_number'),
                        'watch_date': item.get('date_played', ''),
                        'series_url': series_metadata.get('series_launch_page_url', ''),
                        'episode_url': panel.get('link', '')
                    }
            
            # Method 2: Direct episode structure
            if not episode_data.get('series_title') and item.get('title'):
                episode_data = {
                    'series_title': item.get('series_title', item.get('show_title', '')),
                    'episode_title': item.get('title', ''),
                    'episode_number': item.get('episode_number', item.get('episode')),
                    'watch_date': item.get('date_played', item.get('watch_date', '')),
                    'series_url': item.get('series_url', ''),
                    'episode_url': item.get('episode_url', item.get('url', ''))
                }
            
            # Method 3: Media structure
            if not episode_data.get('series_title'):
                media = item.get('media', {})
                if media:
                    episode_data = {
                        'series_title': media.get('series_title', media.get('title', '')),
                        'episode_title': media.get('episode_title', ''),
                        'episode_number': media.get('episode_number'),
                        'watch_date': item.get('date_played', ''),
                        'series_url': media.get('series_url', ''),
                        'episode_url': media.get('url', '')
                    }
            
            # Validate that we have minimum required data
            if episode_data.get('series_title') and episode_data.get('episode_number') is not None:
                return episode_data
            else:
                logger.debug(f"Episode missing required data: {episode_data}")
                return None
                
        except Exception as e:
            logger.debug(f"Error extracting episode from API item: {e}")
            return None