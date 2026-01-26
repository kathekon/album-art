#!/bin/bash
# Install kiosk mode for Album Art Display
set -e

PROJECT_DIR="$HOME/album_art"
SERVICE_FILE="$PROJECT_DIR/scripts/album-art.service"

echo "=== Installing Kiosk Mode ==="

# Check if project exists
if [ ! -d "$PROJECT_DIR" ]; then
    echo "Error: Project not found at $PROJECT_DIR"
    echo "Please run setup-pi.sh first"
    exit 1
fi

# Get current user
CURRENT_USER=$(whoami)

# Create service file with correct user
echo "Creating systemd service..."
sudo tee /etc/systemd/system/album-art.service > /dev/null << EOF
[Unit]
Description=Album Art Display Backend
After=network.target

[Service]
Type=simple
User=$CURRENT_USER
WorkingDirectory=$PROJECT_DIR
Environment="PATH=$HOME/.local/bin:/usr/bin"
ExecStart=$HOME/.local/bin/uv run album-art
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

# Enable and start the service
sudo systemctl daemon-reload
sudo systemctl enable album-art.service
sudo systemctl start album-art.service

# Detect display server and configure autostart
KIOSK_URL="http://localhost:8080"
CHROMIUM_FLAGS="--kiosk --noerrdialogs --disable-infobars --no-first-run --start-maximized --disable-session-crashed-bubble --disable-features=TranslateUI --check-for-update-interval=31536000"

if [ -f "$HOME/.config/wayfire.ini" ]; then
    # Wayland/Wayfire (newer Pi OS)
    echo "Configuring Wayfire autostart..."
    if ! grep -q "album-art-browser" "$HOME/.config/wayfire.ini" 2>/dev/null; then
        cat >> "$HOME/.config/wayfire.ini" << EOF

# Album Art Display Browser
[autostart]
album-art-browser = chromium-browser $KIOSK_URL $CHROMIUM_FLAGS --ozone-platform=wayland
screensaver = false
dpms = false
EOF
    fi
elif [ -d "$HOME/.config/labwc" ]; then
    # labwc
    echo "Configuring labwc autostart..."
    echo "chromium-browser $KIOSK_URL $CHROMIUM_FLAGS &" >> "$HOME/.config/labwc/autostart"
else
    # X11/LXDE (older Pi OS)
    echo "Configuring LXDE autostart..."
    mkdir -p "$HOME/.config/lxsession/LXDE-pi"
    cat > "$HOME/.config/lxsession/LXDE-pi/autostart" << EOF
@lxpanel --profile LXDE-pi
@pcmanfm --desktop --profile LXDE-pi
@xset s off
@xset -dpms
@xset s noblank
@chromium-browser $KIOSK_URL $CHROMIUM_FLAGS
EOF
fi

# Enable desktop autologin
echo "Enabling desktop autologin..."
sudo raspi-config nonint do_boot_behaviour B4 2>/dev/null || true

echo
echo "=== Kiosk installation complete! ==="
echo
echo "The system will start the album art display on boot."
echo "Reboot to test: sudo reboot"
echo
echo "Useful commands:"
echo "  Check backend status: sudo systemctl status album-art"
echo "  View logs: journalctl -u album-art -f"
echo "  Restart backend: sudo systemctl restart album-art"
