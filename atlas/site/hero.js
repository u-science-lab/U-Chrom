// The atlas page's hero, a diagram in line art (hero.json, written by atlas/hero_data.py): a tissue section on a
// slide seen at an angle and, lifted from one of its cells, that cell's nucleus with its 3-D genome (real
// single-cell Hi-C structures; three chromosome copies in colour).  The lifted cell moves from cell to cell; each
// one draws its own genome, which turns about the vertical axis.
(function () {
  'use strict';
  var canvas = document.getElementById('hero-canvas');
  if (!canvas || !canvas.getContext) return;
  var ctx = canvas.getContext('2d');
  var data = null, W = 0, dpr = 1, colors = {}, startT = null, running = false, visible = true;
  var reduced = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  var geo = null, cells = [];

  // ---- helpers -------------------------------------------------------------------------------------------------
  function css(name, fb) {
    var v = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
    return v || fb;
  }
  function readColors() {
    colors = { ink: css('--ink', '#1c1d21'), muted: css('--muted', '#73767d'), paper: css('--paper', '#fbfaf7'),
               hl: [css('--atac', '#dc740d'), css('--rna', '#5b8f34'), css('--hic', '#be2d2a')] };
  }
  function clamp(x, a, b) { return Math.max(a, Math.min(b, x)); }
  function smooth(x) { x = clamp(x, 0, 1); return x * x * (3 - 2 * x); }
  function lerp(a, b, t) { return a + (b - a) * t; }
  function alpha(c, a) {           // a colour of the page with an opacity
    var m = /^#([0-9a-f]{6})$/i.exec(c);
    if (!m) return c;
    var n = parseInt(m[1], 16);
    return 'rgba(' + (n >> 16) + ',' + ((n >> 8) & 255) + ',' + (n & 255) + ',' + clamp(a, 0, 1).toFixed(3) + ')';
  }

  // ---- the slide: section units -> screen, an oblique view (far edge up and to the right) ----------------------
  var SHEAR = 0.42, FLAT = 0.46, PAD = 0.08;
  function layout() {
    var t = data.tissue, sw = t.w + 2 * PAD, sh = t.h + 2 * PAD;
    var S = 0.94 * W / (sw + SHEAR * sh);                      // the slide, sheared, fits the width
    var cx = W / 2, cy = 0.8 * W;
    function P(x, y) {                                          // tissue x, y (y down = towards the viewer)
      var u = x - t.w / 2, v = y - t.h / 2;
      return [cx + S * (u - SHEAR * v), cy + S * FLAT * v];
    }
    var slide = [[-PAD, -PAD], [t.w + PAD, -PAD], [t.w + PAD, t.h + PAD], [-PAD, t.h + PAD]].map(function (p) { return P(p[0], p[1]); });
    var lines = function (ls) { return ls.map(function (l) { return l.map(function (p) { return P(p[0], p[1]); }); }); };
    var dots = [], d = t.dots;
    for (var i = 0; i < d.length; i += 2) dots.push(P(d[i] / 1e4, d[i + 1] / 1e4));
    geo = { P: P, S: S, slide: slide, outline: lines(t.outline), granular: lines(t.granular), dots: dots,
            somata: t.somata.map(function (p) { return P(p[0], p[1]); }), somaR: t.soma_r * S,
            picks: t.picks, nucleus: { x: 0.5 * W, y: 0.275 * W, r: 0.24 * W } };
  }

  function build(d) {
    cells = d.cells.map(function (c) {
      return { type: c.type, cell: c.cell, copies: c.copies.map(function (cp) {
        var p = cp.p, k = p.length / 3, xs = new Float32Array(k), ys = new Float32Array(k), zs = new Float32Array(k);
        for (var i = 0; i < k; i++) { xs[i] = p[3 * i] / 1000; ys[i] = p[3 * i + 1] / 1000; zs[i] = p[3 * i + 2] / 1000; }
        return { hl: cp.hl, x: xs, y: ys, z: zs, n: k };
      }) };
    });
  }

  // ---- timeline (s): an introduction for the first cell, then one cell after another --------------------------
  var INTRO = { slide: 1.8, mark: 1.6, cone: 2.2, ring: 2.8, chrom: 3.3, end: 9.5 }, STEP = 8.5, MOVE = 1.3, DRAW = 2.6;
  function state(t) {
    var n = cells.length;
    if (t < INTRO.end) return { t: t, intro: true, cell: 0, prev: -1, u: t, move: 1 };
    var k = Math.floor((t - INTRO.end) / STEP), u = t - INTRO.end - k * STEP;
    return { t: t, intro: false, cell: (k + 1) % n, prev: k % n, u: u, move: smooth(u / MOVE) };
  }

  // ---- drawing --------------------------------------------------------------------------------------------------
  function poly(pts, frac, close) {
    var m = Math.max(2, Math.ceil(pts.length * frac));
    ctx.beginPath();
    for (var i = 0; i < Math.min(m, pts.length); i++) { if (i === 0) ctx.moveTo(pts[i][0], pts[i][1]); else ctx.lineTo(pts[i][0], pts[i][1]); }
    if (close && frac >= 1) ctx.closePath();
    ctx.stroke();
  }

  function drawSlide(S) {
    var a = S.intro ? smooth(S.u / 0.6) : 1, f = S.intro ? smooth(S.u / INTRO.slide) : 1;
    ctx.lineJoin = 'round'; ctx.lineCap = 'round';
    ctx.strokeStyle = alpha(colors.ink, 0.8 * a); ctx.lineWidth = 1.4;
    poly(geo.slide, 1, true);
    ctx.strokeStyle = alpha(colors.ink, 0.75 * a); ctx.lineWidth = 1.1;
    geo.outline.forEach(function (l) { poly(l, f); });
    ctx.strokeStyle = alpha(colors.ink, 0.4 * a); ctx.lineWidth = 0.8;
    geo.granular.forEach(function (l) { poly(l, f); });
    // stippled nuclei, appearing in a wave from left to right; Purkinje somata as small rings
    var x0 = geo.slide[3][0], x1 = geo.slide[1][0];
    ctx.fillStyle = alpha(colors.ink, 0.55 * a);
    var r = Math.max(0.6, 0.0025 * W);
    for (var i = 0; i < geo.dots.length; i++) {
      var p = geo.dots[i];
      if (f < 1 && (p[0] - x0) / (x1 - x0) > f * 1.15 - 0.05) continue;
      ctx.fillRect(p[0] - r / 2, p[1] - r / 2, r, r);
    }
    ctx.strokeStyle = alpha(colors.ink, 0.55 * a); ctx.lineWidth = 0.8;
    geo.somata.forEach(function (p) {
      if (f < 1 && (p[0] - x0) / (x1 - x0) > f * 1.15 - 0.05) return;
      ctx.beginPath(); ctx.ellipse(p[0], p[1], geo.somaR, geo.somaR * FLAT, 0, 0, 2 * Math.PI); ctx.stroke();
    });
  }

  // the lifted cell on the slide: where it is (moving from the last one), as a ring in the slide's plane
  function pickAt(S) {
    var a = geo.picks[S.cell], b = S.prev >= 0 ? geo.picks[S.prev] : a, m = S.move;
    return geo.P(lerp(b[0], a[0], m), lerp(b[1], a[1], m));
  }

  // outer tangents of two circles (c1, r1) below and (c2, r2) above: [p1, p2] on each side
  function tangents(c1, r1, c2, r2) {
    var dx = c2[0] - c1[0], dy = c2[1] - c1[1], L = Math.hypot(dx, dy), vx = dx / L, vy = dy / L;
    var c = (r1 - r2) / L, s = Math.sqrt(Math.max(0, 1 - c * c)), out = [];
    [1, -1].forEach(function (sg) {
      var nx = vx * c - sg * vy * s, ny = vy * c + sg * vx * s;
      out.push([[c1[0] + r1 * nx, c1[1] + r1 * ny * FLAT], [c2[0] + r2 * nx, c2[1] + r2 * ny]]);
    });
    return out;
  }

  function drawCone(S, p) {
    var N = geo.nucleus, rc = 0.028 * W;
    var grow = S.intro ? smooth((S.u - INTRO.cone) / 0.8) : 1;
    var show = S.intro ? smooth((S.u - INTRO.mark) / 0.4) : 1;
    if (show <= 0) return;
    // a pulse on the slide, then the ring
    var ph = ((S.t * 0.6) % 1);
    ctx.strokeStyle = alpha(colors.ink, 0.45 * (1 - ph) * show); ctx.lineWidth = 1;
    ctx.beginPath(); ctx.ellipse(p[0], p[1], rc * (1 + 1.6 * ph), rc * (1 + 1.6 * ph) * FLAT, 0, 0, 2 * Math.PI); ctx.stroke();
    ctx.strokeStyle = alpha(colors.ink, 0.95 * show); ctx.lineWidth = 1.8;
    ctx.beginPath(); ctx.ellipse(p[0], p[1], rc, rc * FLAT, 0, 0, 2 * Math.PI); ctx.stroke();
    if (grow <= 0) return;
    var tg = tangents(p, rc, [N.x, N.y], N.r);
    // a faint beam between the two lines, up to the envelope
    if (tg[0][1][0] > tg[1][1][0]) tg.reverse();                 // left line first
    var L = tg[0], R = tg[1];
    ctx.fillStyle = alpha(colors.ink, 0.035 * grow);
    ctx.beginPath(); ctx.moveTo(L[0][0], L[0][1]);
    ctx.lineTo(lerp(L[0][0], L[1][0], grow), lerp(L[0][1], L[1][1], grow));
    if (grow >= 1) ctx.arc(N.x, N.y, N.r, Math.atan2(L[1][1] - N.y, L[1][0] - N.x), Math.atan2(R[1][1] - N.y, R[1][0] - N.x), true);
    else ctx.lineTo(lerp(R[0][0], R[1][0], grow), lerp(R[0][1], R[1][1], grow));
    ctx.lineTo(R[0][0], R[0][1]); ctx.closePath(); ctx.fill();
    ctx.strokeStyle = alpha(colors.ink, 0.9); ctx.lineWidth = 1.6;
    tg.forEach(function (l) {
      ctx.beginPath(); ctx.moveTo(l[0][0], l[0][1]);
      ctx.lineTo(lerp(l[0][0], l[1][0], grow), lerp(l[0][1], l[1][1], grow)); ctx.stroke();
    });
  }

  function drawNucleus(S) {
    var N = geo.nucleus;
    var ring = S.intro ? smooth((S.u - INTRO.ring) / 0.7) : 1;
    if (ring <= 0) return;
    // the envelope, drawn from the bottom both ways
    ctx.strokeStyle = alpha(colors.ink, 0.95); ctx.lineWidth = 2;
    ctx.beginPath(); ctx.arc(N.x, N.y, N.r, Math.PI / 2 - Math.PI * ring, Math.PI / 2 + Math.PI * ring); ctx.stroke();
    ctx.save();
    ctx.beginPath(); ctx.arc(N.x, N.y, N.r - 2, 0, 2 * Math.PI); ctx.clip();
    if (S.intro) chromatin(cells[0], smooth((S.u - INTRO.chrom) / DRAW), 1, S.t);
    else {
      var out = 1 - smooth(S.u / 0.6);
      if (out > 0) chromatin(cells[S.prev], 1, out, S.t);
      chromatin(cells[S.cell], smooth((S.u - 0.35) / DRAW), 1, S.t);
    }
    ctx.restore();
    label(S, ring);
  }

  // one cell's chromosome copies as smooth lines (quadratic through the midpoints), the far half fainter
  function chromatin(c, frac, a, t) {
    if (frac <= 0 || a <= 0) return;
    var N = geo.nucleus, k = 0.92 * N.r;
    var spin = reduced ? 0.9 : t * 0.22, cs = Math.cos(spin), sn = Math.sin(spin);
    var tilt = 0.3, ct = Math.cos(tilt), st = Math.sin(tilt);
    var far = new Path2D(), near = new Path2D(), hf = [new Path2D(), new Path2D(), new Path2D()], hn = [new Path2D(), new Path2D(), new Path2D()];
    c.copies.forEach(function (cp) {
      var m = Math.min(cp.n, Math.ceil(cp.n * frac));
      if (m < 3) return;
      var X = new Float32Array(m), Y = new Float32Array(m), D = new Float32Array(m);
      for (var i = 0; i < m; i++) {
        var x = cs * cp.x[i] + sn * cp.z[i], z = -sn * cp.x[i] + cs * cp.z[i];
        var y = ct * cp.y[i] - st * z;
        D[i] = st * cp.y[i] + ct * z; X[i] = N.x + x * k; Y[i] = N.y + y * k;
      }
      var mx0 = X[0], my0 = Y[0];
      for (var j = 1; j < m - 1; j++) {
        var mx = (X[j] + X[j + 1]) / 2, my = (Y[j] + Y[j + 1]) / 2;
        var path = cp.hl >= 0 ? (D[j] >= 0 ? hn[cp.hl] : hf[cp.hl]) : (D[j] >= 0 ? near : far);
        path.moveTo(mx0, my0); path.quadraticCurveTo(X[j], Y[j], mx, my);
        mx0 = mx; my0 = my;
      }
    });
    ctx.lineJoin = 'round'; ctx.lineCap = 'round';
    ctx.lineWidth = 0.7;
    ctx.strokeStyle = alpha(colors.ink, 0.07 * a); ctx.stroke(far);
    ctx.strokeStyle = alpha(colors.ink, 0.17 * a); ctx.stroke(near);
    for (var h = 0; h < 3; h++) {
      ctx.lineWidth = 1.8; ctx.strokeStyle = alpha(colors.hl[h], 0.5 * a); ctx.stroke(hf[h]);
      ctx.lineWidth = 2.6; ctx.strokeStyle = alpha(colors.hl[h], 0.95 * a); ctx.stroke(hn[h]);
    }
  }

  function label(S, a) {
    var N = geo.nucleus, x = N.x + N.r * 0.8, y = N.y - N.r * 0.86;
    var name = function (i, o) {
      if (o <= 0 || i < 0) return;
      ctx.fillStyle = alpha(colors.ink, 0.9 * o); ctx.font = 'italic 400 ' + Math.round(0.034 * W) + 'px Newsreader, Georgia, serif';
      ctx.fillText(cells[i].type, x, y);
    };
    ctx.textAlign = 'left';
    if (S.intro) name(0, smooth((S.u - INTRO.chrom) / 0.8));
    else { name(S.prev, 1 - smooth(S.u / 0.5)); name(S.cell, smooth((S.u - 0.45) / 0.6)); }
    ctx.fillStyle = alpha(colors.muted, a); ctx.font = Math.round(0.022 * W) + 'px Inter, system-ui, sans-serif';
    ctx.fillText('3-D genome of one cell', x, y + 0.03 * W);
    var sl = geo.slide[3];
    ctx.fillText('tissue section', sl[0], sl[1] + 0.045 * W);
  }

  function frame(t) {
    var S = state(t);
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, W, W);
    drawSlide(S);
    drawCone(S, pickAt(S));
    drawNucleus(S);
  }

  // ---- loop -----------------------------------------------------------------------------------------------------
  function resize() {
    var w = canvas.parentElement.clientWidth;
    if (!w) return;
    W = w; dpr = Math.min(2, window.devicePixelRatio || 1);
    canvas.width = Math.round(W * dpr); canvas.height = Math.round(W * dpr);
    canvas.style.width = W + 'px'; canvas.style.height = W + 'px';
    if (data) layout();
  }
  function tick(ts) {
    if (!running) return;
    if (startT === null) startT = ts;
    frame((ts - startT) / 1000);
    requestAnimationFrame(tick);
  }
  function play() { if (!running && visible && data && !reduced) { running = true; requestAnimationFrame(tick); } }
  function pause() { running = false; }
  var STILL = INTRO.end - 0.5;

  fetch('hero.json').then(function (r) { if (!r.ok) throw new Error(r.status); return r.json(); }).then(function (d) {
    data = d; build(d); readColors(); resize();
    var fixed = /[?&]hero=([0-9.]+)/.exec(location.search);       // ?hero=12.5: that moment, still (review)
    if (fixed) { reduced = true; frame(parseFloat(fixed[1])); window.heroFrame = function (t) { readColors(); frame(t); }; return; }
    if (reduced) frame(STILL); else play();
    if (window.IntersectionObserver) {
      var hidden = null;
      new IntersectionObserver(function (es) {                   // off screen: stop the clock, resume where it was
        visible = es[0].isIntersecting;
        if (visible) { if (hidden !== null && startT !== null) startT += performance.now() - hidden; hidden = null; play(); }
        else { hidden = performance.now(); pause(); }
      }).observe(canvas);
    }
    window.addEventListener('resize', function () { resize(); if (reduced) frame(STILL); });
    if (window.matchMedia) {
      window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', function () { readColors(); });
    }
    document.dispatchEvent(new CustomEvent('hero-ready', { detail: d }));
  }).catch(function () { canvas.parentElement.classList.add('hero-failed'); });
})();
