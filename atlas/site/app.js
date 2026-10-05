// The atlas page: reads catalog.json (deployed next to this page) and lists the datasets.
// No framework, no build step.
(function () {
  'use strict';
  var CFG = window.ATLAS_CONFIG || {};
  var DATA = (CFG.dataRoot || '').replace(/\/+$/, '');
  var HOSTED = (CFG.hosted || '').replace(/\/+$/, '');
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

  var GROUPS = [
    ['Organism', function (d) { return d.organism ? [d.organism] : []; }],
    ['Data', function (d) { return d.modalities || []; }]
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

  function fact(value, label) { return el('div', { class: 'fact' }, [el('b', { text: value }), el('span', { text: label })]); }

  function card(d) {
    var meta = [d.organism, d.tissue, d.assembly].filter(Boolean).join(' · ');
    var facts = [fact(fmtN(d.n_cells), 'cells / spots')];
    if (d.sections && d.sections.length > 1) facts.push(fact(String(d.sections.length), 'sections'));
    if (d.contact_maps) facts.push(fact(String(d.contact_maps), d.contact_maps === 1 ? 'contact map' : 'contact maps'));
    if (d.size_mb != null) facts.push(fact(fmtSize(d.size_mb), 'on disk'));
    var src = el('div', { class: 'src' }, [d.paper || '']);
    [[d.doi, 'https://doi.org/' + d.doi, 'doi'], [d.source_url, d.source_url, 'source']].forEach(function (l) {
      if (l[0]) { src.appendChild(document.createTextNode(' · ')); src.appendChild(el('a', { href: l[1], target: '_blank', rel: 'noopener', text: l[2] })); }
    });
    if (d.license) src.appendChild(document.createTextNode(' · ' + d.license));
    var open = HOSTED ? el('a', { class: 'btn', text: 'Open', href: HOSTED + '/?open=' + encodeURIComponent(urlOf(d)), target: '_blank', rel: 'noopener',
                                 title: 'Open in the U-Chrom browser (the first open after a quiet period can take a few seconds)' }) : null;
    return el('article', { class: 'card', id: d.id }, [
      el('div', { class: 'head' }, [el('div', {}, [el('h3', { text: d.title }), el('div', { class: 'meta', text: meta })]), open]),
      d.description ? el('p', { class: 'desc', text: d.description }) : null,
      el('div', { class: 'facts' }, facts),
      el('div', { class: 'tags' }, (d.modalities || []).map(function (m) { return el('span', { class: 'tag', text: m }); })),
      src
    ]);
  }

  function renderChips() {
    var box = $('chips'); box.textContent = '';
    GROUPS.forEach(function (g) {
      var vals = {};
      state.cat.datasets.forEach(function (d) { g[1](d).forEach(function (v) { vals[v] = (vals[v] || 0) + 1; }); });
      var names = Object.keys(vals).sort(function (a, b) { return vals[b] - vals[a] || a.localeCompare(b); });
      if (names.length < 2) return;
      names.forEach(function (v) {
        var on = state.on[g[0]] && state.on[g[0]].has(v);
        var b = el('button', { class: 'chip' + (on ? ' on' : ''), type: 'button', text: v });
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
    var shown = state.cat.datasets.filter(matches);
    $('grid').textContent = '';
    shown.forEach(function (d) { $('grid').appendChild(card(d)); });
    $('empty').hidden = shown.length > 0;
    renderChips();
  }

  function stats(cat) {
    var ds = cat.datasets, cells = ds.reduce(function (a, d) { return a + (d.n_cells || 0); }, 0);
    var papers = {}; ds.forEach(function (d) { papers[d.paper || d.id] = 1; });
    $('stats').textContent = '';
    [[String(ds.length), 'datasets'], [fmtN(cells), 'cells / spots'], [String(Object.keys(papers).length), 'studies']].forEach(function (i) {
      $('stats').appendChild(el('div', { class: 'stat' }, [el('b', { text: i[0] }), el('span', { text: i[1] })]));
    });
    if (cat.updated) $('updated').textContent = 'Updated ' + cat.updated.slice(0, 10) + '.';
  }

  function start(cat) {
    state.cat = cat; stats(cat); render();
    var hash = location.hash.slice(1); if (hash && document.getElementById(hash)) document.getElementById(hash).scrollIntoView();
  }

  if (CFG.repo) $('repo-link').href = CFG.repo;
  $('q').addEventListener('input', function (e) { state.q = e.target.value.trim().toLowerCase(); if (state.cat) render(); });
  fetch('catalog.json', { cache: 'no-cache' }).then(function (r) { if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); }).then(start).catch(function (e) {
    var m = $('err'); m.hidden = false; m.textContent = 'Could not read the catalog: ' + e.message;
  });
})();
