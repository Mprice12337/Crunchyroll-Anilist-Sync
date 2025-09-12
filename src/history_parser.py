"""Crunchyroll history page HTML parser"""
import re
import json
from bs4 import BeautifulSoup
from collections import defaultdict
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

class CrunchyrollHistoryParser:
    def __init__(self):
        self.anime_matcher = re.compile(r'anime|series|episode', re.IGNORECASE)
        # More comprehensive episode pattern
        self.episode_pattern = re.compile(r'(?:E|Episode|ep\.?|e)\s*(\d+)', re.IGNORECASE)
        self.season_pattern = re.compile(r'season\s*(\d+)', re.IGNORECASE)

    def parse_history_html(self, html_content):
        """Parse Crunchyroll history page HTML and extract viewing history"""
        try:
            soup = BeautifulSoup(html_content, 'html.parser')
            history_items = []

            # Parse using the specific HTML structure
            try:
                cards_items = self._parse_history_cards(soup)
                if cards_items:
                    history_items.extend(cards_items)
            except Exception as e:
                logger.debug(f"History cards parsing failed: {e}")

            if not history_items:
                # Fallback to other parsing strategies
                strategies = [
                    self._parse_react_data,
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

            # Remove duplicates based on series + episode combination
            unique_items = self._remove_duplicate_items(history_items)

            logger.info(f"Total unique history items found: {len(unique_items)}")
            return unique_items

        except Exception as e:
            logger.error(f"Error parsing history HTML: {e}")
            return []

    def _parse_history_cards(self, soup):
        """Parse history cards from the specific Crunchyroll HTML structure"""
        history_items = []

        # Find all history playable cards
        cards = soup.find_all('div', class_='history-playable-card--qVdzv')
        logger.debug(f"Found {len(cards)} history cards")

        for i, card in enumerate(cards):
            try:
                logger.debug(f"Processing card {i+1}")
                item = self._extract_card_data(card)
                if item and item.get('series_title'):
                    history_items.append(item)
                    logger.debug(f"Added item: {item}")
                else:
                    logger.debug(f"Skipped card {i+1} - no valid data")
            except Exception as e:
                logger.debug(f"Error parsing card {i+1}: {e}")
                continue

        logger.info(f"Found {len(history_items)} items from history cards")
        return history_items

    def _extract_card_data(self, card):
        """Extract data from a history card element"""
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

            # Debug logging
            logger.debug(f"Raw series: '{series_title}', Raw episode: '{episode_title}'")

            # Clean up the series title
            series_title = self._clean_extracted_series_title(series_title)

            if not series_title:
                logger.debug("No series title found, skipping card")
                return {}

            result = {
                'series_title': series_title,
                'episode_title': episode_title,
                'timestamp': None
            }

            logger.debug(f"Extracted: {result}")
            return result
            
        except Exception as e:
            logger.debug(f"Error extracting card data: {e}")
            return {}

    def _is_episode_text(self, text):
        """Check if text contains episode information"""
        if not text:
            return False
        return bool(self.episode_pattern.search(text))

    def _is_date_text(self, text):
        """Check if text looks like a date"""
        if not text:
            return False
        # Common date patterns
        date_patterns = [
            r'\d{1,2}/\d{1,2}/\d{4}',  # MM/DD/YYYY
            r'\d{4}-\d{2}-\d{2}',      # YYYY-MM-DD
            r'\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\b',  # Month names
            r'\d+\s+(?:minute|hour|day|week|month|year)s?\s+ago',  # "X days ago"
        ]
        for pattern in date_patterns:
            if re.search(pattern, text, re.IGNORECASE):
                return True
        return False

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

    def _clean_extracted_series_title(self, series_title):
        """Clean series title extracted from HTML"""
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

    def _parse_episode_title(self, episode_text):
        """Parse episode number and title from text like 'E11 - MISSION START'"""
        episode_info = {
            'episode_title': episode_text,
            'episode_number': 0,
            'episode_name': ''
        }

        # Pattern to match episode format: E11 - MISSION START
        episode_match = re.match(r'E(\d+)\s*-\s*(.+)', episode_text, re.IGNORECASE)
        if episode_match:
            episode_info['episode_number'] = int(episode_match.group(1))
            episode_info['episode_name'] = episode_match.group(2).strip()
            return episode_info

        # Alternative patterns
        patterns = [
            r'Episode\s*(\d+)\s*[-–]\s*(.+)',  # Episode 11 - Title
            r'Ep\.?\s*(\d+)\s*[-–]\s*(.+)',    # Ep. 11 - Title
            r'(\d+)\s*[-–]\s*(.+)',            # 11 - Title
            r'#(\d+)\s*(.+)?',                 # #11 Title
            r'第(\d+)話\s*(.+)?',              # Japanese format
        ]

        for pattern in patterns:
            match = re.match(pattern, episode_text, re.IGNORECASE)
            if match:
                episode_info['episode_number'] = int(match.group(1))
                if len(match.groups()) > 1 and match.group(2):
                    episode_info['episode_name'] = match.group(2).strip()
                break

        return episode_info

    def _clean_series_title(self, series_title):
        """Clean and normalize series title"""
        if not series_title:
            return ""

        # Start with basic cleaning
        cleaned = self._clean_extracted_series_title(series_title)

        # Additional cleaning for series title normalization
        # Remove language indicators
        cleaned = re.sub(r'\s*\((?:Sub|Dub|Subbed|Dubbed)\)', '', cleaned, flags=re.IGNORECASE)

        # Remove version indicators
        cleaned = re.sub(r'\s*\((?:TV|OVA|Movie|Film)\)', '', cleaned, flags=re.IGNORECASE)

        # Remove "The" prefix for better matching (but keep it for display)
        # This helps with grouping series that might have inconsistent "The" usage

        # Final cleanup
        cleaned = cleaned.strip()

        return cleaned
        cleaned = re.sub(r'\s+S\d+', '', cleaned)

        # Remove year indicators
        cleaned = re.sub(r'\s+\(\d{4}\)', '', cleaned)

        # Remove extra whitespace
        cleaned = ' '.join(cleaned.split())

        return cleaned

    def _extract_detailed_episode_info(self, episode_text):
        """
        Extract detailed episode information including episode number, season, and clean title
        Handles multi-season episode numbering (S2E5, etc.)
        """
        if not episode_text:
            return {'episode_number': 0, 'clean_title': '', 'season': 1, 'is_movie': False}

        logger.debug(f"Extracting episode info from: '{episode_text}'")

        episode_info = {
            'episode_number': 0,
            'clean_title': episode_text,
            'season': 1,
            'is_movie': self._is_movie_or_special(episode_text)
        }

        # If it's a movie/special, don't try to extract episode number
        if episode_info['is_movie']:
            logger.debug(f"Detected as movie/special: '{episode_text}'")
            return episode_info

        # Enhanced patterns for multi-season episode extraction
        season_episode_patterns = [
            r'S(\d+)E(\d+)',                        # S2E5
            r'Season\s*(\d+)\s*Episode\s*(\d+)',    # Season 2 Episode 5
            r'S(\d+)\s*EP?\.?\s*(\d+)',             # S2 EP5, S2 E5
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
                    logger.debug(f"Found S{season_num}E{episode_num} using pattern: {pattern}")

                    # Clean the title by removing the season/episode indicator
                    clean_title = re.sub(pattern, '', episode_text, flags=re.IGNORECASE).strip()
                    clean_title = re.sub(r'^[-–—]\s*', '', clean_title)
                    episode_info['clean_title'] = clean_title

                    return episode_info
                except ValueError:
                    continue

        # Fall back to regular episode patterns
        episode_patterns = [
            r'E(\d+)',                              # E12
            r'Episode\s*(\d+)',                     # Episode 12
            r'Ep\.?\s*(\d+)',                       # Ep. 12 or Ep 12
            r'^(\d+)\s*[-–—]',                      # 12 - (at start)
            r'#(\d+)',                              # #12
            r'第(\d+)話',                           # Japanese format
        ]

        # Also check for standalone season indicators
        season_match = self.season_pattern.search(episode_text)
        if season_match:
            episode_info['season'] = int(season_match.group(1))

        for pattern in episode_patterns:
            match = re.search(pattern, episode_text, re.IGNORECASE)
            if match:
                try:
                    episode_num = int(match.group(1))
                    episode_info['episode_number'] = episode_num
                    logger.debug(f"Found episode number: {episode_num} using pattern: {pattern}")
                    break
                except ValueError:
                    continue

        # If no specific pattern matched, try to find any number (but not for movies)
        if episode_info['episode_number'] == 0 and not episode_info['is_movie']:
            numbers = re.findall(r'\d+', episode_text)
            if numbers:
                try:
                    episode_info['episode_number'] = int(numbers[0])
                    logger.debug(f"Found episode number from first number: {numbers[0]}")
                except ValueError:
                    pass

        # Extract clean title by removing episode indicators
        clean_title = episode_text
        clean_title = re.sub(r'^E\d+\s*[-–—]\s*', '', clean_title, flags=re.IGNORECASE)
        clean_title = re.sub(r'^Episode\s*\d+\s*[-–—]\s*', '', clean_title, flags=re.IGNORECASE)
        clean_title = re.sub(r'^Ep\.?\s*\d+\s*[-–—]\s*', '', clean_title, flags=re.IGNORECASE)
        clean_title = re.sub(r'^\d+\s*[-–—]\s*', '', clean_title)
        clean_title = re.sub(r'^Season\s*\d+\s*', '', clean_title, flags=re.IGNORECASE)
        clean_title = clean_title.strip()

        episode_info['clean_title'] = clean_title

        logger.debug(f"Final episode info: {episode_info}")
        return episode_info

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

    def _parse_react_data(self, soup):
        """Parse React/Next.js data from script tags"""
        history_items = []

        try:
            # Look for __NEXT_DATA__ script tag
            next_data_script = soup.find('script', {'id': '__NEXT_DATA__'})
            if next_data_script:
                data = json.loads(next_data_script.string)
                # Extract history items from the data structure
                items = self._extract_items_from_next_data(data)
                history_items.extend(items)
        except Exception as e:
            logger.debug(f"Failed to parse React data: {e}")

        return history_items

    def _extract_items_from_next_data(self, data):
        """Extract history items from Next.js data structure"""
        items = []

        try:
            # Navigate through the data structure to find history items
            # This is a generic approach - may need adjustment based on actual structure
            if isinstance(data, dict):
                for key, value in data.items():
                    if 'history' in key.lower() or 'episode' in key.lower():
                        if isinstance(value, list):
                            for item in value:
                                parsed_item = self._parse_history_item(item)
                                if parsed_item:
                                    items.append(parsed_item)
                        elif isinstance(value, dict):
                            parsed_item = self._parse_history_item(value)
                            if parsed_item:
                                items.append(parsed_item)
        except Exception as e:
            logger.debug(f"Error extracting from Next.js data: {e}")

        return items

    def _parse_dom_elements(self, soup):
        """Parse DOM elements to find history items using generic selectors"""
        history_items = []

        # Look for common patterns in Crunchyroll's page structure
        selectors = [
            'div[data-testid*="history"]',
            'div[class*="history"]',
            'div[class*="episode"]',
            'a[href*="/watch/"]',
            'div[class*="card"]',
            'li[class*="item"]',
            '.playable-card'
        ]

        for selector in selectors:
            try:
                elements = soup.select(selector)
                for element in elements:
                    item = self._extract_item_from_element(element)
                    if item and item.get('series_title'):
                        history_items.append(item)
            except Exception as e:
                logger.debug(f"Error with selector {selector}: {e}")
                continue

        return history_items

    def _extract_item_from_element(self, element):
        """Extract history item data from a DOM element"""
        if not element:
            return {}

        try:
            # Try to extract series and episode information
            text_content = element.get_text(strip=True)

            # Look for links that might contain titles
            links = element.find_all('a')
            series_title = ""
            episode_title = ""

            for link in links:
                link_text = link.get_text(strip=True)
                href = link.get('href', '')

                if '/series/' in href and not series_title:
                    series_title = link_text
                elif '/watch/' in href and not episode_title:
                    episode_title = link_text

            # If no links found, try to parse from text content
            if not series_title and text_content:
                # This is a basic fallback - may need refinement
                lines = [line.strip() for line in text_content.split('\n') if line.strip()]
                if len(lines) >= 2:
                    series_title = lines[0]
                    episode_title = lines[1]
                elif len(lines) == 1:
                    series_title = lines[0]

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

            # Split into lines and look for episode patterns
            lines = [line.strip() for line in all_text.split('\n') if line.strip()]

            for line in lines:
                if self.episode_pattern.search(line):
                    # This line contains episode information
                    episode_info = self._extract_detailed_episode_info(line)
                    if episode_info['episode_number'] > 0:
                        history_items.append({
                            'series_title': 'Unknown Series',
                            'episode_title': line,
                            'timestamp': None
                        })
        except Exception as e:
            logger.debug(f"Error in broad search: {e}")

        return history_items[:10]  # Limit to prevent too many false positives

    def _parse_date(self, date_string):
        """Parse date string to timestamp"""
        try:
            # Handle format like "09/07/2025"
            if '/' in date_string:
                return datetime.strptime(date_string, '%m/%d/%Y').timestamp()
        except ValueError:
            pass
        return None

    def get_series_progress(self, html_content):
        """
        Main method to extract series progress from HTML content
        Returns a dictionary with series titles and their highest watched episodes plus movies
        """
        try:
            # Parse the HTML and extract history items
            history_items = self.parse_history_html(html_content)

            # Ensure we have a list of items
            if not isinstance(history_items, list):
                logger.warning("Expected list of history items, got different type")
                return {}

            # Get the latest episodes per series (including movies and seasons)
            series_data = self._get_latest_episodes_per_series(history_items)

            # Format the output
            formatted_progress = {}
            for series_title, info in series_data.items():
                # Determine the latest episode info
                current_season = info.get('current_season', 1)
                current_episode = info.get('current_episode', 0)

                formatted_progress[series_title] = {
                    'latest_episode': current_episode,
                    'latest_season': current_season,
                    'episode_name': info['episode_title'],
                    'last_watched': info['timestamp'],
                    'seasons': info['seasons'],  # All season progress
                    'movies': info['movies'],
                    'has_episodes': info['has_episodes'],
                    'total_episodes_watched': sum(info['seasons'].values()) if info['seasons'] else 0
                }

            logger.info(f"Extracted progress for {len(formatted_progress)} series")

            # Return in the expected format for the main.py caller
            return {
                'items': history_items,
                'series_progress': formatted_progress
            }

        except Exception as e:
            logger.error(f"Error extracting series progress: {e}")
            return {'items': [], 'series_progress': {}}

    def _get_latest_episodes_per_series(self, history_items):
        """
        Process history items to find the highest episode number for each series
        Handle multi-season tracking properly
        Also track movies/specials separately
        """
        if not history_items or not isinstance(history_items, list):
            return {}

        series_data = defaultdict(lambda: {
            'latest_overall_episode': 0,
            'title': '',
            'episode_title': '',
            'timestamp': None,
            'seasons': {},  # Track episodes by season: {1: 12, 2: 5}
            'movies': [],  # Track movies/specials separately
            'has_episodes': False
        })

        for item in history_items:
            if not isinstance(item, dict):
                continue

            series_title = self._clean_series_title(item.get('series_title', ''))
            episode_title = item.get('episode_title', '')
            episode_info = self._extract_detailed_episode_info(episode_title)

            if not series_title:
                continue

            series_entry = series_data[series_title]

            if episode_info.get('is_movie', False):
                # This is a movie/special - add to movies list
                movie_info = {
                    'title': episode_info.get('clean_title', episode_title),
                    'full_title': episode_title,
                    'timestamp': item.get('timestamp')
                }

                # Avoid duplicate movies
                if not any(m['title'] == movie_info['title'] for m in series_entry['movies']):
                    series_entry['movies'].append(movie_info)
                    logger.debug(f"Added movie for {series_title}: {movie_info['title']}")

            else:
                # This is a regular episode
                episode_num = episode_info.get('episode_number', 0)
                season_num = episode_info.get('season', 1)

                if episode_num > 0:
                    series_entry['has_episodes'] = True

                    # Track the highest episode for this season
                    if season_num not in series_entry['seasons']:
                        series_entry['seasons'][season_num] = 0

                    if episode_num > series_entry['seasons'][season_num]:
                        series_entry['seasons'][season_num] = episode_num
                        logger.debug(f"Updated {series_title} S{season_num} to episode {episode_num}")

                    # Calculate overall episode position (rough estimate)
                    # This assumes standard 12-24 episode seasons
                    estimated_overall = (season_num - 1) * 12 + episode_num

                    # Keep track of the most recent episode overall
                    if estimated_overall > series_entry['latest_overall_episode']:
                        series_entry.update({
                            'latest_overall_episode': estimated_overall,
                            'title': series_title,
                            'episode_title': episode_info.get('clean_title', episode_title),
                            'current_season': season_num,
                            'current_episode': episode_num,
                            'timestamp': item.get('timestamp')
                        })

        return dict(series_data)

def parse_history_file(file_path):
    """
    Convenience function to parse a history HTML file and return series progress
    """
    parser = CrunchyrollHistoryParser()

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            html_content = f.read()

        result = parser.get_series_progress(html_content)
        series_progress = result.get('series_progress', {})

        # Display results in a clean format
        print(f"\n=== Crunchyroll Series Progress ===")
        print(f"Found {len(series_progress)} series:\n")

        # Sort by series name for consistent output
        for series_title in sorted(series_progress.keys()):
            info = series_progress[series_title]
            latest_ep = info.get('latest_episode', 0)
            latest_season = info.get('latest_season', 1)
            episode_name = info.get('episode_name', '')
            seasons = info.get('seasons', {})
            movies = info.get('movies', [])
            has_episodes = info.get('has_episodes', False)

            print(f"📺 {series_title}")

            # Show episode progress
            if has_episodes and seasons:
                if len(seasons) == 1:
                    # Single season
                    season_num = list(seasons.keys())[0]
                    episode_count = seasons[season_num]
                    if season_num == 1:
                        print(f"   📈 Latest Episode: {episode_count}")
                    else:
                        print(f"   📈 Season {season_num}, Episode {episode_count}")
                else:
                    # Multiple seasons
                    print(f"   📈 Latest: Season {latest_season}, Episode {latest_ep}")
                    print(f"   📊 All Seasons: {dict(seasons)}")

                if episode_name:
                    print(f"      └─ {episode_name}")
            elif not has_episodes and not movies:
                print(f"   ❓ No episode number found")

            # Show movies/specials
            if movies:
                print(f"   🎬 Movies/Specials: {len(movies)}")
                for movie in movies:
                    print(f"      └─ {movie['title']}")

            print()  # Empty line between series

        print(f"Total series: {len(series_progress)}")

        return result

    except FileNotFoundError:
        print(f"Error: File '{file_path}' not found")
        return {'items': [], 'series_progress': {}}
    except Exception as e:
        print(f"Error parsing file: {e}")
        return {'items': [], 'series_progress': {}}