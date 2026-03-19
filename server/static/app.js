const socket = io();

function fmtBytes(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  const units = ["KB", "MB", "GB", "TB"];
  let i = -1;
  let value = bytes;
  do {
    value /= 1024;
    i += 1;
  } while (value >= 1024 && i < units.length - 1);
  return `${value.toFixed(2)} ${units[i]}`;
}

function renderDevices(devices) {
  const container = document.getElementById("devices");
  const select = document.getElementById("deviceSelect");
  if (!container || !select) return;

  if (!devices.length) {
    container.innerHTML = `<p class="meta">No linked devices yet.</p>`;
    select.innerHTML = `<option value="">No devices</option>`;
    return;
  }

  container.innerHTML = devices.map(d => `
    <div class="list-item">
      <div>
        <div><strong>${d.device_name}</strong></div>
        <div class="meta">${d.platform || 'unknown'} • linked ${d.linked_at || '-'}</div>
      </div>
      <div><span class="badge">${d.last_seen_at ? 'online seen' : 'idle'}</span></div>
    </div>
  `).join("");

  const current = select.value;
  select.innerHTML = `<option value="">Select device</option>` + devices.map(d =>
    `<option value="${d.id}">${d.device_name} ${d.platform ? `(${d.platform})` : ''}</option>`
  ).join("");
  const hasCurrent = [...select.options].some(o => o.value === current);
  if (hasCurrent) select.value = current;
}

function renderTransfers(transfers) {
  const container = document.getElementById("transfers");
  if (!container) return;
  if (!transfers.length) {
    container.innerHTML = `<p class="meta">No transfers yet.</p>`;
    return;
  }
  container.innerHTML = transfers.map(t => `
    <div class="list-item">
      <div>
        <div><strong>${t.filename}</strong></div>
        <div class="meta">${t.direction} ${t.device_name ? '• ' + t.device_name : ''}</div>
      </div>
      <div>
        <div><span class="badge">${t.status}</span></div>
        <div class="meta">${fmtBytes(t.size_bytes || 0)} • ${t.uploaded_chunks || 0}/${t.total_chunks || 0} chunks</div>
      </div>
    </div>
  `).join("");
}

async function fetchDashboard() {
  const res = await fetch('/api/dashboard');
  const data = await res.json();
  renderDevices(data.devices || []);
  renderTransfers(data.transfers || []);
}

async function init() {
  await fetchDashboard();

  const form = document.getElementById('sendForm');
  const status = document.getElementById('sendStatus');
  form?.addEventListener('submit', async (e) => {
    e.preventDefault();
    const formData = new FormData(form);
    status.textContent = 'Queueing transfer...';
    const res = await fetch('/api/laptop/send/init', { method: 'POST', body: formData });
    const data = await res.json();
    if (!res.ok || !data.ok) {
      status.textContent = data.error || 'Failed';
      return;
    }
    status.textContent = `Transfer #${data.transfer_id} queued.`;
    form.reset();
    await fetchDashboard();
  });
}

socket.on('dashboard_update', (payload) => {
  renderDevices(payload.devices || []);
  renderTransfers(payload.transfers || []);
});

socket.on('transfer_progress', () => fetchDashboard());
socket.on('connect', () => console.log('socket connected'));

document.addEventListener('DOMContentLoaded', init);