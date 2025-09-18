"""
Fixed Crunchyroll scraper with improved season/episode parsing and better logging
"""

import re
import time
import logging
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
    """Fixed Crunchyroll scraper with improved parsing and logging"""

    def __init__(self, email: str, password: str, headless: bool = True,
                 flaresolverr_url: Optional[str] = None):
        self.email = email
        self.password = password
        self.headless = headless
        self.flaresolverr_url = flaresolverr_url
        self.driver = None
        self.auth_cache = AuthCache()
        self.is_authenticated = False

        # Enhanced patterns for better parsing
        self.episode_pattern = re.compile(r'(?:S\d+\s+)?(?:E|Episode|ep\.?)\s*(\d+)', re.IGNORECASE)
        self.season_pattern = re.compile(r'(?:S|Season)\s*(\d+)', re.IGNORECASE)

        # More comprehensive patterns for different formats
        self.combined_pattern = re.compile(r'S(\d+)\s+E(\d+)', re.IGNORECASE)  # S2 E20
        self.episode_only_pattern = re.compile(r'\bE(\d+)\b', re.IGNORECASE)  # E20

        self.episode_converter = None

    def authenticate(self) -> bool:
        """Authenticate with Crunchyroll"""
        logger.info("🔐 Authenticating with Crunchyroll...")

        self._setup_driver()

        # Try cached authentication first
        if self._try_cached_auth():
            if self._verify_authentication():
                logger.info("✅ Using cached authentication")
                self.is_authenticated = True
                return True
            else:
                logger.info("❌ Cached authentication invalid, clearing cache")
                self.auth_cache.clear_crunchyroll_auth()

        # Fresh authentication
        logger.info("Performing fresh authentication...")

        if self.flaresolverr_url:
            if self._authenticate_with_flaresolverr():
                if self._verify_authentication():
                    self.is_authenticated = True
                    return True
            logger.warning("FlareSolverr authentication failed, falling back to Selenium")

        # Fallback to Selenium
        if self._authenticate_with_selenium():
            if self._verify_authentication():
                self.is_authenticated = True
                return True

        logger.error("❌ All authentication methods failed")
        return False

    def get_watch_history(self, max_pages: int = 10) -> List[Dict[str, Any]]:
        """Get watch history using API only (no HTML fallback)"""
        logger.info(f"📚 Fetching watch history via API (max {max_pages} pages)...")

        if not self.is_authenticated:
            logger.error("Not authenticated! Call authenticate() first.")
            return []

        # Navigate to ensure authentication context
        self.driver.get("https://www.crunchyroll.com")
        time.sleep(2)

        # Get account ID from token endpoint
        account_id = self._get_account_id_from_token_endpoint()

        if not account_id:
            logger.error("Could not get account ID from token endpoint")
            return []

        # Use API only - no HTML fallback
        return self._fetch_history_via_api_clean(account_id, max_pages)

    def _scrape_with_improved_parser(self, max_pages: int) -> List[Dict[str, Any]]:
        """Scrape using improved parser logic with better logging"""
        all_episodes = []
        seen_episodes = set()  # Track unique episodes to avoid duplicates

        try:
            scroll_attempts = 0
            max_scrolls = max_pages * 2

            logger.info(f"🔄 Starting scraping (max {max_scrolls} scrolls for {max_pages} pages)")

            # FIRST: Parse the initial page load (before any scrolling)
            logger.info("📖 Parsing initial page load...")
            initial_episodes = self._parse_with_improved_logic()

            # Add initial episodes with deduplication
            for episode in initial_episodes:
                episode_key = self._create_episode_key(episode)
                if episode_key not in seen_episodes:
                    seen_episodes.add(episode_key)
                    all_episodes.append(episode)

            logger.info(f"📺 Initial load: Found {len(all_episodes)} unique episodes")

            # THEN: Scroll and accumulate additional episodes
            while scroll_attempts < max_scrolls:
                # Scroll to bottom
                self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(3)

                # Parse current episodes using improved logic
                current_episodes = self._parse_with_improved_logic()

                # Count episodes before adding new ones
                episodes_before = len(all_episodes)

                # Add new unique episodes only
                new_episodes_count = 0
                for episode in current_episodes:
                    episode_key = self._create_episode_key(episode)
                    if episode_key not in seen_episodes:
                        seen_episodes.add(episode_key)
                        all_episodes.append(episode)
                        new_episodes_count += 1

                logger.info(
                    f"📺 Scroll {scroll_attempts + 1}: Found {new_episodes_count} new episodes (total: {len(all_episodes)})")

                # Stop if no new episodes found
                if new_episodes_count == 0:
                    logger.info("🏁 No new episodes found, stopping pagination")
                    break

                scroll_attempts += 1
                time.sleep(1)

            # Log final results with more detail
            unique_series = set()
            series_episode_counts = {}

            for episode in all_episodes:
                series = episode.get('series_title', 'Unknown')
                season = episode.get('season', 1)
                series_season_key = f"{series} (Season {season})"
                unique_series.add(series_season_key)

                # Count episodes per series-season
                if series_season_key not in series_episode_counts:
                    series_episode_counts[series_season_key] = 0
                series_episode_counts[series_season_key] += 1

            logger.info(f"✅ Scraping complete: {len(all_episodes)} total episodes")
            logger.info(f"📚 Unique series-seasons found: {len(unique_series)}")

            # Log all unique series for verification
            for i, (series_season, count) in enumerate(sorted(series_episode_counts.items()), 1):
                logger.info(f"  {i}. {series_season}: {count} episodes")

            return all_episodes

        except Exception as e:
            logger.error(f"Error during scraping: {e}")
            return all_episodes

    def _get_account_id_from_token_endpoint(self) -> Optional[str]:
        """Get account ID from token endpoint using browser's JavaScript context"""
        try:
            logger.info("Getting account ID via browser JavaScript...")

            # Extract device_id from browser first
            device_id = self._get_device_id()
            if not device_id:
                logger.warning("Could not extract device_id, generating one...")
                import uuid
                device_id = str(uuid.uuid4())

            # Execute the token request directly in the browser using JavaScript
            logger.debug(f"Making token request with device_id: {device_id[:8]}...")

            token_response = self.driver.execute_script("""
                const deviceId = arguments[0];

                // Make the exact same request the browser would make
                return fetch("https://www.crunchyroll.com/auth/v1/token", {
                    method: "POST",
                    headers: {
                        "accept": "*/*",
                        "accept-language": "en-US,en;q=0.9",
                        "authorization": "Basic bm9haWhkZXZtXzZpeWcwYThsMHE6",
                        "content-type": "application/x-www-form-urlencoded",
                        "priority": "u=1, i",
                        "sec-ch-ua": '"Not)A;Brand";v="8", "Chromium";v="138", "Google Chrome";v="138"',
                        "sec-ch-ua-mobile": "?0",
                        "sec-ch-ua-platform": '"macOS"',
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
                            statusText: response.statusText,
                            headers: Object.fromEntries(response.headers.entries())
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

            logger.debug(f"Token request completed")

            # Handle the response
            if not token_response:
                logger.error("No response from browser token request")
                return None

            if not token_response.get('success'):
                status = token_response.get('status', 'unknown')
                error_msg = token_response.get('error', token_response.get('statusText', 'unknown error'))
                logger.error(f"Browser token request failed: {status} - {error_msg}")

                # Log additional debug info for non-200 responses
                if 'headers' in token_response:
                    logger.debug(f"Response headers: {token_response['headers']}")

                return None

            # Extract account_id from successful response
            data = token_response.get('data', {})
            account_id = data.get('account_id')

            if account_id:
                # Store access token for API calls
                self.access_token = data.get('access_token')
                logger.info(f"✅ Got account ID via browser: {account_id[:8]}...")
                return account_id
            else:
                logger.error("Token response missing account_id")
                logger.debug(f"Response data keys: {list(data.keys()) if data else 'None'}")
                return None

        except Exception as e:
            logger.error(f"Browser token request error: {e}")
            return None

    def _get_device_id(self) -> Optional[str]:
        """Extract device_id from browser context with enhanced methods"""
        try:
            # Method 1: Check localStorage and sessionStorage more thoroughly
            device_id = self.driver.execute_script("""
                // Check multiple storage locations
                try {
                    // Check localStorage first with various key patterns
                    var possibleKeys = [
                        'device_id', 'deviceId', 'cr_device_id', 'crunchyroll_device_id', 
                        'device_id_v2', 'client_device_id', 'user_device_id'
                    ];

                    for (var key of possibleKeys) {
                        var value = localStorage.getItem(key);
                        if (value && value.match(/^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/i)) {
                            return value;
                        }
                    }

                    // Check sessionStorage
                    for (var key of possibleKeys) {
                        var value = sessionStorage.getItem(key);
                        if (value && value.match(/^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/i)) {
                            return value;
                        }
                    }

                    // Look for UUID patterns in any storage value
                    for (var i = 0; i < localStorage.length; i++) {
                        var key = localStorage.key(i);
                        var value = localStorage.getItem(key);
                        if (value && typeof value === 'string') {
                            var match = value.match(/([a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12})/i);
                            if (match) return match[1];
                        }
                    }

                    // Check if there's a device_id in any global variables
                    if (typeof window.cxApiParams !== 'undefined' && window.cxApiParams.deviceId) {
                        return window.cxApiParams.deviceId;
                    }

                    return null;
                } catch(e) {
                    console.error('Device ID extraction error:', e);
                    return null;
                }
            """)

            if device_id:
                logger.debug(f"Found device_id: {device_id[:8]}...")
                return device_id

            # Method 2: Check cookies for device-related IDs
            cookies = self.driver.get_cookies()
            for cookie in cookies:
                name = cookie.get('name', '').lower()
                value = cookie.get('value', '')

                if 'device' in name and value:
                    # Look for UUID pattern in cookie value
                    import re
                    match = re.search(r'([a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12})', value,
                                      re.IGNORECASE)
                    if match:
                        logger.debug(f"Found device_id in cookie {name}: {match.group(1)[:8]}...")
                        return match.group(1)

            # Method 3: Try to find it in page source (last resort)
            try:
                page_source = self.driver.page_source
                import re
                device_matches = re.findall(
                    r'device[_-]?id["\s:=]+([a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12})', page_source,
                    re.IGNORECASE)
                if device_matches:
                    logger.debug(f"Found device_id in page source: {device_matches[0][:8]}...")
                    return device_matches[0]
            except Exception as e:
                logger.debug(f"Error searching page source: {e}")

            logger.debug("Could not extract device_id from browser")
            return None

        except Exception as e:
            logger.debug(f"Error extracting device_id: {e}")
            return None

    def _get_etp_anonymous_id(self) -> Optional[str]:
        """Extract etp-anonymous-id from browser context"""
        try:
            # Try to get from JavaScript
            etp_id = self.driver.execute_script("""
                // Check for etp-anonymous-id in various places
                try {
                    // Check localStorage
                    var etpId = localStorage.getItem('etp_anonymous_id') || localStorage.getItem('etp-anonymous-id');
                    if (etpId) return etpId;

                    // Check global objects
                    if (window.cxApiParams && window.cxApiParams.etpAnonymousId) {
                        return window.cxApiParams.etpAnonymousId;
                    }

                    // Look in page source or meta tags
                    var meta = document.querySelector('meta[name="etp-anonymous-id"]');
                    if (meta) return meta.content;

                    return null;
                } catch(e) {
                    return null;
                }
            """)

            if etp_id:
                logger.debug(f"Found etp-anonymous-id: {etp_id[:8]}...")
                return etp_id

            # Check cookies
            cookies = self.driver.get_cookies()
            for cookie in cookies:
                if 'etp' in cookie.get('name', '').lower() or 'anonymous' in cookie.get('name', '').lower():
                    value = cookie.get('value', '')
                    import re
                    match = re.search(r'([a-f0-9\-]{36})', value)
                    if match:
                        logger.debug(f"Found etp-anonymous-id in cookie: {cookie['name']}")
                        return match.group(1)

            return None

        except Exception as e:
            logger.debug(f"Could not extract etp-anonymous-id: {e}")
            return None

    def _fetch_history_via_api(self, account_id: str, max_pages: int) -> List[Dict[str, Any]]:
        """Fetch history using Crunchyroll's JSON API with enhanced authentication"""
        all_episodes = []
        page_size = 100

        try:
            logger.info(f"🚀 Using Crunchyroll API with account ID: {account_id[:8]}...")

            # Get cookies from the browser session
            cookies = {cookie['name']: cookie['value'] for cookie in self.driver.get_cookies()}

            # Set up headers - use access token if we have it
            headers = {
                'User-Agent': self.driver.execute_script("return navigator.userAgent;"),
                'Accept': 'application/json, text/plain, */*',
                'Accept-Language': 'en-US,en;q=0.9',
                'Accept-Encoding': 'gzip, deflate, br',
                'Referer': 'https://www.crunchyroll.com/history',
                'Origin': 'https://www.crunchyroll.com',
                'Sec-Fetch-Dest': 'empty',
                'Sec-Fetch-Mode': 'cors',
                'Sec-Fetch-Site': 'same-origin',
            }

            # Add Authorization header if we have an access token
            if hasattr(self, 'access_token') and self.access_token:
                headers['Authorization'] = f'Bearer {self.access_token}'
                logger.debug("🔑 Using Bearer token for API authentication")

            import requests
            session = requests.Session()
            session.cookies.update(cookies)
            session.headers.update(headers)

            for page in range(max_pages):
                logger.info(f"📄 Fetching API page {page + 1}/{max_pages}...")

                # Build API URL
                api_url = f"https://www.crunchyroll.com/content/v2/{account_id}/watch-history"
                params = {
                    'page_size': page_size,
                    'locale': 'en-US'
                }

                # Add pagination for subsequent pages
                if page > 0:
                    params['start'] = page * page_size

                try:
                    response = session.get(api_url, params=params, timeout=30)

                    if response.status_code == 401:
                        logger.error("❌ API authentication failed - trying to refresh token...")
                        # Try to get a fresh token
                        fresh_account_id = self._get_account_id_from_token_endpoint()
                        if fresh_account_id and fresh_account_id == account_id:
                            # Update headers with new token and retry
                            if hasattr(self, 'access_token'):
                                session.headers['Authorization'] = f'Bearer {self.access_token}'
                                response = session.get(api_url, params=params, timeout=30)
                            else:
                                break
                        else:
                            break

                    if response.status_code == 403:
                        logger.error("❌ API access forbidden")
                        break
                    elif response.status_code != 200:
                        logger.error(f"❌ API request failed: {response.status_code}")
                        logger.debug(f"Response: {response.text[:500]}")
                        break

                    data = response.json()
                    items = data.get('data', [])

                    if not items:
                        logger.info("📄 No more items found, stopping pagination")
                        break

                    logger.info(f"✅ Found {len(items)} items on page {page + 1}")

                    # Parse episodes from this page
                    page_episodes = self._parse_api_response(items)
                    all_episodes.extend(page_episodes)

                    # Check if we've reached the end
                    total = data.get('total', 0)
                    if len(all_episodes) >= total or len(items) < page_size:
                        logger.info(f"📄 Reached end of history (total available: {total})")
                        break

                    time.sleep(0.5)  # Rate limiting

                except requests.exceptions.RequestException as e:
                    logger.error(f"❌ Network error on page {page + 1}: {e}")
                    break

            # Log comprehensive results
            if all_episodes:
                self._log_api_results(all_episodes)
            else:
                logger.warning("❌ No episodes retrieved from API")

            return all_episodes

        except Exception as e:
            logger.error(f"❌ API scraping failed: {e}")
            return []

    def _fetch_history_via_api_clean(self, account_id: str, max_pages: int) -> List[Dict[str, Any]]:
        """Clean API fetching using browser JavaScript to avoid Cloudflare blocks"""
        all_episodes = []
        page_size = 100

        try:
            logger.info(f"🚀 Using Crunchyroll API via browser (account: {account_id[:8]}...)")

            # Fetch pages with strict limit enforcement using browser JavaScript
            for page in range(max_pages):
                logger.info(f"📄 Fetching page {page + 1}/{max_pages} via browser...")

                # Calculate pagination parameters
                start_param = page * page_size if page > 0 else 0

                # Make API request through browser JavaScript
                api_response = self.driver.execute_script("""
                    const accountId = arguments[0];
                    const pageSize = arguments[1];
                    const startParam = arguments[2];
                    const accessToken = arguments[3];

                    // Build the API URL
                    const apiUrl = `https://www.crunchyroll.com/content/v2/${accountId}/watch-history`;
                    const params = new URLSearchParams({
                        page_size: pageSize,
                        locale: 'en-US'
                    });

                    if (startParam > 0) {
                        params.append('start', startParam);
                    }

                    const fullUrl = `${apiUrl}?${params.toString()}`;

                    // Set up headers
                    const headers = {
                        'Accept': 'application/json',
                        'Accept-Language': 'en-US,en;q=0.9',
                        'sec-fetch-dest': 'empty',
                        'sec-fetch-mode': 'cors',
                        'sec-fetch-site': 'same-origin'
                    };

                    // Add authorization header if we have access token
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
                            return {
                                success: false,
                                status: response.status,
                                statusText: response.statusText,
                                url: fullUrl
                            };
                        }
                        return response.json().then(data => ({
                            success: true,
                            status: response.status,
                            data: data,
                            url: fullUrl
                        }));
                    })
                    .catch(error => ({
                        success: false,
                        error: error.message,
                        url: fullUrl
                    }));
                """, account_id, page_size, start_param, getattr(self, 'access_token', None))

                # Handle the response
                if not api_response or not api_response.get('success'):
                    status = api_response.get('status', 'unknown') if api_response else 'no response'
                    error_msg = api_response.get('error', api_response.get('statusText',
                                                                           'unknown error')) if api_response else 'no response'
                    logger.error(f"API page {page + 1} failed: {status} - {error_msg}")

                    if api_response and api_response.get('url'):
                        logger.debug(f"Failed URL: {api_response['url']}")

                    break

                data = api_response.get('data', {})
                items = data.get('data', [])

                if not items:
                    logger.info(f"No more items at page {page + 1}")
                    break

                # Parse episodes (with minimal logging)
                page_episodes = self._parse_api_response_clean(items)
                all_episodes.extend(page_episodes)

                logger.info(f"Page {page + 1}: {len(page_episodes)} valid episodes (total: {len(all_episodes)})")

                # Stop if we got fewer items than page_size (last page)
                if len(items) < page_size:
                    logger.info("Reached end of available data")
                    break

                # Rate limiting
                time.sleep(0.3)

            # Final summary only
            if all_episodes:
                self._log_clean_summary(all_episodes)
            else:
                logger.warning("No episodes retrieved from browser-based API")

            return all_episodes

        except Exception as e:
            logger.error(f"Browser-based API scraping failed: {e}")
            return []

    def _log_clean_summary(self, all_episodes: List[Dict[str, Any]]) -> None:
        """Clean, concise summary logging"""
        # Count unique series-seasons
        series_counts = {}
        for episode in all_episodes:
            series = episode.get('series_title', 'Unknown')
            season = episode.get('season', 1)
            key = f"{series} S{season}"
            series_counts[key] = series_counts.get(key, 0) + 1

        logger.info("=" * 50)
        logger.info(f"API RESULTS: {len(all_episodes)} episodes from {len(series_counts)} series-seasons")
        logger.info("=" * 50)

        # Show top series only (limit output)
        sorted_series = sorted(series_counts.items(), key=lambda x: x[1], reverse=True)

        for i, (series_season, count) in enumerate(sorted_series[:15], 1):  # Only show top 15
            logger.info(f"{i:2d}. {series_season}: {count} episodes")

        if len(sorted_series) > 15:
            remaining = len(sorted_series) - 15
            remaining_episodes = sum(count for _, count in sorted_series[15:])
            logger.info(f"... and {remaining} more series ({remaining_episodes} episodes)")

        logger.info("=" * 50)

    def _parse_api_response_clean(self, items: List[Dict]) -> List[Dict[str, Any]]:
        """Clean parsing with minimal debug output"""
        episodes = []
        skipped = 0

        for item in items:
            try:
                panel = item.get('panel', {})
                episode_metadata = panel.get('episode_metadata', {})

                series_title = episode_metadata.get('series_title', '').strip()
                episode_number = episode_metadata.get('episode_number', 0)

                # Skip invalid entries silently
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

        # Only log summary for this batch
        if skipped > 0:
            logger.debug(f"Skipped {skipped} invalid items from API response")

        return episodes

    def _log_api_results(self, all_episodes: List[Dict[str, Any]]) -> None:
        """Log comprehensive API scraping results"""
        unique_series = {}
        date_range = {"earliest": None, "latest": None}

        for episode in all_episodes:
            # Count episodes per series-season
            series = episode.get('series_title', 'Unknown')
            season = episode.get('season', 1)
            key = f"{series} (Season {season})"
            if key not in unique_series:
                unique_series[key] = 0
            unique_series[key] += 1

            # Track date range
            date_played = episode.get('date_played', '')
            if date_played:
                if not date_range["earliest"] or date_played < date_range["earliest"]:
                    date_range["earliest"] = date_played
                if not date_range["latest"] or date_played > date_range["latest"]:
                    date_range["latest"] = date_played

        logger.info(f"✅ API scraping complete: {len(all_episodes)} total episodes")
        logger.info(f"📚 Found {len(unique_series)} unique series-seasons")

        if date_range["earliest"] and date_range["latest"]:
            logger.info(f"📅 Date range: {date_range['earliest'][:10]} to {date_range['latest'][:10]}")

        # Show series breakdown
        logger.info("📊 Series breakdown:")
        for i, (series_season, count) in enumerate(sorted(unique_series.items()), 1):
            if i <= 20:  # Show first 20 series
                logger.info(f"  {i:2d}. {series_season}: {count} episodes")
            elif i == 21:
                remaining = len(unique_series) - 20
                logger.info(f"  ... and {remaining} more series")
                break

    def _parse_api_response(self, items: List[Dict]) -> List[Dict[str, Any]]:
        """Parse episodes from API response"""
        episodes = []

        for item in items:
            try:
                panel = item.get('panel', {})
                episode_metadata = panel.get('episode_metadata', {})

                # Extract data from structured API response
                series_title = episode_metadata.get('series_title', '')
                episode_title = panel.get('title', '')
                episode_number = episode_metadata.get('episode_number', 0)
                season_number = episode_metadata.get('season_number', 1)
                date_played = item.get('date_played', '')
                fully_watched = item.get('fully_watched', False)

                # Skip if missing essential data
                if not series_title or not episode_number:
                    logger.debug(f"Skipping API item - missing data: series='{series_title}', ep={episode_number}")
                    continue

                # Build clean episode data
                episode_data = {
                    'series_title': series_title,
                    'episode_title': episode_title,
                    'episode_number': episode_number,
                    'season': season_number,
                    'date_played': date_played,
                    'fully_watched': fully_watched,
                    'series_url': f"https://www.crunchyroll.com/series/{episode_metadata.get('series_slug_title', '')}",
                    'episode_url': f"https://www.crunchyroll.com/watch/{item.get('id', '')}",
                    'api_source': True
                }

                episodes.append(episode_data)

            except Exception as e:
                logger.debug(f"Error parsing API item: {e}")
                continue

        logger.debug(f"🔍 Parsed {len(episodes)} valid episodes from {len(items)} API items")
        return episodes

    def _extract_account_id(self) -> Optional[str]:
        """Extract account ID using multiple improved methods"""
        try:
            logger.info("🔍 Trying multiple methods to extract account ID...")

            # Method 1: Check page source for API calls or embedded data
            try:
                page_source = self.driver.page_source

                # Look for the API endpoint in script tags or embedded JSON
                patterns = [
                    r'content/v2/([a-f0-9\-]{36})/watch-history',  # UUID pattern
                    r'"account_id":\s*"([a-f0-9\-]{36})"',  # JSON account_id field
                    r'"accountId":\s*"([a-f0-9\-]{36})"',  # camelCase variant
                    r'/api/v2/user/([a-f0-9\-]{36})/',  # User API pattern
                ]

                for pattern in patterns:
                    matches = re.findall(pattern, page_source)
                    if matches:
                        account_id = matches[0]
                        logger.info(f"✅ Found account ID in page source: {account_id}")
                        return account_id

            except Exception as e:
                logger.debug(f"Page source method failed: {e}")

            # Method 2: Enhanced JavaScript extraction
            try:
                logger.debug("Trying enhanced JavaScript extraction...")
                account_data = self.driver.execute_script("""
                    // Method 2a: Check window objects
                    if (typeof window !== 'undefined') {
                        // Common state objects
                        var stateKeys = ['__INITIAL_STATE__', '__PRELOADED_STATE__', '__STATE__', 'INITIAL_STATE', 'app_state'];
                        for (var key of stateKeys) {
                            if (window[key] && typeof window[key] === 'object') {
                                var state = window[key];
                                // Look for user/account data
                                if (state.user && state.user.account_id) return state.user.account_id;
                                if (state.user && state.user.id) return state.user.id;
                                if (state.account && state.account.id) return state.account.id;
                                if (state.auth && state.auth.account_id) return state.auth.account_id;
                            }
                        }

                        // Method 2b: Check for API configuration
                        if (window.cxApiParams) {
                            if (window.cxApiParams.accountId) return window.cxApiParams.accountId;
                            if (window.cxApiParams.userId) return window.cxApiParams.userId;
                        }

                        if (window.appConfig && window.appConfig.accountId) {
                            return window.appConfig.accountId;
                        }
                    }

                    // Method 2c: Check localStorage and sessionStorage
                    try {
                        var storageKeys = ['user', 'account', 'auth', 'crunchyroll_user', 'profile'];
                        for (var storageType of [localStorage, sessionStorage]) {
                            for (var key of storageKeys) {
                                var data = storageType.getItem(key);
                                if (data) {
                                    var parsed = JSON.parse(data);
                                    if (parsed.account_id) return parsed.account_id;
                                    if (parsed.id) return parsed.id;
                                    if (parsed.user && parsed.user.account_id) return parsed.user.account_id;
                                }
                            }
                        }
                    } catch(e) {}

                    // Method 2d: Check meta tags
                    var metas = document.querySelectorAll('meta[name*="account"], meta[name*="user"], meta[property*="account"]');
                    for (var meta of metas) {
                        if (meta.content && meta.content.match(/^[a-f0-9\-]{36}$/)) {
                            return meta.content;
                        }
                    }

                    return null;
                """)

                if account_data:
                    logger.info(f"✅ Found account ID via JavaScript: {account_data}")
                    return str(account_data)

            except Exception as e:
                logger.debug(f"JavaScript extraction failed: {e}")

            # Method 3: Intercept network requests (more reliable)
            try:
                logger.debug("Trying network request interception...")

                # Enable logging if not already enabled
                try:
                    caps = self.driver.desired_capabilities
                    caps['goog:loggingPrefs'] = {'browser': 'ALL'}
                except:
                    pass

                # Refresh the page to capture fresh network requests
                logger.debug("Refreshing page to capture network requests...")
                self.driver.refresh()
                time.sleep(3)

                # Check browser console logs for network requests
                try:
                    logs = self.driver.get_log('browser')
                    for log in logs:
                        message = log.get('message', '')
                        if 'watch-history' in message or 'content/v2' in message:
                            # Look for account ID patterns in log messages
                            match = re.search(r'content/v2/([a-f0-9\-]{36})', message)
                            if match:
                                account_id = match.group(1)
                                logger.info(f"✅ Extracted account ID from browser logs: {account_id}")
                                return account_id
                except Exception as e:
                    logger.debug(f"Browser log method failed: {e}")

            except Exception as e:
                logger.debug(f"Network interception failed: {e}")

            # Method 4: Try to trigger an API call and capture it
            try:
                logger.debug("Attempting to trigger API call...")

                # Execute JavaScript to make a test API call or trigger one
                self.driver.execute_script("""
                    // Try to find and click a button that might trigger history loading
                    var buttons = document.querySelectorAll('button, a');
                    for (var btn of buttons) {
                        var text = btn.textContent.toLowerCase();
                        if (text.includes('load') || text.includes('more') || text.includes('history')) {
                            console.log('Triggering potential API call via:', text);
                            btn.click();
                            break;
                        }
                    }

                    // Or try to trigger scroll-based loading
                    window.scrollTo(0, 100);
                    setTimeout(() => window.scrollTo(0, 0), 500);
                """)

                time.sleep(2)

                # Check the page source again after triggering
                page_source = self.driver.page_source
                match = re.search(r'content/v2/([a-f0-9\-]{36})/watch-history', page_source)
                if match:
                    account_id = match.group(1)
                    logger.info(f"✅ Found account ID after triggering API call: {account_id}")
                    return account_id

            except Exception as e:
                logger.debug(f"API trigger method failed: {e}")

            # Method 5: Manual inspection helper
            logger.warning("⚠️ Could not automatically extract account ID")
            logger.info("💡 To find your account ID manually:")
            logger.info("   1. Open browser dev tools (F12)")
            logger.info("   2. Go to Network tab")
            logger.info("   3. Refresh the history page")
            logger.info("   4. Look for requests to 'watch-history'")
            logger.info("   5. The URL will contain your account ID")

            return None

        except Exception as e:
            logger.error(f"Error in account ID extraction: {e}")
            return None

    def _fallback_to_html_scraping(self, max_pages: int) -> List[Dict[str, Any]]:
        """Disabled HTML fallback to prevent log spam"""
        logger.warning("HTML fallback disabled - use API only")
        return []

    def _create_episode_key(self, episode: Dict[str, Any]) -> str:
        """Create a unique key for an episode to avoid duplicates"""
        series = episode.get('series_title', '')
        season = episode.get('season', 1)
        episode_num = episode.get('episode_number', 0)
        return f"{series}|S{season}|E{episode_num}"

    def _parse_with_improved_logic(self) -> List[Dict[str, Any]]:
        """Parse using improved Crunchyroll-specific logic with better logging"""
        try:
            soup = BeautifulSoup(self.driver.page_source, 'html.parser')
            history_items = []

            # Use improved Crunchyroll history card parsing
            cards_items = self._parse_crunchyroll_history_cards_improved(soup)
            if cards_items:
                history_items.extend(cards_items)

            # Convert to expected format and remove duplicates
            unique_items = self._remove_duplicates(history_items)
            episodes = self._convert_to_episodes_improved(unique_items)

            logger.info(f"✅ Parsed {len(episodes)} unique episodes from {len(cards_items)} raw items")
            return episodes

        except Exception as e:
            logger.error(f"Error in improved parser: {e}")
            return []

    def _parse_crunchyroll_history_cards_improved(self, soup) -> List[Dict[str, Any]]:
        """Parse Crunchyroll history cards with improved logic and logging"""
        history_items = []

        try:
            # Find history cards using working selectors
            cards = soup.find_all('div', class_='history-playable-card--qVdzv')
            logger.debug(f"Found {len(cards)} history-playable-card elements")

            # If no specific cards, try broader search
            if not cards:
                cards = soup.find_all('div', class_=lambda x: x and 'card' in x.lower())
                logger.debug(f"Found {len(cards)} general card elements")

            for i, card in enumerate(cards):
                try:
                    item = self._extract_from_history_card_improved(card)
                    if item and item.get('series_title'):
                        history_items.append(item)
                        # More detailed debug logging
                        series = item.get('series_title', 'Unknown')
                        episode_title = item.get('episode_title', 'No episode title')
                        season = item.get('season', 1)
                        raw_text = item.get('raw_text', '')

                        logger.debug(f"Card {i+1}: {series} S{season} - {episode_title}")
                        if raw_text:
                            logger.debug(f"  Raw text: {raw_text[:100]}...")
                    else:
                        logger.debug(f"Card {i+1}: Skipped - no valid data extracted")
                except Exception as e:
                    logger.debug(f"Error parsing card {i + 1}: {e}")
                    continue

            logger.info(f"Extracted {len(history_items)} valid items from {len(cards)} cards")

        except Exception as e:
            logger.error(f"Error parsing history cards: {e}")

        return history_items

    def _extract_from_history_card_improved(self, card) -> Optional[Dict[str, Any]]:
        """Extract data from a single history card with improved season/episode parsing"""
        if not card:
            return None

        try:
            # Get all text from the card for analysis
            all_text = card.get_text(strip=True)

            # Extract series title from series link
            series_title = ""
            series_link = card.select_one('a[href*="/series/"]')
            if series_link:
                series_title = series_link.get_text(strip=True)

            # Extract episode information
            episode_title = ""
            episode_link = card.select_one('a[href*="/watch/"]')
            if episode_link:
                episode_title = episode_link.get_text(strip=True)

            # If no episode link, try episode heading
            if not episode_title:
                episode_heading = card.select_one('h3')
                if episode_heading:
                    episode_title = episode_heading.get_text(strip=True)

            # Clean up series title
            if series_title:
                series_title = self._clean_series_title_improved(series_title)

            # Extract season and episode with improved patterns
            season_number, episode_number = self._extract_season_episode_improved(all_text, episode_title)

            # REMOVED: Episode conversion here - let sync_manager handle it with AniList data
            # The episode_number stays as parsed from Crunchyroll

            # Get URLs
            series_url = ""
            episode_url = ""

            if series_link:
                series_url = self._normalize_url(series_link.get('href', ''))

            if episode_link:
                episode_url = self._normalize_url(episode_link.get('href', ''))

            if series_title:
                return {
                    'series_title': series_title,
                    'episode_title': episode_title,
                    'season': season_number,
                    'episode_number': episode_number,
                    'series_url': series_url,
                    'episode_url': episode_url,
                    'raw_text': all_text,  # Keep for debugging
                    'timestamp': None,
                    'parsing_confidence': self._assess_parsing_confidence(season_number, episode_number, all_text)
                }

        except Exception as e:
            logger.debug(f"Error extracting card data: {e}")

        return None

    def _assess_parsing_confidence(self, season: int, episode: int, raw_text: str) -> str:
        """Assess confidence in parsing results"""
        confidence = "high"

        if season > 5:
            confidence = "low"  # Suspicious season number

        if episode > 30 and season > 1:
            confidence = "medium"  # Might be absolute episode number

        # Check if we found clear season/episode indicators
        if "S" + str(season) in raw_text and "E" + str(episode) in raw_text:
            confidence = "high"

        return confidence

    def _extract_season_episode_improved(self, all_text: str, episode_title: str) -> tuple[int, int]:
        """Extract season and episode numbers with improved pattern matching"""
        season_number = 1
        episode_number = 0

        # Combine both texts for analysis
        combined_text = f"{all_text} {episode_title}"

        logger.debug(f"Analyzing text for season/episode: '{combined_text[:100]}...'")

        # Try combined pattern first (S2 E20) - MOST RELIABLE
        combined_match = self.combined_pattern.search(combined_text)
        if combined_match:
            season_number = int(combined_match.group(1))
            episode_number = int(combined_match.group(2))
            logger.debug(f"Combined pattern match: S{season_number} E{episode_number}")
            return season_number, episode_number

        # Try season pattern (S2 or Season 2) - but be more careful
        season_matches = self.season_pattern.findall(combined_text)
        if season_matches:
            # Take the first reasonable season number
            for season_str in season_matches:
                try:
                    potential_season = int(season_str)
                    if 1 <= potential_season <= 5:  # Reasonable season range
                        season_number = potential_season
                        break
                except ValueError:
                    continue

        # Try episode pattern (E20) - but validate it makes sense
        episode_matches = self.episode_only_pattern.findall(combined_text)
        if episode_matches:
            # Take the first reasonable episode number
            for episode_str in episode_matches:
                try:
                    potential_episode = int(episode_str)
                    if 1 <= potential_episode <= 50:  # Reasonable episode range
                        episode_number = potential_episode
                        break
                except ValueError:
                    continue

        # IMPORTANT: Validate the combination makes sense
        if season_number > 5 and episode_number < 20:
            # This is likely a parsing error - probably should be season 1
            logger.warning(
                f"Suspicious parsing: S{season_number} E{episode_number} - likely parsing error, correcting to S1")
            season_number = 1

        logger.debug(f"Final result: S{season_number} E{episode_number}")
        return season_number, episode_number

    def _clean_series_title_improved(self, title: str) -> str:
        """Clean series title with improved logic"""
        if not title:
            return ""

        cleaned = title.strip()

        # Remove season/episode information that might be in the title
        patterns_to_remove = [
            r'\s*S\d+\s+E\d+.*$',  # S2 E20 and everything after
            r'\s*E\d+.*$',         # E20 and everything after
            r'\s*Episode\s*\d+.*$', # Episode 20 and everything after
            r'\s*Season\s+\d+.*$',  # Season 2 and everything after
        ]

        for pattern in patterns_to_remove:
            cleaned = re.sub(pattern, '', cleaned, flags=re.IGNORECASE)

        # Remove date information
        cleaned = re.sub(r'\s*\d+\s+(?:minute|hour|day|week|month|year)s?\s+ago.*$', '', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'\s*\d{1,2}/\d{1,2}/\d{4}.*$', '', cleaned)

        # Remove year indicators
        cleaned = re.sub(r'\s+\(\d{4}\)', '', cleaned)

        # Remove common unwanted text
        cleaned = re.sub(r'\s*(?:Watch|Continue|Resume|Play)\s*', '', cleaned, flags=re.IGNORECASE)

        # Clean whitespace
        cleaned = ' '.join(cleaned.split())

        return cleaned

    def _convert_to_episodes_improved(self, items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Convert items to episode format with improved validation and logging"""
        episodes = []
        skipped_count = 0

        for item in items:
            series_title = item.get('series_title', '')
            episode_title = item.get('episode_title', '')
            episode_number = item.get('episode_number', 0)
            season = item.get('season', 1)

            if not series_title:
                logger.debug(f"Skipping item - no series title: {item}")
                skipped_count += 1
                continue

            # Skip if no episode number was detected
            if episode_number <= 0:
                # Check if it's a movie/special
                if self._is_movie_or_special(episode_title):
                    logger.debug(f"Skipping movie/special: {series_title} - {episode_title}")
                    skipped_count += 1
                    continue
                else:
                    logger.warning(f"No episode number found for: {series_title} - {episode_title}")
                    skipped_count += 1
                    continue

            episodes.append({
                'series_title': series_title,
                'episode_title': episode_title,
                'episode_number': episode_number,
                'season': season,
                'series_url': item.get('series_url', ''),
                'episode_url': item.get('episode_url', '')
            })

        logger.info(f"Converted {len(episodes)} valid episodes, skipped {skipped_count} items")
        return episodes

    def _is_movie_or_special(self, text: str) -> bool:
        """Check if content is movie/special"""
        if not text:
            return False

        movie_indicators = [
            'movie', 'film', 'compilation', 'special', 'ova', 'ona',
            'recap', 'summary', 'theater', 'theatrical'
        ]

        text_lower = text.lower()
        return any(indicator in text_lower for indicator in movie_indicators)

    def _normalize_url(self, url: str) -> str:
        """Normalize URL to full format"""
        if not url:
            return ""

        if url.startswith('http'):
            return url
        elif url.startswith('/'):
            return f"https://www.crunchyroll.com{url}"
        else:
            return f"https://www.crunchyroll.com/{url}"

    def _remove_duplicates(self, items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Remove duplicate items"""
        seen = set()
        unique_items = []

        for item in items:
            if not isinstance(item, dict):
                continue

            series_title = item.get('series_title', '').strip()
            episode_number = item.get('episode_number', 0)
            season = item.get('season', 1)

            # Create identifier based on series, season, episode
            identifier = f"{series_title}|S{season}|E{episode_number}"

            if identifier not in seen and series_title:
                seen.add(identifier)
                unique_items.append(item)

        logger.info(f"Removed {len(items) - len(unique_items)} duplicates, kept {len(unique_items)} unique items")
        return unique_items

    def _try_cached_auth(self) -> bool:
        """Try to use cached authentication"""
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

                    if cookie.get('secure') is not None:
                        cookie_data['secure'] = cookie.get('secure')
                    if cookie.get('httpOnly') is not None:
                        cookie_data['httpOnly'] = cookie.get('httpOnly')

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
        """Verify authentication"""
        try:
            logger.info("🔍 Verifying authentication...")

            self.driver.get("https://www.crunchyroll.com/account")
            time.sleep(3)

            current_url = self.driver.current_url.lower()
            if "login" in current_url:
                logger.info("❌ Redirected to login page - not authenticated")
                return False

            page_source = self.driver.page_source.lower()
            logged_in_indicators = [
                "account", "profile", "subscription", "settings",
                "logout", "sign out", "premium"
            ]

            indicators_found = [indicator for indicator in logged_in_indicators if indicator in page_source]

            if indicators_found:
                logger.info(f"✅ Authentication verified - found indicators: {indicators_found}")
                return True
            else:
                logger.info("❌ No logged-in indicators found")
                return False

        except Exception as e:
            logger.error(f"Error verifying authentication: {e}")
            return False

    def _authenticate_with_selenium(self) -> bool:
        """Authenticate using Selenium"""
        try:
            logger.info("🌐 Authenticating with Selenium...")

            self.driver.get("https://www.crunchyroll.com/login")

            self._handle_cloudflare_challenge()

            wait = WebDriverWait(self.driver, 30)

            # Find email field
            email_field = None
            email_selectors = ["#email", "input[name='email']", "input[type='email']"]

            for selector in email_selectors:
                try:
                    email_field = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, selector)))
                    if email_field.is_displayed():
                        break
                except TimeoutException:
                    continue

            if not email_field:
                logger.error("❌ Could not find email field")
                self._save_debug_html("login_no_email.html")
                return False

            # Find password field
            password_field = None
            password_selectors = ["#password", "input[name='password']", "input[type='password']"]

            for selector in password_selectors:
                try:
                    password_field = self.driver.find_element(By.CSS_SELECTOR, selector)
                    if password_field.is_displayed():
                        break
                except NoSuchElementException:
                    continue

            if not password_field:
                logger.error("❌ Could not find password field")
                self._save_debug_html("login_no_password.html")
                return False

            # Find submit button
            submit_button = None
            submit_selectors = [
                "button[type='submit']",
                "input[type='submit']",
                "button:contains('Sign In')",
                "button:contains('Log In')",
                ".login-button"
            ]

            for selector in submit_selectors:
                try:
                    submit_button = self.driver.find_element(By.CSS_SELECTOR, selector)
                    if submit_button.is_displayed():
                        break
                except NoSuchElementException:
                    continue

            if not submit_button:
                logger.error("❌ Could not find submit button")
                self._save_debug_html("login_no_submit.html")
                return False

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

            current_url = self.driver.current_url.lower()
            if "login" in current_url:
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
        """Authenticate using FlareSolverr"""
        try:

            logger.info("🔥 Authenticating with FlareSolverr...")

            client = FlareSolverrClient(self.flaresolverr_url)

            if not client.create_session():
                return False

            response = client.solve_challenge("https://www.crunchyroll.com/login")
            if not response:
                return False

            form_data = self._extract_login_form_data(response.get('response', ''))
            form_data['email'] = self.email
            form_data['password'] = self.password

            login_response = client.solve_challenge(
                url="https://www.crunchyroll.com/login",
                cookies=response.get('cookies', []),
                post_data=form_data
            )

            if login_response and "login" not in login_response.get('url', '').lower():
                self.driver.get("https://www.crunchyroll.com")
                time.sleep(2)

                cookies = login_response.get('cookies', [])
                for cookie in cookies:
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

    def _setup_driver(self) -> None:
        """Setup Chrome driver"""
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

    def _handle_cloudflare_challenge(self, max_wait: int = 60) -> bool:
        """Handle Cloudflare challenge"""
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

    def _wait_for_page_load(self, timeout: int = 30) -> bool:
        """Wait for page to load"""
        try:
            self._handle_cloudflare_challenge()

            wait = WebDriverWait(self.driver, timeout)
            wait.until(lambda d: d.execute_script("return document.readyState") == "complete")

            return True

        except TimeoutException:
            logger.error("⏱️ Page load timeout")
            return False

    def _extract_login_form_data(self, html_content: str) -> Dict[str, str]:
        """Extract form data from login page"""
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
        """Cache authentication"""
        try:
            if self.driver:
                cookies = self.driver.get_cookies()
                self.auth_cache.save_crunchyroll_auth(cookies=cookies)
                logger.debug("✅ Authentication cached")
        except Exception as e:
            logger.error(f"Error caching authentication: {e}")

    def _save_debug_html(self, filename: str) -> None:
        """Save HTML to file ONLY - NO LOGGING OF CONTENT"""
        try:
            cache_dir = Path('_cache')
            cache_dir.mkdir(exist_ok=True)

            filepath = cache_dir / filename
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(self.driver.page_source)

            # Only log the filepath - NEVER the content
            logger.debug(f"Debug HTML saved: {filepath.name}")

        except Exception as e:
            logger.error(f"Error saving debug HTML: {e}")

    def cleanup(self) -> None:
        """Clean up resources"""
        if self.driver:
            try:
                self.driver.quit()
                self.driver = None
                logger.debug("Browser closed")
            except Exception as e:
                logger.error(f"Error closing browser: {e}")

class EpisodeNumberConverter:
    """Convert absolute episode numbers to per-season episode numbers"""

    def __init__(self):
        # Common anime season lengths - most anime have 12-13 episodes per season
        self.typical_season_lengths = {
            1: 12,  # Default for season 1
            2: 12,  # Default for season 2
            3: 12,  # Default for season 3
            4: 12,  # Default for season 4+
        }

        # Known anime with non-standard season lengths
        self.known_season_lengths = {
            "The Rising of the Shield Hero": {1: 25, 2: 13, 3: 12, 4: 12},
            "DAN DA DAN": {1: 12, 2: 12},
            "Dandadan": {1: 12, 2: 12},
            "Kaiju No. 8": {1: 12, 2: 12},
            "Tower of God": {1: 13, 2: 13},
            "That Time I Got Reincarnated as a Slime": {1: 24, 2: 24, 3: 24}
        }

    def convert_episode_number(self, series_title: str, season: int, episode_number: int,
                               logger) -> int:
        """Convert absolute episode number to per-season episode number if needed"""

        # If it's season 1, episode number should be correct as-is
        if season == 1:
            return episode_number

        # Check if this looks like an absolute episode number
        if self._looks_like_absolute_episode(series_title, season, episode_number):
            converted = self._convert_absolute_to_per_season(series_title, season, episode_number,
                                                             logger)
            if converted != episode_number:
                logger.info(
                    f"🔄 Converted {series_title} S{season} E{episode_number} → E{converted} (absolute→per-season)")
            return converted

        # Episode number looks reasonable for the season, return as-is
        return episode_number

    def _looks_like_absolute_episode(self, series_title: str, season: int, episode_number: int) -> bool:
        """Determine if episode number looks like an absolute number vs per-season"""

        # For season 1, it's always per-season
        if season == 1:
            return False

        # If episode number is very high for later seasons, likely absolute
        # Most anime seasons are 12-13 episodes, so E20+ in S2+ is suspicious
        if season >= 2 and episode_number > 15:
            return True

        # For known long-running shows in later seasons
        if season >= 3 and episode_number > 20:
            return True

        return False

    def _convert_absolute_to_per_season(self, series_title: str, season: int, absolute_episode: int,
                                        logger) -> int:
        """Convert absolute episode number to per-season episode number"""

        # Get season lengths for this series
        if series_title in self.known_season_lengths:
            season_lengths = self.known_season_lengths[series_title]
        else:
            # Use typical lengths
            season_lengths = self.typical_season_lengths

        # Calculate episodes before this season
        episodes_before = 0
        for s in range(1, season):
            if s in season_lengths:
                episodes_before += season_lengths[s]
            else:
                episodes_before += self.typical_season_lengths.get(s, 12)

        # Convert absolute to per-season
        per_season_episode = absolute_episode - episodes_before

        # Sanity check - if result is <= 0, something went wrong
        if per_season_episode <= 0:
            logger.warning(
                f"⚠️ Episode conversion resulted in {per_season_episode} for {series_title} S{season} E{absolute_episode}")
            return absolute_episode  # Return original if conversion failed

        # Sanity check - if result is way too high, might not be absolute
        expected_season_length = season_lengths.get(season, 12)
        if per_season_episode > expected_season_length + 5:  # Allow some flexibility
            logger.debug(
                f"🤔 Converted episode {per_season_episode} seems high for {series_title} S{season} (expected ~{expected_season_length})")

        return per_season_episode
