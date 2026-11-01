/**
 * Login & Registration Controller
 * Simple, Minimal, Fast & Reliable
 */

// Active password timeout tracker
const passwordPeekTimeouts = {};

// Global Password Visibility Toggle (visible for 1 second)
window.togglePasswordVisibility = function(inputId, btn) {
  const input = document.getElementById(inputId);
  if (!input) return;

  const eyeIcon = btn ? btn.querySelector('.eye-icon') : null;
  const eyeOffIcon = btn ? btn.querySelector('.eye-off-icon') : null;

  // Clear any existing 1-second timeout for this input
  if (passwordPeekTimeouts[inputId]) {
    clearTimeout(passwordPeekTimeouts[inputId]);
    delete passwordPeekTimeouts[inputId];
  }

  // If already text, user clicked to hide early: revert immediately
  if (input.type === 'text') {
    input.type = 'password';
    if (eyeIcon) eyeIcon.style.display = 'block';
    if (eyeOffIcon) eyeOffIcon.style.display = 'none';
    if (btn) {
      btn.setAttribute('aria-label', 'View password for 1 second');
      btn.setAttribute('title', 'View password for 1 second');
    }
    input.focus();
    return;
  }

  // Make password visible in text form
  input.type = 'text';
  if (eyeIcon) eyeIcon.style.display = 'none';
  if (eyeOffIcon) eyeOffIcon.style.display = 'block';
  if (btn) {
    btn.setAttribute('aria-label', 'Password visible (1s)');
    btn.setAttribute('title', 'Password visible (1s)');
  }
  input.focus();

  // Automatically revert back to hidden password after exactly 1 second (1000ms)
  passwordPeekTimeouts[inputId] = setTimeout(() => {
    input.type = 'password';
    if (eyeIcon) eyeIcon.style.display = 'block';
    if (eyeOffIcon) eyeOffIcon.style.display = 'none';
    if (btn) {
      btn.setAttribute('aria-label', 'View password for 1 second');
      btn.setAttribute('title', 'View password for 1 second');
    }
    delete passwordPeekTimeouts[inputId];
  }, 1000);
};

document.addEventListener('DOMContentLoaded', async () => {
  // If already logged in, redirect directly to dashboard
  try {
    const user = await API.getCurrentUser();
    if (user) {
      window.location.href = '/dashboard';
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

  // Password Visibility Toggle Helpers
  const bindToggle = (btnId, inputId) => {
    const btn = document.getElementById(btnId);
    btn?.addEventListener('click', (e) => {
      e.preventDefault();
      window.togglePasswordVisibility(inputId, btn);
    });
  };

  bindToggle('btn-toggle-login-password', 'login-password');
  bindToggle('btn-toggle-reg-password', 'reg-password');

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
        window.location.href = '/dashboard';
      }, 350);
    } else {
      if (loginError) {
        loginError.textContent = result.error || 'Invalid credentials';
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
        window.location.href = '/dashboard';
      }, 350);
    } else {
      if (regError) {
        regError.textContent = result.error || 'Registration failed';
        regError.style.display = 'block';
      }
    }
  });
});
