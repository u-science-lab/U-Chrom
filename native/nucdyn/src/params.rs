//! Calculation parameters.  Defaults are those of the original NucDynamics
//! command line (tjs23/nuc_dynamics, `nuc_dynamics.py`).

use serde::{Deserialize, Serialize};

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(default)]
pub struct Params {
    /// "nuc_dynamics_2017" (the `master` code that produced the Stevens et
    /// al. 2017 structures; default) or "release_1.3" (the later
    /// bead-size-scaled protocol with model selection) or "robust" (the 2017
    /// protocol with a noise-aware observation model: contact restraints
    /// re-weighted by their posterior probability of being true, see
    /// `robust.rs` and the `robust_*` fields).
    pub protocol: String,
    /// Hierarchical particle sizes in bp, applied in the given (descending) order.
    pub particle_sizes: Vec<f64>,
    /// Number of models requested (the original's `-m`).
    pub n_models: usize,
    /// Master random seed.
    pub seed: u64,
    /// Radius of the random-start sphere, in particle radii (`-rad`).
    pub random_radius: f64,
    /// Contact restraint bounds as a fraction of the ideal distance (`-lower`, `-upper`).
    pub contact_dist_lower: f64,
    pub contact_dist_upper: f64,
    /// Backbone restraint bounds (`-bb_lower`, `-bb_upper`).
    pub backbone_dist_lower: f64,
    pub backbone_dist_upper: f64,
    /// Annealing start / end temperature (`-hot`, `-cold`).
    pub temp_start: f64,
    pub temp_end: f64,
    /// Temperature steps per stage (`-temps` / `-temps_by_stage`); one value = all stages.
    pub temp_steps: Vec<usize>,
    /// Dynamics steps per temperature step (`-dyns` / `-dyns_by_stage`).
    pub dynamics_steps: Vec<usize>,
    /// Time step (`-time_step`), multiplied by `tot0` inside the integrator.
    pub time_step: f64,
    /// Contact isolation thresholds in bp (`-iso_cis`, `-iso_trans`).
    pub isolation_threshold_cis: i64,
    pub isolation_threshold_trans: i64,
    /// Contacts closer than this (bp) at both ends do not support each other.
    pub isolation_pos_error: i64,
    /// Particle size (bp) at or below which ambiguous / inactive contacts are
    /// filtered with the structure (`-struct_ambig_size`).
    pub struct_ambig_size: f64,
    /// Particle size (bp) at or below which the worse half of the models is
    /// dropped (`-remove_models_size`).
    pub remove_models_size: f64,
    /// Compute 2 x n_models above `remove_models_size` and keep the best
    /// n_models (the original's behaviour).  False: n_models throughout.
    pub ensemble_selection: bool,
    /// release_1.3: distance-restraint force constant is
    /// `dist_force_scale * n_particles / n_contacts` (215).
    pub dist_force_scale: f64,
    /// 2017: distance-restraint force constant (`fConstD`, 25).
    pub dist_force_const: f64,
    /// 2017: contact target distance = count ** dist_power_law (`-pow`).
    pub dist_power_law: f64,
    /// 2017: repulsion-list distance added to r_i + r_j (`repDist`, 2).
    pub rep_dist: f64,
    /// 2017: contacts with model-mean distance >= this are removed before
    /// stages finer than 0.5 Mb (6 radii).
    pub violated_threshold_2017: f64,
    /// 2017: reproduce the original's repulsion-list overflow (the list is
    /// replaced by zeros, i.e. repulsion is off until the next rebuild, when
    /// more pairs are found than its capacity).  Uses the original's Verlet
    /// list and rebuild schedule.  Off: repulsion is always complete.
    pub emulate_rep_list_overflow: bool,
    /// Thermostat coupling (`beta` in `run_dynamics`) and time unit factor (`tot0`).
    pub beta: f64,
    pub tot0: f64,
    /// Percentile / bead separation used to resolve ambiguous contacts in 3D.
    pub ambig_percentile: f64,
    pub ambig_min_bead_sep: i64,
    /// Neighbour-list skin (in particle radii) added to the repulsion cutoff.
    /// The original uses 2.0 (list radius 4 radii, rebuild after 1 radius of
    /// motion); the pairs inside the cutoff are the same for any skin.
    pub nl_skin: f64,
    /// CPU: repulsion pairs from a cell grid rebuilt every step (default)
    /// instead of a Verlet list with `nl_skin`.
    pub use_cells: bool,
    /// Cell-grid resolution: cells per repulsion cutoff (1: 3x3x3 cells of
    /// the cutoff size; 2: 5x5x5 cells of half the cutoff).  Performance
    /// only: the pairs within the cutoff are the same.
    pub cpu_stencil: usize,
    pub gpu_stencil: usize,
    /// "cpu" or "gpu".
    pub device: String,
    /// Worker threads (0 = all logical cores).
    pub n_threads: usize,
    /// Print progress to stderr.
    pub verbose: bool,
    // ---- protocol "robust" only (ignored by the other protocols) ----
    /// First stage whose restraints are re-weighted (0-based; the weights of
    /// stage s come from the structure of stage s - 1, so >= 1).
    pub robust_start_stage: usize,
    /// Contact kernel f(d) = exp(-((d - d0)+ / s)^k), d in particle radii of
    /// the structure the weights are computed from; k = 2 ("gauss") or 1 ("exp").
    pub robust_kernel: String,
    pub robust_d0: f64,
    /// Kernel width s (start value when learned).
    pub robust_s: f64,
    /// Learn s by maximising the mixture likelihood over `robust_s_grid`.
    pub robust_learn_s: bool,
    pub robust_s_grid: Vec<f64>,
    /// False-contact rate: start value / learned by EM.
    pub robust_eps: f64,
    pub robust_learn_eps: bool,
    pub robust_eps_min: f64,
    pub robust_eps_max: f64,
    /// Responsibilities per model (each model its own weights) instead of
    /// from the ensemble-mean contact probability (one weight set).
    pub robust_per_model: bool,
    /// EM updates per stage: the annealing schedule of a re-weighted stage is
    /// split into this many parts, weights recomputed before each.
    pub robust_segments: usize,
    /// Lower bound of a restraint weight.
    pub robust_w_floor: f64,
    /// Extra annealing passes at the final particle size (weights from the
    /// structure of the previous pass).
    pub robust_refine: usize,
    /// Keep the 2017 removal of contacts violated by >= 6 radii.
    pub robust_remove_violated: bool,
    /// Weight of a restraint from c contacts: 1 - (1 - r)^c (true) or r (false).
    pub robust_count_combine: bool,
    /// Particles sampled for the all-pairs kernel sum when there are more
    /// (0: all).
    pub robust_pair_sample: usize,
}

impl Default for Params {
    fn default() -> Self {
        Params {
            protocol: "nuc_dynamics_2017".to_string(),
            particle_sizes: vec![8e6, 4e6, 2e6, 4e5, 2e5, 1e5],
            n_models: 10,
            seed: 0,
            random_radius: 10.0,
            contact_dist_lower: 0.8,
            contact_dist_upper: 1.2,
            backbone_dist_lower: 0.1,
            backbone_dist_upper: 1.1,
            temp_start: 5000.0,
            temp_end: 10.0,
            temp_steps: vec![500],
            dynamics_steps: vec![100],
            time_step: 0.001,
            isolation_threshold_cis: 2_000_000,
            isolation_threshold_trans: 10_000_000,
            isolation_pos_error: 100,
            struct_ambig_size: 4e5,
            remove_models_size: 1e6,
            ensemble_selection: true,
            dist_force_scale: 215.0,
            dist_force_const: 25.0,
            dist_power_law: -0.33,
            rep_dist: 2.0,
            violated_threshold_2017: 6.0,
            emulate_rep_list_overflow: false,
            beta: 10.0,
            tot0: 20.458,
            ambig_percentile: 98.0,
            ambig_min_bead_sep: 3,
            nl_skin: 1.0,
            use_cells: true,
            cpu_stencil: 1,
            gpu_stencil: 2,
            device: "cpu".to_string(),
            n_threads: 0,
            verbose: false,
            robust_start_stage: 1,
            robust_kernel: "gauss".to_string(),
            robust_d0: 2.0,
            robust_s: 1.5,
            robust_learn_s: true,
            robust_s_grid: vec![0.5, 0.75, 1.0, 1.5, 2.0, 3.0, 4.0, 6.0],
            robust_eps: 0.1,
            robust_learn_eps: true,
            robust_eps_min: 1e-4,
            robust_eps_max: 0.5,
            robust_per_model: false,
            robust_segments: 1,
            robust_w_floor: 0.0,
            robust_refine: 0,
            robust_remove_violated: true,
            robust_count_combine: true,
            robust_pair_sample: 4000,
        }
    }
}

impl Params {
    /// The 2017 code's units and restraint form (`nuc_dynamics_2017`, `robust`).
    pub fn is_2017_family(&self) -> bool {
        matches!(self.protocol.as_str(), "nuc_dynamics_2017" | "robust")
    }
    pub fn temp_steps_for(&self, stage: usize) -> usize {
        by_stage(&self.temp_steps, stage)
    }
    pub fn dyn_steps_for(&self, stage: usize) -> usize {
        by_stage(&self.dynamics_steps, stage)
    }
    pub fn validate(&self) -> Result<(), String> {
        if self.particle_sizes.is_empty() {
            return Err("particle_sizes is empty".into());
        }
        if self.particle_sizes.iter().any(|&s| s <= 0.0) {
            return Err("particle sizes must be positive".into());
        }
        if self.n_models == 0 {
            return Err("n_models must be >= 1".into());
        }
        let ns = self.particle_sizes.len();
        for (name, v) in [("temp_steps", &self.temp_steps), ("dynamics_steps", &self.dynamics_steps)] {
            if v.is_empty() || (v.len() != 1 && v.len() != ns) {
                return Err(format!("{name} must have 1 or {ns} entries"));
            }
            if v.iter().any(|&x| x == 0) {
                return Err(format!("{name} must be positive"));
            }
        }
        if self.temp_start <= 0.0 || self.temp_end <= 0.0 {
            return Err("temperatures must be positive".into());
        }
        if self.nl_skin <= 0.0 {
            return Err("nl_skin must be positive".into());
        }
        match self.protocol.as_str() {
            "nuc_dynamics_2017" | "release_1.3" => {}
            "robust" => {
                if self.robust_start_stage == 0 {
                    return Err("robust_start_stage must be >= 1".into());
                }
                if !matches!(self.robust_kernel.as_str(), "gauss" | "exp") {
                    return Err(format!("unknown robust_kernel {:?}", self.robust_kernel));
                }
                if self.robust_s <= 0.0 || self.robust_s_grid.iter().any(|&x| x <= 0.0) {
                    return Err("robust kernel widths must be positive".into());
                }
                let (e0, e, e1) = (self.robust_eps_min, self.robust_eps, self.robust_eps_max);
                if !(0.0 < e0 && e0 <= e && e <= e1 && e1 < 1.0) {
                    return Err("need 0 < robust_eps_min <= robust_eps <= robust_eps_max < 1".into());
                }
                if self.robust_segments == 0 {
                    return Err("robust_segments must be >= 1".into());
                }
                if !(0.0..=1.0).contains(&self.robust_w_floor) {
                    return Err("robust_w_floor must be in [0, 1]".into());
                }
            }
            p => return Err(format!("unknown protocol {p:?}")),
        }
        match self.device.as_str() {
            "cpu" | "gpu" => Ok(()),
            d => Err(format!("unknown device {d:?}")),
        }
    }
}

fn by_stage(v: &[usize], stage: usize) -> usize {
    if v.len() == 1 {
        v[0]
    } else {
        v[stage]
    }
}

/// `particle_size ** (1/3)`: the particle radius in the original's internal units.
#[inline]
pub fn bead_size(particle_size: f64) -> f64 {
    particle_size.powf(1.0 / 3.0)
}

/// Threshold for removing violated contacts (`remove_violated_threshold`).
pub fn violated_threshold(particle_size: f64, bead: f64) -> Option<f64> {
    if particle_size < 0.25e6 {
        Some(5.0 * bead)
    } else if particle_size < 0.5e6 {
        Some(6.0 * bead)
    } else {
        None
    }
}

/// Annealing schedule of one stage: (temperature, repulsion constant) per
/// temperature step, in the original's internal units (bead-size scaled).
pub fn anneal_schedule(temp_start: f64, temp_end: f64, temp_steps: usize, bead: f64) -> Vec<(f64, f64)> {
    let adj = 1.0 / 10.0f64.atan();
    let decay = (temp_start / temp_end).ln();
    (0..temp_steps)
        .map(|step| {
            let frac = step as f64 / temp_steps as f64;
            let temp = temp_start * (-decay * frac).exp();
            let repulse = 0.5 + adj * (frac * 20.0 - 10.0).atan() / std::f64::consts::PI;
            (temp * bead * bead, repulse / (bead * bead))
        })
        .collect()
}
