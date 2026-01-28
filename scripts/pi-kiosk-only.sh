#!/bin/bash
# Configure Pi as kiosk-only display (server runs elsewhere)
# Usage: ./pi-kiosk-only.sh <server-url> [--mode=off|on|detailed]
# Example: ./pi-kiosk-only.sh http://192.168.1.100:5174 --mode=off

set -e

SERVER_URL=""
DISPLAY_MODE="off"  # Default to no metadata for kiosk mode

# Parse arguments
for arg in "$@"; do
    case $arg in
        --mode=*)
            DISPLAY_MODE="${arg#*=}"
            ;;
        http*)
            SERVER_URL="$arg"
            ;;
    esac
done

if [ -z "$SERVER_URL" ]; then
    echo "Usage: $0 <server-url> [--mode=off|on|detailed]"
    echo "Example: $0 http://192.168.1.100:5174"
    echo "Example: $0 http://192.168.1.100:5174 --mode=off"
    echo ""
    echo "The server URL should be the IP/hostname of the machine running"
    echo "the album-art container (e.g., your Mac)."
    echo ""
    echo "Display modes:"
    echo "  --mode=off      No metadata (just album art) - default for kiosk"
    echo "  --mode=on       Title, artist, album visible"
    echo "  --mode=detailed Full metadata with dimensions, duration, etc."
    exit 1
fi

# Append mode parameter to URL
FULL_URL="${SERVER_URL}?mode=${DISPLAY_MODE}"

echo "=== Configuring Pi Kiosk Mode ==="
echo "Server: $SERVER_URL"
echo "Display mode: $DISPLAY_MODE"
echo "Full URL: $FULL_URL"
echo ""

# Chromium kiosk flags
CHROMIUM_FLAGS="--kiosk --noerrdialogs --disable-infobars --no-first-run"
CHROMIUM_FLAGS="$CHROMIUM_FLAGS --start-maximized --disable-session-crashed-bubble"
CHROMIUM_FLAGS="$CHROMIUM_FLAGS --disable-features=TranslateUI,InfiniteSessionRestore"
CHROMIUM_FLAGS="$CHROMIUM_FLAGS --disable-restore-session-state"
CHROMIUM_FLAGS="$CHROMIUM_FLAGS --check-for-update-interval=31536000"

# Create a helper script to clean Chromium state before launch
# This prevents "Chromium didn't shut down correctly" popups
CHROMIUM_CLEANUP_SCRIPT="$HOME/.local/bin/chromium-kiosk-launch.sh"
mkdir -p "$(dirname "$CHROMIUM_CLEANUP_SCRIPT")"
cat > "$CHROMIUM_CLEANUP_SCRIPT" << 'CLEANUP_EOF'
#!/bin/bash
# Clean Chromium crash state before launching in kiosk mode
PREFS="$HOME/.config/chromium/Default/Preferences"
if [ -f "$PREFS" ]; then
    # Mark as cleanly exited to prevent restore prompts
    sed -i 's/"exit_type":"Crashed"/"exit_type":"Normal"/g' "$PREFS" 2>/dev/null
    sed -i 's/"exited_cleanly":false/"exited_cleanly":true/g' "$PREFS" 2>/dev/null
fi
# Launch Chromium with all arguments passed to this script
exec chromium-browser "$@"
CLEANUP_EOF
chmod +x "$CHROMIUM_CLEANUP_SCRIPT"
echo "Created Chromium cleanup launcher at $CHROMIUM_CLEANUP_SCRIPT"

# Detect display server and configure autostart
if [ -f "$HOME/.config/wayfire.ini" ]; then
    # Wayland/Wayfire (newer Pi OS)
    echo "Configuring Wayfire autostart..."
    # Remove old album-art config if exists
    sed -i '/album-art-browser/d' "$HOME/.config/wayfire.ini" 2>/dev/null || true
    cat >> "$HOME/.config/wayfire.ini" << EOF

# Album Art Display Browser (kiosk mode)
[autostart]
album-art-browser = chromium-browser $FULL_URL $CHROMIUM_FLAGS --ozone-platform=wayland
screensaver = false
dpms = false
EOF

elif [ -d "$HOME/.config/labwc" ]; then
    # labwc
    echo "Configuring labwc autostart..."
    echo "chromium-browser $FULL_URL $CHROMIUM_FLAGS &" >> "$HOME/.config/labwc/autostart"

else
    # X11/LXDE (older Pi OS like Jessie)
    echo "Configuring LXDE/X11 autostart..."
    AUTOSTART_FILE="$HOME/.config/lxsession/LXDE-pi/autostart"
    mkdir -p "$(dirname "$AUTOSTART_FILE")"

    # Backup existing file to preserve any custom entries
    if [ -f "$AUTOSTART_FILE" ]; then
        BACKUP_FILE="${AUTOSTART_FILE}.bak.$(date +%Y%m%d_%H%M%S)"
        cp "$AUTOSTART_FILE" "$BACKUP_FILE"
        echo "Backed up existing autostart to $BACKUP_FILE"
        # Remove any existing album-art/kiosk browser entries to avoid duplicates
        sed -i '/chromium.*5174\|album-art/d' "$AUTOSTART_FILE"
        # Remove duplicate xset entries (we'll add them fresh)
        sed -i '/^@xset/d' "$AUTOSTART_FILE"
    else
        # Create new file with standard LXDE entries
        cat > "$AUTOSTART_FILE" << EOF
@lxpanel --profile LXDE-pi
@pcmanfm --desktop --profile LXDE-pi
EOF
    fi

    # Append DPMS settings and browser (using cleanup launcher)
    # Note: We enable DPMS but let the monitor script control sleep based on playback
    cat >> "$AUTOSTART_FILE" << EOF
@xset s 300 300
@xset +dpms
@xset dpms 600 600 600
@$CHROMIUM_CLEANUP_SCRIPT $FULL_URL $CHROMIUM_FLAGS
EOF
fi

# Enable DPMS with reasonable defaults (will be controlled by monitor script)
echo "Enabling DPMS power management..."
if command -v xset &> /dev/null; then
    export DISPLAY=:0
    xset s 300 300 2>/dev/null || true
    xset +dpms 2>/dev/null || true
    xset dpms 600 600 600 2>/dev/null || true
fi

# Create playback-aware DPMS monitor script
echo "Installing DPMS monitor script..."
DPMS_SCRIPT="$HOME/album-art-dpms.sh"
cat > "$DPMS_SCRIPT" << 'DPMS_EOF'
#!/bin/bash
# Monitor album art playback state and control DPMS accordingly
# When music plays: keep screen awake
# When idle for X minutes: sleep the screen

SERVER_URL="__SERVER_URL__"
IDLE_TIMEOUT_MINUTES=5
CHECK_INTERVAL=60  # seconds

idle_count=0

while true; do
    # Query playback state
    state=$(curl -s --connect-timeout 5 "$SERVER_URL/api/state" 2>/dev/null)

    if [ -z "$state" ]; then
        # Server unreachable, increment idle
        ((idle_count++))
    else
        is_playing=$(echo "$state" | grep -o '"is_playing":\s*true')

        if [ -n "$is_playing" ]; then
            # Music playing - reset idle counter, wake screen
            idle_count=0
            DISPLAY=:0 xset dpms force on 2>/dev/null
        else
            # Nothing playing
            ((idle_count++))
        fi
    fi

    # Check if we have been idle long enough
    idle_minutes=$((idle_count * CHECK_INTERVAL / 60))
    if [ $idle_minutes -ge $IDLE_TIMEOUT_MINUTES ]; then
        DISPLAY=:0 xset dpms force off 2>/dev/null
    fi

    sleep $CHECK_INTERVAL
done
DPMS_EOF

# Replace placeholder with actual server URL
sed -i "s|__SERVER_URL__|$SERVER_URL|g" "$DPMS_SCRIPT"
chmod +x "$DPMS_SCRIPT"
echo "Created DPMS monitor at $DPMS_SCRIPT"

# Create and enable systemd service for DPMS monitor
echo "Installing DPMS monitor systemd service..."
sudo tee /etc/systemd/system/album-art-dpms.service > /dev/null << SYSTEMD_EOF
[Unit]
Description=Album Art DPMS Monitor
After=network.target

[Service]
Type=simple
User=$USER
ExecStart=$DPMS_SCRIPT
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
SYSTEMD_EOF

sudo systemctl daemon-reload
sudo systemctl enable album-art-dpms.service
sudo systemctl start album-art-dpms.service
echo "DPMS monitor service enabled and started"

# Enable desktop autologin (requires sudo)
echo "Enabling desktop autologin..."
sudo raspi-config nonint do_boot_behaviour B4 2>/dev/null || echo "Note: Run 'sudo raspi-config' manually to enable autologin"

echo ""
echo "=== Kiosk configuration complete! ==="
echo ""
echo "The Pi will display $FULL_URL on boot."
echo "Reboot to test: sudo reboot"
echo ""
echo "To test now without reboot:"
echo "  chromium-browser '$FULL_URL' $CHROMIUM_FLAGS &"
