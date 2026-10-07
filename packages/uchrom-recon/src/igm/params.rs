//! Parameters of the IGM protocol.  Defaults: the IGM configuration schema
//! (`core/defaults/config_schema.json` at alberlab/igm `edbb331`) with the
//! annealing protocol of the IGM demo (`demo/config_file.json`), as listed in
//! `benchmarks/bulk/pgs_spec.md` §2.2, §3.2, §4.3, §5, §6.2.

use serde::{Deserialize, Serialize};

/// Soft assignment of one round (EMber-pop).
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct SoftAssign {
    pub beta: f64,
    pub commit: f64,
    pub min_weight: f64,
}

impl SoftAssign {
    /// Weight π of a contact at squared distance `d2` with squared activation distance `d2_act`.
    #[inline]
    pub fn weight(&self, d2: f64, d2_act: f64) -> f64 {
        let t = (0.5 * self.beta * (d2.max(1e-300).ln() - d2_act.max(1e-300).ln())).clamp(-60.0, 60.0);
        let w = 1.0 / (1.0 + t.exp());
        if w >= self.commit {
            1.0
        } else if w <= 1.0 - self.commit {
            0.0
        } else {
            w
        }
    }
}

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
    // ---- opt-in options (IGM-Plus / IGM_2.0); the defaults are IGM 1.0 ----
    /// Uniform bead radius (nm) set by the user instead of deriving radii from
    /// `occupancy` (IGM-Plus `model/bead_radius`).  0 = off.  Mutually
    /// exclusive with occupancy: when > 0, `occupancy` must be 0.
    pub bead_radius: f64,
    /// Genome size (bp, all modelled copies counted) the `occupancy` refers
    /// to.  0 = the modelled beads (IGM / IGM-Plus: with a chromosome subset
    /// the subset alone fills `occupancy` of the nucleus).  Set it to the
    /// whole genome's size to keep whole-genome bead sizes when only some
    /// chromosomes are modelled.
    pub occupancy_total_bp: f64,
    /// Iterative correction of the assignment probability in the A-step
    /// (`p = clean(f, clean(p_now, p_last))`); false: `p = f` (IGM-Plus
    /// `optimization/iter_corr_knob = 0`).
    pub iterative_correction: bool,
    /// A-step pooling of copy combinations: "igm" (IGM 1.0: intra pairs over
    /// the same-copy combinations, inter pairs over all combinations) or "gp"
    /// (G. Polles' approximation, alberlab/IGM_2.0
    /// `GP_ActivationDistanceStep.get_actdist`: every pair over all copy
    /// combinations, keeping per structure the n_possible = min(copies)
    /// smallest distances).
    pub assignment_pooling: String,
    /// Standard deviation (nm) of Gaussian noise added to every initial
    /// coordinate (after pinned loci and interpolation; IGM-Plus
    /// `model/init_noise`).  0 = off.
    pub init_noise: f64,
    // ---- EMber-pop options (benchmarks/bulk/PREREG_POP.md); defaults = IGM ----
    /// Non-contact restraints (two-sided assignment): every bead pair closer
    /// than `noncontact_range (r_i + r_j)` that is neither polymer-bonded nor
    /// assigned a Hi-C contact in the structure is pushed apart,
    /// `U = k (d0 − d)²` for `d < d0`.  0 = off (IGM).
    pub noncontact_kspring: f64,
    /// Range factor of the non-contact restraint (0 = `contact_range`).
    pub noncontact_range: f64,
    /// First σ index (0-based) of `intra_sigma_list` at which the
    /// non-contact restraints act (earlier rounds and the initial relaxation
    /// run without them).
    pub noncontact_from_sigma: usize,
    /// At `max_iterations` without an accepted iteration, go on with the next
    /// σ instead of stopping the run (IGM stops; EMber-pop advances).
    pub advance_on_max_iterations: bool,
    /// Assignment rule: "igm" (hard: a structure gets the contact iff
    /// d <= d_act) or "soft" (EMber-pop: posterior weight
    /// π = 1 / (1 + (d / d_act)^β) of the contact, the latent-contact
    /// posterior under a population-count constraint, IGM's rule as β → ∞;
    /// the contact restraint is weighted by π, the non-contact restraint by 1 − π).
    pub assignment: String,
    /// β of round r (1-based): min(soft_beta_max, soft_beta0 · soft_beta_growth^(r − 1)).
    pub soft_beta0: f64,
    pub soft_beta_growth: f64,
    pub soft_beta_max: f64,
    /// Staged commitment: π ≥ τ → 1, π ≤ 1 − τ → 0 (τ ≥ 1: off).
    pub soft_commit: f64,
    /// Contacts with π below this weight are not restrained (full non-contact).
    pub soft_min_weight: f64,
    /// Shape-free compaction (EMber-pop): radius-of-gyration upper bound (nm,
    /// 0 = off), `U = ½ k N (Rg − rg_cap)²` for Rg > rg_cap (any shape with
    /// that Rg is allowed).
    pub rg_cap: f64,
    pub rg_kspring: f64,
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
            bead_radius: 0.0,
            occupancy_total_bp: 0.0,
            iterative_correction: true,
            assignment_pooling: "igm".into(),
            init_noise: 0.0,
            noncontact_kspring: 0.0,
            noncontact_range: 0.0,
            noncontact_from_sigma: 0,
            advance_on_max_iterations: false,
            assignment: "igm".into(),
            soft_beta0: 4.0,
            soft_beta_growth: 1.0,
            soft_beta_max: 64.0,
            soft_commit: 1.0,
            soft_min_weight: 0.02,
            rg_cap: 0.0,
            rg_kspring: 1.0,
        }
    }
}

impl IgmParams {
    /// Semi-axes of the nucleus (nm); with `nucleus_shape = "none"` the
    /// sphere of `nucleus_radius` (bead volumes, initial territories), no envelope.
    pub fn semiaxes(&self) -> [f64; 3] {
        if self.nucleus_shape == "sphere" || self.nucleus_shape == "none" {
            [self.nucleus_radius; 3]
        } else {
            self.nucleus_semiaxes
        }
    }

    pub fn nucleus_volume(&self) -> f64 {
        let a = self.semiaxes();
        4.0 / 3.0 * std::f64::consts::PI * a[0] * a[1] * a[2]
    }

    /// No nuclear envelope (EMber-pop): `nucleus_shape = "none"`.
    pub fn no_envelope(&self) -> bool {
        self.nucleus_shape == "none"
    }

    /// Range factor of the non-contact restraints.
    pub fn nc_range(&self) -> f64 {
        if self.noncontact_range > 0.0 {
            self.noncontact_range
        } else {
            self.contact_range
        }
    }

    /// Whether the non-contact restraints act at σ index `si` (`None`: the initial relaxation).
    pub fn noncontact_active(&self, si: Option<usize>) -> bool {
        self.noncontact_kspring > 0.0 && si.is_some_and(|k| k >= self.noncontact_from_sigma)
    }

    /// Soft assignment (EMber-pop): β, commitment τ and minimum weight of round `round` (1-based).
    pub fn soft(&self, round: u64) -> Option<SoftAssign> {
        if self.assignment != "soft" {
            return None;
        }
        let beta = (self.soft_beta0 * self.soft_beta_growth.powi(round.saturating_sub(1) as i32)).min(self.soft_beta_max);
        Some(SoftAssign { beta, commit: self.soft_commit, min_weight: self.soft_min_weight })
    }

    /// A-step pooling of G. Polles (`assignment_pooling = "gp"`).
    pub fn gp_pooling(&self) -> bool {
        self.assignment_pooling == "gp"
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
            "sphere" | "ellipsoid" | "none" => {}
            s => return Err(format!("unknown nucleus_shape {s:?}")),
        }
        if self.semiaxes().iter().any(|&x| x <= 0.0) {
            return Err("nucleus size must be positive".into());
        }
        if self.bead_radius < 0.0 || !self.bead_radius.is_finite() {
            return Err("bead_radius must be >= 0 (0 = radii from occupancy)".into());
        }
        if self.bead_radius > 0.0 {
            if self.occupancy != 0.0 {
                return Err("bead_radius and occupancy are mutually exclusive: set occupancy to 0 when bead_radius is given".into());
            }
        } else if !(self.occupancy > 0.0 && self.occupancy < 1.0) {
            return Err("occupancy must be in (0, 1)".into());
        }
        if self.occupancy_total_bp < 0.0 {
            return Err("occupancy_total_bp must be >= 0".into());
        }
        match self.assignment_pooling.as_str() {
            "igm" | "gp" => {}
            s => return Err(format!("unknown assignment_pooling {s:?} (\"igm\" or \"gp\")")),
        }
        match self.assignment.as_str() {
            "igm" => {}
            "soft" => {
                if !(self.soft_beta0 > 0.0 && self.soft_beta_max > 0.0 && self.soft_beta_growth > 0.0) {
                    return Err("soft_beta0, soft_beta_growth and soft_beta_max must be > 0".into());
                }
                if !(self.soft_commit > 0.5) {
                    return Err("soft_commit must be > 0.5 (>= 1: no commitment)".into());
                }
                if !(0.0..1.0).contains(&self.soft_min_weight) {
                    return Err("soft_min_weight must be in [0, 1)".into());
                }
            }
            s => return Err(format!("unknown assignment {s:?} (\"igm\" or \"soft\")")),
        }
        if self.rg_cap < 0.0 || self.rg_kspring < 0.0 {
            return Err("rg_cap and rg_kspring must be >= 0".into());
        }
        if self.noncontact_kspring < 0.0 || self.noncontact_range < 0.0 {
            return Err("noncontact_kspring and noncontact_range must be >= 0".into());
        }
        if self.init_noise < 0.0 {
            return Err("init_noise must be >= 0".into());
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
