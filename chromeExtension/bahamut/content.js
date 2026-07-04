// Bahamut forum.gamer.com.tw — selection-engine site adapter
// Registers item discovery with the shared NsSelector engine (static/module/selector.js).
// Works on both C.php thread pages (all reply floors) and Co.php single-post pages.
// Handles lazyloaded images via data-src attribute.
NsSelector.register({
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
    submit: function (urls) {
        chrome.runtime.sendMessage({
            type: 'downloadImageSelection',
            pageUrl: location.href,
            urls: urls
        });
    }
});
