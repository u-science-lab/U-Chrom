//! Few-cell deconvolution of *diploid* (phased) cells: cells × chromosome copies.
//!
//! The mixture of `mix.rs` (cell = latent variable) combined with the copy-pair latent variable of
//! `diploid.rs`: every cell has one chain per chromosome copy (copy id `2 c + h`, as `diploid.rs`); a
//! contact's candidates are its copy pairs (phased ends fixed, the same-homolog rule for close cis
//! ends, the 2-D neighbourhood phase prior π); restraints are the ambiguous candidate groups of
//! `diploid::dip_groups` (combined distance (Σ d⁻⁴)^(−1/4), the default of EMber diploid), shared by
//! all cells, and the models of cell s weight group g by 1 − Π_contacts (1 − P(true, s)).
//!
//! ```text
//! P(true, s) = o λ_s ν_qs (1 - ε) Σ_c π_qc φ_s,c  /  [ o (1 - ε) Σ_s' λ_s' ν_qs' Σ_c π_qc φ_s',c + ε / N_pairs ]
//! ```
//!
//! Seeds / priors over the cells as `mix.rs` (`mix_prior`, `mix_seed_keep`, `mix_prior_mode`); no
//! restarts, commitment, groups or 2-D cell smoothing here.  Output: copy chains, models cell-major;
//! `cell_probs` (every input contact) and `phase_probs` (copy pair given true, in the most probable cell).

use crate::contacts::{contact_count, Structure};
use crate::diploid::{
    base_dict, candidate_mean_dist, copy_id, dip_groups, input_code, neighbour_prior, prepare_contacts, restraint_set,
    DipContact, DipGroups, DiploidInput, NbrPrior,
};
use crate::dynamics::{DensityCap, RestraintForm, System, V3};
use crate::params::{anneal_schedule, Params};
use crate::pipeline::{Input, Output, StageEngine, StageLog};
use crate::protocol2017::{backbone_restraints, calc_particles, interpolate, remove_isolated_contacts, start_coords};
use crate::robust::{force_constant, kernel_sum, pair_histogram, set_weights, split_schedule, EmData, EmLog, Kernel};
use crate::support::{support_evidence, SupportParams};
use rayon::prelude::*;
use std::collections::BTreeMap;
use std::time::Instant;

fn log(p: &Params, msg: &str) {
    if p.verbose {
        eprintln!("[uchrom_nucdyn] {msg}");
    }
}

/// One E-step + M-step (ε, kernel width, λ) of the cells × copies mixture.
#[allow(clippy::too_many_arguments)]
fn em_step(
    data: &EmData,
    g: &DipGroups,
    odds: &[f64],
    nu: &[f64],
    lambda: &[f64],
    k: usize,
    m: usize,
    kern: &Kernel,
    p: &Params,
    eps0: f64,
    s0: f64,
) -> (Vec<Vec<f64>>, Vec<f64>, Vec<f64>, Vec<f64>, f64, f64, EmLog) {
    let t0 = Instant::now();
    let u = 1.0 / data.n_pairs.max(1.0);
    let ng = g.n_groups();
    let nq = g.contacts.len().max(1) as f64;
    let phi_of = |kk: &Kernel, s: f64| -> (Vec<Vec<f64>>, f64) {
        let gm: Vec<f64> = data.hist.iter().map(|h| kernel_sum(kk, h, data.bin, data.n_pairs, s).max(1e-300)).collect();
        let phi = (0..k)
            .map(|c| {
                let mut row = vec![0.0; g.pairs.len()];
                for r in 0..m {
                    let mi = c * m + r;
                    for (x, v) in row.iter_mut().enumerate() {
                        *v += kk.f(data.dist[mi][x], s) / gm[mi] / m as f64;
                    }
                }
                row
            })
            .collect();
        (phi, gm.iter().sum::<f64>() / gm.len().max(1) as f64)
    };
    // Σ_c π_qc φ_s,c for contact slot q of group gi
    let mixc = |phi: &[Vec<f64>], s: usize, gi: usize, q: usize| -> f64 {
        let s0 = g.goff[gi] as usize;
        let nc = g.goff[gi + 1] as usize - s0;
        (0..nc).map(|c| g.prior[q][c] * phi[s][s0 + c]).sum()
    };
    let contact_of = |q: usize| g.contacts[q] as usize;
    let fit = |phi: &[Vec<f64>]| -> (f64, f64) {
        let mut eps = eps0;
        let term = |eps: f64, gi: usize, q: usize| -> f64 {
            let c = contact_of(q);
            odds[c] * (1.0 - eps) * (0..k).map(|s| lambda[s] * nu[c * k + s] * mixc(phi, s, gi, q)).sum::<f64>()
        };
        if p.robust_learn_eps {
            for _ in 0..200 {
                let fsum: f64 = (0..ng)
                    .into_par_iter()
                    .map(|gi| {
                        (g.coff[gi] as usize..g.coff[gi + 1] as usize)
                            .map(|q| {
                                let a = term(eps, gi, q);
                                if a <= 0.0 { 1.0 } else { eps * u / (a + eps * u) }
                            })
                            .sum::<f64>()
                    })
                    .sum();
                let new = (fsum / nq).clamp(p.robust_eps_min, p.robust_eps_max);
                let done = (new - eps).abs() < 1e-8;
                eps = new;
                if done {
                    break;
                }
            }
        }
        let ll: f64 = (0..ng)
            .into_par_iter()
            .map(|gi| {
                (g.coff[gi] as usize..g.coff[gi + 1] as usize)
                    .map(|q| {
                        let c = contact_of(q);
                        let o = odds[c];
                        let rho = o * (1.0 - eps) / (o * (1.0 - eps) + eps);
                        let mx: f64 = (0..k).map(|s| lambda[s] * nu[c * k + s] * mixc(phi, s, gi, q)).sum();
                        ((rho * mx + (1.0 - rho) * u) / u).ln()
                    })
                    .sum::<f64>()
            })
            .sum();
        (ll / nq, eps)
    };
    let grid: Vec<f64> = if p.robust_learn_s { p.robust_s_grid.clone() } else { vec![s0] };
    let mut best: Option<(f64, f64, f64)> = None;
    for &s in &grid {
        let (phi, _) = phi_of(kern, s);
        let (ll, eps) = fit(&phi);
        if best.is_none_or(|b| ll > b.0) {
            best = Some((ll, s, eps));
        }
    }
    let (ll, s, eps) = best.unwrap();
    let (phi, g_mean) = phi_of(kern, s);
    // responsibilities per group: weights per cell, P(true), cell posterior per contact slot
    let per: Vec<(Vec<f64>, Vec<f64>, Vec<f64>)> = (0..ng)
        .into_par_iter()
        .map(|gi| {
            let mut none = vec![1.0f64; k];
            let mut rt = vec![];
            let mut post = vec![];
            for q in g.coff[gi] as usize..g.coff[gi + 1] as usize {
                let c = contact_of(q);
                let a: Vec<f64> = (0..k).map(|x| odds[c] * lambda[x] * nu[c * k + x] * (1.0 - eps) * mixc(&phi, x, gi, q)).collect();
                let at: f64 = a.iter().sum();
                let den = at + eps * u;
                rt.push(if at <= 0.0 { 0.0 } else { at / den });
                for x in 0..k {
                    none[x] *= 1.0 - if at <= 0.0 { 0.0 } else { a[x] / den };
                    post.push(if at > 0.0 { a[x] / at } else { nu[c * k + x] });
                }
            }
            ((0..k).map(|x| (1.0 - none[x]).max(p.robust_w_floor)).collect(), rt, post)
        })
        .collect();
    let mut w = vec![vec![0.0; ng]; k];
    let mut r_true = vec![];
    let mut post = vec![];
    for (gi, (wg, rt, ps)) in per.into_iter().enumerate() {
        for x in 0..k {
            w[x][gi] = wg[x];
        }
        r_true.extend(rt);
        post.extend(ps);
    }
    let mut lam = lambda.to_vec();
    if p.mix_learn_pi {
        let mut acc = vec![0.0; k];
        for (q, &rt) in r_true.iter().enumerate() {
            for x in 0..k {
                acc[x] += rt * post[q * k + x];
            }
        }
        let tot: f64 = acc.iter().sum();
        if tot > 0.0 {
            for x in 0..k {
                lam[x] = (acc[x] / tot).max(p.mix_pi_floor);
            }
            let t2: f64 = lam.iter().sum();
            lam.iter_mut().for_each(|x| *x /= t2);
        }
    }
    let conf = (0..r_true.len()).filter(|&q| post[q * k..(q + 1) * k].iter().cloned().fold(0.0, f64::max) >= 0.9).count();
    let log = EmLog {
        segment: 0,
        eps,
        s,
        d0: kern.d0,
        loglik: ll,
        mean_w: r_true.iter().sum::<f64>() / nq,
        frac_low: r_true.iter().filter(|&&x| x < 0.5).count() as f64 / nq,
        prox_frac: g_mean * u,
        capture_q: (1.0 - eps) * nq / g_mean,
        n_particles: data.n_particles,
        seconds: t0.elapsed().as_secs_f64(),
        phase_confident: Some(conf as f64 / nq),
        n_ambiguous: Some(r_true.len()),
        ll_marginal: None,
    };
    (w, r_true, post, lam, eps, s, log)
}

/// The cells × copies deconvolution (protocol `robust`, `mix_cells` >= 2, phased input).
pub fn calc_diploid_mix(input: &Input, dip: &DiploidInput, p: &Params, engine: &mut dyn StageEngine, prior: Option<&[f64]>) -> Result<Output, String> {
    p.validate()?;
    let t0 = Instant::now();
    let k = p.mix_cells;
    let m = p.n_models;
    let n_input = input.chr_a.len();
    let mut contacts: Vec<DipContact> = prepare_contacts(input, dip, p.diploid_cis_sep)?;
    if p.robust_dip_nbr_prior {
        let nb = neighbour_prior(&contacts, &NbrPrior::default());
        for (c, q) in contacts.iter_mut().zip(nb) {
            let n = c.n_cand as usize;
            let mut tot = 0.0;
            for i in 0..n {
                c.prior[i] *= q[i];
                tot += c.prior[i];
            }
            for i in 0..n {
                c.prior[i] = if tot > 0.0 { c.prior[i] / tot } else { 1.0 / n as f64 };
            }
        }
    }
    let mut chroms: Vec<u32> = input.chr_a.iter().chain(input.chr_b).copied().collect();
    chroms.sort_unstable();
    chroms.dedup();
    log(p, &format!("diploid mix: {n_input} pooled contacts, {k} cells x {m} models"));
    let kern = Kernel::from_params(p);
    let kern_reach = Kernel { d0: p.robust_d0_grid.iter().cloned().fold(p.robust_d0, f64::max), ..kern };
    let s_max = p.robust_s_grid.iter().cloned().fold(p.robust_s, f64::max);
    let last = *p.particle_sizes.last().unwrap();
    // evidence odds per contact-list index (rows = contact order)
    let odds: Vec<f64> = if p.robust_support_rel > 0.0 {
        let sp = SupportParams { window: p.robust_support_rel * last, seed: p.seed, ..Default::default() };
        let s = support_evidence(input.chr_a, input.pos_a, input.chr_b, input.pos_b, &sp);
        contacts.iter().map(|c| s.lr[c.row as usize] * input.prior_lr.map(|x| x[c.row as usize]).unwrap_or(1.0)).collect()
    } else {
        contacts.iter().map(|c| input.prior_lr.map(|x| x[c.row as usize]).unwrap_or(1.0)).collect()
    };
    let mut keep = {
        let mut d = base_dict(&contacts, &vec![true; contacts.len()]);
        remove_isolated_contacts(&mut d, p.isolation_threshold_cis, p.isolation_pos_error);
        let mut kp = vec![false; contacts.len()];
        for v in d.values() {
            for c in v {
                kp[c.number as usize] = true;
            }
        }
        log(p, &format!("contacts after removing isolated = {}", contact_count(&d)));
        kp
    };
    // cell prior / seed (contact order = input rows)
    let seed: Vec<f64> = match prior {
        Some(pr) => {
            if pr.len() != n_input * k {
                return Err("mix prior: k values per contact".into());
            }
            contacts.iter().flat_map(|c| pr[c.row as usize * k..(c.row as usize + 1) * k].to_vec()).collect()
        }
        None => vec![1.0 / k as f64; contacts.len() * k],
    };
    let mut nu: Vec<f64> = seed.iter().map(|x| p.mix_seed_keep * x + (1.0 - p.mix_seed_keep) / k as f64).collect();
    let mut lambda = vec![1.0 / k as f64; k];
    let (mut eps, mut s) = (p.robust_eps, p.robust_s);
    let mut sizes = p.particle_sizes.clone();
    sizes.extend(std::iter::repeat_n(last, p.robust_refine));
    let mut prev: Option<Structure> = None;
    let mut stages = vec![];
    let mut snapshots: Vec<Vec<Vec<V3>>> = vec![];
    let ploidy = dip.ploidy;
    let copies = |g: &BTreeMap<u32, Vec<i64>>| -> BTreeMap<u32, Vec<i64>> {
        let mut out = BTreeMap::new();
        for (&c, v) in g {
            for h in 0..ploidy[c as usize] {
                out.insert(copy_id(c, h), v.clone());
            }
        }
        out
    };
    let nmt = k * m;
    for (stage, &ps) in sizes.iter().enumerate() {
        let ts = Instant::now();
        if p.robust_remove_violated && stage > 0 && ps < 0.5e6 {
            if let Some(pr) = prev.as_ref() {
                let thr = p.violated_threshold_2017;
                // closest candidate in the closest cell (replicate-mean distance)
                let ok: Vec<bool> = contacts
                    .par_iter()
                    .zip(keep.par_iter())
                    .map(|(c, &kp)| {
                        if !kp {
                            return false;
                        }
                        (0..k).any(|x| {
                            let sub = Structure { coords: pr.coords[x * m..(x + 1) * m].to_vec(), ..pr.clone_layout() };
                            candidate_mean_dist(c, &sub).into_iter().fold(f64::INFINITY, f64::min) < thr
                        })
                    })
                    .collect();
                keep = ok;
            }
        }
        let psi = ps as i32 as i64;
        let d = base_dict(&contacts, &keep);
        let full = calc_particles(&d, &chroms, psi);
        let mut st = Structure::new(&copies(&full));
        let n = st.n_particles();
        st.coords = start_coords(&st, nmt, prev.as_ref(), p, stage);
        let groups = dip_groups(&contacts, &keep, &st, p, p.robust_count_cap);
        let backbone = backbone_restraints(&st, psi, p.backbone_dist_lower, p.backbone_dist_upper);
        let (rs, nb) = restraint_set(backbone, &groups, false);
        let mut sys = System::new(n, vec![1.0; n], vec![1.0; n], &rs).with_form(RestraintForm::Weighted2017);
        if p.mix_density_rho > 0.0 && stage as i64 >= p.mix_density_stage {
            sys.density = Some(DensityCap { kappa: p.mix_density_kappa, r: p.mix_density_r, rho_max: p.mix_density_rho });
        }
        let reweight = stage >= p.robust_start_stage && groups.n_groups() > 0;
        let refine_pass = stage >= p.particle_sizes.len();
        let n_temp = if refine_pass && p.robust_refine_temp_steps > 0 { p.robust_refine_temp_steps } else { p.robust_temp_steps_for(stage.min(p.particle_sizes.len() - 1)) };
        let t_start = if refine_pass && p.robust_refine_temp_start > 0.0 { p.robust_refine_temp_start } else { p.temp_start };
        let schedule = anneal_schedule(t_start, p.temp_end, n_temp, 1.0);
        let dyn_steps = p.robust_dyn_steps_for(stage.min(p.particle_sizes.len() - 1));
        let parts = split_schedule(schedule.len(), if reweight { p.robust_segments } else { 1 });
        let t_prep = ts.elapsed().as_secs_f64();
        log(p, &format!("stage {} ({} kb): {n} particles, {} contacts in {} groups, {k} cells x {m} models", stage + 1, ps / 1e3, groups.n_used, groups.n_groups()));
        let td = Instant::now();
        let mut coords = std::mem::take(&mut st.coords);
        let mut em_logs = vec![];
        let mut t_em = 0.0;
        let mut f_dist = p.dist_force_const;
        // slot q of the groups -> contact index
        for (seg, range) in parts.iter().enumerate() {
            let rows: Vec<Vec<f64>> = if reweight {
                let te = Instant::now();
                let data = EmData::new(&coords, &groups.pairs, &vec![1u32; groups.pairs.len()], &kern_reach, s_max, p.robust_pair_sample);
                let (w, _rt, post, lam, e2, s2, mut l) = em_step(&data, &groups, &odds, &nu, &lambda, k, m, &kern, p, eps, s);
                eps = e2;
                s = s2;
                lambda = lam;
                if p.mix_prior_mode == "posterior" {
                    for (q, &c) in groups.contacts.iter().enumerate() {
                        let c = c as usize;
                        let t: Vec<f64> = (0..k).map(|x| post[q * k + x].max(1e-300).powf(p.mix_prior_temp)).collect();
                        let tot: f64 = t.iter().sum();
                        for x in 0..k {
                            nu[c * k + x] = (1.0 - p.mix_prior_floor) * t[x] / tot + p.mix_prior_floor / k as f64;
                        }
                    }
                }
                l.segment = seg;
                l.seconds = te.elapsed().as_secs_f64();
                t_em += l.seconds;
                log(p, &format!("  EM (part {seg}): eps {:.4} s {:.2} mean P(true) {:.3} cell-confident {:.3} lambda {:?} ll {:.4}", l.eps, l.s, l.mean_w, l.phase_confident.unwrap_or(f64::NAN), lambda, l.loglik));
                em_logs.push(l);
                w.iter().flat_map(|row| std::iter::repeat_n(row.clone(), m)).collect()
            } else {
                // prior-only weights per group: P(cell) of its contacts, every contact true
                let wk: Vec<Vec<f64>> = (0..k)
                    .map(|x| {
                        (0..groups.n_groups())
                            .map(|gi| {
                                let none: f64 = (groups.coff[gi] as usize..groups.coff[gi + 1] as usize)
                                    .map(|q| 1.0 - seed[groups.contacts[q] as usize * k + x])
                                    .product();
                                (1.0 - none).max(p.robust_w_floor)
                            })
                            .collect()
                    })
                    .collect();
                wk.iter().flat_map(|row| std::iter::repeat_n(row.clone(), m)).collect()
            };
            // per-model weights of the groups -> per restraint (every candidate of a group)
            let rows_r: Vec<Vec<f64>> = rows
                .iter()
                .map(|gw| {
                    let mut v = vec![];
                    for gi in 0..groups.n_groups() {
                        for _ in groups.goff[gi]..groups.goff[gi + 1] {
                            v.push(gw[gi]);
                        }
                    }
                    v
                })
                .collect();
            set_weights(&mut sys, nb, &rows_r, nmt);
            let key = stage + 1000 * seg;
            f_dist = force_constant(p, &sys, nb, n);
            coords = engine.anneal(&sys, coords, &schedule[range.clone()], dyn_steps, f_dist, 1.0, key, p)?;
            if stage + 1 == sizes.len() && seg + 1 == parts.len() && p.robust_sample_temp > 0.0 && p.robust_sample_steps > 0 {
                let f_rep = schedule.last().map(|x| x.1).unwrap_or(1.0);
                let block = vec![(p.robust_sample_temp, f_rep); p.robust_sample_steps];
                let ds = if p.robust_sample_dyn_steps > 0 { p.robust_sample_dyn_steps } else { dyn_steps };
                coords = engine.anneal(&sys, coords, &block, ds, f_dist, 1.0, stage + 5000, p)?;
                snapshots.push(coords.clone());
            }
        }
        for c in coords.iter_mut() {
            let kk = c.len() as f64;
            let mut mm = [0.0; 3];
            for q in c.iter() {
                for x in 0..3 {
                    mm[x] += q[x];
                }
            }
            for q in c.iter_mut() {
                for x in 0..3 {
                    q[x] -= mm[x] / kk;
                }
            }
        }
        st.coords = coords;
        let t_dyn = td.elapsed().as_secs_f64() - t_em;
        stages.push(StageLog {
            stage,
            particle_size: ps,
            bead_size: 1.0,
            n_models: nmt,
            n_particles: n,
            n_contacts: groups.n_used,
            n_restraints: sys.n_restraints(),
            dist_force_const: f_dist,
            temp_steps: schedule.len(),
            dynamics_steps: dyn_steps,
            seconds_prepare: t_prep + t_em,
            seconds_dynamics: t_dyn,
            removed_models: vec![],
            device: engine.name(),
            rep_list_overflows: 0,
            steps_without_repulsion: 0,
            robust: em_logs,
        });
        prev = Some(st);
    }
    let st = prev.unwrap();
    // final E-step over every input contact: per cell the candidate mixture (closest-candidate kernel, d0 = mix_assign_d0)
    let kk = Kernel { d0: p.mix_assign_d0, ..kern };
    let gm: Vec<f64> = st
        .coords
        .iter()
        .map(|c| {
            let (h, np) = pair_histogram(c, kern_reach.reach(s_max), 0.02, p.robust_pair_sample);
            kernel_sum(&kk, &h, 0.02, np, s).max(1e-300)
        })
        .collect();
    let npair = {
        let nn = st.n_particles() as f64;
        nn * (nn - 1.0) / 2.0
    };
    let u = 1.0 / npair.max(1.0);
    let mut cell_probs = vec![f64::NAN; n_input * k];
    let mut contact_weights = vec![f64::NAN; n_input];
    let mut phase_probs = vec![f64::NAN; 4 * n_input];
    let res: Vec<(usize, Vec<f64>, f64, Vec<(usize, f64)>)> = contacts
        .par_iter()
        .map(|c| {
            let nc = c.n_cand as usize;
            // phi[s][cand]
            let phi: Vec<Vec<f64>> = (0..k)
                .map(|x| {
                    let sub = Structure { coords: st.coords[x * m..(x + 1) * m].to_vec(), ..st.clone_layout() };
                    let gmx: f64 = gm[x * m..(x + 1) * m].iter().sum::<f64>() / m as f64;
                    candidate_mean_dist(c, &sub).into_iter().map(|dd| kk.f(dd, s) / gmx).collect()
                })
                .collect();
            let a: Vec<f64> = (0..k).map(|x| lambda[x] * (0..nc).map(|q| c.prior[q] * phi[x][q]).sum::<f64>() * (1.0 - eps)).collect();
            let at: f64 = a.iter().sum();
            let post: Vec<f64> = if at > 0.0 { a.iter().map(|v| v / at).collect() } else { vec![1.0 / k as f64; k] };
            let bx = (0..k).max_by(|&x, &y| post[x].partial_cmp(&post[y]).unwrap()).unwrap();
            let pc: Vec<f64> = (0..nc).map(|q| c.prior[q] * phi[bx][q]).collect();
            let pt: f64 = pc.iter().sum();
            let ph: Vec<(usize, f64)> = (0..nc).map(|q| (input_code(c, c.cand[q]), if pt > 0.0 { pc[q] / pt } else { c.prior[q] })).collect();
            (c.row as usize, post, if at > 0.0 { at / (at + eps * u) } else { 0.0 }, ph)
        })
        .collect();
    for (r, post, pt, ph) in res {
        cell_probs[r * k..(r + 1) * k].copy_from_slice(&post);
        contact_weights[r] = pt;
        for x in 0..4 {
            phase_probs[4 * r + x] = 0.0;
        }
        for (code, v) in ph {
            phase_probs[4 * r + code] = v;
        }
    }
    let mut st = st;
    if !snapshots.is_empty() {
        st.coords = snapshots.pop().unwrap();
    }
    let nm = st.coords.len();
    let _ = interpolate;
    Ok(Output {
        chroms: st.chroms,
        seq_pos: st.seq_pos,
        coords: st.coords,
        model_rmsds: vec![f64::NAN; nm],
        particle_size: last,
        stages,
        seconds_total: t0.elapsed().as_secs_f64(),
        contact_weights,
        diploid: true,
        phase_probs,
        mix_cells: k,
        cell_probs,
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::pipeline::CpuEngine;
    use crate::rng::Rng;

    /// Two diploid toy cells (2 chromosomes x 2 homologs, random walks), 40 % of the ends phased;
    /// pooled with a 75 %-correct cell seed: the run separates the cells (long-range assignment
    /// accuracy) and returns copy chains for every cell.
    #[test]
    fn diploid_pool_with_partial_seed() {
        let mut rng = Rng::new(5);
        let names: Vec<String> = vec!["chrA".into(), "chrB".into()];
        let nloc = 120usize;
        let (mut ca, mut pa, mut cb, mut pb, mut ha, mut hb, mut origin) = (vec![], vec![], vec![], vec![], vec![], vec![], vec![]);
        for cell in 0..2 {
            let walks: Vec<Vec<V3>> = (0..4)
                .map(|w| {
                    let mut q = [(w / 2) as f64 * 5.0 + rng.normal() * 3.0, (w % 2) as f64 * 8.0 + rng.normal() * 3.0, rng.normal() * 3.0];
                    (0..nloc)
                        .map(|_| {
                            q = [q[0] + rng.normal() * 0.35, q[1] + rng.normal() * 0.35, q[2] + rng.normal() * 0.35];
                            q
                        })
                        .collect()
                })
                .collect();
            for _ in 0..40_000 {
                let (c1, h1) = ((rng.uniform() * 2.0) as usize, (rng.uniform() * 2.0) as usize);
                let (c2, h2) = if rng.uniform() < 0.85 { (c1, h1) } else { ((rng.uniform() * 2.0) as usize, (rng.uniform() * 2.0) as usize) };
                let (i, j) = ((rng.uniform() * nloc as f64) as usize, (rng.uniform() * nloc as f64) as usize);
                let (a, b) = (walks[2 * c1 + h1][i], walks[2 * c2 + h2][j]);
                if (0..3).map(|x| (a[x] - b[x]).powi(2)).sum::<f64>() < 0.8 {
                    ca.push(c1 as u32);
                    pa.push(i as i64 * 100_000 + 50_000);
                    cb.push(c2 as u32);
                    pb.push(j as i64 * 100_000 + 50_000);
                    ha.push(if rng.uniform() < 0.4 { h1 as i8 } else { -1 });
                    hb.push(if rng.uniform() < 0.4 { h2 as i8 } else { -1 });
                    origin.push(cell);
                }
            }
        }
        let n = ca.len();
        let amb: Vec<i64> = (1..=n as i64).collect();
        let act = vec![true; n];
        let dip = DiploidInput { hap_a: &ha, hap_b: &hb, ploidy: &[2, 2], prior: None };
        let input = Input { names: &names, chr_a: &ca, pos_a: &pa, chr_b: &cb, pos_b: &pb, ambig: &amb, active: &act, prior_lr: None, dip: Some(dip) };
        let mut prior = vec![0.0; 2 * n];
        for i in 0..n {
            let c = if rng.uniform() < 0.5 { (rng.uniform() * 2.0) as usize } else { origin[i] };
            prior[2 * i + c] = 1.0;
        }
        let p = Params {
            protocol: "robust".into(),
            mix_cells: 2,
            mix_seed_keep: 0.95,
            mix_prior_mode: "posterior".into(),
            mix_prior_floor: 0.0,
            particle_sizes: vec![4e6, 1e6, 4e5],
            n_models: 2,
            seed: 3,
            robust_temp_steps: vec![60],
            robust_dynamics_steps: vec![50],
            n_threads: 2,
            ..Default::default()
        };
        let mut eng = CpuEngine::new(2).unwrap();
        let out = crate::mix::calc_with_prior(&input, &p, &mut eng, Some(&prior)).unwrap();
        assert!(out.diploid);
        assert_eq!(out.mix_cells, 2);
        assert_eq!(out.coords.len(), 4);
        assert_eq!(out.chroms, vec![0, 1, 2, 3]);
        let (mut right, mut tot) = (0, 0);
        for i in 0..n {
            if ca[i] == cb[i] && (pa[i] - pb[i]).abs() < 1_000_000 {
                continue;
            }
            tot += 1;
            let best = if out.cell_probs[2 * i] >= out.cell_probs[2 * i + 1] { 0 } else { 1 };
            right += (best == origin[i]) as usize;
        }
        let acc = right as f64 / tot as f64;
        eprintln!("diploid toy pool: long-range cell assignment accuracy {acc:.3} ({tot})");
        assert!(acc > 0.65, "{acc}");
    }
}
