# Album Art Display

## Project Overview
A Python application that monitors Sonos (and eventually Spotify) playback and displays high-resolution album art. Designed to run on a Raspberry Pi in kiosk mode as a dedicated album art display.

## Current Status (Jan 2026)
- **Sonos**: Working - polls via SoCo library on local network
- **Spotify**: Disabled - Spotify paused new developer app creation (security measures after Anna's Archive scrape, Dec 2025). Code is ready, just needs credentials when API reopens.
- **Display**: Browser-based with SSE real-time updates

## Architecture
```
FastAPI Server (Python/uv) --SSE--> Browser (full-screen album art)
       |
   Poller (3s interval)
       |
   +---+---+
   |       |
 Sonos   Spotify
 (SoCo)  (Spotipy - disabled)
```

## Critical: Avoid Destructive File Operations

**NEVER overwrite configuration files without first:**
1. Checking if the file exists and has content
2. Creating a backup (e.g., `file.bak` or `file.YYYYMMDD`)
3. Understanding what existing content will be lost

**Bad patterns to avoid:**
- `cat > file` (overwrites)
- `echo "content" > file` (overwrites)
- Python `open(file, 'w')` without reading first

**Safe patterns:**
- `cat >> file` (append)
- Read file first, merge content, then write
- Create `.bak` backup before any modification

This applies especially to:
- Autostart files (`~/.config/lxsession/*/autostart`)
- Shell profiles (`.bashrc`, `.zshrc`)
- System configs (`/etc/*`)

## Key Files
- `config.toml` - All settings (port, polling interval, Sonos IP, etc.)
- `.env` - Secrets only (Spotify credentials when needed)
- `src/album_art/main.py` - FastAPI app with SSE endpoint
- `src/album_art/sources/sonos.py` - Sonos integration
- `src/album_art/sources/spotify.py` - Spotify integration (ready but disabled)
- `src/album_art/static/` - Frontend (HTML/CSS/JS)

## Running Locally
```bash
uv run album-art
# Open http://localhost:5174
```

## UI Features
- Album art fills viewport (scales up small images)
- Subtle metadata overlay in lower right corner
- Click anywhere to cycle display modes:
  1. **on** - title, artist, album, source badge
  2. **detailed** - adds image dimensions, duration, progress %
  3. **off** - no metadata (just album art)
- Mode preference saved to localStorage

## Configuration
Port and other settings in `config.toml`:
```toml
[server]
port = 5174  # Unusual port to avoid conflicts

[sonos]
ip = "10.0.1.227"  # Direct IP (auto-discovery was timing out)
```

## Docker Deployment (Recommended)

Run the server in a container on your Mac/server, Pi just displays in browser:

```bash
# Build and run
docker compose up -d

# Or manually
docker build -t album-art .
docker run -d -p 5174:5174 -v ./config.toml:/app/config.toml:ro album-art
```

Then configure Pi to display it (see Pi Kiosk-Only below).

## Pi Deployment Options

### Option 1: Kiosk-Only (Recommended for old Pis)
Server runs elsewhere (Mac/container), Pi just displays in Chromium:
```bash
# On the Pi:
./scripts/pi-kiosk-only.sh http://<mac-ip>:5174
sudo reboot
```

### Option 2: Full Pi Install (requires Python 3.11+)
Scripts in `scripts/`:
- `setup-pi.sh` - Initial Pi setup (installs uv, deps)
- `install-kiosk.sh` - Configures Chromium kiosk + systemd service
- `spotify-auth.py` - One-time Spotify OAuth (when API reopens)

## Recent Enhancements (Jan 2026)
- **Enhanced Display Modes**: 5-mode cycle: on → detailed → comparison → debug → off
  - **Comparison mode**: Shows original Sonos thumbnail when using iTunes art
  - **Debug mode**: Queue thumbnail stack with iTunes/Sonos badges and match reasons
  - **Detailed mode**: Shows art source reason (e.g., "itunes (matched)" or "sonos (no album match)")
- **iTunes Album Art**: Added iTunes Search API lookup for high-resolution artwork (up to 3000×3000). Configurable in `[artwork]` section of config.toml.
- **iTunes Album Matching Fix**: Now verifies BOTH artist AND album name match (previously only checked artist, causing wrong album art like "The Wall" for "Dark Side of the Moon")
- **Artwork Prefetching**: Browser prefetches upcoming queue artwork for seamless transitions
- **Art Source Display**: Detailed mode now shows artwork source (sonos/itunes) with reason
- **Configurable Default Mode**: Display mode configurable via:
  - CLI: `uv run album-art --default-mode=off`
  - URL param: `http://server:5174/?mode=off` (highest priority, for kiosk)
  - config.toml: `[display] default_mode = "on"`
  - Pi kiosk defaults to `mode=off` (no metadata)
- **ES5 JavaScript Compatibility**: Frontend JS uses ES5 syntax for old Chromium on Raspberry Pi (no optional chaining `?.`)
- **Bug Fixes**:
  - Fixed empty artist matching in iTunes (would incorrectly match any search)
  - Added 60-second rate limit backoff for iTunes API (prevents hammering on 429)
  - Added grace period for "Nothing Playing" (prevents flash on transient disconnects)
- **Pi Kiosk Improvements**:
  - Script now backs up existing autostart before modifying (preserves other apps like weather station)
  - Added Chromium crash popup prevention (cleans exit state before launch)
  - Added `--disable-restore-session-state` and `--disable-features=InfiniteSessionRestore`

## Planned Features

- **REintegrate with PI screen timeout**: Reimplement the behaviour that previously existed on pi in which the screen would go to sleep at night and/or sometimes show screensavers.  Document old experience (is it still working now or partially working) then determine what we want to do going forward



## Development Workflow

### After Code Changes
Code changes require rebuilding the Docker container:
```bash
docker compose down && docker compose build --no-cache && docker compose up -d

# Verify the change is live:
curl -s http://localhost:5174/api/config  # Check new endpoints exist
curl -s http://localhost:5174/static/app.js | head -50  # Verify JS changes
```

### Updating the Pi Display
After server changes, the Pi's Chromium caches old files aggressively:
```bash
# Clear cache and restart browser
ssh pi@weatherpi3.local "killall chromium-browser; \
  rm -rf ~/.cache/chromium ~/.config/chromium/Default/Cache; \
  DISPLAY=:0 chromium-browser 'http://10.0.1.116:5174/?mode=off' --kiosk &"
```

### Verifying Pi Display (REQUIRED)
Never assume changes worked - take a screenshot:
```bash
ssh pi@weatherpi3.local "DISPLAY=:0 scrot /tmp/screen.png"
scp pi@weatherpi3.local:/tmp/screen.png /tmp/pi-verify.png
open /tmp/pi-verify.png
```

### Common Gotchas
- **"404 Not Found" on new endpoint** → Docker container has old code, rebuild it
- **Pi shows old UI** → Browser cache, clear it and restart Chromium
- **Changes work locally but not on Pi** → Check both server rebuild AND browser cache

## Known Issues / Future Work
- **Sonos connection timeouts**: Docker bridge networking can intermittently lose connection to Sonos. Container will auto-recover on next poll cycle. If stuck showing "Nothing Playing", restart Docker: `docker compose restart`. Note: `network_mode: host` doesn't work on macOS (Docker runs in a VM).
- Sonos auto-discovery times out on some networks - use direct IP instead
- Spotify will provide higher-res art (640x640) when API reopens
- Consider framebuffer fallback for Pi Zero/1 (512MB RAM too low for Chromium)
- Consider adding MusicBrainz as fallback for albums iTunes doesn't match

## SSH to Legacy Raspberry Pi (Debian 8 Jessie)

When connecting from a modern Mac to an old Raspberry Pi running Debian 8 Jessie (OpenSSH 6.7), SSH key authentication may fail silently. The Pi's old OpenSSH doesn't support RSA-SHA2 signatures that modern clients use by default.

**Symptoms:**
- `ssh-copy-id` succeeds but SSH still prompts for password
- `ssh -v` shows: "Server accepts key" followed by "Authentications that can continue: publickey,password"
- Permissions on `~/.ssh` (700) and `authorized_keys` (600) are correct

**Solution:** Add to your Mac's `~/.ssh/config`:
```
Host weatherpi3.local weatherpi3.homestead.com
    PubkeyAcceptedAlgorithms +ssh-rsa
    HostkeyAlgorithms +ssh-rsa
```

This tells the Mac's SSH client to use the legacy RSA-SHA1 algorithm that OpenSSH 6.7 understands.

## Target Deployment: weatherpi3

**Hardware:** Raspberry Pi 3 (armv7l, BCM2835)
**OS:** Raspbian Jessie (Debian 8) - 2015 vintage
**Display:** Has lightdm + Chromium

**Status (Jan 2026):** Configured as kiosk-only display. Server runs in Docker on Mac.

### What Was Done
1. Removed bloatware (wolfram, libreoffice, scratch, etc.) - freed ~1.7GB
2. Fixed apt repos (`legacy.raspbian.org` for Jessie)
3. Attempted Python 3.11 compile - failed due to old OpenSSL (1.0.1 vs required 1.1.1)
4. Decision: Use kiosk-only mode instead

### Apt Repo Fix for Jessie
The default Raspbian Jessie repos are gone. Use legacy:
```bash
sudo sed -i 's|http://mirrordirector.raspbian.org/raspbian/|http://legacy.raspbian.org/raspbian/|g' /etc/apt/sources.list
sudo apt-get update
```
