# Figure 6 — analysis in code, visualization in the browser, for researchers and agents — plan

Paper plan: Fig 6 answers "how do people, and agents, actually use it?". The browser exists (PR #60). Skills,
WebMCP and the browser's Python client do not exist yet; this plan designs them.

Draft: `fig6.pdf` / `fig6.png`, built by `make_fig6.py`. b and the views in d draw real data (Takei 2025 FOV 0,
`extract_data.py`); c reads `results/*.json` from `benchmarks/fig6/`. Parts that are not real results yet sit in a
red dashed PLACEHOLDER frame with the reason (c: measured on a loaded machine; d: agent session illustrative;
e: skills benchmark numbers).

> **Fig 1 follow-up.** Fig 1c and its legend say "a Model Context Protocol (MCP) server with agent skills". With
> this design that becomes "agent skills and WebMCP". Change Fig 1 and `captions/fig1.tex` when Fig 6 is final.

## Message

**Analysis happens in code; visualization happens in the browser; researchers and agents use both.**

- **Analysis = the `uchrom` Python API.** Researchers write notebooks. Coding agents (Claude Code, Codex,
  `uchrom_discovery`) write the same code, guided by **skills**: recipes with the right calls, the checks an
  answer must pass, and how to report it. The script is the record of the analysis.
- **Visualization = the browser.** Researchers use the GUI (linked views, lasso). Agents in the browser use
  **WebMCP** tools that the browser registers itself. Coding agents drive the same actions from Python
  (`uchrom.browser.connect()`).

Both sides share one workspace (groups, views, locus), so work passes between researcher and agent: a lasso
becomes a named group in Python, and a view opened from code appears in the researcher's browser.

No MCP server. For agents that can run code, the Python API plus skills is more flexible and reproducible than a
parallel tool surface, and it leaves nothing to keep in sync. Agents that cannot run code still get the browser
(WebMCP). If chat-only clients need `uchrom` analysis later, a thin MCP wrapper can be added without changing
anything here.

## Panels → evidence needed

| Panel | Claim | Content | Needs |
|---|---|---|---|
| a | Two interfaces, each for researchers and agents | data → **`uchrom` Python API** ⇄ shared workspace ⇄ **browser** (GUI; WebMCP). Researcher → GUI and notebooks. One **agent** (with skills) → writes `uchrom` code, and drives the browser through WebMCP or `uchrom.browser.connect()`. The figure does not split agents by kind; which entry an agent uses depends only on whether it runs code or runs in the browser | Server-side workspace; browser action layer; Python client; WebMCP |
| b | Linked exploration in the browser | Annotated screenshot (Takei 2025, Paper theme): lasso Purkinje cells in the RNA UMAP (1) → 3-D nuclei (2) → Genome view with IF tracks and group-vs-group distance maps (3) → Rg by cell type (4) | Scripted capture; all-FOV Takei 2025 |
| c | Interactive at real scale | c1 time to first frame vs n_spots; c2 latency per interaction vs 100 ms | `benchmarks/fig6/` |
| d | Researcher and agent hand work to each other | The researcher lassoes cells and asks a coding agent "what is different about these cells? show me". Skill `compare-groups` → the script the agent wrote (`connect` → `get_selection` → `uchrom` analysis → `open_view`) → answer with n, test and caveat → the Genome and Stats panes it opened, in the researcher's browser | Skill, Python client, workspace; real run, trimmed and marked `…` |
| e | Skills make agents reliable | e1 anatomy of a skill; e2 task success on a benchmark with ground truth: API docs only vs + skills, by task category | Benchmark tasks + harness |

The WebMCP route is shown in a and in the supplement / demo video (an agent in the browser answering from
`get_view_data` and arranging views). It is not benchmarked, because browser support is still experimental.

Moved out of Fig 6: scHiCAR pseudo-bulk from a lasso (→ Fig 5 or supplement); feature table vs HiGlass,
Juicebox, Nucleome Browser, Vitessce, 3DGB (supplement); demo video (Additional file).

## Design sketch (to be implemented)

### Division of labour

| | Analysis | Visualization |
|---|---|---|
| Lives in | `uchrom` Python API | the browser, as one action layer (`frontend/src/actions.ts`) |
| Researcher | notebooks / scripts | GUI |
| Coding agent | writes Python, guided by skills | `uchrom.browser.connect()` → the same actions over REST/SSE |
| Agent in the browser | — (asks the browser: `get_view_data`) | WebMCP tools registered by the page |

Rules:
- Analysis is implemented **once**, in `uchrom`. The browser never computes; it asks the server (REST).
- Visualization actions are implemented **once**, in the browser's action layer. The GUI, WebMCP and the Python
  client all call it. One schema file (`uchrom/browser/web/ui_tools.json`) defines the actions for WebMCP and for
  the Python client, so names and arguments are identical.
- The workspace (panes, locus, focus, groups, action log) is held by the server and pushed to the browser (SSE).
  A lasso is a named group everywhere; a view opened from any client appears in every open browser.
- Domain know-how lives in skills, not in docstrings or tool descriptions.

### Browser actions (shared by GUI, WebMCP and the Python client)

| Kind | Actions |
|---|---|
| Change the view | `open_view` (type, locus, rows, cells scope), `close_view`, `arrange` (tabs / columns / grid), `set_locus`, `focus` (cell / group / none), `color_by` |
| Selections | `get_selection`, `select_cells`, `save_group`, `list_groups` |
| Read | `get_view_data` (the numbers behind a pane: matrix, track, Rg values, embedding), `describe_dataset` |
| Output | `capture_view` → PNG |

WebMCP: registered with `document.modelContext.registerTool`, feature-detected. WebMCP is a W3C Community
Group draft (Sept 2026; Microsoft and Google editors); Chrome has it behind a flag from 146 and in an origin
trial. It is labelled experimental in the paper.

Python client:

```python
ws = uchrom.browser.connect()             # the running browser server
cells = ws.get_selection()                # the researcher's lasso → cell ids
cd = ws.dataset()                          # the ChromData the browser has loaded
...                                        # any uchrom analysis
ws.open_view("Genome", locus="chr15:40-60Mb", rows=[...], cells=ws.save_group(cells, "lasso 1"))
```

### Skills

`skills/<name>/SKILL.md` (+ `scripts/`, `reference/`), Agent Skills format, shipped as a Claude Code plugin and
usable by Codex. Each skill gives the `uchrom` calls, a script template, the checks, and how to report.

| Skill | Recipe | Checks it enforces |
|---|---|---|
| `load-data` | FOF-CT / seqFISH+ / .scool / .pairs → .chromdata.zarr, QC summary | ploidy, spots per trace, missing loci |
| `call-structures` | TADs, loops, compartments with the right caller per modality | resolution vs bin size, min traces |
| `compare-groups` | a statistic between cell groups, with test and effect size | ≥ n cells per group, report n and test, open the view |
| `associate-modalities` | feature ↔ structure at the spot, cell or cell-type level (Fig 1b) | level stated, confounders (nuclear size) |
| `reconstruct` | scHi-C → 3-D (nucdyn / GEM / MDS) | restraint violations, replicate RMSD |
| `show-in-browser` | turn a result into views for the researcher (Python client) | the view shows what the answer claims |

`uchrom_discovery` can load the same skills, and it respects the dependency rule because skills only use the
public API.

## Agent benchmark (panel e2)

- 30–50 questions over real datasets (Takei 2025, Takei 2021 mESC, scHiCAR MOp, sim_cell1), in 4 categories:
  data inspection, structure calling, group comparison, cross-modal association.
- Ground truth comes from a scripted `uchrom` analysis stored with each question. Numeric answers are graded with a
  tolerance, and statements are graded by rubric.
- Conditions: API docs only vs API docs + skills; Claude Code and Codex (≥ 2 models); 3 runs each. Report
  success, tokens, wall time, and the failure modes (e.g. an unchecked n = 3 comparison, the wrong caller or
  resolution).
- Questions are written before the skills are tuned. A held-out half is not seen while writing skills.

## Engineering order

1. Server-side workspace state + SSE; workspace JSON load/save (also gives reproducible captures).
2. Browser action layer (the GUI calls it) + `ui_tools.json`.
3. Python client `uchrom.browser.connect()` over the same actions.
4. WebMCP registration of the actions, feature-detected; tested in Chrome with the flag.
5. Skills, starting with `compare-groups`, `show-in-browser` and `load-data`.
6. `paper/fig6/capture.py` (Playwright, Paper theme, 300 dpi) and the Takei 2025 all-FOV .chromdata.zarr (shared with Fig 5).
7. Benchmarks: browser performance and the agent benchmark → `paper/fig6/results/*.json`.
8. Demo video recorded with the same script, including the WebMCP route.

## Honesty rules

- Real interface, real transcripts and scripts: crop and trim only, and mark trimmed parts with `…`.
- Report agent failures and above-100-ms latencies, not only successes.
- Say which tool, model and browser versions were used; agent results are dated. WebMCP is labelled experimental.
- Every dataset goes into `example-data/README.md` in the same PR that first uses it.
