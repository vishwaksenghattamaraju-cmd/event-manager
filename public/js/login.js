/**
 * Login & Registration Controller (Lu.ma Small Events Landing Edition)
 */

document.addEventListener('DOMContentLoaded', async () => {
  // If already logged in, redirect directly to dashboard
  const user = await API.getCurrentUser();
  if (user) {
    window.location.href = '/dashboard';
    return;
  }

  const tabLogin = document.getElementById('tab-login');
  const tabRegister = document.getElementById('tab-register');
  const formLogin = document.getElementById('form-login');
  const formRegister = document.getElementById('form-register');
  const loginError = document.getElementById('login-error');
  const regError = document.getElementById('reg-error');
  const modalBackdrop = document.getElementById('auth-modal-backdrop');
  const btnCloseModal = document.getElementById('btn-close-modal');
  const modalTitle = document.getElementById('modal-title');
  const modalSubtitle = document.getElementById('modal-subtitle');

  // Modal Open/Close Controls
  function openAuthModal(tab = 'login') {
    if (!modalBackdrop) return;
    modalBackdrop.classList.add('is-active');
    if (tab === 'register') {
      tabRegister?.click();
    } else {
      tabLogin?.click();
    }
    setTimeout(() => {
      const activeInput = tab === 'register'
        ? document.getElementById('reg-username')
        : document.getElementById('login-username');
      activeInput?.focus();
    }, 120);
  }

  function closeAuthModal() {
    if (!modalBackdrop) return;
    modalBackdrop.classList.remove('is-active');
  }

  // Bind Open Triggers
  document.getElementById('btn-nav-signin')?.addEventListener('click', () => openAuthModal('login'));
  document.getElementById('btn-nav-register')?.addEventListener('click', () => openAuthModal('register'));
  document.getElementById('btn-hero-create')?.addEventListener('click', () => openAuthModal('register'));
  document.getElementById('link-hero-signin')?.addEventListener('click', (e) => {
    e.preventDefault();
    openAuthModal('login');
  });

  // Clicking any small event card prompts to host or manage
  document.querySelectorAll('.luma-event-card').forEach(card => {
    card.addEventListener('click', () => {
      const title = card.getAttribute('title') || 'small event';
      if (window.UI?.toast) {
        UI.toast(`Host or coordinate: ${title}`, 'info');
      }
      openAuthModal('login');
    });
  });

  // Bind Close Triggers
  btnCloseModal?.addEventListener('click', closeAuthModal);
  modalBackdrop?.addEventListener('click', (e) => {
    if (e.target === modalBackdrop) closeAuthModal();
  });
  window.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') closeAuthModal();
  });

  // Check URL Hash for automatic opening
  if (['#signin', '#login', '#auth'].includes(window.location.hash)) {
    openAuthModal('login');
  } else if (window.location.hash === '#register') {
    openAuthModal('register');
  }

  // Hero Quick Demo Chips (Admin & Organizer only)
  document.getElementById('btn-hero-admin')?.addEventListener('click', () => {
    openAuthModal('login');
    document.getElementById('btn-fill-admin')?.click();
  });

  document.getElementById('btn-hero-organizer')?.addEventListener('click', () => {
    openAuthModal('login');
    document.getElementById('btn-fill-organizer')?.click();
  });

  // Tab switching with dynamic titles
  tabLogin?.addEventListener('click', () => {
    tabLogin.classList.add('active');
    tabRegister?.classList.remove('active');
    if (formLogin) formLogin.style.display = 'block';
    if (formRegister) formRegister.style.display = 'none';
    if (loginError) loginError.style.display = 'none';
    if (modalTitle) modalTitle.textContent = 'Welcome Back';
    if (modalSubtitle) modalSubtitle.textContent = 'Sign in to coordinate small events & inventory';
  });

  tabRegister?.addEventListener('click', () => {
    tabRegister.classList.add('active');
    tabLogin?.classList.remove('active');
    if (formRegister) formRegister.style.display = 'block';
    if (formLogin) formLogin.style.display = 'none';
    if (regError) regError.style.display = 'none';
    if (modalTitle) modalTitle.textContent = 'Create Organizer Account';
    if (modalSubtitle) modalSubtitle.textContent = 'Host and manage small events with smart inventory';
  });

  // Instant Demo login button helpers inside modal (Admin & Organizer only)
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
      submitBtn.textContent = 'Sign In';
    }

    if (result.success) {
      UI.toast(`Welcome back, ${result.user.username}!`, 'success');
      setTimeout(() => {
        window.location.href = '/dashboard';
      }, 500);
    } else {
      if (loginError) {
        loginError.textContent = result.error || 'Invalid credentials';
        loginError.style.display = 'block';
      }
    }
  });

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
      UI.toast(`${roleName} account created successfully! Redirecting...`, 'success');
      setTimeout(() => {
        window.location.href = '/dashboard';
      }, 500);
    } else {
      if (regError) {
        regError.textContent = result.error || 'Registration failed';
        regError.style.display = 'block';
      }
    }
  });
});
