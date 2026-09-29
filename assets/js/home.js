document.addEventListener('DOMContentLoaded', () => {
  const header = document.querySelector('.site-header');
  const onScroll = () => { if (header) header.classList.toggle('scrolled', window.scrollY > 8); };
  window.addEventListener('scroll', onScroll, { passive: true });
  onScroll();

  document.documentElement.classList.add('js-ready');
  const io = new IntersectionObserver((entries) => {
    entries.forEach((e) => { if (e.isIntersecting) { e.target.classList.add('in'); io.unobserve(e.target); } });
  }, { threshold: 0.05, rootMargin: '0px 0px -20px 0px' });
  document.querySelectorAll('.reveal').forEach((el) => io.observe(el));
  setTimeout(() => document.querySelectorAll('.reveal:not(.in)').forEach((el) => el.classList.add('in')), 1500);

  const navToggle = document.querySelector('.mobile-toggle');
  const nav = document.querySelector('.main-nav');
  const compactNavQuery = window.matchMedia('(max-width: 1248px)');
  if (navToggle && header && nav) {
    if (!nav.id) nav.id = 'primary-navigation';
    navToggle.setAttribute('aria-controls', nav.id);

    const setNavOpen = (open, returnFocus = false) => {
      header.classList.toggle('nav-open', open);
      navToggle.setAttribute('aria-expanded', String(open));
      if (!open && returnFocus) navToggle.focus({ preventScroll: true });
    };
    navToggle.addEventListener('click', () => {
      setNavOpen(!header.classList.contains('nav-open'));
    });
    nav.querySelectorAll('a').forEach((link) => {
      link.addEventListener('click', () => setNavOpen(false));
    });
    document.addEventListener('keydown', (event) => {
      if (event.key === 'Escape' && !event.isComposing && !event.defaultPrevented && header.classList.contains('nav-open')) {
        event.preventDefault();
        setNavOpen(false, true);
      }
    });
    document.addEventListener('pointerdown', (event) => {
      if (!nav.contains(event.target) && !navToggle.contains(event.target)) setNavOpen(false);
    });
    nav.addEventListener('focusout', (event) => {
      if (event.relatedTarget && !nav.contains(event.relatedTarget) && event.relatedTarget !== navToggle) setNavOpen(false);
    });
    compactNavQuery.addEventListener('change', () => setNavOpen(false));
  }

});
