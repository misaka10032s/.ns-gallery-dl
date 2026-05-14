const reloadBtn       = document.getElementById('reload-btn');
const autoRefreshCb   = document.getElementById('auto-refresh-cb');
const countBadge      = document.getElementById('count-badge');
const pendingCountEl  = document.getElementById('pending-count');
const currentSection  = document.getElementById('current-section');
const currentItemEl   = document.getElementById('current-item');
const pendingList     = document.getElementById('pending-list');

let autoRefreshTimer = null;

function esc(str) {
    return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

function fetchQueue() {
    reloadBtn.disabled = true;
    reloadBtn.textContent = '⟳ Loading...';

    fetch('/api/queue')
        .then(r => r.json())
        .then(render)
        .catch(err => {
            pendingList.innerHTML = '<div class="empty">Failed to load queue. Is the server running?</div>';
            console.error(err);
        })
        .finally(() => {
            reloadBtn.disabled = false;
            reloadBtn.textContent = '⟳ Reload';
        });
}

function render(data) {
    countBadge.textContent = data.total;

    // Current downloading
    if (data.current) {
        currentSection.style.display = '';
        currentItemEl.innerHTML = `<a href="${esc(data.current)}" target="_blank" rel="noopener">${esc(data.current)}</a>`;
    } else {
        currentSection.style.display = 'none';
    }

    // Pending list
    pendingCountEl.textContent = data.pending.length ? `(${data.pending.length})` : '';
    if (data.pending.length === 0) {
        pendingList.innerHTML = `<div class="empty">${data.current ? 'No other items pending.' : 'Queue is empty.'}</div>`;
    } else {
        pendingList.innerHTML = data.pending.map((url, i) =>
            `<div class="item">
                <span class="idx">#${i + 1}</span>
                <a href="${esc(url)}" target="_blank" rel="noopener">${esc(url)}</a>
            </div>`
        ).join('');
    }
}

reloadBtn.addEventListener('click', fetchQueue);

autoRefreshCb.addEventListener('change', () => {
    clearInterval(autoRefreshTimer);
    if (autoRefreshCb.checked) {
        autoRefreshTimer = setInterval(fetchQueue, 5000);
    }
});

fetchQueue();
