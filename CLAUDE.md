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

## Pi Deployment
Scripts in `scripts/`:
- `setup-pi.sh` - Initial Pi setup (installs uv, deps)
- `install-kiosk.sh` - Configures Chromium kiosk + systemd service
- `spotify-auth.py` - One-time Spotify OAuth (when API reopens)

## Known Issues / Future Work
- Sonos auto-discovery times out on some networks - use direct IP instead
- Album art resolution depends on source (Sonos/Pandora returns ~500x500)
- Spotify will provide higher-res art (640x640) when available
- Consider framebuffer fallback for Pi Zero/1 (512MB RAM too low for Chromium)
