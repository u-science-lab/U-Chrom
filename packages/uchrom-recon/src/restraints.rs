//! Distance restraints: contact restraints (`calc_restraints`), backbone
//! restraints (`backbone_restraints`), concatenation, binning of identical
//! restraints (`bin_restraints`) and ambiguity offsets
//! (`calc_ambiguity_offsets`).

use crate::contacts::{searchsorted_right, ContactDict, Structure};

#[derive(Clone, Copy, Debug, PartialEq)]
pub struct Restraint {
    pub i: u32,
    pub j: u32,
    pub lo: f64,
    pub hi: f64,
    pub ambig: i64,
    pub weight: f64,
}

/// Restraint set of one stage, ready for the dynamics.
#[derive(Clone, Debug)]
pub struct RestraintSet {
    pub rest: Vec<Restraint>,
    /// Group boundaries: group g = rest[groups[g]..groups[g+1]].
    pub groups: Vec<u32>,
    /// Number of contacts (sum of contact-restraint weights before binning).
    pub n_contacts: usize,
}

/// Build restraints for the particles of `st` (bins from the stage contacts).
pub fn build_restraints(
    d: &ContactDict,
    st: &Structure,
    particle_size: i64,
    bead: f64,
    contact_lower: f64,
    contact_upper: f64,
    backbone_lower: f64,
    backbone_upper: f64,
) -> RestraintSet {
    // restraints grouped by chromosome pair, in sorted key order; within a
    // pair the contact restraints come before the backbone ones (merge_dicts)
    let mut by_pair: std::collections::BTreeMap<(u32, u32), Vec<Restraint>> = Default::default();
    let mut n_contacts = 0usize;
    for (&(ca, cb), contacts) in d {
        if contacts.is_empty() {
            continue;
        }
        let (Some(sa), Some(sb)) = (st.chrom_slot(ca), st.chrom_slot(cb)) else {
            continue;
        };
        let (pa, pb) = (&st.seq_pos[sa], &st.seq_pos[sb]);
        let v = by_pair.entry((ca, cb)).or_default();
        for c in contacts {
            let ia = searchsorted_right(pa, c.pos_a) as i64 - 1;
            let ib = searchsorted_right(pb, c.pos_b) as i64 - 1;
            // bins start at or below every contact, so ia, ib >= 0
            let ia = ia.max(0) as usize + st.offsets[sa];
            let ib = ib.max(0) as usize + st.offsets[sb];
            v.push(Restraint {
                i: ia as u32,
                j: ib as u32,
                lo: contact_lower * bead,
                hi: contact_upper * bead,
                ambig: c.ambig,
                weight: 1.0,
            });
            n_contacts += 1;
        }
    }
    for (slot, &chrom) in st.chroms.iter().enumerate() {
        let sp = &st.seq_pos[slot];
        let v = by_pair.entry((chrom, chrom)).or_default();
        let off = st.offsets[slot];
        for k in 0..sp.len().saturating_sub(1) {
            let gap = (sp[k + 1] - sp[k]) as f64 / particle_size as f64;
            v.push(Restraint {
                i: (off + k) as u32,
                j: (off + k + 1) as u32,
                lo: gap * (backbone_lower * bead),
                hi: gap * (backbone_upper * bead),
                ambig: 0,
                weight: 1.0,
            });
        }
    }
    let all: Vec<Restraint> = by_pair.into_values().flatten().collect();
    let rest = bin_restraints(all);
    let groups = ambiguity_offsets(&rest);
    RestraintSet { rest, groups, n_contacts }
}

/// `bin_restraints`: order the particle pair, set the ambiguity of
/// single-member groups to 0, merge identical (ambiguity, pair, bounds)
/// restraints and sum their weights.  Output sorted by ambiguity, pair,
/// bounds (the original's `numpy.unique` order).
pub fn bin_restraints(mut r: Vec<Restraint>) -> Vec<Restraint> {
    use std::collections::HashMap;
    for x in r.iter_mut() {
        if x.i > x.j {
            std::mem::swap(&mut x.i, &mut x.j);
        }
    }
    let mut counts: HashMap<i64, usize> = HashMap::new();
    for x in &r {
        *counts.entry(x.ambig).or_insert(0) += 1;
    }
    for x in r.iter_mut() {
        if counts[&x.ambig] == 1 {
            x.ambig = 0;
        }
    }
    r.sort_by(|a, b| {
        (a.ambig, a.i, a.j)
            .cmp(&(b.ambig, b.i, b.j))
            .then(a.lo.partial_cmp(&b.lo).unwrap())
            .then(a.hi.partial_cmp(&b.hi).unwrap())
    });
    let mut out: Vec<Restraint> = Vec::with_capacity(r.len());
    for x in r {
        match out.last_mut() {
            Some(l) if l.ambig == x.ambig && l.i == x.i && l.j == x.j && l.lo == x.lo && l.hi == x.hi => {
                l.weight += x.weight;
            }
            _ => out.push(x),
        }
    }
    out
}

/// `calc_ambiguity_offsets`: a new group starts at every restraint with
/// ambiguity 0 and wherever the ambiguity changes.
pub fn ambiguity_offsets(r: &[Restraint]) -> Vec<u32> {
    let n = r.len();
    let mut starts = vec![false; n + 1];
    starts[0] = true;
    starts[n] = true;
    for k in 0..n {
        if r[k].ambig == 0 {
            starts[k] = true;
        }
        if k > 0 && r[k].ambig != r[k - 1].ambig {
            starts[k] = true;
        }
    }
    starts.iter().enumerate().filter(|(_, &s)| s).map(|(k, _)| k as u32).collect()
}

#[cfg(test)]
mod tests {
    use super::*;

    fn r(i: u32, j: u32, a: i64) -> Restraint {
        Restraint { i, j, lo: 0.8, hi: 1.2, ambig: a, weight: 1.0 }
    }

    #[test]
    fn binning_merges_duplicates_and_orders_pairs() {
        let out = bin_restraints(vec![r(5, 2, 7), r(2, 5, 8), r(1, 3, 9), r(1, 3, 9)]);
        // 7 and 8 are singletons -> ambiguity 0 -> merged; group 9 has 2 members -> merged, ambig kept
        assert_eq!(out.len(), 2);
        assert_eq!((out[0].i, out[0].j, out[0].ambig, out[0].weight), (2, 5, 0, 2.0));
        assert_eq!((out[1].i, out[1].j, out[1].ambig, out[1].weight), (1, 3, 9, 2.0));
    }

    #[test]
    fn offsets_split_zero_groups() {
        let v = vec![r(0, 2, 0), r(0, 3, 0), r(1, 4, 5), r(1, 5, 5), r(2, 6, 6)];
        assert_eq!(ambiguity_offsets(&v), vec![0, 1, 2, 4, 5]);
    }
}
