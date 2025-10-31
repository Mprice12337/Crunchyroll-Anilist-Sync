# CLAUDE.md - Crunchyroll-AniList Sync

> **Purpose**: This file serves as your project's memory for Claude Code. It defines rules, workflows, and preferences that Claude will automatically follow when working on your codebase.

## Project Overview

**Crunchyroll-AniList Sync** is an automated synchronization tool that bridges the gap between Crunchyroll's watch history and AniList's anime tracking system. It scrapes your Crunchyroll viewing history and automatically updates your AniList anime list with accurate progress, including intelligent rewatch detection and episode number conversion.

### Key Features
- **Automated Sync**: Scrapes Crunchyroll watch history and updates AniList progress automatically
- **Intelligent Title Matching**: Fuzzy matching algorithm handles naming variations between platforms
- **Episode Conversion**: Maps absolute episode numbers to per-season numbering (e.g., Episode 24 → Season 2 Episode 12)
- **Rewatch Detection**: Automatically detects and tracks rewatches with proper repeat counters
- **Smart Pagination**: Early-stopping algorithm that skips already-synced content
- **Global Deduplication**: Prevents processing same anime multiple times across pagination
- **Docker Support**: Fully containerized with cron scheduling for hands-off operation
- **Cloudflare Bypass**: Optional FlareSolverr integration for reliable Crunchyroll access

### Project Context
- **Stage**: Production-ready (v0.2.1)
- **Team Size**: Solo developer (Michael Price)
- **Priority Focus**: Reliability, correctness, user-friendliness
- **Use Case**: Personal automation tool, Unraid Docker container

---

## Claude Code Preferences

### Workflow Mode
- **Default Model**: Sonnet for daily work / Opus for complex architectural changes
- **Planning Strategy**: Plan for complex tasks involving multiple files or architectural changes
- **Testing Approach**: Tests on request (no test suite currently exists)
- **Auto-Accept**: Disabled - always confirm before making changes

### Communication Style
- **Verbosity**: Detailed explanations for architectural decisions, concise for routine changes
- **Progress Updates**: Yes, keep user informed of progress especially for multi-step tasks
- **Error Handling**: Explain the issue, propose solution, then implement fix

### Task Management
- **To-Do Lists**: Auto-generate for complex tasks (3+ steps)
- **Subagents**: Use for exploration when searching for patterns across codebase
- **Research**: Proactive web search when dealing with AniList GraphQL API or Selenium issues

---

## Technology Stack

### Backend
- **Language**: Python 3.9+
- **Framework**: None (standalone CLI application)
- **Web Scraping**: Selenium with undetected-chromedriver
- **Browser**: Chrome/Chromium (headless by default)
- **API Client**: GraphQL for AniList (manual implementation)
- **Authentication**:
  - Crunchyroll: Selenium-based web login
  - AniList: OAuth 2.0 authorization code flow
- **Caching**: File-based JSON storage
- **Logging**: Python logging module with file and console handlers

### Infrastructure
- **Containerization**: Docker (Alpine Linux base)
- **Scheduling**: Cron for automated syncs
- **Deployment**: Unraid Docker, general Docker environments
- **Cloudflare Bypass**: FlareSolverr (optional)

### Key Dependencies
- `selenium` - Web automation for Crunchyroll scraping
- `undetected-chromedriver` - Anti-detection Chrome driver
- `requests` - HTTP client for API calls
- `python-dotenv` - Environment variable management
- `beautifulsoup4` or native parsing - HTML parsing

---

## Project Structure

```
CrunchyrollAnilistSync/
├── src/                      # Main application code
│   ├── sync_manager.py       # Orchestration layer
│   ├── crunchyroll_auth.py   # CR authentication
│   ├── crunchyroll_scraper.py # CR web scraping
│   ├── crunchyroll_parser.py # CR HTML parsing
│   ├── history_parser.py     # History data structures
│   ├── anilist_auth.py       # AL OAuth
│   ├── anilist_api.py        # AL GraphQL API
│   ├── anilist_client.py     # AL high-level client
│   ├── anime_matcher.py      # Title matching
│   ├── flaresolvrrr_client.py # Cloudflare bypass
│   └── cache_manager.py      # Caching layer
├── main.py                   # CLI entry point
├── entrypoint.sh            # Docker startup script
├── Dockerfile               # Container definition
├── requirements.txt         # Python dependencies
├── .env.example             # Environment template
├── _cache/                  # Runtime cache (gitignored)
├── logs/                    # Application logs (gitignored)
└── docs/                    # Documentation
    ├── README.md            # User documentation
    ├── ARCHITECTURE.md      # Technical architecture
    ├── CLAUDE.md            # This file
    └── TESTING_GUIDE.md     # Testing procedures
```

### Key Directories
- **`src/`**: All application logic, organized by domain (auth, scraping, matching, sync)
- **`_cache/`**: Persistent cache for tokens and processed data (not committed)
- **`logs/`**: Application and debug logs (not committed)
- **`_resources/`**: Development artifacts and test data (not committed)

---

## Core Architecture

### Primary Components

#### 1. SyncManager (`src/sync_manager.py`)
**Purpose**: Central orchestrator for entire sync process

**Key Responsibilities**:
- Coordinate authentication with both services
- Manage pagination through Crunchyroll history
- Group episodes by series and season per page
- Handle global deduplication via `processed_anime_entries` dict
- Coordinate title matching and progress updates
- Implement rewatch detection logic

**Important Methods**:
- `run_sync()`: Main entry point
- `_update_anilist_progress_with_validation()`: Smart pagination with early stopping
- `_process_series_entry()`: Handle individual anime updates
- `_needs_update()`: Determine if update needed (rewatch-aware)
- `_group_episodes_by_series_and_season()`: Per-page episode aggregation

**Recent Critical Fixes**:
- Added `processed_anime_entries` tracking to prevent duplicate processing across pages
- Fixed rewatch detection to only trigger on episodes 1-3 (not old episodes from pagination)

#### 2. AniListClient (`src/anilist_client.py`)
**Purpose**: High-level AniList operations with intelligent rewatch handling

**Key Methods**:
- `update_anime_progress_with_rewatch_logic()`: Main update entry point
- `_is_rewatch_scenario()`: Detect if user is rewatching (checks repeat counter)
- `_handle_rewatch_update()`: Update ongoing rewatches
- `_handle_normal_update()`: Handle first watches and status transitions
- `_handle_new_watch()`: Initialize new anime entries

**Rewatch Logic**:
- Increment repeat counter only when user actually starts over (episodes 1-3)
- Maintain repeat counter for ongoing rewatches
- Handle COMPLETED → CURRENT transitions correctly
- Differentiate between true rewatches and old pagination data

#### 3. CrunchyrollScraper (`src/crunchyroll_scraper.py`)
**Purpose**: Web scraping and authentication for Crunchyroll

**Key Features**:
- Selenium-based browser automation
- Undetected-chromedriver for anti-detection
- Optional FlareSolverr for Cloudflare bypass
- Session caching to minimize re-authentication
- Pagination through watch history

#### 4. AnimeMatcher (`src/anime_matcher.py`)
**Purpose**: Intelligent title matching between platforms

**Challenges**:
- Different naming conventions (English vs Romaji vs Native)
- Season numbering variations
- Special characters and punctuation
- Abbreviations and alternate titles

**Strategy**:
- Fuzzy string matching with similarity scoring
- Multiple title variants (English, Romaji)
- Season detection from titles
- Confidence threshold filtering

### Design Patterns Used
- **Facade Pattern**: SyncManager provides simplified interface to complex subsystems
- **Adapter Pattern**: Service-specific clients (CrunchyrollScraper, AniListClient) adapt external APIs
- **Strategy Pattern**: Different update strategies based on status (new, ongoing, rewatch, completed)
- **Template Method**: Rewatch detection logic shared across update methods

### Data Flow
```
User Credentials → Authentication → Scraping → Parsing → Matching → Syncing
                        ↓               ↓          ↓         ↓         ↓
                      Cache         History    Episodes   Titles   Progress
                                                    ↓         ↓         ↓
                                             Per-page    AniList   Updates
                                             grouping    search    w/rewatch
```

---

## Development Workflow

### Git Strategy
- **Main Branch**: `main` (production-ready code)
- **Branch Naming**: `feature/*`, `bugfix/*`, `hotfix/*`
- **Commit Convention**: Descriptive commits with context

#### Git Best Practices
- Keep commits atomic and focused
- Write clear commit messages explaining "why" not just "what"
- Test changes before committing (use --dry-run mode)

### Code Review Process
- Solo project - self-review before pushing
- Test with --dry-run and --debug flags
- Verify on test account before using on production data

---

## Testing Strategy

### Test Framework
**Status**: No formal test suite currently implemented

### Manual Testing Approach
1. Use `--dry-run` flag to preview changes without updating AniList
2. Use `--debug` flag for verbose logging
3. Test with clean test account first
4. Monitor logs for unexpected behavior
5. Verify updates in AniList web UI

### Testing Commands
```bash
python main.py --dry-run --debug           # Preview with detailed logging
python main.py --dry-run --max-pages 2     # Test with limited pages
python main.py --no-headless              # Watch browser for debugging
python main.py --clear-cache              # Start fresh
```

### Testing Preferences
- **TDD**: Not currently practiced
- **Test Generation**: Future consideration
- **Manual Testing**: Required before releases

---

## Code Quality Standards

### Linting & Formatting
- **Style**: PEP 8 (Python standard)
- **Linter**: Not currently configured (ESLint equivalent recommended: flake8, ruff)
- **Formatter**: Not currently configured (Prettier equivalent recommended: black)
- **Pre-commit Hooks**: Not configured

### Commands
```bash
python -m py_compile src/*.py              # Check syntax
python -m flake8 src/                      # Lint (if installed)
python -m black src/                       # Format (if installed)
```

### Style Guidelines
- **Indentation**: 4 spaces (Python standard)
- **Line Length**: 100 characters (relaxed from PEP 8's 79)
- **Naming Conventions**:
  - Files & Modules: `snake_case` (e.g., `sync_manager.py`, `anilist_client.py`)
  - Classes: `PascalCase` (e.g., `SyncManager`, `AniListClient`)
  - Functions/Methods: `snake_case` (e.g., `run_sync`, `update_anime_progress`)
  - Variables: `snake_case` (e.g., `anime_id`, `current_progress`)
  - Constants: `UPPER_SNAKE_CASE` (e.g., `MAX_PAGES`, `API_ENDPOINT`)
  - Private Methods: `_leading_underscore` (e.g., `_needs_update`, `_handle_rewatch`)

---

## Environment Setup

### Required Environment Variables
```bash
# Crunchyroll credentials (REQUIRED)
CRUNCHYROLL_EMAIL=your_email@example.com
CRUNCHYROLL_PASSWORD=your_password

# AniList OAuth authorization code (REQUIRED)
# Get from: https://anilist.co/api/v2/oauth/authorize?client_id=21538&response_type=code
ANILIST_AUTH_CODE=your_auth_code_here

# Optional configuration
FLARESOLVERR_URL=http://localhost:8191  # Cloudflare bypass
TZ=America/New_York                     # Timezone
DEBUG=false                             # Debug logging
DRY_RUN=false                           # Preview mode
MAX_PAGES=10                            # History pages to process
HEADLESS=true                           # Headless browser
CRON_SCHEDULE="0 2 * * *"              # Daily at 2 AM
```

### Docker Volume Paths
**Container Paths** (fixed):
- `/app/_cache` - Authentication tokens and cache
- `/app/logs` - Application logs

**Host Paths** (customize):
```bash
/path/to/appdata/crunchyroll-anilist-sync:/app/_cache
/path/to/appdata/crunchyroll-anilist-sync/logs:/app/logs
```

---

## Database

**Type**: File-based cache (JSON)

**Location**: `_cache/` directory

### Cache Files
- `anilist_tokens.json` - OAuth tokens (access_token, refresh_token, expiry)
- `crunchyroll_session.json` - Session cookies and state
- `.first_run_complete` - Docker first-run flag

### Cache Strategy
- No expiration logic (manual clear via `--clear-cache`)
- Tokens refreshed automatically when expired
- Cache persists across container restarts

---

## API Documentation

### AniList GraphQL API
- **Base URL**: `https://graphql.anilist.co`
- **Authentication**: OAuth 2.0 Bearer token
- **Rate Limiting**: 90 requests per minute (enforced in `anilist_api.py`)

#### Key Queries/Mutations
```graphql
# Search for anime
query ($search: String) {
  Page(perPage: 10) {
    media(search: $search, type: ANIME) {
      id, title { romaji, english }, episodes, format, startDate
    }
  }
}

# Get user's list entry
query ($mediaId: Int, $userId: Int) {
  MediaList(mediaId: $mediaId, userId: $userId) {
    id, progress, status, repeat
  }
}

# Update progress
mutation ($mediaId: Int, $progress: Int, $status: MediaListStatus, $repeat: Int) {
  SaveMediaListEntry(mediaId: $mediaId, progress: $progress, status: $status, repeat: $repeat) {
    id, progress, status, repeat
  }
}
```

### Crunchyroll (Web Scraping)
- **No official API** - uses Selenium web scraping
- **Watch History URL**: `https://www.crunchyroll.com/history`
- **Authentication**: Web form login
- **Pagination**: Infinite scroll (loaded page by page)

---

## Coding Conventions

### General Principles
1. **Separation of Concerns**: Each module has single responsibility (auth, scraping, matching, sync)
2. **Explicit Over Implicit**: Clear naming, verbose logging, obvious data flow
3. **Error Tolerance**: Continue processing on individual failures, log errors clearly
4. **Idempotency**: Safe to run multiple times, won't duplicate updates

### Project-Specific Rules

#### 1. Rewatch Detection Logic
**Critical**: Only increment repeat counter for true rewatches (episodes 1-3), not old pagination data

```python
# CORRECT: Check if actually rewatching from beginning
if current_status == 'COMPLETED' and target_progress <= 3:
    new_repeat = current_repeat + 1

# WRONG: Don't increment for old episodes
if current_status == 'COMPLETED' and target_progress < current_progress:
    # This would catch old episodes from pagination!
```

#### 2. Global Deduplication
**Critical**: Track processed anime globally to prevent duplicate updates across pages

```python
# Add to processed_anime_entries after successful update
self.processed_anime_entries[anime_id] = actual_episode

# Check before processing
if anime_id in self.processed_anime_entries:
    if actual_episode <= self.processed_anime_entries[anime_id]:
        return False  # Skip, already processed
```

#### 3. Episode Grouping
**Critical**: Group episodes per page, take highest episode per (series, season) tuple

```python
# Group by (series_title, season) tuple
series_season_progress = {}
for episode in episodes:
    key = (series_title, season)
    if episode_number > series_season_progress.get(key, 0):
        series_season_progress[key] = episode_number
```

### Error Handling
- **Logging**: Use Python `logging` module at appropriate levels (DEBUG, INFO, WARNING, ERROR)
- **User-Facing Errors**: Clear, actionable messages (e.g., "❌ Authentication failed. Check credentials.")
- **Debugging**: Enable with `--debug` flag, logs to both file and console
- **Recovery**: Continue processing other anime on individual failures

### Performance Considerations
- **Caching**: Minimize API calls by caching tokens and responses
- **Rate Limiting**: Respect AniList's 90 req/min limit (handled in `anilist_api.py`)
- **Early Stopping**: Stop processing when 70%+ of items are already synced
- **Smart Delays**: Adaptive delays based on rate limiter status
- **Pagination**: Process in pages, not all at once

---

## Common Tasks

### Adding a New Feature
1. Identify which component(s) need modification
2. Update relevant module(s) in `src/`
3. Test with `--dry-run --debug` flags
4. Update documentation (README.md, ARCHITECTURE.md, this file)
5. Test with real account

### Debugging
- **Logs Location**: `logs/sync.log` (or `/app/logs/sync.log` in container)
- **Debug Mode**: `python main.py --debug` or set `DEBUG=true` env var
- **Browser Visibility**: `python main.py --no-headless` to watch browser
- **Dry Run**: `python main.py --dry-run` to preview changes
- **Common Issues**: See TESTING_GUIDE.md and README.md troubleshooting sections

### Modifying Sync Logic
1. Most changes go in `SyncManager` (`src/sync_manager.py`)
2. Rewatch logic: `AniListClient` (`src/anilist_client.py`)
3. Title matching: `AnimeMatcher` (`src/anime_matcher.py`)
4. Always test with `--dry-run` first
5. Check edge cases: first watch, rewatch, completed series, movies

---

## Docker Configuration

### Base Image
- **Base**: `python:3.9-slim`
- **Optimizations**: Multi-stage builds, layer caching, minimal dependencies

### Environment Variables
All container settings configurable via environment variables (see Environment Setup section)

### Standard Logging
- **Primary Log**: `/app/logs/sync.log` (application log)
- **Cron Log**: `/app/logs/cron.log` (scheduled run log)
- **Console**: Docker logs (stdout/stderr)

### Docker Commands
```bash
docker build -t crunchyroll-anilist-sync .
docker run -d --name cr-al-sync \
  --env-file .env \
  -v ./data/_cache:/app/_cache \
  -v ./data/logs:/app/logs \
  crunchyroll-anilist-sync

docker logs -f cr-al-sync                 # View logs
docker exec cr-al-sync ls -la /app/_cache # Inspect cache
docker exec cr-al-sync rm /app/_cache/.first_run_complete  # Reset first run
```

---

## Security & Privacy

### Security Best Practices
1. **Never hardcode credentials** - always use environment variables
2. **Secure token storage** - cache files contain sensitive tokens, protect volume mounts
3. **HTTPS only** - all API calls use HTTPS
4. **Minimal permissions** - container runs with minimal privileges

### Authentication/Authorization
- **Crunchyroll**: User-level access via username/password
- **AniList**: User-level OAuth (authorization code flow)
- **No elevated privileges** required

### Data Privacy
- **PII**: Email addresses, usernames stored in environment
- **Watch history**: Processed locally, not shared
- **Tokens**: Cached locally, not transmitted except to respective services
- **Compliance**: Personal use tool, no GDPR/HIPAA requirements

---

## Known Issues & Gotchas

### Common Pitfalls

#### 1. Pagination Bug (FIXED in v0.2.1)
**Issue**: Older episodes overwrote completed status, incremented rewatch counter incorrectly

**Solution**: Global deduplication tracking, smarter rewatch detection

**How to Avoid**: Always check `processed_anime_entries` before processing

#### 2. Cloudflare Protection
**Issue**: Crunchyroll may block scraping attempts

**Solution**: Use FlareSolverr (`FLARESOLVERR_URL` env var)

**How to Avoid**: Run FlareSolverr container, configure URL in `.env`

#### 3. AniList Rate Limiting
**Issue**: Exceeding 90 requests per minute causes errors

**Solution**: Built-in rate limiter in `anilist_api.py`

**How to Avoid**: Don't modify rate limiting logic without careful testing

#### 4. Season Mapping Failures
**Issue**: Episode numbers don't match between CR and AL

**Symptoms**: "Could not map episode" warnings

**Cause**: Different season structures or absolute vs per-season numbering

**Mitigation**: Fallback logic in `_determine_correct_entry_and_episode()`

### Technical Debt
- No formal test suite (manual testing only)
- File-based caching (no expiration, no corruption handling)
- Selenium dependency (slow, resource-intensive)
- Limited error recovery for partial failures
- Season mapping could be more robust

---

## Quick Reference

### Most Common Commands
```bash
# Development
python main.py --dry-run --debug          # Test with verbose output
python main.py --no-headless --max-pages 2 # Debug with visible browser
python main.py --clear-cache              # Start fresh

# Docker
docker build -t cr-al-sync:fixed .
docker logs -f cr-al-sync
docker exec cr-al-sync cat /app/logs/sync.log
docker exec cr-al-sync rm /app/_cache/.first_run_complete

# Debugging
grep "Rewatch would be detected" logs/sync.log  # Check for false rewatches
grep "already processed" logs/sync.log         # Check deduplication
grep "ERROR" logs/sync.log                     # Find errors
```

### File Locations
- **Config**: `/app/_cache` (in container)
- **Logs**: `/app/logs` (in container)
- **Main Entry**: `main.py`
- **Core Logic**: `src/sync_manager.py`
- **Rewatch Logic**: `src/anilist_client.py`

---

## Notes for Claude

### When Working on This Project

**Always Consider**:
- Rewatch detection is critical - test thoroughly
- Global deduplication prevents duplicate processing
- Episode grouping happens per-page, not globally
- AniList rate limits must be respected
- Log messages should be clear and actionable

**Before Making Changes**:
- Read ARCHITECTURE.md for system overview
- Check recent bug fixes (see Architecture section 10)
- Test with `--dry-run` first
- Consider pagination edge cases

**When Debugging**:
- Enable `--debug` flag
- Check both application and cron logs
- Look for "already processed" messages (good)
- Look for "Rewatch would be detected" (potentially bad if on old episodes)
- Verify status transitions (PLANNING → CURRENT → COMPLETED)

**What to Update**:
- This file (CLAUDE.md) when workflow/conventions change
- ARCHITECTURE.md when adding components or fixing major bugs
- README.md when adding user-facing features
- TESTING_GUIDE.md when adding testing procedures

---

**Last Updated**: 2025-01-30
