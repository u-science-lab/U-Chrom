# Consensus structure of bulk Hi-C by hierarchical restraint annealing — design, evidence, validation plan

Goal: **one representative 3-D structure per bulk Hi-C map**, whole genome by default (all chromosomes
in one structure, inter-chromosomal restraints), from 1 Mb down to 10 kb, computed by *dynamics* —
a new protocol `consensus` of the native Rust / wgpu engine (`native/nucdyn`), reusing its restraint
forces, cell-grid repulsion, integrator, thermostat, annealing schedule and hierarchical stages —
**without TAD partitioning** (no miniMDS-style domains).  The PyTorch MDS (`uchrom.recon.bulk.mds`)
stays untouched as a baseline.  User API: `uchrom.recon.bulk.consensus.reconstruct_consensus`.

Legend: **[standard]** taken from a published method (cited), **[new]** introduced here, with the
evidence that set it.  "Local" numbers are laptop development runs (Apple M5 Pro, Metal) on real
data at reduced scale (Rao 2014 IMR90 via HTTP range reads; Su 2020 genome-scale imaging, a random
300 of 1,787 cells) — they guided the defaults and are **preliminary**; the validation is the
Sherlock plan of section 8.

## 1. Literature (claims verified from the papers / official code)

| method | contacts → restraints / objective | what we take |
|---|---|---|
| NucDynamics (Stevens et al. 2017 *Nature* 544:59, doi:10.1038/nature21429; code tjs23/nuc_dynamics) | target `d = count^-0.33`, bounds [0.8 d, 1.2 d], backbone [0.1, 1.1]; **flat-bottom**: zero inside the bounds, harmonic outside, asymptotically linear beyond `d_max + 0.5`; simulated annealing 8 → 0.1 Mb, each stage interpolated from the previous | engine, integrator, annealing schedule, flat-bottom saturating force, stage interpolation **[standard]** |
| TADbit / IMP (Baù et al. 2011 *NSMB* 18:107, doi:10.1038/nsmb.1936; Serra et al. 2017 *PLoS CB* 13:e1005665, doi:10.1371/journal.pcbi.1005665; code `restraints.py`) | z-scores of normalised frequencies; z > upfreq → harmonic at a distance linear in z, z < lowfreq → harmonic lower bound, in between nothing; `kforce = |z|^0.5`; MC + CG; 5,000 models, the 1,000 lowest-objective kept, then clustered (Baù: 50,000 / 10,000) | "keep informative pairs only", confidence weights, **keep the lowest-energy runs, then take a central model** **[standard idea]** |
| LorDG (Trieu & Cheng 2017 *NAR* 45:1049, doi:10.1093/nar/gkw1155) | maximise Σ c² / (c² + (x_ij − d_ij)²) (Lorentzian): inconsistent population restraints "barely affect" the others; `d = 1 / IF^α`, α searched in [0.1, 3] | Lorentzian option (on the bound violation, flat bottom kept) **[standard form, new combination]** |
| PASTIS (Varoquaux et al. 2014 *Bioinformatics* 30:i26, doi:10.1093/bioinformatics/btu268) | `c_ij ~ Poisson(β d_ij^α)`, α = −3 theoretical (fitted in PM2) | α fittable; noted, not used |
| HSA (Zou, Zhang & Ouyang 2016 *Genome Biol* 17:40, doi:10.1186/s13059-016-0896-1) | Poisson GLM with a per-track power-law coefficient; Hamiltonian dynamics combined with SA | dynamics-based annealing of a count model — supports the approach |
| ShRec3D (Lesne et al. 2014 *Nat Methods* 11:1141, doi:10.1038/nmeth.3104) | weight 1/C, all-pairs shortest path, MDS | not used |
| miniMDS (Rieber & Mahony 2017 *Bioinformatics* 33:i261, doi:10.1093/bioinformatics/btx271) | `d = c^(−1/α)`, **α = 4** "found to best fit FISH (Wang 2016)"; decay prior w = 0.05; full mode = MDS of the chromosome, partitioned mode = domains (≈ TADs) | α = 4 **[standard]**; full mode as a baseline |
| Hi-BDiSCO (Li & Schlick 2024 *NAR* 52:583, doi:10.1093/nar/gkad1121) | Brownian dynamics; Micro-C frequencies distributed stochastically over replicas, linear restraint forces `h (d − d0)` | dynamics on restraints; per-replica assignment is the population route (our IGM protocol), not the consensus |
| Wang et al. 2016 *Science* 353:598 (doi:10.1126/science.aaf8084) | Hi-C frequency ∝ mean distance^−4.1 ± 0.1 (IMR90 chr21, TAD-to-chromosome scale) | **α = 4** **[standard]** |
| HIPPS (Shi & Thirumalai 2021 *PRX* 11:011051, doi:10.1103/PhysRevX.11.011051) | ⟨r_ij⟩ = Λ ⟨p_ij⟩^(−1/α), α = 4 "following the experimental lead" | baseline (mean distances) |
| Su et al. 2020 *Cell* 182:1641 (doi:10.1016/j.cell.2020.07.032) | Hi-C vs imaging median distance, log-log slope −4.6 (ρ = −0.89) | supports α ≈ 4–4.6; the imaging reference |

## 2. Contacts → restraints

**Units.** Lengths in units of the distance between adjacent bins at the final resolution
(`D_final = 1`); `scale_nm` converts (e.g. from `calibrate.py`).

**Balancing [standard].** Per stage: coverage filter (row sum < 5 % of the median → masked), then
Knight–Ruiz (`deconv.preprocess.kr_balance`, verified against Juicer's KR vectors to 1e-7) — or ICE /
none.  Genome-wide stages balance the genome matrix (cis + trans); fine (cis-only) stages balance each
chromosome's band of pixels (the multiplicative bias model holds on any subset of pixels; reading the
whole cis matrix at 10 kb is what we avoid).

**Target [standard form, new scaling].** `d_ij = D_s (f_ij / f_nn,s)^(−1/α)`, `f_nn,s` = expected
frequency of adjacent bins of stage s (a self-normalisation that fixes the unit per stage), clipped
below at `D_s`.  α = 4 by default (table above); `alpha="fit"` → `α = γ / ν_polymer` from the contact
decay `P(s) ∝ s^−γ`; `calibrate.py` fits α and the nm scale on imaging (an *oracle* variant, flagged).
**New:** the stages must agree where a fine-stage target and a carried coarse target describe the same
pair.  With `D_s = (b_s / b_final)^ν` and `P(s) ∝ s^−γ`, a pair k coarse bins apart has coarse target
`D_c k^(γ/α)` and fine target `D_f (k b_c/b_f)^(γ/α)`; they are equal iff **ν = γ / α**.  So ν is set
from the decay fit (IMR90 1 Mb: γ ≈ 0.9–1.0 → ν ≈ 0.22–0.25), clipped to [0.15, 0.6].

**Bounds [standard form, new values].** `[0.9 d, 1.1 d]` (NucDynamics: 0.8 / 1.2 for single-cell
contacts, whose target is only "close").  A bulk target is a quantitative estimate with relative error
≈ (1/α)(1/√n + model error) ≈ 5–10 %; wider bounds erase the ranking of nearby targets.  Local
evidence (1 Mb, no trans, dense cis): ±20 % → per-chromosome Spearman vs imaging 0.725, ±5 % → 0.743,
±5 % with absolute-error weights 0.759; ±10 % ≈ ±5 % (0.707 vs 0.703 on the sparse path) with fewer
nominal violations.

**Weights [standard idea, new form].** Confidence `n / (n + 10)` (Poisson relative error of f ∝ 1/√n,
saturating where model error dominates), × `trans_weight` (0.3) for inter-chromosomal pairs.  A
relative-error variant × `(D_s / hi)²` (harmonic in the relative violation) is an option; it was worse
on real data (0.743 vs 0.759) and is off by default.  Force constant per stage
`K = force_scale · N / Σ w` (NucDynamics release_1.3: "keep force / particle approximately constant").

**Which pairs [new].** A pair is *measurable* when the **expected** reads at its separation (or of
trans pairs) are ≥ 5 — selecting on the observed count keeps exactly the pairs that got lucky reads
(toy genome: trans r 0.55 with per-pixel selection vs 0.89 with this rule and carried coarse trans).
Then, per stage:
* **dense cis** when the stage has ≤ 3,000 beads (whole genome at 1 Mb and coarser): every measurable
  cis pair with |i − j| ≥ 2;
* otherwise a **cis band** of `max(5, 3 × b_prev / b_s)` bins (12 for a ×4 ladder), plus per bin the 4
  most enriched long-range pairs (O/E ≥ 2, ≥ 5 reads; loops, compartment contacts), plus a
  **log-spaced separation ladder**: per bin and direction one random measurable pair per slot
  `[band q^k, band q^(k+1))`, q = 1.15 — every distance scale is represented with O(n log n)
  restraints (dense is O(n²)); at cis-only stages up to 200 bins (the window read per chromosome);
* **trans only at genome-wide stages** (bins ≥ 1 Mb, or the first stage): the 4 most enriched + 32
  random measurable inter-chromosomal partners per bin, never dense (below);
* **carried restraints**: every restraint of the previous stage outside the new band is kept between
  representative beads (the bead nearest to the coarse bin's midpoint) unless the new stage restrains
  that pair itself — this is how inter-chromosomal and long-range information reaches 250 kb … 10 kb
  without reading trans pixels there;
* **backbone**: adjacent valid beads, target `D_s gap^ν`, bounds [0.1, 1.2] × target, weight 3.

Local evidence for the selection (IMR90 whole genome, final 1 Mb, vs Su 2020 medians, 300 cells):

| variant | cis ρ | per-chromosome cis ρ (median) | trans ρ | per-chromosome spread across runs |
|---|---|---|---|---|
| first version: dense trans at 4 Mb, band + O/E + 4 random per bin at 1 Mb, ±20 %, relative weights | 0.632 | 0.54 | 0.333 | 0.88 |
| same, no trans | 0.708 | 0.66 | — | 0.84 |
| no trans, dense cis at 1 Mb | 0.769 | 0.725 | — | 0.39 |
| no trans, dense cis, ±5 %, absolute weights | 0.801 | 0.759 | — | 0.04 |
| no trans, band + ladder (q = 1.15), ±5 %, absolute weights | 0.768 | 0.726 | — | 0.18 |
| **defaults** (dense cis, ±10 %, sparse trans 4 + 32 per bin, trans weight 0.3), two runs | 0.80 / 0.80 | 0.756 / 0.759 | 0.29 / 0.24 | 0.44 / 0.44 |
| reference: SMACOF 3-D embedding of the same targets, per chromosome | — | 0.777 | — | — |
| reference: 3-D embedding of the imaging medians themselves, per chromosome / genome-wide cis | — | 0.876 / 0.626 | — | — |

Dense trans (≈ 256 k trans vs 13 k cis restraints at 4 Mb) made population-averaged, mutually
inconsistent inter-chromosomal targets dominate the fold (34 % of restraints violated) and cost 0.08
in cis; sparse trans restores cis while keeping (weak) trans information.  Bead radius (0.5 / 0.25 /
0.1 × D), longer annealing (4×) and relative weights did not matter.

## 3. Potential and dynamics

* **Restraint form [standard].** release_1.3 NucDynamics: flat inside [lo, hi], harmonic up to
  1.5 hi, constant force beyond (weighted) — the saturating force already in the engine and on the GPU.
* **Lorentzian [new in the engine].** `U = w K c² δ² / (δ² + c²)`, δ = violation beyond the bounds,
  c = `lorentz_width` × hi: harmonic `w K δ²` for small δ, bounded and redescending for gross violations
  (LorDG's Lorentzian on the flat-bottom violation).  The first stage stays saturating (from a random
  start every restraint is grossly violated and a redescending force would not pull).  CPU f64 + WGSL
  form 2; finite-difference and GPU-vs-CPU tests.  On the consistent toy it brings nothing (as
  expected); its purpose is inconsistent real data — tested on Sherlock (`*_lor` tasks).
* **Repulsion [standard].** NucDynamics `f_rep (4r² − d²)²` between non-adjacent beads closer than
  2r, exact cell grid every step; r = D_s / 2 (0.25 / 0.1 × D tested: no change).
* **Confinement [new, optional].** `½ k (|x| − R)²` beyond R (off by default; a consensus of mean
  distances has no nucleus).
* **Annealing [standard schedule].** First stage T 5,000 → 10 over 500 × 100 MD steps (NucDynamics);
  later stages from T = 500 (200 × 100 steps) — they start from the interpolated structure; a toy sweep
  gave r 0.967 (500) vs 0.954 (100) and 0.945 (2,000); `force_scale` 50 was at the optimum of
  {15, 50, 150}.

## 4. Hierarchy instead of partitioning

Stages `final × 4^k` up to 8 Mb (250 kb → 4 Mb, 1 Mb, 250 kb; 10 kb → 2.56 Mb, 640, 160, 40, 10 kb).
The **whole genome goes through every stage together**: the first stage places all chromosomes
(cis + trans restraints), every later stage starts from the previous one interpolated at the new bead
positions (`protocol2017::interpolate`, the NucDynamics rule) — there is no per-chromosome
reconstruction glued afterwards and no domain partition.  Trans restraints exist only at stages ≥ 1 Mb
(or small genomes) and are carried down (section 2), which keeps fine stages sparse:

| whole human genome | beads | restraints (≈ per bead) | GPU buffers per run (≈) |
|---|---|---|---|
| 1 Mb (dense cis) | 2,863 | 289 k (100) | 5 MB |
| 250 kb | 11,289 | 707 k (63) — band 121 k, ladder + enriched 314 k, carried 261 k | 12 MB |
| 100 kb | ≈ 28,000 | ≈ 2 M (70) | 35 MB |
| 25 kb | ≈ 112,000 | ≈ 8 M (70) | 140 MB |
| 10 kb | ≈ 280,000 | ≈ 20 M (70) | 0.35 GB (restraint forces 16 B per restraint and run) |

(1 Mb / 250 kb: measured, local; finer: extrapolated, measured by `consensus_scaling.sbatch`.)  The
restraint-force buffer is `n_runs × n_restraints × 16 B` in one storage binding (NVIDIA Vulkan limit
4 GiB): 10 kb × 8 runs ≈ 2.6 GB fits, 16 runs does not (open item 3).

## 5. Runs and the consensus

`n_runs` (default 8; 16 in the benchmark) independent runs — own random start, own velocity streams —
batched on the GPU (one buffer set, kernels over (particles, runs)) or parallel on the CPU.  Consensus =
the **medoid** (smallest summed RMSD after superposition, reflection allowed) of the **lowest-energy
half** of the runs [standard idea: TADbit keeps the lowest-objective models, then a central model].  The
superposed mean re-relaxed at low temperature (T 50 → 10) is computed too (`layers["mean_refined"]`,
`consensus="mean_refined"`): averaging superposed runs shrinks regions where runs disagree, the
re-relaxation restores bond lengths but not a fold that no run had — so the medoid (a structure that
satisfies its restraints) is the default; local numbers: 1 Mb cis ρ 0.802 medoid vs 0.794 mean_refined,
trans 0.235 vs 0.263; 250 kb 0.776 / 0.775.  Uncertainty: per-bin RMS deviation of the superposed runs
(`bin_tracks["consensus_spread"]`, whole structure; `consensus_spread_chrom`, per-chromosome
superposition) and run-to-run precision (median RMSD / Rg, distance-matrix r) in `uns`.

## 6. Implementation

| piece | where |
|---|---|
| Lorentzian form, confinement (CPU f64) | `native/nucdyn/src/dynamics.rs` (`RestraintForm::Lorentzian`, `lorentz_term`, `confine`) |
| same on the GPU (f32) | `native/nucdyn/src/gpu/nucdyn.wgsl` (form 2 in `restraints`, confinement in `total_force`), `gpu/mod.rs` (`GpuParams`) |
| protocol: stages, runs, interpolation, per-run energy / violations | `native/nucdyn/src/consensus.rs` (`Stage`, `ConsensusParams`, `run_consensus`) |
| Python binding | `python.rs: calc_consensus(stages, params_json, start=None)`; `uchrom_nucdyn.calc_consensus` |
| sources, balancing, expected, decay fit | `uchrom/recon/bulk/consensus/_contacts.py` |
| ladder, restraint selection, targets, weights, carrying | `uchrom/recon/bulk/consensus/_restraints.py` |
| API, consensus choice, spread, ChromData | `uchrom/recon/bulk/consensus/_run.py` (`reconstruct_consensus`), `_superpose.py`, `_params.py` |

`reconstruct_consensus(data, *, method="anneal", resolution=None, chrom=None, bins=None,
params=ConsensusParams(), n_runs=None, seed=None, device="auto", key_added="consensus.anneal",
copy=False, **overrides)`: `data` = `.cool` / `.mcool` path or URL, a ChromData with a linked cool
(`cd.link_cool`), or counts + `bins=`; returns a ChromData (one cell `consensus`, one trace per
chromosome; `layers["run_k"]`, `layers["mean_refined"]`; `bin_tracks` spread and restraint counts;
`uns["consensus"]` everything needed to reproduce: parameters, α / ν / decay fit, per-stage restraint
counts and logs, per-run energies and violations, precision, timings; `results[key_added]` per-run
table; with a ChromData input and `copy=False` also the consensus table in the input's `results`).

## 7. Correctness checks (synthetic = correctness only)

* Rust: forces = −∇ of the weighted energy for saturating, Lorentzian and confinement terms (max
  relative error 5e-6); Lorentzian limits; stage interpolation; two-stage recovery of a known chain,
  CPU and GPU, both forms (distance r 0.993 per run); GPU (f32) vs CPU (f64), 10 MD steps with the new
  terms from the same velocities: max difference 1.6e-5 bead units.
* Python (`tests/recon/test_consensus.py`): ladder, decay / power-law fits, target / bound / weight
  formulas, KR invariance to bin biases, measurable selection and carrying, Kabsch; synthetic whole
  genome (3 chromosomes in territories, contacts from `min(1, d)^−4` with Poisson reads and bin biases):
  dense path r 0.987 (cis 0.959, trans 0.910), similarity-RMSD / Rg 0.30, run-to-run r 0.998; sparse path
  r 0.986 (cis 0.945, trans 0.913), RMSD / Rg 0.12; single chromosome CPU vs GPU r 0.999; linked-cool
  input; the chunked cooler reader equals the in-memory one.

## 8. Validation (Sherlock; `README.md` for commands and resources)

Real data only, per CLAUDE.md:

* **IMR90**: Rao 2014 in situ (4DN 4DNFIR1JDZH7, GRCh38) → whole-genome consensus at 1 Mb, 250 kb,
  100 kb (and 50 kb) vs **Su 2020 genome-scale DNA-MERFISH** (1,041 loci on chr1–22, X; 1,787 cells,
  homologs resolved; cis and trans) and **Su 2020 chr21** (651 × 50 kb traces) — chr21 both from the
  whole-genome runs and from single-chromosome runs at 50 / 100 kb.
* **mESC**: Bonev 2017 (4DN 4DNFIC21MG3U, mm10) whole genome at 1 Mb, 250 kb, 100 kb vs **Takei 2021
  seqFISH+ 1 Mb** (2,460 loci; homologs split heuristically — flagged).
* **Metrics** (`score.py`): Spearman / Pearson (linear, log-log) between model distances and the
  imaging **median** distances over locus pairs — all, cis by separation band (0–1 … > 50 Mb), trans,
  per-chromosome cis; scale-free RMSD after similarity superposition onto the imaging mean-distance
  embedding (with the embedding's own fidelity reported: 0.70 genome-wide for Su — the medians of a
  population are far from 3-D-embeddable across chromosomes, so the distance correlations are the
  headline); fit to the input (−Spearman of distance vs balanced frequency, cis / trans); run-to-run
  precision; seeds.
* **Baselines on the same balanced input**: U-Chrom PyTorch MDS full mode (genome-wide matrix, and per
  chromosome), miniMDS full mode (per chromosome; @ 9915d21), HIPPS mean distances `(f/f_nn)^−1/4`
  (a distance matrix, not a structure), IGM population median distances when the deconvolution runs
  exist (`$IGM_<dataset>`).
* **Variants**: seeds 1–3, Lorentzian, α fitted, α imaging-calibrated (oracle), no trans,
  mean_refined consensus, CPU path.
* **Scaling**: whole genome 1 Mb → 10 kb on one H100 (8 runs; 16 / 32 runs at 250 kb) and on 8 / 16 / 32
  CPU threads: prepare / engine / wall time, peak RSS, peak GPU memory.

Preliminary local result (Su 2020, 300-cell subsample, IMR90 whole genome at 1 Mb, defaults): consensus
cis ρ 0.80 / trans 0.24 / all 0.31, fit to input cis 0.92; U-Chrom MDS on the genome matrix cis 0.19 /
trans 0.27 / all 0.34 (the genome-wide MDS loses cis structure); U-Chrom MDS per chromosome cis 0.73
(per-chromosome 0.79, no trans placement); HIPPS mean distances cis 0.87 / trans 0.39 / all 0.47.  At
250 kb: consensus cis 0.78 / trans 0.33 / all 0.39 vs HIPPS 0.83 / 0.25 / 0.36.  Speed: 1 Mb (2,863 beads,
8 runs) 18 s engine, 250 kb (11,289 beads, 707 k restraints, 8 runs) 67 s engine, 2.6 GB RSS (M5 Pro GPU).

## 9. Open questions

1. **A single structure vs mean distances.** HIPPS' mean distances correlate better with the imaging
   medians in cis (0.87 vs 0.80 at 1 Mb) than any 3-D structure can: even the stress-optimal 3-D
   embedding of the same targets reaches 0.777 per chromosome, and the genome-wide 3-D embedding of the
   imaging medians themselves only 0.63 in cis.  A consensus structure is bounded by 3-D
   embeddability; the benchmark reports that ceiling next to every number.
2. **Trans placement is weakly determined** (run-to-run distance r ≈ 0.4 genome-wide, trans ρ ≈
   0.25–0.33): bulk inter-chromosomal contacts average over cell-to-cell territory arrangements.
   Report as is; the Lorentzian and trans-weight variants test sensitivity.
3. **10 kb × many runs** needs the restraint-force buffer split (or restraint forces recomputed per
   endpoint without the buffer) above ≈ 4 GiB per binding; 8 runs fit.
4. **Balancing fine stages on the band** (cis-only KR of pixels ≤ 200 bins apart) vs the genome-wide
   matrix: equivalent under the bias model; to be checked against cooler's weights on Sherlock.
5. **α**: 4 (imaging) vs fitted vs calibrated — the `*_afit` / `*_acal` tasks decide whether a
   data-driven α helps; ν = γ/α couples the two.
