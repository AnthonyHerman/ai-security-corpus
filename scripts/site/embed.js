/* embed.js: the corpus inside somebody else's window. With ?embed=acid in the URL (the Internet Explorer window on
   itspricedin.lol frames the site this way) the site's own chrome goes, the palette tilts, every internal link keeps
   the flag and replaces the page (so the host's Back button stays the host's), off-site links open in a new tab, and
   the page talks to its parent: {type:'page', path, title} out, to https://itspricedin.lol only, on load and on every
   in-page navigation; {type:'nav', action:'go'|'refresh'} in, from that origin only, and only from the parent window.
   It runs synchronously in <head> so the class is on <html> before the first paint; without the flag it does nothing.
   Nothing here reads cookies, storage or anything about the visitor: the only thing that leaves is the page's path and title. */
(function () {
  'use strict';
  var FLAG = 'embed', VALUE = 'acid', HOST = 'https://itspricedin.lol';
  var q;
  try { q = new URLSearchParams(location.search); } catch (e) { return; }
  if (q.get(FLAG) !== VALUE) return;
  var html = document.documentElement;
  html.classList.add('embed');
  var root;   // this site's root path on the origin (data-root is the page's relative prefix to it): nav stays inside it
  try { root = new URL(html.getAttribute('data-root') || './', location.href).pathname; } catch (e) { root = '/'; }
  function flagged(href) { var u = new URL(href, location.href); u.searchParams.set(FLAG, VALUE); return u.href; }
  function path() { return location.pathname + location.hash; }
  function announce() {
    if (!window.parent || window.parent === window) return;
    window.parent.postMessage({ type: 'page', path: path(), title: document.title }, HOST);
  }
  document.addEventListener('click', function (e) {
    if (e.defaultPrevented || e.button !== 0) return;
    var a = e.target && e.target.closest ? e.target.closest('a[href]') : null;
    if (!a) return;
    var u;
    try { u = new URL(a.href, location.href); } catch (err) { return; }
    if (!/^https?:$/.test(u.protocol)) return;
    if (u.origin !== location.origin) { a.target = '_blank'; a.rel = 'noopener'; return; }   // github.com and every other site: a new tab, never this frame
    if (u.pathname === location.pathname && u.search === location.search && u.hash) return;   // an in-page anchor: hashchange announces it
    if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) { a.href = flagged(u.href); return; }   // a new tab keeps the flag too
    e.preventDefault();
    location.replace(flagged(u.href));
  });
  document.addEventListener('submit', function (e) {   // the search form is a GET to the index: it keeps the flag
    var f = e.target;
    if (!f || f.tagName !== 'FORM' || (f.getAttribute('method') || 'get').toLowerCase() !== 'get' || f.querySelector('input[name="' + FLAG + '"]')) return;
    var i = document.createElement('input');
    i.type = 'hidden'; i.name = FLAG; i.value = VALUE;
    f.appendChild(i);
  });
  window.addEventListener('message', function (e) {
    if (e.origin !== HOST || e.source !== window.parent) return;
    var m = e.data;
    if (!m || typeof m !== 'object' || m.type !== 'nav') return;
    if (m.action === 'refresh') { location.reload(); return; }
    if (m.action !== 'go' || typeof m.path !== 'string' || m.path.charAt(0) !== '/' || m.path.charAt(1) === '/') return;
    var u;
    try { u = new URL(m.path, location.origin); } catch (err) { return; }
    if (u.origin !== location.origin || u.pathname.indexOf(root) !== 0) return;   // only pages of this site
    location.replace(flagged(u.href));
  });
  window.addEventListener('hashchange', announce);
  var push = history.pushState;   // the site has no router today; if one arrives, the address bar outside stays honest
  history.pushState = function () { var r = push.apply(this, arguments); announce(); return r; };
  if (document.title) announce(); else document.addEventListener('DOMContentLoaded', announce);
})();
