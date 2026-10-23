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
      
      // Auto-redirect if unauthorized (unless on login page or role toggle)
      if (response.status === 401) {
        if (!window.location.pathname.includes('/login') && !url.includes('/api/auth/toggle-role')) {
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
        username: usernameOrEmail,
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
   * Register new user (organizer or admin).
   */
  async register(username, email, password, role = 'organizer') {
    const res = await this.fetch('/api/auth/register', {
      method: 'POST',
      body: JSON.stringify({ username, email, password, role })
    });

    if (res.ok) {
      if (res.data && res.data.user) {
        this.currentUser = res.data.user;
      }
      if (res.data && res.data.csrf_token) {
        this.csrfToken = res.data.csrf_token;
        sessionStorage.setItem('csrf_token', res.data.csrf_token);
      }
      return { success: true, message: res.data ? res.data.message : 'Registration successful', user: res.data ? res.data.user : null };
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
  },

  /**
   * Update profile information (email and/or password).
   */
  async updateProfile(payload) {
    return await this.fetch('/api/auth/profile', {
      method: 'PUT',
      body: JSON.stringify(payload)
    });
  },

  /**
   * Permanently delete user account.
   */
  async deleteAccount() {
    return await this.fetch('/api/auth/account', {
      method: 'DELETE'
    });
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
        <div class="modal-container" style="max-width: 650px;">
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
   * Open the User Profile & Account Settings modal with Delete Account option.
   */
  async openProfileModal() {
    let modal = document.getElementById('modal-user-profile');
    if (!modal) {
      modal = document.createElement('div');
      modal.id = 'modal-user-profile';
      modal.className = 'modal-backdrop';
      modal.innerHTML = `
        <div class="modal-container" style="max-width: 580px;">
          <div class="modal-header">
            <div>
              <h3 class="modal-title">👤 User Profile</h3>
              <p style="font-size: 0.8rem; color: var(--text-muted); margin-top: 0.2rem;">Account credentials, privileges, and preferences</p>
            </div>
            <button class="modal-close" id="btn-close-profile-modal">&times;</button>
          </div>
          <div class="modal-body" id="profile-modal-body" style="padding: 1.25rem;">
            <p style="color: var(--text-muted); text-align: center; padding: 2rem;">Loading profile details...</p>
          </div>
        </div>
      `;
      document.body.appendChild(modal);

      const closeModal = () => {
        modal.classList.remove('open');
        modal.classList.remove('active');
      };

      document.getElementById('btn-close-profile-modal')?.addEventListener('click', closeModal);
      modal.addEventListener('click', (e) => {
        if (e.target === modal) closeModal();
      });
    }

    modal.classList.add('open');
    modal.classList.add('active');

    const body = document.getElementById('profile-modal-body');
    const user = await API.getCurrentUser();
    if (!user) {
      body.innerHTML = `
        <div style="text-align: center; padding: 2rem;">
          <p style="color: var(--danger);">Session expired. Please log in again.</p>
          <button class="btn btn-primary" onclick="window.location.href='/login'" style="margin-top: 1rem;">Go to Login</button>
        </div>
      `;
      return;
    }

    const initial = (user.username || 'U')[0].toUpperCase();
    const roleText = user.is_admin ? 'Administrator' : 'Event Organizer';
    const roleTagClass = user.is_admin ? 'role-admin' : 'role-organizer';
    const joinDate = user.created_at ? UI.formatDate(user.created_at) : 'Active';
    const eventsCount = user.events_count ?? 0;

    body.innerHTML = `
      <!-- Profile Hero Card -->
      <div class="profile-hero">
        <div class="profile-avatar-large">${initial}</div>
        <div class="profile-hero-info">
          <div class="profile-hero-username">
            <span>${user.username}</span>
            <span class="role-tag ${roleTagClass}">${user.is_admin ? 'Admin' : 'Organizer'}</span>
          </div>
          <div class="profile-hero-meta">
            <span>📧 ${user.email}</span>
            <span>📅 Joined: ${joinDate}</span>
          </div>
        </div>
      </div>

      <!-- Quick Stats Grid -->
      <div class="profile-stats-grid">
        <div class="profile-stat-box">
          <div class="profile-stat-label">System Role</div>
          <div class="profile-stat-val" style="font-size: 0.92rem;">${roleText}</div>
        </div>
        <div class="profile-stat-box">
          <div class="profile-stat-label">Booked Events</div>
          <div class="profile-stat-val">${eventsCount}</div>
        </div>
        <div class="profile-stat-box">
          <div class="profile-stat-label">Account Status</div>
          <div class="profile-stat-val" style="color: #34d399; font-size: 0.92rem;">Active ✓</div>
        </div>
      </div>

      <!-- Edit Profile Section -->
      <form id="form-edit-profile" style="margin-bottom: 1.5rem;">
        <div class="profile-section-title">
          <span>⚙️ Account Information</span>
        </div>

        <div class="profile-form-group">
          <label for="profile-input-username">Username</label>
          <input type="text" id="profile-input-username" class="form-input" value="${user.username}" disabled title="Username cannot be changed" style="opacity: 0.7; cursor: not-allowed;">
        </div>

        <div class="profile-form-group">
          <label for="profile-input-email">Email Address</label>
          <input type="email" id="profile-input-email" class="form-input" value="${user.email}" required>
        </div>

        <details style="margin-bottom: 1rem; border: 1px solid var(--border-color); border-radius: var(--radius-sm); padding: 0.5rem 0.75rem; background: var(--bg-surface);">
          <summary style="cursor: pointer; font-size: 0.85rem; font-weight: 600; color: var(--text-main);">🔒 Change Password (Optional)</summary>
          <div style="margin-top: 0.75rem;">
            <div class="profile-form-group">
              <label for="profile-input-current-pwd">Current Password</label>
              <input type="password" id="profile-input-current-pwd" class="form-input" placeholder="Required if changing password">
            </div>
            <div class="profile-form-group">
              <label for="profile-input-new-pwd">New Password</label>
              <input type="password" id="profile-input-new-pwd" class="form-input" placeholder="Minimum 6 characters">
            </div>
          </div>
        </details>

        <div style="display: flex; justify-content: flex-end;">
          <button type="submit" id="btn-save-profile" class="btn btn-primary btn-sm">💾 Save Changes</button>
        </div>
      </form>

      <!-- Danger Zone: Delete Account -->
      <div class="profile-danger-zone">
        <div class="profile-danger-header">
          <div class="profile-danger-title">⚠️ Danger Zone</div>
        </div>
        <div class="profile-danger-desc">
          Permanently delete your user account, organized events, and preferences. Once confirmed, this action cannot be undone.
        </div>

        <div id="delete-account-trigger-section">
          <button type="button" id="btn-trigger-delete" class="btn btn-danger btn-sm">🗑️ Delete Account</button>
        </div>

        <div id="delete-account-confirm-box" class="profile-delete-confirm-box" style="display: none;">
          <div style="font-size: 0.85rem; color: #ef4444; font-weight: 600; margin-bottom: 0.5rem;">
            ⚠️ Final Confirmation Required
          </div>
          <p style="font-size: 0.82rem; color: var(--text-muted); margin-bottom: 0.75rem;">
            To permanently delete this account, please type your username <strong style="color: var(--text-main);">${user.username}</strong> below:
          </p>
          <div style="margin-bottom: 0.75rem;">
            <input type="text" id="input-confirm-delete-name" class="form-input" placeholder="Type ${user.username} to confirm" autocomplete="off">
          </div>
          <div style="display: flex; gap: 0.5rem; justify-content: flex-end; flex-wrap: wrap;">
            <button type="button" id="btn-cancel-delete" class="btn btn-secondary btn-sm">Cancel</button>
            <button type="button" id="btn-confirm-delete-submit" class="btn btn-danger btn-sm" disabled>Confirm Permanent Deletion</button>
          </div>
        </div>
      </div>
    `;

    // Attach Save Changes handler
    document.getElementById('form-edit-profile')?.addEventListener('submit', async (e) => {
      e.preventDefault();
      const saveBtn = document.getElementById('btn-save-profile');
      if (saveBtn) {
        saveBtn.disabled = true;
        saveBtn.textContent = 'Saving...';
      }

      const email = document.getElementById('profile-input-email').value.trim();
      const currentPassword = document.getElementById('profile-input-current-pwd').value;
      const newPassword = document.getElementById('profile-input-new-pwd').value;

      const payload = { email };
      if (newPassword) {
        payload.current_password = currentPassword;
        payload.new_password = newPassword;
      }

      try {
        const res = await API.updateProfile(payload);
        if (res.ok && res.data) {
          API.currentUser = res.data.user;
          UI.toast('Profile updated successfully!', 'success');
          UI.updateNavbarUser(res.data.user);
          setTimeout(() => UI.openProfileModal(), 400);
        } else {
          UI.toast(res.error || 'Failed to update profile', 'error');
        }
      } catch (err) {
        UI.toast(err.message || 'Error updating profile', 'error');
      } finally {
        if (saveBtn) {
          saveBtn.disabled = false;
          saveBtn.textContent = '💾 Save Changes';
        }
      }
    });

    // Attach Delete Account handlers
    const triggerBtn = document.getElementById('btn-trigger-delete');
    const confirmBox = document.getElementById('delete-account-confirm-box');
    const confirmInput = document.getElementById('input-confirm-delete-name');
    const confirmSubmitBtn = document.getElementById('btn-confirm-delete-submit');
    const cancelDeleteBtn = document.getElementById('btn-cancel-delete');

    triggerBtn?.addEventListener('click', () => {
      triggerBtn.style.display = 'none';
      confirmBox.style.display = 'block';
      confirmInput.value = '';
      confirmInput.focus();
    });

    cancelDeleteBtn?.addEventListener('click', () => {
      confirmBox.style.display = 'none';
      triggerBtn.style.display = 'inline-block';
    });

    confirmInput?.addEventListener('input', () => {
      if (confirmInput.value.trim() === user.username) {
        confirmSubmitBtn.disabled = false;
      } else {
        confirmSubmitBtn.disabled = true;
      }
    });

    confirmSubmitBtn?.addEventListener('click', async () => {
      if (confirmInput.value.trim() !== user.username) return;

      confirmSubmitBtn.disabled = true;
      confirmSubmitBtn.textContent = 'Deleting Account...';

      try {
        const res = await API.deleteAccount();
        if (res.ok && res.data && res.data.deleted) {
          UI.toast('Your account has been permanently deleted.', 'info');
          modal.classList.remove('open');
          modal.classList.remove('active');
          setTimeout(() => {
            window.location.href = '/login';
          }, 600);
        } else {
          confirmSubmitBtn.disabled = false;
          confirmSubmitBtn.textContent = 'Confirm Permanent Deletion';
          UI.toast(res.error || 'Failed to delete account.', 'error');
        }
      } catch (err) {
        confirmSubmitBtn.disabled = false;
        confirmSubmitBtn.textContent = 'Confirm Permanent Deletion';
        UI.toast(err.message || 'Network error deleting account.', 'error');
      }
    });
  },

  /**
   * Update navbar user badge and admin-only visibility in-place.
   */
  updateNavbarUser(user) {
    if (!user) return;
    const roleTag = document.querySelector('#nav-user-display .role-tag');
    if (roleTag) {
      roleTag.className = `role-tag ${user.is_admin ? 'role-admin' : 'role-organizer'}`;
      roleTag.textContent = user.is_admin ? 'Admin' : 'Organizer';
    }
    const userName = document.querySelector('#nav-user-display .user-name');
    if (userName) {
      userName.textContent = `👤 ${user.username}`;
    }
    document.querySelectorAll('.admin-only').forEach(el => {
      el.style.display = user.is_admin ? '' : 'none';
    });
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
        <div class="user-badge" id="btn-nav-user-badge" title="Click to view Profile & Settings" style="cursor: pointer;">
          <span class="user-name">👤 ${user.username}</span>
          <span class="role-tag ${roleClass}">${roleText}</span>
          <button id="btn-toggle-role" class="btn btn-secondary btn-sm" title="Toggle role between Admin and Organizer" style="font-size: 0.72rem; padding: 0.15rem 0.45rem; margin-left: 0.25rem;">⇄ Switch</button>
        </div>
        <button id="btn-nav-profile" class="btn btn-secondary btn-sm" title="User Profile & Settings">Profile</button>
        <button id="btn-nav-logout" class="btn btn-secondary btn-sm">Log Out</button>
      `;

      // Profile modal triggers
      document.getElementById('btn-nav-profile')?.addEventListener('click', () => {
        UI.openProfileModal();
      });

      document.getElementById('btn-nav-user-badge')?.addEventListener('click', (e) => {
        // Only trigger if user did not click the switch role button inside the badge
        if (e.target && (e.target.id === 'btn-toggle-role' || e.target.closest('#btn-toggle-role'))) {
          return;
        }
        UI.openProfileModal();
      });

      document.getElementById('btn-toggle-role')?.addEventListener('click', async (e) => {
        e.preventDefault();
        e.stopPropagation();
        const btn = document.getElementById('btn-toggle-role');
        if (btn) {
          btn.disabled = true;
          btn.textContent = '...';
        }
        try {
          const res = await API.fetch('/api/auth/toggle-role', { method: 'POST' });
          if (res.ok && res.data && res.data.user) {
            API.currentUser = res.data.user;
            if (res.data.csrf_token) {
              API.csrfToken = res.data.csrf_token;
              sessionStorage.setItem('csrf_token', res.data.csrf_token);
            }
            UI.toast(`Switched mode to: ${res.data.role.toUpperCase()}`, 'info');
            UI.updateNavbarUser(res.data.user);
            window.dispatchEvent(new CustomEvent('roleChanged', { detail: { role: res.data.role, user: res.data.user } }));

            setTimeout(() => {
              window.location.reload();
            }, 350);
          } else {
            if (btn) {
              btn.disabled = false;
              btn.textContent = '⇄ Switch';
            }
            UI.toast('Failed to switch role: ' + (res.error || 'Server error'), 'error');
          }
        } catch (err) {
          if (btn) {
            btn.disabled = false;
            btn.textContent = '⇄ Switch';
          }
          UI.toast('Failed to switch role: ' + (err.message || 'Network error'), 'error');
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
