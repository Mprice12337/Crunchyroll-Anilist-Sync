# Production Dockerfile with full Chrome support
FROM python:3.9-slim

# Set environment variables early
ENV DEBIAN_FRONTEND=noninteractive \
    DISPLAY=:99 \
    CHROME_BIN=/usr/bin/google-chrome \
    CHROME_PATH=/usr/bin/google-chrome

# Install system dependencies in correct order
RUN apt-get update && apt-get install -y \
    wget \
    gnupg \
    ca-certificates \
    apt-transport-https \
    && wget -q -O - https://dl-ssl.google.com/linux/linux_signing_key.pub | gpg --dearmor -o /usr/share/keyrings/google-chrome.gpg \
    && echo "deb [arch=amd64 signed-by=/usr/share/keyrings/google-chrome.gpg] http://dl.google.com/linux/chrome/deb/ stable main" > /etc/apt/sources.list.d/google-chrome.list \
    && apt-get update \
    && apt-get install -y \
    google-chrome-stable \
    unzip \
    curl \
    cron \
    fonts-liberation \
    libnss3 \
    libxss1 \
    libappindicator3-1 \
    libgbm1 \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements first for better caching
COPY requirements.txt ./

# Install Python dependencies
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
RUN mkdir -p /app/_cache /app/logs && \
    chmod 755 /app/_cache /app/logs

# Use the entrypoint script
ENTRYPOINT ["/app/entrypoint.sh"]