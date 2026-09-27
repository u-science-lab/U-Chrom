---
name: compare-groups
description: Use for any comparison of cell groups in U-Chrom data — do X cells have larger Rg / nuclei / more … than Y, is a mark different, which mark differs most, what is different about selected cells, is it still there at equal spots per trace, p-values. Per-cell stats, Mann–Whitney, effect size, FDR, confounders.
---

# Compare groups of cells

## When to use
"Are X cells different from Y?", "what is special about the cells I selected?", "is chromatin
more compact in …?", "which mark differs most …?" — any group comparison on a ChromData (`.h5cd`).
For contact-map statistics per group (P(s) of pseudo-bulk maps) compute them with *call-structures*
and compare there; for correlations use *associate-modalities*.

## Steps
1. **Get the groups.** Cell ids (`a,b,c`), `field:<cells column>=<value>` (e.g. `field:cell_type=Granule`),
   `field:<col>!=<value>`, or `rest` for b (= every other cell). From an open browser:
   `ws = uchrom.browser.connect(); cells = ws.selected_cells()` (*show-in-browser*). Make the groups
   disjoint; "vs all other cells" means `rest`, not a single other type.
2. **One statistic** — run `scripts/compare_groups.py` (CLI) or import `compare()`:
   ```bash
   python <skill dir>/scripts/compare_groups.py data.h5cd --a field:cell_type=Bergmann --b field:cell_type=Granule --stat rg
   ```
   ```python
   import sys; sys.path.insert(0, "<skill dir>/scripts")
   from compare_groups import compare, scan
   res = compare(cd, "field:cell_type=A", "field:cell_type=B", stat="rg")      # rg | span | n_spots | <cells column>
   ```
   Per-trace statistics (`rg`, `span`, `n_spots`) are summarised as the **median per cell**; the group
   value is the median over cells; the test compares cells.
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
  the difference may reflect nuclear size; if possible compare within a size range. If spots per trace
  differ, compare at equal loci (step 4).
- **One batch / field of view** → say there is no replicate.
- Effect size with the test: median ratio and rank-biserial r (+1: every a cell > every b cell).

## Report template
> *A* (n = … cells, … traces) vs *B* (n = … cells, … traces): median per-cell ⟨stat⟩ … vs … (ratio …);
> Mann–Whitney on per-cell values p = …, rank-biserial r = …. ⟨At k equal loci: … vs …, p = ….⟩
> ⟨Scan: top ⟨field⟩ q = … of … fields, BH-FDR.⟩ Caveats: ⟨every check⟩. Views: ⟨pane ids, if any⟩.
