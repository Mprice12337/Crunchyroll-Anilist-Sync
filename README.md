# Crunchyroll-AniList Sync

A simplified Python application that automatically syncs your Crunchyroll watch history with your AniList anime progress.

## Features

- 🔐 Secure authentication with both Crunchyroll and AniList
- 📚 Scrapes Crunchyroll watch history with smart pagination and early stopping
- 🎯 Intelligent anime title matching between platforms with fuzzy search
- 📈 Updates AniList progress with accurate episode conversion (absolute → per-season)
- 🔄 Intelligent rewatch detection with proper repeat counter management
- 💾 Smart caching to minimize re-authentication and API calls
- 🚫 Global deduplication prevents duplicate processing across pages
- 🐳 Docker support with cron scheduling for automated syncs
- 🛡️ Optional FlareSolverr integration for Cloudflare bypass
- 🔍 Debug mode, dry-run support, and detailed matching diagnostics for testing
- 🔧 Simple configuration via environment variables

## Quick Start

### Prerequisites

- Python 3.9 or higher
- Chrome/Chromium browser (for web scraping)
- Crunchyroll Premium account (recommended)
- AniList account

### Installation

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd crunchyroll-anilist-sync
   ```

2. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Configure environment variables**
   ```bash
   cp .env.example .env
   ```

   Edit `.env` with your credentials:
   ```env
   CRUNCHYROLL_EMAIL=your_email@example.com
   CRUNCHYROLL_PASSWORD=your_password
   ANILIST_AUTH_CODE=your_auth_code_here
   FLARESOLVERR_URL=http://localhost:8191  # Optional
   ```

### AniList Authentication Setup

The sync tool uses a static OAuth client. Follow these steps to get your authentication code:

1. **Visit the authorization URL**:
   ```
   https://anilist.co/api/v2/oauth/authorize?client_id=21538&response_type=code
   ```

2. **Authorize the application**:
   - You'll be redirected to AniList's authorization page
   - Click "Approve" to authorize the sync tool
   - You'll see a PIN code on the next page

3. **Copy the auth code**:
   - Copy the entire code from the PIN page
   - Add it to your `.env` file as `ANILIST_AUTH_CODE`

4. **The auth code is reusable**:
   - Once authenticated, your access token is cached
   - You only need to get a new auth code if the cache is cleared
   - Auth codes don't expire, but cached tokens may expire after 1 year

**Example:**
```env
ANILIST_AUTH_CODE=def502003a1b2c3d4e5f6789...
```

### Usage

```bash
# Basic sync (headless mode)
python main.py

# Run with visible browser (for debugging)
python main.py --no-headless

# Enable debug logging
python main.py --debug

# Dry run (see what would be updated without making changes)
python main.py --dry-run

# Debug matching mode (captures diagnostic data, implies --dry-run)
python main.py --debug-matching --max-pages 10

# Save changeset for review before applying (implies --dry-run)
python main.py --save-changeset --max-pages 10

# Apply a previously saved changeset
python main.py --apply-changeset _cache/changesets/changeset_20260122_103045.json

# Disable early stopping to scan all requested pages (useful for full scans)
python main.py --no-early-stop --max-pages 20

# Limit history pages to scrape
python main.py --max-pages 5

# Clear cache before running (requires new AniList auth)
python main.py --clear-cache
```

## Configuration

### Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `CRUNCHYROLL_EMAIL` | Yes | Your Crunchyroll email address |
| `CRUNCHYROLL_PASSWORD` | Yes | Your Crunchyroll password |
| `ANILIST_AUTH_CODE` | Yes | Your AniList OAuth authorization code (see setup above) |
| `FLARESOLVERR_URL` | No | FlareSolverr URL for Cloudflare bypass |

### Command Line Options

- `--debug`: Enable detailed debug logging
- `--headless`: Run browser in headless mode (default)
- `--no-headless`: Show browser window (useful for debugging)
- `--dry-run`: Show what would be updated without making changes
- `--debug-matching`: Enable detailed matching diagnostics and export debug data (implies --dry-run)
- `--save-changeset`: Save AniList updates to a changeset file for review before applying (implies --dry-run and --no-early-stop)
- `--apply-changeset FILE`: Apply a previously saved changeset file (skips Crunchyroll scraping)
- `--no-early-stop`: Disable early stopping when most items are already synced (useful for full scans)
- `--max-pages N`: Maximum number of history pages to scrape (default: 10)
- `--clear-cache`: Clear all cached data before running

## Docker Usage

### Using Docker Compose

1. **Copy and configure environment file**:
   ```bash
   cp .env.example .env
   # Edit .env with your credentials and auth code
   ```

2. **Get your AniList auth code** (if not already done):
   - Visit: https://anilist.co/api/v2/oauth/authorize?client_id=21538&response_type=code
   - Authorize and copy the code
   - Add to `.env` as `ANILIST_AUTH_CODE`

3. **Build and run**:
   ```bash
   docker-compose up -d
   ```

4. **View logs**:
   ```bash
   docker logs -f crunchyroll-anilist-sync
   ```

The container will:
- Run an initial sync on startup
- Schedule automatic syncs based on `CRON_SCHEDULE` (default: daily at 2 AM)
- Store cache and logs in the `./data` directory

### Environment Variables (Docker)

Additional Docker-specific variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `CRON_SCHEDULE` | `0 2 * * *` | Cron schedule for automatic syncs |
| `TZ` | `America/New_York` | Timezone (e.g., America/Los_Angeles, Europe/London) |
| `HEADLESS` | `true` | Run browser in headless mode |
| `DEBUG` | `false` | Enable debug logging |
| `DRY_RUN` | `false` | Preview changes without updating AniList |
| `MAX_PAGES` | `10` | Maximum history pages to process (subsequent runs) |

### Running on Unraid

For Unraid users, you can configure the container using environment variables in the Docker template:

**To enable debugging and dry-run mode:**
1. In your Unraid Docker settings for this container, add these environment variables:
   - `DEBUG` = `true`
   - `DRY_RUN` = `true`
2. Start the container
3. The sync will run with debug logging and show what would be changed without actually updating AniList

**To test the fix for completed shows:**
```
DEBUG=true
DRY_RUN=true
```

**For production use (after testing):**
```
DEBUG=false
DRY_RUN=false
```

**Additional optional settings:**
```
TZ=America/Los_Angeles    # Set your timezone (default: America/New_York)
MAX_PAGES=5               # Process only 5 pages of history
CRON_SCHEDULE=0 3 * * *   # Run at 3 AM instead of 2 AM
```

**Common timezone examples:**
- US Pacific: `America/Los_Angeles`
- US Mountain: `America/Denver`
- US Central: `America/Chicago`
- US Eastern: `America/New_York`
- UK: `Europe/London`
- Europe Central: `Europe/Paris`
- Asia Tokyo: `Asia/Tokyo`

**Note:** Changes to environment variables require restarting the container to take effect.

## Optional: FlareSolverr Setup

FlareSolverr helps bypass Cloudflare protection that Crunchyroll may use.

### Using Docker:
```bash
docker run -d \
  --name=flaresolverr \
  -p 8191:8191 \
  -e LOG_LEVEL=info \
  --restart unless-stopped \
  ghcr.io/flaresolverr/flaresolverr:latest
```

Then add to your `.env`:
```env
FLARESOLVERR_URL=http://localhost:8191
```

## Troubleshooting

### Common Issues

1. **AniList Authentication Failed**: 
   - Your auth code may be invalid or expired
   - Visit the authorization URL again to get a new code
   - Make sure you copied the entire code from the PIN page
   - If cache is cleared, you'll need to provide the auth code again

2. **Login Failed**: 
   - Verify your Crunchyroll credentials
   - Try running with `--no-headless` to see what's happening
   - Clear cache with `--clear-cache`

3. **Cloudflare Challenges**:
   - Set up FlareSolverr (recommended)
   - Try running with `--no-headless`
   - Wait a few minutes and try again

4. **No Anime Found**:
   - The anime might not be on AniList
   - Title matching might fail for obscure shows
   - Check the debug logs for matching details

## Debug Matching Mode

The `--debug-matching` flag enables comprehensive diagnostic data collection to help troubleshoot anime matching issues. This mode automatically runs in dry-run mode (no AniList updates) and exports detailed matching data to `_cache/debug/`.

### Usage

```bash
# Capture matching diagnostics for 10 pages of history
python main.py --debug-matching --max-pages 10
```

### Output Files

All files are timestamped (e.g., `_YYYYMMDD_HHMMSS`) and saved to `_cache/debug/`:

1. **`crunchyroll_history_*.json`** - Raw and parsed Crunchyroll watch history data
   - Contains the original API responses and parsed episode data
   - Useful for verifying what Crunchyroll is reporting

2. **`anilist_searches_*.json`** - All AniList search queries and results
   - Shows what searches were made and what candidates were returned
   - Includes similarity scores for each candidate

3. **`matching_decisions_*.json`** - Detailed decision records for each episode
   - Input data (CR title, season, episode)
   - All candidates considered with scores
   - Season structure mappings
   - Final selection and reasoning

4. **`matching_summary_*.csv`** - Spreadsheet-friendly summary
   - Quick overview of all matching decisions
   - Columns: CR Title, Season, Episode, Top Match, Selected Anime, Outcome, Reason
   - Easy to import into Excel/Google Sheets for analysis

### Use Cases

- **Troubleshooting mismatches**: Identify why specific anime are being matched incorrectly
- **Testing improvements**: Validate matching algorithm changes before deployment
- **Understanding the algorithm**: See how season structures are built and episodes are mapped
- **Reporting issues**: Include debug files when reporting matching problems

### Matching Algorithm Features

The matching system includes several smart features:

- **Similarity threshold filtering** (0.7 minimum) to exclude unrelated anime
- **Format-based filtering** to exclude supplemental content (commentary, recap, etc.)
- **Intelligent season structure building** from search results
- **TV format preference** over ONA (Original Net Animation) for main seasons
- **Cumulative episode mapping** for absolute vs per-season numbering
- **Enhanced movie matching** using actual movie titles from Crunchyroll metadata
- **Fallback mechanisms** for edge cases and franchise titles

## Changeset Workflow

The changeset workflow allows you to review and approve AniList updates before they are applied. This is useful for:
- **Testing new matching algorithms** without accidentally updating your list
- **Reviewing updates** before committing them to AniList
- **Batch processing** updates at a later time
- **Sharing updates** with others for review

### How It Works

The changeset workflow has two stages:

#### Stage 1: Save Changeset (Dry Run)

Run a sync with `--save-changeset` to:
1. Scrape your Crunchyroll watch history
2. Match anime and determine what updates would be made
3. Save all updates to a changeset file in `_cache/changesets/`
4. **No changes are made to AniList**

```bash
# Save changeset for the last 10 pages of history
python main.py --save-changeset --max-pages 10

# Output: Changeset saved to _cache/changesets/changeset_20260122_103045.json
```

#### Stage 2: Apply Changeset (Wet Run)

After reviewing the changeset file, apply it with `--apply-changeset`:
1. Loads the changeset file
2. Authenticates with AniList
3. Applies each update in sequence
4. Reports success/failure for each update
5. **Skips Crunchyroll scraping entirely**

```bash
# Apply the changeset
python main.py --apply-changeset _cache/changesets/changeset_20260122_103045.json
```

### Changeset File Format

Changeset files are JSON with this structure:

```json
{
  "created_at": "2026-01-22T10:30:00",
  "session_timestamp": "20260122_103045",
  "total_changes": 3,
  "changes": [
    {
      "anime_id": 154587,
      "anime_title": "Sousou no Frieren 2nd Season",
      "progress": 1,
      "total_episodes": 28,
      "update_type": "normal",
      "cr_source": {
        "series": "Frieren: Beyond Journey's End",
        "season": 2,
        "episode": 1,
        "is_movie": false
      },
      "timestamp": "2026-01-22T10:30:15"
    }
  ]
}
```

### Reviewing a Changeset

Before applying, review the changeset to ensure the matches are correct:

1. **Check the JSON file** directly for detailed information
2. **Verify anime_id and anime_title** match what you expect
3. **Check progress values** are correct
4. **Review cr_source** to see the original Crunchyroll data
5. **Look for update_type** to understand what kind of update it is:
   - `normal`: Standard progress update
   - `rewatch`: Rewatch detected
   - `new_series`: Starting a new series

### Use Cases

**Test before committing:**
```bash
# Save changeset with new matching algorithm
python main.py --save-changeset --max-pages 5

# Review the changeset file
cat _cache/changesets/changeset_*.json | jq '.changes[] | {title: .anime_title, progress: .progress}'

# Apply if satisfied
python main.py --apply-changeset _cache/changesets/changeset_*.json
```

**Combine with debug matching:**
```bash
# Run both debug matching and save changeset
python main.py --debug-matching --save-changeset --max-pages 10

# Review both the matching diagnostics AND the changeset
# Apply when confident
python main.py --apply-changeset _cache/changesets/changeset_*.json
```

**Schedule updates:**
```bash
# During the day: save changeset (fast, no updates)
python main.py --save-changeset

# At night: apply changeset (no scraping needed)
python main.py --apply-changeset _cache/changesets/changeset_20260122_103045.json
```

### Important Notes

- **Changesets are timestamped** - each run creates a new file
- **Changesets are independent** - applying one doesn't affect others
- **No Crunchyroll auth needed** - `--apply-changeset` only needs AniList auth
- **Changesets can be edited** - manually fix matches in JSON before applying
- **Idempotent updates** - applying the same changeset twice won't cause issues (AniList handles duplicates)

## Documentation

For developers and contributors:

- **[ARCHITECTURE.md](docs/ARCHITECTURE.md)** - Technical architecture and system design
- **[CLAUDE.md](docs/CLAUDE.md)** - Claude Code configuration and coding conventions

### Recent Updates

**v0.2.1 (2025-01-30)** - Critical Bug Fixes
- Fixed completed shows being incorrectly marked as "still watching"
- Fixed incorrect rewatch counter increments
- Added global deduplication to prevent duplicate processing across pages
- Improved rewatch detection to only trigger on episodes 1-3
- Added support for DEBUG, DRY_RUN, and MAX_PAGES environment variables in Docker

## License

This project is for educational and personal use. Please respect the terms of service of both Crunchyroll and AniList.

## Disclaimer

This tool is not affiliated with Crunchyroll or AniList. Use at your own risk and ensure compliance with both services' terms of service.