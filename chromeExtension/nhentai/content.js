
const getGalleries = () => {
    const links = Array.from(document.querySelectorAll('a[href*="/g/"]'));
    const galleryLinks = links.filter(link => link.href.match(/\/g\/\d+\//) && link.querySelector('img'));
    
    return galleryLinks.map(link => {
        // The container is the 'div' with class 'gallery' that is an ancestor of the link.
        const container = link.closest('div.gallery');
        return {
            container: container || link, // Fallback to the link itself if no container is found
            link: link.href,
        };
    });
};

const addCheckboxes = () => {
    const galleries = getGalleries();
    galleries.forEach(({ container, link }) => {
        if (container.querySelector('.artwork-checkbox')) {
            return;
        }
        const checkbox = document.createElement('input');
        checkbox.type = 'checkbox';
        checkbox.className = 'artwork-checkbox';
        checkbox.dataset.link = link;
        
        // Ensure the container can have absolutely positioned children
        if (getComputedStyle(container).position === 'static') {
            container.style.position = 'relative';
        }
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
            alert('No galleries selected.');
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

// Initial run
addCheckboxes();
addExportButton();
