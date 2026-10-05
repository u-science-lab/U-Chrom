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
    // Defaults: the parameter set recommended from the development set
    // (benchmarks/screcon/robust_devlog.md: M2 variant es4 + M3 candidate c2 —
    // 2,500 MD steps per stage, short cool refinement, sampling at T = 1000,
    // adaptive resolution below 25 kb).
    /// First stage whose restraints are re-weighted (0-based; the weights of
    /// stage s come from the structure of stage s - 1, so >= 1).
    pub robust_start_stage: usize,
    /// Schedule of the robust protocol (empty: `temp_steps` / `dynamics_steps`);
    /// one value = every stage, else one per particle size.
    pub robust_temp_steps: Vec<usize>,
    pub robust_dynamics_steps: Vec<usize>,
    /// Contact kernel f(d) = exp(-((d - d0)+ / s)^k), d in particle radii of
    /// the structure the weights are computed from; k = 2 ("gauss") or 1 ("exp").
    pub robust_kernel: String,
    pub robust_d0: f64,
    /// Non-empty: learn d0 with s (likelihood over the grid product).
    pub robust_d0_grid: Vec<f64>,
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
    /// > 0: scale the restraint force constant by min(1, x N / W), W the sum of
    /// contact-restraint weights, N the particles (bounds the contact pull per
    /// particle at high depth).  0: the 2017 constant.
    pub robust_force_norm: f64,
    /// > 0: restraint target distance from min(count, cap) ** power_law.
    pub robust_count_cap: u32,
    /// > 0: "no contact" term (Poisson capture) on every pair |i - j| >= 2:
    /// U = x q exp(-((d - nc_d0)+ / nc_s)^2), q the capture efficiency of the
    /// latest EM update (at most `robust_nc_qmax`); 0: off.
    pub robust_nc_scale: f64,
    pub robust_nc_d0: f64,
    pub robust_nc_s: f64,
    pub robust_nc_qmax: f64,
    /// > 0: local-support evidence (`support.rs`) with window half-width
    /// `robust_support_rel` x the final particle size; multiplies `prior_lr`.
    pub robust_support_rel: f64,
    /// Adaptive resolution: at particle sizes <= this (bp; 0 = never) runs of
    /// contact-free particles are dropped and interpolated in the output; a
    /// backbone gap of g sizes gets bounds x g^`robust_merge_nu`.
    pub robust_merge_below: f64,
    /// Refinement passes: temperature steps (0 = as the final stage) and start
    /// temperature (0 = `temp_start`).
    pub robust_refine_temp_steps: usize,
    pub robust_refine_temp_start: f64,
    pub robust_merge_nu: f64,
    /// Sampling after the final stage (0 = off): temperature, temperature steps
    /// per snapshot, MD steps per temperature step (0 = as the stage),
    /// snapshots per model (each becomes an output model).
    pub robust_sample_temp: f64,
    pub robust_sample_steps: usize,
    pub robust_sample_dyn_steps: usize,
    pub robust_sample_snapshots: usize,
    // ---- diploid (homolog-resolved) input only (`diploid.rs`; ignored for haploid input) ----
    /// Unphased ends of an intra-chromosomal contact closer than this (bp) are taken to be on
    /// the same homolog (hickit's imputation prior gives P(same homolog) >= 0.99 below
    /// 10 Mb); 0: every copy combination is a candidate.
    pub diploid_cis_sep: i64,
    /// EMber (protocol robust): from the first re-weighted stage on, every candidate copy pair
    /// of an ambiguous contact is its own restraint, weighted by its posterior probability
    /// (true contact on that copy pair).  False: the candidates stay one ambiguous restraint
    /// (NucDynamics combined distance) weighted by the probability that the contact is true.
    /// Default false: chosen on the diploid development set (benchmarks/screcon/diploid_devlog.md:
    /// splitting the soft responsibilities pulls both homologs together early and loses
    /// ~0.2 cis / ~0.3 whole-genome Spearman on the imaging truths).
    pub robust_dip_split: bool,
    /// EMber: multiply the candidate prior by a 2-D neighbourhood phase prior (phased contacts
    /// near the contact in both ends vote for its copy pair; hickit's imputation, re-implemented
    /// with hickit's settings: `diploid::neighbour_prior`).  Default true: chosen on the diploid
    /// development set (diploid_devlog.md §3: phase accuracy +0.06 on the imaging truths, +0.09
    /// on masked GM12878 phases, structure metrics unchanged within 0.01).
    pub robust_dip_nbr_prior: bool,
    /// EMber, deep low-phasing data (benchmarks/screcon/PREREG.md §11; 0 = off, the frozen
    /// behaviour): commit an ambiguous contact to one copy pair when its phase probability is
    /// >= this threshold (hard phasing as hickit `-S`, which uses 0.75).  The probability is the
    /// candidate prior (neighbourhood prior x external prior) before stage
    /// `robust_dip_commit_stage`, or the EM posterior P(c | true) of the structure at that stage.
    pub robust_dip_commit: f64,
    /// With `robust_dip_commit`: the ambiguous contacts below the threshold are dropped (true, as
    /// hickit `-S`) or kept as ambiguous restraints (false).
    pub robust_dip_commit_drop: bool,
    /// With `robust_dip_commit`: -1 = commit by the prior before stage 1; k >= 1 = commit by the
    /// EM posterior of the structure from stage k (0-based stage index k, so after k stages).
    pub robust_dip_commit_stage: i64,
    /// With `robust_dip_commit` by the prior and `robust_dip_commit_drop`: -1 = off; k >= 1 = the
    /// contacts dropped by the prior are re-admitted at stage k (0-based) as ambiguous restraints
    /// and, at stage k + 1, committed by the EM posterior of the structure (>= the same
    /// threshold) or dropped.
    pub robust_dip_readmit_stage: i64,
    /// Diploid input, both protocols (0 = off): before stage 1, keep a contact only if at least
    /// this many other contacts of the same chromosome pair have both ends within
    /// `dip_isolation_radius` (Chebyshev; hickit `-r R -c K`).
    pub dip_isolation_nei: u32,
    pub dip_isolation_radius: i64,
    // ---- few-cell deconvolution ("EMber-mix", `mix.rs`; protocol "robust", haploid input) ----
    /// Number of cells pooled in the input (0 / 1 = off: one structure).  >= 2: the contacts are
    /// deconvolved into this many cells of `n_models` replicate models each (output cell-major).
    pub mix_cells: usize,
    /// Independent symmetry-breaking seeds annealed side by side; the one with the highest
    /// mixture likelihood is kept after stage `mix_select_stage` (0-based).
    pub mix_restarts: usize,
    pub mix_select_stage: usize,
    /// Symmetry-breaking seed of the first stage: "patch" (random 2-D patches of the contact map
    /// to random cells), "random" (every contact to a random cell) or "uniform" (none).
    pub mix_seed: String,
    /// Mean contacts per seed patch.
    pub mix_seed_patch: f64,
    /// Contacts closer than this (bp, cis) are not seeded (uniform over the cells).
    pub mix_seed_min_sep: i64,
    /// Fraction of the seed kept in the E-step prior after the first stage (0: uniform prior).
    pub mix_seed_keep: f64,
    /// Seed "tri" (triangle consistency, `mixseed.rs`): locus grid (bp), neighbours per edge end,
    /// mean-field iterations, temperature from t0 to t1.
    pub mix_tri_res: i64,
    pub mix_tri_max: usize,
    pub mix_tri_iters: usize,
    pub mix_tri_t0: f64,
    pub mix_tri_t1: f64,
    /// Trans-triangle coupling of the cell priors in the EM (exponent; 0 = off; locus grid
    /// `mix_tri_res`) and its pseudo-count.
    pub mix_tri_prior: f64,
    pub mix_tri_pseudo: f64,
    /// E-step prior over the cells after the first stage: "uniform" (the seed kept by
    /// `mix_seed_keep`) or "posterior" (the previous update's posterior^`mix_prior_temp`, mixed
    /// with `mix_prior_floor` of uniform).
    pub mix_prior_mode: String,
    /// Flat region of the contact kernel in the final cell assignment (radii; EMber's d0 = 2).
    pub mix_assign_d0: f64,
    /// Shape-free soft density cap (`dynamics::DensityCap`): ρ_max (0 = off), kernel radius R
    /// (radii), strength κ, first stage (0-based) it acts in.
    pub mix_density_rho: f64,
    pub mix_density_r: f64,
    pub mix_density_kappa: f64,
    pub mix_density_stage: i64,
    pub mix_prior_temp: f64,
    pub mix_prior_floor: f64,
    /// Learn the mixing weights λ (cells of different depth).
    pub mix_learn_pi: bool,
    pub mix_pi_floor: f64,
    /// 2-D neighbourhood smoothing of the cell posteriors as the next prior: exponent γ (0 = off),
    /// radius (bp, Chebyshev), neighbours per contact, pseudo-count.
    pub mix_nbr_prior: f64,
    pub mix_nbr_radius: i64,
    pub mix_nbr_max: usize,
    pub mix_nbr_pseudo: f64,
    /// Staged commitment: from stage `mix_commit_stage` (0-based; -1 = off) a contact whose cell
    /// posterior reaches `mix_commit` (0 = off) is restrained in that cell only; with
    /// `mix_commit_drop` the others are left out at that stage and re-admitted at
    /// `mix_readmit_stage` (-1 = never).
    pub mix_commit: f64,
    pub mix_commit_stage: i64,
    pub mix_commit_drop: bool,
    pub mix_readmit_stage: i64,
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
            robust_temp_steps: vec![50],
            robust_dynamics_steps: vec![50],
            robust_kernel: "exp".to_string(),
            robust_d0: 2.0,
            robust_d0_grid: vec![],
            robust_s: 1.5,
            robust_learn_s: true,
            robust_s_grid: vec![0.5, 0.75, 1.0, 1.5, 2.0, 3.0, 4.0, 6.0],
            robust_eps: 0.1,
            robust_learn_eps: true,
            robust_eps_min: 1e-4,
            robust_eps_max: 0.5,
            robust_per_model: false,
            robust_segments: 2,
            robust_w_floor: 0.0,
            robust_refine: 1,
            robust_remove_violated: true,
            robust_count_combine: true,
            robust_pair_sample: 4000,
            robust_force_norm: 0.0,
            robust_count_cap: 0,
            robust_nc_scale: 0.0,
            robust_nc_d0: 2.0,
            robust_nc_s: 0.5,
            robust_nc_qmax: 10.0,
            robust_support_rel: 4.0,
            robust_merge_below: 25000.0,
            robust_refine_temp_steps: 10,
            robust_refine_temp_start: 500.0,
            robust_merge_nu: 0.5,
            robust_sample_temp: 1000.0,
            robust_sample_steps: 20,
            robust_sample_dyn_steps: 20,
            robust_sample_snapshots: 1,
            diploid_cis_sep: 10_000_000,
            robust_dip_split: false,
            robust_dip_nbr_prior: true,
            robust_dip_commit: 0.0,
            robust_dip_commit_drop: true,
            robust_dip_commit_stage: -1,
            robust_dip_readmit_stage: -1,
            dip_isolation_nei: 0,
            dip_isolation_radius: 10_000_000,
            mix_cells: 0,
            mix_restarts: 1,
            mix_select_stage: 1,
            mix_seed: "patch".to_string(),
            mix_seed_patch: 50.0,
            mix_seed_min_sep: 2_000_000,
            mix_seed_keep: 0.0,
            mix_tri_res: 1_000_000,
            mix_tri_max: 64,
            mix_tri_iters: 200,
            mix_tri_t0: 2.0,
            mix_tri_t1: 0.05,
            mix_tri_prior: 0.0,
            mix_tri_pseudo: 1.0,
            mix_prior_mode: "uniform".to_string(),
            mix_assign_d0: 0.0,
            mix_density_rho: 0.0,
            mix_density_r: 2.0,
            mix_density_kappa: 1.0,
            mix_density_stage: 0,
            mix_prior_temp: 1.0,
            mix_prior_floor: 0.05,
            mix_learn_pi: true,
            mix_pi_floor: 0.01,
            mix_nbr_prior: 0.0,
            mix_nbr_radius: 10_000_000,
            mix_nbr_max: 50,
            mix_nbr_pseudo: 0.4,
            mix_commit: 0.0,
            mix_commit_stage: -1,
            mix_commit_drop: false,
            mix_readmit_stage: -1,
        }
    }
}

impl Params {
    /// The 2017 code's units and restraint form (`nuc_dynamics_2017`, `robust`).
    pub fn is_2017_family(&self) -> bool {
        matches!(self.protocol.as_str(), "nuc_dynamics_2017" | "robust")
    }
    /// protocol robust: `robust_temp_steps` when set, else `temp_steps`
    pub fn robust_temp_steps_for(&self, stage: usize) -> usize {
        if self.robust_temp_steps.is_empty() { by_stage(&self.temp_steps, stage) } else { by_stage(&self.robust_temp_steps, stage) }
    }
    pub fn robust_dyn_steps_for(&self, stage: usize) -> usize {
        if self.robust_dynamics_steps.is_empty() { by_stage(&self.dynamics_steps, stage) } else { by_stage(&self.robust_dynamics_steps, stage) }
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
        if self.robust_dip_commit != 0.0 && !(self.robust_dip_commit > 0.5 && self.robust_dip_commit <= 1.0) {
            return Err("robust_dip_commit: 0 (off) or a threshold in (0.5, 1]".into());
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
                for (name, v) in [("robust_temp_steps", &self.robust_temp_steps), ("robust_dynamics_steps", &self.robust_dynamics_steps)] {
                    if !v.is_empty() && ((v.len() != 1 && v.len() != ns) || v.contains(&0)) {
                        return Err(format!("{name} must be empty or have 1 or {ns} positive entries"));
                    }
                }
                if self.robust_segments == 0 {
                    return Err("robust_segments must be >= 1".into());
                }
                if self.robust_nc_scale > 0.0 && (!self.use_cells || self.robust_nc_s <= 0.0) {
                    return Err("robust_nc_scale needs use_cells and robust_nc_s > 0".into());
                }
                if !(0.0..=1.0).contains(&self.robust_w_floor) {
                    return Err("robust_w_floor must be in [0, 1]".into());
                }
                if self.mix_cells >= 2 {
                    if !matches!(self.mix_seed.as_str(), "patch" | "random" | "uniform" | "tri") {
                        return Err(format!("unknown mix_seed {:?}", self.mix_seed));
                    }
                    if self.mix_commit != 0.0 && !(self.mix_commit > 0.0 && self.mix_commit <= 1.0) {
                        return Err("mix_commit: 0 (off) or a threshold in (0, 1]".into());
                    }
                    if self.mix_nbr_prior < 0.0 || self.mix_nbr_pseudo <= 0.0 {
                        return Err("mix_nbr_prior must be >= 0 and mix_nbr_pseudo > 0".into());
                    }
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

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn robust_defaults_are_the_recommended_set_and_leave_other_protocols_alone() {
        let p = Params { protocol: "robust".into(), ..Default::default() };
        p.validate().unwrap();
        // M3 candidate c2: 50 x 50 per stage, refinement 10 steps from T 500, sampling at T 1000 (20 x 20)
        assert_eq!((p.robust_temp_steps_for(3), p.robust_dyn_steps_for(3)), (50, 50));
        assert_eq!((p.robust_refine_temp_steps, p.robust_refine_temp_start), (10, 500.0));
        assert_eq!((p.robust_sample_temp, p.robust_sample_steps, p.robust_sample_dyn_steps), (1000.0, 20, 20));
        assert_eq!(p.robust_merge_below, 25000.0);
        // the shared schedule fields keep the NucDynamics defaults
        let q = Params::default();
        assert_eq!((q.temp_steps_for(0), q.dyn_steps_for(0)), (500, 100));
        // an empty robust schedule falls back to temp_steps / dynamics_steps
        let r = Params { robust_temp_steps: vec![], robust_dynamics_steps: vec![], ..p.clone() };
        assert_eq!((r.robust_temp_steps_for(0), r.robust_dyn_steps_for(0)), (500, 100));
        let bad = Params { robust_temp_steps: vec![1, 2], ..p };
        assert!(bad.validate().is_err());
    }
}
