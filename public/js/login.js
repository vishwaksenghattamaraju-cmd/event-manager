/**
 * Login & Registration Controller
 * Simple, Minimal, Fast & Reliable
 */

// Global Password Visibility Toggle (persistent show/hide on click)
window.togglePasswordVisibility = function(inputId, btn) {
  const input = document.getElementById(inputId);
  if (!input) return;

  const currentVal = input.value;
  const isCurrentlyVisible = input.type === 'text';
  const shouldShow = !isCurrentlyVisible;

  // Toggle type
  input.type = shouldShow ? 'text' : 'password';
  input.value = currentVal; // preserve value exactly

  const targetBtn = btn || document.getElementById(`btn-toggle-${inputId}`);
  if (targetBtn) {
    const eyeIcon = targetBtn.querySelector('.eye-icon');
    const eyeOffIcon = targetBtn.querySelector('.eye-off-icon');

    if (shouldShow) {
      if (eyeIcon) eyeIcon.style.display = 'none';
      if (eyeOffIcon) eyeOffIcon.style.display = 'block';
      targetBtn.setAttribute('aria-label', 'Hide password');
      targetBtn.setAttribute('title', 'Hide password');
      targetBtn.setAttribute('aria-pressed', 'true');
    } else {
      if (eyeIcon) eyeIcon.style.display = 'block';
      if (eyeOffIcon) eyeOffIcon.style.display = 'none';
      targetBtn.setAttribute('aria-label', 'Show password');
      targetBtn.setAttribute('title', 'Show password');
      targetBtn.setAttribute('aria-pressed', 'false');
    }
  }

  // Restore cursor position to end of input without clearing
  try {
    input.focus();
    const len = input.value.length;
    input.setSelectionRange(len, len);
  } catch (e) {
    // Ignore on unsupported browsers
  }
};

document.addEventListener('DOMContentLoaded', async () => {
  // If already logged in, redirect directly to dashboard
  try {
    const user = await API.getCurrentUser();
    if (user) {
      window.location.replace('/dashboard');
      return;
    }
  } catch (err) {
    console.warn('Session check skipped:', err);
  }

  const tabLogin = document.getElementById('tab-login');
  const tabRegister = document.getElementById('tab-register');
  const formLogin = document.getElementById('form-login');
  const formRegister = document.getElementById('form-register');
  const loginError = document.getElementById('login-error');
  const regError = document.getElementById('reg-error');

  // Password Visibility Toggle Handlers
  const bindToggle = (btnId, inputId) => {
    const btn = document.getElementById(btnId);
    if (!btn) return;
    btn.type = 'button';
    btn.addEventListener('click', (e) => {
      e.preventDefault();
      e.stopPropagation();
      window.togglePasswordVisibility(inputId, btn);
    });
    btn.addEventListener('keydown', (e) => {
      if (e.key === ' ' || e.key === 'Enter') {
        e.preventDefault();
        e.stopPropagation();
        window.togglePasswordVisibility(inputId, btn);
      }
    });
  };

  bindToggle('btn-toggle-login-password', 'login-password');
  bindToggle('btn-toggle-reg-password', 'reg-password');

  // 1-Click Demo Login Autofill Handlers
  const populateDemo = (username, password, roleLabel) => {
    // Ensure Sign In tab is active
    if (!tabLogin?.classList.contains('active')) {
      tabLogin?.click();
    }

    const userInput = document.getElementById('login-username');
    const passInput = document.getElementById('login-password');
    if (userInput) {
      userInput.value = username;
      userInput.dispatchEvent(new Event('input', { bubbles: true }));
    }
    if (passInput) {
      passInput.value = password;
      passInput.dispatchEvent(new Event('input', { bubbles: true }));
    }

    if (loginError) loginError.style.display = 'none';

    if (window.UI?.toast) {
      UI.toast(`Autofilled ${roleLabel} demo credentials!`, 'info');
    }

    // Focus submit button so user can press Enter or click Login
    document.getElementById('btn-login-submit')?.focus();
  };

  document.getElementById('btn-fill-admin')?.addEventListener('click', (e) => {
    e.preventDefault();
    populateDemo('admin', 'Admin@123', 'Administrator');
  });

  document.getElementById('btn-fill-organizer')?.addEventListener('click', (e) => {
    e.preventDefault();
    populateDemo('organizer', 'Organizer@123', 'Organizer');
  });

  // Tab switching
  tabLogin?.addEventListener('click', () => {
    tabLogin.classList.add('active');
    tabRegister?.classList.remove('active');
    tabLogin.setAttribute('aria-selected', 'true');
    tabRegister?.setAttribute('aria-selected', 'false');
    if (formLogin) formLogin.style.display = 'block';
    if (formRegister) formRegister.style.display = 'none';
    if (loginError) loginError.style.display = 'none';
    document.getElementById('login-username')?.focus();
  });

  tabRegister?.addEventListener('click', () => {
    tabRegister.classList.add('active');
    tabLogin?.classList.remove('active');
    tabRegister.setAttribute('aria-selected', 'true');
    tabLogin?.setAttribute('aria-selected', 'false');
    if (formRegister) formRegister.style.display = 'block';
    if (formLogin) formLogin.style.display = 'none';
    if (regError) regError.style.display = 'none';
    document.getElementById('reg-username')?.focus();
  });

  // Check URL Hash for tab selection
  if (window.location.hash === '#register') {
    tabRegister?.click();
  }

  // Handle Login submission
  formLogin?.addEventListener('submit', async (e) => {
    e.preventDefault();
    if (loginError) loginError.style.display = 'none';
    const submitBtn = document.getElementById('btn-login-submit');
    if (submitBtn) {
      submitBtn.disabled = true;
      submitBtn.textContent = 'Signing in...';
    }

    const usernameOrEmail = document.getElementById('login-username')?.value.trim() || '';
    const password = document.getElementById('login-password')?.value || '';

    const result = await API.login(usernameOrEmail, password);
    if (submitBtn) {
      submitBtn.disabled = false;
      submitBtn.textContent = 'Login';
    }

    if (result.success) {
      if (window.UI?.toast) {
        UI.toast(`Welcome back, ${result.user.username}!`, 'success');
      }
      setTimeout(() => {
        window.location.replace('/dashboard');
      }, 350);
    } else {
      if (loginError) {
        loginError.textContent = result.error || 'Invalid username or password.';
        loginError.style.display = 'block';
      }
    }
  });

  // Update register button text on role change
  const roleSelect = document.getElementById('reg-role');
  const regSubmitBtn = document.getElementById('btn-reg-submit');
  if (roleSelect && regSubmitBtn) {
    roleSelect.addEventListener('change', () => {
      regSubmitBtn.textContent = roleSelect.value === 'admin'
        ? 'Create Administrator Account'
        : 'Create Organizer Account';
    });
  }

  // Handle Registration submission
  formRegister?.addEventListener('submit', async (e) => {
    e.preventDefault();
    if (regError) regError.style.display = 'none';
    const submitBtn = document.getElementById('btn-reg-submit');
    if (submitBtn) {
      submitBtn.disabled = true;
      submitBtn.textContent = 'Registering...';
    }

    const username = document.getElementById('reg-username')?.value.trim() || '';
    const email = document.getElementById('reg-email')?.value.trim() || '';
    const role = document.getElementById('reg-role')?.value || 'organizer';
    const password = document.getElementById('reg-password')?.value || '';

    const result = await API.register(username, email, password, role);
    if (submitBtn) {
      submitBtn.disabled = false;
      submitBtn.textContent = role === 'admin' ? 'Create Administrator Account' : 'Create Organizer Account';
    }

    if (result.success) {
      const roleName = role === 'admin' ? 'Administrator' : 'Organizer';
      if (window.UI?.toast) {
        UI.toast(`${roleName} account created! Redirecting...`, 'success');
      }
      setTimeout(() => {
        window.location.replace('/dashboard');
      }, 350);
    } else {
      if (regError) {
        regError.textContent = result.error || 'Registration failed';
        regError.style.display = 'block';
      }
    }
  });

  // PageShow listener: if user navigates back to /login from browser history after logout
  window.addEventListener('pageshow', async (event) => {
    if (event.persisted) {
      try {
        const user = await API.getCurrentUser();
        if (user) {
          window.location.replace('/dashboard');
        }
      } catch (err) {
        // Not authenticated - stay on login page with demo logins active
      }
    }
  });
});
