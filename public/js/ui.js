/**
 * ui.js - Shared UI utilities, notifications, and interaction helpers for The Matrix
 * Provides fallback implementations and prevents 404 console errors.
 */

(function () {
  'use strict';

  window.UI = window.UI || {
    /**
     * Display a temporary floating toast notification
     * @param {string} message - Message to display
     * @param {string} [type='info'] - 'info', 'success', 'warning', or 'error'
     * @param {number} [durationMs=3500] - Duration in milliseconds
     */
    showToast: function (message, type, durationMs) {
      if (typeof window.showToast === 'function') {
        return window.showToast(message, type);
      }

      let toastContainer = document.getElementById('global-toast-container');
      if (!toastContainer) {
        toastContainer = document.createElement('div');
        toastContainer.id = 'global-toast-container';
        toastContainer.style.cssText =
          'position:fixed;bottom:24px;right:24px;z-index:9999;display:flex;flex-direction:column;gap:8px;pointer-events:none;';
        document.body.appendChild(toastContainer);
      }

      const toast = document.createElement('div');
      const bgColors = {
        success: '#10b981',
        error: '#ef4444',
        warning: '#f59e0b',
        info: '#ff7700',
      };
      const bg = bgColors[type] || bgColors.info;

      toast.style.cssText = `background:${bg};color:#fff;padding:12px 18px;border-radius:10px;font-size:14px;font-weight:600;box-shadow:0 8px 24px rgba(0,0,0,0.3);pointer-events:auto;transition:opacity 0.3s ease, transform 0.3s ease;transform:translateY(10px);opacity:0;`;
      toast.textContent = message;

      toastContainer.appendChild(toast);
      requestAnimationFrame(() => {
        toast.style.transform = 'translateY(0)';
        toast.style.opacity = '1';
      });

      setTimeout(() => {
        toast.style.opacity = '0';
        toast.style.transform = 'translateY(10px)';
        setTimeout(() => toast.remove(), 350);
      }, durationMs || 3500);
    },

    /**
     * Escape special HTML characters to prevent XSS
     * @param {string} str
     * @returns {string}
     */
    escapeHtml: function (str) {
      if (!str) return '';
      return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');
    },
  };
})();

