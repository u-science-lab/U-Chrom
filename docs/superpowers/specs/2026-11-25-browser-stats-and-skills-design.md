# U-Chrom WebUI Stats Upgrade (`P(s)` + `window` Scope + Cell-Level Rigor) & Agent Skills Alignment

Date: 2026-11-25  
Base: `origin/main` (`87d65c50`)  
Scope: `packages/uchrom-browser`, `skills/load-data`, `skills/call-structures`, `skills/show-in-browser`

---

## 1. Problem Statement & Goals

Recent Atlas batches (batches 6–11) expanded U-Chrom to 122 datasets across 77 studies, adding:
- 50+ contacts-only single-cell Hi-C / snm3C-seq / scMicro-C / sciDLO datasets (`n_spots == 0`, contact maps stored in `embedded/contacts/<key>/`);
- Format 2.3 (`cell_spatial` / `cell_shapes`), Format 2.4 (`clusters` multi-way contacts), and unordered point-set traces (`uns["trace_kind"] == "set"`).

Three gaps currently limit scientific analysis and browser-agent workflows on these datasets:
1. **No `P(s)` contact decay in WebUI `Stats`**: `StatsView` only offers `rg`, `scaling`, `hist`, and `scatter`. On contacts-only datasets without numeric cell fields (or with only maps + embeddings), `Stats` cannot show chromatin compaction decay $P(s)$ or compare $P(s)$ curves across groups (`compare_groups`).
2. **`chrom_scope="locus"` ignores the locus interval**: `stats/rg` and `stats/scaling` only accept `chrom`, ignoring `[start, end)`. Users and agents inspecting a specific TAD/locus window cannot measure local Rg or local distance scaling within that window.
3. **Statistical rigor & Skills drift**:
   - `StatsView` aggregates `rg` by trace rather than offering per-cell median aggregation + two-group cell-level Mann–Whitney summary (`compare-groups` skill contract), and drops backend `note` sampling/pooling disclosures (`_stats_sample`, `PSEUDOBULK_MAX_CELLS`).
   - `skills/load-data/scripts/inspect_data.py` and `skills/call-structures/scripts/structures.py` still assume external `.cool`/`.scool` files on disk, triggering false `"linked file is missing"` warnings or `FileNotFoundError` on embedded Atlas `.chromdata.zarr` / `.cdz` stores, and lack Format 2.3/2.4/`trace_kind="set"` summaries and `[start, end)` window flags.

### Non-Goals
- Do not modify `packages/chromdata` on-disk Format 2.4 specification or import `uchrom` inside `uchrom-browser` (`test_standalone.py` invariant).
- Do not import `cooler` or `h5py` in the embedded-map `stats_ps` path (must run with `cooler=None, h5py=None` for Cloudflare Containers).
- Do not introduce embedded chat UI or mutate global agent configs.

---

## 2. Architecture & Design

### 2.1 Contact Decay `P(s)` (`Dataset.stats_ps` & `GET /api/datasets/{id}/stats/ps`)

#### Scope & Inputs
- Query parameters:
  - `key: Optional[str] = None` — contact map key in `contact_maps()` (defaults to first non-error map; unknown explicit `key` → `KeyError` → HTTP `404`; when `key=None` and no usable non-error map exists → `LookupError` → HTTP `422`).
  - `chrom: Optional[str] = None` — `None` or `"*"` (`GENOME`) aggregates across all chromosomes in the map; a named chromosome restricts to that chromosome (unknown chromosome → `ValueError` → HTTP `422`).
  - `start: Optional[int] = None`, `end: Optional[int] = None` — optional genomic window `[start, end)` in bp. Requires a single named `chrom` (passing `start`/`end` with `chrom=None` or `chrom="*"` → `ValueError` → HTTP `422`). Input validation: if both `start` and `end` are passed and `int(end) <= int(start)` → `ValueError` → HTTP `422`; clamp `lo = max(0, int(start or 0))` and `hi = min(chrom_length, chrom_length if end is None else int(end))`; if `hi <= lo` (empty or completely out-of-bounds window, matching `contacts()` in `data.py:1679-1682`) → `ValueError` → HTTP `422`. Window `[lo, hi)` maps to half-open overlapping chromosome-local bins `b0 = lo // resolution`, `b1 = min(n_chrom_bins, -(-hi // resolution))` (matching `embedded_contacts` in `data.py:1692` and `cooler.extent`).
  - `resolution: Optional[int] = None` — bin size in bp for `.mcool` / multi-resolution embedded bulk maps: when `resolution is None`, sum/take the genomic span in scope (`hi - lo` for single chrom/window, else `sum(chrom_lengths)`) and choose the **finest** resolution `r` in sorted ascending `info["resolutions"]` with `span / r <= 25_000` (falling back to `info["resolutions"][-1]`), preserving short-range decay while keeping 1-D diagonal arrays tiny; invalid resolution → `ValueError` → HTTP `422`.
  - `cell_id: Optional[str] = None`, `group: Optional[str] = None` — mutually exclusive (`_one_scope` → `ValueError` → HTTP `422`).
    - On `per_cell` (`.scool`) maps:
      - `cell_id`: selects that cell (missing cell in map → `KeyError` → HTTP `404`); sets `group=None, cell_id=str(cell_id), n_cells=1`.
      - `group`: unknown field/registered group id → `KeyError` → HTTP `404`; valid empty dataset group or valid group with zero cells present in the map → `LookupError` → HTTP `422`; `group="all"` uses precomputed `SUM` partitions when embedded and `has_sum()`, else caps at `PSEUDOBULK_MAX_CELLS = 20_000` with a deterministic RNG `default_rng(0)` sample and appends a disclosure to `note`; returns `group=str(group), cell_id=None, n_cells=len(used_cells)`.
      - `cell_id=None, group=None` on `per_cell` maps: pools all cells in the map identically to `group="all"` (including `SUM` fast path and `PSEUDOBULK_MAX_CELLS` cap + `note`), while returning `group=None, cell_id=None, n_cells=len(used_cells)` (preserving exact scope echo parity with `stats_rg` / `stats_scaling`).
    - On bulk (`.cool` / `.mcool`) maps: `group` or `cell_id` → `ValueError` → HTTP `422` (`"contact map ... is not per-cell"`). Returns `group=None, cell_id=None, n_cells=None`.
  - `n_bins: int = 24` — number of log-spaced separation bins (`1 <= n_bins <= 200`, else `ValueError` → HTTP `422`).
  - `smin: Optional[float] = None`, `smax: Optional[float] = None` — optional fit range in bp (`smin <= 0`, `smax <= 0`, or `smin > smax` → `ValueError` → HTTP `422`).

#### Mathematical Definition (Raw Cis Contacts, Parity with `structures.contact_ps`)
- **Raw counts only (`balance=False`)**: single-cell and pseudo-bulk maps are un-balanced; `P(s)` always operates on upper-triangle raw cis counts `bin1 <= bin2` (`bin1_id`, `bin2_id` chromosome-local).
- For each included chromosome $c$ with bin range $[b_0, b_1)$ ($n_c = b_1 - b_0$):
  - If $\max_c n_c < 2$: return empty arrays `sep_bp=[]`, `p=[]`, `n_pairs=[]`, `n_contacts=[]`, `slope=None`, `intercept=None`, `fit_range_bp=None`, `total_cis_contacts=0.0`.
  - Skip chromosomes with $n_c < 2$ when accumulating diagonals, keeping pixels strictly inside $b_0 \le i \le j < b_1$ (`k = j - i >= 0`).
  - Accumulate diagonal sums $C_c(k) = \sum_{j-i=k} \text{count}_{ij}$ ($0 \le k < n_c$) and valid pair counts $N_c(k) = n_c - k$ ($1 \le k < n_c$). Both HDF5 `.cool`/`.scool` and `embedded/contacts` store upper-triangle cis pixels (`i <= j`); filtering `i <= j` guarantees no double-counting even on symmetric inputs.
- Sum across all included chromosomes in scope (assuming uniform binsize $B$, which `embed_scool` and standard coolers guarantee):
  - $C(k) = \sum_c C_c(k)$ for $k \ge 0$, $N_{\text{pairs}}(k) = \sum_c \max(0, n_c - k)$ for $k \ge 1$.
  - Total cis contacts in scope (within the selected chromosomes/window): $T_{\text{cis}} = \sum_{k \ge 0} C(k)$.
  - If $T_{\text{cis}} \le 0$ or $\sum_{k \ge 1} C(k) \le 0$: if $T_{\text{cis}} \le 0$ (or no positive diagonals exist) return empty arrays `sep_bp=[]`, `p=[]`, `n_pairs=[]`, `n_contacts=[]`, `slope=None`, `intercept=None`, `fit_range_bp=None` (with `total_cis_contacts = float(T_cis)`). Note: if only $k = 0$ self-ligation counts exist, $T_{\text{cis}} > 0$ while $p_k = 0$ for all $k \ge 1$, so binned output arrays are empty and `slope=None`.
- **Per-diagonal normalized probability**:
  $$p_k = \frac{C(k) / N_{\text{pairs}}(k)}{T_{\text{cis}}}, \quad s_k = k \cdot B \quad (k \ge 1).$$
  - This matches `structures.contact_ps()` identically on any single chromosome / window (`np.diagonal(M, k).mean() / total`).
- **Log-spaced curve binning (for plotting across 1 kb–100 Mb)**:
  - Over $k \in [1, k_{\max}]$ where $N_{\text{pairs}}(k) > 0$, build `n_bins` geometric edges on $[1, k_{\max} + 0.0001]$ (`np.geomspace(1.0, k_max + 1e-4, n_bins + 1)`). When `n_bins > k_max`, inner short-range bins cover single integer diagonals (`|K_b| = 1`, where $P_b = p_k$ and $s_b = s_k$ identically) and empty sub-unit bins are skipped.
  - For each bin $b$ with non-empty integer diagonals $K_b$ and $\bar{C}_b > 0$:
    $$\bar{C}_b = \sum_{k \in K_b} C(k), \quad \bar{N}_b = \sum_{k \in K_b} N_{\text{pairs}}(k), \quad P_b = \frac{\bar{C}_b / \bar{N}_b}{T_{\text{cis}}}, \quad s_b = \sqrt{s_{\min, b} \cdot s_{\max, b}}$$
    (geometric midpoint of the min and max $s_k = k \cdot B$ in $K_b$; skip bins with $K_b = \emptyset$ or $\bar{C}_b \le 0$).
  - Because `|K_b| = 1` bins equal unbinned $p_k$ identically while wide long-range bins pool counts before dividing by pairs, sparse single-cell/snm3C curves stay unbiased without dropping zero diagonals individually.
- **Power-law slope (exact parity with `structures.contact_ps`)**:
  - Fit OLS of $\log_{10}(p_k)$ on $\log_{10}(s_k)$ over **unbinned** positive diagonals ($k \ge 1$, $C(k) > 0$) restricted to `[smin, smax]` when provided (default: all positive diagonals $k \ge 1$): `np.polyfit(np.log10(s[ok]), np.log10(p[ok]), 1)` when `ok.sum() >= 3`, else `slope=None, intercept=None, fit_range_bp=None`.
  - Thus `stats_ps` and `structures.contact_ps` agree identically on unbinned slope, intercept, and `total_cis_contacts` for any chromosome/window and `[smin, smax]`.

#### Response JSON (`GET /api/datasets/{id}/stats/ps`)
```json
{
  "key": "cells",
  "resolution": 500000,
  "chrom": "chr1",
  "start": 0,
  "end": 100000000,
  "sep_bp": [500000, 1000000, ...],
  "p": [0.00041, 0.00019, ...],
  "n_pairs": [199, 198, ...],
  "n_contacts": [4120.0, 1950.0, ...],
  "slope": -1.02,
  "intercept": 2.31,
  "fit_range_bp": [500000, 99500000],
  "total_cis_contacts": 50000.0,
  "group": "field:cell_type=H1Esc",
  "cell_id": null,
  "n_cells": 312,
  "note": null
}
```
Notice: `embedded` maps MUST read directly from Zarr arrays (`sum_pixels`, `region_pixels`, `cell_pixel_blocks` using `bincount` over diagonal $k = d[:, 1] - d[:, 0]$) without importing `cooler` or `h5py`. External `.cool`/`.mcool` reads via `cooler`, external `.scool` reads via `h5py` bin1_offset slices (`_pseudobulk` pattern).

---

### 2.2 Genomic Window Scope (`chrom_scope="window"`)

#### Semantics Across Backend & Frontend
- `chrom_scope` gains a third option: `'all' | 'locus' | 'window'` (default `'all'`).
  - `'all'`: all chromosomes (`chrom=None, start=None, end=None`).
  - `'locus'`: whole current locus chromosome (`chrom=locus.chrom, start=None, end=None`; if `locus.chrom === '*'`, falls back to `'all'`). Preserves backward compatibility with existing tests and skills.
  - `'window'`: current locus interval (`chrom=locus.chrom, start=locus.start, end=locus.end`; if `locus.chrom === '*'`, falls back to `'all'`).
- **Spot interval filtering (`_stats_spots` in `data.py`)**:
  - Validation helper `_stats_window(chrom, start, end)`: if `start is None and end is None`, return `(None, None)`. Otherwise require `chrom` non-empty and `chrom != "*"` (`GENOME`), else raise `ValueError` (HTTP `422`). Validate against chromosome bounds when available and require `lo = max(0, int(start or 0))` < `hi = min(chrom_len, chrom_len if end is None else int(end))` and `int(end) > int(start)` when both are given (`ValueError` → HTTP `422`).
  - Half-open overlap matching `GeometryFilter`: `(a["end"] > lo) & (a["start"] < hi)`.
  - In `stats_rg`: when `start is not None or end is not None` (sub-chromosome window), omit traces with `< 2` finite spots in the window (a 1-spot fragment has degenerate `Rg = 0` which skews medians). Whole-chromosome/all-chromosome `stats_rg` keeps existing behavior so existing tests do not change.
  - In `_stats_sample`: because Format 2.2 `index/coords/` stores chromosome-copy runs (`trace_offsets`, `chrom_trace`, `trace_cells`, `trace_codes`) without per-run genomic `[start, end)` bounds, do NOT call `self._segments()` (which would read every spot's `bin_id` over HTTP); instead, matching `Dataset.distance()`, sample whole chromosome-copy runs of random cells on `chrom`, forward `start=start, end=end` into `part.stats_rg(chrom, start=start, end=end)` and `part.stats_scaling(chrom, start=start, end=end, n_bins=n_bins)`, report `n_cells` from the spots inside the window, and preserve the sampling disclosure `note`.
- **Schema & Tooling**:
  - `ui_tools.json`: `open_view.chrom_scope` enum becomes `["all", "locus", "window"]`, description updated clearly.
  - `actions.ts`: accept `'all' | 'locus' | 'window'` on `chrom_scope`, `'trace' | 'cell'` on `rg_unit`, and `source` on `stats` (and `matrix`) views; report `chrom_scope`, `rg_unit`, and `source` in `describe_workspace` (`views[*]`).
  - `StatsView.tsx` & `api.ts`: base, overlay (`compare_groups`), and focused-cell fetches for `rg`, `scaling`, and `ps` ALL propagate the same resolved `{chrom, start, end}` from `statsRegion(pane.chromScope, locus)`. When `locus.chrom === "*"`, `statsRegion('window', locus)` falls back cleanly to `{chrom: null, start: null, end: null}` (all chromosomes, never passing `start`/`end` with `*`).
  - `capture.ts`: `paneFilename` includes locus when `pane.type === 'stats' && (pane.chromScope === 'locus' || pane.chromScope === 'window')` and `Workspace.tsx` `usesLocus` includes `p.chromScope === 'window'`.

---

### 2.3 Cell-Level Rg Rigor & Sampling Disclosure (`StatsView.tsx` & `stats.ts`)

1. **Per-cell median vs per-trace distribution on `rg`**:
   - Backend `stats_rg` keeps `trace_ids`, `cell_ids`, `chroms`, `rg`, `n_spots`, and adds `per_cell_median: Optional[float]` (median over cells having at least one finite trace Rg value in scope of each cell's median trace Rg; `None` when `cell_ids` are absent or no finite cell values exist) alongside `note`.
   - Frontend `PaneOptions` adds `rgUnit?: 'trace' | 'cell'` (default `'trace'` for backward compatibility, switchable in `StatsControls` whenever `ds.n_cells > 1` and `kind === 'rg'`).
   - Pure helper `perCellMedians(rg: RgStats): number[]` in `stats.ts` groups finite `rg.rg[i]` values by non-null `rg.cell_ids[i]` and returns each cell's median Rg (excluding cells with zero finite trace Rg values).
   - Pure helper `mannWhitneyTwoSided(a: readonly number[], b: readonly number[])` in `stats.ts`:
     - Filters both arrays to finite numbers; returns `null` when `nA === 0 || nB === 0`.
     - Computes exact `u = U_a` = $\sum_{i,j} [\mathbb{I}(a_i > b_j) + 0.5\,\mathbb{I}(a_i = b_j)]$ via average ranks on pooled sorted values (so swapping `a` and `b` maps `u -> nA * nB - u`).
     - Rank-biserial correlation: `rankBiserial = 2 * u / (nA * nB) - 1` (positive when group `a` tends larger than `b`; swapping `a` and `b` negates `rankBiserial`).
     - Two-sided normal-approximation p-value with tie correction and `0.5` continuity correction: $\sigma^2 = \frac{n_A n_B}{12}\left((N+1) - \frac{\sum (t_k^3 - t_k)}{N(N-1)}\right)$, $z = \max(0, |u - n_A n_B / 2| - 0.5) / \sigma$, $p = \operatorname{erfc}(z / \sqrt{2})$. If $\sigma \le 0$ (all values tied) or $z = 0$, return `p = 1` (and `rankBiserial = 0` when all values are identical). Note: `"u"` is exact, `"p"` is continuity- and tie-corrected normal approximation; sets `exploratory: Math.min(nA, nB) < 5`.
   - When `kind === 'rg'`, `rgUnit === 'cell'`, and `overlays.length === 1`, the legend appends the cell-level two-group comparison (`MW p=… · r=…` or `n<5 exploratory` when `min(n_a, n_b) < 5`).
2. **Sampling / Pooling Disclosure Badge**:
   - Render any non-null `note` returned by `rg`, `scaling`, or `ps` (and when multiple overlaid groups have notes, deduplicate and join) inside `.pane-badge` alongside `chrom` / `start-end` / `baseGroup`, so neither human researchers nor captured screenshots/SVGs ever mistake a sampled or pseudo-bulk-capped curve for an unsampled full-store result.
3. **Contacts-only Dataset Enablement & Bulk-Map Guard**:
   - `supportedPaneTypes(k)` in `workspace.ts`: enable `'stats'` when `k.hasCoords || !!k.manyCells || !!k.hasContactMaps`.
   - Canonical parameter order: `availableKinds(hasCoords: boolean, hasFields: boolean, hasContactMaps = false): StatsKind[]` in `StatsView.tsx` returns `[...(hasCoords ? ['rg', 'scaling'] : []), ...(hasContactMaps ? ['ps'] : []), ...(hasFields ? ['hist', 'scatter'] : [])]`, where `hasContactMaps = (ds?.contact_maps ?? []).some((m) => m.kind !== 'error')`.
   - When `kind === 'ps'`:
     - If more than one usable map exists, `StatsControls` renders a map `source` selector (`Select`), resolved cleanly via `resolvePsMapKey(pane.source, usableMaps)`.
     - Check `selectedMap?.per_cell`: ONLY pass `group`/`cellId` to `fetchPs` and ONLY render `<CompareGroups pane={pane} />` when `selectedMap.per_cell` is `true` (avoiding HTTP `422` when a user has focus or groups on a hybrid dataset with a bulk `.cool`/`.mcool` map).

---

### 2.4 Agent Skills Modernization (`skills/`)

1. **`skills/load-data/scripts/inspect_data.py` & `SKILL.md`**:
   - Dispatch on embedded metadata BEFORE importing optional `cooler` or inspecting external paths: `linked_maps(cd, path=None)` reads `cd.embedded_links()["contacts"]` + `chromdata.embedded.open_all(...)` (using explicit `path` or `getattr(cd, "_store_path", None)` so embedded discovery works without `cooler` or `h5py` installed). Reports `"embedded": True`, `"exists": True`, `"resolutions"`, `"n_cells"` (for `per_cell`), `"has_sum"`, and `"chroms"`, and never emits `"linked file ... is missing"` when an embedded copy is present.
   - `summarize(cd, path=None, group=...)`: report `clusters` (`key`, `n_clusters`, `n_fragments`, `per_cell`, `assay`) when `cd.clusters` is non-empty, `cell_spatial` (`key`, `unit`, `frame`, `n_shapes`) when `uns.get("cell_spatial")` or `cd.cell_shapes` is present, and `trace_kind` (`"set"` vs `"fibre"`).
   - `tracing_qc` & `checks`: when `cd.uns.get("trace_kind") == "set"`, omit `consecutive_loci` (`None` — unordered localizations have no polymer chain step) and add an explicit check noting unordered point-set traces (territory `Rg` valid, consecutive bond length not applicable).
2. **`skills/call-structures/scripts/structures.py` & `SKILL.md`**:
   - Add optional `--start` and `--end` (bp) to `dist-at`, `scaling`, `rg`, and `ps` (with `chrom` required if `--start`/`--end` is given), using the same `[start, end)` half-open overlap and `>= 2` spots per trace fragment rule for windowed `rg`.
   - Dispatch on embedded stores FIRST (when input ends in `.chromdata.zarr` / `.cdz` / `.zarr` and the key is in `cd.embedded_links()["contacts"]` / `open_all(store_path)`): compute `contact_ps` directly via `chromdata.embedded.EmbeddedContacts` without importing `cooler` or `h5py` and without requiring external `.cool`/`.scool` files on disk (including `--cells c0,c1` and full pseudo-bulk via `sum_pixels`/`cell_pixel_blocks`), matching `Dataset.stats_ps` unbinned diagonals and OLS slope.
3. **`skills/show-in-browser/SKILL.md`**:
   - Document `stats="ps"`, `source`, `chrom_scope="window"`, `rg_unit="cell"`, and the rule to report any sampling disclosure badge.

---

## 3. Verification & Acceptance Criteria

1. **Automated Unit & Parity Tests**:
   - `packages/uchrom-browser/tests/`: `test_data.py`, `test_server.py`, `test_embedded_maps.py` (linked vs embedded parity with `cooler=None, h5py=None`, `.cdz` parity, edge cases including zero contacts, `k=0`-only contacts, `< 2`-bin chromosome, `n_bins` > diagonals, empty/invalid `smin`/`smax`, window bounds & clipping, `404`/`422` matrix), `test_standalone.py`.
   - `packages/uchrom-browser/uchrom_browser/frontend`: Vitest suites for `stats.ts`, `workspace.ts`, `actions.ts`, `StatsView` helpers, `capture` vector compatibility (no `SvgContext2D` unsupported primitives), plus deterministic `npm run build` (`static/` clean).
   - `packages/uchrom/tests/skills/`: `test_new_skills.py` covering embedded `.chromdata.zarr`/`.cdz` `inspect_data` & `structures.py ps` (including with `cooler=None, h5py=None`), Format 2.3/2.4/`trace_kind="set"`, and windowed parity with `uchrom_browser.data.Dataset`.
2. **Real-Data Validation (when local fixtures/cache exist)**:
   - `packages/uchrom-browser/tests/fixtures/mESC_Sox2_5cells_wnan.chromdata.zarr` (DNA FISH): `rg`, `scaling`, and sub-region `window` checks across browser backend & `structures.py`.
   - Optional local cache `~/.cache/uchrom/kim2020_scihic/kim2020_scihic.chromdata.zarr` (Kim 2020 H1Esc vs HFF sciHi-C `.scool`, plus embedded temp copy): `stats_ps` population, `H1Esc` vs `HFF`, full `chr1` vs `chr1:0-100Mb` window, and numerical parity with `structures.py ps`.
3. **Live Server & Action/Vector Capture Smoke**:
   - Start `uchrom_browser` on loopback, query `/api/datasets/{id}/stats/{rg,scaling,ps}`, and run rendered browser / `connect()` verification if Playwright/Chrome is available (explicitly recording which stage ran).

---

## 4. Review Log (Planner + GPT-6.2 Sol)

Reviewed read-only by `gpt-6.2-sol` (`reasoning_effort="high"`, 2026-11-25). All findings resolved prior to implementation:
- **HTTP status matrix (`P1`)**: aligned `KeyError -> 404` (unknown dataset/explicit map key/cell/group identifier) vs `LookupError / ValueError -> 422` (`key=None` with no usable map, empty matching cells, bad windows, or grouping on bulk maps).
- **Window bounds & bin mapping (`P1`)**: fixed `[lo, hi)` clamping (`hi <= lo -> ValueError -> 422`) and `b0 = lo // res, b1 = min(n_bins, -(-hi // res))` uniformly across `data.py` and `structures.py`; chose finest `.mcool` resolution with `span / r <= 25_000`.
- **Bin pooling vs unbinned OLS parity (`P1`)**: clarified that geometric curve bins match unbinned $p_k$ where `|K_b| = 1`, pool counts/pairs where `|K_b| > 1`, and compute OLS slope on unbinned positive diagonals matching `structures.contact_ps`.
- **Backed/windowed sampling (`P1`)**: specified window overlap filtering in `_stats_sample` / run selection so sampled cells/runs overlap `[lo, hi)`.
- **Frontend contracts (`P1`/`P2`)**: standardized `availableKinds(hasCoords, hasFields, hasContactMaps = false)` signature, complete TS interfaces (`PsStats`, `note`, `per_cell_median`), full Mann–Whitney tie/continuity/zero-variance math (`u = U_a`, signed rank-biserial, `p = 1, r = 0` on ties), `per_cell` guard for bulk maps on `ps`, and end-to-end window propagation (`statsRegion`).
- **Skills embedded dispatch (`P1`)**: ordered embedded Zarr dispatch before external cooler paths so `inspect_data.py` and `structures.py ps` succeed with `cooler=None, h5py=None`.
