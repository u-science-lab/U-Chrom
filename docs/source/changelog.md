# Changelog

## Unreleased

- `cd.results` is now a `ResultsStore` of `ResultRecord`s: every result
  carries its kind, producing function, parameters, inputs, uchrom
  version and timestamp.  Unwritable values raise `TypeError` at
  assignment.  `.h5cd` format 1.4 stores the provenance as attrs; older
  files still read.
- One calling convention for the structure callers
  (`call_tads_by_pval`, `call_domains_fishnet`, `call_loops_axiswise_f`,
  `call_compartments_axes_pc`, new `call_tads_di`): keyword-only
  `chrom=None` (all chromosomes, one merged table), `trace_ids`,
  `cells`, `params`, `key_added="<what>.<method>"`, `copy`.
  Positional `chrom`, `store=`, `result_key=` and
  `strc.call_*_multi` are deprecated (they warn and keep the 1.x keys).
- `uchrom.tl` / `uchrom.pp` alias namespaces.

## 0.2.0 — 2026-04

- Renamed package from `nucbox` to `uchrom` / `u-chrom`.
- New core container `ChromData` with HDF5 persistence (`.h5cd`) and
  format versioning (see [Concepts — on-disk format](concepts.md)).
- `uchrom.io.save_particles` / extended `read_particles` — all
  reconstruction modules now write `.h5cd` by default.
- Bulk MDS reconstruction (`uchrom.recon.bulk.mds`) — PyTorch SMACOF
  with inter-chromosomal whole-genome support.
- Browser updates:
  - Trace-aware rendering (per `(chrom, trace_id)` polymer).
  - "Per Trace" colour mode.
  - Unified Chromosome / Region / Trace Management tab.
  - Trace Statistics panel (Distance Matrix / Contact Map / Rg
    Histogram / Split by Trace).
  - Click-to-identify trace overlay.
  - Draggable Layers / Properties divider.
  - macOS Dock icon + startup logo.
- ArcFISH-style axis-wise F-test loop caller
  (`uchrom.strc.loop.call_loops_axiswise_f`) — GPU-accelerated via
  PyTorch, CLI under `python -m uchrom.strc.loop`.
- New population-aggregate modules:
  - `uchrom.fea.distance` (median distance matrix, contact frequency,
    radius of gyration)
  - `uchrom.fea.arc` (axis variance cube, LOWESS filter+normalise,
    axis weights)
  - `uchrom.pl.trace_stats` (matplotlib helpers)
  - `uchrom.utils.stats` (Cauchy combination test, log-log LOWESS)
- Version stamp on `.h5cd` files with MAJOR/MINOR semantics and
  legacy-file handling.
