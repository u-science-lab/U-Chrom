from fastapi import WebSocket
import json
import os
import anthropic
import logging

from .agent_tools import TOOLS, SYSTEM_PROMPT

logger = logging.getLogger(__name__)

# Anthropic async client
client = anthropic.AsyncAnthropic()


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
        await run_agent_loop(ws, session.conversation_history)
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
        session.viewport = payload
    elif msg_type == "select_cells":
        session.cell_selection = payload.get("cell_ids", [])
    else:
        await ws.send_json({"type": "error", "message": f"Unknown message type: {msg_type}"})


MAX_TOOL_ITERATIONS = 10  # prevent infinite loops


async def run_agent_loop(websocket: WebSocket, conversation_history: list):
    """Run the Claude agent loop, handling tool calls."""
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
        assistant_content = []
        text_parts = []
        tool_uses = []

        for block in response.content:
            assistant_content.append(block)
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

                if tool_use.name == "render_gosling":
                    spec = tool_use.input.get("spec", {})
                    title = tool_use.input.get("title", "Genomic Visualization")

                    # Send spec to frontend for rendering (ag-ui format)
                    await websocket.send_json({
                        "type": "agent_artifact",
                        "artifact_type": "gosling_spec",
                        "artifact_id": tool_use.id,
                        "title": title,
                        "spec": spec
                    })

                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": tool_use.id,
                        "content": json.dumps({
                            "success": True,
                            "message": f"Gosling spec rendered successfully. Title: {title}",
                            "spec_tracks": len(spec.get("tracks", []))
                        })
                    })
                elif tool_use.name == "patch_gosling":
                    target_id = tool_use.input.get("target_id", "")
                    patch = tool_use.input.get("patch", {})

                    # Forward the JSON-Patch op to the frontend, which applies it
                    # to the active spec (store.applyGoslingPatch).
                    await websocket.send_json({
                        "type": "agent_artifact",
                        "artifact_type": "gosling_patch",
                        "target_id": target_id,
                        "patch": patch,
                    })

                    if not target_id or not patch.get("path"):
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": tool_use.id,
                            "content": json.dumps({
                                "success": False,
                                "error": "patch_gosling requires 'target_id' and a 'patch' with a 'path'.",
                            }),
                        })
                    else:
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": tool_use.id,
                            "content": json.dumps({
                                "success": True,
                                "message": f"Applied {patch.get('op', 'replace')} to {patch.get('path')} on spec {target_id}.",
                            }),
                        })
                elif tool_use.name == "add_notebook_cell":
                    code = tool_use.input.get("code", "")

                    try:
                        # Execute code
                        from .notebook_api import execute_code
                        result = execute_code(code)
                    except Exception as e:
                        # Handle execution failures
                        result = {
                            "status": "error",
                            "output": "",
                            "error": f"Execution failed: {str(e)}"
                        }

                    # Send to frontend
                    await websocket.send_json({
                        "type": "artifact",
                        "artifact_type": "notebook_cell",
                        "content": {
                            "code": code,
                            "output": result.get("output", ""),
                            "error": result.get("error"),
                            "status": result.get("status", "ok")
                        }
                    })

                    # Build tool result with truncated output/error
                    output_preview = result.get("output", "")[:100]
                    error_preview = result.get("error", "")[:100] if result.get("error") else None

                    if error_preview:
                        tool_result_content = f"Cell added with error. Error: {error_preview}"
                    else:
                        tool_result_content = f"Cell added. Output: {output_preview}"

                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": tool_use.id,
                        "content": tool_result_content
                    })
                # Security note: Executes Claude-generated code in Jupyter kernel.
                # Suitable for trusted LLM agents in local/research environments.
                # Production deployments should add sandboxing (containers, pyodide, etc.)
                elif tool_use.name == "run_analysis":
                    analysis_type = tool_use.input.get("type", "")
                    region = tool_use.input.get("region", "") or ""
                    # region may be 'chr21' or 'chr21:1-48000000'; take the chrom
                    chrom = region.split(":")[0].strip() if region else ""

                    try:
                        from .strc_api import run_registered_analysis
                        handle = run_registered_analysis(analysis_type, chrom)

                        # Notify frontend so the relevant panel can refresh
                        await websocket.send_json({
                            "type": "agent_artifact",
                            "artifact_type": "analysis_result",
                            "analysis_type": analysis_type,
                            "chrom": chrom,
                            "result": {handle["type"] + "s": handle["records"]},
                        })

                        # Hand the agent everything it needs to render the result
                        # with render_gosling (data URL + field names + mark).
                        tool_result = {
                            "type": "tool_result",
                            "tool_use_id": tool_use.id,
                            "content": json.dumps({
                                "success": True,
                                "type": handle["type"],
                                "chrom": handle["chrom"],
                                "record_count": handle["record_count"],
                                "data_url": handle["data_url"],
                                "chromosome_field": handle["chromosome_field"],
                                "genomic_fields": handle["genomic_fields"],
                                "suggested_mark": handle["suggested_mark"],
                                "next_step": (
                                    "To visualize, call render_gosling with a track whose "
                                    "data = {\"type\":\"json\",\"url\":data_url,"
                                    "\"chromosomeField\":chromosome_field,"
                                    "\"genomicFields\":genomic_fields} and mark = suggested_mark."
                                ),
                            }),
                        }
                    except Exception as e:
                        tool_result = {
                            "type": "tool_result",
                            "tool_use_id": tool_use.id,
                            "content": f"Analysis failed: {str(e)}"
                        }

                    tool_results.append(tool_result)
                elif tool_use.name == "write_analysis_function":
                    name = (tool_use.input.get("name") or "").strip()
                    code = tool_use.input.get("code", "")
                    meta = {}
                    if tool_use.input.get("chromosome_field"):
                        meta["chromosome_field"] = tool_use.input["chromosome_field"]
                    if tool_use.input.get("genomic_fields"):
                        meta["genomic_fields"] = tuple(tool_use.input["genomic_fields"])
                    if tool_use.input.get("suggested_mark"):
                        meta["suggested_mark"] = tool_use.input["suggested_mark"]
                    if name:
                        meta["result_key"] = name

                    try:
                        from .dynamic_api import register_analysis
                        from .dynamic_analysis import AnalysisValidationError
                        try:
                            handle = register_analysis(name, code, **meta)
                        except AnalysisValidationError as ve:
                            tool_results.append({
                                "type": "tool_result",
                                "tool_use_id": tool_use.id,
                                "content": json.dumps({
                                    "success": False,
                                    "error": f"Rejected by sandbox: {ve}",
                                    "hint": (
                                        "Remove imports/IO/dunder access; define "
                                        "analyze(cd, chrom, **params) returning a DataFrame."
                                    ),
                                }),
                            })
                        else:
                            await websocket.send_json({
                                "type": "agent_artifact",
                                "artifact_type": "custom_analysis_deployed",
                                "analysis_id": name,
                                "data_url": handle["data_url"],
                            })
                            tool_results.append({
                                "type": "tool_result",
                                "tool_use_id": tool_use.id,
                                "content": json.dumps({
                                    "success": True,
                                    "analysis_id": name,
                                    "data_url": handle["data_url"],
                                    "chromosome_field": handle["chromosome_field"],
                                    "genomic_fields": handle["genomic_fields"],
                                    "suggested_mark": handle["suggested_mark"],
                                    "next_step": (
                                        "Endpoint deployed. Replace {chrom} in data_url "
                                        "with the real chromosome, then call render_gosling "
                                        "with data={\"type\":\"json\",\"url\":<data_url>,"
                                        "\"chromosomeField\":chromosome_field,"
                                        "\"genomicFields\":genomic_fields} and "
                                        "mark=suggested_mark."
                                    ),
                                }),
                            })
                    except Exception as e:
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": tool_use.id,
                            "content": f"Deploy failed: {str(e)}",
                        })
                elif tool_use.name == "select_cells":
                    cell_ids = tool_use.input.get("cell_ids", []) or []
                    criteria = tool_use.input.get("criteria", "")
                    await websocket.send_json({
                        "type": "agent_artifact",
                        "artifact_type": "select_cells",
                        "cell_ids": cell_ids,
                        "criteria": criteria,
                    })
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": tool_use.id,
                        "content": f"Selected {len(cell_ids)} cell(s)."
                                   + (f" Criteria: {criteria}" if criteria else ""),
                    })
                elif tool_use.name == "color_embedding":
                    color_by = tool_use.input.get("color_by", "")
                    await websocket.send_json({
                        "type": "agent_artifact",
                        "artifact_type": "color_embedding",
                        "color_by": color_by,
                    })
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": tool_use.id,
                        "content": f"Embedding colored by '{color_by}'.",
                    })
                elif tool_use.name == "show_structure":
                    cell_id = tool_use.input.get("cell_id", "")
                    chrom = tool_use.input.get("chrom", "")
                    await websocket.send_json({
                        "type": "agent_artifact",
                        "artifact_type": "show_structure",
                        "cell_id": cell_id,
                        "chrom": chrom,
                    })
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": tool_use.id,
                        "content": f"Showing 3D structure for cell '{cell_id}'"
                                   + (f", {chrom}" if chrom else "") + ".",
                    })
                elif tool_use.name == "color_structure":
                    color_by = tool_use.input.get("color_by", "")
                    await websocket.send_json({
                        "type": "agent_artifact",
                        "artifact_type": "color_structure",
                        "color_by": color_by,
                    })
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": tool_use.id,
                        "content": f"3D structure colored by '{color_by}'.",
                    })
                elif tool_use.name == "export_view":
                    fmt = (tool_use.input.get("format") or "png").lower()
                    if fmt not in ("png", "pdf"):
                        fmt = "png"
                    await websocket.send_json({
                        "type": "agent_artifact",
                        "artifact_type": "export_view",
                        "format": fmt,
                    })
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": tool_use.id,
                        "content": f"Triggered export of the current view as {fmt.upper()}. "
                                   "The download will start in the user's browser.",
                    })
                else:
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": tool_use.id,
                        "content": json.dumps({"error": f"Unknown tool: {tool_use.name}"})
                    })

            # Add tool results to history and continue loop
            conversation_history.append({
                "role": "user",
                "content": tool_results
            })
            # Continue the loop for Claude to process tool results
            continue

        # If stop_reason is "end_turn" or no more tool calls, we're done
        break
