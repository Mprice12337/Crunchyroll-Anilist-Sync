"""
Crunchyroll API Scraper
"""

import re
import time
import logging
import uuid
from typing import List, Dict, Any, Optional
from pathlib import Path

from cache_manager import AuthCache
from crunchyroll_auth import CrunchyrollAuth
from crunchyroll_parser import CrunchyrollParser

logger = logging.getLogger(__name__)


class CrunchyrollScraper(CrunchyrollAuth, CrunchyrollParser):
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