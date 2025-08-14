
const getGalleries = () => {
    const links = Array.from(document.querySelectorAll('a[href*="/photos-index-aid-"]'));
    const galleryLinks = links.filter(link => link.href.match(/photos-index-aid-\d+\.html/));
    
    return galleryLinks.map(link => {
        // On wnacg, the link is inside a 'li' which is a good container.
        const container = link.closest('li');
        return {
            container: container || link, // Fallback to the link itself
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
            // For wnacg, we need the "slide" URL, not the "view" URL
            const slideUrls = selectedLinks.map(url => url.replace('index', 'slide'));
            chrome.runtime.sendMessage({ type: 'downloadUrls', urls: slideUrls });
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
