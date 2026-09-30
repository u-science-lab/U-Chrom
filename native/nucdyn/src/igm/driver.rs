//! A/M driver of IGM (`bin/igm-run:run_pipeline`, spec §4.3) and the
//! random initial population (`RandomInit` + `RelaxInit`, spec §6.2).

use crate::igm::astep::{self, AStepOpts, Candidates, PairResult};
use crate::igm::forces::{violations, ForceField, HicBonds, Violations, V3};
use crate::igm::genome::Genome;
use crate::igm::md::{self, CgStats, State};
use crate::igm::params::IgmParams;
use crate::rng::{Rng, STREAM_COORDS};
use rayon::prelude::*;
use serde::Serialize;
use std::time::Instant;

/// Per-structure result of one M-step.
#[derive(Clone, Copy, Debug, Default, Serialize)]
pub struct StructStats {
    pub viol: Violations,
    pub n_hic: u64,
    pub energy: f64,
    pub cg_iterations: u32,
    pub cg_evaluations: u32,
}

/// Something that holds a population and runs A- and M-steps on it.
pub trait PopEngine {
    fn name(&self) -> String;
    fn set_population(&mut self, pop: &[Vec<V3>]) -> Result<(), String>;
    fn population(&mut self) -> Result<Vec<Vec<V3>>, String>;
    /// A-step statistics of the selected candidates.
    fn actdist(&mut self, g: &Genome, cand: &Candidates, sel: &[u32]) -> Result<Vec<PairResult>, String>;
    /// Assignment + M-step of every structure.  `round` keys the random streams.
    fn mstep(&mut self, rows: &[(u32, u32, f64)], round: u64) -> Result<Vec<StructStats>, String>;
}

/// Multi-core CPU engine (f64 reference); structures run in parallel.
pub struct CpuPopEngine {
    pub ff: ForceField,
    pub p: IgmParams,
    pub pop: Vec<Vec<V3>>,
    pool: rayon::ThreadPool,
}

impl CpuPopEngine {
    pub fn new(ff: ForceField, p: &IgmParams) -> Result<CpuPopEngine, String> {
        let n = if p.n_threads == 0 { std::thread::available_parallelism().map(|x| x.get()).unwrap_or(1) } else { p.n_threads };
        let pool = rayon::ThreadPoolBuilder::new().num_threads(n).build().map_err(|e| e.to_string())?;
        Ok(CpuPopEngine { ff, p: p.clone(), pop: vec![], pool })
    }
}

impl PopEngine for CpuPopEngine {
    fn name(&self) -> String {
        format!("cpu[{} threads]", self.pool.current_num_threads())
    }
    fn set_population(&mut self, pop: &[Vec<V3>]) -> Result<(), String> {
        self.pop = pop.to_vec();
        Ok(())
    }
    fn population(&mut self) -> Result<Vec<Vec<V3>>, String> {
        Ok(self.pop.clone())
    }
    fn actdist(&mut self, g: &Genome, cand: &Candidates, sel: &[u32]) -> Result<Vec<PairResult>, String> {
        let pop = &self.pop;
        let cr = self.p.contact_range;
        let opts = AStepOpts::from_params(&self.p);
        Ok(self.pool.install(|| astep::actdist_opt(g, cand, sel, pop, cr, opts)))
    }
    fn mstep(&mut self, rows: &[(u32, u32, f64)], round: u64) -> Result<Vec<StructStats>, String> {
        let (ff, p) = (&self.ff, &self.p);
        let n = ff.n;
        let out: Vec<(Vec<V3>, StructStats)> = self.pool.install(|| {
            self.pop
                .par_iter()
                .enumerate()
                .map(|(s, pos)| {
                    let hic = HicBonds::from_pairs(n, &astep::assign(rows, pos));
                    let mut st = State::new(pos.clone());
                    let (cs, e): (CgStats, _) = md::mstep(ff, &hic, &mut st, p, [p.seed, round, s as u64]);
                    let v = violations(ff, &hic, &st.pos, p.violation_tolerance);
                    let ss = StructStats { viol: v, n_hic: hic.n_bonds() as u64, energy: e.total(), cg_iterations: cs.iterations as u32, cg_evaluations: cs.evaluations as u32 };
                    (st.pos, ss)
                })
                .collect()
        });
        let mut stats = Vec::with_capacity(out.len());
        for (s, (pos, ss)) in out.into_iter().enumerate() {
            self.pop[s] = pos;
            stats.push(ss);
        }
        Ok(stats)
    }
}

/// Random territories (IGM `RandomInit`): every chain gets a centre uniform
/// in a ball of radius `R − r̄`, its beads uniform in a ball of radius `r̄`
/// around it, `r̄` = mean over chains of `0.75 R (n_c / n)^{1/3}`.
pub fn random_structure(g: &Genome, init_radius: f64, rng: &mut Rng) -> Vec<V3> {
    let n = g.n_beads() as f64;
    let rbar: f64 = g.chains.iter().map(|c| 0.75 * init_radius * (((c.3 - c.2) as f64) / n).cbrt()).sum::<f64>() / g.chains.len() as f64;
    let ball = |r: f64, rng: &mut Rng| loop {
        let v = [2.0 * rng.uniform() - 1.0, 2.0 * rng.uniform() - 1.0, 2.0 * rng.uniform() - 1.0];
        if v[0] * v[0] + v[1] * v[1] + v[2] * v[2] <= 1.0 {
            return [v[0] * r, v[1] * r, v[2] * r];
        }
    };
    let mut pos = vec![[0.0; 3]; g.n_beads()];
    for c in &g.chains {
        let ctr = ball((init_radius - rbar).max(0.0), rng);
        for b in c.2..c.3 {
            let q = ball(rbar, rng);
            pos[b as usize] = [ctr[0] + q[0], ctr[1] + q[1], ctr[2] + q[2]];
        }
    }
    pos
}

/// Initial positions of selected loci (IGM-Plus expanded initialisation):
/// one entry per (structure, haploid bin, copy) with its target xyz (nm).
#[derive(Clone, Debug, Default)]
pub struct InitPins {
    pub structure: Vec<u32>,
    pub hap: Vec<u32>,
    pub copy: Vec<u32>,
    pub xyz: Vec<V3>,
}

impl InitPins {
    pub fn is_empty(&self) -> bool {
        self.structure.is_empty()
    }

    /// Per structure: (bead, xyz) sorted by bead.
    pub fn resolve(&self, g: &Genome, n_structures: usize) -> Result<Vec<Vec<(u32, V3)>>, String> {
        let m = self.structure.len();
        if self.hap.len() != m || self.copy.len() != m || self.xyz.len() != m {
            return Err("init pin arrays differ in length".into());
        }
        let mut out = vec![vec![]; n_structures];
        for k in 0..m {
            let (s, h, c) = (self.structure[k] as usize, self.hap[k] as usize, self.copy[k] as usize);
            if s >= n_structures {
                return Err(format!("init pin {k}: structure {s} >= n_structures {n_structures}"));
            }
            if h >= g.n_hap() {
                return Err(format!("init pin {k}: bin {h} out of range"));
            }
            let Some(&b) = g.copy_index[h].get(c) else {
                return Err(format!("init pin {k}: bin {h} has no copy {c}"));
            };
            if !self.xyz[k].iter().all(|x| x.is_finite()) {
                return Err(format!("init pin {k}: non-finite position"));
            }
            out[s].push((b, self.xyz[k]));
        }
        for (s, v) in out.iter_mut().enumerate() {
            v.sort_by_key(|x| x.0);
            if v.windows(2).any(|w| w[0].0 == w[1].0) {
                return Err(format!("structure {s}: a bead is pinned twice"));
            }
        }
        Ok(out)
    }
}

/// Place the pinned beads of one structure and interpolate linearly the beads
/// between two consecutive pinned beads of the same chain (the others keep
/// their territory positions).
pub fn apply_pins(g: &Genome, pos: &mut [V3], pins: &[(u32, V3)]) {
    for &(b, x) in pins {
        pos[b as usize] = x;
    }
    for w in pins.windows(2) {
        let ((a, pa), (b, pb)) = (w[0], w[1]);
        if b <= a + 1 || g.bead_chain[a as usize] != g.bead_chain[b as usize] {
            continue;
        }
        let n = (b - a) as f64;
        for k in a + 1..b {
            let t = (k - a) as f64 / n;
            pos[k as usize] = [pa[0] + t * (pb[0] - pa[0]), pa[1] + t * (pb[1] - pa[1]), pa[2] + t * (pb[2] - pa[2])];
        }
    }
}

const STREAM_INIT_NOISE: u64 = 0x494e_4f49;

/// The initial population: random territories, then (opt-in) pinned loci with
/// interpolation and Gaussian noise of `init_noise` nm.
pub fn initial_population(g: &Genome, p: &IgmParams, pins: &[Vec<(u32, V3)>]) -> Vec<Vec<V3>> {
    let mut pop = random_population(g, p, 0);
    if pins.iter().any(|v| !v.is_empty()) || p.init_noise > 0.0 {
        pop.par_iter_mut().enumerate().for_each(|(s, pos)| {
            if let Some(v) = pins.get(s) {
                apply_pins(g, pos, v);
            }
            if p.init_noise > 0.0 {
                let mut rng = Rng::from_keys(&[p.seed, s as u64, 0, STREAM_INIT_NOISE]);
                for q in pos.iter_mut() {
                    for x in q.iter_mut() {
                        *x += p.init_noise * rng.normal();
                    }
                }
            }
        });
    }
    pop
}

pub fn random_population(g: &Genome, p: &IgmParams, salt: u64) -> Vec<Vec<V3>> {
    (0..p.n_structures)
        .into_par_iter()
        .map(|s| {
            let mut rng = Rng::from_keys(&[p.seed, s as u64, salt, STREAM_COORDS]);
            random_structure(g, p.init_radius(), &mut rng)
        })
        .collect()
}

/// Population statistics of one restraint kind and the structure that
/// violates it most (IGM-Plus `log_stats`: largest violated / imposed ratio).
#[derive(Clone, Debug, Serialize)]
pub struct RestraintStat {
    pub kind: String,
    pub imposed: u64,
    pub violated: u64,
    /// structure with the largest violated / imposed ratio (-1: no violation)
    pub worst_structure: i64,
    pub worst_violated: u64,
    pub worst_imposed: u64,
    pub worst_ratio: f64,
    /// structures sharing that ratio
    pub n_worst: u64,
}

/// Kinds reported: Hi-C intra, Hi-C inter, polymer, envelope.
pub const RESTRAINT_KINDS: [&str; 4] = ["hic_intra", "hic_inter", "polymer", "envelope"];

fn kind_counts(v: &Violations) -> [(u64, u64); 4] {
    [
        (v.hic_imposed - v.hic_inter_imposed, v.hic_violated - v.hic_inter_violated),
        (v.hic_inter_imposed, v.hic_inter_violated),
        (v.poly_imposed, v.poly_violated),
        (v.env_imposed, v.env_violated),
    ]
}

/// Per-kind totals and worst structure (cheap: one pass over the stats).
pub fn breakdown(stats: &[StructStats]) -> Vec<RestraintStat> {
    (0..RESTRAINT_KINDS.len())
        .map(|k| {
            let mut r = RestraintStat {
                kind: RESTRAINT_KINDS[k].into(),
                imposed: 0,
                violated: 0,
                worst_structure: -1,
                worst_violated: 0,
                worst_imposed: 0,
                worst_ratio: 0.0,
                n_worst: 0,
            };
            for (s, st) in stats.iter().enumerate() {
                let (imp, vio) = kind_counts(&st.viol)[k];
                r.imposed += imp;
                r.violated += vio;
                if vio == 0 {
                    continue;
                }
                let ratio = vio as f64 / imp as f64;
                if r.worst_structure < 0 || ratio > r.worst_ratio {
                    r.worst_structure = s as i64;
                    r.worst_ratio = ratio;
                    r.worst_violated = vio;
                    r.worst_imposed = imp;
                    r.n_worst = 1;
                } else if ratio == r.worst_ratio {
                    r.n_worst += 1;
                }
            }
            r
        })
        .collect()
}

fn print_breakdown(b: &[RestraintStat]) {
    for r in b {
        if r.imposed == 0 {
            continue;
        }
        if r.worst_structure >= 0 {
            eprintln!(
                "[igm]   {:<9} {} violated of {}; most violated in structure {} ({}/{} = {:.4}{})",
                r.kind,
                r.violated,
                r.imposed,
                r.worst_structure,
                r.worst_violated,
                r.worst_imposed,
                r.worst_ratio,
                if r.n_worst > 1 { format!(", {} structures tie", r.n_worst) } else { String::new() }
            );
        } else {
            eprintln!("[igm]   {:<9} 0 violated of {}", r.kind, r.imposed);
        }
    }
}

#[derive(Clone, Debug, Serialize)]
pub struct RoundLog {
    pub round: u64,
    pub sigma_index: usize,
    pub intra_sigma: f64,
    pub inter_sigma: f64,
    pub iteration: usize,
    pub n_candidates: usize,
    pub n_pairs_restrained: usize,
    pub n_rows: usize,
    pub n_hic_bonds: u64,
    pub violations: Violations,
    pub violation_score: f64,
    pub forced: bool,
    pub accepted: bool,
    pub seconds_astep: f64,
    pub seconds_mstep: f64,
    /// violations per restraint kind (Hi-C intra / inter, polymer, envelope)
    /// with the most violating structure of each
    pub breakdown: Vec<RestraintStat>,
}

pub struct RunOutput {
    pub rounds: Vec<RoundLog>,
    /// log of the initial relaxation (round 0; None with `skip_relax_init`)
    pub relax_log: Option<RoundLog>,
    pub final_stats: Vec<StructStats>,
    /// last A-step: candidate indices and results
    pub last_sel: Vec<u32>,
    pub last_res: Vec<PairResult>,
    pub stopped_at_max_iterations: bool,
    pub seconds_total: f64,
    pub engine: String,
}

/// Iteration forced (IGM `run_pipeline`): run at least `min_iterations − 1`
/// iterations once the first one is not acceptable; also force once after
/// iteration 0 at the last σ (`force_last_iteration`) or at
/// `intra σ ≤ force_minimum_iterations_hic_cutoff`.
pub fn is_forced(p: &IgmParams, it: usize, last_sigma: bool, intra_sigma: f64) -> bool {
    (it > 0 && it + 1 < p.min_iterations)
        || (it == 0 && ((last_sigma && p.force_last_iteration) || intra_sigma <= p.force_minimum_iterations_hic_cutoff))
}

pub fn score(stats: &[StructStats]) -> (Violations, f64) {
    let mut v = Violations::default();
    for s in stats {
        v.add(&s.viol);
    }
    let sc = if v.imposed() > 0 { v.violated() as f64 / v.imposed() as f64 } else { 0.0 };
    (v, sc)
}

/// The full IGM run.  `on_round(log, engine)` is called after every M-step
/// (and after the initial relaxation with `round == 0`); returning an error aborts.
pub fn run_igm(
    g: &Genome,
    cand: &mut Candidates,
    p: &IgmParams,
    engine: &mut dyn PopEngine,
    on_round: &mut dyn FnMut(&RoundLog, &mut dyn PopEngine) -> Result<(), String>,
) -> Result<RunOutput, String> {
    run_igm_with(g, cand, p, &[], engine, on_round)
}

/// As [`run_igm`] with pinned initial loci (`pins[s]`: (bead, xyz) of structure s).
pub fn run_igm_with(
    g: &Genome,
    cand: &mut Candidates,
    p: &IgmParams,
    pins: &[Vec<(u32, V3)>],
    engine: &mut dyn PopEngine,
    on_round: &mut dyn FnMut(&RoundLog, &mut dyn PopEngine) -> Result<(), String>,
) -> Result<RunOutput, String> {
    let t0 = Instant::now();
    let pop = initial_population(g, p, pins);
    engine.set_population(&pop)?;
    drop(pop);
    let mut final_stats = vec![];
    let mut relax_log = None;
    if !p.skip_relax_init {
        let tm = Instant::now();
        let stats = engine.mstep(&[], 0)?;
        let (v, sc) = score(&stats);
        let log = RoundLog {
            round: 0,
            sigma_index: 0,
            intra_sigma: f64::NAN,
            inter_sigma: f64::NAN,
            iteration: 0,
            n_candidates: 0,
            n_pairs_restrained: 0,
            n_rows: 0,
            n_hic_bonds: 0,
            violations: v,
            violation_score: sc,
            forced: false,
            accepted: true,
            seconds_astep: 0.0,
            seconds_mstep: tm.elapsed().as_secs_f64(),
            breakdown: breakdown(&stats),
        };
        if p.verbose {
            eprintln!("[igm] relax init: score {sc:.4}, {} violated of {} ({:.1} s)", v.violated(), v.imposed(), log.seconds_mstep);
            print_breakdown(&log.breakdown);
        }
        on_round(&log, engine)?;
        relax_log = Some(log);
        final_stats = stats;
    }
    let mut rounds = vec![];
    let mut round = 1u64;
    let mut last_sel = vec![];
    let mut last_res = vec![];
    let mut stopped = false;
    let ns = p.intra_sigma_list.len();
    'outer: for si in 0..ns {
        let (intra, inter) = (p.intra_sigma_list[si], p.inter_sigma_list[si]);
        let mut it = 0usize;
        loop {
            if p.random_shuffling {
                engine.set_population(&random_population(g, p, round))?;
            }
            let ta = Instant::now();
            let sel = cand.select(intra, inter);
            let res = engine.actdist(g, cand, &sel)?;
            for v in cand.p_last.iter_mut() {
                *v = 0.0;
            }
            for (&k, r) in sel.iter().zip(&res) {
                cand.p_last[k as usize] = r.p;
            }
            let rows = astep::rows(g, cand, &sel, &res);
            let seconds_astep = ta.elapsed().as_secs_f64();
            let tm = Instant::now();
            let stats = engine.mstep(&rows, round)?;
            let seconds_mstep = tm.elapsed().as_secs_f64();
            let (v, sc) = score(&stats);
            let forced = is_forced(p, it, si + 1 == ns, intra);
            let accepted = sc < p.max_violations && !forced;
            let log = RoundLog {
                round,
                sigma_index: si,
                intra_sigma: intra,
                inter_sigma: inter,
                iteration: it,
                n_candidates: sel.len(),
                n_pairs_restrained: res.iter().filter(|r| r.p > 0.0).count(),
                n_rows: rows.len(),
                n_hic_bonds: stats.iter().map(|s| s.n_hic).sum(),
                violations: v,
                violation_score: sc,
                forced,
                accepted,
                seconds_astep,
                seconds_mstep,
                breakdown: breakdown(&stats),
            };
            if p.verbose {
                eprintln!(
                    "[igm] round {round} sigma ({intra}, {inter}) iter {it}: {} pairs, {} restrained, {:.1} Hi-C bonds / structure, score {sc:.4}{} (A {seconds_astep:.1} s, M {seconds_mstep:.1} s)",
                    log.n_candidates,
                    log.n_pairs_restrained,
                    log.n_hic_bonds as f64 / stats.len().max(1) as f64,
                    if accepted { " accepted" } else if forced { " forced" } else { "" }
                );
                print_breakdown(&log.breakdown);
            }
            on_round(&log, engine)?;
            rounds.push(log);
            final_stats = stats;
            last_sel = sel;
            last_res = res;
            round += 1;
            if accepted {
                break;
            }
            it += 1;
            if it >= p.max_iterations {
                if p.verbose {
                    eprintln!("[igm] Maximum number of iterations reached");
                }
                stopped = true;
                break 'outer;
            }
        }
    }
    Ok(RunOutput {
        rounds,
        relax_log,
        final_stats,
        last_sel,
        last_res,
        stopped_at_max_iterations: stopped,
        seconds_total: t0.elapsed().as_secs_f64(),
        engine: engine.name(),
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn forced_rule() {
        let p = IgmParams { min_iterations: 5, ..Default::default() };
        let f: Vec<bool> = (0..6).map(|it| is_forced(&p, it, false, 0.1)).collect();
        assert_eq!(f, vec![false, true, true, true, false, false]);
        let p = IgmParams { force_last_iteration: true, ..p };
        assert!(is_forced(&p, 0, true, 0.1));
        assert!(!is_forced(&p, 0, false, 0.1));
    }

    #[test]
    fn random_structures_inside_init_ball() {
        let p = IgmParams { n_structures: 3, ..Default::default() };
        let g = Genome::new(&[0, 0, 0, 1, 1], &[0, 1, 2, 0, 1], &[1, 2, 3, 1, 2], &[2, 2], &p).unwrap();
        let pop = random_population(&g, &p, 0);
        assert_eq!(pop.len(), 3);
        for s in &pop {
            assert!(s.iter().all(|q| (q[0] * q[0] + q[1] * q[1] + q[2] * q[2]).sqrt() <= p.init_radius() + 1e-9));
        }
        assert_ne!(pop[0], pop[1]);
    }
}

/// Everything a caller needs from a finished run.
pub struct Population {
    pub genome: Genome,
    pub coords: Vec<Vec<V3>>,
    pub cand: Candidates,
    pub out: RunOutput,
}

/// Set up genome, candidates, force field and engine from arrays, and run.
#[allow(clippy::too_many_arguments)]
pub fn run_population(
    hap_chrom: &[u32],
    hap_start: &[i64],
    hap_end: &[i64],
    copies: &[u32],
    prob_i: &[u32],
    prob_j: &[u32],
    prob_v: &[f64],
    p: &IgmParams,
    on_round: &mut dyn FnMut(&RoundLog, &mut dyn PopEngine) -> Result<(), String>,
) -> Result<Population, String> {
    run_population_with(hap_chrom, hap_start, hap_end, copies, prob_i, prob_j, prob_v, &InitPins::default(), p, on_round)
}

/// As [`run_population`] with pinned initial loci (IGM-Plus expanded initialisation).
#[allow(clippy::too_many_arguments)]
pub fn run_population_with(
    hap_chrom: &[u32],
    hap_start: &[i64],
    hap_end: &[i64],
    copies: &[u32],
    prob_i: &[u32],
    prob_j: &[u32],
    prob_v: &[f64],
    init: &InitPins,
    p: &IgmParams,
    on_round: &mut dyn FnMut(&RoundLog, &mut dyn PopEngine) -> Result<(), String>,
) -> Result<Population, String> {
    p.validate()?;
    let g = Genome::new(hap_chrom, hap_start, hap_end, copies, p)?;
    if p.gp_pooling() && copies.iter().copied().max().unwrap_or(0) > 4 {
        return Err("assignment_pooling=\"gp\" supports at most 4 copies per chromosome".into());
    }
    let pins = if init.is_empty() { vec![] } else { init.resolve(&g, p.n_structures)? };
    let nh = g.n_hap();
    if prob_i.len() != prob_j.len() || prob_i.len() != prob_v.len() {
        return Err("probability arrays differ in length".into());
    }
    if prob_i.iter().chain(prob_j).any(|&x| x as usize >= nh) {
        return Err("probability index out of range".into());
    }
    let min_sigma = p.intra_sigma_list.iter().chain(&p.inter_sigma_list).cloned().fold(f64::INFINITY, f64::min);
    let mut cand = Candidates::from_coo(&g, prob_i, prob_j, prob_v, min_sigma);
    // nearest-neighbour probabilities for the "hic" polymer style
    let mut nn = vec![1.0; nh];
    for ((&i, &j), &v) in prob_i.iter().zip(prob_j).zip(prob_v) {
        let (a, b) = (i.min(j) as usize, i.max(j) as usize);
        if b == a + 1 {
            nn[a] = v;
        }
    }
    let poly = g.polymer_bonds(p, &|h| nn[h]);
    let mut ff = ForceField::new(g.radii.clone(), &poly, p.semiaxes(), p);
    ff.bead_chrom = g.bead_hap.iter().map(|&h| g.hap_chrom[h as usize]).collect();
    let mut engine: Box<dyn PopEngine> = match p.device.as_str() {
        "cpu" => Box::new(CpuPopEngine::new(ff, p)?),
        "gpu" => {
            #[cfg(feature = "gpu")]
            {
                Box::new(crate::igm::gpu::GpuPopEngine::new(&ff, p)?)
            }
            #[cfg(not(feature = "gpu"))]
            {
                return Err("uchrom_nucdyn was built without the `gpu` feature".into());
            }
        }
        d => return Err(format!("unknown device {d:?}")),
    };
    let out = run_igm_with(&g, &mut cand, p, &pins, engine.as_mut(), on_round)?;
    let coords = engine.population()?;
    Ok(Population { genome: g, coords, cand, out })
}

#[cfg(test)]
mod e2e {
    use super::*;

    /// Tiny end-to-end run on the CPU: the population reproduces the input
    /// probabilities of the restrained pairs.
    #[test]
    fn tiny_population_reproduces_contacts() {
        let n = 20usize;
        let chrom: Vec<u32> = (0..2 * n).map(|i| (i / n) as u32).collect();
        let start: Vec<i64> = (0..2 * n).map(|i| ((i % n) * 1_000_000) as i64).collect();
        let end: Vec<i64> = start.iter().map(|&x| x + 1_000_000).collect();
        // neighbours 1, one long-range intra pair per chromosome at 0.6, one inter pair at 0.3
        let (mut pi, mut pj, mut pv) = (vec![], vec![], vec![]);
        for c in 0..2u32 {
            for k in 0..n as u32 - 1 {
                pi.push(c * n as u32 + k);
                pj.push(c * n as u32 + k + 1);
                pv.push(1.0);
            }
            pi.push(c * n as u32 + 2);
            pj.push(c * n as u32 + 15);
            pv.push(0.6);
        }
        pi.push(5);
        pj.push(n as u32 + 5);
        pv.push(0.3);
        let stages: Vec<crate::igm::params::Stage> = crate::igm::params::demo_stages()
            .into_iter()
            .map(|mut s| {
                s.mdsteps /= 20;
                s
            })
            .collect();
        let p = IgmParams {
            n_structures: 40,
            nucleus_radius: 1200.0,
            occupancy: 0.2,
            stages,
            relax: None,
            intra_sigma_list: vec![1.0, 0.2],
            inter_sigma_list: vec![1.0, 0.2],
            max_iterations: 3,
            ..Default::default()
        };
        let pop = run_population(&chrom, &start, &end, &[2, 2], &pi, &pj, &pv, &p, &mut |_, _| Ok(())).unwrap();
        let g = &pop.genome;
        let freq = |i: usize, j: usize, intra: bool| {
            let cb = crate::igm::astep::combos(g, i as u32, j as u32, intra);
            let rc = 2.0 * (g.radii[cb[0][0] as usize] + g.radii[cb[0][1] as usize]);
            let mut c = 0;
            for st in &pop.coords {
                for b in &cb {
                    let (x, y) = (st[b[0] as usize], st[b[1] as usize]);
                    if ((x[0] - y[0]).powi(2) + (x[1] - y[1]).powi(2) + (x[2] - y[2]).powi(2)).sqrt() <= rc {
                        c += 1;
                    }
                }
            }
            c as f64 / (cb.len() * pop.coords.len()) as f64
        };
        let f_nn = freq(3, 4, true);
        let f_long = freq(2, 15, true);
        let f_inter = freq(5, n + 5, false);
        let f_none = freq(2, 10, true);
        eprintln!(
            "contact frequencies: neighbours {f_nn:.2} (1), 2-15 {f_long:.2} (0.6), inter {f_inter:.2} (0.3), 2-10 {f_none:.2} (unrestrained); rounds {}",
            pop.out.rounds.len()
        );
        assert!(f_nn > 0.95);
        assert!((f_long - 0.6).abs() < 0.2, "{f_long}");
        assert!((f_inter - 0.3).abs() < 0.2, "{f_inter}");
    }
}
