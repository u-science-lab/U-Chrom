//! A/M driver of IGM (`bin/igm-run:run_pipeline`, spec §4.3) and the
//! random initial population (`RandomInit` + `RelaxInit`, spec §6.2).

use crate::igm::astep::{self, Candidates, PairResult};
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
        Ok(self.pool.install(|| astep::actdist(g, cand, sel, pop, cr)))
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

pub fn random_population(g: &Genome, p: &IgmParams, salt: u64) -> Vec<Vec<V3>> {
    (0..p.n_structures)
        .into_par_iter()
        .map(|s| {
            let mut rng = Rng::from_keys(&[p.seed, s as u64, salt, STREAM_COORDS]);
            random_structure(g, p.init_radius(), &mut rng)
        })
        .collect()
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
}

pub struct RunOutput {
    pub rounds: Vec<RoundLog>,
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
    let t0 = Instant::now();
    let pop = random_population(g, p, 0);
    engine.set_population(&pop)?;
    drop(pop);
    let mut final_stats = vec![];
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
        };
        if p.verbose {
            eprintln!("[igm] relax init: score {sc:.4} ({:.1} s)", log.seconds_mstep);
        }
        on_round(&log, engine)?;
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
            };
            if p.verbose {
                eprintln!(
                    "[igm] round {round} sigma ({intra}, {inter}) iter {it}: {} pairs, {} restrained, {:.1} Hi-C bonds / structure, score {sc:.4}{} (A {seconds_astep:.1} s, M {seconds_mstep:.1} s)",
                    log.n_candidates,
                    log.n_pairs_restrained,
                    log.n_hic_bonds as f64 / stats.len().max(1) as f64,
                    if accepted { " accepted" } else if forced { " forced" } else { "" }
                );
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
