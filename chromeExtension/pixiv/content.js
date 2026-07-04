// Pixiv — selection-engine site adapter
// Registers item discovery with the shared NsSelector engine (static/module/selector.js).
NsSelector.register({
    getItems: function () {
        var links = Array.from(document.querySelectorAll('a[href*="/artworks/"]'));
        var artworkLinks = links.filter(function (link) {
            return link.href.includes('/artworks/') && link.querySelector('img');
        });
        return artworkLinks.map(function (link) {
            return {
                container: link.closest('div') || link,
                url: link.href
            };
        });
    }
});
