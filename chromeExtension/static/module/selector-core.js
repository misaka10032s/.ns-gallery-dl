/**
 * NS Media Hub — Selection Core (v2)
 * Selection engine: toolbar, click/shift-click handling, mode lifecycle,
 * sessionStorage persistence, and submit with success-driven auto-clear.
 *
 * Depends on: NsCatalog (selector-catalog.js, loaded before this file).
 * Loaded before selector-overview.js and each site's content.js.
 * Exposes: window.NsSelector
 */
(function () {
    'use strict';

    // ── internal state ────────────────────────────────────────────────────────

    var _config = null;
    var _active = false;
    var _selected = new Set();
    var _lastCatalogIdx = -1;   // anchor for shift-click range selection
    var _toolbar = null;
    var _storageKey = 'ns-sel-v2:' + location.href;

    // ── persistence ───────────────────────────────────────────────────────────

    function _save() {
        try {
            sessionStorage.setItem(_storageKey, JSON.stringify(Array.from(_selected)));
        } catch (e) {}
    }

    function _restore() {
        try {
            var raw = sessionStorage.getItem(_storageKey);
            if (!raw) return;
            var arr = JSON.parse(raw);
            if (Array.isArray(arr)) _selected = new Set(arr);
        } catch (e) {}
    }

    // ── count display ─────────────────────────────────────────────────────────

    function _updateCount() {
        if (!_toolbar) return;
        var el = _toolbar.querySelector('.ns-sel-count');
        if (el) el.textContent = '已選 ' + _selected.size + ' 項';
    }

    // ── in-page visual feedback ───────────────────────────────────────────────

    function _applyVisuals() {
        if (!_config || typeof _config.getItems !== 'function') {
            _updateCount();
            return;
        }
        var items;
        try { items = _config.getItems() || []; } catch (e) { items = []; }

        items.forEach(function (item) {
            if (!item || !item.container) return;
            var url = NsCatalog.resolveItemUrl(item);

            // Ensure container is positioned for ::after overlay and sticky badge
            var pos = getComputedStyle(item.container).position;
            if (pos === 'static') item.container.style.position = 'relative';

            if (_selected.has(url)) {
                item.container.classList.add('ns-selected');
            } else {
                item.container.classList.remove('ns-selected');
            }
        });
        _updateCount();

        // Sync overview if it's currently open
        if (window.NsOverview && NsOverview.isOpen()) NsOverview.refresh();
    }

    function _clearVisuals() {
        document.querySelectorAll('.ns-selected').forEach(function (el) {
            el.classList.remove('ns-selected');
        });
    }

    // ── click handling (capture phase, delegated) ─────────────────────────────

    function _handleClick(e) {
        if (!_active) return;
        if (!_config || typeof _config.getItems !== 'function') return;

        var items;
        try { items = _config.getItems() || []; } catch (ex) { items = []; }

        // Find deepest matching item container
        var found = -1;
        for (var i = 0; i < items.length; i++) {
            var c = items[i].container;
            if (!c) continue;
            if (c === e.target || c.contains(e.target)) {
                if (found === -1 || (items[found].container && items[found].container.contains(c))) {
                    found = i;
                }
            }
        }
        if (found === -1) return;

        e.preventDefault();
        e.stopPropagation();

        var clickedUrl = NsCatalog.resolveItemUrl(items[found]);
        var catalog = NsCatalog.getAll();

        if (e.shiftKey && _lastCatalogIdx >= 0) {
            // Shift+click: range select in catalog order
            var clickedCatIdx = -1;
            for (var ci = 0; ci < catalog.length; ci++) {
                if (catalog[ci].url === clickedUrl) { clickedCatIdx = ci; break; }
            }

            if (clickedCatIdx === -1) {
                // Clicked item not yet in catalog — treat as plain toggle
                if (_selected.has(clickedUrl)) {
                    _selected.delete(clickedUrl);
                } else {
                    _selected.add(clickedUrl);
                }
                _lastCatalogIdx = -1;
            } else {
                var lo = Math.min(_lastCatalogIdx, clickedCatIdx);
                var hi = Math.min(Math.max(_lastCatalogIdx, clickedCatIdx), catalog.length - 1);
                for (var j = lo; j <= hi; j++) {
                    _selected.add(catalog[j].url);
                }
                // Anchor stays at _lastCatalogIdx; do not update on shift-click
            }
        } else {
            if (_selected.has(clickedUrl)) {
                _selected.delete(clickedUrl);
                _lastCatalogIdx = -1;
            } else {
                _selected.add(clickedUrl);
                // Record catalog index as new anchor
                var newIdx = -1;
                for (var ci2 = 0; ci2 < catalog.length; ci2++) {
                    if (catalog[ci2].url === clickedUrl) { newIdx = ci2; break; }
                }
                _lastCatalogIdx = newIdx;
            }
        }

        _save();
        _applyVisuals();
    }

    // ── submit ────────────────────────────────────────────────────────────────

    function _doSubmit() {
        var urls = Array.from(_selected);
        if (!urls.length) { alert('尚未選取任何項目。'); return; }

        // Determine message type: adapters declare submitMode: 'imageSelection'
        // when they need the backend to receive page URL context (e.g. bahamut).
        // All other sites use the generic downloadUrls path.
        var msg;
        if (_config && _config.submitMode === 'imageSelection') {
            msg = { type: 'downloadImageSelection', pageUrl: location.href, urls: urls };
        } else {
            msg = { type: 'downloadUrls', urls: urls };
        }

        chrome.runtime.sendMessage(msg, function (response) {
            if (chrome.runtime.lastError) {
                // Channel closed without reply — treat as failure (keep selection)
                console.warn('[NsSelector] submit message error:', chrome.runtime.lastError.message);
                return;
            }
            if (response && response.success) {
                _clearAfterSuccess(urls.length);
            }
            // On failure: selection is intentionally retained
        });
    }

    function _clearAfterSuccess(count) {
        _selected.clear();
        _lastCatalogIdx = -1;
        _save();
        NsCatalog.clear();
        NsCatalog.start(); // resume scanning fresh
        _applyVisuals();
        if (window.NsOverview && NsOverview.isOpen()) NsOverview.refresh();

        // Brief on-page notification
        var notice = document.createElement('div');
        notice.className = 'ns-submit-notice';
        notice.textContent = '已傳送 ' + count + ' 張圖片，選取已清除';
        document.body.appendChild(notice);
        setTimeout(function () { if (notice.parentNode) notice.remove(); }, 3000);
    }

    // ── toolbar ───────────────────────────────────────────────────────────────

    function _showToolbar() {
        if (_toolbar) return;
        _toolbar = document.createElement('div');
        _toolbar.id = 'ns-selection-toolbar';
        _toolbar.innerHTML =
            '<span class="ns-sel-count">已選 0 項</span>' +
            '<button class="ns-sel-btn" id="ns-sel-all">全選</button>' +
            '<button class="ns-sel-btn" id="ns-sel-invert">反選</button>' +
            '<button class="ns-sel-btn" id="ns-sel-clear">清除</button>' +
            '<button class="ns-sel-btn ns-sel-overview" id="ns-sel-overview">一覽 (Alt+G)</button>' +
            '<button class="ns-sel-btn ns-sel-download" id="ns-sel-download">下載所選</button>' +
            '<button class="ns-sel-btn ns-sel-exit" id="ns-sel-exit">離開 (Alt+S)</button>';
        document.body.appendChild(_toolbar);

        _toolbar.querySelector('#ns-sel-all').addEventListener('click', function () {
            NsCatalog.getAll().forEach(function (e) { _selected.add(e.url); });
            _save(); _applyVisuals();
        });

        _toolbar.querySelector('#ns-sel-invert').addEventListener('click', function () {
            NsCatalog.getAll().forEach(function (e) {
                if (_selected.has(e.url)) { _selected.delete(e.url); } else { _selected.add(e.url); }
            });
            _save(); _applyVisuals();
        });

        _toolbar.querySelector('#ns-sel-clear').addEventListener('click', function () {
            _selected.clear();
            _lastCatalogIdx = -1;
            _save(); _applyVisuals();
        });

        _toolbar.querySelector('#ns-sel-overview').addEventListener('click', function () {
            if (window.NsOverview) NsOverview.toggle();
        });

        _toolbar.querySelector('#ns-sel-download').addEventListener('click', _doSubmit);

        _toolbar.querySelector('#ns-sel-exit').addEventListener('click', function () {
            _leave();
        });
    }

    function _hideToolbar() {
        if (_toolbar) { _toolbar.remove(); _toolbar = null; }
    }

    // ── mode lifecycle ────────────────────────────────────────────────────────

    function _enter() {
        _active = true;
        _restore();         // re-load persisted selection
        NsCatalog.start();  // restore catalog + start observing
        _showToolbar();
        _applyVisuals();
        document.body.classList.add('ns-selection-mode');
    }

    function _leave() {
        _active = false;
        NsCatalog.stop();   // stop observing; catalog data is intentionally kept
        _hideToolbar();
        _clearVisuals();
        document.body.classList.remove('ns-selection-mode');
        // IMPORTANT: _selected and sessionStorage are NOT cleared on leave —
        // they survive Alt+S off/on per spec §D.
        if (window.NsOverview && NsOverview.isOpen()) NsOverview.close();
    }

    // ── keyboard shortcuts ────────────────────────────────────────────────────

    document.addEventListener('keydown', function (e) {
        if (e.altKey && (e.key === 's' || e.key === 'S')) {
            _active ? _leave() : _enter();
        }
        if (_active && e.altKey && (e.key === 'g' || e.key === 'G')) {
            if (window.NsOverview) NsOverview.toggle();
        }
    });

    // Capture-phase click interceptor for in-page item selection
    document.addEventListener('click', _handleClick, true);

    // ── public API ────────────────────────────────────────────────────────────

    window.NsSelector = {
        /**
         * Called by each site adapter.  Config is additive; new optional fields:
         *   resolveUrl(imgEl) → string   (site-specific URL rewrite, e.g. Bahamut)
         * Existing field getItems() continues to work unchanged.
         */
        register: function (config) {
            _config = config;
            NsCatalog.configure(config);
        },

        // ── bridge (called by catalog observer) ──────────────────────────────
        _onCatalogUpdate: function () {
            if (_active) _applyVisuals();
        },

        // ── selection API (used by NsOverview) ───────────────────────────────
        has: function (url) { return _selected.has(url); },
        add: function (url) { _selected.add(url); },
        remove: function (url) { _selected.delete(url); },
        toggle: function (url) {
            if (_selected.has(url)) { _selected.delete(url); } else { _selected.add(url); }
        },

        /**
         * Add all catalog entries in [lo, hi] (inclusive, catalog indices) to selection.
         */
        addRange: function (lo, hi) {
            var catalog = NsCatalog.getAll();
            var safeHi = Math.min(hi, catalog.length - 1);
            for (var i = lo; i <= safeHi; i++) {
                _selected.add(catalog[i].url);
            }
        },

        selectAll: function () {
            NsCatalog.getAll().forEach(function (e) { _selected.add(e.url); });
        },

        invertAll: function () {
            NsCatalog.getAll().forEach(function (e) {
                if (_selected.has(e.url)) { _selected.delete(e.url); } else { _selected.add(e.url); }
            });
        },

        clear: function () {
            _selected.clear();
            _lastCatalogIdx = -1;
        },

        getSelectedUrls: function () { return Array.from(_selected); },
        getSelectedCount: function () { return _selected.size; },

        save: function () { _save(); },
        applyVisuals: function () { _applyVisuals(); },
        doSubmit: function () { _doSubmit(); },

        isActive: function () { return _active; }
    };

})();
