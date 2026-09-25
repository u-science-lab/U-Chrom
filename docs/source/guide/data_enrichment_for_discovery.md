# Data Enrichment for Auto-discovery

This page records the proposed design for enriching `ChromData` before
auto-discovery. The goal is to give discovery agents more biological context
without turning `uchrom_discovery` into a general genomics toolbox.

The guiding principle is:

```text
U-Chrom computes reusable data features.
ChromData stores those features with provenance.
Auto-discovery consumes the enriched ChromData schema.
```

In other words, "preprocessing" is a workflow stage, not a module boundary.
Reusable calculations such as sequence features, gene annotations, TADs,
loops, and compartments should live in the same U-Chrom packages that normal
users would call outside auto-discovery.

## Motivation

Current auto-discovery mostly reasons over the data already present in
`ChromData`: 3D coordinates, spot metadata, IF/RNA marker tracks, cell
metadata, linked RNA expression, references, user annotations, prior ideas,
and notebook evidence.

The next stage should expand the measurable feature space before idea
generation. Examples include:

- structural annotations from U-Chrom callers, such as TADs, loops, and A/B
  compartments
- sequence-derived tracks from FASTA, such as GC fraction, CpG density,
  N fraction, and G-quadruplex motif density
- genome annotation tracks from GTF or BED, such as gene body overlap, exon
  overlap, promoter overlap, nearest TSS distance, and gene biotype overlap
- peak tracks from existing score tracks, such as MACS3 `bdgpeakcall`-compatible
  H3K27ac or RNAPIISer2-P domains
- projected interval-level features that make notebook analysis simple, such
  as distance to the nearest TAD boundary or loop anchor membership

These features let auto-discovery ask broader questions:

- Are lamina-associated loci enriched for low-GC, repeat-rich, or
  heterochromatin-associated sequence features?
- Do TAD boundaries have distinctive radial positions or marker profiles?
- Are loop anchors spatially closer to active transcriptional markers?
- Do A/B compartment scores explain cell-type-specific chromatin positioning?
- Do gene-rich, promoter-rich, or G4-rich bins show distinct 3D neighborhoods?

## Existing U-Chrom Groundwork

The repo already has the main storage and structural-analysis foundations:

- `ChromData.tracks` stores per-spot, row-aligned feature tracks.
- `ChromData.results` stores analysis outputs such as DataFrames and arrays.
- `.h5cd` persistence already writes both `tracks` and `results`.
- `uchrom.strc.tad.call_tads_by_pval` calls TADs from chromatin tracing data
  and can store them under `cd.results["tads"]`.
- `uchrom.strc.loop.call_loops_axiswise_f` calls loop candidates and can store
  them under `cd.results["loops"]`.
- `uchrom.strc.comp.call_compartments_axes_pc` calls A/B compartments and can
  store them under `cd.results["compartments"]`.
- `uchrom_discovery.schema.build_discovery_schema` already records track
  columns and result keys, but it should be extended to describe enriched
  feature groups more explicitly.

This means the new work should mostly connect and generalize existing pieces,
not introduce a parallel preprocessing subsystem.

## Module Boundaries

The enrichment design should keep computation in general-purpose U-Chrom
modules.

```text
uchrom.io
  FASTA, GTF, BED, cool, hic, and interval/table readers

uchrom.fea
  reusable feature calculations and interval-to-spot projection

uchrom.strc
  structural callers and structural feature projection

uchrom.core
  ChromData storage conventions and provenance metadata

uchrom_discovery
  orchestration glue, schema exposure, and agent-facing summaries
```

`uchrom_discovery` may provide a convenience command such as
`enrich` or an option on the runner, but that command should delegate to
`uchrom.fea`, `uchrom.strc`, and `uchrom.io`.

## Storage Conventions

Enrichment outputs should use three layers.

### Canonical interval tables

Feature tables that are naturally defined by genomic intervals should be
stored once in `cd.results`.

Suggested keys:

```python
cd.results["bin_features"]       # one row per canonical genomic bin
cd.results["tads"]               # TAD intervals
cd.results["loops"]              # loop anchor pairs
cd.results["compartments"]       # compartment intervals and scores
cd.results["gene_annotations"]   # optional compact interval annotations
```

`bin_features` should use the same coordinate convention as `spots`:
0-based, half-open intervals with columns `chrom`, `start`, and `end`.

### Projected spot-level tracks

Frequently used scalar values should be projected onto `cd.tracks`, because
notebook code and auto-discovery hypotheses commonly operate on spot-aligned
tables.

Examples:

```text
seq.gc_fraction
seq.cpg_density
seq.n_fraction
seq.g4_motif_density
gtf.gene_body_overlap
gtf.promoter_overlap
gtf.nearest_tss_distance
strc.compartment_pc2
strc.compartment_label
strc.distance_to_tad_boundary
strc.loop_anchor_overlap
peak.h3k27ac_overlap
peak.distance_to_h3k27ac
```

Namespacing tracks by source, such as `seq.*`, `gtf.*`, and `strc.*`, keeps
generated fields distinct from experimental IF marker tracks. Peak-derived
features use the `peak.*` namespace.

### Provenance metadata

Every enrichment run should record enough context to reproduce the result.
Use `cd.uns["feature_registry"]` or a similarly named metadata entry.

Suggested fields per feature group:

```json
{
  "feature_group": "sequence",
  "features": ["seq.gc_fraction", "seq.g4_motif_density"],
  "source_path": "genome.fa",
  "source_sha256": "...",
  "genome_assembly": "mm10",
  "coordinate_convention": "0-based half-open",
  "parameters": {"g4_regex": "G{3,}.{1,7}G{3,}.{1,7}G{3,}.{1,7}G{3,}"},
  "created_by": "uchrom.fea.sequence",
  "uchrom_version": "..."
}
```

The registry should also record projection behavior, such as whether the
track was computed directly on `spots` intervals or copied from a canonical
bin table.

The registry entries now include creation time, U-Chrom version, feature count,
output row/non-null summaries, and source SHA-256 digests when the enrichment
stage receives local FASTA/GTF paths.

## Proposed APIs

The public APIs should be useful even when no auto-discovery run happens.

Sequence features:

```python
from uchrom.fea.sequence import compute_sequence_features

features = compute_sequence_features(
    intervals=cdata.spots[["chrom", "start", "end"]].drop_duplicates(),
    fasta="genome.fa",
    features=["gc_fraction", "cpg_density", "n_fraction", "g4_motif_density"],
)
```

Annotation features:

```python
from uchrom.fea.annotation import compute_annotation_features

annotations = compute_annotation_features(
    intervals=bin_table,
    gtf="genes.gtf",
    promoter_window=(-2000, 500),
)
```

Projection:

```python
from uchrom.fea.project import project_interval_features_to_spots

cdata.tracks = project_interval_features_to_spots(
    cdata,
    features,
    prefix="seq",
    into=cdata.tracks,
)
```

Structural callers:

```python
from uchrom.strc.tad import call_tads_by_pval
from uchrom.strc.loop import call_loops_axiswise_f
from uchrom.strc.comp import call_compartments_axes_pc

# chrom=None runs every chromosome and stores ONE merged table per caller
call_tads_by_pval(cdata)            # cd.results["tads.arcfish"]
call_loops_axiswise_f(cdata)        # cd.results["loops.axiswise_f"]
call_compartments_axes_pc(cdata)    # cd.results["compartments.axes_pc"]
```

`add_structural_features(cdata)` looks these keys up first and falls back
to the 1.x keys (`"tads"`, `"loops"`, `"compartments"`).

Peak callers:

```python
from uchrom.fea.peaks import call_peaks_from_track

peaks = call_peaks_from_track(
    cdata,
    "H3K27ac",
    method="macs",
    cutoff=5.0,
    min_length=200,
    max_gap=30,
)
```

`method="macs"` is a MACS3 `bdgpeakcall`-compatible port for single score
tracks. It aggregates repeated spot rows to genomic bins, applies MACS'
bedGraph cutoff/min-length/max-gap scan, uses the same summit tie-breaking rule,
and can be rendered in MACS-compatible narrowPeak format. This is intended for
tracks that already encode a score where larger means more peak-like. For
legacy exploratory use, `method="macs_poisson"` keeps U-Chrom's older binned
dynamic-Poisson approximation, and `method="threshold"` keeps the simpler
quantile/threshold caller.

Auto-discovery convenience:

```python
from uchrom_discovery import build_discovery_schema
from uchrom_discovery.enrichment import DiscoveryEnrichmentConfig, enrich_for_discovery

summary = enrich_for_discovery(
    cdata,
    DiscoveryEnrichmentConfig(
        fasta="genome.fa",
        gtf="genes.gtf",
        peak_tracks=["H3K27ac"],
    ),
)
build_discovery_schema(cdata, store=True)
```

The convenience layer should not implement the computations itself. It should
coordinate existing U-Chrom functions, update provenance metadata, and rebuild
the discovery schema.

The runner uses the same layer as a default pre-discovery stage. For example:

```bash
python -m uchrom_discovery run data.h5cd runs/example \
  --fasta genome.fa \
  --gtf genes.gtf \
  --peak-track H3K27ac \
  --store-schema
```

When enrichment is enabled, the run writes `enriched.h5cd` in the run
directory and uses it for schema generation and notebooks. With
`--store-schema`, the enriched features, schema, and graph metadata are also
written back to the input `.h5cd`.

## Discovery Schema Extensions

`build_discovery_schema` should expose enriched features in a compact,
agent-readable way. It should not dump huge tables into the prompt.

Suggested schema additions:

```python
schema["modalities"]["sequence_features"] = {
    "present": True,
    "fields": ["tracks", "results.bin_features", "uns.feature_registry"],
    "operations": [
        "sequence_track_stratified_distance",
        "gc_content_association",
        "g4_density_association",
    ],
}

schema["modalities"]["genome_annotations"] = {
    "present": True,
    "fields": ["tracks", "results.gene_annotations", "uns.feature_registry"],
    "operations": [
        "annotation_overlap_enrichment",
        "nearest_tss_distance_association",
        "gene_biotype_stratification",
    ],
}

schema["modalities"]["structure_annotations"] = {
    "present": True,
    "fields": ["results.tads", "results.loops", "results.compartments", "tracks"],
    "operations": [
        "tad_boundary_distance",
        "loop_anchor_proximity",
        "compartment_stratified_radial_position",
    ],
}
```

The implemented schema also includes `feature_summary`, which groups enriched
tracks by `sequence`, `annotation`, `structure`, and `peaks`, listing feature
names, projected tracks, source paths, source hashes when available, and result
keys. `schema_to_agent_context()` renders this as an `enriched_features`
section for idea-generation agents.

The schema should also include:

- track groups, such as `seq`, `gtf`, `strc`, and experimental marker groups
- result table schemas for `tads`, `loops`, `compartments`, and `bin_features`
- feature provenance summaries from `uns["feature_registry"]`
- warnings for missing genome assembly, mismatched chromosome naming, or
  missing FASTA/GTF provenance

## Workflow

The enriched auto-discovery workflow should look like this:

```text
raw or existing h5cd
  -> optional U-Chrom structural callers
  -> optional sequence feature calculation
  -> optional annotation feature calculation
  -> interval-to-spot projection into tracks
  -> feature registry update
  -> discovery schema rebuild
  -> idea generation
  -> notebook verification
  -> evidence graph update
```

This workflow can be surfaced through a command, but the command should be a
thin composition layer.

Example:

```bash
python -m uchrom_discovery enrich data.h5cd enriched.h5cd \
  --fasta genome.fa \
  --gtf genes.gtf \
  --sequence gc,cpg,n,g4 \
  --annotation gene_body,exon,promoter,tss \
  --structure tads,loops,compartments \
  --store-schema
```

Then:

```bash
python -m uchrom_discovery iterate enriched.h5cd runs/enriched_iterative \
  --iterations 2 \
  --ideas-per-iteration 10
```

## Implementation Milestones

1. Define storage conventions for `results["bin_features"]`, namespaced
   projected tracks, and `uns["feature_registry"]`.
2. Add interval projection utilities in `uchrom.fea`.
3. Add FASTA-backed sequence features in `uchrom.fea.sequence`.
4. Add GTF/BED-backed annotation features in `uchrom.fea.annotation`.
5. Add structural multi-chromosome wrappers or projection helpers around the
   existing `uchrom.strc` callers.
6. Extend `build_discovery_schema` to expose feature groups and result table
   schemas.
7. Add an auto-discovery convenience command that composes the reusable
   functions and rebuilds the schema.
8. Run an enriched Takei-style iterative discovery example and verify that new
   ideas use sequence, annotation, and structural features naturally.

## Open Design Questions

- Should canonical `bin_features` always be computed on unique `spots`
  intervals, or should users be able to provide an independent bin grid?
- How should chromosome naming be normalized across `h5cd`, FASTA, GTF, BED,
  cool, and hic inputs?
- Should structural callers write one merged result table per feature type, or
  separate per-chromosome keys that a wrapper merges?
- Which projected tracks should be created by default, and which should remain
  only in canonical interval tables?
- Should loop and compartment annotations be computed from tracing data, Hi-C
  matrices, or both when multiple sources are available?
- How much provenance should be required before auto-discovery accepts an
  enriched feature as agent-visible?

## Non-goals

- Do not put general FASTA, GTF, BED, TAD, loop, or compartment algorithms
  inside `uchrom_discovery`.
- Do not store large notebooks, browser logs, or generated graph artifacts
  directly in `ChromData`.
- Do not duplicate every interval-level value into `tracks` by default when a
  canonical result table is more appropriate.
- Do not let auto-discovery prompts infer feature provenance from column names
  alone; use explicit registry metadata.
