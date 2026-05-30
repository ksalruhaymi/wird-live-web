document.addEventListener('DOMContentLoaded', () => {
  const sidebar = document.getElementById('sidebar');
  const overlay = document.getElementById('sidebarOverlay');
  const openBtn = document.getElementById('navbarToggle');
  const closeBtn = document.getElementById('sidebarClose');

  if (!sidebar) return;

  const links = sidebar.querySelectorAll('a[href]');

  const isRTL = () => document.documentElement.getAttribute('dir') === 'rtl';

  const showHamburger = () => { if (openBtn) openBtn.classList.remove('hidden'); };
  const hideHamburger = () => { if (openBtn) openBtn.classList.add('hidden'); };

  const openSidebar = () => {
    sidebar.classList.add('translate-x-0');
    sidebar.classList.remove('-translate-x-full', 'translate-x-full');
    if (overlay) overlay.classList.remove('hidden');
    hideHamburger();
    document.body.style.overflow = 'hidden';
  };

  const closeSidebar = () => {
    sidebar.classList.remove('translate-x-0');
    sidebar.classList.add(isRTL() ? 'translate-x-full' : '-translate-x-full');
    if (overlay) overlay.classList.add('hidden');
    showHamburger();
    document.body.style.overflow = '';
  };

  if (openBtn) openBtn.addEventListener('click', (e) => {
    e.preventDefault();
    openSidebar();
  });

  if (closeBtn) closeBtn.addEventListener('click', closeSidebar);
  if (overlay) overlay.addEventListener('click', closeSidebar);

  links.forEach(a => a.addEventListener('click', closeSidebar));

  const syncOnResize = () => {
    if (window.innerWidth >= 768) {
      sidebar.classList.add('translate-x-0');
      sidebar.classList.remove('-translate-x-full', 'translate-x-full');
      if (overlay) overlay.classList.add('hidden');
      showHamburger();
      document.body.style.overflow = '';
    } else {
      sidebar.classList.remove('translate-x-0');
      sidebar.classList.add(isRTL() ? 'translate-x-full' : '-translate-x-full');
      if (overlay) overlay.classList.add('hidden');
      showHamburger();
      document.body.style.overflow = '';
    }
  };

  window.addEventListener('resize', syncOnResize, { passive: true });
  syncOnResize();
});