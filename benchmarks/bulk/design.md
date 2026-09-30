# Population modelling of bulk Hi-C on the native engine — implementation and validation design

Goal: a new protocol of the native NucDynamics engine (`native/nucdyn`, Rust + wgpu) that
runs **population-based genome structure modelling** (PGS / IGM, Alber lab) — thousands of
diploid structures fitted jointly to one bulk contact-probability matrix by alternating
assignment (A-step) and per-structure annealing (M-step) — with all structures of a population
advanced together on one GPU. The algorithm to reproduce is specified from the original code in
`benchmarks/bulk/pgs_spec.md` (cited below as *spec §n*). The result is also a
**deconvolution** of population Hi-C into a population of single-structure hypotheses, and
§7 is designed to measure how much of that population is actually determined by the data.

Status: design. The data side and the benchmark (preprocessing, truths, forward model, metrics,
baselines, twins, Sherlock jobs) are implemented in `benchmarks/bulk/` (see its README); the engine
protocol is built on the engine branch.

---

## 1. Target: IGM, with a PGS variant only where cheap

Faithful mode = **IGM** (`github.com/alberlab/igm` @ `edbb331`, the Hi-C-only path of
`bin/igm-run`), for the reasons in spec §13: maintained code, plain per-structure harmonic
restraints, explicit MD script, fixed-size bins that map onto ChromData `bins`. The
`pgs2018` variant (TAD beads, fmax scaling, `MinimumPairRestraint` ambiguity, IMP annealing
schedule) is kept as a documented option for the pieces that fit the same kernels
(§2.4, §3.2); its shrinking-envelope choreography and IMP temperature scale are not planned.

Protocol name: `protocol="igm2022"` (default of the new entry point) and `protocol="pgs2018"`.

## 2. Mapping onto the existing engine

### 2.1 What the engine already has (read from `native/nucdyn/src`)

| piece | where | reuse for IGM |
|---|---|---|
| batched state, one buffer per quantity holding all models side by side; kernels dispatched over (particle workgroups, models) | `gpu/mod.rs:run_schedule`, `gpu/nucdyn.wgsl` | **yes** — "models" become the S structures (or a batch of them) |
| dense per-model cell grid rebuilt every step (count → scan → scatter), repulsion gathered per particle over the stencil, no neighbour list | `nucdyn.wgsl:cell_count_k, scan_local, scan_blocks, scatter, total_force` | **yes**, with per-particle radii and new pair forms (§2.2) |
| restraint forces computed per group then gathered per particle through an incidence CSR (`incs`) | `nucdyn.wgsl:restraints`, `total_force`; `dynamics.rs:System::from_arrays` | the gather pattern yes; the **shared** restraint list no (§2.3) |
| velocity Verlet with the NucDynamics thermostat term, per-model kinetic reductions (`mstate`) | `nucdyn.wgsl:motion, force_update, temp_reduce*` | integrator yes; thermostat needs a LAMMPS `temp/rescale` mode + `nve/limit` cap (§2.2) |
| per-temperature-step schedule, velocities re-drawn per step (PCG + Box–Muller, counter-based per (seed, model, step)) | `gpu/mod.rs:run_schedule`, `params.rs:anneal_schedule` | the schedule driver generalises to IGM stages (T ramp, evfactor, envelope factor) |
| CPU f64 reference path, deterministic chunked gathers, finite-difference force tests | `dynamics.rs` | **yes**: the CPU path is the reference for the new force terms, as for the 2017 protocol |
| ambiguous restraint groups (soft-min `(Σ d⁻⁴)^(−¼)`) | `dynamics.rs:group_force_2017`, `group_force`; WGSL `restraints` | **does not match either original**: IGM has no ambiguous restraints (each copy pair is an independent bond, spec §3.2 / §4.2); PGS uses IMP `MinimumPairRestraint` = sum of the `k` lowest scores (hard minimum, spec §3.1). A new group form `min_k` is needed for `pgs2018` only |

GPU limitations that must go: unit masses only (IGM masses are 1 — fine), **equal radii only**
(`run_schedule` returns an error otherwise; IGM radii differ at chromosome ends and PGS radii
differ everywhere), repulsion excluded for global `|i − j| ≤ 1` (`total_force`; IGM/PGS repel
*all* overlapping pairs, bonded ones included: LAMMPS `special_bonds lj/coul 1.0 1.0 1.0`, IMP
`ExcludedVolumeRestraint` over the whole chain), one restraint list for all models.

### 2.2 New force terms and dynamics (both CPU f64 and GPU f32)

| term | IGM form (spec §3.2) | implementation |
|---|---|---|
| per-particle radius | `r_i` from occupancy (spec §2.2) | store in `pos.w` (currently 0); cell size `2 r_max / stencil`; pair cutoff `r_i + r_j` |
| excluded volume | LAMMPS `pair soft`: `U = A(1 + cos(π d / r_c))`, `A = ev·((r_i + r_j)/π)²`, `r_c = r_i + r_j`, all pairs | new `RepulsionForm::SoftCos` (flag `repel_bonded = true`); `ev` per stage. `pgs2018`: `RepulsionForm::HarmonicOverlap` `½(r_i + r_j − d)²` |
| upper-bound bond | lammpgen `harmonic_upper_bound`: `U = k(d − d₀)²`, `F = −2k(d − d₀)` for `d > d₀` | new `RestraintForm::UpperHarmonicLammps` (restraint = (partner, d₀) with global k per class: polymer, Hi-C). `pgs2018`: `½k(s − s₀)²` on surface distance |
| nuclear envelope | `fix ellipsoidalenvelope`: `k² = Σ x²/(a − r_i)²`, if > 1: `t = (1 − 1/√k²)|x|`, `U = ½ k t²` along the normalised ellipsoid gradient | new per-particle term in `total_force` (semi-axes × stage `envelope_factor` in the uniform params). Sphere = equal axes. PGS: `½(|x| − R)²` on centres |
| thermostat | LAMMPS `temp/rescale 1 t0 t1 0.1 1`: target ramps linearly over the stage; if `|T − T_tgt| > 0.1` rescale fully to `T_tgt` each step; `T = Σ m v² / (3N − 3)` (k_B = 1, `units lj`) | new thermostat mode (`Thermostat::Rescale{window, fraction}`) in `force_update` / `temp_reduce`; the existing Berendsen-like term stays for the 2017 protocols |
| velocity cap | `fix nve/limit xmax`: `|v| ≤ xmax / dt` per particle, applied in both half-steps | new branch in `motion` / `force_update` |
| velocity creation | `velocity nonfixed create t0 seed` at every stage (LAMMPS default: *uniform* distribution, zero net momentum, scaled to t0) | existing `vel_init` (Gaussian) + momentum removal; the distribution differs (deliberate, §4) |
| CG polish | `min_style cg; minimize 1e-4 1e-6 500 500` (Polak–Ribière, LAMMPS quadratic/backtracking line search) | **new**: batched nonlinear CG, one per structure, per-structure scalars (β, step, energies, convergence flag) in `mstate`; energy kernel needed (the engine computes forces only). Same stopping rules (relative energy change `etol`, force-norm `ftol`, iteration / evaluation caps) |
| annealing driver | `custom_annealing_protocol`: stages (mdsteps, t0→t1, evfactor, envelope_factor), optional `relax` block before each stage, then CG | generalise `run_schedule` to a list of stages; one submission per stage chunk as now |

Units on the GPU: positions divided by the mean bead radius `r̄` (so O(1) numbers in f32, as
release_1.3 runs in bead units); energies and temperatures are LAMMPS-reduced already.

### 2.3 Per-structure restraint lists (the main new data structure)

In IGM every structure has its own Hi-C restraint set (spec §4.2), so the shared
`rest` / `incs` buffers become **per-structure CSR**:

* `bond_off[s][i]` (u32, n + 1 per structure): start of bead *i*'s incident bonds;
* `bond[s][…]` (vec2: partner u32, `d₀` f32 bits; class bit for k): each restraint stored at
  **both** endpoints, so the force is gathered per particle with no atomics and no
  `rest_f` buffer (for single bonds the pair force is cheap to evaluate twice);
* polymer bonds identical in every structure → kept in the shared incidence (`incs`), only
  Hi-C (and later DamID / FISH / SPRITE) bonds in the per-structure CSR;
* `pgs2018` `min_k` groups (≤ 4 pairs, k ∈ {1, 2}) keep the existing two-phase pattern
  (group kernel writes per-member forces, particles gather) with a per-structure group list.

The CSR is **built on the GPU by the A-step** (§2.5) in two passes (count per (structure,
bead) → exclusive scan per structure → fill) and never leaves the device. Offsets per structure
are absolute into one big buffer; a batch (§2.6) is a contiguous range of structures.

### 2.4 Diploid layout

Bead order = alabtools `make_diploid`: haploid index (chromosomes in genome order) for copy 0,
then again for copy 1; `male` = autosomes ×2, X, Y ×1 (`make_multiploid`). The engine gets a
`copy_index` table (haploid locus → 1 or 2 bead ids) and a chromosome-copy id per bead
(polymer bonds only within the same chain; LAMMPS `mol_id`). ChromData mapping: every bead is a
spot whose `bin_id` is the haploid bin; the copy is a trace (§5).

Ambiguity (which homolog pair carries a contact) is not a restraint property in IGM: the
A-step pools the copy combinations and every structure keeps the combinations that are
already within the activation distance (spec §4.2). So **no ambiguous restraint is needed for
the faithful mode**. The NucDynamics soft-min form is *not* reused for it (it would be a
different model: a soft-min over copies lets one restraint move to the closer homolog during
the run; IGM fixes the assignment for the whole M-step).

### 2.5 A-step on the GPU

Per candidate haploid pair (i, j) with `f_ij ≥ σ` (intra or inter threshold), IGM needs the
`n_c·S` centre distances of the relevant copy combinations (`n_c` = 2 intra, 4 inter for
diploid), `p_now = #(d ≤ 2(r_i + r_j)) / (n_c S)`, the order statistic of rank
`o = min(n_c S − 1, round(n_c p S))` with `p = clean(f, clean(p_now, p_last))`, and then the
per-structure test `d_s ≤ d_act` (spec §4.2). Plan:

1. **Candidate list** on the host from the (sparse, upper-triangular) probability matrix:
   `(i, j, f, p_last)` sorted by (i, j); `p_last` joined from the previous A-step's output.
2. **Population coordinates** resident in a bead-major buffer `X[bead][s]` (the `.hss` layout),
   written back after every M-step batch; a pair reads two contiguous rows of S vec3.
3. **Pass 1 (count + histogram)**: one workgroup per candidate pair (or per tile of pairs
   sharing bead *i*), threads over structures × combinations: count `d ≤ r_c` (→ `p_now`),
   and a 2,048-bin histogram of `log d` in workgroup memory. Compute `p` and `o`, locate the
   bin containing rank `o`.
4. **Pass 2 (exact select)**: re-scan, collect the values inside that bin (typically ≪ S) into
   workgroup memory, select rank `o − count_below` exactly (bitonic sort of the small set).
   Result `d_act` is **exactly** IGM's `sqrt(sortdist[o])` computed in f32 from f32
   coordinates (IGM stores coordinates as float32 and sorts float64 squares; ties / rounding
   differences only at the last bit).
5. **Pass 3 (assignment)**: per (pair, combination, structure) `d_s ≤ d_act` →
   `atomicAdd` into `cnt[s][bead_a]` and `cnt[s][bead_b]` (pass 3a), per-structure scan (3b),
   fill `bond[s]` with an atomic cursor (3c). Order inside a bead's list is arbitrary (forces
   are sums; for bitwise reproducibility on the CPU path, sort by partner).
6. Output per pair `(i, j, d_act, p)` kept as the next `p_last` and optionally written
   (the IGM `actdist.hdf5` columns) for the cross-check (§7d).

Cost model: `n_pairs × n_c × S` distance evaluations per pass (two passes + assignment). From
the IGM demo input (spec §1.3, 2 Mb): 1,702 pairs at σ = 1, 44,944 at σ = 0.02, **614,140 at
σ = 0.01** (inter block). At 200 kb the count at the last σ is O(10⁷–10⁸) [to be measured on
the first real input]; 5·10⁷ pairs × 4 × 10⁴ structures = 2·10¹² distances per pass — bandwidth
bound, tiled by bead so each coordinate row is read once per tile; estimate 1–5 min per A-step
on an H100 [estimate, M4 measures it]. IGM's A-step is one CPU task per 1,000 pairs.

### 2.6 Memory on an 80 GB H100 and batching

Per structure and bead (f32): dynamic state `pos, vel, acc, frc, spos` 5 × 16 B + `pc` 8 B +
cell grid (2 × 4 B × 4 cells) 32 B = 120 B; CG vectors (g, g_prev, d) +48 B; CSR offsets 4 B;
Hi-C bonds 16 B per restraint (8 B at each end) × h restraints per bead. With h = 15 (the
demo's restrained probability mass per haploid bin at σ = 0.01 is 5.2 intra + 8.7 inter;
PGS scaled its domain matrix to an average row sum of 25) → ≈ 410 B per bead-structure.

| model | beads N (diploid) | S | bytes (h = 15) | fits in one batch? |
|---|---|---|---|---|
| Su 2020 chr21, 50 kb, 1 chain | 651 | 10,000 | 2.7 GB | yes |
| Su 2020 genome-scale at 3 Mb bins | ≈ 2,060 | 10,000 | 8.5 GB | yes |
| Takei 2021 mESC 1 Mb | ≈ 4,900 | 10,000 | 20 GB | yes |
| human 1 Mb | ≈ 6,200 | 10,000 | 25 GB | yes |
| human 200 kb (IGM HFF) | 29,838 | 10,000 | 122 GB | no → 2–3 batches of 3,500–5,000 |
| human 200 kb | 29,838 | 1,000 | 12 GB | yes |

Plus the resident population `X` (12 B × N × S: 3.6 GB at 200 kb × 10k) and the A-step
candidate list (24 B per pair: ≤ 2.4 GB for 10⁸ pairs). Batching is trivial because
structures are independent inside an M-step: the M-step loops over batches of structures
(buffers sized for the largest batch), each batch reads its start coordinates from `X` and
writes them back; the A-step always sees the full population. If h at 200 kb is larger than
15, the batch size shrinks proportionally (the engine computes it from the counted CSR size).

### 2.7 Throughput estimate

Measured with the existing engine on an H100 (`paper/fig3/results/a_nucdyn_speed_gpu_h100.json`):
64 models × 25,724 particles × 50,000 steps in 49.6 s ≈ **1.7·10⁹ particle-steps / s** at
saturation (below ~10⁶ particle-models the run is launch-bound: ≈ 4.5 s per 50,000 steps).
IGM M-step ≈ 45,000 MD steps + ≤ 500 CG iterations (spec §6.2). Assuming the new terms cost
1.5–3× the NucDynamics step (per-structure CSR gather, soft-cos with more neighbours at 40 %
occupancy, envelope):

| job | particle-steps per M-step | per M-step | full run (≈ 15–25 M-steps) | original |
|---|---|---|---|---|
| human 200 kb, S = 1,000 | 1.3·10¹² | 13–40 min | 4–15 GPU-h | IGM README: 250 cores × 10–15 h |
| human 200 kb, S = 10,000 | 1.3·10¹³ | 2–6 h | 2–6 GPU-days | (≈ 25,000–37,000 CPU-h by scaling) |
| human 1 Mb, S = 10,000 | 2.8·10¹² | 0.5–1.5 h | 10–35 GPU-h | — |
| demo 2 Mb (3,116 beads), S = 1,000 | 1.4·10¹¹ | 1.5–4 min | < 2 GPU-h | demo: "a few hours" serial for S = 100 |
| Su chr21, S = 5,000 | 1.5·10¹¹ | 1.5–4 min | < 2 GPU-h | — |

These are estimates for planning; M3/M4 replace them with measurements.

## 3. Faithful mode vs deliberate deviations

### 3.1 Faithful (`protocol="igm2022"`, defaults = IGM schema + demo annealing protocol)

Same as IGM: radii from occupancy (spec §2.2), contact = `d ≤ 2(r_i + r_j)`, polymer bonds
`2(r_i + r_{i+1})` (`simple`) or the `hic` form, Hi-C bonds `k = 1`, envelope `k = 1`, random
territory initialisation + relaxation, the A-step rule of spec §4.2 **including** IGM's pooling
of 4 inter combinations and `p_last` from the cleaned p, per-copy independent bonds, the σ
lists and the min / max iteration logic of `bin/igm-run` (spec §4.3), violations as
`(d − d₀)/d₀ > tol` over monitored restraints (spec §5), the annealing stages + CG.

### 3.2 Deviations (each justified; the non-default ones are flags)

| deviation | why | default? |
|---|---|---|
| f32 on the GPU (positions in bead units) | WGSL has no f64; the CPU path stays f64 as the reference | GPU yes |
| RNG: counter-based per (seed, structure, stage) instead of LAMMPS' `velocity create` + `seed · struct_id · …` | batched streams; LAMMPS' uniform velocity distribution replaced by Gaussian (same temperature; the distribution only matters for the first steps after each rescale) | yes |
| exact repulsion pairs every step (cell grid) | LAMMPS with `neigh_modify every 1 check yes` and skin `r_max` is also exact; nothing lost | yes |
| CG: our batched Polak–Ribière with backtracking line search | LAMMPS' `linesearch quadratic` is not specified to the bit; stopping rules kept | yes |
| A-step in one process on the whole population, restraints assigned inside the A-step | IGM assigns in the M-step from the same coordinates → identical result; avoids writing activation files | yes |
| `.hss` exchange through the file system replaced by device buffers | performance only; `.hss` import / export for interop (§5) | yes |
| seeds and restart | a run is resumable per (σ, iteration) from the zarr snapshot (§5) | yes |
| `ActivationDistance` inter pooling: `n_c = 2` (PGS / old IGM helper) | spec §12: the two code generations disagree; offered as `inter_pooling="pgs"` to test the sensitivity | no |
| `pgs2018` restraint pieces (TAD beads, fmax scaling, `min_k` groups, surface-distance bounds) | PGS reference; no IMP annealing schedule | no |
| higher-order benchmarking hooks (keep every intermediate population) | for §7 only | no |

Explicitly **not** planned: IMP's nominal-temperature annealing and PGS's shrinking envelope;
DamID / FISH / SPRITE restraints (spec lists their forms; the kernels generalise — lower bounds,
inverted envelope, dynamic centroid particles — but they are not part of the Hi-C deconvolution
question and FISH restraints would leak the validation data).

## 4. Correctness checks during development (not the validation)

* CPU f64: finite-difference forces of every new term; energy conservation with the thermostat
  off; thread-count independence (existing tests extended).
* GPU vs CPU from identical coordinates and velocities (as `gpu_matches_cpu_for_short_runs`).
* **LAMMPS force cross-check** (Sherlock, lammpgen built from `8a1a4cb`): write the `.data`
  / `.lam` of one IGM structure with IGM's own `create_lammps_data` / `create_lammps_script`,
  replace the protocol by `run 0` + `dump … fx fy fz`, compare per-particle forces and the
  energy components (`epair`, `ebond`, `f_envelope0`) with the engine at the same coordinates
  (target ≤ 1e-10 relative on CPU f64).
* **A-step cross-check**: IGM's `get_actdist` (imported from the cloned repo, a few seconds
  of Python on a small `.hss`) vs the engine on the same population and `p_last`: identical
  `(i, j, p)` rows, `d_act` to f32 rounding; identical per-structure restraint counts.
* Short trajectory from identical start and velocities vs LAMMPS with `temp/rescale` (window
  0.1) and `nve/limit`: agreement to ~1e-6 relative over 100 steps (CPU f64), divergence after
  that is chaotic and expected.

## 5. API and outputs

### 5.1 Native (array level; `uchrom_nucdyn`)

```python
res = uchrom_nucdyn.calc_population_structures(
    chrom, start, end,                 # haploid bins (arrays, genome order)
    prob_i, prob_j, prob_v,            # upper-triangular probability matrix (COO, haploid indices)
    ploidy="diploid",                  # "haploid" | "diploid" | "male" | {chrom: copies}
    n_structures=10_000,
    protocol="igm2022",                # or "pgs2018"
    params=None,                       # dict: occupancy, nucleus (sphere R | ellipsoid a,b,c), sigma lists,
                                       #  annealing stages, k's, tolerances, min/max iterations, batch size
    device="auto", seed=0,
    on_iteration=None,                 # callback(sigma, iteration, coords_view, stats) -> None (streaming)
)
# -> dict(coords=(S, N, 3) float32 or None when streamed, bead_bin=(N,), bead_copy=(N,),
#         radii=(N,), stats=list of per-(sigma, iteration) dicts, actdist=last (i, j, d, p) table)
```

### 5.2 U-Chrom (`uchrom.recon.bulk.pgs`)

```python
from uchrom.recon.bulk.pgs import reconstruct_population, PopulationParams

pop = reconstruct_population(
    hic,                      # path (.cool/.mcool[::resolutions/N], .hic, .hcs) or a DataFrame / matrix
    *,
    resolution=1_000_000, chroms=None, ploidy="diploid",
    probabilities="igm",      # how counts become probabilities: "given" (already probabilities),
                              #  "igm" (balance + neighbour scaling, see open question 2), "pgs2018" (fmax + TAD file)
    params=PopulationParams(n_structures=10_000, protocol="igm2022"),
    device="auto", seed=0,
    out="pop.chromdata.zarr", # streaming writer; None = in memory (small populations only)
    key_added="population.igm",
) -> ChromData | BackedChromData
```

This mirrors `uchrom.recon.sc.nucdyn.reconstruct_nucdyn` (input is a contact file, output a new
ChromData) rather than the `fn(cd, *, …)` form, because the input is a Hi-C matrix, not a
ChromData; the keyword-only arguments, `params=<*Params>`, `device="auto"` and `key_added`
follow `uchrom/core/convention.py`. A flat alias `uchrom.tl.reconstruct_population` is added.

### 5.3 ChromData layout of a population — structures as **cells**

* `bins`: the haploid bins of the model (one row per locus); `bin_tracks["input_prob_rowsum"]`,
  radii in `bin_tracks["radius_nm"]`.
* each structure is a **cell** (`cell_id = "s00000" …`), each chromosome copy a **trace**
  (`trace_id = "s00000:chr1:0"`), each bead a **spot** with `bin_id` → both homologs point to the
  same bin; `coords` in nm.
* `cells`: `violation_score`, per-class violation counts, energies, number of Hi-C restraints,
  batch / seed; `traces`: `chrom`, `copy`.
* `uns["population_model"]`: protocol, all parameters, σ lists as run, iterations per σ,
  nucleus geometry, input provenance; `cd.results.set("population.igm", <activation table>,
  kind=…, function="uchrom.recon.bulk.pgs.reconstruct_population", params=…, inputs=…)`.

Why cells and not `layers`: the NucDynamics wrapper stores the models of **one** cell as
`layers` (alternative coordinates of the same spots). Population structures are different
hypothetical cells; as cells they get every per-cell tool for free (`get_cell`, `iter_cells`,
`cellm` embeddings, per-cell violations in `cells`, comparison with imaged cells that are also
cells), and the zarr store partitions coordinates by chromosome and sorts by cell, so
per-structure and per-chromosome reads are cheap. `layers` would require `n_spots = N` and
10,000 layers of (N, 3), which the format keeps as dense spot-aligned arrays and cannot
partition by structure.

Memory: S × N spots = 6.2·10⁷ at 1 Mb × 10k (≈ 2.5 GB in memory with categorical keys, fine),
3·10⁸ at 200 kb × 10k (≈ 12 GB of spots + 7 GB of float64 coords — too much for memory).
So the entry point streams: `ChromData.writer(out)` receives one batch of structures at a
time (cell-sorted, as the writer expects) at the end of the run, and returns
`ChromData.read(out, backed=True)`. Intermediate populations (per σ / iteration) are optional
snapshots (`keep_intermediate="last_per_sigma" | "all" | None`); `.hss` export
(`uchrom.io.write_hss`) and import (`read_hss`) for interop with alabtools / IGM reports and
for starting from an IGM population.

## 6. Datasets

| dataset | use | catalog status |
|---|---|---|
| Su 2020 IMR90 chr21, 651 × 50 kb (`su2020_imr90/chromosome21.tsv`, Zenodo 3928890) | (b) truth, (c) imaging | **catalogued** (`--su2020_chr21`) |
| Su 2020 `Hi-C_contacts_chromosome21.tsv` (Rao 2014 summed into the 651 loci) | (c) input | **catalogued** |
| Su 2020 **genome-scale** DNA-MERFISH `genomic-scale.tsv` (200,285,524 B; CC-BY-4.0) | (b) diploid genome-wide truth, (c) imaging | **catalogued** (`--su2020_genome`) |
| Su 2020 `Hi-C_contacts_genome-scale.tsv` (2,846,153 B; Rao 2014 summed into 500 kb bins centred on the 1,041 loci) | (c) input | **catalogued, checked in** |
| Su 2020 `genomic-scale-with transcription and nuclear bodies.tsv` (654,711,554 B) | optional (speckle / nucleolus distances) | not catalogued; opt-in |
| Takei 2021 mESC 1 Mb (`4DNFIFLJGGNR.csv`, 2,460 loci, homolog split by `truth.split_homologs`) | (b), (c) | **catalogued** (`--takei2021_1mb`) |
| Takei 2021 mESC 25 kb (`4DNFIHF3JCBY.csv`, homolog-resolved) | (c) local windows | catalogued |
| Bonev 2017 mESC Hi-C (4DN `4DNFIC21MG3U` mcool, 12.6 GB; range-read the 1 Mb level) | (c) input | **catalogued** (`--bonev2017_mesc_4dn`, Sherlock; recipe `real_inputs.py` / `sherlock/build_real.sbatch`) |
| Rao 2014 IMR90 genome-wide (GEO GSE63525 `.hic`, hg19) or 4DN `4DNFIR1JDZH7` (GRCh38 mcool, 4.6 GB) | (c) input at 1 Mb / 500 kb | **catalogued**: 4DN GRCh38 mcool (`--rao2014_imr90_4dn`, Sherlock) → 20 kb → IGM inputs (`real_inputs.py`); GEO `.hic` range-read for the KR check |
| IGM demo `WTC11_HiC_2Mb.hcs` (3,908,025 B, GPL-3 repo) | (d) same-input comparison, smoke tests | not catalogued — < 10 MB but GPL-3 data file; download from the IGM repository at `edbb331` instead of checking in (open question 6) |

What Su 2020 actually provides genome-wide (verified by streaming `genomic-scale.tsv`
from Zenodo 3928890 and reading its `README_August 2020.txt`): DNA-MERFISH of **1,041 loci**
(each 100 kb, `chr1:2,950,000–3,050,000`, spaced ≈ 3 Mb) on **all 22 autosomes and chrX**,
**1,787 IMR90 cells** from 3 experiments (431 / 917 / 439), every row labelled with
**homolog number 1 / 2** (1,860,267 rows each — both homologs resolved per cell), 16 % of
positions missing (NaN), plus a per-locus *distance to the nuclear lamina* column (hg38).
Two more genome-scale files: 2 replicates with transcription state and distances to lamina,
nearest speckle and nucleolus (`genomic-scale-with transcription and nuclear bodies.tsv`),
and 2 replicates after α-amanitin. The authors' Rao 2014 Hi-C binned into 500 kb bins centred
on the imaged loci is included (`Hi-C_contacts_genome-scale.tsv`). This is a better diploid,
genome-wide imaging truth than the Takei 1 Mb set (homologs resolved by the experiment, not by
the `split_homologs` heuristic, and 9× the cells).

## 7. Validation plan (real data first; every metric fixed before modelling)

Common definitions:
* **Scale**: model coordinates are in nm set by occupancy and nuclear size; imaging in nm.
  Every comparison is reported raw and after **one global scale factor** (least squares on the
  median pairwise distances of all loci pairs); no per-pair or per-chromosome fitting.
* **Locus mapping**: an imaged locus maps to the model bead containing its midpoint; a
  homolog-resolved truth maps copy 1 / 2 to bead copies by best global assignment per
  structure and chromosome (the model's copy labels are arbitrary).
* **Seeds**: every population is run with 3 seeds; seed-to-seed spread is the noise floor of
  every metric (and the identifiability probe, §7(b)).

### (a) Reproducing the input (as the papers do)

Population contact frequency `P_model(i,j)` with IGM's contact definition, summed over copies
(`sumCopies`), vs the input: Pearson / Spearman over restrained (f ≥ σ_final) and non-restrained
pairs, intra per chromosome and inter (as `igm/report/hic.py`), per-genomic-distance correlation
and P(s) curves, and the final violation score. Reference numbers: Tjong 2016 row-based
r = 0.956 (inter 0.75), Boninsegna 2022 r = 0.98. This is a fit statistic (the input is the
target), not evidence of deconvolution.

### (b) Deconvolution benchmark with imaging truth

Truth populations (all from `benchmarks/screcon/truth.py` readers, extended for Su
genome-scale): **Su chr21** (651 × 50 kb, one chain per trace; the ≥ 95 %-detection copies,
4,084 eligible), **Su genome-scale** (1,041 loci, 1,787 diploid cells), **Takei 1 Mb** (2,460
loci, 201 cells, homolog split heuristic, flagged). Missing loci interpolated for the forward
model only (screcon convention), scoring on measured loci only.

Forward model: the population Hi-C is the **sum over truth cells of per-cell contacts**, reusing
`benchmarks/screcon/simulate.py`: (i) expected contact probability
`f_ij = mean_cells Σ_copies kernel(d_ij)` (infinite depth — isolates deconvolution from sampling
noise), with the `step` kernel at `r_c` = the model's contact distance (so the input is exactly
what IGM's contact definition would measure on the truth) and with the `gauss` kernel (a
mismatched, smoother kernel, as real cross-linking is); (ii) finite depth — `simulate_reads`
per cell (multinomial / Poisson, eps noise), summed, then the probability preprocessing of the
pipeline (tests preprocessing and noise). Model bins = truth loci (Su chr21: 50 kb chain;
genome-scale: 3 Mb bins centred on the loci so every bin is imaged; Takei: 1 Mb). Model
nucleus: sphere with the truth's median nuclear radius (estimated from the spot cloud),
occupancy default 0.2 — reported, not tuned to the truth. Su chr21 is a single-chromosome
model (one chain in a sphere of the chromosome-territory volume) — a deliberate reduction,
labelled as such.

Metrics (reconstructed population R vs truth T; all on measured loci):
1. **Per-pair distance distributions**: for every loci pair, 1-Wasserstein distance between
   the R and T distance samples (in units of the truth's median consecutive-locus distance)
   and the KS statistic; reported as the median and IQR over pairs, by genomic-separation band,
   intra vs inter. Medians / means alone are also reported but are not the headline.
2. **Contact frequencies at held-out thresholds**: P(d < r) for r ∈ {0.5, 2} × r_c, which the
   model did not fit.
3. **Three-body co-occurrence**: for triplets sampled stratified by separation (and for
   triplets with all three pairwise probabilities above σ_final), the fraction of structures
   with all three pairs in contact, and the "excess" `P(ijk) − P(ij)P(jk)P(ik)/(…)` relative to
   an independence expectation; compared R vs T (absolute error, correlation over triplets).
   Su chr21 and Su genome-scale both allow this (the Su paper itself reports multi-way
   co-occurrence).
4. **Radial position**: per-locus distribution of distance to the population centre / to the
   envelope (Su genome-scale: vs its lamina distances; Wasserstein per locus).
5. **Subpopulation structure**: (i) cluster T (k-means on log-distance features, k chosen on T
   by silhouette, fixed before looking at R), assign R structures to T clusters by nearest
   centroid, compare cluster proportions (total variation); (ii) **classifier two-sample test**:
   a gradient-boosted classifier on log-distance features trained to tell R from T structures
   (cross-validated AUC; 0.5 = indistinguishable).
6. **Nearest-true-cell RMSD** (similarity superposition, mirror allowed, as `screcon/metrics.py`):
   for every R structure the RMSD to its nearest T cell, divided by Rg(T); and the reverse
   (coverage: every T cell to its nearest R structure). Reference: the same statistic for a
   held-out half of the truth cells against the other half (the "perfect population" of equal
   size), and for each baseline.

Baselines, all given **the same input** unless marked:
* **HIPPS** (Hi-C → ⟨r_ij⟩ = Λ p^(−1/4) → maximum-entropy Gaussian ensemble; code already used
  in `benchmarks/fig3/c_hipps_wang2016.py`) — structure-free, pairwise-only, same input;
* **Gaussian fitted to the pairwise contact frequencies**: the maxent Gaussian whose
  per-pair contact probabilities (Maxwell CDF at r_c) match f_ij — pairwise-only by
  construction, same input;
* **Oracle pairwise (DIMES on the truth's mean squared distances**, `benchmarks/fig3/b_dimes.py`,
  marked "oracle"): the best a pairwise-only Gaussian can do with the *true* second moments —
  the ceiling of pairwise-only information;
* **single consensus structures**: U-Chrom MDS (`uchrom.recon.bulk.mds`) and miniMDS on the same
  matrix, replicated S times (+ small noise) — "one structure" baseline;
* **random confined polymer** (floor) and the **held-out truth half** (ceiling).

Identifiability — pairwise data do not determine higher-order statistics; the benchmark measures
how much of R's higher-order structure comes from the data:
* the **gain over pairwise-only**: metrics 3, 5, 6 of R vs the Gaussian / HIPPS baselines, and vs
  the oracle-pairwise DIMES. If R does not beat the oracle on three-body and cluster metrics,
  the A/M procedure adds no higher-order information beyond pairwise statistics (its polymer
  and excluded-volume prior may still help relative to a Gaussian).
* a **twin-truth test**: build a second truth with (nearly) the same pairwise contact map but
  different higher-order statistics — the DIMES ensemble sampled from the truth's second
  moments, or the truth with chains of different cells recombined at domain boundaries — run
  the same pipeline on both inputs; if the two reconstructions have the same three-body /
  cluster statistics while the truths differ, those statistics are prior-driven. The difference
  |metric(R₁) − metric(R₂)| vs |metric(T₁) − metric(T₂)| is the identifiable fraction.
* **seed and S dependence**: higher-order metrics across 3 seeds and S ∈ {1,000, 5,000, 10,000}
  at equal fit quality (a); a statistic that varies across seeds at equal fit is not determined
  by the data.

### (c) Real bulk Hi-C vs independent imaging of the same cell type

* **IMR90**: Rao 2014 IMR90 Hi-C (the authors' 500 kb loci-centred sums; and a genome-wide 1 Mb
  build from GSE63525 for a whole-genome model) → population at the Su genome-scale loci
  (3 Mb bins centred on them, or 1 Mb bins) → compare with Su genome-scale imaging (1,787 cells):
  metrics (b)1, 3, 4 (lamina distance), 5, 6; inter-chromosomal proximity per chromosome pair,
  chromosome radial ordering, A/B spatial segregation (compartments from the Hi-C, distances
  from imaging). chr21 at 50 kb: Rao 50 kb sums (`Hi-C_contacts_chromosome21.tsv`) → single-
  chromosome model → Su chr21 (thousands of copies). Depth caveat: Rao's genome-wide inter
  signal at 500 kb–1 Mb is sparse; report the fraction of pairs above σ_final.
* **mESC**: Bonev 2017 1 Mb (range read of the 4DN mcool) → population → Takei 2021 1 Mb (201
  cells, homolog-split heuristic flagged) and the 25 kb windows (local check from a 25 kb
  single-window model).
* Same baselines as (b) (the oracle is now the imaging's own second moments).
* This is the only test that combines real Hi-C noise, real preprocessing and cell-type
  heterogeneity; expect it to be worse than (b) and report it as is.

### (d) The original IGM on the same input (Sherlock)

* Build IGM (Python 3.6 conda env, alabtools, lammpgen `make serial`) in `$SCRATCH`; runs:
  (1) the shipped demo (WTC11 2 Mb, S = 100, and S = 1,000); (2) the (b) Su genome-scale
  simulated input at S = 1,000. Same σ lists, protocol and seeds-by-structure where possible.
* Compare: wall time and CPU-h (IGM) vs GPU-h (ours); agreement of the two populations on
  (a) and on the (b) metrics, **relative to each code's own seed-to-seed spread**
  (a population from IGM and one from us should differ no more than two IGM seeds do);
  per-(σ, iteration) violation scores and restraint counts per bead; the A-step cross-check of §4.
* "Single consensus structure" baselines on the same inputs: U-Chrom MDS and miniMDS.
* Job sizes: IGM demo S = 1,000 at 2 Mb ≈ 200 cores × a few hours; Su genome-scale S = 1,000 at
  3 Mb similar; ≤ ~3,000 CPU-h in total. Ours: < 1 H100-hour each.

### Cost summary (planning)

| part | compute |
|---|---|
| (a) + (b) Su chr21, Su genome-scale, Takei 1 Mb; 3 seeds × S ∈ {1k, 5k, 10k} × 2 kernels × 2 depths + twin truths | ≈ 100 GPU-h (mostly S = 10k) |
| (c) IMR90 1 Mb genome-wide S = 10k × 3 seeds, chr21 50 kb, mESC 1 Mb | ≈ 50–100 GPU-h |
| (d) IGM reference runs | ≤ 3,000 CPU-h + a few GPU-h |
| scoring (Wasserstein over all pairs, triplets, C2ST) | CPU, ≈ 200 CPU-h |

## 8. Milestones

| # | content | effort |
|---|---|---|
| M0 | this spec + design | done |
| M1 | CPU f64 IGM kernel: per-particle radii, soft-cos repulsion incl. bonded pairs, LAMMPS upper-bound bonds, ellipsoidal envelope, `temp/rescale` + `nve/limit`, annealing stages, CG; finite-difference tests; LAMMPS `run 0` force cross-check on Sherlock | 5–7 d |
| M2 | A-step on CPU (exact selection, per-structure assignment), `p_last` bookkeeping, σ / iteration driver of `igm-run`, violation scoring; cross-check vs IGM `get_actdist` | 3–4 d |
| M3 | GPU: radii in `pos.w`, new pair / bond / envelope terms, per-structure CSR, thermostat modes, batched CG, stage driver; GPU vs CPU tests | 6–9 d |
| M4 | GPU A-step (gather, two-pass exact select, CSR build), batching over structures, resident population, `.hss` / zarr I/O, Python API, streaming writer | 5–7 d |
| M5 | (a) + (d): IGM demo and Su genome-scale simulated input vs original IGM on Sherlock; speed table | 3–5 d (+ queue time) |
| M6 | (b) deconvolution benchmark incl. baselines, twin truths, seeds / S sweep; catalog rows for Su genome-scale | 6–8 d |
| M7 | (c) real data (Rao IMR90, Bonev mESC builds + catalog), write-up | 5–7 d |
| — | `pgs2018` variant (fmax / TAD preprocessing, `min_k` groups) if wanted | +3–4 d |

Total ≈ 7–9 weeks of development for the IGM path.

## 9. Risks

* **Identifiability** (the scientific risk): the A/M procedure fits pairwise contact frequencies;
  three-body statistics, cluster structure and "which structures exist" are not determined by
  them. The benchmark quantifies this (§7(b) gain over pairwise-only, twin truths, seed spread);
  it may well show that most higher-order structure is prior-driven. That is a result, and
  should be reported as such.
* **Input semantics**: IGM's Hi-C → probability preprocessing is not in the code (spec §1.2);
  the scale of `f` (what "probability 1" means) sets how many restraints exist and interacts
  with the contact distance. For simulated inputs we control it; for real data we must choose
  and document a rule (open question 2) and test sensitivity.
* **Inter-pair pooling** differs between PGS and IGM (spec §12); a factor 2 in the effective
  inter probabilities. Sensitivity run planned (`inter_pooling`).
* **Convergence behaviour**: IGM stops at `max_iterations` without failing; populations at the last
  σ may carry many violations. We report violation scores per σ and never hide a non-converged run.
* **Faithfulness of CG and velocity statistics** (§3.2): small, but trajectories will not match
  LAMMPS bitwise; the comparison is statistical (§7(d)).
* **Memory at 200 kb × 10k** requires batching; restraint density at 200 kb is unknown until the
  first input is built (the batch size adapts).
* **Scale / nucleus choice** for comparisons with imaging: one global scale factor, reported;
  nuclear shape (IMR90 is flat) is not in the sphere model — use an ellipsoid from the imaging
  if the sphere is clearly wrong (a documented, pre-registered choice).
* **Licensing**: PGS / IGM / alabtools are GPL-3, lammpgen GPL-2, the engine crate LGPL-3. The
  new protocol must be a clean re-implementation from the specification (as for NucDynamics),
  with no code copied, and cite Tjong 2016, Hua 2018, Boninsegna 2022.

## 10. Open questions for the user

1. Faithful target: IGM (2022) as proposed, with PGS only as a variant — or is exact PGS
   (Tjong 2016, TAD beads, IMP schedule) needed for a specific comparison?
2. Real-data probability preprocessing: IGM's SI procedure is not in the code. Options:
   (a) reconstruct it from the Nat Methods SI (needs the PDF), (b) PGS's fmax scaling with
   fixed-size bins (`alabtools.iterativeScaling`), (c) balance + scale so that the first
   off-diagonal is 1 (what the IGM demo `.hcs` looks like). Which should be the default?
3. Default population size and resolution for real runs: S = 10,000 at 1 Mb (fits one H100),
   or S = 1,000 at 200 kb as in Boninsegna 2022?
4. Output: structures as ChromData **cells** (proposed) — agreed? Keep intermediate populations
   by default or only the final one?
5. Sherlock budget for the original IGM reference runs (≤ ~3,000 CPU-h) — OK?
6. The IGM demo `.hcs` (3.9 MB, GPL-3 repository): download on demand (proposed) or check in?
   The Su genome-scale Hi-C sums (2.8 MB, CC-BY-4.0) would be checked in.
7. Module name: `uchrom.recon.bulk.pgs` (method family) or `uchrom.recon.bulk.igm`?
8. Should DamID / FISH / SPRITE restraints be on the roadmap at all (they turn the method into
   data integration and would consume the imaging needed for validation)?
