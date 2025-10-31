# Architecture Overview
This document serves as a critical reference for understanding the Crunchyroll-AniList Sync codebase architecture, enabling efficient navigation and effective contribution. Update this document as the codebase evolves.

## 1. Project Structure

```
CrunchyrollAnilistSync/
├── src/                      # Main source code
│   ├── sync_manager.py       # Orchestrates entire sync process
│   ├── crunchyroll_auth.py   # Crunchyroll authentication
│   ├── crunchyroll_scraper.py # Web scraping watch history
│   ├── crunchyroll_parser.py # Parse Crunchyroll HTML
│   ├── history_parser.py     # Parse history data structures
│   ├── anilist_auth.py       # AniList OAuth authentication
│   ├── anilist_api.py        # AniList GraphQL API wrapper
│   ├── anilist_client.py     # High-level AniList operations
│   ├── anime_matcher.py      # Title matching algorithm
│   ├── flaresolvrrr_client.py # Cloudflare bypass
│   ├── cache_manager.py      # Caching layer
│   └── __init__.py
├── docs/                    # Documentation
│   ├── ARCHITECTURE.md      # This file
│   ├── CLAUDE.md            # Claude Code configuration
│   └── TESTING_GUIDE.md     # Testing procedures
├── main.py                   # CLI entry point
├── entrypoint.sh            # Docker container entry point
├── Dockerfile               # Container definition
├── README.md                # User-facing documentation (GitHub homepage)
├── requirements.txt         # Python dependencies
├── .env.example             # Environment variable template
├── _cache/                  # Runtime cache directory
├── logs/                    # Application logs
└── _resources/              # Development resources and test data
```

### Key Directories
- **`src/`**: Contains all application logic organized by functional domain (auth, scraping, matching, syncing)
- **`_cache/`**: Stores authentication tokens, API responses, and processed data to minimize re-authentication
- **`logs/`**: Application and debug logs for troubleshooting
- **`_resources/`**: Development artifacts, test data, and documentation templates

## 2. High-Level System Diagram

```
┌─────────┐
│  User   │
└────┬────┘
     │ (Docker run with credentials)
     ▼
┌────────────────────────────────────────┐
│        Docker Container                │
│  ┌──────────────────────────────────┐ │
│  │       main.py (CLI)              │ │
│  └────────────┬─────────────────────┘ │
│               ▼                        │
│  ┌──────────────────────────────────┐ │
│  │     SyncManager                  │ │ ◄─── Orchestration Layer
│  └──┬────────────────────────┬──────┘ │
│     │                        │         │
│     ▼                        ▼         │
│  ┌─────────────┐      ┌──────────┐   │
│  │ Crunchyroll │      │ AniList  │   │ ◄─── Service Adapters
│  │   Client    │      │  Client  │   │
│  └──────┬──────┘      └────┬─────┘   │
│         │                  │          │
└─────────┼──────────────────┼──────────┘
          │                  │
          ▼                  ▼
┌──────────────────┐   ┌──────────────┐
│   Crunchyroll    │   │   AniList    │ ◄─── External APIs
│   Web Platform   │   │  GraphQL API │
└──────────────────┘   └──────────────┘
```

### Data Flow
1. **Authentication**: Authenticate with both Crunchyroll (web scraping) and AniList (OAuth)
2. **Scraping**: Fetch watch history from Crunchyroll via Selenium
3. **Parsing**: Extract episode data from HTML
4. **Matching**: Map Crunchyroll titles to AniList entries using fuzzy matching
5. **Syncing**: Update AniList progress via GraphQL mutations
6. **Caching**: Store tokens and processed data to minimize API calls

## 3. Core Components

### 3.1. Orchestration Layer

#### SyncManager (`src/sync_manager.py`)
**Purpose**: Central coordinator for the entire sync process

**Key Responsibilities**:
- Orchestrate authentication with both services
- Manage pagination through Crunchyroll history
- Group episodes by series and season
- Coordinate title matching and progress updates
- Handle rewatch detection logic
- Implement smart early-stopping for already-synced content
- Global deduplication to prevent processing same anime multiple times

**Key Methods**:
- `run_sync()`: Main entry point for sync process
- `_update_anilist_progress_with_validation()`: Smart pagination with early stopping
- `_group_episodes_by_series_and_season()`: Episode aggregation per page
- `_process_series_entry()`: Handle individual anime series
- `_needs_update()`: Check if update is needed (with rewatch logic)
- `processed_anime_entries`: Dictionary tracking processed anime to prevent duplicates

**Technologies**: Pure Python, orchestrates all other components

### 3.2. Crunchyroll Adapter

#### CrunchyrollScraper (`src/crunchyroll_scraper.py`)
**Purpose**: Web scraping and authentication for Crunchyroll

**Key Responsibilities**:
- Browser automation via Selenium/undetected-chromedriver
- Login flow handling
- Watch history pagination
- Cloudflare bypass (via FlareSolverr)
- Token caching

**Technologies**: Selenium, undetected-chromedriver, FlareSolverr (optional)

#### CrunchyrollAuth (`src/crunchyroll_auth.py`)
**Purpose**: Handle Crunchyroll authentication and session management

**Technologies**: Selenium WebDriver, browser cookies

#### CrunchyrollParser (`src/crunchyroll_parser.py`)
**Purpose**: Parse HTML from Crunchyroll watch history pages

**Key Responsibilities**:
- Extract episode titles, series names, season numbers
- Handle different HTML structures (movies, episodes, specials)
- Normalize data format

**Technologies**: BeautifulSoup4 (or native HTML parsing)

### 3.3. AniList Adapter

#### AniListClient (`src/anilist_client.py`)
**Purpose**: High-level AniList operations with rewatch detection

**Key Responsibilities**:
- Orchestrate auth and API calls
- Implement rewatch detection logic
- Handle status transitions (PLANNING → CURRENT → COMPLETED)
- Manage repeat counters

**Key Methods**:
- `update_anime_progress_with_rewatch_logic()`: Main update entry point
- `_is_rewatch_scenario()`: Detect if user is rewatching
- `_handle_rewatch_update()`: Update ongoing rewatches
- `_handle_normal_update()`: Update first watches
- `_handle_new_watch()`: Initialize new anime entries

**Technologies**: Python, wraps AniListAPI and AniListAuth

#### AniListAuth (`src/anilist_auth.py`)
**Purpose**: OAuth authentication with AniList

**Key Responsibilities**:
- OAuth authorization code flow
- Token exchange and caching
- Token refresh logic
- User ID retrieval

**Technologies**: OAuth 2.0, AniList API

#### AniListAPI (`src/anilist_api.py`)
**Purpose**: GraphQL API wrapper for AniList

**Key Responsibilities**:
- GraphQL query/mutation execution
- Rate limiting (90 requests per minute)
- Error handling and retries
- API response parsing

**Key Endpoints**:
- `search_anime()`: Search by title
- `get_anime_list_entry()`: Get user's current progress
- `update_anime_progress()`: Update progress with status and repeat count

**Technologies**: GraphQL, requests library, rate limiting

### 3.4. Matching Layer

#### AnimeMatcher (`src/anime_matcher.py`)
**Purpose**: Intelligent title matching between Crunchyroll and AniList

**Key Responsibilities**:
- Fuzzy string matching
- Season detection from titles
- Handle alternate titles (English, Romaji, Native)
- Deal with naming variations

**Algorithm**:
- Title normalization (remove punctuation, lowercase)
- Similarity scoring (likely using Levenshtein distance)
- Season number extraction from titles
- Confidence threshold filtering

**Technologies**: String matching algorithms (fuzzywuzzy or difflib)

### 3.5. Support Modules

#### CacheManager (`src/cache_manager.py`)
**Purpose**: Persistent caching for tokens and API responses

**Key Responsibilities**:
- File-based caching in `_cache/` directory
- Token storage and retrieval
- Cache invalidation
- First-run flag management

**Technologies**: File I/O, JSON serialization

#### FlareSolverrClient (`src/flaresolvrrr_client.py`)
**Purpose**: Optional Cloudflare bypass for Crunchyroll

**Key Responsibilities**:
- Proxy requests through FlareSolverr
- Handle Cloudflare challenges
- Session management

**Technologies**: FlareSolverr API, HTTP requests

## 4. Data Stores

### 4.1. File-Based Cache
**Type**: JSON files in `_cache/` directory

**Purpose**: Store authentication tokens and processed data to minimize API calls and re-authentication

**Key Files**:
- `anilist_tokens.json`: AniList OAuth tokens
- `crunchyroll_session.json`: Crunchyroll session data
- `.first_run_complete`: Flag for Docker first-run detection

### 4.2. Log Files
**Type**: Text logs in `logs/` directory

**Purpose**: Application logging for debugging and monitoring

**Key Files**:
- `sync.log`: Main application log
- `cron.log`: Docker cron job logs (in container)

## 5. External Integrations / APIs

### 5.1. Crunchyroll
**Type**: Web scraping (no official API)

**Purpose**: Fetch user watch history

**Integration Method**: Selenium WebDriver with browser automation

**Authentication**: Email/password login with session cookies

**Challenges**: Cloudflare protection, dynamic HTML structure

### 5.2. AniList
**Type**: GraphQL API

**Purpose**: Update anime progress and retrieve anime metadata

**Integration Method**: GraphQL over HTTPS

**Authentication**: OAuth 2.0 authorization code flow

**Rate Limiting**: 90 requests per minute

**Endpoints**:
- `https://anilist.co/api/v2/oauth/authorize` - Authorization
- `https://anilist.co/api/v2/oauth/token` - Token exchange
- `https://graphql.anilist.co` - GraphQL API

### 5.3. FlareSolverr (Optional)
**Type**: Cloudflare bypass proxy

**Purpose**: Solve Cloudflare challenges for Crunchyroll access

**Integration Method**: HTTP API

**Configuration**: Via `FLARESOLVERR_URL` environment variable

## 6. Deployment & Infrastructure

**Containerization**: Docker with Alpine Linux base

**Key Services Used**:
- Chrome/Chromium for web scraping
- Python 3.9+
- Cron for scheduled syncs

**CI/CD Pipeline**: Not currently configured

**Monitoring & Logging**:
- File-based logging to `/app/logs/`
- Console output via Docker logs
- Debug mode available via `DEBUG` environment variable

**Deployment Targets**:
- Unraid Docker
- Any Docker-compatible platform
- Direct Python execution

## 7. Security Considerations

**Authentication**:
- Crunchyroll: Username/password stored in environment variables
- AniList: OAuth 2.0 with authorization code (reusable)

**Authorization**: User-level access only, no admin privileges needed

**Data Encryption**:
- HTTPS for all API calls
- Tokens stored in local filesystem (no encryption at rest)

**Key Security Practices**:
- No hardcoded credentials
- Environment variable-based configuration
- Minimal container permissions
- Headless browser mode by default

**Security Considerations**:
- Credentials stored in container environment (cleared on restart)
- Cache directory may contain sensitive tokens (protect volume mounts)
- No built-in credential rotation

## 8. Development & Testing Environment

**Local Setup**: See README.md for installation instructions

**Testing Frameworks**: Not currently implemented

**Code Quality Tools**:
- Python style: PEP 8 recommended
- No linters currently configured

**Development Mode**:
- `--debug`: Enable verbose logging
- `--dry-run`: Preview changes without updating AniList
- `--no-headless`: Show browser for debugging

## 9. Future Considerations / Roadmap

**Known Architectural Debts**:
- No unit tests or integration tests
- Hard dependency on Selenium (slow, resource-intensive)
- File-based caching (no expiration logic)
- No structured error recovery for partial failures
- Season mapping logic could be more robust

**Planned Improvements**:
- Add comprehensive test suite
- Implement structured logging (JSON format)
- Add metrics and monitoring hooks
- Support for other anime tracking sites (MAL, Kitsu)
- Web UI for configuration and monitoring
- Database backend for better state management

## 10. Bug Fixes & Recent Changes

### Critical Fixes (2024-10-30)
**Issue**: Completed shows incorrectly marked as "still watching" with incremented rewatch counters

**Root Causes**:
1. Per-page episode grouping causing older episodes to overwrite completed status
2. Overly aggressive rewatch detection treating old episodes as rewatches
3. Status transition logic incrementing rewatch counter for all COMPLETED→CURRENT transitions

**Solutions Implemented**:
1. **Global tracking** (`src/sync_manager.py:57, 255-261`): Added `processed_anime_entries` dictionary to track anime processed across pages
2. **Smarter rewatch detection** (`src/sync_manager.py:879-893`): Only treat episodes 1-3 as rewatches, skip older episodes
3. **Fixed status transitions** (`src/anilist_client.py:200-220`): Only increment rewatch counter for actual rewatches from beginning

**Impact**: Prevents duplicate processing and incorrect status updates during pagination

## 11. Project Identification

**Project Name**: Crunchyroll-AniList Sync

**Repository URL**: [To be added]

**Primary Contact**: Michael Price

**Date of Last Update**: 2025-01-30

**Version**: 0.2.1

## 12. Glossary / Acronyms

**CR**: Crunchyroll - Anime streaming service

**AL**: AniList - Anime/manga tracking and social networking service

**GraphQL**: Query language used by AniList API

**OAuth**: Authentication protocol used by AniList

**Selenium**: Web automation framework used for Crunchyroll scraping

**FlareSolverr**: Tool for bypassing Cloudflare protection

**Rewatch**: When a user watches an anime they've already completed

**Repeat Counter**: AniList field tracking number of times anime has been rewatched

**Episode Conversion**: Mapping absolute episode numbers to per-season numbering

**Smart Pagination**: Early-stopping algorithm that stops processing when most episodes are already synced

**Dry Run**: Preview mode that shows what would be changed without actually updating AniList
