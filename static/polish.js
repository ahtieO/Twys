/* Presentation/accessibility only. No price, journal, sync or navigation logic. */
(() => {
  'use strict';

  // Consistent lightweight line icons; no external font or icon service required.
  const icons = {
    marketdesk: '<path d="M4 19V11h4v8m2 0V5h4v14m2 0V9h4v10M3 21h18"/>',
    watchlist: '<path d="m12 3 2.8 5.7 6.2.9-4.5 4.4 1.1 6.2-5.6-3-5.6 3 1.1-6.2L3 9.6l6.2-.9Z"/>',
    newsdesk: '<rect x="4" y="3" width="16" height="18" rx="2"/><path d="M8 7h8M8 11h3m3 0h2M8 15h8M8 18h8"/>',
    macro: '<path d="M4 4v16h16M7 15l4-5 4 2 5-7m-5 0h5v5"/>',
    journal22: '<path d="M5 4h14v17H5a2 2 0 0 1 0-4h14M5 4a2 2 0 0 0-2 2v13M8 8h7M8 12h5"/>',
    performance: '<path d="M3 17 8 12l4 3 8-10M15 5h5v5M4 21h16"/>',
    strategy: '<path d="m12 3 9 9-9 9-9-9Z"/><path d="M8 12h8m-4-4v8"/>',
    psychology: '<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="4"/><path d="M12 3v2m0 14v2M3 12h2m14 0h2"/>',
    screenshots: '<rect x="3" y="4" width="18" height="16" rx="2"/><circle cx="8" cy="9" r="1"/><path d="m4 17 5-5 4 4 3-3 5 5"/>',
    research: '<circle cx="10.5" cy="10.5" r="6.5"/><path d="m16 16 5 5M8 10h5m-5 3h3"/>',
    connections: '<path d="m9 15 6-6m-7 9-1 1a4 4 0 0 1-6-6l4-4a4 4 0 0 1 6 0m2 6a4 4 0 0 0 6 0l4-4a4 4 0 0 0-6-6l-1 1" transform="translate(1 0) scale(.92)"/>',
    data: '<ellipse cx="12" cy="5" rx="8" ry="3"/><path d="M4 5v14c0 4 16 4 16 0V5M4 12c0 4 16 4 16 0"/>'
  };
  const nav = [...document.querySelectorAll('.nav-item')];
  nav.forEach(item => {
    const glyph = item.querySelector('.nav-glyph');
    if (glyph && icons[item.dataset.page]) {
      glyph.setAttribute('aria-hidden', 'true');
      glyph.innerHTML = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">${icons[item.dataset.page]}</svg>`;
    }
    const updateCurrent = () => {
      if (item.classList.contains('active')) item.setAttribute('aria-current', 'page');
      else item.removeAttribute('aria-current');
    };
    new MutationObserver(updateCurrent).observe(item, {attributes: true, attributeFilter: ['class']});
    updateCurrent();
  });

  // Observe only direct page replacements, never the live chart/news subtree.
  const workspace = document.getElementById('workspace');
  const updateBusy = () => workspace.setAttribute('aria-busy', String(Boolean(workspace.querySelector(':scope > .loading'))));
  new MutationObserver(updateBusy).observe(workspace, {childList: true});
  updateBusy();

  // Keyboard focus follows dialogs, including a photo opened above trade details.
  const dialogs = ['global-search-overlay', 'overlay', 'lightbox'].map(id => document.getElementById(id));
  const previousFocus = new Map();
  const openingFocus = new WeakMap();
  const open = dialog => !dialog.classList.contains('hidden');
  // Search focuses its input synchronously, before the class observer runs.
  // Capture that focus entry's origin so Escape returns to the actual opener.
  document.addEventListener('focusin', event => {
    dialogs.forEach(dialog => {
      if (open(dialog) && !previousFocus.has(dialog) && dialog.contains(event.target) && !dialog.contains(event.relatedTarget)) {
        openingFocus.set(dialog, event.relatedTarget);
      }
    });
  });
  const topDialog = () => dialogs.filter(open).at(-1);
  const focusables = dialog => [...dialog.querySelectorAll('button, a[href], input, select, textarea, [tabindex]')]
    .filter(el => !el.disabled && el.tabIndex >= 0 && el.getClientRects().length && !el.closest('[inert]'));
  const focusDialog = dialog => {
    const target = dialog.querySelector('input') || focusables(dialog)[0] || dialog.querySelector('[role="dialog"]') || dialog;
    if (!target.hasAttribute('tabindex') && target === dialog) target.tabIndex = -1;
    target.focus({preventScroll: true});
  };
  function updateDialogs() {
    const opened = dialogs.filter(d => open(d) && !previousFocus.has(d));
    opened.forEach(d => {
      previousFocus.set(d, openingFocus.get(d) || document.activeElement);
      openingFocus.delete(d);
    });
    const closed = dialogs.filter(d => !open(d) && previousFocus.has(d));
    const active = topDialog();
    document.getElementById('app').inert = Boolean(active);
    dialogs.forEach(d => { d.inert = Boolean(active && d !== active); });
    if (opened.length && active) focusDialog(active);
    else if (closed.length) {
      const restore = previousFocus.get(closed.at(-1));
      if (active) {
        if (restore?.isConnected && active.contains(restore)) restore.focus({preventScroll: true});
        else focusDialog(active);
      } else if (restore?.isConnected && !restore.closest('.hidden')) restore.focus({preventScroll: true});
      else workspace.focus({preventScroll: true});
    }
    closed.forEach(d => previousFocus.delete(d));
  }
  dialogs.forEach(d => new MutationObserver(updateDialogs).observe(d, {attributes: true, attributeFilter: ['class']}));
  document.addEventListener('keydown', event => {
    const dialog = topDialog();
    if (!dialog) return;
    if (event.key === 'Escape') {
      // Close only the uppermost dialog; an image may sit over trade details.
      event.preventDefault();
      event.stopImmediatePropagation();
      dialog.classList.add('hidden');
      return;
    }
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'k') {
      // Do not open the command palette behind another modal.
      if (dialog.id !== 'global-search-overlay') {
        event.preventDefault();
        event.stopImmediatePropagation();
      }
      return;
    }
    if (event.key !== 'Tab') return;
    const items = focusables(dialog);
    const first = items[0], last = items.at(-1);
    if (!items.length) { event.preventDefault(); focusDialog(dialog); }
    else if (event.shiftKey && (document.activeElement === first || !items.includes(document.activeElement))) {
      event.preventDefault(); last.focus();
    } else if (!event.shiftKey && (document.activeElement === last || !items.includes(document.activeElement))) {
      event.preventDefault(); first.focus();
    }
  }, true);
})();
