"""
Crunchyroll API Scraper
Fetches watch history from Crunchyroll API using authenticated sessions.
"""

import time
import logging
import uuid
import hashlib
from typing import List, Dict, Any, Optional
from pathlib import Path

from cache_manager import AuthCache
from crunchyroll_auth import CrunchyrollAuth
from crunchyroll_parser import CrunchyrollParser

logger = logging.getLogger(__name__)


class CrunchyrollScraper(CrunchyrollAuth, CrunchyrollParser):
    """Crunchyroll scraper using API-based history fetching"""

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
        """Authenticate with Crunchyroll using cached or fresh authentication"""
        logger.info("🔐 Authenticating with Crunchyroll...")

        self.access_token = None
        self.cached_account_id = None
        self.cached_device_id = None

        if not self._has_cached_auth():
            logger.info("No cached authentication found, performing fresh login...")
            self._setup_driver()

            if self._perform_fresh_authentication():
                logger.info("✅ Fresh authentication successful")
                self.is_authenticated = True
                return True
            return False

        logger.info("Found cached authentication, validating...")
        self._setup_driver()

        if self._try_cached_auth() and self._verify_authentication():
            logger.info("✅ Using cached authentication")
            self.is_authenticated = True
            return True

        logger.info("Cached auth invalid, performing fresh authentication...")
        self.auth_cache.clear_crunchyroll_auth()

        if self._perform_fresh_authentication():
            logger.info("✅ Fresh authentication successful after cache failure")
            self.is_authenticated = True
            return True

        logger.error("❌ All authentication methods failed")
        return False

    def get_watch_history(self, max_pages: int = 10) -> List[Dict[str, Any]]:
        """
        Get complete watch history using Crunchyroll API.
        Fetches all pages up to max_pages.
        """
        logger.info(f"📚 Fetching watch history via API (max {max_pages} pages)...")

        if not self.is_authenticated:
            logger.error("Not authenticated! Call authenticate() first.")
            return []

        all_episodes = []

        for page_num in range(1, max_pages + 1):
            page_episodes = self.get_watch_history_page(page_num)

            if not page_episodes:
                logger.info(f"No more episodes at page {page_num}")
                break

            all_episodes.extend(page_episodes)
            logger.info(f"Page {page_num}: {len(page_episodes)} episodes (total: {len(all_episodes)})")
            time.sleep(0.3)

        return all_episodes

    def get_watch_history_page(self, page_num: int = 1, page_size: int = 50) -> List[Dict[str, Any]]:
        """Get a single page of watch history from Crunchyroll API"""
        if not self.is_authenticated:
            logger.error("Not authenticated! Call authenticate() first.")
            return []

        self.driver.get("https://www.crunchyroll.com")
        time.sleep(1)

        if not self.access_token or not self.cached_account_id:
            logger.warning("Missing access_token or account_id - requesting new tokens...")
            account_id = self._get_account_id()
            if not account_id:
                logger.error("Could not get account ID from token endpoint")
                return []
        else:
            if not self._verify_cached_token():
                logger.error("Cached token validation failed")
                return []
            account_id = self.cached_account_id

        try:
            api_response = self.driver.execute_script("""
                const accountId = arguments[0];
                const pageSize = arguments[1];
                const pageNum = arguments[2];
                const accessToken = arguments[3];

                const apiUrl = `https://www.crunchyroll.com/content/v2/${accountId}/watch-history`;
                const params = new URLSearchParams({
                    locale: 'en-US',
                    page: pageNum,
                    page_size: pageSize,
                    preferred_audio_language: 'ja-JP'
                });

                const fullUrl = `${apiUrl}?${params.toString()}`;

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

                return fetch(fullUrl, {
                    method: 'GET',
                    headers: headers,
                    credentials: 'include',
                    mode: 'cors'
                })
                .then(response => {
                    if (!response.ok) {
                        return { success: false, status: response.status, statusText: response.statusText, url: fullUrl };
                    }
                    return response.json().then(data => ({ 
                        success: true, 
                        data: data,
                        url: fullUrl,
                        itemCount: data?.data?.length || 0,
                        firstItemId: data?.data?.[0]?.id || null,
                        lastItemId: data?.data?.[data.data.length - 1]?.id || null
                    }));
                })
                .catch(error => ({ success: false, error: error.message, url: fullUrl }));
            """, account_id, page_size, page_num, self.access_token)

            if not api_response or not api_response.get('success'):
                status = api_response.get('status', 'unknown') if api_response else 'no response'
                error_msg = api_response.get('error', 'unknown error') if api_response else 'no response'
                requested_url = api_response.get('url', 'unknown') if api_response else 'unknown'
                logger.error(f"API request failed: {status} - {error_msg}")
                logger.error(f"Requested URL: {requested_url}")
                return []

            data = api_response.get('data', {})
            items = data.get('data', [])

            if not items:
                return []

            page_episodes = self._parse_api_response(items)

            if page_episodes:
                first_ep = page_episodes[0]
                last_ep = page_episodes[-1]
                logger.info(f"   First episode: {first_ep.get('series_title')} - E{first_ep.get('episode_number')}")
                logger.info(f"   Last episode: {last_ep.get('series_title')} - E{last_ep.get('episode_number')}")

            logger.info(f"✅ Page {page_num}: Retrieved {len(page_episodes)} episodes")
            return page_episodes

        except Exception as e:
            logger.error(f"Error fetching page {page_num}: {e}")
            return []

    def _get_account_id(self) -> Optional[str]:
        """Get account ID by requesting new tokens from the token endpoint"""
        try:
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
                self._cache_authentication()
            else:
                logger.error("❌ No account_id in token response")

            return account_id

        except Exception as e:
            logger.error(f"Error getting account_id: {e}")
            return None

    def _save_debug_html(self, filename: str) -> None:
        """Save current page HTML for debugging"""
        try:
            cache_dir = Path('_cache')
            cache_dir.mkdir(exist_ok=True)

            filepath = cache_dir / filename
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(self.driver.page_source)

            logger.debug(f"Debug HTML saved: {filepath.name}")

        except Exception as e:
            logger.error(f"Error saving debug HTML: {e}")

    def cleanup(self) -> None:
        """Clean up browser resources"""
        if self.driver:
            try:
                self.driver.quit()
                logger.info("✅ Browser closed successfully")
            except Exception as e:
                logger.error(f"Error closing browser: {e}")

    def __del__(self):
        """Ensure cleanup on object destruction"""
        self.cleanup()