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
        """Load and apply cached authentication cookies"""
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
        """Save current authentication cookies to cache"""
        try:
            if self.driver:
                cookies = self.driver.get_cookies()
                self.auth_cache.save_crunchyroll_auth(cookies=cookies)
                logger.debug("✅ Authentication cached")
        except Exception as e:
            logger.error(f"Error caching authentication: {e}")

    # ==================== API METHODS ====================

    def _get_account_id(self) -> Optional[str]:
        """Get account ID by making token request through browser"""
        try:
            logger.info("Getting account ID via browser JavaScript...")

            # Get device ID for token request
            device_id = self._get_device_id() or str(uuid.uuid4())
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

            if account_id:
                logger.info(f"✅ Got account ID via browser: {account_id[:8]}...")
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
        """Parse episodes from API response items"""
        episodes = []
        skipped = 0

        for item in items:
            try:
                panel = item.get('panel', {})
                episode_metadata = panel.get('episode_metadata', {})

                series_title = episode_metadata.get('series_title', '').strip()
                episode_number = episode_metadata.get('episode_number', 0)

                # Skip invalid entries
                if not series_title or not episode_number or episode_number <= 0:
                    skipped += 1
                    continue

                episodes.append({
                    'series_title': series_title,
                    'episode_title': panel.get('title', '').strip(),
                    'episode_number': episode_number,
                    'season': episode_metadata.get('season_number', 1),
                    'date_played': item.get('date_played', ''),
                    'fully_watched': item.get('fully_watched', False),
                    'api_source': True
                })

            except Exception:
                skipped += 1
                continue

        if skipped > 0:
            logger.debug(f"Skipped {skipped} invalid items from API response")

        return episodes

    def _log_api_summary(self, all_episodes: List[Dict[str, Any]]) -> None:
        """Log clean summary of API results"""
        # Count episodes per series-season
        series_counts = {}
        for episode in all_episodes:
            series = episode.get('series_title', 'Unknown')
            season = episode.get('season', 1)
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