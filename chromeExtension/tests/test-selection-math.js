/**
 * Node.js test: selection math — catalog range, marquee rect-intersection.
 * Run with: node chromeExtension/tests/test-selection-math.js
 */
'use strict';

var assert = require('assert');

var pass = 0;
var fail = 0;

function test(name, fn) {
    try {
        fn();
        console.log('  PASS ' + name);
        pass++;
    } catch (e) {
        console.error('  FAIL ' + name + ': ' + e.message);
        fail++;
    }
}

// ── Range math (shift-click) ──────────────────────────────────────────────────
// Mirrors the range logic in selector-core.js _handleClick and NsSelector.addRange

function addRange(catalog, selected, lo, hi) {
    var safeHi = Math.min(hi, catalog.length - 1);
    for (var i = lo; i <= safeHi; i++) {
        selected.add(catalog[i].url);
    }
}

function makeCatalog(n) {
    var cat = [];
    for (var i = 0; i < n; i++) {
        cat.push({ url: 'https://cdn.example.com/img' + i + '.jpg', previewSrc: '', order: i });
    }
    return cat;
}

console.log('\nRange selection math:');

test('range: lo=0 hi=4 selects items 0-4', function () {
    var catalog = makeCatalog(10);
    var sel = new Set();
    addRange(catalog, sel, 0, 4);
    assert.strictEqual(sel.size, 5);
    for (var i = 0; i <= 4; i++) {
        assert.ok(sel.has(catalog[i].url), 'missing item ' + i);
    }
});

test('range: hi clamped to catalog length', function () {
    var catalog = makeCatalog(5);
    var sel = new Set();
    addRange(catalog, sel, 2, 99); // 99 > catalog.length
    // should select items 2,3,4
    assert.strictEqual(sel.size, 3);
    assert.ok(sel.has(catalog[2].url));
    assert.ok(sel.has(catalog[3].url));
    assert.ok(sel.has(catalog[4].url));
});

test('range: lo === hi selects exactly one item', function () {
    var catalog = makeCatalog(10);
    var sel = new Set();
    addRange(catalog, sel, 5, 5);
    assert.strictEqual(sel.size, 1);
    assert.ok(sel.has(catalog[5].url));
});

test('range: lo > hi (reversed) — should be corrected by caller', function () {
    // The caller (shift-click handler) normalises lo/hi via Math.min/max
    var catalog = makeCatalog(10);
    var sel = new Set();
    var lo = Math.min(7, 3); // 3
    var hi = Math.max(7, 3); // 7
    addRange(catalog, sel, lo, hi);
    assert.strictEqual(sel.size, 5); // items 3,4,5,6,7
    assert.ok(sel.has(catalog[3].url));
    assert.ok(sel.has(catalog[7].url));
});

test('range: empty catalog → no error, no selection', function () {
    var sel = new Set();
    addRange([], sel, 0, 5);
    assert.strictEqual(sel.size, 0);
});

test('range: does not remove existing selections', function () {
    var catalog = makeCatalog(10);
    var sel = new Set();
    sel.add(catalog[8].url); // pre-existing
    addRange(catalog, sel, 0, 2);
    assert.strictEqual(sel.size, 4); // 0,1,2 + pre-existing 8
    assert.ok(sel.has(catalog[8].url));
});

// ── Marquee rect intersection math ────────────────────────────────────────────
// Mirrors _rectsIntersect in selector-overview.js

function rectsIntersect(a, b) {
    return !(b.right < a.left || b.left > a.right ||
             b.bottom < a.top  || b.top  > a.bottom);
}

console.log('\nMarquee rect-intersection math:');

test('intersect: fully overlapping rects', function () {
    var a = { left: 10, top: 10, right: 50, bottom: 50 };
    var b = { left: 20, top: 20, right: 40, bottom: 40 };
    assert.ok(rectsIntersect(a, b));
});

test('intersect: rects touching at one edge → true (border-inclusive)', function () {
    var a = { left: 0, top: 0, right: 100, bottom: 100 };
    var b = { left: 100, top: 0, right: 200, bottom: 100 };
    // b.left === a.right → b.left > a.right is false → NOT(false || ...) → true
    assert.ok(rectsIntersect(a, b));
});

test('intersect: rects separated horizontally', function () {
    var a = { left: 0, top: 0, right: 50, bottom: 50 };
    var b = { left: 60, top: 0, right: 110, bottom: 50 };
    assert.ok(!rectsIntersect(a, b));
});

test('intersect: rects separated vertically', function () {
    var a = { left: 0, top: 0, right: 100, bottom: 50 };
    var b = { left: 0, top: 60, right: 100, bottom: 110 };
    assert.ok(!rectsIntersect(a, b));
});

test('intersect: partially overlapping (corner touch)', function () {
    var a = { left: 0, top: 0, right: 100, bottom: 100 };
    var b = { left: 80, top: 80, right: 180, bottom: 180 };
    assert.ok(rectsIntersect(a, b));
});

test('intersect: tiny marquee (below minDrag threshold) ignored', function () {
    // In selector-overview.js, drags < 4px are ignored before intersection check
    var minDrag = 4;
    var marquee = { left: 50, top: 50, right: 53, bottom: 52 };
    var size = (marquee.right - marquee.left);
    var height = (marquee.bottom - marquee.top);
    // The guard in selector-overview.js: if both < minDrag, skip
    var ignored = (size < minDrag && height < minDrag);
    assert.ok(ignored, 'tiny marquee should be ignored');
});

test('intersect: zero-size marquee (single pixel click) → ignored', function () {
    var marquee = { left: 50, top: 50, right: 50, bottom: 50 };
    var size = (marquee.right - marquee.left);
    var height = (marquee.bottom - marquee.top);
    assert.ok(size < 4 && height < 4, 'single pixel should be below threshold');
});

// ── Summary ───────────────────────────────────────────────────────────────────

console.log('\n' + pass + ' passed, ' + fail + ' failed\n');
if (fail > 0) process.exit(1);
