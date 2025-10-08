#!/bin/bash
set -e

# Configuration
FIRST_RUN_FLAG="/app/_cache/.first_run_complete"
LOG_FILE="/app/logs/cron.log"
SYNC_SCRIPT="/app/run_sync.sh"

# Color codes for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Function to log with timestamp
log() {
    echo -e "${BLUE}[$(date '+%Y-%m-%d %H:%M:%S')]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[$(date '+%Y-%m-%d %H:%M:%S')]${NC} ✅ $1"
}

log_warning() {
    echo -e "${YELLOW}[$(date '+%Y-%m-%d %H:%M:%S')]${NC} ⚠️  $1"
}

log_error() {
    echo -e "${RED}[$(date '+%Y-%m-%d %H:%M:%S')]${NC} ❌ $1"
}

# Create the sync script that will be called by cron
cat > "$SYNC_SCRIPT" << 'EOF'
#!/bin/bash

# Redirect all output to log file
exec >> /app/logs/cron.log 2>&1

echo "========================================"
echo "Starting sync at $(date)"
echo "========================================"

cd /app

# Check if this is the first run
if [ ! -f /app/_cache/.first_run_complete ]; then
    echo "🎯 First run detected - using --max-pages 1 for quick initial sync"
    python main.py --max-pages 1

    # Mark first run as complete
    touch /app/_cache/.first_run_complete
    echo "✅ First run completed successfully"
else
    echo "📚 Subsequent run - performing full sync"
    python main.py
fi

SYNC_EXIT_CODE=$?

if [ $SYNC_EXIT_CODE -eq 0 ]; then
    echo "✅ Sync completed successfully at $(date)"
else
    echo "❌ Sync failed with exit code $SYNC_EXIT_CODE at $(date)"
fi

echo "========================================"
echo ""
EOF

chmod +x "$SYNC_SCRIPT"

# Display welcome banner
echo ""
echo "╔════════════════════════════════════════════════════════════╗"
echo "║         Crunchyroll-AniList Sync Container v0.2.0          ║"
echo "╚════════════════════════════════════════════════════════════╝"
echo ""

# Validate environment variables
log "Validating environment variables..."

required_vars=("CRUNCHYROLL_EMAIL" "CRUNCHYROLL_PASSWORD" "ANILIST_AUTH_CODE")
missing_vars=()

for var in "${required_vars[@]}"; do
    if [ -z "${!var}" ]; then
        missing_vars+=("$var")
    fi
done

if [ ${#missing_vars[@]} -ne 0 ]; then
    log_error "Missing required environment variables:"
    for var in "${missing_vars[@]}"; do
        echo "  - $var"
    done

    # Special message for ANILIST_AUTH_CODE
    if [[ " ${missing_vars[@]} " =~ " ANILIST_AUTH_CODE " ]]; then
        echo ""
        echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        echo "To get your AniList auth code:"
        echo "1. Visit: https://anilist.co/api/v2/oauth/authorize?client_id=21538&response_type=code"
        echo "2. Authorize the application"
        echo "3. Copy the code from the PIN page"
        echo "4. Set ANILIST_AUTH_CODE in your environment or .env file"
        echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        echo ""
    fi

    exit 1
fi

log_success "Environment variables validated"

# Display configuration
echo ""
log "Configuration:"
echo "  • Cron schedule: ${CRON_SCHEDULE:-0 2 * * *}"
echo "  • Headless mode: ${HEADLESS:-true}"
if [ -n "$FLARESOLVERR_URL" ]; then
    echo "  • FlareSolverr: ${FLARESOLVERR_URL}"
else
    echo "  • FlareSolverr: Not configured (optional)"
fi
echo "  • Max pages (first run): 1"
echo "  • Max pages (subsequent): 10 (default)"
echo ""

# Run initial sync immediately
log "Starting initial sync..."
echo ""

if [ ! -f "$FIRST_RUN_FLAG" ]; then
    log_warning "First run detected - using --max-pages 1 for quick initial sync"
    if python main.py --max-pages 1; then
        touch "$FIRST_RUN_FLAG"
        log_success "Initial sync completed successfully"
    else
        log_error "Initial sync failed"
        exit 1
    fi
else
    log "Subsequent run - performing full sync"
    if python main.py; then
        log_success "Initial sync completed successfully"
    else
        log_error "Initial sync failed"
        exit 1
    fi
fi

echo ""
log "Setting up cron job..."

# Create cron schedule
CRON_JOB="${CRON_SCHEDULE} ${SYNC_SCRIPT} >> ${LOG_FILE} 2>&1"

# Write cron job to crontab
echo "$CRON_JOB" | crontab -

# Verify cron job was added
log "Cron job configured:"
crontab -l | sed 's/^/  /'

log_success "Cron service configured"

# Start cron in the foreground
log "Starting cron daemon..."
log_success "Container is running! Sync will run according to schedule: ${CRON_SCHEDULE}"
echo ""
log "Logs are being written to: ${LOG_FILE}"
log "View logs with: docker logs -f <container_name>"
echo ""

# Start cron and tail the log file
cron

# Create initial log file if it doesn't exist
touch "$LOG_FILE"

# Display next scheduled run
echo "╔════════════════════════════════════════════════════════════╗"
echo "║                    Service is Running                      ║"
echo "╚════════════════════════════════════════════════════════════╝"
echo ""

# Tail logs to keep container running and show output
tail -f "$LOG_FILE"