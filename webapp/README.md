# U-Chrom Analysis Workbench

A **conversation-driven** web application for chromatin 3D structure analysis.
Load your own `ChromData` (`.h5cd`), then **talk to an AI agent** that drives the
UI directly: it generates visualizations, runs structure analysis, executes
notebook code, and wires the panels together — you steer with natural language.

> **Scope.** This is an *analysis workbench*, not a data portal. Non-goals:
> dataset publishing/search/download, multi-user collaboration, accounts, and
> native IGV/HiGlass panels. Those are out of scope for this app.

## The core idea: A2UI (Agent-to-UI)

The agent is not just a chatbot — it emits **declarative artifacts** that the
frontend renders. You say *"show the chr21 contact matrix as a heatmap"*; the
agent calls `render_gosling` with a **Gosling.js JSON spec** and the Genomic tab
renders it. You say *"make it a bar chart"*; the agent sends a `patch_gosling`
JSON-patch and the view updates in place. Gosling's declarative JSON maps
cleanly onto an LLM's structured output, which is what makes "conversation as
visualization" practical.

## Architecture

A single React SPA talks to a single FastAPI backend over one WebSocket
(`/ws/main`) plus a handful of REST endpoints. All visualizations read from one
in-memory `ChromData` (REST) and an on-demand IPython kernel (Notebook).

### Frontend component tree

```
App
├── TopBar                      Open File (file browser → WS load_data) + dataset name
├── TwoColumnLayout
│   ├── ChatPanel               /ws/main: streaming dialog + artifact cards
│   └── TabContainer
│       ├── GenomicPanel        └─ GoslingRenderer (spec-driven) [+ ErrorBoundary]
│       ├── EmbeddingPanel      deck.gl UMAP scatter
│       ├── Structure3DPanel    Three.js 3D traces
│       ├── NotebookPanel       code cells + outputs
│       └── (custom)            ComponentRenderer — agent-composed Tier-2 UI
└── GenomicNavBar               chrom:start-end (two-way viewport sync)
```

State lives in a single **Zustand** store (`store.ts`); `artifactHandlers.ts`
routes each incoming `agent_artifact` into the right store slice.

### Backend (single FastAPI entry: `main.py`)

```
webapp/backend/
├── main.py            FastAPI app: router registration + /ws/main + upload/download
├── ws_handler.py      handle_message() dispatcher + run_agent_loop()
│                      └─ Anthropic STREAMING + tool dispatch via TOOL_EXECUTORS
├── agent_tools.py     TOOLS schemas + SYSTEM_PROMPT
├── tool_executors.py  @register(name) executors: artifact emit + tool_result string
├── session.py         Session (ChromData + views + kernel handle)
├── data_api.py        /api/umap /api/coords/batch /api/track /api/browse
├── tileset_api.py     HiGlass-compatible tileset (Gosling matrix tiles)
├── track_wig.py       /api/track_wig/<name> (Gosling signal-track CSV)
├── strc_api.py        /api/tads /api/loops /api/compartments + run_registered_analysis
├── dynamic_api.py     /api/custom/<id>/<chrom> — agent-authored analysis endpoints
├── dynamic_analysis.py AST-sandboxed compile/run for write_analysis_function
├── notebook_api.py    jupyter_client kernel management + execute_code
└── figure_render.py   SVG export
```

### Key design principles

**Single data source.** Every panel reads the session's in-memory
`session.chromdata` over REST — there is no demo/sample data path. Load a file,
or the panels stay empty.

**A2UI artifact channel.** The agent's UI effects travel as `agent_artifact`
messages. `artifactHandlers.ts` (`ARTIFACT_HANDLERS`) maps each `artifact_type`
to a store mutation: `gosling_spec`, `gosling_patch`, `select_cells`,
`color_embedding`, `show_structure`, `color_structure`, `export_view`,
`analysis_result`, `custom_analysis_deployed`, `notebook_cell`, `component_tree`.

**Streaming agent loop.** `run_agent_loop` opens
`client.messages.stream(...)`, forwards text deltas as `agent_message_delta`,
then on a `tool_use` turn dispatches each call through `TOOL_EXECUTORS`, feeds
the `tool_result` back, and repeats up to `MAX_TOOL_ITERATIONS` (10). The loop
itself is tool-agnostic — adding a tool never touches it.

**Backend-authoritative view state.** The backend holds the source of truth for
rendered views (`session.views`). The agent can read it (`get_view_state`) or
block on the next user interaction (`query_user_interaction`); the frontend
reports brushes/clicks as `ui_event`, and reconnecting clients pull a
`view.snapshot`.

**Cross-tab linkage.** Zustand is the hub: `viewport` syncs GenomicNavBar ↔
Gosling ↔ 3D highlight; `cellSelection`/`highlightedCells` link Embedding ↔ 3D.

**Notebook isolation.** The IPython kernel is a separate process seeded with
`cd = ChromData.read(<path>)`; editing `cd` in the notebook does not perturb the
REST-backed visualization panels.

## Setup

### Backend

```bash
pip install -e .                 # installs uchrom (from repo root)
pip install fastapi "uvicorn[standard]" jupyter_client anthropic
export ANTHROPIC_API_KEY=sk-...  # required for the agent
uvicorn webapp.backend.main:app --reload --host 0.0.0.0 --port 8080
```

### Frontend

```bash
cd webapp/frontend
npm install
npm run dev        # Vite dev server on http://localhost:3000
```

The Vite dev server proxies `/api` → `http://localhost:8080` and `/ws` →
`ws://localhost:8080`, so the browser connects to the backend through
`ws://localhost:3000/ws/main` in development.

### Production build

```bash
cd webapp/frontend
npm run build      # tsc + vite build → dist/
```

Serve `dist/` via FastAPI static files or nginx and point `/api` + `/ws` at the
backend.

## Usage

1. **Open a file.** Click **Open File** → browse to a `.h5cd` (or `.csv` /
   FOF-CT core table). The browser lists directories and data files from the
   backend (`/api/browse`); pick a file to load it via the WebSocket.
2. **Explore the tabs.** UMAP (deck.gl, click to highlight cells), 3D structure
   (Three.js, drag/scroll), Genomic (Gosling spec), Notebook (executed cells).
3. **Talk to the agent.** Examples:

   ```
   "Show the chr21 contact matrix as a heatmap"
     → render_gosling (matrix spec) → Genomic tab renders it

   "Color the embedding by cell_type"
     → color_embedding → Embedding tab recolors + focuses

   "Find TADs on chr21, then draw them"
     → run_analysis(type="tad", region="chr21") → returns a render handle;
       agent chains render_gosling(data_url=/api/tads/chr21?format=gosling)

   "Add a cell that computes radius of gyration for cell c5"
     → add_notebook_cell(code=..., run=true) → Notebook tab shows code + output

   "Export the current view as PDF"
     → export_view(format="pdf")

   "Write an analysis that bins contact frequency and plot it"
     → write_analysis_function(...) → sandboxed, deployed at /api/custom/<id>/<chrom>,
       then render_gosling against it
   ```

## Agent tools

The agent (Claude via the Anthropic API) has 13 tools. Most emit an
`agent_artifact` the frontend renders; `get_view_state` and
`query_user_interaction` return data to the *agent* (no UI artifact).

| Tool | Purpose | Artifact type → tab |
|------|---------|---------------------|
| `render_gosling` | Generate a Gosling genomic spec | `gosling_spec` → Genomic |
| `patch_gosling` | JSON-patch an existing spec | `gosling_patch` → Genomic |
| `color_embedding` | Recolor UMAP by marker/metadata | `color_embedding` → Embedding |
| `select_cells` | Highlight a cell subset | `select_cells` → Embedding |
| `show_structure` | Show 3D structure for a cell/chrom | `show_structure` → 3D |
| `color_structure` | Recolor 3D by compartment/TAD/marker | `color_structure` → 3D |
| `add_notebook_cell` | Insert + run a Python cell | `notebook_cell` → Notebook |
| `run_analysis` | TAD/loop/compartment detection (registry) | `analysis_result` → Genomic |
| `write_analysis_function` | Compile + deploy a sandboxed analysis | `custom_analysis_deployed` |
| `export_view` | Export current view (PNG/PDF) | `export_view` |
| `render_component` | Compose a Tier-2 UI from whitelisted parts | `component_tree` → custom |
| `get_view_state` | Read backend-authoritative view state | *(to agent)* |
| `query_user_interaction` | Poll/block on the next user interaction | *(to agent)* |

**Analysis → render handoff.** `run_analysis` and `write_analysis_function`
return a *render handle* in their `tool_result`: `data_url`,
`chromosome_field`, `genomic_fields`, and a `suggested_mark`. The agent uses
these to chain straight into `render_gosling` without guessing field names.

**Gosling data sources.** Signal tracks:
`{"type":"csv","url":"/api/track_wig/<name>"}`. Contact matrix:
`{"type":"matrix","url":"/api/v1/tileset_info/?d=contact-<chrom>"}` (HiGlass
tileset format feeds Gosling's matrix mark).

## Testing

```bash
# from the repo root, using the project's Python 3.11 env
python -m pytest tests/ -q

# focused: the agent-loop pathway
python -m pytest tests/test_agent_linkage_tools.py \
                 tests/backend/test_ws_handler.py \
                 tests/integration/test_e2e_workflow.py -q

# REST + analysis endpoints
python -m pytest tests/test_strc_api.py tests/test_tileset_api.py \
                 tests/test_track_wig.py tests/test_data_api.py -q
```

Agent-loop tests are **link-level**: each drives the full `run_agent_loop` and
asserts on the artifacts / tool_results it produces, mocking only the Anthropic
boundary via the shared harness `tests/_agent_loop_harness.py` (which fakes the
`client.messages.stream(...)` async context manager). `tests/conftest.py` puts
the repo root on `sys.path` so `webapp.backend.*` and `tests.*` resolve from any
subdirectory.

`tests/test_e2e_real_claude.py` exercises the real API and needs
`ANTHROPIC_API_KEY`; run it manually / in CI, not in the default suite.

Frontend: Vitest + React Testing Library for store routing
(`artifactHandlers` → store slices) and `GoslingRenderer` + `ErrorBoundary`
(invalid spec degrades to an inline message instead of crashing the app).

## Development

### Project layout

```
webapp/
├── backend/   (see Architecture above)
└── frontend/
    └── src/
        ├── App.tsx                 root
        ├── store.ts                Zustand state (viewport, cellSelection, ...)
        ├── ws.ts                   WebSocket client (send/onMessage)
        ├── artifactHandlers.ts     ARTIFACT_HANDLERS registry
        ├── components/
        │   ├── TopBar.tsx          Open File browser
        │   ├── ChatPanel.tsx       agent dialog
        │   ├── TabContainer.tsx    tab switcher
        │   ├── GenomicPanel.tsx    Gosling host (+ ErrorBoundary)
        │   ├── GoslingRenderer.tsx Gosling embed + viewport sync + export
        │   ├── EmbeddingPanel.tsx  deck.gl UMAP
        │   ├── Structure3DPanel.tsx Three.js 3D
        │   ├── NotebookPanel.tsx   code cells + outputs
        │   ├── ComponentRenderer.tsx Tier-2 generative UI
        │   ├── ErrorBoundary.tsx   render-error fallback
        │   └── GenomicNavBar.tsx   region nav
        └── specs/                  built-in Gosling specs
```

### Adding a tab

1. Add the tab id to the store's `activeTab` union and render it in
   `TabContainer.tsx`.
2. Build the panel component; subscribe to the store slices it needs.

### Adding an agent tool

The loop stays tool-agnostic — you touch four places:

1. **Schema** — add the tool to `TOOLS` in `agent_tools.py`.
2. **Executor** — `@register("your_tool")` an async `(websocket, tool_input)`
   in `tool_executors.py`; emit an `agent_artifact` (if it has a UI effect) and
   return a `tool_result` content string for the agent.
3. **Frontend** — add a handler under the matching `artifact_type` in
   `ARTIFACT_HANDLERS` (`artifactHandlers.ts`).
4. **Prompt** — document the tool in `SYSTEM_PROMPT` so the agent knows when to
   use it.

## FAQ

**WebSocket connection fails?** Confirm the backend is running on port 8080. In
dev the browser connects via the Vite proxy (`ws://localhost:3000/ws/main` →
`ws://localhost:8080`).

**Genomic tab is blank?** With no file loaded the contact-map view stays empty
by design (no demo data). Load a `.h5cd`, or pick the "Remote Demo" view.

**Red Gosling warnings in the console?** Gosling is pinned to **`gosling.js@1.0.7`**
(downgraded from the `2.0.0-alpha` line, which rendered unreliably). After data
loads you may still see ~4 React lifecycle deprecation messages (`findDOMNode`,
`legacy childContextTypes` / `contextTypes`, `componentWillReceiveProps`). These
come from HiGlass-era dependencies *inside* `node_modules/gosling.js`, not from
this app's code or specs; React prints lifecycle deprecations via `console.error`
so they show up red, but they are warnings and cannot be removed without forking
Gosling. An invalid agent-generated spec is a separate case — that is caught by
the `ErrorBoundary` around `GoslingRenderer` and degrades to an inline message.
See `context/gosling-spec-reference.md` for the spec rules this app targets.

**How do I load my own data?** Convert to `.h5cd`:

```python
from uchrom.core.cdata import ChromData
cd = ChromData.from_dataframe(your_df)   # df needs chrom, start, end, x, y, z
cd.write('your_data.h5cd')
```

**Kernel execution timeout?** Notebook cells time out at 30s
(`notebook_api.execute_code(code, timeout=...)`); raise it for long runs.

## Acknowledgements

- [Gosling.js](https://gosling-lang.org/) — declarative genomic visualization
- [Three.js](https://threejs.org/) — 3D rendering
- [deck.gl](https://deck.gl/) — UMAP scatter
- [Jupyter](https://jupyter.org/) (`jupyter_client`) — notebook kernel
- [Anthropic Claude](https://www.anthropic.com/) — the agent

The contact matrix uses the HiGlass tileset wire format to feed Gosling's matrix
mark; no HiGlass UI component is used.

## License

Same as the U-Chrom main repository.
