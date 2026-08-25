// Global State for Views & Saved Messages
let currentViewMode = localStorage.getItem('tg_drive_view_mode') || 'grid';
let currentSavedMessages = [];
let loadedMessageIds = new Set();
let selectedMessageIds = new Set();
let lastOffsetId = 0;
let hasMoreMessages = true;
let isLoadingMessages = false;

function showDirectory(data) {
    data = data['contents']
    document.getElementById('directory-data').innerHTML = ''
    const isTrash = getCurrentPath().startsWith('/trash')

    // Reset toolbar controls for regular directory view
    const selectAllContainer = document.getElementById('select-all-container');
    const batchActionsBar = document.getElementById('batch-actions-bar');
    const thSelect = document.getElementById('th-select');
    const gridContainer = document.getElementById('directory-grid');
    const tableContainer = document.getElementById('directory-table');
    const infiniteScrollStatus = document.getElementById('infinite-scroll-status');

    if (selectAllContainer) selectAllContainer.style.display = 'none';
    if (batchActionsBar) batchActionsBar.style.display = 'none';
    if (thSelect) thSelect.style.display = 'none';
    if (infiniteScrollStatus) infiniteScrollStatus.style.display = 'none';

    // Show Table, Hide Grid for regular directories
    if (tableContainer) tableContainer.style.display = 'table';
    if (gridContainer) gridContainer.style.display = 'none';

    let html = ''

    // Sort the array based on upload_date
    let entries = Object.entries(data);
    let folders = entries.filter(([key, value]) => value.type === 'folder');
    let files = entries.filter(([key, value]) => value.type === 'file');

    folders.sort((a, b) => new Date(b[1].upload_date) - new Date(a[1].upload_date));
    files.sort((a, b) => new Date(b[1].upload_date) - new Date(a[1].upload_date));

    for (const [key, item] of folders) {
        if (item.type === 'folder') {
            html += `<tr data-path="${item.path}" data-id="${item.id}" class="body-tr folder-tr"><td><div class="td-align"><img src="static/assets/folder-solid-icon.svg">${item.name}</div></td><td><div class="td-align"></div></td><td><div class="td-align"><a data-id="${item.id}" class="more-btn"><img src="static/assets/more-icon.svg" class="rotate-90"></a></div></td></tr>`

            if (isTrash) {
                html += `<div data-path="${item.path}" id="more-option-${item.id}" data-name="${item.name}" class="more-options"><input class="more-options-focus" readonly="readonly" style="height:0;width:0;border:none;position:absolute"><div id="restore-${item.id}" data-path="${item.path}"><img src="static/assets/load-icon.svg"> Restore</div><hr><div id="delete-${item.id}" data-path="${item.path}"><img src="static/assets/trash-icon.svg"> Delete</div></div>`
            }
            else {
                html += `<div data-path="${item.path}" id="more-option-${item.id}" data-name="${item.name}" class="more-options"><input class="more-options-focus" readonly="readonly" style="height:0;width:0;border:none;position:absolute"><div id="rename-${item.id}"><img src="static/assets/pencil-icon.svg"> Rename</div><hr><div id="trash-${item.id}"><img src="static/assets/trash-icon.svg"> Trash</div><hr><div id="folder-share-${item.id}"><img src="static/assets/share-icon.svg"> Share</div></div>`
            }
        }
    }

    for (const [key, item] of files) {
        if (item.type === 'file') {
            const size = convertBytes(item.size)
            html += `<tr data-path="${item.path}" data-id="${item.id}" data-name="${item.name}" class="body-tr file-tr"><td><div class="td-align"><img src="static/assets/file-icon.svg">${item.name}</div></td><td><div class="td-align">${size}</div></td><td><div class="td-align"><a data-id="${item.id}" class="more-btn"><img src="static/assets/more-icon.svg" class="rotate-90"></a></div></td></tr>`

            if (isTrash) {
                html += `<div data-path="${item.path}" id="more-option-${item.id}" data-name="${item.name}" class="more-options"><input class="more-options-focus" readonly="readonly" style="height:0;width:0;border:none;position:absolute"><div id="restore-${item.id}" data-path="${item.path}"><img src="static/assets/load-icon.svg"> Restore</div><hr><div id="delete-${item.id}" data-path="${item.path}"><img src="static/assets/trash-icon.svg"> Delete</div></div>`
            }
            else {
                html += `<div data-path="${item.path}" id="more-option-${item.id}" data-name="${item.name}" class="more-options"><input class="more-options-focus" readonly="readonly" style="height:0;width:0;border:none;position:absolute"><div id="rename-${item.id}"><img src="static/assets/pencil-icon.svg"> Rename</div><hr><div id="trash-${item.id}"><img src="static/assets/trash-icon.svg"> Trash</div><hr><div id="share-${item.id}"><img src="static/assets/share-icon.svg"> Share</div><hr><div id="save-tg-${item.id}"><img src="static/assets/telegram-icon.svg"> Save to Telegram</div></div>`
            }
        }
    }
    document.getElementById('directory-data').innerHTML = html

    if (!isTrash) {
        document.querySelectorAll('.folder-tr').forEach(div => {
            div.ondblclick = openFolder;
        });
        document.querySelectorAll('.file-tr').forEach(div => {
            div.ondblclick = openFile;
        });
    }

    document.querySelectorAll('.more-btn').forEach(div => {
        div.addEventListener('click', function (event) {
            event.preventDefault();
            openMoreButton(div)
        });
    });
}

// ---------------- Saved Messages & Gallery Grid View Logic ---------------- //

function showSavedMessages(messages, initial = true) {
    if (initial) {
        currentSavedMessages = [];
        loadedMessageIds.clear();
        selectedMessageIds.clear();
    }

    const newMessages = [];
    for (const msg of messages) {
        if (!loadedMessageIds.has(msg.id)) {
            loadedMessageIds.add(msg.id);
            currentSavedMessages.push(msg);
            newMessages.push(msg);
        }
    }

    // Show selection controls in header
    const selectAllContainer = document.getElementById('select-all-container');
    const thSelect = document.getElementById('th-select');
    if (selectAllContainer) selectAllContainer.style.display = 'flex';
    if (thSelect) thSelect.style.display = 'table-cell';

    updateSelectionUI();
    applyViewMode(currentViewMode);

    if (initial) {
        renderSavedMessages(currentSavedMessages, false);
    } else if (newMessages.length > 0) {
        renderSavedMessages(newMessages, true);
    }

    bindSavedMessageActions();
}

function renderSavedMessages(messages, append = false) {
    const tbody = document.getElementById('directory-data');
    const gridContainer = document.getElementById('directory-grid');

    if (!append) {
        tbody.innerHTML = '';
        gridContainer.innerHTML = '';
    }

    if (currentSavedMessages.length === 0) {
        tbody.innerHTML = `<tr><td colspan="5" style="text-align: center; padding: 40px; color: #888;">No media files found in your Telegram Saved Messages.</td></tr>`;
        gridContainer.innerHTML = `<div style="grid-column: 1 / -1; text-align: center; padding: 40px; color: #888;">No media files found in your Telegram Saved Messages.</div>`;
        return;
    }

    let listHtml = '';
    let gridHtml = '';

    for (const item of messages) {
        listHtml += createListRowHtml(item);
        gridHtml += createGridCardHtml(item);
    }

    if (append) {
        tbody.insertAdjacentHTML('beforeend', listHtml);
        gridContainer.insertAdjacentHTML('beforeend', gridHtml);
    } else {
        tbody.innerHTML = listHtml;
        gridContainer.innerHTML = gridHtml;
    }
}

function createListRowHtml(item) {
    const sizeStr = convertBytes(item.size);
    const nameEscaped = (item.name || 'file').replace(/"/g, '&quot;');
    const isSelected = selectedMessageIds.has(item.id);
    const thumbSrc = item.has_thumb ? `/api/getThumbnail?msg_id=${item.id}` : 'static/assets/file-icon.svg';

    return `
    <tr class="body-tr saved-msg-tr ${isSelected ? 'selected-row' : ''}" data-msg-id="${item.id}">
        <td style="width: 40px; text-align: center;">
            <input type="checkbox" class="row-select-checkbox" data-msg-id="${item.id}" ${isSelected ? 'checked' : ''} />
        </td>
        <td>
            <div class="td-align" style="gap: 12px;">
                <img src="${thumbSrc}" onerror="this.onerror=null; this.src='static/assets/file-icon.svg';" style="width: 34px; height: 34px; object-fit: cover; border-radius: 4px;" loading="lazy" />
                <span style="font-weight: 500; word-break: break-all;">${item.name}</span>
            </div>
        </td>
        <td><div class="td-align">${sizeStr}</div></td>
        <td><div class="td-align" style="color: #666; font-size: 0.85rem;">${item.date}</div></td>
        <td>
            <div class="td-align" style="justify-content: center; gap: 8px;">
                <button class="tg-action-btn tg-save-btn" data-msg-id="${item.id}" data-name="${nameEscaped}" title="Save to TG Drive">
                    <img src="static/assets/plus-icon.svg" style="width: 16px; height: 16px; margin-right: 4px;" /> Save to Drive
                </button>
                <button class="tg-action-btn tg-download-btn" data-msg-id="${item.id}" data-name="${nameEscaped}" data-size="${item.size}" title="Download to Server">
                    <img src="static/assets/upload-icon.svg" style="width: 16px; height: 16px; transform: rotate(180deg); margin-right: 4px;" /> Download
                </button>
                <button class="tg-action-btn tg-delete-btn" data-msg-id="${item.id}" title="Delete from Saved Messages">
                    <img src="static/assets/trash-icon.svg" style="width: 16px; height: 16px;" />
                </button>
            </div>
        </td>
    </tr>`;
}

function createGridCardHtml(item) {
    const sizeStr = convertBytes(item.size);
    const nameEscaped = (item.name || 'file').replace(/"/g, '&quot;');
    const isSelected = selectedMessageIds.has(item.id);
    const mediaBadge = item.media_type && item.media_type !== 'file' ? `<span class="card-media-type-badge">${item.media_type}</span>` : '';
    const thumbSrc = item.has_thumb ? `/api/getThumbnail?msg_id=${item.id}` : 'static/assets/file-icon.svg';
    const isRealThumb = !!item.has_thumb;

    return `
    <div class="grid-card ${isSelected ? 'selected' : ''}" data-msg-id="${item.id}">
        <input type="checkbox" class="card-checkbox" data-msg-id="${item.id}" ${isSelected ? 'checked' : ''} />
        <div class="card-thumbnail-wrapper">
            <img class="${isRealThumb ? 'card-thumb-img' : 'card-fallback-icon'}" src="${thumbSrc}" onerror="this.onerror=null; this.src='static/assets/file-icon.svg'; this.className='card-fallback-icon';" alt="${nameEscaped}" loading="lazy" />
            ${mediaBadge}
        </div>
        <div class="card-content">
            <div class="card-filename" title="${nameEscaped}">${item.name}</div>
            <div class="card-meta">
                <span>${sizeStr}</span>
                <span>${item.date ? item.date.split(' ')[0] : ''}</span>
            </div>
            <div class="card-actions">
                <button class="card-action-btn btn-save tg-save-btn" data-msg-id="${item.id}" data-name="${nameEscaped}" title="Save to TG Drive">
                    <img src="static/assets/plus-icon.svg" /> Save
                </button>
                <button class="card-action-btn btn-download tg-download-btn" data-msg-id="${item.id}" data-name="${nameEscaped}" data-size="${item.size}" title="Download to Server">
                    <img src="static/assets/upload-icon.svg" style="transform: rotate(180deg);" />
                </button>
                <button class="card-action-btn btn-delete tg-delete-btn" data-msg-id="${item.id}" title="Delete from Saved Messages">
                    <img src="static/assets/trash-icon.svg" />
                </button>
            </div>
        </div>
    </div>`;
}

function bindSavedMessageActions() {
    // Checkbox toggles (both card and table rows)
    document.querySelectorAll('.card-checkbox, .row-select-checkbox').forEach(chk => {
        chk.onchange = (e) => {
            e.stopPropagation();
            const msgId = parseInt(chk.getAttribute('data-msg-id'));
            if (chk.checked) {
                selectedMessageIds.add(msgId);
            } else {
                selectedMessageIds.delete(msgId);
            }
            syncCheckboxStates();
            updateSelectionUI();
        };
    });

    // Save to Drive Buttons
    document.querySelectorAll('.tg-save-btn').forEach(btn => {
        btn.onclick = async (e) => {
            e.stopPropagation();
            const msgId = parseInt(btn.getAttribute('data-msg-id'));
            btn.disabled = true;
            const originalHtml = btn.innerHTML;
            btn.innerHTML = `<img src="static/assets/load-icon.svg" style="animation: spin 1s linear infinite; height: 14px;"> Saving...`;
            try {
                const res = await postJson('/api/saveSavedMessage', { msg_id: msgId, path: '/' });
                if (res.status === 'ok') {
                    btn.innerHTML = `✓ Saved`;
                    btn.style.color = '#2e7d32';
                    btn.style.borderColor = '#2e7d32';
                } else {
                    alert('Failed to save to Drive: ' + (res.message || res.status));
                    btn.disabled = false;
                    btn.innerHTML = originalHtml;
                }
            } catch (err) {
                alert('Error: ' + err);
                btn.disabled = false;
                btn.innerHTML = originalHtml;
            }
        };
    });

    // Download Buttons
    document.querySelectorAll('.tg-download-btn').forEach(btn => {
        btn.onclick = async (e) => {
            e.stopPropagation();
            const msgId = parseInt(btn.getAttribute('data-msg-id'));
            const fileName = btn.getAttribute('data-name');
            const fileSize = parseInt(btn.getAttribute('data-size')) || 0;
            btn.disabled = true;
            const originalHtml = btn.innerHTML;
            btn.innerHTML = `<img src="static/assets/load-icon.svg" style="animation: spin 1s linear infinite; height: 14px;"> Starting...`;
            try {
                const res = await postJson('/api/startBackgroundDownload', {
                    msg_ids: [msgId],
                    names: [fileName],
                    sizes: [fileSize]
                });
                if (res.status === 'ok') {
                    btn.innerHTML = `✓ Queued`;
                    btn.style.color = '#1565c0';
                    btn.style.borderColor = '#1565c0';
                } else {
                    alert('Download error: ' + (res.message || res.status));
                    btn.disabled = false;
                    btn.innerHTML = originalHtml;
                }
            } catch (err) {
                alert('Error: ' + err);
                btn.disabled = false;
                btn.innerHTML = originalHtml;
            }
        };
    });

    // Delete Buttons
    document.querySelectorAll('.tg-delete-btn').forEach(btn => {
        btn.onclick = async (e) => {
            e.stopPropagation();
            if (!confirm('Are you sure you want to delete this message from Telegram Saved Messages?')) {
                return;
            }
            const msgId = parseInt(btn.getAttribute('data-msg-id'));
            btn.disabled = true;
            try {
                const res = await postJson('/api/deleteSavedMessages', { msg_ids: [msgId] });
                if (res.status === 'ok') {
                    // Remove from DOM and internal tracking
                    document.querySelectorAll(`[data-msg-id="${msgId}"]`).forEach(el => el.remove());
                    selectedMessageIds.delete(msgId);
                    loadedMessageIds.delete(msgId);
                    currentSavedMessages = currentSavedMessages.filter(m => m.id !== msgId);
                    updateSelectionUI();
                } else {
                    alert('Failed to delete: ' + (res.message || res.status));
                    btn.disabled = false;
                }
            } catch (err) {
                alert('Error: ' + err);
                btn.disabled = false;
            }
        };
    });
}

function syncCheckboxStates() {
    document.querySelectorAll('.card-checkbox, .row-select-checkbox').forEach(chk => {
        const msgId = parseInt(chk.getAttribute('data-msg-id'));
        const isChecked = selectedMessageIds.has(msgId);
        chk.checked = isChecked;

        const card = chk.closest('.grid-card');
        if (card) card.classList.toggle('selected', isChecked);

        const row = chk.closest('tr');
        if (row) row.classList.toggle('selected-row', isChecked);
    });
}

function updateSelectionUI() {
    const count = selectedMessageIds.size;
    const total = currentSavedMessages.length;

    const selectAllCheckbox = document.getElementById('select-all-checkbox');
    const tableSelectAll = document.getElementById('table-select-all');
    const badge = document.getElementById('selected-count-badge');
    const batchBar = document.getElementById('batch-actions-bar');

    if (badge) badge.innerText = `${count} of ${total} selected`;

    const allSelected = total > 0 && count === total;
    if (selectAllCheckbox) selectAllCheckbox.checked = allSelected;
    if (tableSelectAll) tableSelectAll.checked = allSelected;

    if (batchBar) {
        batchBar.style.display = count > 0 ? 'flex' : 'none';
    }
}

function applyViewMode(mode) {
    currentViewMode = mode;
    localStorage.setItem('tg_drive_view_mode', mode);

    const gridBtn = document.getElementById('view-grid-btn');
    const listBtn = document.getElementById('view-list-btn');
    const gridContainer = document.getElementById('directory-grid');
    const tableContainer = document.getElementById('directory-table');

    if (mode === 'grid') {
        if (gridBtn) gridBtn.classList.add('active');
        if (listBtn) listBtn.classList.remove('active');
        if (gridContainer) gridContainer.style.display = 'grid';
        if (tableContainer) tableContainer.style.display = 'none';
    } else {
        if (gridBtn) gridBtn.classList.remove('active');
        if (listBtn) listBtn.classList.add('active');
        if (gridContainer) gridContainer.style.display = 'none';
        if (tableContainer) tableContainer.style.display = 'table';
    }
}

// ---------------- Infinite Scroll & Batch Action Handlers ---------------- //

async function loadMoreSavedMessages() {
    if (isLoadingMessages || !hasMoreMessages) return;

    isLoadingMessages = true;
    const scrollStatus = document.getElementById('infinite-scroll-status');
    if (scrollStatus) {
        scrollStatus.style.display = 'flex';
        scrollStatus.querySelector('span').innerText = 'Loading more files...';
    }

    try {
        const response = await postJson('/api/getSavedMessages', {
            limit: 40,
            offset_id: lastOffsetId
        });

        if (response.status === 'ok') {
            hasMoreMessages = response.has_more;
            lastOffsetId = response.last_id;

            if (response.messages && response.messages.length > 0) {
                showSavedMessages(response.messages, false);
            }

            if (!hasMoreMessages && scrollStatus) {
                scrollStatus.querySelector('span').innerText = 'All items loaded';
                setTimeout(() => {
                    scrollStatus.style.display = 'none';
                }, 2000);
            } else if (scrollStatus) {
                scrollStatus.style.display = 'none';
            }
        } else {
            if (scrollStatus) scrollStatus.style.display = 'none';
        }
    } catch (err) {
        console.error('Error loading more messages:', err);
        if (scrollStatus) scrollStatus.style.display = 'none';
    } finally {
        isLoadingMessages = false;
    }
}

function initViewControlsAndBatch() {
    // View mode buttons
    const gridBtn = document.getElementById('view-grid-btn');
    const listBtn = document.getElementById('view-list-btn');

    if (gridBtn) gridBtn.onclick = () => applyViewMode('grid');
    if (listBtn) listBtn.onclick = () => applyViewMode('list');

    // Select All Checkbox Handler
    const handleSelectAll = (checked) => {
        if (checked) {
            currentSavedMessages.forEach(m => selectedMessageIds.add(m.id));
        } else {
            selectedMessageIds.clear();
        }
        syncCheckboxStates();
        updateSelectionUI();
    };

    const selectAllCheckbox = document.getElementById('select-all-checkbox');
    if (selectAllCheckbox) {
        selectAllCheckbox.onchange = (e) => handleSelectAll(e.target.checked);
    }

    const tableSelectAll = document.getElementById('table-select-all');
    if (tableSelectAll) {
        tableSelectAll.onchange = (e) => handleSelectAll(e.target.checked);
    }

    // Batch Save to Drive Button
    const batchSaveBtn = document.getElementById('batch-save-btn');
    if (batchSaveBtn) {
        batchSaveBtn.onclick = async () => {
            const selectedIds = Array.from(selectedMessageIds);
            if (selectedIds.length === 0) return;

            batchSaveBtn.disabled = true;
            batchSaveBtn.innerHTML = `<img src="static/assets/load-icon.svg" class="spinner-icon"> Saving ${selectedIds.length} items...`;

            try {
                const res = await postJson('/api/saveSavedMessage', {
                    msg_ids: selectedIds,
                    path: '/'
                });
                if (res.status === 'ok') {
                    batchSaveBtn.innerHTML = `✓ ${res.saved_count || selectedIds.length} Saved to Drive!`;
                    setTimeout(() => {
                        batchSaveBtn.disabled = false;
                        batchSaveBtn.innerHTML = `<img src="static/assets/plus-icon.svg"> Save to Drive`;
                    }, 2500);
                } else {
                    alert('Batch save error: ' + (res.message || res.status));
                    batchSaveBtn.disabled = false;
                    batchSaveBtn.innerHTML = `<img src="static/assets/plus-icon.svg"> Save to Drive`;
                }
            } catch (err) {
                alert('Error: ' + err);
                batchSaveBtn.disabled = false;
                batchSaveBtn.innerHTML = `<img src="static/assets/plus-icon.svg"> Save to Drive`;
            }
        };
    }

    // Batch Download Button
    const batchDownloadBtn = document.getElementById('batch-download-btn');
    if (batchDownloadBtn) {
        batchDownloadBtn.onclick = async () => {
            const selectedIds = Array.from(selectedMessageIds);
            if (selectedIds.length === 0) return;

            const selectedItems = currentSavedMessages.filter(m => selectedMessageIds.has(m.id));
            const names = selectedItems.map(m => m.name);
            const sizes = selectedItems.map(m => m.size);

            batchDownloadBtn.disabled = true;
            batchDownloadBtn.innerHTML = `<img src="static/assets/load-icon.svg" class="spinner-icon"> Starting...`;

            try {
                const res = await postJson('/api/startBackgroundDownload', {
                    msg_ids: selectedIds,
                    names: names,
                    sizes: sizes
                });
                if (res.status === 'ok') {
                    batchDownloadBtn.innerHTML = `✓ ${selectedIds.length} Queued for Download!`;
                    setTimeout(() => {
                        batchDownloadBtn.disabled = false;
                        batchDownloadBtn.innerHTML = `<img src="static/assets/upload-icon.svg" style="transform: rotate(180deg);"> Download`;
                    }, 2500);
                } else {
                    alert('Download error: ' + (res.message || res.status));
                    batchDownloadBtn.disabled = false;
                    batchDownloadBtn.innerHTML = `<img src="static/assets/upload-icon.svg" style="transform: rotate(180deg);"> Download`;
                }
            } catch (err) {
                alert('Error: ' + err);
                batchDownloadBtn.disabled = false;
                batchDownloadBtn.innerHTML = `<img src="static/assets/upload-icon.svg" style="transform: rotate(180deg);"> Download`;
            }
        };
    }

    // Batch Delete Button
    const batchDeleteBtn = document.getElementById('batch-delete-btn');
    if (batchDeleteBtn) {
        batchDeleteBtn.onclick = async () => {
            const selectedIds = Array.from(selectedMessageIds);
            if (selectedIds.length === 0) return;

            if (!confirm(`Are you sure you want to delete ${selectedIds.length} messages from Telegram Saved Messages?`)) {
                return;
            }

            batchDeleteBtn.disabled = true;
            batchDeleteBtn.innerHTML = `<img src="static/assets/load-icon.svg" class="spinner-icon"> Deleting...`;

            try {
                const res = await postJson('/api/deleteSavedMessages', { msg_ids: selectedIds });
                if (res.status === 'ok') {
                    selectedIds.forEach(id => {
                        document.querySelectorAll(`[data-msg-id="${id}"]`).forEach(el => el.remove());
                        selectedMessageIds.delete(id);
                        loadedMessageIds.delete(id);
                    });
                    currentSavedMessages = currentSavedMessages.filter(m => !selectedIds.includes(m.id));
                    updateSelectionUI();
                    batchDeleteBtn.disabled = false;
                    batchDeleteBtn.innerHTML = `<img src="static/assets/trash-icon.svg"> Delete`;
                } else {
                    alert('Failed to delete: ' + (res.message || res.status));
                    batchDeleteBtn.disabled = false;
                    batchDeleteBtn.innerHTML = `<img src="static/assets/trash-icon.svg"> Delete`;
                }
            } catch (err) {
                alert('Error: ' + err);
                batchDeleteBtn.disabled = false;
                batchDeleteBtn.innerHTML = `<img src="static/assets/trash-icon.svg"> Delete`;
            }
        };
    }

    // Infinite Scroll Event on Directory container
    const dirContainer = document.getElementById('directory-container');
    if (dirContainer) {
        dirContainer.addEventListener('scroll', () => {
            if (getCurrentPath() === '/saved_messages') {
                const scrollBottom = dirContainer.scrollHeight - dirContainer.scrollTop - dirContainer.clientHeight;
                if (scrollBottom < 350 && hasMoreMessages && !isLoadingMessages) {
                    loadMoreSavedMessages();
                }
            }
        });
    }
}

// ---------------- Search & Initialization ---------------- //

document.getElementById('search-form').addEventListener('submit', async (event) => {
    event.preventDefault();
    const query = document.getElementById('file-search').value;
    console.log(query)
    if (query === '') {
        alert('Search field is empty');
        return;
    }
    const path = '/?path=/search_' + encodeURI(query);
    console.log(path)
    window.location = path;
});

// Loading Main Page
document.addEventListener('DOMContentLoaded', function () {
    const inputs = ['new-folder-name', 'rename-name', 'file-search'];
    for (let i = 0; i < inputs.length; i++) {
        const el = document.getElementById(inputs[i]);
        if (el) el.addEventListener('input', validateInput);
    }

    initViewControlsAndBatch();

    if (getCurrentPath().includes('/share_')) {
        getCurrentDirectory()
    } else {
        if (getPassword() === null) {
            document.getElementById('bg-blur').style.zIndex = '2';
            document.getElementById('bg-blur').style.opacity = '0.1';

            document.getElementById('get-password').style.zIndex = '3';
            document.getElementById('get-password').style.opacity = '1';
        } else {
            getCurrentDirectory()
        }
    }
});
