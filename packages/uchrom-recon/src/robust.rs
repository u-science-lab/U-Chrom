//! Protocol `robust`: the 2017 NucDynamics protocol with a noise-aware
//! observation model (new single-cell method, `benchmarks/screcon/PREREG.md`
//! §7, milestone M2: optimisation / annealing, no sampling yet).
//!
//! Observation model.  Every observed contact is either *true* (probability
//! 1 - ε) — it landed on particle pair (i, j) with probability
//! f(d_ij) / G, f a contact kernel of the 3-D distance and G = Σ_pairs f the
//! normaliser — or *false* (probability ε), uniform over all N (N - 1) / 2
//! particle pairs.  Given the current structure the posterior probability
//! that a contact on pair k is true is
//!
//! ```text
//!     r_k = (1 - ε) f(d_k) / G  /  [ (1 - ε) f(d_k) / G + ε / N_pairs ]
//! ```
//!
//! and a restraint built from c_k contacts is wanted when at least one of them
//! is true: w_k = 1 - (1 - r_k)^c_k.  EM: E-step = these weights on the
//! contact restraints (force and energy scaled by w_k, `Weighted2017`);
//! M-step = ε (and the kernel width s, by a grid search) maximising the
//! mixture likelihood Σ_k c_k ln[(1 - ε) f(d_k) / G + ε / N_pairs]; the
//! annealing then re-fits the structure to the re-weighted restraints.
//!
//! Everything else is the 2017 protocol (`protocol2017.rs`): isolated-contact
//! filter, particles binned from the current contacts, restraints from binned
//! contact counts, random start / interpolation, annealing schedule, removal
//! of contacts violated by >= 6 radii before stages finer than 0.5 Mb
//! (`robust_remove_violated`).  Weights are computed before the annealing of
//! every stage from `robust_start_stage` on, on the start coordinates (the
//! previous stage's structure interpolated to the new particles, so distances
//! are in the previous stage's particle radii), and again inside the stage
//! when `robust_segments` > 1.  `robust_per_model`: each model gets the
//! weights of its own distances; otherwise one weight set from the
//! ensemble-mean contact probability.

use crate::contacts::{build_contact_dict, contact_count, ContactDict, Structure};
use crate::dynamics::{NoContact, RestraintForm, System, V3};
use crate::params::{anneal_schedule, Params};
use crate::pipeline::{Input, Output, StageEngine, StageLog};
use crate::protocol2017::{
    backbone_restraints, calc_particles, contact_restraints_counted, remove_isolated_contacts, remove_violated_contacts,
    start_coords,
};
use crate::restraints::{Restraint, RestraintSet};
use std::collections::BTreeMap;
use crate::support::{support_evidence, SupportParams};
use rayon::prelude::*;
use serde::Serialize;
use std::time::Instant;

/// One EM update.
#[derive(Clone, Debug, Serialize)]
pub struct EmLog {
    /// 0: before the stage's annealing; k: after part k of the schedule
    pub segment: usize,
    pub eps: f64,
    pub s: f64,
    pub d0: f64,
    /// mixture log-likelihood per contact (+ ln N_pairs, so 0 = "no better than uniform")
    pub loglik: f64,
    /// contact-weighted mean restraint weight (mean over models)
    pub mean_w: f64,
    /// fraction of contacts on restraints with weight < 0.5
    pub frac_low: f64,
    /// G / N_pairs: fraction of pairs in contact under the kernel (mean over models)
    pub prox_frac: f64,
    /// implied capture efficiency (1 - ε) n_contacts / G (mean over models)
    pub capture_q: f64,
    pub n_particles: usize,
    pub seconds: f64,
    /// diploid input: fraction of the homolog-ambiguous contacts whose most likely copy pair
    /// has posterior >= 0.9 (given that the contact is true); absent for haploid input
    #[serde(skip_serializing_if = "Option::is_none")]
    pub phase_confident: Option<f64>,
    /// diploid input: number of homolog-ambiguous contacts in the update
    #[serde(skip_serializing_if = "Option::is_none")]
    pub n_ambiguous: Option<usize>,
    /// few-cell deconvolution: mixture log-likelihood per contact with the cell prior ν replaced by
    /// uniform (λ only; comparable between runs with different seeds / priors)
    #[serde(skip_serializing_if = "Option::is_none")]
    pub ll_marginal: Option<f64>,
}

/// Contact kernel f(d) = exp(-((d - d0)+ / s)^k).
#[derive(Clone, Copy, Debug)]
pub struct Kernel {
    pub gauss: bool,
    pub d0: f64,
}

impl Kernel {
    pub fn from_params(p: &Params) -> Kernel {
        Kernel { gauss: p.robust_kernel == "gauss", d0: p.robust_d0 }
    }
    #[inline]
    pub fn f(&self, d: f64, s: f64) -> f64 {
        let x = (d - self.d0).max(0.0) / s;
        if self.gauss {
            (-x * x).exp()
        } else {
            (-x).exp()
        }
    }
    /// Distance beyond which f < e^-20 for widths up to `s_max`.
    pub fn reach(&self, s_max: f64) -> f64 {
        self.d0 + if self.gauss { 20f64.sqrt() } else { 20.0 } * s_max
    }
}

/// Histogram of all pair distances below `rmax` (unordered pairs i < j,
/// adjacent pairs included), bins of width `bin`.  With `sample` > 0 and more
/// particles, only every k-th particle is a first member (all others the
/// second) and the counts are scaled to all pairs.  Returns (histogram,
/// number of pairs).  Integer counting: independent of the thread count.
pub fn pair_histogram(pos: &[V3], rmax: f64, bin: f64, sample: usize) -> (Vec<f64>, f64) {
    let n = pos.len();
    let nbins = (rmax / bin).ceil() as usize + 1;
    let n_pairs = n as f64 * (n as f64 - 1.0) / 2.0;
    if n < 2 {
        return (vec![0.0; nbins], 0.0);
    }
    let mut mn = [f64::INFINITY; 3];
    let mut mx = [f64::NEG_INFINITY; 3];
    for p in pos {
        for k in 0..3 {
            mn[k] = mn[k].min(p[k]);
            mx[k] = mx[k].max(p[k]);
        }
    }
    let mut cs = rmax;
    let max_cells = (8 * n).max(64) as f64;
    let mut dims;
    loop {
        dims = [0usize; 3];
        for k in 0..3 {
            dims[k] = (((mx[k] - mn[k]) / cs).floor() as usize) + 1;
        }
        if (dims[0] as f64) * (dims[1] as f64) * (dims[2] as f64) <= max_cells || !cs.is_finite() {
            break;
        }
        cs *= 1.26;
    }
    let reach = (rmax / cs).ceil() as usize; // cells to visit on each side
    let cell = |p: &V3| -> [usize; 3] {
        let mut c = [0usize; 3];
        for k in 0..3 {
            let v = ((p[k] - mn[k]) / cs).floor();
            c[k] = if v < 0.0 { 0 } else { (v as usize).min(dims[k] - 1) };
        }
        c
    };
    let lin = |c: [usize; 3]| (c[2] * dims[1] + c[1]) * dims[0] + c[0];
    let ncell = dims[0] * dims[1] * dims[2];
    let pc: Vec<[usize; 3]> = pos.iter().map(cell).collect();
    let mut start = vec![0u32; ncell + 1];
    for c in &pc {
        start[lin(*c) + 1] += 1;
    }
    for k in 0..ncell {
        start[k + 1] += start[k];
    }
    let mut fill = start.clone();
    let mut items = vec![0u32; n];
    for (i, c) in pc.iter().enumerate() {
        let l = lin(*c);
        items[fill[l] as usize] = i as u32;
        fill[l] += 1;
    }
    let stride = if sample > 0 && n > sample { n.div_ceil(sample) } else { 1 };
    let firsts: Vec<usize> = (0..n).step_by(stride).collect();
    let r2max = rmax * rmax;
    let hist: Vec<u64> = firsts
        .par_chunks(64)
        .map(|chunk| {
            let mut h = vec![0u64; nbins];
            for &i in chunk {
                let c = pc[i];
                let p = pos[i];
                for z in c[2].saturating_sub(reach)..=(c[2] + reach).min(dims[2] - 1) {
                    for y in c[1].saturating_sub(reach)..=(c[1] + reach).min(dims[1] - 1) {
                        for x in c[0].saturating_sub(reach)..=(c[0] + reach).min(dims[0] - 1) {
                            let l = lin([x, y, z]);
                            for &j in &items[start[l] as usize..start[l + 1] as usize] {
                                let j = j as usize;
                                // ordered pairs (i, j != i); unordered when not sampling: j > i
                                if j == i || (stride == 1 && j < i) {
                                    continue;
                                }
                                let q = pos[j];
                                let d2 = (q[0] - p[0]).powi(2) + (q[1] - p[1]).powi(2) + (q[2] - p[2]).powi(2);
                                if d2 < r2max {
                                    h[((d2.sqrt() / bin) as usize).min(nbins - 1)] += 1;
                                }
                            }
                        }
                    }
                }
            }
            h
        })
        .reduce(|| vec![0u64; nbins], |mut a, b| {
            for (x, y) in a.iter_mut().zip(b) {
                *x += y;
            }
            a
        });
    // sampled: ordered pairs from |firsts| particles -> unordered pairs of all n
    let scale = if stride == 1 { 1.0 } else { n as f64 / firsts.len() as f64 / 2.0 };
    (hist.into_iter().map(|c| c as f64 * scale).collect(), n_pairs)
}

/// Σ_pairs f(d): histogram bins at their centres; pairs beyond the histogram
/// counted at f(rmax).
pub(crate) fn kernel_sum(k: &Kernel, hist: &[f64], bin: f64, n_pairs: f64, s: f64) -> f64 {
    let mut g = 0.0;
    let mut cnt = 0.0;
    for (b, &h) in hist.iter().enumerate() {
        if h > 0.0 {
            g += h * k.f((b as f64 + 0.5) * bin, s);
            cnt += h;
        }
    }
    let rmax = hist.len() as f64 * bin;
    g + (n_pairs - cnt).max(0.0) * k.f(rmax, s)
}

/// Inputs of one EM update: per-model contact-restraint distances and pair
/// histograms.
pub struct EmData {
    /// [model][contact restraint] distance
    pub dist: Vec<Vec<f64>>,
    pub counts: Vec<u32>,
    pub hist: Vec<Vec<f64>>,
    pub bin: f64,
    pub n_pairs: f64,
    pub n_particles: usize,
    /// Per-contact prior odds factors (input `prior`, p / (1 - p) relative to
    /// the global rate), grouped by restraint: (offsets, values).  None: every
    /// contact 1.
    pub odds: Option<(Vec<u32>, Vec<f64>)>,
}

impl EmData {
    /// Call `f(odds)` once per contact of restraint `k`.
    #[inline]
    pub fn for_contacts(&self, k: usize, mut f: impl FnMut(f64)) {
        match &self.odds {
            Some((off, o)) => {
                for &x in &o[off[k] as usize..off[k + 1] as usize] {
                    f(x)
                }
            }
            None => {
                for _ in 0..self.counts[k] {
                    f(1.0)
                }
            }
        }
    }

    pub fn new(coords: &[Vec<V3>], pairs: &[[u32; 2]], counts: &[u32], k: &Kernel, s_max: f64, sample: usize) -> EmData {
        let bin = 0.02;
        let rmax = k.reach(s_max);
        let n = coords.first().map(|c| c.len()).unwrap_or(0);
        let dist: Vec<Vec<f64>> = coords
            .iter()
            .map(|c| {
                pairs
                    .iter()
                    .map(|&[i, j]| {
                        let (a, b) = (c[i as usize], c[j as usize]);
                        ((a[0] - b[0]).powi(2) + (a[1] - b[1]).powi(2) + (a[2] - b[2]).powi(2)).sqrt()
                    })
                    .collect()
            })
            .collect();
        let mut n_pairs = 0.0;
        let hist: Vec<Vec<f64>> = coords
            .iter()
            .map(|c| {
                let (h, np) = pair_histogram(c, rmax, bin, sample);
                n_pairs = np;
                h
            })
            .collect();
        EmData { dist, counts: counts.to_vec(), hist, bin, n_pairs, n_particles: n, odds: None }
    }

    /// φ[m][k] = f(d_k^m) / G_m(s) (probability of a true contact landing on
    /// pair k in model m) and G_m.
    fn phi(&self, k: &Kernel, s: f64) -> (Vec<Vec<f64>>, Vec<f64>) {
        let g: Vec<f64> =
            self.hist.iter().map(|h| kernel_sum(k, h, self.bin, self.n_pairs, s).max(1e-300)).collect();
        let phi = self.dist.iter().zip(&g).map(|(d, &gm)| d.iter().map(|&x| k.f(x, s) / gm).collect()).collect();
        (phi, g)
    }
}

/// Result of one EM update.
pub struct EmResult {
    /// [model][contact restraint] weight; one row when not per model
    pub weights: Vec<Vec<f64>>,
    pub eps: f64,
    pub s: f64,
    pub log: EmLog,
}

/// Posterior probability that a contact with prior odds factor `o` (1 = no
/// prior information) on a pair of true-contact probability `phi` is true.
#[inline]
fn resp(o: f64, phi: f64, eps: f64, u: f64) -> f64 {
    let a = o * (1.0 - eps) * phi;
    if a <= 0.0 {
        0.0
    } else {
        a / (a + eps * u)
    }
}

/// E-step + M-step on fixed distances.  `per_model`: likelihood and
/// responsibilities per model (pooled for ε, s); otherwise from the
/// ensemble-mean φ.
pub fn em_update(data: &EmData, k: &Kernel, p: &Params, eps0: f64, s0: f64) -> EmResult {
    let t0 = Instant::now();
    let u = 1.0 / data.n_pairs.max(1.0);
    let nm = data.dist.len();
    let nk = data.counts.len();
    let wsum: f64 = data.counts.iter().map(|&c| c as f64).sum::<f64>().max(1.0);
    let rows_of = |phi: &[Vec<f64>]| -> Vec<Vec<f64>> {
        if p.robust_per_model {
            phi.to_vec()
        } else {
            let mut mean = vec![0.0; nk];
            for row in phi {
                for (m, x) in mean.iter_mut().zip(row) {
                    *m += x / nm as f64;
                }
            }
            vec![mean]
        }
    };
    // (loglik per contact, eps)
    let fit = |rows: &[Vec<f64>]| -> (f64, f64) {
        let mut eps = eps0;
        if p.robust_learn_eps {
            for _ in 0..200 {
                let mut fsum = 0.0;
                for row in rows {
                    for (kk, &ph) in row.iter().enumerate() {
                        data.for_contacts(kk, |o| fsum += 1.0 - resp(o, ph, eps, u));
                    }
                }
                let new = (fsum / (wsum * rows.len() as f64)).clamp(p.robust_eps_min, p.robust_eps_max);
                let done = (new - eps).abs() < 1e-8;
                eps = new;
                if done {
                    break;
                }
            }
        }
        let mut ll = 0.0;
        for row in rows {
            for (kk, &ph) in row.iter().enumerate() {
                data.for_contacts(kk, |o| {
                    let rho = o * (1.0 - eps) / (o * (1.0 - eps) + eps);
                    ll += ((rho * ph + (1.0 - rho) * u) / u).ln();
                });
            }
        }
        (ll / (wsum * rows.len() as f64), eps)
    };
    let grid: Vec<f64> = if p.robust_learn_s { p.robust_s_grid.clone() } else { vec![s0] };
    let d0s: Vec<f64> = if p.robust_d0_grid.is_empty() { vec![k.d0] } else { p.robust_d0_grid.clone() };
    let mut best: Option<(f64, f64, f64, f64)> = None;
    for (&s, &d0) in grid.iter().flat_map(|s| d0s.iter().map(move |d| (s, d))) {
        let k = &Kernel { d0, ..*k };
        let (phi, _) = data.phi(k, s);
        let (ll, eps) = fit(&rows_of(&phi));
        if best.is_none_or(|b| ll > b.0) {
            best = Some((ll, s, eps, d0));
        }
    }
    let (ll, s, eps, d0) = best.unwrap();
    let k = &Kernel { d0, ..*k };
    let (phi, g) = data.phi(k, s);
    let rows = rows_of(&phi);
    let weights: Vec<Vec<f64>> = rows
        .iter()
        .map(|row| {
            row.iter()
                .enumerate()
                .map(|(kk, &ph)| {
                    let (mut none, mut sum, mut n) = (1.0f64, 0.0f64, 0.0f64);
                    data.for_contacts(kk, |o| {
                        let r = resp(o, ph, eps, u);
                        none *= 1.0 - r;
                        sum += r;
                        n += 1.0;
                    });
                    let w = if p.robust_count_combine { 1.0 - none } else { sum / n.max(1.0) };
                    w.max(p.robust_w_floor)
                })
                .collect()
        })
        .collect();
    let mut mean_w = 0.0;
    let mut low = 0.0;
    for row in &weights {
        for (&w, &c) in row.iter().zip(&data.counts) {
            mean_w += w * c as f64;
            if w < 0.5 {
                low += c as f64;
            }
        }
    }
    let nr = weights.len() as f64;
    let g_mean = g.iter().sum::<f64>() / g.len().max(1) as f64;
    let log = EmLog {
        segment: 0,
        eps,
        s,
        loglik: ll,
        d0,
        mean_w: mean_w / (wsum * nr),
        frac_low: low / (wsum * nr),
        prox_frac: g_mean * u,
        capture_q: (1.0 - eps) * wsum / g_mean,
        n_particles: data.n_particles,
        seconds: t0.elapsed().as_secs_f64(),
        phase_confident: None,
        n_ambiguous: None,
        ll_marginal: None,
    };
    EmResult { weights, eps, s, log }
}

/// Install contact-restraint weights (restraints `nb..`) into the system.
pub(crate) fn set_weights(sys: &mut System, nb: usize, w: &[Vec<f64>], n_models: usize) {
    let full = |row: &Vec<f64>| -> Vec<f64> {
        let mut v = vec![1.0; nb];
        v.extend_from_slice(row);
        v
    };
    if w.len() == 1 {
        sys.rest_w = full(&w[0]);
        sys.model_w = None;
    } else {
        debug_assert_eq!(w.len(), n_models);
        sys.model_w = Some(w.iter().map(full).collect());
    }
}

/// Per input contact (row of the input arrays): its restraint's weight at the
/// final stage (mean over models), NaN when the contact was filtered out.
fn contact_weights(d: &ContactDict, st: &Structure, sys: &System, nb: usize, n_input: usize) -> Vec<f64> {
    let mut out = vec![f64::NAN; n_input];
    let mean_w = |idx: usize| -> f64 {
        match &sys.model_w {
            Some(w) => w.iter().map(|row| row[idx]).sum::<f64>() / w.len() as f64,
            None => sys.rest_w[idx],
        }
    };
    // same traversal as `contact_restraints_counted`
    let mut idx = nb;
    for (&(ca, cb), contacts) in d {
        let (Some(sa), Some(sb)) = (st.chrom_slot(ca), st.chrom_slot(cb)) else {
            continue;
        };
        let (pa, pb) = (&st.seq_pos[sa], &st.seq_pos[sb]);
        let mut bins: std::collections::BTreeMap<(usize, usize), Vec<u32>> = Default::default();
        for c in contacts {
            let j = pa.partition_point(|&x| x < c.pos_a as i32 as i64);
            let kk = pb.partition_point(|&x| x < c.pos_b as i32 as i64);
            if j >= pa.len() || kk >= pb.len() {
                continue;
            }
            bins.entry((j, kk)).or_default().push(c.number);
        }
        for (_, rows) in bins {
            let w = mean_w(idx);
            for r in rows {
                if (r as usize) < n_input {
                    out[r as usize] = w;
                }
            }
            idx += 1;
        }
    }
    out
}

/// Restraint force constant: the 2017 constant, scaled by min(1, x N / W)
/// with `robust_force_norm` = x > 0 (W: sum of contact-restraint weights,
/// mean over models).
pub(crate) fn force_constant(p: &Params, sys: &System, nb: usize, n: usize) -> f64 {
    if p.robust_force_norm <= 0.0 {
        return p.dist_force_const;
    }
    let w = match &sys.model_w {
        Some(rows) => rows.iter().map(|r| r[nb..].iter().sum::<f64>()).sum::<f64>() / rows.len() as f64,
        None => sys.rest_w[nb..].iter().sum::<f64>(),
    };
    p.dist_force_const * (p.robust_force_norm * n as f64 / w.max(1e-9)).min(1.0)
}

/// Adaptive resolution (`robust_merge_below`): keep only the particles that
/// hold a contact end (a contact end at p goes to the first particle at or
/// after p, as in `contact_restraints`) plus the first and last particle of
/// each chromosome; runs of contact-free particles are dropped (their
/// coordinates are interpolated in the output).
pub fn merge_empty_particles(d: &ContactDict, full: &BTreeMap<u32, Vec<i64>>) -> BTreeMap<u32, Vec<i64>> {
    let mut occ: BTreeMap<u32, Vec<bool>> = full.iter().map(|(&c, v)| (c, vec![false; v.len()])).collect();
    for (&(ca, cb), contacts) in d {
        for c in contacts {
            for (chrom, pos) in [(ca, c.pos_a), (cb, c.pos_b)] {
                if let (Some(sp), Some(o)) = (full.get(&chrom), occ.get_mut(&chrom)) {
                    let k = sp.partition_point(|&x| x < pos as i32 as i64);
                    if k < sp.len() {
                        o[k] = true;
                    }
                }
            }
        }
    }
    full.iter()
        .map(|(&c, sp)| {
            let o = &occ[&c];
            let n = sp.len();
            (c, (0..n).filter(|&k| k == 0 || k + 1 == n || o[k]).map(|k| sp[k]).collect())
        })
        .collect()
}

/// Backbone restraints between consecutive kept particles: a gap of g
/// particle sizes gets bounds (lower, upper) x g^nu (g = 1: the 2017 bounds).
pub fn merged_backbone_restraints(st: &Structure, ps: i64, lower: f64, upper: f64, nu: f64) -> Vec<Restraint> {
    let (bbl, bbu) = (lower as f32 as f64, upper as f32 as f64);
    let mut out = vec![];
    for (slot, sp) in st.seq_pos.iter().enumerate() {
        let off = st.offsets[slot];
        for k in 0..sp.len().saturating_sub(1) {
            let g = (sp[k + 1] - sp[k]) as f64 / ps as f64;
            let dist = if g > 1.0 { g.powf(nu) } else { g };
            out.push(Restraint { i: (off + k) as u32, j: (off + k + 1) as u32, lo: dist * bbl, hi: dist * bbu, ambig: 0, weight: 1.0 });
        }
    }
    out
}

/// Coordinates of `st` (kept particles) at every position of the full grid
/// (linear interpolation, clamped at the ends).
pub(crate) fn expand_to_grid(st: &Structure, full: &BTreeMap<u32, Vec<i64>>) -> (Vec<Vec<i64>>, Vec<Vec<V3>>) {
    let seq: Vec<Vec<i64>> = st.chroms.iter().map(|c| full[c].clone()).collect();
    let coords = (0..st.n_models())
        .map(|m| {
            let mut out = vec![];
            for (slot, sp) in seq.iter().enumerate() {
                let kp = &st.seq_pos[slot];
                let kc = st.chrom_coords(m, slot);
                for &x in sp {
                    let j = kp.partition_point(|&y| y < x);
                    let q = if j < kp.len() && kp[j] == x {
                        kc[j]
                    } else if j == 0 {
                        kc[0]
                    } else if j >= kp.len() {
                        kc[kp.len() - 1]
                    } else {
                        let f = (x - kp[j - 1]) as f64 / (kp[j] - kp[j - 1]) as f64;
                        let (a, b) = (kc[j - 1], kc[j]);
                        [a[0] + f * (b[0] - a[0]), a[1] + f * (b[1] - a[1]), a[2] + f * (b[2] - a[2])]
                    };
                    out.push(q);
                }
            }
            out
        })
        .collect();
    (seq, coords)
}

/// Prior likelihood ratios of the contacts of every contact restraint (same
/// traversal as `contact_restraints_counted`): (offsets, values).
fn restraint_odds(d: &ContactDict, st: &Structure, lr: &[f64]) -> (Vec<u32>, Vec<f64>) {
    let mut off = vec![0u32];
    let mut vals = vec![];
    for (&(ca, cb), contacts) in d {
        let (Some(sa), Some(sb)) = (st.chrom_slot(ca), st.chrom_slot(cb)) else {
            continue;
        };
        let (pa, pb) = (&st.seq_pos[sa], &st.seq_pos[sb]);
        let mut bins: std::collections::BTreeMap<(usize, usize), Vec<f64>> = Default::default();
        for c in contacts {
            let j = pa.partition_point(|&x| x < c.pos_a as i32 as i64);
            let kk = pb.partition_point(|&x| x < c.pos_b as i32 as i64);
            if j >= pa.len() || kk >= pb.len() {
                continue;
            }
            bins.entry((j, kk)).or_default().push(lr.get(c.number as usize).copied().unwrap_or(1.0));
        }
        for (_, v) in bins {
            vals.extend(v);
            off.push(vals.len() as u32);
        }
    }
    (off, vals)
}

fn log(p: &Params, msg: &str) {
    if p.verbose {
        eprintln!("[uchrom_recon] {msg}");
    }
}

/// Split `n` temperature steps into `k` contiguous parts (sizes differ by <= 1).
pub(crate) fn split_schedule(n: usize, k: usize) -> Vec<std::ops::Range<usize>> {
    let k = k.clamp(1, n.max(1));
    (0..k).map(|i| (i * n / k)..((i + 1) * n / k)).collect()
}

/// `calc_genome_structure` of the `robust` protocol.
pub fn calc_genome_structure(input: &Input, p: &Params, engine: &mut dyn StageEngine) -> Result<Output, String> {
    p.validate()?;
    let t0 = Instant::now();
    let n_models = p.n_models;
    let kern = Kernel::from_params(p);
    // histogram reach: the largest d0 of the grid
    let kern_reach = Kernel { d0: p.robust_d0_grid.iter().cloned().fold(p.robust_d0, f64::max), ..kern };
    let s_max = p.robust_s_grid.iter().cloned().fold(p.robust_s, f64::max);
    let mut d = build_contact_dict(input.chr_a, input.pos_a, input.chr_b, input.pos_b, input.ambig, input.active, true);
    let mut chroms: Vec<u32> = input.chr_a.iter().chain(input.chr_b).copied().collect();
    chroms.sort_unstable();
    chroms.dedup();
    log(p, &format!("total number of contacts = {}", contact_count(&d)));
    let last = *p.particle_sizes.last().unwrap();
    // per-contact prior likelihood ratios: input x local support
    let support_lr: Option<Vec<f64>> = if p.robust_support_rel > 0.0 {
        let ts = Instant::now();
        let sp = SupportParams { window: p.robust_support_rel * last, seed: p.seed, ..Default::default() };
        let s = support_evidence(input.chr_a, input.pos_a, input.chr_b, input.pos_b, &sp);
        for &(st, e, n, mu, size) in &s.strata {
            log(p, &format!("  support stratum {st}: {n} contacts, false fraction {e:.3}, NB mean {mu:.2} size {size:.2}"));
        }
        log(p, &format!("support evidence ({} kb window) in {:.2} s", sp.window / 1e3, ts.elapsed().as_secs_f64()));
        let mut lr = s.lr;
        if let Some(x) = input.prior_lr {
            for (a, b) in lr.iter_mut().zip(x) {
                *a *= b;
            }
        }
        Some(lr)
    } else {
        None
    };
    let prior_lr: Option<&[f64]> = support_lr.as_deref().or(input.prior_lr);
    remove_isolated_contacts(&mut d, p.isolation_threshold_cis, p.isolation_pos_error);
    log(p, &format!("contacts after removing isolated = {}", contact_count(&d)));
    let mut sizes = p.particle_sizes.clone();
    sizes.extend(std::iter::repeat_n(last, p.robust_refine));
    let mut prev: Option<Structure> = None;
    let mut stages = vec![];
    let (mut eps, mut s) = (p.robust_eps, p.robust_s);
    let mut final_weights = vec![];
    let mut last_full: BTreeMap<u32, Vec<i64>> = BTreeMap::new();
    let mut last_merged = false;
    let mut snapshots: Vec<Vec<Vec<V3>>> = vec![];
    for (stage, &ps) in sizes.iter().enumerate() {
        let ts = Instant::now();
        if p.robust_remove_violated && stage > 0 && ps < 0.5e6 {
            if let Some(pr) = prev.as_ref() {
                remove_violated_contacts(&mut d, pr, p.violated_threshold_2017);
                log(p, &format!("contacts after removing violated = {}", contact_count(&d)));
            }
        }
        let psi = ps as i32 as i64;
        let full = calc_particles(&d, &chroms, psi);
        let merge = p.robust_merge_below > 0.0 && ps <= p.robust_merge_below;
        let mut st = Structure::new(&if merge { merge_empty_particles(&d, &full) } else { full.clone() });
        let n = st.n_particles();
        st.coords = start_coords(&st, n_models, prev.as_ref(), p, stage);
        let (mut rest, n_used, counts) =
            contact_restraints_counted(&d, &st, p.dist_power_law, p.contact_dist_lower, p.contact_dist_upper);
        if p.robust_count_cap > 0 {
            let (exp32, lo32, hi32) = (p.dist_power_law as f32, p.contact_dist_lower as f32 as f64, p.contact_dist_upper as f32 as f64);
            let dist = (1.0f32 * (p.robust_count_cap as f32).powf(exp32)) as f64;
            for (r, &c) in rest.iter_mut().zip(&counts) {
                if c > p.robust_count_cap {
                    r.lo = dist * lo32;
                    r.hi = dist * hi32;
                }
            }
        }
        let mut all = if merge {
            merged_backbone_restraints(&st, psi, p.backbone_dist_lower, p.backbone_dist_upper, p.robust_merge_nu)
        } else {
            backbone_restraints(&st, psi, p.backbone_dist_lower, p.backbone_dist_upper)
        };
        let nb = all.len();
        all.append(&mut rest);
        let groups: Vec<u32> = (0..=all.len() as u32).collect();
        let pairs: Vec<[u32; 2]> = all[nb..].iter().map(|r| [r.i, r.j]).collect();
        let odds = prior_lr.map(|lr| restraint_odds(&d, &st, lr));
        if let Some((off, _)) = &odds {
            debug_assert_eq!(off.len(), pairs.len() + 1);
        }
        let rs = RestraintSet { rest: all, groups, n_contacts: n_used };
        let mut sys = System::new(n, vec![1.0; n], vec![1.0; n], &rs).with_form(RestraintForm::Weighted2017);
        let refine_pass = stage >= p.particle_sizes.len();
        let n_temp = if refine_pass && p.robust_refine_temp_steps > 0 {
            p.robust_refine_temp_steps
        } else {
            p.robust_temp_steps_for(stage.min(p.particle_sizes.len() - 1))
        };
        let t_start = if refine_pass && p.robust_refine_temp_start > 0.0 { p.robust_refine_temp_start } else { p.temp_start };
        let schedule = anneal_schedule(t_start, p.temp_end, n_temp, 1.0);
        let dyn_steps = p.robust_dyn_steps_for(stage.min(p.particle_sizes.len() - 1));
        let reweight = stage >= p.robust_start_stage && !counts.is_empty();
        let parts = split_schedule(schedule.len(), if reweight { p.robust_segments } else { 1 });
        let t_prep = ts.elapsed().as_secs_f64();
        log(
            p,
            &format!(
                "stage {} ({} kb): {} particles, {} contacts, {} restraints, {} models",
                stage + 1,
                ps / 1e3,
                n,
                n_used,
                sys.n_restraints(),
                n_models
            ),
        );
        let td = Instant::now();
        let mut coords = std::mem::take(&mut st.coords);
        let mut em_logs = vec![];
        let mut f_dist = p.dist_force_const;
        let mut t_em = 0.0;
        for (seg, range) in parts.iter().enumerate() {
            if reweight {
                let te = Instant::now();
                let mut data = EmData::new(&coords, &pairs, &counts, &kern_reach, s_max, p.robust_pair_sample);
                data.odds = odds.clone();
                let res = em_update(&data, &kern, p, eps, s);
                eps = res.eps;
                s = res.s;
                set_weights(&mut sys, nb, &res.weights, n_models);
                if p.robust_nc_scale > 0.0 {
                    let q = res.log.capture_q.clamp(0.0, p.robust_nc_qmax);
                    sys.nc = Some(NoContact { lambda: p.robust_nc_scale * q, d0: p.robust_nc_d0, s: p.robust_nc_s });
                }
                let mut l = res.log;
                l.segment = seg;
                l.seconds = te.elapsed().as_secs_f64();
                t_em += l.seconds;
                log(
                    p,
                    &format!(
                        "  EM (part {seg}): eps {:.4} s {:.2} d0 {:.1} mean w {:.3} low {:.3} prox {:.2e} q {:.3} ll {:.3} ({:.2} s)",
                        l.eps, l.s, l.d0, l.mean_w, l.frac_low, l.prox_frac, l.capture_q, l.loglik, l.seconds
                    ),
                );
                em_logs.push(l);
            }
            if p.mix_density_rho > 0.0 && stage as i64 >= p.mix_density_stage {
                // opt-in shape-free density cap (off by default: the frozen EMber is unchanged)
                sys.density = Some(crate::dynamics::DensityCap { kappa: p.mix_density_kappa, r: p.mix_density_r, rho_max: p.mix_density_rho });
            }
            let key = stage + 1000 * seg;
            f_dist = force_constant(p, &sys, nb, n);
            coords = engine.anneal(&sys, coords, &schedule[range.clone()], dyn_steps, f_dist, 1.0, key, p)?;
        }
        // sampling (calibrated ensembles): after the final annealing, constant temperature
        // `robust_sample_temp` with the final repulsion, velocities re-drawn every temperature
        // step (Andersen-like); one snapshot per model after each block of `robust_sample_steps`
        if stage + 1 == sizes.len() && p.robust_sample_temp > 0.0 && p.robust_sample_steps > 0 {
            let f_rep = schedule.last().map(|x| x.1).unwrap_or(1.0);
            let block = vec![(p.robust_sample_temp, f_rep); p.robust_sample_steps];
            let ds = if p.robust_sample_dyn_steps > 0 { p.robust_sample_dyn_steps } else { dyn_steps };
            for k in 0..p.robust_sample_snapshots.max(1) {
                coords = engine.anneal(&sys, coords, &block, ds, f_dist, 1.0, stage + 5000 + 1000 * k, p)?;
                snapshots.push(coords.clone());
            }
            log(p, &format!("  sampled {} snapshot(s) per model at T = {}", snapshots.len(), p.robust_sample_temp));
        }
        for c in coords.iter_mut() {
            let k = c.len() as f64;
            let mut m = [0.0; 3];
            for q in c.iter() {
                for x in 0..3 {
                    m[x] += q[x];
                }
            }
            for q in c.iter_mut() {
                for x in 0..3 {
                    q[x] -= m[x] / k;
                }
            }
        }
        st.coords = coords;
        let t_dyn = td.elapsed().as_secs_f64() - t_em;
        log(p, &format!("stage {} done in {:.2} s ({:.2} s dynamics)", stage + 1, t_prep + t_dyn + t_em, t_dyn));
        if stage + 1 == sizes.len() {
            final_weights = contact_weights(&d, &st, &sys, nb, input.chr_a.len());
        }
        stages.push(StageLog {
            stage,
            particle_size: ps,
            bead_size: 1.0,
            n_models,
            n_particles: n,
            n_contacts: n_used,
            n_restraints: sys.n_restraints(),
            dist_force_const: f_dist,
            temp_steps: schedule.len(),
            dynamics_steps: dyn_steps,
            seconds_prepare: t_prep + t_em,
            seconds_dynamics: t_dyn,
            removed_models: vec![],
            device: engine.name(),
            rep_list_overflows: engine.overflow_stats().0,
            steps_without_repulsion: engine.overflow_stats().1,
            robust: em_logs,
        });
        last_full = full;
        last_merged = merge;
        prev = Some(st);
    }
    let mut st = prev.unwrap();
    if snapshots.len() > 1 {
        // every snapshot of every model is a model of the output (snapshot-major)
        st.coords = snapshots
            .into_iter()
            .flatten()
            .map(|mut c| {
                let k = c.len() as f64;
                let mut m = [0.0; 3];
                for q in c.iter() {
                    for x in 0..3 {
                        m[x] += q[x];
                    }
                }
                for q in c.iter_mut() {
                    for x in 0..3 {
                        q[x] -= m[x] / k;
                    }
                }
                c
            })
            .collect();
    }
    let (seq_pos, coords) = if last_merged { expand_to_grid(&st, &last_full) } else { (st.seq_pos, st.coords) };
    let nm = coords.len();
    Ok(Output {
        chroms: st.chroms,
        seq_pos,
        coords,
        model_rmsds: vec![f64::NAN; nm],
        particle_size: last,
        stages,
        seconds_total: t0.elapsed().as_secs_f64(),
        contact_weights: final_weights,
        diploid: false,
        phase_probs: vec![],
        mix_cells: 0,
        cell_probs: vec![],
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::rng::Rng;

    fn cloud(n: usize, seed: u64) -> Vec<V3> {
        let mut r = Rng::new(seed);
        (0..n).map(|_| [r.normal() * 5.0, r.normal() * 5.0, r.normal() * 5.0]).collect()
    }

    #[test]
    fn pair_histogram_matches_brute_force() {
        let pos = cloud(700, 3);
        let (h, np) = pair_histogram(&pos, 6.0, 0.1, 0);
        let mut b = vec![0.0; h.len()];
        for i in 0..pos.len() {
            for j in i + 1..pos.len() {
                let d: f64 = (0..3).map(|k| (pos[i][k] - pos[j][k]).powi(2)).sum::<f64>().sqrt();
                if d < 6.0 {
                    b[((d / 0.1) as usize).min(h.len() - 1)] += 1.0;
                }
            }
        }
        assert_eq!(h, b);
        assert_eq!(np, 700.0 * 699.0 / 2.0);
        // sampled: unbiased within a few per cent
        let (hs, _) = pair_histogram(&pos, 6.0, 0.1, 100);
        let (a, c): (f64, f64) = (h.iter().sum(), hs.iter().sum());
        assert!((a / c - 1.0).abs() < 0.1, "{a} vs {c}");
    }

    #[test]
    fn em_downweights_inconsistent_contacts_and_learns_eps() {
        // a compact chain; 900 true contacts between close pairs, 100 between far pairs
        let mut r = Rng::new(9);
        let mut pos = vec![];
        let mut q = [0.0f64; 3];
        for _ in 0..1500 {
            q = [q[0] + r.normal(), q[1] + r.normal(), q[2] + r.normal()];
            pos.push(q);
        }
        let d = |i: usize, j: usize| -> f64 { (0..3).map(|k| (pos[i][k] - pos[j][k]).powi(2)).sum::<f64>().sqrt() };
        let mut pairs = vec![];
        let mut truth = vec![];
        while pairs.len() < 1000 {
            let i = (r.uniform() * 1500.0) as usize;
            let j = (r.uniform() * 1500.0) as usize;
            if i.abs_diff(j) < 2 {
                continue;
            }
            let want_true = pairs.len() < 900;
            let dd = d(i, j);
            if (want_true && dd < 2.5) || (!want_true && dd > 15.0) {
                pairs.push([i as u32, j as u32]);
                truth.push(want_true);
            }
        }
        let counts = vec![1u32; pairs.len()];
        let p = Params { protocol: "robust".into(), ..Default::default() };
        let k = Kernel::from_params(&p);
        let data = EmData::new(&[pos.clone()], &pairs, &counts, &k, 6.0, 0);
        let res = em_update(&data, &k, &p, 0.3, 1.5);
        assert!((res.eps - 0.1).abs() < 0.03, "eps {}", res.eps);
        let w = &res.weights[0];
        let wt: f64 = w.iter().zip(&truth).filter(|(_, &t)| t).map(|(x, _)| x).sum::<f64>() / 900.0;
        let wf: f64 = w.iter().zip(&truth).filter(|(_, &t)| !t).map(|(x, _)| x).sum::<f64>() / 100.0;
        assert!(wt > 0.95 && wf < 0.05, "true {wt} false {wf}");
    }

    #[test]
    fn merging_keeps_contact_particles_and_expands_back() {
        use crate::contacts::Contact;
        let mut d: ContactDict = BTreeMap::new();
        d.insert((0, 0), vec![Contact { pos_a: 150, pos_b: 950, ambig: 1, number: 0 }]);
        let full: BTreeMap<u32, Vec<i64>> = [(0u32, (1..=12).map(|k| k * 100).collect::<Vec<i64>>())].into_iter().collect();
        let kept = merge_empty_particles(&d, &full);
        // contact ends 150 -> particle 200, 950 -> 1000; chromosome ends 100, 1200
        assert_eq!(kept[&0], vec![100, 200, 1000, 1200]);
        let mut st = Structure::new(&kept);
        st.coords = vec![vec![[0.0; 3], [1.0, 0.0, 0.0], [9.0, 0.0, 0.0], [11.0, 0.0, 0.0]]];
        let bb = merged_backbone_restraints(&st, 100, 0.1, 1.1, 0.5);
        assert_eq!(bb.len(), 3);
        assert!((bb[0].hi - 1.1f32 as f64).abs() < 1e-12); // gap 1: the 2017 bound
        assert!((bb[1].hi - 8f64.sqrt() * (1.1f32 as f64)).abs() < 1e-12);
        let (seq, coords) = expand_to_grid(&st, &full);
        assert_eq!(seq[0], full[&0]);
        let x: Vec<f64> = coords[0].iter().map(|q| q[0]).collect();
        assert_eq!(x, vec![0.0, 1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0, 11.0]);
    }

    #[test]
    fn schedule_split_covers_all_steps() {
        let parts = split_schedule(500, 3);
        assert_eq!(parts.len(), 3);
        assert_eq!(parts[0].start, 0);
        assert_eq!(parts[2].end, 500);
        for w in parts.windows(2) {
            assert_eq!(w[0].end, w[1].start);
        }
    }
}
