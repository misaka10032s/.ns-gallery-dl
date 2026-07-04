/**
 * NS Media Hub — Shared Selection Engine
 * Plain IIFE (no ES-module syntax) so it works as a content_scripts plain script.
 * Loaded before each site's content.js. Sites call NsSelector.register(config).
 */
(function () {
    'use strict';

    // ── internal state ──────────────────────────────────────────────────────────
    var _config = null;
    var _active = false;
    var _selected = new Set();
    var _lastIndex = -1;
    var _toolbar = null;
    var _observer = null;
    var _observerTimer = null;
    var _storageKey = 'ns-sel:' + location.href;

    // ── helpers ─────────────────────────────────────────────────────────────────

    function _getItems() {
        if (!_config) return [];
        try { return _config.getItems() || []; } catch (e) { return []; }
    }

    function _save() {
        try {
            sessionStorage.setItem(_storageKey, JSON.stringify(Array.from(_selected)));
        } catch (e) {}
    }

    function _restore() {
        try {
            var raw = sessionStorage.getItem(_storageKey);
            if (raw) { _selected = new Set(JSON.parse(raw)); }
        } catch (e) {}
    }

    function _updateCount() {
        if (!_toolbar) return;
        var el = _toolbar.querySelector('.ns-sel-count');
        if (el) el.textContent = '已選 ' + _selected.size + ' 項';
    }

    function _applyVisuals() {
        var items = _getItems();
        items.forEach(function (item) {
            if (!item.container) return;
            // ensure container is positioned so ::after overlay works
            if (getComputedStyle(item.container).position === 'static') {
                item.container.style.position = 'relative';
            }
            if (_selected.has(item.url)) {
                item.container.classList.add('ns-selected');
            } else {
                item.container.classList.remove('ns-selected');
            }
        });
        _updateCount();
    }

    function _clearVisuals() {
        document.querySelectorAll('.ns-selected').forEach(function (el) {
            el.classList.remove('ns-selected');
            // restore position only if we set it (leave site-set positions intact)
        });
    }

    // ── click handling (delegated, capture phase) ────────────────────────────────

    function _handleClick(e) {
        if (!_active) return;

        var items = _getItems();
        var found = -1;
        for (var i = 0; i < items.length; i++) {
            var c = items[i].container;
            if (c && (c === e.target || c.contains(e.target))) {
                // prefer the most specific match (deepest container that still matches)
                if (found === -1 || (items[found].container.contains(c))) {
                    found = i;
                }
            }
        }
        if (found === -1) return;  // click not on any registered item

        e.preventDefault();
        e.stopPropagation();

        if (e.shiftKey && _lastIndex >= 0) {
            if (_lastIndex >= items.length) {
                // anchor item no longer exists (DOM mutation shrunk list) — treat as plain toggle
                var url = items[found].url;
                if (_selected.has(url)) { _selected.delete(url); } else { _selected.add(url); }
                _lastIndex = found;
            } else {
                var lo = Math.min(_lastIndex, found);
                var hi = Math.min(Math.max(_lastIndex, found), items.length - 1);
                for (var j = lo; j <= hi; j++) {
                    _selected.add(items[j].url);
                }
                // lastIndex stays as the anchor; do not update it on shift-click
            }
        } else {
            var url = items[found].url;
            if (_selected.has(url)) {
                _selected.delete(url);
            } else {
                _selected.add(url);
            }
            _lastIndex = found;
        }

        _save();
        _applyVisuals();
    }

    // ── toolbar ──────────────────────────────────────────────────────────────────

    function _showToolbar() {
        if (_toolbar) return;
        _toolbar = document.createElement('div');
        _toolbar.id = 'ns-selection-toolbar';
        _toolbar.innerHTML =
            '<span class="ns-sel-count">已選 0 項</span>' +
            '<button class="ns-sel-btn" id="ns-sel-all">全選</button>' +
            '<button class="ns-sel-btn" id="ns-sel-invert">反選</button>' +
            '<button class="ns-sel-btn" id="ns-sel-clear">清除</button>' +
            '<button class="ns-sel-btn ns-sel-download" id="ns-sel-download">下載所選</button>' +
            '<button class="ns-sel-btn ns-sel-exit" id="ns-sel-exit">離開選取模式</button>';
        document.body.appendChild(_toolbar);

        _toolbar.querySelector('#ns-sel-all').addEventListener('click', function () {
            _getItems().forEach(function (item) { _selected.add(item.url); });
            _save();
            _applyVisuals();
        });

        _toolbar.querySelector('#ns-sel-invert').addEventListener('click', function () {
            _getItems().forEach(function (item) {
                if (_selected.has(item.url)) {
                    _selected.delete(item.url);
                } else {
                    _selected.add(item.url);
                }
            });
            _save();
            _applyVisuals();
        });

        _toolbar.querySelector('#ns-sel-clear').addEventListener('click', function () {
            _selected.clear();
            _save();
            _applyVisuals();
        });

        _toolbar.querySelector('#ns-sel-download').addEventListener('click', function () {
            var urls = Array.from(_selected);
            if (!urls.length) {
                alert('尚未選取任何項目。');
                return;
            }
            if (_config && typeof _config.submit === 'function') {
                _config.submit(urls);
            } else {
                chrome.runtime.sendMessage({ type: 'downloadUrls', urls: urls });
            }
        });

        _toolbar.querySelector('#ns-sel-exit').addEventListener('click', function () {
            _leave();
        });
    }

    function _hideToolbar() {
        if (_toolbar) {
            _toolbar.remove();
            _toolbar = null;
        }
    }

    // ── mutation observer (active only while mode is ON) ─────────────────────────

    function _startObserver() {
        if (_observer) return;
        _observer = new MutationObserver(function () {
            // debounce: coalesce rapid DOM mutations into one visual pass
            if (_observerTimer) clearTimeout(_observerTimer);
            _observerTimer = setTimeout(function () {
                _observerTimer = null;
                _applyVisuals();
            }, 80);
        });
        _observer.observe(document.body, { childList: true, subtree: true });
    }

    function _stopObserver() {
        if (_observerTimer) { clearTimeout(_observerTimer); _observerTimer = null; }
        if (_observer) { _observer.disconnect(); _observer = null; }
    }

    // ── mode lifecycle ───────────────────────────────────────────────────────────

    function _enter() {
        _active = true;
        _restore();
        _showToolbar();
        _applyVisuals();
        _startObserver();
        document.body.classList.add('ns-selection-mode');
    }

    function _leave() {
        _active = false;
        _stopObserver();
        _hideToolbar();
        _clearVisuals();
        _selected.clear();
        _lastIndex = -1;
        document.body.classList.remove('ns-selection-mode');
        try { sessionStorage.removeItem(_storageKey); } catch (e) {}
    }

    // ── keyboard shortcut ────────────────────────────────────────────────────────

    document.addEventListener('keydown', function (e) {
        if (e.altKey && (e.key === 's' || e.key === 'S')) {
            _active ? _leave() : _enter();
        }
    });

    // ── delegated capture-phase click interceptor ────────────────────────────────

    document.addEventListener('click', _handleClick, true);

    // ── public API ───────────────────────────────────────────────────────────────

    window.NsSelector = {
        /**
         * Called by each site's content.js to register item discovery.
         * @param {{ getItems: () => Array<{ container: Element, url: string }> }} config
         */
        register: function (config) {
            _config = config;
        }
    };

})();
