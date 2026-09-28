//! The structure calculation of the 2017 NucDynamics code (`master` branch
//! of tjs23/nuc_dynamics: `nuc_dynamics.py` + `dyn_util.pyx`), the code that
//! produced the Stevens et al. 2017 structures.
//!
//! Units: particle radius 1, mass 1; no bead-size scaling.  Protocol:
//! isolated contacts removed once; per stage particles binned from the
//! current contacts, restraints from binned contact counts (power law),
//! random start in a ball of radius 10 (first stage) or interpolated
//! coordinates, simulated annealing, contacts violated by >= 6 radii (mean
//! over models) removed for good before every stage finer than 0.5 Mb.
//! The number of models is fixed; models are not selected or superposed.

use crate::contacts::{build_contact_dict, contact_count, supported_contacts, ContactDict, Structure};
use crate::dynamics::{RestraintForm, System, V3};
use crate::params::Params;
use crate::pipeline::{Input, Output, StageEngine, StageLog};
use crate::restraints::{Restraint, RestraintSet};
use crate::rng::{Rng, STREAM_COORDS};
use rayon::prelude::*;
use std::collections::{BTreeMap, HashMap};
use std::time::Instant;

/// `remove_isolated_contacts` (+ `getSupportedPairs`): in place, one
/// threshold for cis and trans, ambiguity ignored.
pub fn remove_isolated_contacts(d: &mut ContactDict, threshold: i64, pos_error: i64) {
    for contacts in d.values_mut() {
        if contacts.is_empty() {
            continue;
        }
        let keep = supported_contacts(contacts, threshold, pos_error);
        let kept: Vec<_> = contacts.iter().zip(&keep).filter(|(_, &k)| k).map(|(c, _)| *c).collect();
        *contacts = kept;
    }
}

/// Particle positions of every chromosome (`calc_restraints` binning):
/// `floor(min/s)*s .. s*ceil(float32(max)/s)` inclusive.  A chromosome with
/// no contacts gets a single particle at 0.
pub fn calc_particles(d: &ContactDict, chroms: &[u32], ps: i64) -> BTreeMap<u32, Vec<i64>> {
    // limits with the original's "0 = unset" convention
    let mut lim: HashMap<u32, (i64, i64)> = chroms.iter().map(|&c| (c, (0, 0))).collect();
    for (&(ca, cb), contacts) in d {
        for c in contacts {
            for (chrom, p) in [(ca, c.pos_a as i32 as i64), (cb, c.pos_b as i32 as i64)] {
                let e = lim.get_mut(&chrom).unwrap();
                if e.0 == 0 || p < e.0 {
                    e.0 = p;
                }
                if p > e.1 {
                    e.1 = p;
                }
            }
        }
    }
    let mut out = BTreeMap::new();
    for &c in chroms {
        let (mn, mx) = lim[&c];
        let first = ps * mn.div_euclid(ps);
        let last = ps * ((mx as i32 as f32) / (ps as i32 as f32)).ceil() as i32 as i64;
        let v: Vec<i64> = (0..).map(|k| first + k * ps).take_while(|&x| x < last + ps).collect();
        out.insert(c, v);
    }
    out
}

/// Contact restraints from binned contact counts (`calc_restraints`): a
/// contact end at p goes to the first particle at or after p; one restraint
/// per non-empty (i, j) cell of each chromosome pair, target distance
/// `N ** power_law` (float32 arithmetic as the original), bounds
/// `lower`/`upper` x target.
pub fn contact_restraints(d: &ContactDict, st: &Structure, power_law: f64, lower: f64, upper: f64) -> (Vec<Restraint>, usize) {
    let (exp32, lo32, hi32) = (power_law as f32, lower as f32 as f64, upper as f32 as f64);
    let mut out = vec![];
    let mut n_used = 0usize;
    for (&(ca, cb), contacts) in d {
        let (Some(sa), Some(sb)) = (st.chrom_slot(ca), st.chrom_slot(cb)) else {
            continue;
        };
        let (pa, pb) = (&st.seq_pos[sa], &st.seq_pos[sb]);
        let mut bins: BTreeMap<(usize, usize), u32> = BTreeMap::new();
        for c in contacts {
            let j = pa.partition_point(|&x| x < c.pos_a as i32 as i64);
            if j >= pa.len() {
                continue;
            }
            let k = pb.partition_point(|&x| x < c.pos_b as i32 as i64);
            if k >= pb.len() {
                continue;
            }
            *bins.entry((j, k)).or_insert(0) += 1;
            n_used += 1;
        }
        for ((j, k), cnt) in bins {
            let dist = (1.0f32 * (cnt as f32).powf(exp32)) as f64;
            out.push(Restraint {
                i: (st.offsets[sa] + j) as u32,
                j: (st.offsets[sb] + k) as u32,
                lo: dist * lo32,
                hi: dist * hi32,
                ambig: 0,
                weight: 1.0,
            });
        }
    }
    (out, n_used)
}

/// Backbone restraints (`concatenate_restraints`), float32 bounds.
pub fn backbone_restraints(st: &Structure, ps: i64, lower: f64, upper: f64) -> Vec<Restraint> {
    let (bbl, bbu) = (lower as f32 as f64, upper as f32 as f64);
    let mut out = vec![];
    for (slot, sp) in st.seq_pos.iter().enumerate() {
        let off = st.offsets[slot];
        for k in 0..sp.len().saturating_sub(1) {
            let dist = (sp[k + 1] - sp[k]) as f64 / ps as f64;
            out.push(Restraint {
                i: (off + k) as u32,
                j: (off + k + 1) as u32,
                lo: dist * bbl,
                hi: dist * bbu,
                ambig: 0,
                weight: 1.0,
            });
        }
    }
    out
}

/// `getInterpolatedCoords` for one position: nearest previous particle,
/// bracketing pair, linear interpolation with a float32 fraction; clamped
/// at the ends.
pub fn interpolate(p: i64, prev: &[i64], coords: &[V3]) -> V3 {
    let m = prev.len();
    // nearest previous particle; ties go to the lower one (the original's
    // linear scan stops at the first strictly larger distance)
    let k = prev.partition_point(|&x| x < p);
    let mut p1 = if k == 0 {
        0
    } else if k == m {
        m - 1
    } else if prev[k] - p < p - prev[k - 1] {
        k
    } else {
        k - 1
    };
    let mut dmin = p - prev[p1];
    let p2;
    if dmin == 0 {
        p2 = p1;
    } else if dmin > 0 {
        p2 = (p1 + 1).min(m - 1);
    } else {
        p2 = p1;
        p1 = p1.saturating_sub(1);
        dmin = p - prev[p1];
    }
    if prev[p2] == prev[p1] {
        coords[p1]
    } else {
        let f = ((dmin as i32 as f32) / ((prev[p2] - prev[p1]) as i32 as f32)) as f64;
        let g = 1.0 - f;
        let (a, b) = (coords[p1], coords[p2]);
        [g * a[0] + f * b[0], g * a[1] + f * b[1], g * a[2] + f * b[2]]
    }
}

/// `remove_violated_contacts`: in place, contacts whose model-averaged
/// distance (interpolated ends) is not below `threshold` are removed.
pub fn remove_violated_contacts(d: &mut ContactDict, prev: &Structure, threshold: f64) {
    let nm = prev.n_models();
    for (&(ca, cb), contacts) in d.iter_mut() {
        let (Some(sa), Some(sb)) = (prev.chrom_slot(ca), prev.chrom_slot(cb)) else {
            continue;
        };
        let keep: Vec<bool> = contacts
            .par_iter()
            .map(|c| {
                let mut s = 0.0;
                for m in 0..nm {
                    let a = interpolate(c.pos_a as i32 as i64, &prev.seq_pos[sa], prev.chrom_coords(m, sa));
                    let b = interpolate(c.pos_b as i32 as i64, &prev.seq_pos[sb], prev.chrom_coords(m, sb));
                    let (dx, dy, dz) = (a[0] - b[0], a[1] - b[1], a[2] - b[2]);
                    s += (dx * dx + dy * dy + dz * dz).sqrt();
                }
                (s / nm as f64) < threshold
            })
            .collect();
        let kept: Vec<_> = contacts.iter().zip(&keep).filter(|(_, &k)| k).map(|(c, _)| *c).collect();
        *contacts = kept;
    }
}

/// `get_random_coords`: every particle uniform in a ball (rejection sampling in the cube).
pub fn random_coords(n: usize, radius: f64, rng: &mut Rng) -> Vec<V3> {
    let r2 = radius * radius;
    (0..n)
        .map(|_| loop {
            let x = radius * (2.0 * rng.uniform() - 1.0);
            let y = radius * (2.0 * rng.uniform() - 1.0);
            let z = radius * (2.0 * rng.uniform() - 1.0);
            if x * x + y * y + z * z < r2 {
                break [x, y, z];
            }
        })
        .collect()
}

/// Particles, restraints and start coordinates of one stage (`anneal_genome`
/// before the annealing).
pub fn setup_stage(
    d: &ContactDict,
    chroms: &[u32],
    num_models: usize,
    particle_size: f64,
    prev: Option<&Structure>,
    p: &Params,
    stage: usize,
) -> Result<(Structure, System, usize), String> {
    let ps = particle_size as i32 as i64;
    let seq_pos = calc_particles(d, chroms, ps);
    let mut st = Structure::new(&seq_pos);
    let n = st.n_particles();
    let coords: Vec<Vec<V3>> = match prev {
        Some(pr) if pr.n_models() == num_models => {
            if pr.n_particles() == n {
                pr.coords.clone()
            } else {
                (0..num_models)
                    .map(|m| {
                        let mut c = Vec::with_capacity(n);
                        for (slot, &chrom) in st.chroms.iter().enumerate() {
                            let ps_ = pr.chrom_slot(chrom).expect("chromosome set is fixed");
                            for &x in &st.seq_pos[slot] {
                                c.push(interpolate(x, &pr.seq_pos[ps_], pr.chrom_coords(m, ps_)));
                            }
                        }
                        c
                    })
                    .collect()
            }
        }
        _ => (0..num_models)
            .map(|m| {
                let mut rng = Rng::from_keys(&[p.seed, stage as u64, m as u64, STREAM_COORDS]);
                random_coords(n, p.random_radius, &mut rng)
            })
            .collect(),
    };
    st.coords = coords;
    let (mut rest, n_used) = contact_restraints(d, &st, p.dist_power_law, p.contact_dist_lower, p.contact_dist_upper);
    let mut all = backbone_restraints(&st, ps, p.backbone_dist_lower, p.backbone_dist_upper);
    all.append(&mut rest);
    let groups: Vec<u32> = (0..=all.len() as u32).collect();
    let rs = RestraintSet { rest: all, groups, n_contacts: n_used };
    let sys = System::new(n, vec![1.0; n], vec![1.0; n], &rs).with_form(RestraintForm::Master2017);
    Ok((st, sys, n_used))
}

fn log(p: &Params, msg: &str) {
    if p.verbose {
        eprintln!("[uchrom_nucdyn] {msg}");
    }
}

/// `calc_genome_structure` of the 2017 code.
pub fn calc_genome_structure(input: &Input, p: &Params, engine: &mut dyn StageEngine) -> Result<Output, String> {
    p.validate()?;
    let t0 = Instant::now();
    let n_models = p.n_models;
    let mut d = build_contact_dict(input.chr_a, input.pos_a, input.chr_b, input.pos_b, input.ambig, input.active, true);
    // every chromosome that appears in the input, in name order
    let mut chroms: Vec<u32> = input.chr_a.iter().chain(input.chr_b).copied().collect();
    chroms.sort_unstable();
    chroms.dedup();
    log(p, &format!("total number of contacts = {}", contact_count(&d)));
    remove_isolated_contacts(&mut d, p.isolation_threshold_cis, p.isolation_pos_error);
    log(p, &format!("contacts after removing isolated = {}", contact_count(&d)));
    let mut prev: Option<Structure> = None;
    let mut stages = vec![];
    let mut last_ps = p.particle_sizes[0];
    for (stage, &ps) in p.particle_sizes.iter().enumerate() {
        let ts = Instant::now();
        last_ps = ps;
        if stage > 0 && ps < 0.5e6 {
            if let Some(pr) = prev.as_ref() {
                remove_violated_contacts(&mut d, pr, p.violated_threshold_2017);
                log(p, &format!("contacts after removing violated = {}", contact_count(&d)));
            }
        }
        let (mut st, sys, n_used) = setup_stage(&d, &chroms, n_models, ps, prev.as_ref(), p, stage)?;
        let schedule = crate::params::anneal_schedule(p.temp_start, p.temp_end, p.temp_steps_for(stage), 1.0);
        let t_prep = ts.elapsed().as_secs_f64();
        log(
            p,
            &format!(
                "stage {} ({} kb): {} particles, {} contacts, {} restraints, {} models",
                stage + 1,
                ps / 1e3,
                sys.n,
                n_used,
                sys.n_restraints(),
                n_models
            ),
        );
        let td = Instant::now();
        let start = std::mem::take(&mut st.coords);
        let mut out = engine.anneal(&sys, start, &schedule, p.dyn_steps_for(stage), p.dist_force_const, 1.0, stage, p)?;
        for c in out.iter_mut() {
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
        st.coords = out;
        let t_dyn = td.elapsed().as_secs_f64();
        log(p, &format!("stage {} done in {:.2} s ({:.2} s dynamics)", stage + 1, t_prep + t_dyn, t_dyn));
        stages.push(StageLog {
            stage,
            particle_size: ps,
            bead_size: 1.0,
            n_models,
            n_particles: sys.n,
            n_contacts: n_used,
            n_restraints: sys.n_restraints(),
            dist_force_const: p.dist_force_const,
            temp_steps: p.temp_steps_for(stage),
            dynamics_steps: p.dyn_steps_for(stage),
            seconds_prepare: t_prep,
            seconds_dynamics: t_dyn,
            removed_models: vec![],
            device: engine.name(),
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
        particle_size: last_ps,
        stages,
        seconds_total: t0.elapsed().as_secs_f64(),
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    fn interp_linear_scan(p: i64, prev: &[i64], coords: &[V3]) -> V3 {
        // literal transcription of the original's scan for the test
        let m = prev.len();
        let mut p1 = 0usize;
        let mut dmin = p - prev[0];
        for j in 1..m {
            let d = p - prev[j];
            if d.abs() < dmin.abs() {
                p1 = j;
                dmin = d;
            } else if d.abs() > dmin.abs() {
                break;
            }
        }
        let p2;
        if dmin == 0 {
            p2 = p1;
        } else if dmin > 0 {
            p2 = (p1 + 1).min(m - 1);
        } else {
            p2 = p1;
            p1 = p1.saturating_sub(1);
            dmin = p - prev[p1];
        }
        if prev[p2] == prev[p1] {
            coords[p1]
        } else {
            let f = ((dmin as f32) / ((prev[p2] - prev[p1]) as f32)) as f64;
            let g = 1.0 - f;
            let (a, b) = (coords[p1], coords[p2]);
            [g * a[0] + f * b[0], g * a[1] + f * b[1], g * a[2] + f * b[2]]
        }
    }

    #[test]
    fn interpolation_matches_linear_scan() {
        let prev: Vec<i64> = (0..50).map(|k| 3_000_000 + k * 400_000).collect();
        let coords: Vec<V3> = (0..50).map(|k| [k as f64, (k * k) as f64 * 0.1, -(k as f64)]).collect();
        let mut r = Rng::new(4);
        for _ in 0..5000 {
            let p = (r.uniform() * 2.4e7) as i64 + 2_000_000;
            assert_eq!(interpolate(p, &prev, &coords), interp_linear_scan(p, &prev, &coords), "p = {p}");
        }
        for &p in &[3_000_000, 3_200_000, 3_400_000, 22_600_000, 30_000_000, 0] {
            assert_eq!(interpolate(p, &prev, &coords), interp_linear_scan(p, &prev, &coords), "p = {p}");
        }
    }

    #[test]
    fn particles_include_both_ends() {
        let mut d: ContactDict = BTreeMap::new();
        d.insert(
            (0, 0),
            vec![crate::contacts::Contact { pos_a: 3_050_000, pos_b: 3_420_000, ambig: 1, number: 0 }],
        );
        let b = calc_particles(&d, &[0, 1], 100_000);
        assert_eq!(b[&0], vec![3_000_000, 3_100_000, 3_200_000, 3_300_000, 3_400_000, 3_500_000]);
        assert_eq!(b[&1], vec![0]);
    }
}
