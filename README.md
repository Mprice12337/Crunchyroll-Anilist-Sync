# Crunchyroll-AniList Sync

A Python application that automatically syncs your Crunchyroll watch history with your AniList anime progress.

## Features

- 🔐 Logs into your Crunchyroll account and scrapes watch history
- 🔗 Authenticates with AniList using OAuth2
- 🎯 Matches anime titles between platforms with intelligent fuzzy matching
- 📈 Updates your AniList progress based on Crunchyroll viewing history
- 🐳 Dockerized for easy deployment
- 🛡️ FlareSolverr integration for Cloudflare challenge bypassing
- 💾 Smart caching system to minimize API calls and avoid duplicate updates
- 🚀 Support for both API-based and HTML scraping methods
- 🔧 Development mode with comprehensive debug output

## Setup

### Prerequisites

- Python 3.9 or higher
- Chrome/Chromium browser (for Selenium)
- Crunchyroll Premium account (recommended for full history access)
- AniList account
- (Optional) FlareSolverr Docker container for Cloudflare protection

### Installation

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd CrunchyrollAnilistSync
   ```

2. **Install dependencies**
   ```bash
   # Using uv (recommended)
   uv sync

   # Or using pip
   pip install -e .
   ```

3. **Set up environment variables**
   ```bash
   cp .env.example .env
   ```

   Edit `.env` and fill in your credentials:
   ```env
   CRUNCHYROLL_EMAIL=your_email@example.com
   CRUNCHYROLL_PASSWORD=your_password
   ANILIST_CLIENT_ID=your_client_id
   ANILIST_CLIENT_SECRET=your_client_secret
   FLARESOLVERR_URL=http://192.168.1.5:8191  # Optional
   ```

### AniList OAuth Setup

1. Go to https://anilist.co/settings/developer
2. Create a new client application
3. Set redirect URI to: `https://anilist.co/api/v2/oauth/pin`
4. Copy the Client ID and Client Secret to your `.env` file

### FlareSolverr Setup (Optional but Recommended)

FlareSolverr helps bypass Cloudflare protection that Crunchyroll may use.

1. **Using Docker:**
   ```bash
   docker run -d \
     --name=flaresolverr \
     -p 8191:8191 \
     -e LOG_LEVEL=info \
     --restart unless-stopped \
     ghcr.io/flaresolverr/flaresolverr:latest
   ```

2. **Update your `.env` file:**
   ```env
   FLARESOLVERR_URL=http://localhost:8191
   ```

## Usage

### Command Line Options

```bash
# Basic usage (runs headless by default)
python main.py

# Run with visible browser
python main.py --no-headless

# Development mode (saves debug files)
python main.py --dev

# Development mode with visible browser
python main.py --dev --no-headless

# Enable debug logging
python main.py --debug

# Check cache status
python main.py --cache-status

# Clear all cache
python main.py --clear-cache

# Show help
python main.py --help
``` 