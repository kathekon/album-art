# Album Art Display

A full-screen album art display for Sonos, designed for Raspberry Pi kiosk setups.

![Python](https://img.shields.io/badge/python-3.11+-blue.svg)
![License](https://img.shields.io/badge/license-MIT-green.svg)

## Features

- **High-resolution artwork** - Fetches up to 3000×3000 art from iTunes Search API
- **Real-time updates** - Server-Sent Events push track changes instantly
- **Kiosk-ready** - Designed for headless Raspberry Pi displays
- **Queue prefetching** - Smooth transitions with preloaded artwork
- **Multiple display modes** - Click to cycle: metadata on/detailed/off

## Quick Start

### Run Locally
```bash
# Install dependencies
pip install uv
uv sync

# Configure your Sonos IP
echo '[sonos]
ip = "YOUR_SONOS_IP"' > config.toml

# Run
uv run album-art
# Open http://localhost:5174
```

### Docker (Recommended)
```bash
docker compose up -d
# Open http://localhost:5174
```

## Raspberry Pi Setup

For Raspberry Pi kiosk display (server runs on your Mac/server):

```bash
# On your Pi:
scp scripts/pi-kiosk-only.sh pi@your-pi:~/
ssh pi@your-pi
./pi-kiosk-only.sh http://YOUR_SERVER_IP:5174
sudo reboot
```

The Pi will boot directly into full-screen Chromium showing your album art.

## Configuration

Create `config.toml`:

```toml
[server]
port = 5174

[sonos]
ip = "192.168.1.100"  # Your Sonos speaker IP

[artwork]
prefer_itunes = true   # Use high-res iTunes art
itunes_size = 1200     # Max: 3000

[display]
default_mode = "on"    # on, detailed, or off
```

## Display Modes

Click anywhere on the display to cycle through modes:

| Mode | Shows |
|------|-------|
| **on** | Title, artist, album, source badge |
| **detailed** | + image dimensions, duration, progress, art source |
| **off** | Album art only (no overlay) |

## Architecture

```
┌─────────────────┐     SSE      ┌─────────────────┐
│  FastAPI Server │─────────────▶│     Browser     │
│   (Python/uv)   │              │  (Full-screen)  │
└────────┬────────┘              └─────────────────┘
         │
    Polls every 3s
         │
    ┌────┴────┐
    │         │
┌───┴───┐ ┌───┴───┐
│ Sonos │ │iTunes │
│ (SoCo)│ │  API  │
└───────┘ └───────┘
```

## API Endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /` | HTML display page |
| `GET /api/state` | Current playback state (JSON) |
| `GET /api/stream` | SSE stream for real-time updates |
| `GET /api/sources` | Available music sources |
| `GET /api/config` | Current configuration |

## Development

```bash
# Run tests
uv run pytest

# Run with auto-reload
uv run album-art --reload

# Rebuild Docker after changes
docker compose down && docker compose build --no-cache && docker compose up -d
```

## Troubleshooting

**Sonos not found?**
- Use direct IP instead of auto-discovery: `[sonos] ip = "192.168.1.100"`
- Check your Sonos is on the same network

**Pi shows "Chromium didn't shut down correctly"?**
- The kiosk script handles this automatically with state cleanup
- If it persists, clear Chromium data: `rm -rf ~/.config/chromium`

**Album art not updating on Pi?**
- Chromium caches aggressively. Clear cache:
  ```bash
  ssh pi@your-pi "killall chromium-browser; rm -rf ~/.cache/chromium"
  ```

## License

MIT
