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

## Analysis via Python code
When the user asks to run analysis (TAD calling, compartments, embeddings, etc.),
output a Python code block. The code runs in the backend with these variables available:
  - `cd`: the loaded ChromData object (uchrom.core.ChromData)
  - `uchrom`: the uchrom package
  - `np`, `pd`: numpy, pandas
  - `emit_artifact(type, payload)`: send results to the frontend

Example — add a track plot panel with analysis results:
```python
result = uchrom.strc.tad.call(cd, chrom="chr15")
emit_artifact("add_panel", {"type": "track_plot", "label": "TADs chr15",
    "data": result.to_dict() if hasattr(result, 'to_dict') else str(result)})
```

Example — show a summary:
```python
n_cells = len(cd.cells)
chroms = list(cd.spots['chrom'].unique())
emit_artifact("text_block", {"content": f"{n_cells} cells, {len(chroms)} chromosomes"})
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

    elif t == "artifact_action":
        await ws.send_json({"type": "not_implemented"})

    elif t == "export_figure":
        # TODO: render and serve
        await ws.send_json({"type": "export_ready", "payload": {"url": None, "format": p.get("format")}})

    else:
        await ws.send_json({"type": "error", "payload": {"message": f"unknown type: {t}"}})
