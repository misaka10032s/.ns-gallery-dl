// wnacg — selection-engine site adapter
// Registers item discovery with the shared NsSelector engine (static/module/selector.js).
// Note: urls are transformed from photos-index-aid-* to photos-slide-aid-* here so the
// engine sends the correct "slide" URL to the downloader (preserves existing behaviour).
NsSelector.register({
    getItems: function () {
        var links = Array.from(document.querySelectorAll('a[href*="/photos-index-aid-"]'));
        var galleryLinks = links.filter(function (link) {
            return link.href.match(/photos-index-aid-\d+\.html/);
        });
        return galleryLinks.map(function (link) {
            return {
                container: link.closest('li') || link,
                url: link.href.replace('index', 'slide')
            };
        });
    }
});
