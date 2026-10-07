//! Default-behaviour regression: a fixed-seed small CPU run of the faithful
//! IGM 1.0 protocol must stay bit-identical when opt-in options are added.
//! The reference hashes were recorded before the IGM-Plus options existed
//! (macOS arm64, f64); other platforms may differ in libm rounding, so the
//! exact check runs on macOS / aarch64 only and a coarse check elsewhere.

use crate::igm::driver::run_population;
use crate::igm::params::{demo_stages, IgmParams, Relax};

/// FNV-1a over the f64 bit patterns.
pub fn hash_f64(v: impl IntoIterator<Item = f64>) -> u64 {
    let mut h: u64 = 0xcbf2_9ce4_8422_2325;
    for x in v {
        for b in x.to_bits().to_le_bytes() {
            h ^= b as u64;
            h = h.wrapping_mul(0x0000_0100_0000_01b3);
        }
    }
    h
}

type Problem = (Vec<u32>, Vec<i64>, Vec<i64>, Vec<u32>, Vec<u32>, Vec<f64>);

/// Two chromosomes x 15 bins; neighbours, i/i+4 intra pairs, five inter pairs.
pub fn small_problem() -> Problem {
    let n = 15usize;
    let chrom: Vec<u32> = (0..2 * n).map(|i| (i / n) as u32).collect();
    let start: Vec<i64> = (0..2 * n).map(|i| ((i % n) * 1_000_000) as i64).collect();
    let end: Vec<i64> = start.iter().map(|&x| x + 1_000_000).collect();
    let (mut pi, mut pj, mut pv) = (vec![], vec![], vec![]);
    for c in 0..2u32 {
        for k in 0..n as u32 - 1 {
            pi.push(c * n as u32 + k);
            pj.push(c * n as u32 + k + 1);
            pv.push(1.0);
        }
        for k in 0..n as u32 - 4 {
            pi.push(c * n as u32 + k);
            pj.push(c * n as u32 + k + 4);
            pv.push(0.25 + 0.05 * (k % 3) as f64);
        }
    }
    for k in 0..5u32 {
        pi.push(k);
        pj.push(n as u32 + 2 * k);
        pv.push(0.15 + 0.1 * k as f64);
    }
    (chrom, start, end, pi, pj, pv)
}

pub fn small_params() -> IgmParams {
    let stages = demo_stages()
        .into_iter()
        .map(|mut s| {
            s.mdsteps /= 100;
            s
        })
        .collect();
    IgmParams {
        n_structures: 6,
        seed: 7,
        nucleus_radius: 1000.0,
        stages,
        relax: Some(Relax { mdsteps: 20, temperature: 1.0, max_velocity: 10.0 }),
        intra_sigma_list: vec![0.2],
        inter_sigma_list: vec![0.2],
        // never accepted: three A/M rounds at sigma 0.2 (iterative correction active)
        max_violations: 0.0,
        max_iterations: 3,
        cg_max_iter: 50,
        cg_max_eval: 50,
        n_threads: 2,
        ..Default::default()
    }
}

/// (coordinate hash, per-round violation-score hash, A-step d_act hash, rounds)
pub fn run_small(p: &IgmParams) -> (u64, u64, u64, usize) {
    let (c, s, e, pi, pj, pv) = small_problem();
    let pop = run_population(&c, &s, &e, &[2, 2], &pi, &pj, &pv, p, &mut |_, _| Ok(())).unwrap();
    let hc = hash_f64(pop.coords.iter().flat_map(|st| st.iter().flat_map(|q| q.iter().copied())));
    let hs = hash_f64(pop.out.rounds.iter().map(|r| r.violation_score));
    let ha = hash_f64(pop.out.last_res.iter().map(|r| r.d2_act));
    (hc, hs, ha, pop.out.rounds.len())
}

#[test]
fn default_run_is_unchanged() {
    let got = run_small(&small_params());
    eprintln!("default small run: coords {:#018x} scores {:#018x} actdist {:#018x} rounds {}", got.0, got.1, got.2, got.3);
    if cfg!(all(target_os = "macos", target_arch = "aarch64")) {
        assert_eq!(got, (REF_COORDS, REF_SCORES, REF_ACTDIST, REF_ROUNDS));
    } else {
        assert_eq!(got.3, REF_ROUNDS);
    }
}

/// Every opt-in option is wired through (changes the result) and runs on CPU
/// and, when an adapter exists, on the GPU.
#[test]
fn options_run_and_change_results() {
    let base = small_params();
    let def = run_small(&base);
    let variants: Vec<(&str, IgmParams)> = vec![
        ("bead_radius", IgmParams { bead_radius: 60.0, occupancy: 0.0, ..base.clone() }),
        ("occupancy_total_bp", IgmParams { occupancy_total_bp: 2.0 * 30.0 * 1e6 * 3.0, ..base.clone() }),
        ("no iterative correction", IgmParams { iterative_correction: false, ..base.clone() }),
        ("gp pooling", IgmParams { assignment_pooling: "gp".into(), ..base.clone() }),
        ("init_noise", IgmParams { init_noise: 5.0, ..base.clone() }),
        ("no envelope (EMber-pop)", IgmParams { nucleus_shape: "none".into(), ..base.clone() }),
        (
            "non-contact restraints (EMber-pop)",
            IgmParams { nucleus_shape: "none".into(), iterative_correction: false, noncontact_kspring: 0.5, noncontact_range: 2.0, advance_on_max_iterations: true, ..base.clone() },
        ),
        (
            "soft assignment (EMber-pop)",
            IgmParams { nucleus_shape: "none".into(), iterative_correction: false, noncontact_kspring: 0.5, assignment: "soft".into(), soft_commit: 0.9, advance_on_max_iterations: true, ..base.clone() },
        ),
    ];
    for (name, p) in &variants {
        let got = run_small(p);
        eprintln!("{name}: coords {:#018x} rounds {}", got.0, got.3);
        assert_ne!(got.0, def.0, "{name} did not change the population");
    }
    #[cfg(feature = "gpu")]
    {
        if crate::gpu::adapter_info().is_ok() {
            for (name, p) in variants {
                let p = IgmParams { device: "gpu".into(), ..p };
                let (c, s, e, pi, pj, pv) = small_problem();
                let pop = run_population(&c, &s, &e, &[2, 2], &pi, &pj, &pv, &p, &mut |_, _| Ok(())).unwrap();
                assert!(pop.coords.iter().flatten().flatten().all(|x| x.is_finite()), "{name} (gpu)");
                assert_eq!(pop.out.rounds.len(), 3, "{name} (gpu)");
            }
        }
    }
}

/// Pinned initial loci: placed, interpolated inside a chain, not across chains;
/// the relaxation log and the per-kind breakdown are reported.
#[test]
fn pinned_initialisation_and_reports() {
    use crate::igm::driver::{initial_population, run_population_with, InitPins};
    use crate::igm::genome::Genome;
    let (c, s, e, pi, pj, pv) = small_problem();
    let p = IgmParams { skip_relax_init: false, ..small_params() };
    let g = Genome::new(&c, &s, &e, &[2, 2], &p).unwrap();
    // structure 1: chr0 copy 0 bins 2 and 6, chr1 copy 1 bin 0 (15 = first bin of chr1)
    let pins = InitPins {
        structure: vec![1, 1, 1],
        hap: vec![2, 6, 15],
        copy: vec![0, 0, 1],
        xyz: vec![[100.0, 0.0, 0.0], [500.0, 40.0, 0.0], [-300.0, -300.0, 0.0]],
    };
    let resolved = pins.resolve(&g, p.n_structures).unwrap();
    let pop = initial_population(&g, &p, &resolved);
    let plain = initial_population(&g, &p, &[]);
    let b = |h: usize, copy: usize| g.copy_index[h][copy] as usize;
    assert_eq!(pop[1][b(2, 0)], [100.0, 0.0, 0.0]);
    assert_eq!(pop[1][b(6, 0)], [500.0, 40.0, 0.0]);
    assert_eq!(pop[1][b(15, 1)], [-300.0, -300.0, 0.0]);
    // bins 3..5 interpolated: bin 4 halfway
    assert!((pop[1][b(4, 0)][0] - 300.0).abs() < 1e-9 && (pop[1][b(4, 0)][1] - 20.0).abs() < 1e-9);
    // outside the pinned stretch, other copies and other structures: territory start
    assert_eq!(pop[1][b(0, 0)], plain[1][b(0, 0)]);
    assert_eq!(pop[1][b(4, 1)], plain[1][b(4, 1)]);
    assert_eq!(pop[0], plain[0]);
    // bad pins
    let bad = InitPins { copy: vec![0, 0, 2], ..pins.clone() };
    assert!(bad.resolve(&g, p.n_structures).is_err());
    let dup = InitPins { hap: vec![2, 2, 15], ..pins.clone() };
    assert!(dup.resolve(&g, p.n_structures).is_err());
    // end to end with the pins; reports
    let out = run_population_with(&c, &s, &e, &[2, 2], &pi, &pj, &pv, &pins, &p, &mut |_, _| Ok(())).unwrap();
    let relax = out.out.relax_log.as_ref().expect("relaxation log");
    assert_eq!(relax.round, 0);
    assert_eq!(relax.breakdown.len(), 4);
    let last = out.out.rounds.last().unwrap();
    let kinds: Vec<&str> = last.breakdown.iter().map(|r| r.kind.as_str()).collect();
    assert_eq!(kinds, ["hic_intra", "hic_inter", "polymer", "envelope"]);
    let (imp, vio): (u64, u64) = last.breakdown.iter().fold((0, 0), |a, r| (a.0 + r.imposed, a.1 + r.violated));
    assert_eq!((imp, vio), (last.violations.imposed(), last.violations.violated()));
    assert!(last.breakdown[1].imposed > 0, "inter-chromosomal Hi-C restraints expected");
    for r in &last.breakdown {
        if r.violated > 0 {
            let w = &out.out.final_stats[r.worst_structure as usize];
            assert!(r.worst_ratio > 0.0 && r.worst_violated > 0 && w.viol.violated() > 0);
        } else {
            assert_eq!(r.worst_structure, -1);
        }
    }
}

const REF_COORDS: u64 = 0x477bf4a77fc9cfea;
const REF_SCORES: u64 = 0x81d23fd7003c2305;
const REF_ACTDIST: u64 = 0xf38748bfb93a8aef;
const REF_ROUNDS: usize = 3;
