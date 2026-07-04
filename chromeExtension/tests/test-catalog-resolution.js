/**
 * Node.js test: catalog URL resolution chain and Bahamut URL rewrite.
 * Run with: node chromeExtension/tests/test-catalog-resolution.js
 *
 * Tests the pure resolution logic in isolation by extracting and re-running
 * the same logic with minimal DOM stubs.
 */
'use strict';

var assert = require('assert');

// ── Minimal DOM stub helpers ─────────────────────────────────────────────────

function makeImg(attrs) {
    var stored = Object.assign({}, attrs);
    var img = {
        tagName: 'IMG',
        parentElement: null,
        getAttribute: function (name) {
            return stored[name] !== undefined ? stored[name] : null;
        }
    };
    // simulate .src property
    img.src = stored.src || '';
    return img;
}

function makeAnchor(href, child) {
    var a = {
        tagName: 'A',
        parentElement: null,
        getAttribute: function (name) { return name === 'href' ? href : null; }
    };
    if (child) child.parentElement = a;
    return a;
}

function makeDiv(child) {
    var d = {
        tagName: 'DIV',
        parentElement: null,
        getAttribute: function () { return null; },
        querySelector: function (sel) {
            if (sel === 'img' && child && child.tagName === 'IMG') return child;
            return null;
        }
    };
    if (child) child.parentElement = d;
    return d;
}

// ── Extracted resolution logic (mirrors selector-catalog.js) ─────────────────

function resolveItemUrl(item, config) {
    var container = item.container;
    if (!container) return item.url || '';

    if (container.tagName !== 'IMG') {
        return item.url || '';
    }

    // 1. Ancestor <a href> pointing at image extension
    var el = container.parentElement;
    while (el) {
        if (el.tagName === 'A') {
            var href = el.getAttribute('href') || '';
            if (/\.(jpg|jpeg|png|gif|webp|avif)(\?[^#]*)?(\#.*)?$/i.test(href)) {
                return href;
            }
            break;
        }
        el = el.parentElement;
    }

    // 2. Site-specific rewrite
    if (config && typeof config.resolveUrl === 'function') {
        var rewritten = config.resolveUrl(container);
        if (rewritten) return rewritten;
    }

    // 3. Fallback
    return container.getAttribute('data-src') || container.getAttribute('src') || item.url || '';
}

function extractPreview(item) {
    var container = item.container;
    if (!container) return item.url || '';
    if (container.tagName === 'IMG') {
        return container.src || container.getAttribute('data-src') || item.url || '';
    }
    var img = container.querySelector('img');
    if (img) return img.src || img.getAttribute('data-src') || item.url || '';
    return item.url || '';
}

// Bahamut resolveUrl (mirrors bahamut/content.js)
var bahamutConfig = {
    resolveUrl: function (img) {
        var src = img.getAttribute('data-src') || img.getAttribute('src') || '';
        if (src.indexOf('truth.bahamut.com.tw') !== -1 && src.indexOf('?') !== -1) {
            return src.split('?')[0];
        }
        return src || '';
    }
};

// ── Tests ────────────────────────────────────────────────────────────────────

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

console.log('\nResolution chain tests:');

// ── §B step 1: ancestor anchor with image extension href ─────────────────────

test('step1: anchor href with .jpg → use href (no query)', function () {
    var img = makeImg({ src: 'https://cdn.example.com/thumb.jpg' });
    var a = makeAnchor('https://cdn.example.com/full.jpg', img);
    var result = resolveItemUrl({ container: img, url: '' }, null);
    assert.strictEqual(result, 'https://cdn.example.com/full.jpg');
});

test('step1: anchor href with query string after .png → accepted', function () {
    var img = makeImg({ src: 'https://cdn.example.com/t.png?s=small' });
    var a = makeAnchor('https://cdn.example.com/full.png?token=xyz', img);
    var result = resolveItemUrl({ container: img, url: '' }, null);
    assert.strictEqual(result, 'https://cdn.example.com/full.png?token=xyz');
});

test('step1: anchor href NOT an image extension → skip, fall to step3', function () {
    var img = makeImg({ src: 'https://cdn.example.com/thumb.jpg', 'data-src': '' });
    var a = makeAnchor('https://www.example.com/page/123', img);
    var result = resolveItemUrl({ container: img, url: '' }, null);
    // falls through to step3 (src)
    assert.strictEqual(result, 'https://cdn.example.com/thumb.jpg');
});

test('step1: ancestor anchor is grandparent → still found', function () {
    var img = makeImg({ src: 'https://cdn.example.com/thumb.jpg' });
    var div = makeDiv(img);
    div.parentElement = null;
    img.parentElement = div;
    var a = makeAnchor('https://cdn.example.com/orig.gif', div);
    a.parentElement = null;
    div.parentElement = a;
    var result = resolveItemUrl({ container: img, url: '' }, null);
    assert.strictEqual(result, 'https://cdn.example.com/orig.gif');
});

// ── §B step 2: Bahamut URL rewrite ───────────────────────────────────────────

test('bahamut: strip resize query params from truth.bahamut.com.tw URL', function () {
    var src = 'https://truth.bahamut.com.tw/s01/202407/abcdef.jpg?w=300&h=200&fit=cover';
    var img = makeImg({ 'data-src': src });
    // No ancestor anchor
    var result = resolveItemUrl({ container: img, url: src }, bahamutConfig);
    assert.strictEqual(result, 'https://truth.bahamut.com.tw/s01/202407/abcdef.jpg');
});

test('bahamut: URL without query passes through unchanged', function () {
    var src = 'https://truth.bahamut.com.tw/s01/202407/abcdef.jpg';
    var img = makeImg({ src: src });
    var result = resolveItemUrl({ container: img, url: src }, bahamutConfig);
    assert.strictEqual(result, src);
});

test('bahamut: non-truth.bahamut URL with query is NOT stripped', function () {
    var src = 'https://i2.bahamut.com.tw/forum/attach/67890.png?t=1234567890';
    var img = makeImg({ src: src });
    var result = resolveItemUrl({ container: img, url: src }, bahamutConfig);
    // bahamutConfig.resolveUrl returns src unchanged; step3 fallback picks up src
    assert.strictEqual(result, src);
});

test('bahamut: step1 anchor takes priority over step2 rewrite', function () {
    var thumb = 'https://truth.bahamut.com.tw/s01/2024/file.jpg?w=200';
    var full  = 'https://truth.bahamut.com.tw/s01/2024/file.jpg';
    // Assume the anchor's href already has the full URL (no query)
    var img = makeImg({ 'data-src': thumb });
    var a = makeAnchor(full + '', img); // full is already stripped
    var result = resolveItemUrl({ container: img, url: thumb }, bahamutConfig);
    assert.strictEqual(result, full); // step1 wins
});

// ── Page-URL adapters: pass url through unchanged ────────────────────────────

test('page-URL adapter: container is DIV, url is page link → unchanged', function () {
    var img = makeImg({ src: 'https://i.pximg.net/thumb.jpg' });
    var d = makeDiv(img);
    var item = { container: d, url: 'https://www.pixiv.net/artworks/12345' };
    var result = resolveItemUrl(item, null);
    assert.strictEqual(result, 'https://www.pixiv.net/artworks/12345');
});

// ── Preview extraction ────────────────────────────────────────────────────────

test('preview: IMG container → src', function () {
    var img = makeImg({ src: 'https://cdn.example.com/thumb.jpg' });
    img.src = 'https://cdn.example.com/thumb.jpg';
    var result = extractPreview({ container: img, url: '' });
    assert.strictEqual(result, 'https://cdn.example.com/thumb.jpg');
});

test('preview: IMG with only data-src (not loaded) → data-src', function () {
    var img = makeImg({ 'data-src': 'https://cdn.example.com/lazy.jpg' });
    img.src = ''; // not yet loaded
    var result = extractPreview({ container: img, url: 'https://cdn.example.com/lazy.jpg' });
    // src is empty string (falsy), falls to data-src
    assert.strictEqual(result, 'https://cdn.example.com/lazy.jpg');
});

test('preview: DIV container → child img src', function () {
    var img = makeImg({ src: 'https://i.pximg.net/thumb.jpg' });
    img.src = 'https://i.pximg.net/thumb.jpg';
    var d = makeDiv(img);
    var result = extractPreview({ container: d, url: 'https://www.pixiv.net/artworks/99' });
    assert.strictEqual(result, 'https://i.pximg.net/thumb.jpg');
});

// ── Summary ───────────────────────────────────────────────────────────────────

console.log('\n' + pass + ' passed, ' + fail + ' failed\n');
if (fail > 0) process.exit(1);
