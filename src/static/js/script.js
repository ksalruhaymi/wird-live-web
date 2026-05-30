function toggleDarkMode() {
  const html = document.documentElement;
  const icon = document.getElementById('themeIcon');
  const isDark = html.getAttribute('data-theme') === 'dark';

  if (isDark) {
    html.removeAttribute('data-theme');
    localStorage.setItem('theme', 'light');
    icon.classList.remove('bi-sun-fill');
    icon.classList.add('bi-moon-fill');
  } else {
    html.setAttribute('data-theme', 'dark');
    localStorage.setItem('theme', 'dark');
    icon.classList.remove('bi-moon-fill');
    icon.classList.add('bi-sun-fill');
  }
}

// تحميل التفضيل عند فتح الصفحة
document.addEventListener('DOMContentLoaded', () => {
  const icon = document.getElementById('themeIcon');
  if (localStorage.getItem('theme') === 'dark') {
    document.documentElement.setAttribute('data-theme', 'dark');
    icon.classList.remove('bi-moon-fill');
    icon.classList.add('bi-sun-fill');
  }
});

//////////////////////////////////////////////////
