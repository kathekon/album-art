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
            status: document.getElementById('status'),
            sourceBadge: document.getElementById('source-badge'),
            playState: document.getElementById('play-state'),
        };

        this.currentTrack = null;
        this.eventSource = null;
        this.reconnectDelay = 1000;
        this.maxReconnectDelay = 30000;

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
            this.reconnectDelay = 1000; // Reset on successful connection
        });

        this.eventSource.addEventListener('update', (event) => {
            const data = JSON.parse(event.data);
            console.log('Update:', data);
            this.handleUpdate(data.current_track);
        });

        this.eventSource.addEventListener('ping', () => {
            // Keepalive, do nothing
        });

        this.eventSource.onerror = (err) => {
            console.error('SSE error:', err);
            this.eventSource.close();
            this.eventSource = null;

            // Exponential backoff reconnect
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
            };
            img.onerror = () => {
                this.elements.albumArt.src = '/static/default-album.svg';
                this.elements.albumArt.classList.remove('loading');
            };
            img.src = track.album_art_url;
        } else if (!track.album_art_url) {
            this.elements.albumArt.src = '/static/default-album.svg';
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
        this.elements.status.classList.remove('hidden');
    }

    showNothingPlaying() {
        this.currentTrack = null;
        this.elements.app.classList.add('nothing-playing');
        this.elements.albumArt.src = '/static/default-album.svg';
        this.elements.title.textContent = 'Nothing Playing';
        this.elements.artist.textContent = '';
        this.elements.album.textContent = '';
        this.elements.trackInfo.classList.remove('hidden');
        this.elements.status.classList.add('hidden');
    }
}

// Initialize when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    new AlbumArtDisplay();
});
