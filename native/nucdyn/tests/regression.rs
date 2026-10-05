//! Bit-identity of the existing protocols on the CPU engine.
//!
//! The golden hashes were recorded with the engine *before* the `robust`
//! protocol was added (commit 628746e), on each platform (libm differs
//! between macOS and Linux, so f64 results are platform specific).  A
//! platform without a recorded hash prints its hash and passes.
//!
//! `UCHROM_NUCDYN_PRINT_GOLDEN=1 cargo test --release --test regression -- --nocapture`
//! prints the hashes of the current build.

use uchrom_nucdyn::params::Params;
use uchrom_nucdyn::pipeline::{calc_genome_structure, CpuEngine, Input};
use uchrom_nucdyn::rng::Rng;

/// Contacts sampled from random-walk chromosomes (3 chromosomes x 30 Mb):
/// pairs closer than a cutoff, plus a few random trans pairs.
fn toy_contacts() -> (Vec<String>, Vec<u32>, Vec<i64>, Vec<u32>, Vec<i64>) {
    let mut rng = Rng::new(42);
    let names: Vec<String> = ["chrA", "chrB", "chrC"].iter().map(|s| s.to_string()).collect();
    let step = 50_000i64;
    let nloc = 600usize;
    let mut walk: Vec<Vec<[f64; 3]>> = vec![];
    for c in 0..3 {
        let mut p = [c as f64 * 3.0, 0.0, 0.0];
        let mut v = vec![];
        for _ in 0..nloc {
            p = [p[0] + rng.normal() * 0.3, p[1] + rng.normal() * 0.3, p[2] + rng.normal() * 0.3];
            v.push(p);
        }
        walk.push(v);
    }
    let (mut ca, mut pa, mut cb, mut pb) = (vec![], vec![], vec![], vec![]);
    for _ in 0..40_000 {
        let c1 = (rng.uniform() * 3.0) as usize;
        let c2 = if rng.uniform() < 0.9 { c1 } else { (rng.uniform() * 3.0) as usize };
        let i = (rng.uniform() * nloc as f64) as usize;
        let j = (rng.uniform() * nloc as f64) as usize;
        let (a, b) = (walk[c1][i], walk[c2][j]);
        let d2: f64 = (0..3).map(|k| (a[k] - b[k]).powi(2)).sum();
        if d2 < 1.0 || rng.uniform() < 0.002 {
            ca.push(c1 as u32);
            pa.push(i as i64 * step + 1 + (rng.uniform() * step as f64) as i64);
            cb.push(c2 as u32);
            pb.push(j as i64 * step + 1 + (rng.uniform() * step as f64) as i64);
        }
    }
    (names, ca, pa, cb, pb)
}

fn fnv(coords: &[Vec<[f64; 3]>]) -> u64 {
    let mut h = 0xcbf2_9ce4_8422_2325u64;
    for c in coords {
        for q in c {
            for x in q {
                for b in x.to_bits().to_le_bytes() {
                    h ^= b as u64;
                    h = h.wrapping_mul(0x0000_0100_0000_01b3);
                }
            }
        }
    }
    h
}

fn run(protocol: &str, emulate: bool) -> u64 {
    run_with(protocol, emulate, |p| p)
}

fn run_with(protocol: &str, emulate: bool, f: impl Fn(Params) -> Params) -> u64 {
    let (names, ca, pa, cb, pb) = toy_contacts();
    let n = ca.len();
    let ambig: Vec<i64> = (1..=n as i64).collect();
    let active = vec![true; n];
    let input = Input { names: &names, chr_a: &ca, pos_a: &pa, chr_b: &cb, pos_b: &pb, ambig: &ambig, active: &active, prior_lr: None, dip: None };
    let p = Params {
        protocol: protocol.to_string(),
        particle_sizes: vec![4e6, 2e6, 4e5, 2e5],
        n_models: 3,
        seed: 5,
        temp_steps: vec![30],
        dynamics_steps: vec![20],
        emulate_rep_list_overflow: emulate,
        n_threads: 3,
        ..Default::default()
    };
    let p = f(p);
    let mut eng = CpuEngine::new(p.n_threads).unwrap();
    let out = calc_genome_structure(&input, &p, &mut eng).unwrap();
    fnv(&out.coords)
}

/// (protocol, emulate overflow, macOS aarch64 hashes, Linux x86-64 hashes).  libm differs between
/// Linux distributions, so Linux has one hash per recorded system: Sherlock (CentOS 7, glibc 2.17)
/// and the GitHub ubuntu-latest runner (recorded on 2026-10-03 by running this test on the
/// pre-`robust` engine, commit 628746e, in CI).  An empty list = not recorded (hash printed).
const GOLDEN: [(&str, bool, &[u64], &[u64]); 3] = [
    ("nuc_dynamics_2017", false, &[0x003d34d7af96f678], &[0x663497c2061b7ff3, 0x66b4673be7e94246]),
    ("nuc_dynamics_2017", true, &[0x392f2bedd2d54888], &[0xf69e41b3cd003a3b, 0x8f322f96b55ab2d0]),
    ("release_1.3", false, &[0x97aac5aaf948cf94], &[0x8ce4aa5821323198, 0xca10c7de591660e9]),
];

/// EMber (protocol "robust") with its frozen defaults (tag `robust-frozen`), on the same toy
/// contacts and a shortened schedule: (macOS aarch64, Linux x86-64: Sherlock, GitHub
/// ubuntu-latest).  Recorded 2026-10-03 on commit 6fcf370, whose CPU engine is that of the tag,
/// before diploid support was added (diploid input takes a separate path, `diploid.rs`).
const GOLDEN_ROBUST: (&[u64], &[u64]) = (&[0x0691d3b6eac2a99a], &[0x50d611f3ba255008, 0xa6236727e14c942c]);

#[test]
fn existing_protocols_bit_identical() {
    let print = std::env::var("UCHROM_NUCDYN_PRINT_GOLDEN").is_ok();
    for (proto, emulate, mac, linux) in GOLDEN {
        let h = run(proto, emulate);
        let want: &[u64] = if cfg!(all(target_os = "macos", target_arch = "aarch64")) {
            mac
        } else if cfg!(all(target_os = "linux", target_arch = "x86_64")) {
            linux
        } else {
            &[]
        };
        if print || want.is_empty() {
            eprintln!("golden {proto} emulate={emulate}: 0x{h:016x}");
        }
        if !want.is_empty() {
            assert!(want.contains(&h), "{proto} (emulate {emulate}) changed: 0x{h:016x} not in {want:x?}");
        }
    }
}

/// EMber: the frozen defaults with the toy schedule (re-weighting, support evidence, refinement,
/// sampling and adaptive resolution all active; particle sizes down to 20 kb so the merging of
/// contact-free particles below 25 kb runs too).
fn run_robust() -> u64 {
    run_with("robust", false, |p| Params {
        particle_sizes: vec![4e6, 2e6, 4e5, 1e5, 2e4],
        robust_temp_steps: vec![12],
        robust_dynamics_steps: vec![10],
        robust_refine_temp_steps: 4,
        robust_sample_steps: 3,
        robust_sample_dyn_steps: 5,
        ..p
    })
}

/// Diploid toy: the haploid toy contacts with every chromosome given two copies; each contact end
/// phased with probability 0.3 (seeded).
fn run_diploid(f: impl Fn(Params) -> Params) -> u64 {
    use uchrom_nucdyn::diploid::DiploidInput;
    let (names, ca, pa, cb, pb) = toy_contacts();
    let n = ca.len();
    let mut rng = Rng::new(77);
    let ha: Vec<i8> = (0..n).map(|_| if rng.uniform() < 0.3 { (rng.uniform() * 2.0) as i8 } else { -1 }).collect();
    let hb: Vec<i8> = (0..n).map(|_| if rng.uniform() < 0.3 { (rng.uniform() * 2.0) as i8 } else { -1 }).collect();
    let ambig: Vec<i64> = (1..=n as i64).collect();
    let active = vec![true; n];
    let ploidy = vec![2u8; names.len()];
    let dip = DiploidInput { hap_a: &ha, hap_b: &hb, ploidy: &ploidy, prior: None };
    let input = Input { names: &names, chr_a: &ca, pos_a: &pa, chr_b: &cb, pos_b: &pb, ambig: &ambig, active: &active, prior_lr: None, dip: Some(dip) };
    let p = f(Params {
        particle_sizes: vec![4e6, 2e6, 1e6, 4e5, 2e5],
        n_models: 2,
        seed: 5,
        temp_steps: vec![12],
        dynamics_steps: vec![10],
        robust_temp_steps: vec![12],
        robust_dynamics_steps: vec![10],
        robust_refine_temp_steps: 4,
        robust_sample_steps: 3,
        robust_sample_dyn_steps: 5,
        n_threads: 3,
        ..Default::default()
    });
    let mut eng = CpuEngine::new(p.n_threads).unwrap();
    let out = calc_genome_structure(&input, &p, &mut eng).unwrap();
    let mut h = fnv(&out.coords);
    for x in &out.phase_probs {
        h ^= x.to_bits();
        h = h.wrapping_mul(0x0000_0100_0000_01b3);
    }
    h
}

/// Diploid protocols on the CPU engine: NucDynamics-2017 diploid, frozen EMber diploid (tag
/// `ember-diploid-frozen`, engine defaults) and EMber deep (tag `ember-deep-frozen`: commit 0.75 by
/// the prior, drop, re-admit at stage 4).  (label, macOS aarch64, Linux x86-64 Sherlock).  Recorded
/// 2026-10-05 with the engine of origin/main c7c7d0f (before the few-cell deconvolution was added).
const GOLDEN_DIPLOID: [(&str, &[u64], &[u64]); 3] = [
    ("diploid nuc_dynamics_2017", &[0x9b77dca2cc24252b], &[0xa8a261bebb58dc0e]),
    ("diploid EMber", &[0xffb80847cb3c9f99], &[0xf5c03b747ac96513]),
    ("diploid EMber deep", &[0x30867b583bbb4f59], &[0x2761ea8585e413ce]),
];

#[test]
fn diploid_bit_identical() {
    let print = std::env::var("UCHROM_NUCDYN_PRINT_GOLDEN").is_ok();
    let hashes = [
        run_diploid(|p| Params { protocol: "nuc_dynamics_2017".into(), ..p }),
        run_diploid(|p| Params { protocol: "robust".into(), ..p }),
        run_diploid(|p| Params {
            protocol: "robust".into(),
            robust_dip_commit: 0.75,
            robust_dip_commit_drop: true,
            robust_dip_readmit_stage: 4,
            particle_sizes: vec![4e6, 2e6, 1e6, 4e5, 2e5, 1e5],
            ..p
        }),
    ];
    for ((label, mac, linux), h) in GOLDEN_DIPLOID.iter().zip(hashes) {
        let want: &[u64] = if cfg!(all(target_os = "macos", target_arch = "aarch64")) {
            mac
        } else if cfg!(all(target_os = "linux", target_arch = "x86_64")) {
            linux
        } else {
            &[]
        };
        if print || want.is_empty() {
            eprintln!("golden {label}: 0x{h:016x}");
        }
        if !want.is_empty() {
            assert!(want.contains(&h), "{label} changed: 0x{h:016x} not in {want:x?}");
        }
    }
}

#[test]
fn ember_bit_identical() {
    let print = std::env::var("UCHROM_NUCDYN_PRINT_GOLDEN").is_ok();
    let h = run_robust();
    let want: &[u64] = if cfg!(all(target_os = "macos", target_arch = "aarch64")) {
        GOLDEN_ROBUST.0
    } else if cfg!(all(target_os = "linux", target_arch = "x86_64")) {
        GOLDEN_ROBUST.1
    } else {
        &[]
    };
    if print || want.is_empty() {
        eprintln!("golden robust: 0x{h:016x}");
    }
    if !want.is_empty() {
        assert!(want.contains(&h), "robust (EMber) changed: 0x{h:016x} not in {want:x?}");
    }
}
