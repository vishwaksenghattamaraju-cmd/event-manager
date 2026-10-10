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

  // Handle Registration submission
  formRegister.addEventListener('submit', async (e) => {
    e.preventDefault();
    regError.style.display = 'none';
    const submitBtn = document.getElementById('btn-reg-submit');
    submitBtn.disabled = true;
    submitBtn.textContent = 'Registering...';

    const username = document.getElementById('reg-username').value.trim();
    const email = document.getElementById('reg-email').value.trim();
    const password = document.getElementById('reg-password').value;

    const result = await API.register(username, email, password);
    submitBtn.disabled = false;
    submitBtn.textContent = 'Create Organizer Account';

    if (result.success) {
      UI.toast('Account created successfully! Please log in.', 'success');
      // Switch back to login form with username filled
      tabLogin.click();
      document.getElementById('login-username').value = username;
      document.getElementById('login-password').focus();
    } else {
      regError.textContent = result.error || 'Registration failed';
      regError.style.display = 'block';
    }
  });
});
