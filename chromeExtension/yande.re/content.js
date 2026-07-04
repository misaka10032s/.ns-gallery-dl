// yande.re — selection-engine site adapter
// Registers item discovery with the shared NsSelector engine (static/module/selector.js).
NsSelector.register({
    getItems: function () {
        var links = Array.from(document.querySelectorAll('a.thumb[href*="/post/show/"]'));
        return links.map(function (link) {
            return {
                container: link.parentElement || link,
                url: link.href
            };
        });
    }
});
