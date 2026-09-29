# screcon — neutral evaluation of single-cell Hi-C 3-D reconstruction (milestone M1)

Method-neutral tests for single-cell genome structures and runnable baselines.  Nothing
here scores a method by its own objective: the held-out test and the imaging-truth
simulation use pairs / loci fixed before any model exists, and every length is either in
the truth's units or in the model's own bead unit (median consecutive-particle distance).

The code is standalone (numpy / scipy / pandas; `uchrom_nucdyn` for the native engine) so
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
rsync -a example-data/stevens2017_mesc example-data/su2020_imr90 example-data/4DNFIFLJGGNR.csv \
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

Aggregation alone:

```bash
python benchmarks/screcon/aggregate.py --heldout RUNS/heldout/scores --sim RUNS/sim/scores \
    --real RUNS/real/scores RUNS/heldout/real_scores --out RUNS/tables
```
