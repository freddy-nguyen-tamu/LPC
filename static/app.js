function setStatus(el, message, ok = true) {
  if (!el) return;
  el.textContent = message;
  el.classList.remove('ok', 'error');
  el.classList.add(ok ? 'ok' : 'error');
}

function bytesToReadable(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  const units = ['KB', 'MB', 'GB', 'TB'];
  let value = bytes;
  let i = -1;
  do {
    value /= 1024;
    i += 1;
  } while (value >= 1024 && i < units.length - 1);
  return `${value.toFixed(2)} ${units[i]}`;
}

async function fetchJson(url, options = {}) {
  const res = await fetch(url, options);
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error(data.error || 'Request failed');
  }
  return data;
}

function getStoredDeviceToken() {
  return localStorage.getItem('device_token') || '';
}

function setStoredDeviceToken(token) {
  localStorage.setItem('device_token', token);
}

function guessPlatform() {
  const ua = navigator.userAgent || '';
  if (/android/i.test(ua)) return 'Android';
  if (/iPhone|iPad|iPod/i.test(ua)) return 'iPhone/iPad';
  return 'Mobile Browser';
}

async function initPhoneMode() {
  const pairForm = document.getElementById('pairForm');
  const pairStatus = document.getElementById('pairStatus');
  const phoneIdentity = document.getElementById('phoneIdentity');
  const uploadSection = document.getElementById('uploadSection');
  const downloadsSection = document.getElementById('downloadsSection');
  const pairSection = document.getElementById('pairSection');
  const uploadForm = document.getElementById('phoneUploadForm');
  const uploadStatus = document.getElementById('uploadStatus');
  const pendingDownloads = document.getElementById('pendingDownloads');

  async function refreshMe() {
    const token = getStoredDeviceToken();
    if (!token) {
      phoneIdentity.textContent = 'This phone is not linked yet.';
      pairSection.style.display = 'block';
      uploadSection.style.display = 'none';
      downloadsSection.style.display = 'none';
      return;
    }

    try {
      const data = await fetchJson(`/api/phone/me?device_token=${encodeURIComponent(token)}`);
      const d = data.device;
      phoneIdentity.textContent = `Linked as ${d.device_name} (${d.platform || 'unknown'})`;
      pairSection.style.display = 'none';
      uploadSection.style.display = 'block';
      downloadsSection.style.display = 'block';
      await refreshPending();
    } catch (err) {
      localStorage.removeItem('device_token');
      phoneIdentity.textContent = 'Stored link is no longer valid. Please pair again.';
      pairSection.style.display = 'block';
      uploadSection.style.display = 'none';
      downloadsSection.style.display = 'none';
    }
  }

  async function refreshPending() {
    const token = getStoredDeviceToken();
    if (!token) return;

    try {
      const data = await fetchJson(`/api/phone/pending?device_token=${encodeURIComponent(token)}`);
      const jobs = data.jobs || [];

      if (!jobs.length) {
        pendingDownloads.innerHTML = '<p class="muted">No downloads waiting.</p>';
        return;
      }

      pendingDownloads.innerHTML = jobs.map(job => `
        <div class="download-card">
          <div><strong>${job.filename}</strong></div>
          <div class="small muted">${bytesToReadable(job.size_bytes)}</div>
          <div style="margin-top:10px;">
            <a class="download-btn" href="${job.download_url}">Download to phone</a>
          </div>
        </div>
      `).join('');
    } catch (err) {
      pendingDownloads.innerHTML = `<p class="status error">${err.message}</p>`;
    }
  }

  pairForm?.addEventListener('submit', async (e) => {
    e.preventDefault();
    const pairCode = document.getElementById('pair_code').value.trim();
    const deviceName = document.getElementById('device_name').value.trim();

    if (!pairCode || !deviceName) {
      setStatus(pairStatus, 'Pair code and phone name are required.', false);
      return;
    }

    try {
      const data = await fetchJson('/api/pair', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          pair_code: pairCode,
          device_name: deviceName,
          platform: guessPlatform()
        })
      });
      setStoredDeviceToken(data.device_token);
      setStatus(pairStatus, 'Phone linked successfully.');
      await refreshMe();
    } catch (err) {
      setStatus(pairStatus, err.message, false);
    }
  });

  uploadForm?.addEventListener('submit', async (e) => {
    e.preventDefault();
    const fileInput = document.getElementById('phone_file');
    const file = fileInput.files?.[0];
    if (!file) {
      setStatus(uploadStatus, 'Choose a file first.', false);
      return;
    }

    const formData = new FormData();
    formData.append('device_token', getStoredDeviceToken());
    formData.append('file', file);

    try {
      setStatus(uploadStatus, 'Uploading...');
      const data = await fetchJson('/api/phone/upload', {
        method: 'POST',
        body: formData
      });
      setStatus(uploadStatus, `Uploaded ${data.filename} successfully.`);
      fileInput.value = '';
    } catch (err) {
      setStatus(uploadStatus, err.message, false);
    }
  });

  await refreshMe();
  setInterval(refreshMe, (window.TRANSFER_APP?.pollSeconds || 4) * 1000);
}

async function initLaptopMode() {
  const sendForm = document.getElementById('sendToPhoneForm');
  const sendStatus = document.getElementById('sendStatus');
  const devicesList = document.getElementById('devicesList');
  const transfersList = document.getElementById('transfersList');

  async function refreshLaptop() {
    try {
      const [devicesData, transfersData] = await Promise.all([
        fetchJson('/api/laptop/devices'),
        fetchJson('/api/laptop/transfers')
      ]);

      const devices = devicesData.devices || [];
      if (!devices.length) {
        devicesList.innerHTML = '<p class="muted">No phones linked yet.</p>';
      } else {
        devicesList.innerHTML = devices.map(d => `
          <div class="list-item">
            <div>
              <strong>${d.device_name}</strong>
              <div class="small muted">${d.platform || 'unknown'}</div>
            </div>
            <div class="small muted right">
              Transfers: ${d.transfer_count}<br>${d.last_seen_at || '-'}
            </div>
          </div>
        `).join('');
      }

      const select = document.getElementById('device_id');
      const currentValue = select.value;
      select.innerHTML = '<option value="">Select a phone</option>' + devices.map(d =>
        `<option value="${d.id}">${d.device_name} ${d.platform ? `(${d.platform})` : ''}</option>`
      ).join('');
      if ([...select.options].some(o => o.value === currentValue)) {
        select.value = currentValue;
      }

      const transfers = transfersData.transfers || [];
      if (!transfers.length) {
        transfersList.innerHTML = '<p class="muted">No transfers yet.</p>';
      } else {
        transfersList.innerHTML = transfers.map(t => `
          <div class="list-item">
            <div>
              <strong>${t.filename}</strong>
              <div class="small muted">${t.direction}${t.device_name ? ` • ${t.device_name}` : ''}</div>
            </div>
            <div class="small muted right">
              ${t.status}<br>${bytesToReadable(t.size_bytes)}
            </div>
          </div>
        `).join('');
      }
    } catch (err) {
      console.error(err);
    }
  }

  sendForm?.addEventListener('submit', async (e) => {
    e.preventDefault();
    const formData = new FormData(sendForm);
    try {
      setStatus(sendStatus, 'Queueing file...');
      const data = await fetchJson('/api/laptop/send', {
        method: 'POST',
        body: formData
      });
      setStatus(sendStatus, data.message);
      sendForm.reset();
      await refreshLaptop();
    } catch (err) {
      setStatus(sendStatus, err.message, false);
    }
  });

  await refreshLaptop();
  setInterval(refreshLaptop, (window.TRANSFER_APP?.pollSeconds || 4) * 1000);
}

window.addEventListener('DOMContentLoaded', async () => {
  if (window.TRANSFER_APP?.mode === 'phone') {
    await initPhoneMode();
  }
  if (window.TRANSFER_APP?.mode === 'laptop') {
    await initLaptopMode();
  }
});