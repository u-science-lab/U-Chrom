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
- **`.h5cd` format 2.0 — the `bins` locus axis** (breaking on disk; 1.x
  files still read).  `cd.bins` (index `bin_id`), required
  `spots.bin_id` (derived from `chrom/start/end` by every constructor and
  loader), bin-level `cd.bin_tracks` vs per-spot `cd.spot_tracks`,
  `cd.binm`, typed `cd.intervals` (`domain | pair | peak | segment`, with
  `to_bins`).  Structure callers also fill `cd.intervals`; compartments add
  segments and a per-bin `pc2` track.  `fea` / `strc` feature writers
  project onto bins (`fea.project_interval_features_to_bins`; the spot
  version is deprecated).  `cd.tracks` is a deprecated spot-aligned view.
  `uchrom.io.upgrade_h5cd` and `python -m uchrom.io.upgrade` rewrite 1.x
  files; the web browser lists bin- and spot-level tracks and typed
  intervals.  Large integer / string datasets are chunked and gzip-4
  compressed (`write(compression=…, compress_floats=…)`); strings are
  encoded / decoded vectorised.
- Fix: `from_fofct` kept the last `##columns=` name intact when it ends in
  `)` (`n_per_dist(um)` was read as `n_per_dist(um`).
- seqFISH+ loader (Takei 2025): `traces` now reports `allele`, `n_spots`,
  `n_loci`, `n_duplicate_loci` and per-column allele majority / agreement
  instead of the first spot's `dbscan_*` values; the docstring warns that
  the default `allele_col="dbscan_ldp_nbr_allele"` often merges homologs
  (default unchanged).

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
