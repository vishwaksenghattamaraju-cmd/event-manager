/**
 * Inventory Catalog Controller
 */

let allInventoryItems = [];
let currentUser = null;

document.addEventListener('DOMContentLoaded', async () => {
  currentUser = await API.getCurrentUser();
  await UI.initNavbar();

  setupModalHandlers();
  setupFilterHandlers();
  await loadInventory();

  // Add Item form submit
  document.getElementById('form-add-item')?.addEventListener('submit', handleAddItemSubmit);

  // Adjust Stock form submit
  document.getElementById('form-adjust-stock')?.addEventListener('submit', handleAdjustStockSubmit);
});

async function loadInventory() {
  const tbody = document.getElementById('inventory-tbody');
  const res = await API.fetch('/api/inventory/items');

  if (!res.ok) {
    tbody.innerHTML = `
      <tr>
        <td colspan="10" style="text-align: center; color: var(--danger); padding: 2rem;">
          Failed to load inventory: ${res.error}
        </td>
      </tr>
    `;
    return;
  }

  allInventoryItems = res.data.items || [];
  renderInventoryTable();
}

function renderInventoryTable() {
  const tbody = document.getElementById('inventory-tbody');
  const query = document.getElementById('inventory-search').value.toLowerCase().trim();
  const categoryFilter = document.getElementById('filter-category').value;
  const statusFilter = document.getElementById('filter-status').value;

  const filtered = allInventoryItems.filter(item => {
    if (query && !item.name.toLowerCase().includes(query) && !item.sku.toLowerCase().includes(query)) {
      return false;
    }
    if (categoryFilter && item.category !== categoryFilter) {
      return false;
    }
    if (statusFilter && item.status !== statusFilter) {
      return false;
    }
    return true;
  });

  if (filtered.length === 0) {
    tbody.innerHTML = `
      <tr>
        <td colspan="10" style="text-align: center; color: var(--text-muted); padding: 2rem;">
          No items match the current search or filters.
        </td>
      </tr>
    `;
    return;
  }

  const isAdmin = currentUser && currentUser.is_admin;

  tbody.innerHTML = filtered.map(item => {
    const netPhysical = item.total_stock - item.unavailable_stock;
    const typeLabel = item.is_consumable ? 'Consumable' : 'Reusable';

    const adminActions = isAdmin ? `
      <button class="btn btn-secondary btn-sm" onclick="openAdjustModal(${item.id})" title="Adjust stock">Adjust</button>
      <button class="btn btn-danger btn-sm" onclick="openDeleteModal(${item.id})" title="Delete item">Delete</button>
    ` : '';

    return `
      <tr>
        <td><span class="sku-badge">${escapeHtml(item.sku)}</span></td>
        <td>
          <strong>${escapeHtml(item.name)}</strong>
          ${item.description ? `<div style="font-size: 0.8rem; color: var(--text-dim);">${escapeHtml(item.description)}</div>` : ''}
        </td>
        <td>${escapeHtml(item.category)}</td>
        <td>${item.total_stock}</td>
        <td style="${item.unavailable_stock > 0 ? 'color: var(--warning);' : ''}">${item.unavailable_stock}</td>
        <td><strong>${netPhysical}</strong></td>
        <td>${item.minimum_threshold}</td>
        <td><span class="badge ${item.is_consumable ? 'badge-info' : ''}" style="background: rgba(255,255,255,0.05);">${typeLabel}</span></td>
        <td>${UI.statusBadge(item.status)}</td>
        <td>
          <div style="display: flex; gap: 0.4rem; align-items: center;">
            ${adminActions}
            <button class="btn btn-secondary btn-sm" onclick="openHistoryModal(${item.id}, '${escapeHtml(item.name)}')">History</button>
          </div>
        </td>
      </tr>
    `;
  }).join('');
}

function setupFilterHandlers() {
  document.getElementById('inventory-search')?.addEventListener('input', renderInventoryTable);
  document.getElementById('filter-category')?.addEventListener('change', renderInventoryTable);
  document.getElementById('filter-status')?.addEventListener('change', renderInventoryTable);
}

function setupModalHandlers() {
  // Open Add Item modal
  document.getElementById('btn-open-add-item')?.addEventListener('click', () => {
    if (!currentUser || !currentUser.is_admin) {
      UI.toast('Administrator access required to add new items. Use "Switch Role" in the navbar.', 'warning');
      return;
    }
    document.getElementById('form-add-item').reset();
    openModal('modal-add-item');
  });

  // Confirm Delete Item button
  document.getElementById('btn-confirm-delete-item')?.addEventListener('click', async () => {
    const itemId = document.getElementById('delete-item-id').value;
    if (!itemId) return;

    const btn = document.getElementById('btn-confirm-delete-item');
    btn.disabled = true;
    btn.textContent = 'Deleting...';

    const res = await API.fetch(`/api/inventory/${itemId}`, {
      method: 'DELETE'
    });

    btn.disabled = false;
    btn.textContent = 'Confirm Delete';

    if (res.ok) {
      UI.toast('Item removed from inventory successfully!', 'success');
      closeModal('modal-delete-item');
      await loadInventory();
    } else {
      UI.toast('Failed to delete item: ' + res.error, 'error');
    }
  });

  // Close modals on buttons with data-close
  document.querySelectorAll('[data-close]').forEach(btn => {
    btn.addEventListener('click', () => {
      const modalId = btn.getAttribute('data-close');
      closeModal(modalId);
    });
  });

  // Close on backdrop click
  document.querySelectorAll('.modal-backdrop').forEach(backdrop => {
    backdrop.addEventListener('click', (e) => {
      if (e.target === backdrop) {
        closeModal(backdrop.id);
      }
    });
  });

  // Close on Escape key
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
      document.querySelectorAll('.modal-backdrop.open').forEach(modal => {
        closeModal(modal.id);
      });
    }
  });
}

function openModal(id) {
  document.getElementById(id)?.classList.add('open');
}

function closeModal(id) {
  document.getElementById(id)?.classList.remove('open');
}

// Open Delete Item modal
window.openDeleteModal = function(itemId) {
  if (!currentUser || !currentUser.is_admin) {
    UI.toast('Administrator access required to delete items. Use "Switch Role" in the navbar.', 'warning');
    return;
  }
  const item = allInventoryItems.find(i => i.id === itemId);
  if (!item) return;

  document.getElementById('delete-item-id').value = item.id;
  document.getElementById('delete-item-name').textContent = item.name;
  document.getElementById('delete-item-info').textContent = 
    `SKU: ${item.sku} | Category: ${item.category} | Current Stock: ${item.total_stock} ${item.unit || 'pieces'}`;
  openModal('modal-delete-item');
};

// Add Item submit handler
async function handleAddItemSubmit(e) {
  e.preventDefault();
  if (!currentUser || !currentUser.is_admin) {
    UI.toast('Administrator access required to register new items. Use "Switch Role" in the navbar.', 'warning');
    return;
  }
  const submitBtn = document.getElementById('btn-submit-add-item');
  submitBtn.disabled = true;
  submitBtn.textContent = 'Saving...';

  const name = document.getElementById('add-name').value.trim();
  const category = document.getElementById('add-category').value;
  const unit = (document.getElementById('add-unit')?.value || 'pieces').trim();
  const totalStock = parseInt(document.getElementById('add-total-stock').value, 10);
  const minThreshold = parseInt(document.getElementById('add-threshold').value, 10);
  const cost = parseFloat(document.getElementById('add-cost')?.value || '0');
  const description = (document.getElementById('add-description')?.value || '').trim();
  const isConsumable = document.getElementById('add-is-consumable')?.checked || false;

  const payload = {
    name,
    category,
    unit,
    total_stock: isNaN(totalStock) ? 0 : totalStock,
    minimum_threshold: isNaN(minThreshold) ? 2 : minThreshold,
    purchase_cost: isNaN(cost) ? 0.0 : cost,
    description,
    is_consumable: isConsumable,
    item_type: isConsumable ? 'consumable' : 'returnable'
  };

  const res = await API.fetch('/api/inventory/items', {
    method: 'POST',
    body: JSON.stringify(payload)
  });

  submitBtn.disabled = false;
  submitBtn.textContent = 'Save Item';

  if (res.ok) {
    UI.toast(`Item '${name}' created successfully!`, 'success');
    closeModal('modal-add-item');
    await loadInventory();
  } else {
    UI.toast('Failed to create item: ' + res.error, 'error');
  }
}

// Adjust Stock modal
window.openAdjustModal = function(itemId) {
  const item = allInventoryItems.find(i => i.id === itemId);
  if (!item) return;

  document.getElementById('adjust-item-id').value = item.id;
  document.getElementById('adjust-item-title').textContent = `${item.name} (${item.sku})`;
  document.getElementById('adjust-item-details').textContent = 
    `Total Physical: ${item.total_stock} | Unavailable (Damaged/Lost): ${item.unavailable_stock} | Net Available: ${item.net_physical_stock}`;
  
  document.getElementById('adjust-quantity').value = 1;
  document.getElementById('adjust-reason').value = '';
  openModal('modal-adjust-stock');
};

// Adjust Stock submit handler
async function handleAdjustStockSubmit(e) {
  e.preventDefault();
  const itemId = document.getElementById('adjust-item-id').value;
  const submitBtn = document.getElementById('btn-submit-adjust');
  submitBtn.disabled = true;
  submitBtn.textContent = 'Applying...';

  const action = document.getElementById('adjust-type').value;
  const qty = parseInt(document.getElementById('adjust-quantity').value, 10);
  const reason = document.getElementById('adjust-reason').value.trim();

  let endpoint = `/api/inventory/${itemId}/adjust`;
  let payload = { reason };

  if (action === 'INCREASE') {
    payload.change_amount = qty;
  } else if (action === 'DECREASE') {
    payload.change_amount = -qty;
  } else if (action === 'MARK_DAMAGED') {
    endpoint = `/api/inventory/${itemId}/unavailable`;
    payload.amount = qty;
    payload.status_kind = 'damaged';
  } else if (action === 'MARK_LOST') {
    endpoint = `/api/inventory/${itemId}/unavailable`;
    payload.amount = qty;
    payload.status_kind = 'maintenance';
  }

  const res = await API.fetch(endpoint, {
    method: 'POST',
    body: JSON.stringify(payload)
  });

  submitBtn.disabled = false;
  submitBtn.textContent = 'Apply Adjustment';

  if (res.ok) {
    UI.toast('Stock adjusted successfully!', 'success');
    closeModal('modal-adjust-stock');
    await loadInventory();
  } else {
    UI.toast('Adjustment failed: ' + res.error, 'error');
  }
};

// Transaction History modal
window.openHistoryModal = async function(itemId, itemName) {
  const modalTitle = document.getElementById('history-modal-title');
  const tbody = document.getElementById('history-tbody');
  modalTitle.textContent = `Transaction History: ${itemName}`;
  tbody.innerHTML = `
    <tr>
      <td colspan="4" style="text-align: center; color: var(--text-muted); padding: 2rem;">Loading history...</td>
    </tr>
  `;
  openModal('modal-history');

  const res = await API.fetch(`/api/inventory/items/${itemId}/transactions`);
  if (!res.ok) {
    tbody.innerHTML = `
      <tr>
        <td colspan="4" style="text-align: center; color: var(--danger); padding: 2rem;">Failed to load transactions: ${res.error}</td>
      </tr>
    `;
    return;
  }

  const txs = res.data.transactions || [];
  if (txs.length === 0) {
    tbody.innerHTML = `
      <tr>
        <td colspan="4" style="text-align: center; color: var(--text-muted); padding: 2rem;">No transaction log entries for this item.</td>
      </tr>
    `;
    return;
  }

  tbody.innerHTML = txs.map(t => {
    const deltaColor = t.quantity_delta > 0 ? 'var(--success)' : t.quantity_delta < 0 ? 'var(--danger)' : 'var(--text-muted)';
    const deltaSign = t.quantity_delta > 0 ? `+${t.quantity_delta}` : `${t.quantity_delta}`;
    const txTypeFormatted = t.transaction_type.replace(/_/g, ' ');

    return `
      <tr>
        <td style="font-size: 0.85rem; color: var(--text-muted);">${UI.formatDate(t.created_at)}</td>
        <td><span class="badge" style="background: rgba(255,255,255,0.06);">${txTypeFormatted}</span></td>
        <td><strong style="color: ${deltaColor};">${deltaSign}</strong></td>
        <td>${escapeHtml(t.reason || '—')}</td>
      </tr>
    `;
  }).join('');
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
