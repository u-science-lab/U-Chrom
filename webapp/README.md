# U-Chrom Analysis Workbench

Interactive web application for chromatin 3D structure data analysis with AI-powered assistance.

## Features

- **Data Loading**: Upload and load .h5cd chromatin data files
- **Interactive Visualization**: 
  - UMAP embeddings with cell highlighting
  - 3D chromatin structure viewer (Three.js)
  - Contact matrices (HiGlass integration)
  - Genomic tracks (IGV.js integration)
  - Synchronized cross-panel selection via 1D-3D event bus
- **AI Agent Integration**:
  - Natural language data analysis queries
  - Automatic Gosling.js visualization generation
  - Real-time spec patching for iterative refinement
  - Multi-tab control (Genomic/Embedding/3D Structure/Notebook)
- **Notebook Interface**: 
  - Jupyter kernel backend for reproducible analysis
  - Track analysis history with code cells and outputs
  - Agent-generated code cells with immediate execution

## Architecture

```
Frontend (React + TypeScript)
  ├── EmbeddingPanel (deck.gl UMAP)
  ├── StructureViewer (Three.js 3D)
  ├── HiGlassPanel (contact matrices)
  ├── IGVPanel (genomic tracks)
  ├── NotebookPanel (code cells)
  └── ChatPanel (agent interaction)
      ↓ WebSocket
Backend (FastAPI + Python)
  ├── /ws/main (WebSocket for agent)
  ├── /api/data/* (ChromData queries)
  ├── /api/v1/tileset_info, /api/v1/tiles (HiGlass)
  ├── /api/track_wig/<name> (IGV.js tracks)
  ├── /api/strc/* (TAD/loop/compartment)
  └── notebook_api (Jupyter kernel)
      └── jupyter_client (code execution)
```

### Key Design Principles

**1D-3D Event Bus**: Global state synchronization across panels via Zustand:
- `viewport` (chrom, start, end) → HiGlass zooms, IGV jumps, 3D highlights bins
- `cellSelection` (ids, label) → UMAP highlights, 3D switches cells, contact matrix recomputes

**A2UI Protocol**: Agent → UI communication via declarative artifacts:
- `render_gosling`: Full Gosling spec generation
- `patch_gosling`: Incremental JSON-patch updates
- `add_notebook_cell`: Code cell insertion with optional execution
- `run_analysis`: TAD/loop/compartment detection

**Jupyter Backend**: Persistent kernel for reproducible analysis:
- `notebook_api.start_kernel()`: Launches IPython kernel
- `notebook_api.execute_code(code, timeout)`: Executes code, returns {status, output, error}
- Agent can inject analysis code via `add_notebook_cell` tool

## Setup

### Backend

```bash
cd webapp/backend
pip install -r requirements.txt
uvicorn webapp.backend.main:app --reload --host 0.0.0.0 --port 8000
```

**Dependencies**:
- `fastapi`, `uvicorn[standard]`
- `uchrom` (install from project root: `pip install -e .`)
- `jupyter_client` (for notebook kernel)
- `anthropic` (for Claude API)

### Frontend

```bash
cd webapp/frontend
npm install
npm run dev
```

Frontend runs on `http://localhost:5173`, connects to `ws://localhost:8000/ws/main`.

### Production Build

```bash
cd webapp/frontend
npm run build  # outputs to dist/
```

Serve `dist/` via FastAPI static files or nginx.

## Usage

### 1. Load Data

Click **Load Data** → select `.h5cd` file (U-Chrom native HDF5 format).

Supported formats:
- `.h5cd` — ChromData with full metadata (recommended)
- `.csv` — flat structure table (requires `chrom, start, end, x, y, z`)
- FOF-CT core table — 4DN FISH Omics Format

### 2. Explore Visualizations

- **UMAP Embedding**: Lasso-select cells → updates `cellSelection` → 3D/contact matrix sync
- **3D Structure**: Rotate (drag), zoom (scroll), pan (right-drag)
- **Contact Matrix**: HiGlass multi-resolution tiling, scroll to zoom
- **Genomic Tracks**: IGV.js for epigenomic signals (ATAC, ChIP, etc.)

### 3. Chat with Agent

Example queries:

```
User: Show contact matrix for chr21
Agent: [calls render_gosling with HiGlass spec]
       → Genomic tab displays chr21 contact heatmap

User: Highlight cells with high Sox2 expression
Agent: [calls color_embedding with color_by="Sox2"]
       → Embedding tab recolors UMAP by Sox2 levels

User: Calculate TADs for chr21
Agent: [calls run_analysis(type="tad", region="chr21")]
       → Results stored, can be overlaid on contact matrix

User: Add a code cell to compute distance variance
Agent: [calls add_notebook_cell with Python code, run=true]
       → Notebook tab shows code + execution output
```

### 4. Review Analysis History

**Notebook Panel** tracks all executed code:
- Agent-generated cells (from `add_notebook_cell`)
- Manual cells (user edits and re-runs)
- Outputs: text, plots (matplotlib → base64 PNG), errors

## Agent Tools

The AI agent (Claude via Anthropic API) has access to:

| Tool | Purpose | Target Tab |
|------|---------|------------|
| `render_gosling` | Generate Gosling.js genomic visualization | Genomic |
| `patch_gosling` | Apply JSON-Patch to existing spec | Genomic |
| `color_embedding` | Color UMAP by marker/metadata | Embedding |
| `select_cells` | Highlight cell subset by criteria | Embedding + 3D |
| `show_structure` | Display 3D structure for cell/chrom | 3D Structure |
| `color_structure` | Color 3D by marker/compartment/TAD | 3D Structure |
| `add_notebook_cell` | Insert executable Python code cell | Notebook |
| `run_analysis` | Run TAD/loop/compartment detection | Backend |

**Gosling Spec Requirements**:
- Set `assembly` (hg19/hg38/mm10), `width`, `height`
- Signal tracks: `{"type":"csv","url":"/api/track_wig/<name>"}`
- Contact matrix: `{"type":"matrix","url":"/api/v1/tileset_info/?d=contact-<chrom>"}`
- Use `mark` types: bar/line/point/rect/area/text/link/triangle

## Testing

```bash
# Backend unit tests
pytest tests/test_tileset_api.py -v   # HiGlass tileset endpoints
pytest tests/test_track_wig.py -v     # IGV.js WIG format
pytest tests/test_bins_api.py -v      # bins metadata API

# Integration tests
pytest tests/integration/ -v
```

## Development

### Project Structure

```
webapp/
├── backend/
│   ├── main.py              # FastAPI app, route registration
│   ├── session.py           # Session class (manages ChromData)
│   ├── ws_handler.py        # WebSocket message handler (A2UI protocol)
│   ├── agent_tools.py       # Tool definitions + system prompt
│   ├── notebook_api.py      # Jupyter kernel management
│   ├── data_api.py          # REST API for ChromData queries
│   ├── tileset_api.py       # HiGlass tileset endpoints
│   ├── track_wig.py         # IGV.js WIG format tracks
│   └── strc_api.py          # Structure analysis (TAD/loop/comp)
├── frontend/
│   ├── src/
│   │   ├── App.tsx          # Root component
│   │   ├── store.ts         # Zustand state (viewport, cellSelection)
│   │   ├── components/
│   │   │   ├── MainCanvas.tsx       # Panel container
│   │   │   ├── HiGlassPanel.tsx     # HiGlass wrapper
│   │   │   ├── IGVPanel.tsx         # IGV.js wrapper
│   │   │   ├── StructureViewer.tsx  # Three.js 3D renderer
│   │   │   ├── CellEmbedding.tsx    # UMAP/t-SNE (deck.gl)
│   │   │   ├── NotebookPanel.tsx    # Code cells + outputs
│   │   │   └── AgentPanel.tsx       # Chat interface
│   │   └── utils/
│   │       └── ws.ts        # WebSocket client
│   ├── package.json
│   └── vite.config.ts
└── README.md               # This file
```

### Adding a New Panel Type

1. **Define panel type** in `frontend/src/store.ts`:
   ```typescript
   type PanelType = 'higlass' | 'igv' | 'structure_3d' | 'your_panel';
   ```

2. **Create React component** in `frontend/src/components/YourPanel.tsx`:
   ```typescript
   export function YourPanel({ config }: { config: YourConfig }) {
     const { viewport, setViewport } = useStore();
     // Subscribe to viewport, render logic...
   }
   ```

3. **Register in MainCanvas** (`frontend/src/components/MainCanvas.tsx`):
   ```typescript
   case 'your_panel':
     return <YourPanel config={panel.config} />;
   ```

4. **Add backend API** (if needed) in `backend/data_api.py`.

### Adding an Agent Tool

1. **Define tool schema** in `backend/agent_tools.py`:
   ```python
   {
       "name": "your_tool",
       "description": "What it does and when to use it",
       "input_schema": {
           "type": "object",
           "properties": {"param": {"type": "string"}},
           "required": ["param"],
       },
   }
   ```

2. **Implement executor** in `backend/ws_handler.py`:
   ```python
   async def handle_your_tool(session: Session, params: dict):
       result = session.cd.your_operation(**params)
       return {"artifact_id": "res123", "data": result}
   ```

3. **Update system prompt** in `SYSTEM_PROMPT` to document the tool.

## FAQ

**Q: WebSocket connection fails?**  
A: Check backend is running on port 8000. Browser console shows `WebSocket connection to 'ws://localhost:8000/ws/main' failed` if backend is down.

**Q: HiGlass panel is blank?**  
A: Verify `/api/v1/tileset_info?d=contact-chr1` returns valid JSON with `datatype: "matrix"` and `bins_per_dimension: 256`.

**Q: How to load my own data?**  
A: Convert to `.h5cd` format:
```python
from uchrom.core.cdata import ChromData
cd = ChromData.from_dataframe(your_df)  # df needs chrom, start, end, x, y, z
cd.write('your_data.h5cd')
```

**Q: Kernel execution timeout?**  
A: Default timeout is 30s. For long computations, increase in `notebook_api.execute_code(code, timeout=60)`.

**Q: How to enable CORS for external frontend?**  
A: Add CORS middleware in `main.py`:
```python
from fastapi.middleware.cors import CORSMiddleware
app.add_middleware(CORSMiddleware, allow_origins=["*"])
```

## Roadmap

- [x] Phase 0: HiGlass + IGV.js integration, 1D-3D event bus
- [x] Phase P6: AI Agent + Jupyter kernel + Notebook UI
- [ ] Phase P7: Figure Composer integration
- [ ] Phase P8: Multi-user collaboration (real-time sync)

## License

Same as U-Chrom main repository (to be specified).

## Acknowledgements

- [HiGlass](http://higlass.io/) (Harvard Medical School)
- [IGV.js](https://github.com/igvteam/igv.js) (Broad Institute)
- [Gosling.js](https://gosling-lang.org/) (Harvard Medical School)
- [Three.js](https://threejs.org/)
- [Anthropic Claude](https://www.anthropic.com/) (AI agent)
