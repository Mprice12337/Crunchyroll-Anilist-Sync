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
# CRITICAL FIX: Changed from 'EOF' to EOF to allow variable expansion
# This ensures environment variables are embedded in the script
cat > "$SYNC_SCRIPT" << EOF
#!/bin/bash

# CRITICAL: Set PATH for cron environment
# Cron runs with minimal PATH, so we need to explicitly set it
PATH=/usr/local/bin:/usr/local/sbin:/usr/bin:/usr/sbin:/bin:/sbin
export PATH

# CRITICAL: Set timezone for consistent logging
export TZ="${TZ:-America/New_York}"

# CRITICAL FIX: Export all required environment variables
# Docker environment variables are NOT automatically available to cron
export CRUNCHYROLL_EMAIL="${CRUNCHYROLL_EMAIL}"
export CRUNCHYROLL_PASSWORD="${CRUNCHYROLL_PASSWORD}"
export ANILIST_AUTH_CODE="${ANILIST_AUTH_CODE}"
export FLARESOLVERR_URL="${FLARESOLVERR_URL}"
export HEADLESS="${HEADLESS}"
export DEBUG="${DEBUG}"
export DRY_RUN="${DRY_RUN}"
export MAX_PAGES="${MAX_PAGES}"

# Redirect all output to log file
exec >> /app/logs/cron.log 2>&1

echo "=========================================="
echo "Starting sync at \$(date)"
echo "=========================================="

# Debug: Verify environment variables are set
echo "Environment check:"
echo "  CRUNCHYROLL_EMAIL: \${CRUNCHYROLL_EMAIL:+SET}"
echo "  CRUNCHYROLL_PASSWORD: \${CRUNCHYROLL_PASSWORD:+SET}"
echo "  ANILIST_AUTH_CODE: \${ANILIST_AUTH_CODE:+SET}"
echo "  FLARESOLVERR_URL: \${FLARESOLVERR_URL:-NOT SET}"
echo ""

cd /app

# Verify Python is available
if ! command -v python3 &> /dev/null; then
    echo "❌ ERROR: python3 command not found in PATH: \$PATH"
    exit 1
fi

# Build command-line flags from environment variables
SYNC_FLAGS=""
if [ "\${DEBUG}" = "true" ]; then
    SYNC_FLAGS="\${SYNC_FLAGS} --debug"
fi
if [ "\${DRY_RUN}" = "true" ]; then
    SYNC_FLAGS="\${SYNC_FLAGS} --dry-run"
fi

# Check if this is the first run
if [ ! -f /app/_cache/.first_run_complete ]; then
    echo "🎯 First run detected - using --max-pages 1 for quick initial sync"
    python3 main.py --max-pages 1 \${SYNC_FLAGS}

    # Mark first run as complete
    touch /app/_cache/.first_run_complete
    echo "✅ First run completed successfully"
else
    echo "📚 Subsequent run - performing full sync"
    # Use MAX_PAGES if set, otherwise use default
    if [ -n "\${MAX_PAGES}" ]; then
        python3 main.py --max-pages \${MAX_PAGES} \${SYNC_FLAGS}
    else
        python3 main.py \${SYNC_FLAGS}
    fi
fi

SYNC_EXIT_CODE=\$?

if [ \$SYNC_EXIT_CODE -eq 0 ]; then
    echo "✅ Sync completed successfully at \$(date)"
else
    echo "❌ Sync failed with exit code \$SYNC_EXIT_CODE at \$(date)"
fi

echo "=========================================="
echo ""
EOF

chmod +x "$SYNC_SCRIPT"

# Display welcome banner
echo ""
echo "╔════════════════════════════════════════════════════════════╗"
echo "║         Crunchyroll-AniList Sync Container v0.2.1          ║"
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
echo "  • Timezone: ${TZ:-America/New_York}"
echo "  • Cron schedule: ${CRON_SCHEDULE:-0 2 * * *}"
echo "  • Headless mode: ${HEADLESS:-true}"
echo "  • Debug mode: ${DEBUG:-false}"
echo "  • Dry-run mode: ${DRY_RUN:-false}"
if [ -n "$FLARESOLVERR_URL" ]; then
    echo "  • FlareSolverr: ${FLARESOLVERR_URL}"
else
    echo "  • FlareSolverr: Not configured (optional)"
fi
echo "  • Max pages (first run): 1"
if [ -n "$MAX_PAGES" ]; then
    echo "  • Max pages (subsequent): ${MAX_PAGES}"
else
    echo "  • Max pages (subsequent): 10 (default)"
fi
echo ""

# Run initial sync immediately (with proper PATH)
log "Starting initial sync..."
echo ""

# Build command-line flags from environment variables
SYNC_FLAGS=""
if [ "${DEBUG}" = "true" ]; then
    SYNC_FLAGS="${SYNC_FLAGS} --debug"
    log "Debug mode enabled"
fi
if [ "${DRY_RUN}" = "true" ]; then
    SYNC_FLAGS="${SYNC_FLAGS} --dry-run"
    log "Dry-run mode enabled (no changes will be made)"
fi

if [ ! -f "$FIRST_RUN_FLAG" ]; then
    log_warning "First run detected - using --max-pages 1 for quick initial sync"
    if python3 main.py --max-pages 1 ${SYNC_FLAGS}; then
        touch "$FIRST_RUN_FLAG"
        log_success "Initial sync completed successfully"
    else
        log_error "Initial sync failed"
        exit 1
    fi
else
    log "Subsequent run - performing full sync"
    # Use MAX_PAGES if set, otherwise use default
    if [ -n "${MAX_PAGES}" ]; then
        log "Using custom max-pages: ${MAX_PAGES}"
        if python3 main.py --max-pages ${MAX_PAGES} ${SYNC_FLAGS}; then
            log_success "Initial sync completed successfully"
        else
            log_error "Initial sync failed"
            exit 1
        fi
    else
        if python3 main.py ${SYNC_FLAGS}; then
            log_success "Initial sync completed successfully"
        else
            log_error "Initial sync failed"
            exit 1
        fi
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

# Create initial log file if it doesn't exist
touch "$LOG_FILE"

# Start cron in FOREGROUND mode (this keeps the container running)
log "Starting cron daemon in foreground mode..."
log_success "Container is running! Sync will run according to schedule: ${CRON_SCHEDULE}"
echo ""
log "Logs are being written to: ${LOG_FILE}"
log "View cron logs with: docker exec <container_name> tail -f /app/logs/cron.log"
echo ""

# Display next scheduled run
echo "╔════════════════════════════════════════════════════════════╗"
echo "║                    Service is Running                      ║"
echo "╚════════════════════════════════════════════════════════════╝"
echo ""

# CRITICAL FIX: Use 'cron -f' to run in foreground
# This keeps the container alive without relying on tail
exec cron -f