---
name: compare-groups
description: Compare a chromatin statistic (radius of gyration, end-to-end span, or any per-cell field such as nuclear volume or an IF mean) between two groups of cells in a U-Chrom ChromData, with the cell as the unit of replication, an effect size, and the checks a report must mention. Use when asked whether cells of one type / cluster / selection differ from others.
---

# Compare two groups of cells

## When to use
"Are X cells different from Y?", "what is special about the cells I selected?", "is chromatin
more compact in …?" — any two-group comparison on a ChromData (`.h5cd`).

## Steps
1. **Get the groups.** From the browser: `ws = uchrom.browser.connect(); cells = ws.selected_cells()`
   (see the *show-in-browser* skill). Otherwise cell ids, or `field:<cells column>=<value>`
   (e.g. `field:cell_type=Granule`). Make the groups disjoint.
2. **Compute, per cell.** Run `scripts/compare_groups.py` (CLI) or import `compare()`:
   ```python
   import sys; sys.path.insert(0, "<skill dir>/scripts")
   from compare_groups import compare
   res = compare(cd, cells, "field:cell_type=Granule", stat="rg")
   ```
   Per-trace statistics are summarised as the **median per cell**; the test compares cells.
3. **Read `res["checks"]` and act on every item** (see below).
4. **Show it** (if a browser is open): select the group, open a Genome view with both groups'
   distance maps and a Stats view comparing them (*show-in-browser*).
5. **Report** (template below).

## Checks (never skip)
- **Unit of replication = cell.** Never test traces or spots as independent samples; hundreds of
  traces from a few cells give tiny, meaningless p-values. Quote trace counts only as context.
- **n per group ≥ 5 cells**, else call the result exploratory and give no p-value claims.
- **Confounders.** If the statistic tracks nuclear volume (`res["confounder"]`, |ρ| > 0.5), say
  that the difference may reflect nuclear size; if possible compare within a size range.
- **One batch / field of view** → say there is no replicate.
- Effect size with the test: median ratio and rank-biserial r (+1: every a cell > every b cell).

## Report template
> *A* (n = … cells, … traces) vs *B* (n = … cells, … traces): median per-cell ⟨stat⟩ … vs … (ratio …);
> Mann–Whitney on per-cell values p = …, rank-biserial r = …. Caveats: ⟨every check⟩.
> Views: ⟨pane ids⟩.
