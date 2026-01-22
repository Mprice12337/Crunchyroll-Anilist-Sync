"""
Crunchyroll Authentication Handler
Manages authentication, token management, and session caching for Crunchyroll API access.
"""

import time
import logging
import uuid
import hashlib
import requests
import os
from typing import Dict, Optional, List
from pathlib import Path
from bs4 import BeautifulSoup

import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException

from cache_manager import AuthCache

logger = logging.getLogger(__name__)


class CrunchyrollAuth:
    """Handles Crunchyroll authentication and token management"""

    def _perform_fresh_authentication(self) -> bool:
        """Perform fresh authentication with Crunchyroll"""
        logger.info("🔐 Performing fresh authentication...")

        if self.flaresolverr_url:
            logger.info("Using FlareSolverr for authentication")
            if self._authenticate_via_flaresolverr():
                return True

        if not self._authenticate_via_browser():
            logger.error("Browser authentication failed")
            return False

        self._capture_tokens_post_login()
        self._cache_authentication()
        return True

    def _authenticate_via_browser(self) -> bool:
        """Authenticate using browser automation"""
        try:
            self.driver.get("https://www.crunchyroll.com/login")
            time.sleep(3)

            if not self._handle_cloudflare_challenge():
                logger.warning("Cloudflare challenge handling timeout")

            wait = WebDriverWait(self.driver, 20)

            email_field = self._find_form_field(wait, [
                'input[type="email"]',
                'input[name="email"]',
                '#email'
            ])

            password_field = self._find_form_field(wait, [
                'input[type="password"]',
                'input[name="password"]',
                '#password'
            ])

            if not email_field or not password_field:
                logger.error("Could not locate login form fields")
                return False

            email_field.clear()
            email_field.send_keys(self.email)
            time.sleep(1)

            password_field.clear()
            password_field.send_keys(self.password)
            time.sleep(1)

            submit_button = self._find_form_field(wait, [
                'button[type="submit"]',
                'button.submit-button',
                'input[type="submit"]'
            ], wait_for_presence=False)

            if submit_button:
                submit_button.click()
            else:
                password_field.submit()

            time.sleep(12)

            if "login" in self.driver.current_url.lower():
                logger.error("Still on login page after submission")
                return False

            logger.info("✅ Browser authentication successful")
            return True

        except Exception as e:
            logger.error(f"Browser authentication error: {e}")
            return False

    def _authenticate_via_flaresolverr(self) -> bool:
        """Authenticate using FlareSolverr proxy"""
        try:
            logger.info("🔐 Attempting authentication via FlareSolverr...")

            # FlareSolverr Strategy: Use it to bypass Cloudflare and get session cookies,
            # then transfer those to Selenium driver for the actual login

            # Step 1: Use FlareSolverr to bypass Cloudflare on login page
            logger.info("Step 1: Using FlareSolverr to bypass Cloudflare...")
            flare_data = {
                "cmd": "request.get",
                "url": "https://www.crunchyroll.com/login",
                "maxTimeout": 60000
            }

            flare_response = requests.post(
                f"{self.flaresolverr_url}/v1",
                json=flare_data,
                timeout=90
            )

            if flare_response.status_code != 200:
                logger.error(f"FlareSolverr request failed: {flare_response.status_code}")
                logger.debug(f"Response: {flare_response.text[:500]}")
                return False

            flare_solution = flare_response.json().get('solution', {})
            if not flare_solution:
                logger.error("No solution in FlareSolverr response")
                return False

            cloudflare_cookies = flare_solution.get('cookies', [])
            logger.info(f"✅ FlareSolverr bypassed Cloudflare, got {len(cloudflare_cookies)} cookies")

            # Step 2: Transfer Cloudflare bypass cookies to Selenium
            logger.info("Step 2: Transferring Cloudflare cookies to Selenium driver...")
            self.driver.get("https://www.crunchyroll.com")
            time.sleep(2)

            # Add Cloudflare cookies to driver
            for cookie in cloudflare_cookies:
                try:
                    cookie_data = {
                        'name': cookie.get('name'),
                        'value': cookie.get('value'),
                        'domain': cookie.get('domain', '.crunchyroll.com'),
                        'path': cookie.get('path', '/'),
                    }

                    if cookie.get('secure') is not None:
                        cookie_data['secure'] = cookie.get('secure')
                    if cookie.get('httpOnly') is not None:
                        cookie_data['httpOnly'] = cookie.get('httpOnly')

                    self.driver.add_cookie(cookie_data)
                    logger.debug(f"Added cookie: {cookie.get('name')}")

                except Exception as e:
                    logger.debug(f"Failed to add cookie {cookie.get('name')}: {e}")

            logger.info("✅ Cloudflare cookies transferred to driver")

            # Step 3: Now use Selenium with Cloudflare bypassed to perform login
            logger.info("Step 3: Performing login via Selenium with Cloudflare bypassed...")
            self.driver.get("https://www.crunchyroll.com/login")
            time.sleep(3)

            # Check if we're past Cloudflare
            page_source = self.driver.page_source.lower()
            if any(indicator in page_source for indicator in ['checking your browser', 'cloudflare', 'just a moment']):
                logger.warning("Still seeing Cloudflare challenge, waiting...")
                time.sleep(5)

            # Now fill in the login form
            wait = WebDriverWait(self.driver, 20)

            email_field = self._find_form_field(wait, [
                'input[type="email"]',
                'input[name="email"]',
                '#email'
            ])

            password_field = self._find_form_field(wait, [
                'input[type="password"]',
                'input[name="password"]',
                '#password'
            ])

            if not email_field or not password_field:
                logger.error("Could not locate login form fields")
                return False

            logger.info("Found login form fields")
            email_field.clear()
            email_field.send_keys(self.email)
            time.sleep(1)

            password_field.clear()
            password_field.send_keys(self.password)
            time.sleep(1)

            submit_button = self._find_form_field(wait, [
                'button[type="submit"]',
                'button.submit-button',
                'input[type="submit"]'
            ], wait_for_presence=False)

            if submit_button:
                logger.info("Clicking submit button")
                submit_button.click()
            else:
                logger.info("Submitting form via password field")
                password_field.submit()

            # Wait for redirect after login
            logger.info("Waiting for login to complete...")
            time.sleep(12)

            # Check if login was successful
            current_url = self.driver.current_url.lower()
            logger.info(f"Current URL after login: {current_url}")

            if "login" in current_url:
                logger.error("❌ Still on login page after submission")
                # Log page source for debugging
                page_source = self.driver.page_source
                if "incorrect" in page_source.lower() or "invalid" in page_source.lower():
                    logger.error("Possible incorrect credentials")
                return False

            logger.info("✅ Login successful via FlareSolverr + Selenium")

            # Step 4: Capture tokens (same as browser method)
            logger.info("Step 4: Capturing authentication tokens...")
            account_id = self._capture_tokens_post_login()

            if not account_id:
                logger.error("❌ Failed to capture tokens after login")
                return False

            logger.info(f"✅ Captured account_id: {account_id[:8]}...")

            # Step 5: Cache authentication
            logger.info("Step 5: Caching authentication...")
            self._cache_authentication()

            logger.info("✅ FlareSolverr authentication completed successfully")
            return True

        except Exception as e:
            logger.error(f"FlareSolverr authentication failed: {e}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            return False

    def _cache_authentication(self) -> None:
        """Save authentication data including tokens and cookies"""
        try:
            if not self.driver:
                logger.warning("No driver available for caching")
                return

            cookies = self.driver.get_cookies()
            auth_data = {
                'access_token': getattr(self, 'access_token', None),
                'account_id': getattr(self, 'cached_account_id', None),
                'device_id': getattr(self, 'cached_device_id', None)
            }

            logger.info(f"💾 Caching authentication:")
            logger.info(f"   - Cookies: {len(cookies)}")
            logger.info(f"   - Access token: {'✅' if auth_data['access_token'] else '❌'}")
            logger.info(f"   - Account ID: {'✅' if auth_data['account_id'] else '❌'}")
            logger.info(f"   - Device ID: {'✅' if auth_data['device_id'] else '❌'}")

            success = self.auth_cache.save_crunchyroll_auth(cookies=cookies, **auth_data)

            if success:
                logger.info("✅ Authentication cached successfully")
                cached_check = self.auth_cache.load_crunchyroll_auth()
                if cached_check:
                    logger.info(f"✅ Cache verification successful")
                else:
                    logger.error("❌ Cache verification failed")
            else:
                logger.error("❌ Failed to cache authentication")

        except Exception as e:
            logger.error(f"Error caching authentication: {e}")

    def _capture_tokens_post_login(self):
        """Capture authentication tokens after successful login"""
        try:
            logger.info("🔍 Capturing authentication tokens via token endpoint...")
            device_id = self._get_or_create_device_id()

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

            data = token_response.get('data', {})
            account_id = data.get('account_id')
            self.access_token = data.get('access_token')
            self.cached_account_id = account_id
            self.cached_device_id = device_id

            if account_id:
                logger.info(f"✅ Got new account ID via browser: {account_id[:8]}...")
            else:
                logger.error("❌ No account_id in token response")

            return account_id

        except Exception as e:
            logger.error(f"Error capturing tokens: {e}")
            return None

    def _get_or_create_device_id(self) -> str:
        """Get existing device_id from cache/browser or create a consistent one"""
        try:
            if hasattr(self, 'cached_device_id') and self.cached_device_id:
                return self.cached_device_id

            device_id = self._get_device_id()
            if device_id:
                return device_id

            email_hash = hashlib.sha256(self.email.encode()).hexdigest()[:16]
            device_id = f"web-{email_hash}-{uuid.uuid4()}"
            logger.info(f"Created new device_id: {device_id[:20]}...")
            return device_id

        except Exception as e:
            logger.error(f"Error getting device_id: {e}")
            return f"web-{uuid.uuid4()}"

    def _get_device_id(self) -> Optional[str]:
        """Retrieve device_id from browser localStorage"""
        try:
            device_id = self.driver.execute_script("""
                const storage = window.localStorage;
                const keys = Object.keys(storage);
                for (let key of keys) {
                    if (key.includes('device_id') || key.includes('deviceId')) {
                        return storage.getItem(key);
                    }
                }
                return null;
            """)
            return device_id
        except Exception as e:
            logger.debug(f"Could not get device_id from browser: {e}")
            return None

    def _has_cached_auth(self) -> bool:
        """Fast check if cached authentication exists"""
        try:
            cached_auth = self.auth_cache.load_crunchyroll_auth()
            if not cached_auth:
                return False

            has_cookies = bool(cached_auth.get('cookies'))
            has_tokens = bool(cached_auth.get('access_token') and cached_auth.get('account_id'))

            return has_cookies or has_tokens

        except Exception as e:
            logger.debug(f"Error checking cached auth: {e}")
            return False

    def _setup_driver(self) -> None:
        """Initialize Chrome driver with appropriate options - DOCKER COMPATIBLE"""
        try:
            options = uc.ChromeOptions()

            # CRITICAL: Set binary location explicitly for Docker
            chrome_binary = os.environ.get('CHROME_BIN', '/usr/bin/google-chrome')
            if os.path.exists(chrome_binary):
                options.binary_location = chrome_binary
                logger.info(f"Using Chrome binary: {chrome_binary}")
            else:
                logger.warning(f"Chrome binary not found at {chrome_binary}, letting uc auto-detect")

            if self.headless:
                options.add_argument('--headless=new')
                logger.info("Running in headless mode")
            else:
                logger.info("Running with visible browser")

            # CRITICAL Docker flags - order matters!
            options.add_argument('--no-sandbox')
            options.add_argument('--disable-dev-shm-usage')
            options.add_argument('--disable-gpu')
            options.add_argument('--disable-software-rasterizer')

            # Window and user agent
            options.add_argument('--window-size=1920,1080')
            options.add_argument(
                '--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')

            # Anti-detection
            options.add_argument('--disable-blink-features=AutomationControlled')
            options.add_argument('--disable-extensions')

            # Stability improvements for Docker
            options.add_argument('--disable-background-networking')
            options.add_argument('--disable-background-timer-throttling')
            options.add_argument('--disable-backgrounding-occluded-windows')
            options.add_argument('--disable-breakpad')
            options.add_argument('--disable-component-extensions-with-background-pages')
            options.add_argument('--disable-features=TranslateUI,BlinkGenPropertyTrees')
            options.add_argument('--disable-ipc-flooding-protection')
            options.add_argument('--disable-renderer-backgrounding')
            options.add_argument('--enable-features=NetworkService,NetworkServiceInProcess')
            options.add_argument('--force-color-profile=srgb')
            options.add_argument('--hide-scrollbars')
            options.add_argument('--metrics-recording-only')
            options.add_argument('--mute-audio')

            # Memory and performance
            options.add_argument('--disable-features=VizDisplayCompositor')
            options.add_argument('--remote-debugging-port=9222')

            # CRITICAL: Prevent automatic driver downloads in Docker
            # Use version_main to match installed Chrome version
            try:
                import shlex
                chrome_version_output = os.popen(f'{shlex.quote(chrome_binary)} --version').read()
                chrome_version = chrome_version_output.split()[-1].split('.')[0]
                logger.info(f"Detected Chrome major version: {chrome_version}")

                # Initialize driver with explicit version
                self.driver = uc.Chrome(
                    options=options,
                    version_main=int(chrome_version),
                    driver_executable_path=None,  # Let uc handle driver
                    use_subprocess=True
                )
            except Exception as version_error:
                logger.warning(f"Could not detect Chrome version: {version_error}")
                logger.info("Attempting to initialize driver without version specification...")
                # Fallback: let uc auto-detect everything
                self.driver = uc.Chrome(options=options, use_subprocess=True)

            # Anti-detection script
            self.driver.execute_script(
                "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
            )

            logger.info("✅ Chrome driver setup completed successfully")
            logger.info(f"   Chrome version: {self.driver.capabilities.get('browserVersion', 'unknown')}")
            logger.info(
                f"   Driver version: {self.driver.capabilities.get('chrome', {}).get('chromedriverVersion', 'unknown')}")

        except Exception as e:
            logger.error(f"Failed to setup Chrome driver: {e}")
            logger.error("Detailed error information:")
            logger.error(f"  Chrome binary location: {os.environ.get('CHROME_BIN', 'not set')}")
            logger.error(
                f"  Chrome binary exists: {os.path.exists(chrome_binary) if 'chrome_binary' in locals() else 'unknown'}")

            # Try to get more detailed error info
            try:
                import traceback
                logger.error(f"Full traceback:\n{traceback.format_exc()}")
            except:
                pass

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

                    for field in ['secure', 'httpOnly']:
                        if cookie.get(field) is not None:
                            cookie_data[field] = cookie.get(field)

                    self.driver.add_cookie(cookie_data)

                except Exception as e:
                    logger.debug(f"Failed to add cookie {cookie.get('name')}: {e}")
                    continue

            self.access_token = cached_auth.get('access_token')
            self.cached_account_id = cached_auth.get('account_id')
            self.cached_device_id = cached_auth.get('device_id')

            if self.access_token and self.cached_account_id:
                logger.info(f"✅ Cached access token and account ID loaded")

            logger.info("✅ Cached cookies loaded successfully")
            return True

        except Exception as e:
            logger.error(f"Error loading cached auth: {e}")
            return False

    def _verify_authentication(self) -> bool:
        """Verify authentication by checking account page and validating token"""
        try:
            logger.info("🔍 Verifying authentication...")

            self.driver.get("https://www.crunchyroll.com/account")
            time.sleep(3)

            if "login" in self.driver.current_url.lower():
                logger.info("❌ Redirected to login page - not authenticated")
                return False

            page_source = self.driver.page_source.lower()
            logged_in_indicators = [
                "account", "profile", "subscription", "settings",
                "logout", "sign out", "premium"
            ]

            indicators_found = [indicator for indicator in logged_in_indicators
                                if indicator in page_source]

            if not indicators_found:
                logger.info("❌ No logged-in indicators found")
                return False

            logger.info(f"✅ Account access verified")

            if self.access_token and self.cached_account_id:
                if self._verify_cached_token():
                    logger.info("✅ Full authentication verification successful")
                    return True

            logger.info("✅ Basic authentication verification successful")
            return True

        except Exception as e:
            logger.error(f"Error verifying authentication: {e}")
            return False

    def _verify_cached_token(self) -> bool:
        """Verify cached access token is still valid"""
        try:
            test_response = self.driver.execute_script("""
                const accountId = arguments[0];
                const accessToken = arguments[1];

                return fetch(`https://www.crunchyroll.com/content/v2/${accountId}/watch-history?locale=en-US&page_size=1`, {
                    headers: {
                        'Authorization': `Bearer ${accessToken}`,
                        'Accept': 'application/json'
                    },
                    credentials: 'include'
                })
                .then(response => ({
                    success: response.ok,
                    status: response.status
                }))
                .catch(error => ({
                    success: false,
                    error: error.message
                }));
            """, self.cached_account_id, self.access_token)

            if test_response and test_response.get('success'):
                return True
            else:
                logger.info(f"❌ Cached token invalid, refreshing...")
                return self._refresh_access_token()

        except Exception as e:
            logger.debug(f"Error verifying cached token: {e}")
            return self._refresh_access_token()

    def _refresh_access_token(self) -> bool:
        """Refresh the access token using the current session"""
        try:
            logger.info("🔄 Refreshing access token...")
            account_id = self._capture_tokens_post_login()

            if account_id:
                self._cache_authentication()
                logger.info("✅ Access token refreshed successfully")
                return True

            logger.error("❌ Failed to refresh access token")
            return False

        except Exception as e:
            logger.error(f"Error refreshing access token: {e}")
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

                cf_indicators = [
                    'checking your browser', 'cloudflare', 'please wait',
                    'ddos protection', 'security check', 'just a moment'
                ]

                if any(indicator in page_source for indicator in cf_indicators):
                    logger.info("☁️ Cloudflare challenge detected, waiting...")
                    time.sleep(5)
                    continue

                if any(indicator in page_source for indicator in ['email', 'password', 'sign in', 'login']):
                    logger.info("✅ Cloudflare challenge completed")
                    return True

                time.sleep(2)

            except Exception as e:
                logger.debug(f"Error during Cloudflare check: {e}")
                time.sleep(2)

        logger.warning("⚠️ Cloudflare challenge timeout")
        return False
