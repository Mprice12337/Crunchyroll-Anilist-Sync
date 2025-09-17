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

        self.episode_converter = EpisodeNumberConverter()

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
        """Get watch history with improved parsing logic"""
        logger.info(f"📚 Scraping watch history (max {max_pages} pages = {max_pages * 2} scrolls)...")

        if not self.is_authenticated:
            logger.error("Not authenticated! Call authenticate() first.")
            return []

        # Navigate to history page
        logger.info("🧭 Navigating to history page...")
        self.driver.get("https://www.crunchyroll.com/history")
        time.sleep(5)

        current_url = self.driver.current_url
        logger.info(f"Current URL: {current_url}")

        if "history" not in current_url.lower():
            logger.error(f"❌ Not on history page! Current URL: {current_url}")
            self._save_debug_html("wrong_page.html")
            return []

        if not self._wait_for_page_load():
            logger.error("Failed to load history page properly")
            return []

        # Save initial page
        self._save_debug_html("history_page_loaded.html")

        # Scrape with improved logic
        return self._scrape_with_improved_parser(max_pages)

    def _scrape_with_improved_parser(self, max_pages: int) -> List[Dict[str, Any]]:
        """Scrape using improved parser logic with better logging"""
        all_episodes = []

        try:
            last_count = 0
            scroll_attempts = 0
            max_scrolls = max_pages * 2

            logger.info(f"🔄 Starting scraping (max {max_scrolls} scrolls for {max_pages} pages)")

            while scroll_attempts < max_scrolls:
                # Scroll to bottom
                self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(3)

                # Parse current episodes using improved logic
                current_episodes = self._parse_with_improved_logic()

                logger.info(f"📺 Scroll {scroll_attempts + 1}: Found {len(current_episodes)} total episodes")

                # Check if we got new episodes
                if len(current_episodes) > last_count:
                    logger.info(f"✅ New episodes found: {len(current_episodes) - last_count}")
                    last_count = len(current_episodes)
                    all_episodes = current_episodes
                else:
                    logger.info("🏁 No new episodes found, stopping pagination")
                    break

                scroll_attempts += 1
                time.sleep(1)

            # Log final results with more detail
            unique_series = set()
            for episode in all_episodes:
                series = episode.get('series_title', 'Unknown')
                season = episode.get('season', 1)
                unique_series.add(f"{series} (Season {season})")

            logger.info(f"✅ Scraping complete: {len(all_episodes)} total episodes")
            logger.info(f"📚 Unique series-seasons found: {len(unique_series)}")

            # Log first few unique series for verification
            for i, series_season in enumerate(sorted(list(unique_series))[:5], 1):
                logger.info(f"  {i}. {series_season}")
            if len(unique_series) > 5:
                logger.info(f"  ... and {len(unique_series) - 5} more series-seasons")

            return all_episodes

        except Exception as e:
            logger.error(f"Error during scraping: {e}")
            return all_episodes

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

            # NEW: Convert absolute episode numbers to per-season if needed
            if series_title and episode_number > 0:
                original_episode = episode_number
                episode_number = self.episode_converter.convert_episode_number(
                    series_title, season_number, episode_number, logger
                )

                if episode_number != original_episode:
                    logger.debug(
                        f"Episode conversion: {series_title} S{season_number} E{original_episode}→E{episode_number}")

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
                    'timestamp': None
                }

        except Exception as e:
            logger.debug(f"Error extracting card data: {e}")

        return None

    def _extract_season_episode_improved(self, all_text: str, episode_title: str) -> tuple[int, int]:
        """Extract season and episode numbers with improved pattern matching"""
        season_number = 1
        episode_number = 0

        # Combine both texts for analysis
        combined_text = f"{all_text} {episode_title}"

        logger.debug(f"Analyzing text for season/episode: '{combined_text[:100]}...'")

        # Try combined pattern first (S2 E20)
        combined_match = self.combined_pattern.search(combined_text)
        if combined_match:
            season_number = int(combined_match.group(1))
            episode_number = int(combined_match.group(2))
            logger.debug(f"Combined pattern match: S{season_number} E{episode_number}")
            return season_number, episode_number

        # Try season pattern (S2 or Season 2)
        season_match = self.season_pattern.search(combined_text)
        if season_match:
            season_number = int(season_match.group(1))
            logger.debug(f"Season pattern match: S{season_number}")

        # Try episode pattern (E20)
        episode_match = self.episode_only_pattern.search(combined_text)
        if episode_match:
            episode_number = int(episode_match.group(1))
            logger.debug(f"Episode pattern match: E{episode_number}")

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
            from flaresolverr_client import FlareSolverrClient

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
