from fastapi import WebSocket
import asyncio
import json
import os
import time
import anthropic
import logging

from .agent_tools import TOOLS, SYSTEM_PROMPT

logger = logging.getLogger(__name__)

# Anthropic async client
client = anthropic.AsyncAnthropic()


def _now() -> float:
    return time.time()


# Pending user-interaction waiters, keyed by (id(session), view_id). A blocking
# query_user_interaction tool registers an asyncio.Future here; the ui_event
# handler resolves it when the user next interacts with that view.
_pending_interactions: dict[tuple, asyncio.Future] = {}


def _interaction_key(session, view_id) -> tuple:
    return (id(session), view_id)


def _resolve_interaction(session, view_id, event: dict) -> None:
    """Resolve a future waiting on the next interaction for this view."""
    for key in (_interaction_key(session, view_id), _interaction_key(session, None)):
        fut = _pending_interactions.get(key)
        if fut is not None and not fut.done():
            fut.set_result(event)
            _pending_interactions.pop(key, None)


async def wait_for_interaction(session, view_id, timeout: float) -> dict | None:
    """Block until the next ui_event for ``view_id`` (or any view if None)."""
    loop = asyncio.get_event_loop()
    fut: asyncio.Future = loop.create_future()
    key = _interaction_key(session, view_id)
    _pending_interactions[key] = fut
    try:
        return await asyncio.wait_for(fut, timeout=timeout)
    except asyncio.TimeoutError:
        return None
    finally:
        _pending_interactions.pop(key, None)


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

        # Optional: validate .h5cd extension
        if not abs_path.endswith('.h5cd'):
            await ws.send_json({"type": "error", "message": "File must be .h5cd format"})
            return

        # Actually read the ChromData into the session so the REST APIs
        # (/api/umap, /api/coords/batch, /api/tileset_info, ...) can serve it.
        try:
            from uchrom.core import ChromData
            cd = ChromData.read(abs_path)
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

        # Start Jupyter kernel for analysis (idempotent)
        from .notebook_api import start_kernel
        start_kernel()  # Safe to call multiple times

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
    elif msg_type == "ui_event":
        # A user interaction on a rendered view (brush, click, selection).
        # Record it on the backend-authoritative view state so the agent can
        # see what the user did (get_view_state / query_user_interaction), and
        # wake any tool currently blocked waiting for the next interaction.
        view_id = payload.get("source_view_id") or payload.get("view_id")
        event = {
            "event_name": payload.get("event_name"),
            "payload": payload.get("payload"),
            "timestamp": _now(),
        }
        if view_id and view_id in session.views:
            session.views[view_id].state["last_interaction"] = event
            session.views[view_id].last_updated = _now()
        # Resolve a pending query_user_interaction future, if any.
        _resolve_interaction(session, view_id, event)
    else:
        await ws.send_json({"type": "error", "message": f"Unknown message type: {msg_type}"})


MAX_TOOL_ITERATIONS = 10  # prevent infinite loops


async def run_agent_loop(websocket: WebSocket, conversation_history: list, session=None):
    """Run the Claude agent loop, dispatching tool calls via TOOL_EXECUTORS.

    The loop itself is tool-agnostic: each tool's side effect + tool_result
    content lives in webapp.backend.tool_executors. To add a tool, register an
    executor there — no change here.

    ``session`` (optional) is surfaced to executors via ``tool_input["_session"]``
    so view-aware tools can read/write the backend-authoritative view state.
    """
    from .tool_executors import TOOL_EXECUTORS

    iterations = 0
    while True:
        iterations += 1
        if iterations > MAX_TOOL_ITERATIONS:
            await websocket.send_json({
                "type": "agent_message",
                "text": f"(Stopped after {MAX_TOOL_ITERATIONS} tool iterations to avoid a loop.)",
            })
            break
        response = await client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=4096,
            system=SYSTEM_PROMPT,
            tools=TOOLS,
            messages=conversation_history
        )

        print(f"Claude response stop_reason: {response.stop_reason}")

        # Process response content
        text_parts = []
        tool_uses = []

        for block in response.content:
            if block.type == "text":
                text_parts.append(block.text)
            elif block.type == "tool_use":
                tool_uses.append(block)

        # Add assistant message to history
        conversation_history.append({
            "role": "assistant",
            "content": response.content
        })

        # Send text response to client
        if text_parts:
            combined_text = "\n".join(text_parts)
            await websocket.send_json({
                "type": "agent_message",
                "text": combined_text
            })

        # Handle tool calls
        if response.stop_reason == "tool_use" and tool_uses:
            tool_results = []

            for tool_use in tool_uses:
                print(f"Tool call: {tool_use.name}, input: {tool_use.input}")
                executor = TOOL_EXECUTORS.get(tool_use.name)
                if executor is None:
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
                try:
                    content = await executor(websocket, tool_input)
                except Exception as e:  # defensive: an executor bug must not kill the loop
                    logger.exception("tool executor %s failed", tool_use.name)
                    content = json.dumps({"success": False, "error": f"{tool_use.name} failed: {e}"})
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tool_use.id,
                    "content": content,
                })

            # Add tool results to history and continue the loop.
            conversation_history.append({"role": "user", "content": tool_results})
            continue

        # If stop_reason is "end_turn" or no more tool calls, we're done
        break

