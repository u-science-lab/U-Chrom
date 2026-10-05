# ChromData 2.0 Design

This page records the proposed next data model for `ChromData`: the next
MAJOR bump of the on-disk format (1.x → 2.0) and of the package (0.3.0).
It is a design document: nothing here is implemented yet unless stated
otherwise.  Sections 2 and 3 are implemented; section 4 is implemented on
a Zarr + Parquet container (`.chromdata.zarr`) instead of HDF5.

The goal is to make `ChromData` the *single* container for chromatin
tracing, bulk / single-cell Hi-C, and other per-locus omics — while keeping
memory bounded on genome-wide, many-cell datasets.

The guiding principle is:

```text
spots   tell what was observed          (one row per observation, O(n))
bins    tell where on the genome        (one row per locus, shared by all cells)
cells   tell who                        (one row per cell, any modality)
contacts tell who touched whom          (external, lazy, never O(n²) in memory)
results tell what was derived           (typed, with provenance, round-trippable)
```

## Motivation

1.x `ChromData` works well for imaging data (FOF-CT, PyHiM, seqFISH+).
Four structural gaps remain against the project goal of *unifying*
tracing, Hi-C and multi-omics:

1. **Hi-C has no home.** The data model requires `coords` for every row.
   Contact data (pairs / cool / scool) can only enter after
   reconstruction.  The Higashi tutorial works around this with
   `coords=np.zeros(...)` (`tutorials/higashi_embedding.py:186`) — a
   placeholder that is indistinguishable from real coordinates at the
   origin.
2. **No locus axis.** Everything is aligned to the spot axis.  A bulk
   ATAC track is locus-level, but `tracks` is `(n_spots, n_tracks)`, so
   it is duplicated once per trace.  TADs / loops / compartments are also
   locus-level, but live in an untyped `results` dict.  `fea.project`
   (`unique_spot_intervals` + `project_interval_features_to_spots`) is
   already a de-facto bin axis rebuilt on every call.
3. **Inconsistent analysis API.** Some functions take `cd` and write
   `cd.results[...]` (`strc.*.call_*`, `fea.add_*`), some take a dense
   matrix (`strc.tad.di`, `recon.bulk.mds.run_mds`), and several recon
   entry points are CSV-in / CSV-out CLIs (`nucdyn`, `gem`, `mds`).
   Result key naming, per-chromosome merging and provenance are ad hoc.
4. **Everything is in memory.** `ChromData.read` materialises every
   array; `get_cell` / `get_trace` scan the whole `spots` table and copy.
   A genome-wide Dip-C / multiplexed-tracing dataset easily reaches 1e8
   spots (~2.4 GB of float64 coords alone, plus spots / tracks / layers).

Separately, `results` currently **drops** any value that is not a
`DataFrame` or `ndarray` on write (e.g. `strc.tad.fishnet` stores a dict
under `results[ensemble_key]`, which silently disappears after a
write/read round trip).  That bug is fixed in format 1.2 (typed
`results` entries: DataFrame / Series / nested dict / ndarray / JSON, and
`TypeError` for anything else); 2.0 turns the fix into a contract (see
section 3).

## Overview

```text
ChromData (2.0)
├── bins        DataFrame (n_bins)          chrom, start, end, [resolution]   ← NEW (locus axis)
│   ├── binm    dict[str, ndarray]           per-bin multi-dim (e.g. PC loadings)
│   └── tracks  DataFrame (n_bins)          bulk per-locus signal (ATAC, ChIP, GC…)
├── spots       DataFrame (n_spots)         bin_id, trace_id, cell_id, [chrom,start,end]
│   ├── coords  ndarray (n_spots, 3) | None  x,y,z; NaN allowed with explicit status
│   ├── layers  dict[str, (n_spots, 3)]
│   └── spot_tracks DataFrame (n_spots)     per-observation signal (IF, per-spot intensity)
├── traces      DataFrame (n_traces)
├── cells       DataFrame (n_cells)         any modality: tracing, sc-Hi-C, RNA…
│   └── cellm   dict[str, ndarray]
├── contacts    ContactsCollection          ← NEW, external + lazy (cool/mcool/scool/hic/pairs)
├── intervals   dict[str, IntervalTable]    ← NEW, typed TADs / loops / peaks / compartments
├── results     ResultsStore                typed, provenance-tracked
└── uns         dict
```

Compatibility shim: `cd.tracks` keeps working as a spot-aligned view
during the 2.x series (see section 2, *Migration*).

---

## 1. Contacts layer — unifying Hi-C

### Starting point

The unmerged branch `origin/codex/linked-mudata-scool-framework`
(commit `0df715f`) already implements the right idea:

- `cd.link_scool(path, key=..., cell_name=..., bin_size=..., coordinate_status=...)`
  and `cd.link_mudata(path, key=..., modalities=..., cell_axis=...)` record
  *external* files under `uns["linked_scool"]` / `uns["linked_mudata"]`;
- `load_linked_scool(key, cell=...)` returns a `cooler.Cooler` lazily;
- `coord_status()` reports `complete / partially_missing / unavailable_all_nan`;
- `validate_links()` checks paths, formats and declared coordinate status;
- `UChromProject` wraps a `ChromData` plus its links.

**Status:** that branch is now merged (`link_mudata`, `link_scool`,
`set_cell_spatial_coordinates`, `coord_status`, `validate_links`,
`UChromProject`).  It only adds `uns` keys, so it needs no format bump
and ships inside format 1.2.  2.0 then promotes the
`uns["linked_*"]` records to a first-class, typed `cd.contacts` attribute
rather than re-inventing it.  `UChromProject` becomes unnecessary once
`ChromData` owns the links; keep it as a thin alias for one release.

### Proposed API

```python
cd.contacts.link(
    "hic_bulk",
    "GM12878.mcool",
    kind="bulk",                 # "bulk" | "single_cell"
    format="mcool",              # inferred from suffix: cool/mcool/scool/hic/pairs
    genome_assembly="hg38",
    resolutions=None,            # discovered from the file when None
    normalization="weight",      # cooler balance column / .hic norm (KR, VC…)
)
cd.contacts.link(
    "schic",
    "GSE305439_DNA_1Mb.scool",
    kind="single_cell",
    cell_map="RNAbarcode",       # column in cd.cells that matches scool cell names
    # or cell_map=pd.Series(scool_name, index=cell_id)
)

h = cd.contacts["hic_bulk"]           # ContactRef — metadata only, no I/O
h.resolutions                         # [5000, 10000, …]
m = h.matrix("chr21", resolution=30_000, balance=True)            # dense, one chrom
m = h.matrix("chr21", "chr22", resolution=1_000_000)              # trans block
p = h.pixels("chr21", resolution=10_000)                          # sparse COO DataFrame
s = cd.contacts["schic"].matrix("chr1", resolution=1_000_000, cell="c0042")
for cell_id, m in cd.contacts["schic"].iter_cells("chr1", batch=64): ...
h.bins(resolution=30_000)             # bin table in ChromData bins schema
```

`ContactRef` is a small dataclass (`key, path, format, kind, genome_assembly,
resolutions, normalization, cell_map, sha256?, created_utc`) plus lazy
accessor methods.  Backends:

| format | reader | notes |
|--------|--------|-------|
| `cool` / `mcool` / `scool` | `cooler` (core dep) | native lazy, chunked |
| `hic` | `hicstraw` (extra `[hic]`) | per-chrom-pair fetch |
| `pairs` / `pairs.gz` | pairix / pandas chunked | discouraged for large data; `cd.contacts.to_cool(key)` converts once via `cooler cload` |

Nothing is ever loaded until a matrix / pixel accessor is called.  All
existing loaders (`io.load_cool`, `io.load_hic*`, `recon.fish._hic`,
`recon.bulk.mds.__main__.load_contacts_from_mcool`) collapse into the
`ContactRef` backends.

### Optional coordinates

2.0 separates *"this cell/spot has no coordinates"* from *"coordinates are
(0, 0, 0)"*:

- `coords` may be `None` (no coordinate modality at all), or contain NaN.
- Per-spot status lives in `spots["coord_status"]` (categorical:
  `measured`, `imputed`, `reconstructed`, `missing`); a dataset-level
  summary is `cd.coord_status()` (from the branch).
- Per-cell modality membership lives in `cells["has_coords"]`,
  `cells["has_contacts"]`, `cells["has_rna"]` (booleans maintained by
  `link` / constructors).

This lets an sc-Hi-C experiment be represented as:

```python
cd = ChromData.from_contacts(
    "cells.scool", key="schic", resolution=1_000_000,
)   # bins from the scool, cells from its cell list, spots empty, coords=None
cd = recon.sc.nucdyn(cd, contacts="schic", cells=cd.cells.index[:10])
# → adds spots/coords for the 10 reconstructed cells, coord_status="reconstructed"
```

and sc-Hi-C cells, reconstructed cells and tracing cells share one
`cells` axis, one `cellm["X_higashi"]` embedding, and one `bins` axis.
The zeros placeholder in the Higashi tutorial goes away.

### On-disk layout

```text
contacts/
└── <key>/                         group, attrs only — no pixel data
    @path            "GM12878.mcool"   (stored relative to the .h5cd when possible)
    @format          "mcool"
    @kind            "bulk"
    @genome_assembly "hg38"
    @normalization   "weight"
    @resolutions     int64[]
    @sha256          optional
    cell_map/        optional DataFrame group (cell_id → external cell name)
```

Paths are stored relative to the `.h5cd` file when they share a parent
directory, so a project folder can be moved as a unit.

### Migration / compat

- 1.x files with `uns["linked_scool"]` / `uns["linked_mudata"]` are
  upgraded on read into `cd.contacts` / `cd.links["mudata"]`.
- `link_scool` / `link_mudata` / `load_linked_scool` stay as deprecated
  wrappers over `cd.contacts` for one minor release.
- `linked_adata` (current AnnData link) and `link_mudata` merge into one
  `cd.links` registry for *cell-level* external modalities (RNA, ATAC
  matrices); `cd.contacts` is reserved for locus-pair data.

### Open questions

- Should `cd.contacts` also accept an in-memory sparse matrix (for small
  synthetic tests / derived contact maps such as `fea.contact_frequency`)?
  Proposal: yes, stored inline under `contacts/<key>/pixels` as COO, capped
  by a size warning.
- Where do Higashi-imputed maps go?  Today they stay on disk and only the
  path is recorded in `uns`.  Under 2.0 they become a `kind="single_cell"`
  `ContactRef` with `format="higashi_dir"`.

---

## 2. `bins` — a locus axis separate from `spots`

**Status:** implemented (roadmap step 3, format 2.0): `uchrom.core.bins`,
`uchrom.core.intervals`, `uchrom.io.upgrade_h5cd`.  Differences from the
text below, as built:

- The bin-level table is `cd.bin_tracks` during 2.x, because `cd.tracks`
  stays the deprecated spot-aligned shim for the whole series; on disk
  `tracks/` is bin-level as specified.  The shim warns on every access
  (it cannot know the caller's "spot-length expectations") and
  `cd.tracks[col] = values` writes through.
- `spots["chrom"/"start"/"end"]` are derived from `bins` but kept as
  materialised columns in memory (not stored on disk), with no
  per-access warning.  A lazy accessor needs a DataFrame proxy, which
  arrives with backed mode (step 6).  `write()` checks that they agree
  with `bins[bin_id]`; `cd.rebuild_bins()` re-derives bins after edits.
- Bins derived from spots are ordered by chromosome (category order),
  start, end — not first occurrence — so `bin_id` follows genome order.
- `binsets` / `rebin` are not implemented yet.
- Categorical columns are stored as `{codes, categories}`, and the
  compression part of step 6 already ships with 2.0: `write()` chunks
  datasets of ≥ 4,096 elements (65,536 rows per chunk) and compresses them
  with gzip level 4 by default (`compression="lzf"` / `None` opt-in;
  both built into h5py).  Strings are encoded / decoded vectorised.
  Spots are not sorted and `index/` is not written (step 6,
  `@spot_order = "unsorted"`); coords stay float64.

### Motivation

AnnData's obs/var split is what makes per-gene annotations (var) and
per-cell annotations (obs) cheap and unambiguous.  ChromData needs the
same split between *where on the genome* (bins) and *which observation*
(spots).

### Schema

```text
bins        DataFrame, index = bin_id (int, 0..n_bins-1)
  chrom     category
  start     int64
  end       int64
  resolution int64 (optional; constant per bin set)
  name      optional (e.g. FOF-CT readout / probe name)

spots       DataFrame (n_spots)
  bin_id    int32   → bins.index   (REQUIRED in 2.0)
  trace_id  category
  cell_id   category (optional)
  coord_status category (optional)
  … any extra per-spot column
```

`spots["chrom"/"start"/"end"]` become derived columns: materialised
lazily from `bins` via `cd.spots_with_loci()` and on `to_dataframe()`.
Tracing designs with irregular probes simply get an irregular `bins`
table (one row per probe locus) — `bin_id` does not require a uniform
grid.

Rules:

| data | lives in | aligned to |
|------|----------|-----------|
| bulk ATAC / ChIP / GC / annotation features | `cd.tracks` | bins |
| per-spot IF intensity, seqFISH z-scores | `cd.spot_tracks` | spots |
| per-bin embeddings / loadings | `cd.binm[key]` | bins (first axis) |
| TADs, loops, peaks, compartment calls | `cd.intervals[key]` | typed interval tables (below) |
| per-bin compartment score | `cd.tracks["compartment.pc1"]` | bins |

`fea.project.project_interval_features_to_spots` becomes
`project_interval_features_to_bins` (exact interval overlap once per bin,
not once per spot), and every `add_*_features` function writes to
`cd.tracks` (bins) instead of the spot table.

### Typed interval tables

`cd.intervals` is a dict of DataFrames with a declared schema, validated
on assignment:

| kind | required columns | examples |
|------|------------------|----------|
| `domain` | `chrom, start, end` | TADs, FISHnet domains |
| `pair` | `chrom1, start1, end1, chrom2, start2, end2` | loops |
| `peak` | `chrom, start, end, [summit, score, pvalue, qvalue]` | MACS peaks |
| `segment` | `chrom, start, end, label` | A/B compartment segments |

```python
cd.intervals["tads.arcfish"]          # IntervalTable(kind="domain", …)
cd.intervals["tads.arcfish"].to_bins(cd.bins)   # → bool / id per bin
```

Each interval table carries `attrs = {"kind", "source_result"}` linking
back to the result record that produced it (section 3).

### Multi-resolution

- One `ChromData` has exactly **one active bin set** (`cd.bins`) — the
  resolution the spots are observed at.
- Alternative bin sets live under `cd.binsets[name]` (e.g. `"1Mb"`,
  `"100kb"`), each a `bins`-schema table plus its own `tracks`.
  `cd.rebin("1Mb", agg="mean")` aggregates spots / tracks onto another
  set and returns a new `ChromData` whose active set is `"1Mb"`.
- Contacts are multi-resolution natively (`mcool`), so they do not need
  binsets; `ContactRef.bins(resolution)` returns a bin table that can be
  registered as a binset.

### Migration / compat

- `_read_v1` builds `bins` from `spots[["chrom","start","end"]]
  .drop_duplicates()` (same logic as `fea.project.unique_spot_intervals`)
  and derives `spots["bin_id"]`.
- A 1.x `tracks` table (spot-aligned) is split on read: columns that are
  constant for every spot sharing a `bin_id` move to bin-level `tracks`;
  the rest stay in `spot_tracks`.  The split is logged.
- For the whole 2.x series `cd.tracks_spot_view()` (and a deprecated
  `cd.tracks` property that warns when accessed with spot-length
  expectations) returns the old spot-aligned frame.
- Constructors keep accepting `spots` with `chrom/start/end` and no
  `bin_id`; `bins` is derived automatically.

### Open questions

- Should `bins` allow overlapping intervals (some tracing designs use
  overlapping probe sets)?  Proposal: allowed, but `rebin` and
  `project_*` warn.
- Haplotype-resolved data: is the haplotype a spot attribute
  (`spots["haplotype"]`) or a bin attribute?  Proposal: spot attribute;
  bins are haplotype-agnostic.

---

## 3. Unified analysis API

**Status:** implemented for the `strc` callers (roadmap step 2, format
1.4).  `uchrom.core.results` holds `ResultsStore` / `ResultRecord`,
`uchrom.core.convention` the shared helpers, `uchrom.tl` / `uchrom.pp`
the aliases.  Differences from the text below, as built:

- On disk the value stays where 1.2/1.3 put it (`results/<key>`) and the
  provenance is added as attrs on it (`_kind`, `_function`, `_params`,
  `_inputs`, `_uchrom_version`, `_created_utc`) instead of moving the
  value under `results/<key>/value`, so 1.x readers still read results.
- `call_tads_di(cd, *, contacts=...)` resolves `contacts` through
  `cd.uns["linked_cool"]` (or a path) until `cd.contacts` exists (step 4).
- The FISHnet ensemble is stored at `f"{key_added}.ensemble"` as
  `{chrom: {"mask", "bin_ids", "n_traces"}}`.
- Existing `*Params` dataclasses are not made frozen (that would break
  callers that mutate them); the new `DICallerParams` is frozen.
- `fea.*`, `im.*`, `recon.*`, `emb.*` and `pl.*` are not converted yet.

### Namespace

**Recommendation:** keep the existing domain modules (`recon`, `im`,
`strc`, `fea`, `emb`, `pl`) — they map onto how users think about
chromatin analysis and are already documented — but enforce *one calling
convention* across all of them, plus thin scanpy-style aliases:

```python
import uchrom as uc
uc.tl.call_tads(cd, method="arcfish")      # alias → uchrom.strc.tad.call_tads_by_pval
uc.pp.impute(cd, method="snapfish")        # alias → uchrom.im.impute.impute_coordinates
uc.pl.distance_matrix(cd, trace_id=3)
```

`uc.pp` = preprocessing that changes coords / spots (impute, align,
normalise, rebin); `uc.tl` = tools that add annotations (structures,
features, embeddings, reconstruction); `uc.pl` = plotting.  Aliases are a
flat, discoverable surface; the domain modules remain the canonical home
and hold the implementations.

### Calling convention

Every public analysis function follows:

```python
def call_tads_by_pval(
    cd: ChromData,
    *,
    chrom: str | Sequence[str] | None = None,   # None = all chroms
    trace_ids: Sequence | None = None,          # optional selection
    cells: Sequence | None = None,
    params: TADCallerParams | None = None,      # frozen dataclass, all knobs
    device: str = "auto",
    key_added: str = "tads.arcfish",            # where the result is stored
    copy: bool = False,                         # True → return modified copy
) -> pd.DataFrame | ChromData | None: ...
```

Rules:

1. `cd` first, keyword-only after it.
2. Selection via `chrom` / `trace_ids` / `cells`; `chrom=None` iterates
   chromosomes internally and **merges** per-chrom outputs into one
   table (with a `chrom` column) under a single key — no more one key per
   chromosome or last-chrom-wins overwrites.
3. All tuning knobs in a frozen `*Params` dataclass (the pattern already
   used by `TADCallerParams`, `LoopCallerParams`, `FISHnetParams`,
   `SpotAlignerParams`, `GEMFISHParams`).
4. `key_added` replaces `result_key` / `store`; default key is
   `"<what>.<method>"`.
5. Return value: `copy=False` → the primary table (what users look at);
   `copy=True` → a new `ChromData`.  Functions never return `None`
   silently.
6. Matrix-level kernels (e.g. `calc_directionality_index(contact_mat)`,
   `smacof(dist_mat)`) stay public but live in a `*.core` / `_kernels`
   submodule and are documented as low-level; the `cd`-level wrapper is
   the user API.

### Results store with provenance

`cd.results` becomes a `ResultsStore` (a `MutableMapping`) whose values
are `ResultRecord`s:

```python
@dataclass
class ResultRecord:
    kind: str            # "table" | "intervals" | "array" | "mapping" | "scalar"
    value: Any           # DataFrame | ndarray | JSON-able mapping | scalar
    params: dict         # asdict(params)
    function: str        # "uchrom.strc.tad.call_tads_by_pval"
    uchrom_version: str
    inputs: dict         # {"coords_layer": "X", "contacts": "hic_bulk", "chrom": [...]}
    created_utc: str
```

`cd.results["tads.arcfish"]` returns the value (backward compatible);
`cd.results.record("tads.arcfish")` returns the full record.  Interval
outputs are *also* exposed through `cd.intervals` (same object, not a
copy).  This subsumes today's `fea.registry.append_feature_registry_entry`
(which becomes the implementation of the provenance write).

**Serialisation contract:** every `ResultRecord.kind` has a declared
writer/reader; assigning a value whose type has no writer raises
`TypeError` *at assignment time*, not at `write()`.  Round-trip tests
cover each kind.  (The current silent-drop bug is the motivating case.)

### Reconstruction returns `ChromData`

- `recon.sc.nucdyn`, `recon.sc.gem`, `recon.bulk.mds` get library entry
  points `reconstruct_*(cd | contacts_path, ...) -> ChromData`, mirroring
  `recon.fish.reconstruct_gem_fish` which already does this.
- Their `__main__` CLIs become thin wrappers: read input → call library
  function → `cd.write(out.h5cd)`; `.csv` output kept via
  `--format csv` → `cd.to_dataframe().to_csv`.
- Inputs come from `cd.contacts[key]` when given a `ChromData`, so the
  reconstructed coordinates land in the same object as the contacts,
  with `coord_status="reconstructed"` and a `layers["recon.<method>"]`
  copy when coords already existed.

### API mapping (existing → 2.0)

| Existing | 2.0 form | Notes |
|----------|---------|-------|
| `strc.tad.call_tads_by_pval(cd, chrom, params, device, store, result_key)` | `call_tads_by_pval(cd, *, chrom=None, params, device, key_added="tads.arcfish", copy)` → alias `tl.call_tads(method="arcfish")` | merged per-chrom table; also `cd.intervals` |
| `strc.tad.call_domains_fishnet(cd, …)` | `call_domains_fishnet(cd, *, chrom=None, params, key_added="tads.fishnet")` | ensemble mask → `ResultRecord(kind="mapping")` |
| `strc.tad.call_domains_fishnet_trace(...)` | unchanged (per-trace kernel) | low-level |
| `strc.tad.get_domains(contact_mat, …)` / `calc_directionality_index` | `call_tads_di(cd, *, contacts="hic_bulk", resolution, chrom=None, key_added="tads.di")`; kernels stay | Hi-C path now `cd`-based |
| `strc.loop.call_loops_axiswise_f(cd, chrom, …)` | `call_loops_axiswise_f(cd, *, chrom=None, …, key_added="loops.axiswise_f")` → `tl.call_loops` | `kind="pair"` intervals |
| `strc.comp.call_compartments_axes_pc(cd, chrom, …)` | same convention, `key_added="compartments.axes_pc"` → `tl.call_compartments` | PC1 → `cd.tracks`, segments → `cd.intervals` |
| `strc.call_tads_multi / call_loops_multi / call_compartments_multi / call_structures_multi` | removed; replaced by `chrom=None` on each caller | |
| `strc.add_structural_features / compute_structural_features` | `tl.structural_features(cd, keys=[...])` → writes `cd.tracks` (bins) | |
| `fea.add_sequence_features / add_annotation_features / add_peak_features` | same names, write `cd.tracks` (bins) + `ResultRecord` | `project=` flag goes away |
| `fea.compute_*_features` | unchanged (pure functions on interval tables) | |
| `fea.mean_distance_matrix / contact_frequency / radius_of_gyration(df)` | take `cd`; `radius_of_gyration` → `cd.traces["rg"]`; matrices returned, optionally stored as in-memory `ContactRef` | |
| `fea.axis_variance_cube / filter_normalize / axis_weight` | low-level kernels, unchanged | |
| `fea.project.project_interval_features_to_spots` | `project_interval_features_to_bins` | spot version deprecated |
| `im.impute.impute_coordinates(cd, method)` | `impute_coordinates(cd, *, method, layer_added="imputed", copy)` → `pp.impute` | sets `coord_status="imputed"` |
| `im.trace.align_spots(...)` | `align_spots(cd, *, params, key_added)` → `pp.align_spots` | output = `trace_id` assignment |
| `recon.fish.reconstruct_gem_fish(hic_path, chrom, fish_cd, …)` | `reconstruct_gem_fish(cd, *, contacts="hic_bulk", chrom, …)` | path form kept as convenience |
| `recon.sc.nucdyn` / `recon.sc.gem` (CLI, CSV) | `reconstruct_nucdyn(cd, *, contacts, cells)` / `reconstruct_gem(...)` → `ChromData` | CLI wraps library |
| `recon.bulk.mds.run_mds(contact_mat)` / `inter_mds(path)` / `partitioned_mds` | `reconstruct_mds(cd, *, contacts, resolution, chrom=None, mode="intra"|"inter"|"partitioned")` | kernels stay |
| `emb.higashi.run(...)` | `embed_higashi(cd, *, contacts="schic", key_added="X_higashi")` → `tl.embed` | writes `cellm`, imputed maps as `ContactRef` |
| `pl.plot_distance_matrix / plot_contact_map / plot_rg_histogram / plot_structure_3d` | `pl.distance_matrix(cd, …)` etc. (old names aliased) | take `cd`, not raw arrays |
| `io.load_cool / load_hic / load_hic_inter / load_hic_genome` | `ContactRef` backends; `io.*` kept as wrappers | |

### Open questions

- `copy=False` returning a table vs scanpy's "return None": returning the
  table is friendlier in notebooks and is what current callers already do;
  keep it.
- Should `uc.tl` / `uc.pp` exist at all, or only the convention?  They
  cost almost nothing (re-exports) and help discoverability; recommend
  adding them once at least three callers conform.

---

## 4. OOM-friendly storage

**Status:** implemented on a **Zarr + Parquet container**,
`<name>.chromdata.zarr` (roadmap steps 6, 7 and 8; format 2.1 since step 7 — see
*Format 2.0 container: `.chromdata.zarr`* below).  The HDF5 plan in the
rest of this section was the starting point; the Figure 2 benchmarks (#64)
showed HDF5 to be the bottleneck (1e7 real spots: h5cd 1.x 5.50 GB, 7.2 s
full read, 23.5 GB peak RSS, against Parquet 2.11 GB, 0.73 s, 13.1 GB), so
the container changed.  As built:

- sorted spots, the `index/` offsets, backed mode (`read(path,
  backed=True)`, `get_*`, `iter_traces` / `iter_cells`, `to_memory()`),
  float32 coords (opt-in) and compression are done;
- the data model (section 2) is unchanged, and the HDF5 `.h5cd` 2.0 of
  #65 stays readable (writing it warns);
- step 7 is done (format 2.1): spot tables partitioned by chromosome,
  `columns=` / `tracks=` selection, the streaming writer and imports, the
  streaming population callers and the memory budget — see *Format 2.1*
  and *Streaming (roadmap step 7, as built)* below;
- not done: `backed="r+"`, `binsets/`, streaming compartments / FISHnet.
  Backed `spots` is a light proxy (`BackedFrame`), not a `DataFrame`
  subclass.

### Goals

- Open a 1e8-spot file in constant memory; read only the traces / cells /
  chromosome being analysed.
- Import FOF-CT / seqFISH+ dumps larger than RAM by streaming.
- Keep the in-memory API identical — backed and in-memory objects expose
  the same attributes.

### Physical ordering and row-group index

2.0 writes spots **sorted by `(cell_id, trace_id, bin order)`** and stores
offset indexes so any cell / trace / chromosome is a small number of
contiguous slices:

```text
index/
├── trace_offsets   int64 (n_traces + 1)   spot row range per trace (in traces order)
├── cell_offsets    int64 (n_cells + 1)    spot row range per cell
└── chrom_trace     int32 (n_traces)       chrom code of each trace (traces are single-chrom)
```

`get_trace(t)` → one slice; `get_cell(c)` → one slice; `get_chrom(ch)` →
the union of that chromosome's trace slices (read in order, coalesced).
In-memory objects build the same index lazily (`np.searchsorted` on the
sorted codes) so subsetting also stops doing full-table boolean scans.

### Backed mode

*As built:* `ChromData.read("big.chromdata.zarr", backed=True)` (read-only;
`"r+"` is not implemented).  The plan was:

```python
cd = ChromData.read("big.h5cd", backed="r")     # or "r+"
cd.n_spots, cd.cells, cd.bins, cd.traces        # small tables: loaded eagerly
cd.coords                                        # BackedArray (h5py dataset proxy)
cd.spots                                         # BackedFrame: columns loaded on access
sub = cd.get_cell("c17")                         # in-memory ChromData, reads 1 slice
for batch in cd.iter_traces(batch=1024):         # in-memory ChromData per batch
    ...
cd.to_memory()                                   # explicit full load
```

- Eager: `bins`, `tracks` (bins-aligned — small), `traces`, `cells`,
  `cellm`, `intervals`, `results`, `uns`, `index/*`.
- Lazy: `coords`, `layers/*`, `spots/*` columns, `spot_tracks/*`.
- `contacts/*` are always external and lazy, in both modes.
- Slicing a backed object returns an **in-memory** `ChromData` (a copy of
  the slice).  Views over backed data are not offered — copies of small
  slices are cheap and avoid aliasing bugs.  In-memory subsetting keeps
  returning copies, but stops sharing `results` / `uns` by reference (1.x
  `__getitem__` passes `self.results` / `self.uns` through, so mutating a
  subset mutates the parent).
- `backed="r+"` allows appending columns / layers / results without
  rewriting coords.

### Streaming iterators and per-trace compute

```python
cd.iter_traces(batch=1024, chrom=None, columns=None)   # yields ChromData
cd.iter_cells(batch=64)
cd.compute_distances(trace_id=t)                       # reads one slice
cd.map_traces(fn, batch=1024, n_jobs=4)                # fn(ChromData) -> DataFrame, concatenated
```

Population-level callers (`call_loops_axiswise_f`, `call_tads_by_pval`,
`call_compartments_axes_pc`, `fishnet`) accumulate per-bin-pair
statistics over `iter_traces` batches instead of stacking all traces of a
chromosome at once; the axis-variance cube becomes a streaming reduction
(sum / sum-of-squares / count per bin pair).  Memory then scales with
`n_bins(chrom)²`, not `n_traces × n_bins²`.

### Memory budget knobs

```python
uchrom.settings.memory_budget = "8GB"   # default: 50 % of available RAM
uchrom.settings.default_batch = "auto"  # batch size derived from budget
```

`iter_*` with `batch="auto"` and the population callers size their
batches from the budget; `to_memory()` / `read(backed=None)` warn when
the estimated footprint exceeds it.

### Chunked write / streaming import

```python
with ChromData.writer("big.h5cd", bins=bins, cells=cells, coord_dtype="float32") as w:
    for chunk in pd.read_csv("fofct_core.csv", comment="#", chunksize=2_000_000):
        w.append(coords=chunk[["X","Y","Z"]].to_numpy(), spots=to_spots(chunk))
# on close: external sort by (cell, trace, bin) if input was unsorted,
# then write index/*
```

`from_fofct(path, out="big.h5cd")` and `from_seqfish_multiomics(glob,
out=...)` use the writer when the input exceeds the memory budget and
return a backed `ChromData`.  Categorical columns are encoded with a
dictionary accumulated across chunks.

### dtypes and compression

| dataset | default dtype | option |
|---------|---------------|--------|
| `coords`, `layers/*` | float64 | `coord_dtype="float32"` — halves size; recommended for imaging (nm/µm precision ≪ float32 eps) |
| `spots/bin_id` | int32 | |
| categorical codes (`trace_id`, `cell_id`, `chrom`) | int8/16/32 by cardinality, + `categories` dataset | replaces 1.x byte-string storage |
| `spots/*` numeric extras | as given | |

- Chunking: `coords` chunked `(rows_per_chunk, 3)` with
  `rows_per_chunk ≈ 64k`, aligned to trace boundaries where practical.
- Compression: `gzip` level 4 by default (universally readable),
  `lzf` / `blosc` (via `hdf5plugin`) opt-in.  Categorical codes and
  offsets compress very well.

### HDF5 vs zarr

| | HDF5 (h5py) | zarr |
|---|---|---|
| single-file, easy to share | ✅ | ❌ (directory / zip) |
| existing format + readers | ✅ (1.x is HDF5) | ❌ new stack |
| concurrent parallel writes | ❌ (single writer) | ✅ |
| cloud / object storage | weak | ✅ native |
| append columns without rewrite | ✅ | ✅ |
| ecosystem alignment | AnnData `.h5ad`, cooler | AnnData zarr, SpatialData |

The first recommendation here was to stay on HDF5 for 2.0.  The Figure 2
benchmarks (#64) changed that: on real data the per-spot tables dominate,
and a columnar table format (Parquet) beat both HDF5 layouts on size, read
time and peak memory.  **Decision (format 2.0 as shipped): a Zarr
container with the large tables stored as Parquet** — the SpatialData
approach.  `.cdz` (the same tree zipped, uncompressed) restores the
single-file property.

### Format 2.0 container: `.chromdata.zarr`

```text
x.chromdata.zarr/
├── zarr.json                  root group; attrs: uchrom_format_version "2.0",
│                              uchrom_version, uchrom = {format, format_version,
│                              spot_order "cell,trace,bin", n_spots, n_bins,
│                              n_traces, n_cells, n_row_groups, has_source_row, …}
├── tables/                    zarr group; attrs["tables"] = table metadata
│   ├── spots.parquet          sorted by (cell, trace, bin): bin_id int32,
│   │                          trace_id / cell_id int16/32 codes, x, y, z,
│   │                          extra spot columns (coord_status, spot_id, …);
│   │                          row groups of ~65,536 rows ending on cell
│   │                          boundaries; statistics on
│   ├── spot_tracks.parquet    row-aligned with spots (same row groups)
│   ├── layers/<key>.parquet   row-aligned x, y, z
│   ├── categories/<table>.<col>.parquet   values of the coded columns
│   ├── bins.parquet           chrom (dictionary), start, end, [name, …]
│   ├── bin_tracks.parquet  traces.parquet  cells.parquet
│   ├── intervals/<key>.parquet            (+ kind, source_result in attrs)
│   └── points/<key>.parquet
├── index/                     zarr arrays: trace_offsets, trace_codes,
│                              trace_cells, chrom_trace, cell_offsets,
│                              cell_codes, row_groups, [source_row]
├── cellm/<key>, binm/<key>    zarr arrays (zstd)
├── results/<key>              zarr group / array; attrs = provenance + _type;
│                              tables as <key>/table.parquet
├── uns/                       attrs (JSON) + arrays for numeric arrays > 64 values
├── contacts/                  attrs: linked .cool / .scool records
└── links/                     attrs: linked .h5ad / .h5mu records
```

The authoritative layout is `uchrom/core/spec.md`; the code is
`uchrom/core/zarrcd.py` (container, writer, readers) and
`uchrom/core/backed.py` (`BackedChromData`).

**Decisions**

1. **Parquet for rows, Zarr for arrays, JSON attrs for metadata.**  Every
   table (spots, tracks, cells, traces, bins, intervals, points, result
   tables) is Parquet, zstd level 3.  `cellm`, `binm`, `index/` and result
   arrays are Zarr v3 arrays (zstd).  Provenance, `uns`, table metadata and
   linked-file records are attributes.  Parquet gives column pruning,
   row-group reads, per-column encodings and statistics, and every
   dataframe tool (DuckDB, Polars, Arrow) reads the files directly.
2. **Zarr v3 (zarr-python ≥ 3).**  That needs Python ≥ 3.11, so the
   package now requires 3.11 (CI tests 3.11 and 3.12).  Zarr format 2 via
   zarr-python 2.18 would have kept 3.10, at the cost of an older on-disk
   spec and two code paths.
3. **Coordinates live in `spots.parquet` as `x, y, z`**, not a separate
   array: one row-group read serves a cell's spots and coordinates, and the
   spots file on its own is the "structure table" of the project vision
   (minus the loci, which are `bins[bin_id]`).  `layers` are separate
   Parquet files with the same row groups.
4. **Categorical spot-aligned columns are integer codes** (int16 / int32)
   with the categories in `tables/categories/`, not Parquet dictionary
   columns.  Parquet dictionaries are per row group: a 60,000-category
   `trace_id` would either be repeated in every group or come back with
   per-group dictionaries that must be unified (and re-sorted into the
   original category order) on every read.  Codes decode with no string
   work and keep the category order exactly.  Small tables (bins, cells,
   traces, results) keep pandas categoricals as Parquet dictionaries.
5. **Spots are stored sorted by (cell code, trace code, bin_id)**, a
   stable sort.  Row groups end on cell boundaries (on (cell, trace) run
   boundaries when there is no `cell_id`), so `get_cell` reads one group,
   `get_trace` one group, and a chromosome is the union of its (cell,
   trace) runs.  The permutation is kept in `index/source_row`
   (`read(path, original_order=True)` restores the written order); an
   already sorted object is written unchanged, without `source_row`.  **Row
   order therefore changes on a round trip**: tests compare after sorting
   by a stable key, or read with `original_order=True`.
6. **The index is per (cell, trace) run**, not per trace id: a trace id
   shared by several cells (one trace per chromosome per cell, as
   `from_dataframe` assigns) has one run per cell.  `chrom_trace` is `-1`
   for a run spanning several chromosomes; `get_chrom` then filters those
   rows.  `iter_traces(batch)` counts runs.
7. **Backed mode reads row groups, not pages.**  pyarrow reads whole row
   groups; `SpotRows` keeps the two most recent decoded groups per file
   (sequential `iter_*` decodes each group once) and copies small
   selections out of a group so it can be freed.  Parquet files are read
   with plain file reads, not memory maps (mapped pages would count as
   resident memory).  65,536 rows per group was chosen on the 10.9 M-spot
   Takei data: 262,144 rows gave a 2 % smaller file and the same full-read
   time but doubled `get_cell` latency (8 → 19 ms).  Format 2.1 uses 16,384 rows (see *Format 2.1*).
8. **zstd level 3, float64 coordinates by default.**  On Takei FOV 0's 62
   float spot tracks, zstd-3 is 63 MB vs 69 MB (zstd-1), 92 MB (snappy)
   and 182 MB (none); decoding is ~25 % slower than snappy.
   Byte-stream-split made these tracks 2.5× larger (many repeated
   values), so it is off.  `coord_dtype="float32"` is opt-in: it saves
   38 % on the Liu 2025 MOp store (coords dominate), 4 % on the Takei
   cerebellum store (62 tracks dominate), and changes the values.
9. **Writes are atomic**: the store is built in a temporary sibling
   directory and renamed into place.  Writing over an existing store is
   allowed; writing over any other directory is refused; writing a backed
   object onto its own source is refused.
10. **`.cdz`** is the finished tree zipped with `ZIP_STORED`, `zarr.json`
    first.  Zarr reads it through `zarr.storage.ZipStore`; each Parquet
    member is read in place through a byte-range view of the archive (no
    fsspec needed).
11. **Linked files** (`uns["linked_cool" / "linked_scool"]` →
    `contacts/`, `uns["linked_anndata" / "linked_mudata"]` → `links/`)
    keep their records verbatim; absolute paths next to the store also
    get a relative copy, used on read when the absolute path no longer
    exists (a moved project folder).  In memory they stay in `uns`.
12. **Portable names**: keys that are not portable file / node names, or
    that clash case-insensitively (macOS), are stored as `_<i>`; the attrs
    map them back.  `uns` values keep their Python types (tuples, numpy
    arrays, NaN) through a small JSON tagging scheme.
13. **Dispatch by path**: `*.zarr` → zarr, `*.cdz` → zip, `*.h5cd` →
    HDF5; other existing paths are sniffed.  `write()` to `.h5cd` (and to
    unknown suffixes, as before) still writes HDF5 2.0 in this release,
    with a `DeprecationWarning`.  `python -m uchrom.io.upgrade old.h5cd`
    converts to `old.chromdata.zarr`.
14. **The web browser opens stores backed.**  Summaries, trace and cell
    lists come from `index/` plus the `bin_id` column; geometry requests
    that name cells, traces or chromosomes read only those rows and reuse
    the in-memory encoder, so responses are identical.  Other views load
    the per-spot columns they need on first use.

### Measured (real data, one M5 Pro laptop, 64 GB)

Takei 2025 cerebellum whole-cell subsets (62 per-spot tracks; #64 harness,
fresh process per trial, warm OS cache, median of 3):

| n_spots | format | size | write | full read | read peak RSS |
|---|---|---|---|---|---|
| 1.0e7 | h5cd 1.x (#64) | 5.50 GB | 3.5 s | 7.2 s | 23.0 GB |
| | h5cd 2.0 (#65) | 4.96 GB | 5.4 s | 4.4 s | 20.2 GB |
| | Parquet (flat table, snappy) | 2.11 GB | 13.3 s | 0.80 s | 12.8 GB |
| | **chromdata.zarr 2.0** | **1.90 GB** | 17.4 s | **0.98 s** | **6.0 GB** |
| | chromdata.zarr 2.0, float32 coords | 1.84 GB | 16.8 s | 0.94 s | 6.0 GB |

Backed access (`read(backed=True)`, fresh process): open 0.03 s at 1e7 and
0.19 s at 1e8 (a store of Takei rep 1 replicated 10×); `get_trace` /
`get_cell` 7 / 8 ms at 1e7 and 16 / 22 ms at 1e8; resident memory after
open 0.17 GB (1e7) / 0.43 GB (1e8).  `get_chrom` is a scan in this sort
order (0.8 s at 1e7, 8.9 s at 1e8).  Converting the 10.9 M-spot 1.x file
takes 45 s at 25 GB peak (the 1.x reader dominates); the store is 2.07 GB
(1.x: 6.29 GB, h5cd 2.0: 5.41 GB) and reads back value-identical.  Full
reads are ~20 % slower than a flat Parquet file: two zstd files instead of
one snappy file, and building a `ChromData` (loci from `bins`,
categoricals) instead of returning a flat DataFrame — but at half the peak
memory.  Full numbers: PR #66 and `u-chrom-paper/figures/fig2/results/`.

### Format 2.1: chromosome partitions

**Why.**  In 2.0, `get_chrom` was a scan: spots sorted cell › trace › bin
put every chromosome in every row group.  Profile of a backed `get_chrom`
on the Takei 2025 cerebellum subsets (fresh process, warm cache, chr1 /
chr7 / chr12 / chr19):

| n_spots | row groups read | spots: I/O + decode | spot_tracks (62 cols): I/O + decode | Arrow → pandas | ChromData assembly | total |
|---|---|---|---|---|---|---|
| 1e7 | 144 / 144 | 0.01–0.02 + 0.16–0.18 s (232 MB) | 0.07–0.13 + 0.36–0.41 s (1.64 GB) | 0.02–0.09 s | ~0.01 s | 0.72–0.84 s |
| 1e8 | 1439 / 1439 | 0.11–0.21 + 1.7–1.8 s (2.3 GB) | 1.0–1.3 + 8.3–9.8 s (16.5 GB) | 1.8–4.6 s | ~0.1 s | 8.8–13.2 s |

Decoding the whole `spot_tracks` file dominates (~70 %), then the whole
spots file (~25 %); the pandas conversion and the object assembly are
small.  Two fixes: read one chromosome's row groups only, and do not read
the tracks when only coordinates are needed.

**Layout.**  The spot-aligned tables are partitioned by chromosome, hive
style — `tables/spots/chrom=<name>/part-0.parquet`, the same for
`spot_tracks` and `layers/<key>` — in chromosome category order, sorted
(cell, trace, bin) inside a partition (stored order chrom › cell › trace ›
bin).  Rows are numbered globally, partition after partition; `index/`
keeps its 2.0 arrays with global offsets (`cell_offsets` now has one entry
per (chromosome, cell) run) plus `partition_offsets`, `partition_groups`,
`partition_chrom` and `cell_partition`.  `get_trace` reads one slice of
one partition, `get_chrom` one partition, `get_cell` one slice per
chromosome (partitions read in parallel threads).  A trace over several
chromosomes is split into one run per partition.  Full reads decode
partition by partition into preallocated single-chunk columns, so the
pandas conversion stays zero-copy and the peak is the table plus one
partition (a plain `concat_tables` doubled the peak: 5.9 → 10.8 GB).

**Column selection.**  `get_*`, `iter_*`, `to_memory`, `read(...)` take
`columns=` / `tracks=`; `columns="coords"` reads `x, y, z` and the key
columns only.  The web browser's geometry reads use it.

**Row-group size** (`benchmarks/fig2/rowgroup_sweep.py`, Takei 1e7, 3
fresh processes, query times pooled over 20 random ids × 3):

| rows / group | store | full read | get_trace | get_cell | get_chrom | get_cell, coords | get_chrom, coords |
|---|---|---|---|---|---|---|---|
| 8,192 | 2.96 GB | 1.26 s | 5.2 ms | 22.5 ms | 42.4 ms | 4.7 ms | 13.5 ms |
| **16,384 (default)** | **2.58 GB** | **1.17 s** | **5.3 ms** | **24.5 ms** | **41.0 ms** | **4.6 ms** | **13.4 ms** |
| 32,768 | 2.67 GB | 1.14 s | 6.1 ms | 29.9 ms | 39.4 ms | 4.6 ms | 13.3 ms |
| 65,536 | 2.57 GB | 1.15 s | 7.6 ms | 47.7 ms | 39.6 ms | 4.4 ms | 13.3 ms |

A cell has spots on every chromosome, so `get_cell` decodes one group per
chromosome and table; halving the group halves that work until per-call
overheads dominate.  16,384 rows keeps the file within 0.2 % of the
smallest and the full read within 3 %, and makes `get_cell` 2× faster than
65,536; 8,192 buys 2 ms for a 15 % larger file.

**Before / after** (panel b / c harness, 3 fresh processes; 1e8 = rep 1
replicated):

| | 2.0 | 2.1 |
|---|---|---|
| backed `get_chrom`, 1e7 / 1e8 | 0.77 s / 8.9 s | 0.040 s / 0.49 s |
| … with `columns="coords"`, 1e7 / 1e8 | — | 0.013 s / 0.14 s |
| backed `get_cell`, 1e7 / 1e8 | 7.9 ms / 22 ms | 23 ms / 42 ms (`coords`: 4.4 / 22 ms) |
| backed `get_trace`, 1e7 / 1e8 | 7.1 ms / 16 ms | 5.3 ms / 20 ms |
| full read, 1e7 | 0.98 s, 6.1 GB peak | 1.11 s, 6.8 GB peak |
| store, Takei 1e7 subset (62 tracks) | 1.90 GB | 2.58 GB (+36 %) |
| store, Takei rep 1 (10.9 M spots) | 2.17 GB | 2.94 GB (+35 %) |
| store, Liu 2025 MOp (no tracks) | 294 MB | 285 MB (−3 %) |
| backed memory after trace + cell queries, 1e7 / 1e8 | 0.35 / 0.57 GB | 0.82 / 1.30 GB |

**Regressions, stated plainly.**  `get_cell` is ~3× slower at 1e7 and ~2×
at 1e8 on data with many per-spot tracks (one row group per chromosome
instead of one; with `columns="coords"` it is faster than before); the
backed process holds more (the 256 MB row-group cache fills with
per-chromosome groups); tiny stores carry per-partition overhead (1e4
spots: 2.6 → 4.6 MB); full reads are 13 % slower; and the Takei store is
35 % larger.  The size (`benchmarks/fig2/spot_tracks_encoding.py` →
`results/spot_tracks_encoding.json`, Takei rep 1's 62 tracks, 10.9 M
rows): with identical Parquet options the same `spot_tracks` take 1.82 GB
in the 2.0 order and 2.56 GB in the 2.1 order — the per-spot z-scores
repeat within a cell *across* chromosomes (neighbouring voxels), which the
cell-contiguous 2.0 order put in the same zstd pages.  No encoding
recovers it: 65k / 262k-row groups 2.57 / 2.53 GB; zstd-9 / -15 2.44 /
2.41 GB at 5× / 11× the write time; dictionary encoding of the floats
3.42 GB; `BYTE_STREAM_SPLIT` 4.63 GB (the repeated values compress worse
once their bytes are split).  Defaults unchanged (zstd-3, 16k rows); the
cost is inherent to partitioning by chromosome, and is the price of the
16–22× faster `get_chrom`.

**Compatibility.**  `ZARR_FORMAT_VERSION = "2.1"`; readers dispatch on
`tables.attrs["tables"]["spots"]["layout"]` — a 2.0 store is read as one
unpartitioned partition, in memory and backed.  A 2.0 reader cannot read a
2.1 store (it finds no `tables/spots.parquet`): a MINOR bump that is not
additive for old readers, accepted because the container is new and
`python -m uchrom.io.upgrade old.chromdata.zarr new.chromdata.zarr`
rewrites stores.  The zarr container version is now separate from the
`.h5cd` `FORMAT_VERSION` (2.0).

### Format 2.2: coordinates once, cell-sorted primary tables, derived columns

**Why.**  2.1 bought a 20× faster `get_chrom` with a 35 % larger Takei
store and a 3× slower `get_cell` (one row group per chromosome for 62
tracks).  A first attempt at "both" (PR #70: the 2.0 primary plus a
chromosome-partitioned *copy* of the coordinates, and a lossless decimal
float codec) reached 2.0's `get_cell` and 2.1's `get_chrom(coords)`, but
duplicated the coordinates (Liu 2025: 387 MB vs 311 MB for a flat Parquet
file) and read 39 % slower than flat Parquet.  Its profile named the
costs: Arrow decode ~0.25 s, copies ~0.2 s, the float codec ~0.2 s, and
~0.22 s turning the 10 M per-spot probe names (`"chr10-1393"`, one per
bin) into Python strings.

**Layout** (`uchrom/core/spec.md`):

- Coordinates + keys (`bin_id`, trace / cell codes, x, y, z) are stored
  **once**, partitioned by chromosome (`tables/coords/chrom=<c>/`, sorted
  by (cell, trace, bin), 16,384-row groups).
- Every other spot-aligned column (extra spot columns, `spot_tracks`,
  `layers`) is in cell-sorted **primary** tables (`tables/primary/`,
  order cell › trace › chromosome › bin, 65,536-row groups on cell
  boundaries), with **no key columns**.  Each (cell, trace, chromosome)
  triple is one run on both sides with its rows in the same order;
  `index/coords/primary_run` maps the runs one to one.
- Spot columns that are a function of the bin, the cell or the trace are
  stored **once per key** (`tables/derived/<key>.parquet`), detected on
  write (bitwise for numbers, `str` equality for object columns, codes for
  categoricals), rebuilt with one gather on read — exact dtype and values.
  Takei's `name` (one probe name per bin) and Liu's `Chrom_order`,
  `Sample_ID`, `RNA/DNA_experiment_ID` (per bin) and `FOV_ID`,
  `CellID_byFOV` (per cell) qualify.  A column already in `bins` with the
  same values is referenced, not stored.
- Float columns of the primary tables use Parquet dictionary pages
  (per-spot z-scores repeat within a cell; Parquet falls back to plain
  pages per column chunk).  The PR #70 decimal codec is kept as an option
  (`float_encoding=`), off by default: it saves space but costs read time.
- The reader decodes row groups in parallel threads into preallocated
  buffers; a full read reads the coordinate partitions as stored, then
  gathers them into primary order block by block (random reads, sequential
  writes — scattering into the strided `(n, 3)` array was 3× slower);
  derived columns and loci are materialised with multi-threaded gathers;
  the `index/` arrays are fetched concurrently with the small tables.

**Measured** (`benchmarks/fig2/cd22_variants.py` →
`u-chrom-paper/figures/fig2/results/cd22_v2_variants.json`; Takei 2025 rep 1 whole-cell
subsets with 62 spot tracks, Liu 2025 MOp 9.58 M spots; 3 fresh processes,
median, warm cache; 20 random ids × 3 per query level; streaming = exact
chr11 median map under a 2 GB budget; Apple M5 Pro, 64 GB):

| data | store | size | write | full read | read peak | get_trace | get_cell | get_chrom | get_chrom coords | streaming |
|---|---|---|---|---|---|---|---|---|---|---|
| Takei 1e7 | Parquet (defaults) | 2115 MB | 14.7 s | 0.76 s | 12.8 GB | — | — | — | — | — |
| Takei 1e7 | 2.1 | 2575 MB | 23.2 s | 0.81 s | 8.4 GB | 5.6 ms | 25.0 ms | 39 ms | 13.9 ms | 4.3 s, 1.64 GB |
| Takei 1e7 | **2.2** | **1813 MB** | 18.8 s | **0.57 s** | **9.1 GB** | 5.9 ms | **8.5 ms** | 533 ms | 14.7 ms | 4.8 s, 1.69 GB |
| Takei 1e6 | Parquet / 2.1 / 2.2 | 212 / 264 / 183 MB | 1.4 / 2.5 / 2.5 s | 0.13 / 0.14 / 0.14 s | 1.5 / 1.3 / 1.5 GB | — / 1.6 / 1.4 ms | — / 1.5 / 1.3 ms | — / 6.5 / 30 ms | — / 2.1 / 2.1 ms | — / 0.9 / 0.9 s |
| Takei 1e5 | Parquet / 2.1 / 2.2 | 23 / 32 / 20 MB | 0.2 / 0.5 / 0.4 s | 0.05 / 0.07 / 0.07 s | 0.30 / 0.34 / 0.30 GB | | | | | |
| Liu MOp | Parquet / 2.1 / 2.2 | 311 / 272 / **255** MB | 2.1 / 4.0 / 3.3 s | 0.23 / 0.28 / 0.25 s | 2.6 / 2.2 / **2.0** GB | — / 6.0 / 5.5 ms | — / 7.9 / 6.9 ms | — / 20 / 89 ms | — / 15.9 / 17.4 ms | |

Ablations at Takei 1e7 (size, full read): the default 1813 MB, 0.55 s;
without derived columns 1851 MB, 0.80 s (the probe-name strings); without
float dictionary pages 1855 MB, 0.65 s; + decimal codec on the coordinates
1771 MB, 0.55 s (Liu: 209 MB but 0.29 s); + decimal codec everywhere
1624 MB, 0.76 s; the serial pre-2.2 reader 2.54 s (peak 6.0 GB).

**Wins.**  Smaller than flat Parquet and than 2.1 on both datasets
(Takei −14 % / −30 %, Liu −18 % / −6 %); full read 25 % faster than Parquet
at 1e7 with 29 % less peak memory; `get_cell` back at 2.0 speed (8.5 ms vs
25 ms in 2.1); `get_chrom(columns="coords")` and streaming unchanged.

**Losses, stated plainly.**  `get_chrom` *with* the spot tracks reads a
slice of every primary row group: 0.53 s at 1e7 (2.1: 39 ms; 2.0: 0.77 s)
— use `columns="coords"` or `tracks=[...]`; full reads of small stores pay
the open cost (1e5: 0.07 vs 0.05 s); Liu reads 9 % slower than Parquet
(0.25 vs 0.23 s); writes are slower than Parquet (18.8 vs 14.7 s at 1e7).

**Compatibility.**  `ZARR_FORMAT_VERSION = "2.2"`; readers dispatch on
`tables.attrs["tables"]["spots"]["layout"]` ("primary+coords"); 2.0 and 2.1
stores stay readable in memory and backed.  `python -m uchrom.io.upgrade`
rewrites a store and keeps its original row order.  The streaming writer
writes 2.2 (identical to the in-memory writer, derived columns included:
one extra pass over the spill runs).  The real stores were converted
(`benchmarks/cd22_convert_validate.py` →
`u-chrom-paper/figures/fig2/results/cd22_convert_validation.json`): Takei rep 1
2.94 → 2.05 GB, Liu 285 → 267 MB, both bitwise identical in original
order, backed subsets equal to in-memory ones.

### Streaming (roadmap step 7, as built)

- **Memory budget**: `uchrom.settings.memory_budget` (bytes or `"8GB"`;
  default half of the available RAM); `iter_*(batch="auto")` sizes batches
  from it.  macOS / glibc keep freed pages resident, so the band loops call
  `uchrom.utils.memory.release_memory()`.
- **Writer**: `ChromData.writer(path)` →
  `uchrom.core.stream.ChromDataWriter`.  `append` spills each chunk, split
  by chromosome and sorted by the range key (cell id, or trace id), to a
  Parquet run; loci get provisional ids; trace / cell ids are collected.
  `finish` fixes the bins (given, or `bins_from_loci` of the loci seen),
  the categories (sorted, as `astype("category")`), and writes each
  partition in pieces of whole cells (one slice per run, budget-sized),
  sorted by (cell, trace, bin, input row), through the same
  `SpotPartitionWriter` as the in-memory writer — rows, order, `index/`,
  row groups and `source_row` are identical.  Column types are unified
  over chunks (int → float when a later chunk has NaN).  (This answers the
  open question on external sorting: in-house.)
- **Imports**: `ChromData.from_fofct(path, out=..., chunksize="auto")`
  (header scanned, then `pd.read_csv(chunksize=)`), and
  `read_seqfish_multiomics(glob, out=...)` (one FOV at a time; bins and
  cells from the loci / cell ids seen); both return the store backed.
- **Population statistics**: `uchrom.fea.distance_map(cd, chrom,
  "median" | "mean")` — exact.  The mean accumulates per-pair sums in trace
  order (`np.add.at`, the additions the dense `np.nanmean` makes, same
  order: bitwise equal).  An exact median needs all values of a pair, so
  the pair observations are gathered one *row band* of the matrix at a
  time (rows `i` whose pairs `(i, j > i)` fit the budget, 80 bytes each)
  and reduced with a grouped median — one pass over the chromosome's
  traces per band; memory is the band plus the `n_bins²` output,
  independent of the number of traces.  No approximation.  The ArcFISH
  loop F-test and TAD caller stream the same way
  (`uchrom.fea.arc_stream.axis_cube_streaming`, `streaming=True`, default
  on backed data): exact lower medians (`torch.nanmedian` semantics),
  identical outlier masks, filtered variances equal to the torch path up to
  summation order (≤ 1e-9 relative in tests), same calls.
  `call_compartments_axes_pc` and `fishnet` are not streamed yet.
- **Real data** (`benchmarks/cd21_streaming_validation.py`,
  `benchmarks/fig2/d_streaming.py`; M5 Pro, 64 GB):
  - Liu 2025 MOp FOF-CT (1.68 GB, 9.58 M spots): in-memory `from_fofct` +
    write 12.6 GB peak / 20 s; `from_fofct(out=, memory_budget="4GB")`
    1.3 GB / 20 s; the two stores are value-identical (stored and original
    order, `index/` identical).
  - Takei 2025 rep 1, 3 FOV CSVs (7.9 GB, 10.9 M spots):
    `read_seqfish_multiomics` in memory + write 28.1 GB / 142 s; with
    `out=` 15.0 GB / 165 s (the peak is one FOV's CSV parse); identical.
  - Median and mean distance maps, streaming vs in memory, bitwise
    identical: Takei chr19 / chr11 / chr1 (chr1: 7,656 bins, 200 M pair
    observations, 60 bands at a 1 GB budget, 14 s) and all 20 Liu
    chromosomes (also identical to the dense `mean_distance_matrix`).
  - Panel d (chr11 median map): streaming peaks at 1.6 GB (1e7 spots,
    54 k traces, 4 bands) and 2.3 GB (1e8, 540 k traces, 551 M pair
    observations, 31 bands) under a 2 GB budget; "load all" takes 9.7 GB
    at 1e7 and does not fit at 1e8.  Identical at every size.
  - ArcFISH on Takei 2021 mESC (FOF-CT, 20 chromosomes): loops 5 = 5,
    same calls, p-values identical; TADs 223 = 223, same calls, max
    relative p-value difference 4e-12.  Streaming is slower on this small
    dataset (12 vs 7 s; 8 vs 3 s).

### Format 2.0 HDF5 layout (the first plan)

As built by #65 (without `index/`, sorted spots, `contacts/`, `links/`),
this is the deprecated `.h5cd` container; the plan was:


```text
data.h5cd
├── @uchrom_format_version = "2.0"
├── @uchrom_version        = "0.3.0"
├── @spot_order            = "cell,trace,bin"     (or "unsorted")
├── bins/                  DataFrame group (index = bin_id)
├── binsets/<name>/        optional: bins-schema DataFrame + tracks/
├── tracks/                DataFrame group, n_bins rows
├── binm/<key>             (n_bins, …)
├── spots/                 DataFrame group, n_spots rows
│   ├── bin_id             int32, chunked, compressed
│   ├── trace_id/          {codes int*, categories}
│   ├── cell_id/           {codes int*, categories}
│   └── coord_status/      {codes, categories}  (optional)
├── coords                 (n_spots, 3) float32|float64, chunked — absent when coords is None
├── layers/<key>           (n_spots, 3)
├── spot_tracks/           DataFrame group, n_spots rows
├── traces/                DataFrame group
├── cells/                 DataFrame group
├── cellm/<key>            (n_cells, …)
├── index/                 trace_offsets, cell_offsets, chrom_trace
├── contacts/<key>/        attrs + optional cell_map (section 1)
├── links/<key>/           external cell-level modalities (h5ad / h5mu)
├── intervals/<key>/       DataFrame group, @kind
├── results/<key>/         @kind, @function, @uchrom_version, @created_utc,
│                          params (JSON attr), inputs (JSON attr), value/…
└── uns/                   unchanged from 1.x
```

### Read dispatch

*As built:* `ChromData.read(path, backed=False, original_order=False)`
dispatches on the path first (`uchrom.core.zarrcd.container_kind`):
`.chromdata.zarr` / `.cdz` → `BackedChromData`, loaded with `to_memory()`
unless `backed=True`, after the same MAJOR / MINOR check
(`_check_zarr_version`); `.h5cd` → the HDF5 readers below, and
`backed=True` raises with the `upgrade` command.  The plan was:

```python
FORMAT_VERSION = "2.0"
_SUPPORTED_MAJORS = {1: _read_v1, 2: _read_v2}

def read(cls, path, backed=None):
    ...
    major, minor = _parse_version(version_str)
    reader = _SUPPORTED_MAJORS.get(major)
    if reader is None:
        raise ValueError(...)            # unknown MAJOR, as today
    if major == 1:
        if backed:
            raise ValueError("backed mode requires format 2.x; run "
                             "uchrom.io.upgrade_h5cd(path) first")
        cd = _read_v1(cls, f)
        return _upgrade_v1_in_memory(cd)  # derive bins/bin_id, split tracks,
                                          # lift uns['linked_*'] → contacts/links
    return _read_v2(cls, f, backed=backed)
```

- Writers always emit 2.0.  `uchrom.io.upgrade_h5cd(src, dst)` converts
  1.x → 2.0 on disk (including the sort + index build).
- `_read_v1` is kept indefinitely; `_write_v1` is not.

### Migration / compat

- In-memory API stays the same for common paths (`cd.coords`, `cd.spots`,
  `get_*`, `compute_distances`, `to_dataframe`, `write`, `read`).
- `cd.spots` in 2.0 no longer *stores* `chrom/start/end`, but
  `cd.spots["chrom"]` keeps working through a derived-column accessor for
  the 2.x series, with a deprecation warning pointing to `bin_id` /
  `cd.spots_with_loci()`.

### Open questions

- External sort for unsorted streaming imports: implement in-house
  (chunked argsort + merge) or require sorted input?  Proposal: in-house,
  since FOF-CT exports are frequently cell-interleaved.
- Should backed `cd.spots` be a real `pandas.DataFrame` subclass or a
  lightweight proxy?  Proxy is simpler and avoids pandas internals;
  `to_memory()` gives a real DataFrame.

---

## Phased roadmap

Each step is one PR, validated on real data per the project rules
(`example-data/README.md` catalog; Takei 2025 fixture, 4DN FOF-CT, IMR90
cool, H1Esc-HFF sci-Hi-C).

| # | PR | Format | Depends on |
|---|----|--------|-----------|
| 0 | Fix `results` silent-drop on write (raise on unsupported types + round-trip tests) | 1.2 | — (**done**) |
| 1 | Merge `codex/linked-mudata-scool-framework` (`link_scool`, `link_mudata`, `coord_status`, `validate_links`) | 1.2 (uns only) | — (**done**) |
| 2 | Calling convention + `ResultsStore` / `ResultRecord` + `key_added`; convert `strc.*` callers, merge per-chrom outputs; `uc.tl` / `uc.pp` aliases | 1.4 (results gain attrs; 1.3 went to `points/`) | 0 (**done**) |
| 3 | `bins` axis, `bin_id`, bin-level `tracks` vs `spot_tracks`, `intervals`, `fea.project` → bins; 1.x upgrade path | **2.0** | 2 (**done**) |
| 4 | `cd.contacts` (`ContactRef`, cool/mcool/scool/hic backends), optional coords + `coord_status`; `ChromData.from_contacts`; Higashi tutorial without zeros | 2.0 | 1, 3 |
| 5 | Recon library entry points returning `ChromData` (nucdyn, gem, mds); CLIs become wrappers | 2.0 | 4 |
| 6 | Sorted spots + `index/*`, backed mode, `iter_traces` / `iter_cells`, float32 coords, compression | 2.0 (`.chromdata.zarr`) | 3 (**done**, with 8) |
| 7 | Streaming writer + streaming `from_fofct` / `from_seqfish_multiomics`; streaming population callers; memory budget; spot tables partitioned by chromosome, `columns=` | 2.1 | 6 (**done**) |
| 8 | ~~Optional zarr `_Store` backend~~ → zarr + Parquet **is** the 2.0 container; `.h5cd` writing deprecated | 2.0 | 6 (**done**) |

Steps 3 and 4 are the breaking ones and should ship together as
`u-chrom 0.3.0` with `upgrade_h5cd` and a migration note in the
changelog.
