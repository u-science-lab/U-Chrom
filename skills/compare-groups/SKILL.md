---
name: compare-groups
description: Use for any comparison of cell groups in U-Chrom data — do X cells have larger Rg / nuclei / more … than Y, is a mark different, which mark differs most, what is different about selected cells, is it still there at equal spots per trace, per-cell contact stats (P(s) slope, cis contacts, contact density), multi-way clusters, p-values. Per-cell stats, Mann–Whitney, effect size, FDR, confounders.
---

# Compare groups of cells

## When to use
"Are X cells different from Y?", "what is special about the cells I selected?", "is chromatin
more compact in …?", "which mark differs most …?" — any group comparison on a ChromData (`.chromdata.zarr` / `.cdz`; convert an older `.h5cd` first with `python -m uchrom.io.upgrade old.h5cd`).
For pseudo-bulk contact-map statistics use *call-structures*; for per-cell contact-map comparisons
(`ps_slope`, `cis_contacts`, `contact_density`), windowed tracing (`--chrom`/`--start`/`--end`), or
multi-way cluster comparisons (`clusters:<key>:n_clusters|median_size|cis_frac`), use this skill.
For correlations use *associate-modalities*.

## Steps
1. **Get the groups.** Cell ids (`a,b,c`), `field:<cells column>=<value>` (e.g. `field:cell_type=<TYPE>`),
   `field:<col>!=<value>`, or `rest` for b (= every other cell). From an open browser:
   `ws = uchrom_browser.connect(); cells = ws.selected_cells()` (*show-in-browser*). Make the groups
   disjoint; "vs all other cells" means `rest`, not a single other type.
2. **One statistic** — run `scripts/compare_groups.py` (CLI) or import `compare()`:
   ```bash
   python <skill dir>/scripts/compare_groups.py data.chromdata.zarr --a field:cell_type=<TYPE_A> --b field:cell_type=<TYPE_B> --stat rg
   python <skill dir>/scripts/compare_groups.py data.chromdata.zarr --a field:cell_type=<TYPE_A> --b field:cell_type=<TYPE_B> --stat rg --chrom chr1 --start 0 --end 10000000
   python <skill dir>/scripts/compare_groups.py data.chromdata.zarr --a field:cell_type=<TYPE_A> --b field:cell_type=<TYPE_B> --stat ps_slope --chrom chr1 [--smin 1e5 --smax 1e7] [--cool per_cell]
   python <skill dir>/scripts/compare_groups.py data.chromdata.zarr --a field:cell_type=<TYPE_A> --b field:cell_type=<TYPE_B> --stat clusters:sprite:cis_frac
   ```
   ```python
   import sys; sys.path.insert(0, "<skill dir>/scripts")
   from compare_groups import compare, scan
   res = compare(cd, "field:cell_type=A", "field:cell_type=B", stat="rg")
   # stat: rg | span | n_spots | ps_slope | cis_contacts | contact_density | clusters:<key>:<n_clusters|median_size|cis_frac> | <cells column>
   ```
   Per-trace statistics (`rg`, `span`, `n_spots`) are summarised as the **median per cell**; the group
   value is the median over cells; the test compares cells. Optional `chrom`, `start`, `end` restrict
   tracing (dropping `< 2`-spot trace fragments for `rg`/`span`), contact maps, and clusters to a genomic
   window. Per-cell contact stats read embedded Zarr maps (`embedded/contacts`) first without needing
   `cooler` or `h5py`, falling back to `linked_scool` via `h5py`.
3. **Many features / "what is different"** — `scan()` / `--scan if.` (prefix; `""` = every numeric
   cells column) tests each column per cell, sorts by p, and adds **BH-FDR q** across all columns tested
   plus the categorical composition (e.g. which cell type the selection is). Report the top field with
   its q, the number tested, and the correction.
4. **Equal detection** — if `res["checks"]` says spots per trace differ, rerun with `equalize=k`
   (`--equalize k`): Rg/span recomputed on k random loci per trace (mean of 20 draws; traces with fewer
   dropped). Pick k ≈ the lower quartile of spots per trace of the sparser group; report k, both
   medians and the p before/after.
5. **Read `res["checks"]` and act on every item** (see below).
6. **Show it** only if a browser is open (*show-in-browser*).
7. **Report** (template below).

## Checks (never skip)
- **Unit of replication = cell.** Never test traces or spots as independent samples; hundreds of
  traces from a few cells give tiny, meaningless p-values. Quote trace counts only as context.
- **Medians, not means**, for per-cell and per-group summaries (skewed statistics); rank test, not t-test.
- **n per group ≥ 5 cells**, else call the result exploratory and give no p-value claims.
- **Multiple testing.** Scanning many marks/genes → BH-FDR (q) across all of them; say how many.
- **Confounders.** If the statistic tracks nuclear volume (`res["confounder"]`, |ρ| > 0.5), say
  the difference may reflect nuclear size; if possible compare within a size range. For `ps_slope` and
  `contact_density`, check `res["depth_confounder"]` (`cis_contacts`) and warn if median `cis_contacts < 1000`.
  If spots per trace differ, compare at equal loci (step 4).
- **Set traces & single region/batch.** If `uns["trace_kind"] == "set"`, `span` is not meaningful — prefer `rg`.
  One `fov`/`region`/`batch`/`replicate`/`sample` → say there is no replicate.
- Effect size with the test: median ratio and rank-biserial r (+1: every a cell > every b cell).

## Report template
> *A* (n = … cells, … traces) vs *B* (n = … cells, … traces): median per-cell ⟨stat⟩ … vs … (ratio …);
> Mann–Whitney on per-cell values p = …, rank-biserial r = …. ⟨At k equal loci: … vs …, p = ….⟩
> ⟨Scan: top ⟨field⟩ q = … of … fields, BH-FDR.⟩ Caveats: ⟨every check⟩. Views: ⟨pane ids, if any⟩.
