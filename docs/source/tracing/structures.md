# Calling structures

`uchrom.strc` calls chromatin structures from the 3-D data itself — from the distances between loci in
many traces, not from a contact map: loops (a per-axis F-test, ArcFISH), TADs (ArcFISH p-values),
domains per allele (FISHnet) and A/B compartments.  The callers work on any population of traces — chromatin
tracing, DNA seqFISH+, an ensemble of models — and run on PyTorch (`device="auto"`: CUDA, Apple MPS or
CPU); on a backed store they stream.  TADs can also be called from a Hi-C map linked to the data (the
directionality index), to compare the two; the callers made for contact maps — compartments by the cis
eigenvector, insulation domains, HiCCUPS and Mustache loops — are in the bulk Hi-C chapter
([calling structures from a map](../bulk/structures)).  The same callers run on 3-D structures
reconstructed from single-cell Hi-C (a reconstruction is a `ChromData` with coordinates): compartments
come out as from imaging with the same number of traces, TADs and loops do not at tens of cells
([calling structures from single cells](../schic/structures.md)).

| Structure | API |
|-----------|-----|
| loops | `uchrom.strc.loop.call_loops_axiswise_f`, `uc.tl.call_loops` |
| TADs | `uchrom.strc.tad.call_tads_by_pval`, `call_tads_di` (Hi-C), `uc.tl.call_tads` |
| domains per trace / allele | `uchrom.strc.tad.call_domains_fishnet` |
| A/B compartments | `uchrom.strc.comp.call_compartments_axes_pc`, `uc.tl.call_compartments`; from a linked Hi-C map: `call_compartments_hic` (`method="hic_pc1"`) |
| all of them, projected onto bins / spots | `uchrom.strc.call_structures_multi`, `add_structural_features` |
| the same, on reconstructed single-cell structures (Dip-C / hickit `.3dg`, EMber models) | `uchrom.io.read_3dg_cells`, `ds.load("tan2018_gm12878")`; `call_compartments_axes_pc(centromeres=)` per chromosome arm |
| compare calls with a reference | `match_loops`, `score_loops` (anchor vs background distances), `tad_boundaries`, `compare_boundaries`, `boundary_frequency`, `compare_compartments` |
| draw them | `uchrom.pl.draw_domains`, `draw_loops`, `plot_compartments` |

## Tutorials

```{toctree}
:maxdepth: 1

/tutorials/loop_calling
/tutorials/tad_calling
/tutorials/fishnet_domains
/tutorials/compartment
```

API: [loops](../reference/api/strc_loop), [TADs](../reference/api/strc_tad),
[compartments](../reference/api/strc_comp), [enrichment](../reference/api/strc_enrichment).

## Calling convention

Every `cd`-level caller follows one convention (ChromData 2.0 design,
section 3):

```python
table = caller(
    cd,
    chrom=None,          # None = every chromosome, merged into ONE table
    trace_ids=None,      # optional selection
    cells=None,
    params=None,         # frozen-style *Params dataclass with every knob
    device="auto",
    key_added="<what>.<method>",   # cd.results key; None = do not store
    copy=False,          # True → return a new ChromData, cd untouched
)
```

| Caller | default `key_added` | alias |
|--------|---------------------|-------|
| `strc.tad.call_tads_by_pval` | `"tads.arcfish"` | `uc.tl.call_tads(cd, method="arcfish")` |
| `strc.tad.call_domains_fishnet` | `"tads.fishnet"` (+ `"tads.fishnet.ensemble"`) | `uc.tl.call_tads(cd, method="fishnet")` |
| `strc.tad.call_tads_di` | `"tads.di"` | `uc.tl.call_tads(cd, method="di")` |
| `strc.loop.call_loops_axiswise_f` | `"loops.axiswise_f"` | `uc.tl.call_loops(cd)` |
| `strc.comp.call_compartments_axes_pc` | `"compartments.axes_pc"` | `uc.tl.call_compartments(cd)` |

Results are stored with provenance (see [Where results live](#where-results-live)).
The 1.x forms — positional `chrom`, `store=`, `result_key=` and the
`strc.call_*_multi` helpers — still work but emit a
`DeprecationWarning`; when used they keep the 1.x keys (`"tads"`,
`"loops"`, `"compartments"`, `"fishnet_domains"` / `"fishnet_ensemble"`).

## Loop calling

```python
from uchrom.strc.loop import call_loops_axiswise_f, LoopCallerParams

loops = call_loops_axiswise_f(
    cd,
    chrom="chr17",       # or None for every chromosome (one merged table)
    device="auto",
    params=LoopCallerParams(
        fdr_cutoff=0.1,
        pval_cutoff=1e-5,
        gap=50_000,
        inner_cut=25_000,
        outer_cut=50_000,
    ),
)                        # also stored at cd.results['loops.axiswise_f']
```

### Algorithm

The three tracing callers implement ArcFISH (Yu et al. 2025; github.com/hyuyu104/ArcFISH) and give the authors'
results: uchrom-reproducibility `benchmarks/toolkit_parity/arcfish_parity/` runs both on the authors' tutorial data and four more datasets and compares the
per-locus statistics, test matrices and calls (`results/parity.json`).  For each chromosome separately:

1. **Loci and coordinates** — the chromosome's starts with a finite coordinate; a trace that observed a locus more
   than once keeps its first spot; genomic distances `|start_i − start_j|`.
2. **Filter + normalise** (`uchrom.fea.arc.filter_normalize`), per axis and locus pair over the traces:
   - `raw_var` = the median squared deviation of the differences from their median (medians: the mean of the two
     middle values for an even count);
   - LOWESS of `log raw_var` on `log` genomic distance (`frac` 0.1) → the stratified s.d.; a difference more than
     4 s.d. from the pair's median is an outlier and is removed;
   - the remaining count and variance; LOWESS again for the expected variance; `norm_var = var / expected`.
3. **Axis weights** — per axis, each trace centred at its mean over the loci, the mean square of each locus over the
   traces, `w = 1 / median over loci`, normalised to sum 1.
4. **Per-axis F-test** of each pair `i < j` with `start_j − start_i ∈ [cut_lo, cut_up]`: the background pairs
   `(k, l)`, `k < l`, within `outer_cut` of `i` and of `j`, except those within `inner_cut` of both and those in row
   `i` or column `j` (at least 4); `F = norm_var[i, j] / count-weighted mean(norm_var[background])`;
   `p = F.cdf(F; count[i, j], background count)`.
5. **Cauchy combination** of the axes with the weights; **Benjamini–Hochberg** over the tested pairs → candidates.
6. **Clusters** of candidates within `gap` of each other in both loci; the summit is the cluster's smallest p.
7. **Contact frequency** — a summit is kept when the fraction of traces whose two spots are closer than the mean
   3-D distance of the pairs exactly `contact_sep` (25 kb) apart exceeds 1/2 (a cluster of two pairs) or 1/3
   (otherwise; no such pairs → no filter).
8. **Final p-value threshold** (`pval_cutoff`) → loops.

Output columns: `chrom1, start1, end1, chrom2, start2, end2, stat, pval, fdr, score, cluster_size, contact_freq,
summit_i, summit_j`; the test matrices: `uchrom.strc.loop.axiswise_f.arcfish_loop_matrices`.

### GPU acceleration

All tensor operations run through `torch` on the user's device (`auto`
picks CUDA > MPS > CPU).  LOWESS stays on CPU via `statsmodels`.
See [`call_loops_axiswise_f`](../reference/api/strc_loop) for all parameters.

### Batch / CLI

```bash
python -m uchrom.strc.loop \
    --input=data.chromdata.zarr \
    --output=loops.bedpe \
    --chrom=chr17 \
    --device=auto
```

Output formats are inferred from the extension: `.bedpe` (BEDPE TSV),
`.csv` (full DataFrame), anything else (write ChromData with
`results['loops.axiswise_f']` set; change the key with `--key_added`).

## TAD calling

`uchrom.strc.tad` ships three methods:

### 1. F-test caller (`call_tads_by_pval`)

For every locus at least `window_bp / 2` from both ends, the loci within `window_bp` on each side form a left
and a right segment; per axis an F-test compares the count-weighted variance of the pairs within the segments with
that of the pairs across, and the axes are combined with the Cauchy test (`stat`).  Boundaries are the local maxima
of the same statistic with F(1, 1) p-values (`stat_prox`) whose Benjamini–Hochberg FDR over all tested loci is below
`fdr_cutoff`.  Level 0 holds the domains between consecutive boundaries (the first and the last locus count as
boundaries); removing the weakest boundary at a time adds the merged domain at levels 1, 2, ….

```python
from uchrom.strc.tad import call_tads_by_pval, TADCallerParams

tads = call_tads_by_pval(
    cd,                   # chrom=None → every chromosome
    params=TADCallerParams(window_bp=1e5, fdr_cutoff=0.1, hierarchical=True),
    device="auto",
)
# tads: DataFrame (chrom, start, end, level, start1, end1, start2, end2, stat1, stat2); level 0 = finest
# per-locus statistics and boundary calls: uchrom.strc.tad.arc_pval.arcfish_boundary_stats(cd, chrom=...)
```

### 2. FISHnet per-allele caller (`call_domains_fishnet`)

FISHnet (Patel et al. 2025, *Nature Methods*) runs a per-trace modularity
optimisation on the pairwise distance matrix, so every allele gets its
own set of domain boundaries.  Thresholds at which the community count
is stable across ``plateau_size`` adjacent steps are grouped and
consensed into final calls.  Population-level aggregation sums the
per-allele domain masks into an "ensemble domain mask".

```python
from uchrom.strc.tad import call_domains_fishnet, FISHnetParams

fishnet_df = call_domains_fishnet(
    cd, chrom="chr19",
    params=FISHnetParams(plateau_size=4, n_louvain_runs=20),
    max_traces=200,       # per chromosome
)
ens = cd.results["tads.fishnet.ensemble"]["chr19"]   # one entry per chromosome
ens["mask"], ens["bin_ids"], ens["n_traces"]
```

### 3. Directionality index (`call_tads_di`)

Classic Dixon-style caller on a Hi-C contact matrix.  The `cd`-level
caller reads the matrix from a `.cool` / `.mcool` linked with
`cd.link_cool` (or a path):

```python
from uchrom.strc.tad import call_tads_di, DICallerParams

cd.link_cool("K562_chr21_30kb.cool", key="k562")   # K562 Hi-C (Ray 2019)
tads = call_tads_di(cd, contacts="k562", chrom="chr21",
                    params=DICallerParams(window=50, smoothing_param=0.1))
# tads: DataFrame (chrom, start, end, start_bin, end_bin); cd.results['tads.di']
```

The matrix-level kernel stays public (low level):

```python
from uchrom.strc.tad import get_domains

domains = get_domains(contact_mat, smoothing_param=0.1, min_size_frac=0.05)
# → list of (start_idx, end_idx) in bin space, end exclusive
```

## A/B compartment calling

`uchrom.strc.comp.call_compartments_axes_pc` is ArcFISH's caller.  For each axis it takes the eigenvector of the
second-largest eigenvalue of `exp(-norm_var)` (a missing entry counts as 1), weights the three by the axis weights
and splits the loci with k-means (`n_clusters=2, random_state=0, n_init=1`); runs shorter than
`min_compartment_bp` are flipped, the shortest first.

```python
from uchrom.strc.comp import call_compartments_axes_pc, CompartmentCallerParams

comps = call_compartments_axes_pc(
    cd, chrom="chr1",     # or None for every chromosome
    params=CompartmentCallerParams(min_compartment_bp=0),
    device="auto",
)
# comps: DataFrame (chrom, start, end, bin_index, cluster, compartment, pc2, eig_x, eig_y, eig_z)
```

Without other information A is the **less compact** cluster (the authors' rule: per axis the median normalised
variance of each cluster's pairs, majority over the axes; B compartments are the more compacted).  Name A by an
annotation with `CompartmentCallerParams(a_track="<bin_tracks column>")` (gene density, an active mark) or
`a_cluster=`.

## Where results live

`cd.results` is a `ResultsStore`: indexing returns the value, and
`record()` returns the value plus its provenance.

```python
cd.results["loops.axiswise_f"]          # DataFrame
cd.results["tads.arcfish"]              # DataFrame
cd.results["compartments.axes_pc"]      # DataFrame, one row per bin

rec = cd.results.record("tads.arcfish")
rec.kind            # "intervals"
rec.function        # "uchrom.strc.tad.call_tads_by_pval"
rec.params          # asdict(TADCallerParams(...))
rec.inputs          # {"chrom": [...], "n_traces": ..., "n_spots": ...}
rec.uchrom_version, rec.created_utc
```

Values and provenance round-trip through `.chromdata.zarr`, so a
single file carries tracing coordinates, calls, how they were made, and
cell metadata.
