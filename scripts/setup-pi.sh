#!/bin/bash
# Raspberry Pi initial setup script for Album Art Display
set -e

echo "=== Album Art Display - Pi Setup ==="
echo

# Update system
echo "Updating system packages..."
sudo apt-get update
sudo apt-get upgrade -y

# Install required system packages
echo "Installing system dependencies..."
sudo apt-get install -y \
    git \
    curl \
    chromium-browser \
    fonts-noto-color-emoji

# Install uv (Python package manager)
if ! command -v uv &> /dev/null; then
    echo "Installing uv..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    # Add to current shell
    export PATH="$HOME/.local/bin:$PATH"
else
    echo "uv already installed"
fi

# Ensure uv is in PATH for this script
export PATH="$HOME/.local/bin:$PATH"

# Setup project directory
PROJECT_DIR="$HOME/album_art"
if [ -d "$PROJECT_DIR" ]; then
    echo "Project directory exists at $PROJECT_DIR"
    echo "Run 'git pull' to update if needed"
else
    echo
    echo "Project directory not found."
    echo "Clone your repository to $PROJECT_DIR:"
    echo "  git clone <your-repo-url> $PROJECT_DIR"
fi

# Install Python dependencies if project exists
if [ -d "$PROJECT_DIR" ] && [ -f "$PROJECT_DIR/pyproject.toml" ]; then
    cd "$PROJECT_DIR"
    echo "Installing Python dependencies..."
    uv sync
fi

# Disable screen blanking
echo "Disabling screen blanking..."
sudo raspi-config nonint do_blanking 1 2>/dev/null || true

echo
echo "=== Setup complete! ==="
echo
echo "Next steps:"
echo "1. Clone your repo to $PROJECT_DIR (if not done)"
echo "2. Copy your .env file: cp .env.example .env && nano .env"
echo "3. Copy .spotify_cache from dev machine (if using Spotify)"
echo "4. Test: cd $PROJECT_DIR && uv run album-art"
echo "5. Install kiosk mode: ./scripts/install-kiosk.sh"
