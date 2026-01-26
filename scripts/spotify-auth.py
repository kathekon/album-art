#!/usr/bin/env python
"""One-time Spotify OAuth authorization script.

Run this script once on a machine with a browser to authorize
and generate the token cache file, then copy .spotify_cache to the Pi.
"""

import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import spotipy
from spotipy.oauth2 import SpotifyOAuth

from album_art.config import get_settings


def main():
    settings = get_settings()

    if not settings.spotify.client_id or not settings.spotify.client_secret:
        print("Error: SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET must be set")
        print()
        print("Setup instructions:")
        print("1. Go to https://developer.spotify.com/dashboard")
        print("2. Create an app (any name)")
        print("3. Go to app settings and add redirect URI:")
        print(f"   {settings.spotify.redirect_uri}")
        print("4. Copy your .env.example to .env and fill in:")
        print("   - SPOTIFY_CLIENT_ID")
        print("   - SPOTIFY_CLIENT_SECRET")
        print("5. Run this script again")
        sys.exit(1)

    print("Authorizing with Spotify...")
    print(f"Redirect URI: {settings.spotify.redirect_uri}")
    print()
    print("A browser window will open. Log in to Spotify and authorize the app.")
    print()

    auth_manager = SpotifyOAuth(
        client_id=settings.spotify.client_id,
        client_secret=settings.spotify.client_secret,
        redirect_uri=settings.spotify.redirect_uri,
        scope="user-read-currently-playing user-read-playback-state",
        cache_path=settings.spotify.cache_path,
        open_browser=True,
    )

    # This will open browser for authorization
    sp = spotipy.Spotify(auth_manager=auth_manager)

    # Verify by getting user info
    try:
        user = sp.current_user()
        print()
        print(f"Successfully authorized as: {user['display_name']}")
        print(f"Token cached to: {settings.spotify.cache_path}")
        print()
        print("To deploy to Raspberry Pi, copy the cache file:")
        print(f"  scp {settings.spotify.cache_path} pi@<pi-hostname>:~/album_art/")
    except Exception as e:
        print(f"Error verifying authorization: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
