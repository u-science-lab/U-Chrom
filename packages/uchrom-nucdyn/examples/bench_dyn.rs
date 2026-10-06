//! Per-step cost of `run_dynamics` (1 thread, cell grid) on a dense random chain, and the
//! share of the force evaluation.  `cargo run --release --example bench_dyn [n] [steps]`

use std::time::Instant;
use uchrom_nucdyn::dynamics::{compute_forces_mode, run_dynamics, DynParams, Model, RestraintForm, System};
use uchrom_nucdyn::restraints::{ambiguity_offsets, Restraint, RestraintSet};
use uchrom_nucdyn::rng::Rng;

fn main() {
    let n: usize = std::env::args().nth(1).map(|s| s.parse().unwrap()).unwrap_or(25_000);
    let steps: usize = std::env::args().nth(2).map(|s| s.parse().unwrap()).unwrap_or(200);
    let mut rng = Rng::new(1);
    let r_sphere = (n as f64 / 0.4 * 3.0 / (4.0 * std::f64::consts::PI)).cbrt();
    let mut pos = vec![];
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
    // POS_FILE: raw little-endian f64 xyz of a real structure (overrides n and the random chain)
    let (n, pos) = match std::env::var("POS_FILE") {
        Ok(f) => {
            let b = std::fs::read(f).unwrap();
            let v: Vec<f64> = b.chunks_exact(8).map(|c| f64::from_le_bytes(c.try_into().unwrap())).collect();
            let p: Vec<[f64; 3]> = v.chunks_exact(3).map(|c| [c[0], c[1], c[2]]).collect();
            (p.len(), p)
        }
        Err(_) => (n, pos),
    };
    let mut rest = vec![];
    for i in 0..n - 1 {
        rest.push(Restraint { i: i as u32, j: i as u32 + 1, lo: 0.1, hi: 1.1, ambig: 0, weight: 1.0 });
    }
    let n_random = if std::env::var("POS_FILE").is_ok() { 0 } else { 4 * n };
    for _ in 0..n_random {
        let i = (rng.uniform() * n as f64) as u32;
        let j = (rng.uniform() * n as f64) as u32;
        rest.push(Restraint { i: i.min(j), j: i.max(j), lo: 0.8, hi: 1.2, ambig: 0, weight: 1.0 });
    }
    let rest = uchrom_nucdyn::restraints::bin_restraints(rest);
    let groups: Vec<u32> = (0..=rest.len() as u32).collect();
    let _ = ambiguity_offsets;
    let rs = RestraintSet { rest, groups, n_contacts: 0 };
    let sys = System::new(n, vec![1.0; n], vec![1.0; n], &rs).with_form(RestraintForm::Weighted2017);
    let dp = DynParams { t_ref: std::env::var("TREF").map(|x| x.parse().unwrap()).unwrap_or(50.0), t_step: 0.001, n_steps: steps, f_rep: 0.8, f_dist: 25.0, beta: 10.0, tot0: 20.458, skin: 2.0, original_nl_schedule: false, use_cells: true, emulate_overflow: false };
    let mut m = Model::new(pos.clone(), Rng::new(3));
    m.grid.stencil = 1;
    let t = Instant::now();
    run_dynamics(&sys, &mut m, &dp, false, None);
    let per_step = t.elapsed().as_secs_f64() / steps as f64;
    let mut m2 = Model::new(m.pos.clone(), Rng::new(3));
    m2.grid.stencil = 1;
    let t = Instant::now();
    for _ in 0..steps {
        compute_forces_mode(&sys, &mut m2, 0.8, 25.0, false, false, true);
    }
    let per_force = t.elapsed().as_secs_f64() / steps as f64;
    println!("n={n}: {:.3} ms per MD step, {:.3} ms per force evaluation ({:.0} %), {:.3} us / particle-step",
             per_step * 1e3, per_force * 1e3, 100.0 * per_force / per_step, per_step * 1e6 / n as f64);
    // Verlet list with a small skin, continuing from the same (relaxed) positions
    for skin in [0.3, 0.6, 1.0] {
        let dpv = DynParams { use_cells: false, skin, ..dp };
        let mut mv = Model::new(m.pos.clone(), Rng::new(3));
        let t = Instant::now();
        run_dynamics(&sys, &mut mv, &dpv, false, None);
        let ps = t.elapsed().as_secs_f64() / steps as f64;
        println!("  verlet skin {skin}: {:.3} ms per MD step ({} list builds)", ps * 1e3, mv.nl.n_builds);
    }
}
