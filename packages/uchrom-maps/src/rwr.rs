//! Random walk with restart (RWR) on single-cell contact maps, and the SnapHiC statistics across cells.
//!
//! The imputation of scHiCluster (Zhou et al. 2019, *PNAS* 116:14011) and SnapHiC (Yu et al. 2021, *Nat
//! Methods* 18:1056): a cell's chromosome is a graph — one node per bin, an edge between neighbouring bins
//! (the chain) and between the two bins of every contact (binary) — and the imputed contact of two bins is
//! the stationary probability of a random walk that restarts at its origin with probability `rp`:
//!
//! ```text
//!     Q = rp (I - (1 - rp) P)^-1,   P = D^-1 A   (row-stochastic; A adjacency, D = diag(degrees))
//!     R = Q + Q^T                                (SnapHiC's symmetrised map)
//! ```
//!
//! With `M = D - (1 - rp) A` (symmetric, strictly diagonally dominant: positive definite) `Q = rp M^-1 D`,
//! so `R_ij = rp G_ij (d_i + d_j)` with `G = M^-1`.  Only a band of `R` is used (`|i - j| <= max_diag`), and
//! `M` is sparse: the chain plus a few contacts per bin.  Here `G` is computed on the *profile* of `M`
//! widened to the band (row `i` holds columns `f_i ..= i`, `f_i = min(i - max_diag, leftmost neighbour)`):
//! a Cholesky factorisation in profile storage (fill stays inside the profile) and the selected inversion
//! of Takahashi et al. (1973) / Erisman & Tinney (1975), `Z[k, j] = -sum_m Z[k, m] l_m` over the rows `m > j`
//! of column `j` of the factor, which gives every entry of `G` inside the profile — the band among them —
//! exactly (to rounding), in `O(sum_j |S_j|^2)` instead of the `O(m^3)` of a dense inverse.
//!
//! Sliding windows (SnapHiC2: Li et al. 2022, *Comput Struct Biotechnol J* 20:2778): the graph of a window
//! of `size` bins (the chain and the contacts with both bins inside) is solved on its own; windows start
//! every `step` bins and a pixel takes its value from the window whose centre is nearest to the pixel's
//! midpoint (`i + j` in `[2 s + size - step, 2 s + size + step)` for the window starting at `s`).  `size = 0`
//! solves the whole chromosome as one graph (SnapHiC's original "inverse" method).
//!
//! SnapHiC statistics ([`snaphic_chrom`]): per cell, the band is normalised per diagonal (z-scores, the top
//! `trim` share of each diagonal left out of the mean and standard deviation), every pixel gets its local
//! background (the mean over the `(2 outer + 1)^2` square around it minus the `(2 inner + 1)^2` one), and
//! the sums over cells that the paired t-test needs are accumulated (`z`, background, their difference and
//! its square, the cells with `z > outlier`).  Cells run in parallel batches, the windows of a cell too.

use rayon::prelude::*;

/// Parameters of the RWR band of one cell ([`rwr_band`]).
#[derive(Clone, Copy, Debug)]
pub struct RwrParams {
    /// restart probability (SnapHiC 0.05)
    pub rp: f64,
    /// window size in bins; 0 = the whole chromosome
    pub window: usize,
    /// window step in bins (SnapHiC2: window / 2)
    pub step: usize,
    /// band of the output: offsets `0 ..= max_diag`
    pub max_diag: usize,
    /// contacts closer than this (bins) are left out (SnapHiC: 2)
    pub min_sep: usize,
    /// link neighbouring bins
    pub chain: bool,
    /// leave at 0 the pixels SnapHiC v0.2's sliding windows never set (sums `i + j = (2k + 1) step` and
    /// `i + j <= step`): only to compare with the authors' code
    pub holes: bool,
}

/// Sparse symmetric adjacency (CSR, sorted unique neighbours).
pub struct Graph {
    pub n: usize,
    ptr: Vec<usize>,
    idx: Vec<u32>,
}

impl Graph {
    /// The binary graph of one cell's chromosome: an edge per contact `(i, j)` with `|i - j| >= min_sep`
    /// (duplicates merged) and, with `chain`, between every pair of neighbouring bins.
    pub fn new(n: usize, ci: &[i64], cj: &[i64], min_sep: usize, chain: bool) -> Result<Graph, String> {
        if ci.len() != cj.len() {
            return Err("contacts: i and j differ in length".into());
        }
        let mut edges: Vec<(u32, u32)> = Vec::with_capacity(ci.len() + n);
        for (&a, &b) in ci.iter().zip(cj) {
            if a < 0 || b < 0 || a as usize >= n || b as usize >= n {
                return Err(format!("contact ({a}, {b}) outside the chromosome's {n} bins"));
            }
            let (lo, hi) = if a <= b { (a as u32, b as u32) } else { (b as u32, a as u32) };
            if ((hi - lo) as usize) >= min_sep.max(1) {
                edges.push((lo, hi));
            }
        }
        if chain {
            for k in 1..n {
                edges.push(((k - 1) as u32, k as u32));
            }
        }
        edges.sort_unstable();
        edges.dedup();
        let mut deg = vec![0usize; n + 1];
        for &(a, b) in &edges {
            deg[a as usize] += 1;
            deg[b as usize] += 1;
        }
        let mut ptr = vec![0usize; n + 1];
        for k in 0..n {
            ptr[k + 1] = ptr[k] + deg[k];
        }
        let mut fill = ptr.clone();
        let mut idx = vec![0u32; ptr[n]];
        // edges sorted by (a, b): pushing b into a's list keeps it sorted; a into b's list arrives in
        // increasing a — sorted as well, but interleaved with b's own (larger) neighbours: sort per row
        for &(a, b) in &edges {
            idx[fill[a as usize]] = b;
            fill[a as usize] += 1;
            idx[fill[b as usize]] = a;
            fill[b as usize] += 1;
        }
        for k in 0..n {
            idx[ptr[k]..ptr[k + 1]].sort_unstable();
        }
        Ok(Graph { n, ptr, idx })
    }

    #[inline]
    fn neighbours(&self, k: usize) -> &[u32] {
        &self.idx[self.ptr[k]..self.ptr[k + 1]]
    }

    /// Neighbours of `k` inside `[s, e)`.
    #[inline]
    fn neighbours_in(&self, k: usize, s: usize, e: usize) -> &[u32] {
        let nb = self.neighbours(k);
        let lo = nb.partition_point(|&q| (q as usize) < s);
        let hi = nb.partition_point(|&q| (q as usize) < e);
        &nb[lo..hi]
    }
}

// ----------------------------------------------------------------------------------------------------------
// dense helpers (four accumulators: lets the compiler vectorise the reductions)
// ----------------------------------------------------------------------------------------------------------

#[inline(always)]
fn dot(a: &[f64], b: &[f64]) -> f64 {
    let n = a.len().min(b.len());
    let (a, b) = (&a[..n], &b[..n]);
    let mut s = [0.0f64; 4];
    let chunks = n / 4;
    for c in 0..chunks {
        let k = 4 * c;
        s[0] += a[k] * b[k];
        s[1] += a[k + 1] * b[k + 1];
        s[2] += a[k + 2] * b[k + 2];
        s[3] += a[k + 3] * b[k + 3];
    }
    let mut r = (s[0] + s[1]) + (s[2] + s[3]);
    for k in 4 * chunks..n {
        r += a[k] * b[k];
    }
    r
}

#[inline(always)]
fn axpy(y: &mut [f64], x: &[f64], alpha: f64) {
    for (yv, &xv) in y.iter_mut().zip(x) {
        *yv += alpha * xv;
    }
}

// ----------------------------------------------------------------------------------------------------------
// one window: profile Cholesky + selected inversion
// ----------------------------------------------------------------------------------------------------------

/// Profile storage of a lower triangle: row `k` holds columns `first[k] ..= k` at `ptr[k] ..`.
struct Profile {
    first: Vec<usize>,
    ptr: Vec<usize>,
}

impl Profile {
    #[inline(always)]
    fn at(&self, k: usize, col: usize) -> usize {
        self.ptr[k] + col - self.first[k]
    }
    #[inline(always)]
    fn row(&self, k: usize) -> std::ops::Range<usize> {
        self.ptr[k]..self.ptr[k + 1]
    }
}

/// The windows of a chromosome of `n` bins: starts, and the range of pixel sums `i + j` each one owns.
#[derive(Clone, Debug)]
pub struct WindowPlan {
    pub starts: Vec<usize>,
    pub ends: Vec<usize>,
    /// pixel sums `c = i + j` owned by window `k`: `c_lo[k] <= c < c_hi[k]`
    pub c_lo: Vec<i64>,
    pub c_hi: Vec<i64>,
}

/// The windows SnapHiC2 solves: starts `0, step, 2 step, ...` and every pixel to the window whose centre is
/// nearest to its midpoint.  `window == 0` (or `>= n`): one window, the whole chromosome.
pub fn plan_windows(n: usize, window: usize, step: usize, max_diag: usize) -> Result<WindowPlan, String> {
    if n == 0 {
        return Ok(WindowPlan { starts: vec![], ends: vec![], c_lo: vec![], c_hi: vec![] });
    }
    if window == 0 || window >= n {
        return Ok(WindowPlan { starts: vec![0], ends: vec![n], c_lo: vec![i64::MIN], c_hi: vec![i64::MAX] });
    }
    if step == 0 || step > window {
        return Err(format!("step {step} must be in 1 ..= window {window}"));
    }
    if max_diag + step > window {
        return Err(format!(
            "window {window} bins too small for the band: needs window - step >= max_diag ({max_diag})"
        ));
    }
    let (w, st, ni) = (window as i64, step as i64, n as i64);
    // the pixel of sum c belongs to k = floor((c - w + step) / (2 step)); the largest sum is 2 n - 2
    let top = 2 * ni - 2 - w + st;
    let k_max = if top < 0 { 0 } else { top.div_euclid(2 * st) };
    let mut out = WindowPlan { starts: vec![], ends: vec![], c_lo: vec![], c_hi: vec![] };
    for k in 0..=k_max {
        let s = k * st;
        out.starts.push(s as usize);
        out.ends.push(((s + w) as usize).min(n));
        out.c_lo.push(if k == 0 { i64::MIN } else { 2 * s + w - st });
        out.c_hi.push(if k == k_max { i64::MAX } else { 2 * (s + st) + w - st });
    }
    Ok(out)
}

/// Owned pixels of window `k`, in canonical order (rows ascending, offsets ascending): calls `f(i, d)`.
#[inline]
fn for_owned(plan: &WindowPlan, k: usize, n: usize, max_diag: usize, mut f: impl FnMut(usize, usize)) {
    let (s, e) = (plan.starts[k], plan.ends[k]);
    let (lo, hi) = (plan.c_lo[k], plan.c_hi[k]);
    for i in s..e {
        let ii = i as i64;
        let d0 = if lo == i64::MIN { 0 } else { (lo - 2 * ii).max(0) };
        let d1 = {
            let mut d1 = (max_diag as i64).min((n - 1 - i) as i64).min((e - 1 - i) as i64);
            if hi != i64::MAX {
                d1 = d1.min(hi - 1 - 2 * ii);
            }
            d1
        };
        let mut d = d0;
        while d <= d1 {
            f(i, d as usize);
            d += 1;
        }
    }
}

/// The values of the pixels window `k` owns (canonical order of [`for_owned`]).
fn solve_window(g: &Graph, plan: &WindowPlan, k: usize, rp: f64, max_diag: usize) -> Result<Vec<f64>, String> {
    let (s, e) = (plan.starts[k], plan.ends[k]);
    let n = g.n;
    let m = e - s;
    let b = max_diag;
    // owned pixels: the smallest row (the recursion of the inverse stops at this column)
    let mut j_stop = usize::MAX;
    let mut n_owned = 0usize;
    for_owned(plan, k, n, max_diag, |i, _| {
        j_stop = j_stop.min(i - s);
        n_owned += 1;
    });
    if n_owned == 0 {
        return Ok(vec![]);
    }
    // local degrees and profile
    let mut deg = vec![0.0f64; m];
    let mut first = vec![0usize; m];
    for q in 0..m {
        let nb = g.neighbours_in(s + q, s, e);
        deg[q] = nb.len() as f64;
        let mut f = q.saturating_sub(b);
        if let Some(&left) = nb.first() {
            f = f.min(left as usize - s);
        }
        first[q] = f;
    }
    if deg.iter().any(|&d| d == 0.0) {
        return Err("a bin without neighbours in its window (chain=False and no contact): the walk is undefined".into());
    }
    let mut ptr = vec![0usize; m + 1];
    for q in 0..m {
        ptr[q + 1] = ptr[q] + (q - first[q] + 1);
    }
    let prof = Profile { first, ptr };
    let total = prof.ptr[m];
    // M = D - (1 - rp) A, lower triangle in profile storage
    let mut l = vec![0.0f64; total];
    let off = -(1.0 - rp);
    for q in 0..m {
        for &nbr in g.neighbours_in(s + q, s, e) {
            let c = nbr as usize - s;
            if c < q {
                l[prof.at(q, c)] = off;
            }
        }
        l[prof.at(q, q)] = deg[q];
    }
    // Cholesky M = L L^T, row by row (fill stays in the profile)
    for i in 0..m {
        let fi = prof.first[i];
        let (done, rest) = l.split_at_mut(prof.ptr[i]);
        let row_i = &mut rest[..i - fi + 1];
        for j in fi..i {
            let fj = prof.first[j];
            let k0 = fi.max(fj);
            let row_j = &done[prof.ptr[j]..prof.ptr[j + 1]];
            let sdot = dot(&row_i[k0 - fi..j - fi], &row_j[k0 - fj..j - fj]);
            row_i[j - fi] = (row_i[j - fi] - sdot) / row_j[j - fj];
        }
        let sq = dot(&row_i[..i - fi], &row_i[..i - fi]);
        let dd = row_i[i - fi] - sq;
        if !(dd > 0.0) {
            return Err(format!("Cholesky failed at bin {} (pivot {dd})", s + i));
        }
        row_i[i - fi] = dd.sqrt();
    }
    // long rows: rows q whose profile reaches beyond the band (first[q] < q - b) belong to the column
    // structure of j in first[q] ..= q - b - 1 (CSR over j, rows ascending)
    let mut lcount = vec![0usize; m + 1];
    for q in 0..m {
        if q >= b + 1 && prof.first[q] + b < q {
            for j in prof.first[q]..(q - b) {
                lcount[j + 1] += 1;
            }
        }
    }
    for j in 0..m {
        lcount[j + 1] += lcount[j];
    }
    let mut lfill = lcount.clone();
    let mut lrows = vec![0usize; lcount[m]];
    for q in 0..m {
        if q >= b + 1 && prof.first[q] + b < q {
            for j in prof.first[q]..(q - b) {
                lrows[lfill[j]] = q;
                lfill[j] += 1;
            }
        }
    }
    // selected inversion: Z = M^-1 on the profile, columns from the last down to j_stop
    let mut z = vec![0.0f64; total];
    let mut lb: Vec<f64> = Vec::with_capacity(b + 1);
    let mut ll: Vec<f64> = Vec::new();
    let mut yb: Vec<f64> = Vec::with_capacity(b + 1);
    let mut yl: Vec<f64> = Vec::new();
    for j in (j_stop..m).rev() {
        let jb = (j + b).min(m - 1);
        let nb = jb - j;
        let longs = &lrows[lcount[j]..lcount[j + 1]];
        let ljj = l[prof.at(j, j)];
        lb.clear();
        for a in 0..nb {
            let q = j + 1 + a;
            lb.push(l[prof.at(q, j)] / ljj);
        }
        ll.clear();
        for &q in longs {
            ll.push(l[prof.at(q, j)] / ljj);
        }
        yb.clear();
        yb.resize(nb, 0.0);
        yl.clear();
        yl.resize(longs.len(), 0.0);
        // band x band (symmetric): row q = j + 1 + a holds Z[q, j+1 .. q] contiguously
        for a in 0..nb {
            let q = j + 1 + a;
            let r = prof.row(q);
            let base = r.start + (j + 1) - prof.first[q];
            let zq = &z[base..base + a];
            let la = lb[a];
            let mut acc = dot(zq, &lb[..a]) + z[base + a] * la;
            if a > 0 {
                axpy(&mut yb[..a], zq, la);
            }
            acc += yb[a];
            yb[a] = acc;
        }
        // long rows: band columns contiguous, long columns scattered
        for (c, &q) in longs.iter().enumerate() {
            let r = prof.row(q);
            let fq = prof.first[q];
            let base = r.start + (j + 1) - fq;
            let zq = &z[base..base + nb];
            let lc = ll[c];
            let mut acc = dot(zq, &lb);
            axpy(&mut yb, zq, lc);
            for c2 in 0..c {
                let zv = z[r.start + longs[c2] - fq];
                acc += zv * ll[c2];
                yl[c2] += zv * lc;
            }
            acc += z[r.start + q - fq] * lc;
            yl[c] += acc;
        }
        for a in 0..nb {
            let q = j + 1 + a;
            z[prof.at(q, j)] = -yb[a];
        }
        for (c, &q) in longs.iter().enumerate() {
            z[prof.at(q, j)] = -yl[c];
        }
        z[prof.at(j, j)] = 1.0 / (ljj * ljj) + dot(&lb, &yb) + dot(&ll, &yl);
    }
    // R_ij = rp G_ij (d_i + d_j) for the owned pixels
    let mut out = Vec::with_capacity(n_owned);
    for_owned(plan, k, n, max_diag, |i, d| {
        let (a, c) = (i - s, i + d - s);
        out.push(rp * z[prof.at(c, a)] * (deg[a] + deg[c]));
    });
    Ok(out)
}

/// The RWR band of one cell's chromosome: `band[i * (max_diag + 1) + d] = R(i, i + d)` (NaN beyond the
/// chromosome).  Windows run in parallel (rayon).
pub fn rwr_band(n: usize, ci: &[i64], cj: &[i64], p: &RwrParams) -> Result<Vec<f64>, String> {
    if !(p.rp > 0.0 && p.rp < 1.0) {
        return Err(format!("restart probability {} must be in (0, 1)", p.rp));
    }
    let g = Graph::new(n, ci, cj, p.min_sep, p.chain)?;
    let plan = plan_windows(n, p.window, p.step, p.max_diag)?;
    let w = p.max_diag + 1;
    let vals: Vec<Result<Vec<f64>, String>> =
        (0..plan.starts.len()).into_par_iter().map(|k| solve_window(&g, &plan, k, p.rp, p.max_diag)).collect();
    let mut band = vec![f64::NAN; n * w];
    for (k, v) in vals.into_iter().enumerate() {
        let v = v?;
        let mut it = v.into_iter();
        for_owned(&plan, k, n, p.max_diag, |i, d| {
            band[i * w + d] = it.next().unwrap();
        });
    }
    if p.holes && p.window > 0 && p.window < n {
        let st = p.step;
        for i in 0..n {
            for d in 0..w.min(n - i) {
                let c = 2 * i + d;
                if c <= st || (c - st) % (2 * st) == 0 {
                    band[i * w + d] = 0.0;
                }
            }
        }
    }
    Ok(band)
}

// ----------------------------------------------------------------------------------------------------------
// SnapHiC: per-diagonal z-scores, local background, sums over cells
// ----------------------------------------------------------------------------------------------------------

/// Parameters of the SnapHiC normalisation and statistics.
#[derive(Clone, Copy, Debug)]
pub struct SnapParams {
    /// bins at each chromosome end left out of the normalisation (SnapHiC: the 50 kb buffer, 5 bins)
    pub edge: usize,
    /// share of the largest values of a diagonal left out of its mean and standard deviation (0.01)
    pub trim: f64,
    /// a diagonal with a smaller standard deviation is all zero (1e-6)
    pub min_sd: f64,
    /// local background: the `(2 outer + 1)^2` square minus the `(2 inner + 1)^2` one (2, 5)
    pub inner: usize,
    pub outer: usize,
    /// pixels with offsets `1 ..= out_diag` are tested
    pub out_diag: usize,
    /// a cell is an outlier at a pixel when its z-score exceeds this (1.96)
    pub outlier: f64,
    /// cells imputed at once (memory: ~3 bands each); 0 = the number of threads
    pub batch: usize,
}

/// Mean and standard deviation of the values of each diagonal `1 ..= max_diag` inside the trimmed rows
/// (`edge <= i`, `i + d <= n - 1 - edge`), the largest `round(trim * len) - 1` values left out (SnapHiC);
/// `None` where the diagonal is empty.
fn diagonal_stats(band: &[f64], n: usize, max_diag: usize, edge: usize, trim: f64) -> Vec<Option<(f64, f64)>> {
    let w = max_diag + 1;
    (0..w)
        .into_par_iter()
        .map(|d| {
            if d == 0 || n < 2 * edge + d + 1 {
                return None;
            }
            let (i0, i1) = (edge, n - 1 - edge - d); // rows i0 ..= i1
            let mut v: Vec<f64> = (i0..=i1).map(|i| band[i * w + d]).collect();
            let len = v.len();
            let t = (trim * len as f64).round_ties_even() as i64 - 1;
            let rest: &[f64] = if t < 0 {
                // SnapHiC keeps vals[-1:], the smallest value: standard deviation 0
                let mn = v.iter().cloned().fold(f64::INFINITY, f64::min);
                return Some((mn, 0.0));
            } else {
                let t = t as usize;
                if t > 0 {
                    v.select_nth_unstable_by(t - 1, |a, b| b.partial_cmp(a).unwrap_or(std::cmp::Ordering::Equal));
                }
                &v[t..]
            };
            let cnt = rest.len() as f64;
            let mu = crate::pairwise::pairwise_sum(rest) / cnt;
            let dev: Vec<f64> = rest.iter().map(|&x| (x - mu) * (x - mu)).collect();
            let sd = (crate::pairwise::pairwise_sum(&dev) / cnt).sqrt();
            Some((mu, sd))
        })
        .collect()
}

/// SnapHiC's normalisation of one cell's RWR band, in place: z-scores per diagonal inside the trimmed rows
/// (0 for a diagonal with standard deviation below `min_sd`), 0 for the other pixels of the chromosome with
/// offsets `1 ..= max_diag` (SnapHiC leaves them out: zeros in its matrices), NaN on the diagonal and
/// beyond the chromosome.
pub fn zscore_band(band: &mut [f64], n: usize, max_diag: usize, edge: usize, trim: f64, min_sd: f64) {
    let w = max_diag + 1;
    let stats = diagonal_stats(band, n, max_diag, edge, trim);
    band.par_chunks_mut(w).enumerate().for_each(|(i, row)| {
        row[0] = f64::NAN;
        for d in 1..w {
            if i + d >= n {
                row[d] = f64::NAN;
            } else if i >= edge && i + d + edge < n {
                row[d] = match stats[d] {
                    Some((mu, sd)) if sd >= min_sd => (row[d] - mu) / sd,
                    _ => 0.0,
                };
            } else {
                row[d] = 0.0;
            }
        }
    });
}

/// Local background of every pixel `(i, i + d)`, `1 <= d <= out_diag`: the mean of the defined entries
/// (`0 <= a < b < n`; offsets beyond `max_diag` count as 0) of the `(2 outer + 1)^2` square around it minus
/// the `(2 inner + 1)^2` square.  `z`: a normalised band (offsets `0 ..= max_diag`).  Layout `n x (out_diag
/// + 1)`, NaN for `d = 0` and beyond the chromosome.
pub fn local_background(
    z: &[f64],
    n: usize,
    max_diag: usize,
    out_diag: usize,
    inner: usize,
    outer: usize,
) -> Vec<f64> {
    let w = max_diag + 1;
    let wp = max_diag + 2;
    // row prefix sums over offsets 1 ..: pre[a * wp + t] = sum of z(a, t'), 1 <= t' < t, inside the chromosome
    let mut pre = vec![0.0f64; n * wp];
    pre.par_chunks_mut(wp).enumerate().for_each(|(a, p)| {
        let mut s = 0.0;
        p[0] = 0.0;
        p[1] = 0.0;
        for t in 1..w {
            if a + t < n {
                s += z[a * w + t];
            }
            p[t + 1] = s;
        }
    });
    let wo = out_diag + 1;
    let mut out = vec![f64::NAN; n * wo];
    let (ni, md) = (n as i64, max_diag as i64);
    out.par_chunks_mut(wo).enumerate().for_each(|(i, row)| {
        let ii = i as i64;
        for d in 1..wo {
            if i + d >= n {
                break;
            }
            let j = ii + d as i64;
            let box_sum = |h: i64| -> (f64, i64) {
                let (mut sum, mut cnt) = (0.0, 0i64);
                for a in (ii - h).max(0)..=(ii + h).min(ni - 1) {
                    // offsets of the row's columns j - h ..= j + h, inside 1 ..= n - 1 - a
                    let t0 = (j - h - a).max(1);
                    let t1 = (j + h - a).min(ni - 1 - a);
                    if t1 < t0 {
                        continue;
                    }
                    cnt += t1 - t0 + 1;
                    let (lo, hi) = (t0.min(md + 1), t1.min(md));
                    if hi >= lo {
                        let p = &pre[(a as usize) * wp..];
                        sum += p[(hi + 1) as usize] - p[lo as usize];
                    }
                }
                (sum, cnt)
            };
            let (sb, cb) = box_sum(outer as i64);
            let (ss, cs) = box_sum(inner as i64);
            let c = cb - cs;
            row[d] = if c > 0 { (sb - ss) / c as f64 } else { f64::NAN };
        }
    });
    out
}

/// Sums over the cells of one chromosome, layout `n x (out_diag + 1)`; pixels outside the tested region
/// (`margin <= i`, `i + d <= n - 1 - margin`, `1 <= d <= out_diag`, `margin = max(edge, outer)`) stay 0.
pub struct SnapAcc {
    pub sum_z: Vec<f64>,
    pub sum_l: Vec<f64>,
    pub sum_d: Vec<f64>,
    pub sum_dd: Vec<f64>,
    pub n_out: Vec<i64>,
    pub n_cells: usize,
}

/// One cell: RWR band, z-scores, local background.
fn cell_z_and_background(
    n: usize,
    ci: &[i64],
    cj: &[i64],
    rw: &RwrParams,
    sp: &SnapParams,
) -> Result<(Vec<f64>, Vec<f64>), String> {
    let mut band = rwr_band(n, ci, cj, rw)?;
    zscore_band(&mut band, n, rw.max_diag, sp.edge, sp.trim, sp.min_sd);
    let lb = local_background(&band, n, rw.max_diag, sp.out_diag, sp.inner, sp.outer);
    Ok((band, lb))
}

/// SnapHiC's sums over cells for one chromosome (see the module docs).  `cells[c] = (i, j)`: the contacts
/// of cell `c` (bins of the chromosome).
pub fn snaphic_chrom(n: usize, cells: &[(&[i64], &[i64])], rw: &RwrParams, sp: &SnapParams) -> Result<SnapAcc, String> {
    if sp.out_diag + sp.outer > rw.max_diag {
        return Err(format!(
            "max_diag {} must cover the tested offsets and their background (out_diag {} + outer {})",
            rw.max_diag, sp.out_diag, sp.outer
        ));
    }
    let wo = sp.out_diag + 1;
    let w = rw.max_diag + 1;
    let mut acc = SnapAcc {
        sum_z: vec![0.0; n * wo],
        sum_l: vec![0.0; n * wo],
        sum_d: vec![0.0; n * wo],
        sum_dd: vec![0.0; n * wo],
        n_out: vec![0; n * wo],
        n_cells: cells.len(),
    };
    let batch = if sp.batch == 0 { rayon::current_num_threads().max(1) } else { sp.batch };
    // tested pixels: both bins at least `margin` bins from the chromosome ends (SnapHiC: the normalised rows
    // and the background square inside the chromosome)
    let margin = sp.edge.max(sp.outer);
    for chunk in cells.chunks(batch) {
        let done: Vec<Result<(Vec<f64>, Vec<f64>), String>> =
            chunk.par_iter().map(|(ci, cj)| cell_z_and_background(n, ci, cj, rw, sp)).collect();
        let done: Vec<(Vec<f64>, Vec<f64>)> = done.into_iter().collect::<Result<_, _>>()?;
        let SnapAcc { sum_z, sum_l, sum_d, sum_dd, n_out, .. } = &mut acc;
        sum_z
            .par_chunks_mut(wo)
            .zip(sum_l.par_chunks_mut(wo))
            .zip(sum_d.par_chunks_mut(wo))
            .zip(sum_dd.par_chunks_mut(wo))
            .zip(n_out.par_chunks_mut(wo))
            .enumerate()
            .for_each(|(i, ((((sz, sl), sd), sdd), no))| {
                if i < margin {
                    return;
                }
                for d in 1..wo {
                    if i + d + margin >= n {
                        break;
                    }
                    for (zb, lb) in &done {
                        let zv = zb[i * w + d];
                        let lv = lb[i * wo + d];
                        let df = zv - lv;
                        sz[d] += zv;
                        sl[d] += lv;
                        sd[d] += df;
                        sdd[d] += df * df;
                        if zv > sp.outlier {
                            no[d] += 1;
                        }
                    }
                }
            });
    }
    Ok(acc)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn lcg(s: &mut u64) -> f64 {
        *s = s.wrapping_mul(6364136223846793005).wrapping_add(1442695040888963407);
        ((*s >> 11) as f64) / ((1u64 << 53) as f64)
    }

    /// dense reference: R = rp (G D + D G), G = (D - (1 - rp) A)^-1 by Gauss-Jordan
    fn dense_r(n: usize, g: &Graph, s: usize, e: usize, rp: f64) -> Vec<f64> {
        let m = e - s;
        let mut a = vec![0.0f64; m * m];
        let mut deg = vec![0.0f64; m];
        for q in 0..m {
            let nb = g.neighbours_in(s + q, s, e);
            deg[q] = nb.len() as f64;
            for &c in nb {
                a[q * m + (c as usize - s)] = -(1.0 - rp);
            }
            a[q * m + q] = deg[q];
        }
        let _ = n;
        // invert
        let mut inv = vec![0.0f64; m * m];
        for q in 0..m {
            inv[q * m + q] = 1.0;
        }
        for c in 0..m {
            let p = a[c * m + c];
            for k in 0..m {
                a[c * m + k] /= p;
                inv[c * m + k] /= p;
            }
            for r in 0..m {
                if r != c {
                    let f = a[r * m + c];
                    if f != 0.0 {
                        for k in 0..m {
                            a[r * m + k] -= f * a[c * m + k];
                            inv[r * m + k] -= f * inv[c * m + k];
                        }
                    }
                }
            }
        }
        let mut r = vec![0.0f64; m * m];
        for i in 0..m {
            for j in 0..m {
                r[i * m + j] = rp * inv[i * m + j] * (deg[i] + deg[j]);
            }
        }
        r
    }

    fn random_cell(n: usize, k: usize, seed: u64) -> (Vec<i64>, Vec<i64>) {
        let mut s = seed;
        let (mut ci, mut cj) = (vec![], vec![]);
        for _ in 0..k {
            let a = (lcg(&mut s) * n as f64) as i64;
            // distances spread over scales, a few long ones
            let d = (lcg(&mut s).powi(3) * n as f64) as i64 + 2;
            let b = a + d;
            if (b as usize) < n {
                ci.push(a);
                cj.push(b);
            }
        }
        (ci, cj)
    }

    #[test]
    fn whole_chromosome_matches_dense_inverse() {
        let n = 120;
        let (ci, cj) = random_cell(n, 80, 7);
        let p = RwrParams { rp: 0.05, window: 0, step: 0, max_diag: 30, min_sep: 2, chain: true, holes: false };
        let band = rwr_band(n, &ci, &cj, &p).unwrap();
        let g = Graph::new(n, &ci, &cj, 2, true).unwrap();
        let r = dense_r(n, &g, 0, n, 0.05);
        let w = p.max_diag + 1;
        for i in 0..n {
            for d in 0..w {
                if i + d < n {
                    let (x, y) = (band[i * w + d], r[i * n + i + d]);
                    assert!((x - y).abs() <= 1e-12 * y.abs().max(1.0), "{i} {d}: {x} vs {y}");
                } else {
                    assert!(band[i * w + d].is_nan());
                }
            }
        }
    }

    #[test]
    fn windows_take_the_window_of_the_pixel_midpoint() {
        let n = 301;
        let (ci, cj) = random_cell(n, 300, 11);
        let (win, step, md) = (80usize, 40usize, 25usize);
        let p = RwrParams { rp: 0.05, window: win, step, max_diag: md, min_sep: 2, chain: true, holes: false };
        let band = rwr_band(n, &ci, &cj, &p).unwrap();
        let g = Graph::new(n, &ci, &cj, 2, true).unwrap();
        let plan = plan_windows(n, win, step, md).unwrap();
        let w = md + 1;
        let mut seen = vec![false; n * w];
        for k in 0..plan.starts.len() {
            let (s, e) = (plan.starts[k], plan.ends[k]);
            let r = dense_r(n, &g, s, e, 0.05);
            let m = e - s;
            for_owned(&plan, k, n, md, |i, d| {
                assert!(!seen[i * w + d]);
                seen[i * w + d] = true;
                let y = r[(i - s) * m + (i + d - s)];
                let x = band[i * w + d];
                assert!((x - y).abs() <= 1e-12 * y.abs().max(1.0));
                // the window whose centre is nearest to the pixel's midpoint
                let c = (2 * i + d) as f64 / 2.0;
                let best = (0..plan.starts.len())
                    .map(|q| ((plan.starts[q] as f64 + win as f64 / 2.0 - c).abs(), q))
                    .fold((f64::INFINITY, 0), |a, b| if b.0 < a.0 { b } else { a });
                assert!((best.0 - (s as f64 + win as f64 / 2.0 - c).abs()).abs() < 1e-9);
            });
        }
        for i in 0..n {
            for d in 0..w {
                assert_eq!(seen[i * w + d], i + d < n, "pixel {i} {d}");
            }
        }
    }

    #[test]
    fn zscores_and_background() {
        let n = 200;
        let (ci, cj) = random_cell(n, 150, 3);
        let p = RwrParams { rp: 0.05, window: 0, step: 0, max_diag: 25, min_sep: 2, chain: true, holes: false };
        let mut band = rwr_band(n, &ci, &cj, &p).unwrap();
        let raw = band.clone();
        zscore_band(&mut band, n, 25, 5, 0.01, 1e-6);
        let w = 26;
        // diagonal 3: z of the kept values has mean ~0 when nothing is trimmed (len 187 -> round(1.87) - 1 = 1)
        let d = 3;
        let vals: Vec<f64> = (5..=(n - 1 - 5 - d)).map(|i| raw[i * w + d]).collect();
        let mut sorted = vals.clone();
        sorted.sort_by(|a, b| b.partial_cmp(a).unwrap());
        let rest = &sorted[1..];
        let mu = rest.iter().sum::<f64>() / rest.len() as f64;
        let sd = (rest.iter().map(|x| (x - mu) * (x - mu)).sum::<f64>() / rest.len() as f64).sqrt();
        for (q, i) in (5..=(n - 1 - 5 - d)).enumerate() {
            assert!((band[i * w + d] - (vals[q] - mu) / sd).abs() < 1e-10);
        }
        assert_eq!(band[2 * w + d], 0.0);
        assert!(band[10 * w].is_nan());
        // background by brute force
        let lb = local_background(&band, n, 25, 20, 2, 5);
        let zat = |a: i64, b: i64| -> Option<f64> {
            if a < 0 || b >= n as i64 || b <= a {
                None
            } else if b - a > 25 {
                Some(0.0)
            } else {
                Some(band[a as usize * w + (b - a) as usize])
            }
        };
        for &(i, d) in &[(0usize, 1usize), (7, 4), (50, 20), (190, 9), (100, 1)] {
            if i + d >= n {
                continue;
            }
            let (ii, jj) = (i as i64, (i + d) as i64);
            let (mut s, mut c) = (0.0, 0);
            for a in ii - 5..=ii + 5 {
                for b in jj - 5..=jj + 5 {
                    if (a - ii).abs() <= 2 && (b - jj).abs() <= 2 {
                        continue;
                    }
                    if let Some(v) = zat(a, b) {
                        s += v;
                        c += 1;
                    }
                }
            }
            assert!((lb[i * 21 + d] - s / c as f64).abs() < 1e-10, "{i} {d}");
        }
    }
}
