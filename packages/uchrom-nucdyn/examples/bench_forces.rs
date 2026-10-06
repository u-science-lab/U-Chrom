//! Micro-benchmark of one force evaluation on a dense random chain.
//! `cargo run --release --example bench_forces [n]`

use std::time::Instant;
use uchrom_nucdyn::dynamics::{compute_forces_mode, Model, System};
use uchrom_nucdyn::restraints::{ambiguity_offsets, Restraint, RestraintSet};
use uchrom_nucdyn::rng::Rng;

fn main() {
    let n: usize = std::env::args().nth(1).map(|s| s.parse().unwrap()).unwrap_or(25_000);
    let mut rng = Rng::new(1);
    // random walk with step ~1 folded into a sphere with density ~0.4 / radius^3
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
    let mut rest = vec![];
    for i in 0..n - 1 {
        rest.push(Restraint { i: i as u32, j: i as u32 + 1, lo: 0.1, hi: 1.1, ambig: 0, weight: 1.0 });
    }
    for _ in 0..3 * n {
        let i = (rng.uniform() * n as f64) as u32;
        let j = (rng.uniform() * n as f64) as u32;
        rest.push(Restraint { i: i.min(j), j: i.max(j), lo: 0.8, hi: 1.2, ambig: 0, weight: 1.0 });
    }
    let rest = uchrom_nucdyn::restraints::bin_restraints(rest);
    let groups = ambiguity_offsets(&rest);
    let rs = RestraintSet { rest, groups, n_contacts: 0 };
    let sys = System::new(n, vec![1.0; n], vec![1.0; n], &rs);
    for &(cells, par) in &[(true, false), (false, false), (true, true)] {
        let mut m = Model::new(pos.clone(), Rng::new(0));
        m.grid.stencil = std::env::var("STENCIL").map(|x| x.parse().unwrap()).unwrap_or(1);
        m.nl.build(&pos, &sys.radii, 1.0, false);
        let reps = 50;
        let t = Instant::now();
        for _ in 0..reps {
            compute_forces_mode(&sys, &mut m, std::env::var("FREP").map(|x| x.parse().unwrap()).unwrap_or(0.5), 25.0, par, false, cells);
        }
        let dt = t.elapsed().as_secs_f64() / reps as f64;
        let nb = m.nl.nb.len() as f64 / n as f64;
        println!("n={n} cells={cells} parallel={par}: {:.3} ms per evaluation (verlet list {:.1} per particle)", dt * 1e3, nb);
    }
    {
        let mut m = Model::new(pos.clone(), Rng::new(0));
        m.nl.build(&pos, &sys.radii, 1.0, false);
        let t = Instant::now();
        let mut tot = 0.0;
        let mut hits = 0usize;
        for _ in 0..50 {
            for i in 0..n {
                let p = pos[i];
                let mut acc = [0.0f64; 3];
                for &j in &m.nl.nb[m.nl.off[i] as usize..m.nl.off[i + 1] as usize] {
                    let q = pos[j as usize];
                    let (dx, dy, dz) = (q[0] - p[0], q[1] - p[1], q[2] - p[2]);
                    let d2 = dx * dx + dy * dy + dz * dz;
                    if d2 > 4.0 {
                        continue;
                    }
                    hits += 1;
                    let dr = 4.0 - d2;
                    acc[0] -= dx * dr;
                    acc[1] -= dy * dr;
                    acc[2] -= dz * dr;
                }
                tot += acc[0] + acc[1] + acc[2];
            }
        }
        println!("raw verlet loop {:.3} ms ({tot}, hits/particle {})", t.elapsed().as_secs_f64() / 50.0 * 1e3, hits as f64 / 50.0 / n as f64);
    }
    let t = Instant::now();
    let mut m = Model::new(pos.clone(), Rng::new(0));
    for _ in 0..50 {
        m.grid.build(&pos, 2.0);
    }
    println!("grid build {:.3} ms, dims {:?}", t.elapsed().as_secs_f64() / 50.0 * 1e3, m.grid.dims);
}
