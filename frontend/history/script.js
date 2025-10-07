document.addEventListener('DOMContentLoaded', () => {
    // UI Elements
    const recordsContainer = document.getElementById('records');
    const outputTextarea = document.getElementById('output-textarea');
    const jsonModeCheckbox = document.getElementById('json-mode-checkbox');
    const startDateInput = document.getElementById('start-date');
    const endDateInput = document.getElementById('end-date');
    const btn1Day = document.getElementById('btn-1-day');
    const btn7Days = document.getElementById('btn-7-days');
    const btn30Days = document.getElementById('btn-30-days');
    const statusFilterBtn = document.getElementById('status-filter-btn');
    const openDomainModalBtn = document.getElementById('open-domain-modal-btn');
    const clearFiltersBtn = document.getElementById('clear-filters-btn');
    const domainModal = document.getElementById('domain-filter-modal');
    const closeModalBtns = document.querySelectorAll('.close-btn');
    const domainListContainer = document.getElementById('domain-list');
    const applyDomainFilterBtn = document.getElementById('apply-domain-filter-btn');
    const deselectAllDomainsBtn = document.getElementById('deselect-all-domains-btn');
    const langSelector = document.querySelector('.lang-selector');
    const submitSelectedBtn = document.getElementById('submit-selected-btn');
    const selectedDomainsDisplay = document.getElementById('selected-domains-display');
    const notificationContainer = document.getElementById('notification-container');
    const reloadBtn = document.getElementById('reload-btn');
    const actionLogBtn = document.getElementById('action-log-btn');
    const actionLogModal = document.getElementById('action-log-modal');
    const logEntriesContainer = document.getElementById('log-entries-container');

    // State
    let fullHistoryData = {};
    let currentStatusFilter = 'all'; // 'all', 'failed', 'success'
    let isFetching = false;
    let expandedGroups = new Set();

    // --- Notification System ---
    function showNotification(message, type = 'success', duration = 5000) {
        const notif = document.createElement('div');
        notif.className = `notification ${type}`;
        
        const messageSpan = document.createElement('span');
        messageSpan.textContent = message;
        notif.appendChild(messageSpan);

        const closeBtn = document.createElement('button');
        closeBtn.className = 'notification-close-btn';
        closeBtn.innerHTML = '&times;';
        notif.appendChild(closeBtn);

        const fadeDuration = 0.5; // seconds
        notif.style.animation = `fadeIn ${fadeDuration}s, fadeOut ${fadeDuration}s ${duration / 1000 - fadeDuration}s forwards`;
        
        const timeoutId = setTimeout(() => notif.remove(), duration);

        closeBtn.addEventListener('click', () => {
            clearTimeout(timeoutId);
            notif.remove();
        });

        notificationContainer.appendChild(notif);
    }

    // --- Language Setup ---
    function updateActiveLangButton(lang) {
        langSelector.querySelectorAll('button').forEach(btn => {
            btn.classList.toggle('lang-active', btn.dataset.langSet === lang);
        });
    }

    const savedLang = localStorage.getItem('language') || 'zh';
    setLanguage(savedLang);
    updateActiveLangButton(savedLang);

    langSelector.addEventListener('click', (event) => {
        const lang = event.target.dataset.langSet;
        if (lang) {
            setLanguage(lang);
            updateActiveLangButton(lang);
            applyFilters();
            updateStatusFilterButtonText();
        }
    });

    function updateStatusFilterButtonText() {
        statusFilterBtn.textContent = getTranslation(`filter${currentStatusFilter.charAt(0).toUpperCase() + currentStatusFilter.slice(1)}`);
    }

    // --- Data Fetching and Initial Setup ---
    function fetchData() {
        if (isFetching) return;
        isFetching = true;
        reloadBtn.textContent = getTranslation('reloading');
        reloadBtn.disabled = true;

        fetch('/api/history')
            .then(response => response.json())
            .then(data => {
                fullHistoryData = data;
                populateDomainFilter(fullHistoryData);
                applyFilters();
            })
            .catch(error => {
                showNotification('Failed to load history.', 'error');
                console.error('Error fetching history:', error);
            })
            .finally(() => {
                isFetching = false;
                reloadBtn.textContent = getTranslation('reload');
                reloadBtn.disabled = false;
            });
    }

    fetchData(); // Initial data load
    reloadBtn.addEventListener('click', fetchData);

    // --- Action Log ---
    function logAction(url, oldStatus, newStatus) {
        let log = JSON.parse(localStorage.getItem('actionLog') || '[]');
        const logEntry = {
            timestamp: new Date().toISOString(),
            url,
            oldStatus,
            newStatus
        };
        log.unshift(logEntry);
        log = log.slice(0, 100); // Keep only the last 100 entries
        localStorage.setItem('actionLog', JSON.stringify(log));
    }

    function renderActionLog() {
        let log = JSON.parse(localStorage.getItem('actionLog') || '[]');
        logEntriesContainer.innerHTML = '';
        if (log.length === 0) {
            logEntriesContainer.innerHTML = `<div style="text-align: center; padding: 20px; color: #777;">${getTranslation('noActionLog')}</div>`;
            return;
        }
        log.forEach(entry => {
            const entryDiv = document.createElement('div');
            entryDiv.className = 'log-entry';
            const time = new Date(entry.timestamp).toLocaleString();
            entryDiv.innerHTML = `[${time}] URL: ${entry.url} <br> &rarr; Status changed from <strong>${entry.oldStatus}</strong> to <strong>${entry.newStatus}</strong>`;
            logEntriesContainer.appendChild(entryDiv);
        });
    }

    // --- Rendering Logic ---
    function renderHistory(historyData) {
        recordsContainer.innerHTML = '';
        const sortedDates = Object.keys(historyData).sort((a, b) => new Date(b) - new Date(a));

        if (sortedDates.length === 0 || sortedDates.every(date => historyData[date].length === 0)) {
            recordsContainer.innerHTML = `<div style="text-align: center; padding: 20px; color: #777;">${getTranslation('noRecordsFound')}</div>`;
            return;
        }

        sortedDates.forEach(date => {
            const items = historyData[date];
            if (items.length === 0) return;

            const groupDiv = document.createElement('div');
            groupDiv.className = 'history-group';
            groupDiv.dataset.date = date;

            const headerDiv = document.createElement('div');
            headerDiv.className = 'history-header';
            headerDiv.innerHTML = `<input type="checkbox" class="date-checkbox"> ${date} (${items.length} ${getTranslation('itemsSuffix')})`;

            const contentDiv = document.createElement('div');
            contentDiv.className = 'history-content';

            // Restore expanded state
            if (expandedGroups.has(date)) {
                contentDiv.style.display = 'block';
            }

            items.forEach(item => {
                const entryDiv = document.createElement('div');
                const resultClass = item.result === 'success' ? 'success' : 'failed';
                entryDiv.className = `history-entry ${resultClass}`;
                
                const markButtonText = getTranslation(item.result === 'success' ? 'markAsFailed' : 'markAsSuccess');

                entryDiv.innerHTML = `
                    <div class="history-entry-main">
                        <input type="checkbox" class="entry-checkbox" data-url="${item.url}">
                        <a href="${item.url}" target="_blank">${item.url}</a>
                    </div>
                    <div class="history-entry-actions">
                        <button class="entry-action-btn fetch-btn" data-url="${item.url}">fetch</button>
                        <button class="entry-action-btn mark-status-btn" data-url="${item.url}" data-current-status="${item.result}">${markButtonText}</button>
                    </div>
                `;
                contentDiv.appendChild(entryDiv);
            });

            groupDiv.appendChild(headerDiv);
            groupDiv.appendChild(contentDiv);
            recordsContainer.appendChild(groupDiv);
        });
        updateOutput();
    }

    // --- Filtering Logic ---
    function populateDomainFilter(data) {
        const domains = new Set();
        Object.values(data).flat().forEach(item => {
            try {
                const domain = new URL(item.url).hostname;
                domains.add(domain);
            } catch (e) { console.warn(`Invalid URL: ${item.url}`); }
        });

        domainListContainer.innerHTML = '';
        Array.from(domains).sort().forEach(domain => {
            const label = document.createElement('label');
            label.innerHTML = `<input type="checkbox" name="domain" value="${domain}"> ${domain}`;
            domainListContainer.appendChild(label);
        });
    }

    function applyFilters() {
        let filteredData = JSON.parse(JSON.stringify(fullHistoryData));
        const startDate = startDateInput.value ? new Date(startDateInput.value) : null;
        const endDate = endDateInput.value ? new Date(endDateInput.value) : null;
        
        if (startDate) startDate.setHours(0, 0, 0, 0);
        if (endDate) endDate.setHours(23, 59, 59, 999);

        const selectedDomains = Array.from(domainListContainer.querySelectorAll('input[name="domain"]:checked')).map(cb => cb.value);

        if (selectedDomains.length > 0) {
            openDomainModalBtn.classList.add('filter-active');
            selectedDomainsDisplay.innerHTML = selectedDomains.map(d => 
                `<span class="domain-badge">${d}<span class="remove-domain-btn" data-domain="${d}">&times;</span></span>`
            ).join('');
        } else {
            openDomainModalBtn.classList.remove('filter-active');
            selectedDomainsDisplay.innerHTML = '';
        }

        for (const date in filteredData) {
            const recordDate = new Date(date);
            if ((startDate && recordDate < startDate) || (endDate && recordDate > endDate)) {
                delete filteredData[date];
                continue;
            }

            if (selectedDomains.length > 0) {
                filteredData[date] = filteredData[date].filter(item => {
                    try { return selectedDomains.includes(new URL(item.url).hostname); } catch { return false; }
                });
            }

            if (currentStatusFilter !== 'all') {
                filteredData[date] = filteredData[date].filter(item => item.result === currentStatusFilter);
            }
        }
        renderHistory(filteredData);
    }

    // --- Event Listeners ---
    function setDateRange(days) {
        const end = new Date();
        const start = new Date();
        start.setDate(end.getDate() - (days - 1));
        const formatDate = (d) => d.toISOString().split('T')[0];
        startDateInput.value = formatDate(start);
        endDateInput.value = formatDate(end);
        applyFilters();
    }

    btn1Day.addEventListener('click', () => setDateRange(1));
    btn7Days.addEventListener('click', () => setDateRange(7));
    btn30Days.addEventListener('click', () => setDateRange(30));
    startDateInput.addEventListener('change', applyFilters);
    endDateInput.addEventListener('change', applyFilters);

    statusFilterBtn.addEventListener('click', () => {
        const states = ['all', 'failed', 'success'];
        const currentIndex = states.indexOf(currentStatusFilter);
        currentStatusFilter = states[(currentIndex + 1) % states.length];
        updateStatusFilterButtonText();
        applyFilters();
    });

    clearFiltersBtn.addEventListener('click', () => {
        startDateInput.value = '';
        endDateInput.value = '';
        domainListContainer.querySelectorAll('input[name="domain"]:checked').forEach(cb => cb.checked = false);
        currentStatusFilter = 'all';
        updateStatusFilterButtonText();
        applyFilters();
    });

    // Modal listeners
    [domainModal, actionLogModal].forEach(modal => {
        const closeBtn = modal.querySelector('.close-btn');
        closeBtn.addEventListener('click', () => modal.style.display = 'none');
    });
    openDomainModalBtn.addEventListener('click', () => domainModal.style.display = 'block');
    actionLogBtn.addEventListener('click', () => {
        renderActionLog();
        actionLogModal.style.display = 'block';
    });
    window.addEventListener('click', (event) => {
        if (event.target == domainModal) domainModal.style.display = 'none';
        if (event.target == actionLogModal) actionLogModal.style.display = 'none';
    });
    applyDomainFilterBtn.addEventListener('click', () => {
        applyFilters();
        domainModal.style.display = 'none';
    });
    deselectAllDomainsBtn.addEventListener('click', () => {
        domainListContainer.querySelectorAll('input[name="domain"]:checked').forEach(cb => cb.checked = false);
    });

    selectedDomainsDisplay.addEventListener('click', (event) => {
        if (event.target.classList.contains('remove-domain-btn')) {
            const domainToRemove = event.target.dataset.domain;
            const domainCheckbox = domainListContainer.querySelector(`input[value="${domainToRemove}"]`);
            if (domainCheckbox) {
                domainCheckbox.checked = false;
                applyFilters();
            }
        }
    });

    // Submit listener
    submitSelectedBtn.addEventListener('click', () => {
        const text = outputTextarea.value.trim();
        if (text === '') return;

        let urls;
        try {
            // Try parsing as JSON first
            if (text.startsWith('[') && text.endsWith(']')) {
                urls = JSON.parse(text);
            } else {
                // Fallback to newline-separated
                urls = text.split('\n');
            }
        } catch (e) {
            // If JSON parsing fails, treat as newline-separated
            urls = text.split('\n');
        }
        
        const finalUrls = urls.map(url => url.trim()).filter(url => url.length > 0);

        if (finalUrls.length === 0) return;

        fetch('/download', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ links: finalUrls }),
        })
        .then(response => {
            if (response.ok) {
                showNotification(getTranslation('submitSuccessMsg'), 'success');
            } else {
                throw new Error('Server responded with an error.');
            }
        })
        .catch(error => {
            console.error('Error submitting URLs:', error);
            showNotification(getTranslation('submitErrorMsg'), 'error');
        });
    });

    // --- Entry-specific and other listeners ---
    recordsContainer.addEventListener('click', (event) => {
        const target = event.target;
        // Accordion toggle
        const header = target.closest('.history-header');
        if (header && !target.closest('.entry-action-btn, input[type="checkbox"]')) {
            const content = header.nextElementSibling;
            const group = header.closest('.history-group');
            const date = group.dataset.date;
            const isOpening = content.style.display === 'none';
            
            content.style.display = isOpening ? 'block' : 'none';
            if (isOpening) {
                expandedGroups.add(date);
            } else {
                expandedGroups.delete(date);
            }
            return;
        }

        // Fetch button
        if (target.classList.contains('fetch-btn')) {
            const url = target.dataset.url;
            target.disabled = true;
            target.classList.remove('status-success', 'status-danger');

            fetch('/api/fetch_status', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ url: url })
            })
            .then(response => response.json())
            .then(data => {
                if (data.error) {
                    throw new Error(data.error);
                }
                // Check for 2xx status codes
                if (data.status_code >= 200 && data.status_code < 300) {
                    target.classList.add('status-success');
                } else {
                    target.classList.add('status-danger');
                }
            })
            .catch((err) => {
                console.error('Fetch proxy error:', err);
                target.classList.add('status-danger');
            })
            .finally(() => { target.disabled = false; });
            return;
        }

        // Mark status button
        if (target.classList.contains('mark-status-btn')) {
            const url = target.dataset.url;
            const oldStatus = target.dataset.currentStatus;
            const newStatus = oldStatus === 'success' ? 'failed' : 'success';
            const date = target.closest('.history-group').dataset.date;

            target.disabled = true;

            fetch('/api/history', {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ date, url, status: newStatus })
            })
            .then(response => {
                if (!response.ok) {
                    throw new Error('Server failed to update history.');
                }
                return response.json();
            })
            .then(() => {
                // Log the action locally for the action log UI
                logAction(url, oldStatus, newStatus);
                // Optimistically update the UI before full refetch for faster feedback
                const item = fullHistoryData[date]?.find(i => i.url === url);
                if(item) item.result = newStatus;
                applyFilters();
                // Optionally, you could call fetchData() here for a full refresh,
                // but optimistic update is faster for the user.
            })
            .catch(err => {
                console.error('Error updating status:', err);
                showNotification('Failed to update status.', 'error');
            })
            .finally(() => {
                target.disabled = false;
            });

            return;
        }
    });
    
    recordsContainer.addEventListener('change', (event) => {
        const target = event.target;
        if (target.type !== 'checkbox') return;
        const group = target.closest('.history-group');
        if (!group) return;

        if (target.classList.contains('date-checkbox')) {
            group.querySelectorAll('.entry-checkbox').forEach(cb => cb.checked = target.checked);
        } else if (target.classList.contains('entry-checkbox')) {
            const dateCheckbox = group.querySelector('.date-checkbox');
            const allEntries = Array.from(group.querySelectorAll('.entry-checkbox'));
            dateCheckbox.checked = allEntries.every(cb => cb.checked);
            dateCheckbox.indeterminate = !dateCheckbox.checked && allEntries.some(cb => cb.checked);
        }
        updateOutput();
    });

    jsonModeCheckbox.addEventListener('change', updateOutput);

    function updateOutput() {
        const allCheckedEntries = recordsContainer.querySelectorAll('.entry-checkbox:checked');
        const urls = Array.from(allCheckedEntries).map(cb => cb.dataset.url);
        
        if (jsonModeCheckbox.checked) {
            outputTextarea.value = JSON.stringify(urls, null, 2);
        } else {
            outputTextarea.value = urls.join('\n');
        }
    }
});
