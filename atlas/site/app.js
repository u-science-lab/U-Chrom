// The atlas page: reads catalog.json (deployed next to this page; dataset addresses are data root + path)
// and lists the datasets. No framework, no build step.
(function () {
  'use strict';
  var CFG = window.ATLAS_CONFIG || {};
  var DATA = (CFG.dataRoot || '').replace(/\/+$/, '');
  var $ = function (id) { return document.getElementById(id); };
  var state = { cat: null, q: '', on: {} };   // on: {group: Set(values)}

  function el(tag, attrs, kids) {
    var e = document.createElement(tag);
    Object.keys(attrs || {}).forEach(function (k) {
      if (k === 'text') e.textContent = attrs[k]; else if (k === 'class') e.className = attrs[k]; else e.setAttribute(k, attrs[k]);
    });
    (kids || []).forEach(function (c) { if (c) e.appendChild(typeof c === 'string' ? document.createTextNode(c) : c); });
    return e;
  }
  function fmtSize(mb) { return mb >= 1000 ? (mb / 1000).toFixed(1) + ' GB' : Math.round(mb) + ' MB'; }
  function fmtN(n) { return n >= 1e6 ? (n / 1e6).toFixed(1) + 'M' : n >= 1e4 ? Math.round(n / 1e3) + 'k' : n.toLocaleString(); }
  function urlOf(d) { return d.url || (DATA + '/' + String(d.path).replace(/^\/+/, '')); }
  function paperKey(d) { return d.paper || 'Other'; }

  var GROUPS = [
    ['Organism', function (d) { return d.organism ? [d.organism] : []; }],
    ['Data', function (d) { return d.modalities || []; }],
    ['Paper', function (d) { return [paperKey(d)]; }]
  ];

  function matches(d) {
    var hay = [d.title, d.paper, d.organism, d.tissue, d.assembly, d.description].concat(d.modalities || []).join(' ').toLowerCase();
    if (state.q && state.q.split(/\s+/).some(function (w) { return w && hay.indexOf(w) < 0; })) return false;
    return GROUPS.every(function (g) {
      var sel = state.on[g[0]];
      if (!sel || !sel.size) return true;
      var have = g[1](d);
      return Array.from(sel).every(function (v) { return have.indexOf(v) >= 0; });
    });
  }

  function copy(text, btn) {
    var done = function () { var t = btn.textContent; btn.textContent = 'Copied'; setTimeout(function () { btn.textContent = t; }, 1200); };
    if (navigator.clipboard && window.isSecureContext) navigator.clipboard.writeText(text).then(done, done);
    else { var ta = el('textarea', { text: text }); document.body.appendChild(ta); ta.select(); try { document.execCommand('copy'); } catch (e) {} ta.remove(); done(); }
  }
  function localBase() { return ($('local').value || 'http://127.0.0.1:8765').replace(/\/+$/, ''); }
  function snippet(d) {
    return 'from uchrom import ChromData\n\ncd = ChromData.read(\n    "' + urlOf(d) + '",\n    backed=True,   # reads only what is needed, over HTTP\n)\nprint(cd)\n';
  }

  function card(d) {
    var meta = [d.organism, d.assembly, d.tissue].filter(Boolean).join(' · ');
    var facts = [fmtN(d.n_cells) + ' spots / cells'];
    if (d.sections && d.sections.length) facts.push(d.sections.length + ' sections');
    if (d.contact_maps) facts.push(d.contact_maps + ' contact maps');
    if (d.size_mb != null) facts.push(fmtSize(d.size_mb));
    var src = [d.paper];
    var srcEl = el('div', { class: 'src' }, [d.paper || '']);
    if (d.doi) { srcEl.appendChild(document.createTextNode(' · ')); srcEl.appendChild(el('a', { href: 'https://doi.org/' + d.doi, target: '_blank', rel: 'noopener', text: 'doi:' + d.doi })); }
    if (d.source_url) { srcEl.appendChild(document.createTextNode(' · ')); srcEl.appendChild(el('a', { href: d.source_url, target: '_blank', rel: 'noopener', text: 'source' })); }
    if (d.license) srcEl.appendChild(document.createTextNode(' · ' + d.license));
    var open = el('a', { class: 'btn primary', text: 'Open in U-Chrom', title: 'Needs the local browser running (see below)', href: '#' });
    open.addEventListener('click', function (e) { e.preventDefault(); window.open(localBase() + '/?open=' + encodeURIComponent(urlOf(d)), '_blank', 'noopener'); });
    var py = el('button', { class: 'btn', text: 'Python', title: 'Copy a snippet that reads this dataset' });
    py.addEventListener('click', function () { copy(snippet(d), py); });
    var cu = el('button', { class: 'btn', text: 'Copy URL' });
    cu.addEventListener('click', function () { copy(urlOf(d), cu); });
    return el('article', { class: 'card', id: d.id }, [
      el('h3', { text: d.title }), el('div', { class: 'meta', text: meta + (meta ? ' · ' : '') + facts.join(' · ') }),
      d.description ? el('p', { class: 'desc', text: d.description }) : null,
      el('div', { class: 'tags' }, (d.modalities || []).map(function (m) { return el('span', { class: 'tag', text: m }); })),
      srcEl, el('div', { class: 'actions' }, [open, py, cu])
    ]);
  }

  function renderChips() {
    var box = $('chips'); box.textContent = '';
    GROUPS.forEach(function (g) {
      var vals = {};
      state.cat.datasets.forEach(function (d) { g[1](d).forEach(function (v) { vals[v] = (vals[v] || 0) + 1; }); });
      var names = Object.keys(vals).sort(function (a, b) { return vals[b] - vals[a] || a.localeCompare(b); });
      if (names.length < 2) return;
      box.appendChild(el('span', { class: 'grp', text: g[0] }));
      names.forEach(function (v) {
        var on = state.on[g[0]] && state.on[g[0]].has(v);
        var b = el('button', { class: 'chip' + (on ? ' on' : ''), type: 'button', text: v + ' ' + vals[v] });
        b.addEventListener('click', function () {
          var s = state.on[g[0]] || (state.on[g[0]] = new Set());
          if (s.has(v)) s.delete(v); else s.add(v);
          render();
        });
        box.appendChild(b);
      });
    });
  }

  function render() {
    var ds = state.cat.datasets, shown = ds.filter(matches);
    $('grid').textContent = '';
    shown.forEach(function (d) { $('grid').appendChild(card(d)); });
    $('count').textContent = shown.length === ds.length ? ds.length + ' datasets' : shown.length + ' of ' + ds.length + ' datasets';
    renderChips();
  }

  function stats(cat) {
    var ds = cat.datasets, cells = ds.reduce(function (a, d) { return a + (d.n_cells || 0); }, 0);
    var mb = ds.reduce(function (a, d) { return a + (d.size_mb || 0); }, 0);
    var papers = {}; ds.forEach(function (d) { papers[paperKey(d)] = 1; });
    var items = [[String(ds.length), 'datasets'], [fmtN(cells), 'spots / cells'], [String(Object.keys(papers).length), 'papers'], [fmtSize(mb), 'in the atlas']];
    $('stats').textContent = '';
    items.forEach(function (i) { $('stats').appendChild(el('div', { class: 'stat' }, [el('b', { text: i[0] }), el('span', { text: i[1] })])); });
    if (cat.updated) $('updated').textContent = 'Catalog updated ' + cat.updated.replace('T', ' ').replace('Z', ' UTC') + '.';
  }

  function load(url) { return fetch(url, { cache: 'no-cache' }).then(function (r) { if (!r.ok) throw new Error(url + ' -> HTTP ' + r.status); return r.json(); }); }

  function start(cat) {
    state.cat = cat; stats(cat); render();
    var hash = location.hash.slice(1); if (hash && document.getElementById(hash)) document.getElementById(hash).scrollIntoView();
  }

  $('install').textContent = CFG.install || 'pip install "u-chrom[web]"';
  if (CFG.repo) $('repo-link').href = CFG.repo;
  try { var saved = localStorage.getItem('uchrom.atlas.local'); if (saved) $('local').value = saved; } catch (e) {}
  $('local').addEventListener('change', function () { try { localStorage.setItem('uchrom.atlas.local', $('local').value); } catch (e) {} });
  $('q').addEventListener('input', function (e) { state.q = e.target.value.trim().toLowerCase(); if (state.cat) render(); });

  load('catalog.json').then(start).catch(function (e) {
    var m = $('err'); m.hidden = false; m.textContent = 'Could not read the catalog: ' + e.message;
  });
})();
