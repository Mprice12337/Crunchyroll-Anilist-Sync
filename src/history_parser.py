"""Crunchyroll history page HTML parser"""

import re
import logging
from typing import List, Dict, Any, Optional
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


class CrunchyrollHistoryParser:
    """Parser for Crunchyroll watch history HTML pages"""

    def __init__(self):
        self.anime_matcher = re.compile(r'anime|series|episode', re.IGNORECASE)
        self.episode_pattern = re.compile(r'(?:E|Episode|ep\.?|e)\s*(\d+)', re.IGNORECASE)
        self.season_pattern = re.compile(r'season\s*(\d+)', re.IGNORECASE)

    def parse_history_page(self, soup) -> Dict[str, Any]:
        """Main entry point for parsing history data"""
        try:
            if isinstance(soup, str):
                return self.parse_history_html(soup)
            else:
                html_content = str(soup)
                return self.parse_history_html(html_content)
        except Exception as e:
            logger.error(f"Error in parse_history_page: {e}")
            return {'items': [], 'total_count': 0}

    def parse_history_html(self, html_content: str) -> Dict[str, Any]:
        """Parse Crunchyroll history page HTML and extract viewing history"""
        try:
            if isinstance(html_content, str):
                soup = BeautifulSoup(html_content, 'html.parser')
            else:
                soup = html_content

            history_items = []

            if soup.find('div', class_='history-container'):
                return self._parse_mock_history_structure(soup)

            try:
                cards_items = self._parse_history_cards(soup)
                if cards_items:
                    history_items.extend(cards_items)
            except Exception as e:
                logger.debug(f"History cards parsing failed: {e}")

            if not history_items:
                try:
                    alternative_items = self._parse_alternative_structure(soup)
                    if alternative_items:
                        history_items.extend(alternative_items)
                except Exception as e:
                    logger.debug(f"Alternative parsing failed: {e}")

            logger.info(f"Successfully parsed {len(history_items)} history items")

            return {
                'items': history_items,
                'total_count': len(history_items)
            }

        except Exception as e:
            logger.error(f"Failed to parse history HTML: {e}")
            return {'items': [], 'total_count': 0}

    def _parse_mock_history_structure(self, soup: BeautifulSoup) -> Dict[str, Any]:
        """Parse the mock HTML structure created by the scraper"""
        history_items = []

        try:
            mock_items = soup.select('.history-container .history-item')
            logger.debug(f"Found {len(mock_items)} items in mock structure")

            for item in mock_items:
                try:
                    series_title_elem = item.select_one('.series-title')
                    episode_info_elem = item.select_one('.episode-info')
                    episode_title_elem = item.select_one('.episode-title')
                    watch_date_elem = item.select_one('.watch-date')

                    series_title = series_title_elem.get_text(strip=True) if series_title_elem else ""
                    episode_info = episode_info_elem.get_text(strip=True) if episode_info_elem else ""
                    episode_title = episode_title_elem.get_text(strip=True) if episode_title_elem else ""
                    watch_date = watch_date_elem.get_text(strip=True) if watch_date_elem else ""

                    episode_number = None
                    if episode_info:
                        ep_match = self.episode_pattern.search(episode_info)
                        if ep_match:
                            episode_number = int(ep_match.group(1))

                    if series_title and episode_number:
                        history_item = {
                            'series_title': series_title,
                            'episode_title': episode_title,
                            'episode_number': episode_number,
                            'watch_date': watch_date,
                            'season': 1
                        }

                        history_items.append(history_item)
                        logger.debug(f"Parsed mock item: {series_title} Episode {episode_number}")

                except Exception as e:
                    logger.debug(f"Error parsing mock history item: {e}")
                    continue

            logger.info(f"Successfully parsed {len(history_items)} items from mock structure")
            return {
                'items': history_items,
                'total_count': len(history_items)
            }

        except Exception as e:
            logger.error(f"Error parsing mock history structure: {e}")
            return {'items': [], 'total_count': 0}

    def _parse_history_cards(self, soup: BeautifulSoup) -> List[Dict[str, Any]]:
        """Parse standard Crunchyroll history card structure"""
        history_items = []

        try:
            cards = soup.select('.content-card, .episode-card')

            for card in cards:
                try:
                    extracted = self._extract_card_data(card)
                    if extracted and extracted.get('series_title'):
                        history_items.append(extracted)
                except Exception as e:
                    logger.debug(f"Error extracting card data: {e}")
                    continue

            return history_items

        except Exception as e:
            logger.error(f"Error parsing history cards: {e}")
            return []

    def _parse_alternative_structure(self, soup: BeautifulSoup) -> List[Dict[str, Any]]:
        """Alternative parsing method for different HTML structures"""
        history_items = []

        try:
            alternative_selectors = [
                '.content-card',
                '.episode-card',
                '.media-card',
                '.playable-card',
                '[data-testid*="episode"]',
                '[data-testid*="history"]',
                '.grid-item'
            ]

            for selector in alternative_selectors:
                items = soup.select(selector)
                if items:
                    logger.debug(f"Found {len(items)} items with selector: {selector}")

                    for item in items[:50]:
                        try:
                            extracted_data = self._extract_alternative_data(item)
                            if extracted_data and extracted_data.get('series_title'):
                                history_items.append(extracted_data)
                        except Exception as e:
                            logger.debug(f"Error extracting alternative data: {e}")
                            continue

                    if history_items:
                        break

            return history_items

        except Exception as e:
            logger.error(f"Alternative structure parsing failed: {e}")
            return []

    def _extract_card_data(self, card) -> Optional[Dict[str, Any]]:
        """Extract data from a standard card element"""
        try:
            text_content = card.get_text(strip=True)

            if not text_content:
                return None

            lines = [line.strip() for line in text_content.split('\n') if line.strip()]

            if not lines:
                return None

            series_title = lines[0] if lines else ""
            episode_info = ""
            episode_number = None

            for line in lines[1:]:
                if any(keyword in line.lower() for keyword in ['episode', 'ep', 'e']):
                    episode_info = line
                    ep_match = self.episode_pattern.search(line)
                    if ep_match:
                        episode_number = int(ep_match.group(1))
                    break

            watch_date = ""
            for line in lines:
                if self._is_date_text(line):
                    watch_date = line
                    break

            if series_title:
                return {
                    'series_title': series_title,
                    'episode_title': episode_info,
                    'episode_number': episode_number,
                    'watch_date': watch_date,
                    'season': 1
                }

            return None

        except Exception as e:
            logger.debug(f"Error in _extract_card_data: {e}")
            return None

    def _extract_alternative_data(self, item) -> Optional[Dict[str, Any]]:
        """Extract data from alternative HTML structures"""
        try:
            text_content = item.get_text(strip=True)

            if not text_content:
                return None

            lines = [line.strip() for line in text_content.split('\n') if line.strip()]

            if not lines:
                return None

            series_title = lines[0] if lines else ""
            episode_info = ""
            episode_number = None

            for line in lines[1:]:
                if any(keyword in line.lower() for keyword in ['episode', 'ep', 'e']):
                    episode_info = line
                    ep_match = self.episode_pattern.search(line)
                    if ep_match:
                        episode_number = int(ep_match.group(1))
                    break

            watch_date = ""
            for line in lines:
                if self._is_date_text(line):
                    watch_date = line
                    break

            series_url = ""
            episode_url = ""

            links = item.find_all('a', href=True)
            for link in links:
                href = link.get('href', '')
                if '/series/' in href:
                    series_url = href if href.startswith('http') else f"https://www.crunchyroll.com{href}"
                elif '/watch/' in href:
                    episode_url = href if href.startswith('http') else f"https://www.crunchyroll.com{href}"

            if series_title:
                return {
                    'series_title': series_title,
                    'episode_title': episode_info,
                    'episode_number': episode_number,
                    'watch_date': watch_date,
                    'series_url': series_url,
                    'episode_url': episode_url
                }

            return None

        except Exception as e:
            logger.debug(f"Error in _extract_alternative_data: {e}")
            return None

    def _is_date_text(self, text: str) -> bool:
        """Check if text contains date-like patterns"""
        date_indicators = [
            'ago', 'yesterday', 'today', 'week', 'month', 'year',
            'jan', 'feb', 'mar', 'apr', 'may', 'jun',
            'jul', 'aug', 'sep', 'oct', 'nov', 'dec'
        ]

        text_lower = text.lower()
        return any(indicator in text_lower for indicator in date_indicators)