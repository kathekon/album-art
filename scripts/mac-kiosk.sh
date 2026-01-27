#!/bin/bash
# Launch album art display in Chrome's app mode (no browser chrome)
# Starts the Docker container if not running
# Usage: ./mac-kiosk.sh [url]

set -e

URL="${1:-http://localhost:5174}"
PORT="${URL##*:}"  # Extract port from URL

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$SCRIPT_DIR/.."

# Check if server is already running
if ! curl -s "http://localhost:$PORT" > /dev/null 2>&1; then
    echo "Starting album-art container..."
    cd "$PROJECT_DIR" || exit 1

    # Start container (will build if needed)
    docker compose up -d

    # Wait for server to be ready (max 15 seconds)
    echo -n "Waiting for server"
    for i in {1..30}; do
        if curl -s "http://localhost:$PORT" > /dev/null 2>&1; then
            echo " ready!"
            break
        fi
        echo -n "."
        sleep 0.5
    done

    # Check if server started
    if ! curl -s "http://localhost:$PORT" > /dev/null 2>&1; then
        echo " failed to start. Check: docker logs album_art-album-art-1"
        exit 1
    fi
else
    echo "Server already running on port $PORT"
fi

# Find Chrome binary (must call directly - 'open -a' ignores --args if Chrome is running)
if [ -x "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" ]; then
    CHROME="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
elif [ -x "$HOME/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" ]; then
    CHROME="$HOME/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
else
    echo "Error: Google Chrome not found"
    exit 1
fi

echo "Launching $URL in app mode..."
"$CHROME" --app="$URL" &
