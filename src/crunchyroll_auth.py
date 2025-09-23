"""
Crunchyroll Auth Handler
"""

import time
import logging
from typing import List, Dict, Optional

import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from bs4 import BeautifulSoup

from flaresolvrrr_client import FlareSolverrClient

logger = logging.getLogger(__name__)


class CrunchyrollAuth:
    """Crunchyroll authentication handler"""

    # ==================== AUTHENTICATION METHODS ====================

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