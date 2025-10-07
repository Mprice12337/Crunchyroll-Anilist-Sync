# Enhanced Dockerfile with better Chrome support and anti-detection
FROM python:3.9-slim

# Set environment variables early
ENV DEBIAN_FRONTEND=noninteractive \
    DISPLAY=:99 \
    CHROME_BIN=/usr/bin/google-chrome \
    CHROME_PATH=/usr/bin/google-chrome \
    LANGUAGE=en_US.UTF-8 \
    LANG=en_US.UTF-8 \
    LC_ALL=en_US.UTF-8 \
    TZ=America/New_York

# Install system dependencies in optimal order
RUN apt-get update && apt-get install -y \
    # Required for Chrome installation
    wget \
    gnupg \
    ca-certificates \
    apt-transport-https \
    # Locale support (important for anti-detection)
    locales \
    # Additional dependencies
    unzip \
    curl \
    cron \
    # Timezone data
    tzdata \
    && echo "en_US.UTF-8 UTF-8" > /etc/locale.gen \
    && locale-gen en_US.UTF-8 \
    && update-locale LANG=en_US.UTF-8 \
    # Add Google Chrome repository
    && wget -q -O - https://dl-ssl.google.com/linux/linux_signing_key.pub | gpg --dearmor -o /usr/share/keyrings/google-chrome.gpg \
    && echo "deb [arch=amd64 signed-by=/usr/share/keyrings/google-chrome.gpg] http://dl.google.com/linux/chrome/deb/ stable main" > /etc/apt/sources.list.d/google-chrome.list \
    && apt-get update \
    # Install Chrome and all required libraries
    && apt-get install -y \
    google-chrome-stable \
    # Font packages (CRITICAL for rendering and anti-detection)
    fonts-liberation \
    fonts-noto-color-emoji \
    fonts-noto-cjk \
    # Graphics libraries (for WebGL/Canvas)
    libnss3 \
    libxss1 \
    libappindicator3-1 \
    libgbm1 \
    libasound2 \
    libatk-bridge2.0-0 \
    libatk1.0-0 \
    libcups2 \
    libdbus-1-3 \
    libdrm2 \
    libglib2.0-0 \
    libgtk-3-0 \
    libnspr4 \
    libpango-1.0-0 \
    libx11-6 \
    libx11-xcb1 \
    libxcb1 \
    libxcomposite1 \
    libxcursor1 \
    libxdamage1 \
    libxext6 \
    libxfixes3 \
    libxi6 \
    libxrandr2 \
    libxrender1 \
    libxtst6 \
    # Cleanup
    && rm -rf /var/lib/apt/lists/* \
    # Verify Chrome installation
    && google-chrome --version

# Set timezone
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

# Set working directory
WORKDIR /app

# Copy requirements first for better caching
COPY requirements.txt ./

# Install Python dependencies
# IMPORTANT: Pin undetected-chromedriver to a stable version
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY main.py ./
COPY src/ ./src/
COPY entrypoint.sh ./

# Make entrypoint executable
RUN chmod +x /app/entrypoint.sh

# Default cron schedule: daily at 2 AM
ENV CRON_SCHEDULE="0 2 * * *"

# Default to headless mode
ENV HEADLESS=true

# Create necessary directories with proper permissions
RUN mkdir -p /app/_cache /app/logs \
    && chmod 755 /app/_cache /app/logs

# Create a fake X11 display for better anti-detection (optional but helpful)
# This makes headless mode appear more like a real display
ENV DISPLAY=:99

# CRITICAL: Set Chrome to use /dev/shm for better performance and stability
RUN mkdir -p /dev/shm && chmod 1777 /dev/shm

# Add a healthcheck to ensure container is working
HEALTHCHECK --interval=1h --timeout=30s --start-period=10s --retries=3 \
    CMD test -f /app/_cache/.first_run_complete || exit 1

# Use the entrypoint script
ENTRYPOINT ["/app/entrypoint.sh"]