# Figure 2 — the shared index at real scale: plan

Design: `fig2_mock.pdf`, built by `make_fig2.py`; real numbers: `make_fig2.py --real` → `fig2_real.pdf`. Panel a (`panel_a.py`) is the ChromData 2.0 schematic; panels b–f use
placeholder data from `mock_data()`, to be replaced by `load_results()`.

## Panels → evidence needed

| Panel | Claim | Benchmark | Needs (roadmap step in `docs/source/guide/chromdata_2_0_design.md`) |
|---|---|---|---|
| a | Tables joined by keys: `bins`, `spots` (bin_id · trace_id · cell_id), `traces`, `cells`, `contacts` linked | — (schematic of the implemented schema) | 2, 3 |
| b | Compact storage, fast full reads | File size, write time, full read and peak memory vs n_spots (10⁴–10⁸) for FOF-CT/CSV, Parquet, AnnData (spots as obs), h5cd 1.x, h5cd 2.x | 3, 6 (compression, float32) |
| c | Access by level is fast | get_trace / get_cell / get_chrom latency, 1.x scan vs 2.x index; resident memory in backed mode | 6 |
| d | Population analysis beyond RAM | Peak RSS vs n_traces for load-all vs `iter_traces` under a memory budget; identical results (median distance map, axis-wise loop F-test) | 7 |
| e | Contacts linked, queried through the shared index | Cell groups defined in ChromData query the community `.scool`: pseudo-bulk identical to the published per-type `.cool` for every cell type; pseudo-bulk time vs n cells, first query vs cached. (Size / import time → supplement) | 4 (optional; current `link_scool` suffices) |
| f | Lossless round trips | FOF-CT, AnnData/MuData, .cool/.scool, PDB, .3dg: which fields survive, checked by value equality / checksums | 3 |

## Status (fig2_real.pdf)

| Panel | Status | What the figure shows |
|---|---|---|
| a | schematic, matches the code | tables joined by keys; right: the actual `x.chromdata.zarr` 2.1 layout written by `uchrom.core.zarrcd` (`tables/spots/chrom=…/` partitions, spot_tracks / layers, index/ with partition offsets, cellm/ · binm/, results/ · uns/, contacts/ · links/; `.cdz` = one zip); filled / hollow markers = eager / lazy parts of `read(backed=True)` |
| b | **real** (Takei 2025 rep 1, 1e4–1e7 spots) | chromdata.zarr 2.1 vs Parquet, AnnData (spots as obs) and FOF-CT (official `uchrom.io.write_fofct`, re-measured); 1e8 infeasible in memory for every format.  **Regression, stated:** the 2.1 store is 36 % larger than 2.0 on this data (2.58 vs 1.90 GB at 1e7; the 62 per-spot tracks compress worse once chromosomes are split — see `results/spot_tracks_encoding.json`) and the full read 13 % slower (1.11 vs 0.98 s).  The ChromData version comparison (h5cd 1.x, h5cd 2.0, chromdata.zarr, float32) is the supplementary `figS_formats.pdf` (`make_figS_formats.py`) |
| c | **real** (1e4–1e7; backed also 1e8 by replicated cells, hollow markers) | backed chromdata.zarr 2.1 from disk: get_trace / get_cell / get_chrom, get_chrom with `columns="coords"`, open (solid / dashed teal), the 2.0 layout's get_chrom as a thin grey reference, vs the common baseline "load the flat table, then subset" with Parquet and AnnData (dashed / dotted, load + get_trace); memory used, backed vs whole table loaded.  get_chrom 0.77 → 0.04 s (1e7), 8.9 → 0.49 s (1e8); **get_cell slower**: 7.9 → 23 ms (1e7), 22 → 42 ms (1e8) |
| d | **real** (Takei subsets 1e4–1e7 + 1e8 replicated) | exact median distance map of chr11 (`uchrom.fea.distance_map`): memory used vs traces, load all + compute vs streaming `iter_traces` under a 2 GB budget (1e8: load all out of RAM); streaming vs in-memory medians bitwise identical at every size (1e8: vs the chromosome loaded alone) — scatter at 1e7 |
| e | **real** (scHiCAR MOp, 22 cell types) | schematic cell group → linked .scool → a real Oligo pseudo-bulk thumbnail; pseudo-bulk through the index (`Dataset.contacts(group=)`) = published `contacts_<type>.cool` (coarsened to 1 Mb) for 22/22 types, all chromosomes, max \|Δ\| = 0; pseudo-bulk time vs cells (first vs cached) |
| f | **real** | chromdata.zarr, FOF-CT (official `uchrom.io.write_fofct`), AnnData, .cool / .scool, PDB, .3dg round trips |

## Engineering order (one PR each, real-data validated per CLAUDE.md)

1. Step 2 — calling convention, `ResultsStore` / `ResultRecord`, `key_added`; `strc.*` callers converted.
2. Step 3 — `bins` axis (`bin_id`), bin-level `tracks` vs `spot_tracks`, typed `intervals`, `fea.project` → bins, `upgrade_h5cd` from 1.x (format 2.0).
3. Step 6 — spots sorted by cell › trace › bin, `index/` offsets, backed mode, `iter_traces` / `iter_cells`, float32 + compression (2.1).
4. Step 7 — streaming import (`from_fofct`, seqFISH+), streaming population callers, memory budget, chromosome-partitioned spot tables (2.1). **Done.**
5. Benchmarks (`benchmarks/fig2/`) on real data → `paper/fig2/results/*.json` → `load_results()`.

## Data

The largest real imaging dataset is Takei 2025 cerebellum, all FOVs (Zenodo 7693825, about 2.8 GB tarball). Scaling points
above the real size are made by replicating real traces and are labelled as such. Other datasets:
- Takei 2021 mESC (4DN);
- Bintu 2018 IMR90;
- scHiCAR MOp;
- a 4DN FOF-CT set, to be chosen.

Every dataset goes into `example-data/README.md` in the same PR that first uses it.

## Supplementary figures

- `figS_formats.pdf` (`make_figS_formats.py`): ChromData format versions (h5cd 1.x / 2.0, chromdata.zarr, float32).
- `figS_contacts.pdf` (`make_figS_contacts.py`, legend `figS_contacts_legend.md`): the former panel e — on-disk size linked vs copied (store alone and user total, the `.scool` kept either way), import time link vs copy, per-type query first vs cached (`results/e_query.json`).

## Honesty rules

- Report the numbers even where 2.x is slower (for example, write time on small files).
- Panel a must match the implemented schema. Update the schematic if the implementation deviates.
- The dataset-coverage scatter moves to the supplement.
