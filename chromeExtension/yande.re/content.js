
const getArtworks = () => {
    const links = Array.from(document.querySelectorAll('a.thumb[href*="/post/show/"]'));
    
    const artworkContainers = links.map(link => link.parentElement);
    return artworkContainers.map((container, index) => ({
        container,
        link: links[index].href,
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
        checkbox.dataset.link = link;
        container.style.position = 'relative';
        container.appendChild(checkbox);
    });
};

const addExportButton = () => {
    if (document.getElementById('ns-export-button')) {
        return;
    }
    const exportButton = document.createElement('button');
    exportButton.id = 'ns-export-button';
    exportButton.textContent = 'Export Selected';
    document.body.appendChild(exportButton);

    exportButton.addEventListener('click', () => {
        const selectedLinks = [];
        document.querySelectorAll('.artwork-checkbox:checked').forEach(checkbox => {
            selectedLinks.push(checkbox.dataset.link);
        });

        if (selectedLinks.length > 0) {
            chrome.runtime.sendMessage({ type: 'downloadUrls', urls: selectedLinks });
        } else {
            alert('No artworks selected.');
        }
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
