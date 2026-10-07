"""Control channel: let code and agents drive the open browser page (see ``API.md`` → *Control*).

The page stays the owner of what is on screen.  A caller (``uchrom_browser.connect()``, a test, a
script) posts an action; the server forwards it to the active page over Server-Sent Events; the page
runs it with the same functions as its GUI (``frontend/src/actions.ts``) and posts the result back,
which the server returns to the caller.  The actions are defined once in ``ui_tools.json``, which is
also what the page registers as WebMCP tools.
"""

import asyncio
import itertools
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, AsyncIterator, Dict, List, Optional

TOOLS_PATH = Path(__file__).with_name("ui_tools.json")
KEEPALIVE_S = 15.0


def load_tools() -> Dict[str, Any]:
    return json.loads(TOOLS_PATH.read_text())


class NoPage(RuntimeError):
    """No browser page is connected."""


class ActionError(RuntimeError):
    """The page ran the action and reported an error."""


@dataclass
class _Page:
    id: str
    queue: asyncio.Queue
    since: float = field(default_factory=time.time)
    active_at: float = field(default_factory=time.time)


class ActionBroker:
    """Routes actions to the most recently active page and waits for its result."""

    def __init__(self):
        self._pages: Dict[str, _Page] = {}
        self._pending: Dict[str, asyncio.Future] = {}
        self._ids = itertools.count(1)

    # -- pages -----------------------------------------------------------
    async def events(self, page_id: str) -> AsyncIterator[str]:
        page = _Page(page_id, asyncio.Queue())
        self._pages[page_id] = page
        try:
            yield f"event: hello\ndata: {json.dumps({'page': page_id})}\n\n"
            while True:
                try:
                    msg = await asyncio.wait_for(page.queue.get(), KEEPALIVE_S)
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
                    continue
                yield f"event: action\ndata: {json.dumps(msg)}\n\n"
        finally:
            if self._pages.get(page_id) is page:
                del self._pages[page_id]

    def mark_active(self, page_id: str) -> bool:
        page = self._pages.get(page_id)
        if page:
            page.active_at = time.time()
        return page is not None

    def pages(self) -> List[Dict[str, Any]]:
        order = sorted(self._pages.values(), key=lambda p: -p.active_at)
        return [{"page": p.id, "since": p.since, "active_at": p.active_at, "active": i == 0}
                for i, p in enumerate(order)]

    # -- actions ---------------------------------------------------------
    async def call(self, name: str, args: Dict[str, Any], timeout: float = 30.0,
                   page_id: Optional[str] = None) -> Any:
        if page_id is not None:
            page = self._pages.get(page_id)
        else:
            page = max(self._pages.values(), key=lambda p: p.active_at, default=None)
        if page is None:
            raise NoPage("no browser page is connected; open the browser (python -m uchrom_browser …)")
        action_id = f"a{next(self._ids)}"
        fut = asyncio.get_running_loop().create_future()
        self._pending[action_id] = fut
        await page.queue.put({"id": action_id, "name": name, "args": args or {}})
        try:
            ok, payload = await asyncio.wait_for(fut, timeout)
        finally:
            self._pending.pop(action_id, None)
        if not ok:
            raise ActionError(str(payload))
        return payload

    def resolve(self, action_id: str, ok: bool, payload: Any) -> bool:
        fut = self._pending.get(action_id)
        if fut is None or fut.done():
            return False
        fut.set_result((ok, payload))
        return True


_MODELS = None


def _models():
    """Request bodies (module-level classes, so FastAPI resolves them; pydantic imported lazily)."""
    global _MODELS
    if _MODELS is None:
        from pydantic import BaseModel

        class ActionRequest(BaseModel):
            name: str
            args: Dict[str, Any] = {}
            timeout: float = 30.0
            page: Optional[str] = None

        class ResultRequest(BaseModel):
            ok: bool = True
            result: Any = None
            error: Optional[str] = None

        _MODELS = (ActionRequest, ResultRequest)
    return _MODELS


def add_routes(app, broker: ActionBroker) -> None:
    """Mount the control endpoints on a FastAPI app."""
    from fastapi import HTTPException
    from fastapi.responses import StreamingResponse

    ActionRequest, ResultRequest = _models()  # no `from __future__ import annotations` here: FastAPI
    #                                           must see these classes, not their names
    tools = load_tools()
    names = {t["name"] for t in tools["tools"]}

    @app.get("/api/control/tools")
    def control_tools() -> Dict[str, Any]:
        return tools

    @app.get("/api/control/pages")
    def control_pages() -> List[Dict[str, Any]]:
        return broker.pages()

    @app.get("/api/control/events")
    async def control_events(page: str) -> StreamingResponse:
        return StreamingResponse(broker.events(page), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    @app.post("/api/control/active")
    def control_active(page: str) -> Dict[str, Any]:
        return {"ok": broker.mark_active(page)}

    @app.post("/api/control/actions")
    async def control_action(req: ActionRequest) -> Dict[str, Any]:
        if req.name not in names:
            raise HTTPException(404, f"unknown action: {req.name}")
        try:
            result = await broker.call(req.name, req.args, req.timeout, req.page)
        except NoPage as exc:
            raise HTTPException(409, str(exc)) from None
        except asyncio.TimeoutError:
            raise HTTPException(504, f"the page did not answer {req.name} within {req.timeout:g} s") from None
        except ActionError as exc:
            raise HTTPException(422, str(exc)) from None
        return {"ok": True, "result": result}

    @app.post("/api/control/results/{action_id}")
    def control_result(action_id: str, req: ResultRequest) -> Dict[str, Any]:
        return {"accepted": broker.resolve(action_id, req.ok, req.result if req.ok else req.error)}
