//! Diploid (homolog-resolved, partially phased) single-cell structures, for the 2017
//! protocol (`nuc_dynamics_2017`) and EMber (`robust`).
//!
//! Input: every contact end carries a haplotype — 0, 1 or unknown — as written by hickit /
//! Dip-C (`.pairs` `phase0` / `phase1`, Dip-C `.con`); each chromosome has one or two copies
//! (`ploidy`: e.g. 1 for chrX / chrY of a male).
//!
//! Particles: one chain per chromosome copy (copy id `2 c + h`), both copies of a
//! chromosome on the same particle grid (the haploid grid of the chromosome, from the
//! contacts of both homologs).  Same schedule, start coordinates, backbone, repulsion and
//! annealing as the haploid protocols.
//!
//! Candidate copy pairs of a contact: a phased end is on its homolog, an unphased end on
//! either copy (single-copy chromosomes: the one copy), so a contact has 1, 2 or 4
//! candidates.  Unphased ends of an intra-chromosomal contact closer than
//! `diploid_cis_sep` (10 Mb) are put on the same homolog (hickit's imputation prior
//! `spacial_adj` gives P(same homolog) >= 0.99 there; Dip-C `impute3 -s` likewise only
//! imputes inter-homolog for distant pairs), so such a contact keeps the same-homolog
//! combinations only.
//!
//! Restraints: contacts are binned per stage like the 2017 protocol, by their *set* of
//! candidate particle pairs; a bin of N contacts gets the 2017 bounds of N^-0.33.
//!
//! * `nuc_dynamics_2017`: a bin with more than one candidate is one ambiguous restraint —
//!   the combined distance (Σ d⁻⁴)^(−1/4) of the candidates must lie within the bounds, the
//!   ambiguity-group force of the original `dyn_util.pyx` (`getRestraintForce` with
//!   `restAmbig` strides; NucProcess writes homolog ambiguity as groups of NCC contacts on
//!   `chrN.a` / `chrN.b`, tjs23/nuc_dynamics release_1.3 `homologous_pair`).
//! * `robust` (EMber): the mixture observation model of `robust.rs` with the copy pair as a
//!   latent variable.  A true contact lands on candidate pair c with probability
//!   π_c f(d_c) / G (π: prior over the candidates, uniform unless given), a false one
//!   uniformly on any pair, so
//!
//!   ```text
//!   P(true, c | structure) = o π_c (1 - ε) φ_c / [ o (1 - ε) Σ_c' π_c' φ_c' + ε / N_pairs ]
//!   ```
//!
//!   (o: the contact's prior odds, φ = f(d) / G).  From the first re-weighted stage on, the
//!   candidates of a bin stay one ambiguous restraint (combined distance, as the 2017 protocol)
//!   weighted by P(true) = Σ_c P(true, c) combined over its contacts (default); with
//!   `robust_dip_split` every candidate is its own restraint with weight
//!   1 − Π_contacts (1 − P(true, c)) — the literal soft M-step, which on the development set
//!   pulls both homologs of an uncertain contact together and loses accuracy; ε and the kernel width are fitted as in `robust.rs` with the marginal
//!   likelihood Σ_c π_c φ_c.  Phasing is thereby inferred from the structure: the soft
//!   counterpart of Dip-C's `impute3` (which assigns a contact to the candidate whose 3-D
//!   distance is < 0.5 x the second best) and of IGM's A-step (which assigns ambiguous
//!   copy pairs by the current distances).  Before the first re-weighted stage the
//!   restraints are the ambiguous ones of the 2017 protocol.
//!
//! Filters on the base (copy-agnostic) contacts: the isolated-contact filter of the 2017
//! protocol (genomic positions only); removal of violated contacts (stages < 0.5 Mb): a
//! contact is kept when its closest candidate (model-mean distance) is < 6 radii.
//!
//! Output: copy chains in copy-id order; per input contact the probability of each
//! (hap_a, hap_b) given that the contact is true — EM posteriors of the last update
//! (EMber) or the closest candidate of the final structure (2017) — and, for EMber, the
//! probability that the contact is true.

use crate::contacts::{contact_count, Contact, ContactDict, Structure};
use crate::dynamics::{NoContact, RestraintForm, System, V3};
use crate::params::{anneal_schedule, Params};
use crate::pipeline::{Input, Output, StageEngine, StageLog};
use crate::protocol2017::{
    backbone_restraints, calc_particles, interpolate, remove_isolated_contacts, start_coords,
};
use crate::restraints::{Restraint, RestraintSet};
use crate::robust::{
    expand_to_grid, force_constant, kernel_sum, merge_empty_particles, merged_backbone_restraints, set_weights,
    split_schedule, EmData, EmLog, Kernel,
};
use crate::support::{support_evidence, SupportParams};
use rayon::prelude::*;
use std::collections::BTreeMap;
use std::time::Instant;

/// Phasing of the input contacts.
#[derive(Clone, Copy, Debug)]
pub struct DiploidInput<'a> {
    /// Haplotype of each contact end: 0, 1 or -1 (unknown).
    pub hap_a: &'a [i8],
    pub hap_b: &'a [i8],
    /// Copies of each chromosome (index = chromosome id of `Input::names`): 1 or 2.
    pub ploidy: &'a [u8],
    /// Optional prior over the copy pair of each contact (e.g. hickit's imputed
    /// `phase_prob00..11`): 4 values per contact, index 2 hap_a + hap_b, input orientation;
    /// renormalised over the candidates (all zero: uniform).
    pub prior: Option<&'a [f64]>,
}

/// Copy id of haplotype `h` of chromosome `c`.
#[inline]
pub fn copy_id(c: u32, h: u8) -> u32 {
    2 * c + h as u32
}

/// One contact in canonical orientation ((chrom, pos) of end a <= end b) with its candidate
/// copy pairs.
#[derive(Clone, Debug)]
pub struct DipContact {
    pub ca: u32,
    pub pa: i64,
    pub cb: u32,
    pub pb: i64,
    /// input row
    pub row: u32,
    /// ends swapped relative to the input
    pub swapped: bool,
    pub n_cand: u8,
    /// candidate (hap_a, hap_b) codes 2 h_a + h_b (canonical orientation)
    pub cand: [u8; 4],
    /// prior of each candidate (sums to 1)
    pub prior: [f64; 4],
}

impl DipContact {
    pub fn ambiguous(&self) -> bool {
        self.n_cand > 1
    }
}

/// Candidate copy pairs of every input contact.
pub fn prepare_contacts(input: &Input, dip: &DiploidInput, cis_sep: i64) -> Result<Vec<DipContact>, String> {
    let n = input.chr_a.len();
    if dip.hap_a.len() != n || dip.hap_b.len() != n {
        return Err("hap_a / hap_b: one value per contact".into());
    }
    if dip.ploidy.len() != input.names.len() {
        return Err("ploidy: one value per chromosome name".into());
    }
    if dip.ploidy.iter().any(|&k| k != 1 && k != 2) {
        return Err("ploidy must be 1 or 2".into());
    }
    if let Some(pr) = dip.prior {
        if pr.len() != 4 * n || pr.iter().any(|x| !(*x >= 0.0)) {
            return Err("phase prior: 4 non-negative values per contact".into());
        }
    }
    let mut out = Vec::with_capacity(n);
    for i in 0..n {
        let (mut ca, mut pa, mut ha, mut cb, mut pb, mut hb) =
            (input.chr_a[i], input.pos_a[i], dip.hap_a[i], input.chr_b[i], input.pos_b[i], dip.hap_b[i]);
        if ha > 1 || hb > 1 || ha < -1 || hb < -1 {
            return Err(format!("contact {i}: haplotype must be 0, 1 or -1"));
        }
        let swapped = (ca, pa) > (cb, pb);
        if swapped {
            std::mem::swap(&mut ca, &mut cb);
            std::mem::swap(&mut pa, &mut pb);
            std::mem::swap(&mut ha, &mut hb);
        }
        let haps = |c: u32, h: i8| -> Vec<u8> {
            if dip.ploidy[c as usize] == 1 {
                vec![0]
            } else if h >= 0 {
                vec![h as u8]
            } else {
                vec![0, 1]
            }
        };
        let (sa, sb) = (haps(ca, ha), haps(cb, hb));
        let mut cand: Vec<u8> = sa.iter().flat_map(|&x| sb.iter().map(move |&y| 2 * x + y)).collect();
        if ca == cb && dip.ploidy[ca as usize] == 2 && cis_sep > 0 && (pb - pa).abs() < cis_sep {
            let same: Vec<u8> = cand.iter().copied().filter(|&c| c >> 1 == c & 1).collect();
            if !same.is_empty() {
                cand = same;
            }
        }
        let mut prior = [0.0; 4];
        let mut tot = 0.0;
        if let Some(pr) = dip.prior {
            for (k, &c) in cand.iter().enumerate() {
                // input orientation of code c
                let (x, y) = (c >> 1, c & 1);
                let ci = if swapped { 2 * y + x } else { 2 * x + y };
                prior[k] = pr[4 * i + ci as usize];
                tot += prior[k];
            }
        }
        if tot > 0.0 {
            for v in prior.iter_mut().take(cand.len()) {
                *v /= tot;
            }
        } else {
            for v in prior.iter_mut().take(cand.len()) {
                *v = 1.0 / cand.len() as f64;
            }
        }
        let mut c4 = [0u8; 4];
        c4[..cand.len()].copy_from_slice(&cand);
        out.push(DipContact { ca, pa, cb, pb, row: i as u32, swapped, n_cand: cand.len() as u8, cand: c4, prior });
    }
    Ok(out)
}

/// Settings of the 2-D neighbourhood phase prior (hickit 0.1.1 `hk_impute` defaults:
/// `phase.c`, `main.c`).
#[derive(Clone, Copy, Debug)]
pub struct NbrPrior {
    /// neighbourhood radius (bp, Chebyshev distance of the two ends; hickit `-r`, 10 Mb)
    pub max_radius: i64,
    /// minimum distance scale of the weights (bp; hickit `imput_min_radius`, 50 kb)
    pub min_radius: i64,
    /// neighbours per contact (hickit `imput_max_nei`, 50)
    pub max_nei: usize,
    /// pseudo-count (hickit `imput_pseudo_cnt`, 0.4)
    pub pseudo: f64,
    /// iterations (hickit runs `-n` = 1000; here at most this many, stopped earlier when no
    /// probability moves by more than 1e-5)
    pub max_iter: usize,
}

impl Default for NbrPrior {
    fn default() -> Self {
        NbrPrior { max_radius: 10_000_000, min_radius: 50_000, max_nei: 50, pseudo: 0.4, max_iter: 200 }
    }
}

/// hickit `spacial_adj`: an intra-chromosomal contact at separation d has P(same homolog) of
/// at least min(0.99, 1e7 / d).
fn spatial_adj(c: &DipContact, p: &mut [f64; 4]) {
    if c.ca != c.cb {
        return;
    }
    let same = p[0] + p[3];
    let diff = p[1] + p[2];
    if same + 1.0 == 1.0 || diff + 1.0 == 1.0 {
        return;
    }
    let d = (c.pb - c.pa).abs();
    let mut r = if d > 0 { 1e7 / d as f64 } else { 1.0 };
    if r < same {
        return;
    }
    if r > 0.99 {
        r = 0.99;
    }
    *p = [r * p[0] / same, (1.0 - r) * p[1] / diff, (1.0 - r) * p[2] / diff, r * p[3] / same];
}

/// 2-D neighbourhood phase prior (the imputation of hickit `hk_impute`, re-implemented): every
/// contact gets a distribution over its candidate copy pairs from the distributions of its
/// `max_nei` nearest contacts of the same chromosome pair (both ends within `max_radius`,
/// Chebyshev distance d), weighted 1 / (d / r + 0.001) with r the contact's own span (trans:
/// `max_radius`; at least `min_radius`), plus a pseudo-count; phased ends stay fixed; iterated
/// (Jacobi) from uniform.  Returns the prior of every contact in its candidate order.
/// Differences from hickit: the nearest neighbours are taken per contact (hickit adds each
/// pair to both lists up to the per-contact cap), iterations stop at convergence, and the
/// same-homolog rule of `diploid_cis_sep` has already removed candidates.
pub fn neighbour_prior(contacts: &[DipContact], np: &NbrPrior) -> Vec<[f64; 4]> {
    let n = contacts.len();
    // group by chromosome pair, sorted by pos_a
    let mut order: Vec<usize> = (0..n).collect();
    order.sort_by_key(|&k| (contacts[k].ca, contacts[k].cb, contacts[k].pa, contacts[k].pb));
    let mut group_start = vec![0usize; n]; // position range of k's group in `order`
    let mut group_end = vec![0usize; n];
    let mut rank = vec![0usize; n];
    let mut s = 0;
    while s < n {
        let (ca, cb) = (contacts[order[s]].ca, contacts[order[s]].cb);
        let mut e = s;
        while e < n && contacts[order[e]].ca == ca && contacts[order[e]].cb == cb {
            e += 1;
        }
        for (q, &k) in order[s..e].iter().enumerate() {
            group_start[k] = s;
            group_end[k] = e;
            rank[k] = s + q;
        }
        s = e;
    }
    let pw = {
        // hickit hk_pseudo_weight: mean of 1 / (d / R + 1e-3) over d in [0, R)
        let m = 1000;
        let step = (np.max_radius / m as i64) as f64;
        (0..m).map(|i| 1.0 / ((i as f64 * step) / np.max_radius as f64 + 1e-3)).sum::<f64>() / m as f64
    };
    let coef = 1.0 / pw;
    // neighbours (index, weight) of every contact
    let nei: Vec<Vec<(u32, f64)>> = (0..n)
        .into_par_iter()
        .map(|k| {
            let c = &contacts[k];
            let mut best: Vec<(i64, u32)> = Vec::with_capacity(np.max_nei + 1);
            let worst = |b: &Vec<(i64, u32)>| b.iter().map(|x| x.0).max().unwrap_or(i64::MAX);
            let consider = |j: usize, best: &mut Vec<(i64, u32)>| -> bool {
                let o = &contacts[j];
                let y = (o.pa - c.pa).abs();
                if y > np.max_radius || (best.len() >= np.max_nei && y > worst(best)) {
                    return false; // further along this direction only gets worse
                }
                let z = (o.pb - c.pb).abs();
                if z <= np.max_radius {
                    let d = y.max(z);
                    if best.len() < np.max_nei {
                        best.push((d, j as u32));
                    } else if d < worst(best) {
                        let wi = (0..best.len()).max_by_key(|&i| best[i].0).unwrap();
                        best[wi] = (d, j as u32);
                    }
                }
                true
            };
            let r0 = rank[k];
            let mut q = r0;
            while q > group_start[k] {
                q -= 1;
                if !consider(order[q], &mut best) {
                    break;
                }
            }
            for &j in &order[r0 + 1..group_end[k]] {
                if !consider(j, &mut best) {
                    break;
                }
            }
            let span = if c.ca != c.cb { np.max_radius } else { (c.pb - c.pa).abs() }.max(np.min_radius) as f64;
            best.into_iter().map(|(d, j)| (j, coef / (d as f64 / span + 1e-3))).collect()
        })
        .collect();
    // start: uniform over the candidates (hickit: 0.25 / 0.5 / 1 by phased ends)
    let init = |c: &DipContact| -> [f64; 4] {
        let mut p = [0.0; 4];
        for &code in &c.cand[..c.n_cand as usize] {
            p[code as usize] = 1.0 / c.n_cand as f64;
        }
        p
    };
    let mut cur: Vec<[f64; 4]> = contacts
        .iter()
        .map(|c| {
            let mut p = init(c);
            spatial_adj(c, &mut p);
            p
        })
        .collect();
    for _ in 0..np.max_iter {
        let next: Vec<[f64; 4]> = (0..n)
            .into_par_iter()
            .map(|k| {
                let c = &contacts[k];
                if c.n_cand == 1 {
                    return cur[k];
                }
                let mut v = [0.25 * np.pseudo; 4];
                for &(j, w) in &nei[k] {
                    let pj = &cur[j as usize];
                    for x in 0..4 {
                        v[x] += w * pj[x];
                    }
                }
                let mut p = [0.0; 4];
                let tot: f64 = c.cand[..c.n_cand as usize].iter().map(|&code| v[code as usize]).sum();
                for &code in &c.cand[..c.n_cand as usize] {
                    p[code as usize] = v[code as usize] / tot;
                }
                spatial_adj(c, &mut p);
                p
            })
            .collect();
        let delta = next.iter().zip(&cur).map(|(a, b)| (0..4).map(|x| (a[x] - b[x]).abs()).fold(0.0, f64::max)).fold(0.0, f64::max);
        cur = next;
        if delta < 1e-5 {
            break;
        }
    }
    contacts
        .iter()
        .zip(&cur)
        .map(|(c, p)| {
            let mut out = [0.0; 4];
            let tot: f64 = c.cand[..c.n_cand as usize].iter().map(|&code| p[code as usize]).sum();
            for (i, &code) in c.cand[..c.n_cand as usize].iter().enumerate() {
                out[i] = if tot > 0.0 { p[code as usize] / tot } else { 1.0 / c.n_cand as f64 };
            }
            out
        })
        .collect()
}

/// The neighbourhood prior of every input contact as P(hap_a, hap_b) (4 values per contact,
/// index 2 hap_a + hap_b, input orientation) — for validation against hickit's imputation.
pub fn neighbour_phase_probs(input: &Input, dip: &DiploidInput, cis_sep: i64, np: &NbrPrior) -> Result<Vec<f64>, String> {
    let contacts = prepare_contacts(input, dip, cis_sep)?;
    let pr = neighbour_prior(&contacts, np);
    let mut out = vec![0.0; 4 * contacts.len()];
    for (c, q) in contacts.iter().zip(&pr) {
        for i in 0..c.n_cand as usize {
            out[4 * c.row as usize + input_code(c, c.cand[i])] = q[i];
        }
    }
    Ok(out)
}

/// hickit-like isolated-contact filter (`-r radius -c min_nei`): true for the contacts with at
/// least `min_nei` other contacts of the same chromosome pair whose ends are both within
/// `radius` (Chebyshev distance on genomic positions).  Scans stop at `min_nei`.
pub fn isolation_keep(contacts: &[DipContact], min_nei: u32, radius: i64) -> Vec<bool> {
    let n = contacts.len();
    let mut order: Vec<usize> = (0..n).collect();
    order.sort_by_key(|&k| (contacts[k].ca, contacts[k].cb, contacts[k].pa));
    let mut gstart = vec![0usize; n];
    let mut gend = vec![0usize; n];
    let mut s = 0;
    while s < n {
        let key = (contacts[order[s]].ca, contacts[order[s]].cb);
        let mut e = s;
        while e < n && (contacts[order[e]].ca, contacts[order[e]].cb) == key {
            e += 1;
        }
        for q in s..e {
            gstart[q] = s;
            gend[q] = e;
        }
        s = e;
    }
    let ok: Vec<bool> = (0..n)
        .into_par_iter()
        .map(|q| {
            let c = &contacts[order[q]];
            let mut cnt = 0u32;
            let mut j = q;
            while j > gstart[q] {
                j -= 1;
                let o = &contacts[order[j]];
                if c.pa - o.pa > radius {
                    break;
                }
                if (o.pb - c.pb).abs() <= radius {
                    cnt += 1;
                    if cnt >= min_nei {
                        return true;
                    }
                }
            }
            for &k in &order[q + 1..gend[q]] {
                let o = &contacts[k];
                if o.pa - c.pa > radius {
                    break;
                }
                if (o.pb - c.pb).abs() <= radius {
                    cnt += 1;
                    if cnt >= min_nei {
                        return true;
                    }
                }
            }
            cnt >= min_nei
        })
        .collect();
    let mut keep = vec![false; n];
    for (q, &k) in order.iter().enumerate() {
        keep[k] = ok[q];
    }
    keep
}

/// Hard phasing (`robust_dip_commit`): every kept ambiguous contact whose probability over its
/// candidates (`probs[k]`, candidate order; `None` = unknown) has its maximum >= `tau` becomes
/// unambiguous on that candidate; the other ambiguous contacts are dropped (`drop`) or stay
/// ambiguous.  Returns (committed, dropped).
pub fn commit_contacts(contacts: &mut [DipContact], keep: &mut [bool], probs: &[Option<[f64; 4]>], tau: f64, drop: bool) -> (usize, usize) {
    let (mut n_commit, mut n_drop) = (0, 0);
    for (k, c) in contacts.iter_mut().enumerate() {
        if !keep[k] || c.n_cand < 2 {
            continue;
        }
        let best = probs[k].map(|p| {
            (0..c.n_cand as usize).fold((0usize, f64::NEG_INFINITY), |a, i| if p[i] > a.1 { (i, p[i]) } else { a })
        });
        match best {
            Some((i, x)) if x >= tau => {
                c.cand = [c.cand[i], 0, 0, 0];
                c.prior = [1.0, 0.0, 0.0, 0.0];
                c.n_cand = 1;
                n_commit += 1;
            }
            _ if drop => {
                keep[k] = false;
                n_drop += 1;
            }
            _ => {}
        }
    }
    (n_commit, n_drop)
}

/// Base (copy-agnostic) contact dictionary of the kept contacts; `Contact::number` = index
/// into `contacts`.
pub(crate) fn base_dict(contacts: &[DipContact], keep: &[bool]) -> ContactDict {
    let mut d: ContactDict = BTreeMap::new();
    for (k, c) in contacts.iter().enumerate() {
        if keep[k] {
            d.entry((c.ca, c.cb)).or_default().push(Contact { pos_a: c.pa, pos_b: c.pb, ambig: 0, number: k as u32 });
        }
    }
    d
}

/// Candidate restraints of one stage: contacts binned by their set of candidate particle
/// pairs.
#[derive(Clone, Debug, Default)]
pub struct DipGroups {
    /// candidate particle pairs, grouped (`goff`)
    pub pairs: Vec<[u32; 2]>,
    /// candidate code (2 h_a + h_b, canonical orientation) of every candidate
    pub code: Vec<u8>,
    pub goff: Vec<u32>,
    /// restraint bounds of each group
    pub lim: Vec<[f64; 2]>,
    /// contacts of each group (`coff`): index into the contact list, and the prior of every
    /// candidate of the group (group order)
    pub coff: Vec<u32>,
    pub contacts: Vec<u32>,
    pub prior: Vec<[f64; 4]>,
    pub n_used: usize,
}

impl DipGroups {
    pub fn n_groups(&self) -> usize {
        self.goff.len().saturating_sub(1)
    }
    pub fn counts(&self) -> Vec<u32> {
        self.coff.windows(2).map(|w| w[1] - w[0]).collect()
    }
}

/// Bin the kept contacts on the particles of `st` (copy chains).  A contact end at p goes to
/// the first particle at or after p (2017 convention); ends beyond the last particle are
/// dropped.  Target distance count^power_law (float32 as the 2017 code), optionally capped.
pub fn dip_groups(contacts: &[DipContact], keep: &[bool], st: &Structure, p: &Params, count_cap: u32) -> DipGroups {
    let (exp32, lo32, hi32) = (p.dist_power_law as f32, p.contact_dist_lower as f32 as f64, p.contact_dist_upper as f32 as f64);
    // key: sorted (particle pair, code) of the candidates
    let mut bins: BTreeMap<Vec<(u32, u32, u8)>, Vec<u32>> = BTreeMap::new();
    let mut n_used = 0usize;
    for (k, c) in contacts.iter().enumerate() {
        if !keep[k] {
            continue;
        }
        let mut key = Vec::with_capacity(c.n_cand as usize);
        let mut ok = true;
        for &code in &c.cand[..c.n_cand as usize] {
            let (ia, ib) = (copy_id(c.ca, code >> 1), copy_id(c.cb, code & 1));
            let (Some(sa), Some(sb)) = (st.chrom_slot(ia), st.chrom_slot(ib)) else {
                ok = false;
                break;
            };
            let (spa, spb) = (&st.seq_pos[sa], &st.seq_pos[sb]);
            let j = spa.partition_point(|&x| x < c.pa as i32 as i64);
            let l = spb.partition_point(|&x| x < c.pb as i32 as i64);
            if j >= spa.len() || l >= spb.len() {
                ok = false;
                break;
            }
            key.push(((st.offsets[sa] + j) as u32, (st.offsets[sb] + l) as u32, code));
        }
        if !ok {
            continue;
        }
        key.sort_unstable();
        bins.entry(key).or_default().push(k as u32);
        n_used += 1;
    }
    let mut g = DipGroups { goff: vec![0], coff: vec![0], n_used, ..Default::default() };
    for (key, members) in bins {
        let cnt = if count_cap > 0 { (members.len() as u32).min(count_cap) } else { members.len() as u32 };
        let dist = (1.0f32 * (cnt as f32).powf(exp32)) as f64;
        g.lim.push([dist * lo32, dist * hi32]);
        for &(i, j, code) in &key {
            g.pairs.push([i, j]);
            g.code.push(code);
        }
        g.goff.push(g.pairs.len() as u32);
        for &m in &members {
            let c = &contacts[m as usize];
            let mut pr = [0.0; 4];
            for (q, &(_, _, code)) in key.iter().enumerate() {
                let k = c.cand[..c.n_cand as usize].iter().position(|&x| x == code).unwrap();
                pr[q] = c.prior[k];
            }
            g.contacts.push(m);
            g.prior.push(pr);
        }
        g.coff.push(g.contacts.len() as u32);
    }
    g
}

/// Restraint set: `backbone` then the candidates, as ambiguous groups (`split` false) or one
/// restraint per candidate (`split` true).
pub(crate) fn restraint_set(backbone: Vec<Restraint>, g: &DipGroups, split: bool) -> (RestraintSet, usize) {
    let nb = backbone.len();
    let mut rest = backbone;
    let mut groups: Vec<u32> = (0..nb as u32).collect();
    for gi in 0..g.n_groups() {
        let (s, e) = (g.goff[gi] as usize, g.goff[gi + 1] as usize);
        let [lo, hi] = g.lim[gi];
        if !split {
            groups.push(rest.len() as u32);
        }
        for k in s..e {
            if split {
                groups.push(rest.len() as u32);
            }
            rest.push(Restraint { i: g.pairs[k][0], j: g.pairs[k][1], lo, hi, ambig: 0, weight: 1.0 });
        }
    }
    groups.push(rest.len() as u32);
    (RestraintSet { rest, groups, n_contacts: g.n_used }, nb)
}

/// Per-candidate weights → one weight per ambiguous group (`robust_dip_split` false): the
/// group weight is P(true) of its contacts combined like `robust_count_combine`.
fn group_weights(g: &DipGroups, w_true: &[f64]) -> Vec<f64> {
    (0..g.n_groups()).map(|gi| w_true[gi]).collect()
}

/// Result of one diploid EM update.
pub struct DipEmResult {
    /// [row][candidate] restraint weight (one row unless per model)
    pub weights: Vec<Vec<f64>>,
    /// [row][group] weight of the group as one ambiguous restraint (P(true) combined)
    pub group_w: Vec<Vec<f64>>,
    /// per grouped contact: P(true) (mean over rows) and P(candidate | true) (group order)
    pub r_true: Vec<f64>,
    pub post: Vec<[f64; 4]>,
    pub eps: f64,
    pub s: f64,
    pub log: EmLog,
}

/// E-step + M-step of the diploid mixture on fixed distances.  `data.dist[m][k]`: distance of
/// candidate k (grouped order of `g.pairs`) in model m; `odds`: per grouped contact.
pub fn em_update_dip(data: &EmData, g: &DipGroups, odds: &[f64], k: &Kernel, p: &Params, eps0: f64, s0: f64) -> DipEmResult {
    let t0 = Instant::now();
    let u = 1.0 / data.n_pairs.max(1.0);
    let nm = data.dist.len();
    let ng = g.n_groups();
    let nc_tot = g.contacts.len().max(1) as f64;
    let phi_rows = |k: &Kernel, s: f64| -> (Vec<Vec<f64>>, Vec<f64>) {
        let gm: Vec<f64> = data.hist.iter().map(|h| kernel_sum(k, h, data.bin, data.n_pairs, s).max(1e-300)).collect();
        let phi: Vec<Vec<f64>> = data.dist.iter().zip(&gm).map(|(d, &x)| d.iter().map(|&y| k.f(y, s) / x).collect()).collect();
        let rows = if p.robust_per_model {
            phi
        } else {
            let mut mean = vec![0.0; g.pairs.len()];
            for row in &phi {
                for (a, b) in mean.iter_mut().zip(row) {
                    *a += b / nm as f64;
                }
            }
            vec![mean]
        };
        (rows, gm)
    };
    // Σ_c π_c φ_c of a contact (group gi, contact q) in `row`
    let mix = |row: &[f64], gi: usize, q: usize| -> f64 {
        let s = g.goff[gi] as usize;
        let n = g.goff[gi + 1] as usize - s;
        (0..n).map(|c| g.prior[q][c] * row[s + c]).sum()
    };
    let fit = |rows: &[Vec<f64>]| -> (f64, f64) {
        let mut eps = eps0;
        if p.robust_learn_eps {
            for _ in 0..200 {
                let mut fsum = 0.0;
                for row in rows {
                    for gi in 0..ng {
                        for q in g.coff[gi] as usize..g.coff[gi + 1] as usize {
                            let a = odds[q] * (1.0 - eps) * mix(row, gi, q);
                            fsum += if a <= 0.0 { 1.0 } else { eps * u / (a + eps * u) };
                        }
                    }
                }
                let new = (fsum / (nc_tot * rows.len() as f64)).clamp(p.robust_eps_min, p.robust_eps_max);
                let done = (new - eps).abs() < 1e-8;
                eps = new;
                if done {
                    break;
                }
            }
        }
        let mut ll = 0.0;
        for row in rows {
            for gi in 0..ng {
                for q in g.coff[gi] as usize..g.coff[gi + 1] as usize {
                    let o = odds[q];
                    let rho = o * (1.0 - eps) / (o * (1.0 - eps) + eps);
                    ll += ((rho * mix(row, gi, q) + (1.0 - rho) * u) / u).ln();
                }
            }
        }
        (ll / (nc_tot * rows.len() as f64), eps)
    };
    let grid: Vec<f64> = if p.robust_learn_s { p.robust_s_grid.clone() } else { vec![s0] };
    let d0s: Vec<f64> = if p.robust_d0_grid.is_empty() { vec![k.d0] } else { p.robust_d0_grid.clone() };
    let mut best: Option<(f64, f64, f64, f64)> = None;
    for (&s, &d0) in grid.iter().flat_map(|s| d0s.iter().map(move |d| (s, d))) {
        let kk = Kernel { d0, ..*k };
        let (rows, _) = phi_rows(&kk, s);
        let (ll, eps) = fit(&rows);
        if best.is_none_or(|b| ll > b.0) {
            best = Some((ll, s, eps, d0));
        }
    }
    let (ll, s, eps, d0) = best.unwrap();
    let kk = Kernel { d0, ..*k };
    let (rows, gm) = phi_rows(&kk, s);
    let nrow = rows.len();
    let mut weights = vec![vec![0.0; g.pairs.len()]; nrow];
    let mut group_w = vec![vec![0.0; ng]; nrow];
    let mut r_true = vec![0.0; g.contacts.len()];
    let mut post = vec![[0.0; 4]; g.contacts.len()];
    for (ri, row) in rows.iter().enumerate() {
        for gi in 0..ng {
            let s0 = g.goff[gi] as usize;
            let nc = g.goff[gi + 1] as usize - s0;
            let mut none_c = [1.0f64; 4];
            let mut sum_c = [0.0f64; 4];
            let (mut none_t, mut sum_t) = (1.0f64, 0.0f64);
            let (q0, q1) = (g.coff[gi] as usize, g.coff[gi + 1] as usize);
            for q in q0..q1 {
                let o = odds[q];
                let mut a = [0.0f64; 4];
                let mut at = 0.0;
                for c in 0..nc {
                    a[c] = o * g.prior[q][c] * (1.0 - eps) * row[s0 + c];
                    at += a[c];
                }
                let den = at + eps * u;
                let rt = if at <= 0.0 { 0.0 } else { at / den };
                none_t *= 1.0 - rt;
                sum_t += rt;
                r_true[q] += rt / nrow as f64;
                for c in 0..nc {
                    let rc = if at <= 0.0 { 0.0 } else { a[c] / den };
                    none_c[c] *= 1.0 - rc;
                    sum_c[c] += rc;
                    // P(c | true): prior when nothing is close
                    let pc = if at > 0.0 { a[c] / at } else { g.prior[q][c] };
                    post[q][c] += pc / nrow as f64;
                }
            }
            let n = (q1 - q0).max(1) as f64;
            for c in 0..nc {
                let w = if p.robust_count_combine { 1.0 - none_c[c] } else { sum_c[c] / n };
                weights[ri][s0 + c] = w.max(p.robust_w_floor);
            }
            let wt = if p.robust_count_combine { 1.0 - none_t } else { sum_t / n };
            group_w[ri][gi] = wt.max(p.robust_w_floor);
        }
    }
    let mean_w = r_true.iter().sum::<f64>() / nc_tot;
    let low = r_true.iter().filter(|&&x| x < 0.5).count() as f64 / nc_tot;
    let mut n_amb = 0usize;
    let mut conf = 0usize;
    for gi in 0..ng {
        let nc = (g.goff[gi + 1] - g.goff[gi]) as usize;
        if nc > 1 {
            for q in g.coff[gi] as usize..g.coff[gi + 1] as usize {
                n_amb += 1;
                if post[q][..nc].iter().cloned().fold(0.0, f64::max) >= 0.9 {
                    conf += 1;
                }
            }
        }
    }
    let g_mean = gm.iter().sum::<f64>() / gm.len().max(1) as f64;
    let log = EmLog {
        segment: 0,
        eps,
        s,
        d0,
        loglik: ll,
        mean_w,
        frac_low: low,
        prox_frac: g_mean * u,
        capture_q: (1.0 - eps) * nc_tot / g_mean,
        n_particles: data.n_particles,
        seconds: t0.elapsed().as_secs_f64(),
        phase_confident: Some(if n_amb > 0 { conf as f64 / n_amb as f64 } else { f64::NAN }),
        n_ambiguous: Some(n_amb),
        ll_marginal: None,
    };
    DipEmResult { weights, group_w, r_true, post, eps, s, log }
}

/// Model-mean distance of every candidate of a contact (ends interpolated on the copy chains).
pub(crate) fn candidate_mean_dist(c: &DipContact, st: &Structure) -> Vec<f64> {
    let nm = st.n_models();
    c.cand[..c.n_cand as usize]
        .iter()
        .map(|&code| {
            let (Some(sa), Some(sb)) = (st.chrom_slot(copy_id(c.ca, code >> 1)), st.chrom_slot(copy_id(c.cb, code & 1))) else {
                return f64::INFINITY;
            };
            let mut s = 0.0;
            for m in 0..nm {
                let a = interpolate(c.pa as i32 as i64, &st.seq_pos[sa], st.chrom_coords(m, sa));
                let b = interpolate(c.pb as i32 as i64, &st.seq_pos[sb], st.chrom_coords(m, sb));
                s += ((a[0] - b[0]).powi(2) + (a[1] - b[1]).powi(2) + (a[2] - b[2]).powi(2)).sqrt();
            }
            s / nm as f64
        })
        .collect()
}

fn log(p: &Params, msg: &str) {
    if p.verbose {
        eprintln!("[uchrom_nucdyn] {msg}");
    }
}

fn centre(coords: &mut [Vec<V3>]) {
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
}

/// Input-orientation code of canonical code `c` of a contact.
#[inline]
pub(crate) fn input_code(c: &DipContact, code: u8) -> usize {
    let (x, y) = (code >> 1, code & 1);
    if c.swapped {
        (2 * y + x) as usize
    } else {
        (2 * x + y) as usize
    }
}

/// The diploid structure calculation (protocols `nuc_dynamics_2017` and `robust`).
pub fn calc_genome_structure(input: &Input, dip: &DiploidInput, p: &Params, engine: &mut dyn StageEngine) -> Result<Output, String> {
    p.validate()?;
    let robust = match p.protocol.as_str() {
        "nuc_dynamics_2017" => false,
        "robust" => true,
        x => return Err(format!("diploid input needs protocol nuc_dynamics_2017 or robust (EMber), not {x:?}")),
    };
    let t0 = Instant::now();
    let n_models = p.n_models;
    let n_input = input.chr_a.len();
    let mut contacts = prepare_contacts(input, dip, p.diploid_cis_sep)?;
    if robust && p.robust_dip_nbr_prior {
        let ts = Instant::now();
        let nb = neighbour_prior(&contacts, &NbrPrior::default());
        for (c, q) in contacts.iter_mut().zip(nb) {
            let k = c.n_cand as usize;
            let mut tot = 0.0;
            for i in 0..k {
                c.prior[i] *= q[i];
                tot += c.prior[i];
            }
            for i in 0..k {
                c.prior[i] = if tot > 0.0 { c.prior[i] / tot } else { 1.0 / k as f64 };
            }
        }
        log(p, &format!("2-D neighbourhood phase prior in {:.2} s", ts.elapsed().as_secs_f64()));
    }
    let mut chroms: Vec<u32> = input.chr_a.iter().chain(input.chr_b).copied().collect();
    chroms.sort_unstable();
    chroms.dedup();
    let n_amb = contacts.iter().filter(|c| c.ambiguous()).count();
    log(
        p,
        &format!(
            "diploid: {} contacts ({} with one candidate copy pair, {} ambiguous), {} chromosome copies",
            contacts.len(),
            contacts.len() - n_amb,
            n_amb,
            chroms.iter().map(|&c| dip.ploidy[c as usize] as usize).sum::<usize>()
        ),
    );
    // EMber evidence per contact (input rows): local support x given prior
    let kern = Kernel::from_params(p);
    let kern_reach = Kernel { d0: p.robust_d0_grid.iter().cloned().fold(p.robust_d0, f64::max), ..kern };
    let s_max = p.robust_s_grid.iter().cloned().fold(p.robust_s, f64::max);
    let last = *p.particle_sizes.last().unwrap();
    let row_lr: Option<Vec<f64>> = if robust && p.robust_support_rel > 0.0 {
        let sp = SupportParams { window: p.robust_support_rel * last, seed: p.seed, ..Default::default() };
        let s = support_evidence(input.chr_a, input.pos_a, input.chr_b, input.pos_b, &sp);
        let mut lr = s.lr;
        if let Some(x) = input.prior_lr {
            for (a, b) in lr.iter_mut().zip(x) {
                *a *= b;
            }
        }
        Some(lr)
    } else if robust {
        input.prior_lr.map(|x| x.to_vec())
    } else {
        None
    };
    // isolated contacts (genomic positions, both homologs together)
    let mut keep = if p.dip_isolation_nei > 0 {
        let k = isolation_keep(&contacts, p.dip_isolation_nei, p.dip_isolation_radius);
        log(
            p,
            &format!(
                "contacts after the isolation filter (>= {} neighbours within {} kb) = {}",
                p.dip_isolation_nei,
                p.dip_isolation_radius / 1000,
                k.iter().filter(|&&x| x).count()
            ),
        );
        k
    } else {
        vec![true; contacts.len()]
    };
    {
        let mut d = base_dict(&contacts, &keep);
        log(p, &format!("total number of contacts = {}", contact_count(&d)));
        remove_isolated_contacts(&mut d, p.isolation_threshold_cis, p.isolation_pos_error);
        keep = vec![false; contacts.len()];
        for v in d.values() {
            for c in v {
                keep[c.number as usize] = true;
            }
        }
        log(p, &format!("contacts after removing isolated = {}", contact_count(&d)));
    }
    let commit = robust && p.robust_dip_commit > 0.0;
    // contacts dropped by the prior commitment (re-admitted at `robust_dip_readmit_stage`)
    let mut dropped_by_prior = vec![false; contacts.len()];
    if commit && p.robust_dip_commit_stage < 0 {
        let probs: Vec<Option<[f64; 4]>> = contacts.iter().map(|c| Some(c.prior)).collect();
        let before = keep.clone();
        let (nc, nd) = commit_contacts(&mut contacts, &mut keep, &probs, p.robust_dip_commit, p.robust_dip_commit_drop);
        for k in 0..contacts.len() {
            dropped_by_prior[k] = before[k] && !keep[k];
        }
        log(p, &format!("phase commitment by the prior (>= {}): {nc} committed, {nd} dropped", p.robust_dip_commit));
    }
    let readmit = commit && p.robust_dip_commit_stage < 0 && p.robust_dip_commit_drop && p.robust_dip_readmit_stage >= 1;
    let mut sizes = p.particle_sizes.clone();
    if robust {
        sizes.extend(std::iter::repeat_n(last, p.robust_refine));
    }
    let mut prev: Option<Structure> = None;
    let mut stages = vec![];
    let (mut eps, mut s) = (p.robust_eps, p.robust_s);
    let mut last_full: BTreeMap<u32, Vec<i64>> = BTreeMap::new();
    let mut last_merged = false;
    let mut snapshots: Vec<Vec<Vec<V3>>> = vec![];
    // last EM update: groups (contacts) and its posteriors
    let mut last_em: Option<(DipGroups, Vec<f64>, Vec<[f64; 4]>)> = None;
    for (stage, &ps) in sizes.iter().enumerate() {
        let ts = Instant::now();
        if readmit && stage as i64 == p.robust_dip_readmit_stage {
            // re-admit the contacts the prior could not phase, as ambiguous restraints for one
            // stage; the next stage commits them by the structure (below) or drops them
            let n_re = dropped_by_prior.iter().filter(|&&x| x).count();
            for (k, &d) in dropped_by_prior.iter().enumerate() {
                if d {
                    keep[k] = true;
                }
            }
            log(p, &format!("stage {}: {n_re} contacts re-admitted as ambiguous", stage + 1));
        }
        let staged = p.robust_dip_commit_stage >= 1 && stage as i64 == p.robust_dip_commit_stage;
        let after_readmit = readmit && stage as i64 == p.robust_dip_readmit_stage + 1;
        if commit && (staged || after_readmit) {
            // staged commitment: EM posterior P(c | true) of the structure so far (prior included)
            let mut probs: Vec<Option<[f64; 4]>> = vec![None; contacts.len()];
            if let Some((g, _, post)) = last_em.as_ref() {
                for gi in 0..g.n_groups() {
                    let s0 = g.goff[gi] as usize;
                    let nc = g.goff[gi + 1] as usize - s0;
                    for q in g.coff[gi] as usize..g.coff[gi + 1] as usize {
                        let k = g.contacts[q] as usize;
                        let c = &contacts[k];
                        let mut pr = [0.0; 4];
                        for j in 0..nc {
                            if let Some(i) = c.cand[..c.n_cand as usize].iter().position(|&x| x == g.code[s0 + j]) {
                                pr[i] = post[q][j];
                            }
                        }
                        probs[k] = Some(pr);
                    }
                }
            }
            let (nc, nd) = commit_contacts(&mut contacts, &mut keep, &probs, p.robust_dip_commit, p.robust_dip_commit_drop);
            log(p, &format!("phase commitment by the structure at stage {} (>= {}): {nc} committed, {nd} dropped", stage + 1, p.robust_dip_commit));
        }
        let remove = if robust { p.robust_remove_violated } else { true };
        if remove && stage > 0 && ps < 0.5e6 {
            if let Some(pr) = prev.as_ref() {
                let thr = p.violated_threshold_2017;
                let ok: Vec<bool> = contacts
                    .par_iter()
                    .zip(keep.par_iter())
                    .map(|(c, &k)| k && candidate_mean_dist(c, pr).into_iter().fold(f64::INFINITY, f64::min) < thr)
                    .collect();
                keep = ok;
                log(p, &format!("contacts after removing violated = {}", keep.iter().filter(|&&k| k).count()));
            }
        }
        let psi = ps as i32 as i64;
        let d = base_dict(&contacts, &keep);
        let full = calc_particles(&d, &chroms, psi);
        let merge = robust && p.robust_merge_below > 0.0 && ps <= p.robust_merge_below;
        let grid = if merge { merge_empty_particles(&d, &full) } else { full.clone() };
        let copies = |g: &BTreeMap<u32, Vec<i64>>| -> BTreeMap<u32, Vec<i64>> {
            let mut out = BTreeMap::new();
            for (&c, v) in g {
                for h in 0..dip.ploidy[c as usize] {
                    out.insert(copy_id(c, h), v.clone());
                }
            }
            out
        };
        let mut st = Structure::new(&copies(&grid));
        let n = st.n_particles();
        st.coords = start_coords(&st, n_models, prev.as_ref(), p, stage);
        let groups = dip_groups(&contacts, &keep, &st, p, if robust { p.robust_count_cap } else { 0 });
        let backbone = if merge {
            merged_backbone_restraints(&st, psi, p.backbone_dist_lower, p.backbone_dist_upper, p.robust_merge_nu)
        } else {
            backbone_restraints(&st, psi, p.backbone_dist_lower, p.backbone_dist_upper)
        };
        let reweight = robust && stage >= p.robust_start_stage && groups.n_groups() > 0;
        let split = reweight && p.robust_dip_split;
        let (rs, nb) = restraint_set(backbone, &groups, split);
        let form = if robust { RestraintForm::Weighted2017 } else { RestraintForm::Master2017 };
        let mut sys = System::new(n, vec![1.0; n], vec![1.0; n], &rs).with_form(form);
        let (schedule, dyn_steps) = if robust {
            let refine_pass = stage >= p.particle_sizes.len();
            let n_temp = if refine_pass && p.robust_refine_temp_steps > 0 {
                p.robust_refine_temp_steps
            } else {
                p.robust_temp_steps_for(stage.min(p.particle_sizes.len() - 1))
            };
            let t_start = if refine_pass && p.robust_refine_temp_start > 0.0 { p.robust_refine_temp_start } else { p.temp_start };
            (anneal_schedule(t_start, p.temp_end, n_temp, 1.0), p.robust_dyn_steps_for(stage.min(p.particle_sizes.len() - 1)))
        } else {
            (anneal_schedule(p.temp_start, p.temp_end, p.temp_steps_for(stage), 1.0), p.dyn_steps_for(stage))
        };
        let parts = split_schedule(schedule.len(), if reweight { p.robust_segments } else { 1 });
        // evidence odds of the grouped contacts
        let odds: Vec<f64> = groups
            .contacts
            .iter()
            .map(|&k| row_lr.as_ref().map(|lr| lr[contacts[k as usize].row as usize]).unwrap_or(1.0))
            .collect();
        let t_prep = ts.elapsed().as_secs_f64();
        log(
            p,
            &format!(
                "stage {} ({} kb): {} particles, {} contacts, {} restraints ({} candidate groups), {} models",
                stage + 1,
                ps / 1e3,
                n,
                groups.n_used,
                sys.n_restraints(),
                groups.n_groups(),
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
                let data = EmData::new(&coords, &groups.pairs, &vec![1u32; groups.pairs.len()], &kern_reach, s_max, p.robust_pair_sample);
                let res = em_update_dip(&data, &groups, &odds, &kern, p, eps, s);
                eps = res.eps;
                s = res.s;
                if split {
                    set_weights(&mut sys, nb, &res.weights, n_models);
                } else {
                    let rows: Vec<Vec<f64>> = res
                        .group_w
                        .iter()
                        .map(|gw| {
                            let gw = group_weights(&groups, gw);
                            let mut v = vec![];
                            for gi in 0..groups.n_groups() {
                                for _ in groups.goff[gi]..groups.goff[gi + 1] {
                                    v.push(gw[gi]);
                                }
                            }
                            v
                        })
                        .collect();
                    set_weights(&mut sys, nb, &rows, n_models);
                }
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
                        "  EM (part {seg}): eps {:.4} s {:.2} mean P(true) {:.3} low {:.3} ambiguous {} phase-confident {:.3} ll {:.3} ({:.2} s)",
                        l.eps,
                        l.s,
                        l.mean_w,
                        l.frac_low,
                        l.n_ambiguous.unwrap_or(0),
                        l.phase_confident.unwrap_or(f64::NAN),
                        l.loglik,
                        l.seconds
                    ),
                );
                em_logs.push(l);
                last_em = Some((groups.clone(), res.r_true, res.post));
            }
            let key = stage + 1000 * seg;
            f_dist = if robust { force_constant(p, &sys, nb, n) } else { p.dist_force_const };
            coords = engine.anneal(&sys, coords, &schedule[range.clone()], dyn_steps, f_dist, 1.0, key, p)?;
        }
        if robust && stage + 1 == sizes.len() && p.robust_sample_temp > 0.0 && p.robust_sample_steps > 0 {
            let f_rep = schedule.last().map(|x| x.1).unwrap_or(1.0);
            let block = vec![(p.robust_sample_temp, f_rep); p.robust_sample_steps];
            let ds = if p.robust_sample_dyn_steps > 0 { p.robust_sample_dyn_steps } else { dyn_steps };
            for k in 0..p.robust_sample_snapshots.max(1) {
                coords = engine.anneal(&sys, coords, &block, ds, f_dist, 1.0, stage + 5000 + 1000 * k, p)?;
                snapshots.push(coords.clone());
            }
        }
        centre(&mut coords);
        st.coords = coords;
        let t_dyn = td.elapsed().as_secs_f64() - t_em;
        log(p, &format!("stage {} done in {:.2} s ({:.2} s dynamics)", stage + 1, t_prep + t_dyn + t_em, t_dyn));
        stages.push(StageLog {
            stage,
            particle_size: ps,
            bead_size: 1.0,
            n_models,
            n_particles: n,
            n_contacts: groups.n_used,
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
        last_full = copies(&full);
        last_merged = merge;
        prev = Some(st);
    }
    let mut st = prev.unwrap();
    if snapshots.len() > 1 {
        st.coords = snapshots.into_iter().flatten().collect();
        centre(&mut st.coords);
    }
    // per input contact: phase probabilities and (EMber) P(true)
    let mut phase_probs = vec![f64::NAN; 4 * n_input];
    let mut contact_weights = if robust { vec![f64::NAN; n_input] } else { vec![] };
    match (&last_em, robust) {
        (Some((g, r_true, post)), true) => {
            for gi in 0..g.n_groups() {
                let s0 = g.goff[gi] as usize;
                let nc = g.goff[gi + 1] as usize - s0;
                for q in g.coff[gi] as usize..g.coff[gi + 1] as usize {
                    let c = &contacts[g.contacts[q] as usize];
                    let r = c.row as usize;
                    contact_weights[r] = r_true[q];
                    for k in 0..4 {
                        phase_probs[4 * r + k] = 0.0;
                    }
                    for k in 0..nc {
                        phase_probs[4 * r + input_code(c, g.code[s0 + k])] = post[q][k];
                    }
                }
            }
        }
        _ => {
            // closest candidate in the final structure (as Dip-C impute3, without its thresholds)
            let res: Vec<Option<(usize, usize)>> = contacts
                .par_iter()
                .zip(keep.par_iter())
                .map(|(c, &k)| {
                    if !k {
                        return None;
                    }
                    let dist = candidate_mean_dist(c, &st);
                    let (best, _) = dist.iter().enumerate().fold((0, f64::INFINITY), |a, (i, &x)| if x < a.1 { (i, x) } else { a });
                    dist[best].is_finite().then(|| (c.row as usize, input_code(c, c.cand[best])))
                })
                .collect();
            for (r, code) in res.into_iter().flatten() {
                for k in 0..4 {
                    phase_probs[4 * r + k] = 0.0;
                }
                phase_probs[4 * r + code] = 1.0;
            }
        }
    }
    let (seq_pos, coords) = if last_merged { expand_to_grid(&st, &last_full) } else { (st.seq_pos.clone(), st.coords.clone()) };
    let nm = coords.len();
    Ok(Output {
        chroms: st.chroms,
        seq_pos,
        coords,
        model_rmsds: vec![f64::NAN; nm],
        particle_size: last,
        stages,
        seconds_total: t0.elapsed().as_secs_f64(),
        contact_weights,
        diploid: true,
        phase_probs,
        mix_cells: 0,
        cell_probs: vec![],
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::pipeline::CpuEngine;
    use crate::rng::Rng;

    fn input<'a>(names: &'a [String], ca: &'a [u32], pa: &'a [i64], cb: &'a [u32], pb: &'a [i64], amb: &'a [i64], act: &'a [bool]) -> Input<'a> {
        Input { names, chr_a: ca, pos_a: pa, chr_b: cb, pos_b: pb, ambig: amb, active: act, prior_lr: None, dip: None }
    }

    #[test]
    fn candidates_follow_phase_ploidy_and_cis_rule() {
        let names: Vec<String> = vec!["chr1".into(), "chrX".into()];
        // 0: cis close, unphased; 1: cis far, unphased; 2: cis far, end a phased 1;
        // 3: trans, unphased; 4: trans to the single-copy chrX, end a phased 0; 5: swapped ends
        let ca = [0u32, 0, 0, 0, 0, 1];
        let pa = [1_000_000i64, 1_000_000, 1_000_000, 5_000_000, 5_000_000, 7_000_000];
        let cb = [0u32, 0, 0, 1, 1, 0];
        let pb = [3_000_000i64, 40_000_000, 40_000_000, 9_000_000, 9_000_000, 2_000_000];
        let ha = [-1i8, -1, 1, -1, 0, -1];
        let hb = [-1i8, -1, -1, -1, 1, 1];
        let amb: Vec<i64> = (1..=6).collect();
        let act = [true; 6];
        let inp = input(&names, &ca, &pa, &cb, &pb, &amb, &act);
        let dip = DiploidInput { hap_a: &ha, hap_b: &hb, ploidy: &[2, 1], prior: None };
        let c = prepare_contacts(&inp, &dip, 10_000_000).unwrap();
        let cands = |k: usize| c[k].cand[..c[k].n_cand as usize].to_vec();
        assert_eq!(cands(0), vec![0, 3]); // same homolog only
        assert_eq!(cands(1), vec![0, 1, 2, 3]);
        assert_eq!(cands(2), vec![2, 3]); // hap_a = 1
        assert_eq!(cands(3), vec![0, 2]); // chrX single copy -> h_b = 0
        assert_eq!(cands(4), vec![0]); // phased chr1 copy 0, chrX
        // row 5: (chrX, 7 Mb, ?) - (chr1, 2 Mb, 1) -> canonical (chr1, 2 Mb, 1) - (chrX, 7 Mb, 0)
        assert!(c[5].swapped);
        assert_eq!((c[5].ca, c[5].pa), (0, 2_000_000));
        assert_eq!(cands(5), vec![2]);
        assert_eq!(input_code(&c[5], 2), 1); // input orientation: (hap_a = 0 on chrX, hap_b = 1)
        for k in 0..6 {
            let s: f64 = c[k].prior[..c[k].n_cand as usize].iter().sum();
            assert!((s - 1.0).abs() < 1e-12);
        }
        // a given prior is renormalised over the candidates, in the input orientation
        let mut pr = vec![0.25; 24];
        pr[4 * 5..4 * 6].copy_from_slice(&[0.0, 0.9, 0.0, 0.1]);
        pr[4 * 1..4 * 2].copy_from_slice(&[0.4, 0.1, 0.1, 0.4]);
        let dip2 = DiploidInput { prior: Some(&pr), ..dip };
        let c2 = prepare_contacts(&inp, &dip2, 10_000_000).unwrap();
        assert_eq!(c2[1].prior, [0.4, 0.1, 0.1, 0.4]);
        assert_eq!(c2[5].prior[0], 1.0);
    }

    #[test]
    fn groups_bin_contacts_by_candidate_set() {
        let names: Vec<String> = vec!["chr1".into()];
        let ca = [0u32, 0, 0];
        let pa = [150i64, 160, 150];
        let cb = [0u32, 0, 0];
        let pb = [950i64, 980, 950];
        let ha = [-1i8, -1, 0];
        let hb = [-1i8, -1, 0];
        let amb = [1i64, 2, 3];
        let act = [true; 3];
        let inp = input(&names, &ca, &pa, &cb, &pb, &amb, &act);
        let dip = DiploidInput { hap_a: &ha, hap_b: &hb, ploidy: &[2], prior: None };
        let c = prepare_contacts(&inp, &dip, 0).unwrap();
        let grid: BTreeMap<u32, Vec<i64>> = [(0u32, (1..=10).map(|k| k * 100).collect::<Vec<i64>>()), (1, (1..=10).map(|k| k * 100).collect())]
            .into_iter()
            .collect();
        let st = Structure::new(&grid);
        let p = Params::default();
        let g = dip_groups(&c, &[true; 3], &st, &p, 0);
        // contacts 0 and 1: same 4 candidates (bins 1 and 9 / 9) -> one group of 2 contacts; contact 2 fixed
        assert_eq!(g.n_groups(), 2);
        assert_eq!(g.counts(), vec![1, 2]); // key order: (1, 9, 0) < (1, 19, 1)
        assert_eq!(g.pairs[..1], [[1, 9]]);
        assert_eq!(g.pairs[1..], [[1, 9], [1, 19], [11, 9], [11, 19]]);
        let two = (1.0f32 * 2f32.powf(-0.33f32)) as f64;
        assert!((g.lim[1][1] - two * (1.2f32 as f64)).abs() < 1e-12);
        let (rs, nb) = restraint_set(vec![], &g, false);
        assert_eq!((nb, rs.groups.clone()), (0, vec![0, 1, 5]));
        let (rs, _) = restraint_set(vec![], &g, true);
        assert_eq!(rs.groups, vec![0, 1, 2, 3, 4, 5]);
    }

    #[test]
    fn neighbour_prior_follows_phased_neighbours() {
        // chr1: a block of contacts near (20 Mb, 40 Mb) phased (1, 1), another near (60, 90) phased
        // (0, 0); one unphased contact in each block, one isolated far away
        let names: Vec<String> = vec!["chr1".into()];
        let (mut pa, mut pb, mut ha, mut hb) = (vec![], vec![], vec![], vec![]);
        for k in 0..20i64 {
            pa.push(20_000_000 + k * 10_000);
            pb.push(40_000_000 + k * 7_000);
            ha.push(1i8);
            hb.push(if k % 2 == 0 { 1 } else { -1 });
            pa.push(60_000_000 + k * 10_000);
            pb.push(90_000_000 + k * 9_000);
            ha.push(if k % 3 == 0 { -1 } else { 0 });
            hb.push(0i8);
        }
        pa.extend([20_050_000, 60_050_000, 150_000_000]);
        pb.extend([40_030_000, 90_020_000, 200_000_000]);
        ha.extend([-1, -1, -1]);
        hb.extend([-1, -1, -1]);
        let n = pa.len();
        let (ca, cb) = (vec![0u32; n], vec![0u32; n]);
        let amb: Vec<i64> = (1..=n as i64).collect();
        let act = vec![true; n];
        let inp = input(&names, &ca, &pa, &cb, &pb, &amb, &act);
        let dip = DiploidInput { hap_a: &ha, hap_b: &hb, ploidy: &[2], prior: None };
        let p = neighbour_phase_probs(&inp, &dip, 10_000_000, &NbrPrior::default()).unwrap();
        let q = |r: usize| &p[4 * r..4 * r + 4];
        assert!(q(n - 3)[3] > 0.9, "{:?}", q(n - 3));
        assert!(q(n - 2)[0] > 0.9, "{:?}", q(n - 2));
        // no neighbours: hickit's spatial prior only (separation 50 Mb -> P(same) >= 0.2 -> uniform stays)
        assert!((q(n - 1).iter().sum::<f64>() - 1.0).abs() < 1e-9 && q(n - 1).iter().all(|&x| (x - 0.25).abs() < 1e-9), "{:?}", q(n - 1));
        // phased contacts keep their phases
        assert_eq!(q(0)[3], 1.0);
    }

    #[test]
    fn em_infers_the_homolog_from_the_structure() {
        // two copies of a chain far apart; true contacts on copy 0 or 1, half of them phased
        let n = 200usize;
        let mut r = Rng::new(3);
        let mut pos: Vec<V3> = vec![];
        for copy in 0..2 {
            let mut q = [copy as f64 * 40.0, 0.0, 0.0];
            for _ in 0..n {
                q = [q[0] + r.normal() * 0.8, q[1] + r.normal() * 0.8, q[2] + r.normal() * 0.8];
                pos.push(q);
            }
        }
        let d = |i: usize, j: usize| -> f64 { (0..3).map(|k| (pos[i][k] - pos[j][k]).powi(2)).sum::<f64>().sqrt() };
        // groups: each contact its own group with candidates (i0, j0), (i1, j1)
        let mut g = DipGroups { goff: vec![0], coff: vec![0], ..Default::default() };
        let mut truth = vec![];
        while truth.len() < 400 {
            let i = (r.uniform() * n as f64) as usize;
            let j = (r.uniform() * n as f64) as usize;
            let h = (r.uniform() * 2.0) as usize;
            // informative contacts: close on the true copy, far on the other one
            if i.abs_diff(j) < 3 || d(i + h * n, j + h * n) > 2.5 || d(i + (1 - h) * n, j + (1 - h) * n) < 6.0 {
                continue;
            }
            for c in 0..2 {
                g.pairs.push([(i + c * n) as u32, (j + c * n) as u32]);
                g.code.push((3 * c) as u8);
            }
            g.goff.push(g.pairs.len() as u32);
            g.lim.push([0.8, 1.2]);
            g.contacts.push(truth.len() as u32);
            g.prior.push([0.5, 0.5, 0.0, 0.0]);
            g.coff.push(g.contacts.len() as u32);
            truth.push(h);
        }
        let p = Params { protocol: "robust".into(), ..Default::default() };
        let k = Kernel::from_params(&p);
        let data = EmData::new(&[pos.clone()], &g.pairs, &vec![1; g.pairs.len()], &k, 6.0, 0);
        let res = em_update_dip(&data, &g, &vec![1.0; truth.len()], &k, &p, 0.1, 1.5);
        let correct = truth.iter().enumerate().filter(|&(q, &h)| res.post[q][h] > 0.9).count();
        assert!(correct as f64 / truth.len() as f64 > 0.97, "{correct} / {}", truth.len());
        // the weight of the wrong copy pair is small, of the right one large
        let w = &res.weights[0];
        let (mut right, mut wrong) = (0.0, 0.0);
        for (q, &h) in truth.iter().enumerate() {
            right += w[2 * q + h];
            wrong += w[2 * q + 1 - h];
        }
        assert!(right / 400.0 > 0.9 && wrong / 400.0 < 0.05, "{right} {wrong}");
        assert!(res.eps < 0.05, "eps {}", res.eps);
    }

    /// Two homologs of 3 chromosomes, each a random walk; contacts from the truth, a third of the
    /// ends phased.  The diploid run separates the homologs: per-copy distance matrices correlate
    /// with the truth, and EMber's phase posteriors of unphased ends are mostly right.
    fn toy_diploid(seed: u64) -> (Vec<String>, Vec<u32>, Vec<i64>, Vec<u32>, Vec<i64>, Vec<i8>, Vec<i8>, Vec<(usize, usize)>, Vec<Vec<V3>>) {
        let mut rng = Rng::new(seed);
        let names: Vec<String> = ["chrA", "chrB", "chrC"].iter().map(|s| s.to_string()).collect();
        let step = 100_000i64;
        let nloc = 150usize;
        // walks[chrom][copy]
        let mut walks: Vec<Vec<Vec<V3>>> = vec![];
        for c in 0..3 {
            let mut per = vec![];
            for h in 0..2 {
                let mut q = [c as f64 * 6.0, h as f64 * 9.0, 0.0];
                let mut v = vec![];
                for _ in 0..nloc {
                    q = [q[0] + rng.normal() * 0.35, q[1] + rng.normal() * 0.35, q[2] + rng.normal() * 0.35];
                    v.push(q);
                }
                per.push(v);
            }
            walks.push(per);
        }
        let (mut ca, mut pa, mut cb, mut pb, mut ha, mut hb, mut truth) = (vec![], vec![], vec![], vec![], vec![], vec![], vec![]);
        for _ in 0..60_000 {
            let c1 = (rng.uniform() * 3.0) as usize;
            let c2 = if rng.uniform() < 0.9 { c1 } else { (rng.uniform() * 3.0) as usize };
            let h1 = (rng.uniform() * 2.0) as usize;
            let h2 = if c1 == c2 && rng.uniform() < 0.9 { h1 } else { (rng.uniform() * 2.0) as usize };
            let i = (rng.uniform() * nloc as f64) as usize;
            let j = (rng.uniform() * nloc as f64) as usize;
            let (a, b) = (walks[c1][h1][i], walks[c2][h2][j]);
            let d2: f64 = (0..3).map(|k| (a[k] - b[k]).powi(2)).sum();
            if d2 < 0.8 {
                ca.push(c1 as u32);
                pa.push(i as i64 * step + 1 + (rng.uniform() * step as f64) as i64);
                cb.push(c2 as u32);
                pb.push(j as i64 * step + 1 + (rng.uniform() * step as f64) as i64);
                ha.push(if rng.uniform() < 0.35 { h1 as i8 } else { -1 });
                hb.push(if rng.uniform() < 0.35 { h2 as i8 } else { -1 });
                truth.push((h1, h2));
            }
        }
        let flat: Vec<Vec<V3>> = walks.into_iter().flatten().collect(); // copy-id order (c, h)
        (names, ca, pa, cb, pb, ha, hb, truth, flat)
    }

    fn pearson(a: &[f64], b: &[f64]) -> f64 {
        let n = a.len() as f64;
        let (ma, mb) = (a.iter().sum::<f64>() / n, b.iter().sum::<f64>() / n);
        let (mut sab, mut saa, mut sbb) = (0.0, 0.0, 0.0);
        for (x, y) in a.iter().zip(b) {
            sab += (x - ma) * (y - mb);
            saa += (x - ma).powi(2);
            sbb += (y - mb).powi(2);
        }
        sab / (saa * sbb).sqrt()
    }

    #[test]
    fn diploid_runs_separate_the_homologs() {
        let (names, ca, pa, cb, pb, ha, hb, truth, walks) = toy_diploid(11);
        let n = ca.len();
        let amb: Vec<i64> = (1..=n as i64).collect();
        let act = vec![true; n];
        let dip = DiploidInput { hap_a: &ha, hap_b: &hb, ploidy: &[2, 2, 2], prior: None };
        let inp = Input { dip: Some(dip), ..input(&names, &ca, &pa, &cb, &pb, &amb, &act) };
        // (label, protocol, split, commit threshold, commit stage, drop, isolation neighbours, readmit stage)
        let cases: [(&str, &str, bool, f64, i64, bool, u32, i64); 7] = [
            ("nuc_dynamics_2017", "nuc_dynamics_2017", true, 0.0, -1, true, 0, -1),
            ("robust", "robust", false, 0.0, -1, true, 0, -1),
            ("robust (split)", "robust", true, 0.0, -1, true, 0, -1),
            ("robust, commit 0.75 by prior, drop", "robust", false, 0.75, -1, true, 0, -1),
            ("robust, commit 0.75 at stage 3, keep", "robust", false, 0.75, 2, false, 0, -1),
            ("robust, isolation -c2 -r10m", "robust", false, 0.0, -1, true, 2, -1),
            ("robust, commit 0.75 by prior, re-admit at stage 2", "robust", false, 0.75, -1, true, 0, 1),
        ];
        for (label, proto, split, tau, cstage, drop, iso, readmit) in cases {
            let p = Params {
                protocol: proto.into(),
                robust_dip_split: split,
                robust_dip_commit: tau,
                robust_dip_commit_stage: cstage,
                robust_dip_commit_drop: drop,
                dip_isolation_nei: iso,
                robust_dip_readmit_stage: readmit,
                particle_sizes: vec![4e6, 1e6, 4e5, 2e5],
                n_models: 2,
                seed: 3,
                temp_steps: vec![60],
                dynamics_steps: vec![50],
                robust_temp_steps: vec![60],
                robust_dynamics_steps: vec![50],
                n_threads: 2,
                ..Default::default()
            };
            let mut eng = CpuEngine::new(2).unwrap();
            let out = calc_genome_structure(&inp, &dip, &p, &mut eng).unwrap();
            assert!(out.diploid);
            assert_eq!(out.chroms, vec![0, 1, 2, 3, 4, 5]);
            // per copy: distance-matrix r vs the truth walk at the particle positions (200 kb)
            let mut rs = vec![];
            for (slot, &cid) in out.chroms.iter().enumerate() {
                let tw = &walks[cid as usize];
                let sp = &out.seq_pos[slot];
                let off: usize = out.seq_pos[..slot].iter().map(|v| v.len()).sum();
                let mut dm = vec![];
                let mut dt = vec![];
                for a in 0..sp.len() {
                    for b in a + 2..sp.len() {
                        let (la, lb) = (((sp[a] - 1) / 100_000) as usize, ((sp[b] - 1) / 100_000) as usize);
                        if la >= tw.len() || lb >= tw.len() {
                            continue;
                        }
                        let x = &out.coords[0];
                        dm.push((0..3).map(|k| (x[off + a][k] - x[off + b][k]).powi(2)).sum::<f64>().sqrt());
                        dt.push((0..3).map(|k| (tw[la][k] - tw[lb][k]).powi(2)).sum::<f64>().sqrt());
                    }
                }
                rs.push(pearson(&dm, &dt));
            }
            let mean_r = rs.iter().sum::<f64>() / rs.len() as f64;
            // phase of the contacts with an unphased end, where the truth tells the candidates
            // apart (the true copy pair is in contact, every other combination >= 3 apart)
            let (mut right, mut tot) = (0usize, 0usize);
            for r in 0..n {
                let pp = &out.phase_probs[4 * r..4 * r + 4];
                if pp[0].is_nan() || (ha[r] >= 0 && hb[r] >= 0) {
                    continue;
                }
                let (t1, t2) = truth[r];
                let la = ((pa[r] - 1) / 100_000) as usize;
                let lb = ((pb[r] - 1) / 100_000) as usize;
                let dist = |x: usize, y: usize| -> f64 {
                    let (a, b) = (walks[2 * ca[r] as usize + x][la], walks[2 * cb[r] as usize + y][lb]);
                    (0..3).map(|k| (a[k] - b[k]).powi(2)).sum::<f64>().sqrt()
                };
                let informative = (0..4).all(|c| {
                    let (x, y) = (c >> 1, c & 1);
                    (x == t1 && y == t2) || (ha[r] >= 0 && x != ha[r] as usize) || (hb[r] >= 0 && y != hb[r] as usize) || dist(x, y) >= 3.0
                });
                if !informative {
                    continue;
                }
                let best = (0..4).max_by(|&a, &b| pp[a].partial_cmp(&pp[b]).unwrap()).unwrap();
                tot += 1;
                right += (best == 2 * t1 + t2) as usize;
            }
            let acc = right as f64 / tot as f64;
            eprintln!("{label}: per-copy distance r {rs:.3?} (mean {mean_r:.3}), phase accuracy {acc:.3} ({tot} informative contacts)");
            assert!(mean_r > 0.6, "{label}: mean r {mean_r}");
            assert!(acc > 0.9, "{label}: phase accuracy {acc}");
            if proto == "robust" && tau == 0.0 {
                assert!(out.contact_weights.iter().filter(|x| x.is_finite()).count() > n / 2);
                assert!(out.stages.iter().any(|s| s.robust.iter().any(|l| l.n_ambiguous.unwrap_or(0) > 0)));
            }
        }
    }

    fn dc(ca: u32, pa: i64, cb: u32, pb: i64, cand: &[u8], prior: &[f64]) -> DipContact {
        let mut c4 = [0u8; 4];
        c4[..cand.len()].copy_from_slice(cand);
        let mut p4 = [0.0; 4];
        p4[..prior.len()].copy_from_slice(prior);
        DipContact { ca, pa, cb, pb, row: 0, swapped: false, n_cand: cand.len() as u8, cand: c4, prior: p4 }
    }

    #[test]
    fn commit_contacts_hard_phases_confident_and_drops_or_keeps_the_rest() {
        let base = vec![
            dc(0, 100, 0, 5_000, &[0, 3], &[0.8, 0.2]),
            dc(0, 200, 0, 6_000, &[0, 3], &[0.6, 0.4]),
            dc(0, 300, 1, 9_000, &[1], &[1.0]),
            dc(0, 400, 1, 9_500, &[0, 1, 2, 3], &[0.1, 0.1, 0.05, 0.75]),
        ];
        let probs: Vec<Option<[f64; 4]>> = base.iter().map(|c| Some(c.prior)).collect();
        for drop in [true, false] {
            let mut cs = base.clone();
            let mut keep = vec![true; 4];
            let (nc, nd) = commit_contacts(&mut cs, &mut keep, &probs, 0.75, drop);
            assert_eq!(nc, 2);
            assert_eq!((cs[0].n_cand, cs[0].cand[0], cs[0].prior[0]), (1, 0, 1.0));
            assert_eq!((cs[3].n_cand, cs[3].cand[0]), (1, 3));
            assert_eq!(cs[2].n_cand, 1); // already unambiguous: untouched
            if drop {
                assert_eq!((nd, keep.clone()), (1, vec![true, false, true, true]));
            } else {
                assert_eq!((nd, keep.clone(), cs[1].n_cand), (0, vec![true; 4], 2));
            }
        }
        // unknown probability: dropped / kept, never committed
        let mut cs = base.clone();
        let mut keep = vec![true; 4];
        let (nc, nd) = commit_contacts(&mut cs, &mut keep, &[None, None, None, None], 0.75, true);
        assert_eq!((nc, nd), (0, 3));
    }

    #[test]
    fn isolation_keep_counts_neighbours_within_the_radius() {
        // chromosome pair (0, 0): three contacts close together and one far away; (0, 1): one alone
        let cs = vec![
            dc(0, 1_000_000, 0, 5_000_000, &[0], &[1.0]),
            dc(0, 1_500_000, 0, 5_200_000, &[0], &[1.0]),
            dc(0, 2_000_000, 0, 4_800_000, &[0], &[1.0]),
            dc(0, 1_200_000, 0, 30_000_000, &[0], &[1.0]),
            dc(0, 1_000_000, 1, 5_000_000, &[0], &[1.0]),
        ];
        assert_eq!(isolation_keep(&cs, 2, 1_000_000), vec![true, true, true, false, false]);
        assert_eq!(isolation_keep(&cs, 3, 1_000_000), vec![false; 5]);
        assert_eq!(isolation_keep(&cs, 1, 100_000_000), vec![true, true, true, true, false]);
    }
}
