"""
Debug collector for capturing detailed matching diagnostics.
"""

import json
import csv
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional

logger = logging.getLogger(__name__)


class DebugCollector:
    """Collects and exports debug data during the sync process."""

    def __init__(self, output_dir: str = "_cache/debug"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.session_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        self.crunchyroll_pages: List[Dict[str, Any]] = []
        self.anilist_searches: List[Dict[str, Any]] = []
        self.matching_decisions: List[Dict[str, Any]] = []
        self.changeset_entries: List[Dict[str, Any]] = []

        self._decision_counter = 0

        logger.info(f"Debug collector initialized - output dir: {self.output_dir}")

    def record_crunchyroll_page(self, page_num: int, raw_items: List[Dict],
                                 parsed_episodes: List[Dict]) -> None:
        """Record raw and parsed Crunchyroll data for a page."""
        self.crunchyroll_pages.append({
            'page_num': page_num,
            'timestamp': datetime.now().isoformat(),
            'raw_item_count': len(raw_items) if raw_items else 0,
            'parsed_episode_count': len(parsed_episodes) if parsed_episodes else 0,
            'raw_items': raw_items or [],
            'parsed_episodes': parsed_episodes or []
        })
        logger.debug(f"Recorded CR page {page_num}: {len(raw_items or [])} raw, "
                     f"{len(parsed_episodes or [])} parsed")

    def record_anilist_search(self, query: str, results: List[Dict],
                               context: str = "primary") -> None:
        """Record an AniList search query and its results."""
        self.anilist_searches.append({
            'timestamp': datetime.now().isoformat(),
            'query': query,
            'context': context,
            'result_count': len(results) if results else 0,
            'results': self._sanitize_search_results(results)
        })
        logger.debug(f"Recorded AniList search: '{query}' -> {len(results or [])} results")

    def _sanitize_search_results(self, results: Optional[List[Dict]]) -> List[Dict]:
        """Extract relevant fields from search results for logging."""
        if not results:
            return []

        sanitized = []
        for result in results:
            sanitized.append({
                'id': result.get('id'),
                'title': result.get('title', {}),
                'format': result.get('format'),
                'episodes': result.get('episodes'),
                'status': result.get('status'),
                'startDate': result.get('startDate'),
                'seasonYear': result.get('seasonYear'),
                'season': result.get('season'),
            })
        return sanitized

    def record_matching_decision(self, decision: Dict[str, Any]) -> None:
        """
        Record a complete matching decision.

        Expected decision structure:
        {
            'input': {
                'series_title': str,
                'cr_season': int,
                'cr_episode': int,
                'is_movie': bool
            },
            'candidates': [
                {
                    'anilist_id': int,
                    'title': str,
                    'format': str,
                    'episodes': int,
                    'similarity_score': float
                }
            ],
            'season_structure': dict,  # The built season mapping
            'selected': {
                'anilist_id': int,
                'title': str,
                'mapped_season': int,
                'mapped_episode': int,
                'reason': str
            } or None,
            'outcome': 'matched' | 'no_match' | 'skipped'
        }
        """
        self._decision_counter += 1
        decision['decision_id'] = self._decision_counter
        decision['timestamp'] = datetime.now().isoformat()

        self.matching_decisions.append(decision)

        input_data = decision.get('input', {})
        outcome = decision.get('outcome', 'unknown')
        logger.debug(f"Recorded decision #{self._decision_counter}: "
                     f"{input_data.get('series_title')} -> {outcome}")

    def record_changeset_entry(self, anime_id: int, anime_title: str, progress: int,
                                total_episodes: Optional[int], cr_source: Dict[str, Any],
                                update_type: str = 'normal') -> None:
        """
        Record an AniList update that would be made.

        Args:
            anime_id: AniList media ID
            anime_title: AniList anime title
            progress: Episode number to update to
            total_episodes: Total episodes in the series (if known)
            cr_source: Source data from Crunchyroll
                {
                    'series': str,
                    'season': int,
                    'episode': int,
                    'is_movie': bool
                }
            update_type: Type of update ('normal', 'rewatch', 'new_series')
        """
        entry = {
            'anime_id': anime_id,
            'anime_title': anime_title,
            'progress': progress,
            'total_episodes': total_episodes,
            'cr_source': cr_source,
            'update_type': update_type,
            'timestamp': datetime.now().isoformat()
        }

        self.changeset_entries.append(entry)
        logger.debug(f"Recorded changeset entry: {anime_title} -> E{progress}")

    def export_all(self) -> Dict[str, Path]:
        """Export all collected data to files. Returns paths to created files."""
        exported_files = {}

        # Export Crunchyroll history
        cr_file = self._export_crunchyroll_history()
        if cr_file:
            exported_files['crunchyroll_history'] = cr_file

        # Export AniList searches
        search_file = self._export_anilist_searches()
        if search_file:
            exported_files['anilist_searches'] = search_file

        # Export matching decisions (JSON)
        decisions_file = self._export_matching_decisions()
        if decisions_file:
            exported_files['matching_decisions'] = decisions_file

        # Export matching summary (CSV)
        summary_file = self._export_matching_summary_csv()
        if summary_file:
            exported_files['matching_summary'] = summary_file

        # Export changeset (if any entries recorded)
        changeset_file = self._export_changeset()
        if changeset_file:
            exported_files['changeset'] = changeset_file

        logger.info(f"Debug data exported to {self.output_dir}/")
        for name, path in exported_files.items():
            logger.info(f"  - {path.name}")

        return exported_files

    def _export_crunchyroll_history(self) -> Optional[Path]:
        """Export Crunchyroll history data to JSON."""
        if not self.crunchyroll_pages:
            return None

        filename = f"crunchyroll_history_{self.session_timestamp}.json"
        filepath = self.output_dir / filename

        data = {
            'session_timestamp': self.session_timestamp,
            'total_pages': len(self.crunchyroll_pages),
            'total_raw_items': sum(p['raw_item_count'] for p in self.crunchyroll_pages),
            'total_parsed_episodes': sum(p['parsed_episode_count'] for p in self.crunchyroll_pages),
            'pages': self.crunchyroll_pages
        }

        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False, default=str)

        return filepath

    def _export_anilist_searches(self) -> Optional[Path]:
        """Export AniList search data to JSON."""
        if not self.anilist_searches:
            return None

        filename = f"anilist_searches_{self.session_timestamp}.json"
        filepath = self.output_dir / filename

        data = {
            'session_timestamp': self.session_timestamp,
            'total_searches': len(self.anilist_searches),
            'searches': self.anilist_searches
        }

        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False, default=str)

        return filepath

    def _export_matching_decisions(self) -> Optional[Path]:
        """Export matching decisions to JSON."""
        if not self.matching_decisions:
            return None

        filename = f"matching_decisions_{self.session_timestamp}.json"
        filepath = self.output_dir / filename

        data = {
            'session_timestamp': self.session_timestamp,
            'total_decisions': len(self.matching_decisions),
            'summary': {
                'matched': sum(1 for d in self.matching_decisions if d.get('outcome') == 'matched'),
                'no_match': sum(1 for d in self.matching_decisions if d.get('outcome') == 'no_match'),
                'skipped': sum(1 for d in self.matching_decisions if d.get('outcome') == 'skipped'),
            },
            'decisions': self.matching_decisions
        }

        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False, default=str)

        return filepath

    def _export_matching_summary_csv(self) -> Optional[Path]:
        """Export matching summary to CSV for spreadsheet analysis."""
        if not self.matching_decisions:
            return None

        filename = f"matching_summary_{self.session_timestamp}.csv"
        filepath = self.output_dir / filename

        fieldnames = [
            'Decision ID', 'CR Title', 'CR Season', 'CR Episode', 'Is Movie',
            'Num Candidates', 'Top Match ID', 'Top Match Title', 'Top Similarity',
            'Selected ID', 'Selected Title', 'Mapped Season', 'Mapped Episode',
            'Outcome', 'Selection Reason'
        ]

        with open(filepath, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()

            for decision in self.matching_decisions:
                input_data = decision.get('input', {})
                candidates = decision.get('candidates', [])
                selected = decision.get('selected', {}) or {}

                # Find top candidate by similarity
                top_candidate = None
                top_similarity = 0
                for candidate in candidates:
                    sim = candidate.get('similarity_score', 0)
                    if sim > top_similarity:
                        top_similarity = sim
                        top_candidate = candidate

                row = {
                    'Decision ID': decision.get('decision_id', ''),
                    'CR Title': input_data.get('series_title', ''),
                    'CR Season': input_data.get('cr_season', ''),
                    'CR Episode': input_data.get('cr_episode', ''),
                    'Is Movie': 'Yes' if input_data.get('is_movie') else 'No',
                    'Num Candidates': len(candidates),
                    'Top Match ID': top_candidate.get('anilist_id', '') if top_candidate else '',
                    'Top Match Title': top_candidate.get('title', '') if top_candidate else '',
                    'Top Similarity': f"{top_similarity:.3f}" if top_candidate else '',
                    'Selected ID': selected.get('anilist_id', ''),
                    'Selected Title': selected.get('title', ''),
                    'Mapped Season': selected.get('mapped_season', ''),
                    'Mapped Episode': selected.get('mapped_episode', ''),
                    'Outcome': decision.get('outcome', ''),
                    'Selection Reason': selected.get('reason', '')
                }
                writer.writerow(row)

        return filepath

    def _export_changeset(self) -> Optional[Path]:
        """Export changeset to JSON in _cache/changesets/ directory."""
        if not self.changeset_entries:
            return None

        # Use dedicated changesets directory
        changeset_dir = Path("_cache/changesets")
        changeset_dir.mkdir(parents=True, exist_ok=True)

        filename = f"changeset_{self.session_timestamp}.json"
        filepath = changeset_dir / filename

        data = {
            'created_at': datetime.now().isoformat(),
            'session_timestamp': self.session_timestamp,
            'total_changes': len(self.changeset_entries),
            'changes': self.changeset_entries
        }

        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False, default=str)

        logger.info(f"Changeset saved to {filepath}")
        return filepath

    @staticmethod
    def load_changeset(filepath: str) -> Dict[str, Any]:
        """
        Load and validate a changeset file.

        Args:
            filepath: Path to the changeset JSON file

        Returns:
            Dictionary containing changeset data

        Raises:
            FileNotFoundError: If file doesn't exist
            ValueError: If file format is invalid
        """
        filepath = Path(filepath)
        if not filepath.exists():
            raise FileNotFoundError(f"Changeset file not found: {filepath}")

        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in changeset file: {e}")

        # Validate structure
        if 'changes' not in data:
            raise ValueError("Invalid changeset format: missing 'changes' field")

        if not isinstance(data['changes'], list):
            raise ValueError("Invalid changeset format: 'changes' must be a list")

        # Validate each change entry
        required_fields = ['anime_id', 'anime_title', 'progress']
        for i, change in enumerate(data['changes']):
            for field in required_fields:
                if field not in change:
                    raise ValueError(f"Change #{i+1} missing required field: {field}")

        logger.info(f"Loaded changeset with {len(data['changes'])} entries from {filepath}")
        return data

    def get_stats(self) -> Dict[str, Any]:
        """Get current collection statistics."""
        return {
            'crunchyroll_pages': len(self.crunchyroll_pages),
            'anilist_searches': len(self.anilist_searches),
            'matching_decisions': len(self.matching_decisions),
            'changeset_entries': len(self.changeset_entries),
            'outcomes': {
                'matched': sum(1 for d in self.matching_decisions if d.get('outcome') == 'matched'),
                'no_match': sum(1 for d in self.matching_decisions if d.get('outcome') == 'no_match'),
                'skipped': sum(1 for d in self.matching_decisions if d.get('outcome') == 'skipped'),
            }
        }
