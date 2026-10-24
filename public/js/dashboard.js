/**
 * Dashboard Controller
 * Loads and renders live metrics from /api/reports/dashboard-summary
 */

let categoryChartInstance = null;

document.addEventListener('DOMContentLoaded', async () => {
  await UI.initNavbar();
  await loadDashboardData();

  window.addEventListener('roleChanged', () => {
    loadDashboardData();
  });
});

async function loadDashboardData() {
  const res = await API.fetch('/api/reports/dashboard-summary');
  if (!res.ok) {
    UI.toast('Failed to load dashboard metrics: ' + res.error, 'error');
    return;
  }

  const { inventory, events } = res.data;

  // 1. Update 4 Metric Cards
  document.getElementById('metric-total-items').textContent = inventory.total_items_count;
  document.getElementById('metric-total-stock').textContent = inventory.total_physical_stock;
  document.getElementById('metric-stock-sub').textContent = 
    `${inventory.total_unavailable_stock} units currently damaged/lost`;

  const atRiskEl = document.getElementById('metric-items-at-risk');
  atRiskEl.textContent = inventory.items_at_risk_count;
  if (inventory.items_at_risk_count === 0) {
    atRiskEl.style.color = 'var(--success)';
  } else {
    atRiskEl.style.color = 'var(--danger)';
  }

  document.getElementById('metric-upcoming-events').textContent = events.upcoming_confirmed_count;

  // 2. Render Chart.js Chart
  renderCategoryChart(inventory.category_distribution);

  // 3. Render Items At Risk List
  renderAtRiskTable(inventory.items_at_risk);

  // 4. Render AI Shortage Radar
  await loadAiShortageRisks();

  // 5. Render Recent Events Table
  renderRecentEventsTable(events.recent_events);
}

function renderCategoryChart(distribution) {
  const ctx = document.getElementById('categoryChart').getContext('2d');
  
  if (categoryChartInstance) {
    categoryChartInstance.destroy();
  }

  if (!distribution || distribution.length === 0) {
    // Show empty placeholder
    return;
  }

  const labels = distribution.map(d => d.category);
  const data = distribution.map(d => d.total_stock);

  const colors = [
    'rgba(228, 12, 12, 0.88)',
    'rgba(95, 148, 113, 0.88)',
    'rgba(92, 7, 7, 0.88)',
    'rgba(245, 158, 11, 0.88)',
    'rgba(180, 20, 20, 0.88)',
    'rgba(111, 166, 130, 0.88)',
    'rgba(254, 242, 241, 0.75)'
  ];

  const isLight = document.documentElement.getAttribute('data-theme') === 'light';

  categoryChartInstance = new Chart(ctx, {
    type: 'doughnut',
    data: {
      labels: labels,
      datasets: [{
        data: data,
        backgroundColor: colors.slice(0, labels.length),
        borderColor: isLight ? '#ffffff' : '#0a0000',
        borderWidth: 2,
        hoverOffset: 6
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: {
          position: window.innerWidth <= 640 ? 'bottom' : 'right',
          labels: {
            color: isLight ? '#475569' : '#d4b8b6',
            font: { family: 'Outfit', size: window.innerWidth <= 640 ? 11 : 12 },
            boxWidth: window.innerWidth <= 640 ? 12 : 16,
            padding: window.innerWidth <= 640 ? 8 : 12
          }
        },
        tooltip: {
          callbacks: {
            label: function(context) {
              return ` ${context.label}: ${context.raw} units`;
            }
          }
        }
      },
      cutout: '65%'
    }
  });
}

// Update chart dynamically when user toggles light/dark mode
window.addEventListener('themeChanged', (e) => {
  if (categoryChartInstance) {
    const isLight = e.detail.theme === 'light';
    categoryChartInstance.data.datasets[0].borderColor = isLight ? '#ffffff' : '#0a0000';
    categoryChartInstance.options.plugins.legend.labels.color = isLight ? '#475569' : '#d4b8b6';
    categoryChartInstance.update();
  }
});

function renderAtRiskTable(items) {
  const container = document.getElementById('at-risk-container');
  if (!items || items.length === 0) {
    container.innerHTML = `
      <div style="text-align: center; padding: 2rem; color: var(--success);">
        <p style="font-size: 1.5rem; margin-bottom: 0.5rem;">✓</p>
        <p style="font-weight: 500;">All inventory stocks are above safety thresholds!</p>
      </div>
    `;
    return;
  }

  const rows = items.map(item => `
    <tr>
      <td>
        <strong>${escapeHtml(item.name)}</strong>
        <div class="sku-badge" style="display: inline-block; margin-left: 0.5rem;">${item.sku}</div>
      </td>
      <td>${item.category}</td>
      <td>
        <strong style="color: ${item.net_physical_stock === 0 ? 'var(--danger)' : 'var(--warning)'};">
          ${item.net_physical_stock}
        </strong> / min ${item.minimum_threshold}
      </td>
      <td>${UI.statusBadge(item.status)}</td>
    </tr>
  `).join('');

  container.innerHTML = `
    <table class="data-table">
      <thead>
        <tr>
          <th>Item</th>
          <th>Category</th>
          <th>Net / Min</th>
          <th>Status</th>
        </tr>
      </thead>
      <tbody>
        ${rows}
      </tbody>
    </table>
  `;
}

function renderRecentEventsTable(events) {
  const tbody = document.getElementById('recent-events-tbody');
  if (!events || events.length === 0) {
    tbody.innerHTML = `
      <tr>
        <td colspan="6" style="text-align: center; color: var(--text-muted); padding: 2rem;">
          No events created yet. Click "+ New Booking" to schedule your first event.
        </td>
      </tr>
    `;
    return;
  }

  tbody.innerHTML = events.map(evt => {
    const itemsCount = evt.items ? evt.items.reduce((acc, i) => acc + i.quantity_requested, 0) : 0;
    const itemsSummary = evt.items && evt.items.length > 0
      ? `${evt.items.length} item types (${itemsCount} units)`
      : 'None';

    const windowText = `${UI.formatDate(evt.start_time)} &rarr; ${UI.formatDate(evt.end_time)}`;

    return `
      <tr>
        <td><strong>${escapeHtml(evt.title)}</strong></td>
        <td style="text-transform: capitalize;">${evt.event_type}</td>
        <td style="font-size: 0.85rem; color: var(--text-muted);">${windowText}</td>
        <td>${itemsSummary}</td>
        <td>${UI.statusBadge(evt.status)}</td>
        <td>
          <a href="/events" class="btn btn-secondary btn-sm">Details</a>
        </td>
      </tr>
    `;
  }).join('');
}

function escapeHtml(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

async function loadAiShortageRisks() {
  const container = document.getElementById('ai-risk-container');
  if (!container) return;

  const res = await API.fetch('/api/ml/shortage-risks?days_ahead=14&min_level=medium');
  if (!res.ok) {
    container.innerHTML = `<p style="color: var(--text-muted); font-size: 0.9rem;">Unable to load shortage radar: ${res.error}</p>`;
    return;
  }

  const risks = res.data.items_at_risk || [];
  if (risks.length === 0) {
    container.innerHTML = `
      <div style="text-align: center; padding: 1.5rem; color: var(--success);">
        <p style="font-size: 1.25rem; margin-bottom: 0.25rem;">✓</p>
        <p style="font-weight: 500;">AI Shortage Radar Clear: No catalog items at Medium or High risk over the next 14 days!</p>
      </div>
    `;
    return;
  }

  const rows = risks.map(r => {
    const badgeClass = r.risk_level === 'High' ? 'badge-out-of-stock' : 'badge-low-stock';
    return `
      <tr>
        <td><strong>${escapeHtml(r.item_name)}</strong></td>
        <td>${escapeHtml(r.category)}</td>
        <td>${r.current_stock} units</td>
        <td><strong>${r.total_reserved_upcoming} units</strong></td>
        <td><span class="badge ${badgeClass}">${r.risk_level} (${Math.round(r.risk_score * 100)}%)</span></td>
        <td style="font-size: 0.85rem; color: var(--text-muted);">${escapeHtml(r.reason)}</td>
      </tr>
    `;
  }).join('');

  container.innerHTML = `
    <table class="data-table">
      <thead>
        <tr>
          <th>Item</th>
          <th>Category</th>
          <th>Available Cushion</th>
          <th>14d Demand</th>
          <th>Risk Level</th>
          <th>AI Diagnostic Reason</th>
        </tr>
      </thead>
      <tbody>
        ${rows}
      </tbody>
    </table>
  `;
}
