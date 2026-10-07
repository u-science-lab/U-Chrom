//! The Mustache scale-space scan: `uchrom.strc.loop.mustache._scan`, bit for bit.
//!
//! Per row tile of the normalised band (the reference's tiles: `tile` rows, a halo of `halo` rows /
//! columns), the image (z-scores in the band `min_diag < j - i <= D`, 0 for absent pixels, `fill`
//! elsewhere) is smoothed with every Gaussian of every octave ([`crate::gauss`], scipy's arithmetic),
//! differenced (`L_k = G_k - G_{k+1}`), and at every eligible pixel the 3 x 3 maximum (zero outside the
//! tile image) and the reference's update rule give the best response and its layer; the per-layer
//! `|L|` sums (numpy's pairwise summation, per tile, added in tile order), counts and minima feed the
//! exponential fits.
//!
//! Only what the eligible pixels need is computed: the Gaussians on the rows `r0 - 1 .. r1 + 1` and, per
//! row, on the columns of the band `min_diag - 2 ..= D + 2` from the diagonal (the reference filters
//! the whole tile image; values elsewhere are never read).  The values computed are the same numbers, so
//! results equal the reference's exactly.  Tiles run in parallel (rayon).

use crate::gauss::{axis0, axis1_row, Arith};
use crate::pairwise::np_sum;
use rayon::prelude::*;

/// Inputs of [`scan`].
pub struct Input<'a> {
    /// all pixels, sorted by (x, y): row bin, column bin, normalised value
    pub x: &'a [i64],
    pub y: &'a [i64],
    pub z: &'a [f64],
    /// the eligible pixels (sorted by (x, y))
    pub ex: &'a [i64],
    pub ey: &'a [i64],
    /// bins of the chromosome
    pub n: usize,
    pub max_diag: usize,
    pub min_diag: i64,
    /// image value outside the band
    pub fill: f64,
    /// per octave: the correlation weights of its `scales + 2` Gaussians (scipy's, odd lengths)
    pub weights: &'a [Vec<Vec<f64>>],
    /// rows of the halo (the largest radius + 2)
    pub halo: usize,
    /// rows per tile
    pub tile: usize,
    /// scipy's accumulation scheme (fused multiply-adds or not)
    pub arith: Arith,
}

/// Result of [`scan`].
#[derive(Debug, Clone, Default)]
pub struct Output {
    pub best: Vec<f64>,
    pub layer: Vec<i16>,
    pub st_sum: Vec<f64>,
    pub st_cnt: Vec<i64>,
    pub st_min: Vec<f64>,
}

struct TileOut {
    e0: usize,
    best: Vec<f64>,
    layer: Vec<i16>,
    sum: Vec<f64>,
    cnt: Vec<i64>,
    min: Vec<f64>,
}

#[derive(Default)]
struct Bufs {
    img: Vec<f64>,
    tmp: Vec<f64>,
    ga: Vec<f64>,
    gb: Vec<f64>,
    ext: Vec<f64>,
    lp: [Vec<f64>; 3],
    mp: [Vec<f64>; 3],
    abs: Vec<f64>,
}

/// One Gaussian of the tile into `g` (rows `rows`, per-row output columns `win(row)`).
#[allow(clippy::too_many_arguments)]
fn smooth(
    arith: Arith,
    img: &[f64],
    h: usize,
    w: usize,
    k: &[f64],
    rows: (usize, usize),
    win: &dyn Fn(usize) -> (usize, usize),
    tmp: &mut [f64],
    ext: &mut Vec<f64>,
    g: &mut [f64],
) {
    let s = (k.len() - 1) / 2;
    let np = arith.n_plain(s);
    axis0(img, h, w, k, np, rows, |r| {
        let (lo, hi) = win(r);
        if lo >= hi {
            (0, 0)
        } else {
            (lo.saturating_sub(s), (hi + s).min(w))
        }
    }, tmp);
    for r in rows.0..rows.1 {
        let (lo, hi) = win(r);
        if lo >= hi {
            continue;
        }
        let off = (r - rows.0) * w;
        axis1_row(&tmp[off..off + w], k, np, lo, hi, ext, &mut g[off + lo..off + hi]);
    }
}

fn scan_tile(inp: &Input, row_ptr: &[usize], r0: usize, r1: usize, e0: usize, e1: usize, b: &mut Bufs) -> TileOut {
    let n = inp.n;
    let dmax = inp.max_diag;
    let a0 = r0.saturating_sub(inp.halo);
    let a1 = (r1 + inp.halo).min(n);
    let b0 = a0;
    let b1 = (r1 + dmax + 1 + inp.halo).min(n);
    let (h, w) = (a1 - a0, b1 - b0);
    // the image
    b.img.clear();
    b.img.resize(h * w, inp.fill);
    for yy in 0..h {
        // 0 where min_diag < (x - y) <= D (local x - y = global j - i since b0 = a0)
        let lo = (yy as i64 + inp.min_diag + 1).max(0) as usize;
        let hi = (yy + dmax + 1).min(w);
        if lo < hi {
            b.img[yy * w + lo..yy * w + hi].fill(0.0);
        }
    }
    for q in row_ptr[a0]..row_ptr[a1] {
        let (px, py) = (inp.x[q], inp.y[q]);
        if py - px > inp.min_diag {
            b.img[(px as usize - a0) * w + (py as usize - b0)] = inp.z[q];
        }
    }
    // rows / columns where L is needed: the eligible pixels and their 3 x 3 neighbourhoods
    let rows = ((r0.saturating_sub(1)).max(a0) - a0, (r1 + 1).min(a1) - a0);
    let md = inp.min_diag;
    let win = move |r: usize| -> (usize, usize) {
        let lo = (r as i64 + md - 2).max(0) as usize;
        let hi = (r + dmax + 3).min(w);
        (lo.min(hi), hi)
    };
    let nr = rows.1 - rows.0;
    // tmp: a zero row above and below the rows (the 3 x 3 maximum's padding outside the image)
    b.tmp.resize((nr + 2) * w, 0.0);
    b.tmp[..w].fill(0.0);
    b.tmp[(nr + 1) * w..(nr + 2) * w].fill(0.0);
    b.ga.resize(nr * w, 0.0);
    b.gb.resize(nr * w, 0.0);
    let m = e1 - e0;
    // local positions of the eligible pixels (row within `rows`, column)
    // flat offsets of the eligible pixels in the row buffers (row within `rows`, column)
    let pos: Vec<usize> = (e0..e1).map(|e| (inp.ex[e] as usize - a0 - rows.0) * w + (inp.ey[e] as usize - b0)).collect();
    let n_oct = inp.weights.len();
    let s_sc = inp.weights[0].len() - 2; // scales
    let kk = n_oct * (s_sc - 1);
    let mut out = TileOut {
        e0,
        best: vec![0.0; m],
        layer: vec![-1; m],
        sum: vec![0.0; kk],
        cnt: vec![0; kk],
        min: vec![f64::INFINITY; kk],
    };
    for v in b.lp.iter_mut().chain(b.mp.iter_mut()) {
        v.resize(m, 0.0);
    }
    for (q, ws) in inp.weights.iter().enumerate() {
        let Bufs { img, tmp, ga, gb, ext, lp, mp, abs } = b;
        smooth(inp.arith, img, h, w, &ws[0], rows, &win, &mut tmp[w..], ext, ga);
        for k in 0..=s_sc {
            // L_k = G_k - G_{k+1}
            smooth(inp.arith, img, h, w, &ws[k + 1], rows, &win, &mut tmp[w..], ext, gb);
            let slot = k % 3;
            // L_k into ga (G_k is not needed any more) and its maximum over columns c - 1 ..= c + 1 into
            // tmp (free until the next Gaussian): 0 outside the image as the reference's zero padding,
            // -inf outside the window (never read: an eligible pixel's neighbours lie in the window)
            for r in rows.0..rows.1 {
                let (lo, hi) = win(r);
                if lo >= hi {
                    continue;
                }
                let off = (r - rows.0) * w;
                for (a, &bv) in ga[off + lo..off + hi].iter_mut().zip(&gb[off + lo..off + hi]) {
                    *a -= bv;
                }
                let l = &ga[off..off + w];
                let t = &mut tmp[w + off..w + off + w];
                let get = |c: isize| -> f64 {
                    if c < 0 || c >= w as isize {
                        0.0
                    } else if (c as usize) < lo || (c as usize) >= hi {
                        f64::NEG_INFINITY
                    } else {
                        l[c as usize]
                    }
                };
                if hi - lo >= 3 {
                    for (c, tc) in t[lo + 1..hi - 1].iter_mut().enumerate() {
                        let c = c + lo + 1;
                        *tc = l[c - 1].max(l[c]).max(l[c + 1]);
                    }
                }
                for c in [lo, hi - 1] {
                    let ci = c as isize;
                    t[c] = get(ci - 1).max(get(ci)).max(get(ci + 1));
                }
            }
            {
                let (lpk, mpk) = (&mut lp[slot], &mut mp[slot]);
                // rows above / below an eligible pixel are in `rows` or outside the image (the zero rows)
                for ((&o, l), mxo) in pos.iter().zip(lpk.iter_mut()).zip(mpk.iter_mut()) {
                    *l = ga[o];
                    *mxo = tmp[o].max(tmp[o + w]).max(tmp[o + 2 * w]);
                }
            }
            std::mem::swap(ga, gb);
            // the update of layer k - 1 needs L_{k-2}, L_{k-1}, L_k
            if k >= 2 {
                let kc = k - 1;
                let (sp, sc, sn) = ((kc - 1) % 3, kc % 3, k % 3);
                let j = q * (s_sc - 1) + (kc - 1);
                abs.clear();
                abs.extend(lp[sc].iter().map(|v| v.abs()));
                out.sum[j] = np_sum(abs);
                out.cnt[j] = m as i64;
                out.min[j] = abs.iter().cloned().fold(f64::INFINITY, f64::min);
                let (lpp, lpc, lpn) = (&lp[sp][..m], &lp[sc][..m], &lp[sn][..m]);
                let (mpp, mpc, mpn) = (&mp[sp][..m], &mp[sc][..m], &mp[sn][..m]);
                let (best, layer) = (&mut out.best[..m], &mut out.layer[..m]);
                let jj = j as i16;
                for e in 0..m {
                    let lc = lpc[e];
                    let upd = (lc > best[e])
                        & (lc == mpc[e])
                        & ((lpp[e] == mpp[e]) | (lpn[e] == mpn[e]))
                        & (lc > mpp[e])
                        & (lc > mpn[e]);
                    best[e] = if upd { lc } else { best[e] };
                    layer[e] = if upd { jj } else { layer[e] };
                }
            }
        }
    }
    out
}

/// The scan of one chromosome (see the module docs).
pub fn scan(inp: &Input) -> Result<Output, String> {
    let n = inp.n;
    if inp.x.len() != inp.y.len() || inp.x.len() != inp.z.len() || inp.ex.len() != inp.ey.len() {
        return Err("x, y, z (and ex, ey) must have the same length".into());
    }
    if inp.weights.is_empty() || inp.weights.iter().any(|o| o.len() < 4 || o.len() != inp.weights[0].len()) {
        return Err("weights: per octave the same number (>= 4) of kernels".into());
    }
    if inp.weights.iter().flatten().any(|k| k.len() % 2 == 0) {
        return Err("weights: odd kernel lengths".into());
    }
    let s_sc = inp.weights[0].len() - 2;
    if inp.weights.len() * (s_sc - 1) > i16::MAX as usize {
        return Err("too many layers".into());
    }
    let sorted = |a: &[i64], b: &[i64]| a.windows(2).zip(b.windows(2)).all(|(u, v)| (u[0], v[0]) <= (u[1], v[1]));
    if !sorted(inp.x, inp.y) || !sorted(inp.ex, inp.ey) {
        return Err("pixels must be sorted by (x, y)".into());
    }
    let in_band = |x: &[i64], y: &[i64]| x.iter().zip(y).all(|(&i, &j)| i >= 0 && j >= i && j < n as i64 && j - i <= inp.max_diag as i64);
    if !in_band(inp.x, inp.y) || !in_band(inp.ex, inp.ey) {
        return Err("pixels must have 0 <= x <= y < n and y - x <= max_diag".into());
    }
    let ptr = |x: &[i64]| -> Vec<usize> {
        let mut p = vec![0usize; n + 1];
        for &i in x {
            p[i as usize + 1] += 1;
        }
        for k in 0..n {
            p[k + 1] += p[k];
        }
        p
    };
    let row_ptr = ptr(inp.x);
    let el_ptr = ptr(inp.ex);
    let t = inp.tile.max(1);
    let tiles: Vec<(usize, usize, usize, usize)> = (0..n)
        .step_by(t)
        .map(|r0| {
            let r1 = (r0 + t).min(n);
            (r0, r1, el_ptr[r0], el_ptr[r1])
        })
        .filter(|&(_, _, e0, e1)| e0 < e1)
        .collect();
    let parts: Vec<TileOut> = tiles
        .par_iter()
        .map_init(Bufs::default, |b, &(r0, r1, e0, e1)| scan_tile(inp, &row_ptr, r0, r1, e0, e1, b))
        .collect();
    let kk = inp.weights.len() * (s_sc - 1);
    let m = inp.ex.len();
    let mut out = Output {
        best: vec![0.0; m],
        layer: vec![-1; m],
        st_sum: vec![0.0; kk],
        st_cnt: vec![0; kk],
        st_min: vec![f64::INFINITY; kk],
    };
    for p in parts {
        let e1 = p.e0 + p.best.len();
        out.best[p.e0..e1].copy_from_slice(&p.best);
        out.layer[p.e0..e1].copy_from_slice(&p.layer);
        for j in 0..kk {
            out.st_sum[j] += p.sum[j];
            out.st_cnt[j] += p.cnt[j];
            out.st_min[j] = out.st_min[j].min(p.min[j]);
        }
    }
    Ok(out)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::gauss::{gaussian_filter, gaussian_weights};

    fn lcg(seed: &mut u64) -> f64 {
        *seed = seed.wrapping_mul(6364136223846793005).wrapping_add(1442695040888963407);
        ((*seed >> 11) as f64) / ((1u64 << 53) as f64)
    }

    struct Toy {
        n: usize,
        x: Vec<i64>,
        y: Vec<i64>,
        z: Vec<f64>,
        ex: Vec<i64>,
        ey: Vec<i64>,
    }

    /// Noise plus Gaussian blobs (loops) of several widths; 15 % of the pixels absent.
    fn toy(n: usize, dmax: usize, min_diag: i64, seed: u64) -> Toy {
        let mut s = seed;
        let mut blobs = vec![];
        for b in 0..(n / 6) {
            let i = lcg(&mut s) * n as f64;
            let d = min_diag as f64 + 2.0 + lcg(&mut s) * (dmax as f64 - min_diag as f64 - 2.0);
            blobs.push((i, i + d, 1.0 + (b % 3) as f64 * 0.8, 3.0 + 3.0 * lcg(&mut s)));
        }
        let (mut x, mut y, mut z) = (vec![], vec![], vec![]);
        for i in 0..n {
            for j in i..(i + dmax + 1).min(n) {
                if lcg(&mut s) < 0.85 {
                    let mut v = (lcg(&mut s) - 0.5) * 0.6;
                    for &(bi, bj, sd, amp) in &blobs {
                        let r2 = (i as f64 - bi).powi(2) + (j as f64 - bj).powi(2);
                        v += amp * (-r2 / (2.0 * sd * sd)).exp();
                    }
                    x.push(i as i64);
                    y.push(j as i64);
                    z.push(v);
                }
            }
        }
        let el: Vec<usize> = (0..x.len()).filter(|&q| z[q] != 0.0 && y[q] - x[q] >= min_diag).collect();
        let ex = el.iter().map(|&q| x[q]).collect();
        let ey = el.iter().map(|&q| y[q]).collect();
        Toy { n, x, y, z, ex, ey }
    }

    fn weights(sig0: f64, octaves: usize, scales: usize) -> (Vec<Vec<Vec<f64>>>, usize) {
        let mut out = vec![];
        let mut rmax = 0;
        for q in 0..octaves {
            let o = sig0 * 2f64.powi(q as i32);
            let mut ks = vec![];
            for k in 1..=scales + 2 {
                let sg = o * 2f64.powf((k as f64 - 1.0) / scales as f64);
                let r = (2.0 * sg).ceil() as usize;
                rmax = rmax.max(r);
                ks.push(gaussian_weights(sg, r));
            }
            out.push(ks);
        }
        (out, rmax + 2)
    }

    /// The reference's algorithm on the whole chromosome image (one tile, full images).
    fn reference(t: &Toy, dmax: usize, min_diag: i64, fill: f64, ws: &[Vec<Vec<f64>>], arith: Arith) -> Output {
        let n = t.n;
        let mut img = vec![fill; n * n];
        for i in 0..n {
            for j in 0..n {
                let d = j as i64 - i as i64;
                if d > min_diag && d <= dmax as i64 {
                    img[i * n + j] = 0.0;
                }
            }
        }
        for q in 0..t.x.len() {
            if t.y[q] - t.x[q] > min_diag {
                img[t.x[q] as usize * n + t.y[q] as usize] = t.z[q];
            }
        }
        let s = ws[0].len() - 2;
        let m = t.ex.len();
        let mut out = Output {
            best: vec![0.0; m],
            layer: vec![-1; m],
            st_sum: vec![0.0; ws.len() * (s - 1)],
            st_cnt: vec![0; ws.len() * (s - 1)],
            st_min: vec![f64::INFINITY; ws.len() * (s - 1)],
        };
        for (q, ks) in ws.iter().enumerate() {
            let g: Vec<Vec<f64>> = ks.iter().map(|k| gaussian_filter(&img, n, n, k, arith)).collect();
            let mut lp = vec![vec![0.0; m]; s + 1];
            let mut mp = vec![vec![0.0; m]; s + 1];
            for k in 0..=s {
                let l: Vec<f64> = g[k].iter().zip(&g[k + 1]).map(|(a, b)| a - b).collect();
                for e in 0..m {
                    let (py, px) = (t.ex[e], t.ey[e]);
                    lp[k][e] = l[py as usize * n + px as usize];
                    let mut mx = f64::NEG_INFINITY;
                    for dy in -1..=1 {
                        for dx in -1..=1 {
                            let (yy, xx) = (py + dy, px + dx);
                            let v = if yy < 0 || xx < 0 || yy >= n as i64 || xx >= n as i64 { 0.0 } else { l[yy as usize * n + xx as usize] };
                            mx = mx.max(v);
                        }
                    }
                    mp[k][e] = mx;
                }
            }
            for k in 1..s {
                let j = q * (s - 1) + k - 1;
                let a: Vec<f64> = lp[k].iter().map(|v| v.abs()).collect();
                out.st_sum[j] += np_sum(&a);
                out.st_cnt[j] += m as i64;
                out.st_min[j] = out.st_min[j].min(a.iter().cloned().fold(f64::INFINITY, f64::min));
                for e in 0..m {
                    let lc = lp[k][e];
                    if lc > out.best[e] && lc == mp[k][e] && (lp[k - 1][e] == mp[k - 1][e] || lp[k + 1][e] == mp[k + 1][e])
                        && lc > mp[k - 1][e] && lc > mp[k + 1][e]
                    {
                        out.best[e] = lc;
                        out.layer[e] = j as i16;
                    }
                }
            }
        }
        out
    }

    #[test]
    fn tiles_equal_the_whole_image() {
        let (n, dmax, md) = (150usize, 30usize, 2i64);
        let t = toy(n, dmax, md, 9);
        let (ws, halo) = weights(1.0, 2, 4);
        for arith in [Arith::PLAIN, Arith::FUSED, Arith { fma: true, block: 8, min_terms: 10 }, Arith { fma: true, block: 2, min_terms: 3 }] {
            let want = reference(&t, dmax, md, 2.0, &ws, arith);
            let n_ext = want.layer.iter().filter(|&&l| l >= 0).count();
            assert!(n_ext >= 8, "{n_ext} extrema");
            // one tile covering everything: identical to the reference, statistics included
            let mk = |tile| Input {
                x: &t.x, y: &t.y, z: &t.z, ex: &t.ex, ey: &t.ey, n, max_diag: dmax, min_diag: md, fill: 2.0,
                weights: &ws, halo, tile, arith,
            };
            let one = scan(&mk(10_000)).unwrap();
            assert_eq!(one.best, want.best);
            assert_eq!(one.layer, want.layer);
            assert_eq!(one.st_sum, want.st_sum);
            assert_eq!(one.st_cnt, want.st_cnt);
            assert_eq!(one.st_min, want.st_min);
            // smaller tiles: the same responses and layers (the sums are grouped per tile)
            for tile in [5usize, 16] {
                let got = scan(&mk(tile)).unwrap();
                assert_eq!(got.best, want.best, "tile {tile}");
                assert_eq!(got.layer, want.layer, "tile {tile}");
                assert_eq!(got.st_cnt, want.st_cnt);
                assert_eq!(got.st_min, want.st_min);
                for (a, b) in got.st_sum.iter().zip(&want.st_sum) {
                    assert!((a - b).abs() <= 1e-12 * b.abs());
                }
            }
        }
    }
}
