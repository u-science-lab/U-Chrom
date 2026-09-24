# ChromData 2.0 Design

This page records the proposed next data model for `ChromData`: the next
MAJOR bump of the on-disk format (1.x → 2.0) and of the package (0.3.0).
It is a design document: nothing here is implemented yet unless stated
otherwise.

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

**Recommendation:** rebase that branch onto `main` and merge it first,
as-is, as format 1.3 (purely additive `uns` keys; 1.2 is already taken by
the typed-`results` fix).  2.0 then promotes the
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

- 1.3 files with `uns["linked_scool"]` / `uns["linked_mudata"]` are
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

**Recommendation:** stay on HDF5 for 2.0 — it keeps one file per dataset,
reuses the 1.x reader / writer helpers and matches `cooler`.  Keep all
array I/O behind a small `_Store` interface (`create_dataset`, `read_slice`,
`attrs`) so a zarr backend (`.zarrcd`) can be added later for cloud /
parallel-write use cases without touching `ChromData`.

### Format 2.0 HDF5 layout

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

Consistent with the existing `FORMAT_VERSION` mechanism in `cdata.py`:

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
| 1 | Rebase + merge `codex/linked-mudata-scool-framework` (`link_scool`, `link_mudata`, `coord_status`, `validate_links`) | 1.3 | — |
| 2 | Calling convention + `ResultsStore` / `ResultRecord` + `key_added`; convert `strc.*` callers, merge per-chrom outputs; `uc.tl` / `uc.pp` aliases | 1.4 (results gain attrs) | 0 |
| 3 | `bins` axis, `bin_id`, bin-level `tracks` vs `spot_tracks`, `intervals`, `fea.project` → bins; 1.x upgrade path | **2.0** | 2 |
| 4 | `cd.contacts` (`ContactRef`, cool/mcool/scool/hic backends), optional coords + `coord_status`; `ChromData.from_contacts`; Higashi tutorial without zeros | 2.0 | 1, 3 |
| 5 | Recon library entry points returning `ChromData` (nucdyn, gem, mds); CLIs become wrappers | 2.0 | 4 |
| 6 | Sorted spots + `index/*`, backed mode, `iter_traces` / `iter_cells`, float32 coords, compression | 2.1 | 3 |
| 7 | Streaming writer + streaming `from_fofct` / `from_seqfish_multiomics`; streaming population callers; memory budget | 2.1 | 6 |
| 8 | Optional zarr `_Store` backend | 2.2 | 6 |

Steps 3 and 4 are the breaking ones and should ship together as
`u-chrom 0.3.0` with `upgrade_h5cd` and a migration note in the
changelog.
