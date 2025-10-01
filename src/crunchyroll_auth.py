"""
Crunchyroll Authentication Handler
Manages authentication, token management, and session caching for Crunchyroll API access.
"""

import time
import logging
import uuid
import hashlib
import requests
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

            time.sleep(5)

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
            flaresolverr_data = {
                "cmd": "request.post",
                "url": "https://www.crunchyroll.com/login",
                "postData": f"email={self.email}&password={self.password}",
                "maxTimeout": 60000
            }

            response = requests.post(
                f"{self.flaresolverr_url}/v1",
                json=flaresolverr_data,
                timeout=90
            )

            if response.status_code != 200:
                logger.error(f"FlareSolverr request failed: {response.status_code}")
                return False

            login_response = response.json().get('solution', {})

            if login_response and "login" not in login_response.get('url', '').lower():
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

                logger.info("✅ FlareSolverr login successful, capturing authentication tokens...")
                self._capture_tokens_post_login()
                self._cache_authentication()
                return True

            return False

        except Exception as e:
            logger.error(f"FlareSolverr authentication failed: {e}")
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
        """Initialize Chrome driver with appropriate options"""
        try:
            options = uc.ChromeOptions()

            if self.headless:
                options.add_argument('--headless=new')
                logger.info("Running in headless mode")
            else:
                logger.info("Running with visible browser")

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