"""Application configuration using TOML + environment variables."""

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Self

from dotenv import load_dotenv

# Load .env file for secrets
load_dotenv()


@dataclass
class ServerConfig:
    """Server settings."""

    host: str = "0.0.0.0"
    port: int = 5174
    debug: bool = False


@dataclass
class PollingConfig:
    """Polling settings."""

    interval: float = 3.0


@dataclass
class SonosConfig:
    """Sonos settings."""

    enabled: bool = True
    ip: str = ""
    room: str = ""


@dataclass
class SpotifyConfig:
    """Spotify settings."""

    enabled: bool = False  # Spotify API new apps paused (Jan 2026)
    redirect_uri: str = "http://localhost:5174/callback"
    cache_path: str = ".spotify_cache"

    # These come from environment variables (secrets)
    client_id: str = field(default_factory=lambda: os.getenv("SPOTIFY_CLIENT_ID", ""))
    client_secret: str = field(default_factory=lambda: os.getenv("SPOTIFY_CLIENT_SECRET", ""))


@dataclass
class Settings:
    """Application settings loaded from config.toml and environment."""

    server: ServerConfig = field(default_factory=ServerConfig)
    polling: PollingConfig = field(default_factory=PollingConfig)
    sonos: SonosConfig = field(default_factory=SonosConfig)
    spotify: SpotifyConfig = field(default_factory=SpotifyConfig)

    @classmethod
    def load(cls, config_path: Path | None = None) -> Self:
        """Load settings from config.toml file."""
        if config_path is None:
            # Look for config.toml in current directory or project root
            config_path = Path("config.toml")
            if not config_path.exists():
                config_path = Path(__file__).parent.parent.parent / "config.toml"

        data = {}
        if config_path.exists():
            with open(config_path, "rb") as f:
                data = tomllib.load(f)

        return cls(
            server=ServerConfig(**data.get("server", {})),
            polling=PollingConfig(**data.get("polling", {})),
            sonos=SonosConfig(**data.get("sonos", {})),
            spotify=SpotifyConfig(
                **{
                    **data.get("spotify", {}),
                    # Always load secrets from env
                    "client_id": os.getenv("SPOTIFY_CLIENT_ID", ""),
                    "client_secret": os.getenv("SPOTIFY_CLIENT_SECRET", ""),
                }
            ),
        )


# Global settings instance - loaded lazily
_settings: Settings | None = None


def get_settings() -> Settings:
    """Get the global settings instance."""
    global _settings
    if _settings is None:
        _settings = Settings.load()
    return _settings
