# Figure 2 — ChromData at real scale: plan and status

`make_fig2.py` → `fig2.pdf` / `fig2.png` (170 × 222 mm, Arial, text ≥ 6 pt, lines ≥ 0.3 pt).
Panel a is `panel_a.py`; every other panel is drawn from `results/*.json` (written by `benchmarks/fig2/`).
Nothing is mock data and there are no watermarks. The full legend is `legend.md`; the LaTeX caption is
`paper/manuscript/captions/fig2.tex`.

## Baselines

The main-figure baselines are the **storage schemes publicly used by the community for chromatin-tracing
data**:
- the 4DN FOF-CT core table (CSV);
- AnnData with spots as observations (scverse);
- SpatialData (scverse, Zarr + Parquet: spots as a 3-D points element, cells as a table element).

Flat Parquet is the storage engine under chromdata.zarr, so it is the lower bound without the hierarchy, index
and metadata. It is shown in the supplement (`figS_formats`) as the overhead reference, together with the
ChromData format versions.

## Panels

| Panel | Title | Evidence | JSON (script) |
|---|---|---|---|
| a | ChromData: tables joined by keys | schematic of the implemented model; `x.chromdata.zarr` 2.2 layout with a storage-type glyph per node (Parquet / Zarr / JSON) and the Zarr and Apache Parquet logos (`paper/fig1/logos_ext/`, see `SOURCES.md`) | — (`panel_a.py`) |
| b | Interoperability with community formats | what survives export → import: chromdata.zarr, FOF-CT, AnnData, .cool / .scool, PDB (export only), .3dg (import only) × coords, cell › trace, tracks, cell table, contacts | `f_roundtrip.json` (`f_roundtrip.py`) |
| c | Storage and full reads | file size and full-read time vs spots, Takei 2025 subsets 1e4–1e7: chromdata.zarr 2.2, FOF-CT, AnnData, SpatialData | `b_storage.json` (`b_storage.py`) |
| d | Access by level | query latency, backed chromdata.zarr 2.2 (get_trace / get_cell / get_chrom / get_chrom coords only / open, 1e4–1e8) vs load + query (FOF-CT to 1e6, AnnData to 1e7) and SpatialData's lazy filter (to 1e7) | `c_access.json` (`c_access.py`) |
| e | Beyond RAM | left: memory to open + query, backed vs whole table loaded; right: exact median distance map of chr11, streaming `iter_traces` (2 GB budget) vs load all, 1e8 point, identity inset | `c_access.json`, `d_streaming.json` (`d_streaming.py`) |
| f | Groups from one modality, structure from another | scHiCAR MOp: Leiden clusters on the RNA PCA (`uchrom.emb.cluster_cells`), 3 clusters on the RNA UMAP; their pseudo-bulk maps from the linked per-cell .scool (`Dataset.contacts(group=)`), P(s) slopes, pseudo-bulk time vs cells; identity vs the published per-type .cool (22/22) | `f_crossmodal.json` (`f_crossmodal.py`), `e_query.json`, `e_contacts.json` |

**Panel letters changed** from the 2.1 figure:

| now | was |
|---|---|
| b (interoperability) | f |
| c (storage) | b |
| d (access) | c |
| e (beyond RAM) | d, plus the memory plot of c |
| f (cross-modal) | new; it absorbs e's correctness and timing |

The JSON files keep their old names: `b_storage` → c, `c_access` → d / e, `d_streaming` → e, `e_query` / `e_contacts` → f and supplement, `f_roundtrip` → b.

## Supplementary figures

- `figS_formats.pdf` (`make_figS_formats.py`, legend `figS_formats_legend.md`):
  - (a) file size and (b) full reads for flat Parquet (reference), chromdata.zarr 2.2 / 2.1 / 2.0, 2.0 with float32 coordinates, h5cd 2.0 and 1.x;
  - (c) backed `get_chrom` and (d) `get_cell` by layout (2.0 / 2.1 / 2.2; all columns and coordinates only).
- `figS_contacts.pdf` (`make_figS_contacts.py`, legend `figS_contacts_legend.md`): linked vs copied contacts (size, import time, per-type query).

## Status

- Numbers: Apple M5 Pro, 64 GB, macOS 26.4.1; warm page cache; 3 fresh processes per point.
- Every panel is real; format 2.2 is on main (#71).
- The 1e8 points come from the replicated store. It was built by `replicate_store.py`, measured, then deleted.

## Honesty rules

- Report the numbers even where chromdata.zarr loses: `get_chrom` with all 62 tracks is 0.52 s at 1e7 and 6.7 s at 1e8 (2.1: 0.04 / 0.49 s); writes are slower than flat Parquet; small stores pay the open cost.
- Panel a must match the implemented schema.
- The replicated 1e8 points are labelled as replicated cells.
