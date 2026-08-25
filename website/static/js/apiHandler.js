// Api Fuctions
async function postJson(url, data) {
    data['password'] = getPassword()
    const response = await fetch(url, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify(data)
    })
    return await response.json()
}

document.getElementById('pass-login').addEventListener('click', async () => {
    const password = document.getElementById('auth-pass').value
    const data = { 'pass': password }
    const json = await postJson('/api/checkPassword', data)
    if (json.status === 'ok') {
        localStorage.setItem('password', password)
        alert('Logged In Successfully')
        window.location.reload()
    }
    else {
        alert('Wrong Password')
    }

})

async function getCurrentDirectory() {
    let path = getCurrentPath()
    if (path === 'redirect') {
        return
    }

    // Reset dashboard view if not on /downloads
    const dlDashboard = document.getElementById('downloads-dashboard');
    if (dlDashboard && path !== '/downloads') {
        dlDashboard.style.display = 'none';
    }

    if (path === '/saved_messages') {
        await loadSavedMessagesView()
        return
    }

    if (path === '/downloads') {
        await loadDownloadsView()
        return
    }

    try {
        const auth = getFolderAuthFromPath()
        console.log(path)

        const data = { 'path': path, 'auth': auth }
        const json = await postJson('/api/getDirectory', data)

        if (json.status === 'ok') {
            if (getCurrentPath().startsWith('/share')) {
                const sections = document.querySelector('.sidebar-menu').getElementsByTagName('a')
                console.log(path)

                if (removeSlash(json['auth_home_path']) === removeSlash(path.split('_')[1])) {
                    sections[0].setAttribute('class', 'selected-item')

                } else {
                    sections[0].setAttribute('class', 'unselected-item')
                }
                sections[0].href = `/?path=/share_${removeSlash(json['auth_home_path'])}&auth=${auth}`
                console.log(`/?path=/share_${removeSlash(json['auth_home_path'])}&auth=${auth}`)
            }

            console.log(json)
            showDirectory(json['data'])
        } else {
            alert('404 Current Directory Not Found')
        }
    }
    catch (err) {
        console.log(err)
        alert('404 Current Directory Not Found')
    }
}

async function loadSavedMessagesView() {
    const directoryThead = document.querySelector('.directory table thead tr');
    if (directoryThead) {
        directoryThead.innerHTML = `
            <th id="th-select" style="width: 40px; text-align: center;">
                <input type="checkbox" id="table-select-all" />
            </th>
            <th style="width: 42%;">Name</th>
            <th style="width: 15%;">File Size</th>
            <th style="width: 18%;">Date</th>
            <th style="width: 25%; text-align: center;">Actions</th>
        `;
    }

    const tbody = document.getElementById('directory-data');
    const gridContainer = document.getElementById('directory-grid');
    const loadingHtml = `<div style="text-align: center; padding: 40px; color: #666; width: 100%;"><img src="static/assets/load-icon.svg" style="animation: spin 1s linear infinite; height: 24px; vertical-align: middle; margin-right: 8px;"> Loading Telegram Saved Messages...</div>`;

    if (tbody) tbody.innerHTML = `<tr><td colspan="5">${loadingHtml}</td></tr>`;
    if (gridContainer) gridContainer.innerHTML = loadingHtml;

    lastOffsetId = 0;
    hasMoreMessages = true;

    try {
        const response = await postJson('/api/getSavedMessages', { limit: 40, offset_id: 0 });
        if (response.status === 'ok') {
            lastOffsetId = response.last_id || 0;
            hasMoreMessages = response.has_more || false;
            showSavedMessages(response.messages || [], true);
        } else if (response.status === 'no_user_session') {
            const noSessionHtml = `<div style="text-align: center; padding: 40px; color: #888; width: 100%;">No Telegram User Session (STRING_SESSIONS) configured. Please add your STRING_SESSIONS in .env to access Saved Messages.</div>`;
            if (tbody) tbody.innerHTML = `<tr><td colspan="5">${noSessionHtml}</td></tr>`;
            if (gridContainer) gridContainer.innerHTML = noSessionHtml;
        } else {
            const errHtml = `<div style="text-align: center; padding: 40px; color: #e53935; width: 100%;">Error loading Saved Messages: ${response.message || response.status}</div>`;
            if (tbody) tbody.innerHTML = `<tr><td colspan="5">${errHtml}</td></tr>`;
            if (gridContainer) gridContainer.innerHTML = errHtml;
        }
    } catch (err) {
        const errHtml = `<div style="text-align: center; padding: 40px; color: #e53935; width: 100%;">Error: ${err.message}</div>`;
        if (tbody) tbody.innerHTML = `<tr><td colspan="5">${errHtml}</td></tr>`;
        if (gridContainer) gridContainer.innerHTML = errHtml;
    }
}

// ---------------- Downloads & Transfers Dashboard ---------------- //

let downloadsPollTimer = null;

async function loadDownloadsView() {
    // Hide table, grid, select-all, view toggle, and infinite scroll
    const selectAllContainer = document.getElementById('select-all-container');
    const batchActionsBar = document.getElementById('batch-actions-bar');
    const viewToggle = document.getElementById('view-mode-toggle');
    const tableContainer = document.getElementById('directory-table');
    const gridContainer = document.getElementById('directory-grid');
    const infiniteScrollStatus = document.getElementById('infinite-scroll-status');
    const dirContainer = document.getElementById('directory-container');

    if (selectAllContainer) selectAllContainer.style.display = 'none';
    if (batchActionsBar) batchActionsBar.style.display = 'none';
    if (viewToggle) viewToggle.style.display = 'none';
    if (tableContainer) tableContainer.style.display = 'none';
    if (gridContainer) gridContainer.style.display = 'none';
    if (infiniteScrollStatus) infiniteScrollStatus.style.display = 'none';

    let dlContainer = document.getElementById('downloads-dashboard');
    if (!dlContainer) {
        dlContainer = document.createElement('div');
        dlContainer.id = 'downloads-dashboard';
        dlContainer.className = 'downloads-container';
        dirContainer.appendChild(dlContainer);
    }
    dlContainer.style.display = 'flex';

    if (downloadsPollTimer) clearInterval(downloadsPollTimer);

    // Initial load
    await updateDownloadsUI();

    // Poll every 1 second
    downloadsPollTimer = setInterval(async () => {
        if (getCurrentPath() !== '/downloads') {
            clearInterval(downloadsPollTimer);
            downloadsPollTimer = null;
            return;
        }
        await updateDownloadsUI();
    }, 1000);
}

function formatSpeed(bytesPerSec) {
    if (!bytesPerSec || bytesPerSec <= 0) return '0 KB/s';
    return convertBytes(bytesPerSec) + '/s';
}

function formatETA(seconds) {
    if (!seconds || seconds <= 0 || !isFinite(seconds)) return '--';
    if (seconds < 60) return `${seconds}s left`;
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    if (mins < 60) return `${mins}m ${secs}s left`;
    const hours = Math.floor(mins / 60);
    const remMins = mins % 60;
    return `${hours}h ${remMins}m left`;
}

async function updateDownloadsUI() {
    const dlContainer = document.getElementById('downloads-dashboard');
    if (!dlContainer || getCurrentPath() !== '/downloads') return;

    try {
        const response = await postJson('/api/getTasks', {});
        if (response.status !== 'ok') return;

        const tasks = response.tasks || {};
        const metrics = response.metrics || {};
        const taskList = Object.values(tasks);

        const totalSpeed = formatSpeed(metrics.total_speed || 0);
        const totalDownloaded = convertBytes(metrics.total_downloaded || 0);
        const activeCount = metrics.active_count || 0;
        const totalTasks = taskList.length;

        // Update nav badge
        const badge = document.getElementById('nav-downloads-badge');
        if (badge) {
            if (activeCount > 0) {
                badge.style.display = 'inline-block';
                badge.innerText = activeCount;
            } else {
                badge.style.display = 'none';
            }
        }

        let html = `
        <div class="downloads-metrics-bar">
            <div class="metric-card">
                <div class="metric-icon-wrapper" style="background: #e8f0fe; color: #1a73e8;">
                    <img src="static/assets/download-icon.svg" />
                </div>
                <div class="metric-info">
                    <span class="metric-label">Download Speed</span>
                    <span class="metric-value">${totalSpeed}</span>
                </div>
            </div>

            <div class="metric-card">
                <div class="metric-icon-wrapper" style="background: #e6f4ea; color: #137333;">
                    <img src="static/assets/load-icon.svg" />
                </div>
                <div class="metric-info">
                    <span class="metric-label">Active Transfers</span>
                    <span class="metric-value">${activeCount} active <span style="font-size: 0.8rem; font-weight: 500; color: #666;">(${totalTasks} total)</span></span>
                </div>
            </div>

            <div class="metric-card">
                <div class="metric-icon-wrapper" style="background: #fef7e0; color: #b06000;">
                    <img src="static/assets/file-icon.svg" />
                </div>
                <div class="metric-info">
                    <span class="metric-label">Total Transferred</span>
                    <span class="metric-value">${totalDownloaded}</span>
                </div>
            </div>

            <div class="metric-card" style="justify-content: center;">
                <button class="batch-btn" id="btn-clear-completed" style="width: 100%; justify-content: center; height: 42px; cursor: pointer;">
                    <img src="static/assets/trash-icon.svg"> Clear Completed
                </button>
            </div>
        </div>

        <div class="downloads-list">
        `;

        if (taskList.length === 0) {
            html += `
            <div style="text-align: center; padding: 60px 20px; color: #888; background: #fafafa; border-radius: 12px; border: 1px dashed #dadce0;">
                <img src="static/assets/download-icon.svg" style="width: 48px; height: 48px; opacity: 0.3; margin-bottom: 12px;" />
                <div style="font-size: 1.1rem; font-weight: 500; color: #5f6368; margin-bottom: 6px;">No Active Downloads</div>
                <div style="font-size: 0.85rem; color: #888;">When you download files from Telegram Saved Messages or URL Upload, live progress will appear here.</div>
            </div>
            `;
        } else {
            const order = { 'downloading': 1, 'running': 1, 'queued': 2, 'paused': 3, 'completed': 4, 'cancelled': 5, 'error': 6 };
            taskList.sort((a, b) => (order[a.status] || 9) - (order[b.status] || 9));

            for (const t of taskList) {
                const currentBytes = t.current || 0;
                const totalBytes = t.total || 0;
                const percent = totalBytes > 0 ? Math.min(100, Math.max(0, (currentBytes / totalBytes) * 100)) : (t.status === 'completed' ? 100 : 0);
                const speedFormatted = formatSpeed(t.speed || 0);
                const etaFormatted = formatETA(t.eta || 0);
                const statusClass = t.status || 'downloading';
                const pulseDot = (t.status === 'downloading' || t.status === 'running') ? '<span class="pulse-dot"></span>' : '';
                const isPaused = t.status === 'paused';
                const isCompleted = t.status === 'completed';
                const isFailed = t.status === 'error' || t.status === 'cancelled';

                html += `
                <div class="download-task-card" data-task-id="${t.id}">
                    <div class="task-header">
                        <div class="task-title-group">
                            <div class="task-icon">
                                <img src="static/assets/file-icon.svg" />
                            </div>
                            <span class="task-filename" title="${t.filename || 'File'}">${t.filename || 'File'}</span>
                        </div>
                        <span class="task-badge ${statusClass}">
                            ${pulseDot} ${t.status || 'Active'}
                        </span>
                    </div>

                    <div class="task-progress-container">
                        <div class="task-progress-fill ${statusClass}" style="width: ${percent.toFixed(1)}%;"></div>
                    </div>

                    <div class="task-details-bar">
                        <span class="task-stat-item">
                            Transferred: <strong>${convertBytes(currentBytes)} / ${convertBytes(totalBytes)}</strong> (${percent.toFixed(1)}%)
                        </span>
                        
                        ${!isCompleted && !isFailed ? `
                        <span class="task-stat-item">
                            Speed: <strong>⚡ ${speedFormatted}</strong>
                        </span>
                        <span class="task-stat-item">
                            ETA: <strong>⏱ ${etaFormatted}</strong>
                        </span>
                        ` : ''}

                        <div class="task-actions-group">
                            ${!isCompleted && !isFailed ? `
                            <button class="task-btn btn-pause-resume" data-task-id="${t.id}" data-action="${isPaused ? 'resume' : 'pause'}">
                                ${isPaused ? '▶ Resume' : '⏸ Pause'}
                            </button>
                            <button class="task-btn btn-cancel btn-cancel-task" data-task-id="${t.id}">
                                ✕ Cancel
                            </button>
                            ` : `
                            <button class="task-btn btn-cancel-task" data-task-id="${t.id}" style="color: #666;">
                                ✕ Remove
                            </button>
                            `}
                        </div>
                    </div>
                </div>
                `;
            }
        }

        html += `</div>`;
        dlContainer.innerHTML = html;

        // Bind Action Buttons
        const clearBtn = document.getElementById('btn-clear-completed');
        if (clearBtn) {
            clearBtn.onclick = async () => {
                await postJson('/api/clearCompletedTasks', {});
                await updateDownloadsUI();
            };
        }

        dlContainer.querySelectorAll('.btn-pause-resume').forEach(btn => {
            btn.onclick = async (e) => {
                e.stopPropagation();
                const taskId = btn.getAttribute('data-task-id');
                const action = btn.getAttribute('data-action');
                if (action === 'pause') {
                    await postJson('/api/pauseTask', { id: taskId });
                } else {
                    await postJson('/api/resumeTask', { id: taskId });
                }
                await updateDownloadsUI();
            };
        });

        dlContainer.querySelectorAll('.btn-cancel-task').forEach(btn => {
            btn.onclick = async (e) => {
                e.stopPropagation();
                const taskId = btn.getAttribute('data-task-id');
                await postJson('/api/cancelTask', { id: taskId });
                await updateDownloadsUI();
            };
        });

    } catch (err) {
        console.error('Error updating downloads UI:', err);
    }
}

// Periodic Background Badge Updater
setInterval(async () => {
    try {
        if (getPassword()) {
            const res = await postJson('/api/getTasks', {});
            if (res.status === 'ok' && res.metrics) {
                const badge = document.getElementById('nav-downloads-badge');
                if (badge) {
                    const count = res.metrics.active_count || 0;
                    if (count > 0) {
                        badge.style.display = 'inline-block';
                        badge.innerText = count;
                    } else {
                        badge.style.display = 'none';
                    }
                }
            }
        }
    } catch { }
}, 4000);

async function createNewFolder() {
    const folderName = document.getElementById('new-folder-name').value;
    const path = getCurrentPath()
    if (path === 'redirect') {
        return
    }
    if (folderName.length > 0) {
        const data = {
            'name': folderName,
            'path': path
        }
        try {
            const json = await postJson('/api/createNewFolder', data)

            if (json.status === 'ok') {
                window.location.reload();
            } else {
                alert(json.status)
            }
        }
        catch (err) {
            alert('Error Creating Folder')
        }
    } else {
        alert('Folder Name Cannot Be Empty')
    }
}


async function getFolderShareAuth(path) {
    const data = { 'path': path }
    const json = await postJson('/api/getFolderShareAuth', data)
    if (json.status === 'ok') {
        return json.auth
    } else {
        alert('Error Getting Folder Share Auth')
    }
}

// File Uploader Start

const MAX_FILE_SIZE = MAX_FILE_SIZE__SDGJDG // Will be replaced by the python

const fileInput = document.getElementById('fileInput');
const progressBar = document.getElementById('progress-bar');
const cancelButton = document.getElementById('cancel-file-upload');
const uploadPercent = document.getElementById('upload-percent');
let uploadRequest = null;
let uploadStep = 0;
let uploadID = null;

fileInput.addEventListener('change', async (e) => {
    const file = fileInput.files[0];

    if (file.size > MAX_FILE_SIZE) {
        alert(`File size exceeds ${(MAX_FILE_SIZE / (1024 * 1024 * 1024)).toFixed(2)} GB limit`);
        return;
    }

    // Showing file uploader
    document.getElementById('bg-blur').style.zIndex = '2';
    document.getElementById('bg-blur').style.opacity = '0.1';
    document.getElementById('file-uploader').style.zIndex = '3';
    document.getElementById('file-uploader').style.opacity = '1';

    document.getElementById('upload-filename').innerText = 'Filename: ' + file.name;
    document.getElementById('upload-filesize').innerText = 'Filesize: ' + (file.size / (1024 * 1024)).toFixed(2) + ' MB';
    document.getElementById('upload-status').innerText = 'Status: Uploading To Backend Server';


    const formData = new FormData();
    formData.append('file', file);
    formData.append('path', getCurrentPath());
    formData.append('password', getPassword());
    const id = getRandomId();
    formData.append('id', id);
    formData.append('total_size', file.size);

    uploadStep = 1;
    uploadRequest = new XMLHttpRequest();
    uploadRequest.open('POST', '/api/upload', true);

    uploadRequest.upload.addEventListener('progress', (e) => {
        if (e.lengthComputable) {
            const percentComplete = (e.loaded / e.total) * 100;
            progressBar.style.width = percentComplete + '%';
            uploadPercent.innerText = 'Progress : ' + percentComplete.toFixed(2) + '%';
        }
    });

    uploadRequest.upload.addEventListener('load', async () => {
        await updateSaveProgress(id)
    });

    uploadRequest.upload.addEventListener('error', () => {
        alert('Upload failed');
        window.location.reload();
    });

    uploadRequest.send(formData);
});

cancelButton.addEventListener('click', () => {
    if (uploadStep === 1) {
        uploadRequest.abort();
    } else if (uploadStep === 2) {
        const data = { 'id': uploadID }
        postJson('/api/cancelUpload', data)
    }
    alert('Upload canceled');
    window.location.reload();
});

async function updateSaveProgress(id) {
    console.log('save progress')
    progressBar.style.width = '0%';
    uploadPercent.innerText = 'Progress : 0%'
    document.getElementById('upload-status').innerText = 'Status: Processing File On Backend Server';

    const interval = setInterval(async () => {
        const response = await postJson('/api/getSaveProgress', { 'id': id })
        const data = response['data']

        if (data[0] === 'running') {
            const current = data[1];
            const total = data[2];
            document.getElementById('upload-filesize').innerText = 'Filesize: ' + (total / (1024 * 1024)).toFixed(2) + ' MB';

            const percentComplete = (current / total) * 100;
            progressBar.style.width = percentComplete + '%';
            uploadPercent.innerText = 'Progress : ' + percentComplete.toFixed(2) + '%';
        }
        else if (data[0] === 'completed') {
            clearInterval(interval);
            uploadPercent.innerText = 'Progress : 100%'
            progressBar.style.width = '100%';

            await handleUpload2(id)
        }
    }, 3000)

}

async function handleUpload2(id) {
    console.log(id)
    document.getElementById('upload-status').innerText = 'Status: Uploading To Telegram Server';
    progressBar.style.width = '0%';
    uploadPercent.innerText = 'Progress : 0%';

    const interval = setInterval(async () => {
        const response = await postJson('/api/getUploadProgress', { 'id': id })
        const data = response['data']

        if (data[0] === 'running') {
            const current = data[1];
            const total = data[2];
            document.getElementById('upload-filesize').innerText = 'Filesize: ' + (total / (1024 * 1024)).toFixed(2) + ' MB';

            let percentComplete
            if (total === 0) {
                percentComplete = 0
            }
            else {
                percentComplete = (current / total) * 100;
            }
            progressBar.style.width = percentComplete + '%';
            uploadPercent.innerText = 'Progress : ' + percentComplete.toFixed(2) + '%';
        }
        else if (data[0] === 'completed') {
            clearInterval(interval);
            alert('Upload Completed')
            window.location.reload();
        }
    }, 3000)
}

// File Uploader End


// URL Uploader Start

async function get_file_info_from_url(url) {
    const data = { 'url': url }
    const json = await postJson('/api/getFileInfoFromUrl', data)
    if (json.status === 'ok') {
        return json.data
    } else {
        throw new Error(`Error Getting File Info : ${json.status}`)
    }

}

async function start_file_download_from_url(url, filename, singleThreaded) {
    const data = { 'url': url, 'path': getCurrentPath(), 'filename': filename, 'singleThreaded': singleThreaded }
    const json = await postJson('/api/startFileDownloadFromUrl', data)
    if (json.status === 'ok') {
        return json.id
    } else {
        throw new Error(`Error Starting File Download : ${json.status}`)
    }
}

async function download_progress_updater(id, file_name, file_size) {
    uploadID = id;
    uploadStep = 2
    // Showing file uploader
    document.getElementById('bg-blur').style.zIndex = '2';
    document.getElementById('bg-blur').style.opacity = '0.1';
    document.getElementById('file-uploader').style.zIndex = '3';
    document.getElementById('file-uploader').style.opacity = '1';

    document.getElementById('upload-filename').innerText = 'Filename: ' + file_name;
    document.getElementById('upload-filesize').innerText = 'Filesize: ' + (file_size / (1024 * 1024)).toFixed(2) + ' MB';

    const interval = setInterval(async () => {
        const response = await postJson('/api/getFileDownloadProgress', { 'id': id })
        const data = response['data']

        if (data[0] === 'error') {
            clearInterval(interval);
            alert('Failed To Download File From URL To Backend Server')
            window.location.reload()
        }
        else if (data[0] === 'completed') {
            clearInterval(interval);
            uploadPercent.innerText = 'Progress : 100%'
            progressBar.style.width = '100%';
            await handleUpload2(id)
        }
        else {
            const current = data[1];
            const total = data[2];

            const percentComplete = (current / total) * 100;
            progressBar.style.width = percentComplete + '%';
            uploadPercent.innerText = 'Progress : ' + percentComplete.toFixed(2) + '%';

            if (data[0] === 'Downloading') {
                document.getElementById('upload-status').innerText = 'Status: Downloading File From Url To Backend Server';
            }
            else {
                document.getElementById('upload-status').innerText = `Status: ${data[0]}`;
            }
        }
    }, 3000)
}


async function Start_URL_Upload() {
    try {
        document.getElementById('new-url-upload').style.opacity = '0';
        setTimeout(() => {
            document.getElementById('new-url-upload').style.zIndex = '-1';
        }, 300)

        const file_url = document.getElementById('remote-url').value
        const singleThreaded = document.getElementById('single-threaded-toggle').checked

        const file_info = await get_file_info_from_url(file_url)
        const file_name = file_info.file_name
        const file_size = file_info.file_size

        if (file_size > MAX_FILE_SIZE) {
            throw new Error(`File size exceeds ${(MAX_FILE_SIZE / (1024 * 1024 * 1024)).toFixed(2)} GB limit`)
        }

        const id = await start_file_download_from_url(file_url, file_name, singleThreaded)

        await download_progress_updater(id, file_name, file_size)

    }
    catch (err) {
        alert(err)
        window.location.reload()
    }


}

// URL Uploader End