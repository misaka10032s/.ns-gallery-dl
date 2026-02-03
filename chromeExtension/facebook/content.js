
const getGalleries = () => {
    // Find all 'a' tags that contain an 'img' with the specific src pattern
    const links = Array.from(document.querySelectorAll('a'));
    
    const validLinks = links.filter(link => {
        const img = link.querySelector('img');
        if (!img) return false;
        
        // User example: https://scontent.ftpe14-1.fna.fbcdn.net/v/...
        return img.src.includes('scontent') && img.src.includes('fbcdn.net');
    });

    return validLinks.map(link => {
        return {
            container: link,
            link: link.href
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
        
        // Stop propagation so clicking the checkbox doesn't open the image
        checkbox.addEventListener('click', (e) => {
            e.stopPropagation();
        });

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
            alert('No images selected.');
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
