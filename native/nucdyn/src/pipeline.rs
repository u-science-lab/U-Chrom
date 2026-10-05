//! The hierarchical structure calculation (`calc_genome_structure` and
//! `anneal_genome` of the original NucDynamics).

use crate::align::{align_coord_models, remove_models};
use crate::contacts::{
    build_contact_dict, calc_bins, calc_limits, contact_count, initial_clean_contacts, remove_violated_contacts,
    resolve_3d_ambiguous, ContactDict, Structure,
};
use crate::dynamics::{run_dynamics, DynParams, Model, System, V3};
use crate::params::{anneal_schedule, bead_size, violated_threshold, Params};
use crate::restraints::build_restraints;
use crate::rng::{Rng, STREAM_COORDS, STREAM_VELOC};
use rayon::prelude::*;
use serde::Serialize;
use std::time::Instant;

/// Flat contact input.  Chromosome ids index `names`, which must be sorted.
pub struct Input<'a> {
    pub names: &'a [String],
    pub chr_a: &'a [u32],
    pub pos_a: &'a [i64],
    pub chr_b: &'a [u32],
    pub pos_b: &'a [i64],
    pub ambig: &'a [i64],
    pub active: &'a [bool],
    /// protocol `robust`: per-contact likelihood ratio true / false from other
    /// evidence (multiplies the posterior odds; 1 = none, 0 = certainly false).
    pub prior_lr: Option<&'a [f64]>,
    /// Diploid (homolog-resolved) input: haplotype of each contact end and copies per
    /// chromosome (`diploid.rs`).  None: haploid (one particle chain per chromosome).
    pub dip: Option<crate::diploid::DiploidInput<'a>>,
}

#[derive(Clone, Debug, Serialize)]
pub struct StageLog {
    pub stage: usize,
    pub particle_size: f64,
    pub bead_size: f64,
    pub n_models: usize,
    pub n_particles: usize,
    pub n_contacts: usize,
    pub n_restraints: usize,
    pub dist_force_const: f64,
    pub temp_steps: usize,
    pub dynamics_steps: usize,
    pub seconds_prepare: f64,
    pub seconds_dynamics: f64,
    pub removed_models: Vec<usize>,
    pub device: String,
    /// emulated repulsion-list overflows / MD steps without repulsion (sum over models;
    /// only with `emulate_rep_list_overflow`)
    pub rep_list_overflows: u64,
    pub steps_without_repulsion: u64,
    /// protocol `robust`: the EM updates of this stage
    #[serde(skip_serializing_if = "Vec::is_empty")]
    pub robust: Vec<crate::robust::EmLog>,
}

pub struct Output {
    pub chroms: Vec<u32>,
    pub seq_pos: Vec<Vec<i64>>,
    /// models x particles, in particle radii (coords / bead size), superposed.
    pub coords: Vec<Vec<V3>>,
    pub model_rmsds: Vec<f64>,
    pub particle_size: f64,
    pub stages: Vec<StageLog>,
    pub seconds_total: f64,
    /// protocol `robust`: final restraint weight of every input contact (NaN = filtered out); empty otherwise
    pub contact_weights: Vec<f64>,
    /// Diploid input: `chroms` are copy ids (2 x chromosome + haplotype, `diploid::copy_id`).
    pub diploid: bool,
    /// Diploid input: per input contact 4 values, the probability of each (hap_a, hap_b)
    /// (index 2 hap_a + hap_b, input orientation) given that the contact is true (NaN =
    /// filtered out); empty otherwise.
    pub phase_probs: Vec<f64>,
    /// Few-cell deconvolution (`mix.rs`): number of cells (0 = off); `coords` are cell-major
    /// (cell s = models s n .. (s + 1) n of n per cell).
    pub mix_cells: usize,
    /// Few-cell deconvolution: per input contact `mix_cells` values, P(cell | true) from the
    /// final structures (every input contact, filtered ones included); empty otherwise.
    pub cell_probs: Vec<f64>,
}

/// Something that anneals the models of one stage.
pub trait StageEngine {
    #[allow(clippy::too_many_arguments)]
    fn anneal(
        &mut self,
        sys: &System,
        start: Vec<Vec<V3>>,
        schedule: &[(f64, f64)],
        dyn_steps: usize,
        f_dist: f64,
        bead: f64,
        stage: usize,
        params: &Params,
    ) -> Result<Vec<Vec<V3>>, String>;
    fn name(&self) -> String;
    /// (list overflows, steps without repulsion) of the last `anneal` call
    fn overflow_stats(&self) -> (u64, u64) {
        (0, 0)
    }
}

/// Multi-core CPU engine (f64).  Models run in parallel; when there are
/// fewer models than threads, the force loops of each model are split too.
pub struct CpuEngine {
    pool: rayon::ThreadPool,
    n_threads: usize,
    last_overflow: (u64, u64),
}

impl CpuEngine {
    pub fn new(n_threads: usize) -> Result<CpuEngine, String> {
        let n = if n_threads == 0 { std::thread::available_parallelism().map(|x| x.get()).unwrap_or(1) } else { n_threads };
        let pool = rayon::ThreadPoolBuilder::new().num_threads(n).build().map_err(|e| e.to_string())?;
        Ok(CpuEngine { pool, n_threads: n, last_overflow: (0, 0) })
    }
    pub fn install<R: Send>(&self, f: impl FnOnce() -> R + Send) -> R {
        self.pool.install(f)
    }
}

impl StageEngine for CpuEngine {
    fn anneal(
        &mut self,
        sys: &System,
        start: Vec<Vec<V3>>,
        schedule: &[(f64, f64)],
        dyn_steps: usize,
        f_dist: f64,
        bead: f64,
        stage: usize,
        p: &Params,
    ) -> Result<Vec<Vec<V3>>, String> {
        let inner = start.len() < self.n_threads && sys.n >= 2048;
        let master = p.is_2017_family();
        // 2017: list radius repDist + r_i + r_j; release_1.3: 2 (r_i + r_j)
        let skin = if master { p.rep_dist } else { p.nl_skin * bead };
        let emulate = master && p.emulate_rep_list_overflow;
        let seed = p.seed;
        let out = self.pool.install(|| {
            start
                .into_par_iter()
                .enumerate()
                .map(|(mi, pos)| {
                    let sysm = sys.for_model(mi);
                    let mut m = Model::new(pos, Rng::from_keys(&[seed, stage as u64, mi as u64, STREAM_VELOC]));
                    m.grid.stencil = p.cpu_stencil.clamp(1, 4);
                    for &(t_ref, f_rep) in schedule {
                        let dp = DynParams {
                            t_ref,
                            t_step: p.time_step,
                            n_steps: dyn_steps,
                            f_rep,
                            f_dist,
                            beta: p.beta,
                            tot0: p.tot0,
                            skin,
                            original_nl_schedule: emulate,
                            use_cells: p.use_cells && !emulate,
                            emulate_overflow: emulate,
                        };
                        run_dynamics(&sysm, &mut m, &dp, inner, None);
                    }
                    (m.pos, m.overflow_events, m.steps_without_repulsion)
                })
                .collect::<Vec<_>>()
        });
        self.last_overflow = (out.iter().map(|x| x.1).sum(), out.iter().map(|x| x.2).sum());
        Ok(out.into_iter().map(|x| x.0).collect())
    }
    fn overflow_stats(&self) -> (u64, u64) {
        self.last_overflow
    }
    fn name(&self) -> String {
        format!("cpu[{}]", self.n_threads)
    }
}

/// `get_random_coords`: uniform in a sphere of the given radius.
fn random_coords(n: usize, radius: f64, rng: &mut Rng) -> Vec<V3> {
    (0..n)
        .map(|_| {
            let u = rng.uniform();
            let x = [rng.normal(), rng.normal(), rng.normal()];
            let norm = (x[0] * x[0] + x[1] * x[1] + x[2] * x[2]).sqrt();
            let s = radius * u.powf(1.0 / 3.0) / norm;
            [x[0] * s, x[1] * s, x[2] * s]
        })
        .collect()
}

/// Mass / radius / restraint system and starting coordinates of one stage.
pub struct StageSetup {
    pub st: Structure,
    pub sys: System,
    pub f_dist: f64,
    pub n_contacts: usize,
}

/// `anneal_genome` without the annealing: bins, restraints, start coords.
pub fn setup_stage(
    d: &ContactDict,
    num_models: usize,
    particle_size: f64,
    prev: Option<&Structure>,
    p: &Params,
    stage: usize,
) -> Result<StageSetup, String> {
    let bead = bead_size(particle_size);
    let ps = particle_size as i32 as i64;
    let seq_pos = calc_bins(&calc_limits(d), ps);
    if seq_pos.is_empty() {
        return Err(format!("stage {stage}: no contacts left"));
    }
    let mut st = Structure::new(&seq_pos);
    let n = st.n_particles();
    let mut coords: Vec<Vec<V3>> = vec![Vec::with_capacity(n); num_models];
    for (slot, &chrom) in st.chroms.iter().enumerate() {
        let sp = &st.seq_pos[slot];
        let prev_slot = prev.and_then(|pr| pr.chrom_slot(chrom).map(|s| (pr, s)));
        match prev_slot {
            Some((pr, ps_)) if pr.n_models() == num_models => {
                let same = pr.seq_pos[ps_].len() == sp.len();
                for (m, c) in coords.iter_mut().enumerate() {
                    if same {
                        c.extend_from_slice(pr.chrom_coords(m, ps_));
                    } else {
                        for &x in sp {
                            c.push(pr.interp_coord(m, ps_, x as f64));
                        }
                    }
                }
            }
            _ => {
                for (m, c) in coords.iter_mut().enumerate() {
                    let mut rng = Rng::from_keys(&[p.seed, stage as u64, chrom as u64, m as u64, STREAM_COORDS]);
                    c.extend(random_coords(sp.len(), p.random_radius * bead, &mut rng));
                }
            }
        }
    }
    st.coords = coords;
    let rs = build_restraints(
        d,
        &st,
        ps,
        bead,
        p.contact_dist_lower,
        p.contact_dist_upper,
        p.backbone_dist_lower,
        p.backbone_dist_upper,
    );
    if rs.n_contacts == 0 {
        return Err(format!("stage {stage}: no contact restraints"));
    }
    // "Adjust to keep force/particle approximately constant"
    let f_dist = p.dist_force_scale * (n as f64 / rs.n_contacts as f64);
    let sys = System::new(n, vec![1.0; n], vec![bead; n], &rs);
    Ok(StageSetup { st, sys, f_dist, n_contacts: rs.n_contacts })
}

fn log(p: &Params, msg: &str) {
    if p.verbose {
        eprintln!("[uchrom_nucdyn] {msg}");
    }
}

/// The full hierarchical protocol of the chosen version.
pub fn calc_genome_structure(input: &Input, p: &Params, engine: &mut dyn StageEngine) -> Result<Output, String> {
    p.validate()?;
    check_input(input)?;
    if let Some(dip) = &input.dip {
        if p.protocol == "robust" && p.mix_cells >= 2 {
            return crate::mixdip::calc_diploid_mix(input, dip, p, engine, None);
        }
        return crate::diploid::calc_genome_structure(input, dip, p, engine);
    }
    if p.protocol == "nuc_dynamics_2017" {
        crate::protocol2017::calc_genome_structure(input, p, engine)
    } else if p.protocol == "robust" && p.mix_cells >= 2 {
        crate::mix::calc_genome_structure(input, p, engine)
    } else if p.protocol == "robust" {
        crate::robust::calc_genome_structure(input, p, engine)
    } else {
        calc_genome_structure_release13(input, p, engine)
    }
}

fn check_input(input: &Input) -> Result<(), String> {
    let n = input.chr_a.len();
    for v in [input.pos_a.len(), input.chr_b.len(), input.pos_b.len(), input.ambig.len(), input.active.len()] {
        if v != n {
            return Err("contact arrays differ in length".into());
        }
    }
    let nn = input.names.len() as u32;
    if input.chr_a.iter().chain(input.chr_b).any(|&c| c >= nn) {
        return Err("chromosome id out of range".into());
    }
    if input.names.windows(2).any(|w| w[0] >= w[1]) {
        return Err("chromosome names must be sorted and unique".into());
    }
    if input.pos_a.iter().chain(input.pos_b).any(|&x| x < 0 || x > i32::MAX as i64) {
        return Err("contact positions must be in [0, 2^31)".into());
    }
    Ok(())
}

/// `calc_genome_structure` of `release_1.3`.
pub fn calc_genome_structure_release13(input: &Input, p: &Params, engine: &mut dyn StageEngine) -> Result<Output, String> {
    let t0 = Instant::now();
    let req = p.n_models;
    let mut contact_dict = build_contact_dict(input.chr_a, input.pos_a, input.chr_b, input.pos_b, input.ambig, input.active, false);
    log(p, &format!("total number of contacts = {}", contact_count(&contact_dict)));
    let mut using_inactive = false;
    let mut prev: Option<Structure> = None;
    let mut num_models = req;
    let mut stages = vec![];
    let mut last_ps = p.particle_sizes[0];
    for (stage, &ps) in p.particle_sizes.iter().enumerate() {
        let ts = Instant::now();
        last_ps = ps;
        if ps <= p.struct_ambig_size && !using_inactive {
            contact_dict =
                build_contact_dict(input.chr_a, input.pos_a, input.chr_b, input.pos_b, input.ambig, input.active, true);
            using_inactive = true;
        }
        let bead = bead_size(ps);
        let mut removed = vec![];
        let mut stage_dict: ContactDict;
        match prev.as_mut() {
            None => {
                stage_dict = initial_clean_contacts(
                    &contact_dict,
                    p.isolation_threshold_cis,
                    p.isolation_threshold_trans,
                    p.isolation_pos_error,
                );
                num_models = if p.ensemble_selection && ps > p.remove_models_size { 2 * req } else { req };
            }
            Some(pr) => {
                if ps <= p.remove_models_size && num_models > req {
                    let (kept, idx) = remove_models(&pr.coords, req);
                    removed = (0..num_models).filter(|i| !idx.contains(i)).collect();
                    pr.coords = kept;
                    num_models = req;
                    log(p, &format!("removed models {removed:?}"));
                }
                if ps <= p.struct_ambig_size {
                    stage_dict = resolve_3d_ambiguous(&contact_dict, pr, p.ambig_percentile, p.ambig_min_bead_sep);
                } else {
                    stage_dict = initial_clean_contacts(
                        &contact_dict,
                        p.isolation_threshold_cis,
                        p.isolation_threshold_trans,
                        p.isolation_pos_error,
                    );
                }
            }
        }
        if let (Some(thr), Some(pr)) = (violated_threshold(ps, bead), prev.as_ref()) {
            stage_dict = remove_violated_contacts(&stage_dict, pr, thr);
            log(p, &format!("contacts after removing violated = {}", contact_count(&stage_dict)));
        }
        let setup = setup_stage(&stage_dict, num_models, ps, prev.as_ref(), p, stage)?;
        let schedule = anneal_schedule(p.temp_start, p.temp_end, p.temp_steps_for(stage), bead);
        let t_prep = ts.elapsed().as_secs_f64();
        log(
            p,
            &format!(
                "stage {} ({} kb): {} particles, {} contacts, {} restraints, {} models",
                stage + 1,
                ps / 1e3,
                setup.sys.n,
                setup.n_contacts,
                setup.sys.n_restraints(),
                num_models
            ),
        );
        let td = Instant::now();
        let StageSetup { mut st, sys, f_dist, n_contacts } = setup;
        let start = std::mem::take(&mut st.coords);
        let mut out = engine.anneal(&sys, start, &schedule, p.dyn_steps_for(stage), f_dist, bead, stage, p)?;
        // centre each model
        for c in out.iter_mut() {
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
        st.coords = out;
        let t_dyn = td.elapsed().as_secs_f64();
        log(p, &format!("stage {} done in {:.2} s ({:.2} s dynamics)", stage + 1, t_prep + t_dyn, t_dyn));
        stages.push(StageLog {
            stage,
            particle_size: ps,
            bead_size: bead,
            n_models: num_models,
            n_particles: sys.n,
            n_contacts,
            n_restraints: sys.n_restraints(),
            dist_force_const: f_dist,
            temp_steps: p.temp_steps_for(stage),
            dynamics_steps: p.dyn_steps_for(stage),
            seconds_prepare: t_prep,
            seconds_dynamics: t_dyn,
            removed_models: removed,
            device: engine.name(),
            rep_list_overflows: 0,
            steps_without_repulsion: 0,
            robust: vec![],
        });
        prev = Some(st);
    }
    let st = prev.unwrap();
    let bead = bead_size(last_ps);
    let scaled: Vec<Vec<V3>> =
        st.coords.iter().map(|c| c.iter().map(|q| [q[0] / bead, q[1] / bead, q[2] / bead]).collect()).collect();
    let (coords, model_rmsds) = if scaled.len() > 1 { align_coord_models(&scaled) } else { (scaled, vec![0.0]) };
    Ok(Output {
        chroms: st.chroms,
        seq_pos: st.seq_pos,
        coords,
        model_rmsds,
        particle_size: last_ps,
        stages,
        seconds_total: t0.elapsed().as_secs_f64(),
        contact_weights: vec![],
        diploid: false,
        phase_probs: vec![],
        mix_cells: 0,
        cell_probs: vec![],
    })
}
