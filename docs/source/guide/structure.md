# Structure identification

`uchrom.strc` groups algorithms that detect 3D chromatin features.

| Submodule | Status | Method |
|-----------|--------|--------|
| `uchrom.strc.loop` | available | ArcFISH-style axis-wise F-test |
| `uchrom.strc.tad` | available | Directionality index, ArcFISH-style F-test (hierarchical), FISHnet per-allele |
| `uchrom.strc.comp` | available | ArcFISH-style per-axis PC2 + KMeans |

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

For each chromosome separately:

1. **Per-axis pairwise difference tensor** `(3, n_traces, n_bins, n_bins)`
2. **Filter + normalise**
   - Compute per-pair `raw_var` = NaN-median over traces of squared
     deviation from the trace-wise median.
   - LOWESS fit `log(raw_var) ~ log(1D genomic distance)` for the
     stratified expected variance; convert to `strata_std`.
   - Flag per-trace observations where `|diff − median(diff)| > 4σ` as
     outliers (NaN in the 4-D tensor).
   - Recompute per-pair variance and count from the cleaned tensor;
     LOWESS again for the expected variance; normalise.
3. **Axis weights** — `w_c = 1 / median_trace(trace_variance_c)`,
   normalised to sum 1.
4. **Per-axis F-test** on each candidate `(i, j)` with `d1d ∈ [cut_lo, cut_up]`:
   - Local ring background `[inner_cut, outer_cut]` excluding row *i*
     and column *j*.
   - `F_c = norm_var[i,j] / count-weighted-mean(norm_var[ring])`.
   - Left-tail F-CDF → per-axis p-value.
5. **ACAT Cauchy combination** of per-axis p-values using axis weights.
6. **Benjamini–Hochberg FDR** → candidate mask.
7. **Cluster** accepted candidates by 1D proximity (`gap`); the lowest-p
   entry per cluster is the "summit".
8. **Pseudo-contact-frequency filter** — only keep summits where the
   fraction of traces with 3D pdist below the adjacent-bin cutoff
   exceeds 1/2 (singleton cluster) or 1/3 (larger cluster).
9. **Final p-value threshold** → output.

Output columns: `chrom1, start1, end1, chrom2, start2, end2, score,
pval, fdr, cluster_size, contact_freq, summit_i, summit_j`.

### GPU acceleration

All tensor operations run through `torch` on the user's device (`auto`
picks CUDA > MPS > CPU).  LOWESS stays on CPU via `statsmodels`.
See [`call_loops_axiswise_f`](../api/strc_loop) for all parameters.

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

For each candidate boundary position the caller runs a per-axis F-test
on the count-weighted intra-domain vs inter-domain variance inside a
window of size `window_bp`.  The three axes are combined with the
standard ACAT Cauchy test, peaks are picked in `-log10 p`, BH-FDR
adjusted, and (optionally) emitted as a hierarchy of nested TADs.

```python
from uchrom.strc.tad import call_tads_by_pval, TADCallerParams

tads = call_tads_by_pval(
    cd,                   # chrom=None → every chromosome
    params=TADCallerParams(
        window_bp=1e5, fdr_cutoff=0.1,
        hierarchical=True, max_levels=3,
    ),
    device="auto",
)
# tads: DataFrame (chrom, start, end, level, score, pval, fdr)
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

`uchrom.strc.comp.call_compartments_axes_pc` is an ArcFISH-style
caller.  For each axis it builds a pseudo-contact matrix
`K_c = exp(-norm_var_c)`, takes the second-largest eigenvector (PC2)
which encodes the compartment-scale alternation, stacks the three
weighted PC2's as features, and runs KMeans(2) to label bins A / B.

```python
from uchrom.strc.comp import call_compartments_axes_pc, CompartmentCallerParams

comps = call_compartments_axes_pc(
    cd, chrom="chr1",     # or None for every chromosome
    params=CompartmentCallerParams(min_bins=2),
    device="auto",
)
# comps: DataFrame (chrom, start, end, bin_index, cluster, compartment, pc2)
```

A/B labels default to the convention that the more compact (smaller
mean intra-distance) cluster is A.  Override with the `a_cluster`
parameter if you have gene-density ground truth.

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
