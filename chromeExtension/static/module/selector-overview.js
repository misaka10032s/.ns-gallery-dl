/**
 * NS Media Hub — Overview Overlay (v2)
 * Fullscreen in-page overlay with a uniform tile grid for bulk selection.
 * Interactions: click-toggle, Shift+click range, drag-marquee, 全選/反選/清除/下載所選.
 *
 * Depends on: NsCatalog (selector-catalog.js) and NsSelector (selector-core.js).
 * Loaded before each site's content.js.
 * Exposes: window.NsOverview
 */
(function () {
    'use strict';

    // ── state ─────────────────────────────────────────────────────────────────

    var _overlay = null;       // the fullscreen overlay element
    var _gridEl = null;        // the scrollable tile grid inside the overlay
    var _countEl = null;       // live count display in overlay header
    var _renderedCount = 0;    // how many catalog entries have been rendered so far
    var _isOpen = false;

    // Drag-marquee state
    var _dragging = false;
    var _dragStartX = 0;
    var _dragStartY = 0;
    var _dragCatalogSnap = null; // catalog snapshot captured at drag start
    var _marqueeEl = null;

    // Shift-click anchor within the overview (catalog index)
    var _lastClickIdx = -1;

    // ── overlay construction ──────────────────────────────────────────────────

    function _buildOverlay() {
        var ov = document.createElement('div');
        ov.id = 'ns-overview-overlay';
        ov.innerHTML =
            '<div class="ns-ovr-header">' +
                '<span class="ns-ovr-title">NS Media Hub — 圖片總覽</span>' +
                '<span class="ns-ovr-count">已選 0 項 / 共 0 張</span>' +
                '<div class="ns-ovr-actions">' +
                    '<button class="ns-ovr-btn" id="ns-ovr-all">全選</button>' +
                    '<button class="ns-ovr-btn" id="ns-ovr-invert">反選</button>' +
                    '<button class="ns-ovr-btn" id="ns-ovr-clear">清除</button>' +
                    '<button class="ns-ovr-btn ns-ovr-download" id="ns-ovr-download">下載所選</button>' +
                    '<button class="ns-ovr-btn ns-ovr-close" id="ns-ovr-close">✕ 關閉</button>' +
                '</div>' +
            '</div>' +
            '<div class="ns-ovr-grid" id="ns-ovr-grid"></div>';
        return ov;
    }

    function _attachHeaderEvents() {
        _overlay.querySelector('#ns-ovr-all').addEventListener('click', function () {
            NsSelector.selectAll();
            NsSelector.save();
            _refreshTileStates();
            NsSelector.applyVisuals();
            _updateCount();
        });

        _overlay.querySelector('#ns-ovr-invert').addEventListener('click', function () {
            NsSelector.invertAll();
            NsSelector.save();
            _refreshTileStates();
            NsSelector.applyVisuals();
            _updateCount();
        });

        _overlay.querySelector('#ns-ovr-clear').addEventListener('click', function () {
            NsSelector.clear();
            NsSelector.save();
            _refreshTileStates();
            NsSelector.applyVisuals();
            _updateCount();
        });

        _overlay.querySelector('#ns-ovr-download').addEventListener('click', function () {
            NsSelector.doSubmit();
        });

        _overlay.querySelector('#ns-ovr-close').addEventListener('click', function () {
            _close();
        });
    }

    // ── tile rendering ────────────────────────────────────────────────────────

    function _makeTile(entry) {
        var tile = document.createElement('div');
        tile.className = 'ns-ovr-tile';
        tile.dataset.url = entry.url;
        tile.dataset.catIdx = String(entry.order);

        // Thumbnail image with lazy loading
        var img = document.createElement('img');
        img.loading = 'lazy';
        img.src = entry.previewSrc || entry.url;
        // Fallback: if previewSrc fails, try the original URL
        img.addEventListener('error', function () {
            if (img.src !== entry.url) img.src = entry.url;
        });
        img.draggable = false;

        // Corner check badge (shows when selected)
        var check = document.createElement('span');
        check.className = 'ns-ovr-check';
        check.textContent = '✓';

        tile.appendChild(img);
        tile.appendChild(check);

        if (NsSelector.has(entry.url)) {
            tile.classList.add('ns-ovr-tile-selected');
        }

        return tile;
    }

    function _appendNewTiles() {
        var catalog = NsCatalog.getAll();
        var fragment = document.createDocumentFragment();
        for (var i = _renderedCount; i < catalog.length; i++) {
            fragment.appendChild(_makeTile(catalog[i]));
        }
        _renderedCount = catalog.length;
        _gridEl.appendChild(fragment);
        _updateCount();
    }

    function _refreshTileStates() {
        var tiles = _gridEl.querySelectorAll('.ns-ovr-tile');
        tiles.forEach(function (tile) {
            var url = tile.dataset.url;
            if (NsSelector.has(url)) {
                tile.classList.add('ns-ovr-tile-selected');
            } else {
                tile.classList.remove('ns-ovr-tile-selected');
            }
        });
        _updateCount();
    }

    function _updateCount() {
        if (!_countEl) return;
        var sel = NsSelector.getSelectedCount();
        var total = NsCatalog.getCount();
        _countEl.textContent = '已選 ' + sel + ' 項 / 共 ' + total + ' 張';
    }

    // ── tile click handling ───────────────────────────────────────────────────

    function _handleTileClick(e) {
        var tile = e.target.closest('.ns-ovr-tile');
        if (!tile) return;

        var url = tile.dataset.url;
        var catIdx = parseInt(tile.dataset.catIdx, 10);

        if (e.shiftKey && _lastClickIdx >= 0) {
            var lo = Math.min(_lastClickIdx, catIdx);
            var hi = Math.max(_lastClickIdx, catIdx);
            NsSelector.addRange(lo, hi);
            // Anchor stays at _lastClickIdx
        } else {
            NsSelector.toggle(url);
            _lastClickIdx = NsSelector.has(url) ? catIdx : -1;
        }

        NsSelector.save();
        _refreshTileStates();
        NsSelector.applyVisuals();
    }

    // ── drag-marquee ──────────────────────────────────────────────────────────

    function _rectsIntersect(a, b) {
        // a and b are {left, top, right, bottom} in viewport coords
        return !(b.right < a.left || b.left > a.right ||
                 b.bottom < a.top  || b.top  > a.bottom);
    }

    function _onGridMouseDown(e) {
        if (e.button !== 0) return;
        // Do not start marquee when clicking a tile or a button
        if (e.target.closest('.ns-ovr-tile') || e.target.closest('button')) return;

        _dragging = true;
        _dragStartX = e.clientX;
        _dragStartY = e.clientY;
        _dragCatalogSnap = NsCatalog.getAll(); // freeze catalog at drag start

        _marqueeEl = document.createElement('div');
        _marqueeEl.className = 'ns-ovr-marquee';
        document.body.appendChild(_marqueeEl);

        document.addEventListener('mousemove', _onMarqueeMove);
        document.addEventListener('mouseup', _onMarqueeUp);
        e.preventDefault();
    }

    function _onMarqueeMove(e) {
        if (!_dragging || !_marqueeEl) return;
        var x1 = Math.min(e.clientX, _dragStartX);
        var y1 = Math.min(e.clientY, _dragStartY);
        var x2 = Math.max(e.clientX, _dragStartX);
        var y2 = Math.max(e.clientY, _dragStartY);
        _marqueeEl.style.left   = x1 + 'px';
        _marqueeEl.style.top    = y1 + 'px';
        _marqueeEl.style.width  = (x2 - x1) + 'px';
        _marqueeEl.style.height = (y2 - y1) + 'px';
    }

    function _onMarqueeUp(e) {
        if (!_dragging) return;
        _dragging = false;
        document.removeEventListener('mousemove', _onMarqueeMove);
        document.removeEventListener('mouseup', _onMarqueeUp);

        var marqueeRect = {
            left:   Math.min(e.clientX, _dragStartX),
            top:    Math.min(e.clientY, _dragStartY),
            right:  Math.max(e.clientX, _dragStartX),
            bottom: Math.max(e.clientY, _dragStartY)
        };

        if (_marqueeEl) { _marqueeEl.remove(); _marqueeEl = null; }

        var minDrag = 4; // ignore accidental micro-drags
        if ((marqueeRect.right - marqueeRect.left) < minDrag &&
            (marqueeRect.bottom - marqueeRect.top) < minDrag) {
            _dragCatalogSnap = null;
            return;
        }

        // Build a set of catalog URLs valid at drag start (guard against growth mid-gesture)
        var snapUrls = new Set();
        if (_dragCatalogSnap) {
            _dragCatalogSnap.forEach(function (e2) { snapUrls.add(e2.url); });
        }
        _dragCatalogSnap = null;

        // Select tiles that intersect the marquee (viewport coords)
        var tiles = _gridEl.querySelectorAll('.ns-ovr-tile');
        var changed = false;
        tiles.forEach(function (tile) {
            var url = tile.dataset.url;
            if (!snapUrls.has(url)) return; // skip tiles added after drag start
            var tileRect = tile.getBoundingClientRect();
            if (_rectsIntersect(tileRect, marqueeRect)) {
                NsSelector.add(url);
                changed = true;
            }
        });

        if (changed) {
            NsSelector.save();
            _refreshTileStates();
            NsSelector.applyVisuals();
        }
    }

    // ── open / close ──────────────────────────────────────────────────────────

    function _open() {
        if (_isOpen) return;
        _isOpen = true;
        _lastClickIdx = -1;
        _renderedCount = 0;

        _overlay = _buildOverlay();
        document.body.appendChild(_overlay);

        _gridEl = _overlay.querySelector('#ns-ovr-grid');
        _countEl = _overlay.querySelector('.ns-ovr-count');

        _attachHeaderEvents();

        // Tile click handler (delegated to grid)
        _gridEl.addEventListener('click', _handleTileClick);

        // Drag-marquee starts on the grid background
        _gridEl.addEventListener('mousedown', _onGridMouseDown);

        // Initial tile render
        _appendNewTiles();

        // Lock body scroll
        document.body.style.overflow = 'hidden';

        // Esc to close
        document.addEventListener('keydown', _onKeydown);
    }

    function _close() {
        if (!_isOpen) return;
        _isOpen = false;

        // Clean up marquee if dragging when closed
        if (_dragging) {
            _dragging = false;
            document.removeEventListener('mousemove', _onMarqueeMove);
            document.removeEventListener('mouseup', _onMarqueeUp);
            if (_marqueeEl) { _marqueeEl.remove(); _marqueeEl = null; }
        }

        document.removeEventListener('keydown', _onKeydown);
        document.body.style.overflow = '';

        if (_overlay) { _overlay.remove(); _overlay = null; }
        _gridEl = null;
        _countEl = null;
        _renderedCount = 0;
        _lastClickIdx = -1;
        _dragCatalogSnap = null;
    }

    function _onKeydown(e) {
        if (e.key === 'Escape') _close();
    }

    // ── public API ────────────────────────────────────────────────────────────

    window.NsOverview = {
        open: function () { _open(); },
        close: function () { _close(); },
        toggle: function () { if (_isOpen) { _close(); } else { _open(); } },
        isOpen: function () { return _isOpen; },

        /**
         * Called by NsSelector._onCatalogUpdate and NsSelector.applyVisuals.
         * Appends new tiles + refreshes selected states.
         */
        refresh: function () {
            if (!_isOpen) return;
            _appendNewTiles();   // add any new catalog entries
            _refreshTileStates(); // sync selected classes
        }
    };

    // Alt+G shortcut (also wired in selector-core.js for when mode is active)
    document.addEventListener('keydown', function (e) {
        if (e.altKey && (e.key === 'g' || e.key === 'G')) {
            if (window.NsSelector && NsSelector.isActive()) {
                window.NsOverview.toggle();
            }
        }
    });

})();
