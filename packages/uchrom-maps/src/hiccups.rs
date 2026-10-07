//! HiCCUPS scoring of one chromosome: `uchrom.strc.loop.hiccups._score_chrom`, bit for bit.
//!
//! For every testable pixel `(i, j)` of the band `0 < j - i < D` the four locally adjusted expecteds
//! `λ_k = E_raw(i, j) · Σ_{K_k} O_bal / Σ_{K_k} E_bal` (donut, vertical, horizontal, lower-left), their
//! λ-chunk (`edges`), the per-kernel (λ-chunk × count) histograms and the candidates (pixels whose count
//! reaches the chunk's least passable count `cmin` for all four kernels).
//!
//! The numpy reference sums the kernels on summed-area tables (SAT) of dense row tiles; floating-point
//! sums depend on where the tables start, so this port keeps the reference's tiles (`tile_rows`, the same
//! origin `r0 - w`) and builds the same tables in the same order (`cumsum` down the columns, then along
//! the rows), but streams them: only the `2w + 2` table rows a pixel row needs are kept (a ring buffer),
//! instead of the reference's ~13 dense tile-sized arrays.  The footprint test ("no masked bin, ignored
//! diagonal or position beyond the chromosome in the union of the kernels") is exact integer logic and
//! is done per bin and per separation (it factorises: every row, column and separation of the window is
//! touched by the union of the footprints).  Tiles run in parallel (rayon); histograms are merged and
//! candidates concatenated in tile order, so the output is the reference's, in its order.

use rayon::prelude::*;

/// The four kernels, in the reference's order.
pub const KERNELS: [&str; 4] = ["donut", "vertical", "horizontal", "lowleft"];

/// A rectangle of neighbour offsets `(dy0, dy1, dx0, dx1, sign)`.
pub type Rect5 = (i64, i64, i64, i64, i64);

/// Footprint of every kernel as signed rectangles `(dy0, dy1, dx0, dx1, sign)` of neighbour offsets
/// (inclusive) — `uchrom.strc.loop.hiccups.kernel_rects`, same rectangles in the same order.
pub fn kernel_rects(p: i64, w: i64) -> [Vec<Rect5>; 4] {
    [
        vec![
            (-w, w, -w, w, 1),
            (-p, p, -p, p, -1),
            (-w, -p - 1, 0, 0, -1),
            (p + 1, w, 0, 0, -1),
            (0, 0, -w, -p - 1, -1),
            (0, 0, p + 1, w, -1),
        ],
        vec![(-w, -p - 1, -1, 1, 1), (p + 1, w, -1, 1, 1)],
        vec![(-1, 1, -w, -p - 1, 1), (-1, 1, p + 1, w, 1)],
        vec![(1, w, -w, -1, 1), (1, p, -p, -1, -1)],
    ]
}

/// Inputs of [`score_chrom`].
pub struct Input<'a> {
    /// bins of the chromosome
    pub n: usize,
    /// band pixels sorted by row: row bin, column bin (`j >= i`), raw count
    pub bi: &'a [i64],
    pub bj: &'a [i64],
    pub count: &'a [f64],
    /// balancing weights (NaN: masked bin), `n` values
    pub weight: &'a [f64],
    /// expected balanced contact per separation (NaN: undefined / ignored diagonal)
    pub expected: &'a [f64],
    pub p: usize,
    pub w: usize,
    /// separations `0 < j - i < max_diag` are tested
    pub max_diag: usize,
    /// rows per tile (the reference's `T`)
    pub tile_rows: usize,
    /// upper edges of the λ-chunks
    pub edges: &'a [f64],
    /// least count of a candidate, per λ-chunk
    pub cmin: &'a [i64],
}

/// Result of [`score_chrom`].
#[derive(Default, Debug, Clone)]
pub struct Output {
    /// per kernel: histogram rows (λ-chunk) × columns (count), row-major, and its shape
    pub hist: [Vec<i64>; 4],
    pub hist_shape: [(usize, usize); 4],
    /// candidates in the reference's order (tile by tile, row-major)
    pub i: Vec<i64>,
    pub j: Vec<i64>,
    pub cnt: Vec<i64>,
    pub lam: [Vec<f64>; 4],
    pub n_tested: u64,
}

#[derive(Clone, Copy)]
struct Rect {
    top: usize,  // table row offset of the rectangle's top edge, from the pixel row - w
    bot: usize,  // ... of its bottom edge (exclusive)
    left: usize, // table column offset of its left edge, from the pixel column - w
    right: usize,
    neg: bool,
}

fn rects_of(p: usize, w: usize) -> [Vec<Rect>; 4] {
    let wi = w as i64;
    kernel_rects(p as i64, wi).map(|v| {
        v.into_iter()
            .map(|(dy0, dy1, dx0, dx1, s)| Rect {
                top: (dy0 + wi) as usize,
                bot: (dy1 + 1 + wi) as usize,
                left: (dx0 + wi) as usize,
                right: (dx1 + 1 + wi) as usize,
                neg: s < 0,
            })
            .collect()
    })
}

#[derive(Default)]
struct TileOut {
    hist: [Vec<Vec<i64>>; 4],
    i: Vec<i64>,
    j: Vec<i64>,
    cnt: Vec<i64>,
    lam: [Vec<f64>; 4],
    n_tested: u64,
    /// a λ beyond the chunks (the reference raises): kernel, value
    overflow: Option<(usize, f64)>,
}

/// Kernel sums of the pixels at table column offsets `x0 .. x0 + out.len()` (table column offset = pixel
/// column - w), from the table rows `rows` of the kernel's rectangles; per pixel the operations of the
/// reference's `_kernel_sum_at`, in its order.
#[inline(always)]
fn ksum_range(ring: &[f64], rows: &[(usize, usize)], rects: &[Rect], x0: usize, out: &mut [f64]) {
    let len = out.len();
    for (q, (rc, &(top, bot))) in rects.iter().zip(rows).enumerate() {
        let br = &ring[bot + x0 + rc.right..][..len];
        let tr = &ring[top + x0 + rc.right..][..len];
        let bl = &ring[bot + x0 + rc.left..][..len];
        let tl = &ring[top + x0 + rc.left..][..len];
        let it = out.iter_mut().zip(br).zip(tr).zip(bl).zip(tl);
        match (q == 0, rc.neg) {
            (true, false) => it.for_each(|((((o, &b), &t), &c), &d)| *o = 0.0 + (((b - t) - c) + d)),
            (true, true) => it.for_each(|((((o, &b), &t), &c), &d)| *o = 0.0 - (((b - t) - c) + d)),
            (false, false) => it.for_each(|((((o, &b), &t), &c), &d)| *o += ((b - t) - c) + d),
            (false, true) => it.for_each(|((((o, &b), &t), &c), &d)| *o -= ((b - t) - c) + d),
        }
    }
}

/// λ-chunk lookup: the first edge `>= l` (`np.searchsorted(edges, l, side="left")`).  A table over the
/// leading bits of `l` (exponent and 6 mantissa bits) gives the first edge at or above the start of
/// `l`'s bucket; exact comparisons step over the edges below `l` inside the bucket (for the λ-chunks, 3
/// edges per binade and 64 buckets: at most one; a predicted branch beats a branch-free step here).
struct Chunks<'a> {
    edges: &'a [f64],
    key0: u64,
    table: Vec<u16>,
}

const CHUNK_SHIFT: u32 = 46;

impl<'a> Chunks<'a> {
    fn new(edges: &'a [f64]) -> Self {
        let key0 = edges[0].to_bits() >> CHUNK_SHIFT;
        let key1 = edges[edges.len() - 1].to_bits() >> CHUNK_SHIFT;
        let size = (key1 - key0 + 1).min(1 << 20) as usize;
        let table: Vec<u16> = (0..size as u64)
            .map(|k| {
                let lo = f64::from_bits((key0 + k) << CHUNK_SHIFT);
                edges.partition_point(|&e| e < lo).min(edges.len() - 1) as u16
            })
            .collect();
        Chunks { edges, key0, table }
    }

    /// `l` must not exceed the last edge (nor be NaN).
    #[inline(always)]
    fn of(&self, l: f64) -> usize {
        let e = self.edges;
        let bits = if l > 0.0 { l.to_bits() } else { 0 };
        let key = ((bits >> CHUNK_SHIFT).saturating_sub(self.key0) as usize).min(self.table.len() - 1);
        let mut g = self.table[key] as usize;
        while e[g] < l {
            g += 1;
        }
        g
    }
}

struct Shared<'a> {
    inp: &'a Input<'a>,
    rects: [Vec<Rect>; 4],
    row_ptr: Vec<usize>,
    /// every row's column bins strictly increase (no duplicate pixels)
    strict_rows: bool,
    /// bins whose window `k - w ..= k + w` lies in the chromosome without a masked bin
    bin_ok: Vec<bool>,
    /// separations whose window `s - 2w ..= s + 2w` has a defined expected everywhere
    sep_ok: Vec<bool>,
    /// expected with NaN as 0 (the reference's `E0` where the column is valid)
    e0: Vec<f64>,
    chunks: Chunks<'a>,
}

fn score_tile(sh: &Shared, r0: usize, r1: usize) -> TileOut {
    let inp = sh.inp;
    let (n, w, dmax) = (inp.n as i64, inp.w as i64, inp.max_diag as i64);
    let (r0i, r1i) = (r0 as i64, r1 as i64);
    let a0 = r0i - w; // first dense row / column (global bin; may be negative)
    let a1 = r1i + w;
    let c0 = a0;
    let c1 = (r1i + dmax + w).min(n + w);
    let hgt = (a1 - a0) as usize;
    let wid = (c1 - c0) as usize;
    let sw = wid + 1; // table row length
    let ring_rows = 2 * inp.w + 2;
    let mut ring_o = vec![0.0f64; ring_rows * sw];
    let mut ring_e = vec![0.0f64; ring_rows * sw];
    let mut col_o = vec![0.0f64; wid];
    let mut col_e = vec![0.0f64; wid];
    let mut row_o = vec![0.0f64; wid];
    let mut raw_row = vec![0.0f64; wid];
    let ne = inp.expected.len() as i64;
    // valid columns of the tile (1.0 / 0.0: the reference's E0 is e * valid)
    let col_ok: Vec<f64> = (0..wid)
        .map(|x| {
            let g = c0 + x as i64;
            (g >= 0 && g < n && !inp.weight[g as usize].is_nan()) as u8 as f64
        })
        .collect();
    let mut out = TileOut::default();
    for h in out.hist.iter_mut() {
        *h = vec![Vec::new(); inp.edges.len()];
    }
    let mut rows_buf: [Vec<(usize, usize)>; 4] = [vec![], vec![], vec![], vec![]];
    let mut ke: [Vec<f64>; 4] = [vec![], vec![], vec![], vec![]];
    let mut ko: [Vec<f64>; 4] = [vec![], vec![], vec![], vec![]];
    let mut e_raw: Vec<f64> = vec![];
    let last_edge = inp.edges[inp.edges.len() - 2];

    // table row 0 is zero (ring slot 0 already is); rows 1..=hgt follow the dense rows.  Adding 0 leaves a
    // column sum unchanged (all values are >= +0), so only the valid non-zero cells are added.
    for r in 1..=hgt {
        let y = r - 1; // dense row
        let g = a0 + y as i64; // its bin
        if g >= 0 && g < n && !inp.weight[g as usize].is_nan() {
            let wr = inp.weight[g as usize];
            let (s0, s1) = (sh.row_ptr[g as usize], sh.row_ptr[g as usize + 1]);
            // O = raw * wr * wc on the valid cells
            if sh.strict_rows {
                for q in s0..s1 {
                    let jg = inp.bj[q];
                    if jg >= c1 {
                        continue;
                    }
                    let x = (jg - c0) as usize;
                    let sep = jg - g;
                    if col_ok[x] != 0.0 && sep < ne && !inp.expected[sep as usize].is_nan() {
                        col_o[x] += inp.count[q] * wr * inp.weight[jg as usize];
                    }
                }
            } else {
                // duplicates: the last value of a cell wins, as in the reference's dense assignment
                for q in s0..s1 {
                    let jg = inp.bj[q];
                    if jg < c1 {
                        row_o[(jg - c0) as usize] = inp.count[q];
                    }
                }
                for q in s0..s1 {
                    let jg = inp.bj[q];
                    if jg >= c1 {
                        continue;
                    }
                    let x = (jg - c0) as usize;
                    let v = row_o[x];
                    if v.is_nan() {
                        continue; // this cell was added already
                    }
                    let sep = jg - g;
                    if col_ok[x] != 0.0 && sep < ne && !inp.expected[sep as usize].is_nan() {
                        col_o[x] += v * wr * inp.weight[jg as usize];
                    }
                    row_o[x] = f64::NAN;
                }
                for q in s0..s1 {
                    let jg = inp.bj[q];
                    if jg < c1 {
                        row_o[(jg - c0) as usize] = 0.0;
                    }
                }
            }
            // E0[x] = e[x - y] on the valid cells (separation x - y since c0 = a0)
            let lo = y;
            let hi = (y as i64 + ne).min(wid as i64) as usize;
            if lo < hi {
                let e = &sh.e0[..hi - lo];
                for ((c, &v), &ok) in col_e[lo..hi].iter_mut().zip(e).zip(&col_ok[lo..hi]) {
                    *c += v * ok;
                }
            }
        }
        let slot = (r % ring_rows) * sw;
        {
            let so = &mut ring_o[slot..slot + sw];
            let se = &mut ring_e[slot..slot + sw];
            so[0] = 0.0;
            se[0] = 0.0;
            let (mut ao, mut ae) = (0.0f64, 0.0f64);
            for x in 0..wid {
                ao += col_o[x];
                ae += col_e[x];
                so[x + 1] = ao;
                se[x + 1] = ae;
            }
        }
        // pixel row Y = r - w - 1 (dense row) is complete once table row Y + w + 1 = r exists
        if r < 2 * inp.w + 1 {
            continue;
        }
        let yy = r - inp.w - 1;
        let gi = a0 + yy as i64;
        if gi >= r1i || gi < 0 || gi >= n || !sh.bin_ok[gi as usize] {
            continue;
        }
        let gi_u = gi as usize;
        let j_hi = (gi + dmax - 1).min(n - 1);
        if j_hi <= gi {
            continue;
        }
        let len = (j_hi - gi) as usize; // columns gi + 1 ..= j_hi
        let x0 = (gi + 1 - c0) as usize - inp.w;
        for k in 0..4 {
            rows_buf[k].clear();
            for rc in &sh.rects[k] {
                let top = ((yy - inp.w + rc.top) % ring_rows) * sw;
                let bot = ((yy - inp.w + rc.bot) % ring_rows) * sw;
                rows_buf[k].push((top, bot));
            }
            ke[k].resize(len, 0.0);
            ko[k].resize(len, 0.0);
            ksum_range(&ring_e, &rows_buf[k], &sh.rects[k], x0, &mut ke[k][..len]);
            ksum_range(&ring_o, &rows_buf[k], &sh.rects[k], x0, &mut ko[k][..len]);
        }
        // raw counts of the pixel row (the last value of a cell wins)
        let (s0, s1) = (sh.row_ptr[gi_u], sh.row_ptr[gi_u + 1]);
        for q in s0..s1 {
            let jg = inp.bj[q];
            if jg < c1 {
                raw_row[(jg - c0) as usize] = inp.count[q];
            }
        }
        // E_raw = E / (w_i w_j) and λ_k = E_raw Σ_K O / Σ_K E for the whole row (the reference's
        // operations per pixel; values at untested pixels are not used)
        let wi = inp.weight[gi_u];
        e_raw.resize(len, 0.0);
        {
            let ex = &inp.expected[1..=len];
            let wj = &inp.weight[gi_u + 1..gi_u + 1 + len];
            for ((r, &e), &wv) in e_raw.iter_mut().zip(ex).zip(wj) {
                *r = e / (wi * wv);
            }
        }
        for k in 0..4 {
            // ko[k] becomes λ_k
            for ((o, &kev), &er) in ko[k].iter_mut().zip(&ke[k]).zip(&e_raw) {
                *o = er * *o / kev;
            }
        }
        for t in 0..len {
            let gj = gi + 1 + t as i64;
            let sep = t + 1;
            if !sh.sep_ok[sep] || !sh.bin_ok[gj as usize] {
                continue;
            }
            if !(ke[0][t] > 0.0 && ke[1][t] > 0.0 && ke[2][t] > 0.0 && ke[3][t] > 0.0) {
                continue;
            }
            let c = raw_row[(gj - c0) as usize].round_ties_even() as i64;
            let cu = c.max(0) as usize;
            out.n_tested += 1;
            let mut cand = true;
            let lam = [ko[0][t], ko[1][t], ko[2][t], ko[3][t]];
            for (k, &l) in lam.iter().enumerate() {
                if l.is_nan() || l > last_edge {
                    if out.overflow.is_none() {
                        out.overflow = Some((k, l));
                    }
                    continue;
                }
                let lb = sh.chunks.of(l);
                let hrow = &mut out.hist[k][lb];
                if hrow.len() <= cu {
                    hrow.resize(cu + 1, 0);
                }
                hrow[cu] += 1;
                cand &= c >= inp.cmin[lb];
            }
            if cand {
                out.i.push(gi);
                out.j.push(gj);
                out.cnt.push(c);
                for (dst, &l) in out.lam.iter_mut().zip(&lam) {
                    dst.push(l);
                }
            }
        }
        for q in s0..s1 {
            let jg = inp.bj[q];
            if jg < c1 {
                raw_row[(jg - c0) as usize] = 0.0;
            }
        }
    }
    out
}

/// Score one chromosome (see the module docs).  `Err` when a λ exceeds the last λ-chunk.
pub fn score_chrom(inp: &Input) -> Result<Output, String> {
    let n = inp.n;
    let w = inp.w;
    if inp.p < 1 || inp.p >= w {
        return Err(format!("need 1 <= p < w, got p={}, w={}", inp.p, w));
    }
    if inp.bi.len() != inp.bj.len() || inp.bi.len() != inp.count.len() {
        return Err("bi, bj and count must have the same length".into());
    }
    if inp.weight.len() != n {
        return Err(format!("weight has {} values for {} bins", inp.weight.len(), n));
    }
    if inp.expected.len() < inp.max_diag + 1 {
        return Err(format!("expected has {} values, at least max_diag + 1 = {} are needed", inp.expected.len(), inp.max_diag + 1));
    }
    if inp.edges.len() < 2 || inp.cmin.len() != inp.edges.len() {
        return Err("edges and cmin must have the same length (>= 2)".into());
    }
    if inp.bi.windows(2).any(|v| v[1] < v[0]) {
        return Err("band pixels must be sorted by row".into());
    }
    if inp.bi.iter().zip(inp.bj).any(|(&i, &j)| i < 0 || j < i || j >= n as i64) {
        return Err("band pixels must have 0 <= i <= j < n".into());
    }
    // row pointers
    let mut row_ptr = vec![0usize; n + 1];
    for &i in inp.bi {
        row_ptr[i as usize + 1] += 1;
    }
    for k in 0..n {
        row_ptr[k + 1] += row_ptr[k];
    }
    // per-bin window validity: bins k - w ..= k + w inside [0, n) and unmasked
    let mut bad_pre = vec![0usize; n + 1];
    for k in 0..n {
        bad_pre[k + 1] = bad_pre[k] + inp.weight[k].is_nan() as usize;
    }
    let bin_ok: Vec<bool> = (0..n)
        .map(|k| k >= w && k + w < n && bad_pre[k + w + 1] - bad_pre[k - w] == 0)
        .collect();
    // per-separation window validity: s - 2w ..= s + 2w defined
    let ne = inp.expected.len();
    let mut nan_pre = vec![0usize; ne + 1];
    for s in 0..ne {
        nan_pre[s + 1] = nan_pre[s] + inp.expected[s].is_nan() as usize;
    }
    let sep_ok: Vec<bool> = (0..inp.max_diag.max(1))
        .map(|s| s >= 2 * w && s + 2 * w < ne && nan_pre[s + 2 * w + 1] - nan_pre[s - 2 * w] == 0)
        .collect();
    let e0: Vec<f64> = inp.expected.iter().map(|&v| if v.is_nan() { 0.0 } else { v }).collect();
    if inp.edges.iter().any(|e| e.is_nan()) || inp.edges.windows(2).any(|v| v[0] >= v[1]) || inp.edges[0] <= 0.0 {
        return Err("edges must be positive and increasing".into());
    }
    let strict_rows = (0..n).all(|r| inp.bj[row_ptr[r]..row_ptr[r + 1]].windows(2).all(|v| v[0] < v[1]));
    let sh = Shared {
        inp,
        rects: rects_of(inp.p, w),
        row_ptr,
        strict_rows,
        bin_ok,
        sep_ok,
        e0,
        chunks: Chunks::new(inp.edges),
    };
    let t = inp.tile_rows.max(1);
    let tiles: Vec<(usize, usize)> = (0..n).step_by(t).map(|r0| (r0, (r0 + t).min(n))).collect();
    let parts: Vec<TileOut> = tiles.par_iter().map(|&(r0, r1)| score_tile(&sh, r0, r1)).collect();

    // merge in tile order (the reference raises at the first tile with an overflowing λ)
    if let Some((k, l)) = parts.iter().find_map(|p| p.overflow) {
        return Err(format!("a locally adjusted expected of {l:.3e} ({}) is beyond the λ-chunks", KERNELS[k]));
    }
    let mut out = Output::default();
    let n_cand: usize = parts.iter().map(|p| p.i.len()).sum();
    out.i.reserve_exact(n_cand);
    out.j.reserve_exact(n_cand);
    out.cnt.reserve_exact(n_cand);
    for k in 0..4 {
        out.lam[k].reserve_exact(n_cand);
    }
    for k in 0..4 {
        let rows = parts
            .iter()
            .map(|p| p.hist[k].iter().rposition(|r| !r.is_empty()).map_or(0, |x| x + 1))
            .max()
            .unwrap_or(0);
        let cols = parts.iter().flat_map(|p| p.hist[k].iter().map(|r| r.len())).max().unwrap_or(0);
        let mut h = vec![0i64; rows * cols];
        for p in &parts {
            for (lb, r) in p.hist[k].iter().enumerate().take(rows) {
                for (c, &v) in r.iter().enumerate() {
                    h[lb * cols + c] += v;
                }
            }
        }
        out.hist[k] = h;
        out.hist_shape[k] = (rows, cols);
    }
    for p in parts {
        out.n_tested += p.n_tested;
        out.i.extend_from_slice(&p.i);
        out.j.extend_from_slice(&p.j);
        out.cnt.extend_from_slice(&p.cnt);
        for k in 0..4 {
            out.lam[k].extend_from_slice(&p.lam[k]);
        }
    }
    Ok(out)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn lcg(seed: &mut u64) -> f64 {
        *seed = seed.wrapping_mul(6364136223846793005).wrapping_add(1442695040888963407);
        ((*seed >> 11) as f64) / ((1u64 << 53) as f64)
    }

    struct Toy {
        bi: Vec<i64>,
        bj: Vec<i64>,
        count: Vec<f64>,
        weight: Vec<f64>,
        expected: Vec<f64>,
    }

    /// A random band: counts decaying with separation, some masked bins, an undefined diagonal.
    fn toy(n: usize, dmax: usize, seed: u64) -> Toy {
        let mut s = seed;
        let (mut bi, mut bj, mut count) = (vec![], vec![], vec![]);
        for i in 0..n {
            for j in i..(i + dmax + 1).min(n) {
                let lam = 200.0 / (1.0 + (j - i) as f64);
                let c = (lam * 2.0 * lcg(&mut s)).floor();
                if c > 0.0 {
                    bi.push(i as i64);
                    bj.push(j as i64);
                    count.push(c);
                }
            }
        }
        let mut weight: Vec<f64> = (0..n).map(|_| 0.5 + lcg(&mut s)).collect();
        for m in [5usize, 40, 41] {
            if m < n {
                weight[m] = f64::NAN;
            }
        }
        let mut expected: Vec<f64> = (0..dmax + 1).map(|d| 100.0 / (1.0 + d as f64)).collect();
        expected[0] = f64::NAN;
        expected[1] = f64::NAN;
        if dmax > 30 {
            expected[30] = f64::NAN;
        }
        Toy { bi, bj, count, weight, expected }
    }

    fn edges() -> (Vec<f64>, Vec<i64>) {
        let e: Vec<f64> = (0..160).map(|k| 2f64.powf(k as f64 / 3.0)).collect();
        let c: Vec<i64> = e.iter().map(|&x| (x * 1.2) as i64).collect();
        (e, c)
    }

    #[test]
    fn kernel_sums_match_brute_force_and_tiling_does_not_change_sets() {
        let (n, p, w, dmax) = (90usize, 2usize, 5usize, 40usize);
        let t = toy(n, dmax + 2 * w + 1, 11);
        let (edges, cmin) = edges();
        // dense matrices (upper triangle), the way the reference sees them
        let mut raw = vec![0.0; n * n];
        for q in 0..t.bi.len() {
            raw[t.bi[q] as usize * n + t.bj[q] as usize] = t.count[q];
        }
        let cell = |i: i64, j: i64| -> Option<(f64, f64)> {
            if i < 0 || j < 0 || i >= n as i64 || j >= n as i64 {
                return None;
            }
            let (wi, wj) = (t.weight[i as usize], t.weight[j as usize]);
            let sep = j - i;
            if wi.is_nan() || wj.is_nan() || sep < 0 || sep as usize >= t.expected.len() {
                return None;
            }
            let e = t.expected[sep as usize];
            if e.is_nan() {
                return None;
            }
            Some((raw[i as usize * n + j as usize] * wi * wj, e))
        };
        let rects = kernel_rects(p as i64, w as i64);
        let mut want = std::collections::BTreeMap::new();
        for i in 0..n as i64 {
            for j in (i + 1)..n as i64 {
                if j - i >= dmax as i64 {
                    continue;
                }
                // footprint: the window minus the peak square
                let wi = w as i64;
                let pi = p as i64;
                let clean = (-wi..=wi).all(|dy| {
                    (-wi..=wi).all(|dx| (dy.abs() <= pi && dx.abs() <= pi) || cell(i + dy, j + dx).is_some())
                });
                if !clean {
                    continue;
                }
                let mut lam = [0.0; 4];
                let mut ok = true;
                for k in 0..4 {
                    let (mut so, mut se) = (0.0, 0.0);
                    for &(dy0, dy1, dx0, dx1, s) in &rects[k] {
                        for dy in dy0..=dy1 {
                            for dx in dx0..=dx1 {
                                let (o, e) = cell(i + dy, j + dx).unwrap();
                                so += s as f64 * o;
                                se += s as f64 * e;
                            }
                        }
                    }
                    ok &= se > 0.0;
                    let (_, ec) = cell(i, j).unwrap();
                    lam[k] = ec / (t.weight[i as usize] * t.weight[j as usize]) * so / se;
                }
                if ok {
                    want.insert((i, j), lam);
                }
            }
        }
        assert!(want.len() > 200, "{} testable pixels", want.len());
        let mut base: Option<Output> = None;
        for tile in [7usize, 32, 1000] {
            let inp = Input {
                n,
                bi: &t.bi,
                bj: &t.bj,
                count: &t.count,
                weight: &t.weight,
                expected: &t.expected,
                p,
                w,
                max_diag: dmax,
                tile_rows: tile,
                edges: &edges,
                cmin: &cmin,
            };
            let out = score_chrom(&inp).unwrap();
            assert_eq!(out.n_tested as usize, want.len());
            // candidates are a subset of the tested pixels, with the brute-force λ
            for q in 0..out.i.len() {
                let lam = want[&(out.i[q], out.j[q])];
                for (k, &l) in lam.iter().enumerate() {
                    let rel = (out.lam[k][q] - l).abs() / l.abs().max(1e-300);
                    assert!(rel < 1e-9, "tile {tile} {:?} kernel {k}: {} vs {l}", (out.i[q], out.j[q]), out.lam[k][q]);
                }
            }
            // histogram totals = tested pixels
            for k in 0..4 {
                assert_eq!(out.hist[k].iter().sum::<i64>() as u64, out.n_tested);
            }
            // the candidate filter: count >= cmin[chunk] for all kernels
            let mut n_cand = 0;
            for (&(i, j), lam) in &want {
                let c = raw[i as usize * n + j as usize] as i64;
                if (0..4).all(|k| c >= cmin[edges.partition_point(|&e| e < lam[k])]) {
                    n_cand += 1;
                }
            }
            assert_eq!(out.i.len(), n_cand);
            if let Some(b) = &base {
                assert_eq!(b.i, out.i);
                assert_eq!(b.j, out.j);
                assert_eq!(b.hist, out.hist);
            } else {
                base = Some(out);
            }
        }
    }

    #[test]
    fn overflowing_lambda_is_an_error() {
        let (n, dmax) = (60usize, 30usize);
        let t = toy(n, dmax + 12, 5);
        let edges: Vec<f64> = (1..4).map(|k| k as f64 * 1e-6).collect();
        let cmin = vec![0i64; 3];
        let inp = Input {
            n,
            bi: &t.bi,
            bj: &t.bj,
            count: &t.count,
            weight: &t.weight,
            expected: &t.expected,
            p: 1,
            w: 3,
            max_diag: dmax,
            tile_rows: 16,
            edges: &edges,
            cmin: &cmin,
        };
        let err = score_chrom(&inp).unwrap_err();
        assert!(err.contains("beyond the λ-chunks"), "{err}");
    }

    #[test]
    fn duplicate_pixels_take_the_last_value() {
        // the reference fills a dense matrix (`raw[i, j] = count`): of duplicated pixels the last counts
        let (n, p, w, dmax) = (80usize, 1usize, 3usize, 30usize);
        let t = toy(n, dmax + 2 * w + 1, 21);
        let (edges, cmin) = edges();
        let mk = |bi: &[i64], bj: &[i64], c: &[f64]| -> Output {
            let inp = Input {
                n,
                bi,
                bj,
                count: c,
                weight: &t.weight,
                expected: &t.expected,
                p,
                w,
                max_diag: dmax,
                tile_rows: 20,
                edges: &edges,
                cmin: &cmin,
            };
            score_chrom(&inp).unwrap()
        };
        let want = mk(&t.bi, &t.bj, &t.count);
        // every 7th pixel duplicated: first a bogus count, then the true one
        let (mut bi, mut bj, mut c) = (vec![], vec![], vec![]);
        for q in 0..t.bi.len() {
            if q % 7 == 0 {
                bi.push(t.bi[q]);
                bj.push(t.bj[q]);
                c.push(t.count[q] * 3.0 + 5.0);
            }
            bi.push(t.bi[q]);
            bj.push(t.bj[q]);
            c.push(t.count[q]);
        }
        let got = mk(&bi, &bj, &c);
        assert!(want.n_tested > 100);
        assert_eq!(got.n_tested, want.n_tested);
        assert_eq!(got.i, want.i);
        assert_eq!(got.cnt, want.cnt);
        assert_eq!(got.lam, want.lam);
        assert_eq!(got.hist, want.hist);
    }
}
