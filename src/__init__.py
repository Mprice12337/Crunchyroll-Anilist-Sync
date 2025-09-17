"""
Crunchyroll-AniList Sync package
"""

__version__ = "0.2.0"

from .sync_manager import SyncManager
from .anilist_client import AniListClient
from .anime_matcher import AnimeMatcher
from .cache_manager import CacheManager, AuthCache

__all__ = [
    'SyncManager',
    'AniListClient',
    'AnimeMatcher',
    'CacheManager',
    'AuthCache'
]