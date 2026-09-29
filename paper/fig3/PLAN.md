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
   now says so. Anything that used it as IMR90 (the GEM-FISH tutorial, `call_tads_di` test,
   `cd2_callers_validation.py`) was pairing IMR90 imaging with K562 Hi-C.
   **Resolved (data-hygiene PR):** renamed to `K562_chr21_30kb.cool` (no alias); the tests, the DI benchmark
   and the docs use it as a generic (K562) Hi-C matrix; the GEM-FISH tutorial moved to real IMR90.
2. **The GEM-FISH tutorial (part 2) synthesises Hi-C from the FISH mean** — against the "never fabricate
   inputs" rule. Real Hi-C for that region now exists (`rao2014_imr90/`, below); the tutorial should be
   switched to it. (The notebook code itself ran on the K562 cool; only its intro said "synthesises".)
   **Resolved:** part 2 now runs on Rao 2014 IMR90 chr21 (5 kb slice checked in, summed to 30 kb on the
   Bintu segment grid, hg19): Pearson 0.71–0.73, mean relative error 0.33–0.35 vs the FISH median distances
   (before, on K562: 0.77 / 0.35); Hi-C vs 1/distance Spearman over chr21 only 0.03 (K562: 0.16).
3. **`cell1.pairs` cited the wrong GEO series** (GSE80006 is Flyamer 2017). Stevens 2017 is **GSE80280**;
   fixed in the catalog. `cell1.pairs` is Stevens Cell 1 (every distinct contact is in the NucDynamics
   repo's `Cell_1_contacts.ncc`). `cell2.pairs.gz` (503,696 contacts) does not match any GSE80280 cell file
   size and is marked unverified. It carries hickit haplotype-phase columns (diploid, phased mouse cell), so it
   is not Stevens 2017 at all; source still unidentified; only `tests/smoke/fasthigashi_smoke.py` uses it.
4. **U-Chrom "GEM" is not GEM.** `uchrom.recon.sc.gem` has GEM's stretch / bend terms but no manifold
   learning (no KL divergence, no Hi-C probability distribution, no conformation mixture) and uses
   the inverse-power-law distance restraints that GEM was designed to avoid. GEM itself (Zhu et al. 2018)
   is in *Nucleic Acids Research*, not Nat Commun, and was benchmarked on bulk Hi-C, not single-cell Hi-C.
5. **Two library bugs found and fixed in this PR** (each with a test):
   - `uchrom.io.count_contacts` sorted the (particle_1, particle_2) array with `axis=0`, i.e. each column
     independently, scrambling which particles every scHi-C contact joins (feeds both NucDynamics and
     "GEM"). Now `axis=1`. Effect on Cell 1 at 100 kb: contacts violated by > 5 radii 11 % → 0 %,
     model-to-model RMSD 5.3 → 2.6 radii (panel a). The in-repo `sim_cell1` structure was built with the
     bug and should be rebuilt (`build_sim_cell1.py`) after the NucDynamics port PR (finding 6).
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
| `cell2.pairs.gz` provenance unverified (phased diploid mouse cell, not Stevens) | — | Not used in Fig. 3; only a manual FastHigashi smoke script uses it |

## Estimated engineering effort

| Item | Effort |
|---|---|
| NucDynamics port fixes (finding 6) + ensemble + 8-cell run + original-code timing | 4–6 days |
| GEM: real re-implementation + chr14 CV reproduction (or rename, 0.5 day) | 3–5 days |
| MDS: reflection fix, GM12878 chr22 KR slices, miniMDS side-by-side | 1–2 days |
| GEM-FISH: align port with paper (list above), chr20/21/22, 10 held-out splits | 4–6 days |
| Panel b final (bootstrap CIs, radius sweep, figure-ready JSON) | 1–2 days |
| Panel e + figure assembly + legend | 2–3 days |
| ~~Fix GEM-FISH tutorial (real Hi-C), rename / replace `IMR90_chr21_30kb.cool`~~ (done) | — |
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
- `benchmarks/fig3/c_gemfish_wang2016.py`, `c_gemfish_first_look.py` — panel c
- `example-data/build_rao2014_slices.py` — Rao 2014 `.hic` slices over HTTP
- `paper/fig3/feasibility/*.json` — outputs of the runs above

## Decisions after the mock (2026-09-27)

- **Related work in the text.** Panel c's discussion cites IGM (Boninsegna et al. 2022, `igm`) as the
  other method that joins Hi-C with FISH distances, next to GEM-FISH (`gemfish`). Panel b cites HIPPS
  (Shi & Thirumalai, Phys Rev X 2021, `hipps`; the 2019 FISH–Hi-C paradox paper is `fishhicparadox`) and DIMES (Nat Commun 2023, `dimes`) as the maximum-entropy link between
  imaged distances and contact maps. All four are in `paper/manuscript/refs.bib`, checked on Crossref.
  IGM is not run here (≈ 1 week of work; not needed for the claim).
- **NucDynamics gets a speed panel.** Next to accuracy vs the published models, panel a shows wall time
  per ensemble: original `nuc_dynamics` (single core and its own parallel mode) vs U-Chrom on CPU and
  GPU (Taichi), on the same Stevens cell and schedule; any extrapolated original timing is labelled.
- `uchrom.recon.sc.gem` is renamed (not GEM) and dropped from the figure.
