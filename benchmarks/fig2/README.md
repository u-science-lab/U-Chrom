# Figure 2 benchmarks

One script per panel of Figure 2 (`paper/fig2/PLAN.md`).  Each writes
`paper/fig2/results/<panel>.json`; `python paper/fig2/make_fig2.py --real`
draws the figure from those files (`fig2_real.pdf`, watermarked
"PARTIAL — panel d mock" until panel d has results; see the status table
in `paper/fig2/PLAN.md`).

| Script | Panel | Data | What it measures |
|---|---|---|---|
| `b_storage.py` | b | Takei 2025 cerebellum rep 1, all FOVs (whole-cell subsets) | file size, write time, full-read time, peak RSS vs n_spots for FOF-CT/CSV, Parquet, AnnData (spots as obs), h5cd N.x |
| `c_access.py` | c | same subsets | `get_trace` / `get_cell` / `get_chrom` latency (median, IQR of 20 random ids) and load time vs n_spots |
| — | d | — | **not possible yet**: out-of-core analysis needs streaming (`iter_traces`, backed mode, roadmap steps 6–7).  Panel d stays mock. |
| `e_contacts.py` | e | scHiCAR MOp `.h5cd` + 1 Mb `.scool` | on-disk size linked vs copied; web-browser pseudo-bulk time vs cells aggregated (first query vs cached) |
| `f_roundtrip.py` | f | Takei 2025 FOV0, sim_cell1, scHiCAR | field-by-field round trips (`.chromdata.zarr`, FOF-CT via `uchrom.io.write_fofct`, AnnData, .cool/.scool, PDB, .3dg) → preserved / partial / lost / NA matrix |
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
* `make_fig2.py --real` draws every series of `b_storage.json` (labels
  mapped in `FORMATS` / `FORMAT_LABEL`; an unknown label is an error) and,
  in panel c, backed chromdata.zarr (solid) vs h5cd 1.x in memory
  (dashed), with the open / load time as its own series.

## Adding h5cd 2.x

* b: the h5cd format's label comes from `uchrom.core.cdata.FORMAT_VERSION`, so
  running `b_storage.py --formats h5cd` on a 2.x checkout adds an "h5cd 2.x"
  series; results are merged by label into the existing JSON.
* c: add a backend class (`open`, `ids`, `get`) to `c_access.BACKENDS`, e.g. an
  indexed in-memory and a backed variant; name it `h5cd 2.x …` (a label
  containing "backed" feeds the resident-memory plot).
* Re-run `make_fig2.py --real`: the watermark disappears once 2.x numbers are
  present.
