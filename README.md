# Crunchyroll-AniList Sync

A simplified Python application that automatically syncs your Crunchyroll watch history with your AniList anime progress.

## Features

- 🔐 Secure authentication with both Crunchyroll and AniList
- 📚 Scrapes Crunchyroll watch history with pagination support
- 🎯 Intelligent anime title matching between platforms
- 📈 Updates AniList progress based on your viewing history
- 💾 Smart caching to minimize re-authentication and API calls
- 🐳 Docker support with optional FlareSolverr integration
- 🔧 Simple configuration and straightforward operation

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
   ANILIST_CLIENT_ID=your_client_id
   ANILIST_CLIENT_SECRET=your_client_secret
   FLARESOLVERR_URL=http://localhost:8191  # Optional
   ```

### AniList OAuth Setup

1. Go to https://anilist.co/settings/developer
2. Create a new client application:
   - **Name**: Crunchyroll Sync (or any name you prefer)
   - **Redirect URI**: `https://anilist.co/api/v2/oauth/pin`
3. Copy the Client ID and Client Secret to your `.env` file

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

# Limit history pages to scrape
python main.py --max-pages 5

# Clear cache before running
python main.py --clear-cache
```

## Configuration

### Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `CRUNCHYROLL_EMAIL` | Yes | Your Crunchyroll email address |
| `CRUNCHYROLL_PASSWORD` | Yes | Your Crunchyroll password |
| `ANILIST_CLIENT_ID` | Yes | AniList OAuth client ID |
| `ANILIST_CLIENT_SECRET` | Yes | AniList OAuth client secret |
| `FLARESOLVERR_URL` | No | FlareSolverr URL for Cloudflare bypass |

### Command Line Options

- `--debug`: Enable detailed debug logging
- `--headless`: Run browser in headless mode (default)
- `--no-headless`: Show browser window (useful for debugging)
- `--dry-run`: Show what would be updated without making changes
- `--max-pages N`: Maximum number of history pages to scrape (default: 10)
- `--clear-cache`: Clear all cached data before running

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

## How It Works

1. **Authentication**: Authenticates with both Crunchyroll and AniList using cached credentials when possible
2. **History Scraping**: Scrapes your Crunchyroll watch history using Selenium with Cloudflare protection handling
3. **Title Matching**: Uses fuzzy string matching to find corresponding anime on AniList
4. **Progress Update**: Updates your AniList progress based on the highest episode watched for each series
5. **Caching**: Caches authentication and anime mappings to speed up subsequent runs

## Architecture

The application consists of several clean, focused modules:

- **`main.py`**: Entry point and argument parsing
- **`sync_manager.py`**: Orchestrates the entire sync process
- **`crunchyroll_scraper.py`**: Handles Crunchyroll authentication and history scraping
- **`anilist_client.py`**: Manages AniList API interactions
- **`anime_matcher.py`**: Matches anime titles between platforms
- **`cache_manager.py`**: Handles authentication and data caching

## Troubleshooting

### Common Issues

1. **Login Failed**: 
   - Verify your Crunchyroll credentials
   - Try running with `--no-headless` to see what's happening
   - Clear cache with `--clear-cache`

2. **Cloudflare Challenges**:
   - Set up FlareSolverr (recommended)
   - Try running with `--no-headless`
   - Wait a few minutes and try again

3. **No Anime Found**:
   - The anime might not be on AniList
   - Title matching might fail for obscure shows
   - Check the debug logs for matching details

4. **Rate Limiting**:
   - The app includes automatic rate limiting
   - If issues persist, reduce `--max-pages`

### Debug Mode

Run with `--debug` to see detailed logs:
```bash
python main.py --debug --no-headless
```

This will show:
- Authentication steps
- HTML parsing details
- Anime matching scores
- API request/response information

## Development

### Project Structure
```
crunchyroll-anilist-sync/
├── main.py                 # Entry point
├── src/                    # Main source code
│   ├── sync_manager.py     # Sync orchestration
│   ├── crunchyroll_scraper.py  # Crunchyroll integration
│   ├── anilist_client.py   # AniList API client
│   ├── anime_matcher.py    # Title matching logic
│   ├── cache_manager.py    # Caching utilities
│   └── flaresolverr_client.py  # FlareSolverr integration
├── logs/                   # Application logs
├── _cache/                 # Cached data
└── requirements.txt        # Python dependencies
```

### Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests if applicable
5. Submit a pull request

## License

This project is for educational and personal use. Please respect the terms of service of both Crunchyroll and AniList.

## Disclaimer

This tool is not affiliated with Crunchyroll or AniList. Use at your own risk and ensure compliance with both services' terms of service.