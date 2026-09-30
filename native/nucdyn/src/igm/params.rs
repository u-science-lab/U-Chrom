//! Parameters of the IGM protocol.  Defaults: the IGM configuration schema
//! (`core/defaults/config_schema.json` at alberlab/igm `edbb331`) with the
//! annealing protocol of the IGM demo (`demo/config_file.json`), as listed in
//! `benchmarks/bulk/pgs_spec.md` §2.2, §3.2, §4.3, §5, §6.2.

use serde::{Deserialize, Serialize};

/// One stage of `custom_annealing_protocol` (spec §6.2).
#[derive(Clone, Debug, Serialize, Deserialize, PartialEq)]
pub struct Stage {
    pub mdsteps: usize,
    pub tstart: f64,
    pub tstop: f64,
    /// excluded-volume prefactor (`fix adapt … pair soft a … scale yes`)
    pub evfactor: f64,
    /// envelope semi-axes factor
    pub envelope_factor: f64,
}

/// Optional `relax` block, run before every stage (spec §6.2).
#[derive(Clone, Debug, Serialize, Deserialize, PartialEq)]
pub struct Relax {
    pub mdsteps: usize,
    pub temperature: f64,
    pub max_velocity: f64,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(default)]
pub struct IgmParams {
    /// Population size S.
    pub n_structures: usize,
    pub seed: u64,
    /// Genome volume occupancy (spec §2.2; schema 0.2, demo / paper 0.4).
    pub occupancy: f64,
    /// "sphere" or "ellipsoid".
    pub nucleus_shape: String,
    /// Sphere radius (nm).
    pub nucleus_radius: f64,
    /// Ellipsoid semi-axes (nm).
    pub nucleus_semiaxes: [f64; 3],
    /// Radius of the random initial territories (nm); 0 = nucleus radius
    /// (smallest semi-axis for an ellipsoid).  IGM default 5000.
    pub init_radius: f64,
    /// Contact definition: centre distance <= contact_range * (r_i + r_j) (2).
    pub contact_range: f64,
    /// Excluded-volume prefactor `evfactor` (schema 1.0).
    pub evfactor: f64,
    pub contact_kspring: f64,
    pub polymer_kspring: f64,
    pub nucleus_kspring: f64,
    /// "simple" (d0 = contact_range (r_i + r_j)) or "hic" (shell-volume form from P[i, i+1]).
    pub polymer_bonds_style: String,
    pub stages: Vec<Stage>,
    pub relax: Option<Relax>,
    pub timestep: f64,
    /// `fix nve/limit` maximum displacement per step.
    pub max_velocity: f64,
    /// `fix temp/rescale 1 t0 t1 window fraction`.
    pub rescale_window: f64,
    pub rescale_fraction: f64,
    pub cg_etol: f64,
    pub cg_ftol: f64,
    pub cg_max_iter: usize,
    pub cg_max_eval: usize,
    /// LAMMPS `min_modify dmax` (maximum displacement of the first line-search trial).
    pub cg_dmax: f64,
    pub intra_sigma_list: Vec<f64>,
    pub inter_sigma_list: Vec<f64>,
    /// Accept a sigma when violation_score < max_violations.
    pub max_violations: f64,
    /// A restraint is violated when (d - d0) / d0 > violation_tolerance.
    pub violation_tolerance: f64,
    pub min_iterations: usize,
    /// Per sigma; reaching it stops the run with the current population.
    pub max_iterations: usize,
    pub force_last_iteration: bool,
    pub force_minimum_iterations_hic_cutoff: f64,
    /// Start every M-step from a fresh random structure (`optimization/random_shuffling`).
    pub random_shuffling: bool,
    /// Skip the RelaxInit run (tests).
    pub skip_relax_init: bool,
    /// "cpu" or "gpu".
    pub device: String,
    pub n_threads: usize,
    /// GPU: structures per M-step batch (0 = automatic).
    pub batch_size: usize,
    pub verbose: bool,
}

pub fn demo_stages() -> Vec<Stage> {
    let st = |mdsteps, tstart, tstop, evfactor, envelope_factor| Stage { mdsteps, tstart, tstop, evfactor, envelope_factor };
    vec![
        st(5000, 5000.0, 500.0, 0.5, 1.2),
        st(15000, 500.0, 50.0, 1.0, 1.0),
        st(15000, 50.0, 1.0, 1.0, 1.0),
        st(10000, 1.0, 0.0, 1.0, 1.0),
    ]
}

impl Default for IgmParams {
    fn default() -> Self {
        IgmParams {
            n_structures: 10_000,
            seed: 0,
            occupancy: 0.2,
            nucleus_shape: "sphere".into(),
            nucleus_radius: 5000.0,
            nucleus_semiaxes: [5000.0, 5000.0, 5000.0],
            init_radius: 0.0,
            contact_range: 2.0,
            evfactor: 1.0,
            contact_kspring: 1.0,
            polymer_kspring: 1.0,
            nucleus_kspring: 1.0,
            polymer_bonds_style: "simple".into(),
            stages: demo_stages(),
            relax: Some(Relax { mdsteps: 500, temperature: 1.0, max_velocity: 10.0 }),
            timestep: 0.25,
            max_velocity: 1000.0,
            rescale_window: 0.1,
            rescale_fraction: 1.0,
            cg_etol: 1e-4,
            cg_ftol: 1e-6,
            cg_max_iter: 500,
            cg_max_eval: 500,
            cg_dmax: 0.1,
            intra_sigma_list: vec![1.0, 0.2, 0.1, 0.05, 0.02, 0.01],
            inter_sigma_list: vec![1.0, 0.2, 0.1, 0.05, 0.02, 0.01],
            max_violations: 0.01,
            violation_tolerance: 0.05,
            min_iterations: 5,
            max_iterations: 10,
            force_last_iteration: false,
            force_minimum_iterations_hic_cutoff: 0.0,
            random_shuffling: false,
            skip_relax_init: false,
            device: "cpu".into(),
            n_threads: 0,
            batch_size: 0,
            verbose: false,
        }
    }
}

impl IgmParams {
    /// Semi-axes of the nucleus (nm).
    pub fn semiaxes(&self) -> [f64; 3] {
        if self.nucleus_shape == "sphere" {
            [self.nucleus_radius; 3]
        } else {
            self.nucleus_semiaxes
        }
    }

    pub fn nucleus_volume(&self) -> f64 {
        let a = self.semiaxes();
        4.0 / 3.0 * std::f64::consts::PI * a[0] * a[1] * a[2]
    }

    pub fn init_radius(&self) -> f64 {
        if self.init_radius > 0.0 {
            self.init_radius
        } else {
            let a = self.semiaxes();
            a[0].min(a[1]).min(a[2])
        }
    }

    pub fn validate(&self) -> Result<(), String> {
        if self.n_structures == 0 {
            return Err("n_structures must be >= 1".into());
        }
        match self.nucleus_shape.as_str() {
            "sphere" | "ellipsoid" => {}
            s => return Err(format!("unknown nucleus_shape {s:?}")),
        }
        if self.semiaxes().iter().any(|&x| x <= 0.0) {
            return Err("nucleus size must be positive".into());
        }
        if !(self.occupancy > 0.0 && self.occupancy < 1.0) {
            return Err("occupancy must be in (0, 1)".into());
        }
        match self.polymer_bonds_style.as_str() {
            "simple" | "hic" => {}
            s => return Err(format!("unknown polymer_bonds_style {s:?}")),
        }
        if self.stages.is_empty() {
            return Err("stages is empty".into());
        }
        if self.intra_sigma_list.len() != self.inter_sigma_list.len() || self.intra_sigma_list.is_empty() {
            return Err("intra_sigma_list and inter_sigma_list must be non-empty and of equal length".into());
        }
        if self.timestep <= 0.0 || self.max_velocity <= 0.0 {
            return Err("timestep and max_velocity must be positive".into());
        }
        if self.max_iterations == 0 {
            return Err("max_iterations must be >= 1".into());
        }
        match self.device.as_str() {
            "cpu" | "gpu" => Ok(()),
            d => Err(format!("unknown device {d:?}")),
        }
    }
}
