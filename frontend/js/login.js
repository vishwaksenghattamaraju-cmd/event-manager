/**
 * Login & Registration Controller
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

  // Tab switching
  tabLogin.addEventListener('click', () => {
    tabLogin.classList.add('active');
    tabRegister.classList.remove('active');
    formLogin.style.display = 'block';
    formRegister.style.display = 'none';
    loginError.style.display = 'none';
  });

  tabRegister.addEventListener('click', () => {
    tabRegister.classList.add('active');
    tabLogin.classList.remove('active');
    formRegister.style.display = 'block';
    formLogin.style.display = 'none';
    regError.style.display = 'none';
  });

  // Instant Demo login button helpers
  document.getElementById('btn-fill-admin')?.addEventListener('click', () => {
    tabLogin.click();
    document.getElementById('login-username').value = 'admin';
    document.getElementById('login-password').value = 'Admin@123';
    document.getElementById('btn-login-submit').click();
  });

  document.getElementById('btn-fill-organizer')?.addEventListener('click', () => {
    tabLogin.click();
    document.getElementById('login-username').value = 'organizer';
    document.getElementById('login-password').value = 'Organizer@123';
    document.getElementById('btn-login-submit').click();
  });

  document.getElementById('btn-fill-vishwak')?.addEventListener('click', () => {
    tabLogin.click();
    document.getElementById('login-username').value = 'vishwaksen';
    document.getElementById('login-password').value = 'Organizer@123';
    document.getElementById('btn-login-submit').click();
  });

  // Handle Login submission
  formLogin.addEventListener('submit', async (e) => {
    e.preventDefault();
    loginError.style.display = 'none';
    const submitBtn = document.getElementById('btn-login-submit');
    submitBtn.disabled = true;
    submitBtn.textContent = 'Signing in...';

    const usernameOrEmail = document.getElementById('login-username').value.trim();
    const password = document.getElementById('login-password').value;

    const result = await API.login(usernameOrEmail, password);
    submitBtn.disabled = false;
    submitBtn.textContent = 'Sign In';

    if (result.success) {
      UI.toast(`Welcome back, ${result.user.username}!`, 'success');
      setTimeout(() => {
        window.location.href = '/dashboard';
      }, 500);
    } else {
      loginError.textContent = result.error || 'Invalid credentials';
      loginError.style.display = 'block';
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
  formRegister.addEventListener('submit', async (e) => {
    e.preventDefault();
    regError.style.display = 'none';
    const submitBtn = document.getElementById('btn-reg-submit');
    submitBtn.disabled = true;
    submitBtn.textContent = 'Registering...';

    const username = document.getElementById('reg-username').value.trim();
    const email = document.getElementById('reg-email').value.trim();
    const role = document.getElementById('reg-role')?.value || 'organizer';
    const password = document.getElementById('reg-password').value;

    const result = await API.register(username, email, password, role);
    submitBtn.disabled = false;
    submitBtn.textContent = role === 'admin' ? 'Create Administrator Account' : 'Create Organizer Account';

    if (result.success) {
      const roleName = role === 'admin' ? 'Administrator' : 'Organizer';
      UI.toast(`${roleName} account created successfully! Redirecting...`, 'success');
      setTimeout(() => {
        window.location.href = '/dashboard';
      }, 500);
    } else {
      regError.textContent = result.error || 'Registration failed';
      regError.style.display = 'block';
    }
  });
});
