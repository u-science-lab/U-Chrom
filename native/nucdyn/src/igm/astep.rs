//! A-step (assignment) of IGM on the CPU: the activation-distance rule of
//! `ActivationDistanceStep.get_actdist` (spec §4.2), re-implemented from the
//! specification.
//!
//! For every candidate haploid pair (i, j) with input probability f ≥ σ
//! (intra / inter threshold):
//!
//! 1. copy combinations: intra `(ii[k], jj[k])` for the copies present in
//!    both lists (`n_possible = min(len ii, len jj)`, 2 for diploid), inter
//!    all `len ii · len jj` combinations (4 for diploid);
//! 2. squared centre distances of every combination in every structure
//!    (`n_possible · S` values); `p_now = #(d² ≤ r_c²) / (n_possible S)` with
//!    `r_c = contact_range (r_i + r_j)` (radii of the first copies);
//! 3. `t = clean(p_now, p_last)`, `p = clean(f, t)`,
//!    `clean(a, b) = max(0, (a − b)/(1 − b))` if b < 1 else a;
//! 4. if p > 0: `o = min(nS − 1, round(n p S))` (Python's round-half-even),
//!    `d_act² = sorted(d²)[o]`, one row per combination.
//!
//! Opt-in variants (`AStepOpts`; the defaults are the rule above):
//!
//! * `iterative_correction = false` (IGM-Plus `iter_corr_knob = 0`): step 3
//!   becomes `p = f`;
//! * `gp_pooling` (G. Polles' approximation, alberlab/IGM_2.0
//!   `GP_ActivationDistanceStep.get_actdist`): every pair, intra or inter,
//!   takes all `len ii · len jj` copy combinations; per structure only the
//!   `n_possible = min(len ii, len jj)` smallest squared distances enter
//!   `p_now` and the rank selection (`n_possible · S` values).  The rows
//!   (which combinations get a restraint) are those of the IGM rule.
//!
//! Assignment (`intraHiC._apply` / `interHiC._apply`): a structure receives
//! the bond of a row iff its current `d² ≤ d_act²` (IGM compares
//! `d ≤ sqrt(d_act²)`; the square form avoids a rounding difference).

use crate::igm::forces::V3;
use crate::igm::genome::Genome;
use rayon::prelude::*;

/// All pairs of the input matrix that can ever be restrained (f > 0, i < j).
#[derive(Clone, Debug, Default)]
pub struct Candidates {
    pub i: Vec<u32>,
    pub j: Vec<u32>,
    pub f: Vec<f64>,
    pub intra: Vec<bool>,
    /// cleaned p of the latest A-step that saw the pair (0 = none)
    pub p_last: Vec<f64>,
}

impl Candidates {
    /// From an upper-triangular (or symmetric) COO matrix of haploid indices;
    /// the diagonal and duplicate entries are dropped (first kept).
    pub fn from_coo(g: &Genome, pi: &[u32], pj: &[u32], pv: &[f64], min_f: f64) -> Candidates {
        let mut v: Vec<(u32, u32, f64)> = pi
            .iter()
            .zip(pj)
            .zip(pv)
            .filter(|((&i, &j), &f)| i != j && f > 0.0 && f >= min_f)
            .map(|((&i, &j), &f)| (i.min(j), i.max(j), f))
            .collect();
        v.sort_by(|a, b| (a.0, a.1).cmp(&(b.0, b.1)));
        v.dedup_by(|b, a| a.0 == b.0 && a.1 == b.1);
        let mut c = Candidates::default();
        for (i, j, f) in v {
            c.i.push(i);
            c.j.push(j);
            c.f.push(f);
            c.intra.push(g.hap_chrom[i as usize] == g.hap_chrom[j as usize]);
            c.p_last.push(0.0);
        }
        c
    }

    pub fn len(&self) -> usize {
        self.i.len()
    }

    pub fn is_empty(&self) -> bool {
        self.i.is_empty()
    }

    /// Indices of the candidates active at (intra σ, inter σ).
    pub fn select(&self, intra_sigma: f64, inter_sigma: f64) -> Vec<u32> {
        (0..self.len())
            .filter(|&k| self.f[k] >= if self.intra[k] { intra_sigma } else { inter_sigma })
            .map(|k| k as u32)
            .collect()
    }
}

/// Copy combinations of a haploid pair and `n_possible`.
pub fn combos(g: &Genome, i: u32, j: u32, intra: bool) -> Vec<[u32; 2]> {
    let (ii, jj) = (&g.copy_index[i as usize], &g.copy_index[j as usize]);
    if intra {
        ii.iter().zip(jj.iter()).map(|(&a, &b)| [a, b]).collect()
    } else {
        ii.iter().flat_map(|&a| jj.iter().map(move |&b| [a, b])).collect()
    }
}

#[inline]
pub fn clean(a: f64, b: f64) -> f64 {
    if b < 1.0 {
        ((a - b) / (1.0 - b)).max(0.0)
    } else {
        a
    }
}

/// Python 3 `round` (half to even), for non-negative arguments.
#[inline]
pub fn round_half_even(x: f64) -> f64 {
    let r = x.round();
    if (x - x.trunc()).abs() == 0.5 {
        2.0 * (x / 2.0).round()
    } else {
        r
    }
}

/// Result of the A-step for one candidate pair.
#[derive(Clone, Copy, Debug, Default, PartialEq)]
pub struct PairResult {
    pub p_now: f64,
    pub p: f64,
    /// rank selected (valid when p > 0)
    pub rank: u64,
    /// squared activation distance (valid when p > 0)
    pub d2_act: f64,
}

/// Options of the A-step (defaults: IGM 1.0).
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct AStepOpts {
    pub iterative_correction: bool,
    pub gp_pooling: bool,
}

impl Default for AStepOpts {
    fn default() -> Self {
        AStepOpts { iterative_correction: true, gp_pooling: false }
    }
}

impl AStepOpts {
    pub fn from_params(p: &crate::igm::params::IgmParams) -> AStepOpts {
        AStepOpts { iterative_correction: p.iterative_correction, gp_pooling: p.gp_pooling() }
    }
}

/// Copy combinations entering `p_now` / the rank selection, and `n_possible`
/// per structure (IGM: the row combinations, all of them; GP: all copy
/// combinations, the `min(copies)` smallest per structure).
pub fn pool_combos(g: &Genome, i: u32, j: u32, intra: bool, gp: bool) -> (Vec<[u32; 2]>, usize) {
    if gp {
        let (ii, jj) = (&g.copy_index[i as usize], &g.copy_index[j as usize]);
        (combos(g, i, j, false), ii.len().min(jj.len()))
    } else {
        let cb = combos(g, i, j, intra);
        let n = cb.len();
        (cb, n)
    }
}

/// `p` and the rank `o` from the in-contact count (shared by CPU and GPU paths).
pub fn p_and_rank(f: f64, p_last: f64, n_in: u64, n_total: u64) -> (f64, f64, Option<u64>) {
    p_and_rank_opt(f, p_last, n_in, n_total, true)
}

/// As [`p_and_rank`]; `iterative_correction = false` uses `p = f`.
pub fn p_and_rank_opt(f: f64, p_last: f64, n_in: u64, n_total: u64, iterative_correction: bool) -> (f64, f64, Option<u64>) {
    let p_now = n_in as f64 / n_total as f64;
    let p = if iterative_correction { clean(f, clean(p_now, p_last)) } else { f };
    if p > 0.0 {
        let o = round_half_even(n_total as f64 * p).min((n_total - 1) as f64) as u64;
        (p_now, p, Some(o))
    } else {
        (p_now, p, None)
    }
}

#[inline]
fn d2(a: &V3, b: &V3) -> f64 {
    (a[0] - b[0]).powi(2) + (a[1] - b[1]).powi(2) + (a[2] - b[2]).powi(2)
}

/// Activation distances of the selected candidates over the population.
pub fn actdist(g: &Genome, cand: &Candidates, sel: &[u32], pop: &[Vec<V3>], contact_range: f64) -> Vec<PairResult> {
    actdist_opt(g, cand, sel, pop, contact_range, AStepOpts::default())
}

/// As [`actdist`] with the opt-in A-step variants.
pub fn actdist_opt(g: &Genome, cand: &Candidates, sel: &[u32], pop: &[Vec<V3>], contact_range: f64, opts: AStepOpts) -> Vec<PairResult> {
    let s = pop.len();
    sel.par_iter()
        .map(|&k| {
            let k = k as usize;
            let (i, j) = (cand.i[k], cand.j[k]);
            let (cb, np) = pool_combos(g, i, j, cand.intra[k], opts.gp_pooling);
            let b0 = &cb[0];
            let rc = contact_range * (g.radii[b0[0] as usize] + g.radii[b0[1] as usize]);
            let rc2 = rc * rc;
            let mut ds = Vec::with_capacity(np * s);
            if opts.gp_pooling {
                let mut tmp = Vec::with_capacity(cb.len());
                for st in pop {
                    tmp.clear();
                    tmp.extend(cb.iter().map(|c| d2(&st[c[0] as usize], &st[c[1] as usize])));
                    tmp.sort_by(|a, b| a.total_cmp(b));
                    ds.extend_from_slice(&tmp[..np]);
                }
            } else {
                for c in &cb {
                    for st in pop {
                        ds.push(d2(&st[c[0] as usize], &st[c[1] as usize]));
                    }
                }
            }
            let n_in = ds.iter().filter(|&&x| x <= rc2).count() as u64;
            let (p_now, p, o) = p_and_rank_opt(cand.f[k], cand.p_last[k], n_in, ds.len() as u64, opts.iterative_correction);
            match o {
                Some(o) => {
                    let (_, v, _) = ds.select_nth_unstable_by(o as usize, |a, b| a.total_cmp(b));
                    PairResult { p_now, p, rank: o, d2_act: *v }
                }
                None => PairResult { p_now, p, rank: 0, d2_act: -1.0 },
            }
        })
        .collect()
}

/// Rows `(bead_a, bead_b, d_act²)` of the pairs with p > 0.
pub fn rows(g: &Genome, cand: &Candidates, sel: &[u32], res: &[PairResult]) -> Vec<(u32, u32, f64)> {
    let mut out = vec![];
    for (&k, r) in sel.iter().zip(res) {
        if r.p > 0.0 {
            let k = k as usize;
            for c in combos(g, cand.i[k], cand.j[k], cand.intra[k]) {
                out.push((c[0], c[1], r.d2_act));
            }
        }
    }
    out
}

/// Per-structure assignment: the bonds of structure `pos`.
pub fn assign(rows: &[(u32, u32, f64)], pos: &[V3]) -> Vec<[u32; 2]> {
    rows.iter().filter(|r| d2(&pos[r.0 as usize], &pos[r.1 as usize]) <= r.2).map(|r| [r.0, r.1]).collect()
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::igm::params::IgmParams;

    #[test]
    fn clean_and_round() {
        assert_eq!(clean(0.3, 0.0), 0.3);
        assert!((clean(0.5, 0.2) - 0.375).abs() < 1e-15);
        assert_eq!(clean(0.1, 0.2), 0.0);
        assert_eq!(clean(0.4, 1.0), 0.4);
        assert_eq!(round_half_even(2.5), 2.0);
        assert_eq!(round_half_even(3.5), 4.0);
        assert_eq!(round_half_even(3.4999), 3.0);
        assert_eq!(round_half_even(0.5), 0.0);
    }

    /// Hand-computed toy: one intra pair, S = 4 structures.
    #[test]
    fn hand_computed_actdist() {
        let p = IgmParams { occupancy: 0.2, nucleus_radius: 1000.0, ..Default::default() };
        // chr0: bins 0, 1; chr1: bin 2; diploid
        let g = Genome::new(&[0, 0, 1], &[0, 100, 0], &[100, 200, 100], &[2, 2], &p).unwrap();
        // beads: copy0: 0 (h0), 1 (h1), 2 (h2); copy1: 3 (h0), 4 (h1), 5 (h2)
        assert_eq!(g.copy_index[0], vec![0, 3]);
        let r = g.radii[0];
        let rc = 2.0 * (2.0 * r);
        // population of 4 structures; place beads along x; distances chosen explicitly
        // intra pair (h0, h1): copy-0 distance d_a, copy-1 distance d_b
        let mk = |d_a: f64, d_b: f64| {
            let mut pos = vec![[0.0; 3]; 6];
            pos[1] = [d_a, 0.0, 0.0];
            pos[3] = [0.0, 1e5, 0.0];
            pos[4] = [d_b, 1e5, 0.0];
            pos
        };
        let dists = [(0.5 * rc, 3.0 * rc), (2.0 * rc, 0.9 * rc), (1.5 * rc, 4.0 * rc), (5.0 * rc, 1.2 * rc)];
        let pop: Vec<Vec<V3>> = dists.iter().map(|&(a, b)| mk(a, b)).collect();
        let mut cand = Candidates { i: vec![0], j: vec![1], f: vec![0.5], intra: vec![true], p_last: vec![0.0] };
        // 8 values: 0.5, 3, 2, 0.9, 1.5, 4, 5, 1.2 (× rc); in contact (≤ rc): 0.5, 0.9 -> p_now = 2/8
        // t = clean(0.25, 0) = 0.25; p = clean(0.5, 0.25) = 1/3; o = round(8/3) = 3
        // sorted: 0.5 0.9 1.2 1.5 2 3 4 5 -> d_act = 1.5 rc
        let res = actdist(&g, &cand, &[0], &pop, 2.0);
        assert!((res[0].p_now - 0.25).abs() < 1e-15);
        assert!((res[0].p - 1.0 / 3.0).abs() < 1e-15);
        assert_eq!(res[0].rank, 3);
        assert!((res[0].d2_act.sqrt() / rc - 1.5).abs() < 1e-12);
        let rw = rows(&g, &cand, &[0], &res);
        assert_eq!(rw.len(), 2);
        // structure 0: copy0 0.5 ≤ 1.5 yes, copy1 3 no; structure 2: copy0 1.5 yes (equal), copy1 4 no;
        // structure 1: 2 no, 0.9 yes; structure 3: 5 no, 1.2 yes
        let n: Vec<usize> = pop.iter().map(|x| assign(&rw, x).len()).collect();
        assert_eq!(n, vec![1, 1, 1, 1]);
        // with p_last = 1/3 (previous round), t = clean(0.25, 1/3) = 0 -> p = 0.5 -> o = 4 -> 2 rc
        cand.p_last[0] = 1.0 / 3.0;
        let res = actdist(&g, &cand, &[0], &pop, 2.0);
        assert!((res[0].p - 0.5).abs() < 1e-15);
        assert_eq!(res[0].rank, 4);
        assert!((res[0].d2_act.sqrt() / rc - 2.0).abs() < 1e-12);
        // f below the current contact frequency -> no restraint
        cand.p_last[0] = 0.0;
        cand.f[0] = 0.2;
        let res = actdist(&g, &cand, &[0], &pop, 2.0);
        assert_eq!(res[0].p, 0.0);
        assert!(rows(&g, &cand, &[0], &res).is_empty());
    }

    /// Hand-computed GP pooling and the iterative-correction switch.
    #[test]
    fn gp_pooling_and_no_iterative_correction() {
        let p = IgmParams { occupancy: 0.2, nucleus_radius: 1000.0, ..Default::default() };
        let g = Genome::new(&[0, 0, 1], &[0, 100, 0], &[100, 200, 100], &[2, 2], &p).unwrap();
        let r = g.radii[0];
        let rc = 2.0 * (2.0 * r);
        // beads: copy0 h0=0 h1=1 h2=2; copy1 h0=3 h1=4 h2=5.  Intra pair (h0, h1) has the
        // four combinations (0,1) (0,4) (3,1) (3,4); on the x axis: 0 at 0, 3 at `far`,
        // 1 at a, 4 at b -> d(0,1) = a, d(0,4) = b, d(3,1) = far - a, d(3,4) = far - b
        let far = 100.0 * rc;
        let mk = |a: f64, b: f64| {
            let mut pos = vec![[0.0, 5e5, 0.0]; 6];
            pos[0] = [0.0, 0.0, 0.0];
            pos[3] = [far, 0.0, 0.0];
            pos[1] = [a, 0.0, 0.0];
            pos[4] = [b, 0.0, 0.0];
            pos
        };
        // structure 0: d = 0.5, 100 - 0.8, 100 - 0.5, 0.8 (x rc): GP keeps {0.5, 0.8}, IGM (same copy) {0.5, 0.8}
        // structure 1: d = 3, 2, 97, 98: GP keeps {2, 3}, IGM {3, 98}
        let pop = vec![mk(0.5 * rc, far - 0.8 * rc), mk(3.0 * rc, 2.0 * rc)];
        let cand = Candidates { i: vec![0], j: vec![1], f: vec![0.9], intra: vec![true], p_last: vec![0.2] };
        let gp = AStepOpts { iterative_correction: true, gp_pooling: true };
        let res = actdist_opt(&g, &cand, &[0], &pop, 2.0, gp);
        // GP values 0.5 0.8 2 3: p_now = 2/4; t = clean(0.5, 0.2) = 0.375; p = clean(0.9, 0.375) = 0.84;
        // o = round(4 * 0.84) = 3 -> d_act = 3 rc
        assert!((res[0].p_now - 0.5).abs() < 1e-15);
        assert!((res[0].p - 0.84).abs() < 1e-12, "{}", res[0].p);
        assert_eq!(res[0].rank, 3);
        assert!((res[0].d2_act.sqrt() / rc - 3.0).abs() < 1e-9);
        // IGM values 0.5 0.8 3 98: p_now = 2/4 as well, rank 3 -> 98 rc
        let igm = actdist_opt(&g, &cand, &[0], &pop, 2.0, AStepOpts::default());
        assert_eq!(igm[0].rank, 3);
        assert!((igm[0].d2_act.sqrt() / rc - 98.0).abs() < 1e-9);
        assert_eq!(igm, actdist(&g, &cand, &[0], &pop, 2.0));
        // the rows are the IGM rows (same-copy combinations for intra) in both modes
        assert_eq!(rows(&g, &cand, &[0], &res).len(), 2);
        // no iterative correction: p = f (o = min(3, round(3.6)) = 3)
        let noic = AStepOpts { iterative_correction: false, gp_pooling: false };
        let res = actdist_opt(&g, &cand, &[0], &pop, 2.0, noic);
        assert_eq!(res[0].p, 0.9);
        assert_eq!(res[0].rank, 3);
        // f below p_now is still restrained without the correction (o = round(0.4) = 0)
        let cand2 = Candidates { f: vec![0.1], ..cand.clone() };
        let res = actdist_opt(&g, &cand2, &[0], &pop, 2.0, noic);
        assert_eq!(res[0].p, 0.1);
        assert_eq!(res[0].rank, 0);
        // inter pair, diploid: GP pools 2 of 4 per structure, IGM all 4; intra IGM 2
        assert_eq!(pool_combos(&g, 0, 2, false, true).1, 2);
        assert_eq!(pool_combos(&g, 0, 2, false, true).0.len(), 4);
        assert_eq!(pool_combos(&g, 0, 2, false, false).1, 4);
        assert_eq!(pool_combos(&g, 0, 1, true, false).1, 2);
        assert_eq!(pool_combos(&g, 0, 1, true, true).0.len(), 4);
    }

    #[test]
    fn inter_uses_four_combinations() {
        let p = IgmParams::default();
        let g = Genome::new(&[0, 1], &[0, 0], &[100, 100], &[2, 2], &p).unwrap();
        assert_eq!(combos(&g, 0, 1, false).len(), 4);
        assert_eq!(combos(&g, 0, 1, true).len(), 2);
        let g = Genome::new(&[0, 1], &[0, 0], &[100, 100], &[2, 1], &p).unwrap();
        assert_eq!(combos(&g, 0, 1, false).len(), 2);
        let cand = Candidates::from_coo(&g, &[0, 1, 0, 0], &[1, 0, 0, 1], &[0.3, 0.3, 1.0, 0.5], 0.0);
        assert_eq!(cand.len(), 1);
        assert!(!cand.intra[0]);
    }
}
