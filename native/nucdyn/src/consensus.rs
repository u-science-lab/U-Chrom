//! Protocol "consensus": one representative structure per bulk Hi-C map by
//! hierarchical restraint annealing (new; design in
//! `benchmarks/bulk/consensus/design.md`).
//!
//! The caller (U-Chrom, `uchrom.recon.bulk.consensus`) turns the contact map
//! into one restraint set per resolution stage (targets from a power law of
//! the normalised contact frequency, bounds, confidence weights, carried-over
//! coarse restraints, backbone).  This module runs the stages on the engine
//! of the NucDynamics protocols: every run starts from a random ball (first
//! stage) or from the previous stage's structure interpolated at the new bead
//! positions (`protocol2017::interpolate`), and is annealed with the
//! NucDynamics integrator, thermostat, repulsion (exact cell grid) and
//! annealing schedule (`params::anneal_schedule`, bead-size scaled as in
//! release_1.3).  Restraints use the release_1.3 saturating form (harmonic
//! up to 1.5 d_max, constant force beyond; weighted) or the Lorentzian form
//! (`RestraintForm::Lorentzian`); optional spherical confinement.  All runs
//! of a stage are independent (random starts, own velocity streams) and are
//! computed together: in parallel on the CPU, batched on the GPU.
//!
//! Units: whatever the caller uses for the targets (U-Chrom: the distance of
//! adjacent final-resolution bins = 1).  Each stage has one bead radius; the
//! temperature and repulsion schedule are scaled by it (release_1.3).

use crate::dynamics::{compute_forces_mode, lorentz_term, Model, RestraintForm, System, V3};
use crate::params::{anneal_schedule, Params};
use crate::pipeline::StageEngine;
use crate::protocol2017::interpolate;
use crate::rng::{Rng, STREAM_COORDS};
use serde::{Deserialize, Serialize};
use std::time::Instant;

/// One resolution stage.  Beads are grouped by chromosome (contiguous), and
/// sorted by position within a chromosome.
#[derive(Clone, Debug)]
pub struct Stage {
    pub particle_size: f64,
    /// Bead radius (repulsion distance = 2 radius).
    pub radius: f64,
    pub chrom: Vec<u32>,
    /// Genomic position of every bead (e.g. the bin midpoint), for the
    /// interpolation between stages.
    pub pos: Vec<i64>,
    pub rest_i: Vec<u32>,
    pub rest_j: Vec<u32>,
    pub rest_lo: Vec<f64>,
    pub rest_hi: Vec<f64>,
    pub rest_w: Vec<f64>,
    /// "saturating" (release_1.3 form) or "lorentzian".
    pub form: String,
    /// Distance-restraint force constant K.
    pub force_const: f64,
    pub temp_start: f64,
    pub temp_end: f64,
    pub temp_steps: usize,
    pub dyn_steps: usize,
}

impl Stage {
    pub fn n(&self) -> usize {
        self.chrom.len()
    }

    fn validate(&self, k: usize) -> Result<(), String> {
        let n = self.n();
        if n == 0 {
            return Err(format!("stage {k}: no beads"));
        }
        if self.pos.len() != n {
            return Err(format!("stage {k}: chrom / pos lengths differ"));
        }
        let nr = self.rest_i.len();
        if [self.rest_j.len(), self.rest_lo.len(), self.rest_hi.len(), self.rest_w.len()].iter().any(|&x| x != nr) {
            return Err(format!("stage {k}: restraint arrays differ in length"));
        }
        if self.rest_i.iter().chain(&self.rest_j).any(|&x| x as usize >= n) {
            return Err(format!("stage {k}: restraint index out of range"));
        }
        if self.rest_lo.iter().zip(&self.rest_hi).any(|(&a, &b)| !(a >= 0.0 && b >= a && b.is_finite())) {
            return Err(format!("stage {k}: restraint bounds must satisfy 0 <= lo <= hi < inf"));
        }
        if self.rest_w.iter().any(|&w| !(w >= 0.0 && w.is_finite())) {
            return Err(format!("stage {k}: restraint weights must be finite and >= 0"));
        }
        if !(self.radius > 0.0) {
            return Err(format!("stage {k}: radius must be positive"));
        }
        for w in 0..n.saturating_sub(1) {
            if self.chrom[w + 1] < self.chrom[w] || (self.chrom[w + 1] == self.chrom[w] && self.pos[w + 1] < self.pos[w]) {
                return Err(format!("stage {k}: beads must be grouped by chromosome (ascending ids) and sorted by position"));
            }
        }
        match self.form.as_str() {
            "saturating" | "lorentzian" => {}
            f => return Err(format!("stage {k}: unknown restraint form {f:?}")),
        }
        if self.temp_steps == 0 || self.dyn_steps == 0 || !(self.temp_start > 0.0 && self.temp_end > 0.0) {
            return Err(format!("stage {k}: temperatures and step counts must be positive"));
        }
        Ok(())
    }

    fn form(&self) -> RestraintForm {
        if self.form == "lorentzian" {
            RestraintForm::Lorentzian
        } else {
            RestraintForm::Release13
        }
    }

    /// The engine's `System` of this stage (unit masses, one radius).
    pub fn system(&self, p: &ConsensusParams) -> System {
        let n = self.n();
        let pairs: Vec<[u32; 2]> = self.rest_i.iter().zip(&self.rest_j).map(|(&a, &b)| [a.min(b), a.max(b)]).collect();
        let lims: Vec<[f64; 2]> = self.rest_lo.iter().zip(&self.rest_hi).map(|(&a, &b)| [a, b]).collect();
        let groups: Vec<u32> = (0..=pairs.len() as u32).collect();
        let mut sys = System::from_arrays(n, vec![1.0; n], vec![self.radius; n], pairs, lims, self.rest_w.clone(), groups)
            .with_form(self.form());
        sys.lorentz_c = p.lorentz_width;
        if p.confinement_radius > 0.0 && p.confinement_k > 0.0 {
            sys = sys.with_confinement(p.confinement_radius, p.confinement_k);
        }
        sys
    }
}

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(default)]
pub struct ConsensusParams {
    /// Independent runs (random starts).
    pub n_runs: usize,
    pub seed: u64,
    /// "cpu" or "gpu".
    pub device: String,
    pub n_threads: usize,
    /// Lorentzian width relative to d_max.
    pub lorentz_width: f64,
    /// Spherical confinement (0: off), same units as the targets.
    pub confinement_radius: f64,
    pub confinement_k: f64,
    /// Radius of the random-start ball of the first stage.
    pub random_radius: f64,
    /// Integrator (NucDynamics defaults).
    pub time_step: f64,
    pub beta: f64,
    pub tot0: f64,
    pub cpu_stencil: usize,
    pub gpu_stencil: usize,
    /// Return the coordinates of every stage (else the last only).
    pub keep_stages: bool,
    /// Relative violation above which a restraint counts as violated in the report.
    pub violation_tolerance: f64,
    pub verbose: bool,
}

impl Default for ConsensusParams {
    fn default() -> Self {
        ConsensusParams {
            n_runs: 8,
            seed: 0,
            device: "cpu".into(),
            n_threads: 0,
            lorentz_width: 1.0,
            confinement_radius: 0.0,
            confinement_k: 1.0,
            random_radius: 10.0,
            time_step: 0.001,
            beta: 10.0,
            tot0: 20.458,
            cpu_stencil: 1,
            gpu_stencil: 2,
            keep_stages: false,
            violation_tolerance: 0.1,
            verbose: false,
        }
    }
}

impl ConsensusParams {
    pub fn validate(&self) -> Result<(), String> {
        if self.n_runs == 0 {
            return Err("n_runs must be >= 1".into());
        }
        if !(self.lorentz_width > 0.0) {
            return Err("lorentz_width must be positive".into());
        }
        if !(self.random_radius > 0.0) {
            return Err("random_radius must be positive".into());
        }
        match self.device.as_str() {
            "cpu" | "gpu" => Ok(()),
            d => Err(format!("unknown device {d:?}")),
        }
    }

    /// NucDynamics parameters for the stage engines (integrator, stencils, seed).
    pub fn engine_params(&self) -> Params {
        Params {
            protocol: "release_1.3".into(),
            n_models: self.n_runs,
            seed: self.seed,
            time_step: self.time_step,
            beta: self.beta,
            tot0: self.tot0,
            use_cells: true,
            cpu_stencil: self.cpu_stencil,
            gpu_stencil: self.gpu_stencil,
            device: self.device.clone(),
            n_threads: self.n_threads,
            verbose: self.verbose,
            ..Params::default()
        }
    }
}

/// Restraint report of one structure.
#[derive(Clone, Debug, Serialize, Default)]
pub struct RunStats {
    /// Weighted restraint energy (`sum w U`, the form of the stage).
    pub energy: f64,
    /// Restraints outside [lo, hi] / violated by more than `violation_tolerance` x the bound.
    pub n_outside: usize,
    pub n_violated: usize,
    pub n_restraints: usize,
    /// RMS of the relative violation (violation / bound).
    pub rms_rel_violation: f64,
}

#[derive(Clone, Debug, Serialize)]
pub struct StageLog {
    pub stage: usize,
    pub particle_size: f64,
    pub radius: f64,
    pub n_particles: usize,
    pub n_restraints: usize,
    pub form: String,
    pub force_const: f64,
    pub temp_start: f64,
    pub temp_end: f64,
    pub temp_steps: usize,
    pub dyn_steps: usize,
    pub start: String,
    pub seconds_prepare: f64,
    pub seconds_dynamics: f64,
    pub device: String,
    pub runs: Vec<RunStats>,
}

pub struct ConsensusOutput {
    /// runs x beads of the last stage (each run centred).
    pub coords: Vec<Vec<V3>>,
    /// per stage (only with `keep_stages`): runs x beads.
    pub stage_coords: Vec<Vec<Vec<V3>>>,
    pub stages: Vec<StageLog>,
    pub seconds_total: f64,
}

/// Weighted restraint energy of the form of `sys` (`sum_r w_r U(d_r)`; the
/// force of `compute_forces` is its negative gradient) and violation counts.
pub fn restraint_report(sys: &System, pos: &[V3], f_const: f64, tol: f64) -> RunStats {
    let mut st = RunStats { n_restraints: sys.n_restraints(), ..Default::default() };
    let mut s2 = 0.0;
    for ((p, l), &w) in sys.rest_pairs.iter().zip(&sys.rest_lim).zip(&sys.rest_w) {
        if p[0] == p[1] {
            continue;
        }
        let (a, b) = (pos[p[0] as usize], pos[p[1] as usize]);
        let r = ((a[0] - b[0]).powi(2) + (a[1] - b[1]).powi(2) + (a[2] - b[2]).powi(2)).sqrt();
        let [lo, hi] = *l;
        let rel = if r < lo {
            (lo - r) / lo.max(1e-12)
        } else if r > hi {
            (r - hi) / hi.max(1e-12)
        } else {
            0.0
        };
        if rel > 0.0 {
            st.n_outside += 1;
        }
        if rel > tol {
            st.n_violated += 1;
        }
        s2 += rel * rel;
        st.energy += w * pair_energy(sys.form, r.max(1e-4), lo, hi, sys.lorentz_c, f_const);
    }
    st.rms_rel_violation = (s2 / st.n_restraints.max(1) as f64).sqrt();
    st
}

/// Energy of one single (non-ambiguous) restraint without the weight.
pub fn pair_energy(form: RestraintForm, r: f64, lo: f64, hi: f64, lorentz_c: f64, f_const: f64) -> f64 {
    match form {
        RestraintForm::Lorentzian => lorentz_term(r, lo, hi, lorentz_c, f_const).map(|x| x.0).unwrap_or(0.0),
        _ => {
            // release_1.3 (exponent 2, switch 0.5 d_max, asymptote 1): continuous energy
            let ds = 0.5 * hi;
            if r < lo {
                f_const * (lo - r) * (lo - r)
            } else if r <= hi {
                0.0
            } else if r <= hi + ds {
                f_const * (r - hi) * (r - hi)
            } else {
                f_const * (ds * ds + 2.0 * ds * (r - hi - ds))
            }
        }
    }
}

fn random_ball(n: usize, radius: f64, rng: &mut Rng) -> Vec<V3> {
    (0..n)
        .map(|_| {
            let u = rng.uniform();
            let x = [rng.normal(), rng.normal(), rng.normal()];
            let norm = (x[0] * x[0] + x[1] * x[1] + x[2] * x[2]).sqrt().max(1e-12);
            let s = radius * u.powf(1.0 / 3.0) / norm;
            [x[0] * s, x[1] * s, x[2] * s]
        })
        .collect()
}

/// Ranges of beads per chromosome: (chrom, start, end).
fn chrom_ranges(chrom: &[u32]) -> Vec<(u32, usize, usize)> {
    let mut out = vec![];
    let mut s = 0;
    for i in 1..=chrom.len() {
        if i == chrom.len() || chrom[i] != chrom[s] {
            out.push((chrom[s], s, i));
            s = i;
        }
    }
    out
}

/// Start coordinates of stage `k` of every run: the previous stage
/// interpolated at the new bead positions (per chromosome; ends clamped).  A
/// chromosome absent from the previous stage starts in a small random ball
/// around the previous structure's centre.
pub fn interpolate_stage(prev: &Stage, prev_coords: &[Vec<V3>], next: &Stage, seed: u64, k: usize) -> Vec<Vec<V3>> {
    let pr = chrom_ranges(&prev.chrom);
    let nr = chrom_ranges(&next.chrom);
    prev_coords
        .iter()
        .enumerate()
        .map(|(run, pc)| {
            let mut out = Vec::with_capacity(next.n());
            for &(c, s, e) in &nr {
                match pr.iter().find(|x| x.0 == c) {
                    Some(&(_, ps, pe)) => {
                        for &x in &next.pos[s..e] {
                            out.push(interpolate(x, &prev.pos[ps..pe], &pc[ps..pe]));
                        }
                    }
                    None => {
                        let mut rng = Rng::from_keys(&[seed, k as u64, c as u64, run as u64, STREAM_COORDS]);
                        out.extend(random_ball(e - s, 2.0 * next.radius, &mut rng));
                    }
                }
            }
            out
        })
        .collect()
}

fn centre(c: &mut [V3]) {
    let k = c.len() as f64;
    let mut m = [0.0; 3];
    for q in c.iter() {
        for d in 0..3 {
            m[d] += q[d];
        }
    }
    for q in c.iter_mut() {
        for d in 0..3 {
            q[d] -= m[d] / k;
        }
    }
}

fn log(p: &ConsensusParams, msg: &str) {
    if p.verbose {
        eprintln!("[uchrom_nucdyn consensus] {msg}");
    }
}

/// Run every stage.  `start`: coordinates of the first stage for every run
/// (e.g. the superposed mean for a refinement), else random balls.
pub fn run_consensus(
    stages: &[Stage],
    p: &ConsensusParams,
    engine: &mut dyn StageEngine,
    start: Option<Vec<Vec<V3>>>,
) -> Result<ConsensusOutput, String> {
    p.validate()?;
    if stages.is_empty() {
        return Err("no stages".into());
    }
    for (k, s) in stages.iter().enumerate() {
        s.validate(k)?;
    }
    if let Some(st) = &start {
        if st.len() != p.n_runs || st.iter().any(|c| c.len() != stages[0].n()) {
            return Err(format!("start coordinates must be {} runs x {} beads", p.n_runs, stages[0].n()));
        }
    }
    let t0 = Instant::now();
    let ep = p.engine_params();
    let mut logs = vec![];
    let mut stage_coords = vec![];
    let mut prev: Option<Vec<Vec<V3>>> = None;
    let mut start = start;
    for (k, st) in stages.iter().enumerate() {
        let ts = Instant::now();
        let sys = st.system(p);
        let (coords, how) = match (k, start.take(), prev.as_ref()) {
            (0, Some(c), _) => (c, "given"),
            (0, None, _) => (
                (0..p.n_runs)
                    .map(|r| {
                        let mut rng = Rng::from_keys(&[p.seed, 0, r as u64, STREAM_COORDS, 0xC0]);
                        random_ball(st.n(), p.random_radius, &mut rng)
                    })
                    .collect(),
                "random",
            ),
            (_, _, Some(pc)) => (interpolate_stage(&stages[k - 1], pc, st, p.seed, k), "interpolated"),
            _ => unreachable!(),
        };
        let schedule = anneal_schedule(st.temp_start, st.temp_end, st.temp_steps, st.radius);
        let t_prep = ts.elapsed().as_secs_f64();
        log(
            p,
            &format!(
                "stage {} ({} kb): {} beads, {} restraints, {} runs, K = {:.3}, T {} -> {}",
                k + 1,
                st.particle_size / 1e3,
                st.n(),
                sys.n_restraints(),
                p.n_runs,
                st.force_const,
                st.temp_start,
                st.temp_end
            ),
        );
        let td = Instant::now();
        let mut out = engine.anneal(&sys, coords, &schedule, st.dyn_steps, st.force_const, st.radius, k, &ep)?;
        for c in out.iter_mut() {
            centre(c);
        }
        let t_dyn = td.elapsed().as_secs_f64();
        let runs: Vec<RunStats> = out.iter().map(|c| restraint_report(&sys, c, st.force_const, p.violation_tolerance)).collect();
        log(p, &format!("stage {} done: {:.2} s dynamics", k + 1, t_dyn));
        logs.push(StageLog {
            stage: k,
            particle_size: st.particle_size,
            radius: st.radius,
            n_particles: st.n(),
            n_restraints: sys.n_restraints(),
            form: st.form.clone(),
            force_const: st.force_const,
            temp_start: st.temp_start,
            temp_end: st.temp_end,
            temp_steps: st.temp_steps,
            dyn_steps: st.dyn_steps,
            start: how.into(),
            seconds_prepare: t_prep,
            seconds_dynamics: t_dyn,
            device: engine.name(),
            runs,
        });
        if p.keep_stages {
            stage_coords.push(out.clone());
        }
        prev = Some(out);
    }
    Ok(ConsensusOutput { coords: prev.unwrap(), stage_coords, stages: logs, seconds_total: t0.elapsed().as_secs_f64() })
}

/// Energy (weighted restraints + repulsion + confinement) and forces of one
/// structure: the force the dynamics uses, for tests.
pub fn energy_and_forces(sys: &System, pos: &[V3], f_rep: f64, f_dist: f64) -> (f64, Vec<V3>) {
    let mut m = Model::new(pos.to_vec(), Rng::new(0));
    let (e_rep, _) = compute_forces_mode(sys, &mut m, f_rep, f_dist, false, true, true);
    let mut e = e_rep;
    for ((p, l), &w) in sys.rest_pairs.iter().zip(&sys.rest_lim).zip(&sys.rest_w) {
        let (a, b) = (pos[p[0] as usize], pos[p[1] as usize]);
        let r = ((a[0] - b[0]).powi(2) + (a[1] - b[1]).powi(2) + (a[2] - b[2]).powi(2)).sqrt();
        e += w * pair_energy(sys.form, r, l[0], l[1], sys.lorentz_c, f_dist);
    }
    (e, m.force)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::pipeline::CpuEngine;

    fn toy_system(form: RestraintForm, conf: bool, seed: u64) -> (System, Vec<V3>) {
        let n = 80;
        let mut rng = Rng::new(seed);
        let mut pos = vec![];
        let mut p = [0.0f64; 3];
        for _ in 0..n {
            p = [p[0] + rng.normal() * 0.9, p[1] + rng.normal() * 0.9, p[2] + rng.normal() * 0.9];
            pos.push(p);
        }
        let mut pairs = vec![];
        let mut lims = vec![];
        let mut w = vec![];
        for i in 0..n - 1 {
            pairs.push([i as u32, i as u32 + 1]);
            lims.push([0.2, 1.2]);
            w.push(3.0);
        }
        let mut seen = std::collections::HashSet::new();
        for k in 0..3 * n {
            let i = (rng.uniform() * n as f64) as u32;
            let j = (rng.uniform() * n as f64) as u32;
            if (i as i64 - j as i64).abs() < 2 || !seen.insert((i.min(j), i.max(j))) {
                continue;
            }
            let t = 1.0 + 4.0 * rng.uniform();
            pairs.push([i.min(j), i.max(j)]);
            lims.push([0.8 * t, 1.2 * t]);
            w.push(0.2 + (k % 5) as f64 * 0.4);
        }
        let groups = (0..=pairs.len() as u32).collect();
        let mut sys = System::from_arrays(n, vec![1.0; n], vec![0.5; n], pairs, lims, w, groups).with_form(form);
        sys.lorentz_c = 0.7;
        if conf {
            sys = sys.with_confinement(3.0, 2.5);
        }
        (sys, pos)
    }

    /// Forces of the consensus terms (weighted saturating / Lorentzian
    /// restraints, repulsion, confinement) = -grad of the weighted energy.
    #[test]
    fn consensus_forces_match_finite_differences() {
        for (form, conf) in [
            (RestraintForm::Release13, false),
            (RestraintForm::Lorentzian, false),
            (RestraintForm::Lorentzian, true),
            (RestraintForm::Release13, true),
        ] {
            let (sys, pos) = toy_system(form, conf, 7);
            let (f_rep, f_dist) = (0.6, 3.0);
            let (_, f) = energy_and_forces(&sys, &pos, f_rep, f_dist);
            let h = 1e-6;
            let (mut max_err, mut max_f) = (0.0f64, 0.0f64);
            for i in 0..sys.n {
                for d in 0..3 {
                    let mut p1 = pos.clone();
                    p1[i][d] += h;
                    let mut p2 = pos.clone();
                    p2[i][d] -= h;
                    let num = -(energy_and_forces(&sys, &p1, f_rep, f_dist).0 - energy_and_forces(&sys, &p2, f_rep, f_dist).0) / (2.0 * h);
                    max_err = max_err.max((num - f[i][d]).abs());
                    max_f = max_f.max(num.abs());
                }
            }
            eprintln!("{form:?} conf={conf}: max |F| {max_f:.3}, max error {max_err:.2e}");
            assert!(max_f > 1.0);
            assert!(max_err < 1e-5 * max_f.max(1.0), "{form:?} conf={conf}: max_err {max_err} max_f {max_f}");
        }
    }

    #[test]
    fn lorentzian_is_bounded_and_redescending() {
        let (lo, hi, c, k) = (0.8, 1.2, 0.5, 2.0);
        let e_far = lorentz_term(100.0, lo, hi, c, k).unwrap().0;
        assert!((e_far - k * (c * hi) * (c * hi)).abs() < 1e-3 * e_far);
        let f_small = lorentz_term(1.25, lo, hi, c, k).unwrap().1.abs();
        let f_far = lorentz_term(50.0, lo, hi, c, k).unwrap().1.abs();
        assert!(f_far < 1e-3 * f_small.max(1e-9) * 1e3 && f_far < 1e-3, "force at 50: {f_far}");
        assert!(lorentz_term(1.0, lo, hi, c, k).is_none());
        // harmonic limit: U ~ K delta^2 for delta << c
        let d = 1e-3;
        let e = lorentz_term(hi + d, lo, hi, c, k).unwrap().0;
        assert!((e / (k * d * d) - 1.0).abs() < 1e-4);
    }

    /// A chain folded into a known shape: restraints at the true distances of
    /// random pairs (2 stages) recover it; returns the distance-matrix r of each run.
    fn recovery(eng: &mut dyn StageEngine, form: &str) -> Vec<f64> {
        // truth: a random walk of 120 beads, step 1, confined loosely
        let n = 120usize;
        let mut rng = Rng::new(3);
        let mut truth = vec![[0.0f64; 3]; n];
        for i in 1..n {
            loop {
                let v = [rng.normal(), rng.normal(), rng.normal()];
                let l = (v[0] * v[0] + v[1] * v[1] + v[2] * v[2]).sqrt();
                let q = [truth[i - 1][0] + v[0] / l, truth[i - 1][1] + v[1] / l, truth[i - 1][2] + v[2] / l];
                if (q[0] * q[0] + q[1] * q[1] + q[2] * q[2]).sqrt() < 4.0 {
                    truth[i] = q;
                    break;
                }
            }
        }
        let dist = |a: &V3, b: &V3| ((a[0] - b[0]).powi(2) + (a[1] - b[1]).powi(2) + (a[2] - b[2]).powi(2)).sqrt();
        let make_stage = |factor: usize, radius: f64, temp_start: f64, all: bool| -> Stage {
            // coarse beads = means of `factor` fine beads
            let m = n / factor;
            let pts: Vec<V3> = (0..m)
                .map(|b| {
                    let mut c = [0.0; 3];
                    for i in b * factor..(b + 1) * factor {
                        for d in 0..3 {
                            c[d] += truth[i][d] / factor as f64;
                        }
                    }
                    c
                })
                .collect();
            let (mut ri, mut rj, mut lo, mut hi, mut w) = (vec![], vec![], vec![], vec![], vec![]);
            for i in 0..m {
                for j in i + 1..m {
                    if !all && j - i > 8 && (i * 7 + j * 13) % 5 != 0 {
                        continue;
                    }
                    let d = dist(&pts[i], &pts[j]).max(2.0 * radius);
                    ri.push(i as u32);
                    rj.push(j as u32);
                    lo.push(0.9 * d);
                    hi.push(1.1 * d);
                    w.push(if j == i + 1 { 3.0 } else { 1.0 });
                }
            }
            let nr = ri.len() as f64;
            Stage {
                particle_size: (factor * 10_000) as f64,
                radius,
                chrom: vec![0; m],
                pos: (0..m).map(|b| ((b * factor) as i64 * 10_000) + (factor as i64 * 5_000)).collect(),
                rest_i: ri,
                rest_j: rj,
                rest_lo: lo,
                rest_hi: hi,
                rest_w: w,
                form: form.into(),
                force_const: 50.0 * m as f64 / nr,
                temp_start,
                temp_end: 10.0,
                temp_steps: 150,
                dyn_steps: 60,
            }
        };
        let stages = vec![make_stage(4, 0.3, 5000.0, true), make_stage(1, 0.3, 500.0, false)];
        let p = ConsensusParams { n_runs: 4, seed: 11, random_radius: 6.0, n_threads: 4, ..Default::default() };
        let p = ConsensusParams { device: eng.name(), ..p };
        let p = ConsensusParams { device: if p.device.starts_with("gpu") { "gpu".into() } else { "cpu".into() }, ..p };
        let out = run_consensus(&stages, &p, eng, None).unwrap();
        assert_eq!(out.coords.len(), 4);
        let mut rs = vec![];
        for c in &out.coords {
            let (mut a, mut b) = (vec![], vec![]);
            for i in 0..n {
                for j in i + 2..n {
                    a.push(dist(&truth[i], &truth[j]));
                    b.push(dist(&c[i], &c[j]));
                }
            }
            let (ma, mb) = (a.iter().sum::<f64>() / a.len() as f64, b.iter().sum::<f64>() / b.len() as f64);
            let (mut sab, mut saa, mut sbb) = (0.0, 0.0, 0.0);
            for (x, y) in a.iter().zip(&b) {
                sab += (x - ma) * (y - mb);
                saa += (x - ma) * (x - ma);
                sbb += (y - mb) * (y - mb);
            }
            rs.push(sab / (saa * sbb).sqrt());
        }
        eprintln!(
            "{} {form}: distance-matrix r vs truth per run: {rs:?}; violated (run 0) per stage: {:?}",
            eng.name(),
            out.stages.iter().map(|s| s.runs[0].n_violated).collect::<Vec<_>>()
        );
        rs
    }

    #[test]
    fn two_stage_recovers_a_known_structure() {
        let mut eng = CpuEngine::new(4).unwrap();
        for form in ["saturating", "lorentzian"] {
            let rs = recovery(&mut eng, form);
            assert!(rs.iter().all(|&r| r > 0.9), "{form}: {rs:?}");
        }
    }

    #[cfg(feature = "gpu")]
    #[test]
    fn two_stage_recovery_on_the_gpu() {
        let Ok(mut eng) = crate::gpu::GpuEngine::new(0) else {
            eprintln!("no GPU adapter: skipped");
            return;
        };
        for form in ["saturating", "lorentzian"] {
            let rs = recovery(&mut eng, form);
            assert!(rs.iter().all(|&r| r > 0.9), "{form}: {rs:?}");
        }
    }

    #[test]
    fn interpolation_between_stages_follows_the_chain() {
        let prev = Stage {
            particle_size: 4e5,
            radius: 1.0,
            chrom: vec![0, 0, 0, 1],
            pos: vec![200_000, 600_000, 1_000_000, 200_000],
            rest_i: vec![],
            rest_j: vec![],
            rest_lo: vec![],
            rest_hi: vec![],
            rest_w: vec![],
            form: "saturating".into(),
            force_const: 1.0,
            temp_start: 1.0,
            temp_end: 1.0,
            temp_steps: 1,
            dyn_steps: 1,
        };
        let next = Stage { chrom: vec![0, 0, 1, 2], pos: vec![400_000, 1_100_000, 50_000, 0], ..prev.clone() };
        let pc = vec![vec![[0.0, 0.0, 0.0], [4.0, 0.0, 0.0], [8.0, 0.0, 0.0], [1.0, 1.0, 1.0]]];
        let out = interpolate_stage(&prev, &pc, &next, 0, 1);
        assert!((out[0][0][0] - 2.0).abs() < 1e-6);
        assert!((out[0][1][0] - 8.0).abs() < 1e-6);
        assert_eq!(out[0][2], [1.0, 1.0, 1.0]);
        assert!(out[0][3][0].abs() <= 2.0);
    }
}
