from fastapi import WebSocket
import asyncio
import json
import os
import time
import uuid
import anthropic
import logging

from .agent_tools import TOOLS, SYSTEM_PROMPT

logger = logging.getLogger(__name__)

# Anthropic async client
client = anthropic.AsyncAnthropic()


def _now() -> float:
    return time.time()


def _looks_like_fofct(path: str) -> bool:
    """Heuristic: does this CSV look like a FOF-CT core table?

    FOF-CT files are recognised by either a ``##`` / ``#`` header block at the
    top (e.g. ``##columns=(Spot_ID,Trace_ID,X,Y,Z,...)``) or by carrying the
    FOF-CT signature columns (Spot_ID / Trace_ID + X/Y/Z) in their header row.
    A plain structure-table CSV instead has lowercase ``chrom,start,end,x,y,z``.
    We only need to read the first few KB to decide.
    """
    try:
        with open(path, "r") as fh:
            head = fh.read(8192)
    except Exception:
        return False

    for raw in head.splitlines():
        line = raw.strip()
        if not line:
            continue
        # Strip the trailing-comma padding + surrounding quotes some FOF-CT
        # writers add so every line has the same column count.
        stripped = line.rstrip(",").strip()
        if stripped.startswith('"') and stripped.endswith('"') and len(stripped) >= 2:
            stripped = stripped[1:-1]
        # Any ``#`` header line is a strong FOF-CT signal.
        if stripped.startswith("#"):
            return True
        # First non-comment line is the column header. Decide by content:
        #   - a plain structure table carries the full lowercase set
        #     chrom,start,end,x,y,z (what from_dataframe requires) → NOT FOF-CT
        #   - otherwise, FOF-CT signature columns (Spot_ID / Trace_ID + X/Y/Z;
        #     note FOF-CT uses Chrom_Start/Chrom_End, not start/end) → FOF-CT
        cols = {c.strip().lower() for c in stripped.split(",")}
        if {"chrom", "start", "end", "x", "y", "z"}.issubset(cols):
            return False
        has_spot_or_trace = "spot_id" in cols or "trace_id" in cols
        has_xyz = {"x", "y", "z"}.issubset(cols)
        return has_spot_or_trace and has_xyz
    return False


def _load_chromdata(abs_path: str):
    """Load a ChromData from disk, dispatching by extension / content.

    Supported inputs:
      - ``.h5cd``        → ``ChromData.read`` (native HDF5 container)
      - ``.csv``         → FOF-CT core table (``from_fofct``) when it has a
                           ``#`` header or FOF-CT signature columns, otherwise
                           a plain structure table (``pd.read_csv`` +
                           ``from_dataframe`` requiring chrom,start,end,x,y,z)
      - ``.fofct``/other → attempt ``from_fofct``

    Returns the loaded ``ChromData``. Raises on unreadable / malformed input;
    the caller turns the exception into a ws error message.
    """
    import pandas as pd
    from uchrom.core import ChromData

    lower = abs_path.lower()
    if lower.endswith(".h5cd"):
        return ChromData.read(abs_path)
    if lower.endswith(".csv"):
        if _looks_like_fofct(abs_path):
            return ChromData.from_fofct(abs_path)
        df = pd.read_csv(abs_path)
        return ChromData.from_dataframe(df)
    # Unknown extension (e.g. .fofct / .tsv / .txt) — best-effort FOF-CT parse.
    return ChromData.from_fofct(abs_path)


# Pending user-interaction waiters, keyed by a unique ``interaction_id``. A
# blocking ``query_user_interaction`` tool registers a waiter here (AG-UI style:
# every awaited interaction carries an id, can time out, and is popped cleanly on
# resolve/timeout/cancel — mirrors pantheon's pending-Future pattern). The
# ``ui_event`` handler resolves a waiter when the user next interacts.
class _InteractionWaiter:
    """One pending wait for a user interaction.

    ``interaction_id`` makes resolution precise: a ``ui_event`` that echoes the
    same id resolves exactly this waiter. ``view_id`` (may be None == "any view")
    is the fallback match for *organic* interactions that don't echo an id (e.g.
    a Gosling brush the user just happened to make).
    """

    __slots__ = ("future", "session_key", "view_id", "interaction_id")

    def __init__(self, future, session_key, view_id, interaction_id):
        self.future = future
        self.session_key = session_key
        self.view_id = view_id
        self.interaction_id = interaction_id


_pending_interactions: dict[str, _InteractionWaiter] = {}


def _interaction_key(session, view_id) -> tuple:
    """Legacy helper retained for callers/tests; identifies a (session, view)."""
    return (id(session), view_id)


def _resolve_interaction(session, view_id, event: dict, interaction_id=None) -> bool:
    """Resolve a pending interaction waiter, returning True if one was resolved.

    Resolution policy (precise first, then a forgiving fallback):
      1. If the event echoes an ``interaction_id``, resolve ONLY the waiter with
         that exact id (and same session). A named-but-missing target resolves
         nothing — a stale/foreign id must not wake an unrelated waiter.
      2. If the event carries no id (an organic brush/click/select), resolve the
         first waiter for this session whose ``view_id`` matches (or that waits
         on any view, view_id=None).
    """
    skey = id(session)

    if interaction_id:
        w = _pending_interactions.get(interaction_id)
        if w is not None and w.session_key == skey and not w.future.done():
            w.future.set_result(event)
            _pending_interactions.pop(interaction_id, None)
            return True
        # Named target gone/foreign → do NOT fall back to view matching.
        return False

    for iid, w in list(_pending_interactions.items()):
        if w.session_key != skey or w.future.done():
            continue
        if w.view_id is None or w.view_id == view_id:
            w.future.set_result(event)
            _pending_interactions.pop(iid, None)
            return True
    return False


# Pending view-snapshot waiters, keyed by a unique ``request_id``. The
# ``capture_view_snapshot`` tool registers a Future here, asks the frontend to
# render+toDataURL the target view (``request_snapshot`` message), and blocks on
# the Future; the ``snapshot_result`` handler resolves it. Parallel to
# ``_pending_interactions`` — same pantheon pending-Future pattern, separate
# registry because the round-trip carries an image, not a UI event.
_pending_snapshots: dict[str, asyncio.Future] = {}


def _resolve_snapshot(request_id: str, result: dict) -> bool:
    """Resolve a pending snapshot waiter, returning True if one was resolved.

    ``result`` is ``{"data_url": <str|None>, "error": <str|None>}`` — the
    frontend reports either a captured data URL or a capture error.
    """
    fut = _pending_snapshots.get(request_id)
    if fut is not None and not fut.done():
        fut.set_result(result)
        _pending_snapshots.pop(request_id, None)
        return True
    return False


async def wait_for_snapshot(request_id: str, timeout: float) -> dict | None:
    """Block until the frontend reports ``snapshot_result`` for ``request_id``.

    Returns the result dict ``{"data_url", "error"}``, or None on timeout. The
    waiter is always popped (resolve / timeout / cancel) so the registry never
    leaks — mirrors :func:`wait_for_interaction`.
    """
    loop = asyncio.get_event_loop()
    fut: asyncio.Future = loop.create_future()
    _pending_snapshots[request_id] = fut
    try:
        return await asyncio.wait_for(fut, timeout=timeout)
    except asyncio.TimeoutError:
        return None
    finally:
        _pending_snapshots.pop(request_id, None)


async def wait_for_interaction(
    session, view_id, timeout: float, interaction_id: str | None = None
) -> dict | None:
    """Block until the next ui_event resolves this waiter, or ``timeout`` elapses.

    Registers an :class:`_InteractionWaiter` under ``interaction_id`` (generated
    if not supplied) and awaits it. Returns the interaction event dict, or None
    on timeout. The waiter is always popped (resolve / timeout / cancel) so the
    registry never leaks — the ``finally`` mirrors pantheon's ``finally pop``.
    """
    if interaction_id is None:
        interaction_id = uuid.uuid4().hex
    loop = asyncio.get_event_loop()
    fut: asyncio.Future = loop.create_future()
    _pending_interactions[interaction_id] = _InteractionWaiter(
        fut, id(session), view_id, interaction_id
    )
    try:
        return await asyncio.wait_for(fut, timeout=timeout)
    except asyncio.TimeoutError:
        return None
    finally:
        _pending_interactions.pop(interaction_id, None)


async def handle_message(ws, session, msg: dict, executor):
    """Central message dispatcher for /ws/main.

    Args:
        ws: WebSocket connection
        session: Session object (from session.py)
        msg: Incoming message dict with 'type' field
        executor: ThreadPoolExecutor for blocking operations
    """
    msg_type = msg.get("type")
    payload = msg.get("payload", {})

    if msg_type == "user_message":
        user_text = payload.get("text", "")
        if not user_text:
            await ws.send_json({"type": "error", "message": "user_message requires 'text' field"})
            return

        # Append to session's conversation history for multi-turn dialog
        session.conversation_history.append({"role": "user", "content": user_text})

        # Call agent loop with full history
        await run_agent_loop(ws, session.conversation_history, session)
    elif msg_type == "load_data":
        path = payload.get("path")
        if not path:
            await ws.send_json({"type": "error", "message": "load_data requires 'path' field"})
            return

        # Validate file exists
        abs_path = os.path.abspath(path)
        if not os.path.exists(abs_path):
            await ws.send_json({"type": "error", "message": f"File not found: {path}"})
            return

        # Accept the formats the file browser / open dialog advertise:
        # native .h5cd, plain structure-table .csv, and FOF-CT core tables
        # (.csv with a # header / signature columns, or .fofct). Reject the
        # rest up front with a clear message.
        lower = abs_path.lower()
        if not (lower.endswith(".h5cd") or lower.endswith(".csv") or lower.endswith(".fofct")):
            await ws.send_json({
                "type": "error",
                "message": "File must be .h5cd, .csv, or FOF-CT (.fofct) format",
            })
            return

        # Dispatch by extension / content: .h5cd → ChromData.read; structure
        # CSV → from_dataframe; FOF-CT → from_fofct (see _load_chromdata).
        try:
            cd = _load_chromdata(abs_path)
        except Exception as e:
            await ws.send_json({"type": "error", "message": f"Failed to read {os.path.basename(abs_path)}: {e}"})
            return

        session.h5cd_path = abs_path
        session.chromdata = cd
        # data_api serves from its module-level current_session; point it here.
        import webapp.backend.data_api as _data_api
        _data_api.current_session = session
        # tileset cache is keyed per-chrom on the previous dataset — clear it.
        try:
            from .tileset_api import clear_cache
            clear_cache()
        except Exception:
            pass

        # Start Jupyter kernel for analysis (idempotent) and seed it with the
        # loaded ChromData so notebook cells can reference `cd` directly.
        # seed_kernel re-reads a path with ChromData.read, which only works for
        # .h5cd. For CSV / FOF-CT inputs we persist the already-parsed cd to a
        # temporary .h5cd and seed the kernel from that, so the notebook's `cd`
        # is identical to the session's without re-running the CSV parser.
        from .notebook_api import start_kernel, seed_kernel
        start_kernel()  # Safe to call multiple times
        try:
            if lower.endswith(".h5cd"):
                seed_path = abs_path
            else:
                import tempfile
                seed_path = os.path.join(
                    tempfile.gettempdir(),
                    f"uchrom_seed_{uuid.uuid4().hex}.h5cd",
                )
                cd.write(seed_path)
            seed_kernel(seed_path)  # binds `cd`, sets matplotlib Agg backend
        except Exception:
            logger.exception("Failed to seed kernel with %s", abs_path)

        n_cells = cd.cells.shape[0] if getattr(cd, "cells", None) is not None else 0
        n_spots = cd.coords.shape[0] if getattr(cd, "coords", None) is not None else 0
        await ws.send_json({
            "type": "data_loaded",
            "path": abs_path,
            "n_cells": int(n_cells),
            "n_spots": int(n_spots),
        })

        # Send initial confirmation message
        await ws.send_json({
            "type": "artifact",
            "artifact_type": "text",
            "content": f"Data loaded: {os.path.basename(abs_path)} — {n_cells} cells, {n_spots} spots.\n\nYou can now ask questions or request visualizations.",
            "title": "Ready"
        })
    elif msg_type == "update_viewport":
        from .session import Viewport
        if isinstance(payload, dict):
            session.viewport = Viewport(
                chrom=payload.get("chrom"),
                start=payload.get("start"),
                end=payload.get("end"),
            )
        else:
            session.viewport = payload
    elif msg_type == "select_cells":
        session.cell_selection = payload.get("cell_ids", [])
    elif msg_type == "view.request_snapshot":
        # Client (re)connected or detected a revision gap — send full view state.
        view_id = payload.get("view_id")
        views = session.views
        if view_id:
            v = views.get(view_id)
            snapshot = [v.to_dict()] if v is not None else []
        else:
            snapshot = [v.to_dict() for v in views.values()]
        await ws.send_json({"type": "view.snapshot", "views": snapshot})
    elif msg_type == "snapshot_result":
        # The frontend captured (or failed to capture) a view image in response
        # to a ``request_snapshot`` from capture_view_snapshot. Resolve the
        # blocked tool's Future with the data URL (or error) keyed by request_id.
        request_id = payload.get("request_id")
        if request_id:
            _resolve_snapshot(request_id, {
                "data_url": payload.get("data_url"),
                "error": payload.get("error"),
            })
    elif msg_type == "view.diagnostic":
        # The frontend caught a rendering error (React error-boundary trip or a
        # Gosling spec failure) and is feeding it back so the agent can SEE that
        # its output "画崩了" via get_view_state and self-correct. Store it on the
        # view's capped diagnostics list. We accept diagnostics for a view even
        # if it isn't registered yet (race on first render) by creating a stub.
        view_id = payload.get("view_id") or payload.get("source_view_id")
        if view_id:
            view = session.views.get(view_id)
            if view is None:
                view = session.get_or_create_view(
                    view_id, payload.get("view_type", "gosling")
                )
            view.add_diagnostic({
                "level": payload.get("level", "error"),
                "source": payload.get("source", "render"),
                "message": str(payload.get("message", ""))[:2000],
                "detail": str(payload.get("detail", ""))[:4000] if payload.get("detail") else None,
                "revision": payload.get("revision"),
                "timestamp": _now(),
            })
    elif msg_type == "ui_event":
        # A user interaction on a rendered view (brush, click, selection, 3D
        # spot pick). Record it on the backend-authoritative view state so the
        # agent can see what the user did (get_view_state / query_user_interaction),
        # and wake any tool currently blocked waiting for the next interaction.
        view_id = payload.get("source_view_id") or payload.get("view_id")
        # AG-UI-style id round-trip: if a blocking query_user_interaction told the
        # frontend which interaction it is waiting for, the frontend echoes that
        # id back here so we resolve EXACTLY that waiter (not just any view match).
        interaction_id = payload.get("interaction_id")
        event = {
            "event_name": payload.get("event_name"),
            "payload": payload.get("payload"),
            "timestamp": _now(),
        }
        if interaction_id:
            event["interaction_id"] = interaction_id
        if view_id and view_id in session.views:
            session.views[view_id].state["last_interaction"] = event
            session.views[view_id].last_updated = _now()
        # Resolve a pending query_user_interaction waiter, if any.
        _resolve_interaction(session, view_id, event, interaction_id)
    else:
        await ws.send_json({"type": "error", "message": f"Unknown message type: {msg_type}"})


MAX_TOOL_ITERATIONS = 10  # prevent infinite loops
DEFAULT_MODEL = "claude-opus-4-8"  # can be overridden via config or env


def _tool_status_and_summary(content, executor_failed: bool) -> tuple[str, str | None]:
    """Classify a tool execution outcome for the frontend's three-state UI.

    Mirrors Vercel AI SDK tool-part states (input-available → output-available /
    output-error). Returns ``(status, summary)`` where status is ``"ok"`` or
    ``"error"`` and summary is a short one-liner (never the full payload).

    Determination (pragmatic — must not break the existing 13 tools):
      - executor raised  → error (caller passes executor_failed=True).
      - dict return carrying ``_content_blocks`` (capture_view_snapshot's image
        path) → ok; that structured return only happens on success.
      - any other dict   → error iff ``success`` is explicitly False.
      - str return that is JSON with ``success: false`` → error; otherwise ok.
        Non-JSON strings (the plain "Cell added…" style) are treated as ok.
    """
    if executor_failed:
        # ``content`` here is the JSON error string the loop built on exception.
        msg = None
        try:
            parsed = json.loads(content) if isinstance(content, str) else {}
            msg = parsed.get("error")
        except (ValueError, TypeError):
            msg = None
        return "error", (msg or "tool execution failed")[:200]

    if isinstance(content, dict):
        if "_content_blocks" in content:
            return "ok", None
        if content.get("success") is False:
            return "error", (content.get("error") or "tool reported failure")[:200]
        return "ok", None

    if isinstance(content, str):
        try:
            parsed = json.loads(content)
        except (ValueError, TypeError):
            # Plain-text tool_result (e.g. "Cell added. Output: …") → success.
            return "ok", content[:200] if content else None
        if isinstance(parsed, dict):
            if parsed.get("success") is False:
                return "error", (parsed.get("error") or "tool reported failure")[:200]
            summary = parsed.get("message") if isinstance(parsed.get("message"), str) else None
            return "ok", summary[:200] if summary else None
        return "ok", None

    return "ok", None


async def run_agent_loop(websocket: WebSocket, conversation_history: list, session=None, model: str = None):
    """Run the Claude agent loop with streaming, dispatching tool calls via TOOL_EXECUTORS.

    The loop itself is tool-agnostic: each tool's side effect + tool_result
    content lives in webapp.backend.tool_executors. To add a tool, register an
    executor there — no change here.

    Args:
        websocket: WebSocket connection for sending responses
        conversation_history: Full conversation history (user + assistant turns)
        session: Optional Session object for view-state authority
        model: Model name override (defaults to DEFAULT_MODEL or UCHROM_MODEL env)
    """
    from .tool_executors import TOOL_EXECUTORS

    if model is None:
        model = os.getenv("UCHROM_MODEL", DEFAULT_MODEL)

    iterations = 0
    while True:
        iterations += 1
        if iterations > MAX_TOOL_ITERATIONS:
            await websocket.send_json({
                "type": "agent_message",
                "text": f"(Stopped after {MAX_TOOL_ITERATIONS} tool iterations to avoid a loop.)",
            })
            break

        # Stream the response for real-time text delivery. We forward the
        # Anthropic streaming lifecycle (message_start / content_block_start /
        # content_block_delta / content_block_stop / message_stop) to the client
        # so the frontend can maintain stable, in-place message bubbles keyed by
        # message_id, with per-block text appended at a stable index — instead of
        # spawning a fresh bubble per delta. Mirrors the Anthropic / Vercel AI SDK
        # streaming protocols.
        async with client.messages.stream(
            model=model,
            max_tokens=4096,
            system=SYSTEM_PROMPT,
            tools=TOOLS,
            messages=conversation_history
        ) as stream:
            # Fallback id in case the SDK never surfaces a message_start event
            # (the real API always does; this keeps deltas well-formed regardless).
            message_id = f"msg_{uuid.uuid4().hex}"
            message_started = False

            async for event in stream:
                etype = event.type
                if etype == "message_start":
                    # Prefer the SDK-provided message id for a stable, real id.
                    sdk_id = getattr(getattr(event, "message", None), "id", None)
                    if sdk_id:
                        message_id = sdk_id
                    message_started = True
                    await websocket.send_json({
                        "type": "message_start",
                        "message_id": message_id,
                    })
                elif etype == "content_block_start":
                    cb = getattr(event, "content_block", None)
                    block_type = getattr(cb, "type", None)
                    frame = {
                        "type": "content_block_start",
                        "message_id": message_id,
                        "index": event.index,
                        "block_type": block_type,
                    }
                    # For a tool_use block, Anthropic's content_block.name is the
                    # tool name and .id the tool_use id. Forward both so the
                    # frontend can label the loading indicator ("calling X…") the
                    # moment the block opens — before the tool even runs.
                    if block_type == "tool_use":
                        frame["tool_name"] = getattr(cb, "name", None)
                        frame["tool_use_id"] = getattr(cb, "id", None)
                    await websocket.send_json(frame)
                elif etype == "content_block_delta":
                    if event.delta.type == "text_delta":
                        await websocket.send_json({
                            "type": "agent_message_delta",
                            "message_id": message_id,
                            "index": event.index,
                            "text": event.delta.text,
                        })
                elif etype == "content_block_stop":
                    await websocket.send_json({
                        "type": "content_block_stop",
                        "message_id": message_id,
                        "index": event.index,
                    })
                elif etype == "message_stop":
                    await websocket.send_json({
                        "type": "message_stop",
                        "message_id": message_id,
                    })

            # Get the final message
            response = await stream.get_final_message()

            # Defensive: if the SDK never emitted message_start/message_stop
            # events (e.g. a degraded transport), still bracket the turn so the
            # client can finalize its bubble rather than leak an open one.
            if not message_started:
                await websocket.send_json({
                    "type": "message_stop",
                    "message_id": message_id,
                })

        print(f"Claude response stop_reason: {response.stop_reason}")

        # Add assistant message to history
        conversation_history.append({
            "role": "assistant",
            "content": response.content
        })

        # Extract tool uses from response
        tool_uses = [block for block in response.content if block.type == "tool_use"]

        # Handle tool calls
        if response.stop_reason == "tool_use" and tool_uses:
            tool_results = []

            for tool_use in tool_uses:
                print(f"Tool call: {tool_use.name}, input: {tool_use.input}")
                # Announce the call before running it so the frontend can show a
                # "calling {tool_name}…" loading indicator keyed by tool_use_id
                # (Vercel AI SDK input-available state).
                await websocket.send_json({
                    "type": "tool_call_start",
                    "tool_use_id": tool_use.id,
                    "tool_name": tool_use.name,
                    "message_id": message_id,
                })
                executor = TOOL_EXECUTORS.get(tool_use.name)
                if executor is None:
                    await websocket.send_json({
                        "type": "tool_call_result",
                        "tool_use_id": tool_use.id,
                        "tool_name": tool_use.name,
                        "status": "error",
                        "summary": f"Unknown tool: {tool_use.name}",
                    })
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": tool_use.id,
                        "content": json.dumps({"error": f"Unknown tool: {tool_use.name}"}),
                    })
                    continue

                # Surface the tool_use id to executors that need it (render_gosling
                # uses it as the artifact_id so patch_gosling can target the spec).
                # Also surface the session so view-aware tools can read/write the
                # backend-authoritative view state.
                tool_input = dict(tool_use.input)
                tool_input["_tool_use_id"] = tool_use.id
                tool_input["_session"] = session
                executor_failed = False
                try:
                    content = await executor(websocket, tool_input)
                except Exception as e:  # defensive: an executor bug must not kill the loop
                    logger.exception("tool executor %s failed", tool_use.name)
                    content = json.dumps({"success": False, "error": f"{tool_use.name} failed: {e}"})
                    executor_failed = True
                # Classify the outcome and tell the frontend to finalize the
                # indicator as ✓ done or ✗ error (output-available / output-error).
                status, summary = _tool_status_and_summary(content, executor_failed)
                await websocket.send_json({
                    "type": "tool_call_result",
                    "tool_use_id": tool_use.id,
                    "tool_name": tool_use.name,
                    "status": status,
                    "summary": summary,
                })
                # Executors normally return a plain string (the tool_result text).
                # An executor that needs the agent to SEE an image (e.g.
                # capture_view_snapshot) instead returns a dict carrying a
                # ready-made Anthropic content-block list under ``_content_blocks``
                # (text + image blocks). Pass that through verbatim so the image
                # reaches the vision model; everything else stays a string and is
                # untouched — backwards compatible with the other 12 tools.
                if isinstance(content, dict) and "_content_blocks" in content:
                    result_content = content["_content_blocks"]
                else:
                    result_content = content
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tool_use.id,
                    "content": result_content,
                })

            # Add tool results to history and continue the loop.
            conversation_history.append({"role": "user", "content": tool_results})
            continue

        # If stop_reason is "end_turn" or no more tool calls, we're done
        break

