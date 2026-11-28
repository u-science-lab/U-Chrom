# Browser Stats Upgrade (`P(s)` + `window` Scope + Cell-Level Rigor) & Agent Skills Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add raw cis contact decay `P(s)` (`stats="ps"`), true `[start, end)` genomic window scope (`chrom_scope="window"`), cell-level Rg summary + sampling disclosure in `uchrom-browser`, and align `load-data` / `call-structures` / `show-in-browser` skills with embedded Atlas stores and Format 2.3/2.4.

**Architecture:** `uchrom-browser` computes `stats_ps` directly on `EmbeddedContacts` Zarr partitions (zero `cooler`/`h5py` dependency) and external `.cool`/`.mcool`/`.scool` files, extends `_stats_spots`/`stats_rg`/`stats_scaling` with half-open `[start, end)` filtering, exposes `ps`, `window`, `rg_unit`, and `note` through `ui_tools.json` + `StatsView.tsx`, and mirrors the exact same semantics in `skills/` scripts.

**Tech Stack:** Python 3.11+ (`chromdata`, `numpy`, `pandas`, `fastapi`, `zarr`), TypeScript/React (`zustand`, `vitest`, `vite`, `SvgContext2D`), `scipy` (skills only).

**Spec:** `docs/superpowers/specs/2026-11-25-browser-stats-and-skills-design.md`

## Global Constraints
- `packages/uchrom-browser` MUST NEVER import `uchrom` (`test_standalone.py` enforces).
- Embedded contact maps in `uchrom-browser` MUST run with `cooler` and `h5py` absent (`sys.modules["cooler"] = None; sys.modules["h5py"] = None`).
- Do NOT modify Format 2.4 (`chromdata` on-disk layout stays unchanged).
- Frontend changes MUST run `npm run build` in `packages/uchrom-browser/uchrom_browser/frontend` and commit updated `packages/uchrom-browser/uchrom_browser/static/` so `git status --porcelain -- ../static` is clean.
- `StatsView.tsx` MUST only use Canvas 2D primitives recorded by `SvgContext2D` (`svgctx.ts`) for vector SVG/PDF export.

## Review Focus
1. **Un-indexed/Backed vs Embedded `.scool` parity (`group="all"` and `cell_id=None, group=None`)**: Calling `stats_ps` with `cell_id=None, group=None` on a `per_cell` map (both external `.scool` and embedded with/without `SUM`) aggregates all cells identically to `group="all"` while returning `"group": None`, and fails with `422` if `group` or `cell_id` is passed on a bulk `.cool`/`.mcool`.
2. **Large backed store `_stats_sample` with `[start, end)` window**: When `_index_segments()` is True (`LARGE_SPOTS`), `_stats_sample` samples whole chromosome-copy runs on `chrom` without calling `self._segments()`, forwards `start` and `end` to `part.stats_rg` / `part.stats_scaling`, and returns the non-empty sampling disclosure `note` (`even when note is set`).
3. **`start`/`end` validation & `chr*` (`GENOME`) boundary**: Passing `start` or `end` when `chrom` is `None` or `"*"` raises `ValueError` (`422`); passing `end <= start` or an empty clamped `[lo, hi)` window (`hi <= lo`) raises `ValueError` (`422`); in `StatsView`, switching locus to `"*"` while `chromScope === "window"` falls back via `statsRegion` to `{chrom: null, start: null, end: null}`.
4. **Windowed `stats_rg` 1-spot fragment artifact**: Traces with `< 2` finite spots inside `[start, end)` are excluded from windowed `stats_rg` (`start is not None or end is not None`) so degenerate `rg = 0` values do not corrupt medians, while unwindowed `stats_rg` keeps existing behavior.
5. **Embedded `.cdz` / missing external file in `skills/`**: Dispatch embedded metadata/maps before external cooler imports so deleting external `.cool`/`.scool` files after `embed_links` (or setting `sys.modules["cooler"] = None; sys.modules["h5py"] = None`) does NOT cause `inspect_data.py` to emit `"linked file is missing"` or `structures.py ps` to fail.

---

### Task 1: Backend `stats_ps` & Window-Scoped `stats_rg` / `stats_scaling`

**Files:**
- Modify: `packages/uchrom-browser/uchrom_browser/data.py`
- Modify: `packages/uchrom-browser/uchrom_browser/server.py`
- Modify: `packages/uchrom-browser/uchrom_browser/API.md`
- Test: `packages/uchrom-browser/tests/test_data.py`
- Test: `packages/uchrom-browser/tests/test_server.py`
- Test: `packages/uchrom-browser/tests/test_embedded_maps.py`

**Interfaces:**
- Produces:
  - `Dataset.stats_rg(self, chrom=None, cell_id=None, group=None, start=None, end=None) -> Dict[str, Any]` (adds `"per_cell_median": float | None`, `"note": str | None`)
  - `Dataset.stats_scaling(self, chrom=None, cell_id=None, n_bins: int = 24, group=None, start=None, end=None) -> Dict[str, Any]` (adds `"note": str | None`)
  - `Dataset.stats_ps(self, key: Optional[str] = None, chrom: Optional[str] = None, start: Optional[int] = None, end: Optional[int] = None, resolution: Optional[int] = None, cell_id: Optional[str] = None, group: Optional[str] = None, n_bins: int = 24, smin: Optional[float] = None, smax: Optional[float] = None) -> Dict[str, Any]`
  - `GET /api/datasets/{dataset_id}/stats/ps` (use keyword args on `/stats/rg`, `/stats/scaling`, and `/stats/ps` in `server.py`)

- [ ] **Step 1: Write failing tests in `test_data.py`, `test_server.py`, and `test_embedded_maps.py`**
  - `test_data.py`: `test_stats_window_and_per_cell_median` (asserts `[start, end)` half-open overlap, `< 2`-spot window trace drop in `stats_rg`, `per_cell_median` vs trace median when a cell has unequal traces + null-only cell exclusion, `ValueError` on `start` without `chrom` or `chrom="*"` or `end <= start` or out-of-bounds empty window, and `_stats_sample` forwarding `start`/`end` with monkeypatched `LARGE_SPOTS`/`STATS_MAX_SPOTS`); `test_stats_ps_power_law_and_edge_cases` (analytical $C(k) = (n-k)\cdot \text{round}(10000 \cdot k^{-1})$ recovers `slope` within `0.02` of `-1.0`, checks `total_cis_contacts`, single-diagonal first bin `p[0]` equality to $C(1)/(n-1)/T_{\text{cis}}$ when `n_bins >= n`, `smin`/`smax` range, zero contacts, `k=0`-only contacts, `< 2`-bin chromosome, `n_bins > k_max`, and invalid `smin`/`smax`).
  - `test_embedded_maps.py`: `test_stats_ps_embedded_equals_linked` (parametrized across `bulk` & `cells`, `chrom=None`/`"chr1"`/`"chr2"` with `start`/`end`, `resolution=2*RES`, `cell_id="c1"`, `group="field:cell_type=A"`, `group="all"`, and default `cell_id=None, group=None`), plus `test_stats_ps_embedded_needs_no_cooler` (`cooler=None, h5py=None`) and `.cdz` parity.
  - `test_server.py`: `test_stats_routes_and_ps` (`GET /stats/rg`, `/stats/scaling`, `/stats/ps` HTTP `200`, `404` for unknown explicit map key/missing cell/unknown group id, `422` for `key=None` with no usable map, valid group with zero matches in map, `start` without `chrom`, `end <= start`, out-of-bounds empty window, `cell_id`+`group`, or `group` on bulk map).
- [ ] **Step 2: Run tests to verify they fail**
  - Run: `(cd packages/uchrom-browser && ../../.venv/bin/pytest tests/test_data.py tests/test_server.py tests/test_embedded_maps.py -k "stats" -v)`
  - Expected: FAIL (`AttributeError: 'Dataset' object has no attribute 'stats_ps'` / unexpected keyword argument `start`).
- [ ] **Step 3: Implement `stats_ps`, `_stats_window`, `_ps_from_diagonals`, and window filtering in `data.py`, wire routes in `server.py`, and document in `API.md`**
  - Validate `start`/`end` cleanly via `_stats_window(chrom, start, end)`.
  - Ensure `_ps_from_diagonals` computes exact upper-triangle `C(k)` and `N_pairs(k)` across selected chromosomes/window, normalized by `total_cis_contacts`, log-binned curve (`n_bins`), and OLS slope on unbinned positive diagonals in `[smin, smax]`.
  - Support embedded maps without importing `cooler`/`h5py` and external `.cool`/`.mcool`/`.scool` maps.
- [ ] **Step 4: Run full `uchrom-browser` Python test suite (including `test_standalone.py`)**
  - Run: `(cd packages/uchrom-browser && ../../.venv/bin/pytest tests -v)`
  - Expected: PASS (0 failures).
- [ ] **Step 5: Commit Task 1**
  - `git add packages/uchrom-browser/uchrom_browser/data.py packages/uchrom-browser/uchrom_browser/server.py packages/uchrom-browser/uchrom_browser/API.md packages/uchrom-browser/tests/test_data.py packages/uchrom-browser/tests/test_server.py packages/uchrom-browser/tests/test_embedded_maps.py`
  - `git commit -m "feat(browser): add contact P(s) stats and genomic window scope"`

---

### Task 2: Frontend `StatsView`, Controls, Unified Actions & Vector Capture

**Files:**
- Modify: `packages/uchrom-browser/uchrom_browser/ui_tools.json`
- Modify: `packages/uchrom-browser/uchrom_browser/frontend/src/types.ts`
- Modify: `packages/uchrom-browser/uchrom_browser/frontend/src/stats.ts`
- Modify: `packages/uchrom-browser/uchrom_browser/frontend/src/workspace.ts`
- Modify: `packages/uchrom-browser/uchrom_browser/frontend/src/api.ts`
- Modify: `packages/uchrom-browser/uchrom_browser/frontend/src/actions.ts`
- Modify: `packages/uchrom-browser/uchrom_browser/frontend/src/capture.ts`
- Modify: `packages/uchrom-browser/uchrom_browser/frontend/src/components/Workspace.tsx`
- Modify: `packages/uchrom-browser/uchrom_browser/frontend/src/components/StatsView.tsx`
- Test: `packages/uchrom-browser/uchrom_browser/frontend/src/statsHelpers.test.ts`
- Test: `packages/uchrom-browser/uchrom_browser/frontend/src/actions.state.test.ts`
- Test: `packages/uchrom-browser/uchrom_browser/frontend/src/actions.test.ts`

**Interfaces:**
- Consumes: `GET /api/datasets/{id}/stats/{rg,scaling,ps}` from Task 1.
- Produces:
  - `StatsKind = 'rg' | 'scaling' | 'ps' | 'hist' | 'scatter'`
  - `ChromScope = 'all' | 'locus' | 'window'`
  - `RgUnit = 'trace' | 'cell'`
  - `statsRegion(scope: ChromScope | undefined, locus: Locus | null | undefined): { chrom: string | null; start: number | null; end: number | null }`
  - `perCellMedians(rg: RgStats): number[]`
  - `mannWhitneyTwoSided(a: readonly number[], b: readonly number[]): { u: number; p: number; rankBiserial: number; nA: number; nB: number; exploratory: boolean } | null`
  - `availableKinds(hasCoords: boolean, hasFields: boolean, hasContactMaps?: boolean): StatsKind[]`

- [ ] **Step 1: Write failing Vitest tests in `statsHelpers.test.ts` and `actions.state.test.ts`**
  - `statsHelpers.test.ts`:
    - `statsRegion` for `'all'`, `'locus'`, `'window'`, and `chrom === '*'` fallback.
    - `perCellMedians` with multiple traces per cell and `null` handling.
    - `mannWhitneyTwoSided` with known distinct samples, tied samples, identical samples (`p = 1, r = 0`), and `< 5` exploratory flag.
    - `supportedPaneTypes` enabling `'stats'` when `hasContactMaps: true` (even with `hasCoords: false, manyCells: false`).
    - `availableKinds(false, false, true)` returning `['ps']`, `availableKinds(true, false)` returning `['rg', 'scaling']`, `parseWorkspace` preserving `statsKind: 'ps'`, `chromScope: 'window'`, `rgUnit: 'cell'`, and `svgctx` capture compatibility test for `StatsView` (`unsupported.size === 0`).
  - `actions.state.test.ts`:
    - `open_view` schema includes `chrom_scope: ['all', 'locus', 'window']`, `stats: ['rg', 'scaling', 'ps', 'hist', 'scatter']`, `rg_unit: ['trace', 'cell']`, and `source`.
    - `describe_workspace` reflects `chrom_scope: 'window'`, `stats: 'ps'`, `source`, and `rg_unit: 'cell'`.
- [ ] **Step 2: Run Vitest to verify tests fail**
  - Run: `(cd packages/uchrom-browser/uchrom_browser/frontend && npx vitest run src/statsHelpers.test.ts src/actions.state.test.ts)`
  - Expected: FAIL (`statsRegion`, `perCellMedians`, `mannWhitneyTwoSided` not exported / enum mismatches).
- [ ] **Step 3: Implement types, pure helpers, workspace/actions/API updates, and `StatsView.tsx` rendering**
  - Add `PsStats` & `note` / `per_cell_median` in `types.ts`; update `api.ts` (`fetchPs`, `start`/`end` on `fetchRg`/`fetchScaling`).
  - Implement `statsRegion`, `perCellMedians`, `mannWhitneyTwoSided` in `stats.ts` (pure TS tie-corrected + 0.5-continuity-corrected normal approximation with `u = U_a`, signed `rankBiserial`, `p = 1, r = 0` on all ties, `exploratory: min(nA, nB) < 5`).
  - Update `workspace.ts`, `ui_tools.json`, `actions.ts`, `capture.ts`, `Workspace.tsx`.
  - Update `StatsView.tsx`: add `'ps'` rendering (log-log `sep_bp` vs `p` curves + dashed OLS slope line for base + overlaid `compare_groups`, slope & cis contact legend), `'window'` scope option propagating `{chrom, start, end}` uniformly to base/overlay/cell requests, `source` picker for `ps` when usable maps > 1 + `per_cell` guard for bulk maps, `rgUnit` `'trace' | 'cell'` toggle & cell-level histogram/Mann–Whitney summary, and `.pane-badge` rendering of `chrom`, `start-end`, `baseGroup`, and `note`.
- [ ] **Step 4: Run full frontend Vitest suite + production Vite build + rebuild idempotence check**
  - Run: `(cd packages/uchrom-browser/uchrom_browser/frontend && npx vitest run && npm run build && npm run build)`
  - Verify `../static` builds cleanly and passes `test_server.py::test_health_and_list`.
- [ ] **Step 5: Commit Task 2**
  - `git add packages/uchrom-browser/uchrom_browser/ui_tools.json packages/uchrom-browser/uchrom_browser/frontend packages/uchrom-browser/uchrom_browser/static`
  - `git commit -m "feat(browser-ui): add P(s) chart, window scope, and cell-level Rg mode"`

---

### Task 3: Agent Skills Modernization & Parity Tests

**Files:**
- Modify: `skills/load-data/scripts/inspect_data.py`
- Modify: `skills/load-data/SKILL.md`
- Modify: `skills/call-structures/scripts/structures.py`
- Modify: `skills/call-structures/SKILL.md`
- Modify: `skills/show-in-browser/SKILL.md`
- Test: `packages/uchrom/tests/skills/test_new_skills.py`

**Interfaces:**
- Consumes: `ChromData.embedded_links()`, `chromdata.embedded.open_all()`, `chromdata.embedded.EmbeddedContacts`, `cd.clusters`, `cd.cell_shapes`.
- Produces:
  - `inspect_data.summarize(cd)` with `embedded` map metadata, `clusters`, `cell_spatial`, `trace_kind`, and `trace_kind == "set"` QC handling.
  - `structures.py` `--start` / `--end` window support for `dist-at`, `scaling`, `rg`, `ps`, plus embedded-store `.chromdata.zarr`/`.cdz` support in `contact_ps` / `open_cooler`.

- [ ] **Step 1: Write failing tests in `packages/uchrom/tests/skills/test_new_skills.py`**
  - `test_inspect_embedded_cdz_and_format24(tmp_path)`: builds `linked_store`, embeds with `embed_links`, zips `.cdz`, deletes external `.cool`/`.scool`/`.h5ad`/`.png`, adds `clusters` and `cell_spatial` and `trace_kind="set"`, verifies `inspect_data.summarize` detects embedded maps (`exists=True`, `embedded=True`, `n_cells=3`), reports `clusters` and `cell_spatial`, sets `qc["consecutive_loci"] is None`, emits no `"linked file ... is missing"` check, and emits point-set check.
  - `test_structures_ps_on_embedded_cdz_and_window_parity(tmp_path)`: runs `structures.contact_ps` on embedded `.cdz` (both `bulk` and `cells` with `--cells c0,c1` and all cells) with external coolers deleted, verifies exact slope match vs `Dataset.stats_ps`; verifies windowed `rg`, `scaling`, `ps` match `Dataset.stats_{rg,scaling,ps}` on `[start, end)`.
- [ ] **Step 2: Run skill tests to verify they fail**
  - Run: `(cd packages/uchrom && ../../.venv/bin/pytest tests/skills -v)`
  - Expected: FAIL (`"linked file ... is missing"` or `FileNotFoundError` / missing `--start` arg).
- [ ] **Step 3: Update `inspect_data.py`, `structures.py`, and the three `SKILL.md` files**
  - Update `inspect_data.py` (`linked_maps`, `tracing_qc`, `summarize`, `checks`) and `skills/load-data/SKILL.md`.
  - Update `structures.py` (`trace_table`, `distance_at_separation`, `scaling`, `rg_table`, `rg_by_chrom`, `contact_ps` with embedded Zarr support, CLI `--start` / `--end`) and `skills/call-structures/SKILL.md`.
  - Update `skills/show-in-browser/SKILL.md` with `stats="ps"`, `source`, `chrom_scope="window"`, `rg_unit="cell"`.
- [ ] **Step 4: Run skill tests to verify they pass**
  - Run: `(cd packages/uchrom && ../../.venv/bin/pytest tests/skills -v)`
  - Expected: PASS (all skill tests green).
- [ ] **Step 5: Commit Task 3**
  - `git add skills/ packages/uchrom/tests/skills/test_new_skills.py`
  - `git commit -m "feat(skills): support embedded stores, Format 2.3/2.4, and window stats"`

---

### Task 4: Real-Data Validation, Live Server/Control Smoke & Codex `gpt-6.2-sol` Review

- [ ] **Step 1: Real-data verification**
  - Run checks against `packages/uchrom-browser/tests/fixtures/mESC_Sox2_5cells_wnan.chromdata.zarr` and `/Users/bakezq/.cache/uchrom/kim2020_scihic/kim2020_scihic.chromdata.zarr` (including an embedded temp copy with external `.scool` absent) verifying `stats_rg`, `stats_scaling`, `stats_ps`, `inspect_data.py`, and `structures.py` parity.
- [ ] **Step 2: Live server & control/browser verification**
  - Start `uchrom_browser` on loopback, query `/api/health` and `/api/datasets/{id}/stats/{rg,scaling,ps}` over HTTP. If headless browser (Playwright/Chrome) is present, verify live rendered page + `uchrom_browser.connect()` `open_view` + `describe_workspace` + `capture(format="svg")`.
- [ ] **Step 3: Independent Codex `gpt-6.2-sol` whole-branch code review**
  - Run `codex exec -m gpt-6.2-sol -c 'model_reasoning_effort="high"' --sandbox read-only -C /Users/bakezq/Coding/U-Chrom/.worktrees/stats-and-skills-v2 -` on `git diff origin/main...HEAD`.
  - Fix any valid findings, rebuild `static/` if needed, re-run full suites (`packages/chromdata`, `packages/uchrom-browser`, `packages/uchrom/tests/skills`, frontend `vitest run` + `npm run build`, `git diff --check`).
