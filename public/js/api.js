/**
 * Central API Client & Authentication Management
 * Event Inventory Management System
 */

const API = {
  csrfToken: sessionStorage.getItem('csrf_token') || null,
  currentUser: null,

  /**
   * Wrapper around fetch with credentials, CSRF headers, and error handling.
   */
  async fetch(url, options = {}) {
    const defaultHeaders = {
      'Content-Type': 'application/json',
      'Accept': 'application/json',
      'X-Target-Path': url
    };

    // Attach CSRF token on mutating methods
    const method = (options.method || 'GET').toUpperCase();
    if (['POST', 'PUT', 'DELETE', 'PATCH'].includes(method)) {
      if (this.csrfToken) {
        defaultHeaders['X-CSRF-Token'] = this.csrfToken;
      }
    }

    const mergedOptions = {
      ...options,
      credentials: 'include',
      headers: {
        ...defaultHeaders,
        ...(options.headers || {})
      }
    };

    try {
      const response = await fetch(url, mergedOptions);
      
      // Auto-redirect if unauthorized (unless on login page)
      if (response.status === 401) {
        if (!window.location.pathname.includes('/login')) {
          sessionStorage.removeItem('csrf_token');
          window.location.href = '/login';
        }
        const data = await response.json().catch(() => ({}));
        return { ok: false, status: 401, error: data.error || 'Authentication required' };
      }

      const data = await response.json().catch(() => ({}));

      if (!response.ok) {
        return {
          ok: false,
          status: response.status,
          error: data.error || `Request failed with status ${response.status}`,
          details: data
        };
      }

      return { ok: true, status: response.status, data };
    } catch (err) {
      console.error('Network / Fetch Error:', err);
      return { ok: false, status: 0, error: 'Network error or server unreachable. Please check connection.' };
    }
  },

  /**
   * Fetch current authenticated user.
   */
  async getCurrentUser() {
    const res = await this.fetch('/api/auth/me');
    if (res.ok && res.data.user) {
      this.currentUser = res.data.user;
      if (res.data.csrf_token) {
        this.csrfToken = res.data.csrf_token;
        sessionStorage.setItem('csrf_token', res.data.csrf_token);
      }
      return this.currentUser;
    }
    this.currentUser = null;
    return null;
  },

  /**
   * Log in user with credentials.
   */
  async login(usernameOrEmail, password) {
    const res = await this.fetch('/api/auth/login', {
      method: 'POST',
      body: JSON.stringify({
        username_or_email: usernameOrEmail,
        password: password
      })
    });

    if (res.ok) {
      this.currentUser = res.data.user;
      if (res.data.csrf_token) {
        this.csrfToken = res.data.csrf_token;
        sessionStorage.setItem('csrf_token', res.data.csrf_token);
      }
      return { success: true, user: res.data.user };
    }
    return { success: false, error: res.error };
  },

  /**
   * Register new event organizer.
   */
  async register(username, email, password) {
    const res = await this.fetch('/api/auth/register', {
      method: 'POST',
      body: JSON.stringify({ username, email, password })
    });

    if (res.ok) {
      return { success: true, message: res.data.message };
    }
    return { success: false, error: res.error };
  },

  /**
   * Log out current user and redirect.
   */
  async logout() {
    await this.fetch('/api/auth/logout', { method: 'POST' });
    this.csrfToken = null;
    this.currentUser = null;
    sessionStorage.removeItem('csrf_token');
    window.location.href = '/login';
  },

  /**
   * Fetch active alerts.
   */
  async getAlerts(severity = null) {
    let url = '/api/alerts';
    if (severity) url += `?severity=${encodeURIComponent(severity)}`;
    const res = await this.fetch(url);
    return res.ok ? res.data : { alerts: [], total_active: 0 };
  },

  /**
   * Resolve an alert.
   */
  async resolveAlert(alertId) {
    const res = await this.fetch(`/api/alerts/${alertId}/resolve`, {
      method: 'POST'
    });
    return res.ok ? { success: true, data: res.data } : { success: false, error: res.error };
  }
};

/**
 * Global UI Helpers
 */
const UI = {
  /**
   * Display floating toast message.
   */
  toast(message, type = 'info') {
    let container = document.getElementById('toast-container');
    if (!container) {
      container = document.createElement('div');
      container.id = 'toast-container';
      container.className = 'toast-container';
      document.body.appendChild(container);
    }

    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.innerHTML = `
      <span>${type === 'success' ? '✓' : type === 'error' ? '✕' : 'ℹ'}</span>
      <span>${message}</span>
    `;

    container.appendChild(toast);

    setTimeout(() => {
      toast.style.opacity = '0';
      toast.style.transform = 'translateY(10px)';
      toast.style.transition = 'all 0.3s ease';
      setTimeout(() => toast.remove(), 300);
    }, 4000);
  },

  /**
   * Refresh alert badge counter in navbar.
   */
  async refreshAlertBadge() {
    const badge = document.getElementById('nav-alert-badge');
    if (!badge) return;

    try {
      const data = await API.getAlerts();
      const count = data.total_active || 0;
      if (count > 0) {
        badge.textContent = count > 99 ? '99+' : count;
        badge.style.display = 'flex';
        badge.style.background = (data.critical_count > 0) ? 'var(--danger)' : 'var(--warning)';
      } else {
        badge.style.display = 'none';
      }
    } catch (e) {
      // Non-blocking
    }
  },

  /**
   * Open the Alert Center modal showing live warnings.
   */
  async openAlertsModal() {
    let modal = document.getElementById('modal-alerts-center');
    if (!modal) {
      modal = document.createElement('div');
      modal.id = 'modal-alerts-center';
      modal.className = 'modal-backdrop';
      modal.innerHTML = `
        <div class="modal" style="max-width: 650px;">
          <div class="modal-header">
            <div>
              <h3 class="modal-title">🔔 Alert & Shortage Radar</h3>
              <p style="font-size: 0.8rem; color: var(--text-muted); margin-top: 0.2rem;">Live stock threshold warnings & ML predictions</p>
            </div>
            <button class="modal-close" id="btn-close-alerts-modal">&times;</button>
          </div>
          <div class="modal-body" id="alerts-modal-content" style="max-height: 60vh; overflow-y: auto;">
            <p style="color: var(--text-muted); text-align: center; padding: 2rem;">Loading active alerts...</p>
          </div>
          <div class="modal-footer">
            <button class="btn btn-secondary" id="btn-dismiss-alerts-modal">Close</button>
          </div>
        </div>
      `;
      document.body.appendChild(modal);

      document.getElementById('btn-close-alerts-modal')?.addEventListener('click', () => {
        modal.classList.remove('active');
      });
      document.getElementById('btn-dismiss-alerts-modal')?.addEventListener('click', () => {
        modal.classList.remove('active');
      });
    }

    modal.classList.add('active');
    const content = document.getElementById('alerts-modal-content');

    const data = await API.getAlerts();
    const alerts = data.alerts || [];

    if (alerts.length === 0) {
      content.innerHTML = `
        <div style="text-align: center; padding: 2.5rem 1rem;">
          <div style="font-size: 2.5rem; margin-bottom: 0.5rem;">✨</div>
          <h4 style="color: #34d399; margin-bottom: 0.25rem;">All Systems Healthy</h4>
          <p style="color: var(--text-muted); font-size: 0.85rem;">No active stock shortages or high shortage risks detected.</p>
        </div>
      `;
      return;
    }

    content.innerHTML = alerts.map(a => `
      <div class="alert-item-card ${a.severity.toLowerCase()}" id="alert-card-${a.id}">
        <div class="alert-item-header">
          <span style="font-weight: 600; font-size: 0.95rem; color: var(--text-main);">
            ${a.item_name ? a.item_name : 'General Notice'}
          </span>
          <span class="alert-severity-tag ${a.severity.toLowerCase()}">${a.severity}</span>
        </div>
        <div class="alert-message-text">${a.message}</div>
        ${a.recommended_action ? `
          <div class="alert-recommendation">
            💡 <strong>Action:</strong> ${a.recommended_action}
          </div>
        ` : ''}
        <div class="alert-footer-bar">
          <span>🕒 ${UI.formatDate(a.created_at)}</span>
          <button class="btn btn-secondary btn-sm" onclick="UI.handleResolveAlert(${a.id})">
            ✓ Mark Resolved
          </button>
        </div>
      </div>
    `).join('');
  },

  /**
   * Handle user resolving an alert.
   */
  async handleResolveAlert(alertId) {
    const res = await API.resolveAlert(alertId);
    if (res.success) {
      UI.toast(`Alert #${alertId} marked resolved.`, 'success');
      const card = document.getElementById(`alert-card-${alertId}`);
      if (card) {
        card.style.opacity = '0';
        card.style.transform = 'scale(0.95)';
        card.style.transition = 'all 0.3s ease';
        setTimeout(() => card.remove(), 300);
      }
      UI.refreshAlertBadge();
    } else {
      UI.toast(res.error || 'Failed to resolve alert.', 'error');
    }
  },

  /**
   * Get current theme ('light' or 'dark').
   */
  getTheme() {
    return document.documentElement.getAttribute('data-theme') || localStorage.getItem('theme') || 'dark';
  },

  /**
   * Get theme icon for button.
   */
  getThemeIcon() {
    return this.getTheme() === 'light' ? '☀️' : '🌙';
  },

  /**
   * Initialize theme from localStorage.
   */
  initTheme() {
    const theme = localStorage.getItem('theme') || 'dark';
    document.documentElement.setAttribute('data-theme', theme);
    const btns = document.querySelectorAll('.theme-toggle-btn');
    btns.forEach(btn => {
      btn.textContent = theme === 'light' ? '☀️' : '🌙';
      btn.title = theme === 'light' ? 'Switch to Dark Mode' : 'Switch to Light Mode';
    });
  },

  /**
   * Toggle between light and dark theme.
   */
  toggleTheme() {
    const current = this.getTheme();
    const next = current === 'light' ? 'dark' : 'light';
    document.documentElement.setAttribute('data-theme', next);
    localStorage.setItem('theme', next);

    const btns = document.querySelectorAll('.theme-toggle-btn');
    btns.forEach(btn => {
      btn.textContent = next === 'light' ? '☀️' : '🌙';
      btn.title = next === 'light' ? 'Switch to Dark Mode' : 'Switch to Light Mode';
    });

    window.dispatchEvent(new CustomEvent('themeChanged', { detail: { theme: next } }));
    this.toast(`Switched to ${next === 'light' ? 'Light' : 'Dark'} Mode`, 'info');
  },

  /**
   * Initialize standard navigation bar on application pages.
   */
  async initNavbar() {
    this.initTheme();
    const user = await API.getCurrentUser();
    if (!user) {
      if (!window.location.pathname.includes('/login')) {
        window.location.href = '/login';
      }
      return;
    }

    // Populate user badge, theme toggle & alert bell
    const userDisplay = document.getElementById('nav-user-display');
    if (userDisplay) {
      const roleClass = user.is_admin ? 'role-admin' : 'role-organizer';
      const roleText = user.is_admin ? 'Admin' : 'Organizer';
      userDisplay.innerHTML = `
        <button id="btn-theme-toggle" class="theme-toggle-btn" title="Switch Theme (Light / Dark)">
          ${UI.getThemeIcon()}
        </button>
        <button id="btn-nav-alerts" class="nav-alert-btn" title="View Active Stock & Risk Alerts">
          🔔
          <span id="nav-alert-badge" class="nav-alert-badge" style="display: none;">0</span>
        </button>
        <div class="user-badge">
          <span>👤 ${user.username}</span>
          <span class="role-tag ${roleClass}">${roleText}</span>
          <button id="btn-toggle-role" class="btn btn-secondary btn-sm" title="Toggle role between Admin and Organizer" style="font-size: 0.72rem; padding: 0.15rem 0.45rem; margin-left: 0.25rem;">⇄ Switch</button>
        </div>
        <button id="btn-nav-logout" class="btn btn-secondary btn-sm">Log Out</button>
      `;

      document.getElementById('btn-toggle-role')?.addEventListener('click', async () => {
        const res = await API.fetch('/api/auth/toggle-role', { method: 'POST' });
        if (res.ok) {
          UI.toast(`Switched mode to: ${res.data.role.toUpperCase()}`, 'info');
          setTimeout(() => window.location.reload(), 400);
        } else {
          UI.toast('Failed to switch role: ' + res.error, 'error');
        }
      });

      document.getElementById('btn-nav-logout')?.addEventListener('click', () => {
        API.logout();
      });

      document.getElementById('btn-theme-toggle')?.addEventListener('click', () => {
        UI.toggleTheme();
      });

      document.getElementById('btn-nav-alerts')?.addEventListener('click', () => {
        UI.openAlertsModal();
      });

      // Poll/refresh alert count
      UI.refreshAlertBadge();
    }

    // Adjust UI based on admin role
    if (!user.is_admin) {
      document.querySelectorAll('.admin-only').forEach(el => {
        el.style.display = 'none';
      });
    }

    // Highlight active link
    const currentPath = window.location.pathname;
    document.querySelectorAll('.nav-link').forEach(link => {
      if (link.getAttribute('href') === currentPath) {
        link.classList.add('active');
      }
    });
  },

  /**
   * Format ISO date strings into local readable format.
   */
  formatDate(isoString) {
    if (!isoString) return '—';
    const d = new Date(isoString);
    if (isNaN(d.getTime())) return isoString;
    return d.toLocaleString('en-US', {
      month: 'short',
      day: 'numeric',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit'
    });
  },

  /**
   * Format status badge HTML.
   */
  statusBadge(status) {
    const lower = (status || '').toLowerCase();
    let badgeClass = 'badge-info';
    if (['in_stock', 'confirmed', 'completed'].includes(lower)) {
      badgeClass = 'badge-in-stock';
    } else if (['low_stock', 'draft'].includes(lower)) {
      badgeClass = 'badge-low-stock';
    } else if (['out_of_stock', 'cancelled'].includes(lower)) {
      badgeClass = 'badge-out-of-stock';
    }
    const cleanLabel = status.replace(/_/g, ' ');
    return `<span class="badge ${badgeClass}">${cleanLabel}</span>`;
  }
};

// Auto-initialize theme on load
UI.initTheme();
document.addEventListener('DOMContentLoaded', () => {
  UI.initTheme();
});
