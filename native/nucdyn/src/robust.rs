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
use crate::dynamics::{RestraintForm, System, V3};
use crate::params::{anneal_schedule, Params};
use crate::pipeline::{Input, Output, StageEngine, StageLog};
use crate::protocol2017::{
    backbone_restraints, calc_particles, contact_restraints_counted, remove_isolated_contacts, remove_violated_contacts,
    start_coords,
};
use crate::restraints::RestraintSet;
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
fn kernel_sum(k: &Kernel, hist: &[f64], bin: f64, n_pairs: f64, s: f64) -> f64 {
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
}

impl EmData {
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
        EmData { dist, counts: counts.to_vec(), hist, bin, n_pairs, n_particles: n }
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

/// Responsibility of a contact with probability `phi` under the true component.
#[inline]
fn resp(phi: f64, eps: f64, u: f64) -> f64 {
    let a = (1.0 - eps) * phi;
    a / (a + eps * u)
}

/// E-step + M-step on fixed distances.  `per_model`: likelihood and
/// responsibilities per model (pooled for ε, s); otherwise from the
/// ensemble-mean φ.
pub fn em_update(data: &EmData, k: &Kernel, p: &Params, eps0: f64, s0: f64) -> EmResult {
    let t0 = Instant::now();
    let u = 1.0 / data.n_pairs.max(1.0);
    let nm = data.dist.len();
    let wsum: f64 = data.counts.iter().map(|&c| c as f64).sum::<f64>().max(1.0);
    // returns (loglik per contact, eps, responsibilities rows)
    let fit = |phi: &[Vec<f64>]| -> (f64, f64, Vec<Vec<f64>>) {
        let rows: Vec<Vec<f64>> = if p.robust_per_model {
            phi.to_vec()
        } else {
            let nk = data.counts.len();
            let mut mean = vec![0.0; nk];
            for row in phi {
                for (m, x) in mean.iter_mut().zip(row) {
                    *m += x / nm as f64;
                }
            }
            vec![mean]
        };
        let mut eps = eps0;
        if p.robust_learn_eps {
            for _ in 0..200 {
                let mut fsum = 0.0;
                for row in &rows {
                    for (&ph, &c) in row.iter().zip(&data.counts) {
                        fsum += c as f64 * (1.0 - resp(ph, eps, u));
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
        for row in &rows {
            for (&ph, &c) in row.iter().zip(&data.counts) {
                ll += c as f64 * (((1.0 - eps) * ph + eps * u) / u).ln();
            }
        }
        let rr = rows.iter().map(|row| row.iter().map(|&ph| resp(ph, eps, u)).collect()).collect();
        (ll / (wsum * rows.len() as f64), eps, rr)
    };
    let grid: Vec<f64> = if p.robust_learn_s { p.robust_s_grid.clone() } else { vec![s0] };
    let mut best: Option<(f64, f64, f64, Vec<Vec<f64>>, Vec<f64>)> = None;
    for &s in &grid {
        let (phi, g) = data.phi(k, s);
        let (ll, eps, rr) = fit(&phi);
        if best.as_ref().is_none_or(|b| ll > b.0) {
            best = Some((ll, s, eps, rr, g));
        }
    }
    let (ll, s, eps, rr, g) = best.unwrap();
    let weights: Vec<Vec<f64>> = rr
        .iter()
        .map(|row| {
            row.iter()
                .zip(&data.counts)
                .map(|(&r, &c)| {
                    let w = if p.robust_count_combine { 1.0 - (1.0 - r).powi(c as i32) } else { r };
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
        mean_w: mean_w / (wsum * nr),
        frac_low: low / (wsum * nr),
        prox_frac: g_mean * u,
        capture_q: (1.0 - eps) * wsum / g_mean,
        n_particles: data.n_particles,
        seconds: t0.elapsed().as_secs_f64(),
    };
    EmResult { weights, eps, s, log }
}

/// Install contact-restraint weights (restraints `nb..`) into the system.
fn set_weights(sys: &mut System, nb: usize, w: &[Vec<f64>], n_models: usize) {
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

fn log(p: &Params, msg: &str) {
    if p.verbose {
        eprintln!("[uchrom_nucdyn] {msg}");
    }
}

/// Split `n` temperature steps into `k` contiguous parts (sizes differ by <= 1).
fn split_schedule(n: usize, k: usize) -> Vec<std::ops::Range<usize>> {
    let k = k.clamp(1, n.max(1));
    (0..k).map(|i| (i * n / k)..((i + 1) * n / k)).collect()
}

/// `calc_genome_structure` of the `robust` protocol.
pub fn calc_genome_structure(input: &Input, p: &Params, engine: &mut dyn StageEngine) -> Result<Output, String> {
    p.validate()?;
    let t0 = Instant::now();
    let n_models = p.n_models;
    let kern = Kernel::from_params(p);
    let s_max = p.robust_s_grid.iter().cloned().fold(p.robust_s, f64::max);
    let mut d = build_contact_dict(input.chr_a, input.pos_a, input.chr_b, input.pos_b, input.ambig, input.active, true);
    let mut chroms: Vec<u32> = input.chr_a.iter().chain(input.chr_b).copied().collect();
    chroms.sort_unstable();
    chroms.dedup();
    log(p, &format!("total number of contacts = {}", contact_count(&d)));
    remove_isolated_contacts(&mut d, p.isolation_threshold_cis, p.isolation_pos_error);
    log(p, &format!("contacts after removing isolated = {}", contact_count(&d)));
    let mut sizes = p.particle_sizes.clone();
    let last = *sizes.last().unwrap();
    sizes.extend(std::iter::repeat_n(last, p.robust_refine));
    let mut prev: Option<Structure> = None;
    let mut stages = vec![];
    let (mut eps, mut s) = (p.robust_eps, p.robust_s);
    let mut final_weights = vec![];
    for (stage, &ps) in sizes.iter().enumerate() {
        let ts = Instant::now();
        if p.robust_remove_violated && stage > 0 && ps < 0.5e6 {
            if let Some(pr) = prev.as_ref() {
                remove_violated_contacts(&mut d, pr, p.violated_threshold_2017);
                log(p, &format!("contacts after removing violated = {}", contact_count(&d)));
            }
        }
        let psi = ps as i32 as i64;
        let mut st = Structure::new(&calc_particles(&d, &chroms, psi));
        let n = st.n_particles();
        st.coords = start_coords(&st, n_models, prev.as_ref(), p, stage);
        let (mut rest, n_used, counts) =
            contact_restraints_counted(&d, &st, p.dist_power_law, p.contact_dist_lower, p.contact_dist_upper);
        let mut all = backbone_restraints(&st, psi, p.backbone_dist_lower, p.backbone_dist_upper);
        let nb = all.len();
        all.append(&mut rest);
        let groups: Vec<u32> = (0..=all.len() as u32).collect();
        let pairs: Vec<[u32; 2]> = all[nb..].iter().map(|r| [r.i, r.j]).collect();
        let rs = RestraintSet { rest: all, groups, n_contacts: n_used };
        let mut sys = System::new(n, vec![1.0; n], vec![1.0; n], &rs).with_form(RestraintForm::Weighted2017);
        let schedule = anneal_schedule(p.temp_start, p.temp_end, p.temp_steps_for(stage.min(p.particle_sizes.len() - 1)), 1.0);
        let dyn_steps = p.dyn_steps_for(stage.min(p.particle_sizes.len() - 1));
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
        let mut t_em = 0.0;
        for (seg, range) in parts.iter().enumerate() {
            if reweight {
                let te = Instant::now();
                let data = EmData::new(&coords, &pairs, &counts, &kern, s_max, p.robust_pair_sample);
                let res = em_update(&data, &kern, p, eps, s);
                eps = res.eps;
                s = res.s;
                set_weights(&mut sys, nb, &res.weights, n_models);
                let mut l = res.log;
                l.segment = seg;
                l.seconds = te.elapsed().as_secs_f64();
                t_em += l.seconds;
                log(
                    p,
                    &format!(
                        "  EM (part {seg}): eps {:.4} s {:.2} mean w {:.3} low {:.3} prox {:.2e} q {:.3} ll {:.3} ({:.2} s)",
                        l.eps, l.s, l.mean_w, l.frac_low, l.prox_frac, l.capture_q, l.loglik, l.seconds
                    ),
                );
                em_logs.push(l);
            }
            let key = stage + 1000 * seg;
            coords = engine.anneal(&sys, coords, &schedule[range.clone()], dyn_steps, p.dist_force_const, 1.0, key, p)?;
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
            dist_force_const: p.dist_force_const,
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
        prev = Some(st);
    }
    let st = prev.unwrap();
    let nm = st.coords.len();
    Ok(Output {
        chroms: st.chroms,
        seq_pos: st.seq_pos,
        coords: st.coords,
        model_rmsds: vec![f64::NAN; nm],
        particle_size: last,
        stages,
        seconds_total: t0.elapsed().as_secs_f64(),
        contact_weights: final_weights,
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
