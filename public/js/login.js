/**
 * Login & Registration Controller
 * Full Header & Form Synchronization • Serverless Resilience • Seamless User Experience
 */

// Active password peek timeout tracker
const passwordPeekTimeouts = {};

/**
 * Password Visibility Toggle: displays password in text form for exactly 1 second,
 * then automatically reverts to hidden password. Clicking again before 1 second hides it early.
 */
window.togglePasswordVisibility = function(inputId, btn) {
  const input = document.getElementById(inputId);
  if (!input) return;

  const currentVal = input.value;
  const targetBtn = btn || document.getElementById(`btn-toggle-${inputId}`);
  const eyeIcon = targetBtn?.querySelector('.eye-icon');
  const eyeOffIcon = targetBtn?.querySelector('.eye-off-icon');

  // Clear existing auto-hide timeout
  if (passwordPeekTimeouts[inputId]) {
    clearTimeout(passwordPeekTimeouts[inputId]);
    delete passwordPeekTimeouts[inputId];
  }

  // If already text, user clicked to hide early: revert immediately
  if (input.type === 'text') {
    input.type = 'password';
    input.value = currentVal;
    if (eyeIcon) eyeIcon.style.display = 'block';
    if (eyeOffIcon) eyeOffIcon.style.display = 'none';
    if (targetBtn) {
      targetBtn.setAttribute('aria-label', 'View password for 1 second');
      targetBtn.setAttribute('title', 'View password for 1 second');
      targetBtn.setAttribute('aria-pressed', 'false');
    }
    input.focus();
    return;
  }

  // Make password visible in text form
  input.type = 'text';
  input.value = currentVal;
  if (eyeIcon) eyeIcon.style.display = 'none';
  if (eyeOffIcon) eyeOffIcon.style.display = 'block';
  if (targetBtn) {
    targetBtn.setAttribute('aria-label', 'Password visible (1s)');
    targetBtn.setAttribute('title', 'Password visible (1s)');
    targetBtn.setAttribute('aria-pressed', 'true');
  }

  // Restore cursor position to end of input without clearing value
  try {
    input.focus();
    const len = input.value.length;
    input.setSelectionRange(len, len);
  } catch (e) {}

  // Automatically revert back to password after exactly 1 second (1000ms)
  passwordPeekTimeouts[inputId] = setTimeout(() => {
    input.type = 'password';
    input.value = currentVal;
    if (eyeIcon) eyeIcon.style.display = 'block';
    if (eyeOffIcon) eyeOffIcon.style.display = 'none';
    if (targetBtn) {
      targetBtn.setAttribute('aria-label', 'View password for 1 second');
      targetBtn.setAttribute('title', 'View password for 1 second');
      targetBtn.setAttribute('aria-pressed', 'false');
    }
    delete passwordPeekTimeouts[inputId];
  }, 1000);
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

  const authTitle = document.getElementById('auth-title') || document.querySelector('.auth-title');
  const authSubtitle = document.getElementById('auth-subtitle') || document.querySelector('.auth-subtitle');

  const inputLoginUser = document.getElementById('login-username');
  const inputLoginPass = document.getElementById('login-password');
  const inputRegUser = document.getElementById('reg-username');
  const inputRegEmail = document.getElementById('reg-email');
  const inputRegPass = document.getElementById('reg-password');
  const selectRegRole = document.getElementById('reg-role');

  // Bind Theme Toggle Button if present
  const themeToggleBtn = document.getElementById('btn-theme-toggle');
  if (themeToggleBtn) {
    themeToggleBtn.addEventListener('click', (e) => {
      e.preventDefault();
      if (window.UI?.toggleTheme) {
        window.UI.toggleTheme();
      } else if (window.API?.toggleTheme) {
        window.API.toggleTheme();
      }
    });
  }

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
      activateLoginTab(false);
    }

    if (inputLoginUser) {
      inputLoginUser.value = username;
      inputLoginUser.dispatchEvent(new Event('input', { bubbles: true }));
    }
    if (inputLoginPass) {
      inputLoginPass.value = password;
      inputLoginPass.dispatchEvent(new Event('input', { bubbles: true }));
    }

    if (loginError) loginError.style.display = 'none';

    if (window.UI?.toast) {
      UI.toast(`Autofilled ${roleLabel} demo credentials!`, 'info');
    }

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

  // Setup Registered User Quick-Fill Chip if present in vault
  const setupRegisteredUserChip = () => {
    try {
      const vault = JSON.parse(localStorage.getItem('matrix_registered_accounts') || '[]');
      const btnFillReg = document.getElementById('btn-fill-registered');
      const nameSpan = document.getElementById('btn-fill-reg-name');
      if (vault && vault.length > 0 && btnFillReg && nameSpan) {
        const latest = vault[0];
        nameSpan.textContent = latest.username.length > 14 ? latest.username.slice(0, 12) + '…' : latest.username;
        btnFillReg.title = `Autofill ${latest.username} (${latest.role || 'organizer'})`;
        btnFillReg.style.display = 'inline-flex';
        btnFillReg.onclick = (e) => {
          e.preventDefault();
          populateDemo(latest.username, latest.password, latest.username);
        };
      }
    } catch (e) {
      console.warn('Registered chip setup notice:', e);
    }
  };
  setupRegisteredUserChip();

  // Tab switching and synchronization
  const activateLoginTab = (shouldFocus = true) => {
    tabLogin?.classList.add('active');
    tabRegister?.classList.remove('active');
    tabLogin?.setAttribute('aria-selected', 'true');
    tabRegister?.setAttribute('aria-selected', 'false');

    if (formLogin) formLogin.style.display = 'block';
    if (formRegister) formRegister.style.display = 'none';
    if (loginError) loginError.style.display = 'none';

    // Synchronize Card Title & Subtitle
    if (authTitle) authTitle.textContent = 'Login';
    if (authSubtitle) authSubtitle.textContent = 'Sign in to continue to The Matrix';
    document.title = 'Sign In • The Matrix';

    // Synchronize Form Values: Transfer entered values from Register to Sign In
    if (inputLoginUser && !inputLoginUser.value.trim()) {
      const regUser = (inputRegUser?.value || '').trim();
      const regEmail = (inputRegEmail?.value || '').trim();
      if (regUser) {
        inputLoginUser.value = regUser;
      } else if (regEmail) {
        inputLoginUser.value = regEmail;
      }
    }
    if (inputLoginPass && !inputLoginPass.value && inputRegPass?.value) {
      inputLoginPass.value = inputRegPass.value;
    }

    // Keep URL Hash in sync
    if (window.location.hash === '#register') {
      try { history.replaceState(null, '', '#login'); } catch (e) { window.location.hash = 'login'; }
    }

    if (shouldFocus) {
      inputLoginUser?.focus();
    }
  };

  const activateRegisterTab = (shouldFocus = true) => {
    tabRegister?.classList.add('active');
    tabLogin?.classList.remove('active');
    tabRegister?.setAttribute('aria-selected', 'true');
    tabLogin?.setAttribute('aria-selected', 'false');

    if (formRegister) formRegister.style.display = 'block';
    if (formLogin) formLogin.style.display = 'none';
    if (regError) regError.style.display = 'none';

    // Synchronize Card Title & Subtitle
    if (authTitle) authTitle.textContent = 'Create Account';
    if (authSubtitle) authSubtitle.textContent = 'Sign up to get started with The Matrix';
    document.title = 'Register • The Matrix';

    // Synchronize Form Values: Transfer entered values from Sign In to Register
    const loginVal = (inputLoginUser?.value || '').trim();
    if (loginVal) {
      if (loginVal.includes('@')) {
        if (inputRegEmail && !inputRegEmail.value.trim()) {
          inputRegEmail.value = loginVal;
        }
        if (inputRegUser && !inputRegUser.value.trim()) {
          inputRegUser.value = loginVal.split('@')[0];
        }
      } else {
        if (inputRegUser && !inputRegUser.value.trim()) {
          inputRegUser.value = loginVal;
        }
      }
    }
    if (inputRegPass && !inputRegPass.value && inputLoginPass?.value) {
      inputRegPass.value = inputLoginPass.value;
    }

    // Keep URL Hash in sync
    if (window.location.hash !== '#register') {
      try { history.replaceState(null, '', '#register'); } catch (e) { window.location.hash = 'register'; }
    }

    if (shouldFocus) {
      if (inputRegUser && !inputRegUser.value) {
        inputRegUser.focus();
      } else if (inputRegEmail && !inputRegEmail.value) {
        inputRegEmail.focus();
      } else {
        inputRegPass?.focus();
      }
    }
  };

  tabLogin?.addEventListener('click', () => activateLoginTab(true));
  tabRegister?.addEventListener('click', () => activateRegisterTab(true));

  // Contextual Switch Links inside form bodies
  document.getElementById('link-goto-register')?.addEventListener('click', (e) => {
    e.preventDefault();
    activateRegisterTab(true);
  });

  document.getElementById('link-goto-login')?.addEventListener('click', (e) => {
    e.preventDefault();
    activateLoginTab(true);
  });

  // Keyboard accessibility for tabs
  const handleTabKeyDown = (activateFn) => (e) => {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      activateFn(true);
    }
  };
  tabLogin?.addEventListener('keydown', handleTabKeyDown(activateLoginTab));
  tabRegister?.addEventListener('keydown', handleTabKeyDown(activateRegisterTab));

  // Hash navigation listener (supports browser back/forward buttons)
  window.addEventListener('hashchange', () => {
    if (window.location.hash === '#register') {
      activateRegisterTab(false);
    } else {
      activateLoginTab(false);
    }
  });

  // Check URL Hash for tab selection on initial page load
  if (window.location.hash === '#register') {
    activateRegisterTab(false);
  } else {
    // If not on register tab, pre-fill last logged-in / registered username if available
    const lastUser = localStorage.getItem('matrix_last_username');
    if (lastUser && inputLoginUser && !inputLoginUser.value) {
      inputLoginUser.value = lastUser;
    }
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

    const usernameOrEmail = inputLoginUser?.value.trim() || '';
    const password = inputLoginPass?.value || '';

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
  const regSubmitBtn = document.getElementById('btn-reg-submit');
  if (selectRegRole && regSubmitBtn) {
    selectRegRole.addEventListener('change', () => {
      regSubmitBtn.textContent = selectRegRole.value === 'admin'
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

    const username = inputRegUser?.value.trim() || '';
    const email = inputRegEmail?.value.trim() || '';
    const role = selectRegRole?.value || 'organizer';
    const password = inputRegPass?.value || '';

    const result = await API.register(username, email, password, role);
    if (submitBtn) {
      submitBtn.disabled = false;
      submitBtn.textContent = role === 'admin' ? 'Create Administrator Account' : 'Create Organizer Account';
    }

    if (result.success) {
      const roleName = role === 'admin' ? 'Administrator' : 'Organizer';
      if (inputLoginUser) inputLoginUser.value = username;
      if (inputLoginPass) inputLoginPass.value = password;
      setupRegisteredUserChip();

      if (window.UI?.toast) {
        UI.toast(`${roleName} account created! Redirecting to dashboard...`, 'success');
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
    setupRegisteredUserChip();
  });
});
