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

  // 1. Update Bento Hero & Metric Cards
  const totalStock = inventory.total_physical_stock || 0;
  const unavailableStock = inventory.total_unavailable_stock || 0;
  const operationalStock = Math.max(0, totalStock - unavailableStock);
  const integrityPct = totalStock > 0 ? Math.round((operationalStock / totalStock) * 100) : 100;

  const totalStockEl = document.getElementById('metric-total-stock');
  if (totalStockEl) totalStockEl.textContent = totalStock;

  const meterValEl = document.getElementById('metric-stock-integrity-pct');
  if (meterValEl) meterValEl.textContent = `${integrityPct}% Operational`;

  const meterBarEl = document.getElementById('metric-stock-progress-bar');
  if (meterBarEl) meterBarEl.style.width = `${integrityPct}%`;

  const stockSubEl = document.getElementById('metric-stock-sub');
  if (stockSubEl) {
    stockSubEl.textContent = unavailableStock === 0 
      ? '0 units currently damaged/lost' 
      : `${unavailableStock} units damaged/under maintenance`;
  }

  // Catalog Diversity
  const totalItemsEl = document.getElementById('metric-total-items');
  if (totalItemsEl) totalItemsEl.textContent = inventory.total_items_count;

  // Real-Time Shortage Sentinel
  const atRiskEl = document.getElementById('metric-items-at-risk');
  const riskPill = document.getElementById('metric-risk-pill');
  const sentinelBadge = document.getElementById('sentinel-icon-badge');

  if (atRiskEl) {
    atRiskEl.textContent = inventory.items_at_risk_count;
    if (inventory.items_at_risk_count === 0) {
      atRiskEl.style.color = 'var(--success)';
      if (riskPill) {
        riskPill.className = 'bento-pill bento-pill--safe';
        riskPill.textContent = 'Nominal';
      }
      if (sentinelBadge) {
        sentinelBadge.style.background = 'rgba(16, 185, 129, 0.14)';
        sentinelBadge.style.color = '#10b981';
      }
    } else {
      atRiskEl.style.color = 'var(--danger)';
      if (riskPill) {
        riskPill.className = 'bento-pill bento-pill--danger';
        riskPill.textContent = `${inventory.items_at_risk_count} Depleted`;
      }
      if (sentinelBadge) {
        sentinelBadge.style.background = 'rgba(239, 68, 68, 0.16)';
        sentinelBadge.style.color = '#ef4444';
      }
    }
  }

  // Event Commitments
  const upcomingEl = document.getElementById('metric-upcoming-events');
  if (upcomingEl) upcomingEl.textContent = events.upcoming_confirmed_count;

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
    return;
  }

  const labels = distribution.map(d => d.category);
  const data = distribution.map(d => d.total_stock);

  const isLight = document.documentElement.getAttribute('data-theme') === 'light';

  const lightColors = [
    'rgba(79, 70, 229, 0.90)',
    'rgba(2, 132, 199, 0.90)',
    'rgba(124, 58, 237, 0.90)',
    'rgba(37, 99, 235, 0.90)',
    'rgba(217, 119, 6, 0.90)',
    'rgba(5, 150, 105, 0.90)',
    'rgba(99, 102, 241, 0.85)'
  ];

  const darkColors = [
    'rgba(99, 102, 241, 0.90)',
    'rgba(56, 189, 248, 0.90)',
    'rgba(139, 92, 246, 0.90)',
    'rgba(37, 99, 235, 0.90)',
    'rgba(245, 158, 11, 0.90)',
    'rgba(16, 185, 129, 0.90)',
    'rgba(196, 181, 253, 0.90)'
  ];

  const colors = isLight ? lightColors : darkColors;

  categoryChartInstance = new Chart(ctx, {
    type: 'doughnut',
    data: {
      labels: labels,
      datasets: [{
        data: data,
        backgroundColor: colors.slice(0, labels.length),
        borderColor: isLight ? '#ffffff' : '#080d1a',
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
            color: isLight ? '#334155' : '#94a3b8',
            font: { family: 'Roboto, sans-serif', size: window.innerWidth <= 640 ? 11 : 12 },
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
    const lightColors = [
      'rgba(79, 70, 229, 0.90)',
      'rgba(2, 132, 199, 0.90)',
      'rgba(124, 58, 237, 0.90)',
      'rgba(37, 99, 235, 0.90)',
      'rgba(217, 119, 6, 0.90)',
      'rgba(5, 150, 105, 0.90)',
      'rgba(99, 102, 241, 0.85)'
    ];
    const darkColors = [
      'rgba(99, 102, 241, 0.90)',
      'rgba(56, 189, 248, 0.90)',
      'rgba(139, 92, 246, 0.90)',
      'rgba(37, 99, 235, 0.90)',
      'rgba(245, 158, 11, 0.90)',
      'rgba(16, 185, 129, 0.90)',
      'rgba(196, 181, 253, 0.90)'
    ];
    const activeColors = isLight ? lightColors : darkColors;
    categoryChartInstance.data.datasets[0].backgroundColor = activeColors.slice(0, categoryChartInstance.data.labels.length);
    categoryChartInstance.data.datasets[0].borderColor = isLight ? '#ffffff' : '#080d1a';
    categoryChartInstance.options.plugins.legend.labels.color = isLight ? '#334155' : '#94a3b8';
    categoryChartInstance.update();
  }
});

function renderAtRiskTable(items) {
  const container = document.getElementById('at-risk-container');
  if (!items || items.length === 0) {
    container.innerHTML = `
      <div class="sentinel-empty-state">
        <div class="sentinel-shield-icon">
          <svg width="42" height="42" viewBox="0 0 24 24" fill="none" stroke="#10b981" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="display: inline-block;">
            <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>
            <path d="m9 12 2 2 4-4"/>
          </svg>
        </div>
        <div class="sentinel-status-headline">All Stock Safeguards Active</div>
        <p class="sentinel-status-desc">Every resource in your catalog maintains an operational cushion well above critical replenishment thresholds.</p>
        <div class="sentinel-metrics-strip">
          <span class="sentinel-metric-chip">Zero Critical Deficits</span>
          <span class="sentinel-metric-chip">Threshold Safeguards Active</span>
        </div>
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
