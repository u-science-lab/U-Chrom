# u-chrom-nucdyn

Native NucDynamics engine for [U-Chrom](../../README.md): single-cell Hi-C
genome structure calculation by simulated annealing of a particle model,
written in Rust with PyO3 bindings.

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
