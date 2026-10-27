/**
 * Inventory Catalog & Management Studio Controller
 * Lu.ma Inspired Edition
 *
 * Features:
 * - Fluid tab switching between Item Studio (Add New Item) and Warehouse Catalog table
 * - Real-time metadata pill synchronisation (Category, Unit, Consumable toggle)
 * - Single-row search & filters with live debounced filtering
 * - Obsidian glass data table with interactive stock adjustment, deletion, and audit history
 */

let allInventoryItems = [];
let currentUser = null;

document.addEventListener('DOMContentLoaded', async () => {
  currentUser = await API.getCurrentUser();
  await UI.initNavbar();

  setupStudioTabs();
  setupPillSync();
  setupFilterHandlers();
  setupModalHandlers();
  await loadInventory();

  // Initial tab restoration (defaults to create studio or user's stored preference)
  const initialHash = window.location.hash.toLowerCase();
  const savedTab = localStorage.getItem('inventory_tab');
  if (initialHash === '#catalog' || (savedTab === 'catalog' && initialHash !== '#create' && initialHash !== '#new')) {
    switchInventoryTab('catalog');
  } else {
    switchInventoryTab('create');
  }

  // Add Item form submission
  document.getElementById('form-add-item')?.addEventListener('submit', handleAddItemSubmit);

  // Adjust Stock form submission
  document.getElementById('form-adjust-stock')?.addEventListener('submit', handleAdjustStockSubmit);

  // Listen for role toggle in navbar
  window.addEventListener('roleChanged', (e) => {
    if (e.detail && e.detail.user) {
      currentUser = e.detail.user;
      renderInventoryTable();
    }
  });
});

/* ==========================================================================
   Studio Tab Switching (Add New Item Studio vs. Warehouse Catalog)
   ========================================================================== */
function setupStudioTabs() {
  const tabCreate = document.getElementById('tab-btn-create-item');
  const tabCatalog = document.getElementById('tab-btn-catalog');
  const btnOpenAdd = document.getElementById('btn-open-add-item');
  const btnCancelAdd = document.getElementById('btn-cancel-add-item');

  tabCreate?.addEventListener('click', () => {
    if (!currentUser || !currentUser.is_admin) {
      UI.toast('Administrator access required to register new items. Switch role in the navbar.', 'warning');
      return;
    }
    switchInventoryTab('create');
  });

  tabCatalog?.addEventListener('click', () => switchInventoryTab('catalog'));

  btnOpenAdd?.addEventListener('click', () => {
    if (!currentUser || !currentUser.is_admin) {
      UI.toast('Administrator access required to register new items. Switch role in the navbar.', 'warning');
      return;
    }
    switchInventoryTab('create');
  });

  btnCancelAdd?.addEventListener('click', () => switchInventoryTab('catalog'));
}

function switchInventoryTab(target) {
  const tabCreate = document.getElementById('tab-btn-create-item');
  const tabCatalog = document.getElementById('tab-btn-catalog');
  const panelCreate = document.getElementById('panel-create-item');
  const panelCatalog = document.getElementById('panel-warehouse-catalog');

  if (target === 'create') {
    tabCreate?.classList.add('active');
    tabCreate?.setAttribute('aria-selected', 'true');
    tabCatalog?.classList.remove('active');
    tabCatalog?.setAttribute('aria-selected', 'false');

    if (panelCreate) panelCreate.style.display = 'block';
    if (panelCatalog) panelCatalog.style.display = 'none';

    localStorage.setItem('inventory_tab', 'create');
    window.location.hash = 'create';

    // Auto-focus the item name input
    setTimeout(() => {
      document.getElementById('add-name')?.focus();
    }, 50);
  } else {
    tabCatalog?.classList.add('active');
    tabCatalog?.setAttribute('aria-selected', 'true');
    tabCreate?.classList.remove('active');
    tabCreate?.setAttribute('aria-selected', 'false');

    if (panelCreate) panelCreate.style.display = 'none';
    if (panelCatalog) panelCatalog.style.display = 'block';

    localStorage.setItem('inventory_tab', 'catalog');
    window.location.hash = 'catalog';
  }
}

/* ==========================================================================
   Metadata Pill Synchronisation & Quick Click Handlers
   ========================================================================== */
function setupPillSync() {
  const categorySelect = document.getElementById('add-category');
  const unitInput = document.getElementById('add-unit');
  const consumableCheckbox = document.getElementById('add-is-consumable');

  const pillCategory = document.getElementById('pill-category-select');
  const pillUnit = document.getElementById('pill-unit-select');
  const pillType = document.getElementById('pill-type-select');

  const labelCategory = document.getElementById('category-pill-label');
  const labelUnit = document.getElementById('unit-pill-label');
  const labelType = document.getElementById('type-pill-label');

  // Category sync
  categorySelect?.addEventListener('change', () => {
    if (labelCategory) {
      labelCategory.textContent = `Category: ${categorySelect.value}`;
    }
  });

  pillCategory?.addEventListener('click', () => {
    categorySelect?.focus();
  });

  // Unit sync
  unitInput?.addEventListener('input', () => {
    const val = unitInput.value.trim() || 'pieces';
    if (labelUnit) {
      labelUnit.textContent = `Unit: ${val}`;
    }
  });

  pillUnit?.addEventListener('click', () => {
    unitInput?.focus();
  });

  // Consumable sync
  consumableCheckbox?.addEventListener('change', () => {
    if (labelType) {
      labelType.textContent = consumableCheckbox.checked ? 'Consumable Stock' : 'Reusable Equipment';
    }
  });

  pillType?.addEventListener('click', () => {
    if (consumableCheckbox) {
      consumableCheckbox.checked = !consumableCheckbox.checked;
      consumableCheckbox.dispatchEvent(new Event('change'));
    }
  });
}

/* ==========================================================================
   Data Fetching & Table Rendering
   ========================================================================== */
async function loadInventory() {
  const tbody = document.getElementById('inventory-tbody');
  const res = await API.fetch('/api/inventory/items');

  if (!res.ok) {
    if (tbody) {
      tbody.innerHTML = `
        <tr>
          <td colspan="10" style="text-align: center; color: var(--danger); padding: 2.5rem;">
            Failed to load inventory: ${escapeHtml(res.error || 'Network error')}
          </td>
        </tr>
      `;
    }
    return;
  }

  allInventoryItems = res.data.items || [];

  // Update topbar inventory count badge
  const countBadge = document.getElementById('inventory-count-badge');
  if (countBadge) {
    countBadge.textContent = allInventoryItems.length;
  }

  renderInventoryTable();
}

function renderInventoryTable() {
  const tbody = document.getElementById('inventory-tbody');
  if (!tbody) return;

  const queryInput = document.getElementById('inventory-search');
  const query = (queryInput?.value || '').toLowerCase().trim();
  const categoryFilter = document.getElementById('filter-category')?.value || '';
  const statusFilter = document.getElementById('filter-status')?.value || '';

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
        <td colspan="10" style="text-align: center; color: var(--luma-text-muted); padding: 3rem 1.5rem;">
          <div style="font-size: 1.5rem; margin-bottom: 0.5rem;">📦</div>
          <div style="font-weight: 600; color: var(--luma-text-main, #ffffff);">No inventory items found</div>
          <div style="font-size: 0.85rem; color: var(--luma-text-dim); margin-top: 0.25rem;">
            Adjust search criteria or click &ldquo;Add New Item&rdquo; to register warehouse stock.
          </div>
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
          <strong style="color: var(--luma-text-main, #ffffff); font-size: 0.94rem;">${escapeHtml(item.name)}</strong>
          ${item.description ? `<div style="font-size: 0.78rem; color: var(--luma-text-dim); margin-top: 0.15rem;">${escapeHtml(item.description)}</div>` : ''}
        </td>
        <td><span style="color: var(--luma-text-muted, rgba(255,255,255,0.85));">${escapeHtml(item.category)}</span></td>
        <td><span style="font-weight: 600; color: var(--luma-text-main, #ffffff);">${item.total_stock}</span> <span style="font-size: 0.75rem; color: var(--luma-text-dim);">${escapeHtml(item.unit || 'units')}</span></td>
        <td style="${item.unavailable_stock > 0 ? 'color: var(--luma-warn, #fbbf24); font-weight: 600;' : 'color: var(--luma-text-dim);'}">${item.unavailable_stock}</td>
        <td><strong style="color: var(--luma-net-avail, #38bdf8); font-size: 1.05rem;">${netPhysical}</strong></td>
        <td style="color: var(--luma-text-muted);">${item.minimum_threshold}</td>
        <td>
          <span class="badge inventory-type-badge ${item.is_consumable ? 'badge-info' : ''}">
            ${typeLabel}
          </span>
        </td>
        <td>${UI.statusBadge(item.status)}</td>
        <td>
          <div style="display: flex; gap: 0.4rem; align-items: center;">
            ${adminActions}
            <button class="btn btn-secondary btn-sm" onclick="openHistoryModal(${item.id}, '${escapeHtml(item.name).replace(/'/g, "\\'")}')">History</button>
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

/* ==========================================================================
   Add Item Submit Handler
   ========================================================================== */
async function handleAddItemSubmit(e) {
  e.preventDefault();
  if (!currentUser || !currentUser.is_admin) {
    UI.toast('Administrator access required to register new items. Switch role in the navbar.', 'warning');
    return;
  }

  const submitBtn = document.getElementById('btn-submit-add-item');
  if (submitBtn) {
    submitBtn.disabled = true;
    submitBtn.textContent = 'Registering Item...';
  }

  const name = document.getElementById('add-name')?.value.trim();
  const category = document.getElementById('add-category')?.value || 'Audio';
  const unit = (document.getElementById('add-unit')?.value || 'pieces').trim();
  const totalStock = parseInt(document.getElementById('add-total-stock')?.value, 10);
  const minThreshold = parseInt(document.getElementById('add-threshold')?.value, 10);
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

  if (submitBtn) {
    submitBtn.disabled = false;
    submitBtn.textContent = 'Save Item to Catalog';
  }

  if (res.ok) {
    UI.toast(`Item &ldquo;${name}&rdquo; successfully registered in warehouse catalog!`, 'success');
    document.getElementById('form-add-item')?.reset();

    // Reset pill labels to defaults
    const labelCat = document.getElementById('category-pill-label');
    const labelUnit = document.getElementById('unit-pill-label');
    const labelType = document.getElementById('type-pill-label');
    if (labelCat) labelCat.textContent = 'Category: Audio';
    if (labelUnit) labelUnit.textContent = 'Unit: pieces';
    if (labelType) labelType.textContent = 'Reusable Equipment';

    // Switch to catalog tab and reload
    switchInventoryTab('catalog');
    await loadInventory();
  } else {
    UI.toast('Failed to register item: ' + (res.error || 'Unknown error'), 'error');
  }
}

/* ==========================================================================
   Modals: Stock Adjustment, Deletion, and Transaction History
   ========================================================================== */
function setupModalHandlers() {
  // Confirm Delete Item button
  document.getElementById('btn-confirm-delete-item')?.addEventListener('click', async () => {
    const itemId = document.getElementById('delete-item-id')?.value;
    if (!itemId) return;

    const btn = document.getElementById('btn-confirm-delete-item');
    if (btn) {
      btn.disabled = true;
      btn.textContent = 'Deleting...';
    }

    const res = await API.fetch(`/api/inventory/${itemId}`, {
      method: 'DELETE'
    });

    if (btn) {
      btn.disabled = false;
      btn.textContent = 'Confirm Delete';
    }

    if (res.ok) {
      UI.toast('Item removed from warehouse catalog successfully!', 'success');
      closeModal('modal-delete-item');
      await loadInventory();
    } else {
      UI.toast('Failed to delete item: ' + (res.error || 'Server error'), 'error');
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
    UI.toast('Administrator access required to delete items. Switch role in navbar.', 'warning');
    return;
  }
  const item = allInventoryItems.find(i => i.id === itemId);
  if (!item) return;

  const inputId = document.getElementById('delete-item-id');
  const nameEl = document.getElementById('delete-item-name');
  const infoEl = document.getElementById('delete-item-info');

  if (inputId) inputId.value = item.id;
  if (nameEl) nameEl.textContent = item.name;
  if (infoEl) {
    infoEl.textContent = `SKU: ${item.sku} | Category: ${item.category} | Current Stock: ${item.total_stock} ${item.unit || 'pieces'}`;
  }
  openModal('modal-delete-item');
};

// Open Adjust Stock modal
window.openAdjustModal = function(itemId) {
  if (!currentUser || !currentUser.is_admin) {
    UI.toast('Administrator access required to adjust stock. Switch role in navbar.', 'warning');
    return;
  }
  const item = allInventoryItems.find(i => i.id === itemId);
  if (!item) return;

  const idInput = document.getElementById('adjust-item-id');
  const titleEl = document.getElementById('adjust-item-title');
  const detailsEl = document.getElementById('adjust-item-details');
  const qtyInput = document.getElementById('adjust-quantity');
  const reasonInput = document.getElementById('adjust-reason');

  if (idInput) idInput.value = item.id;
  if (titleEl) titleEl.textContent = `${item.name} (${item.sku})`;
  if (detailsEl) {
    detailsEl.textContent = `Total Physical: ${item.total_stock} | Unavailable (Damaged/Maintenance): ${item.unavailable_stock} | Net Available: ${item.net_physical_stock || (item.total_stock - item.unavailable_stock)}`;
  }
  if (qtyInput) qtyInput.value = 1;
  if (reasonInput) reasonInput.value = '';

  openModal('modal-adjust-stock');
};

// Adjust Stock submit handler
async function handleAdjustStockSubmit(e) {
  e.preventDefault();
  if (!currentUser || !currentUser.is_admin) {
    UI.toast('Administrator access required to adjust stock.', 'warning');
    return;
  }

  const itemId = document.getElementById('adjust-item-id')?.value;
  const submitBtn = document.getElementById('btn-submit-adjust');
  if (submitBtn) {
    submitBtn.disabled = true;
    submitBtn.textContent = 'Applying...';
  }

  const action = document.getElementById('adjust-type')?.value;
  const qty = parseInt(document.getElementById('adjust-quantity')?.value, 10);
  const reason = (document.getElementById('adjust-reason')?.value || '').trim();

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

  if (submitBtn) {
    submitBtn.disabled = false;
    submitBtn.textContent = 'Apply Adjustment';
  }

  if (res.ok) {
    UI.toast('Warehouse stock adjusted successfully!', 'success');
    closeModal('modal-adjust-stock');
    await loadInventory();
  } else {
    UI.toast('Adjustment failed: ' + (res.error || 'Server error'), 'error');
  }
}

// Transaction History modal
window.openHistoryModal = async function(itemId, itemName) {
  const modalTitle = document.getElementById('history-modal-title');
  const tbody = document.getElementById('history-tbody');
  if (modalTitle) modalTitle.textContent = `Transaction History: ${itemName}`;
  if (tbody) {
    tbody.innerHTML = `
      <tr>
        <td colspan="4" style="text-align: center; color: var(--luma-text-muted); padding: 2rem;">Loading history...</td>
      </tr>
    `;
  }
  openModal('modal-history');

  const res = await API.fetch(`/api/inventory/items/${itemId}/transactions`);
  if (!res.ok) {
    if (tbody) {
      tbody.innerHTML = `
        <tr>
          <td colspan="4" style="text-align: center; color: var(--danger); padding: 2rem;">
            Failed to load transactions: ${escapeHtml(res.error || 'Network error')}
          </td>
        </tr>
      `;
    }
    return;
  }

  const txs = res.data.transactions || [];
  if (txs.length === 0) {
    if (tbody) {
      tbody.innerHTML = `
        <tr>
          <td colspan="4" style="text-align: center; color: var(--luma-text-muted); padding: 2rem;">
            No transaction audit entries for this item.
          </td>
        </tr>
      `;
    }
    return;
  }

  if (tbody) {
    tbody.innerHTML = txs.map(t => {
      const deltaColor = t.quantity_delta > 0 ? '#10b981' : t.quantity_delta < 0 ? '#f43f5e' : 'var(--luma-text-muted)';
      const deltaSign = t.quantity_delta > 0 ? `+${t.quantity_delta}` : `${t.quantity_delta}`;
      const txTypeFormatted = t.transaction_type.replace(/_/g, ' ');

      return `
        <tr>
          <td style="font-size: 0.82rem; color: var(--luma-text-muted);">${UI.formatDate(t.created_at)}</td>
          <td><span class="badge inventory-history-badge">${txTypeFormatted}</span></td>
          <td><strong style="color: ${deltaColor};">${deltaSign}</strong></td>
          <td style="color: var(--luma-text-muted, rgba(255,255,255,0.85));">${escapeHtml(t.reason || '—')}</td>
        </tr>
      `;
    }).join('');
  }
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
