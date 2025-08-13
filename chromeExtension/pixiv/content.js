
const getArtworks = () => {
    const links = Array.from(document.querySelectorAll('a[href*="/artworks/"]'));
    const artworkLinks = links.filter(link => link.href.includes('/artworks/') && link.querySelector('img'));
    const artworkContainers = artworkLinks.map(link => link.closest('div'));
    return artworkContainers.map((container, index) => ({
        container,
        link: artworkLinks[index].href,
    }));
};

const addCheckboxes = () => {
    const artworks = getArtworks();
    artworks.forEach(({ container, link }) => {
        if (container.querySelector('.artwork-checkbox')) {
            return;
        }
        const checkbox = document.createElement('input');
        checkbox.type = 'checkbox';
        checkbox.className = 'artwork-checkbox';
        checkbox.style.position = 'absolute';
        checkbox.style.top = '10px';
        checkbox.style.left = '10px';
        checkbox.style.zIndex = '1000';
        checkbox.dataset.link = link;
        container.style.position = 'relative';
        container.appendChild(checkbox);
    });
};

const addExportButton = () => {
    if (document.getElementById('export-button')) {
        return;
    }
    const exportButton = document.createElement('button');
    exportButton.id = 'export-button';
    exportButton.textContent = 'Export';
    exportButton.style.position = 'fixed';
    exportButton.style.bottom = '20px';
    exportButton.style.left = '20px';
    exportButton.style.zIndex = '1000';
    exportButton.style.padding = '10px 20px';
    exportButton.style.backgroundColor = '#007bff';
    exportButton.style.color = 'white';
    exportButton.style.border = 'none';
    exportButton.style.borderRadius = '5px';
    exportButton.style.cursor = 'pointer';
    document.body.appendChild(exportButton);

    exportButton.addEventListener('click', () => {
        const selectedLinks = [];
        document.querySelectorAll('.artwork-checkbox:checked').forEach(checkbox => {
            selectedLinks.push(checkbox.dataset.link);
        });
        const artworkIds = selectedLinks.map(link => link.split('/').pop());
        alert(JSON.stringify(artworkIds));
    });
};

const observer = new MutationObserver(() => {
    addCheckboxes();
    addExportButton();
});

observer.observe(document.body, {
    childList: true,
    subtree: true,
});

addCheckboxes();
addExportButton();
