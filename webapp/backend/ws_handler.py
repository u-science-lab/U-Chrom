import asyncio
import json
import os
from fastapi import WebSocket
from .session import Session, Viewport


def _load_chromdata(path: str, fmt: str):
    from uchrom.core import ChromData
    from uchrom.io.seqfish_multiomics import read_seqfish_multiomics
    if fmt == "h5cd":
        return ChromData.read(path)
    elif fmt == "fofct":
        return ChromData.from_fofct(path)
    elif fmt == "seqfish_multiomics":
        return read_seqfish_multiomics(path)
    else:
        return ChromData.read(path)


_SYSTEM_PROMPT = """\
You are an assistant for U-Chrom, a chromatin 3D structure analysis tool.

## Navigation actions
When the user asks to view a genomic region or navigate:
  <action type="set_viewport">{"chrom":"chr15","start":30000000,"end":60000000}</action>

When the user asks to select cells by type:
  <action type="select_cells">{"mode":"cell_type","ids":[],"label":"Purkinje"}</action>

When the user asks to highlight specific genomic regions:
  <action type="highlight_region">{"chrom":"chr15","start":30000000,"end":35000000,"color":"#ff6b6b","label":"TAD boundary"}</action>

When the user asks to change the colormap:
  <action type="set_colormap">{"scheme":"viridis","property":"compartment"}</action>

## Analysis via Python code
When the user asks to run analysis (TAD calling, compartments, embeddings, etc.),
output a Python code block. The code runs in the backend with these variables available:
  - `cd`: the loaded ChromData object (uchrom.core.ChromData)
  - `uchrom`: the uchrom package
  - `np`, `pd`: numpy, pandas
  - `emit_artifact(type, payload)`: send results to the frontend

Artifact types:
- "text_block": Display text message
  emit_artifact("text_block", {"content": "Analysis complete", "format": "info|error|success"})

- "add_panel": Add a new visualization panel
  emit_artifact("add_panel", {"type": "track_plot", "label": "TADs chr15", "data": {...}})

- "highlight_region": Highlight genomic regions in 3D view
  emit_artifact("highlight_region", {"regions": [
    {"chrom": "chr15", "start": 30000000, "end": 35000000, "color": "#ff6b6b", "label": "Region 1"}
  ]})

- "set_colormap": Change 3D structure coloring
  emit_artifact("set_colormap", {"scheme": "viridis", "property": "compartment", "range": [0, 1]})

- "figure": Export publication-ready figure
  emit_artifact("figure", {"path": "figure.pdf", "preview": "base64...", "format": "pdf"})

- "data": Structured analysis results (JSON)
  emit_artifact("data", {"type": "compartment_diff", "regions": [...], "stats": {...}})

## Publication-ready figure generation
When the user asks to generate a figure for publication (e.g., "适合 Nature 投稿", "for Cell journal"):
```python
from uchrom.pl import create_figure, PanelSpec

# Infer parameters from user request:
# - "Nature" → style="nature", dpi=300
# - "Cell" → style="cell", dpi=300
# - "Science" → style="science", dpi=300
# - "single column" → column_mode="single"
# - "double column" → column_mode="double"

panels = [
    PanelSpec(
        type="structure_3d",  # or "contact_map", "track"
        data={"projection": "xy"},
        label="A",
        title="3D Structure",
        colormap="RdBu_r",
    ),
    PanelSpec(
        type="contact_map",
        data={"matrix": None},  # auto-compute
        label="B",
        title="Contact Map",
    ),
]

fig = create_figure(
    chromdata=cd,
    layout="1x2",  # or "2x1", "3x1", etc.
    panels=panels,
    style="nature",  # inferred from user request
    dpi=300,
)

# Export and send to frontend
import tempfile
pdf_path = tempfile.mktemp(suffix=".pdf")
fig.save(pdf_path)
preview_base64 = fig.to_base64(dpi=150)

emit_artifact("figure", {
    "path": pdf_path,
    "preview": preview_base64,
    "format": "pdf",
    "params": fig.metadata
})
emit_artifact("text_block", {"content": f"Generated figure with {len(panels)} panels"})
```

Example — user: "生成 Figure 2: 三个细胞的 A/B compartment 对比，适合 Nature 投稿"
```python
from uchrom.pl import create_figure, PanelSpec

cells = ["cell_001", "cell_002", "cell_003"]
panels = []

for i, cell_id in enumerate(cells):
    cd_cell = cd.get_cell(cell_id)
    # Assume compartment data exists in cd_cell
    panels.append(PanelSpec(
        type="track",
        data={"track_type": "signal", "positions": [], "values": []},  # placeholder
        label=chr(65 + i),  # A, B, C
        title=f"Cell {cell_id}",
    ))

fig = create_figure(
    chromdata=cd,
    layout="3x1",
    panels=panels,
    style="nature",
    dpi=300,
)

import tempfile
pdf_path = tempfile.mktemp(suffix=".pdf")
fig.save(pdf_path)
preview_base64 = fig.to_base64(dpi=150)

emit_artifact("figure", {
    "path": pdf_path,
    "preview": preview_base64,
    "format": "pdf",
    "params": fig.metadata
})
```

- "data": Structured analysis results (JSON)
  emit_artifact("data", {"type": "compartment_diff", "regions": [...], "stats": {...}})

Example — highlight significant regions:
```python
result = uchrom.strc.comp.detect_compartments(cd, chrom="chr15")
significant = result[result['score'] > 0.8]
regions = [{"chrom": r.chrom, "start": r.start, "end": r.end, "color": "#ff6b6b"}
           for _, r in significant.iterrows()]
emit_artifact("highlight_region", {"regions": regions})
emit_artifact("text_block", {"content": f"Found {len(regions)} significant compartments"})
```

Rules:
- Use action tags for navigation/selection, Python code for analysis.
- chrom values: chr1..chr19, chrX. start/end are integers (base pairs).
- Keep code minimal — only what's needed to answer the question.
"""


def _parse_actions(text: str) -> list[dict]:
    """Extract <action type="...">JSON</action> tags from Claude's response."""
    import re
    actions = []
    for m in re.finditer(r'<action type="([^"]+)">([^<]+)</action>', text):
        try:
            actions.append({"action_type": m.group(1), "payload": json.loads(m.group(2))})
        except json.JSONDecodeError:
            pass
    return actions


def _extract_code_blocks(text: str) -> list[str]:
    """Extract ```python ... ``` blocks from Claude's response."""
    import re
    return re.findall(r'```python\n(.*?)```', text, re.DOTALL)


def _run_code_in_worker(code: str, chromdata_path: str | None) -> list[dict]:
    """Execute code in isolated process. Returns list of emit_artifact calls."""
    import sys, io, numpy as np, pandas as pd
    artifacts = []

    def emit_artifact(type_: str, payload: dict):
        artifacts.append({"artifact_type": type_, "payload": payload})

    sandbox = {
        "emit_artifact": emit_artifact,
        "np": np, "pd": pd,
        "__builtins__": __builtins__,  # full builtins — local deploy, no hostile users
    }

    # Load uchrom and chromdata
    try:
        import uchrom
        sandbox["uchrom"] = uchrom
        if chromdata_path:
            from uchrom.core import ChromData
            sandbox["cd"] = ChromData.read(chromdata_path)
    except Exception:
        pass

    try:
        exec(code, sandbox)  # noqa: S102
    except Exception as e:
        artifacts.append({"artifact_type": "text_block",
                          "payload": {"content": f"Code error: {e}", "format": "error"}})
    return artifacts


async def _run_agent(ws: WebSocket, session: Session, text: str, session_id: str, executor=None):
    """Spawn claude CLI, pass prompt via stdin, stream partial tokens via stream_event."""
    ctx = ""
    if session.chromdata is not None:
        cd = session.chromdata
        n_cells = len(cd.cells) if cd.cells is not None else 0
        chroms = list(cd.spots["chrom"].unique()) if cd.spots is not None else []
        ctx = (f"\n\nLoaded data: {n_cells} cells, chroms: {[str(c) for c in chroms[:8]]}"
               f"{'...' if len(chroms) > 8 else ''}")
        if session.viewport.chrom:
            ctx += f", current viewport: {session.viewport.chrom}:{session.viewport.start}-{session.viewport.end}"

    history = ""
    for turn in session.conversation_history:
        history += f"\n{turn['role'].upper()}: {turn['content']}"

    prompt = (_SYSTEM_PROMPT + "\n\n" + history + f"\nUSER: {text}" + ctx).lstrip()

    proc = await asyncio.create_subprocess_exec(
        "claude", "-p",
        "--output-format", "stream-json",
        "--include-partial-messages",
        "--bare",
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
        cwd=os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
    )
    # Pass prompt via stdin — avoids argv length limits
    proc.stdin.write(prompt.encode())
    proc.stdin.close()

    full_response = []
    async for line in proc.stdout:
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue

        etype = event.get("type")

        # Partial streaming: content_block_delta → text_delta
        if etype == "stream_event":
            inner = event.get("event", {})
            if inner.get("type") == "content_block_delta":
                delta = inner.get("delta", {})
                if delta.get("type") == "text_delta":
                    token = delta.get("text", "")
                    if token:
                        full_response.append(token)
                        await ws.send_json({
                            "type": "agent_token",
                            "payload": {"session_id": session_id, "token": token}
                        })

        # Fallback: complete assistant message (when --include-partial-messages unsupported)
        elif etype == "assistant" and not full_response:
            for block in event.get("message", {}).get("content", []):
                if block.get("type") == "text" and block.get("text"):
                    full_response.append(block["text"])
                    await ws.send_json({
                        "type": "agent_token",
                        "payload": {"session_id": session_id, "token": block["text"]}
                    })

        elif etype == "result":
            await ws.send_json({
                "type": "agent_token",
                "payload": {"session_id": session_id, "token": "", "done": True}
            })

    await proc.wait()

    # Parse actions from full response and push to frontend
    full_text = "".join(full_response)
    for action in _parse_actions(full_text):
        atype = action["action_type"]
        payload = action["payload"]
        if atype == "set_viewport":
            session.viewport = Viewport(
                chrom=payload.get("chrom"),
                start=payload.get("start"),
                end=payload.get("end"),
            )
            await ws.send_json({"type": "agent_viewport_update", "payload": payload})
        elif atype == "select_cells":
            session.cell_selection = payload.get("ids", [])
            await ws.send_json({"type": "agent_cell_selection", "payload": payload})
        elif atype == "highlight_region":
            await ws.send_json({"type": "agent_highlight_region", "payload": payload})
        elif atype == "set_colormap":
            await ws.send_json({"type": "agent_set_colormap", "payload": payload})

    # Execute Python code blocks in subprocess worker
    code_blocks = _extract_code_blocks(full_text)
    if code_blocks and executor is not None:
        # Save chromdata to temp file for worker process (avoids pickling ChromData)
        chromdata_path = None
        if session.chromdata is not None:
            import tempfile
            tmp = tempfile.NamedTemporaryFile(suffix=".h5cd", delete=False)
            tmp.close()
            session.chromdata.write(tmp.name)
            chromdata_path = tmp.name

        loop = asyncio.get_running_loop()
        for code in code_blocks:
            try:
                artifacts = await loop.run_in_executor(
                    executor, _run_code_in_worker, code, chromdata_path
                )
                for art in artifacts:
                    await ws.send_json({"type": "agent_artifact", "payload": art})
            except Exception as e:
                await ws.send_json({"type": "agent_artifact", "payload": {
                    "artifact_type": "text_block",
                    "payload": {"content": f"Execution error: {e}", "format": "error"}
                }})

    # Store turn in session history for next call
    if full_response:
        session.conversation_history.append({"role": "user", "content": text})
        session.conversation_history.append({"role": "assistant", "content": full_text})


async def _run_agent_multimodal(ws: WebSocket, session: Session, image_base64: str, prompt: str, session_id: str, executor=None):
    """Run agent with multimodal input (image + text)."""
    import os

    # Build context
    ctx = ""
    if session.chromdata is not None:
        cd = session.chromdata
        n_cells = len(cd.cells) if cd.cells is not None else 0
        chroms = list(cd.spots["chrom"].unique()) if cd.spots is not None else []
        ctx = (f"\n\nLoaded data: {n_cells} cells, chroms: {[str(c) for c in chroms[:8]]}"
               f"{'...' if len(chroms) > 8 else ''}")
        if session.viewport.chrom:
            ctx += f", current viewport: {session.viewport.chrom}:{session.viewport.start}-{session.viewport.end}"

    # Call Claude API with vision
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

        messages = [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/png",
                            "data": image_base64,
                        },
                    },
                    {
                        "type": "text",
                        "text": prompt + ctx,
                    },
                ],
            }
        ]

        # Stream response
        full_response = []
        with client.messages.stream(
            model="claude-opus-4",
            max_tokens=2048,
            messages=messages,
        ) as stream:
            for text in stream.text_stream:
                full_response.append(text)
                await ws.send_json({
                    "type": "agent_token",
                    "payload": {"session_id": session_id, "token": text}
                })

        await ws.send_json({
            "type": "agent_token",
            "payload": {"session_id": session_id, "token": "", "done": True}
        })

        # Store in history
        full_text = "".join(full_response)
        if full_text:
            session.conversation_history.append({"role": "user", "content": f"[Image] {prompt}"})
            session.conversation_history.append({"role": "assistant", "content": full_text})

    except Exception as e:
        await ws.send_json({
            "type": "agent_token",
            "payload": {"session_id": session_id, "token": f"\n\nError: {e}", "done": True}
        })


async def handle_message(ws: WebSocket, session: Session, msg: dict, executor) -> None:
    t = msg.get("type")
    p = msg.get("payload", {})

    if t == "load_data":
        path = p.get("path", "")
        fmt = p.get("format", "h5cd")
        loop = asyncio.get_running_loop()
        try:
            session.chromdata = await loop.run_in_executor(executor, _load_chromdata, path, fmt)
            cd = session.chromdata
            n_cells = len(cd.cells) if cd.cells is not None else 0
            chroms = list(cd.spots["chrom"].unique()) if cd.spots is not None else []
            await ws.send_json({"type": "data_loaded", "payload": {
                "cell_count": n_cells,
                "chroms": [str(c) for c in chroms],
                "umap_url": "/api/umap" if "umap" in (cd.cellm or {}) else None,
            }})
        except Exception as e:
            await ws.send_json({"type": "error", "payload": {"message": str(e)}})

    elif t == "update_viewport":
        session.viewport = Viewport(**{k: p[k] for k in ("chrom", "start", "end") if k in p})

    elif t == "select_cells":
        session.cell_selection = p.get("ids", [])

    elif t == "run_analysis":
        # TODO: dispatch to ProcessPoolExecutor
        await ws.send_json({"type": "analysis_progress", "payload": {"job_id": None, "progress": 0, "status": "queued"}})

    elif t == "agent_message":
        session_id = p.get("session_id", session.session_id)
        text = p.get("text", "")
        async def _safe_run():
            try:
                await _run_agent(ws, session, text, session_id, executor)
            except Exception as e:
                import traceback
                traceback.print_exc()
                try:
                    await ws.send_json({"type": "error", "payload": {"message": str(e)}})
                except Exception:
                    pass
        asyncio.create_task(_safe_run())

    elif t == "multimodal_query":
        session_id = p.get("session_id", session.session_id)
        image_base64 = p.get("image", "")
        prompt = p.get("prompt", "Analyze this image.")
        async def _safe_run_multimodal():
            try:
                await _run_agent_multimodal(ws, session, image_base64, prompt, session_id, executor)
            except Exception as e:
                import traceback
                traceback.print_exc()
                try:
                    await ws.send_json({"type": "error", "payload": {"message": str(e)}})
                except Exception:
                    pass
        asyncio.create_task(_safe_run_multimodal())

    elif t == "artifact_action":
        await ws.send_json({"type": "not_implemented"})

    elif t == "export_figure":
        # TODO: render and serve
        await ws.send_json({"type": "export_ready", "payload": {"url": None, "format": p.get("format")}})

    else:
        await ws.send_json({"type": "error", "payload": {"message": f"unknown type: {t}"}})
