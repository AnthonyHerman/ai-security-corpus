// AI Security Corpus: client-side search, the sticky bar, the section rail. No dependencies.
(function () {
  'use strict';
  var root = document.documentElement.getAttribute('data-root') || './';
  var q = document.getElementById('q');
  var box = document.getElementById('results');
  var prompt = q && q.closest('.prompt');
  var corpus = null, loading = null, timer = null, items = [], quiet = false;
  var CAP = 60;

  // ---------- keys: / focuses search, Esc closes the list, then leaves the field ----------
  document.addEventListener('keydown', function (e) {
    var el = document.activeElement, tag = el && el.tagName;
    var typing = /input|textarea|select/i.test(tag || '');
    if (e.key === '/' && !typing && q && !e.metaKey && !e.ctrlKey && !e.altKey) { e.preventDefault(); q.focus(); q.select(); return; }
    if (e.key === 'Escape') {
      // refocusing the prompt must not reopen the list it just closed
      if (box && !box.hidden) { hide(); if (q) { quiet = true; q.focus(); quiet = false; } return; }
      if (typing) el.blur();
    }
  });

  // ---------- search ----------
  function load() {
    // corpus.json is the whole site model; a title/url-only index would be only 3% smaller gzipped,
    // since titles and URLs are the bulk of it, so the one file serves both
    if (loading) return loading;
    loading = fetch(root + 'data/corpus.json').then(function (r) {
      if (!r.ok) throw new Error(r.status);
      return r.json();
    }).then(function (d) {
      corpus = d;
      items = [];
      d.groups.forEach(function (g) {
        g.categories.forEach(function (c) {
          var cat = { g: g.name, n: (c.label || c.name).replace(/\s*\([^)]*\)$/, ''), h: catPath(g, c) };
          c.sections.forEach(function (s) {
            s.links.forEach(function (l) {
              items.push({ t: l.t, u: l.u, d: l.d, k: (l.t + ' ' + l.d).toLowerCase(), c: cat, href: root + cat.h });
            });
          });
        });
      });
      return d;
    });
    return loading;
  }
  function catPath(g, c) {
    var p = c.path.split('/');
    return (p.length === 3 ? p[0] + '/' + p[1] : g.slug + '/' + c.slug) + '/';
  }
  function esc(s) {
    return String(s).replace(/[&<>"]/g, function (ch) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[ch]; });
  }
  function hilite(s, terms) {
    // one pass over the escaped text with every term in a single alternation, so a later term can never
    // match inside a <mark> tag inserted by an earlier one
    var parts = terms.filter(function (t) { return t.length >= 2; })
      .map(function (t) { return esc(t).replace(/[.*+?^${}()|[\]\\]/g, '\\$&'); });
    if (!parts.length) return esc(s);
    var re = new RegExp('(' + parts.join('|') + ')', 'ig');
    return esc(s).replace(re, '<mark>$1</mark>');
  }
  function fmt(n) { return String(n).replace(/\B(?=(\d{3})+(?!\d))/g, ','); }
  var live = document.getElementById('q-status');
  function announce(text) { if (live) live.textContent = text; }
  function show(html) { box.innerHTML = html; box.hidden = false; box.scrollTop = 0; }
  function hide() {
    if (box) { box.hidden = true; box.innerHTML = ''; }
    if (prompt) prompt.classList.remove('live');
    announce('');
  }
  function status(msg) {
    if (!box) return;
    show('<p class="rs">' + msg + '</p>');
    announce(msg);
  }
  function run() {
    var text = q.value.trim().toLowerCase();
    if (!text) { hide(); return; }
    if (prompt) prompt.classList.add('live');
    if (!corpus) {
      status('Loading');
      load().then(run, function () { status('Search is unavailable'); });
      return;
    }
    var terms = text.split(/\s+/).filter(Boolean);
    var hits = [];
    for (var i = 0; i < items.length; i++) {
      var it = items[i], ok = true;
      for (var j = 0; j < terms.length; j++) { if (it.k.indexOf(terms[j]) < 0) { ok = false; break; } }
      if (ok) hits.push(it);
    }
    if (!hits.length) { status('No results'); return; }
    var groups = [], byCat = {};
    hits.slice(0, CAP).forEach(function (h) {
      var key = h.c.h;
      if (!byCat[key]) { byCat[key] = { c: h.c, href: h.href, rows: [] }; groups.push(byCat[key]); }
      byCat[key].rows.push(h);
    });
    var spoken = fmt(hits.length) + (hits.length === 1 ? ' result' : ' results');
    var summary = spoken;
    if (hits.length > CAP) { summary = CAP + ' of ' + fmt(hits.length); spoken += ', first ' + CAP + ' shown'; }
    var html = '<p class="rs">' + summary + '</p>';
    groups.forEach(function (gr) {
      html += '<h2 class="rh"><a href="' + esc(gr.href) + '">' + esc(gr.c.n) + '</a><span class="g">' + esc(gr.c.g) + '</span></h2>' +
        '<ul class="links" aria-label="' + esc(gr.c.n) + '">';
      gr.rows.forEach(function (r) {
        html += '<li><a href="' + esc(r.u) + '"><span>' + hilite(r.t, terms) + '</span><i>' + hilite(r.d, terms) + '</i></a></li>';
      });
      html += '</ul>';
    });
    show(html);
    announce(spoken);
  }

  if (q && box) {
    q.addEventListener('input', function () {
      clearTimeout(timer);
      timer = setTimeout(run, corpus ? 60 : 0);
    });
    q.addEventListener('focus', function () { if (!quiet && q.value.trim() && box.hidden) run(); });
    q.addEventListener('keydown', function (e) {
      // Enter and ArrowDown both step into the list; a second Enter on the focused row opens it
      if ((e.key === 'ArrowDown' || e.key === 'Enter') && !box.hidden) {
        var first = box.querySelector('li a');
        if (first) { e.preventDefault(); first.focus(); }
      }
    });
    box.addEventListener('keydown', function (e) {
      var links = Array.prototype.slice.call(box.querySelectorAll('li a'));
      var i = links.indexOf(document.activeElement);
      if (i < 0) return;
      if (e.key === 'ArrowDown') { e.preventDefault(); (links[i + 1] || links[0]).focus(); }
      else if (e.key === 'ArrowUp') { e.preventDefault(); if (i === 0) q.focus(); else links[i - 1].focus(); }
      else if (e.key === 'Home') { e.preventDefault(); links[0].focus(); }
      else if (e.key === 'End') { e.preventDefault(); links[links.length - 1].focus(); }
    });
    document.addEventListener('click', function (e) {
      if (!box.hidden && !box.contains(e.target) && e.target !== q) hide();
    });
    var form = q.closest('form');
    if (form) form.addEventListener('submit', function (e) { e.preventDefault(); run(); });
    // Deep link from the site's SearchAction: ?q=term
    var m = /[?&]q=([^&]+)/.exec(location.search);
    if (m) {
      try { q.value = decodeURIComponent(m[1].replace(/\+/g, ' ')); } catch (err) { q.value = ''; }
      if (q.value) { q.focus(); run(); }
    }
  }

  // ---------- category page: the sticky bar ----------
  var bar = document.querySelector('.bar.sticky');
  if (bar) {
    // the rail sticks under the bar, whatever height the bar is
    var barH = function () { document.documentElement.style.setProperty('--bar-h', bar.offsetHeight + 'px'); };
    barH();
    if ('ResizeObserver' in window) new ResizeObserver(barH).observe(bar);
    else window.addEventListener('resize', barH);
    // once the page heading has scrolled under the bar, the bar draws its rule and names the page
    var h1 = document.querySelector('.cat-hero h1');
    if (h1 && 'IntersectionObserver' in window) {
      new IntersectionObserver(function (en) {
        bar.classList.toggle('past', !en[0].isIntersecting && en[0].boundingClientRect.top < 80);
      }, { rootMargin: '-' + bar.offsetHeight + 'px 0px 0px 0px' }).observe(h1);
    }
  }

  // ---------- category page: mark the section in view in the rail ----------
  var rail = document.querySelector('.rail');
  if (rail && 'IntersectionObserver' in window) {
    var map = {}, list = rail.querySelector('ol');
    rail.querySelectorAll('a[href^="#"]').forEach(function (a) { map[a.getAttribute('href').slice(1)] = a; });
    // keep the current entry in view by scrolling the rail's own box only, never the document
    // (scrollIntoView also moves the page, which yanked phone readers back to the tab row)
    var reveal = function (a) {
      var r = a.getBoundingClientRect();
      if (list.scrollWidth > list.clientWidth + 1) {
        var lb = list.getBoundingClientRect();
        if (r.left < lb.left + 12 || r.right > lb.right - 60) list.scrollLeft += r.left - lb.left - 20;
      } else if (rail.scrollHeight > rail.clientHeight + 1) {
        var rb = rail.getBoundingClientRect();
        if (r.top < rb.top || r.bottom > rb.bottom) rail.scrollTop += r.top - rb.top - rb.height / 2;
      }
    };
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (en) {
        if (en.isIntersecting) {
          rail.querySelectorAll('a.on').forEach(function (a) { a.classList.remove('on'); });
          var a = map[en.target.id];
          if (a) { a.classList.add('on'); reveal(a); }
        }
      });
    }, { rootMargin: '-30% 0px -60% 0px' });
    document.querySelectorAll('.section').forEach(function (s) { io.observe(s); });
  }
})();
