"""
Fixed Crunchyroll scraper with integrated working parser logic
"""

import re
import time
import logging
from typing import List, Dict, Any, Optional
from pathlib import Path
from collections import defaultdict

import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from bs4 import BeautifulSoup

from cache_manager import AuthCache

logger = logging.getLogger(__name__)

class CrunchyrollScraper:
    """Crunchyroll scraper with integrated working parser logic"""

    def __init__(self, email: str, password: str, headless: bool = True,
                 flaresolverr_url: Optional[str] = None):
        self.email = email
        self.password = password
        self.headless = headless
        self.flaresolverr_url = flaresolverr_url
        self.driver = None
        self.auth_cache = AuthCache()
        self.is_authenticated = False

        # Episode parsing patterns from working parser
        self.episode_pattern = re.compile(r'(?:E|Episode|ep\.?|e)\s*(\d+)', re.IGNORECASE)
        self.season_pattern = re.compile(r'season\s*(\d+)', re.IGNORECASE)

    def authenticate(self) -> bool:
        """Authenticate with Crunchyroll with proper verification"""
        logger.info("🔐 Authenticating with Crunchyroll...")

        # Setup driver first
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
            # Try FlareSolverr first for Cloudflare bypass
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
        """Get watch history from Crunchyroll using working parser logic"""
        logger.info(f"📚 Scraping watch history (max {max_pages} pages)...")

        if not self.is_authenticated:
            logger.error("Not authenticated! Call authenticate() first.")
            return []

        # Navigate to history page with verification
        logger.info("Navigating to history page...")
        self.driver.get("https://www.crunchyroll.com/history")

        # Wait and verify we're on the right page
        time.sleep(5)

        current_url = self.driver.current_url
        logger.info(f"Current URL: {current_url}")

        # Check if we were redirected away from history page
        if "history" not in current_url.lower():
            logger.error(f"❌ Not on history page! Current URL: {current_url}")
            return []

        # Handle any Cloudflare challenges
        if not self._wait_for_page_load():
            logger.error("Failed to load history page properly")
            return []

        # Save initial page for debugging (but don't log content)
        self._save_debug_html("history_page_initial.html")

        # Look for history content
        if not self._verify_history_page_content():
            logger.error("❌ History page doesn't contain expected content")
            return []

        # Scrape episodes with pagination using working parser
        return self._scrape_episodes_with_working_parser(max_pages)

    def _scrape_episodes_with_working_parser(self, max_pages: int) -> List[Dict[str, Any]]:
        """Scrape episodes using the working parser logic"""
        all_episodes = []

        try:
            last_count = 0
            scroll_attempts = 0
            max_scrolls = max_pages * 2

            logger.info(f"🔄 Starting pagination scraping (max {max_scrolls} scrolls)")

            while scroll_attempts < max_scrolls:
                # Scroll to bottom
                self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(3)

                # Parse current episodes using working parser
                current_episodes = self._parse_history_with_working_logic()

                # Check if we got new episodes
                if len(current_episodes) > last_count:
                    logger.info(f"📺 Found {len(current_episodes)} total episodes (scroll {scroll_attempts + 1})")
                    last_count = len(current_episodes)
                    all_episodes = current_episodes
                else:
                    logger.info("🏁 No new episodes found, stopping pagination")
                    break

                scroll_attempts += 1

                # Save intermediate results every 5 scrolls
                if scroll_attempts % 5 == 0:
                    self._save_debug_html(f"history_page_scroll_{scroll_attempts}.html")

                time.sleep(1)

            logger.info(f"✅ Pagination complete: {len(all_episodes)} total episodes")
            return all_episodes

        except Exception as e:
            logger.error(f"Error during episode scraping: {e}")
            return all_episodes

    def _parse_history_with_working_logic(self) -> List[Dict[str, Any]]:
        """Parse history using the working parser logic"""
        try:
            soup = BeautifulSoup(self.driver.page_source, 'html.parser')
            history_items = []

            # Try the specific Crunchyroll history card parsing first
            try:
                cards_items = self._parse_history_cards(soup)
                if cards_items:
                    history_items.extend(cards_items)
                    logger.debug(f"Found {len(cards_items)} items from history cards")
            except Exception as e:
                logger.debug(f"History cards parsing failed: {e}")

            # If no items found, try fallback strategies
            if not history_items:
                strategies = [
                    self._parse_dom_elements,
                    self._extract_from_broad_search
                ]

                for strategy in strategies:
                    try:
                        items = strategy(soup)
                        if items and isinstance(items, list):
                            history_items.extend(items)
                            logger.info(f"Found {len(items)} items using {strategy.__name__}")
                            break
                    except Exception as e:
                        logger.debug(f"Strategy {strategy.__name__} failed: {e}")
                        continue

            # Remove duplicates and convert to expected format
            unique_items = self._remove_duplicate_items(history_items)
            converted_items = self._convert_to_episode_format(unique_items)

            logger.debug(f"Converted {len(unique_items)} unique items to {len(converted_items)} episodes")
            return converted_items

        except Exception as e:
            logger.error(f"Error parsing history with working logic: {e}")
            return []

    def _parse_history_cards(self, soup):
        """Parse history cards from the specific Crunchyroll HTML structure"""
        history_items = []

        # Find all history playable cards (from working parser)
        cards = soup.find_all('div', class_='history-playable-card--qVdzv')
        logger.debug(f"Found {len(cards)} history-playable-card elements")

        # If no specific cards found, try broader card search
        if not cards:
            cards = soup.find_all('div', class_=lambda x: x and 'card' in x.lower())
            logger.debug(f"Found {len(cards)} general card elements")

        for i, card in enumerate(cards):
            try:
                item = self._extract_card_data(card)
                if item and item.get('series_title'):
                    history_items.append(item)
                    if i < 3:  # Log first few for debugging
                        logger.debug(f"Card {i+1}: {item}")
            except Exception as e:
                logger.debug(f"Error parsing card {i + 1}: {e}")
                continue

        logger.info(f"Found {len(history_items)} items from history cards")
        return history_items

    def _extract_card_data(self, card):
        """Extract data from a history card element (from working parser)"""
        if not card:
            return {}

        try:
            # Extract series title from the series link
            series_title = ""
            series_link = card.select_one('a[href*="/series/"]')
            if series_link:
                series_title = series_link.get_text(strip=True)

            # Extract episode information - try multiple approaches
            episode_title = ""

            # First, try to find the episode link
            episode_link = card.select_one('a[href*="/watch/"]')
            if episode_link:
                episode_title = episode_link.get_text(strip=True)

            # If no episode link, try to find episode title in h3 elements
            if not episode_title:
                episode_heading = card.select_one('h3')
                if episode_heading:
                    episode_title = episode_heading.get_text(strip=True)

            # If still no episode title, look for any text with episode patterns
            if not episode_title:
                all_text = card.get_text()
                lines = [line.strip() for line in all_text.split('\n') if line.strip()]
                for line in lines:
                    if self.episode_pattern.search(line):
                        episode_title = line
                        break

            # Clean up the series title
            series_title = self._clean_extracted_series_title(series_title)

            if not series_title:
                return {}

            result = {
                'series_title': series_title,
                'episode_title': episode_title,
                'timestamp': None
            }

            return result

        except Exception as e:
            logger.debug(f"Error extracting card data: {e}")
            return {}

    def _parse_dom_elements(self, soup):
        """Parse DOM elements to find history items using Crunchyroll-specific selectors"""
        history_items = []

        # Crunchyroll-specific selectors
        selectors = [
            'div[data-testid*="history"]',
            'div[class*="history"]',
            'div[class*="playable-card"]',
            'a[href*="/watch/"]',
            'div[class*="episode"]',
            '.playable-card'
        ]

        for selector in selectors:
            try:
                elements = soup.select(selector)
                logger.debug(f"Selector '{selector}' found {len(elements)} elements")

                for element in elements:
                    item = self._extract_item_from_element(element)
                    if item and item.get('series_title'):
                        history_items.append(item)

                if history_items:
                    break  # Use first successful selector

            except Exception as e:
                logger.debug(f"Error with selector {selector}: {e}")
                continue

        return history_items

    def _extract_item_from_element(self, element):
        """Extract history item data from a DOM element"""
        if not element:
            return {}

        try:
            # Look for links that might contain titles
            links = element.find_all('a')
            series_title = ""
            episode_title = ""

            for link in links:
                link_text = link.get_text(strip=True)
                href = link.get('href', '')

                if '/series/' in href and not series_title:
                    series_title = self._clean_extracted_series_title(link_text)
                elif '/watch/' in href and not episode_title:
                    episode_title = link_text

            # If no links found, try to parse from text content
            if not series_title:
                text_content = element.get_text(strip=True)
                lines = [line.strip() for line in text_content.split('\n') if line.strip()]

                # Look for the series title (usually the first substantial line)
                for line in lines:
                    if len(line) > 5 and not self.episode_pattern.search(line):
                        series_title = self._clean_extracted_series_title(line)
                        break

                # Look for episode title
                for line in lines:
                    if self.episode_pattern.search(line):
                        episode_title = line
                        break

            if series_title:
                return {
                    'series_title': series_title,
                    'episode_title': episode_title,
                    'timestamp': None
                }

        except Exception as e:
            logger.debug(f"Error extracting from element: {e}")

        return {}

    def _extract_from_broad_search(self, soup):
        """Broad search for any text that might contain episode information"""
        history_items = []

        try:
            # Look for any text that matches episode patterns
            all_text = soup.get_text()
            lines = [line.strip() for line in all_text.split('\n') if line.strip()]

            current_series = ""

            for line in lines:
                # If this line has episode pattern, try to find associated series
                if self.episode_pattern.search(line):
                    episode_info = self._extract_detailed_episode_info(line)
                    if episode_info['episode_number'] > 0:
                        # Use the most recent series title we found
                        series_title = current_series if current_series else "Unknown Series"

                        history_items.append({
                            'series_title': series_title,
                            'episode_title': line,
                            'timestamp': None
                        })
                else:
                    # This might be a series title
                    cleaned = self._clean_extracted_series_title(line)
                    if len(cleaned) > 5:  # Reasonable series title length
                        current_series = cleaned

        except Exception as e:
            logger.debug(f"Error in broad search: {e}")

        return history_items[:20]  # Limit to prevent too many false positives

    def _convert_to_episode_format(self, history_items):
        """Convert history items to the expected episode format for sync_manager"""
        episodes = []

        for item in history_items:
            series_title = item.get('series_title', '')
            episode_title = item.get('episode_title', '')

            if not series_title:
                continue

            # Extract episode number from episode title
            episode_info = self._extract_detailed_episode_info(episode_title)
            episode_number = episode_info.get('episode_number', 0)

            if episode_number > 0:
                episodes.append({
                    'series_title': series_title,
                    'episode_title': episode_title,
                    'episode_number': episode_number,
                    'series_url': '',
                    'episode_url': ''
                })

        return episodes

    def _clean_extracted_series_title(self, series_title):
        """Clean series title extracted from HTML (from working parser)"""
        if not series_title:
            return ""

        cleaned = series_title.strip()

        # Remove episode information if it got mixed in
        cleaned = re.sub(r'\s*E\d+.*$', '', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'\s*Episode\s*\d+.*$', '', cleaned, flags=re.IGNORECASE)

        # Remove date information
        cleaned = re.sub(r'\s*\d+\s+(?:minute|hour|day|week|month|year)s?\s+ago.*$', '', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'\s*\d{1,2}/\d{1,2}/\d{4}.*$', '', cleaned)

        # Remove season indicators from title
        cleaned = re.sub(r'\s+Season\s+\d+', '', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'\s+S\d+', '', cleaned)

        # Remove year indicators
        cleaned = re.sub(r'\s+\(\d{4}\)', '', cleaned)

        # Remove common unwanted text
        cleaned = re.sub(r'\s*(?:Watch|Continue|Resume|Play)\s*', '', cleaned, flags=re.IGNORECASE)

        # Remove extra whitespace and normalize
        cleaned = ' '.join(cleaned.split())

        return cleaned

    def _extract_detailed_episode_info(self, episode_text):
        """Extract detailed episode information (from working parser)"""
        if not episode_text:
            return {'episode_number': 0, 'clean_title': '', 'season': 1, 'is_movie': False}

        episode_info = {
            'episode_number': 0,
            'clean_title': episode_text,
            'season': 1,
            'is_movie': self._is_movie_or_special(episode_text)
        }

        # If it's a movie/special, don't try to extract episode number
        if episode_info['is_movie']:
            return episode_info

        # Enhanced patterns for multi-season episode extraction
        season_episode_patterns = [
            r'S(\d+)E(\d+)',  # S2E5
            r'Season\s*(\d+)\s*Episode\s*(\d+)',  # Season 2 Episode 5
            r'S(\d+)\s*EP?\.?\s*(\d+)',  # S2 EP5, S2 E5
        ]

        # Try season + episode patterns first
        for pattern in season_episode_patterns:
            match = re.search(pattern, episode_text, re.IGNORECASE)
            if match:
                try:
                    season_num = int(match.group(1))
                    episode_num = int(match.group(2))
                    episode_info['season'] = season_num
                    episode_info['episode_number'] = episode_num
                    return episode_info
                except ValueError:
                    continue

        # Fall back to regular episode patterns
        episode_patterns = [
            r'E(\d+)',  # E12
            r'Episode\s*(\d+)',  # Episode 12
            r'Ep\.?\s*(\d+)',  # Ep. 12 or Ep 12
            r'^(\d+)\s*[-–—]',  # 12 - (at start)
            r'#(\d+)',  # #12
        ]

        for pattern in episode_patterns:
            match = re.search(pattern, episode_text, re.IGNORECASE)
            if match:
                try:
                    episode_num = int(match.group(1))
                    episode_info['episode_number'] = episode_num
                    break
                except ValueError:
                    continue

        return episode_info

    def _is_movie_or_special(self, episode_text):
        """Check if the content is a movie, special, or compilation"""
        if not episode_text:
            return False

        movie_indicators = [
            'movie', 'film', 'compilation', 'special', 'ova', 'ona',
            'recap', 'summary', 'theater', 'theatrical'
        ]

        for indicator in movie_indicators:
            if indicator in episode_text.lower():
                return True

        return False

    def _remove_duplicate_items(self, items):
        """Remove duplicate history items based on series and episode"""
        if not items:
            return []

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

    # Authentication and helper methods (keeping existing logic but removing HTML logging)

    def _verify_authentication(self) -> bool:
        """Verify that we're actually logged in"""
        try:
            logger.info("🔍 Verifying authentication status...")

            self.driver.get("https://www.crunchyroll.com/account")
            time.sleep(3)

            current_url = self.driver.current_url.lower()
            page_source = self.driver.page_source.lower()

            if "login" in current_url:
                logger.info("❌ Redirected to login page - not authenticated")
                return False

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

    def _verify_history_page_content(self) -> bool:
        """Verify that the history page contains expected content"""
        try:
            page_source = self.driver.page_source.lower()

            history_indicators = [
                "watch history", "recently watched", "continue watching",
                "history", "episode", "anime"
            ]

            found_indicators = [indicator for indicator in history_indicators if indicator in page_source]

            if found_indicators:
                logger.info(f"✅ History page verified - found: {found_indicators}")
                return True
            else:
                logger.warning("⚠️ History page doesn't contain expected indicators")
                # Check for any episode content
                soup = BeautifulSoup(self.driver.page_source, 'html.parser')

                potential_episodes = soup.find_all(['div', 'article'], class_=lambda x: x and any(
                    keyword in x.lower() for keyword in ['card', 'item', 'episode', 'content']
                ))

                if potential_episodes:
                    logger.info(f"✅ Found {len(potential_episodes)} potential episode elements")
                    return True
                else:
                    logger.warning("❌ No episode content found on page")
                    return False

        except Exception as e:
            logger.error(f"Error verifying history page: {e}")
            return False

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

    def _authenticate_with_selenium(self) -> bool:
        """Authenticate using Selenium"""
        try:
            logger.info("🌐 Authenticating with Selenium...")

            self.driver.get("https://www.crunchyroll.com/login")

            self._handle_cloudflare_challenge()

            wait = WebDriverWait(self.driver, 30)

            # Find form fields
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
                self._save_debug_html("login_page_no_email.html")
                return False

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
                self._save_debug_html("login_page_no_password.html")
                return False

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
                self._save_debug_html("login_page_no_submit.html")
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

            logger.info("✅ Selenium authentication appears successful")
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
        """Handle Cloudflare challenge if present"""
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
        """Wait for page to load completely"""
        try:
            self._handle_cloudflare_challenge()

            wait = WebDriverWait(self.driver, timeout)
            wait.until(lambda d: d.execute_script("return document.readyState") == "complete")

            return True

        except TimeoutException:
            logger.error("⏱️ Page load timeout")
            return False

    def _extract_login_form_data(self, html_content: str) -> Dict[str, str]:
        """Extract form data from login page HTML"""
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
        """Cache current authentication state"""
        try:
            if self.driver:
                cookies = self.driver.get_cookies()
                self.auth_cache.save_crunchyroll_auth(cookies=cookies)
                logger.debug("✅ Authentication cached successfully")
        except Exception as e:
            logger.error(f"Error caching authentication: {e}")

    def _save_debug_html(self, filename: str) -> None:
        """Save current page HTML for debugging (file only, no logging)"""
        try:
            cache_dir = Path('_cache')
            cache_dir.mkdir(exist_ok=True)

            filepath = cache_dir / filename
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(self.driver.page_source)

            logger.debug(f"🔍 Debug HTML saved: {filepath}")

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