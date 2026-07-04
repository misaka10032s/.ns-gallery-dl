// nhentai — selection-engine site adapter
// Registers item discovery with the shared NsSelector engine (static/module/selector.js).
NsSelector.register({
    getItems: function () {
        var links = Array.from(document.querySelectorAll('a[href*="/g/"]'));
        var galleryLinks = links.filter(function (link) {
            return link.href.match(/\/g\/\d+\/$/) && link.querySelector('img');
        });
        return galleryLinks.map(function (link) {
            return {
                container: link.closest('div.gallery') || link,
                url: link.href
            };
        });
    }
});
