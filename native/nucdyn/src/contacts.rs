//! Contact handling: the contact dictionary, isolation filter, particle
//! binning, violated-contact removal and 3-D ambiguity resolution.
//!
//! Each function re-implements the behaviour of the corresponding function
//! of the original NucDynamics (`nuc_dynamics.py`); the names are kept so
//! the two can be compared side by side.

use rayon::prelude::*;
use std::collections::{BTreeMap, HashMap, HashSet};

/// One contact: sequence positions of both ends, ambiguity group and the
/// row it came from.
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct Contact {
    pub pos_a: i64,
    pub pos_b: i64,
    pub ambig: i64,
    pub number: u32,
}

/// Contacts keyed by chromosome pair `(a, b)` with `a <= b`.  Chromosome
/// ids are ranks in the sorted list of names, so id order is the string
/// order the original uses (`chr_a > chr_b` → swap).
pub type ContactDict = BTreeMap<(u32, u32), Vec<Contact>>;

/// Build the contact dictionary from flat arrays (one entry per contact).
/// `names` must be sorted; ids index into it.  Inactive contacts are
/// skipped unless `include_inactive`.
pub fn build_contact_dict(
    chr_a: &[u32],
    pos_a: &[i64],
    chr_b: &[u32],
    pos_b: &[i64],
    ambig: &[i64],
    active: &[bool],
    include_inactive: bool,
) -> ContactDict {
    let mut d: ContactDict = BTreeMap::new();
    for i in 0..chr_a.len() {
        if !include_inactive && !active[i] {
            continue;
        }
        let (mut ca, mut pa, mut cb, mut pb) = (chr_a[i], pos_a[i], chr_b[i], pos_b[i]);
        if ca > cb {
            std::mem::swap(&mut ca, &mut cb);
            std::mem::swap(&mut pa, &mut pb);
        }
        d.entry((ca, cb)).or_default().push(Contact {
            pos_a: pa,
            pos_b: pb,
            ambig: ambig[i],
            number: i as u32,
        });
    }
    d
}

pub fn contact_count(d: &ContactDict) -> usize {
    d.values().map(|v| v.len()).sum()
}

#[inline]
fn between(x: i64, a: i64, b: i64) -> bool {
    a < x && x < b
}

/// `initial_clean_contacts`: keep only unambiguous contacts that are
/// supported by another contact of the same chromosome pair within the
/// isolation threshold at both ends.
pub fn initial_clean_contacts(d: &ContactDict, threshold_cis: i64, threshold_trans: i64, pos_error: i64) -> ContactDict {
    let mut ag_size: HashMap<i64, usize> = HashMap::new();
    for v in d.values() {
        for c in v {
            *ag_size.entry(c.ambig).or_insert(0) += 1;
        }
    }
    let mut out: ContactDict = BTreeMap::new();
    for (&(ca, cb), contacts) in d {
        let contacts: Vec<Contact> = contacts.iter().copied().filter(|c| ag_size[&c.ambig] == 1).collect();
        let threshold = if ca == cb { threshold_cis } else { threshold_trans };
        if contacts.is_empty() {
            continue;
        }
        let supported = supported_contacts(&contacts, threshold, pos_error);
        if !supported.iter().any(|&s| s) {
            continue;
        }
        let kept: Vec<Contact> = contacts
            .iter()
            .zip(&supported)
            .filter(|(_, &s)| s)
            .map(|(c, _)| *c)
            .collect();
        out.insert((ca, cb), kept);
    }
    out
}

/// For each contact i: is there a contact j != i with both ends within
/// (pos_error, threshold) of i's ends, in the same or the swapped orientation?
/// Same result as the original's N x N boolean matrices, computed with
/// sorted windows.  (Positions are cast to int32 by the original.)
pub fn supported_contacts(contacts: &[Contact], threshold: i64, pos_error: i64) -> Vec<bool> {
    let n = contacts.len();
    let a: Vec<i64> = contacts.iter().map(|c| c.pos_a as i32 as i64).collect();
    let b: Vec<i64> = contacts.iter().map(|c| c.pos_b as i32 as i64).collect();
    let mut by_a: Vec<usize> = (0..n).collect();
    by_a.sort_by_key(|&i| a[i]);
    let mut by_b: Vec<usize> = (0..n).collect();
    by_b.sort_by_key(|&i| b[i]);
    let sa: Vec<i64> = by_a.iter().map(|&i| a[i]).collect();
    let sb: Vec<i64> = by_b.iter().map(|&i| b[i]).collect();
    let lo = |s: &[i64], x: i64| s.partition_point(|&v| v <= x);
    let hi = |s: &[i64], x: i64| s.partition_point(|&v| v < x);
    let check = |i: usize| -> bool {
        // same orientation: |a_i - a_j| and |b_i - b_j| in (e, T)
        let (s, e) = (lo(&sa, a[i] - threshold), hi(&sa, a[i] + threshold));
        for &j in &by_a[s..e] {
            if between((a[i] - a[j]).abs(), pos_error, threshold) && between((b[i] - b[j]).abs(), pos_error, threshold) {
                return true;
            }
        }
        // swapped: |a_i - b_j| and |b_i - a_j| in (e, T), j != i
        let (s, e) = (lo(&sb, a[i] - threshold), hi(&sb, a[i] + threshold));
        for &j in &by_b[s..e] {
            if j != i
                && between((a[i] - b[j]).abs(), pos_error, threshold)
                && between((b[i] - a[j]).abs(), pos_error, threshold)
            {
                return true;
            }
        }
        false
    };
    if n > 4096 {
        (0..n).into_par_iter().map(check).collect()
    } else {
        (0..n).map(check).collect()
    }
}

/// `calc_limits`: min / max contact position of each chromosome.
pub fn calc_limits(d: &ContactDict) -> BTreeMap<u32, (i64, i64)> {
    let mut lim: BTreeMap<u32, (i64, i64)> = BTreeMap::new();
    for (&(ca, cb), contacts) in d {
        if contacts.is_empty() {
            continue;
        }
        for (chrom, side) in [(ca, 0), (cb, 1)] {
            let it = contacts.iter().map(|c| if side == 0 { c.pos_a } else { c.pos_b });
            let mn = it.clone().min().unwrap();
            let mx = it.max().unwrap();
            let e = lim.entry(chrom).or_insert((mn, mx));
            e.0 = e.0.min(mn);
            e.1 = e.1.max(mx);
        }
    }
    lim
}

/// `calc_bins`: particle start positions, aligned to multiples of the
/// particle size, covering every contact of the chromosome.
pub fn calc_bins(limits: &BTreeMap<u32, (i64, i64)>, particle_size: i64) -> BTreeMap<u32, Vec<i64>> {
    let mut bins = BTreeMap::new();
    for (&chrom, &(start, end)) in limits {
        let first = start.div_euclid(particle_size);
        let last = 1 + (end - 1).div_euclid(particle_size);
        let mut v: Vec<i64> = (first..last).map(|k| k * particle_size).collect();
        if v.is_empty() {
            // (original: an empty chromosome; cannot hold its contacts)
            v.push(first * particle_size);
        }
        bins.insert(chrom, v);
    }
    bins
}

/// `numpy.searchsorted(v, x, side='right')`.
#[inline]
pub fn searchsorted_right(v: &[i64], x: i64) -> usize {
    v.partition_point(|&p| p <= x)
}

/// `numpy.interp` for one coordinate column: particle coordinates `fp` at
/// positions `xp` (ascending) evaluated at `x`, clamped at the ends.
pub fn interp(x: f64, xp: &[i64], fp: impl Fn(usize) -> f64) -> f64 {
    let n = xp.len();
    if n == 1 || x <= xp[0] as f64 {
        return fp(0);
    }
    if x >= xp[n - 1] as f64 {
        return fp(n - 1);
    }
    // xp[k] <= x < xp[k+1]
    let k = xp.partition_point(|&p| (p as f64) <= x) - 1;
    let (x0, x1) = (xp[k] as f64, xp[k + 1] as f64);
    let (f0, f1) = (fp(k), fp(k + 1));
    let slope = (f1 - f0) / (x1 - x0);
    slope * (x - x0) + f0
}

/// Particle structure of one stage: chromosomes in id order, their particle
/// start positions, and the coordinates of every model (concatenated).
#[derive(Clone, Debug)]
pub struct Structure {
    pub chroms: Vec<u32>,
    pub seq_pos: Vec<Vec<i64>>,
    pub offsets: Vec<usize>,
    pub coords: Vec<Vec<[f64; 3]>>,
}

impl Structure {
    pub fn new(seq_pos_dict: &BTreeMap<u32, Vec<i64>>) -> Structure {
        let chroms: Vec<u32> = seq_pos_dict.keys().copied().collect();
        let seq_pos: Vec<Vec<i64>> = seq_pos_dict.values().cloned().collect();
        let mut offsets = vec![0usize];
        for s in &seq_pos {
            offsets.push(offsets.last().unwrap() + s.len());
        }
        Structure { chroms, seq_pos, offsets, coords: vec![] }
    }
    pub fn n_particles(&self) -> usize {
        *self.offsets.last().unwrap()
    }
    /// The same chains without coordinates.
    pub fn clone_layout(&self) -> Structure {
        Structure { chroms: self.chroms.clone(), seq_pos: self.seq_pos.clone(), offsets: self.offsets.clone(), coords: vec![] }
    }
    pub fn n_models(&self) -> usize {
        self.coords.len()
    }
    pub fn chrom_slot(&self, chrom: u32) -> Option<usize> {
        self.chroms.binary_search(&chrom).ok()
    }
    /// Coordinates of chromosome `slot` in model `m`.
    pub fn chrom_coords(&self, m: usize, slot: usize) -> &[[f64; 3]] {
        &self.coords[m][self.offsets[slot]..self.offsets[slot + 1]]
    }
    /// Interpolated coordinate of sequence position `pos` of chromosome
    /// `slot` in model `m` (`get_interpolated_coords`).
    pub fn interp_coord(&self, m: usize, slot: usize, pos: f64) -> [f64; 3] {
        let c = self.chrom_coords(m, slot);
        let xp = &self.seq_pos[slot];
        [
            interp(pos, xp, |k| c[k][0]),
            interp(pos, xp, |k| c[k][1]),
            interp(pos, xp, |k| c[k][2]),
        ]
    }
}

/// `remove_violated_contacts`: drop contacts whose 3-D distance, averaged
/// over the models of the previous stage, is not below `threshold`.
/// Chromosome pairs not in the previous structure are dropped.
pub fn remove_violated_contacts(d: &ContactDict, prev: &Structure, threshold: f64) -> ContactDict {
    let mut out: ContactDict = BTreeMap::new();
    let nm = prev.n_models();
    for (&(ca, cb), contacts) in d {
        let (Some(sa), Some(sb)) = (prev.chrom_slot(ca), prev.chrom_slot(cb)) else {
            continue;
        };
        let keep: Vec<Contact> = contacts
            .par_iter()
            .filter(|c| {
                let mut s = 0.0;
                for m in 0..nm {
                    let p = prev.interp_coord(m, sa, c.pos_a as i32 as f64);
                    let q = prev.interp_coord(m, sb, c.pos_b as i32 as f64);
                    let (dx, dy, dz) = (p[0] - q[0], p[1] - q[1], p[2] - q[2]);
                    s += (dx * dx + dy * dy + dz * dz).sqrt();
                }
                (s / nm as f64) < threshold
            })
            .copied()
            .collect();
        out.insert((ca, cb), keep);
    }
    out
}

/// numpy.percentile with linear interpolation.
pub fn percentile(values: &[f64], q: f64) -> f64 {
    let mut v: Vec<f64> = values.to_vec();
    v.sort_by(|a, b| a.partial_cmp(b).unwrap());
    let n = v.len();
    if n == 1 {
        return v[0];
    }
    let pos = q / 100.0 * (n - 1) as f64;
    let lo = pos.floor() as usize;
    let hi = (lo + 1).min(n - 1);
    let frac = pos - lo as f64;
    v[lo] + (v[hi] - v[lo]) * frac
}

/// `resolve_3d_ambiguous`: within each ambiguity group of several contacts,
/// keep the contacts whose model-averaged distance is close to the group's
/// closest one (and below a percentile threshold).
pub fn resolve_3d_ambiguous(d: &ContactDict, prev: &Structure, percentile_threshold: f64, min_bead_sep: i64) -> ContactDict {
    struct Item {
        key: (u32, u32),
        idx: usize,
        dist: f64,
        sep: i64,
    }
    // particle index of each contact end: searchsorted(side='right') clamped
    // to the last particle (as the original; note: no "- 1" here)
    let pidx = |slot: usize, pos: i64| -> usize {
        let sp = &prev.seq_pos[slot];
        searchsorted_right(sp, pos).min(sp.len() - 1)
    };
    let mut groups: BTreeMap<i64, Vec<Item>> = BTreeMap::new();
    for (&(ca, cb), contacts) in d {
        if prev.chrom_slot(ca).is_none() || prev.chrom_slot(cb).is_none() {
            continue;
        }
        for (idx, c) in contacts.iter().enumerate() {
            groups.entry(c.ambig).or_default().push(Item {
                key: (ca, cb),
                idx,
                dist: 0.0,
                sep: 0,
            });
        }
    }
    groups.retain(|_, v| v.len() > 1);
    let nm = prev.n_models();
    let mut min_dists: HashMap<i64, f64> = HashMap::new();
    let mut min_seps: HashMap<i64, i64> = HashMap::new();
    let mut closest_nz = vec![];
    for (&g, items) in groups.iter_mut() {
        for it in items.iter_mut() {
            let (ca, cb) = it.key;
            let c = d[&it.key][it.idx];
            let (sa, sb) = (prev.chrom_slot(ca).unwrap(), prev.chrom_slot(cb).unwrap());
            let (i, j) = (pidx(sa, c.pos_a), pidx(sb, c.pos_b));
            let mut s2 = 0.0;
            for m in 0..nm {
                let p = prev.chrom_coords(m, sa)[i];
                let q = prev.chrom_coords(m, sb)[j];
                let (dx, dy, dz) = (p[0] - q[0], p[1] - q[1], p[2] - q[2]);
                s2 += dx * dx + dy * dy + dz * dz;
            }
            it.dist = (s2 / nm as f64).sqrt();
            it.sep = if ca == cb { (j as i64 - i as i64).abs() } else { 99999 };
        }
        let min_sep = items.iter().map(|x| x.sep).min().unwrap();
        let min_dist = items.iter().map(|x| x.dist).fold(f64::INFINITY, f64::min);
        min_seps.insert(g, min_sep);
        min_dists.insert(g, min_dist);
        if min_dist > 0.0 {
            closest_nz.push(min_dist);
        }
    }
    let mut remove: HashSet<((u32, u32), usize)> = HashSet::new();
    if !closest_nz.is_empty() {
        let dist_thresh = percentile(&closest_nz, percentile_threshold);
        for (g, items) in &groups {
            let (min_dist, min_sep) = (min_dists[g], min_seps[g]);
            for it in items {
                let trans = it.key.0 != it.key.1;
                if min_dist == 0.0 && trans {
                    remove.insert((it.key, it.idx));
                    continue;
                }
                if min_sep < min_bead_sep && trans {
                    remove.insert((it.key, it.idx));
                    continue;
                }
                if it.dist != min_dist && it.dist > min_dist + dist_thresh / 2.0 {
                    remove.insert((it.key, it.idx));
                    continue;
                }
                if it.dist > dist_thresh {
                    remove.insert((it.key, it.idx));
                }
            }
        }
    }
    let mut out: ContactDict = BTreeMap::new();
    for (&key, contacts) in d {
        let kept: Vec<Contact> = contacts
            .iter()
            .enumerate()
            .filter(|(i, _)| !remove.contains(&(key, *i)))
            .map(|(_, c)| *c)
            .collect();
        if !kept.is_empty() {
            out.insert(key, kept);
        }
    }
    out
}

#[cfg(test)]
mod tests {
    use super::*;

    fn brute_supported(c: &[Contact], t: i64, e: i64) -> Vec<bool> {
        (0..c.len())
            .map(|i| {
                (0..c.len()).any(|j| {
                    (between((c[i].pos_a - c[j].pos_a).abs(), e, t) && between((c[i].pos_b - c[j].pos_b).abs(), e, t))
                        || (j != i
                            && between((c[i].pos_a - c[j].pos_b).abs(), e, t)
                            && between((c[i].pos_b - c[j].pos_a).abs(), e, t))
                })
            })
            .collect()
    }

    #[test]
    fn isolation_filter_matches_brute_force() {
        let mut r = crate::rng::Rng::new(3);
        let c: Vec<Contact> = (0..3000)
            .map(|k| Contact {
                pos_a: (r.uniform() * 5e7) as i64,
                pos_b: (r.uniform() * 5e7) as i64,
                ambig: k,
                number: k as u32,
            })
            .collect();
        for t in [200_000i64, 2_000_000] {
            assert_eq!(supported_contacts(&c, t, 100), brute_supported(&c, t, 100));
        }
    }

    #[test]
    fn interp_matches_numpy_semantics() {
        let xp = vec![0i64, 10, 20];
        let fp = [0.0, 1.0, 4.0];
        assert_eq!(interp(-5.0, &xp, |k| fp[k]), 0.0);
        assert_eq!(interp(25.0, &xp, |k| fp[k]), 4.0);
        assert_eq!(interp(10.0, &xp, |k| fp[k]), 1.0);
        assert!((interp(15.0, &xp, |k| fp[k]) - 2.5).abs() < 1e-12);
    }

    #[test]
    fn bins_cover_limits() {
        let mut lim = BTreeMap::new();
        lim.insert(0u32, (3_150_000i64, 3_450_000i64));
        let b = calc_bins(&lim, 100_000);
        assert_eq!(b[&0], vec![3_100_000, 3_200_000, 3_300_000, 3_400_000]);
    }
}
