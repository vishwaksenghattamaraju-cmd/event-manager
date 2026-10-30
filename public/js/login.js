/**
 * Login & Registration Controller
 * Simple, Minimal, Fast & Reliable
 */

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

  // 1-Click Demo Login Helpers
  document.getElementById('btn-fill-admin')?.addEventListener('click', () => {
    tabLogin?.click();
    const u = document.getElementById('login-username');
    const p = document.getElementById('login-password');
    if (u) u.value = 'admin';
    if (p) p.value = 'Admin@123';
    document.getElementById('btn-login-submit')?.click();
  });

  document.getElementById('btn-fill-organizer')?.addEventListener('click', () => {
    tabLogin?.click();
    const u = document.getElementById('login-username');
    const p = document.getElementById('login-password');
    if (u) u.value = 'organizer';
    if (p) p.value = 'Organizer@123';
    document.getElementById('btn-login-submit')?.click();
  });

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
