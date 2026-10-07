# A spot reconstructed as one cell — development log (PREREG §13)

Registered 2026-10-05 (`PREREG.md` §13, commit d826cfb) and the designs materialised (57432cd) before any
reconstruction.  Development units only; nothing of the held-back sets has been built or run.  Methods
frozen (EMber haploid = tag `robust-frozen`; EMber deep diploid = tag `ember-deep-frozen`; NucDynamics
2017 protocol), engine build `dom-4181d07` of this branch (cargo regression tests of the frozen protocols
pass on Sherlock and on the laptop, CPU and `--features gpu`).  Full tables: `results/dominant_dev.md`,
numbers `results/dominant_dev.json`, every scored table `results/dominant_dev_scores.tsv.gz` (1,694 rows:
1,130 mixtures, pure controls, D-only controls).

## 1. What was run

| dataset | dominants | designs | levels (cis contacts) | tables | runs |
| --- | --- | --- | --- | --- | --- |
| Nagano 2017 serum (haploid) | 12 | 24 (m = 1, 2) | 10 k, 30 k, 100 k, full (103-208 k) | 768 | ~1,900 |
| Stevens 2017 cells 1-4 (haploid) | 4 | 24 | 10 k, 30 k, full (25-98 k) | 414 | ~1,120 |
| Tan 2021 cortex (diploid, phased) | 8 (2 per type P / O / A / M) | 16 | 10 k, 30 k, 100 k, full (173-858 k) | 512 | ~1,260 |

200 kb, 2 models per run, one GPU per dominant (RTX 2080 Ti / similar).  Mean wall time per run: EMber 5.8 /
5.3 / 9.1 s, NucDynamics 39 / 32 / 70 s (Nagano / Stevens / Tan).  About 9 GPU-hours in total.

Operational issues (no effect on the numbers, all reruns from scratch of the affected outputs): (1) run files
of different f collided (`f0.9` → stem `f0`) in the first submission — those 40 outputs were deleted before
any scoring and the name fixed; (2) the wgpu adapter is lost after ~25-30 engine calls in one process
(`No suitable graphics adapter`) — the runner now starts a fresh process every 15 calls; (3) `owners`
preemption left one truncated `.npz` — outputs are now written atomically and the `.json` marks completion.

## 2. E1 — recovery of the dominant cell (EMber, per-copy r vs the dominant's own EMber structure)

Mean over all designs (m = 1 and 2) per dataset and level; ΔE1 = E1 − E1(pure control of the same dominant
at the same N), 95 % bootstrap CIs over dominants in `results/dominant_dev.md`.

| dataset | level | pure (f = 1) | f 0.9 | 0.8 | 0.7 | 0.6 | 0.5 | ΔE1 at 0.9 / 0.8 | f_drop |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Nagano | 10 k | 0.605 | 0.580 | 0.546 | 0.520 | 0.499 | 0.481 | −0.025 / −0.059 | 0.8 |
| Nagano | 30 k | 0.790 | 0.771 | 0.732 | 0.680 | 0.622 | 0.578 | −0.018 / −0.057 | 0.8 |
| Nagano | 100 k | 0.928 | 0.894 | 0.833 | 0.765 | 0.687 | 0.632 | −0.034 / −0.096 | 0.8 |
| Nagano | full | 0.957 | 0.910 | 0.844 | 0.768 | 0.690 | 0.640 | −0.047 / −0.114 | 0.8 |
| Stevens | 10 k | 0.747 | 0.740 | 0.686 | 0.636 | 0.573 | 0.513 | −0.007 / −0.061 | 0.8 |
| Stevens | 30 k | 0.940 | 0.887 | 0.797 | 0.693 | 0.623 | 0.545 | −0.052 / −0.143 | 0.9 |
| Stevens | full | 0.986 | 0.957 | 0.880 | 0.785 | 0.710 | 0.644 | −0.034 / −0.112 | 0.8 |
| Tan | 10 k | 0.431 | 0.405 | 0.387 | 0.355 | 0.338 | 0.305 | −0.025 / −0.044 | 0.7 |
| Tan | 30 k | 0.775 | 0.715 | 0.641 | 0.554 | 0.480 | 0.408 | −0.060 / −0.134 | 0.9 |
| Tan | 100 k | 0.928 | 0.899 | 0.824 | 0.718 | 0.601 | 0.497 | −0.028 / −0.104 | 0.8 |
| Tan | full | 0.994 | 0.915 | 0.827 | 0.714 | 0.607 | 0.522 | −0.079 / −0.167 | 0.9 |

(f_drop = largest f < 1 with mean ΔE1 < −0.05; "0.8" means the structure stays within 0.05 of the pure control
only at f = 0.9; "0.9" means not even there.)

* **The dominant cell is recovered only when it holds >= ~90 % of the contacts.**  At every depth >= 30 k the
  loss is already 0.06-0.17 at f = 0.8 and 0.3-0.47 at f = 0.5.  It is roughly linear in the minor share:
  each 10 % of foreign contacts costs ~0.06-0.09 of per-copy r at >= 100 k cis.
* **It is mixing, not depth**: the D-only control (the same dominant rows without the minors) loses only
  0.03-0.07 at f = 0.5 at >= 100 k; the minors' contacts account for 77-94 % of the loss (`mixing_effect`
  column).  At 10 k the pure cell itself is poor (Nagano 0.61, Tan 0.43) and depth dominates.
* **At f = 0.5 the structure is not the dominant's**: for m = 1 it agrees as much with the minor's own
  structure as with the dominant's (Nagano 0.61 vs 0.56, Stevens 0.59 vs 0.56, Tan 0.37 vs 0.41) — a
  consensus of the two cells, as in §12's naive EMber.  The minor's r rises steadily as f falls (Nagano
  0.43 at f 0.9 → 0.57 at 0.5).
* Caveat (affects levels, not differences): the reference is the dominant's EMber structure from all its
  contacts, which include the sampled ones; E1 of subsamples is therefore an upper bound of agreement with
  an independent truth (most visibly Stevens cell 3, 25 k cis, whose 10 k control scores 0.91).  ΔE1 and the
  depth / mixing split compare like with like.

## 3. E2 — EMber − NucDynamics on the mixtures (both vs the dominant's EMber reference)

| dataset | 10 k | 30 k | 100 k | full | all f < 1 mixtures, own-method reference |
| --- | --- | --- | --- | --- | --- |
| Nagano | +0.020 [+0.016, +0.024] | +0.004 [−0.001, +0.009] | +0.006 [+0.001, +0.011] | +0.009 [+0.005, +0.014] | +0.007 |
| Stevens | +0.010 [+0.003, +0.017] | +0.007 [+0.006, +0.008] | – | +0.009 [+0.008, +0.010] | +0.013 |
| Tan (diploid) | −0.010 [−0.017, −0.003] | −0.012 [−0.020, −0.005] | +0.015 [+0.006, +0.024] | +0.025 [+0.008, +0.042] | +0.007 |

* EMber is consistently but only slightly better on haploid mixtures (+0.004 to +0.020); its noise model
  does **not** rescue mixed spots — the per-f gains (≤ 0.02) are an order of magnitude smaller than the
  mixing losses (0.1-0.4).  ε (Q1) sits at its lower bound 1e-4 on every haploid run: the contacts of a
  second cell are not "false" for the mixture model, they form a consistent second structure that a single
  fold absorbs.
* **Diploid at low depth EMber deep is worse than NucDynamics** (−0.01 at 10 k and 30 k; also on the pure
  controls: 0.43 vs 0.47 at 10 k, 0.78 vs 0.80 at 30 k).  The frozen deep configuration commits contacts by
  the phase prior and drops the rest until the 200 kb stage; with 10-30 k contacts and few phased ends that
  leaves too few restraints.  At 100 k / full EMber is better (+0.015 / +0.025).  The secondary comparison
  with each method's own reference (removes the advantage of an EMber reference) gives the same sign
  (+0.007 to +0.013 overall).

## 4. E3 — spot QC (single-cell-like f >= 0.8 vs mixed f <= 0.6; registered directions)

Mean ROC-AUC over levels (per level with CIs in `results/dominant_dev.md`):

| metric | Nagano | Stevens | Tan | mean |
| --- | --- | --- | --- | --- |
| Q1 ε (+) | 0.50 | 0.50 | 0.53 | 0.51 |
| Q2 fraction down-weighted (+) | 0.85 | 0.87 | 0.89 | 0.87 |
| **Q3 violation rate (+)** | 0.86 | 0.96 | 0.90 | **0.91** |
| Q4 seed-to-seed r (−) | 0.62 | 0.72 | 0.78 | 0.71 |
| Q5 long-range transitivity (−) | 0.71 | 0.84 | 0.71 | 0.75 |
| Q6 trans-triangle closure (−) | 0.71 | 0.78 | 0.78 | 0.76 |
| **Q7 partner conflict, 10 kb (+)** | **0.94** | 0.93 | 0.81 | 0.89 |
| logistic Q1-Q7 + log N, leave-one-dominant-out | 0.91 | 0.96 | 0.89 | 0.92 |

* Two metrics separate the classes well: the model-based violation rate Q3 and the model-free partner
  conflict Q7 (best on Nagano, 0.96 at >= 30 k; a contact table statistic, no reconstruction needed).  The
  graph-closure metrics Q5 / Q6 work only at low depth (AUC falls to ~0.6 at full depth: closure depends on
  depth more than on mixing).  ε is uninformative (see §3); run-to-run reproducibility is a poor QC (mixed
  spots reproduce as well as single cells — the consensus fold is stable).
* The logistic combination does not beat the best single metric by a useful margin.
* **QC proposal (dev only, by the registered rule = highest mean AUC): Q3, violation rate**, flag a spot as
  mixed when the fraction of its >= 400 kb / trans contacts that end > 2 bead units apart in its EMber model
  is at or above the per-dataset, per-level Youden threshold:

  | dataset | 10 k | 30 k | 100 k | full | sens / spec range |
  | --- | --- | --- | --- | --- | --- |
  | Nagano | 0.364 | 0.378 | 0.424 | 0.423 | 0.81-0.96 / 0.62-0.78 |
  | Stevens | 0.295 | 0.269 | – | 0.253 | 0.92-1.00 / 0.87-0.90 |
  | Tan | 0.532 | 0.411 | 0.388 | 0.375 | 0.94-1.00 / 0.82-0.88 |

  Runner-up Q7 (partner conflict) has thresholds that hardly depend on depth (Nagano 0.74-0.76, Stevens
  0.49-0.55, Tan 0.86-0.87) and higher specificity on Nagano (0.85-0.93).
* **The thresholds do not transfer between datasets**: the single-cell baseline of every metric depends on
  the protocol and the cell (Q3 0.25 vs 0.42 vs 0.38 at full depth; Q7 0.49 vs 0.76 vs 0.87).  A spatial
  dataset needs its own calibration (e.g. in-silico mixtures of its own most single-cell-like spots, or of
  matched single-cell data of the same protocol), not these numbers.  Within a dataset the metric orders
  spots well (Spearman with E1 −0.45 to −0.94 for Q3).

## 5. Reading

1. Reconstructing a spot as one cell gives the dominant cell's structure only when that cell contributes
   ~90 % or more of the contacts; at 80 % the structure is already 0.06-0.17 worse than the cell's own, and
   at 50 % it is a two-cell consensus that resembles the minor as much as the dominant.
2. EMber's noise model is not a mixture model: a second cell's contacts are not outliers; EMber is only
   marginally better than NucDynamics on haploid mixtures and, with the frozen deep configuration, worse on
   sparse diploid spots.
3. Spot QC is feasible inside a dataset: the violation rate of the one-cell model (Q3) and the model-free
   partner-conflict rate (Q7) separate f >= 0.8 from f <= 0.6 with AUC ~0.9, but their thresholds must be
   calibrated per protocol.
4. For the 10 µm spatial Hi-C spots of Chen et al. 2026 (median 7.6 k cis in adult cortex, 1.6 k in
   hippocampus): even a pure single cell at 10 k cis gives per-copy r 0.6 (haploid) / 0.43 (diploid deep) vs
   its full-depth structure in these tests; a "single-spot 3-D structure" at that depth is at best coarse, and
   any spot with a 20 % foreign share loses another ~0.05.

Not done, waiting for approval: the held-back test (Nagano held-back half, Stevens cells 5-8, Tan held-back
pool cells) with the Q3 rule frozen as above.
