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

        // Track prefetched artwork URLs to avoid duplicate fetches
        this.prefetchedUrls = new Set();

        this.init();
    }

    init() {
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

        // Load saved mode from localStorage
        // Only restore 'on' or 'detailed' - don't persist 'off' across sessions
        const savedMode = localStorage.getItem('displayMode');
        if (savedMode === 'detailed') {
            this.currentModeIndex = 1;
            this.elements.app.dataset.mode = 'detailed';
        } else {
            // Default to 'on' (metadata visible, no file info)
            this.currentModeIndex = 0;
            this.elements.app.dataset.mode = 'on';
        }
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
