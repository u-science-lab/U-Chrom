//! GPU (f32) vs CPU (f64) agreement of the IGM kernels.

use super::*;
use crate::igm::astep;
use crate::igm::forces::{compute, violations, Grid, HicBonds, Scale};
use crate::igm::md::{minimize, run, RunParams, State};
use crate::rng::Rng;

/// Two diploid chromosomes of `n` beads each in a small nucleus, S structures.
fn setup(n: usize, s: usize, seed: u64) -> (Genome, ForceField, IgmParams, Vec<Vec<V3>>) {
    let p = IgmParams { n_structures: s, nucleus_radius: 1500.0, occupancy: 0.3, seed, ..Default::default() };
    let chrom: Vec<u32> = (0..2 * n).map(|i| (i / n) as u32).collect();
    let start: Vec<i64> = (0..2 * n).map(|i| ((i % n) * 100_000) as i64).collect();
    let end: Vec<i64> = start.iter().map(|&x| x + 100_000).collect();
    let g = Genome::new(&chrom, &start, &end, &[2, 2], &p).unwrap();
    let poly = g.polymer_bonds(&p, &|_| 1.0);
    let ff = ForceField::new(g.radii.clone(), &poly, p.semiaxes(), &p);
    // f32-representable start coordinates, so both sides start identically
    let pop: Vec<Vec<V3>> = crate::igm::driver::random_population(&g, &p, 0)
        .into_iter()
        .map(|st| st.into_iter().map(|q| [q[0] as f32 as f64, q[1] as f32 as f64, q[2] as f32 as f64]).collect())
        .collect();
    (g, ff, p, pop)
}

fn random_rows(g: &Genome, k: usize, seed: u64) -> Vec<(u32, u32, f64)> {
    let mut rng = Rng::new(seed);
    let n = g.n_beads();
    (0..k)
        .map(|_| {
            let a = (rng.uniform() * n as f64) as u32;
            let mut b = (rng.uniform() * n as f64) as u32;
            if a == b {
                b = (b + 1) % n as u32;
            }
            (a.min(b), a.max(b), (1500.0f64 * (0.3 + rng.uniform())).powi(2) as f32 as f64)
        })
        .collect()
}

#[test]
fn gpu_md_matches_cpu() {
    let (g, ff, p, pop) = setup(150, 3, 1);
    let Ok(mut eng) = GpuPopEngine::new(&ff, &p) else {
        eprintln!("no GPU adapter: skipped");
        return;
    };
    let rows = random_rows(&g, 400, 3);
    let mut rng = Rng::new(9);
    let vel: Vec<Vec<V3>> = pop
        .iter()
        .map(|st| st.iter().map(|_| [(rng.normal() * 30.0) as f32 as f64, (rng.normal() * 30.0) as f32 as f64, (rng.normal() * 30.0) as f32 as f64]).collect())
        .collect();
    let (steps, t0, t1) = (20, 500.0, 300.0);
    let gpu = eng.debug_md(&pop, &vel, &rows, steps, t0, t1, 1000.0, 0.5, 1.2).unwrap();
    let mut max_d = 0.0f64;
    let mut max_mv = 0.0f64;
    for s in 0..pop.len() {
        let hic = HicBonds::from_pairs(ff.n, &astep::assign(&rows, &pop[s]));
        let mut st = State::new(pop[s].clone());
        st.vel = vel[s].clone();
        let rp = RunParams { n_steps: steps, t0, t1, dt: p.timestep, xlimit: 1000.0, window: p.rescale_window, fraction: 1.0, scale: Scale { ev: 0.5, env: 1.2 } };
        run(&ff, &hic, &mut st, &rp);
        for i in 0..ff.n {
            let d: f64 = (0..3).map(|k| (gpu[s][i][k] - st.pos[i][k]).powi(2)).sum::<f64>().sqrt();
            let mv: f64 = (0..3).map(|k| (pop[s][i][k] - st.pos[i][k]).powi(2)).sum::<f64>().sqrt();
            max_d = max_d.max(d);
            max_mv = max_mv.max(mv);
        }
    }
    eprintln!("IGM MD GPU (f32) vs CPU (f64), {steps} steps: max diff {max_d:.3e} nm, max move {max_mv:.1} nm");
    assert!(max_mv > 10.0);
    assert!(max_d < 1e-2, "max diff {max_d} nm");
}

#[test]
fn gpu_forces_energy_and_violations_match_cpu() {
    let (g, ff, p, pop) = setup(200, 2, 2);
    // push some beads through the envelope
    let pop: Vec<Vec<V3>> = pop.iter().map(|st| st.iter().map(|q| [(q[0] * 1.3) as f32 as f64, (q[1] * 1.3) as f32 as f64, (q[2] * 1.3) as f32 as f64]).collect()).collect();
    let Ok(mut eng) = GpuPopEngine::new(&ff, &p) else {
        eprintln!("no GPU adapter: skipped");
        return;
    };
    let rows = random_rows(&g, 600, 5);
    // CG with a single evaluation: the energy at the start and the violation counts
    let mut q = p.clone();
    q.cg_max_eval = 1;
    eng.p = q;
    let (_, stats) = eng.debug_cg(&pop, &rows, 1.0, 1.0).unwrap();
    for s in 0..pop.len() {
        let hic = HicBonds::from_pairs(ff.n, &astep::assign(&rows, &pop[s]));
        let mut f = vec![[0.0; 3]; ff.n];
        let e = compute(&ff, &hic, &pop[s], Scale { ev: 1.0, env: 1.0 }, &mut Grid::default(), &mut f);
        let v = violations(&ff, &hic, &pop[s], p.violation_tolerance);
        eprintln!("structure {s}: energy CPU {:.6e} GPU {:.6e}; {v:?}", e.total(), stats[s].energy);
        assert!(((stats[s].energy - e.total()) / e.total()).abs() < 1e-4);
        assert_eq!(stats[s].viol, v);
        assert!(v.hic_imposed > 0 && v.env_violated > 0);
    }
}

#[test]
fn gpu_cg_matches_cpu() {
    let (g, ff, p, pop) = setup(120, 2, 4);
    let Ok(mut eng) = GpuPopEngine::new(&ff, &p) else {
        eprintln!("no GPU adapter: skipped");
        return;
    };
    let rows = random_rows(&g, 300, 7);
    let mut q = p.clone();
    q.cg_max_eval = 60;
    q.cg_max_iter = 60;
    q.cg_dmax = 20.0;
    eng.p = q.clone();
    let (gpu, stats) = eng.debug_cg(&pop, &rows, 1.0, 1.0).unwrap();
    for s in 0..pop.len() {
        let hic = HicBonds::from_pairs(ff.n, &astep::assign(&rows, &pop[s]));
        let mut st = State::new(pop[s].clone());
        let sc = Scale { ev: 1.0, env: 1.0 };
        let cs = minimize(&ff, &hic, &mut st, sc, q.cg_etol, q.cg_ftol, q.cg_max_iter, q.cg_max_eval, q.cg_dmax);
        let mut f = vec![[0.0; 3]; ff.n];
        let eg = compute(&ff, &hic, &gpu[s], sc, &mut Grid::default(), &mut f).total();
        eprintln!(
            "CG structure {s}: CPU {:.6e} -> {:.6e} ({} it, {} ev); GPU -> {:.6e} ({} it, {} ev)",
            cs.e_start, cs.e_final, cs.iterations, cs.evaluations, eg, stats[s].cg_iterations, stats[s].cg_evaluations
        );
        assert!(eg < 0.9 * cs.e_start);
        assert!((eg - cs.e_final).abs() / cs.e_final < 0.05, "GPU {eg} CPU {}", cs.e_final);
    }
}

#[test]
fn gpu_astep_matches_cpu() {
    let (g, ff, mut p, pop) = setup(60, 300, 5);
    p.n_structures = pop.len();
    let Ok(mut eng) = GpuPopEngine::new(&ff, &p) else {
        eprintln!("no GPU adapter: skipped");
        return;
    };
    eng.set_population(&pop).unwrap();
    let nh = g.n_hap() as u32;
    let (mut pi, mut pj, mut pv) = (vec![], vec![], vec![]);
    let mut rng = Rng::new(1);
    for i in 0..nh {
        for j in i + 1..nh {
            pi.push(i);
            pj.push(j);
            pv.push(rng.uniform().powi(3));
        }
    }
    let mut cand = Candidates::from_coo(&g, &pi, &pj, &pv, 0.0);
    for k in 0..cand.len() {
        cand.p_last[k] = if k % 3 == 0 { 0.5 * cand.f[k] } else { 0.0 };
    }
    let sel = cand.select(0.02, 0.02);
    let gp = eng.actdist(&g, &cand, &sel).unwrap();
    // CPU reference on the same (f32-representable) coordinates
    let cp = astep::actdist(&g, &cand, &sel, &pop, p.contact_range);
    let (mut same_p, mut max_rel, mut restrained) = (0usize, 0.0f64, 0usize);
    for (a, b) in gp.iter().zip(&cp) {
        if a.p == b.p {
            same_p += 1;
        }
        if a.p > 0.0 && b.p > 0.0 {
            restrained += 1;
            max_rel = max_rel.max((a.d2_act - b.d2_act).abs() / b.d2_act);
        }
    }
    eprintln!("A-step GPU vs CPU: {} pairs, identical p for {same_p}, {restrained} restrained, max rel. diff of d_act^2 {max_rel:.2e}", sel.len());
    assert!(restrained > 100);
    assert!(same_p as f64 >= 0.999 * sel.len() as f64);
    assert!(max_rel < 1e-5);
    // per-structure assignment on the GPU vs the CPU rule
    let rows = astep::rows(&g, &cand, &sel, &gp);
    let mut q = p.clone();
    q.cg_max_eval = 1;
    eng.p = q;
    let (_, stats) = eng.debug_cg(&pop, &rows, 1.0, 1.0).unwrap();
    // (the rule in f32, as the GPU evaluates it: with f64 distances the element of
    // rank o itself can fall on either side of its f32-rounded d_act^2)
    let assign_f32 = |pos: &[V3]| {
        rows.iter()
            .filter(|r| {
                let (a, b) = (pos[r.0 as usize], pos[r.1 as usize]);
                let d = [(a[0] as f32 - b[0] as f32), (a[1] as f32 - b[1] as f32), (a[2] as f32 - b[2] as f32)];
                d[0] * d[0] + d[1] * d[1] + d[2] * d[2] <= r.2 as f32
            })
            .count() as u64
    };
    let mut mismatch = 0;
    let mut total = 0u64;
    let mut diff = 0u64;
    for s in 0..pop.len() {
        let n_cpu = assign_f32(&pop[s]);
        diff += n_cpu.abs_diff(stats[s].n_hic);
        total += n_cpu;
        if n_cpu != stats[s].n_hic {
            if mismatch < 5 {
                eprintln!("structure {s}: CPU {n_cpu} GPU {}", stats[s].n_hic);
            }
            mismatch += 1;
        }
    }
    eprintln!("assignment: {total} bonds; {mismatch} of {} structures differ in the Hi-C bond count (total |diff| {diff})", pop.len());
    assert!(total > 0);
    // the only differences allowed are the rank-o elements themselves (d^2 == d_act^2 up to
    // the last bit: the GPU compiler may fuse the distance into FMAs), at most one per row
    assert!(diff as usize <= rows.len(), "{diff} > {} rows", rows.len());
    assert!(diff as f64 <= 1e-3 * total as f64);
}

/// Intra / inter Hi-C violation breakdown (inter flag carried in the CSR partner word).
#[test]
fn gpu_inter_violation_breakdown_matches_cpu() {
    let (g, mut ff, p, pop) = setup(150, 2, 12);
    ff.bead_chrom = g.bead_hap.iter().map(|&h| g.hap_chrom[h as usize]).collect();
    let pop: Vec<Vec<V3>> = pop.iter().map(|st| st.iter().map(|q| [(q[0] * 1.2) as f32 as f64, (q[1] * 1.2) as f32 as f64, (q[2] * 1.2) as f32 as f64]).collect()).collect();
    let Ok(mut eng) = GpuPopEngine::new(&ff, &p) else {
        eprintln!("no GPU adapter: skipped");
        return;
    };
    let rows = random_rows(&g, 500, 13);
    let mut q = p.clone();
    q.cg_max_eval = 1;
    eng.p = q;
    let (_, stats) = eng.debug_cg(&pop, &rows, 1.0, 1.0).unwrap();
    for s in 0..pop.len() {
        let hic = HicBonds::from_pairs(ff.n, &astep::assign(&rows, &pop[s]));
        let v = violations(&ff, &hic, &pop[s], p.violation_tolerance);
        eprintln!("structure {s}: {v:?}");
        assert_eq!(stats[s].viol, v);
        assert!(v.hic_inter_imposed > 0 && v.hic_inter_imposed < v.hic_imposed);
        assert!(v.hic_inter_violated <= v.hic_violated);
    }
}

/// GP pooling and the iterative-correction switch in the GPU A-step.
#[test]
fn gpu_astep_options_match_cpu() {
    let (g, ff, mut p, pop) = setup(40, 200, 6);
    p.n_structures = pop.len();
    let nh = g.n_hap() as u32;
    let (mut pi, mut pj, mut pv) = (vec![], vec![], vec![]);
    let mut rng = Rng::new(2);
    for i in 0..nh {
        for j in i + 1..nh {
            pi.push(i);
            pj.push(j);
            pv.push(rng.uniform().powi(3));
        }
    }
    let mut cand = Candidates::from_coo(&g, &pi, &pj, &pv, 0.0);
    for k in 0..cand.len() {
        cand.p_last[k] = if k % 3 == 0 { 0.5 * cand.f[k] } else { 0.0 };
    }
    let sel = cand.select(0.02, 0.02);
    for (pool, ic) in [("gp", true), ("igm", false), ("gp", false)] {
        let mut q = p.clone();
        q.assignment_pooling = pool.into();
        q.iterative_correction = ic;
        let Ok(mut eng) = GpuPopEngine::new(&ff, &q) else {
            eprintln!("no GPU adapter: skipped");
            return;
        };
        eng.set_population(&pop).unwrap();
        let gpu = eng.actdist(&g, &cand, &sel).unwrap();
        let cpu = astep::actdist_opt(&g, &cand, &sel, &pop, q.contact_range, astep::AStepOpts::from_params(&q));
        let (mut same_p, mut max_rel, mut restrained) = (0usize, 0.0f64, 0usize);
        for (a, b) in gpu.iter().zip(&cpu) {
            same_p += (a.p == b.p) as usize;
            if a.p > 0.0 && b.p > 0.0 {
                restrained += 1;
                max_rel = max_rel.max((a.d2_act - b.d2_act).abs() / b.d2_act);
            }
        }
        eprintln!("A-step {pool} (iterative correction {ic}) GPU vs CPU: {} pairs, identical p {same_p}, {restrained} restrained, max rel. diff d_act^2 {max_rel:.2e}", sel.len());
        assert!(restrained > 100);
        assert!(same_p as f64 >= 0.999 * sel.len() as f64);
        assert!(max_rel < 1e-5);
    }
}

/// EMber-pop: no envelope + non-contact restraints, GPU vs CPU (MD and energies).
#[test]
fn gpu_noncontact_matches_cpu() {
    let (g, ff0, p0, pop) = setup(150, 3, 6);
    let p = IgmParams { nucleus_shape: "none".into(), noncontact_kspring: 0.5, noncontact_range: 2.0, ..p0 };
    let poly = g.polymer_bonds(&p, &|_| 1.0);
    let mut ff = ForceField::new(g.radii.clone(), &poly, p.semiaxes(), &p);
    ff.bead_chrom = ff0.bead_chrom.clone();
    ff.k_nc = p.noncontact_kspring;
    let Ok(mut eng) = GpuPopEngine::new(&ff, &p) else {
        eprintln!("no GPU adapter: skipped");
        return;
    };
    let rows: Vec<(u32, u32, f64)> = random_rows(&g, 400, 13).into_iter().filter(|r| !g.polymer_neighbours(r.0, r.1)).collect();
    // energies and violation counts (envelope off: no envelope restraints imposed)
    let mut q = p.clone();
    q.cg_max_eval = 1;
    eng.p = q;
    let (_, stats) = eng.debug_cg(&pop, &rows, 1.0, 1.0).unwrap();
    for s in 0..pop.len() {
        let hic = HicBonds::from_pairs(ff.n, &astep::assign(&rows, &pop[s]));
        let mut f = vec![[0.0; 3]; ff.n];
        let e = compute(&ff, &hic, &pop[s], Scale { ev: 1.0, env: 1.0 }, &mut Grid::default(), &mut f);
        let v = violations(&ff, &hic, &pop[s], p.violation_tolerance);
        eprintln!("structure {s}: energy CPU {:.6e} (nc {:.3e}) GPU {:.6e}", e.total(), e.nc, stats[s].energy);
        assert!(e.nc > 0.0 && e.env == 0.0);
        assert!(((stats[s].energy - e.total()) / e.total()).abs() < 1e-4);
        assert_eq!(stats[s].viol, v);
        assert_eq!(v.env_imposed, 0);
    }
    // MD
    eng.p = p.clone();
    let mut rng = Rng::new(10);
    let vel: Vec<Vec<V3>> = pop
        .iter()
        .map(|st| st.iter().map(|_| [(rng.normal() * 30.0) as f32 as f64, (rng.normal() * 30.0) as f32 as f64, (rng.normal() * 30.0) as f32 as f64]).collect())
        .collect();
    let (steps, t0, t1) = (20, 500.0, 300.0);
    let gpu = eng.debug_md(&pop, &vel, &rows, steps, t0, t1, 1000.0, 1.0, 1.0).unwrap();
    let mut max_d = 0.0f64;
    for s in 0..pop.len() {
        let hic = HicBonds::from_pairs(ff.n, &astep::assign(&rows, &pop[s]));
        let mut st = State::new(pop[s].clone());
        st.vel = vel[s].clone();
        let rp = RunParams { n_steps: steps, t0, t1, dt: p.timestep, xlimit: 1000.0, window: p.rescale_window, fraction: 1.0, scale: Scale { ev: 1.0, env: 1.0 } };
        run(&ff, &hic, &mut st, &rp);
        for i in 0..ff.n {
            let d: f64 = (0..3).map(|k| (gpu[s][i][k] - st.pos[i][k]).powi(2)).sum::<f64>().sqrt();
            max_d = max_d.max(d);
        }
    }
    eprintln!("non-contact MD GPU vs CPU: max diff {max_d:.3e} nm");
    assert!(max_d < 1e-2, "max diff {max_d} nm");
}

/// EMber-pop soft assignment (weights quantised to 9 bits on the GPU), with
/// non-contact restraints and no envelope: GPU vs CPU energies, violations, MD.
#[test]
fn gpu_soft_assignment_matches_cpu() {
    use crate::igm::params::SoftAssign;
    let (g, ff0, p0, pop) = setup(150, 3, 8);
    let p = IgmParams { nucleus_shape: "none".into(), noncontact_kspring: 0.5, noncontact_range: 2.0, assignment: "soft".into(), ..p0 };
    let poly = g.polymer_bonds(&p, &|_| 1.0);
    let mut ff = ForceField::new(g.radii.clone(), &poly, p.semiaxes(), &p);
    ff.bead_chrom = ff0.bead_chrom.clone();
    ff.k_nc = p.noncontact_kspring;
    let Ok(mut eng) = GpuPopEngine::new(&ff, &p) else {
        eprintln!("no GPU adapter: skipped");
        return;
    };
    let sa = SoftAssign { beta: 6.0, commit: 0.95, min_weight: 0.05 };
    eng.set_soft(Some(sa)).unwrap();
    let rows: Vec<(u32, u32, f64)> = random_rows(&g, 400, 17).into_iter().filter(|r| !g.polymer_neighbours(r.0, r.1)).collect();
    // CPU bonds with the GPU's 9-bit weights
    let cpu_hic = |pos: &[V3]| {
        let (pairs, w) = astep::assign_soft(&rows, pos, &sa);
        let wq: Vec<f64> = w.iter().map(|&x| (x * 511.0).round() / 511.0).collect();
        HicBonds::from_weighted(ff.n, &pairs, &wq)
    };
    let mut q = p.clone();
    q.cg_max_eval = 1;
    eng.p = q;
    let (_, stats) = eng.debug_cg(&pop, &rows, 1.0, 1.0).unwrap();
    for s in 0..pop.len() {
        let hic = cpu_hic(&pop[s]);
        assert!(hic.w.iter().any(|&x| x < 1.0 && x > 0.0), "no fractional weights");
        let mut f = vec![[0.0; 3]; ff.n];
        let e = compute(&ff, &hic, &pop[s], Scale { ev: 1.0, env: 1.0 }, &mut Grid::default(), &mut f);
        let v = violations(&ff, &hic, &pop[s], p.violation_tolerance);
        eprintln!("soft structure {s}: energy CPU {:.6e} GPU {:.6e}, {} weighted ends", e.total(), stats[s].energy, hic.partner.len());
        assert!(((stats[s].energy - e.total()) / e.total()).abs() < 1e-4);
        assert_eq!(stats[s].viol, v);
    }
    eng.p = p.clone();
    let mut rng = Rng::new(12);
    let vel: Vec<Vec<V3>> = pop
        .iter()
        .map(|st| st.iter().map(|_| [(rng.normal() * 30.0) as f32 as f64, (rng.normal() * 30.0) as f32 as f64, (rng.normal() * 30.0) as f32 as f64]).collect())
        .collect();
    let (steps, t0, t1) = (20, 500.0, 300.0);
    let gpu = eng.debug_md(&pop, &vel, &rows, steps, t0, t1, 1000.0, 1.0, 1.0).unwrap();
    let mut max_d = 0.0f64;
    for s in 0..pop.len() {
        let hic = cpu_hic(&pop[s]);
        let mut st = State::new(pop[s].clone());
        st.vel = vel[s].clone();
        let rp = RunParams { n_steps: steps, t0, t1, dt: p.timestep, xlimit: 1000.0, window: p.rescale_window, fraction: 1.0, scale: Scale { ev: 1.0, env: 1.0 } };
        run(&ff, &hic, &mut st, &rp);
        for i in 0..ff.n {
            let d: f64 = (0..3).map(|k| (gpu[s][i][k] - st.pos[i][k]).powi(2)).sum::<f64>().sqrt();
            max_d = max_d.max(d);
        }
    }
    eprintln!("soft MD GPU vs CPU: max diff {max_d:.3e} nm");
    assert!(max_d < 1e-2, "max diff {max_d} nm");
}

/// EMber-pop radius-of-gyration cap (no envelope): GPU vs CPU energies and MD.
#[test]
fn gpu_rg_cap_matches_cpu() {
    let (g, ff0, p0, pop) = setup(150, 3, 9);
    for two in [false, true] {
    let p = IgmParams { nucleus_shape: "none".into(), rg_cap: if two { 3000.0 } else { 300.0 }, rg_kspring: 0.2, rg_two_sided: two, ..p0.clone() };
    let poly = g.polymer_bonds(&p, &|_| 1.0);
    let mut ff = ForceField::new(g.radii.clone(), &poly, p.semiaxes(), &p);
    ff.bead_chrom = ff0.bead_chrom.clone();
    let Ok(mut eng) = GpuPopEngine::new(&ff, &p) else {
        eprintln!("no GPU adapter: skipped");
        return;
    };
    let rows = random_rows(&g, 300, 19);
    let mut q = p.clone();
    q.cg_max_eval = 1;
    eng.p = q;
    let (_, stats) = eng.debug_cg(&pop, &rows, 1.0, 1.0).unwrap();
    for s in 0..pop.len() {
        let hic = HicBonds::from_pairs(ff.n, &astep::assign(&rows, &pop[s]));
        let mut f = vec![[0.0; 3]; ff.n];
        let e = compute(&ff, &hic, &pop[s], Scale { ev: 1.0, env: 1.0 }, &mut Grid::default(), &mut f);
        eprintln!("rg structure {s}: energy CPU {:.6e} (cap {:.3e}) GPU {:.6e}", e.total(), e.env, stats[s].energy);
        assert!(e.env > 0.0);
        assert!(((stats[s].energy - e.total()) / e.total()).abs() < 1e-4);
    }
    eng.p = p.clone();
    let mut rng = Rng::new(14);
    let vel: Vec<Vec<V3>> = pop
        .iter()
        .map(|st| st.iter().map(|_| [(rng.normal() * 30.0) as f32 as f64, (rng.normal() * 30.0) as f32 as f64, (rng.normal() * 30.0) as f32 as f64]).collect())
        .collect();
    let (steps, t0, t1) = (20, 500.0, 300.0);
    let gpu = eng.debug_md(&pop, &vel, &rows, steps, t0, t1, 1000.0, 1.0, 1.0).unwrap();
    let mut max_d = 0.0f64;
    for s in 0..pop.len() {
        let hic = HicBonds::from_pairs(ff.n, &astep::assign(&rows, &pop[s]));
        let mut st = State::new(pop[s].clone());
        st.vel = vel[s].clone();
        let rp = RunParams { n_steps: steps, t0, t1, dt: p.timestep, xlimit: 1000.0, window: p.rescale_window, fraction: 1.0, scale: Scale { ev: 1.0, env: 1.0 } };
        run(&ff, &hic, &mut st, &rp);
        for i in 0..ff.n {
            let d: f64 = (0..3).map(|k| (gpu[s][i][k] - st.pos[i][k]).powi(2)).sum::<f64>().sqrt();
            max_d = max_d.max(d);
        }
    }
    eprintln!("rg-cap (two-sided {two}) MD GPU vs CPU: max diff {max_d:.3e} nm");
    assert!(max_d < 1e-2, "max diff {max_d} nm");
    }
}

/// EMber-pop gyration-shape prior (no envelope): GPU vs CPU energies and MD.
#[test]
fn gpu_gyration_prior_matches_cpu() {
    let (g, ff0, p0, pop) = setup(150, 3, 10);
    let p = IgmParams { nucleus_shape: "none".into(), gyration_prior: [900.0, 500.0, 150.0], gyration_kspring: 0.2, ..p0 };
    let poly = g.polymer_bonds(&p, &|_| 1.0);
    let mut ff = ForceField::new(g.radii.clone(), &poly, p.semiaxes(), &p);
    ff.bead_chrom = ff0.bead_chrom.clone();
    let Ok(mut eng) = GpuPopEngine::new(&ff, &p) else {
        eprintln!("no GPU adapter: skipped");
        return;
    };
    let rows = random_rows(&g, 300, 21);
    let mut q = p.clone();
    q.cg_max_eval = 1;
    eng.p = q;
    let (_, stats) = eng.debug_cg(&pop, &rows, 1.0, 1.0).unwrap();
    for s in 0..pop.len() {
        let hic = HicBonds::from_pairs(ff.n, &astep::assign(&rows, &pop[s]));
        let mut f = vec![[0.0; 3]; ff.n];
        let e = compute(&ff, &hic, &pop[s], Scale { ev: 1.0, env: 1.0 }, &mut Grid::default(), &mut f);
        eprintln!("gyration structure {s}: energy CPU {:.6e} (prior {:.3e}) GPU {:.6e}", e.total(), e.env, stats[s].energy);
        assert!(e.env > 0.0);
        assert!(((stats[s].energy - e.total()) / e.total()).abs() < 1e-4);
    }
    eng.p = p.clone();
    let mut rng = Rng::new(15);
    let vel: Vec<Vec<V3>> = pop
        .iter()
        .map(|st| st.iter().map(|_| [(rng.normal() * 30.0) as f32 as f64, (rng.normal() * 30.0) as f32 as f64, (rng.normal() * 30.0) as f32 as f64]).collect())
        .collect();
    let (steps, t0, t1) = (20, 500.0, 300.0);
    let gpu = eng.debug_md(&pop, &vel, &rows, steps, t0, t1, 1000.0, 1.0, 1.0).unwrap();
    let mut max_d = 0.0f64;
    for s in 0..pop.len() {
        let hic = HicBonds::from_pairs(ff.n, &astep::assign(&rows, &pop[s]));
        let mut st = State::new(pop[s].clone());
        st.vel = vel[s].clone();
        let rp = RunParams { n_steps: steps, t0, t1, dt: p.timestep, xlimit: 1000.0, window: p.rescale_window, fraction: 1.0, scale: Scale { ev: 1.0, env: 1.0 } };
        run(&ff, &hic, &mut st, &rp);
        for i in 0..ff.n {
            let d: f64 = (0..3).map(|k| (gpu[s][i][k] - st.pos[i][k]).powi(2)).sum::<f64>().sqrt();
            max_d = max_d.max(d);
        }
    }
    eprintln!("gyration-prior MD GPU vs CPU: max diff {max_d:.3e} nm");
    assert!(max_d < 1e-2, "max diff {max_d} nm");
}
