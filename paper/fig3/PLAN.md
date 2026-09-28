# Figure 3 — Bridges between contacts and geometry: data and reproduction plan

Status: **data verified and staged; feasibility checks run; no figure yet** (2026-09-27).
Inputs are catalogued in `example-data/README.md` ("Figure 3 datasets"); feasibility scripts are in
`benchmarks/fig3/`, their raw outputs in `paper/fig3/feasibility/*.json`. All DOIs below were checked
against Crossref on 2026-09-27.

## Concept

In ChromData, sequencing contacts and imaging geometry are layers on one shared locus index (`bins`).
Fig. 3 shows that the bridges between the two are trustworthy **on real data, in the original papers'
own setups**:

- **a. Contacts → geometry.** Each reconstruction method in `uchrom.recon` is run on the dataset its
  original paper used and scored with that paper's metric, next to the original implementation (or, where
  it cannot run, the original authors' deposited structures).
- **b. Geometry → contacts.** Contact frequency computed from imaging distances vs real Hi-C of the same
  cell type and region (map correlation, distance-decay-removed correlation, P(s)), with cross-cell-type
  controls.
- **c. Joint reconstruction.** GEM-FISH with Hi-C plus a training subset of FISH, scored on held-out FISH
  (the paper's own 90/10 cell split).
- **(optional) e.** The reconstructions of one region stored side by side as `layers` of one ChromData.

Imputation is Fig. 4 and is not covered here.

## Findings of the data check that change the plan

1. **`example-data/IMR90_chr21_30kb.cool` is K562 Hi-C, not IMR90.** Its source 4DN file 4DNFI4QQPDMR is
   "in situ Hi-C on non-heat treated K562 cells" (set 4DNESU95RUNO, Ray et al. 2019, PNAS 116:19431,
   doi:10.1073/pnas.1901244116). Re-deriving chr21 at 30 kb from the downloaded mcool (md5 verified)
   reproduces the file exactly. Chr21 has 1.06 M contacts vs 9.2 M in real Rao 2014 IMR90. The catalog
   now says so; the file name is kept for the tests. Anything that used it as IMR90 (the GEM-FISH
   tutorial, `call_tads_di` test, `cd2_callers_validation.py`) was pairing IMR90 imaging with K562 Hi-C.
2. **The GEM-FISH tutorial (part 2) synthesises Hi-C from the FISH mean** — against the "never fabricate
   inputs" rule. Real Hi-C for that region now exists (`rao2014_imr90/`, below); the tutorial should be
   switched to it.
3. **`cell1.pairs` cited the wrong GEO series** (GSE80006 is Flyamer 2017). Stevens 2017 is **GSE80280**;
   fixed in the catalog. `cell1.pairs` is Stevens Cell 1 (every distinct contact is in the NucDynamics
   repo's `Cell_1_contacts.ncc`). `cell2.pairs.gz` (503,720 reads) does not match any GSE80280 cell file
   size and is marked unverified.
4. **U-Chrom "GEM" is not GEM.** `uchrom.recon.sc.gem` has GEM's stretch / bend terms but no manifold
   learning (no KL divergence, no Hi-C probability distribution, no conformation mixture) and uses
   the inverse-power-law distance restraints that GEM was designed to avoid. GEM itself (Zhu et al. 2018)
   is in *Nucleic Acids Research*, not Nat Commun, and was benchmarked on bulk Hi-C, not single-cell Hi-C.
5. **Two library bugs found and fixed in this PR** (each with a test):
   - `uchrom.io.count_contacts` sorted the (particle_1, particle_2) array with `axis=0`, i.e. each column
     independently, scrambling which particles every scHi-C contact joins (feeds both NucDynamics and
     "GEM"). Now `axis=1`. Effect on Cell 1 at 100 kb: contacts violated by > 5 radii 11 % → 0 %,
     model-to-model RMSD 5.3 → 2.6 radii (panel a). The in-repo `sim_cell1` structure was built with the
     bug and should be rebuilt (`build_sim_cell1.py`) in a follow-up.
   - `reconstruct_gem_fish(tads=...)` crashed when the TAD windows leave gaps (as the Wang 2016 TADs do):
     coordinates were built for the TAD bins, spots for every bin. Spots now cover the TAD bins only.
6. **Further NucDynamics port defects (not fixed here, listed for the port PR)**, from a line-by-line
   comparison with `tjs23/nuc_dynamics` master (the 2017 code): velocity half-step
   `vel += 0.5 + dt*(…)` instead of `0.5*dt*(…)`; temperature from |v| instead of m·|v|²; velocities never
   initialised; 500 steps per stage instead of 500 × 100 with dt·20.458; repulsion and far-restraint
   force formulas differ; no isolated-contact filter; violated-contact removal at every stage from a
   single structure; short-range contacts (|i−j| < 2) dropped; particles not aligned to the genome and
   off-chromosome positions wrapped to the last particle; non-uniform random start; one model instead
   of an ensemble (paper: 20 at 4 Mb, best 10 kept); float32.

## Panel a — contacts → geometry

| Method (U-Chrom) | Original paper | Paper's benchmark data | Paper's metric and numbers | Original code | Status here |
|---|---|---|---|---|---|
| NucDynamics `recon.sc.nucdyn` (Taichi) | Stevens et al. 2017, *Nature* 544:59, doi:10.1038/nature21429 | 8 haploid mESC G1 cells, GEO **GSE80280** (mm10); contacts 31–112 k per cell | Ensemble precision: RMSD between models < 1.75 particle radii at 100 kb (ED Table 2, Cell 1 0.41 … Cell 7 1.75); restraints violated > 4 radii: 0.02–0.42 %; 10–70 % contact drop-out keeps the fold (RMSD < 2.5) | github.com/tjs23/nuc_dynamics, Python + Cython, LGPL-3.0. **Builds** in a venv with cython < 3, numpy < 2; runs on `cell1.pairs` (converted to NCC). A full default run ≈ 5 h per model on 1 core (models parallel); 10 models to 2 Mb: 12 min | Data: **downloaded** (`stevens2017_mesc/`, 43 MB: contacts + the paper's 10 published 100 kb models per cell) |
| "GEM" `recon.sc.gem` (Taichi) | Zhu et al. 2018, *Nucleic Acids Res* 46:e50, doi:10.1093/nar/gky065 | Bulk Hi-C: Lieberman-Aiden 2009 chr14 1 Mb (GSE18199), Rao 2014 GM12878 chr19 5 kb, Dixon 2012 chr21 40 kb vs Wang 2016 FISH; yeast; simulations | chr14 10-fold CV Pearson 0.931 (MDS 0.340, ChromSDE 0.756, ShRec3D 0.680); chr21 relative error vs FISH 0.183 | github.com/mlcb-thu/GEM — **MATLAB only, no licence file**; ships chr14 1 Mb example. **Cannot run here** (no MATLAB; Octave untested) | The U-Chrom code is not GEM (finding 4) → cannot be compared as GEM |
| MDS / SMACOF `recon.bulk.mds` (PyTorch) | miniMDS: Rieber & Mahony 2017, *Bioinformatics* 33:i261, doi:10.1093/bioinformatics/btx271 | Rao 2014 **GM12878** in situ, MAPQ ≥ 30, KR; chr22 at 1 / 10 / 100 kb; all chromosomes at 10 kb | Pearson(input c^−1/4 distances, structure distances): chr22 100 kb miniMDS ≈ 0.80 (mMDS / cMDS ≈ 0.90); all chromosomes 10 kb 0.42–0.63; chr22 10 kb runtime ≈ 1 min; values read off figures | github.com/seqcode/miniMDS, Python 3, MIT. **Runs** (full mode in the main env; `--partitioned` needs numpy < 2 venv) | Data: GM12878 `.hic` is 51 GB → **to slice** (`build_rao2014_slices.py --cell GM12878 --chroms 22`) |
| GEM-FISH `recon.fish` (PyTorch) | Abbas et al. 2019, *Nat Commun* 10:2049, doi:10.1038/s41467-019-10005-6 | Rao 2014 IMR90 5 kb (MAPQ ≥ 30, KR) + Wang et al. 2016 (*Science* 353:598, doi:10.1126/science.aaf8084) multiplexed FISH of TAD centres: chr20 (30 TADs), chr21 (34, 120 cells), chr22 (27), chrX | Mean relative error vs FISH, final model: chr20 0.16, chr21 0.14, chr22 0.16, Xa 0.16, Xi 0.21 (GEM Hi-C only: 0.30 / 0.30 / 0.20 / 1.37 / 1.93); held-out 10 % of cells: chr21 0.188 ± 0.010; A/B assignment 32/34 (chr21) | github.com/ahmedabbas81/GEM-FISH, MATLAB, MIT. **Cannot run here** (no MATLAB), **but ships all inputs and the final 5 kb models** of chr20/21/22 | Data: **downloaded** (`abbas2019_gemfish/`, 40 MB) + Hi-C **built** (`rao2014_imr90/`) |

### Feasibility numbers (real data, small scale)

*NucDynamics, Stevens Cell 1 (`cell1.pairs`, 105,700 reads), 8 Mb → 100 kb, 25,654 particles, CPU (18 cores):*

| | U-Chrom before `count_contacts` fix | after fix | Published models (GEO) |
|---|---|---|---|
| Runtime per model | 63–74 s, 0.4 GB | 69 s, 0.4 GB | (original code: ≈ 5 h per model, 1 core) |
| Median 3-D distance of input contacts (radii) / same-separation background | 2.32 / 2.42 | 1.24 / 2.36 | — |
| Contacts ≤ 1.2 radii / > 5 radii | 16 % / 11 % | 43 % / 0.0 % | — |
| Model-to-model RMSD, genome (radii), 2 seeds | 5.32 | 2.62 | 0.62 (0.50–0.75; paper reports 0.41) |
| Distance-matrix r between models (median chrom) | 0.956 | 0.928 | 0.999 |
| vs published models: RMSD (best of mirror) / distance-matrix r (median chrom) | 16.2 / 0.70 | 13.4–13.9 / 0.75 | — |

*"GEM", Cell 1, 1.28 Mb (2,000 particles), 10,000 steps:* 5–6.5 min per model on CPU; contacts median
1.16 vs background 1.20; model-to-model RMSD 1.91, distance-matrix r 0.71. No original to compare against.

*MDS vs miniMDS, real Rao 2014 IMR90 chr21 (4DN 4DNFIR1JDZH7, range-read, ICE):*

| Resolution | miniMDS time | U-Chrom time (CPU) | U-Chrom vs miniMDS: distance r / RMSD (Rg units) | miniMDS seed vs seed | Fit to Hi-C (Spearman), miniMDS / U-Chrom |
|---|---|---|---|---|---|
| 100 kb (320 bins) | 7.7–9.1 s | 0.73 s | 0.953 / 0.45 | 0.944 / 0.50 | 0.923 / 0.922 |
| 25 kb (1,287 bins) | 24–30 s | 1.72 s | 0.999 / 0.05 | 0.999 / 0.06 | 0.738 / 0.737 |
| 25 kb, partitioned | 12.1 s | 1.24 s | 0.863 / 0.40 | 0.924 / 0.57 | 0.691 / 0.638 |

Full MDS matches miniMDS within miniMDS's own seed spread, 10–20× faster. **Partitioned mode does not**:
U-Chrom's `procrustes_alignment` forbids reflections, miniMDS allows them (patching reflection in
raised the fit 0.637 → 0.665); the TAD partitioner also differs and 6–7 bins are dropped.

*GEM-FISH, paper setup (chr21, Wang 2016 34 TADs × 120 cells, 90/10 cell split; Rao 2014 IMR90 5 kb,
MAPQ > 0, ICE instead of MAPQ ≥ 30 + KR):*

| Model (`c_gemfish_wang2016.py`, split 0) | Relative error, training cells | Relative error, held-out 10 % | Pearson / Spearman vs held-out | Runtime (CPU) |
|---|---|---|---|---|
| Paper's final model (repo, nm, no rescaling) | 0.143 (paper Table 1: 0.14) | 0.173 (paper Supp. Table 9: 0.188 ± 0.010) | 0.784 / 0.762 | (MATLAB; not run) |
| U-Chrom GEM-FISH, Hi-C only | 0.302 (paper's GEM: 0.30) | 0.340 (paper's GEM: 0.362) | 0.580 / 0.557 | 403 s |
| U-Chrom GEM-FISH, Hi-C + training FISH | 0.188 | 0.217 | 0.712 / 0.683 | 411 s |

U-Chrom models are in reduced units and get one least-squares scale fitted on the training FISH (the
paper's model gets none), which favours U-Chrom slightly. One split only here; the final panel uses 10.
Runtime is dominated by the dense 9.6 k × 9.6 k chromosome matrix on CPU (high system time); 6,364 model
bins, identical to the paper's model.

### Plan for panel a

- **NucDynamics**: fix the port (finding 6), add a multi-model ensemble, then run all 8 Stevens cells at
  the paper's schedule; plot (i) ensemble RMSD per cell vs ED Table 2, (ii) U-Chrom vs published-model
  RMSD / distance r per cell (ceiling: published model vs published model), (iii) runtime vs the original
  (original timed on a subset of stages, extrapolated and labelled as such).
- **GEM**: either (A, recommended) re-implement GEM's actual objective (KL of Student-t 3-D kernel vs
  Hi-C probabilities + conformational energy, M conformations) in PyTorch — the MATLAB core is ~200
  lines — and reproduce the chr14 1 Mb 10-fold CV Pearson (0.931) on the example that the GEM repo ships,
  or (B) rename the current module to a generic restraint-based minimiser and drop "GEM" from the figure.
  Without MATLAB, the comparison is to the paper's numbers only.
- **MDS**: slice GM12878 chr22 (100 kb and 10 kb, MAPQ ≥ 30 KR — needs a `--norm KR --mapq30` option in
  `build_rao2014_slices.py`) and reproduce the input–output Pearson (≈ 0.80 at 100 kb) and runtime,
  miniMDS run side by side; fix the reflection in partitioned alignment first.
- **GEM-FISH**: see panel c; for panel a, report the Hi-C-only and Hi-C+FISH relative error on chr20/21/22
  next to the paper's Table 1 and the shipped final models (which reproduce Table 1: 0.163 / 0.143 / 0.156).

## Panel b — geometry → contacts

Claim: contact frequency computed from imaged distances reproduces bulk Hi-C of the **same** cell type,
beyond the distance-decay that any two maps share.

| Pairing | Imaging (accession, size, status) | Hi-C (accession, size, status) | Paper reference |
|---|---|---|---|
| IMR90 chr21:28–30 Mb, 65 × 30 kb | Bintu 2018 (doi:10.1126/science.aau1783), GitHub `Data/IMR90_chr21-28-30Mb.csv`, 7.8 MB, 4,871 chr — **downloaded** | Rao 2014 IMR90 (GSE63525 `IMR90_combined.hic`, 13 GB) → chr21 5 kb slice 3.8 MB — **built** | Bintu Fig. 1J: median distance vs Hi-C ρ = −0.96 |
| K562 chr21:28–30 Mb | Bintu 2018 `K562_chr21-28-30Mb.csv`, 20 MB, 13,996 chr — **downloaded** | Rao 2014 K562 (`K562_combined.hic`) → slice — **built** | — |
| IMR90 chr21:18.6–20.6 Mb | Bintu 2018 `IMR90_chr21-18-20Mb.csv`, 2 MB, 1,277 chr — **downloaded** | same IMR90 slice | — |
| IMR90 whole chr21, 651 × 50 kb | Su et al. 2020 (doi:10.1016/j.cell.2020.07.032), Zenodo 3928890, 261 MB, 7,591 chr — **downloaded** | the authors' own binned Rao 2014 IMR90 (same Zenodo record, 1 MB) — **downloaded** | — |
| mESC, 20 chromosomes × 60 × 25 kb | Takei 2021 (doi:10.1038/s41586-020-03126-2), 4DN 4DNFIHF3JCBY, 22 MB — **already present** | Bonev 2017 (doi:10.1016/j.cell.2017.09.043) G1 mESC, 4DN 4DNFIC21MG3U, 12.6 GB — **range-read** (only the 20 windows, 25 kb, ~30 s) | Takei 2021: Spearman −0.84, median distance vs Hi-C, 146,741 pairs |

### Feasibility numbers (`b_first_look.py`, `b_takei_bonev.py`)

Pearson of log10 imaging contact frequency (d < 200 nm) vs log10 Hi-C over off-diagonal pairs; "O/E" is the
same after dividing every diagonal by its mean (distance-decay removed); median distance vs Hi-C is log–log.

| Pairing | log–log r | O/E r | median distance vs Hi-C r | P(s) slope, imaging / Hi-C |
|---|---|---|---|---|
| IMR90 28–30 Mb, matched | 0.968 | 0.809 | −0.975 (paper −0.96) | −1.02 / −1.49 |
| K562 28–30 Mb, matched | 0.922 | 0.579 | −0.927 | −0.85 / −1.27 |
| IMR90 imaging vs **K562** Hi-C (control) | 0.886 | 0.363 | −0.878 | — |
| K562 imaging vs **IMR90** Hi-C (control) | 0.933 | 0.618 | −0.938 | — |
| IMR90 18.6–20.6 Mb, matched | 0.900 | −0.06 | −0.919 | −0.35 / −0.59 |
| IMR90 whole chr21 (Su 2020, authors' Hi-C) | 0.840 | 0.603 | −0.877 (mean distance) | −0.63 / −1.11 (300 nm, 0.1–10 Mb) |
| mESC 20 × 1.5 Mb (Takei vs Bonev), pooled 35,399 pairs | 0.885 (Spearman 0.910) | — | Spearman −0.931 (paper −0.84 on a larger pair set) | — |

Honest reading: raw correlations are high for every pairing, **including mismatched cell types**, because
distance-decay dominates. The distance-decay-removed correlation separates them for IMR90 imaging
(0.81 matched vs 0.36 with K562 Hi-C) but **not for K562 imaging** (0.58 matched vs 0.62 with IMR90 Hi-C).
The 18.6–20.6 Mb region (gene-poor, low Hi-C coverage) has no signal beyond distance-decay. P(s) from
imaging is shallower than Hi-C at every radius (a known saturation of distance-threshold contacts).

### Plan for panel b

Main: IMR90 chr21:28–30 Mb (heat maps imaging vs Hi-C, upper/lower triangle) + whole-chr21 Su 2020 +
mESC Takei/Bonev scatter; a summary bar of O/E r for matched vs mismatched pairs with a trace-bootstrap
CI; P(s) curves at several radii. Report the K562 result as is. Replace the fixed radius by a sweep and
show the chosen one is not cherry-picked.

## Panel c — joint reconstruction (GEM-FISH), held-out FISH

Data: exactly the paper's — Wang 2016 chr20/21/22 TAD FISH from the GEM-FISH repo and Rao 2014 IMR90 Hi-C.
chrX FISH is not in the repo (the Science supplement returns HTTP 403 to scripts; retrieve manually if Xa/Xi
are wanted). Metric: mean relative error on the 10 % held-out cells, 10 splits (paper Supp. Table 9:
chr20 0.210 ± 0.014, chr21 0.188 ± 0.010, chr22 0.205 ± 0.011; GEM 0.352 / 0.362 / 0.237), plus the A/B
assignment of TADs (Table 2). Reference model: the repo's final structures, scored with our code:
chr21 relative error 0.143 on all cells, 0.173 on a 10 % held-out split (split 0).

A second, finer check uses Bintu 2018 chr21:18.6–20.6 Mb (65 × 30 kb, trace-level split 50/50;
`c_gemfish_first_look.py`): Hi-C-only model vs held-out FISH median distances Pearson 0.847, Hi-C + FISH
0.800 (worse), Hi-C matrix alone (no model) Spearman 0.867, FISH half vs half 0.956. So on this region the
current port's FISH terms do not help — to be revisited after the port is aligned with the paper.

Needed port changes before panel c (from the code comparison with the MATLAB original): joint KL with the
(1 + d²)⁻¹ kernel (the port uses row-wise KL with (1 + d)⁻¹); Wang TAD windows instead of DI calls; FISH
target = mean over cells (port: median); TAD-level Hi-C = size-normalised block mean on KR 5 kb (port: block
sum); Rg target from the chromosome-volume scaling (port: per-TAD spot Rg², which is undefined for one spot
per TAD, so the Rg term is silently off); FISH-fitted bond lengths and assembly fallback (chr21 a = 0.038,
b = 0.21; port: c = 1, β = 0.5); λ in consistent units.

## External baselines: HIPPS (panel c) and DIMES (panel b)

Code: the authors' repository github.com/anyuzx/HIPPS-DIMES (Guang Shi; MIT), commit `beee45d` (2026-09-25,
package 4.0). Cloned, not vendored; imported from the clone by `--hipps-dimes PATH` (its dependencies are all
in the U-Chrom environment; its own `tests/test_basic.py` pass there: 62 passed, 3 skipped). Citations: HIPPS
is Shi & Thirumalai, *Phys Rev X* 11:011051 (2021), doi:10.1103/PhysRevX.11.011051; the contact–distance
relation it builds on is *Nat Commun* 10:3894 (2019) — the `hipps` key planned for `refs.bib` points to the
2019 paper, which is not the structure method. DIMES is *Nat Commun* 14:1150 (2023).
Scripts: `benchmarks/fig3/c_hipps_wang2016.py`, `benchmarks/fig3/b_dimes.py`; results in
`paper/fig3/results/`. All runs on one 18-core Mac shared with other jobs (load average 70–110 during the
runs), so wall times are indicative only and inflated for every method.

### Panel c — HIPPS as the Hi-C-only baseline

Parameters (paper / code defaults, none tuned on FISH): α = 4 (<r> ∝ p^−1/4), p normalised by its maximum,
maximum-entropy fit by iterative scaling, learning rate 10, 10,000 iterations, 1,000 conformations; TAD
distance = ensemble mean distance. Hi-C: the same `rao2014_imr90/IMR90_chr<N>_5kb_hg19.cool` slices and ICE
balancing (`ignore_diags=1`) as `c_gemfish_wang2016.py` (chr20 / chr22 slices built for this PR). Two ways to
reach the TADs, both HIPPS's own: **TAD level** = HIPPS block average (PRX App. C) of balanced 5 kb contacts
over each TAD × TAD block, then HIPPS on the 27–34 TADs; **100 kb** = the paper's resolution, raw counts
summed to 100 kb, balanced, empty bins dropped (330–576 loci), TAD distance = mean over bin pairs (as for the
U-Chrom and GEM-FISH models). Scoring is imported from `c_gemfish_wang2016.py`: same 90/10 cell splits
(`default_rng(0)`, splits 0–2), relative error vs mean FISH, one least-squares scale fitted on the training
FISH for every model except the paper's (nm). U-Chrom was re-run here for the same three splits on chr20/21/22
(`c_gemfish_wang2016.py --chrom N`, new option; chr21 split 0 reproduces the feasibility numbers exactly).

Mean relative error, mean of 3 splits (held-out SD across splits 0.002–0.021):

| chrom | model | training cells | held-out 10 % | Pearson (held-out) | paper (Table 1 / Supp. Table 9) |
|---|---|---|---|---|---|
| chr20 | U-Chrom GEM-FISH, Hi-C only | 0.359 | 0.373 | 0.63 | GEM 0.30 / 0.352 |
| chr20 | U-Chrom GEM-FISH, Hi-C + FISH | 0.214 | 0.235 | 0.67 | GEM-FISH 0.16 / 0.210 |
| chr20 | **HIPPS, TAD level (Hi-C only)** | **0.122** | **0.157** | 0.65 | — |
| chr20 | HIPPS, 100 kb (Hi-C only) | 0.129 | 0.158 | 0.66 | — |
| chr20 | GEM-FISH paper final model (repo) | 0.163 | 0.193 | 0.69 | |
| chr21 | U-Chrom GEM-FISH, Hi-C only | 0.303 | 0.325 | 0.65 | GEM 0.30 / 0.362 |
| chr21 | U-Chrom GEM-FISH, Hi-C + FISH | 0.188 | 0.216 | 0.72 | GEM-FISH 0.14 / 0.188 |
| chr21 | **HIPPS, TAD level (Hi-C only)** | **0.108** | **0.160** | 0.68 | — |
| chr21 | HIPPS, 100 kb (Hi-C only) | 0.120 | 0.170 | 0.62 | — |
| chr21 | GEM-FISH paper final model (repo) | 0.144 | 0.171 | 0.80 | |
| chr22 | U-Chrom GEM-FISH, Hi-C only | 0.323 | 0.330 | 0.58 | GEM 0.20 / 0.237 |
| chr22 | U-Chrom GEM-FISH, Hi-C + FISH | 0.205 | 0.227 | 0.58 | GEM-FISH 0.16 / 0.205 |
| chr22 | **HIPPS, TAD level (Hi-C only)** | **0.076** | **0.123** | 0.73 | — |
| chr22 | HIPPS, 100 kb (Hi-C only) | 0.085 | 0.127 | 0.71 | — |
| chr22 | GEM-FISH paper final model (repo) | 0.156 | 0.173 | 0.75 | |

**HIPPS, with no FISH at all beyond the one scale factor, beats every U-Chrom model on every chromosome,
including U-Chrom Hi-C + FISH, and has a lower relative error than the GEM-FISH paper's own final model**
(which is Hi-C + all FISH, in nm; fitting it the same one scale changes nothing: 0.164 / 0.144 / 0.155). On
Pearson vs held-out FISH the paper's model stays best on chr20/21. Where the HIPPS gain comes from: its
target alone, Λ·p^−1/4 before the maximum-entropy step, already scores 0.106–0.130 (training) — the
power law on balanced Hi-C is simply a good predictor of Wang 2016 TAD distances; the max-ent step changes
the error by ≤ 0.007. With the PRX paper's length scale (Λ = 117 nm per 100 kb, fitted there to GM12878
chromosome volumes) and no FISH scale at all, the 100 kb model gives 0.153 / 0.128 / 0.329 (chr20 / 21 / 22),
so the absolute scale does not transfer to every chromosome. IS convergence (relative loss): TAD level
0.06–0.08, 100 kb 0.19–0.24; stopping at 1,000 iterations (PRX Fig. 11) changes the error by ≤ 0.008.
Consequence for the paper: panel c cannot claim that U-Chrom's joint Hi-C + FISH model is the best
predictor of held-out FISH; the port's Hi-C → distance step (finding list under "Needed port changes") is
the likely gap, since a single power law does better than the full current pipeline.

Runtime (wall, same loaded machine): HIPPS TAD level 3–8 s + 1–6 s Hi-C aggregation; HIPPS 100 kb
214–1,146 s (330–576 loci × 10,000 eigendecompositions); U-Chrom GEM-FISH 1,500–1,760 s per model at
6,289–6,364 5 kb bins (403 s for the same chr21 run on a quieter machine, see above).

### Panel b — DIMES vs U-Chrom's direct contact frequency

Input as in the DIMES paper (Eq. 10): the mean *squared* distance map of the traces (pair-wise NaN
exclusion, as for U-Chrom). Fit: the code's direct inversion (`DI`), which the HIPPS-DIMES README prescribes
for a valid mean-squared-distance map and which gives the same maximum-entropy model the paper's iterative
scaling (γ = 10) converges to, in one step (fit loss ~1e−14); where the code refuses DI because pair-wise
missing data make the map not a valid EDM (Bintu K562; 13 of 20 Takei chromosomes) it falls back to the
paper's IS, γ = 10, 10,000 iterations (final relative loss 0.05 K562; Takei median 0.08, max 0.27). The
paper's IS is also run on every map ≤ 100 loci as a check (`dimes_is`; same numbers within 0.01–0.04). On Su
2020 (651 loci) IS at γ = 10 does not converge (loss rises 0.67 → 0.97 over 300 iterations), DI is exact.
Contact frequency = fraction of 10,000 sampled conformations with d < r; the Gaussian model's analytic
contact probability (infinite ensemble) is also reported. Hi-C, radii and the metric code are those of
`b_first_look.py` / `b_takei_bonev.py`; U-Chrom numbers are recomputed in the same run and reproduce the
feasibility table. r = 200 nm (Takei 0.2 µm):

| Pairing | log–log r, U-Chrom | log–log r, DIMES (analytic) | O/E r, U-Chrom | O/E r, DIMES (analytic) |
|---|---|---|---|---|
| IMR90 28–30 Mb, matched | 0.968 | **0.973** (0.975) | 0.809 | **0.841** (0.854) |
| K562 28–30 Mb, matched | **0.922** | 0.907 (0.910) | **0.579** | 0.547 (0.552) |
| control: IMR90 imaging vs K562 Hi-C | 0.886 | 0.864 (0.864) | 0.363 | 0.227 (0.224) |
| control: K562 imaging vs IMR90 Hi-C | 0.933 | 0.914 (0.919) | 0.618 | 0.572 (0.592) |
| IMR90 18.6–20.6 Mb, matched | 0.900 | 0.893 (0.901) | −0.062 | −0.060 (−0.042) |
| Su 2020 IMR90 whole chr21 | **0.840** | 0.836 (0.858) | **0.603** | 0.574 (0.619) |
| Takei 2021 mESC vs Bonev (pooled, 35,399 pairs) | **0.885** | 0.818 (0.819) | **0.523** | 0.463 (0.464) |

Cell-type control, matched minus mismatched O/E: IMR90 imaging U-Chrom 0.809 − 0.363 = **0.45**, DIMES
0.841 − 0.227 = **0.61** (DIMES separates the cell types better); K562 imaging U-Chrom 0.579 − 0.618 =
−0.04, DIMES 0.547 − 0.572 = −0.03 (neither separates them). Reading: on the IMR90 28–30 Mb block —
the panel's main example — DIMES is better than direct counting on both metrics and on the control; on
K562, whole-chromosome Su 2020 (sampled ensemble) and Takei mESC, direct counting is better (Takei by
0.07 log–log, 0.06 O/E). On Su 2020 DIMES's analytic contact probability beats direct counting (0.858 /
0.619) while its 10,000-conformation ensemble does not (0.836 / 0.574): sampling noise at the low contact
probabilities of Mb-scale pairs. Spearman (not in the table) follows the same pattern (Takei 0.910 vs
0.844). Runtime: U-Chrom direct counting 0.9–7.9 s per Bintu block, 2.9 s for Takei, 173 s for Su 2020 (NaN-aware
pair-wise cube over 7,591 × 651 traces); DIMES fit 0.0–0.6 s (DI) / 20 s (IS, 65 loci) / 141 s (Takei, 20 fits),
plus 5–7 s (Bintu), 86 s (Takei) and 330 s (Su) to sample 10,000 conformations and count contacts.

## Panel e (optional) — layers

One ChromData for IMR90 chr21:28–30 Mb holding the Bintu traces (`coords`), the Hi-C (`link_cool`), and
consensus models from MDS, GEM-FISH (Hi-C only / + FISH) as `layers`, with a small table of their
distance-matrix correlations to the imaging median. Cheap once a and c exist.

## Risks and gaps

| Risk / gap | Consequence | What we do instead (no fabrication) |
|---|---|---|
| No MATLAB → GEM and GEM-FISH originals cannot run | No runtime or run-to-run comparison against the originals | Compare to the papers' numbers and to GEM-FISH's **deposited final models** (reproduce Table 1 with our scorer: done). Octave (Homebrew bottle, untested) is a possible route for GEM-FISH TAD level (~1 min in MATLAB). |
| U-Chrom "GEM" is not GEM | Cannot be labelled a GEM reproduction | Re-implement GEM (≈ 3–5 days) or rename and drop from Fig. 3 |
| NucDynamics port has ~10 algorithmic defects | Current structures are far from the published ones (RMSD 16.2 radii before the count fix, 13.4–13.9 after; distance r 0.70 → 0.75, published-vs-published 0.999) | Fix the port first; original code runs (Python/Cython), but slowly: time a few stages and extrapolate, compare the final structures to GEO's published models |
| GM12878 (51 GB) and Bonev mESC (12.6 GB) too large | — | HTTP range reads (`hicstraw` for `.hic`, `fsspec`+`h5py` for `.mcool`): only the needed blocks, tested |
| chrX Wang 2016 FISH not in the GEM-FISH repo | Xa / Xi rows of Table 1 cannot be reproduced | Autosomes only, or download the Science supplement manually |
| Bintu GitHub repo has no licence file | Redistribution unclear | Do not commit the CSVs; download on demand (as now) |
| Hi-C normalisation / MAPQ differ from the papers (MAPQ > 0 raw slices vs MAPQ ≥ 30 KR) | Small numeric differences | Add `--norm KR` / `_30.hic` to the slicer before the final runs |
| Cross-cell control fails for K562 imaging | Weakens "cell-type specific" claim | Report as is; claim only what IMR90 / Su / Takei support |
| `cell2.pairs.gz` provenance unverified | — | Not used in Fig. 3 |

## Estimated engineering effort

| Item | Effort |
|---|---|
| NucDynamics port fixes (finding 6) + ensemble + 8-cell run + original-code timing | 4–6 days |
| GEM: real re-implementation + chr14 CV reproduction (or rename, 0.5 day) | 3–5 days |
| MDS: reflection fix, GM12878 chr22 KR slices, miniMDS side-by-side | 1–2 days |
| GEM-FISH: align port with paper (list above), chr20/21/22, 10 held-out splits | 4–6 days |
| Panel b final (bootstrap CIs, radius sweep, figure-ready JSON) | 1–2 days |
| Panel e + figure assembly + legend | 2–3 days |
| Fix GEM-FISH tutorial (real Hi-C), rename / replace `IMR90_chr21_30kb.cool` | 1 day |
| **Total** | **≈ 3–4 weeks** |

## Recommendation for the panel set

a (NucDynamics vs Stevens deposited models; MDS vs miniMDS on the paper's GM12878 chr22; GEM-FISH vs the
paper's Table 1) — b (IMR90 28–30 Mb + Su whole-chr21 + Takei/Bonev, with matched-vs-mismatched O/E) — c
(GEM-FISH held-out FISH on chr20/21/22) — e optional. Drop "GEM" from a unless it is re-implemented.

## Files

- `benchmarks/fig3/a_sc_consistency.py` — precision and contact consistency of scHi-C models
- `benchmarks/fig3/a_nucdyn_vs_published.py` — U-Chrom models vs Stevens 2017 GEO structures
- `benchmarks/fig3/mds_vs_minimds/` — miniMDS side-by-side (IMR90 chr21, range-read)
- `benchmarks/fig3/b_first_look.py`, `b_takei_bonev.py` — panel b
- `benchmarks/fig3/c_gemfish_wang2016.py` (`--chrom 20|21|22`), `c_gemfish_first_look.py` — panel c
- `benchmarks/fig3/c_hipps_wang2016.py`, `b_dimes.py` — HIPPS / DIMES external baselines (panels c / b)
- `paper/fig3/results/*.json` — baseline runs and the matching U-Chrom runs (3 splits, chr20/21/22)
- `example-data/build_rao2014_slices.py` — Rao 2014 `.hic` slices over HTTP
- `paper/fig3/feasibility/*.json` — outputs of the runs above
