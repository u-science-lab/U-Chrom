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
    let (names, ca, pa, cb, pb) = toy_contacts();
    let n = ca.len();
    let ambig: Vec<i64> = (1..=n as i64).collect();
    let active = vec![true; n];
    let input = Input { names: &names, chr_a: &ca, pos_a: &pa, chr_b: &cb, pos_b: &pb, ambig: &ambig, active: &active, prior_lr: None };
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
