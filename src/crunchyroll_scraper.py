"""
Clean Crunchyroll scraper focused on API-based history fetching
"""

import re
import time
import logging
import uuid
from typing import List, Dict, Any, Optional
from pathlib import Path

import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from bs4 import BeautifulSoup

from cache_manager import AuthCache
from flaresolvrrr_client import FlareSolverrClient

logger = logging.getLogger(__name__)


class CrunchyrollScraper:
    """Clean Crunchyroll scraper using API-based history fetching"""

    def __init__(self, email: str, password: str, headless: bool = True,
                 flaresolverr_url: Optional[str] = None):
        self.email = email
        self.password = password
        self.headless = headless
        self.flaresolverr_url = flaresolverr_url
        self.driver = None
        self.auth_cache = AuthCache()
        self.is_authenticated = False
        self.access_token = None

    def authenticate(self) -> bool:
        """Authenticate with Crunchyroll using cached or fresh credentials"""
        logger.info("🔐 Authenticating with Crunchyroll...")

        # Initialize instance variables
        self.access_token = None
        self.cached_account_id = None
        self.cached_device_id = None

        self._setup_driver()

        # Try cached authentication first
        if self._try_cached_auth() and self._verify_authentication():
            logger.info("✅ Using cached authentication")
            self.is_authenticated = True
            return True
        else:
            # Clear invalid cache
            self.auth_cache.clear_crunchyroll_auth()

        # Fresh authentication
        logger.info("Performing fresh authentication...")

        if self._perform_fresh_authentication():
            self.is_authenticated = True
            return True

        logger.error("❌ All authentication methods failed")
        return False

    def _verify_cached_token(self) -> bool:
        """Verify that cached access token is still valid"""
        try:
            if not self.access_token or not self.cached_account_id:
                return False

            # Make a simple API call to verify token validity
            test_response = self.driver.execute_script("""
                const accessToken = arguments[0];
                const accountId = arguments[1];

                return fetch(`https://www.crunchyroll.com/content/v2/${accountId}/watch-history?page_size=1&locale=en-US`, {
                    method: 'GET',
                    headers: {
                        'Accept': 'application/json',
                        'Authorization': `Bearer ${accessToken}`,
                        'sec-fetch-dest': 'empty',
                        'sec-fetch-mode': 'cors',
                        'sec-fetch-site': 'same-origin'
                    },
                    credentials: 'include',
                    mode: 'cors'
                })
                .then(response => ({
                    success: response.ok,
                    status: response.status
                }))
                .catch(error => ({
                    success: false,
                    error: error.message
                }));
            """, self.access_token, self.cached_account_id)

            if test_response and test_response.get('success'):
                logger.debug("✅ Cached token is valid")
                return True
            else:
                logger.debug(f"❌ Cached token invalid: {test_response}")
                return False

        except Exception as e:
            logger.debug(f"Error verifying cached token: {e}")
            return False

    def get_watch_history(self, max_pages: int = 10) -> List[Dict[str, Any]]:
        """Get watch history using Crunchyroll API"""
        logger.info(f"📚 Fetching watch history via API (max {max_pages} pages)...")

        if not self.is_authenticated:
            logger.error("Not authenticated! Call authenticate() first.")
            return []

        # Ensure we're on Crunchyroll to maintain session context
        self.driver.get("https://www.crunchyroll.com")
        time.sleep(2)

        # Get account ID for API calls
        account_id = self._get_account_id()
        if not account_id:
            logger.error("Could not get account ID from token endpoint")
            return []

        # Fetch history via browser-based API calls
        return self._fetch_history_via_browser_api(account_id, max_pages)

    def _get_or_create_device_id(self) -> str:
        """Get existing device_id from cache/browser or create a consistent one"""
        try:
            # First, try cached device_id
            if hasattr(self, 'cached_device_id') and self.cached_device_id:
                logger.debug(f"Using cached device_id: {self.cached_device_id[:8]}...")
                return self.cached_device_id

            # Try to get from browser storage
            device_id = self._get_device_id()
            if device_id:
                logger.debug(f"Found device_id in browser: {device_id[:8]}...")
                return device_id

            # Create a consistent device_id based on user email (so it's the same across runs)
            import hashlib
            email_hash = hashlib.md5(self.email.encode()).hexdigest()
            # Format as UUID
            device_id = f"{email_hash[:8]}-{email_hash[8:12]}-{email_hash[12:16]}-{email_hash[16:20]}-{email_hash[20:32]}"

            logger.debug(f"Generated consistent device_id: {device_id[:8]}...")

            # Store it in localStorage for future use
            self.driver.execute_script(f"localStorage.setItem('cr_device_id', '{device_id}');")

            return device_id

        except Exception as e:
            logger.debug(f"Error getting/creating device_id: {e}")
            # Fallback to random UUID
            return str(uuid.uuid4())

    def cleanup(self) -> None:
        """Clean up browser resources"""
        if self.driver:
            try:
                self.driver.quit()
                self.driver = None
                logger.debug("Browser closed")
            except Exception as e:
                logger.error(f"Error closing browser: {e}")

    # ==================== AUTHENTICATION METHODS ====================

    def _setup_driver(self) -> None:
        """Initialize Chrome driver with appropriate options"""
        try:
            options = uc.ChromeOptions()

            if self.headless:
                options.add_argument('--headless=new')
                logger.info("Running in headless mode")
            else:
                logger.info("Running with visible browser")

            # Essential Chrome options
            options.add_argument('--no-sandbox')
            options.add_argument('--disable-dev-shm-usage')
            options.add_argument('--disable-blink-features=AutomationControlled')
            options.add_argument('--window-size=1920,1080')
            options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')

            self.driver = uc.Chrome(options=options)
            self.driver.execute_script(
                "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
            )

            logger.info("✅ Chrome driver setup completed")

        except Exception as e:
            logger.error(f"Failed to setup Chrome driver: {e}")
            raise

    def _try_cached_auth(self) -> bool:
        """Load and apply cached authentication cookies and tokens"""
        cached_auth = self.auth_cache.load_crunchyroll_auth()
        if not cached_auth:
            return False

        logger.info("Testing cached authentication...")

        try:
            self.driver.get("https://www.crunchyroll.com")
            time.sleep(2)

            cookies = cached_auth.get('cookies', [])
            logger.info(f"Loading {len(cookies)} cached cookies...")

            for cookie in cookies:
                try:
                    cookie_data = {
                        'name': cookie.get('name'),
                        'value': cookie.get('value'),
                        'domain': cookie.get('domain', '.crunchyroll.com'),
                        'path': cookie.get('path', '/'),
                    }

                    # Add optional fields if present
                    for field in ['secure', 'httpOnly']:
                        if cookie.get(field) is not None:
                            cookie_data[field] = cookie.get(field)

                    self.driver.add_cookie(cookie_data)

                except Exception as e:
                    logger.debug(f"Failed to add cookie {cookie.get('name')}: {e}")
                    continue

            # Load cached access_token and device_id if available
            self.access_token = cached_auth.get('access_token')
            self.cached_account_id = cached_auth.get('account_id')
            self.cached_device_id = cached_auth.get('device_id')

            if self.access_token and self.cached_account_id:
                logger.info("✅ Cached access token and account ID loaded")
            else:
                logger.debug("No cached access token/account ID found")

            logger.info("✅ Cached cookies loaded successfully")
            return True

        except Exception as e:
            logger.error(f"Error loading cached auth: {e}")
            return False

    def _verify_authentication(self) -> bool:
        """Verify that authentication is working by checking account page"""
        try:
            logger.info("🔍 Verifying authentication...")

            self.driver.get("https://www.crunchyroll.com/account")
            time.sleep(3)

            # Check if redirected to login
            if "login" in self.driver.current_url.lower():
                logger.info("❌ Redirected to login page - not authenticated")
                return False

            # Look for logged-in indicators
            page_source = self.driver.page_source.lower()
            logged_in_indicators = [
                "account", "profile", "subscription", "settings",
                "logout", "sign out", "premium"
            ]

            indicators_found = [indicator for indicator in logged_in_indicators
                              if indicator in page_source]

            if indicators_found:
                logger.info(f"✅ Authentication verified - found indicators: {indicators_found}")
                return True
            else:
                logger.info("❌ No logged-in indicators found")
                return False

        except Exception as e:
            logger.error(f"Error verifying authentication: {e}")
            return False

    def _perform_fresh_authentication(self) -> bool:
        """Perform fresh authentication using available methods"""
        # Try FlareSolverr first if available
        if self.flaresolverr_url:
            if self._authenticate_with_flaresolverr():
                if self._verify_authentication():
                    return True
            logger.warning("FlareSolverr authentication failed, falling back to Selenium")

        # Fallback to direct Selenium
        if self._authenticate_with_selenium():
            if self._verify_authentication():
                return True

        return False

    def _authenticate_with_selenium(self) -> bool:
        """Authenticate using direct Selenium interaction"""
        try:
            logger.info("🌐 Authenticating with Selenium...")

            self.driver.get("https://www.crunchyroll.com/login")
            self._handle_cloudflare_challenge()

            wait = WebDriverWait(self.driver, 30)

            # Find and fill email field
            email_field = self._find_form_field(wait, [
                "#email", "input[name='email']", "input[type='email']"
            ])
            if not email_field:
                logger.error("❌ Could not find email field")
                self._save_debug_html("login_no_email.html")
                return False

            # Find and fill password field
            password_field = self._find_form_field(wait, [
                "#password", "input[name='password']", "input[type='password']"
            ], wait_for_presence=False)
            if not password_field:
                logger.error("❌ Could not find password field")
                self._save_debug_html("login_no_password.html")
                return False

            # Find submit button
            submit_button = self._find_form_field(wait, [
                "button[type='submit']", "input[type='submit']",
                "button:contains('Sign In')", "button:contains('Log In')", ".login-button"
            ], wait_for_presence=False)
            if not submit_button:
                logger.error("❌ Could not find submit button")
                self._save_debug_html("login_no_submit.html")
                return False

            # Fill and submit form
            logger.info("📝 Filling login form...")
            email_field.clear()
            email_field.send_keys(self.email)
            time.sleep(1)

            password_field.clear()
            password_field.send_keys(self.password)
            time.sleep(1)

            logger.info("🔘 Clicking submit button...")
            submit_button.click()
            time.sleep(5)

            # Check if still on login page
            if "login" in self.driver.current_url.lower():
                logger.error("❌ Still on login page after submission")
                self._save_debug_html("login_failed.html")
                return False

            self._cache_authentication()
            logger.info("✅ Selenium authentication successful")
            return True

        except Exception as e:
            logger.error(f"Selenium authentication failed: {e}")
            self._save_debug_html("selenium_auth_error.html")
            return False

    def _authenticate_with_flaresolverr(self) -> bool:
        """Authenticate using FlareSolverr service"""
        try:
            logger.info("🔥 Authenticating with FlareSolverr...")

            client = FlareSolverrClient(self.flaresolverr_url)

            if not client.create_session():
                return False

            # Get login page
            response = client.solve_challenge("https://www.crunchyroll.com/login")
            if not response:
                return False

            # Extract form data and add credentials
            form_data = self._extract_login_form_data(response.get('response', ''))
            form_data['email'] = self.email
            form_data['password'] = self.password

            # Submit login
            login_response = client.solve_challenge(
                url="https://www.crunchyroll.com/login",
                cookies=response.get('cookies', []),
                post_data=form_data
            )

            if login_response and "login" not in login_response.get('url', '').lower():
                # Apply cookies to browser session
                self.driver.get("https://www.crunchyroll.com")
                time.sleep(2)

                for cookie in login_response.get('cookies', []):
                    try:
                        self.driver.add_cookie({
                            'name': cookie.get('name'),
                            'value': cookie.get('value'),
                            'domain': cookie.get('domain', '.crunchyroll.com'),
                            'path': cookie.get('path', '/'),
                        })
                    except Exception as e:
                        logger.debug(f"Failed to add FlareSolverr cookie: {e}")

                self._cache_authentication()
                logger.info("✅ FlareSolverr authentication successful")
                return True

            return False

        except Exception as e:
            logger.error(f"FlareSolverr authentication failed: {e}")
            return False

    def _find_form_field(self, wait, selectors: List[str], wait_for_presence: bool = True):
        """Find a form field using multiple selectors"""
        for selector in selectors:
            try:
                if wait_for_presence:
                    element = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, selector)))
                else:
                    element = self.driver.find_element(By.CSS_SELECTOR, selector)

                if element.is_displayed():
                    return element
            except (TimeoutException, NoSuchElementException):
                continue
        return None

    def _handle_cloudflare_challenge(self, max_wait: int = 60) -> bool:
        """Wait for Cloudflare challenge to complete"""
        start_time = time.time()

        while time.time() - start_time < max_wait:
            try:
                page_source = self.driver.page_source.lower()

                # Check for Cloudflare indicators
                cf_indicators = [
                    'checking your browser', 'cloudflare', 'please wait',
                    'ddos protection', 'security check', 'just a moment'
                ]

                if any(indicator in page_source for indicator in cf_indicators):
                    logger.info("☁️ Cloudflare challenge detected, waiting...")
                    time.sleep(5)
                    continue

                # Check for login form
                if any(indicator in page_source for indicator in ['email', 'password', 'sign in', 'login']):
                    logger.info("✅ Cloudflare challenge completed")
                    return True

                time.sleep(2)

            except Exception as e:
                logger.debug(f"Error during Cloudflare check: {e}")
                time.sleep(2)

        logger.warning("⚠️ Cloudflare challenge timeout")
        return False

    def _extract_login_form_data(self, html_content: str) -> Dict[str, str]:
        """Extract hidden form fields from login page"""
        try:
            soup = BeautifulSoup(html_content, 'html.parser')
            form = soup.find('form')
            form_data = {}

            if form:
                for hidden_input in form.find_all('input', {'type': 'hidden'}):
                    name = hidden_input.get('name')
                    value = hidden_input.get('value', '')
                    if name:
                        form_data[name] = value

            return form_data

        except Exception as e:
            logger.error(f"Error extracting form data: {e}")
            return {}

    def _cache_authentication(self) -> None:
        """Save current authentication cookies and tokens to cache"""
        try:
            if self.driver:
                cookies = self.driver.get_cookies()

                # Cache cookies along with access_token, account_id, and device_id
                auth_data = {
                    'access_token': getattr(self, 'access_token', None),
                    'account_id': getattr(self, 'cached_account_id', None),
                    'device_id': getattr(self, 'cached_device_id', None)
                }

                self.auth_cache.save_crunchyroll_auth(cookies=cookies, **auth_data)
                logger.debug("✅ Authentication and tokens cached")
        except Exception as e:
            logger.error(f"Error caching authentication: {e}")

    # ==================== API METHODS ====================

    def _get_account_id(self) -> Optional[str]:
        """Get account ID, using cached value if available or making token request if needed"""
        try:
            # First, try to use cached account_id and access_token
            if hasattr(self, 'cached_account_id') and hasattr(self, 'access_token') and \
                    self.cached_account_id and self.access_token:

                logger.info(f"✅ Using cached account ID: {self.cached_account_id[:8]}...")

                # Verify the cached token is still valid by making a simple API call
                if self._verify_cached_token():
                    return self.cached_account_id
                else:
                    logger.info("Cached token invalid, requesting new one...")

            logger.info("Getting account ID via browser JavaScript...")

            # Get or generate device ID consistently
            device_id = self._get_or_create_device_id()
            logger.debug(f"Making token request with device_id: {device_id[:8]}...")

            # Make token request via browser JavaScript
            token_response = self.driver.execute_script("""
                const deviceId = arguments[0];

                return fetch("https://www.crunchyroll.com/auth/v1/token", {
                    method: "POST",
                    headers: {
                        "accept": "*/*",
                        "accept-language": "en-US,en;q=0.9",
                        "authorization": "Basic bm9haWhkZXZtXzZpeWcwYThsMHE6",
                        "content-type": "application/x-www-form-urlencoded",
                        "sec-fetch-dest": "empty",
                        "sec-fetch-mode": "cors",
                        "sec-fetch-site": "same-origin"
                    },
                    referrer: "https://www.crunchyroll.com/history",
                    body: `device_id=${deviceId}&device_type=Chrome&grant_type=etp_rt_cookie`,
                    mode: "cors",
                    credentials: "include"
                })
                .then(response => {
                    if (!response.ok) {
                        return {
                            success: false,
                            status: response.status,
                            statusText: response.statusText
                        };
                    }
                    return response.json().then(data => ({
                        success: true,
                        status: response.status,
                        data: data
                    }));
                })
                .catch(error => ({
                    success: false,
                    error: error.message
                }));
            """, device_id)

            if not token_response or not token_response.get('success'):
                status = token_response.get('status', 'unknown') if token_response else 'no response'
                error_msg = token_response.get('error', 'unknown error') if token_response else 'no response'
                logger.error(f"Browser token request failed: {status} - {error_msg}")
                return None

            # Extract account_id and access_token
            data = token_response.get('data', {})
            account_id = data.get('account_id')
            self.access_token = data.get('access_token')
            self.cached_account_id = account_id
            self.cached_device_id = device_id

            if account_id:
                logger.info(f"✅ Got new account ID via browser: {account_id[:8]}...")

                # Update cache with new tokens
                self._cache_authentication()

                return account_id
            else:
                logger.error("Token response missing account_id")
                return None

        except Exception as e:
            logger.error(f"Browser token request error: {e}")
            return None

    def _get_device_id(self) -> Optional[str]:
        """Extract device_id from browser storage"""
        try:
            device_id = self.driver.execute_script("""
                // Check localStorage for device_id patterns
                var possibleKeys = [
                    'device_id', 'deviceId', 'cr_device_id', 'crunchyroll_device_id'
                ];

                for (var key of possibleKeys) {
                    var value = localStorage.getItem(key);
                    if (value && value.match(/^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/i)) {
                        return value;
                    }
                }

                // Look for UUID patterns in any localStorage value
                for (var i = 0; i < localStorage.length; i++) {
                    var key = localStorage.key(i);
                    var value = localStorage.getItem(key);
                    if (value && typeof value === 'string') {
                        var match = value.match(/([a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12})/i);
                        if (match) return match[1];
                    }
                }

                return null;
            """)

            if device_id:
                logger.debug(f"Found device_id: {device_id[:8]}...")
                return device_id

            # Fallback: check cookies for device ID patterns
            cookies = self.driver.get_cookies()
            for cookie in cookies:
                if 'device' in cookie.get('name', '').lower():
                    value = cookie.get('value', '')
                    match = re.search(r'([a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12})',
                                    value, re.IGNORECASE)
                    if match:
                        logger.debug(f"Found device_id in cookie: {match.group(1)[:8]}...")
                        return match.group(1)

            return None

        except Exception as e:
            logger.debug(f"Error extracting device_id: {e}")
            return None

    def _fetch_history_via_browser_api(self, account_id: str, max_pages: int) -> List[Dict[str, Any]]:
        """Fetch watch history using browser-based API calls"""
        all_episodes = []
        page_size = 100

        try:
            logger.info(f"🚀 Using Crunchyroll API via browser (account: {account_id[:8]}...)")

            for page in range(max_pages):
                logger.info(f"📄 Fetching page {page + 1}/{max_pages} via browser...")

                start_param = page * page_size if page > 0 else 0

                # Make API request through browser JavaScript
                api_response = self.driver.execute_script("""
                    const accountId = arguments[0];
                    const pageSize = arguments[1];
                    const startParam = arguments[2];
                    const accessToken = arguments[3];

                    const apiUrl = `https://www.crunchyroll.com/content/v2/${accountId}/watch-history`;
                    const params = new URLSearchParams({
                        page_size: pageSize,
                        locale: 'en-US'
                    });

                    if (startParam > 0) {
                        params.append('start', startParam);
                    }

                    const headers = {
                        'Accept': 'application/json',
                        'Accept-Language': 'en-US,en;q=0.9',
                        'sec-fetch-dest': 'empty',
                        'sec-fetch-mode': 'cors',
                        'sec-fetch-site': 'same-origin'
                    };

                    if (accessToken) {
                        headers['Authorization'] = `Bearer ${accessToken}`;
                    }

                    return fetch(`${apiUrl}?${params.toString()}`, {
                        method: 'GET',
                        headers: headers,
                        credentials: 'include',
                        mode: 'cors'
                    })
                    .then(response => {
                        if (!response.ok) {
                            return { success: false, status: response.status, statusText: response.statusText };
                        }
                        return response.json().then(data => ({ success: true, data: data }));
                    })
                    .catch(error => ({ success: false, error: error.message }));
                """, account_id, page_size, start_param, self.access_token)

                # Handle response
                if not api_response or not api_response.get('success'):
                    status = api_response.get('status', 'unknown') if api_response else 'no response'
                    error_msg = api_response.get('error', 'unknown error') if api_response else 'no response'
                    logger.error(f"API page {page + 1} failed: {status} - {error_msg}")
                    break

                data = api_response.get('data', {})
                items = data.get('data', [])

                if not items:
                    logger.info(f"No more items at page {page + 1}")
                    break

                # Parse episodes from this page
                page_episodes = self._parse_api_response(items)
                all_episodes.extend(page_episodes)

                logger.info(f"Page {page + 1}: {len(page_episodes)} valid episodes (total: {len(all_episodes)})")

                # Stop if we got fewer items than page_size (indicating last page)
                if len(items) < page_size:
                    logger.info("Reached end of available data")
                    break

                time.sleep(0.3)  # Rate limiting

            # Log final summary
            if all_episodes:
                self._log_api_summary(all_episodes)
            else:
                logger.warning("No episodes retrieved from browser-based API")

            return all_episodes

        except Exception as e:
            logger.error(f"Browser-based API scraping failed: {e}")
            return []

    def _parse_api_response(self, items: List[Dict]) -> List[Dict[str, Any]]:
        """Parse episodes from API response items with proper season detection"""
        episodes = []
        skipped = 0

        for item in items:
            try:
                panel = item.get('panel', {})
                episode_metadata = panel.get('episode_metadata', {})

                series_title = episode_metadata.get('series_title', '').strip()
                episode_number = episode_metadata.get('episode_number', 0)
                episode_title = panel.get('title', '').strip()
                season_title = episode_metadata.get('season_title', '').strip()

                # Skip invalid entries
                if not series_title or not episode_number or episode_number <= 0:
                    skipped += 1
                    continue

                # CRITICAL: Check if this is compilation/recap content that should be skipped
                if self._is_compilation_or_recap_content(season_title, episode_title, episode_metadata):
                    logger.debug(f"Skipping compilation/recap content: {series_title} - {season_title} - {episode_title}")
                    skipped += 1
                    continue

                # Use season_display_number as primary source, fall back to parsing season_title
                detected_season = self._extract_correct_season_number(episode_metadata)

                # Safely handle season_display_number for debugging
                season_display_number = episode_metadata.get('season_display_number', '').strip()
                raw_season_number = None
                if season_display_number and season_display_number.isdigit():
                    try:
                        raw_season_number = int(season_display_number)
                    except ValueError:
                        raw_season_number = None

                episodes.append({
                    'series_title': series_title,
                    'episode_title': episode_title,
                    'episode_number': episode_number,
                    'season': detected_season,
                    'season_title': season_title,
                    'raw_season_number': raw_season_number,  # Keep for debugging, can be None
                    'season_display_number': season_display_number,  # Keep raw string for debugging
                    'date_played': item.get('date_played', ''),
                    'fully_watched': item.get('fully_watched', False),
                    'api_source': True
                })

            except Exception as e:
                logger.debug(f"Error parsing episode item: {e}")
                skipped += 1
                continue

        if skipped > 0:
            logger.debug(f"Skipped {skipped} invalid items from API response")

        return episodes

    def _validate_and_correct_season(self, series_title: str, episode_number: int,
                                     raw_season: int, episode_title: str) -> int:
        """Validate and correct season number based on known patterns"""

        # For very high season numbers, it's likely an error
        if raw_season > 10:
            logger.debug(f"Suspicious season number {raw_season} for {series_title}, defaulting to 1")
            return 1

        # Check for known problematic patterns
        series_lower = series_title.lower()
        episode_title_lower = episode_title.lower()

        # Known single-season anime that Crunchyroll might misclassify
        single_season_patterns = [
            'dan da dan',
            'kabaneri of the iron fortress',
            'chainsaw man',  # Only season 1 exists currently
        ]

        for pattern in single_season_patterns:
            if pattern in series_lower:
                if raw_season > 1:
                    logger.debug(f"Correcting season for known single-season anime: {series_title} S{raw_season} → S1")
                return 1

        # For very high episode numbers, might indicate absolute numbering
        # In this case, season 1 is more likely correct
        if episode_number > 50 and raw_season > 1:
            logger.debug(
                f"High episode number {episode_number} with season {raw_season}, using season 1 for {series_title}")
            return 1

        # Check episode title for season indicators that might override
        if episode_title_lower:
            # Look for explicit season indicators in episode title
            season_match = re.search(r'season\s+(\d+)', episode_title_lower)
            if season_match:
                detected = int(season_match.group(1))
                if detected != raw_season:
                    logger.debug(
                        f"Episode title indicates season {detected} vs API season {raw_season} for {series_title}")
                    return detected

        # For reasonable season numbers (1-4), trust the API but with caution
        if 1 <= raw_season <= 4:
            return raw_season

        # Default to season 1 for anything else
        logger.debug(f"Defaulting to season 1 for {series_title} (raw season: {raw_season})")
        return 1

    def _is_compilation_or_recap_content(self, season_title: str, episode_title: str,
                                         episode_metadata: Dict[str, Any]) -> bool:
        """Detect compilation, recap, or movie content that should be skipped"""

        # Check season title for compilation indicators
        season_title_lower = season_title.lower() if season_title else ""

        # Handle None or empty season_title properly
        if not season_title or season_title.strip() == "":
            # Check if season_display_number is empty (often indicates specials/compilations)
            season_display_number = episode_metadata.get('season_display_number', '').strip()
            if not season_display_number:
                # Additional check - if it's a very long duration, it might be a compilation
                duration_ms = episode_metadata.get('duration_ms', 0)
                normal_episode_duration = 25 * 60 * 1000  # 25 minutes in milliseconds
                if duration_ms > normal_episode_duration * 2:  # More than 50 minutes
                    logger.debug(f"Long duration content detected ({duration_ms / 1000 / 60:.1f} min), likely compilation")
                    return True

        compilation_indicators = [
            'compilation', 'recap', 'summary', 'movie', 'film',
            'gekijouban', 'theatrical', 'special collection'
        ]

        for indicator in compilation_indicators:
            if indicator in season_title_lower:
                return True

        # Check episode title for compilation indicators
        episode_title_lower = episode_title.lower() if episode_title else ""
        for indicator in compilation_indicators:
            if indicator in episode_title_lower:
                return True

        # Check identifier pattern - sometimes compilations have different patterns
        identifier = episode_metadata.get('identifier', '')
        if identifier and '|M' in identifier:  # 'M' often indicates movie/compilation
            return True

        return False

    def _log_api_summary(self, all_episodes: List[Dict[str, Any]]) -> None:
        """Log clean summary of API results"""
        # Count episodes per series-season using the processed season field
        series_counts = {}
        for episode in all_episodes:
            series = episode.get('series_title', 'Unknown')
            season = episode.get('season', 1)  # Use the processed season field
            key = f"{series} S{season}"
            series_counts[key] = series_counts.get(key, 0) + 1

        logger.info("=" * 50)
        logger.info(f"API RESULTS: {len(all_episodes)} episodes from {len(series_counts)} series-seasons")
        logger.info("=" * 50)

        # Show top 15 series
        sorted_series = sorted(series_counts.items(), key=lambda x: x[1], reverse=True)
        for i, (series_season, count) in enumerate(sorted_series[:15], 1):
            logger.info(f"{i:2d}. {series_season}: {count} episodes")

        if len(sorted_series) > 15:
            remaining = len(sorted_series) - 15
            remaining_episodes = sum(count for _, count in sorted_series[15:])
            logger.info(f"... and {remaining} more series ({remaining_episodes} episodes)")

        logger.info("=" * 50)

    def _extract_correct_season_number(self, episode_metadata: Dict[str, Any]) -> int:
        """Extract correct season number using season_display_number as primary source"""

        # Primary: Use season_display_number if available and numeric
        season_display_number = episode_metadata.get('season_display_number', '').strip()
        logger.debug(f"extract_correct_season_number - Input season_display_number: {season_display_number!r}")

        if season_display_number and season_display_number.isdigit():
            try:
                season_num = int(season_display_number)
                if 1 <= season_num <= 20:  # Reasonable range
                    logger.debug(f"Using season_display_number: {season_num}")
                    return season_num
                else:
                    logger.debug(f"season_display_number {season_num} out of reasonable range, falling back")
            except ValueError:
                logger.debug(f"Could not convert season_display_number '{season_display_number}' to int")
        else:
            logger.debug(f"season_display_number is empty or non-numeric: {season_display_number!r}")

        # Secondary: Parse season number from season_title
        season_title = episode_metadata.get('season_title', '')
        if season_title:
            extracted_season = self._extract_season_from_title(season_title)
            if extracted_season > 1:
                logger.debug(f"Using season from title parsing: {extracted_season}")
                return extracted_season

        # Tertiary: Use season_sequence_number if it makes sense
        season_sequence = episode_metadata.get('season_sequence_number', 0)
        if isinstance(season_sequence, int) and 1 <= season_sequence <= 10:
            logger.debug(f"Using season_sequence_number: {season_sequence}")
            return season_sequence

        # Last resort: Use the raw season_number but validate it
        raw_season_number = episode_metadata.get('season_number', 1)
        if isinstance(raw_season_number, int) and 1 <= raw_season_number <= 10:
            logger.debug(f"Using raw season_number: {raw_season_number}")
            return raw_season_number

        # Default to season 1
        logger.debug("Defaulting to season 1")
        return 1


    def _extract_season_from_title(self, title: str) -> int:
        """Extract season number from season title"""
        if not title:
            return 1

        # Look for "Season X" or "Season X" patterns
        season_patterns = [
            r'Season\s+(\d+)',  # "Season 2"
            r'(\d+)(?:st|nd|rd|th)?\s+Season',  # "2nd Season"
            r'Part\s+(\d+)',  # "Part 2"
        ]

        for pattern in season_patterns:
            match = re.search(pattern, title, re.IGNORECASE)
            if match:
                try:
                    season_num = int(match.group(1))
                    if 1 <= season_num <= 20:  # Reasonable range
                        return season_num
                except (ValueError, IndexError):
                    continue

        return 1

    # ==================== UTILITY METHODS ====================

    def _save_debug_html(self, filename: str) -> None:
        """Save current page HTML for debugging (file only, no logging)"""
        try:
            cache_dir = Path('_cache')
            cache_dir.mkdir(exist_ok=True)

            filepath = cache_dir / filename
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(self.driver.page_source)

            logger.debug(f"Debug HTML saved: {filepath.name}")

        except Exception as e:
            logger.error(f"Error saving debug HTML: {e}")