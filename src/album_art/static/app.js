/**
 * Album Art Display - SSE Client
 */

class AlbumArtDisplay {
    constructor() {
        this.elements = {
            app: document.getElementById('app'),
            albumArt: document.getElementById('album-art'),
            trackInfo: document.getElementById('track-info'),
            title: document.getElementById('title'),
            artist: document.getElementById('artist'),
            album: document.getElementById('album'),
            fileInfo: document.getElementById('file-info'),
            status: document.getElementById('status'),
            sourceBadge: document.getElementById('source-badge'),
            playState: document.getElementById('play-state'),
        };

        this.currentTrack = null;
        this.eventSource = null;
        this.reconnectDelay = 1000;
        this.maxReconnectDelay = 30000;

        // Display modes: on -> detailed -> off -> on...
        this.modes = ['on', 'detailed', 'off'];
        this.currentModeIndex = 0;
        this.serverDefaultMode = 'on';  // Will be fetched from server

        // Track prefetched artwork URLs to avoid duplicate fetches
        this.prefetchedUrls = new Set();

        this.init();
    }

    async init() {
        // Fetch server config for default display mode
        await this.loadServerConfig();

        this.connect();

        // Handle visibility change to reconnect when tab becomes visible
        document.addEventListener('visibilitychange', () => {
            if (document.visibilityState === 'visible' && !this.eventSource) {
                this.connect();
            }
        });

        // Click anywhere to cycle display modes
        document.addEventListener('click', () => {
            this.cycleDisplayMode();
        });

        // Apply display mode: user preference overrides server default
        this.applyInitialMode();
    }

    async loadServerConfig() {
        try {
            const response = await fetch('/api/config');
            const config = await response.json();
            if (config.display && config.display.default_mode) {
                this.serverDefaultMode = config.display.default_mode;
                console.log('Server default mode:', this.serverDefaultMode);
            }
        } catch (err) {
            console.warn('Could not fetch server config, using defaults:', err);
        }
    }

    applyInitialMode() {
        // Priority: URL param > localStorage > server default
        const urlParams = new URLSearchParams(window.location.search);
        const urlMode = urlParams.get('mode');
        const savedMode = localStorage.getItem('displayMode');

        let mode;
        let source;
        if (urlMode && this.modes.includes(urlMode)) {
            // URL parameter takes highest priority (for kiosk setups)
            mode = urlMode;
            source = 'URL parameter';
        } else if (savedMode && this.modes.includes(savedMode)) {
            // User has a saved preference
            mode = savedMode;
            source = 'user preference';
        } else {
            // Fall back to server default
            mode = this.serverDefaultMode;
            source = 'server default';
        }

        this.currentModeIndex = this.modes.indexOf(mode);
        if (this.currentModeIndex === -1) {
            this.currentModeIndex = 0;
            mode = 'on';
        }

        this.elements.app.dataset.mode = mode;
        console.log('Display mode:', mode, `(${source})`);
    }

    cycleDisplayMode() {
        this.currentModeIndex = (this.currentModeIndex + 1) % this.modes.length;
        const newMode = this.modes[this.currentModeIndex];
        this.elements.app.dataset.mode = newMode;
        localStorage.setItem('displayMode', newMode);
        console.log('Display mode:', newMode);
    }

    connect() {
        if (this.eventSource) {
            this.eventSource.close();
        }

        console.log('Connecting to SSE stream...');
        this.eventSource = new EventSource('/api/stream');

        this.eventSource.addEventListener('state', (event) => {
            const data = JSON.parse(event.data);
            console.log('Initial state:', data);
            this.handleUpdate(data.current_track);
            this.reconnectDelay = 1000;
        });

        this.eventSource.addEventListener('update', (event) => {
            const data = JSON.parse(event.data);
            console.log('Update:', data);
            this.handleUpdate(data.current_track);
        });

        this.eventSource.addEventListener('ping', () => {
            // Keepalive
        });

        this.eventSource.onerror = (err) => {
            console.error('SSE error:', err);
            this.eventSource.close();
            this.eventSource = null;

            console.log(`Reconnecting in ${this.reconnectDelay}ms...`);
            setTimeout(() => {
                this.connect();
            }, this.reconnectDelay);

            this.reconnectDelay = Math.min(
                this.reconnectDelay * 2,
                this.maxReconnectDelay
            );
        };
    }

    handleUpdate(track) {
        if (!track) {
            this.showNothingPlaying();
            return;
        }

        this.currentTrack = track;
        this.updateDisplay(track);

        // Prefetch upcoming artwork for smooth transitions
        if (track.upcoming_art_urls && track.upcoming_art_urls.length > 0) {
            this.prefetchArtwork(track.upcoming_art_urls);
        }
    }

    prefetchArtwork(urls) {
        urls.forEach(url => {
            if (url && !this.prefetchedUrls.has(url)) {
                const img = new Image();
                img.src = url;
                this.prefetchedUrls.add(url);
                console.log('Prefetching artwork:', url.substring(0, 60) + '...');
            }
        });
    }

    updateDisplay(track) {
        this.elements.app.classList.remove('nothing-playing');

        // Update album art with fade transition
        if (track.album_art_url && track.album_art_url !== this.elements.albumArt.src) {
            this.elements.albumArt.classList.add('loading');

            const img = new Image();
            img.onload = () => {
                this.elements.albumArt.src = track.album_art_url;
                this.elements.albumArt.classList.remove('loading');
                // Update file info with image dimensions
                this.updateFileInfo(track, img.naturalWidth, img.naturalHeight);
            };
            img.onerror = () => {
                this.elements.albumArt.src = '/static/default-album.svg';
                this.elements.albumArt.classList.remove('loading');
                this.elements.fileInfo.textContent = '';
            };
            img.src = track.album_art_url;
        } else if (!track.album_art_url) {
            this.elements.albumArt.src = '/static/default-album.svg';
            this.elements.fileInfo.textContent = '';
        }

        // Update track info
        this.elements.title.textContent = track.title;
        this.elements.artist.textContent = track.artist;
        this.elements.album.textContent = track.album;
        this.elements.trackInfo.classList.remove('hidden');

        // Update status
        this.elements.sourceBadge.textContent = track.source;
        this.elements.sourceBadge.className = track.source;
        this.elements.playState.textContent = track.is_playing ? 'Playing' : 'Paused';
    }

    updateFileInfo(track, width, height) {
        const parts = [];

        // Room name (for multi-room Sonos setups)
        if (track.room_name) {
            parts.push(track.room_name);
        }

        // Image dimensions
        if (width && height) {
            parts.push(`${width}×${height}`);
        }

        // Art source (sonos, itunes, spotify)
        if (track.art_source) {
            parts.push(track.art_source);
        }

        // Duration
        if (track.duration_ms) {
            const mins = Math.floor(track.duration_ms / 60000);
            const secs = Math.floor((track.duration_ms % 60000) / 1000);
            parts.push(`${mins}:${secs.toString().padStart(2, '0')}`);
        }

        // Position
        if (track.position_ms && track.duration_ms) {
            const pct = Math.round((track.position_ms / track.duration_ms) * 100);
            parts.push(`${pct}%`);
        }

        this.elements.fileInfo.textContent = parts.join(' · ');
    }

    showNothingPlaying() {
        this.currentTrack = null;
        this.elements.app.classList.add('nothing-playing');
        this.elements.albumArt.src = '/static/default-album.svg';
        this.elements.title.textContent = 'Nothing Playing';
        this.elements.artist.textContent = '';
        this.elements.album.textContent = '';
        this.elements.fileInfo.textContent = '';
        this.elements.trackInfo.classList.remove('hidden');
    }
}

// Initialize when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    new AlbumArtDisplay();
});
