//! GPU step-time micro-benchmark on a dense random chain (density like a
//! 100 kb mouse genome structure).  `cargo run --release --features gpu --example bench_gpu [n]`

use std::time::Instant;
use uchrom_nucdyn::dynamics::{RestraintForm, System, V3};
use uchrom_nucdyn::gpu::GpuEngine;
use uchrom_nucdyn::restraints::{ambiguity_offsets, bin_restraints, Restraint, RestraintSet};
use uchrom_nucdyn::rng::Rng;

fn main() {
    let n: usize = std::env::args().nth(1).map(|s| s.parse().unwrap()).unwrap_or(25_000);
    let mut rng = Rng::new(1);
    let r_sphere = (n as f64 / 0.55 * 3.0 / (4.0 * std::f64::consts::PI)).cbrt();
    let mut pos: Vec<V3> = vec![];
    let mut p = [0.0f64; 3];
    for _ in 0..n {
        loop {
            let q = [p[0] + rng.normal() * 0.6, p[1] + rng.normal() * 0.6, p[2] + rng.normal() * 0.6];
            if (q[0] * q[0] + q[1] * q[1] + q[2] * q[2]).sqrt() < r_sphere {
                p = q;
                break;
            }
        }
        pos.push(p);
    }
    let mut rest = vec![];
    for i in 0..n - 1 {
        rest.push(Restraint { i: i as u32, j: i as u32 + 1, lo: 0.1, hi: 1.1, ambig: 0, weight: 1.0 });
    }
    for _ in 0..3 * n {
        let i = (rng.uniform() * n as f64) as u32;
        let j = (rng.uniform() * n as f64) as u32;
        rest.push(Restraint { i: i.min(j), j: i.max(j), lo: 0.8, hi: 1.2, ambig: 0, weight: 1.0 });
    }
    let rest = bin_restraints(rest);
    let groups = ambiguity_offsets(&rest);
    let rs = RestraintSet { rest, groups, n_contacts: 0 };
    let sys = System::new(n, vec![1.0; n], vec![1.0; n], &rs).with_form(RestraintForm::Master2017);
    let mut eng = GpuEngine::new(0).expect("GPU");
    for &m in &[1usize, 4, 10, 20, 40] {
        for &f_rep in &[0.5, 0.0] {
            let steps = 200;
            let start = vec![pos.clone(); m];
            // warm-up
            eng.run_schedule(&sys, start.clone(), &[(10.0, f_rep)], 10, 25.0, 1.0, 0.020458, 0.4888, 1, None).unwrap();
            let t = Instant::now();
            eng.run_schedule(&sys, start, &[(10.0, f_rep); 2], steps / 2, 25.0, 1.0, 0.020458, 0.4888, 1, None).unwrap();
            let dt = t.elapsed().as_secs_f64();
            println!(
                "n={n} models={m} f_rep={f_rep}: {:.3} ms per step, {:.1} ns per particle-step",
                dt / steps as f64 * 1e3,
                dt / steps as f64 / (n * m) as f64 * 1e9
            );
        }
    }
}
