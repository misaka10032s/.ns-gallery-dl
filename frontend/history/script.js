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
    const closeModalBtn = document.querySelector('.close-btn');
    const domainListContainer = document.getElementById('domain-list');
    const applyDomainFilterBtn = document.getElementById('apply-domain-filter-btn');
    const deselectAllDomainsBtn = document.getElementById('deselect-all-domains-btn');
    const langSelector = document.querySelector('.lang-selector');
    const submitSelectedBtn = document.getElementById('submit-selected-btn');
    const selectedDomainsDisplay = document.getElementById('selected-domains-display');

    // State
    let fullHistoryData = {};
    let currentStatusFilter = 'all'; // 'all', 'failed', 'success'

    // --- Language Setup ---
    function updateActiveLangButton(lang) {
        langSelector.querySelectorAll('button').forEach(btn => {
            if (btn.dataset.langSet === lang) {
                btn.classList.add('lang-active');
            } else {
                btn.classList.remove('lang-active');
            }
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
            // Re-render with the new language for dynamic text
            applyFilters();
            // also update status filter button text
            updateStatusFilterButtonText();
        }
    });

    function updateStatusFilterButtonText() {
        if (currentStatusFilter === 'all') {
            statusFilterBtn.textContent = getTranslation('filterAll');
        } else if (currentStatusFilter === 'failed') {
            statusFilterBtn.textContent = getTranslation('filterFailed');
        } else {
            statusFilterBtn.textContent = getTranslation('filterSuccess');
        }
    }

    // --- Data Fetching and Initial Setup ---
    fetch('/api/history')
        .then(response => response.json())
        .then(data => {
            fullHistoryData = data;
            populateDomainFilter(fullHistoryData);
            renderHistory(fullHistoryData);
        })
        .catch(error => {
            recordsContainer.textContent = 'Failed to load history.';
            console.error('Error fetching history:', error);
        });

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

            items.forEach(item => {
                const entryDiv = document.createElement('div');
                const resultClass = item.result === 'success' ? 'success' : 'failed';
                entryDiv.className = `history-entry ${resultClass}`;
                entryDiv.innerHTML = `<input type="checkbox" class="entry-checkbox" data-url="${item.url}"> <a href="${item.url}" target="_blank">${item.url}</a>`;
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
            } catch (e) {
                console.warn(`Invalid URL found in history: ${item.url}`);
            }
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

        const selectedDomains = Array.from(domainListContainer.querySelectorAll('input[name="domain"]:checked'))
                                     .map(cb => cb.value);

        // Update UI based on domain filter
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
                    try {
                        const domain = new URL(item.url).hostname;
                        return selectedDomains.includes(domain);
                    } catch {
                        return false;
                    }
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
        if (currentStatusFilter === 'all') {
            currentStatusFilter = 'failed';
        } else if (currentStatusFilter === 'failed') {
            currentStatusFilter = 'success';
        } else {
            currentStatusFilter = 'all';
        }
        updateStatusFilterButtonText();
        applyFilters();
    });

    clearFiltersBtn.addEventListener('click', () => {
        startDateInput.value = '';
        endDateInput.value = '';
        domainListContainer.querySelectorAll('input[name="domain"]:checked').forEach(cb => cb.checked = false);
        currentStatusFilter = 'all';
        updateStatusFilterButtonText();
        applyFilters(); // applyFilters will handle UI updates
    });

    // Modal listeners
    openDomainModalBtn.addEventListener('click', () => domainModal.style.display = 'block');
    closeModalBtn.addEventListener('click', () => domainModal.style.display = 'none');
    window.addEventListener('click', (event) => {
        if (event.target == domainModal) {
            domainModal.style.display = 'none';
        }
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
        const urls = Array.from(recordsContainer.querySelectorAll('.entry-checkbox:checked')).map(cb => cb.dataset.url);
        if (urls.length === 0) return;

        fetch('/download', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ links: urls }),
        })
        .then(response => {
            if (response.ok) {
                alert(getTranslation('submitSuccessMsg'));
            } else {
                throw new Error('Server responded with an error.');
            }
        })
        .catch(error => {
            console.error('Error submitting URLs:', error);
            alert(getTranslation('submitErrorMsg'));
        });
    });

    // --- Existing Event Listeners (Accordion, Checkboxes, Output) ---
    recordsContainer.addEventListener('click', (event) => {
        const header = event.target.closest('.history-header');
        if (header && event.target.type !== 'checkbox') {
            const content = header.nextElementSibling;
            if (content) content.style.display = content.style.display === 'block' ? 'none' : 'block';
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
            outputTextarea.value = JSON.stringify(urls);
        } else {
            outputTextarea.value = urls.join('\n');
        }
    }
});
