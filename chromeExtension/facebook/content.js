// Facebook — selection-engine site adapter
// Registers item discovery with the shared NsSelector engine (static/module/selector.js).
NsSelector.register({
    getItems: function () {
        var links = Array.from(document.querySelectorAll('a'));
        var validLinks = links.filter(function (link) {
            var img = link.querySelector('img');
            // Match fbcdn.net scontent images (user-uploaded photos)
            return img && img.src.includes('scontent') && img.src.includes('fbcdn.net');
        });
        return validLinks.map(function (link) {
            return {
                container: link,
                url: link.href
            };
        });
    }
});
