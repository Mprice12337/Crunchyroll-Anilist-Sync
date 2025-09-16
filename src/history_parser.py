"""Crunchyroll history page HTML parser"""
import re
import json
import logging
from datetime import datetime
from typing import List, Dict, Any, Optional
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

class CrunchyrollHistoryParser:
    def __init__(self):
        self.anime_matcher = re.compile(r'anime|series|episode', re.IGNORECASE)
        # More comprehensive episode pattern
        self.episode_pattern = re.compile(r'(?:E|Episode|ep\.?|e)\s*(\d+)', re.IGNORECASE)
        self.season_pattern = re.compile(r'season\s*(\d+)', re.IGNORECASE)

    def parse_history_page(self, soup):
        """Main entry point for parsing history data - compatibility method"""
        try:
            if isinstance(soup, str):
                # If it's a string, parse it as HTML
                return self.parse_history_html(soup)
            else:
                # If it's already a BeautifulSoup object, convert to string first
                html_content = str(soup)
                return self.parse_history_html(html_content)
        except Exception as e:
            logger.error(f"Error in parse_history_page: {e}")
            return []

    def parse_history_html(self, html_content):
        """Parse Crunchyroll history page HTML and extract viewing history"""
        try:
            if isinstance(html_content, str):
                soup = BeautifulSoup(html_content, 'html.parser')
            else:
                soup = html_content  # Already a BeautifulSoup object
                
            history_items = []

            # Check if this is our mock HTML structure from pagination
            if soup.find('div', class_='history-container'):
                return self._parse_mock_history_structure(soup)

            # Parse using the specific HTML structure
            try:
                cards_items = self._parse_history_cards(soup)
                if cards_items:
                    history_items.extend(cards_items)
            except Exception as e:
                logger.debug(f"History cards parsing failed: {e}")

            if not history_items:
                # Try alternative parsing methods
                try:
                    alternative_items = self._parse_alternative_structure(soup)
                    if alternative_items:
                        history_items.extend(alternative_items)
                except Exception as e:
                    logger.debug(f"Alternative parsing failed: {e}")

            logger.info(f"Successfully parsed {len(history_items)} history items")
            
            # Return in the expected format for sync_manager
            return {
                'items': history_items,
                'total_count': len(history_items)
            }

        except Exception as e:
            logger.error(f"Failed to parse history HTML: {e}")
            return {'items': [], 'total_count': 0}

    def _parse_alternative_structure(self, soup):
        """Alternative parsing method for different HTML structures"""
        history_items = []
        
        try:
            # Try different selectors for history items
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
                    logger.debug(f"Found {len(items)} items with alternative selector: {selector}")
                    
                    for item in items[:50]:  # Limit to 50 items
                        try:
                            extracted_data = self._extract_alternative_data(item)
                            if extracted_data and extracted_data.get('series_title'):
                                history_items.append(extracted_data)
                        except Exception as e:
                            logger.debug(f"Error extracting alternative data: {e}")
                            continue
                    
                    if history_items:
                        break  # Use the first selector that worked
            
            return history_items
            
        except Exception as e:
            logger.error(f"Alternative structure parsing failed: {e}")
            return []

    def parse_history_html(self, html_content):
        """Parse Crunchyroll history page HTML and extract viewing history"""
        try:
            if isinstance(html_content, str):
                soup = BeautifulSoup(html_content, 'html.parser')
            else:
                soup = html_content

            # Check if this is our mock HTML structure
            if soup.select('.history-container .history-item'):
                logger.debug("Detected mock HTML structure, using specialized parser")
                return self._parse_mock_history_structure(soup)

            # ... existing code for regular HTML parsing ...
        except Exception as e:
            logger.error(f"Failed to parse history HTML: {e}")
            return []

    def _parse_mock_history_structure(self, soup):
        """Parse the mock HTML structure created by the scraper"""
        history_items = []

        try:
            # Find all history items in our mock structure
            mock_items = soup.select('.history-container .history-item')
            logger.debug(f"Found {len(mock_items)} items in mock structure")

            for item in mock_items:
                try:
                    # Extract data from our known mock structure
                    series_title_elem = item.select_one('.series-title')
                    episode_info_elem = item.select_one('.episode-info')
                    episode_title_elem = item.select_one('.episode-title')
                    watch_date_elem = item.select_one('.watch-date')

                    series_title = series_title_elem.get_text(strip=True) if series_title_elem else ""
                    episode_info = episode_info_elem.get_text(strip=True) if episode_info_elem else ""
                    episode_title = episode_title_elem.get_text(strip=True) if episode_title_elem else ""
                    watch_date = watch_date_elem.get_text(strip=True) if watch_date_elem else ""

                    # Extract episode number from episode info
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
                            'season': 1  # Default season
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
            return []

    def _extract_alternative_data(self, item):
        """Extract data from alternative HTML structures"""
        try:
            # Get all text content and try to parse it
            text_content = item.get_text(strip=True)
            
            if not text_content:
                return None
            
            # Split into lines and clean up
            lines = [line.strip() for line in text_content.split('\n') if line.strip()]
            
            if not lines:
                return None
            
            # First line is usually the series title
            series_title = lines[0] if lines else ""
            
            # Look for episode information
            episode_info = ""
            episode_number = None
            
            for line in lines[1:]:
                if any(keyword in line.lower() for keyword in ['episode', 'ep', 'e']):
                    episode_info = line
                    # Try to extract episode number
                    ep_match = self.episode_pattern.search(line)
                    if ep_match:
                        episode_number = int(ep_match.group(1))
                    break
            
            # Look for date information
            watch_date = ""
            for line in lines:
                if self._is_date_text(line):
                    watch_date = line
                    break
            
            # Try to find links
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