// The atlas page's hero: from a tissue section to one cell's genome, in line art, from real data (hero.json,
// written by atlas/hero_data.py).  One world frame in units of the section's size: the section, a field of view
// placed at its real scale at a Purkinje-layer point, and the traced chromatin of one nucleus of that field.
// A camera zooms section -> field -> nucleus (log scale); each layer fades in and out with the zoom; the
// chromatin turns about the vertical axis.  The only motion is the camera, the drawing and the turning.
(function () {
  'use strict';
  var canvas = document.getElementById('hero-canvas');
  if (!canvas || !canvas.getContext) return;
  var ctx = canvas.getContext('2d');
  var data = null, W = 0, dpr = 1, colors = {}, startT = null, running = false, visible = true;
  var reduced = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  // ---- helpers -------------------------------------------------------------------------------------------------
  function css(name, fb) {
    var v = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
    return v || fb;
  }
  function readColors() {
    colors = { ink: css('--ink', '#1c1d21'), muted: css('--muted', '#73767d'), paper: css('--paper', '#fbfaf7'),
               accent: css('--atac', '#dc740d'), blue: css('--ab', '#3651a2'), green: css('--rna', '#5b8f34') };
  }
  function clamp(x, a, b) { return Math.max(a, Math.min(b, x)); }
  function smooth(x) { x = clamp(x, 0, 1); return x * x * (3 - 2 * x); }
  function band(z, a, b, c, d) { return smooth((z - a) / (b - a)) * (1 - smooth((z - c) / (d - c))); }
  function lerp(a, b, t) { return a + (b - a) * t; }
  function alpha(c, a) {           // a colour of the page with an opacity
    var m = /^#([0-9a-f]{6})$/i.exec(c);
    if (!m) return c;
    var n = parseInt(m[1], 16);
    return 'rgba(' + (n >> 16) + ',' + ((n >> 8) & 255) + ',' + (n & 255) + ',' + a.toFixed(3) + ')';
  }

  // ---- the world ------------------------------------------------------------------------------------------------
  var world = {};
  function build(d) {
    var s = d.section, f = d.field;
    var um = 1 / s.size_um;                                     // 1 um in section units
    // turn the field so that its granular layer (down in the image) points where the section's does
    var gd = s.granular_dir, theta = Math.atan2(gd[1], gd[0]) - Math.PI / 2;
    var ct = Math.cos(theta), st = Math.sin(theta), half = f.size_um / 2;
    function fieldToWorld(x, y) {                              // field um -> section units
      var dx = (x - half) * um, dy = (y - half) * um;
      return [s.zoom[0] + ct * dx - st * dy, s.zoom[1] + st * dx + ct * dy];
    }
    world = { um: um, ct: ct, st: st, fieldToWorld: fieldToWorld, section: s, field: f,
              cells: f.cells.map(function (c) { var p = fieldToWorld(c[0], c[1]); return [p[0], p[1], c[2] * um, c[3]]; }),
              box: [[0, 0], [f.size_um, 0], [f.size_um, f.size_um], [0, f.size_um]].map(function (p) { return fieldToWorld(p[0], p[1]); }),
              nuclei: d.nuclei.map(function (n) {
                var c = fieldToWorld(n.x, n.y);
                return { cx: c[0], cy: c[1], r: n.r * um, rUm: n.r, type: n.type, cell: n.cell, traces: n.traces.map(function (t) {
                  var p = t.p, k = p.length / 3, xs = new Float32Array(k), ys = new Float32Array(k), zs = new Float32Array(k);
                  for (var i = 0; i < k; i++) {                    // um, turned like the field
                    var x = p[3 * i] / 100, y = p[3 * i + 1] / 100;
                    xs[i] = ct * x - st * y; ys[i] = st * x + ct * y; zs[i] = p[3 * i + 2] / 100;
                  }
                  var brk = new Uint8Array(k); t.b.forEach(function (b) { brk[b] = 1; });
                  var mk = new Uint8Array(k); t.k27.forEach(function (j) { mk[j] = 1; });
                  return { chrom: t.chrom, x: xs, y: ys, z: zs, brk: brk, mk: mk, n: k };
                }) };
              }) };
    world.nuclei.forEach(function (n) {           // the radius (um) that holds 90 % of the traced loci
      var d = [];
      n.traces.forEach(function (t) { for (var i = 0; i < t.n; i++) d.push(Math.hypot(t.x[i], t.y[i], t.z[i])); });
      d.sort(function (a, b) { return a - b; });
      n.envUm = Math.max(n.rUm, 1.06 * d[Math.floor(0.9 * (d.length - 1))]);
    });
  }

  // ---- camera ---------------------------------------------------------------------------------------------------
  function camSection() { var s = world.section; return { x: s.w / 2, y: s.h / 2, k: 0.9 * W / Math.max(s.w, s.h) }; }
  function camField() { var z = world.section.zoom; return { x: z[0], y: z[1], k: 0.9 * W / (world.field.size_um * world.um) }; }
  function camNucleus(n) { return { x: n.cx, y: n.cy, k: 0.42 * W / (n.envUm * world.um) }; }
  function mix(a, b, t) {                                       // zoom on a log scale, the centre follows the scale
    var lk = lerp(Math.log(a.k), Math.log(b.k), t);
    var u = (Math.log(b.k) === Math.log(a.k)) ? t : (lk - Math.log(a.k)) / (Math.log(b.k) - Math.log(a.k));
    return { x: lerp(a.x, b.x, u), y: lerp(a.y, b.y, u), k: Math.exp(lk) };
  }

  // ---- timeline (s) ---------------------------------------------------------------------------------------------
  var T = { draw: 2.4, mark: 3.2, toField: 5.0, holdField: 6.8, toCell: 8.6, drawChrom: 11.0, spinEnd: 17.0, back: 19.0 };
  function state(t) {
    var cycle = Math.floor(t / T.back), u = t - cycle * T.back;
    var n = world.nuclei[cycle % world.nuclei.length];
    var A = camSection(), B = camField(), C = camNucleus(n), cam;
    if (u < T.mark) cam = A;
    else if (u < T.toField) cam = mix(A, B, smooth((u - T.mark) / (T.toField - T.mark)));
    else if (u < T.holdField) cam = B;
    else if (u < T.toCell) cam = mix(B, C, smooth((u - T.holdField) / (T.toCell - T.holdField)));
    else if (u < T.spinEnd) cam = C;
    else cam = mix(C, A, smooth((u - T.spinEnd) / (T.back - T.spinEnd)));
    // zoom level: 0 section, 0.5 field, 1 nucleus
    var z0 = Math.log(A.k), z1 = Math.log(B.k), z2 = Math.log(C.k), lk = Math.log(cam.k);
    var z = lk <= z1 ? 0.5 * (lk - z0) / (z1 - z0) : 0.5 + 0.5 * (lk - z1) / (z2 - z1);
    return { u: u, cycle: cycle, n: n, cam: cam, z: clamp(z, 0, 1), first: cycle === 0 };
  }

  // ---- drawing --------------------------------------------------------------------------------------------------
  function polyline(pts, cam, frac) {
    var m = Math.max(2, Math.ceil(pts.length * frac));
    ctx.beginPath();
    for (var i = 0; i < Math.min(m, pts.length); i++) {
      var x = (pts[i][0] - cam.x) * cam.k + W / 2, y = (pts[i][1] - cam.y) * cam.k + W / 2;
      if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
    }
    ctx.stroke();
  }

  function drawSection(S, a) {
    if (a <= 0.01) return;
    var s = world.section, cam = S.cam;
    var frac = S.first ? smooth(S.u / T.draw) : 1;
    ctx.lineJoin = 'round'; ctx.lineCap = 'round';
    ctx.strokeStyle = alpha(colors.ink, 0.85 * a); ctx.lineWidth = 1.4;
    s.outline.forEach(function (p) { polyline(p, cam, frac); });
    ctx.strokeStyle = alpha(colors.ink, 0.55 * a); ctx.lineWidth = 1;
    s.granular.forEach(function (p) { polyline(p, cam, frac); });
    ctx.setLineDash([3, 3]); ctx.strokeStyle = alpha(colors.accent, 0.7 * a); ctx.lineWidth = 1;
    s.purkinje.forEach(function (p) { polyline(p, cam, frac); });
    ctx.setLineDash([]);
    // the field of view, at its real size, and a pulse where it lies
    var show = S.first ? smooth((S.u - T.draw) / 0.5) : 1;
    if (show > 0) {
      ctx.strokeStyle = alpha(colors.accent, a * show); ctx.lineWidth = 1.3;
      polyline(world.box.concat([world.box[0]]), cam, 1);
      var z = world.section.zoom, cx = (z[0] - cam.x) * cam.k + W / 2, cy = (z[1] - cam.y) * cam.k + W / 2;
      var ph = (S.u % 1.6) / 1.6;
      ctx.beginPath(); ctx.arc(cx, cy, 4 + 14 * ph, 0, 2 * Math.PI);
      ctx.strokeStyle = alpha(colors.accent, a * show * (1 - ph)); ctx.stroke();
    }
  }

  function drawField(S, a, target) {
    if (a <= 0.01) return;
    var cam = S.cam, cells = world.cells;
    var grow = smooth((S.u - T.mark - 0.3) / 1.6);
    if (S.u >= T.spinEnd || S.u < T.mark) grow = 1;
    for (var i = 0; i < cells.length; i++) {
      var c = cells[i], x = (c[0] - cam.x) * cam.k + W / 2, y = (c[1] - cam.y) * cam.k + W / 2, r = c[2] * cam.k;
      if (x < -r || y < -r || x > W + r || y > W + r) continue;
      var g = clamp(grow * 1.6 - (i % 7) * 0.08, 0, 1);       // nuclei appear in waves
      if (g <= 0) continue;
      ctx.beginPath(); ctx.arc(x, y, Math.max(0.5, r * g), 0, 2 * Math.PI);
      var pk = c[3] === 1;
      ctx.strokeStyle = alpha(pk ? colors.accent : colors.ink, (pk ? 0.85 : 0.5) * a * g);
      ctx.lineWidth = pk ? 1.2 : 0.8; ctx.stroke();
    }
    // the nucleus about to be opened
    var n = target, x0 = (n.cx - cam.x) * cam.k + W / 2, y0 = (n.cy - cam.y) * cam.k + W / 2;
    var on = smooth((S.u - T.toField) / 0.6) * (1 - smooth((S.u - T.toCell) / 0.4));
    if (on > 0) {
      var ph = ((S.u - T.toField) % 1.2) / 1.2;
      ctx.beginPath(); ctx.arc(x0, y0, n.r * cam.k + 3 + 10 * ph, 0, 2 * Math.PI);
      ctx.strokeStyle = alpha(colors.accent, a * on * (1 - ph)); ctx.lineWidth = 1.4; ctx.stroke();
    }
  }

  function drawNucleus(S, a) {
    if (a <= 0.01) return;
    var n = S.n, cam = S.cam, k = cam.k * world.um;             // um -> px
    var cx = (n.cx - cam.x) * cam.k + W / 2, cy = (n.cy - cam.y) * cam.k + W / 2;
    // the envelope: from the field's sphere-equivalent nucleus to the outline that holds the traced loci
    var R = lerp(n.rUm, n.envUm, smooth((S.z - 0.8) / 0.2)) * k;
    ctx.beginPath(); ctx.arc(cx, cy, R, 0, 2 * Math.PI);
    ctx.strokeStyle = alpha(colors.ink, 0.5 * a); ctx.lineWidth = 1.2; ctx.stroke();
    var spin = reduced ? 0.6 : (S.u - T.toCell + 2) * 0.32, cs = Math.cos(spin), sn = Math.sin(spin);
    var drawn = reduced ? 1 : smooth((S.u - (T.toCell - 0.4)) / (T.drawChrom - T.toCell + 0.4));
    var hi = reduced ? 1 : smooth((S.u - T.drawChrom + 0.5) / 1.5);
    var total = 0;
    n.traces.forEach(function (t) { total += t.n; });
    var budget = Math.ceil(total * drawn), used = 0;
    // segments split by depth: the far half fainter, drawn first; chr1 (both copies) in blue
    var far = new Path2D(), near = new Path2D(), farHi = new Path2D(), nearHi = new Path2D();
    n.traces.forEach(function (t) {
      var m = Math.min(t.n, Math.max(0, budget - used));
      used += t.n;
      var hl = t.chrom === 'chr1', px0 = 0, py0 = 0, d0 = 0;
      for (var i = 0; i < m; i++) {
        var x = cs * t.x[i] + sn * t.z[i], d = -sn * t.x[i] + cs * t.z[i];
        var px = cx + x * k, py = cy + t.y[i] * k;
        if (i > 0 && !t.brk[i]) {
          var path = (d + d0 >= 0) ? (hl ? nearHi : near) : (hl ? farHi : far);
          path.moveTo(px0, py0); path.lineTo(px, py);
        }
        px0 = px; py0 = py; d0 = d;
      }
    });
    ctx.lineJoin = 'round'; ctx.lineCap = 'round';
    ctx.lineWidth = 0.75;
    ctx.strokeStyle = alpha(colors.ink, 0.26 * a); ctx.stroke(far);
    ctx.strokeStyle = alpha(colors.ink, 0.62 * a); ctx.stroke(near);
    ctx.lineWidth = 1.3;
    ctx.strokeStyle = alpha(colors.blue, (0.25 + 0.35 * hi) * a); ctx.stroke(farHi);
    ctx.strokeStyle = alpha(colors.blue, (0.45 + 0.5 * hi) * a); ctx.stroke(nearHi);
    // H3K27ac-rich loci of this cell
    if (hi > 0) {
      ctx.fillStyle = alpha(colors.green, 0.85 * hi * a);
      n.traces.forEach(function (t) {
        for (var i = 0; i < t.n; i++) {
          if (!t.mk[i]) continue;
          var x = cs * t.x[i] + sn * t.z[i];
          ctx.beginPath(); ctx.arc(cx + x * k, cy + t.y[i] * k, 1.4, 0, 2 * Math.PI); ctx.fill();
        }
      });
    }
  }

  function scaleBar(S) {
    var cam = S.cam, umPx = cam.k * world.um;                    // px per um
    var nice = [1, 2, 5, 10, 20, 50, 100, 200, 500, 1000], L = nice[0];
    for (var i = 0; i < nice.length; i++) if (nice[i] * umPx <= W * 0.22) L = nice[i];
    var len = L * umPx, x0 = 14, y0 = W - 16;
    ctx.strokeStyle = alpha(colors.ink, 0.8); ctx.lineWidth = 1.5;
    ctx.beginPath(); ctx.moveTo(x0, y0); ctx.lineTo(x0 + len, y0); ctx.stroke();
    ctx.fillStyle = alpha(colors.ink, 0.85); ctx.font = '500 12px Inter, system-ui, sans-serif';
    ctx.fillText((L >= 1000 ? L / 1000 + ' mm' : L + ' µm'), x0, y0 - 7);
    var label = S.z < 0.25 ? 'tissue section' : S.z < 0.75 ? 'field of view · nuclei' :
      (S.n.type + ' cell · chromatin traced in 3-D');
    ctx.fillStyle = alpha(colors.muted, 0.95); ctx.font = '12px Inter, system-ui, sans-serif';
    ctx.textAlign = 'right'; ctx.fillText(label, W - 14, y0); ctx.textAlign = 'left';
  }

  function frame(t) {
    var S = state(t);
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, W, W);
    var z = S.z;
    drawSection(S, 1 - smooth((z - 0.32) / 0.2));
    drawField(S, band(z, 0.18, 0.4, 0.78, 0.92), S.n);
    drawNucleus(S, smooth((z - 0.72) / 0.18));
    scaleBar(S);
  }

  // ---- loop -----------------------------------------------------------------------------------------------------
  function resize() {
    var w = canvas.parentElement.clientWidth;
    if (!w) return;
    W = w; dpr = Math.min(2, window.devicePixelRatio || 1);
    canvas.width = Math.round(W * dpr); canvas.height = Math.round(W * dpr);
    canvas.style.width = W + 'px'; canvas.style.height = W + 'px';
  }
  function tick(ts) {
    if (!running) return;
    if (startT === null) startT = ts;
    frame((ts - startT) / 1000);
    requestAnimationFrame(tick);
  }
  function play() { if (!running && visible && data && !reduced) { running = true; requestAnimationFrame(tick); } }
  function pause() { running = false; }

  fetch('hero.json').then(function (r) { if (!r.ok) throw new Error(r.status); return r.json(); }).then(function (d) {
    data = d; build(d); readColors(); resize();
    var fixed = /[?&]hero=([0-9.]+)/.exec(location.search);       // ?hero=12.5: that moment, still (review)
    if (fixed) { reduced = true; frame(parseFloat(fixed[1])); window.heroFrame = function (t) { readColors(); frame(t); }; return; }
    if (reduced) frame(T.spinEnd - 1); else play();
    if (window.IntersectionObserver) {
      new IntersectionObserver(function (es) {
        visible = es[0].isIntersecting;
        if (visible) { if (startT !== null) startT = null; play(); } else pause();
      }).observe(canvas);
    }
    window.addEventListener('resize', function () { resize(); if (reduced) frame(T.spinEnd - 1); });
    if (window.matchMedia) {
      window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', function () { readColors(); });
    }
    document.dispatchEvent(new CustomEvent('hero-ready', { detail: d }));
  }).catch(function () { canvas.parentElement.classList.add('hero-failed'); });
})();
