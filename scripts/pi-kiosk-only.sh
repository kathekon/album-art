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

    # Append screen blanking disable and browser (using cleanup launcher)
    cat >> "$AUTOSTART_FILE" << EOF
@xset s off
@xset -dpms
@xset s noblank
@$CHROMIUM_CLEANUP_SCRIPT $FULL_URL $CHROMIUM_FLAGS
EOF
fi

# Disable screen blanking and screensaver
echo "Disabling screen blanking and screensaver..."
if command -v xset &> /dev/null; then
    export DISPLAY=:0
    xset s off 2>/dev/null || true
    xset -dpms 2>/dev/null || true
    xset s noblank 2>/dev/null || true
fi

# Disable xscreensaver if running
if command -v xscreensaver-command &> /dev/null; then
    xscreensaver-command -exit 2>/dev/null || true
    # Prevent xscreensaver from starting on boot
    if [ -f "$HOME/.config/lxsession/LXDE-pi/autostart" ]; then
        sed -i '/xscreensaver/d' "$HOME/.config/lxsession/LXDE-pi/autostart" 2>/dev/null || true
    fi
fi

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
