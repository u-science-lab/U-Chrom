# Plan (deferred): spatial deconvolution of spatial Hi-C spots into 3-D structures

Status: recorded 2026-09-30, **not started**.  Fig. 3 stays on faithfulness / speed /
comparability; this is a candidate for an additional figure.

## Idea

A spatial Hi-C spot (DBiT-style barcode grid, 10-50 µm) holds the contacts of a few
cells or partial nuclei.  IGM deconvolves a population average into S structures; a
spot is a tiny population, so a spot-level IGM (S = k cells per spot, contacts
hard-assigned to one cell each) could split a spot into per-cell structures — the 3-D
analogue of spot deconvolution in spatial transcriptomics (Tangram etc.).

## Data (2026)

| Paper | Spot | Contacts per spot (median) | 3-D modelling |
|---|---|---|---|
| Spatial Hi-C-RNA, Guo … Deng, Cell 2026, doi:10.1016/j.cell.2026.07.039 (GEO GSE311199) | 20 µm (brain, melanoma), 10 µm (E11.5) | cis > 1 kb 136k / trans 42k (adult brain); 35k / 27k (E11.5) | none |
| Spatial-ATAC-Hi-C, Wang … Yue, Nat Methods 2026, doi:10.1038/s41592-026-03217-4 (GEO GSE307620) | 50 x 50 grid, likely 20 µm (unverified) | ~96k Hi-C fragments | none (Higashi / scHiCluster per spot) |
| Spatial Hi-C, Chen … Chen, Nat Methods 2026, doi:10.1038/s41592-026-03218-3 (GSA CRA016676, Zenodo 17961135) | 10 / 20 / 50 µm | 72k valid contacts (50 µm, E13) | abstract claims single-spot 3-D; no modelling code released |

## Obstacles

1. Contacts per cell: 30-60k if a 20 µm spot holds 2-4 cells — borderline but in the
   range of Stevens 2017 single-cell structures.
2. **Homologs cannot be phased** (inbred mice, no SNPs): each contact has 2k possible
   origins in a spot of k diploid cells.  The main obstacle.
3. Sectioning (10 µm) cuts nuclei: partial genomes; maybe only local structures.

## Two routes

- **Reference-free**: spot-level IGM with S = k (A-step assigns each contact to the cell
  whose structure it fits; M-step refines).  Engine change: raw contacts, binary
  assignment, small S.
- **Reference-based (Tangram-like)**: map reference single-cell 3-D structures with cell
  types (brain: Tan 2021 Dip-C; embryo: HiRES, Liu 2023 Science) onto spots in contact
  space, optionally constrained by the spot's RNA (Cell 2026 data), then refine with the
  spot's contacts starting from the reference structures (`init_positions`).  Phasing and
  missing parts come from the reference.

## Steps when started

1. Per-spot statistics on the Cell 2026 and Chen 2026 data: contacts, and the number of
   cells per spot from the Dip-C rule "a fragment end takes part in at most two contacts".
2. In-silico mixtures of **real** single cells with known origin (like simulated
   doublets): haploid (Stevens 2017, 8 cells), diploid phased (Dip-C), diploid unphased.
   Metrics: contact-to-cell assignment accuracy; structure similarity to each cell's own
   reconstruction; scored with the `benchmarks/screcon` framework.
3. Pick the route from step 2; then the spatial data (per-region structure maps, links to RNA).
4. Novelty check: Hi-C multiplet deconvolution into structures; reference-based
   deconvolution of spatial Hi-C.

Estimated effort: steps 1 + 4 about one day, step 2 two to three days.

## Plan (2026-10-06, not run — waiting for approval): per-spot EMber on Chen et al. 2026 spatial Hi-C

Goal: test the "single-spot 3-D structure" claim of Chen et al. (Nat Methods 2026, GSA CRA016676) with
per-spot EMber + the spot QC of PREREG §13 (`benchmarks/screcon/dominant_devlog.md`).

**What exists (checked 2026-10-06).**  All 15 runs of CRA016676 were already processed by earlier work
(local branch `Nanguage/spatial-hic-chen2026` in the `fig6` workspace, not pushed; pipeline
`barcodes.py` → `bwa mem -5SP -T0` → `pairtools parse` (mapq 30) → per-spot dedup, cis >= 1 kb; pilot
CRR1161506 matches the authors' per-spot counts, r(log) 0.999):
* Sherlock `$OAK/uchrom/spatial_hic_chen2026/<run>/` (45 GB): `<run>.dedup.pairs.gz` (readID = barcode
  pair), `.pixels_1Mb.scool`, `.bulk.mcool`, `.barcode_stats.tsv`.  Adult cortex 10 µm = CRR1829219
  (1.6 GB pairs), adult hippocampus 10 µm = CRR1829220 (0.75 GB), embryonic brain 10 µm = CRR1829213 /
  15 / 17, 20 µm = CRR1829212 / 14 / 16, E13 50 µm = CRR1161506 / 07 / CRR1831973, cerebellum 20 µm =
  CRR1161509 / 10.
* Barcode pair → spot mapping established for 10 sections (~50.9 k spots); **not** for E13 R3 and the two
  cerebellum runs.  `$SCRATCH/chen2026` (124 GB) is a leftover duplicate of the pilot (FASTQ + chunks) and can
  be deleted by the user.
* Laptop `fig6/example-data/spatial_hic_chen2026/` (41 GB): Zenodo 17961135 (Seurat objects; the only
  per-read contact file the authors published is the E13 R1 BEDPE), authors' code, scool / mcool, catalog
  entry in that branch's `example-data/README.md`.

**Depth per spot (cis >= 1 kb, all barcode pairs incl. off-tissue; `barcode_stats.tsv`).**

| section | spots | median cis | p90 | spots >= 10 k | >= 30 k |
| --- | --- | --- | --- | --- | --- |
| adult cortex 10 µm (CRR1829219) | 9,216 | 7,597 | 25,489 | 3,678 | 608 |
| adult hippocampus 10 µm (CRR1829220) | 9,216 | 1,613 | 14,357 | 1,414 | 191 |
| embryonic brain 10 µm E14.5 / E16.5 / E18.5 | 9,216 each | 10.3 k / 16.2 k / 17.7 k | 19-30 k | 4,780 / 6,804 / 7,035 | 157 / 953 / 792 |

**What §13 development says about these depths.**  A pure single cell at 10 k cis reconstructs to per-copy
r 0.61 (haploid Nagano) / 0.43 (diploid Tan, EMber deep) against its own full-depth structure; at 30 k 0.79 /
0.78.  A 20 % foreign share costs another 0.04-0.13.  So a 10 µm spot at its median depth (2-8 k cis in
adult brain) cannot carry a single-cell structure in the sense tested here; only the deepest spots (>= 30 k,
~600 in cortex) are in the range where a one-cell structure is meaningful, and only if the QC calls them
single-cell-like.  The mouse brain sections are unphased (inbred): spots must be run pseudo-haploid
(homologs on one chain) — **not covered by §13**, which used phased Tan cells; before Chen runs, add a
dated §13 addition: the Tan development mixtures re-run with phases dropped and haploid EMber (cost ~1 h GPU),
to calibrate E1 / QC for unphased diploid input.

**Proposed protocol (register as a PREREG addition before running).**
1. Pull `CRR1829219` / `CRR1829220` dedup pairs (2.4 GB) to `$SCRATCH`; split per spot with the established
   barcode → spot map (in-tissue spots only), drop spots < 10 k cis; GEO tables per spot.
2. Per spot: EMber haploid (`robust-frozen`), 200 kb, 2 models, seeds 2 and 3; NucDynamics seed 2 on a random
   500-spot subset (baseline).  QC: Q3 violation rate, Q7 partner conflict (the two §13 metrics that work),
   plus Q2.
3. Calibration inside the dataset (the §13 thresholds do not transfer between protocols): in-silico mixtures
   of the section's own top-QC spots (f 1.0 / 0.8 / 0.6 / 0.5 at 10 k and 30 k cis), the same scoring as
   `dominant.py`; thresholds from those, then applied to all spots.
4. Tests of the claim, all spot-intrinsic or cross-spot: (a) fraction of spots QC-passing per depth bin;
   (b) held-out contacts per spot (`heldout.py split`, 10 %) — cis AUC of the spot structure vs a P(s)-only
   baseline; (c) structure similarity of neighbouring vs distant spots of the same cell-type region
   (neighbours share cells in 10 µm sections; a single-cell structure should not be more similar to its
   neighbours than to distant spots of the same type beyond what shared cells explain); (d) compare with the
   authors' per-spot results (their compartment / insulation calls) where available.
5. Report: what fraction of spots support a one-cell structure, at what quality, and whether that supports
   "single-spot 3-D structure".

**Cost.**  No download or alignment (done; redoing alignment from FASTQ would be 2.3 TB and ~3,500 CPU-hours).
Cortex + hippocampus: ~5.1 k spots >= 10 k cis x 2 EMber seeds x ~5 s ≈ 15 GPU-hours (with process
overhead), NucDynamics subset ~4 GPU-hours, scoring ~10 CPU-hours; calibration mixtures ~2 GPU-hours.  Adding
the three embryonic 10 µm sections (~18.6 k spots >= 10 k): ~50 GPU-hours more.  Storage ~30 GB on `$SCRATCH`.
