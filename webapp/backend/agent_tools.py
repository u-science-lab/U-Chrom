"""Agent tool definitions and system prompt for the A2UI loop.

render_gosling / patch_gosling are fully implemented in ws_handler.
The other 6 tools are defined here (schema + artifact protocol) but their
executors are placeholders in P2 — filled in P3 (notebook) and P4 (rest).
"""

TOOLS = [
    {
        "name": "render_gosling",
        "description": """Generate and render a Gosling genomic visualization spec. Use for genome browser tracks, contact matrices, and other genomic visualizations. The spec renders in the Genomic tab.

GOSLING SCHEMA REFERENCE:

1. MARK TYPES (track.mark):
   - 'rect': heatmaps, contact matrices
   - 'bar': signal tracks, compartments
   - 'rule': boundaries, lines
   - 'link': arcs for loops, interactions
   - 'text': labels, annotations
   - 'area': filled regions
   - 'line': line plots
   - 'point': scatter plots

2. DATA FORMATS (track.data.type):
   - 'json': inline array or URL, fields: {chromosome, genomicFields:[start,end], ...}
   - 'csv': URL with chromosomeField and genomicFields
   - 'matrix': HiGlass tileset for Hi-C (url: '/api/v1/tileset_info/?d=...')
   - 'beddb': BED-like genomic intervals

3. ENCODING CHANNELS (track.<channel>):
   - x, xe: genomic position (start, end)
   - y, ye: quantitative values or genomic positions (contact maps)
   - color: categorical or quantitative mapping
   - stroke, strokeWidth: outline styling
   - opacity: transparency
   - size: point/text size

4. GENOMIC FIELDS (for json/csv data):
   - chromosomeField: field name for chromosome (e.g., 'chrom')
   - genomicFields: array of position fields (e.g., ['start','end'])
   Example: {"type":"csv","url":"...","chromosomeField":"chrom","genomicFields":["start","end"]}

5. TRACK ALIGNMENT:
   - alignment: 'overlay' (superimpose tracks)
   - alignment: 'stack' (vertical stacking)

6. COMMON PATTERNS:

   Contact map heatmap:
   {
     "data": {"type":"matrix","url":"/api/v1/tileset_info/?d=contact-chr1"},
     "mark": "rect",
     "x": {"field":"start1","type":"genomic"},
     "xe": {"field":"end1","type":"genomic"},
     "y": {"field":"start2","type":"genomic"},
     "ye": {"field":"end2","type":"genomic"},
     "color": {"field":"value","type":"quantitative"}
   }

   TAD boundaries (vertical rules):
   {
     "data": {"type":"json","values":[{"chrom":"chr1","pos":1000000},...],"chromosomeField":"chrom","genomicFields":["pos"]},
     "mark": "rule",
     "x": {"field":"pos","type":"genomic"},
     "strokeWidth": {"value":2},
     "color": {"value":"red"}
   }

   Loops (arcs):
   {
     "data": {"type":"json","values":[{"chrom":"chr1","start1":1000000,"end1":1020000,"start2":2000000,"end2":2020000},...],"chromosomeField":"chrom","genomicFields":["start1","end1","start2","end2"]},
     "mark": "link",
     "x": {"field":"start1","type":"genomic"},
     "xe": {"field":"end1","type":"genomic"},
     "x1": {"field":"start2","type":"genomic"},
     "x1e": {"field":"end2","type":"genomic"},
     "stroke": {"value":"blue"},
     "strokeWidth": {"value":1}
   }

   Compartments (bars):
   {
     "data": {"type":"json","values":[{"chrom":"chr1","start":0,"end":1000000,"compartment":"A"},...],"chromosomeField":"chrom","genomicFields":["start","end"]},
     "mark": "bar",
     "x": {"field":"start","type":"genomic"},
     "xe": {"field":"end","type":"genomic"},
     "color": {"field":"compartment","type":"nominal","domain":["A","B"],"range":["red","blue"]}
   }

   Signal track (ChIP-seq, ATAC-seq):
   {
     "data": {"type":"csv","url":"/api/track_csv/H3K27ac","chromosomeField":"chrom","genomicFields":["start","end"]},
     "mark": "bar",
     "x": {"field":"start","type":"genomic"},
     "xe": {"field":"end","type":"genomic"},
     "y": {"field":"value","type":"quantitative"}
   }

REQUIRED TOP-LEVEL FIELDS:
- assembly: 'hg19', 'hg38', 'mm10', etc.
- tracks: array of track objects
- width: visualization width
- height: visualization height

DO NOT HALLUCINATE:
- Field names must match actual data (e.g., don't use 'position' if data has 'start')
- Encoding channels are fixed: x/xe/y/ye/color/stroke/strokeWidth/opacity/size
- Mark types are fixed: rect/bar/rule/link/text/area/line/point
- Always specify chromosomeField and genomicFields for json/csv data""",
        "input_schema": {
            "type": "object",
            "properties": {
                "spec": {"type": "object", "description": "A valid Gosling.js spec object with 'tracks' array."},
                "title": {"type": "string", "description": "Optional title for the visualization"},
            },
            "required": ["spec"],
        },
    },
    {
        "name": "patch_gosling",
        "description": "Apply an incremental JSON-Patch-style change to the currently active Gosling spec (e.g. change a mark, color, or domain). Use when the user wants to tweak an existing visualization rather than recreate it.",
        "input_schema": {
            "type": "object",
            "properties": {
                "target_id": {"type": "string", "description": "artifact_id of the spec to patch"},
                "patch": {
                    "type": "object",
                    "description": "JSON Patch op: {op:'replace'|'add'|'remove', path:'/tracks/0/mark', value:<any>}",
                    "properties": {
                        "op": {"type": "string"},
                        "path": {"type": "string"},
                        "value": {},
                    },
                    "required": ["op", "path"],
                },
            },
            "required": ["target_id", "patch"],
        },
    },
    {
        "name": "color_embedding",
        "description": "Color the UMAP embedding by a marker or cell metadata column. Renders in the Embedding tab.",
        "input_schema": {
            "type": "object",
            "properties": {"color_by": {"type": "string", "description": "marker name or cell_type"}},
            "required": ["color_by"],
        },
    },
    {
        "name": "select_cells",
        "description": "Highlight/select a subset of cells by id or criteria. Affects Embedding and 3D tabs.",
        "input_schema": {
            "type": "object",
            "properties": {
                "cell_ids": {"type": "array", "items": {"type": "string"}},
                "criteria": {"type": "string", "description": "optional natural-language criteria"},
            },
        },
    },
    {
        "name": "show_structure",
        "description": "Display the 3D structure of a given cell/chromosome in the 3D Structure tab.",
        "input_schema": {
            "type": "object",
            "properties": {
                "cell_id": {"type": "string"},
                "chrom": {"type": "string"},
            },
            "required": ["cell_id"],
        },
    },
    {
        "name": "color_structure",
        "description": "Color the 3D structure by marker, compartment, or TAD.",
        "input_schema": {
            "type": "object",
            "properties": {"color_by": {"type": "string"}},
            "required": ["color_by"],
        },
    },
    {
        "name": "add_notebook_cell",
        "description": "Insert a Python code cell into the Notebook tab. Set run=true to execute it immediately. The user can edit and re-run the cell.",
        "input_schema": {
            "type": "object",
            "properties": {
                "code": {"type": "string"},
                "run": {"type": "boolean", "description": "execute immediately (default false)"},
            },
            "required": ["code"],
        },
    },
    {
        "name": "run_analysis",
        "description": """Run a structure-identification analysis (TAD, loop, or compartment) on a genomic region.

Returns a JSON handle describing how to visualize the result:
  - data_url: the endpoint serving the result as a Gosling-ready bare JSON array
  - chromosome_field / genomic_fields: field names to put in the track's data block
  - suggested_mark: a sensible Gosling mark for this result type
  - record_count: how many features were found

WORKFLOW: after run_analysis succeeds, call render_gosling with a track like
  {"data":{"type":"json","url":<data_url>,"chromosomeField":<chromosome_field>,
   "genomicFields":<genomic_fields>}, "mark":<suggested_mark>, ...}
to draw the computed result. This is the standard analysis→render handoff.""",
        "input_schema": {
            "type": "object",
            "properties": {
                "type": {"type": "string", "enum": ["tad", "loop", "compartment"]},
                "region": {"type": "string", "description": "e.g. 'chr21' or 'chr21:1-48000000'"},
            },
            "required": ["type", "region"],
        },
    },
    {
        "name": "write_analysis_function",
        "description": """Author and deploy a CUSTOM Python analysis as a live API endpoint.

Use this when no built-in analysis (run_analysis: tad/loop/compartment) fits —
e.g. custom insulation score, radius-of-gyration profile, or a bespoke caller.

YOUR CODE MUST define exactly this top-level function:
    def analyze(cd, chrom, **params):
        # cd: ChromData already subset to `chrom`
        # available: cd.coords (N,3 ndarray), cd.spots (DataFrame),
        #            cd.compute_distances(trace_id=...)
        # pre-bound: np, pd  (NO import statements allowed)
        # MUST return a pandas DataFrame containing chromosome_field and
        # genomic_fields columns.
        ...
        return pd.DataFrame({"chrom": [...], "start": [...], "end": [...]})

FORBIDDEN: import, open, eval/exec/compile, file/network/os access, lambda,
async, global/nonlocal, with, and ANY dunder attribute access (e.g. __class__).
Treat cd as read-only. Keep it O(n) over <100K spots; 10s execution timeout.

After success, returns the SAME render handle as run_analysis (analysis_id /
data_url / chromosome_field / genomic_fields / suggested_mark). Then call
render_gosling with a json track whose url points at data_url (replace the
{chrom} placeholder with the real chromosome).""",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "short id (a-z0-9_)"},
                "code": {"type": "string", "description": "Python defining analyze(cd, chrom, **params)"},
                "chromosome_field": {"type": "string", "description": "chrom column name (default 'chrom')"},
                "genomic_fields": {
                    "type": "array", "items": {"type": "string"},
                    "description": "position columns, e.g. ['start','end']",
                },
                "suggested_mark": {
                    "type": "string",
                    "description": "Gosling mark: rule/bar/link/point/line",
                },
            },
            "required": ["name", "code"],
        },
    },
    {
        "name": "export_view",
        "description": "Export the current Genomic (Gosling) visualization as an image file the user can download. Use when the user asks to save, download, or export the current view/figure.",
        "input_schema": {
            "type": "object",
            "properties": {
                "format": {
                    "type": "string",
                    "enum": ["png", "pdf"],
                    "description": "Image format (default png)",
                },
            },
        },
    },
    {
        "name": "get_view_state",
        "description": """Read the backend-authoritative state of a rendered view.

Use this to see the CURRENT state of a visualization — including any change the
USER made (e.g. brushed a region, clicked a feature). The state includes a
'last_interaction' field if the user has interacted since the view was created.

Pass the view_id returned by render_gosling. Omit view_id to list all views.""",
        "input_schema": {
            "type": "object",
            "properties": {
                "view_id": {"type": "string", "description": "view id from render_gosling; omit for all"},
            },
        },
    },
    {
        "name": "query_user_interaction",
        "description": """Get the user's interaction with a view (brush/click/selection).

Two modes:
  - wait=false (default): return the LAST interaction immediately, or null if none.
  - wait=true: BLOCK until the user next interacts (up to timeout_seconds), then
    return it. Use this to ask the user to pick a region/feature and act on it.

Returns {event_name, payload, timestamp} where payload depends on the event:
  brush_selection → {chrom, start, end};  region_click → {chrom, position};
  cell_selection → {cell_ids: [...]}.

This is how you SEE what the user does in the UI — closing the agent↔user loop.""",
        "input_schema": {
            "type": "object",
            "properties": {
                "view_id": {"type": "string", "description": "view id to watch; omit for any view"},
                "wait": {"type": "boolean", "description": "block for the next interaction (default false)"},
                "timeout_seconds": {"type": "number", "description": "max wait when wait=true (default 30)"},
            },
        },
    },
    {
        "name": "render_component",
        "description": """Compose a CUSTOM layout from whitelisted U-Chrom UI components.

Use this when a single chart isn't enough and you need a bespoke arrangement —
e.g. two views side-by-side for comparison, a panel with a parameter control, or
a titled section with text + a table. You are building your OWN UI by composing
trusted building blocks (you are NOT writing code or HTML).

The 'tree' is a node: {component, props?, children?}. Allowed components:
  Layout:   Panel, Row, Column
  Display:  Text, Table
  Controls: Button, Slider, Select
  Views:    GoslingView (props.view_id → an existing render_gosling view),
            EmbeddingView, StructureView

props are LITERAL values only, or a data reference {"$dataPath": "..."}; no
expressions/code. Unknown component names are rejected. Example:
  {"component":"Row","children":[
     {"component":"Panel","props":{"title":"Embedding"},
      "children":[{"component":"EmbeddingView"}]},
     {"component":"Panel","props":{"title":"Structure"},
      "children":[{"component":"StructureView"}]}]}""",
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "tree": {
                    "type": "object",
                    "description": "root node: {component, props?, children?}",
                },
            },
            "required": ["tree"],
        },
    },
]

SYSTEM_PROMPT = """You are a genomics visualization assistant for U-Chrom, a chromatin 3D structure analysis workbench, with expertise in Gosling.js.

You drive a multi-tab UI directly through tools:
- render_gosling / patch_gosling → Genomic tab (Gosling specs)
- color_embedding / select_cells → Embedding tab (UMAP)
- show_structure / color_structure → 3D Structure tab
- add_notebook_cell → Notebook tab (Python)
- run_analysis → TAD/loop/compartment, results feed back into visualizations
- write_analysis_function → author+deploy a CUSTOM sandboxed analysis as a live endpoint, then render its output
- export_view → download the current Gosling view as PNG/PDF
- get_view_state / query_user_interaction → SEE the current view state and what the user did (brush/click/select)
- render_component → compose a CUSTOM layout from whitelisted UI blocks (Panel/Row/Column/Text/Table/Button/Slider/Select/GoslingView/EmbeddingView/StructureView) when one chart isn't enough

Gosling concepts:
- Tracks have 'data' (source), 'mark' (bar/line/point/rect/area/text/link/triangle), and encodings (x, y, color, size).
- Signal tracks: {"type":"csv","url":"/api/track_csv/<name>","chromosomeField":"chrom","genomicFields":["start","end"]}, mark "bar"/"line".
- Hi-C contact matrix: data {"type":"matrix","url":"/api/v1/tileset_info/?d=contact-<chrom>"}, mark "bar", with x/xe/ys/ye genomic fields and color quantitative.
- Always set 'assembly' (hg19/hg38/mm10), 'width', 'height'.

Be helpful, explain what you're creating, and generate accurate specs. To tweak an existing spec, prefer patch_gosling over recreating.

When a user asks for an analysis that tad/loop/compartment don't cover, prefer
write_analysis_function over add_notebook_cell: it deploys a reusable endpoint
you can immediately visualize. Define analyze(cd, chrom, **params) returning a
DataFrame; you cannot import modules (np/pd are pre-bound) or touch the
filesystem/network. Keep it O(n) over <100K spots."""
