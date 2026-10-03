# u-chrom-nucdyn

Native NucDynamics engine for [U-Chrom](../../README.md): single-cell Hi-C
genome structure calculation by simulated annealing of a particle model,
written in Rust with PyO3 bindings.  It also runs protocol **"igm"**: population
modelling of bulk Hi-C (the A/M deconvolution of IGM / PGS; see
[Protocol "igm"](#protocol-igm-population-modelling-of-bulk-hi-c)).

* **CPU**: f64, multi-core with rayon.  The models of an ensemble run in
  parallel; when there are fewer models than cores, the force loops of each
  model are split across threads too.  Every force is *gathered* per
  particle over fixed chunks, so a seed gives bitwise-identical results for
  any number of threads.
* **GPU**: wgpu (WGSL compute shaders; Metal on macOS, Vulkan on Linux /
  NVIDIA, DX12 on Windows), f32.  All models of an ensemble are advanced
  together in one set of buffers and every kernel is dispatched over
  (particles, models); nothing is read back until the end of a stage.

Import name `uchrom_nucdyn`, pip name `u-chrom-nucdyn`.  U-Chrom uses it from
`uchrom.recon.sc.nucdyn` whenever it is installed.

```bash
pip install ./native/nucdyn                  # CPU + GPU backend (default)
cd native/nucdyn && maturin build --release --features python   # CPU-only wheel
cargo test --release [--features gpu]        # Rust tests
```

```python
from uchrom.recon.sc.nucdyn import reconstruct_nucdyn
cd = reconstruct_nucdyn("cell1.pairs", n_models=10, device="auto", seed=1)
cd.coords                     # model 0 (particle radii); cd.layers["model_<k>"]: every model

import uchrom_nucdyn          # array-level API
res = uchrom_nucdyn.calc_genome_structure(chr_a, pos_a, chr_b, pos_b, n_models=10, device="gpu")
```

## Attribution

This is a clean re-implementation of the algorithm of **NucDynamics**:

> Stevens, T. J., Lando, D., Basu, S., Atkinson, L. P., Cao, Y., Lee, S. F.,
> Leeb, M., Wohlfahrt, K. J., Boucher, W., O'Shaughnessy-Kirwan, A., Cramard,
> J., Faure, A. J., Ralser, M., Blanco, E., Morey, L., Sansó, M., Palayret,
> M. G. S., Lehner, B., Di Croce, L., Wutz, A., Hendrich, B., Klenerman, D. &
> Laue, E. D. (2017). 3D structures of individual mammalian genomes studied
> by single-cell Hi-C. *Nature* 544, 59–64. doi:10.1038/nature21429

Original implementation: <https://github.com/tjs23/nuc_dynamics> (Tim J.
Stevens; Python + Cython), GNU Lesser General Public License v3.0.  No code
was copied: the behaviour of each original function was re-implemented from
the algorithm, and the Rust functions keep the original names so the two can
be compared side by side.  This crate is distributed under the
LGPL-3.0-or-later as well.  Please cite Stevens et al. 2017 when you use
structures computed with this engine.

## Protocols

`protocol="nuc_dynamics_2017"` (default) follows the `master` branch of
tjs23/nuc_dynamics (`nuc_dynamics.py` + `dyn_util.pyx`; algorithm unchanged
since 2017-10), the code behind the published 2017 structures (its particle
convention is the one of the GEO models).  `protocol="release_1.3"` follows
the repository's later default branch (`release_1.3`, 2021–22: bead-size
scaling, restraint weights, 3-D ambiguity resolution, model selection).

`protocol="robust"` (public name **EMber**; alias `protocol="ember"` in the Python
wrapper; `uchrom.recon.sc.reconstruct_ember`) is **not** NucDynamics: it is the new single-cell
method of U-Chrom (`benchmarks/screcon/PREREG.md` §7; milestone M2,
annealing only), built on the 2017 protocol.  Each contact is modelled as a
true proximity or a false contact (uniform over pairs, rate ε); before every
stage from `robust_start_stage` on (and `robust_segments` times inside it,
plus `robust_refine` extra passes at the final size) the contact restraints
are re-weighted by the posterior probability that they are true (EM: ε and
the contact-kernel width fitted to the current distances; `src/robust.rs`).
Optional evidence: per-contact likelihood ratios (`prior_lr`), the
structure-free local-support evidence (`robust_support_rel`, `src/support.rs`)
and a Poisson "no contact" term (`robust_nc_scale`).  With re-weighting
disabled (`robust_start_stage` beyond the schedule) it equals the 2017
protocol bit for bit; the existing protocols are unchanged
(`tests/regression.rs`, golden hashes recorded before `robust` was added).
Development log: `benchmarks/screcon/robust_devlog.md`.

### Where each element of the original is implemented (2017 protocol)

| Original (`master`) | What it does | Here |
|---|---|---|
| `load_ncc_file` | contact position = fragment start on +, end on −; `chr_a > chr_b` (string order) → swap ends; cis order kept | `uchrom_nucdyn.read_ncc` (Python), `contacts::build_contact_dict` |
| `remove_isolated_contacts` + `getSupportedPairs` | once, before stage 1: keep a contact if another contact of the same chromosome pair lies within (100 bp, 2 Mb) at both ends (either orientation) | `protocol2017::remove_isolated_contacts`, `contacts::supported_contacts` (sorted windows, same result as the O(n²) scan; tested against brute force) |
| `calc_restraints` (binning) | particles at `floor(min/s)·s … s·ceil(float32(max)/s)` inclusive; a contact end at p → first particle with position ≥ p; chromosome without contacts → one particle at 0 | `protocol2017::calc_particles`, `contact_restraints` (float32 `ceil` reproduced) |
| `calc_restraints` (restraints) | one restraint per non-empty (i, j) cell of each chromosome pair incl. i = j and \|i − j\| = 1; target `N^-0.33` (float32 `powf`), bounds 0.8 / 1.2 × target (float32 constants) | `protocol2017::contact_restraints` |
| `concatenate_restraints` | backbone (k, k+1) bounds 0.1 / 1.1 (float32); global indices in string-sorted chromosome order | `protocol2017::backbone_restraints`, `setup_stage` |
| `getRestraintForce` | harmonic below d_min and in (d_max, d_max + 0.5]; constant force K beyond (switch 0.5 absolute, asymptote 1); K = 25; ambiguous groups via (Σ d⁻⁴)^(−1/4) | `dynamics::group_force_2017`; GPU `restraints` kernel (form 0) |
| `getRepulsiveForce` | k_rep (4 − d²)² for d ≤ r_i + r_j = 2, pairs with global \|i − j\| ≥ 2 (also across chromosome boundaries) | `dynamics::compute_forces_mode` / `repulse`; GPU `total_force` |
| `getRepulsionList` + rebuild in `runDynamics` | list radius repDist + r_i + r_j = 4; rebuilt at step 0 of every call and when a particle moved > 1 radius (checked before the position update) | default: exact cell grid rebuilt every step (`CellGrid`); original schedule: `NeighbourList` + `original_nl_schedule` (used for the bitwise cross-check) |
| `runDynamics` (list capacity) | overflow → list replaced by zeros → no repulsion until the next rebuild | not reproduced by default; `emulate_rep_list_overflow=True` reproduces it (Verlet list, original schedule) |
| `runDynamics` init | v ~ N(0, 1), scaled to T_ref (T = Σ m v² / (3 N k_B), k_B = 0.0019872041); forces at the start coordinates | `dynamics::run_dynamics`; GPU `vel_init`, `temp_reduce_vinit`, `vel_scale`, `force_only` |
| `updateMotion` / `updateVelocity` | Δt = 0.001 × 20.458; β = 10 / 20.458; a = F/m + β(T_ref/T − 1) v; x += Δt v + ½Δt² a; v += Δt a; v += ½Δt (F/m + λ' v − a) with T from the updated v | `dynamics::run_dynamics`; GPU `motion`, `temp_reduce*`, `force_update` |
| `anneal_genome` schedule | 500 temperature steps: T = 5000·exp(−ln(500)·f), k_rep = 0.5 + atan(20f − 10)/(π atan 10), 100 MD steps each, fresh velocities per step | `params::anneal_schedule`, `pipeline::CpuEngine::anneal`, `gpu::GpuEngine::run_schedule` |
| `get_random_coords` | stage 1: every particle uniform in a ball of radius 10 (rejection sampling in the cube) | `protocol2017::random_coords` |
| `getInterpolatedCoords` | later stages: coordinates interpolated from the previous stage at the new particle positions (nearest / bracketing particle, float32 fraction, clamped ends) | `protocol2017::interpolate` (tested against a literal transcription of the scan) |
| `remove_violated_contacts` | before stages < 0.5 Mb: contacts whose model-mean distance (ends interpolated) ≥ 6 radii are removed for good | `protocol2017::remove_violated_contacts` |
| `calc_genome_structure` | stages 8, 4, 2, 0.4, 0.2, 0.1 Mb; fixed number of models; each model centred; no selection or superposition | `protocol2017::calc_genome_structure` |
| `parallel_split_job` | one process per model | models in parallel on rayon threads (CPU) / batched on the GPU |

The release_1.3 protocol is implemented in `contacts.rs`
(`initial_clean_contacts` with cis 2 Mb / trans 10 Mb thresholds and
unambiguous contacts only, `calc_bins`, `remove_violated_contacts` with
5 / 6 × bead thresholds, `resolve_3d_ambiguous`), `restraints.rs`
(`calc_restraints`, `backbone_restraints`, `bin_restraints`,
`calc_ambiguity_offsets`), `dynamics::group_force` (weights, switch at
0.5 d_max), `align.rs` (`align_coord_models`, `remove_models`: 2 × n models
above 1 Mb, the n closest to the mean kept) and
`pipeline::calc_genome_structure_release13` (bead = size^(1/3) scaling,
K = 215 N / n_contacts, output ÷ bead and superposed).

### Deviations from the original, and why

* **Repulsion pairs are exact.**  The original checks the neighbour list
  *before* moving the particles, so a pair can come within the cutoff
  during a step and be missed until the next rebuild (seen from random
  starts at high temperature).  The default cell grid finds every pair at
  every step.  With `original_nl_schedule` the engine reproduces the
  original to ≤ 2e-13 particle radii over 100 steps (cross-check below).
* **Neighbour-list overflow** (repulsion switched off after the list
  capacity is exceeded) is not reproduced unless
  `emulate_rep_list_overflow=True` (2017 protocol).
* **Neighbour-list region bug** of the original (its bounding-box arrays hold
  one all-zero box too many when the particle count is a multiple of 8 below
  2048, or of 256 above; pairs of one particle block are then missed) is not
  reproduced.
* **Random numbers**: independent xoshiro256++ streams per (seed, stage,
  model) on the CPU and a counter-based PCG hash + Box–Muller on the GPU,
  instead of numpy's global Mersenne Twister re-seeded per stage (whose
  state is also copied into every worker process by `fork`, so the models of
  a stage draw the same velocities there).  Same distributions.
* **GPU precision**: f32 (WGSL has no f64); the order of force summation
  within a cell depends on atomics, so GPU runs are not bitwise
  reproducible.  From identical start coordinates and velocities, GPU and
  CPU agree to ~3e-5 radii after 10 steps (Rust test
  `gpu_matches_cpu_for_short_runs`); ensembles agree statistically.
* **Not implemented**: the paper's final round (ambiguous contacts
  disambiguated and isolated contacts re-added with the 100 kb structures,
  then one more 100 kb calculation — in neither code version), diploid /
  homologue ambiguity handling of release_1.3, starting from an N3D file,
  intermediate file output, the release_1.3 list-overflow quirk.

## Protocol "igm": population modelling of bulk Hi-C

`uchrom_nucdyn.calc_population(...)` (U-Chrom: `uchrom.recon.bulk.deconv.deconvolve(..., method="igm")`)
fits a population of S diploid genome structures to one haploid contact-probability
matrix by alternating the A-step (activation distances computed over the population
decide which structure carries which contact restraint) and the M-step (every structure
annealed and minimised independently), over a decreasing probability threshold σ.

This is a clean re-implementation of the algorithm of **IGM** and its predecessor **PGS**:

> Boninsegna, L., Yildirim, A., Polles, G., Zhan, Y., Quinodoz, S. A., Finn, E. H.,
> Guttman, M., Zhou, X. J. & Alber, F. (2022). Integrative genome modeling platform
> reveals essentiality of rare contact events in 3D genome organizations.
> *Nature Methods* 19, 938–949. doi:10.1038/s41592-022-01527-x
>
> Tjong, H., Li, W., Kalhor, R., Dai, C., Hao, S., Gong, K., Zhou, Y., Li, H., Zhou,
> X. J., Le Gros, M. A., Larabell, C. A., Chen, L. & Alber, F. (2016). Population-based
> 3D genome structure analysis reveals driving forces in spatial genome organization.
> *PNAS* 113, E1663–E1672. doi:10.1073/pnas.1512577113
>
> Hua, N., Tjong, H., Shin, H., Gong, K., Zhou, X. J. & Alber, F. (2018). Producing
> genome structure populations with the dynamic and automated PGS software.
> *Nature Protocols* 13, 915–926. doi:10.1038/nprot.2018.008

Original code: github.com/alberlab/igm (GPL-3.0), alabtools (GPL-3.0), lammpgen (the
modified LAMMPS, GPL-2.0), pgs (GPL-3.0).  **No code of these was copied or
translated**: the engine was written from the algorithm specification
`benchmarks/bulk/pgs_spec.md` (which records what the original code does, with
citations to its functions) and stays LGPL-3.0-or-later.  Please cite the papers above
when you use populations computed with this protocol.

```python
import uchrom_nucdyn as un
res = un.calc_population(chrom, start, end, prob_i, prob_j, prob_v, ploidy="diploid",
                         n_structures=1000, device="gpu", seed=1)
res["coords"]          # (S, N_beads, 3) float32, nm; res["bead_bin"], res["bead_copy"], res["radii"]
res["rounds"]          # per A/M round: sigma, iteration, restrained pairs, bonds, violation score, timings
```

### Where each element of the original is implemented (IGM `edbb331`)

| Original | What it does | Here |
|---|---|---|
| `_preprocess.py:PrepareGenomeIndex`, alabtools `make_diploid` / `make_multiploid` | bead layout: haploid index for copy 0, then copy 1 (`male`: X, Y single); `copy_index` | `igm/genome.rs:Genome::new`; ploidy strings in `uchrom_nucdyn.resolve_copies` |
| `_preprocess.py:Preprocess` | radii `r = (ρ · size / (4π/3))^{1/3}`, `ρ = occupancy · V_nuc / Σ sizes` (sphere or ellipsoid) | `Genome::new` |
| `ActivationDistanceStep.get_actdist` (`rcutsq`, `contact_range`) | contact: centre distance ≤ 2 (r_i + r_j) | `igm/astep.rs`, `forces.rs:hic_d0` |
| LAMMPS `pair soft` + `PairIJ Coeffs` (`create_lammps_data`), `special_bonds 1 1 1`, `fix adapt … scale yes` | `U = A(1 + cos(π d/r_c))`, `A = evfactor · stage_ev · ((r_i + r_j)/π)²`, `r_c = r_i + r_j`, all pairs incl. bonded neighbours and homologs | `igm/forces.rs:soft_pair`; GPU `igm.wgsl:total_force` (cell grid rebuilt every step, stencil over `2 r_max`) |
| lammpgen `bond_harmonic_upper_bound.cpp` | `U = k(d − d0)²` for d > d0 (no ½), `F = −2k(d − d0)` | `forces.rs:upper_bond`; WGSL `upper_bond` |
| `restraints/polymer.py:Polymer` (`simple`, `hic`) | consecutive beads of one chain: `d0 = contact_range (r_i + r_{i+1})`, or the shell-volume form from `P[i, i+1]` | `genome.rs:polymer_bonds` (shared CSR, both ends) |
| `restraints/envelope.py` → `fix ellipsoidalenvelope` (`fix_ellipsoidal_envelope.cpp`) | `k² = Σ x²/(a − r)²`; if > 1: `t = (1 − 1/√k²)|x|`, `U = ½ k t²`, force `k t` along the normalised `(x/(a−r)², …)`; semi-axes × stage factor | `forces.rs:envelope`; WGSL `total_force` |
| `intra_hic.py` / `inter_hic.py` `_apply` | per structure, per activation row: bond iff current `d ≤ d_act`, `d0 = contact_range (r_i + r_j)`, `k = contact_kspring` | `astep.rs:assign` (CPU); `igm.wgsl:assign_total / assign_count / assign_scan / assign_fill` (per-structure CSR on the device) |
| `ActivationDistanceStep.get_actdist` | intra: same-copy combinations (n = 2), inter: all (n = 4); `p_now`, `clean`, `o = min(nS − 1, round(n p S))`, `d_act = sqrt(sortdist[o])`, one row per combination; `p_last` = cleaned p of the previous A-step | `astep.rs:actdist`, `p_and_rank`, `round_half_even`; GPU `astep.wgsl:ad_count` + `ad_select` (exact radix select of the rank-o f32 square; host computes p and o in f64) |
| `ModelingStep.task` → `kernel/lammps.py:create_lammps_script` | per stage: `fix adapt`, envelope factor, `relax` block (`velocity create`, `temp/rescale T T`, `nve/limit`), `velocity create t0`, `temp/rescale t0 t1 0.1 1`, `run`; then `min_style cg; minimize etol ftol maxiter maxeval` | `igm/md.rs:mstep` (CPU); `igm/gpu.rs:mstep`, `md_run`, `cg_run` |
| LAMMPS `velocity … create` (defaults) | uniform components, zero momentum, scaled to T with `dof = 3N − 3` | `md.rs:velocity_create`; WGSL `vel_create`, `vel_mean`, `vel_center`, `vel_scale_set` |
| `fix nve/limit` | `v += ½dt F`, `|v| ≤ xmax/dt`, `x += dt v`; `v += ½dt F`, limit | `md.rs:run`; WGSL `integrate1`, `force_int2` |
| `fix temp/rescale` | every step: target `t0 + (step/n)(t1 − t0)`; if `|T − target| > window` rescale to `T − fraction(T − target)` | `md.rs:run`; WGSL `temp_rescale` (factor applied at the next `integrate1`) |
| LAMMPS `min cg` | Polak–Ribière, `β = max(0, (g₁·g₁ − g₁·g₀)/g₀·g₀)`, restart every `3N` iterations, `h = g` if not downhill; stop on `etol` (relative), `ftol` (force 2-norm), `maxiter`, `maxeval` | `md.rs:minimize`; GPU: one state machine per structure (`cg_force`, `cg_decide`, `cg_update`, `cg_dir`) |
| `RandomInit` / `RelaxInit` | chain centres uniform in a ball of `R_init − r̄`, beads uniform in a ball of `r̄ = mean(0.75 R_init (n_c/n)^{1/3})`; then one M-step with polymer, excluded volume and envelope only | `igm/driver.rs:random_structure`, `run_igm` (round 0) |
| `bin/igm-run:run_pipeline` | σ lists popped in lockstep; per σ: A-step → M-step → `violation_score = Σ violated / Σ imposed`; accept if `< max_violations` and not forced; forced for `0 < it < min_iterations − 1`, once after iteration 0 at the last σ (`force_last_iteration`) or at `intra σ ≤ force_minimum_iterations_hic_cutoff`; stop at `max_iterations` with the current population | `driver.rs:run_igm`, `is_forced` |
| `ModelingStep` `getViolationRatio` | Hi-C / polymer `(d − d0)/d0 > tol`; envelope `t/(k · 0.1 R̄) > tol`; excluded volume not monitored | `forces.rs:violations`; WGSL `violations_k` |
| `.hss` output (`coordinates` (N, S, 3)), intermediate `.hss` per iteration | population | returned arrays; U-Chrom writes a ChromData (cells = structures, traces = chromosome copies), intermediate rounds optional (`keep_intermediate`) |

### Opt-in options from IGM-Plus and IGM_2.0 (defaults = IGM 1.0)

IGM-Plus (github.com/alberlab/IGM-Plus v2.0.2, `b1891b4`, GPL-3.0; common ancestor
with `alberlab/igm` 2021-09-17, same A-step) and IGM_2.0 (github.com/alberlab/IGM_2.0,
`82143c0`, GPL-3.0) change a few implementation details.  They are available as opt-in
parameters, re-implemented from the behaviour described below (no code copied); with
the defaults the engine runs the IGM 1.0 protocol above bit for bit
(`igm/regression_tests.rs:default_run_is_unchanged`, `tests/test_deconv_igm.py::test_default_run_unchanged_by_the_options`,
CPU f64, hashes recorded before the options existed).

| Original | What it does | Here (parameter, default) | Differences |
|---|---|---|---|
| IGM-Plus `_preprocess.py:PrepareGenomeIndex` (`genome/usechr`) + `Preprocess` | model a chromosome subset (e.g. one chromosome, haploid or diploid via `ploidy`); radii from the occupancy over the **modelled** index; envelope = the full nucleus | U-Chrom `deconvolve(..., chrom=)` (bins restricted before the engine) with `ploidy`; `occupancy_total_bp` (0 = modelled beads, as IGM-Plus); U-Chrom `IgmParams.occupancy_scope = "model"` / `"genome"` / bp | `"genome"` is an addition: radii of the whole-genome model (Σ input bin sizes × copies), so a subset keeps whole-genome bead sizes and fills its natural share of the nucleus |
| IGM-Plus `_preprocess.py:Preprocess` (`model/bead_radius` when `model/occupancy` is absent) | one radius (nm) for every bead instead of radii from the occupancy | `bead_radius` (0 / `None` = off); requires `occupancy = 0` (Rust) / `occupancy=None` (Python; `replace(bead_radius=…)` drops it) | IGM-Plus silently prefers `occupancy` when both are given; here giving both is an error |
| IGM-Plus `restraints/intra_hic.py:intraHiC` / `inter_hic.py:interHiC`, `ModelingStep.add_hic` | intra- and inter-chromosomal Hi-C bonds as two restraint objects (same `contact_range`, same `contact_kspring`), reported separately in the violation summary | `Violations.hic_inter_imposed / hic_inter_violated` (subset of `hic_*`); round logs' `breakdown` (`hic_intra`, `hic_inter`, `polymer`, `envelope`); GPU: inter flag in bit 31 of the CSR partner word (`igm.wgsl:assign_fill`, `violations_k`) | separate σ lists already existed (`intra_sigma_list` / `inter_sigma_list`, IGM 1.0); IGM-Plus adds no separate force constant or contact range, so neither is added; always reported (reporting only, no effect on the run) |
| IGM-Plus `ActivationDistanceStep.__init__` / `get_actdist` (`optimization/iter_corr_knob`) | knob = 0: `p = p_wish` instead of `clean(p_wish, clean(p_now, p_last))` | `iterative_correction` (true); `astep.rs:p_and_rank_opt`; GPU host side | — |
| IGM-Plus `RandomInit.task` (`restraints/tracing/assignment_file`, `model/init_noise`) | selected loci of a structure start at given xyz; loci between two consecutive pinned loci linearly interpolated; Gaussian noise `init_noise · N(0,1)` on every coordinate | `driver.rs:InitPins`, `apply_pins`, `initial_population`; `calc_population(init_pins=…)`; U-Chrom `deconvolve(init_positions=DataFrame)`; `init_noise` (0) | interpolation only between pins of the **same chain** (IGM-Plus interpolates between consecutive pinned bead indices, also across chain ends); noise whenever `init_noise > 0` (IGM-Plus: in tracing mode); the pins set the start only — IGM-Plus' `Tracing` positional restraint is stage 2 (`benchmarks/bulk/design.md`) |
| IGM-Plus `RelaxInit.task` (violations after relaxation), `ModelingStep.log_stats` ("Mostly violated in structure …") | violation counts after the initial relaxation; per restraint kind the structure with the largest violated / imposed ratio (and the number of ties) | `RunOutput.relax_log` (`res["relax_init"]`, `uns["deconv"]["relax_init"]`); `RoundLog.breakdown` (`driver.rs:breakdown`), printed with `verbose` | reporting only |
| IGM_2.0 `steps/GP_ActivationDistanceStep.py:get_actdist` (G. Polles) | every pair (intra and inter) pools all `len ii · len jj` copy combinations; per structure the `n_possible = min(len ii, len jj)` smallest distances enter `p_now` and the rank selection; rows as IGM 1.0 (intra: same copy, inter: all) | `assignment_pooling = "gp"` ("igm"); `astep.rs:pool_combos`, `actdist_opt`; GPU `astep.wgsl:item` (per-structure rank among ≤ 16 combinations; ≤ 4 copies) | — (for the sensitivity analysis of `benchmarks/bulk/design.md`) |

Not adopted from IGM-Plus: the imaging-derived restraints (volume maps, lamina DamID with
imaged laminas, tracing / single-cell FISH restraints; design in
`benchmarks/bulk/design.md`, "Stage 2"), the `polymer/violations` switch (polymer bonds
are always monitored, as in IGM 1.0), `polymer_bonds_style = "none"`.

### Deviations from the original, and why

* **Line search of the final minimisation**: LAMMPS' `backtrack` (Armijo slope 0.4,
  α halved, first step `min(1, dmax/max|h|)`, `dmax = 0.1`) instead of IGM's default
  `quadratic`.  The quadratic variant adds a secant step whose exact bookkeeping is not
  specified; with `dmax = 0.1` nm the minimisation is a small polish after 47,000 MD
  steps either way.  The stopping rules and the PR update are LAMMPS'.
* **Random numbers**: counter-based streams keyed by (seed, round, structure, stage)
  (xoshiro256++ on the CPU, a PCG hash on the GPU) instead of LAMMPS' generator seeded
  with `((seed · struct_id · (step_no + 2)) mod 9190037) + 1`.  The velocity
  distribution is LAMMPS' (uniform components, zero momentum, scaled to T).
* **GPU arithmetic is f32**, coordinates in nm (ulp 5·10⁻⁴ nm at 5 µm, far below every
  length scale of the model); the CPU path is f64.  Force summation order on the GPU
  depends on atomics, so GPU runs are not bitwise reproducible.
* **A-step on squared distances**: a structure gets a row's bond iff `d² ≤ d_act²`
  (IGM: `d ≤ sqrt(sortdist[o])`); the same test without a square-root rounding.  On
  the GPU the activation distance is selected exactly from the f32 squares (no
  histogram approximation).  The assignment is made in the A-step from the same
  coordinates the M-step starts from (IGM re-reads them in the M-step): identical rows.
* **Neighbour search**: every excluded-volume pair within `r_i + r_j` at every step
  (cell grid); LAMMPS with `neigh_modify every 1 check yes` is also exact.  `max_neigh`
  has no counterpart.
* **`max_iterations`** is counted per σ (the spec's reading of `run_pipeline`,
  [unverified]); `force_last_iteration` defaults to `false` (the demo sets `true`;
  the benchmark scripts use the demo configuration).
* **Envelope violation ratio** uses `R̄` = mean semi-axis ([unverified] for ellipsoids).
* **Not implemented**: PGS (`method="pgs"`: TAD beads, fmax scaling, IMP
  `MinimumPairRestraint`, IMP annealing schedule), IGM's `inter_pooling` alternative of
  the old `utils/actdist.py`, DamID / FISH / SPRITE / nucleolus restraints (not part
  of the Hi-C deconvolution; imaging data are kept for validation), restart from an
  intermediate population, `.hss` export.
* **GPU memory limit**: the population is one resident buffer of `S · N · 16` bytes,
  which must fit one storage binding (4 GiB on NVIDIA Vulkan): e.g. 1 Mb (≈ 6,100
  beads) × 10,000 structures = 1 GB, 200 kb (≈ 30,900 beads) × 1,000 = 0.5 GB; 200 kb
  × 10,000 (4.9 GB) would need a host-resident population (not implemented).  The
  M-step runs in batches of structures sized from `UCHROM_IGM_GPU_BUDGET_GB`
  (default 16) and the binding limit.

### Checks

* Rust (`cargo test --release --features gpu`): finite-difference forces of every term
  (each term alone and together), constants of the soft potential / bond / envelope
  (incl. the ellipsoid normal), NVE energy conservation, thermostat ramp and velocity
  cap, CG descent, hand-computed A-step (p_now, clean, rank, d_act, per-structure
  assignment, p_last), forced-iteration rule, and **GPU vs CPU**: 20 MD steps from the
  same velocities (max difference 4·10⁻⁴ nm after moves of 900 nm), energies and
  violation counts identical, CG final energies to 10⁻⁶, A-step p identical for all
  5,221 pairs and `d_act²` to 2·10⁻⁷ (assignment identical except the rank-o element
  itself at exact ties of the f32 square).  Opt-in options: hand-computed GP pooling
  and `iterative_correction = false`, `bead_radius` / `occupancy_total_bp` radii,
  pinned initialisation (placement, same-chain interpolation, errors), per-kind
  violation breakdown and worst structure, every option changes the result, GPU vs CPU
  for the GP / no-correction A-step (p identical for all pairs) and for the intra /
  inter violation counts (identical), and the fixed-seed default run unchanged.
* Python (`tests/test_deconv_igm.py`): synthetic end-to-end (2 chromosomes × 50 bins,
  diploid, 200 structures; truth population from a designed matrix, its contact
  probabilities fitted again with another seed): Pearson 0.995 and mean |Δp| 0.02 over
  the pairs ≥ 0.05.  Synthetic data test correctness only; the real-data comparison
  with the original IGM is `benchmarks/bulk/sherlock/` (`igm_demo_*`).

## Validation (Stevens et al. 2017, 8 cells, 100 kb)

See the pull request / `paper/fig3/results/a_nucdyn_engine_*.json` and the
scripts in `benchmarks/fig3/a_nucdyn_engine_*.py`:

* `a_nucdyn_engine_crosscheck.py` — stage 1 restraint set vs the original
  (bitwise identical, both branches), and trajectories from identical
  inputs (≤ 2e-13 radii after 100 steps with the original's list schedule);
* `a_nucdyn_engine_run.py` / `a_nucdyn_engine_score.py` — all 8 cells,
  10 models, full schedule, CPU and GPU: ensemble RMSD vs Extended Data
  Table 2, RMSD / distance-matrix r vs the published GEO models,
  restraint violations;
* `a_nucdyn_engine_original_timing.py`, `a_nucdyn_engine_speed.py` — speed
  of the original, the old Taichi port and this engine.
