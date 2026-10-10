/**
 * Events and Booking Engine Controller
 * Supports live availability checking with debouncing and shortage alerts
 */

let allEvents = [];
let catalogItems = [];
let checkAvailabilityTimer = null;
let lastAvailabilityResult = null;
let currentUser = null;

document.addEventListener('DOMContentLoaded', async () => {
  currentUser = await API.getCurrentUser();
  await UI.initNavbar();

  setupModalHandlers();
  setupFilterHandlers();
  await loadCatalogItems();
  await loadEvents();

  // Setup Booking Form
  const btnOpenBooking = document.getElementById('btn-open-booking-modal');
  btnOpenBooking?.addEventListener('click', openNewBookingModal);

  document.getElementById('btn-add-item-row')?.addEventListener('click', () => addItemPickerRow());
  document.getElementById('btn-ai-recommend')?.addEventListener('click', handleAiRecommend);
  document.getElementById('booking-start')?.addEventListener('change', triggerLiveAvailabilityCheck);
  document.getElementById('booking-end')?.addEventListener('change', triggerLiveAvailabilityCheck);

  // Booking submissions
  document.getElementById('form-booking')?.addEventListener('submit', (e) => {
    e.preventDefault();
    submitBooking('CONFIRMED');
  });

  document.getElementById('btn-submit-draft')?.addEventListener('click', () => {
    submitBooking('DRAFT');
  });
});

async function handleAiRecommend() {
  const btn = document.getElementById('btn-ai-recommend');
  const eventType = document.getElementById('booking-type').value;
  const attendees = parseInt(document.getElementById('booking-attendees').value, 10) || 50;
  const startTime = document.getElementById('booking-start').value;
  const endTime = document.getElementById('booking-end').value;

  let duration = 4.0;
  if (startTime && endTime) {
    const diffMs = new Date(endTime) - new Date(startTime);
    if (diffMs > 0) {
      duration = Math.max(1.0, Math.round((diffMs / (1000 * 60 * 60)) * 10) / 10);
    }
  }

  btn.disabled = true;
  btn.textContent = '⚡ Analyzing...';

  const res = await API.fetch('/api/ml/predict-items', {
    method: 'POST',
    body: JSON.stringify({
      event_type: eventType,
      expected_guests: attendees,
      duration_hours: duration,
      start_time: startTime,
      respect_stock: false
    })
  });

  btn.disabled = false;
  btn.textContent = '⚡ AI Auto-Recommend';

  if (!res.ok) {
    UI.toast('AI prediction failed: ' + res.error, 'error');
    return;
  }

  const items = res.data.items || [];
  if (items.length === 0) {
    UI.toast('No item recommendations generated.', 'warning');
    return;
  }

  const list = document.getElementById('booking-items-list');
  list.innerHTML = '';

  items.forEach(rec => {
    if (rec.suggested_quantity > 0) {
      let matchedCatalogId = rec.item_id;
      if (!matchedCatalogId) {
        const found = catalogItems.find(c => 
          c.category.toLowerCase() === rec.category.toLowerCase() ||
          c.name.toLowerCase().includes(rec.item_key.toLowerCase())
        );
        if (found) matchedCatalogId = found.id;
      }
      addItemPickerRow(matchedCatalogId || '', rec.suggested_quantity);
    }
  });

  UI.toast(`⚡ Loaded AI recommendations for ${attendees} guests!`, 'success');
  triggerLiveAvailabilityCheck();
}

async function loadCatalogItems() {
  const res = await API.fetch('/api/inventory/items');
  if (res.ok) {
    catalogItems = (res.data.items || []).filter(i => i.is_active);
  }
}

async function loadEvents() {
  const tbody = document.getElementById('events-tbody');
  const res = await API.fetch('/api/events');

  if (!res.ok) {
    tbody.innerHTML = `
      <tr>
        <td colspan="7" style="text-align: center; color: var(--danger); padding: 2rem;">
          Failed to load events: ${res.error}
        </td>
      </tr>
    `;
    return;
  }

  allEvents = res.data.events || [];
  renderEventsTable();
}

function renderEventsTable() {
  const tbody = document.getElementById('events-tbody');
  const query = document.getElementById('event-search').value.toLowerCase().trim();
  const statusFilter = document.getElementById('filter-event-status').value.toLowerCase();

  const filtered = allEvents.filter(evt => {
    const title = evt.name || evt.title || '';
    if (query && !title.toLowerCase().includes(query) && !(evt.description || '').toLowerCase().includes(query)) {
      return false;
    }
    if (statusFilter && (evt.status || '').toLowerCase() !== statusFilter) {
      return false;
    }
    return true;
  });

  if (filtered.length === 0) {
    tbody.innerHTML = `
      <tr>
        <td colspan="7" style="text-align: center; color: var(--text-muted); padding: 2rem;">
          No events found matching your search.
        </td>
      </tr>
    `;
    return;
  }

  tbody.innerHTML = filtered.map(evt => {
    const windowText = `${UI.formatDate(evt.start_time)}<br><span style="color: var(--text-dim);">&darr; ${UI.formatDate(evt.end_time)}</span>`;
    const itemCount = (evt.items || []).reduce((sum, i) => sum + (i.quantity || i.quantity_requested || 0), 0);
    const itemLabel = `${(evt.items || []).length} items (${itemCount} units)`;
    const title = evt.name || evt.title || 'Untitled Event';

    // Action buttons based on status
    const status = (evt.status || '').toUpperCase();
    let actionsHtml = `<button class="btn btn-secondary btn-sm" onclick="viewEventDetails(${evt.id})">Details</button>`;

    if (status === 'DRAFT') {
      actionsHtml += `
        <button class="btn btn-primary btn-sm" style="margin-left: 0.35rem;" onclick="confirmBooking(${evt.id})">Confirm</button>
        <button class="btn btn-danger btn-sm" style="margin-left: 0.35rem;" onclick="cancelBooking(${evt.id})">Cancel</button>
      `;
    } else if (status === 'CONFIRMED') {
      actionsHtml += `
        <button class="btn btn-secondary btn-sm" style="margin-left: 0.35rem; color: var(--success);" onclick="completeBooking(${evt.id})">Complete</button>
        <button class="btn btn-danger btn-sm" style="margin-left: 0.35rem;" onclick="cancelBooking(${evt.id})">Cancel</button>
      `;
    }

    return `
      <tr>
        <td>
          <strong>${escapeHtml(title)}</strong>
          ${evt.description ? `<div style="font-size: 0.8rem; color: var(--text-dim);">${escapeHtml(evt.description)}</div>` : ''}
        </td>
        <td style="text-transform: capitalize;">${escapeHtml(evt.event_type)}</td>
        <td style="font-size: 0.85rem;">${windowText}</td>
        <td>${evt.expected_attendees || '—'}</td>
        <td>${itemLabel}</td>
        <td>${UI.statusBadge(evt.status)}</td>
        <td><div style="display: flex; align-items: center;">${actionsHtml}</div></td>
      </tr>
    `;
  }).join('');
}

function setupFilterHandlers() {
  document.getElementById('event-search')?.addEventListener('input', renderEventsTable);
  document.getElementById('filter-event-status')?.addEventListener('change', renderEventsTable);
}

function setupModalHandlers() {
  document.querySelectorAll('[data-close]').forEach(btn => {
    btn.addEventListener('click', () => {
      const modalId = btn.getAttribute('data-close');
      document.getElementById(modalId)?.classList.remove('open');
    });
  });

  document.querySelectorAll('.modal-backdrop').forEach(backdrop => {
    backdrop.addEventListener('click', (e) => {
      if (e.target === backdrop) backdrop.classList.remove('open');
    });
  });

  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
      document.querySelectorAll('.modal-backdrop.open').forEach(m => m.classList.remove('open'));
    }
  });
}

function openNewBookingModal() {
  document.getElementById('form-booking').reset();
  document.getElementById('booking-items-list').innerHTML = '';
  document.getElementById('availability-preview').style.display = 'none';
  lastAvailabilityResult = null;

  // Set default start/end times (tomorrow 10:00 to 18:00)
  const tomorrow = new Date();
  tomorrow.setDate(tomorrow.getDate() + 1);
  tomorrow.setHours(10, 0, 0, 0);

  const endTomorrow = new Date(tomorrow);
  endTomorrow.setHours(18, 0, 0, 0);

  document.getElementById('booking-start').value = formatDateTimeInput(tomorrow);
  document.getElementById('booking-end').value = formatDateTimeInput(endTomorrow);

  // Add 1 default item row
  addItemPickerRow();

  document.getElementById('modal-booking').classList.add('open');
  triggerLiveAvailabilityCheck();
}

function formatDateTimeInput(date) {
  const pad = (num) => String(num).padStart(2, '0');
  const year = date.getFullYear();
  const month = pad(date.getMonth() + 1);
  const day = pad(date.getDate());
  const hours = pad(date.getHours());
  const minutes = pad(date.getMinutes());
  return `${year}-${month}-${day}T${hours}:${minutes}`;
}

function addItemPickerRow(selectedItemId = '', quantity = 1) {
  const list = document.getElementById('booking-items-list');
  const rowId = 'picker-row-' + Date.now() + '-' + Math.floor(Math.random() * 1000);

  const row = document.createElement('div');
  row.className = 'item-picker-row';
  row.id = rowId;

  const optionsHtml = catalogItems.map(item => {
    const selected = item.id == selectedItemId ? 'selected' : '';
    return `<option value="${item.id}" ${selected}>${escapeHtml(item.name)} (${item.category} &bull; ${item.sku})</option>`;
  }).join('');

  row.innerHTML = `
    <select class="form-select item-picker-select" onchange="triggerLiveAvailabilityCheck()">
      <option value="">-- Choose item from catalog --</option>
      ${optionsHtml}
    </select>
    <input type="number" class="form-input item-picker-qty" min="1" value="${quantity}" placeholder="Qty" oninput="triggerLiveAvailabilityCheck()">
    <button type="button" class="btn btn-secondary btn-sm" style="color: var(--danger);" onclick="removeItemPickerRow('${rowId}')">&times;</button>
  `;

  list.appendChild(row);
  triggerLiveAvailabilityCheck();
}

window.removeItemPickerRow = function(rowId) {
  document.getElementById(rowId)?.remove();
  triggerLiveAvailabilityCheck();
};

function getSelectedBookingItems() {
  const items = [];
  const rows = document.querySelectorAll('.item-picker-row');

  rows.forEach(row => {
    const select = row.querySelector('.item-picker-select');
    const qtyInput = row.querySelector('.item-picker-qty');
    const itemId = parseInt(select.value, 10);
    const qty = parseInt(qtyInput.value, 10);

    if (itemId && qty > 0) {
      items.push({ inventory_item_id: itemId, quantity_requested: qty });
    }
  });

  return items;
}

window.triggerLiveAvailabilityCheck = function() {
  clearTimeout(checkAvailabilityTimer);
  checkAvailabilityTimer = setTimeout(checkLiveAvailability, 300);
};

async function checkLiveAvailability() {
  const previewBox = document.getElementById('availability-preview');
  const msgEl = document.getElementById('availability-message');
  const shortagesList = document.getElementById('availability-shortages');
  const submitConfirmBtn = document.getElementById('btn-submit-confirm');

  const startTime = document.getElementById('booking-start').value;
  const endTime = document.getElementById('booking-end').value;
  const items = getSelectedBookingItems();

  if (!startTime || !endTime || items.length === 0) {
    previewBox.style.display = 'none';
    return;
  }

  // Visual state: checking
  previewBox.style.display = 'block';
  previewBox.className = 'availability-box checking';
  msgEl.innerHTML = '⚡ Checking warehouse &amp; reservation calendar...';
  shortagesList.style.display = 'none';

  const payload = {
    start_time: startTime,
    end_time: endTime,
    items: items
  };

  const res = await API.fetch('/api/events/check-availability', {
    method: 'POST',
    body: JSON.stringify(payload)
  });

  if (!res.ok) {
    previewBox.className = 'availability-box shortage';
    msgEl.innerHTML = `⚠️ Availability check error: ${escapeHtml(res.error)}`;
    return;
  }

  lastAvailabilityResult = res.data;
  const isAvailable = res.data.is_sufficient !== undefined ? res.data.is_sufficient : Boolean(res.data.available);

  if (isAvailable) {
    previewBox.className = 'availability-box available';
    msgEl.innerHTML = '✓ All requested items are fully available for this time window!';
    shortagesList.style.display = 'none';
    if (submitConfirmBtn) submitConfirmBtn.disabled = false;
  } else {
    previewBox.className = 'availability-box shortage';
    msgEl.innerHTML = `<strong>⚠️ Shortage Detected!</strong> Cannot confirm booking due to conflicting reservations or warehouse limits:`;

    shortagesList.innerHTML = (res.data.shortages || []).map(s => {
      const shortageAmount = s.short_by || s.shortage || 0;
      const itemId = s.item_id || s.inventory_item_id;
      const itemName = s.item_name || `Item #${itemId}`;
      return `
        <li class="shortage-item">
          <span><strong>${escapeHtml(itemName)}</strong></span>
          <span>Requested: <strong>${s.requested}</strong> | Available: <strong>${s.available}</strong> (Deficit: -${shortageAmount})</span>
        </li>
      `;
    }).join('');
    shortagesList.style.display = 'block';
  }
}

async function submitBooking(status) {
  const title = document.getElementById('booking-title').value.trim();
  const eventType = document.getElementById('booking-type').value;
  const attendees = parseInt(document.getElementById('booking-attendees').value, 10);
  const startTime = document.getElementById('booking-start').value;
  const endTime = document.getElementById('booking-end').value;
  const description = document.getElementById('booking-description').value.trim();
  const items = getSelectedBookingItems();

  if (!title || !startTime || !endTime) {
    UI.toast('Please fill in event title and schedule dates.', 'error');
    return;
  }

  if (new Date(startTime) >= new Date(endTime)) {
    UI.toast('Event start time must precede end time.', 'error');
    return;
  }

  if (items.length === 0) {
    UI.toast('Please select at least one item from the inventory catalog.', 'error');
    return;
  }

  // If submitting as confirmed and availability was not checked or failed
  if (status === 'CONFIRMED' && lastAvailabilityResult && !lastAvailabilityResult.available) {
    UI.toast('Cannot confirm: requested items have a shortage for this time window. Save as Draft or adjust items.', 'error');
    return;
  }

  const payload = {
    title,
    event_type: eventType,
    expected_attendees: attendees,
    start_time: startTime,
    end_time: endTime,
    description,
    status,
    items
  };

  const submitBtn = status === 'CONFIRMED' ? document.getElementById('btn-submit-confirm') : document.getElementById('btn-submit-draft');
  if (submitBtn) submitBtn.disabled = true;

  const res = await API.fetch('/api/events', {
    method: 'POST',
    body: JSON.stringify(payload)
  });

  if (submitBtn) submitBtn.disabled = false;

  if (res.ok) {
    UI.toast(`Event booking ${status.toLowerCase()} successfully!`, 'success');
    document.getElementById('modal-booking').classList.remove('open');
    await loadEvents();
  } else {
    UI.toast(`Booking error: ${res.error}`, 'error');
  }
}

window.confirmBooking = async function(eventId) {
  if (!confirm('Are you sure you want to confirm this booking and reserve inventory?')) return;
  const res = await API.fetch(`/api/events/${eventId}/confirm`, { method: 'POST' });
  if (res.ok) {
    UI.toast('Booking confirmed and inventory reserved!', 'success');
    await loadEvents();
  } else {
    UI.toast(`Cannot confirm booking: ${res.error}`, 'error');
  }
};

window.cancelBooking = async function(eventId) {
  if (!confirm('Cancel this event booking and release reserved items?')) return;
  const res = await API.fetch(`/api/events/${eventId}/cancel`, { method: 'POST' });
  if (res.ok) {
    UI.toast('Booking cancelled. Reserved stock released back to catalog.', 'info');
    await loadEvents();
  } else {
    UI.toast(`Cancellation failed: ${res.error}`, 'error');
  }
};

window.completeBooking = async function(eventId) {
  if (!confirm('Mark event completed? Any consumable items will be permanently deducted from inventory.')) return;
  const res = await API.fetch(`/api/events/${eventId}/complete`, { method: 'POST' });
  if (res.ok) {
    UI.toast('Event completed successfully!', 'success');
    await loadEvents();
  } else {
    UI.toast(`Completion failed: ${res.error}`, 'error');
  }
};

window.viewEventDetails = function(eventId) {
  const evt = allEvents.find(e => e.id === eventId);
  if (!evt) return;

  document.getElementById('details-title').textContent = evt.title;
  const content = document.getElementById('details-content');

  const itemsList = (evt.items || []).map(i => `
    <li style="display: flex; justify-content: space-between; padding: 0.4rem 0; border-bottom: 1px solid rgba(255,255,255,0.05);">
      <span>${escapeHtml(i.item ? i.item.name : 'Item #' + i.inventory_item_id)}</span>
      <strong>${i.quantity_requested} units</strong>
    </li>
  `).join('') || '<p style="color: var(--text-muted);">No items reserved.</p>';

  content.innerHTML = `
    <div style="margin-bottom: 1rem;">
      <div style="display: flex; justify-content: space-between; align-items: center;">
        <span style="color: var(--text-muted); font-size: 0.9rem;">Status:</span>
        <span>${UI.statusBadge(evt.status)}</span>
      </div>
      <div style="display: flex; justify-content: space-between; align-items: center; margin-top: 0.5rem;">
        <span style="color: var(--text-muted); font-size: 0.9rem;">Event Type:</span>
        <strong>${escapeHtml(evt.event_type)}</strong>
      </div>
      <div style="display: flex; justify-content: space-between; align-items: center; margin-top: 0.5rem;">
        <span style="color: var(--text-muted); font-size: 0.9rem;">Attendees:</span>
        <strong>${evt.expected_attendees || '—'}</strong>
      </div>
    </div>

    <div style="background: rgba(255,255,255,0.03); padding: 0.85rem; border-radius: var(--radius-md); margin-bottom: 1rem;">
      <div style="font-size: 0.8rem; color: var(--text-muted); margin-bottom: 0.25rem;">SCHEDULE WINDOW</div>
      <div style="font-size: 0.9rem;"><strong>From:</strong> ${UI.formatDate(evt.start_time)}</div>
      <div style="font-size: 0.9rem; margin-top: 0.25rem;"><strong>To:</strong> ${UI.formatDate(evt.end_time)}</div>
    </div>

    ${evt.description ? `
      <div style="margin-bottom: 1rem;">
        <div style="font-size: 0.8rem; color: var(--text-muted);">NOTES</div>
        <p style="font-size: 0.9rem;">${escapeHtml(evt.description)}</p>
      </div>
    ` : ''}

    <div>
      <div style="font-size: 0.85rem; color: var(--text-muted); margin-bottom: 0.5rem; text-transform: uppercase;">Reserved Inventory Items</div>
      <ul style="list-style: none;">
        ${itemsList}
      </ul>
    </div>
  `;

  document.getElementById('modal-event-details').classList.add('open');
};

function escapeHtml(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}
