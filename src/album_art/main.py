"""FastAPI application for album art display."""

import asyncio
import json
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from sse_starlette.sse import EventSourceResponse

from .config import get_settings
from .services.poller import poller
from .services.state import playback_state

# Configure logging
settings = get_settings()
logging.basicConfig(
    level=logging.DEBUG if settings.server.debug else logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler for startup/shutdown."""
    # Startup
    logger.info("Starting album art display...")
    logger.info(f"Server: http://{settings.server.host}:{settings.server.port}")
    await poller.start()
    yield
    # Shutdown
    logger.info("Shutting down...")
    await poller.stop()


app = FastAPI(
    title="Album Art Display",
    description="Display album art from Sonos and Spotify",
    version="0.1.0",
    lifespan=lifespan,
)

# Mount static files
static_path = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=str(static_path)), name="static")


@app.get("/", response_class=HTMLResponse)
async def index():
    """Serve the main display page."""
    html_path = static_path / "index.html"
    return HTMLResponse(content=html_path.read_text())


@app.get("/api/state")
async def get_state():
    """Get current playback state."""
    return playback_state.to_dict()


@app.get("/api/sources")
async def get_sources():
    """Get status of all configured sources."""
    return {
        "sources": [
            {
                "name": source.name,
                "available": source.is_available,
            }
            for source in poller.sources
        ]
    }


@app.get("/api/config")
async def get_config():
    """Get client-side configuration."""
    # Use get_settings() to pick up CLI overrides (not module-level settings)
    current_settings = get_settings()
    return {
        "display": {
            "default_mode": current_settings.display.default_mode,
        }
    }


@app.get("/api/stream")
async def stream(request: Request):
    """SSE endpoint for real-time playback updates."""

    async def event_generator():
        queue: asyncio.Queue = asyncio.Queue()

        async def on_update(track):
            await queue.put(track)

        # Subscribe to state changes
        playback_state.subscribe(on_update)

        try:
            # Send initial state
            yield {
                "event": "state",
                "data": json.dumps(playback_state.to_dict()),
            }

            while True:
                # Check for disconnect
                if await request.is_disconnected():
                    break

                try:
                    # Wait for updates with timeout
                    track = await asyncio.wait_for(queue.get(), timeout=30.0)
                    yield {
                        "event": "update",
                        "data": json.dumps(
                            {
                                "current_track": track.to_dict() if track else None,
                            }
                        ),
                    }
                except asyncio.TimeoutError:
                    # Send keepalive
                    yield {"event": "ping", "data": ""}
        finally:
            playback_state.unsubscribe(on_update)

    return EventSourceResponse(event_generator())


def run():
    """Run the application with uvicorn."""
    import argparse

    import uvicorn

    from .config import Settings, set_settings

    parser = argparse.ArgumentParser(description="Album Art Display")
    parser.add_argument(
        "--default-mode",
        choices=["on", "detailed", "off"],
        help="Default display mode for metadata (on, detailed, off)",
    )
    parser.add_argument(
        "--port",
        type=int,
        help="Port to run on (overrides config.toml)",
    )
    args = parser.parse_args()

    # Load settings and apply CLI overrides
    settings = Settings.load()
    if args.default_mode:
        settings.display.default_mode = args.default_mode
    if args.port:
        settings.server.port = args.port

    # Store settings so they're available to the app
    set_settings(settings)

    uvicorn.run(
        "album_art.main:app",
        host=settings.server.host,
        port=settings.server.port,
        reload=settings.server.debug,
    )


if __name__ == "__main__":
    run()
