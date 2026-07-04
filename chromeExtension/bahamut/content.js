// Bahamut forum.gamer.com.tw — selection-engine site adapter
// Registers item discovery with the shared NsSelector engine (selector-catalog/core/overview).
// Works on both C.php thread pages (all reply floors) and Co.php single-post pages.
// Handles lazyloaded images via data-src attribute.
NsSelector.register({
    /**
     * v2 resolver override: strip CDN resize params from truth.bahamut.com.tw URLs
     * so the catalog stores the original full-resolution image URL.
     * e.g. https://truth.bahamut.com.tw/s01/…/file.jpg?w=300&h=200&fit=cover
     *   →  https://truth.bahamut.com.tw/s01/…/file.jpg
     */
    resolveUrl: function (img) {
        var src = img.getAttribute('data-src') || img.getAttribute('src') || '';
        if (src.indexOf('truth.bahamut.com.tw') !== -1 && src.indexOf('?') !== -1) {
            return src.split('?')[0];
        }
        return src || '';
    },
    getItems: function () {
        var imgs = Array.from(document.querySelectorAll('div.c-article__content img'));
        return imgs.map(function (img) {
            var src = img.getAttribute('data-src') || img.getAttribute('src') || '';
            return { container: img, url: src };
        }).filter(function (item) {
            // Must be an absolute http(s) URL and not a forum icon/emoticon
            return item.url &&
                   item.url.indexOf('http') === 0 &&
                   item.url.indexOf('i2.bahamut.com.tw/forum/icons') === -1;
        });
    },
    submitMode: 'imageSelection'
});
