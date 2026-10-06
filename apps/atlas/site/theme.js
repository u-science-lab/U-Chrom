// Light / dark theme.  Loaded in <head> (not deferred) so that a theme chosen earlier is set before the page is
// drawn.  Without a choice the page follows the system's setting; the toggle in the top bar stores one
// (localStorage) and sets <html data-theme>.  A change is announced as a 'themechange' event on document.
(function () {
  'use strict';
  var KEY = 'uchrom-atlas-theme', root = document.documentElement;
  var media = window.matchMedia ? window.matchMedia('(prefers-color-scheme: dark)') : null;
  function stored() { try { var t = localStorage.getItem(KEY); return t === 'dark' || t === 'light' ? t : null; } catch (e) { return null; } }
  function current() { return root.getAttribute('data-theme') || (media && media.matches ? 'dark' : 'light'); }
  var t = stored();
  if (t) root.setAttribute('data-theme', t);

  function label() {
    var b = document.getElementById('theme-toggle');
    if (!b) return;
    var text = current() === 'dark' ? 'Switch to light theme' : 'Switch to dark theme';
    b.setAttribute('aria-label', text); b.title = text;
  }
  function announce() { label(); document.dispatchEvent(new CustomEvent('themechange', { detail: current() })); }
  document.addEventListener('DOMContentLoaded', function () {
    label();
    var b = document.getElementById('theme-toggle');
    if (b) b.addEventListener('click', function () {
      var next = current() === 'dark' ? 'light' : 'dark';
      root.setAttribute('data-theme', next);
      try { localStorage.setItem(KEY, next); } catch (e) { /* private mode: this page only */ }
      announce();
    });
  });
  if (media && media.addEventListener) media.addEventListener('change', function () { if (!stored()) announce(); });
})();
