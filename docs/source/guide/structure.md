# Structure identification

`uchrom.strc` groups algorithms that detect 3D chromatin features.

| Submodule | Status | Method |
|-----------|--------|--------|
| `uchrom.strc.loop` | available | ArcFISH-style axis-wise F-test |
| `uchrom.strc.tad` | available | Directionality index **and** ArcFISH-style F-test (hierarchical) |
| `uchrom.strc.comp` | available | ArcFISH-style per-axis PC2 + KMeans |

## Loop calling (ArcFISH-style)

```python
from uchrom.strc.loop import call_loops_axiswise_f, LoopCallerParams

loops = call_loops_axiswise_f(
    cd,
    chrom="chr17",
    device="auto",
    params=LoopCallerParams(
        fdr_cutoff=0.1,
        pval_cutoff=1e-5,
        gap=50_000,
        inner_cut=25_000,
        outer_cut=50_000,
    ),
    store=True,  # also write cd.results['loops']
)
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
    --input=data.h5cd \
    --output=loops.bedpe \
    --chrom=chr17 \
    --device=auto
```

Output formats are inferred from the extension: `.bedpe` (BEDPE TSV),
`.csv` (full DataFrame), anything else (write ChromData with
`results['loops']` set).

## TAD calling

`uchrom.strc.tad` ships two methods:

### 1. ArcFISH-style F-test (`call_tads_by_pval`)

For each candidate boundary position the caller runs a per-axis F-test
on the count-weighted intra-domain vs inter-domain variance inside a
window of size `window_bp`.  The three axes are combined with the
standard ACAT Cauchy test, peaks are picked in `-log10 p`, BH-FDR
adjusted, and (optionally) emitted as a hierarchy of nested TADs.

```python
from uchrom.strc.tad import call_tads_by_pval, TADCallerParams

tads = call_tads_by_pval(
    cd, chrom="chr1",
    params=TADCallerParams(
        window_bp=1e5, fdr_cutoff=0.1,
        hierarchical=True, max_levels=3,
    ),
    device="auto",
)
# tads: DataFrame (chrom, start, end, level, score, pval, fdr)
```

### 2. Directionality index (`get_domains`)

Classic Dixon-style caller on a contact matrix.

```python
import torch
from uchrom.strc.tad import get_domains

domains = get_domains(contact_mat, smoothing_param=0.1, min_size_frac=0.05)
# → list of (start_idx, end_idx) in bin space
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
    cd, chrom="chr1",
    params=CompartmentCallerParams(min_bins=2),
    device="auto",
)
# comps: DataFrame (chrom, start, end, bin_index, cluster, compartment, pc2)
```

A/B labels default to the convention that the more compact (smaller
mean intra-distance) cluster is A.  Override with the `a_cluster`
parameter if you have gene-density ground truth.

## Where results live

Structure calls are stored under `cd.results`:

```python
cd.results["loops"]        # DataFrame
cd.results["tads"]         # DataFrame (planned convention)
cd.results["compartments"] # ndarray or DataFrame
```

They round-trip through `.h5cd` via the standard writer, so a single
file can carry tracing coordinates + calls + cell metadata.
