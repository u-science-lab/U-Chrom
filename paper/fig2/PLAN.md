# Figure 2 — the shared index at real scale: plan

Design: `fig2_mock.pdf`, built by `make_fig2.py`. Panel a (`panel_a.py`) is the ChromData 2.0 schematic; panels b–f use
placeholder data from `mock_data()`, to be replaced by `load_results()`.

## Panels → evidence needed

| Panel | Claim | Benchmark | Needs (roadmap step in `docs/source/guide/chromdata_2_0_design.md`) |
|---|---|---|---|
| a | Tables joined by keys: `bins`, `spots` (bin_id · trace_id · cell_id), `traces`, `cells`, `contacts` linked | — (schematic of the implemented schema) | 2, 3 |
| b | Compact storage, fast full reads | File size, write time, full read and peak memory vs n_spots (10⁴–10⁸) for FOF-CT/CSV, Parquet, AnnData (spots as obs), h5cd 1.x, h5cd 2.x | 3, 6 (compression, float32) |
| c | Access by level is fast | get_trace / get_cell / get_chrom latency, 1.x scan vs 2.x index; resident memory in backed mode | 6 |
| d | Population analysis beyond RAM | Peak RSS vs n_traces for load-all vs `iter_traces` under a memory budget; identical results (median distance map, axis-wise loop F-test) | 7 |
| e | Contacts linked, not copied | On-disk size linked vs copied; pseudo-bulk aggregation time vs n cells (scHiCAR .scool), first query vs cached | 4 (optional; current `link_scool` suffices) |
| f | Lossless round trips | FOF-CT, AnnData/MuData, .cool/.scool, PDB, .3dg: which fields survive, checked by value equality / checksums | 3 |

## Engineering order (one PR each, real-data validated per CLAUDE.md)

1. Step 2 — calling convention, `ResultsStore` / `ResultRecord`, `key_added`; `strc.*` callers converted.
2. Step 3 — `bins` axis (`bin_id`), bin-level `tracks` vs `spot_tracks`, typed `intervals`, `fea.project` → bins, `upgrade_h5cd` from 1.x (format 2.0).
3. Step 6 — spots sorted by cell › trace › bin, `index/` offsets, backed mode, `iter_traces` / `iter_cells`, float32 + compression (2.1).
4. Step 7 — streaming import (`from_fofct`, seqFISH+), streaming population callers, memory budget (2.1).
5. Benchmarks (`benchmarks/fig2/`) on real data → `paper/fig2/results/*.json` → `load_results()`.

## Data

The largest real imaging dataset is Takei 2025 cerebellum, all FOVs (Zenodo 7693825, about 2.8 GB tarball). Scaling points
above the real size are made by replicating real traces and are labelled as such. Other datasets:
- Takei 2021 mESC (4DN);
- Bintu 2018 IMR90;
- scHiCAR MOp;
- a 4DN FOF-CT set, to be chosen.

Every dataset goes into `example-data/README.md` in the same PR that first uses it.

## Honesty rules

- Report the numbers even where 2.x is slower (for example, write time on small files).
- Panel a must match the implemented schema. Update the schematic if the implementation deviates.
- The dataset-coverage scatter moves to the supplement.
