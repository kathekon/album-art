# Album Art Display - Enhanced Display Modes

## Requested Features

1. **Enhanced "detailed" mode**: Show queue status and cached image count indicators
2. **Comparison mode**: When using iTunes art, show original Sonos thumbnail above metadata
3. **Debug mode**: Vertical thumbnail stack on left showing prefetched queue images with source badges
4. Click anywhere to cycle: `on` → `detailed` → `comparison` → `debug` → `off`

---

## Implementation Plan

### Phase 1: Backend - Preserve Original Sonos URL

**File**: [base.py](../src/album_art/sources/base.py)

Add new fields to `TrackInfo`:

```python
# Preserve original Sonos URL when iTunes is used (for comparison mode)
original_sonos_art_url: str | None = None

# Enhanced queue items with iTunes lookup results
upcoming_queue_items: list[dict] = field(default_factory=list)
# Each item: {sonos_url, itunes_url, title, artist, album, has_itunes_match, display_url}

# Queue status indicator
queue_in_use: bool = False
```

Update `to_dict()` to include new fields.

---

### Phase 2: Backend - Enhanced Queue Processing

**File**: [sonos.py](../src/album_art/sources/sonos.py)

1. **Preserve original URL** when iTunes art is found:
```python
original_sonos_url = album_art  # Save before iTunes lookup
if settings.artwork.prefer_itunes:
    itunes_art = await get_itunes_artwork(artist, album)
    if itunes_art:
        album_art = itunes_art
        art_source = "itunes"
```

2. **New method** `_get_enhanced_queue_items()`:
   - Get queue items with metadata (title, artist, album)
   - Do iTunes lookups for each item **in parallel** using `asyncio.gather()`
   - Return list of dicts with both Sonos and iTunes URLs

3. **Return both URLs** in TrackInfo:
```python
return TrackInfo(
    album_art_url=album_art,
    original_sonos_art_url=original_sonos_url if art_source == "itunes" else None,
    upcoming_queue_items=queue_items,
    queue_in_use=len(queue_items) > 0,
    # Keep backward compat
    upcoming_art_urls=[item["display_url"] for item in queue_items],
)
```

---

### Phase 3: Frontend HTML

**File**: [index.html](../src/album_art/templates/index.html)

Add new elements:

```html
<!-- Debug mode: Queue thumbnail stack (left side) -->
<div id="queue-debug" class="hidden">
    <div id="queue-thumbnails"></div>
</div>

<!-- Comparison mode: Original Sonos thumbnail (above metadata) -->
<div id="comparison-thumbnail" class="hidden">
    <img id="sonos-art-thumb" src="" alt="Sonos Original">
    <span class="source-label">Sonos Original</span>
</div>

<!-- Detailed mode indicators -->
<div id="detailed-indicators">
    <span id="queue-indicator"></span>
    <span id="cache-indicator"></span>
</div>
```

---

### Phase 4: Frontend CSS

**File**: [style.css](../src/album_art/static/style.css)

```css
/* Queue debug panel - left side vertical stack */
#queue-debug {
    position: fixed;
    left: 16px;
    top: 50%;
    transform: translateY(-50%);
    display: flex;
    flex-direction: column;
    gap: 8px;
}

.queue-thumbnail { width: 80px; height: 80px; border-radius: 4px; }
.queue-thumbnail.has-itunes { border: 2px solid rgba(100, 255, 100, 0.5); }
.queue-thumbnail.no-itunes { border: 2px solid rgba(255, 200, 0, 0.5); }

.queue-source-badge {
    position: absolute; bottom: 2px; right: 2px;
    font-size: 0.5rem; padding: 1px 4px;
}
.queue-source-badge.itunes { background: rgba(251, 91, 137, 0.9); color: white; }
.queue-source-badge.sonos { background: rgba(255, 255, 255, 0.8); color: #333; }

/* Comparison thumbnail - above metadata */
#comparison-thumbnail {
    position: fixed;
    bottom: 160px;
    right: 32px;
}
#sonos-art-thumb { width: 100px; height: 100px; border-radius: 4px; }

/* Mode visibility rules */
#app[data-mode="on"] #comparison-thumbnail,
#app[data-mode="on"] #queue-debug,
#app[data-mode="on"] #detailed-indicators { display: none; }

#app[data-mode="detailed"] #detailed-indicators { display: flex; }
#app[data-mode="detailed"] #comparison-thumbnail,
#app[data-mode="detailed"] #queue-debug { display: none; }

#app[data-mode="comparison"] #comparison-thumbnail { display: block; }
#app[data-mode="comparison"] #queue-debug { display: none; }

#app[data-mode="debug"] #queue-debug { display: flex; }
#app[data-mode="debug"] #detailed-indicators { display: flex; }
```

---

### Phase 5: Frontend JavaScript

**File**: [app.js](../src/album_art/static/app.js)

1. **Update mode array**:
```javascript
this.modes = ['on', 'detailed', 'comparison', 'debug', 'off'];
```

2. **Smart mode cycling** - skip comparison if no iTunes art, skip debug if no queue:
```javascript
cycleDisplayMode() {
    let nextIndex = (this.currentModeIndex + 1) % this.modes.length;
    let newMode = this.modes[nextIndex];

    // Skip comparison if not using iTunes (nothing to compare)
    if (newMode === 'comparison' && !this.hasComparisonData()) {
        nextIndex = (nextIndex + 1) % this.modes.length;
        newMode = this.modes[nextIndex];
    }

    // Skip debug if no queue data
    if (newMode === 'debug' && !this.hasQueueData()) {
        nextIndex = (nextIndex + 1) % this.modes.length;
        newMode = this.modes[nextIndex];
    }

    this.currentModeIndex = nextIndex;
    this.elements.app.dataset.mode = newMode;
}
```

3. **New update methods**:
   - `updateComparisonThumbnail(track)` - set Sonos thumbnail src
   - `updateQueueDebug(track)` - render thumbnail stack with source badges
   - `updateDetailedIndicators(track)` - show queue count and cached image count

---

## Files to Modify

| File | Changes |
|------|---------|
| [base.py](../src/album_art/sources/base.py) | Add `original_sonos_art_url`, `upcoming_queue_items`, `queue_in_use` |
| [sonos.py](../src/album_art/sources/sonos.py) | Preserve original URL, add `_get_enhanced_queue_items()` |
| [index.html](../src/album_art/templates/index.html) | Add comparison thumbnail, queue debug panel, indicators |
| [style.css](../src/album_art/static/style.css) | Position new elements, mode visibility rules |
| [app.js](../src/album_art/static/app.js) | 5-mode cycling, render methods for new elements |

---

## Verification

1. **Detailed mode**: Play a queue → should show "Q: 5 items" and "Cached: X images"
2. **Comparison mode**: When iTunes art is used → should show small Sonos thumbnail above metadata
3. **Debug mode**: Should show vertical stack of queue thumbnails with green (iTunes) or yellow (Sonos) borders
4. **Mode cycling**: Click should cycle through available modes, skipping comparison/debug when no data

---

## Performance Notes

- iTunes lookups for queue items done in parallel via `asyncio.gather()`
- Existing iTunes cache prevents duplicate lookups
- Queue items rarely change, so lookups amortized over time
