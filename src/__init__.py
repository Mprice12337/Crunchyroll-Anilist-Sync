"""
Crunchyroll-AniList Sync package
"""

__version__ = "0.2.0"

from .sync_manager import SyncManager
from .anilist_client import AniListClient
from .anilist_auth import AniListAuth
from .anilist_api import AniListAPI, RateLimitTracker
from .anime_matcher import AnimeMatcher
from .cache_manager import CacheManager, AuthCache

__all__ = [
    'SyncManager',
    'AniListClient',
    'AniListAuth',
    'AniListAPI',
    'RateLimitTracker',
    'AnimeMatcher',
    'CacheManager',
]