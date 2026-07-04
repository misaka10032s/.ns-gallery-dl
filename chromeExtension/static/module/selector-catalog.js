/**
 * NS Media Hub — Catalog Layer (v2)
 * Maintains a persistent, ordered catalog of every image discovered while
 * selection mode is ON.  Virtual-scroll safe: the live DOM is only a projection
 * of the catalog; recycled DOM nodes never lose state.
 *
 * Loaded FIRST in every content_scripts entry (before selector-core.js).
 * Exposes: window.NsCatalog
 */
(function () {
    'use strict';

    var _catalog = [];      // [{ url, previewSrc, order }]
    var _urlSet = new Set(); // fast dedup
    var _config = null;
    var _active = false;
    var _observer = null;
    var _scanTimer = null;
    var _storageKey = 'ns-cat-v2:' + location.href;

    // ── URL resolution chain ──────────────────────────────────────────────────
    // Only applies to image-URL sites where container IS an <img> element.
    // Page-URL sites (pixiv, nhentai, etc.) pass url through unchanged.

    function _resolveItemUrl(item) {
        var container = item.container;
        if (!container) return item.url || '';

        if (container.tagName !== 'IMG') {
            // Page-URL adapter: url is already the canonical backend key
            return item.url || '';
        }

        // 1. Ancestor <a href> pointing at an image extension (original URL)
        var el = container.parentElement;
        while (el) {
            if (el.tagName === 'A') {
                var href = el.getAttribute('href') || '';
                // Match extension optionally followed by query string / fragment
                if (/\.(jpg|jpeg|png|gif|webp|avif)(\?[^#]*)?(\#.*)?$/i.test(href)) {
                    return href;
                }
                break; // stop at first ancestor anchor regardless
            }
            el = el.parentElement;
        }

        // 2. Site-specific rewrite (adapter may provide resolveUrl(imgEl) → string)
        if (_config && typeof _config.resolveUrl === 'function') {
            var rewritten = _config.resolveUrl(container);
            if (rewritten) return rewritten;
        }

        // 3. Fallback: data-src (lazy) or src
        return container.getAttribute('data-src') || container.getAttribute('src') || item.url || '';
    }

    function _extractPreview(item) {
        var container = item.container;
        if (!container) return item.url || '';
        if (container.tagName === 'IMG') {
            // Current loaded src is already a usable preview thumbnail
            return container.src || container.getAttribute('data-src') || item.url || '';
        }
        // For page-URL containers: look for the first child img
        var img = container.querySelector('img');
        if (img) return img.src || img.getAttribute('data-src') || item.url || '';
        return item.url || '';
    }

    // ── scan ──────────────────────────────────────────────────────────────────

    function _scan() {
        if (!_config || typeof _config.getItems !== 'function') return false;
        var items;
        try { items = _config.getItems() || []; } catch (e) { return false; }

        var added = false;
        for (var i = 0; i < items.length; i++) {
            var item = items[i];
            if (!item) continue;
            var url = _resolveItemUrl(item);
            if (!url || _urlSet.has(url)) continue;
            _urlSet.add(url);
            _catalog.push({
                url: url,
                previewSrc: _extractPreview(item),
                order: _catalog.length
            });
            added = true;
        }
        if (added) _save();
        return added;
    }

    // ── persistence ───────────────────────────────────────────────────────────

    function _save() {
        try {
            sessionStorage.setItem(_storageKey, JSON.stringify(_catalog));
        } catch (e) {}
    }

    function _restore() {
        try {
            var raw = sessionStorage.getItem(_storageKey);
            if (!raw) return;
            var arr = JSON.parse(raw);
            if (!Array.isArray(arr)) return;
            _catalog = arr;
            arr.forEach(function (e) { if (e && e.url) _urlSet.add(e.url); });
        } catch (e) {}
    }

    // ── mutation observer ─────────────────────────────────────────────────────

    function _startObserver() {
        if (_observer) return;
        _observer = new MutationObserver(function () {
            if (_scanTimer) clearTimeout(_scanTimer);
            _scanTimer = setTimeout(function () {
                _scanTimer = null;
                var added = _scan();
                if (added && window.NsSelector) {
                    NsSelector._onCatalogUpdate();
                }
            }, 150);
        });
        _observer.observe(document.body, { childList: true, subtree: true });
    }

    function _stopObserver() {
        if (_scanTimer) { clearTimeout(_scanTimer); _scanTimer = null; }
        if (_observer) { _observer.disconnect(); _observer = null; }
    }

    // ── public API ────────────────────────────────────────────────────────────

    window.NsCatalog = {
        /** Called by NsSelector.register to share the adapter config. */
        configure: function (config) {
            _config = config;
        },

        /** Start scanning + observing (call on mode enter). */
        start: function () {
            if (_active) return;
            _active = true;
            _restore();
            _scan();
            _startObserver();
        },

        /** Stop observing but keep catalog data (call on mode leave). */
        stop: function () {
            if (!_active) return;
            _active = false;
            _stopObserver();
        },

        /** Clear catalog completely (call after successful submit). */
        clear: function () {
            _catalog = [];
            _urlSet = new Set();
            try { sessionStorage.removeItem(_storageKey); } catch (e) {}
        },

        /** Return a shallow copy of the catalog array. */
        getAll: function () {
            return _catalog.slice();
        },

        getCount: function () {
            return _catalog.length;
        },

        isActive: function () {
            return _active;
        },

        /** Trigger an immediate scan (e.g. after a forced DOM update). */
        rescan: function () {
            _scan();
        },

        /**
         * Apply the v2 URL resolution chain to a raw adapter item.
         * Used by selector-core.js to keep resolution logic consistent.
         * @param {{ container: Element, url: string }} item
         * @returns {string}
         */
        resolveItemUrl: function (item) {
            return _resolveItemUrl(item);
        },

        /**
         * Extract the best available preview thumbnail src for an adapter item.
         * @param {{ container: Element, url: string }} item
         * @returns {string}
         */
        extractPreview: function (item) {
            return _extractPreview(item);
        }
    };

})();
