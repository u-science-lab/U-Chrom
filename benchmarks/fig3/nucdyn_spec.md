# NucDynamics (Stevens et al. 2017) — reference algorithm specification

This is an implementation-independent specification of the structure calculation in the
**original NucDynamics code as it was in 2017**, written line by line from its source, as the
correctness target for a new engine (and for checking any port). Everything below describes what
the code does, including its quirks; where the paper (Stevens et al. 2017, *Nature* 544:59,
doi:10.1038/nature21429, Supplementary Methods "3D genome structure calculations") says something
different, that is listed separately in §12.

**Source.** `github.com/tjs23/nuc_dynamics`, branch `master` (last change 2020-11-13, "Add LGPLv3";
the algorithm is unchanged since 2017-10). Files: `nuc_dynamics.py` (997 lines,
md5 `f75cf859115ecb1cc578c27adb6ccf69`) and `dyn_util.pyx` (1154 lines, md5
`2fb2073ff08910b80e401eddeccefdf1`). Citations below are `file:function`. The default branch of
that repository (`release_1.3`, 2021–22) is a *different* model (all distances scaled by a bead
size, restraint weights, model reduction, 3-D disambiguation — §13); it is **not** what produced
the 2017 structures and is not the target.

Why `master` and not `release_1.3`: the deposited GEO models (GSE80280) place particle *k* of a
chromosome at sequence position `floor(min/size)·size + k·size` up to `ceil(max/size)·size`
inclusive (Cell 1 chr1: 3,000,000 … 195,400,000, 1,925 particles) — exactly `master`'s
`calc_restraints` binning (§3), not `release_1.3`'s `calc_bins`, which has one particle fewer.

Build of the original (for timing and as the reference engine): Python 3.11, `numpy<2`,
`cython<3` (0.29.37), `python setup_cython.py build_ext --inplace` (clang, default
distutils flags). `master` reads only the *old* 15-column NCC format (integer ambiguity group;
`load_ncc_file` raises `TypeError` on the newer "1.1"-style groups). The wrapper used here is
`benchmarks/fig3/nucdyn_original/orig_run.py` (times each stage, changes nothing else).

---

## 0. Units and conventions

- Lengths: **particle radii** (every particle has radius 1.0; `nuc_dynamics.py:anneal_genome`
  sets `radii = ones`). All output coordinates are in these units.
- Masses: 1.0 for every particle (`anneal_genome`: `masses = ones`), "hydrogen-like" in the
  paper's words; energies are in kcal/mol-like units with Boltzmann constant
  `BOLTZMANN_K = 0.0019872041` (kcal·mol⁻¹·K⁻¹, `dyn_util.pyx` module constant).
- Time: the user time step `time_step = 0.001` (ps) is multiplied by **`tot0 = 20.458`** inside
  `dyn_util.pyx:runDynamics` (`tStep0 = tStep * tot0`), i.e. converted to AKMA time units
  (1 AKMA unit = 48.888 fs; 1 ps ≈ 20.455 AKMA). Internal step **Δt = 0.020458**. The thermostat
  coupling is divided by the same factor (`beta /= tot0`, so β = 10/20.458 = 0.48881).
- Temperatures are "pseudo-Kelvin".
- Particles are indexed globally by concatenating chromosomes in **Python string sort order**
  of their names (`chr1, chr10, chr11, …, chr19, chr2, …, chr9, chrX`; `load_ncc_file`:
  `chromosomes = sorted(chromosomes)`; offsets in `dyn_util.pyx:concatenate_restraints` from
  `sorted(pos_dict)`). The global order matters for the repulsion exclusion (§6.2).

## 1. Input and contact loading — `nuc_dynamics.py:load_ncc_file`

- One NCC line = one contact observation (`num_obs = 1`; no deduplication — identical lines are
  counted twice).
- Position of each end: `f_start` if strand `+`, else `f_end` (the ligation-junction side of the
  fragment end).
- If `chr_a > chr_b` (string comparison) the two ends are swapped; **within a chromosome the order
  of the two positions is kept as in the file** (not sorted).
- Contacts are stored per ordered chromosome pair `(chr_a, chr_b)` as an int array
  `(4, n) = [pos_a, pos_b, num_obs, ambig_group]` in file order. The ambiguity group is read but
  **never used** in `master` (all restraints are treated as unambiguous, §5).
- The chromosome list is every chromosome name that appears (including chrY/chrM etc. if present),
  string-sorted.

## 2. Isolated-contact filter — `nuc_dynamics.py:remove_isolated_contacts`, `dyn_util.pyx:getSupportedPairs`

Applied **once**, before the first stage (`calc_genome_structure`), never undone. Independently for
every chromosome pair `(chr_a, chr_b)` (cis and trans alike), with `T = isolation_threshold`
(default `-iso 2.0` Mb → 2,000,000 bp, int32) and `posErr = 100` bp:

contact *i* = `(A, B)` is kept iff there exists another contact *j* ≠ *i* = `(C, D)` of the same
chromosome pair with

    (100 < |C − A| < T  and  100 < |D − B| < T)   or   (100 < |D − A| < T  and  100 < |C − B| < T)

(strict inequalities; integer positions). Consequences: exact duplicates do **not** support each
other; a contact whose only neighbour is within 100 bp at one end is dropped. Complexity O(n²) per
chromosome pair in the original. Stevens Cell 1 (GEO): 111,838 → 111,673 contacts.

## 3. Particles (genome binning) — `dyn_util.pyx:calc_restraints`

Recomputed **at every stage** from the *current* contact set (after isolated / violated removals),
for particle size `s` (bp, int32):

1. For each chromosome *c*: `min_c`, `max_c` = smallest / largest contact position of *c* over all
   its contacts (either end, all partner chromosomes). (The code uses `limits[a,0] == 0` as "unset",
   so a true minimum of 0 is not representable; irrelevant for real data.)
2. `first_c = s · floor(min_c / s)` (Python floor division), `last_c = s · (int) ceil((float32)max_c / s)`
   — the division is done in **single precision** (`<float>` cast), then C `ceil`.
3. Particle positions `pos_c = arange(first_c, last_c + s, s)` (int32) → `n_c = (last_c − first_c)/s + 1`
   particles, i.e. both ends inclusive.
4. A contact end at position `p` is assigned to the particle index `j` = the **smallest j with
   `pos_c[j] ≥ p`** (linear scan). So particle *j* represents the genomic interval
   `(pos_c[j] − s, pos_c[j]]`; the first particle only receives contacts exactly at `first_c`.
   Positions are **not** wrapped or clamped: every contact lies inside `[first_c, last_c]` by
   construction. (Output positions are these `pos_c` values.)
5. A chromosome whose contacts were all removed keeps a single particle at 0 (`limits = [0, 0]`).

## 4. Contact restraints — `dyn_util.pyx:calc_restraints`

- For each ordered chromosome pair `(a, b)` present in the contact dict, contacts are binned into
  an `n_a × n_b` count matrix `N[i, j] += num_obs` (int32), **oriented as stored** (§1): for cis
  contacts recorded both as `(p, q)` and `(q, p)`, cells `(i, j)` and `(j, i)` are separate
  restraints. (The GEO files are sorted, cis `pos_a ≤ pos_b`, so this does not arise for them.)
- Every cell with `N ≥ min_count = 1` becomes one restraint between particles `i` (of *a*) and `j`
  (of *b*), including **`i == j`** (same particle; skipped by the force and statistics routines,
  §6.3) and **`|i − j| = 1`** (adjacent particles: kept, *on top of* the backbone restraint).
- Target distance `d_t = scale · N^exponent` with `scale = 1.0`, `exponent = -0.33`
  (`-pow`), bounds **`d_min = 0.8 · d_t`, `d_max = 1.2 · d_t`** (`-lower`, `-upper`). The function
  arguments `scale, exponent, lower, upper` are C `float` (float32): −0.33 → −0.33000001311,
  0.8 → 0.80000001192, 1.2 → 1.20000004768; the product is formed in double.
- Weights (row 2) are written as 1.0 and **not used**.

## 5. Backbone restraints and concatenation — `dyn_util.pyx:concatenate_restraints`

- For every chromosome, every sequence-adjacent pair `(k, k+1)` gets a restraint with
  `d = (pos[k+1] − pos[k]) / s = 1.0` and bounds **`[0.1·d, 1.1·d]`** (`-bb_lower`, `-bb_upper`;
  cast to float32: 0.10000000149, 1.10000002384).
- Restraint list = all backbone restraints (chromosomes in sorted order), then all contact restraints
  per chromosome pair. Indices are int32 global particle indices, bounds float64 `(n, 2)`.
- Ambiguity strides are all 1 (`anneal_genome`: `ambiguity = ones(num_restraints)`), so every
  restraint is a single pair (the ambiguous-restraint branch of the force routine is dead code in
  `master`).

## 6. Force field — `dyn_util.pyx`

### 6.1 Distance restraints — `getRestraintForce` (fConstD = K = 25.0, distSwitch = 0.5, asymptote = 1.0, exponent = 2.0)

Constants: `b = asymptote·ds² − exponent·ds³ = 0.25 − 0.25 = 0`, `a = ds² − asymptote·ds − b/ds = −0.25`.
For a restraint `(j, k, d_min, d_max)` with `j ≠ k`, `r = |x_j − x_k|`:

| regime | energy U | radial coefficient `rjk` |
|---|---|---|
| `r² < d_min²` (r floored: `r² = max(r², 1e-8)`) | `K (d_min − r)²` | `+2K (d_min − r)` |
| `d_min ≤ r ≤ d_max` | 0 | 0 |
| `d_max < r ≤ d_max + 0.5` | `K (r − d_max)²` | `−2K (r − d_max)` |
| `r > d_max + 0.5` | `K (a + d + b/d) = K (d − 0.25)`, `d = r − d_max` | `−K (asymptote − b/d²) = −K` (constant) |

Force: `F_j += rjk · (x_j − x_k) / r`, `F_k −= rjk · (x_j − x_k) / r`. Beyond the switch the
restraint pulls with a constant force of magnitude K = 25 (continuous with the harmonic part at
d = 0.5). Backbone and contact restraints use the same function and the same K.

### 6.2 Repulsion — `getRepulsiveForce`

For each pair `(j, k)` in the neighbour list (§7) with `R = radius_j + radius_k = 2.0`:
skip if `|Δx| > R` or `|Δy| > R` or `|Δz| > R` or `d² > R²` (so `d = R` is included); otherwise, with
`dr = R² − d²`:

    U = k_rep · dr²            F_k += 4 k_rep dr (x_k − x_j),   F_j −= 4 k_rep dr (x_k − x_j)

i.e. a **quartic** soft sphere `k_rep (4 − d²)²` for `d ≤ 2`, with `k_rep` from the annealing
schedule (§8). Pairs are only those with **global index `j ≥ i + 2`** (§7), so sequence neighbours
are never repelled — and neither are the last particle of one chromosome and the first particle
of the next chromosome in the sorted concatenation (index distance 1).

### 6.3 Statistics (logging only) — `getStats`

`nViol` = restraints outside `[d_min, d_max]`, `rmsd = sqrt(Σ viol² / nRest)` over all restraints
(`j == k` skipped but counted in `nRest`). Not used by the algorithm.

## 7. Neighbour (repulsion) list — `getRepulsionList`, maintenance in `runDynamics`

- Built with `repDist = 2.0` (argument default of `runDynamics`): candidate pairs `j ≥ i + 2` with
  `d ≤ d_lim = repDist + r_i + r_j = 4.0` at build time. The search uses axis-aligned bounding boxes
  of consecutive particle blocks (`s1 = 8` particles; for `N ≥ 8·256 = 2048` particles a two-level
  scheme with blocks of `s2 = 256`), boxes padded by `repDist + max_radius = 3.0`, sorted by x-start
  (heapsort) with early break; the result is **exact** (all and only pairs within 4.0).
- Built at step 0 of **every** `runDynamics` call (i.e. at the start of every temperature step) and
  rebuilt at step `> 0` whenever the largest squared displacement of any particle since the last
  build exceeds `deltaLim = 0.25 · repDist² = 1.0` (displacement > 1.0 radius). The check happens
  before the position update of that step. With cutoff 4 = 2 + 2·1, this makes the repulsion
  effectively exact.
- Capacity `nRepMax`: `nCoords · 10` in the first call of a model, afterwards
  `int32(1.05 · n_rep_found)` of the previous call (`nuc_dynamics.py:anneal_model`). **Quirk:** if a
  build finds more pairs than `nRepMax`, the list is filled to capacity, then *replaced by a new
  all-zero array* of size `1.1 · found` while `nRep` keeps the truncated count — every stored pair is
  `(0, 0)`, whose force is zero. **Repulsion is therefore switched off until the next rebuild**
  (next displacement > 1.0, which at low temperature may be after the whole 100-step call). An
  exact-reproduction engine should implement this behaviour behind a flag; a "fixed" engine should
  report how often it occurs. Measured with an instrumented copy of `dyn_util.pyx` (counters only),
  Stevens Cell 1, one model: see the table below — it is not a rare corner case at the fine stages.

  | stage | list builds | overflowing builds | steps with repulsion off (of 50,000) |
  |---|---|---|---|
  | 8 Mb | 3,519 | 125 | 498 (1.0 %) |
  | 4 Mb | 3,263 | 60 | 206 (0.4 %) |
  | 2 Mb | 3,123 | 1 | 4 (0.0 %) |
  | 400 kb | 6,540 | 1,031 | 5,421 (10.8 %) |
  <!-- NL_OVERFLOW_ROWS -->

  The growth factor 1.05 of `anneal_model` is too small when the structure compacts between
  temperature steps, so the first build of a call overflows and the whole call can run without
  repulsion.

## 8. Annealing schedule — `nuc_dynamics.py:anneal_genome`, `anneal_model`

Per stage (all stages identical), with `temp_start = 5000` (`-hot`), `temp_end = 10` (`-cold`),
`temp_steps = 500` (`-temps`), `dynamics_steps = 100` (`-dyns`), `time_step = 0.001` (`-time_step`):

    for step in 0 .. temp_steps−1:
        frac    = step / temp_steps
        T_ref   = temp_start · exp(−ln(temp_start/temp_end) · frac)          # exponential, 5000 → 10.1
        k_rep   = 0.5 + atan(20·frac − 10) / (π · atan(10))                   # sigmoid, 0.182 → 0.817
        runDynamics(coords, T_ref, nSteps = dynamics_steps, fConstR = k_rep, fConstD = 25, ...)

→ **500 × 100 = 50,000 integration steps per stage per model**, 300,000 for the default six stages.
Each `runDynamics` call re-draws velocities (§9) and rebuilds the neighbour list; nothing but the
coordinates carries over between temperature steps. After the last temperature step the model is
centred (`model_coords −= mean`).

## 9. Integrator and thermostat — `runDynamics`, `updateMotion`, `updateVelocity`, `getTemp`

Temperature measure (`getTemp`): `T(v) = Σ_i m_i |v_i|² / (3 N k_B)`.

At the start of each call: `v ~ Normal(0, 1)` per component (`numpy.random.normal`, global legacy
RandomState), then `v *= sqrt(T_ref / T(v))` (instantaneous temperature exactly `T_ref`). Forces
`F(x)` are computed (repulsion + restraints).

Each of the `nSteps` steps (Δt = 0.020458, β = 10/20.458):

1. neighbour-list check / rebuild (§7);
2. `updateMotion`: `T = max(T(v), 0.001)`, `λ = β (T_ref / T − 1)`; for every particle
   `a = F/m + λ v`; `x += Δt v + ½ Δt² a`; `v += Δt a` (a is stored);
3. `F = 0`; `F += repulsion(x)`; `F += restraints(x)`;
4. `updateVelocity`: `T' = max(T(v), 0.001)` with the *updated* v, `λ' = β (T_ref / T' − 1)`;
   `v += ½ Δt (F/m + λ' v − a)`.

Net effect: velocity Verlet with a Berendsen-like velocity-proportional thermostat term inside the
acceleration (the velocity half-step is `0.5·Δt·(…)`).

## 10. Hierarchical protocol — `nuc_dynamics.py:calc_genome_structure`, `anneal_genome`

Default particle sizes (`-s`): **8, 4, 2, 0.4, 0.2, 0.1 Mb** (sorted descending). `num_models`
(`-m`, default 1) is **fixed for all stages**: model *m* of stage *s+1* starts from model *m* of stage
*s*; there is no model selection, no alignment and no re-seeding of individual models in `master`.

Stage loop:

1. **Violated-contact removal** (`remove_violated_contacts`), only if `stage > 0` and
   `particle_size < 0.5 Mb`: threshold **6.0 radii** (the `elif particle_size < 0.25e6: 5.0` branch
   is unreachable). With the default sizes: before the 400 kb, 200 kb and 100 kb stages, using the
   previous stage's coordinates. For every contact, both end positions are **linearly interpolated**
   on the previous stage's particle positions (§10.3) for every model; the Euclidean distance is
   **averaged over all models**; contacts with mean distance `≥ 6.0` are removed permanently
   (cumulative over stages; the removal also shrinks chromosome extents in §3). Absolute distance,
   not relative to `d_max`.
2. **Restraints** recomputed from the current contacts (§3–§5).
3. **Start coordinates**:
   - stage 0: `get_random_coords` — for every model, for every particle in global order, draw
     `x, y, z = R·(2U − 1)` with `U = numpy.random.uniform(0, 1)` until `x² + y² + z² < R²`,
     `R = random_radius = 10.0` (`-rad`): uniform in a ball of radius 10 radii (rejection sampling;
     independent of chromosome structure);
   - later stages: the previous stage's coordinates, interpolated per model
     (`dyn_util.pyx:getInterpolatedCoords`) if the particle count changed.
   - `numpy.random.seed(random_seed)` is called at the start of **every** stage
     (`anneal_genome`); `-ran` defaults to `int(time())`.
4. **Anneal** all models (§8), in parallel over models (§11).

### 10.3 Interpolation — `dyn_util.pyx:getInterpolatedCoords`

For each new position `p` of chromosome *c*: find the nearest previous particle position (linear
scan that stops once the distance grows), then the bracketing pair `(p1, p2)` and interpolate
`x = (1 − f) x_{p1} + f x_{p2}`, `f = (float32)(p − pos_{p1}) / (float32)(pos_{p2} − pos_{p1})`
(single-precision division). Positions outside the previous range copy the end particle
(clamped). This equals `numpy.interp` per coordinate up to the float32 `f`.

## 11. Parallelism, randomness, precision, output

- **Parallelism**: `parallel_split_job` starts `min(num_cpu, num_models)` `multiprocessing.Process`es
  (`-cpu`, default all cores); task *t* (= model *t*) goes to process `t % num_cpu`; each model is
  annealed serially in single-threaded Cython. Stages are barriers (all models finish before the next
  stage). No threading, no SIMD beyond the C compiler's, no GPU.
- **Randomness**: velocities come from the global numpy RandomState. Under the `fork` start method
  (Linux) every child inherits the parent's state (just seeded, §10), so the first model of every
  process draws the **same velocity sequence** — with `num_models ≤ num_cpu` all models of a stage
  do, and they differ only by their start coordinates; under `spawn` (macOS, Python ≥ 3.8, as
  here) each child re-imports numpy and is seeded from OS entropy, so runs are not reproducible
  even with `-ran`. In-process (`orig_run.py --serial`) the velocities come from the seeded global
  stream and a run is reproducible.
- **Precision**: float64 for coordinates, velocities, accelerations, forces, masses, radii,
  restraint bounds; int32 for restraint and neighbour-list indices and for sequence positions
  (genome positions must be < 2³¹). float32 only where listed (§3 ceil, §4 parameters, §5 backbone
  bounds, §10.3 interpolation fraction).
- **Output**: per chromosome an array `(num_models, n_c, 3)` in radii, each model centred on its own
  centroid (all particles), plus the particle positions `pos_c`. `export_n3d_coords`: blocks
  `chrom  n_coords  n_models` then `pos  x1 y1 z1  x2 y2 z2 …` (`%.8f`); `export_pdb_coords`: one
  `MODEL` per model, chains `a, b, …` in numeric chromosome order, sequence position in the last
  column (extended PDB). Models are not superimposed on each other.
- **Performance notes** (not semantics): the neighbour-list repulsion makes a step O(N); in
  `getRepulsiveForce` the variable `repDist` is not `cdef`-typed, so the per-pair comparisons go
  through Python float objects — the main reason the original is slow. Measured costs are in
  `u-chrom-paper/manuscripts/full/figures/fig3/results/a_nucdyn_original_timing.json`.

## 12. Paper (Supplementary Methods) vs `master` code

| Item | Paper | `master` code (what this spec describes) |
|---|---|---|
| Resolution schedule | 4, 2, 0.4, 0.2, 0.1 Mb | 8, 4, 2, 0.4, 0.2, 0.1 Mb |
| Models | 20 at 4 Mb; best 10 (lowest median pairwise RMSD) kept after 400 kb | fixed `-m` for all stages, no selection |
| Steps | 500 temperature steps, "motion steps 10,000" | 500 × 100 = 50,000 per stage |
| Cooling | "linearly" | exponential in the step fraction |
| Repulsion | `k1 (d − d_lim)²`, d_lim = 2, k1 up to 1.0 | `k_rep (4 − d²)²`, k_rep 0.18 → 0.82 |
| Far restraint | linear beyond d_upper + 0.5 | same (constant force K) |
| Violation removal | > 6.0 above d_upper from the 400 kb structures, > 5.0 above d_upper from the 200 kb structures | ensemble-mean distance ≥ 6.0 (absolute) before the 400, 200 and 100 kb stages |
| Random start | sphere "radius of 1000 particles" | ball of radius 10 radii |
| Final round | ambiguous contacts disambiguated and isolated contacts re-added (mean distance < 5.0) using the 100 kb structures, then one more 100 kb calculation | not implemented |
| Precision metric | mean pairwise all-particle RMSD after SVD superposition, ± SEM | — |
| Violation metric | restraint violated if `d > d_upper + δ`, δ = 3 or 4 radii | — |

The GEO models are the paper's final structures (with the extra round). ED Table 2 reports four
stages (400 kb, 200 kb, 100 kb without and with the ambiguous restraints); the harness
(`nucdyn_harness.py`) carries the full table.

**Metric calibration on the GEO models** (`u-chrom-paper/manuscripts/full/figures/fig3/results/a_nucdyn_reference_published.json`):
the "precision" of ED Table 2 is reproduced for all eight cells, within 0.01 radii, by the **RMSD of
each model to the superposed ensemble mean** (Cell 1 0.414 vs 0.41 … Cell 7 1.742 vs 1.75), not by
the mean pairwise RMSD (≈ 1.5 × larger, 0.615 for Cell 1), although the table's footnote says
"mean pairwise". ED Table 2's restraint counts (`N_rest`) and violation shares are **not**
reproducible from the deposited contact lists: e.g. Cell 8 has 32,482 restraints in the table
but only 25,994 contacts between distinct particles in the GEO file; the violation shares match
only for Cell 8 (0.03 / 0.02 %), the one cell whose GEO file has no duplicate lines. The harness
therefore reports violations on one fixed definition (restraint = unique non-adjacent particle
pair, `d_upper = 1.2 n^-0.33`, violated if `d > d_upper + δ`) and uses the published models as
the baseline for that definition.

## 13. What changed in `release_1.3` (not the target)

`bead_size = particle_size^(1/3)` scales every distance, the random radius, `T_ref ·= bead²`,
`k_rep /= bead²`; restraint weights and a global restraint force scale
`dist = 215 · N_particles / Σ weights`; binning by `searchsorted(..., side='right') − 1`
(particle = `[pos, pos + s)`, one particle fewer at the end); separate cis / trans isolation
thresholds (2 / 10 Mb) and unambiguous contacts only; 3-D disambiguation at ≤ 0.4 Mb; violation
thresholds 6·bead (< 0.5 Mb) and 5·bead (< 0.25 Mb); **2 × m models above 1 Mb, then the m models
with the lowest RMSD to the (weight-aligned) mean are kept**; random start uniform in a ball via
normal/u^(1/3); models aligned (mirror allowed) on export. It is a re-parameterised model and does
not reproduce the 2017 particle convention.
