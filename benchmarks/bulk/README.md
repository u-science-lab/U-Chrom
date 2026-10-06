# bulk — population deconvolution of bulk Hi-C: inputs, benchmark, real data

Data side and evaluation of the population deconvolution
`uchrom.recon.bulk.deconv.deconvolve(method="igm")` (the IGM A/M protocol on the native engine,
`uchrom.recon.bulk.deconv.igm`, built on the engine branch).  Specification of the original
algorithm: `pgs_spec.md`; design and the validation plan (a)–(d): `design.md` section 7.
Datasets: `example-data/README.md`, section "Bulk Hi-C deconvolution benchmark".

Everything here is standalone numpy / scipy / pandas (+ cooler / h5py / fsspec for real Hi-C,
scikit-learn optional for the classifier test) so it runs in the Sherlock `venv-main`, which
has no U-Chrom install: `_common.load_preprocess()` loads the one library module it needs,
`packages/uchrom/uchrom/recon/bulk/deconv/preprocess.py`, from its file path.  Only `run_deconv.py` (the
deconvolution) and reading ChromData outputs need U-Chrom.

| file | what |
| --- | --- |
| `packages/uchrom/uchrom/recon/bulk/deconv/preprocess.py` | **library**: Hi-C → haploid contact probabilities, IGM SI section 6 protocol (below); `ProbabilityMatrix` (symmetric CSR + bins + provenance, `.npz`) |
| `population.py` | population container `(S structures, P copies, L loci, 3)` + lamina; converters from the engine's arrays and from a ChromData population (cells = structures, traces = copies) |
| `truths.py` | imaging truth populations: Su 2020 genome-scale (primary), Su 2020 chr21, Takei 2021 1 Mb |
| `forward.py` | `truth`; `bulk`: population Hi-C = sum of per-cell contacts (infinite depth = exact IGM-pooled probabilities; finite depth = reads + bias + noise → raw fine matrix → preprocessing) |
| `bulk_metrics.py` | population-vs-population metrics (below) |
| `bulk_baselines.py` | HIPPS, contact-matched Gaussian, DIMES oracle, consensus MDS, random polymer, truth halves |
| `twins.py` | twin truths for the identifiability test |
| `score.py` | `score` (populations vs truth), `twin` (identifiable fraction) |
| `bulk_aggregate.py` | tidy tables `long.csv`, `headline.csv`, `gain.csv`, `twin.csv` |
| `real_inputs.py` | real Hi-C → IGM inputs (`preprocess`), Su 2020 Hi-C cross-check (`su_crosscheck`) |
| `kr_check.py` | KR balancing vs Juicer's KR vectors (HTTP range reads) |
| `run_deconv.py` | driver: input `.npz` → `deconvolve(method="igm")` → ChromData |
| `sherlock/*.sbatch` | jobs (`_env.sh` holds the paths) |
| `results/` | small checked-in results (KR check, laptop plumbing provenance) |
| `tests/` | `pytest benchmarks/bulk/tests` (~10 s, synthetic toys; library tests: `pytest tests/recon/test_deconv_preprocess.py`) |

## 1. Hi-C → contact probabilities (`uchrom.recon.bulk.deconv.preprocess`)

The IGM paper's own protocol (Boninsegna et al. 2022 SI section 6; `pgs_spec.md` 1.2), resolutions
as parameters (`IGMPreprocessParams`):

1. coverage filter at the fine resolution (20 kb): bins with coverage < 3 % dropped (see open issue 1);
2. **Knight–Ruiz** balancing at 20 kb (`kr_balance`: our implementation of Knight & Ruiz 2013
   `bnewt`, on the symmetric sparse matrix incl. the diagonal; `ice` / given `weights` / `none`
   also available);
3. `p = min(g / f_max, 1)`;
4. coarse matrix (200 kb or any coarse bins, e.g. bins centred on imaged loci): mean of the top
   10 % of each block's fine probabilities after removing values above `Q3 + 1.5 IQR`
   (alabtools `TopmeanSummaryMatrix` block statistics: zeros count, fine diagonal = 0, a zero
   fence → block mean; values equal to the fence are kept as the SI says — alabtools' strict `<`
   is `fence_inclusive=False`);
5. `f_max` fitted jointly (bracketed log-bisection) so that the mean non-zero row sum of the
   coarse matrix (entries < 0.001 zeroed) is 24 ± 1 % (unreachable targets are reported, not
   fatal: `rounds[*].target_reached`);
6. coarse inter-chromosomal probabilities > 0.2 → the fine bins of their fine inter entries > 0.2
   are removed and 2–5 repeated;
7. consecutive coarse bins → 1, diagonal → 1.

Input: sparse counts + bins, or a file (`preprocess_hic` / `load_contacts`: `.cool`, `.mcool`
path **or URL** (HTTP range reads of one level), `.hic` via hic-straw; a missing level is
summed from the finest dividing one, e.g. 10 kb → 20 kb, block by block).  Output: symmetric
CSR + coarse bins (`n_fine`, `n_fine_valid`, `masked`, `rowsum`) + provenance (per-round KR
convergence, `f_max`, averages, removed bins, pairs ≥ σ for σ = 1 … 0.01).

**KR check** (`kr_check.py`, laptop, range reads; `results/kr_check.json`): on the GEO Rao 2014
IMR90 `.hic` (Juicer's own KR vectors of exactly these counts), chr21 at 1 Mb / 50 kb / 25 kb and
chr1 at 1 Mb, our weights equal Juicer's up to one scale factor with max relative deviation
≤ 1.1e-7 (Pearson of log weights 1.0; same bins kept).  The KR vectors shipped in the 4DN mcools
(4DNFIR1JDZH7 IMR90, 4DNFIC21MG3U Bonev) correlate 0.996–0.9999 with ours but do **not** balance the
mcools' own counts (row-sum CV with the 4DN vector 0.008–1.45 vs ~1e-8 with ours): they were
computed on a different count matrix (4DN's `.hic` of the same pairs) — so do not use `bins/KR`
of those mcools as `balance="weights"`.

**Real-data plumbing** (laptop; `results/plumbing_imr90_chr21_22_igm200kb.json`): 4DN IMR90
chr21 + chr22 10 kb level range-read (11 s) → 20 kb (4,877 bins, 1.73 M pixels, 20.2 M
contacts) → 1,500 bins below 3 % coverage (the acrocentric p-arms and gaps) → KR (6 outer
iterations, max row deviation 1.6e-7) → `f_max` = 2.95e-3, 23.9 contacts / bin → 5 coarse inter
entries > 0.2 → 42 fine bins removed → round 2: `f_max` = 2.89e-3, 24.1, max inter 0.12;
489 coarse bins (132 fully masked).  Whole genome: `sherlock/build_real.sbatch`.

## 2. Truths and simulated population Hi-C

| dataset | structures × copies × loci | model bins | notes |
| --- | --- | --- | --- |
| `su2020_genome` | 1,787 × 2 × 1,041 | 3 Mb centred (also 1 Mb) | homologs resolved by the experiment; lamina distances; 16 % missing |
| `su2020_chr21` | 7,591 × 1 × 651 | the 50 kb loci | each chromosome copy = one structure (single-chromosome model in a territory sphere) |
| `takei2021_1mb` | 201 × 2 × 2,460 | 1 Mb centred | homologs split by `screcon/truth.split_homologs` (heuristic; flagged); a (cell, chromosome) is kept when the copies are ≥ 1 Rg apart and each has ≥ 40 % detection (3,262 of 3,819 kept; 43 % of positions missing); chrX / Y single copy |

`forward.py bulk`: contact kernel `step` (IGM's definition: centre distance < 2 (r_i + r_j)) or
`gauss` (mismatched); `rc` from IGM's bead radii (`--rc igm` default: occupancy 0.2 in a sphere of
the truth's median nuclear radius — sqrt(5/3) Rg of each cell's spots —, or `--rc-nm` /
`--rc-rel`).  **Infinite depth** = exact probabilities in IGM's pooling (cis: mean over structures
and same-copy combinations; trans: all copy combinations; missing positions left out).
**Finite depth**: reads ∝ kernel summed over *all* copy combinations and cells (homolog-crossing
cis contacts count, as in real Hi-C), multinomial + uniform noise (`--eps`) + log-normal
per-fine-bin bias (`--bias-sd`), each read end in a random one of `--fine-sub` fine bins → raw
fine matrix (`*.counts.npz`) → the IGM preprocessing onto the model bins (target = the truth's
own mean row sum, "oracle scale", or `--target 24`).  All outputs share the `ProbabilityMatrix`
`.npz` interface of real data.

Laptop truth extraction (`forward.py truth`, seconds): Su genome-scale — median consecutive-locus
distance 1,146 nm, nuclear radius (Rg sphere) 7.5 µm; Su chr21 — 336 nm, territory radius 1.2 µm;
Takei 1 Mb — 653 nm, 6.3 µm.  IGM bead radius for 3 Mb centred bins at occupancy 0.2: 353 nm,
contact distance rc = 1.41 µm.

## 3. Metrics (`bulk_metrics.py`, R vs T on T's loci)

Copy labels are arbitrary: cis distance samples pool same-copy combinations, trans samples all
copy combinations; R is rescaled by **one global factor** (least squares on per-pair medians,
reported), lengths in the truth's unit (median consecutive-locus distance).

1. **per-pair distributions**: W1 (100 quantiles, all pairs) and exact KS (20,000 stratified
   pairs); median / IQR, by cis separation band (0–1, 1–2, 2–5, 5–10, 10–20, 20–50, > 50 Mb) and
   trans; Spearman of per-pair medians;
2. **held-out contact frequencies** P(d < r) at r = 0.5 rc and 2 rc (the fit uses rc): MAE, log
   Pearson, cis / trans;
3. **three-body**: intra-chromosomal triplets stratified by span (and the set with all three input
   probabilities ≥ σ = 0.01): `p3` = P(all three pairs < rc), `coop` = P(ik | ij, jk) − P(ik); MAE
   and Spearman;
4. **radial**: distance to the structure centroid / structure RMS radius, W1 per locus and
   Spearman of per-locus means; **lamina** (Su genome-scale; R needs `meta.nucleus`): Spearman of
   per-locus mean lamina distance, W1 of normalised lamina distances;
5. **subpopulations**: features = log distances of 2,000 stratified pairs (cis: mean over copies;
   trans: min over combinations), imputed / standardised / PCA-20 on T; k-means on T (k = 2–8 by
   silhouette, fixed before R), R → nearest T centroid, total variation of proportions;
   **C2ST**: histogram gradient boosting (scikit-learn; numpy logistic regression otherwise),
   5-fold AUC on balanced samples;
6. **nearest true cell**: RMSD after similarity superposition (mirror) with per-chromosome
   diploid copy matching (alternating fit / assignment from three starts incl. an internal-shape
   match), / Rg(T cell), 20 feature-space candidates, 500 query structures; and the reverse
   (coverage).

**Baselines** (`bulk_baselines.py`), same input unless marked: **HIPPS** (⟨r⟩ = p^−1/4 → max-ent
Gaussian), **contact-matched Gaussian** (Maxwell inversion of f at rc, refined so the realised
probabilities match) — both pairwise-only; **DIMES oracle** (Gaussian with the truth's diploid
second moments; *oracle*); **consensus** (SMACOF on p^−1/4, replicated with 5 % noise; `--consensus-engine uchrom`
= `uchrom.recon.bulk.mds.run_mds`; miniMDS itself is not run here); **random polymer**
(floor); **truth half A vs half B** (ceiling).  Input-based Gaussians: homolog pairs get
`v_i + v_j` fitted to the trans values; targets are fitted by relative least squares on the
covariance factor (the plain PSD projection lets noisy long-range targets wreck short-range
structure: on a toy the cis contact error dropped from 0.37 to < 0.03).

**Information gain over pairwise-only** (`gain.csv`): per loss metric M,
`(M_pw − M_R) / (M_pw − M_ceiling)`, M_pw = the better of HIPPS / contact-Gaussian; 1 = the
deconvolution reaches the truth-half ceiling, 0 = no better than a pairwise-only ensemble,
< 0 worse.  `gain_over_oracle` uses the DIMES oracle instead (a method that beats it extracts
higher-order information that no pairwise-only Gaussian has).  C2ST uses |AUC − 0.5|.

## 4. Twin truths (`twins.py`)

* `gaussian`: the max-ent Gaussian whose pairwise contact probabilities at rc equal the
  truth's (the contact-matched Gaussian applied to the truth's exact input) — pairwise map
  matched, all higher-order structure Gaussian;
* `chrom_shuffle`: new cells assembled from whole chromosomes (both copies) of independently
  drawn truth cells, each cell centred on its centroid — every intra-chromosomal statistic of
  any order and each chromosome's radial position preserved exactly in distribution, inter-
  chromosome coupling destroyed (trans pairwise frequencies change; reported as `pair_match`).
  On a 100-cell Su subset: cis contact MAE 0.030 (resampling noise), trans Pearson 0.31 at rc.
  Gaussian twin of a 190-copy Su chr21 subset: contact MAE 0.020 at rc (Pearson 0.94), 0.097 at
  2 rc — it is matched at the fit's rc only, by construction.

The same pipeline runs on truth and twin; `score.py twin` reports higher-order distances
(three-body MAE, cluster TV, C2ST |AUC − 0.5|) between the truths (d_T) and between the
reconstructions (d_R); **identifiable fraction** d_R / d_T (≈ 0: prior-driven).  The
pairwise-only baselines on the two inputs are the negative control.

## 5. Commands

Laptop (tests, plumbing; < 2 min each):

```bash
pytest tests/recon/test_deconv_preprocess.py benchmarks/bulk/tests
python benchmarks/bulk/kr_check.py --out kr.json                     # range reads, ~2 min
python benchmarks/bulk/real_inputs.py preprocess --source <4DNFIR1JDZH7 URL> --chroms chr21 chr22 \
    --fine 20000 --coarse 200000 --target 24 --out imr90_chr21_22.npz
python benchmarks/bulk/forward.py truth --dataset su2020_genome --out SIM/su/truth.npz   # 6 s
```

Sherlock: copy the repo to `$SCRATCH/uchrom-nd/repo` (`rsync -a --exclude .git ./ sherlock:$SCRATCH/uchrom-nd/repo/`);
data go to `$SCRATCH/uchrom-nd/data` (downloaded by the jobs).  Outputs under
`$SCRATCH/uchrom-nd/runs/bulk/{sim,real,base,models,scores,twin,tables}`.

| step | command (from `$SCRATCH/uchrom-nd/repo`) | resources |
| --- | --- | --- |
| setup | `sbatch benchmarks/bulk/sherlock/setup_bulk.sbatch` (wheels into venv-main, truths download, tests) | 2 CPU, 8 GB, 1 h |
| KR check (all chromosomes) | `sbatch benchmarks/bulk/sherlock/kr_check.sbatch` | 2 CPU, 32 GB, 3 h |
| (b) truths, simulated inputs, twins, manifest | `sbatch benchmarks/bulk/sherlock/sim_prepare.sbatch` | 16 CPU, 96 GB, ≤ 8 h |
| (c) real inputs IMR90 | `sbatch --export=ALL,CELL=imr90 benchmarks/bulk/sherlock/build_real.sbatch` (4.6 GB download, whole-genome 20 kb → 200 kb, Su-centred 3 Mb / 1 Mb, Su Hi-C cross-check) | 8 CPU, 192 GB, ≤ 12 h |
| (c) real inputs mESC | `sbatch --export=ALL,CELL=bonev --time=16:00:00 benchmarks/bulk/sherlock/build_real.sbatch` (12.6 GB) | 8 CPU, 192 GB, ≤ 16 h |
| manifest incl. real | re-run `sim_prepare.sbatch` after `build_real` (cached steps are skipped) | minutes |
| baselines | `sbatch --array=1-$N benchmarks/bulk/sherlock/baselines.sbatch` (`N` = lines of `manifest.tsv`) | 16 CPU, 64 GB, ≤ 4 h per input |
| deconvolution | `sbatch --array=1-$N --export=ALL,ENGINE_PY=<engine python> benchmarks/bulk/sherlock/deconv_igm.sbatch` (3 seeds × S ∈ {1k, 5k, 10k}; `SIZES`, `SEEDS`, `NUCLEUS_KW` overridable) | 1 H100, 8 CPU, 128 GB, ≤ 24 h |
| score | `sbatch --array=1-$N [--export=ALL,ENGINE_PY=...] benchmarks/bulk/sherlock/score.sbatch` | 16 CPU, 96 GB, ≤ 12 h |
| twins | `sbatch [--export=ALL,ENGINE_PY=...,S=1000,SEED=1] benchmarks/bulk/sherlock/twin_score.sbatch` | 16 CPU, 64 GB, ≤ 8 h |
| tables | `sbatch benchmarks/bulk/sherlock/aggregate.sbatch` → `tables/{long,headline,gain,twin}.csv` | 1 CPU, 8 GB |

Order: setup → sim_prepare → build_real (both) → sim_prepare again (adds the real rows) →
baselines + deconvolution → score → twin_score → aggregate.  Memory of `build_real` is set for
the whole-genome 20 kb matrix (~4·10⁸ pixels at 1·10⁹ contacts); use a bigmem partition if
192 GB is not enough.

### Plugging in the engine's output

`deconvolve(...)` returns a ChromData whose **cells are structures and traces chromosome copies**
(`traces["copy"]` when present, else the order of a cell's traces per chromosome); spots point at
the haploid bins.  `run_deconv.py --input X.npz --n-structures S --seed k --out Y.chromdata.zarr`
writes it; `score.py score --pop igm=Y.chromdata.zarr` (or `--pop-dir` of a model directory)
maps it onto the truth loci by bin midpoint (`population.from_chromdata`).  A raw engine
`.npz` with `coords (S, N, 3)`, `bead_bin`, `bead_copy`, `chrom` / `start` / `end` of the haploid
bins is read the same way (`population.from_arrays`).  For the lamina metric set
`Population.meta["nucleus"] = {"shape": "sphere", "radius": R}` (or `ellipsoid` semi-axes); the
ChromData path takes `uns["population_model"]` into `meta`.

### Aggregation alone

```bash
python benchmarks/bulk/bulk_aggregate.py --scores RUNS/bulk/scores --twin RUNS/bulk/twin --out RUNS/bulk/tables
```

## 6. Status and open issues

Built and tested on synthetic toys and on real data at laptop scale (KR vs Juicer, IMR90 chr21–22
preprocessing, Su genome-scale / chr21 / Takei 1 Mb truths, a 100-cell Su forward + baselines +
twin + scoring pass).  Nothing of (b)/(c) has been run at full scale; no deconvolution result
exists yet (engine branch).  Open:

1. **"sequence coverage < 3 %"** (SI step 1) is ambiguous; implemented as the bin's raw contacts
   relative to the median bin (or a given per-bin sequence-coverage array).  Check against the
   SI's numbers (290 of 154,423 bins removed by the inter filter) once the whole-genome build runs.
2. **Target contacts for non-200 kb bins**: 24 is the SI's packing argument for 200 kb beads at
   40 % occupancy; for 3 Mb / 1 Mb locus-centred bins and the simulated inputs the oracle target
   (truth mean row sum) is used; the right real-data rule for other bin sizes is open.
3. **Top-mean on sparse fine blocks**: with finite depth the top-10 % mean of a 10 × 10 block of
   noisy counts compresses the dynamic range (100-cell Su subset, 2·10⁷ reads: Pearson 0.78 but
   Spearman 0.34 vs the exact probabilities) — a property of the protocol worth quantifying on the
   full grid.
4. 4DN mcool KR vectors do not balance the mcool counts (above); the real inputs use our KR.
5. The Su 2020 cross-check uses the 4DN GRCh38 cooler (GEO `.hic` is hg19); the authors' bins are
   500 kb centred on the loci, i.e. two 250 kb bins exactly.
6. miniMDS itself is not run (the consensus baseline is SMACOF on the same power law, or U-Chrom
   MDS); nearest-true-cell copy matching is a heuristic upper bound on the optimal RMSD.
