//! Local-support evidence for the `robust` observation model (structure-free).
//!
//! A false contact is uniform over locus pairs, so the number of other
//! contacts in a Chebyshev window of half-width W around it (both ends, same
//! chromosome pair) is distributed as the number around a *random location*
//! of the same chromosome pair and separation.  True contacts are spatially
//! correlated (neighbouring loci of two loci in contact are close too), so
//! they have more support.  Per separation stratum (cis: floor(log2(max(s,
//! W) / W)); trans: one stratum) the support counts of the contacts are fitted
//! as a mixture: false = the empirical distribution at random locations,
//! true = a negative binomial (EM; NB mean = weighted mean, size by a 1-D
//! search).  The evidence of a contact is the likelihood ratio
//! P(n | true) / P(n | false), which multiplies its posterior odds in the
//! structure EM (`Input::prior_lr`).

use crate::rng::Rng;
use rayon::prelude::*;
use std::collections::HashMap;

/// Settings of the support evidence.
#[derive(Clone, Copy, Debug)]
pub struct SupportParams {
    /// window half-width, bp
    pub window: f64,
    /// random locations per contact
    pub n_random: usize,
    /// counts are capped here
    pub nmax: usize,
    /// strata with fewer random locations are left at LR 1
    pub min_random: usize,
    pub lr_min: f64,
    pub lr_max: f64,
    pub seed: u64,
}

impl Default for SupportParams {
    fn default() -> Self {
        SupportParams { window: 4e5, n_random: 5, nmax: 30, min_random: 50, lr_min: 1e-3, lr_max: 1e3, seed: 0 }
    }
}

/// Result: per contact the support count, the LR and the stratum; per stratum
/// (key, fitted false fraction, contacts, NB mean, NB size).
#[derive(Clone, Debug, Default)]
pub struct Support {
    pub n: Vec<u32>,
    pub lr: Vec<f64>,
    pub stratum: Vec<i32>,
    pub strata: Vec<(i32, f64, usize, f64, f64)>,
}

/// ln Γ(x), x > 0 (Lanczos, g = 7, n = 9; |rel. error| < 1e-13).
pub fn ln_gamma(x: f64) -> f64 {
    const G: [f64; 9] = [
        0.999_999_999_999_809_9,
        676.520_368_121_885_1,
        -1_259.139_216_722_402_8,
        771.323_428_777_653_1,
        -176.615_029_162_140_6,
        12.507_343_278_686_905,
        -0.138_571_095_265_720_12,
        9.984_369_578_019_572e-6,
        1.505_632_735_149_311_6e-7,
    ];
    if x < 0.5 {
        let pi = std::f64::consts::PI;
        return (pi / (pi * x).sin()).ln() - ln_gamma(1.0 - x);
    }
    let x = x - 1.0;
    let mut a = G[0];
    let t = x + 7.5;
    for (i, &g) in G.iter().enumerate().skip(1) {
        a += g / (x + i as f64);
    }
    0.5 * (2.0 * std::f64::consts::PI).ln() + (x + 0.5) * t.ln() - t + a.ln()
}

/// Negative-binomial pmf on 0..=nmax (mean mu, size r), the tail lumped into nmax.
pub fn nb_pmf(mu: f64, r: f64, nmax: usize) -> Vec<f64> {
    let p = r / (r + mu); // success probability
    let mut v = Vec::with_capacity(nmax + 1);
    let mut acc = 0.0;
    for k in 0..nmax {
        let kf = k as f64;
        let lp = ln_gamma(kf + r) - ln_gamma(r) - ln_gamma(kf + 1.0) + r * p.ln() + kf * (1.0 - p).ln();
        let x = lp.exp();
        acc += x;
        v.push(x);
    }
    v.push((1.0 - acc).max(0.0));
    for x in v.iter_mut() {
        *x += 1e-12;
    }
    v
}

/// Maximise a unimodal 1-D function on [a, b] (golden section).
fn golden_max(f: impl Fn(f64) -> f64, mut a: f64, mut b: f64, iters: usize) -> f64 {
    let g = 0.5 * (5f64.sqrt() - 1.0);
    let (mut c, mut d) = (b - g * (b - a), a + g * (b - a));
    let (mut fc, mut fd) = (f(c), f(d));
    for _ in 0..iters {
        if fc > fd {
            b = d;
            d = c;
            fd = fc;
            c = b - g * (b - a);
            fc = f(c);
        } else {
            a = c;
            c = d;
            fc = fd;
            d = a + g * (b - a);
            fd = f(d);
        }
    }
    0.5 * (a + b)
}

/// Weighted maximum-likelihood NB fit on histogram weights `w` (0..=nmax, the
/// last bin a censored tail): alternating golden-section searches over ln mu
/// and ln size, starting from (`mu0`, `size0`).
fn fit_nb(w: &[f64], nmax: usize, mu0: f64, size0: f64) -> (f64, f64) {
    let ll = |mu: f64, r: f64| -> f64 {
        let v = nb_pmf(mu, r, nmax);
        w.iter().zip(&v).map(|(a, b)| a * b.ln()).sum()
    };
    let (mut lm, mut lr) = (mu0.max(1e-3).ln(), size0.ln());
    let hi_m = (5.0 * nmax as f64).ln();
    for _ in 0..4 {
        lm = golden_max(|x| ll(x.exp(), lr.exp()), -5.0, hi_m, 40);
        lr = golden_max(|x| ll(lm.exp(), x.exp()), -4.0, 8.0, 40);
    }
    (lm.exp(), lr.exp())
}

/// Mixture fit of one stratum: observed counts `obs` (capped), false
/// distribution `pf` (normalised).  -> (eps, P_true, mu, size).
fn fit_stratum(h: &[f64], pf: &[f64], nmax: usize) -> (f64, Vec<f64>, f64, f64) {
    let tot: f64 = h.iter().sum::<f64>().max(1e-300);
    let mean_obs = h.iter().enumerate().map(|(k, x)| k as f64 * x).sum::<f64>() / tot;
    let mean_f = pf.iter().enumerate().map(|(k, x)| k as f64 * x).sum::<f64>();
    let (mut eps, mut mu, mut size) = (0.3, (mean_obs.max(mean_f + 1.0)) * 1.5, 1.0);
    let mut pt = nb_pmf(mu, size, nmax);
    for _ in 0..100 {
        let post: Vec<f64> = (0..=nmax).map(|k| (1.0 - eps) * pt[k] / ((1.0 - eps) * pt[k] + eps * pf[k])).collect();
        let w: Vec<f64> = h.iter().zip(&post).map(|(a, b)| a * b).collect();
        let new_eps = (1.0 - w.iter().sum::<f64>() / tot).clamp(1e-6, 1.0 - 1e-6);
        let (m, s) = fit_nb(&w, nmax, mu, size);
        mu = m;
        size = s;
        pt = nb_pmf(mu, size, nmax);
        let done = (new_eps - eps).abs() < 1e-6;
        eps = new_eps;
        if done {
            break;
        }
    }
    (eps, pt, mu, size)
}

/// Contacts of one chromosome pair in a grid of W x W cells.
struct Grid {
    w: f64,
    cells: HashMap<(i64, i64), Vec<(i64, i64)>>,
}

impl Grid {
    fn new(pts: &[(i64, i64)], w: f64) -> Grid {
        let mut cells: HashMap<(i64, i64), Vec<(i64, i64)>> = HashMap::new();
        for &(a, b) in pts {
            cells.entry(((a as f64 / w).floor() as i64, (b as f64 / w).floor() as i64)).or_default().push((a, b));
        }
        Grid { w, cells }
    }
    /// contacts with |a' - a| <= W and |b' - b| <= W
    fn count(&self, a: i64, b: i64) -> u32 {
        let (ca, cb) = ((a as f64 / self.w).floor() as i64, (b as f64 / self.w).floor() as i64);
        let wi = self.w;
        let mut n = 0u32;
        for da in -1..=1 {
            for db in -1..=1 {
                if let Some(v) = self.cells.get(&(ca + da, cb + db)) {
                    for &(x, y) in v {
                        if ((x - a) as f64).abs() <= wi && ((y - b) as f64).abs() <= wi {
                            n += 1;
                        }
                    }
                }
            }
        }
        n
    }
}

/// Support evidence of every contact (chromosome ids, positions).
pub fn support_evidence(chr_a: &[u32], pos_a: &[i64], chr_b: &[u32], pos_b: &[i64], sp: &SupportParams) -> Support {
    let n = chr_a.len();
    let w = sp.window;
    // canonical order: (chrom_a, pos_a) <= (chrom_b, pos_b)
    let canon: Vec<(u32, u32, i64, i64)> = (0..n)
        .map(|i| {
            let (ca, pa, cb, pb) = (chr_a[i], pos_a[i], chr_b[i], pos_b[i]);
            if ca > cb || (ca == cb && pa > pb) {
                (cb, ca, pb, pa)
            } else {
                (ca, cb, pa, pb)
            }
        })
        .collect();
    let mut by_pair: HashMap<(u32, u32), Vec<usize>> = HashMap::new();
    for (i, c) in canon.iter().enumerate() {
        by_pair.entry((c.0, c.1)).or_default().push(i);
    }
    let mut lim: HashMap<u32, (i64, i64)> = HashMap::new();
    for c in &canon {
        for (ch, p) in [(c.0, c.2), (c.1, c.3)] {
            let e = lim.entry(ch).or_insert((p, p));
            e.0 = e.0.min(p);
            e.1 = e.1.max(p);
        }
    }
    let grids: HashMap<(u32, u32), Grid> = by_pair
        .par_iter()
        .map(|(&k, idx)| (k, Grid::new(&idx.iter().map(|&i| (canon[i].2, canon[i].3)).collect::<Vec<_>>(), w)))
        .collect();
    let stratum_sep = |sep: i64| -> i32 { ((sep as f64).max(w) / w).log2().floor() as i32 };
    let n_obs: Vec<u32> = canon.par_iter().map(|c| grids[&(c.0, c.1)].count(c.2, c.3).saturating_sub(1)).collect();
    let strat: Vec<i32> = canon.iter().map(|c| if c.0 != c.1 { -1 } else { stratum_sep(c.3 - c.2) }).collect();
    // random locations
    let rand: Vec<(i32, u32)> = (0..n)
        .into_par_iter()
        .flat_map_iter(|i| {
            let c = canon[i];
            let mut rng = Rng::from_keys(&[sp.seed, i as u64, 0x5u64]);
            let (lo_a, hi_a) = lim[&c.0];
            let (lo_b, hi_b) = lim[&c.1];
            let g = &grids[&(c.0, c.1)];
            let mut out = Vec::with_capacity(sp.n_random);
            for _ in 0..sp.n_random {
                let ra = lo_a + (rng.uniform() * (hi_a - lo_a + 1) as f64) as i64;
                if c.0 == c.1 {
                    let rb = ra + (c.3 - c.2);
                    if rb <= hi_a {
                        out.push((strat[i], g.count(ra, rb)));
                    }
                } else {
                    let rb = lo_b + (rng.uniform() * (hi_b - lo_b + 1) as f64) as i64;
                    out.push((-1, g.count(ra, rb)));
                }
            }
            out
        })
        .collect();
    let nmax = sp.nmax;
    let mut strata: Vec<i32> = strat.clone();
    strata.sort_unstable();
    strata.dedup();
    let mut lr = vec![1.0; n];
    let mut info = vec![];
    for s in strata {
        let mut pf = vec![0.1; nmax + 1];
        let mut nr = 0usize;
        for &(rs, k) in &rand {
            if rs == s {
                pf[(k as usize).min(nmax)] += 1.0;
                nr += 1;
            }
        }
        if nr < sp.min_random {
            continue;
        }
        let tot: f64 = pf.iter().sum();
        for x in pf.iter_mut() {
            *x /= tot;
        }
        let mut h = vec![0.0; nmax + 1];
        let mut cnt = 0usize;
        for i in 0..n {
            if strat[i] == s {
                h[(n_obs[i] as usize).min(nmax)] += 1.0;
                cnt += 1;
            }
        }
        let (eps, pt, mu, size) = fit_stratum(&h, &pf, nmax);
        for i in 0..n {
            if strat[i] == s {
                let k = (n_obs[i] as usize).min(nmax);
                lr[i] = (pt[k] / pf[k]).clamp(sp.lr_min, sp.lr_max);
            }
        }
        info.push((s, eps, cnt, mu, size));
    }
    Support { n: n_obs, lr, stratum: strat, strata: info }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn ln_gamma_matches_factorials() {
        let mut f = 1.0f64;
        for k in 1..20 {
            f *= k as f64;
            assert!((ln_gamma(k as f64 + 1.0) - f.ln()).abs() < 1e-10, "{k}");
        }
        assert!((ln_gamma(0.5) - std::f64::consts::PI.sqrt().ln()).abs() < 1e-12);
    }

    #[test]
    fn nb_pmf_sums_to_one_and_has_the_mean() {
        let v = nb_pmf(3.0, 2.0, 200);
        let s: f64 = v.iter().sum();
        let m: f64 = v.iter().enumerate().map(|(k, x)| k as f64 * x).sum();
        assert!((s - 1.0).abs() < 1e-6 && (m - 3.0).abs() < 1e-3, "{s} {m}");
    }

    #[test]
    fn clustered_contacts_beat_uniform_noise() {
        // one chromosome of 50 Mb: 2000 clustered "true" contacts (around 40 hot spots) + 500 uniform
        let mut r = Rng::new(1);
        let (mut a, mut b, mut truth) = (vec![], vec![], vec![]);
        let spots: Vec<(f64, f64)> = (0..40)
            .map(|_| {
                let x = r.uniform() * 4.5e7;
                (x, x + r.uniform() * 4e6)
            })
            .collect();
        for k in 0..2500 {
            let (x, y, t) = if k < 2000 {
                let (sx, sy) = spots[k % 40];
                (sx + r.normal() * 1e5, sy + r.normal() * 1e5, true)
            } else {
                let x = r.uniform() * 5e7;
                (x, r.uniform() * 5e7, false)
            };
            a.push(x.max(0.0) as i64);
            b.push(y.max(0.0) as i64);
            truth.push(t);
        }
        let c = vec![0u32; a.len()];
        let sp = SupportParams { window: 2e5, ..Default::default() };
        let s = support_evidence(&c, &a, &c, &b, &sp);
        let mean = |f: bool| -> f64 {
            let v: Vec<f64> = s.lr.iter().zip(&truth).filter(|(_, &t)| t == f).map(|(x, _)| x.ln()).collect();
            v.iter().sum::<f64>() / v.len() as f64
        };
        assert!(mean(true) > 1.0 && mean(false) < -1.0, "log LR true {} false {}", mean(true), mean(false));
    }
}
