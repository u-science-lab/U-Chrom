# screcon — neutral evaluation of single-cell Hi-C 3-D reconstruction (milestone M1)

Method-neutral tests for single-cell genome structures and runnable baselines.  Nothing
here scores a method by its own objective: the held-out test and the imaging-truth
simulation use pairs / loci fixed before any model exists, and every length is either in
the truth's units or in the model's own bead unit (median consecutive-particle distance).

The code is standalone (numpy / scipy / pandas; `uchrom_recon` for the native engine) so
it runs in the Sherlock `venv-main`, which has no U-Chrom install.  Reusable parts move to
`uchrom.recon.eval` later.

| file | what |
| --- | --- |
| `contacts.py` | read GEO (`chr_A pos_A chr_B pos_B`) / `.pairs` tables keeping raw lines, write subsets back byte-identical, `.pairs` for hickit, particle index (2017 convention: particle covers `(pos - size, pos]`), genomic grid |
| `metrics.py` | superposition (rigid / similarity, mirror), precision (ED Table 2), distance-matrix r, violations (NucDynamics-style and Si-C-style), ROC-AUC, PR-AUC, grouped bootstrap |
| `heldout.py` | held-out contact test: `split`, `score` |
| `truth.py` | imaging truth cells: Su 2020 chr21, Takei 2021 1 Mb (homolog split) and 25 kb |
| `simulate.py` | `truth`, forward model `reads` / `grid`, `score` vs truth with structure-free baselines |
| `baselines.py` | random-polymer ensemble on the held-out grid |
| `score_real.py` | unified real-data scoring (precision, both violation types, vs published models) |
| `run_nucdyn.py`, `run_nucdyn_original.py`, `run_sic.py`, `run_hickit.py` | baseline runners on any table, output the common `.npz` |
| `models_io.py` | NucDynamics PDB / N3D, Si-C `genome.pdb`, hickit `.3dg` → `.npz` |
| `aggregate.py` | tidy `heldout.csv`, `sim.csv`, `real.csv`, `summary.json` |
| `diploid*.py`, `run_diploid.py` | diploid (homolog-resolved) benchmarks: copy-chain convention and phased I/O, imaging-truth simulation with phasing, held-out on copy chains, Dip-C GM12878 references / phase hold-back, aggregation and the pre-registered test (`diploid_devlog.md`, `DIPLOID_TEST_RESULTS.md`) |
| `matched_data.py` | matched-modality inputs: structure sets on the 2,460 Takei 1 Mb loci (`data/takei2021_1mb_loci.csv`), Takei 2021 mESC / brain imaging (homolog copies), Nagano 2017 fend pairs → mm10 tables, models / Dip-C `.3dg` → sets |
| `matched.py` | matched-modality comparison: scHi-C structures vs imaging of the same cell type as distributions over cells (§6) |
| `sherlock/*.sbatch` | the jobs (`_env.sh` holds the paths) |
| `tests/` | `pytest benchmarks/screcon/tests` (~2 s; synthetic toys only check the scorers and I/O) |

Model file convention (`.npz`): `chrom` (N,), `pos` (N,) = particle end in the 2017
convention, `coords` (M, N, 3).

## 1. Held-out contact test (`heldout.py`)

* `split`: 10 % of the reads held out (seeded), `--folds 3` disjoint held-out sets;
  `train.txt.gz` keeps the input's header and lines unchanged, so every method reads it as
  it reads the original table.
* evaluation pairs at 100 kb (fixed at split time, identical for all methods):
  positives = bin pairs hit by a held-out read and no training read (cis |i−j| ≥ 2);
  negatives = never-contacted pairs, 10 per positive — cis at the **same chromosome and
  the same separation** (fallback: the same √2-spaced separation band, reported), trans
  keeping one anchor of the positive with the partner drawn from the other trans
  positives' anchors (`--trans-match shuffle`; `any` / `chrom_pair` available).
* Why: with exact separation matching any score that depends on the separation alone
  (P(s) prior, expected polymer distance, a random-walk ensemble in expectation) ties
  within each stratum, so its cis ROC-AUC is 0.5; `score` reports this check
  (`ps_baseline_cis_auc`, = 0.5 on Stevens cell 1).  Random trans pairs would let a
  per-bin prior win (the middle of a chromosome is closer to other chromosomes in any
  chain model): on a toy, random-polymer trans AUC 0.57 (`any`) vs 0.51 (`shuffle`).
* `score`: models mapped by genomic position; distances in bead units; scores =
  −(ensemble median distance) and fraction of models with d < 2 bead units; ROC-AUC,
  PR-AUC (chance = 1/11) overall / cis / trans / cis separation bands, 95 % bootstrap CI
  over positives with their negatives.  A bin with no particle counts as far (coverage
  is reported).

Plumbing check on real data (laptop, seconds): Stevens cell 1, fold 1 — 100,654 training
/ 11,184 held-out reads → 4,001 positives (3,303 cis, 698 trans), 40,010 negatives, no
fallbacks.  The published GEO models (built from *all* reads, so leaky — plumbing only):
cis AUC 0.755, trans 0.998; a random polymer: cis 0.497, trans 0.488.

## 2. Imaging-truth simulation (`truth.py`, `simulate.py`)

Truth sets (5 cells each, seed 1):

* `su2020_chr21` — Su et al. 2020 IMR90 chr21, 651 × 50 kb loci (Zenodo 3928890);
  copies with ≥ 95 % detection (4,084 eligible).
* `takei2021_1mb` — Takei et al. 2021 mESC seqFISH+ 1 Mb, 2,460 loci genome-wide (4DN
  **4DNFIFLJGGNR**; the catalog's `4DNFIHF3JCBY.csv` is the 25 kb dataset, 20 regions ×
  60 loci — available as `takei2021_25kb`).  The deposited 1 Mb table does not resolve
  homologs; `truth.split_homologs` (constrained 2-means) separates them; a chromosome is
  kept when the two clusters are ≥ 1 Rg apart and the kept copy has ≥ 60 % detection;
  chrX (male line) is single copy.  On the homolog-resolved 25 kb table the split puts a
  median 97.8 % of spots on the right homolog.  61 of 201 cells keep all 20 chromosomes.
  **Heuristic** — flagged in each truth's `meta`.
* missing loci: interpolated along the chain for the forward model only (flag
  `measured`); scoring uses measured loci only.

Forward model: p(d) = q·exp(−(d/rc)²) (also `step`, `sigmoid`); depth fixed (`--reads`,
`--reads-per-mb`: signal reads multinomial ∝ p) or Poisson(q·f(d)) per locus pair; a
fraction eps of the reads uniform over all locus pairs; positions uniform inside the
loci; rc in nm or relative to the median consecutive-locus distance (Su: 327 nm; Takei
1 Mb: ~640 nm).  Depths: Stevens 2017 has ~40 reads/Mb (haploid), Dip-C ~170/Mb;
the grid spans 10–160 reads/Mb (Takei) and 40–640/Mb (Su, 50 kb loci need more).

Score vs truth: RMSD after similarity superposition (scale by least squares, mirror
allowed) in nm and / Rg(truth), per-chromosome median; distance-matrix Pearson / Spearman
(whole, cis); ensemble-mean distance matrix and superposed mean structure; baselines:
`random_polymer`, `pop_mean` (mean distance per loci pair over the other imaged cells),
`pop_ps` (population mean distance vs genomic separation; trans = mean trans distance) —
distance matrices scored directly and embedded by classical MDS for the RMSD.
Smoke numbers (Su truth 1, 320 reads/Mb, rc = 1, eps = 0, native engine 4 models with a
shortened schedule): Spearman 0.95, RMSD/Rg 0.48; random polymer 0.26 / 0.88;
pop_mean 0.44 / 0.85.

## 3. Real-data scoring (`score_real.py`)

Precision (RMSD to superposed mean; also / bead unit), violations of the contacts the
models were built from — NucDynamics-style %V>3 / %V>4 (d > 1.2 n^−0.33 + 3 / + 4) in bead
units and in native units, Si-C-style % contact pairs > 2 bead units — and vs the
published GEO models (per-chromosome distance-matrix r, RMSD / Rg).  For the GEO cell-1
models: precision 0.414 radii (ED Table 2: 0.41), %V>4 native 0.81 (ED Table 2 "final"
0.22 — the table counts ambiguous restraints we do not have), Si-C-style 51.9 %
(median contact distance 2.04 bead units).

## 4. Baselines

| runner | method | notes |
| --- | --- | --- |
| `run_nucdyn.py` | U-Chrom native NucDynamics (CPU f64 / GPU f32) | schedule 8, 4, 2, 0.4, 0.2, 0.1 Mb truncated above `--res`, `--res` appended |
| `run_nucdyn_original.py` | nuc_dynamics master 778697a | NCC conversion as fig3; reads its **N3D** output (explicit chromosome names; PDB chain letters shift when a chromosome loses all particles) |
| `run_sic.py` | Si-C HEAD 2a4d445 shipped binaries | 1 kb preparation re-done in Python (the script needs MySQL's `replace`); ≤ 20 chromosomes (`insert_contract_assign.c`), integer kb with 2·res < 2 Mb → **no 1 Mb** (use 250 kb, compared at the truth loci); beads = whole chromosome from 0, contact-free beads interpolated (`interpolated` flag) |
| `run_hickit.py` | hickit 0.1.1 release binary (glibc ≥ 2.15, CentOS 7 OK) | Dip-C schedule, **haploid** (`-P1`, no `-S` / imputation); merged empty beads resampled to the grid |
| `baselines.py random_polymer` | random walks | floor of the held-out test |

Si-C and hickit have only been run on the laptop in parts: the Si-C binaries are Linux
x86-64 and could not be executed on macOS (the Python preparation is tested with a stub
binary; `sherlock/smoke.sbatch` is its first real run); hickit was built from source on
macOS for a smoke run (Su chr21, 50 kb: Spearman 0.89 vs truth).

## 5. Sherlock runs

Copy the repo to `$SCRATCH/uchrom-nd/repo` and the data to `$SCRATCH/uchrom-nd/data`:

```bash
rsync -a --exclude .git ./ sherlock:$SCRATCH/uchrom-nd/repo/
rsync -a $UCHROM_DATA/stevens2017_mesc $UCHROM_DATA/su2020_imr90 $UCHROM_DATA/4DNFIFLJGGNR.csv \
    sherlock:$SCRATCH/uchrom-nd/data/
```

| step | command (from `$SCRATCH/uchrom-nd/repo`) | resources per job / task |
| --- | --- | --- |
| setup | `sbatch benchmarks/screcon/sherlock/setup_screcon.sbatch` | 2 CPU, 8 GB, 30 min |
| held-out split | `sbatch benchmarks/screcon/sherlock/heldout_prepare.sbatch` | 2 CPU, 16 GB, ≤ 1 h |
| sim truth + grid | `sbatch benchmarks/screcon/sherlock/sim_prepare.sbatch` | 4 CPU, 32 GB, ≤ 2 h |
| smoke (all runners) | `sbatch benchmarks/screcon/sherlock/smoke.sbatch` | 8 CPU, 16 GB, ≤ 2 h |
| (i) native GPU | `sbatch benchmarks/screcon/sherlock/heldout_nucdyn_gpu.sbatch` | 1 H100, 8 CPU, 32 GB, ≤ 6 h (24 tables) |
| (i) native CPU | `sbatch --array=1-24 benchmarks/screcon/sherlock/heldout_nucdyn_cpu.sbatch` | 16 CPU, 16 GB, ≤ 4 h |
| (i) original | `sbatch --array=1-24 benchmarks/screcon/sherlock/heldout_orig.sbatch` | 10 CPU, 24 GB, ≤ 16 h |
| (i) Si-C | `sbatch --array=1-24 benchmarks/screcon/sherlock/heldout_sic.sbatch` | 10 CPU, 48 GB, ≤ 48 h (guess) |
| (i) hickit | `sbatch --array=1-24 benchmarks/screcon/sherlock/heldout_hickit.sbatch` | 10 CPU, 16 GB, ≤ 2 h |
| (i) score | `sbatch --array=1-24 benchmarks/screcon/sherlock/heldout_score.sbatch` | 4 CPU, 32 GB, ≤ 4 h |
| (ii) native GPU | `sbatch benchmarks/screcon/sherlock/sim_nucdyn_gpu.sbatch` | 1 H100, ≤ 8 h (180 tables) |
| (ii) CPU methods | `sbatch --array=1-180%60 --export=ALL,METHOD=orig benchmarks/screcon/sherlock/sim_cpu.sbatch` (also `METHOD=hickit --time=01:00:00`, `METHOD=sic --time=24:00:00`, `METHOD=nucdyn_cpu`) | 5 CPU, 16 GB, ≤ 6 h |
| (ii) score | `sbatch benchmarks/screcon/sherlock/sim_score.sbatch` | 4 CPU, 32 GB, ≤ 4 h |
| real, full tables | `sbatch --array=1-8 --export=ALL,METHOD=hickit --time=02:00:00 benchmarks/screcon/sherlock/real_full.sbatch`; `... METHOD=sic ...` | 10 CPU, 48 GB, ≤ 48 h |
| real score + tables | `sbatch benchmarks/screcon/sherlock/real_score.sbatch` (runs `aggregate.py` → `$SCRATCH/uchrom-nd/runs/screcon/tables/`) | 4 CPU, 32 GB, ≤ 4 h |

Order: setup → heldout_prepare + sim_prepare → smoke → method jobs → score jobs →
real_score (aggregation).  Everything writes under `$SCRATCH/uchrom-nd/runs/screcon/`
(`heldout/{split,models,scores,real_scores}`, `sim/{truth,reads,models,scores}`,
`real/{models,scores}`, `tables/`).

## 6. Matched-modality comparison (`matched_data.py`, `matched.py`)

Real scHi-C structures against chromatin tracing of the **same cell type**, compared as
distributions over cells (no cell is measured both ways) — replaces "simulated Hi-C from
imaged cells".  Datasets and their verified / unverified facts: `apps/atlas/recipes/README.md`,
"Matched-modality datasets".

* **Common locus axis**: the 2,460 Takei 2021 ~1 Mb loci (`data/takei2021_1mb_loci.csv`,
  coordinates recovered from 4DN `4DNFIFLJGGNR` ↔ Zenodo spots).  Models (100 kb particles)
  take the particle covering each probe midpoint; Dip-C (20 kb, per haplotype) likewise.
* **Imaging** — mESC: Takei 2021 Nature, E14 serum/LIF, 446 cells (both replicates),
  homologs split by `truth.split_homologs` (kept: clusters ≥ 1 Rg apart, copy detection
  ≥ 50 %; 6,648 chromosomes with two copies, 910 with one (mostly the single chrX), 1,361
  rejected).  Brain: Takei 2021 Science, 2,762 cortex cells; detection is low (median 1,678
  spots per cell for 4,920 locus copies), so homologs are the authors' DBSCAN `labelID`
  (a (cell, chromosome) is kept only with exactly two labels, the paper's rule; copy
  detection ≥ 20 %): 11,388 two-copy chromosomes; median 397 loci per cell.  Our 2-means
  split agrees with DBSCAN on only 68 % of spots at this detection, so it is not used there.
* **scHi-C** — Stevens 2017 (8 haploid G1 cells; the fig3 native-GPU and screcon hickit
  10-model runs, model 0); Nagano 2017 haploid cells, fend pairs lifted mm9 → mm10, stated
  QC (serum: `passed_qc`, non-mitotic, ≥ 100 k contacts → 403 cells; 2i: same QC, ≥ 50 k,
  200 drawn); reconstructed here with the native NucDynamics (GPU, `nuc_dynamics_2017`,
  100 kb, 2 models, seed 1) and hickit (haploid Dip-C schedule to 100 kb, 2 models);
  model 0 is the cell's structure, model 1 a replicate check.  Brain: Tan 2021 Dip-C
  published `20k.1.clean.3dg` (rep 2 as a check), 510 adult cortex cells, diploid.
* **Features** (`matched.py` docstring): per-pair distance distributions after dividing by
  the cell's own 1 Mb unit (median distance of the 0.75–1.25 Mb pairs) — medians,
  P(s)-detrended medians, Wasserstein-1, KS; scaling exponent 2–50 Mb; per-pair CV; radial
  position per locus / chromosome (r / (√(5/3)·Rg)); trans proximity of chromosome pairs
  (min distance < 1 u); intermingling.  Nucleus features use pseudo-haploid imaging nuclei
  (one homolog per chromosome at random) against haploid models, and models get random
  imaging detection masks (`--mask-like-imaging`).
* **References**: `ceiling` = n_A imaging cells vs the other imaging cells (5 draws; capped
  at half the imaging cells); `random_polymer`; `ps_only` (fractional-Brownian chains with
  the imaging exponent).  Read every model number against both.

Results — `model [ceiling ± sd; structure-free baseline closest to the ceiling]`
($SCRATCH/uchrom-nd/runs/screcon/matched/tables/summary.{csv,md}; every metric in the csv):

| comparison | n_a | pair.median_resid_spearman | pair.ks_median | scaling.alpha_diff | variab.cv_spearman | variab.cv_ratio | radial.locus_spearman | radial.chrom_spearman | trans.spearman | mingle.chrom_spearman | mingle.level_ratio |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| brain/Astrocyte/dipc | 26 | 0.24 [0.17±0.06; 0.03] | 0.36 [0.36±0.01; 0.38] | 0.03 [0.01±0.01; 0.00] | 0.11 [0.12±0.05; 0.00] | 0.81 [0.87±0.03; 0.84] | 0.32 [0.23±0.13; 0.10] | 0.30 [0.28±0.25; 0.04] | 0.03 [0.04±0.05; 0.04] | 0.60 [0.51±0.16; 0.60] | 0.66 [0.94±0.09; 1.35] |
| brain/Excitatory/dipc | 197 | 0.44 [0.51±0.01; 0.01] | 0.19 [0.18±0.00; 0.28] | 0.01 [-0.00±0.00; 0.00] | 0.17 [0.27±0.01; 0.02] | 0.89 [0.96±0.01; 0.89] | 0.81 [0.78±0.03; 0.00] | 0.72 [0.74±0.14; 0.04] | 0.25 [0.30±0.08; 0.19] | 0.75 [0.77±0.04; 0.71] | 0.81 [0.99±0.02; 1.38] |
| brain/Inhibitory/dipc | 50 | 0.18 [0.19±0.03; 0.03] | 0.32 [0.34±0.01; 0.38] | 0.02 [0.00±0.01; 0.01] | 0.03 [0.07±0.01; 0.01] | 0.82 [0.89±0.01; 0.78] | 0.45 [0.30±0.01; -0.02] | 0.66 [0.40±0.10; 0.17] | -0.01 [0.04±0.05; 0.01] | 0.45 [0.68±0.08; 0.51] | 0.78 [1.01±0.06; 1.20] |
| brain/Microglia/dipc | 35 | 0.21 [0.17±0.04; 0.01] | 0.50 [0.42±0.02; 0.43] | 0.06 [0.01±0.02; -0.01] | 0.05 [0.19±0.05; -0.04] | 0.77 [1.02±0.03; 0.80] | 0.30 [0.22±0.05; 0.02] | 0.42 [0.11±0.19; 0.07] | 0.05 [0.03±0.05; 0.05] | 0.72 [0.29±0.23; 0.35] | 0.40 [1.01±0.09; 1.01] |
| brain/Oligodendrocyte/dipc | 61 | 0.07 [0.18±0.06; 0.01] | 0.40 [0.52±0.08; 0.44] | -0.00 [0.00±0.03; -0.00] | 0.02 [0.07±0.08; 0.00] | 0.85 [1.04±0.15; 0.87] | 0.27 [0.11±0.08; 0.05] | -0.17 [-0.13±0.25; 0.06] | -0.01 [0.01±0.09; 0.06] | 0.74 [0.42±0.21; 0.51] | 0.41 [0.98±0.25; 1.14] |
| brain/all/dipc | 462 | 0.48 [0.58±0.01; 0.02] | 0.15 [0.14±0.00; 0.23] | -0.00 [-0.00±0.00; 0.00] | 0.23 [0.35±0.02; 0.01] | 0.92 [0.98±0.00; 0.90] | 0.84 [0.85±0.01; 0.04] | 0.92 [0.87±0.08; 0.07] | 0.21 [0.49±0.05; 0.29] | 0.88 [0.87±0.05; 0.73] | 0.81 [1.02±0.01; 1.37] |
| brain/all/dipc_diploid | 462 | 0.48 [0.58±0.01; 0.01] | 0.15 [0.14±0.00; 0.23] | -0.00 [-0.00±0.00; 0.00] | 0.23 [0.35±0.02; 0.02] | 0.92 [0.98±0.00; 0.90] | 0.89 [0.93±0.00; -0.02] | 0.85 [0.95±0.02; 0.27] | 0.36 [0.65±0.02; 0.36] | 0.92 [0.90±0.04; 0.74] | 0.88 [1.02±0.01; 0.94] |
| brain/all/dipc_rep2 | 462 | 0.48 [0.58±0.01; 0.02] | 0.15 [0.14±0.00; 0.23] | -0.00 [-0.00±0.00; 0.00] | 0.22 [0.35±0.02; 0.01] | 0.92 [0.98±0.00; 0.90] | 0.84 [0.85±0.01; 0.04] | 0.90 [0.87±0.08; 0.07] | 0.24 [0.49±0.05; 0.29] | 0.87 [0.87±0.05; 0.73] | 0.80 [1.02±0.01; 1.37] |
| brain/img_Excitatory_vs_Oligodendrocyte | 1725 | 0.25 [0.18±0.06; nan] | 0.35 [0.52±0.08; nan] | 0.06 [0.00±0.03; nan] | 0.14 [0.07±0.08; nan] | 1.06 [1.04±0.15; nan] | 0.39 [0.11±0.08; nan] | 0.37 [-0.13±0.25; nan] | 0.09 [0.01±0.09; nan] | 0.69 [0.42±0.21; nan] | 0.66 [0.98±0.25; nan] |
| brain/x_Excitatory_vs_Oligodendrocyte/dipc | 175 | 0.14 [0.18±0.06; 0.01] | 0.39 [0.52±0.08; 0.41] | 0.06 [0.00±0.03; -0.00] | 0.03 [0.07±0.08; 0.02] | 0.93 [1.04±0.15; 0.94] | 0.32 [0.11±0.08; -0.01] | 0.19 [-0.13±0.25; -0.05] | -0.02 [0.01±0.09; 0.01] | 0.58 [0.42±0.21; 0.46] | 0.43 [0.98±0.25; 1.02] |
| brain/x_Oligodendrocyte_vs_Excitatory/dipc | 71 | 0.20 [0.38±0.01; -0.01] | 0.32 [0.27±0.01; 0.34] | -0.04 [-0.00±0.01; 0.00] | 0.11 [0.18±0.01; 0.02] | 0.85 [0.89±0.01; 0.83] | 0.64 [0.63±0.05; 0.02] | 0.87 [0.56±0.25; 0.06] | 0.07 [0.13±0.05; 0.15] | 0.59 [0.64±0.09; 0.58] | 0.86 [1.00±0.08; 1.39] |
| mesc/check/nagano_serum_nucdyn_vs_hickit | 403 | 0.96 [0.91±0.00; nan] | 0.06 [0.08±0.00; nan] | -0.02 [-0.00±0.00; nan] | 0.92 [0.79±0.01; nan] | 1.06 [1.00±0.01; nan] | 0.98 [0.98±0.00; nan] | 0.98 [0.92±0.02; nan] | 0.94 [0.79±0.03; nan] | 1.00 [0.97±0.01; nan] | 0.83 [0.98±0.03; nan] |
| mesc/nagano_2i/hickit | 186 | 0.45 [0.72±0.01; 0.12] | 0.20 [0.08±0.00; 0.24] | 0.05 [-0.00±0.01; 0.00] | -0.17 [0.77±0.01; 0.04] | 0.54 [1.00±0.01; 0.51] | 0.25 [0.73±0.03; -0.10] | 0.37 [0.66±0.04; 0.75] | 0.60 [0.75±0.02; 0.70] | 0.91 [0.94±0.04; 0.70] | 1.02 [1.00±0.02; 1.07] |
| mesc/nagano_2i/nucdyn_gpu | 186 | 0.57 [0.72±0.01; 0.12] | 0.13 [0.08±0.00; 0.24] | -0.00 [-0.00±0.01; 0.00] | 0.13 [0.77±0.01; 0.04] | 0.53 [1.00±0.01; 0.51] | 0.44 [0.73±0.03; -0.10] | 0.59 [0.66±0.04; 0.75] | 0.42 [0.75±0.02; 0.70] | 0.92 [0.94±0.04; 0.70] | 0.94 [1.00±0.02; 1.07] |
| mesc/nagano_serum/hickit | 373 | 0.57 [0.72±0.01; 0.15] | 0.14 [0.08±0.00; 0.23] | -0.01 [0.00±0.01; 0.00] | 0.49 [0.77±0.00; -0.00] | 0.53 [1.00±0.01; 0.51] | 0.23 [0.74±0.02; -0.18] | 0.63 [0.72±0.03; 0.76] | 0.45 [0.76±0.01; 0.78] | 0.96 [0.96±0.01; 0.64] | 1.46 [0.99±0.02; 1.08] |
| mesc/nagano_serum/hickit_model1 | 373 | 0.57 [0.72±0.01; 0.15] | 0.14 [0.08±0.00; 0.23] | -0.01 [0.00±0.01; 0.00] | 0.48 [0.77±0.00; -0.00] | 0.53 [1.00±0.01; 0.51] | 0.23 [0.74±0.02; -0.18] | 0.63 [0.72±0.03; 0.76] | 0.49 [0.76±0.01; 0.78] | 0.96 [0.96±0.01; 0.64] | 1.46 [0.99±0.02; 1.08] |
| mesc/nagano_serum/nucdyn_gpu | 373 | 0.60 [0.72±0.01; 0.15] | 0.13 [0.08±0.00; 0.23] | -0.03 [0.00±0.01; 0.00] | 0.46 [0.77±0.00; -0.00] | 0.56 [1.00±0.01; 0.51] | 0.28 [0.74±0.02; -0.18] | 0.65 [0.72±0.03; 0.76] | 0.35 [0.76±0.01; 0.78] | 0.95 [0.96±0.01; 0.64] | 1.21 [0.99±0.02; 1.08] |
| mesc/nagano_serum/nucdyn_gpu_model1 | 373 | 0.59 [0.72±0.01; 0.15] | 0.13 [0.08±0.00; 0.23] | -0.03 [0.00±0.01; 0.00] | 0.46 [0.77±0.00; -0.00] | 0.56 [1.00±0.01; 0.51] | 0.28 [0.74±0.02; -0.18] | 0.66 [0.72±0.03; 0.76] | 0.35 [0.76±0.01; 0.78] | 0.96 [0.96±0.01; 0.64] | 1.21 [0.99±0.02; 1.08] |
| mesc/nagano_serum_G1/hickit | 79 | 0.44 [0.64±0.01; 0.08] | 0.26 [0.10±0.00; 0.26] | -0.06 [0.00±0.01; 0.00] | 0.46 [0.68±0.03; -0.00] | 0.45 [0.96±0.01; 0.50] | 0.22 [0.65±0.03; -0.08] | 0.63 [0.60±0.13; 0.70] | 0.41 [0.69±0.02; 0.60] | 0.93 [0.88±0.04; 0.61] | 0.97 [0.99±0.03; 1.07] |
| mesc/nagano_serum_G1/nucdyn_gpu | 79 | 0.48 [0.64±0.01; 0.08] | 0.28 [0.10±0.00; 0.26] | -0.07 [0.00±0.01; 0.00] | 0.43 [0.68±0.03; -0.00] | 0.47 [0.96±0.01; 0.50] | 0.32 [0.65±0.03; -0.08] | 0.63 [0.60±0.13; 0.70] | 0.35 [0.69±0.02; 0.60] | 0.94 [0.88±0.04; 0.61] | 0.84 [0.99±0.03; 1.07] |
| mesc/stevens/hickit | 7 | 0.26 [0.29±0.06; 0.00] | 0.33 [0.27±0.03; 0.38] | 0.00 [0.00±0.03; -0.00] | 0.11 [0.21±0.05; -0.01] | 0.42 [0.66±0.02; 0.44] | 0.08 [0.34±0.08; 0.02] | 0.08 [0.27±0.20; 0.18] | 0.25 [0.33±0.03; 0.29] | 0.66 [0.53±0.22; 0.32] | 1.01 [0.98±0.08; 1.05] |
| mesc/stevens/nucdyn_gpu | 7 | 0.29 [0.29±0.06; 0.00] | 0.33 [0.27±0.03; 0.38] | -0.00 [0.00±0.03; -0.00] | 0.12 [0.21±0.05; -0.01] | 0.42 [0.66±0.02; 0.44] | 0.49 [0.34±0.08; 0.02] | 0.51 [0.27±0.20; 0.18] | 0.11 [0.33±0.03; 0.29] | 0.83 [0.53±0.22; 0.32] | 1.00 [0.98±0.08; 1.05] |

Reading:

* **mESC, Nagano serum (373 cells after masking) vs Takei E14 (415)**: both methods recover the
  scaling exponent (α 0.20 / 0.21 vs 0.23; random walk 0.50) and a good part of the
  locus-specific cis signal beyond P(s) (P(s)-detrended pair medians ρ = 0.60 NucDynamics,
  0.57 hickit; ceiling 0.72; P(s)-only 0.09, random polymer 0.15) and of the per-pair
  variability ranking (CV ρ 0.46 / 0.49, ceiling 0.77, baselines 0).  The models are about
  half as variable as imaging (CV ratio 0.56; ≈ the baselines' 0.51 — imaging noise and
  homolog / cell-state mixing are in the imaging CV).  Nucleus-scale features are weak:
  per-locus radial position ρ 0.28 / 0.23 vs ceiling 0.74 (per chromosome 0.65 / 0.63 —
  *below* the random polymer's 0.76, i.e. chromosome size alone explains more), trans
  proximity 0.35 / 0.45 vs 0.76 (random polymer 0.78: again chromosome size), trans
  residuals at noise level everywhere (ceiling 0.06 ± 0.07 — not measurable with ~400
  cells).  Intermingling per chromosome is matched (0.95 vs 0.96) but the random polymer
  already reaches 0.64.
* **Methods are indistinguishable here**: NucDynamics vs hickit on the same Nagano cells
  agree far better with each other (detrended pairs 0.96, radial per locus 0.98, trans
  0.94) than either agrees with imaging; model 1 reproduces model 0 everywhere.  The gap to
  the ceiling is a data / cell-state gap (or a scHi-C limitation), not a method difference —
  this comparison cannot rank these two methods.
* **Stevens 2017 (7 usable cells)** is too small: ceilings with 7–8 imaging cells are low
  (detrended 0.29 ± 0.06) and the models sit at them; radial per locus 0.49 (NucDynamics) vs
  0.08 (hickit) is within the noise of 7 cells.  The G1-only Nagano subset (79 cells) is not
  closer to imaging than all phases (its ceiling is lower too: 0.64); 2i vs serum is mixed
  (detrended pairs lower for 2i, 0.57 / 0.45 vs 0.60 / 0.57; NucDynamics radial per locus
  higher, 0.44 vs 0.28) — no clear culture effect.
* **Brain, Dip-C vs Takei 2021 Science**: all cells: detrended pair medians 0.48 (ceiling
  0.58), KS 0.15 (0.14), α identical, radial per locus 0.84 (0.85) and per chromosome 0.92
  (0.87) — at the ceiling, far above baselines (≤ 0.07); trans 0.21 vs 0.49.  The rep-2
  structures give the same numbers.  Excitatory neurons (197 Dip-C vs 1,725 imaged cells):
  0.44 (0.51), radial 0.81 (0.78).  Cell-type specificity, each against its own size-matched
  ceiling: Dip-C *oligodendrocytes* (71) vs imaged *excitatory* neurons reach 0.20 of a 0.38
  ceiling on detrended pairs (matched type: 0.44 of 0.51) — type-specific cis structure in
  Dip-C that the imaging confirms — but radial position is at the ceiling either way (0.64 vs
  0.63), so the radial agreement is not type-specific at this resolution.  The other per-type comparisons (26–61 Dip-C cells, 66–275 imaged cells) have
  ceilings at the noise level (e.g. oligodendrocyte detrended 0.18 ± 0.06) and imaging-vs-imaging
  across types is no worse than the within-type ceiling there, so they are uninformative.
  Dip-C is less intermingled than the imaging (level ratio 0.4–0.8; imaging localisation
  error and DBSCAN homolog assignment both inflate intermingling).
* Figure panel: one row per feature (detrended pairs, KS, α, CV, radial locus / chromosome,
  trans, intermingling), x = metric value; per row a grey band from the best structure-free
  baseline to the imaging ceiling (± sd), dots for NucDynamics and hickit (mESC) and Dip-C
  (brain), plus the NucDynamics-vs-hickit point to show that methods agree with each other
  more than with imaging; a second small panel: Dip-C matched vs mismatched cell type.

Caveats: Nagano haploid ESC20 (129, 2i or serum) vs E14 (129/Ola, serum/LIF, diploid;
Stevens 2017 is 2i-adapted haploid G1); the scHi-C cells mix G1 / S / G2 (the G1-only
subset is reported); haploid models vs one homolog of diploid nuclei (pseudo-haploid
sampling, not a haploid nucleus — nuclear size and packing differ); imaging localisation
error (~50–100 nm) and the 250 nm z sampling inflate short-range variability (CV ratios
< 1 are partly this); heuristic homolog split (mESC) and low brain detection; Tan 2021
males (CAST × B6 F1, P56–P347) vs Takei 2021 females (C57BL/6J, 6–7 weeks); brain sections
cut nuclei in z (radial / trans features use whatever is detected; masks carry this over
to the models); the ceiling uses at most half the imaging cells, so for large n_A it is
slightly pessimistic.

| step | command (from `$SCRATCH/uchrom-nd/repo-matched`) | resources |
| --- | --- | --- |
| downloads | `sbatch --export=ALL,PART=mesc …/download_matched.sbatch`; `PART=brain --time=06:00:00` | 2 CPU, ≤ 4–6 h |
| inputs | `sbatch --export=ALL,PART=mesc …/matched_prepare.sbatch`; `PART=brain`; `PART=dipc` | 2 CPU, 32 GB, ≤ 3 h |
| NucDynamics | `sbatch …/matched_nucdyn_gpu.sbatch` (+ `COND=2i`, `COND=serum,REVERSE=1` to split) | 1 GPU, ~40 s per cell (RTX 3090) |
| hickit | `sbatch --array=1-30 …/matched_hickit.sbatch` | 10 CPU, ~25 min per task |
| compare | `sbatch --export=ALL,PART=mesc …/matched_compare.sbatch`; `PART=brain` | 4 CPU, 48 GB, ≤ 6 h |

Aggregation alone:

```bash
python benchmarks/screcon/aggregate.py --heldout RUNS/heldout/scores --sim RUNS/sim/scores \
    --real RUNS/real/scores RUNS/heldout/real_scores --out RUNS/tables
```
