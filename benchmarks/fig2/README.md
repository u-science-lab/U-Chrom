# Figure 2 benchmarks

One script per panel of Figure 2 (`paper/fig2/PLAN.md`).  Each writes
`paper/fig2/results/<panel>.json`; `python paper/fig2/make_fig2.py --real`
draws the figure from those files (`fig2_real.pdf`; panels still on
placeholder data sit in a grey dashed box, see the status table in
`paper/fig2/PLAN.md`).  `make_figS_formats.py` draws the ChromData
format-version comparison (supplementary `figS_formats.pdf`).

| Script | Panel | Data | What it measures |
|---|---|---|---|
| `b_capabilities.py` | b (current Fig. 2b) + Supp. Table S1 | tiny synthetic toy objects (no dataset) | what each container can represent: stores each data element with the AnnData / SpatialData / MuData / cooler / uchrom API, writes, reads back and compares (seconds, < 1 GB); marks + evidence URLs → `b_capabilities.json`, `paper/fig2/tableS_capabilities.md` |
| `b_storage.py` | b | Takei 2025 cerebellum rep 1, all FOVs (whole-cell subsets) | file size, write time, full-read time, peak RSS vs n_spots for FOF-CT/CSV, Parquet, AnnData (spots as obs), h5cd N.x |
| `c_access.py` | c | same subsets | `get_trace` / `get_cell` / `get_chrom` latency (median, IQR of 20 random ids) and open / load time vs n_spots; backed chromdata.zarr vs the in-memory baseline (Parquet / AnnData: load the flat table, subset with a pandas boolean mask) |
| `d_streaming.py` | d | same subsets + the 1e8 replicated store | exact median distance map of one chromosome (`uchrom.fea.distance_map`): peak RSS and time, "load all" (`ChromData.read` + in-memory) vs streaming (`backed=True`, `iter_traces` under a 2 GB budget); bitwise identity of the two results + a scatter |
| `e_contacts_query.py` | e + supplement | scHiCAR MOp `.chromdata.zarr` + 1 Mb `.scool` + published `contacts_<type>.cool` | group pseudo-bulk through the index (`Dataset.contacts(group=)` → `_pseudobulk`) vs the published per-type maps for all 22 cell types and all chromosomes (max \|Δ\|); an Oligo thumbnail; link vs copy import time and sizes (→ `make_figS_contacts.py`) |
| `e_contacts.py` | e (right) | scHiCAR MOp store written as `.h5cd` (legacy writer) + 1 Mb `.scool` | web-browser pseudo-bulk time vs cells aggregated (first query vs cached); first on-disk size comparison (HDF5) |
| `rowgroup_sweep.py` | format 2.1 | Takei 1e7 subset | row-group size (8k / 16k / 32k / 65k): size, full read, get_cell / get_trace / get_chrom (± `columns="coords"`) |
| `spot_tracks_encoding.py` | format 2.1 | Takei 1e7 subset | why 2.1 is larger on Takei: size per table, 2.0 vs 2.1 row order, Parquet options (row groups, zstd level, dictionary, byte_stream_split) |
| `replicate_store.py` | c, d | Takei 2.1 store | the 1e8-spot store (whole copies with renamed cells / traces, streamed per partition) |
| `f_crossmodal.py` | Supp. Fig. S2 (was f) | scHiCAR MOp `.chromdata.zarr` + linked 1 Mb `.scool` | Leiden clusters of the RNA PCA (`uchrom.emb.cluster_cells`), marker genes, the chosen clusters' pseudo-bulk maps via `Dataset.contacts(group=)`, P(s) and slopes |
| `f_roundtrip.py` | Supp. Fig. S1e (was b) | Takei 2025 FOV0, sim_cell1, scHiCAR | field-by-field round trips (`.chromdata.zarr`, FOF-CT via `uchrom.io.write_fofct`, AnnData, .cool/.scool, PDB, .3dg) → preserved / partial / lost / NA matrix |
| `allele_qc.py` | supplement | Takei 2025 raw spot CSVs | diagnostic of the published homolog calls (loci per trace, duplicate loci, genomic–spatial Spearman) |

## Setup

```bash
python example-data/download_data.py --takei2025_cerebellum   # 2.85 GB (Zenodo 7693825)
python example-data/build_takei2025_cerebellum.py              # per-FOV + combined .chromdata.zarr
python example-data/download_data.py --schicar_rna --schicar_dna && python example-data/build_schicar_mop.py   # panel e
python example-data/build_takei2025_fov0.py                    # panel f
```

Environment variables: `UCHROM_EXAMPLE_DATA` (where the datasets live;
default `example-data/`), `UCHROM_FIG2_WORK` (scratch for staged subsets and
temporary files; default `example-data/fig2_work/`, tens of GB at 1e7 spots).
The scripts put this checkout first on `sys.path`, so they measure the
checkout's `uchrom`, not an installed copy.

## Protocol

* Every timed trial runs in a **fresh interpreter** (`_common.run_child`); peak
  RSS is `getrusage(ru_maxrss)` of that process (absolute; the RSS after
  imports is recorded as a baseline).
* b: 3 repeats per (size, format), median with min/max.  The OS page cache is
  not flushed (no root), so reads are warm-cache reads of a just-written file.
  Sizes above the real data size replicate real cells under new ids and are
  flagged `replicated`; sizes whose in-memory footprint cannot fit in RAM are
  listed under `infeasible` with the reason.
* FOF-CT: panel f uses the official writer (`uchrom.io.write_fofct` /
  `cd.to_fofct`, PR #67).  Panel b's FOF-CT series was measured with the
  minimal `_common.write_fofct` (core columns, extra spot columns and tracks),
  kept so the existing numbers stay reproducible.  Reading uses
  `ChromData.from_fofct`.

## Format 2.0 series (PR #66)

Run on the 2.0 checkout (the 1.x, FOF-CT and AnnData series are #64's, kept):

```bash
python benchmarks/fig2/b_storage.py --sizes 1e4,1e5,1e6,1e7,1e8 --formats parquet,h5cd2,zarr,zarr_f32
python benchmarks/fig2/c_access.py --sizes 1e4,1e5,1e6,1e7 --backends h5cd-2-memory,zarr-memory
python benchmarks/fig2/replicate_store.py takei2025_cerebellum.chromdata.zarr takei_1e8.chromdata.zarr --n 1e8
python benchmarks/fig2/c_access.py --sizes 1e4,1e5,1e6,1e7,1e8 --backends zarr-backed \
    --prebuilt 1e8=takei_1e8.chromdata.zarr
```

* b: `h5cd2` = "h5cd 2.0" (the HDF5 writer of format 2.0), `zarr` =
  "chromdata.zarr 2.0" (`.chromdata.zarr`, `cd.write` defaults), `zarr_f32` =
  the same with `coord_dtype="float32"`.  Parquet was re-run next to them.
  Staged 1.x pickles are upgraded on load (`_common.load_stage`), so the
  subsets are the same cells as #64's.  1e8 stays infeasible in memory for
  every format (~53 GB table).
* c: `h5cd-2-memory`, `zarr-memory` (full read, then the in-memory scan) and
  `zarr-backed` (`read(backed=True)`; `get_*` reads row ranges).  The 1e8
  point is a store built by `replicate_store.py` (whole Takei rep 1 copied
  10x with renamed cells / traces, streamed row group by row group,
  flagged `replicated`); only the backed backend can open it.
* Baseline for c (the in-memory approach most people use):

  ```bash
  python benchmarks/fig2/c_access.py --sizes 1e4,1e5,1e6,1e7 --backends parquet-memory,anndata-memory
  ```

  `parquet-memory` loads the panel-b Parquet flat table (`pd.read_parquet`)
  and subsets with `df[df.trace_id == id]`; `anndata-memory` loads the
  spots-as-obs `.h5ad` and takes `adata[mask].copy()`.  At 1e7 spots: load
  0.82 s (Parquet) / 7.6 s (AnnData), get_trace 2.1 / 9.2 ms, memory 12.9 /
  5.7 GB above the interpreter baseline.
* `make_fig2.py --real`: panel b draws chromdata.zarr 2.0, Parquet, AnnData
  and FOF-CT; panel c draws backed chromdata.zarr (solid) against the
  Parquet / AnnData baseline as one "load + get_trace" line each.  The h5cd
  1.x / 2.0 / float32 series are in `make_figS_formats.py`.

## Format 2.1 series (this PR: chromosome partitions, streaming)

```bash
python -m uchrom.io.upgrade takei2025_cerebellum_rep1.chromdata.zarr takei2025_cerebellum_rep1.v21.chromdata.zarr
python benchmarks/fig2/replicate_store.py takei2025_cerebellum_rep1.v21.chromdata.zarr takei_1e8.v21.chromdata.zarr --n 1e8
python benchmarks/fig2/rowgroup_sweep.py --n 1e7 --rows 8192,16384,32768,65536 --repeats 3
python benchmarks/fig2/c_access.py --sizes 1e4,1e5,1e6,1e7,1e8 --backends zarr-backed --repeats 3 \
    --prebuilt 1e8=takei_1e8.v21.chromdata.zarr
python benchmarks/fig2/b_storage.py --sizes 1e4,1e5,1e6,1e7,1e8 --formats zarr,fofct --repeats 3
python benchmarks/fig2/d_streaming.py --sizes 1e4,1e5,1e6,1e7 --prebuilt 1e8=takei_1e8.v21.chromdata.zarr --repeats 3
python benchmarks/fig2/e_contacts_query.py --repeats 3
python benchmarks/fig2/spot_tracks_encoding.py OLD_2_0.chromdata.zarr NEW_2_1.chromdata.zarr
python benchmarks/cd21_streaming_validation.py --data example-data --work /tmp/cd21   # conversion, streaming imports, identity
```

* Series are labelled with the container version ("chromdata.zarr 2.1");
  the 2.0 series stay in the JSONs for before / after (panel c draws the
  2.0 `get_chrom` as a thin grey line).  `c_access.py` now runs each size
  in `--repeats` fresh processes (query times pooled) and also times
  `get_*(..., columns="coords")`.
* Panel b's FOF-CT series is re-measured with the official
  `uchrom.io.write_fofct` (recorded as `writer` in `b_storage.json`).
* `replicate_store.py` needs a 2.1 source (it copies each partition's row
  groups).

## Adding h5cd 2.x

* b: the h5cd format's label comes from `FORMAT_VERSION` of
  `uchrom.io._h5cd_legacy` (`.h5cd` is no longer a ChromData format; the
  legacy module keeps its reader / writer for these baselines), so running
  `b_storage.py --formats h5cd` on this checkout adds an "h5cd 2.x" series;
  results are merged by label into the existing JSON.
* c: add a backend class (`open`, `ids`, `get`) to `c_access.BACKENDS`, e.g. an
  indexed in-memory and a backed variant; name it `h5cd 2.x …` (a label
  containing "backed" feeds the resident-memory plot).
* Re-run `make_fig2.py --real`: the watermark disappears once 2.x numbers are
  present.

## Figure 2 redesign (format 2.2; panels a–f)

Panel letters: **b** interoperability (`f_roundtrip.json`), **c** storage (`b_storage.json`), **d** access
(`c_access.json`), **e** beyond RAM (`c_access.json` memory + `d_streaming.json`), **f** cross-modal
(`f_crossmodal.json`, `e_query.json`, `e_contacts.json`).  The JSON names are kept.

Baselines of the main figure: the storage schemes publicly used by the community for chromatin-tracing data —
FOF-CT, AnnData (spots as obs) and **SpatialData** (`spatialdata` 0.7.2, already in the environment):

* `_common.to_spatialdata`: the flat spot table (coordinates, loci, ids, other spot columns, all spot tracks) as
  one 3-D points element (`PointsModel.parse(df, coordinates={"x","y","z"})`) and the cell table as a table
  element (`TableModel.parse`, not linked to a region because cells are not a SpatialData element);
  `SpatialData.write` defaults.  Full read (`b_storage.py --formats spatialdata`) = `read_zarr` +
  `points["spots"].compute()` + the table (import of `spatialdata` / `dask` kept out of the timing, like the other
  readers).  Note the peak: 30 GB for 1e7 spots (dask partitions concatenated).
* `c_access.py --backends spatialdata-lazy`: open = `read_zarr` (lazy dask points); a query = the idiomatic dask
  filter on the id column + `.compute()` (`pts[pts.trace_id == id].compute()`).  Its spatial queries (bounding
  box, polygon) do not address genomic ids.
* `c_access.py --backends fofct-memory`: `ChromData.from_fofct` + in-memory `get_*` (1e4–1e6; at 1e7 the FOF-CT
  reader peaks at 37.7 GB, above the machine-safety limit, see `b_storage.json`).

Flat Parquet moves to `figS_formats` as the overhead reference.

```bash
python benchmarks/fig2/b_storage.py --sizes 1e4,1e5,1e6,1e7 --formats zarr,spatialdata --repeats 3
python benchmarks/fig2/replicate_store.py takei2025_cerebellum_rep1.v22.chromdata.zarr takei_1e8.v22.chromdata.zarr --n 1e8
python benchmarks/fig2/c_access.py --sizes 1e4,1e5,1e6,1e7,1e8 --backends zarr-backed --repeats 3 --prebuilt 1e8=takei_1e8.v22.chromdata.zarr
python benchmarks/fig2/d_streaming.py --sizes 1e4,1e5,1e6,1e7 --prebuilt 1e8=takei_1e8.v22.chromdata.zarr --repeats 3
python benchmarks/fig2/c_access.py --sizes 1e4,1e5,1e6,1e7 --backends spatialdata-lazy --repeats 3
python benchmarks/fig2/c_access.py --sizes 1e4,1e5,1e6 --backends fofct-memory --repeats 3
python benchmarks/fig2/f_crossmodal.py
python paper/fig2/make_fig2.py && python paper/fig2/make_figS_formats.py && python paper/fig2/make_figS_contacts.py
```

`replicate_store.py` now also takes a 2.2 source (primary row groups copied; coordinate codes shifted).
