//! M-step of one structure on the CPU (f64): the LAMMPS script IGM writes
//! (spec §6.2), re-implemented from its documented behaviour.
//!
//! * `velocity all create T seed` (LAMMPS defaults `dist uniform`, `mom yes`,
//!   `rot no`): every component uniform in [−½, ½), net momentum removed,
//!   scaled to T with `T = Σ m v² / (3N − 3)` (`units lj`, k_B = 1, masses 1);
//! * `fix nve/limit xmax`: velocity Verlet, `v += ½ dt F` then
//!   `|v| ≤ xmax / dt`, `x += dt v`; forces; `v += ½ dt F`, limit again;
//! * `fix temp/rescale 1 t0 t1 window fraction` (end of every step): target
//!   `t0 + (step / n)(t1 − t0)`; if `|T − target| > window` the velocities are
//!   rescaled to `T − fraction (T − target)`;
//! * `min_style cg` + `minimize etol ftol maxiter maxeval`: Polak–Ribière CG
//!   with LAMMPS' restart rule and stopping criteria; the line search is
//!   LAMMPS' `backtrack` (the IGM script keeps the default `quadratic`; see
//!   the README for this deviation).

use crate::igm::forces::{compute, Energies, ForceField, Grid, HicBonds, Scale, V3};
use crate::igm::params::IgmParams;
use crate::rng::Rng;

/// Per-structure dynamic state.
pub struct State {
    pub pos: Vec<V3>,
    pub vel: Vec<V3>,
    pub frc: Vec<V3>,
    pub grid: Grid,
}

impl State {
    pub fn new(pos: Vec<V3>) -> State {
        let n = pos.len();
        State { pos, vel: vec![[0.0; 3]; n], frc: vec![[0.0; 3]; n], grid: Grid::default() }
    }
}

pub fn dof(n: usize) -> f64 {
    ((3 * n) as f64 - 3.0).max(1.0)
}

pub fn temperature(vel: &[V3]) -> f64 {
    vel.iter().map(|v| v[0] * v[0] + v[1] * v[1] + v[2] * v[2]).sum::<f64>() / dof(vel.len())
}

/// Scale velocities to temperature `t` after removing the net momentum.
pub fn finish_velocities(vel: &mut [V3], t: f64) {
    let n = vel.len() as f64;
    let mut m = [0.0; 3];
    for v in vel.iter() {
        for k in 0..3 {
            m[k] += v[k];
        }
    }
    for v in vel.iter_mut() {
        for k in 0..3 {
            v[k] -= m[k] / n;
        }
    }
    let t0 = temperature(vel);
    let s = if t0 > 0.0 { (t / t0).sqrt() } else { 0.0 };
    for v in vel.iter_mut() {
        for k in 0..3 {
            v[k] *= s;
        }
    }
}

/// LAMMPS `velocity create` (uniform) with our counter-based stream.
pub fn velocity_create(vel: &mut [V3], t: f64, rng: &mut Rng) {
    for v in vel.iter_mut() {
        *v = [rng.uniform() - 0.5, rng.uniform() - 0.5, rng.uniform() - 0.5];
    }
    finish_velocities(vel, t);
}

#[derive(Clone, Copy, Debug)]
pub struct RunParams {
    pub n_steps: usize,
    pub t0: f64,
    pub t1: f64,
    pub dt: f64,
    pub xlimit: f64,
    pub window: f64,
    pub fraction: f64,
    pub scale: Scale,
}

#[inline]
fn limit(v: &mut V3, vlim2: f64) {
    let s = v[0] * v[0] + v[1] * v[1] + v[2] * v[2];
    if s > vlim2 {
        let f = (vlim2 / s).sqrt();
        v[0] *= f;
        v[1] *= f;
        v[2] *= f;
    }
}

/// One LAMMPS `run` with `nve/limit` + `temp/rescale` (velocities as given).
pub fn run(ff: &ForceField, hic: &HicBonds, st: &mut State, rp: &RunParams) {
    let n = st.pos.len();
    let half = 0.5 * rp.dt;
    let vlim = rp.xlimit / rp.dt;
    let vlim2 = vlim * vlim;
    compute(ff, hic, &st.pos, rp.scale, &mut st.grid, &mut st.frc);
    for step in 1..=rp.n_steps {
        for i in 0..n {
            let (v, f) = (&mut st.vel[i], st.frc[i]);
            for k in 0..3 {
                v[k] += half * f[k];
            }
            limit(v, vlim2);
            for k in 0..3 {
                st.pos[i][k] += rp.dt * v[k];
            }
        }
        compute(ff, hic, &st.pos, rp.scale, &mut st.grid, &mut st.frc);
        for i in 0..n {
            let (v, f) = (&mut st.vel[i], st.frc[i]);
            for k in 0..3 {
                v[k] += half * f[k];
            }
            limit(v, vlim2);
        }
        let t = temperature(&st.vel);
        let target = rp.t0 + (step as f64 / rp.n_steps as f64) * (rp.t1 - rp.t0);
        if t > 0.0 && (t - target).abs() > rp.window {
            let tt = t - rp.fraction * (t - target);
            let fct = (tt.max(0.0) / t).sqrt();
            for v in st.vel.iter_mut() {
                for k in 0..3 {
                    v[k] *= fct;
                }
            }
        }
    }
}

#[derive(Clone, Copy, Debug, Default, serde::Serialize)]
pub struct CgStats {
    pub iterations: usize,
    pub evaluations: usize,
    pub e_start: f64,
    pub e_final: f64,
    /// 0 max iterations, 1 etol, 2 ftol, 3 max evaluations, 4 line search failed, 5 zero force / not downhill
    pub stop: u32,
}

pub const CG_BACKTRACK_SLOPE: f64 = 0.4;
pub const CG_ALPHA_REDUCE: f64 = 0.5;
pub const CG_EMACH: f64 = 1e-8;
pub const CG_EPS_ENERGY: f64 = 1e-8;

fn dot(a: &[V3], b: &[V3]) -> f64 {
    a.iter().zip(b).map(|(x, y)| x[0] * y[0] + x[1] * y[1] + x[2] * y[2]).sum()
}

/// Polak–Ribière CG with backtracking line search (LAMMPS `min cg`,
/// `linestyle backtrack`).  Positions updated in place.
#[allow(clippy::too_many_arguments)]
pub fn minimize(ff: &ForceField, hic: &HicBonds, st: &mut State, scale: Scale, etol: f64, ftol: f64, max_iter: usize, max_eval: usize, dmax: f64) -> CgStats {
    let n = st.pos.len();
    let mut e = compute(ff, hic, &st.pos, scale, &mut st.grid, &mut st.frc).total();
    let mut cs = CgStats { e_start: e, evaluations: 1, ..Default::default() };
    let mut g = st.frc.clone();
    let mut h = st.frc.clone();
    let mut gg = dot(&g, &g);
    let mut x0 = st.pos.clone();
    cs.stop = 0;
    for iter in 0..max_iter {
        cs.iterations = iter + 1;
        // line search along h
        let fdoth = dot(&st.frc, &h);
        if fdoth <= 0.0 {
            cs.stop = 5;
            break;
        }
        let hmax = h.iter().flat_map(|v| v.iter()).fold(0.0f64, |a, &b| a.max(b.abs()));
        if hmax == 0.0 {
            cs.stop = 5;
            break;
        }
        let mut alpha = (dmax / hmax).min(1.0);
        x0.copy_from_slice(&st.pos);
        let e0 = e;
        let mut ok = false;
        loop {
            for i in 0..n {
                for k in 0..3 {
                    st.pos[i][k] = x0[i][k] + alpha * h[i][k];
                }
            }
            let et = compute(ff, hic, &st.pos, scale, &mut st.grid, &mut st.frc).total();
            cs.evaluations += 1;
            let de_ideal = -CG_BACKTRACK_SLOPE * alpha * fdoth;
            if et - e0 <= de_ideal {
                e = et;
                ok = true;
                break;
            }
            alpha *= CG_ALPHA_REDUCE;
            if alpha <= 0.0 || de_ideal >= -CG_EMACH || cs.evaluations >= max_eval {
                break;
            }
        }
        if !ok {
            st.pos.copy_from_slice(&x0);
            e = compute(ff, hic, &st.pos, scale, &mut st.grid, &mut st.frc).total();
            cs.stop = if cs.evaluations >= max_eval { 3 } else { 4 };
            break;
        }
        if (e - e0).abs() < etol * 0.5 * (e.abs() + e0.abs() + CG_EPS_ENERGY) {
            cs.stop = 1;
            break;
        }
        let dot0 = dot(&st.frc, &st.frc);
        let dot1 = dot(&st.frc, &g);
        if dot0 < ftol * ftol {
            cs.stop = 2;
            break;
        }
        if cs.evaluations >= max_eval {
            cs.stop = 3;
            break;
        }
        let mut beta = ((dot0 - dot1) / gg).max(0.0);
        if (iter + 1) % (3 * n) == 0 {
            beta = 0.0;
        }
        gg = dot0;
        g.copy_from_slice(&st.frc);
        for i in 0..n {
            for k in 0..3 {
                h[i][k] = g[i][k] + beta * h[i][k];
            }
        }
        if dot(&h, &g) <= 0.0 {
            h.copy_from_slice(&g);
        }
    }
    cs.e_final = e;
    cs
}

/// Stream key purposes.
pub const STREAM_VEL_RELAX: u64 = 0x5245_4c41;
pub const STREAM_VEL_STAGE: u64 = 0x5354_4147;

/// The whole M-step of one structure: stages (+ relax) then CG.
/// `key`: (seed, round, structure) for the velocity streams.
pub fn mstep(ff: &ForceField, hic: &HicBonds, st: &mut State, p: &IgmParams, key: [u64; 3]) -> (CgStats, Energies) {
    let mut last = Scale { ev: 1.0, env: 1.0 };
    for (k, sg) in p.stages.iter().enumerate() {
        let scale = Scale { ev: sg.evfactor, env: sg.envelope_factor };
        last = scale;
        if let Some(r) = &p.relax {
            let mut rng = Rng::from_keys(&[key[0], key[1], key[2], k as u64, STREAM_VEL_RELAX]);
            velocity_create(&mut st.vel, r.temperature, &mut rng);
            let rp = RunParams { n_steps: r.mdsteps, t0: r.temperature, t1: r.temperature, dt: p.timestep, xlimit: r.max_velocity, window: p.rescale_window, fraction: p.rescale_fraction, scale };
            run(ff, hic, st, &rp);
        }
        let mut rng = Rng::from_keys(&[key[0], key[1], key[2], k as u64, STREAM_VEL_STAGE]);
        velocity_create(&mut st.vel, sg.tstart, &mut rng);
        let rp = RunParams { n_steps: sg.mdsteps, t0: sg.tstart, t1: sg.tstop, dt: p.timestep, xlimit: p.max_velocity, window: p.rescale_window, fraction: p.rescale_fraction, scale };
        run(ff, hic, st, &rp);
    }
    let cs = minimize(ff, hic, st, last, p.cg_etol, p.cg_ftol, p.cg_max_iter, p.cg_max_eval, p.cg_dmax);
    let e = compute(ff, hic, &st.pos, last, &mut st.grid, &mut st.frc);
    (cs, e)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::igm::forces::tests_support::toy;

    #[test]
    fn velocity_create_zero_momentum_and_temperature() {
        let mut v = vec![[0.0; 3]; 500];
        let mut rng = Rng::new(3);
        velocity_create(&mut v, 123.0, &mut rng);
        let m: f64 = v.iter().map(|x| x[0]).sum();
        assert!(m.abs() < 1e-9);
        assert!((temperature(&v) - 123.0).abs() < 1e-9);
    }

    #[test]
    fn energy_conserved_nve() {
        // no thermostat (huge window), no limit: velocity Verlet conserves energy
        let (mut ff, hic, pos) = toy(200, 4, true);
        ff.axes = [1e7; 3];
        let mut st = State::new(pos);
        let sc = Scale { ev: 1.0, env: 1.0 };
        // relax first so forces are moderate
        minimize(&ff, &hic, &mut st, sc, 0.0, 0.0, 200, 400, 5.0);
        let mut rng = Rng::new(1);
        velocity_create(&mut st.vel, 20.0, &mut rng);
        let tot = |st: &mut State| {
            let e = compute(&ff, &hic, &st.pos, sc, &mut st.grid, &mut st.frc).total();
            e + 0.5 * st.vel.iter().map(|v| v[0] * v[0] + v[1] * v[1] + v[2] * v[2]).sum::<f64>()
        };
        let e0 = tot(&mut st);
        let rp = RunParams { n_steps: 2000, t0: 0.0, t1: 0.0, dt: 0.01, xlimit: 1e9, window: 1e30, fraction: 1.0, scale: sc };
        run(&ff, &hic, &mut st, &rp);
        let e1 = tot(&mut st);
        let kin = 0.5 * st.vel.iter().map(|v| v[0] * v[0] + v[1] * v[1] + v[2] * v[2]).sum::<f64>();
        assert!(kin > 1.0);
        assert!(((e1 - e0) / e0.abs().max(kin)).abs() < 1e-3, "drift {e0} -> {e1}");
    }

    #[test]
    fn rescale_follows_ramp_and_limit_caps() {
        let (ff, hic, pos) = toy(150, 6, true);
        let mut st = State::new(pos);
        let mut rng = Rng::new(2);
        velocity_create(&mut st.vel, 500.0, &mut rng);
        let sc = Scale { ev: 1.0, env: 1.0 };
        let rp = RunParams { n_steps: 300, t0: 500.0, t1: 50.0, dt: 0.25, xlimit: 1000.0, window: 0.1, fraction: 1.0, scale: sc };
        run(&ff, &hic, &mut st, &rp);
        assert!((temperature(&st.vel) - 50.0).abs() <= 0.1 + 1e-9, "{}", temperature(&st.vel));
        // a tiny limit caps every speed
        let rp = RunParams { n_steps: 5, t0: 5000.0, t1: 5000.0, dt: 0.25, xlimit: 0.01, window: 1e30, fraction: 1.0, scale: sc };
        velocity_create(&mut st.vel, 5000.0, &mut rng);
        run(&ff, &hic, &mut st, &rp);
        assert!(st.vel.iter().all(|v| (v[0] * v[0] + v[1] * v[1] + v[2] * v[2]).sqrt() <= 0.04 + 1e-9));
    }

    #[test]
    fn cg_decreases_energy() {
        let (ff, hic, pos) = toy(200, 7, false);
        let mut st = State::new(pos);
        let sc = Scale { ev: 1.0, env: 1.0 };
        let cs = minimize(&ff, &hic, &mut st, sc, 1e-8, 1e-8, 300, 1000, 10.0);
        assert!(cs.e_final < 0.5 * cs.e_start, "{cs:?}");
        // LAMMPS default dmax = 0.1: small steps, still downhill
        let (ff, hic, pos) = toy(200, 7, false);
        let mut st = State::new(pos);
        let cs = minimize(&ff, &hic, &mut st, sc, 1e-4, 1e-6, 500, 500, 0.1);
        assert!(cs.e_final < cs.e_start && cs.evaluations <= 500, "{cs:?}");
    }
}
