---
name: call-structures
description: Use before computing structure in U-Chrom data — 3-D distance between loci N Mb apart, distance vs separation, Rg per chromosome, slope of contact probability P(s) vs genomic distance from a contact map (.cool/.mcool/.scool, pseudo-bulk), TADs (ArcFISH), compartments, loops. Script + bin-size rules. Differences between cell groups → compare-groups.
---

# Structure statistics and calls

## When to use
"Median 3-D distance between loci 1 Mb apart", "distance vs genomic separation", "radius of gyration per
chromosome, which is largest?", "fit the slope of contact probability vs genomic distance from the contact
map", "P(s) / distance decay between X and Y Mb (per cell type, pseudo-bulk)", "call TADs on chrN, how many
domains?", A/B compartments, loops — on tracing / DNA seqFISH+ / simulated structures or on contact maps.

Script: `<skill dir>/scripts/structures.py` (CLI prints JSON with numbers, n and `checks`; or import
its functions). First run *load-data* if you have not looked at the dataset.

## Pick the method by data type
| question | tracing / seqFISH+ (3-D coords) | contact maps (scHi-C, Hi-C) |
|---|---|---|
| distance at separation s | `structures.py dist-at data.h5cd --chrom chrN --sep 1e6 --tol 0.1` | — |
| scaling | `scaling --chrom chrN` (median distance per log bin, exponent of d ∝ s^α) | `ps` (P(s) slope) |
| radius of gyration | `rg` (per trace; median per chromosome over traces and over cells) | — |
| TADs | `tads --chrom chrN` → `uchrom.strc.tad.call_tads_by_pval` | `uchrom.strc.tad.get_domains` (directionality index) on a balanced matrix |
| compartments | `comps --chrom chrN` → `uchrom.strc.comp.call_compartments_axes_pc` | eigenvector of the O/E correlation matrix (cooltools) |
| loops | `uchrom.strc.loop.call_loops_axiswise_f` (needs dense ≤ 50 kb traces, ≥ ~100 traces) | a dot caller on ≥ 10 kb maps |

Never replace a contact-map question with a 3-D-distance proxy (or the reverse): if the question
says "from the contact map", use the map.

## Tracing: resolution first
Callers read the spot loci as bins. With sparse traces (each trace detects a few % of the loci, as in
genome-wide DNA seqFISH+) the native-resolution map is mostly empty and the caller's default window
(ArcFISH `window_bp = 1e5` ≈ 4 × 25 kb bins, made for dense tracing) calls noise. So:
1. `structures.py coverage data.h5cd --chrom chrN` → per bin size: median fraction of bins a trace
   observes, expected traces per bin pair.
2. Use the finest bin size where the median trace observes ≥ 50 % of bins (`--bin-size auto`; dense
   tracing data stays at native resolution). `bin_traces()` averages a trace's spots per bin (this also
   merges duplicate loci).
3. Keep the window in *bins*: `--window-bins 4` → `window_bp = 4 × bin size`. "Default settings" of a
   caller means its default parameters *at the data's usable resolution* — say what you used.
4. Report n traces (< 20 → exploratory), bin size, window, FDR, the number of level-1 domains (level 1
   = all boundaries; higher levels drop the weakest boundary), and a sensitivity check at the
   neighbouring bin size if the count matters.

```python
import sys; sys.path.insert(0, "<skill dir>/scripts")
from structures import call_tads, coverage, distance_at_separation
res = call_tads(cd, "chr15", bin_size="auto", window_bins=4)   # res["n_domains_level1"], res["checks"]
```

## Distances and Rg
- `dist-at` pools **all pairs of loci in all traces** whose separation is within s·(1 ± tol) and gives
  the median over pairs, n pairs and n traces, plus the median of per-cell medians (use that for
  cell-level comparisons). State the unit (`uns['xyz_unit']`).
- `rg` gives per chromosome the median over traces (population statistic) and the median of per-cell
  medians. Rg grows with chromosome length and with the number of detected loci — say so when ranking
  chromosomes or groups.
- Statistics use every spot (like `uchrom.fea.distance`); callers average duplicates.

## Contact maps: P(s)
```bash
python structures.py ps data.h5cd --cool <linked_cool key>[,<key2>,...] [--res 1e6] --chrom chr1 --smin 2e6 --smax 2e7
python structures.py ps data.h5cd --cool <linked_scool key> --cells c1,c2,... ...   # sum chosen cells
python structures.py ps file.mcool::/resolutions/1000000 --chrom chr1 ...
```
- Raw counts (`balance=False`; single-cell maps can't be balanced). P(s) per diagonal = mean contacts
  per bin pair, **divided by the total cis contacts of the chromosome** (depth normalisation, so groups
  of different depth are comparable). Slope = OLS of log10 P on log10 s, one point per diagonal with
  smin ≤ s ≤ smax. Use the map's own resolution unless the question names one (`--res` for `.mcool`).
- **Pseudo-bulk per group**: sum the group's maps. If a cell type is split into sub-clusters
  (`L23IT.1`, `L23IT.2`, …) sum all of them (comma-separated keys) — or sum the cells from the `.scool`
  — and say which. One map per group has no replicate: compare slopes descriptively, or compute
  per-cell slopes from the `.scool` and test cells (*compare-groups*).
- Single-cell maps are sparse (thousands of contacts): quote the total and treat the slope as noisy.

## Checks
- Right modality for the question (map vs coordinates); resolution and window stated.
- n traces / n cells / n contacts behind every number; < 20 traces → exploratory.
- Units; for P(s) the normalisation and the fit range.
- A/B labels are a convention — orient them with an active mark or gene density before saying "active".

## Report
> On chrN (… traces from … cells, loci at … bp binned to … bp), ⟨caller, params⟩ gives …; median
> distance at … Mb = … µm (… pairs, … traces); P(s) slope … (s = … – … Mb, … diagonals, depth-normalised,
> map …). Caveats: ….
