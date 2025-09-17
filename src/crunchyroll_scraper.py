"""
Fixed Crunchyroll scraper with working parser logic and NO HTML logging
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
    """Fixed Crunchyroll scraper with working parser and no HTML logging"""

    def __init__(self, email: str, password: str, headless: bool = True,
                 flaresolverr_url: Optional[str] = None):
        self.email = email
        self.password = password
        self.headless = headless
        self.flaresolverr_url = flaresolverr_url
        self.driver = None
        self.auth_cache = AuthCache()
        self.is_authenticated = False

        # Working episode and season patterns
        self.episode_pattern = re.compile(r'(?:E|Episode|ep\.?|e)\s*(\d+)', re.IGNORECASE)
        self.season_pattern = re.compile(r'season\s*(\d+)', re.IGNORECASE)

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
        """Get watch history with working parser logic"""
        logger.info(f"📚 Scraping watch history (max {max_pages} pages)...")

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

        # Scrape with working logic
        return self._scrape_with_working_parser(max_pages)

    def _scrape_with_working_parser(self, max_pages: int) -> List[Dict[str, Any]]:
        """Scrape using the working parser logic"""
        all_episodes = []

        try:
            last_count = 0
            scroll_attempts = 0
            max_scrolls = max_pages * 2

            logger.info(f"🔄 Starting scraping (max {max_scrolls} scrolls)")

            while scroll_attempts < max_scrolls:
                # Scroll to bottom
                self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(3)

                # Parse current episodes using working logic
                current_episodes = self._parse_with_working_logic()

                # Check if we got new episodes
                if len(current_episodes) > last_count:
                    logger.info(f"📺 Found {len(current_episodes)} total episodes (scroll {scroll_attempts + 1})")
                    last_count = len(current_episodes)
                    all_episodes = current_episodes
                else:
                    logger.info("🏁 No new episodes found, stopping pagination")
                    break

                scroll_attempts += 1
                time.sleep(1)

            logger.info(f"✅ Scraping complete: {len(all_episodes)} total episodes")
            return all_episodes

        except Exception as e:
            logger.error(f"Error during scraping: {e}")
            return all_episodes

    def _parse_with_working_logic(self) -> List[Dict[str, Any]]:
        """Parse using working Crunchyroll-specific logic"""
        try:
            soup = BeautifulSoup(self.driver.page_source, 'html.parser')
            history_items = []

            # Use the working Crunchyroll history card parsing
            cards_items = self._parse_crunchyroll_history_cards(soup)
            if cards_items:
                history_items.extend(cards_items)

            # Convert to expected format and remove duplicates
            unique_items = self._remove_duplicates(history_items)
            episodes = self._convert_to_episodes(unique_items)

            logger.info(f"✅ Parsed {len(episodes)} unique episodes")
            return episodes

        except Exception as e:
            logger.error(f"Error in working parser: {e}")
            return []

    def _parse_crunchyroll_history_cards(self, soup) -> List[Dict[str, Any]]:
        """Parse Crunchyroll history cards using working logic"""
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
                    item = self._extract_from_history_card(card)
                    if item and item.get('series_title'):
                        history_items.append(item)
                        logger.debug(f"Card {i+1}: {item['series_title']} - {item.get('episode_title', 'No episode title')}")
                except Exception as e:
                    logger.debug(f"Error parsing card {i + 1}: {e}")
                    continue

            logger.info(f"Extracted {len(history_items)} items from history cards")

        except Exception as e:
            logger.error(f"Error parsing history cards: {e}")

        return history_items

    def _extract_from_history_card(self, card) -> Optional[Dict[str, Any]]:
        """Extract data from a single history card using working logic"""
        if not card:
            return None

        try:
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
                series_title = self._clean_series_title(series_title)

            # Extract season from context
            all_text = card.get_text()
            season_number = self._extract_season_from_text(all_text)

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
                    'series_url': series_url,
                    'episode_url': episode_url,
                    'timestamp': None
                }

        except Exception as e:
            logger.debug(f"Error extracting card data: {e}")

        return None

    def _clean_series_title(self, title: str) -> str:
        """Clean series title using working logic"""
        if not title:
            return ""

        cleaned = title.strip()

        # Remove episode information
        cleaned = re.sub(r'\s*E\d+.*$', '', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'\s*Episode\s*\d+.*$', '', cleaned, flags=re.IGNORECASE)

        # Remove date information
        cleaned = re.sub(r'\s*\d+\s+(?:minute|hour|day|week|month|year)s?\s+ago.*$', '', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'\s*\d{1,2}/\d{1,2}/\d{4}.*$', '', cleaned)

        # Remove season from title if redundant
        cleaned = re.sub(r'\s+Season\s+\d+', '', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'\s+S\d+', '', cleaned)

        # Remove year indicators
        cleaned = re.sub(r'\s+\(\d{4}\)', '', cleaned)

        # Remove common unwanted text
        cleaned = re.sub(r'\s*(?:Watch|Continue|Resume|Play)\s*', '', cleaned, flags=re.IGNORECASE)

        # Clean whitespace
        cleaned = ' '.join(cleaned.split())

        return cleaned

    def _extract_season_from_text(self, text: str) -> int:
        """Extract season number from text"""
        if not text:
            return 1

        season_match = self.season_pattern.search(text)
        if season_match:
            try:
                return int(season_match.group(1))
            except ValueError:
                pass

        return 1

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
            episode_title = item.get('episode_title', '').strip()
            identifier = f"{series_title}|{episode_title}"

            if identifier not in seen and series_title:
                seen.add(identifier)
                unique_items.append(item)

        return unique_items

    def _convert_to_episodes(self, items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Convert items to episode format with episode numbers"""
        episodes = []

        for item in items:
            series_title = item.get('series_title', '')
            episode_title = item.get('episode_title', '')

            if not series_title:
                continue

            # Extract episode number
            episode_number = self._extract_episode_number(episode_title)

            if episode_number > 0:
                episodes.append({
                    'series_title': series_title,
                    'episode_title': episode_title,
                    'episode_number': episode_number,
                    'season': item.get('season', 1),
                    'series_url': item.get('series_url', ''),
                    'episode_url': item.get('episode_url', '')
                })

        return episodes

    def _extract_episode_number(self, episode_text: str) -> int:
        """Extract episode number using working logic"""
        if not episode_text:
            return 0

        # Skip movies/specials
        if self._is_movie_or_special(episode_text):
            return 0

        episode_match = self.episode_pattern.search(episode_text)
        if episode_match:
            try:
                return int(episode_match.group(1))
            except ValueError:
                pass

        return 0

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

    # Authentication methods (keep existing logic)
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