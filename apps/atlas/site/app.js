// The atlas page: reads catalog.json (deployed next to this page, with the figure index merged in by
// `python apps/atlas/build.py site`) and lists the datasets by study. No framework, no build step.
(function () {
  'use strict';
  var CFG = window.ATLAS_CONFIG || {};
  var DATA = (CFG.dataRoot || '').replace(/\/+$/, '');
  var HOSTED = (CFG.hosted || '').replace(/\/+$/, '');
  var FIG = 'figures/';
  var $ = function (id) { return document.getElementById(id); };
  var state = { cat: null, q: '', on: {}, page: 0 };   // on: {group: Set(values)}; page: 0-based
  var PAGE = 10;         // datasets per page, about: a study is never split, a page holds studies up to this many

  // what the catalog's modality names are called on the page, and their colour (the U-Chrom logo palette)
  var MODS = {
    'Hi-C per spot': ['Contact maps per spot', 'hic'], 'Hi-C per cell': ['Contact maps per cell', 'hic'],
    '3-D coordinates': ['3-D structures', 'xyz'], 'A/B per spot': ['A/B compartments', 'ab'],
    'RNA': ['RNA', 'rna'], 'ATAC per spot': ['Accessibility (ATAC)', 'atac'], 'ATAC per cell': ['Accessibility (ATAC)', 'atac'],
    'images': ['Tissue images', 'img'],
    'signals per spot': ['Signals per locus (IF, RNA)', 'sig']
  };
  var HIDDEN = { 'Hi-C bulk': 1, 'embeddings': 1 };

  function el(tag, attrs, kids) {
    var e = document.createElement(tag);
    Object.keys(attrs || {}).forEach(function (k) {
      if (k === 'text') e.textContent = attrs[k]; else if (k === 'class') e.className = attrs[k]; else e.setAttribute(k, attrs[k]);
    });
    (kids || []).forEach(function (c) { if (c) e.appendChild(typeof c === 'string' ? document.createTextNode(c) : c); });
    return e;
  }
  function fmtSize(mb) { return mb >= 1000 ? (mb / 1000).toFixed(1) + ' GB' : Math.max(1, Math.round(mb)) + ' MB'; }
  function fmtN(n) { return n >= 1e6 ? (n / 1e6).toFixed(1) + 'M' : n >= 1e4 ? Math.round(n / 1e3) + 'k' : n.toLocaleString('en-US'); }
  function fmtMb(bp) { return Math.round(bp / 1e6) + ''; }
  function urlOf(d) { return d.url || (DATA + '/' + String(d.path).replace(/^\/+/, '')); }
  function openUrl(d) { return HOSTED ? HOSTED + '/?open=' + encodeURIComponent(urlOf(d)) : null; }
  function mods(d) { return (d.modalities || []).filter(function (m) { return !HIDDEN[m]; }); }
  function modLabel(m) { return (MODS[m] || [m])[0]; }
  function unit(d) { var s = study(d); return s && /spatial/i.test(s.category || s.kind || '') ? 'spots' : 'cells'; }
  function study(d) { return state.studies[d.study] || null; }
  function nameOf(d) { return d.name || d.title; }

  var localDataset = null;
  var localInstall = 'uv pip install -e packages/chromdata -e packages/uchrom-browser -e packages/uchrom-agent';
  function shellQuote(value) {
    return "'" + String(value).replace(/'/g, "'\\''") + "'";
  }
  function localCommand(d) {
    return 'python -m uchrom_browser ' + shellQuote(urlOf(d));
  }
  function localInstruction(d, question) {
    var prompt = question || 'Inspect this dataset and explain the most useful first analysis.';
    return 'From a U-Chrom checkout, install the source packages if needed with: ' + localInstall + '. Then run the local browser command. '
      + 'After the page opens, paste this instruction into your already-configured Claude Code or Codex U-Chrom MCP. '
      + 'First run uchrom_setup_status, then read the canonical state with uchrom_workspace_snapshot and uchrom_get_selection. '
      + 'Only after that, analyze the question, call uchrom_propose_ui_changes for a pending plan, and wait for the user to Apply it in the local WebUI. Dataset: ' + urlOf(d) + '. Question: ' + prompt;
  }
  function showLocal(d) {
    localDataset = d;
    var dialog = $('handoff-dialog');
    var studyMeta = study(d) || {};
    var facts = $('handoff-facts');
    facts.textContent = '';
    [['Dataset', nameOf(d)], ['Dataset ID', d.id], ['Current catalog version', state.cat.updated || 'not recorded'],
      ['Study', studyMeta.citation || d.paper || '—']].forEach(function (row) {
      facts.appendChild(el('dt', { text: row[0] }));
      facts.appendChild(el('dd', { text: row[1] }));
    });
    $('handoff-question').value = '';
    $('handoff-install').value = localInstall;
    $('handoff-command').value = localCommand(d);
    $('handoff-instruction').value = localInstruction(d, '');
    $('handoff-result').hidden = false;
    if (typeof dialog.showModal === 'function') dialog.showModal();
    else dialog.setAttribute('open', '');
  }

  function copyField(fieldId, buttonId, copiedText, fallbackText) {
    var text = $(fieldId).value;
    if (!text) return;
    if (!navigator.clipboard) {
      $(fieldId).focus();
      $(fieldId).select();
      $(buttonId).textContent = fallbackText;
      return;
    }
    navigator.clipboard.writeText(text).then(function () {
      $(buttonId).textContent = copiedText;
    }).catch(function () {
      $(fieldId).focus();
      $(fieldId).select();
      $(buttonId).textContent = fallbackText;
    });
  }

  $('handoff-question').addEventListener('input', function () {
    if (localDataset) $('handoff-instruction').value = localInstruction(localDataset, $('handoff-question').value.trim());
  });
  $('handoff-copy-command').addEventListener('click', function () {
    copyField('handoff-command', 'handoff-copy-command', 'Copied', 'Select and copy the command');
  });
  $('handoff-copy-install').addEventListener('click', function () {
    copyField('handoff-install', 'handoff-copy-install', 'Copied', 'Select and copy the command');
  });
  $('handoff-copy-instruction').addEventListener('click', function () {
    copyField('handoff-instruction', 'handoff-copy-instruction', 'Copied', 'Select and copy the instruction');
  });

  var GROUPS = [
    ['Type', function (d) { var s = study(d); return s && s.category ? [s.category] : []; }],
    ['Species', function (d) { return d.organism ? [d.organism] : []; }],
    ['Data', function (d) { return mods(d).map(modLabel); }]
  ];

  function matches(d) {
    var s = study(d) || {};
    var hay = [d.name, d.title, d.organism, d.tissue, d.assembly, d.description, s.citation, s.journal, s.kind, s.title]
      .concat(mods(d).map(modLabel)).join(' ').toLowerCase();
    if (state.q && state.q.split(/\s+/).some(function (w) { return w && hay.indexOf(w) < 0; })) return false;
    return GROUPS.every(function (g) {
      var sel = state.on[g[0]];
      if (!sel || !sel.size) return true;
      var have = g[1](d);
      return Array.from(sel).every(function (v) { return have.indexOf(v) >= 0; });
    });
  }

  function figure(d, big) {
    var f = d.figures || {}, k = big ? 'hero.' : '';
    var space = f[k + 'space'], map = f[k + 'map'];
    if (!space && !map) return null;
    var tip = [];
    if (space) tip.push((f.section ? f.section + ': ' : '') + layoutText(f, d));
    if (map) tip.push(mapText(f, d));
    return el('div', { class: 'fig' + (map ? '' : ' single'), title: tip.join(' · ') }, [
      space ? el('img', { src: FIG + space, alt: nameOf(d) + ': ' + layoutText(f, d), loading: 'lazy' }) : null,
      map ? el('img', { class: 'map', src: FIG + map, alt: 'Contact map of ' + nameOf(d), loading: 'lazy' }) : null
    ]);
  }

  function card(d) {
    var href = openUrl(d);
    var facts = [fmtN(d.n_cells) + ' ' + unit(d)];
    if (d.sections && d.sections.length > 1) facts.push(d.sections.length + ' sections');
    if (d.contact_maps) facts.push(d.contact_maps + (d.contact_maps === 1 ? ' contact map' : ' contact maps'));
    var fig = figure(d, false);
    var title = el('h3', { text: nameOf(d) });
    var kids = [
      fig && href ? el('a', { class: 'fig-link', href: href, target: '_blank', rel: 'noopener', tabindex: '-1', 'aria-hidden': 'true' }, [fig]) : fig,
      el('div', { class: 'body' }, [
        title,
        el('p', { class: 'meta', text: [d.organism, d.tissue, d.assembly].filter(Boolean).join(' · ') }),
        el('p', { class: 'facts', text: facts.join(' · ') }),
        el('ul', { class: 'mods' }, mods(d).map(function (m) {
          return el('li', { class: 'mod ' + ((MODS[m] || [])[1] || 'other') }, [modLabel(m)]);
        })),
        d.description ? el('p', { class: 'desc', text: d.description }) : null,
        d.note ? el('p', { class: 'note', text: d.note }) : null,
        el('div', { class: 'actions' }, [
          href ? el('a', { class: 'open', href: href, target: '_blank', rel: 'noopener',
                           title: 'Open in the U-Chrom browser (the first open after a quiet spell takes a few seconds)' },
                    ['Open in browser ', el('span', { 'aria-hidden': 'true', text: '→' })]) : null,
          el('button', { class: 'continue-local', type: 'button', title: 'Prepare a local browser command and MCP instruction' }, ['Continue locally']),
          d.download ? el('a', { class: 'download', href: DATA + '/' + d.download, download: '',
                                 title: 'The whole dataset as one .cdz file (a ChromData store in one zip): open it with the U-Chrom browser or ChromData.read' },
                          [el('span', { class: 'dl-icon', 'aria-hidden': 'true', text: '↓' }), 'Download',
                           el('span', { class: 'dl-size', text: '.cdz · ' + fmtSize(d.download_mb || d.size_mb || 0) })]) : null
        ])
      ])
    ];
    var article = el('article', { class: 'card', id: d.id }, kids);
    article.querySelector('.continue-local').addEventListener('click', function () { showLocal(d); });
    return article;
  }

  function studyBlock(s, ds) {
    var links = el('p', { class: 'links' });
    var add = function (node) { if (links.childNodes.length) links.appendChild(document.createTextNode(' · ')); links.appendChild(node); };
    if (s.doi) add(el('a', { href: 'https://doi.org/' + s.doi, target: '_blank', rel: 'noopener', text: 'Paper' }));
    if (s.source_url) add(el('a', { href: s.source_url, target: '_blank', rel: 'noopener', text: s.source || 'Data source' }));
    if (s.license) add(document.createTextNode(/^see /.test(s.license) ? 'Licence as deposited' : 'Licence ' + s.license));
    return el('section', { class: 'study', id: 'study-' + s.id }, [
      el('header', { class: 'study-head' }, [
        el('p', { class: 'kind', text: s.kind || '' }),
        el('h3', {}, [s.citation || s.id, s.journal ? el('span', { class: 'journal', text: s.journal }) : null]),
        s.title ? el('p', { class: 'paper', text: s.title }) : null,
        s.summary ? el('p', { class: 'summary', text: s.summary }) : null,
        links
      ]),
      el('div', { class: 'cards' }, ds.map(card))
    ]);
  }

  function renderChips() {
    var box = $('chips'); box.textContent = '';
    GROUPS.forEach(function (g) {
      var vals = {};
      state.cat.datasets.forEach(function (d) { g[1](d).forEach(function (v) { vals[v] = (vals[v] || 0) + 1; }); });
      var names = Object.keys(vals).sort(function (a, b) { return vals[b] - vals[a] || a.localeCompare(b); });
      if (names.length < 2) return;
      var grp = el('div', { class: 'grp' }, [el('span', { class: 'grp-name', text: g[0] })]);
      names.forEach(function (v) {
        var on = state.on[g[0]] && state.on[g[0]].has(v);
        var b = el('button', { class: 'chip' + (on ? ' on' : ''), type: 'button', 'aria-pressed': on ? 'true' : 'false', text: v });
        b.addEventListener('click', function () {
          var s = state.on[g[0]] || (state.on[g[0]] = new Set());
          if (s.has(v)) s.delete(v); else s.add(v);
          refilter();
        });
        grp.appendChild(b);
      });
      box.appendChild(grp);
    });
  }

  // the studies that have datasets to show, with those datasets, in the catalogue's order; then cut into pages
  function groups() {
    var shown = state.cat.datasets.filter(matches), out = [];
    state.order.forEach(function (sid) {
      var ds = shown.filter(function (d) { return (d.study || '') === sid; });
      if (ds.length) out.push({ s: state.studies[sid] || { id: sid, citation: ds[0].paper }, ds: ds });
    });
    return { shown: shown, groups: out };
  }
  function paginate(gs) {
    var pages = [], cur = [], n = 0;
    gs.forEach(function (g) {
      if (cur.length && n + g.ds.length > PAGE) { pages.push(cur); cur = []; n = 0; }
      cur.push(g); n += g.ds.length;
    });
    if (cur.length) pages.push(cur);
    return pages;
  }
  function pageOf(id) {                     // the page that shows a dataset or study (a link to #id)
    var pages = paginate(groups().groups);
    for (var i = 0; i < pages.length; i++) {
      if (pages[i].some(function (g) { return 'study-' + g.s.id === id || g.ds.some(function (d) { return d.id === id; }); })) return i;
    }
    return -1;
  }

  // what is shown: "All datasets", or the chosen filters and the search words
  function heading(shown, nStudies) {
    var parts = [];
    GROUPS.forEach(function (g) { var sel = state.on[g[0]]; if (sel) sel.forEach(function (v) { parts.push(v); }); });
    if (state.q) parts.push('“' + state.q + '”');
    var count = shown.length + (shown.length === 1 ? ' dataset' : ' datasets') + ' · ' + nStudies + (nStudies === 1 ? ' study' : ' studies');
    return el('div', { class: 'results', id: 'results' }, [el('h3', { text: parts.length ? parts.join(' · ') : 'All datasets' }), el('span', { text: count })]);
  }

  function pager(n) {
    var box = $('pager'); box.textContent = '';
    box.hidden = n < 2;
    if (n < 2) return;
    var go = function (i) {
      return function () { state.page = i; render(); var r = $('results'); if (r) r.scrollIntoView({ behavior: 'smooth', block: 'start' }); };
    };
    var prev = el('button', { type: 'button', class: 'pg-step', text: '← Previous' });
    if (state.page === 0) prev.disabled = true; else prev.addEventListener('click', go(state.page - 1));
    box.appendChild(prev);
    for (var i = 0; i < n; i++) {
      var b = el('button', { type: 'button', class: 'pg' + (i === state.page ? ' on' : ''), text: String(i + 1), 'aria-label': 'Page ' + (i + 1) });
      if (i === state.page) b.setAttribute('aria-current', 'page'); else b.addEventListener('click', go(i));
      box.appendChild(b);
    }
    var next = el('button', { type: 'button', class: 'pg-step', text: 'Next →' });
    if (state.page === n - 1) next.disabled = true; else next.addEventListener('click', go(state.page + 1));
    box.appendChild(next);
  }

  function render() {
    var r = groups(), pages = paginate(r.groups), box = $('studies');
    state.page = Math.max(0, Math.min(state.page, pages.length - 1));
    box.textContent = '';
    if (r.shown.length) box.appendChild(heading(r.shown, r.groups.length));
    (pages[state.page] || []).forEach(function (g) { box.appendChild(studyBlock(g.s, g.ds)); });
    pager(pages.length);
    $('empty').hidden = r.shown.length > 0;
    renderChips();
  }
  function refilter() { state.page = 0; render(); }

  function stats(cat) {
    var ds = cat.datasets, cells = ds.reduce(function (a, d) { return a + (d.n_cells || 0); }, 0);
    var species = {}; ds.forEach(function (d) { if (d.organism) species[d.organism] = 1; });
    var box = $('stats'); box.textContent = '';
    var studies = {}; ds.forEach(function (d) { studies[d.study || d.paper || d.id] = 1; });
    [[String(ds.length), 'datasets'], [fmtN(cells), 'cells and spots'], [String(Object.keys(studies).length), 'studies'],
     [String(Object.keys(species).length), 'species']].forEach(function (i) {
      box.appendChild(el('div', {}, [el('dt', { text: i[1] }), el('dd', { text: i[0] })]));
    });
    if (cat.updated) $('updated').textContent = 'Catalogue updated ' + cat.updated.slice(0, 10) + '.';
  }

  function colouredBy(f) { return /cell_?type|anno/i.test(f.color_by || '') ? 'cell type' : 'cluster'; }
  // what a figure shows, in words: "spots coloured by cluster" / "cells in rna_umap, coloured by cell type"
  function layoutText(f, d) {
    if (f.layout === 'structure') return '3-D structure of cell ' + f.layout_key + ', chromosomes coloured';
    var what = f.layout === 'embedding' ? unit(d) + ' in ' + (f.layout_key || 'an embedding') : unit(d);
    return f.color_by ? what + (f.layout === 'embedding' ? ', ' : ' ') + 'coloured by ' + colouredBy(f) : what;
  }
  function mapText(f, d) {
    return f.chrom + ':' + fmtMb(f.start) + '–' + fmtMb(f.end) + ' Mb at ' + (f.resolution / 1e3) + ' kb, all ' + unit(d) + ' merged';
  }

  function start(cat) {
    state.cat = cat;
    state.studies = {}; state.order = [];
    (cat.studies || []).forEach(function (s) { state.studies[s.id] = s; state.order.push(s.id); });
    cat.datasets.forEach(function (d) { var k = d.study || ''; if (state.order.indexOf(k) < 0) state.order.push(k); });
    var hash = location.hash.slice(1), at = hash ? pageOf(hash) : -1;
    if (at > 0) state.page = at;
    stats(cat); render();
    $('hint').hidden = !HOSTED;
    if (hash && document.getElementById(hash)) document.getElementById(hash).scrollIntoView();
  }

  $('q').addEventListener('input', function (e) { state.q = e.target.value.trim().toLowerCase(); if (state.cat) refilter(); });
  $('reset').addEventListener('click', function () { state.q = ''; state.on = {}; $('q').value = ''; refilter(); });
  fetch('catalog.json', { cache: 'no-cache' }).then(function (r) { if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); }).then(start).catch(function (e) {
    var m = $('err'); m.hidden = false; m.textContent = 'Could not read the catalogue: ' + e.message;
  });
})();
