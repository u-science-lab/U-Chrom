"""Local, process-local agent control state for the browser WebUI.

The agent layer pins a page explicitly, reads the page's canonical workspace through the
existing :class:`~uchrom_browser.control.ActionBroker`, and turns mutations into plans that
must be approved by the local WebUI before execution.
"""

from __future__ import annotations

import asyncio
import copy
import itertools
import json
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from .control import ActionBroker, ActionError, NoPage, load_tools


class AgentConflict(RuntimeError):
    """A page pin, revision, or plan state prevents the requested operation."""


class AgentInputError(ValueError):
    """An action or plan request is malformed."""


class AgentAction(BaseModel):
    name: str
    args: Dict[str, Any] = Field(default_factory=dict)


class AttachRequest(BaseModel):
    page_id: str


class PlanRequest(BaseModel):
    page_id: str
    expected_revision: str
    actions: List[AgentAction]


@dataclass
class AgentSession:
    page_id: str
    state_revision: int = 0
    canonical: Optional[Dict[str, Any]] = None
    attached_at: float = field(default_factory=time.time)

    @property
    def revision(self) -> str:
        return f"r_{self.state_revision}"


@dataclass
class PendingPlan:
    plan_id: str
    page_id: str
    expected_revision: str
    actions: List[Dict[str, Any]]
    status: str = "pending"
    results: List[Dict[str, Any]] = field(default_factory=list)
    state_revision: Optional[str] = None
    canonical: Optional[Dict[str, Any]] = None
    created_at: float = field(default_factory=time.time)

    def as_dict(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {
            "plan_id": self.plan_id,
            "status": self.status,
            "page_id": self.page_id,
            "expected_revision": self.expected_revision,
            "actions": copy.deepcopy(self.actions),
        }
        if self.results:
            out["results"] = copy.deepcopy(self.results)
        if self.state_revision is not None:
            out["state_revision"] = self.state_revision
        if self.canonical is not None:
            out["canonical"] = copy.deepcopy(self.canonical)
        return out


class AgentState:
    """In-memory agent sessions and plans owned by one local FastAPI process."""

    MAX_PLANS = 100

    def __init__(self, broker: ActionBroker):
        self.broker = broker
        self.sessions: Dict[str, AgentSession] = {}
        self.plans: Dict[str, PendingPlan] = {}
        self._ids = itertools.count(1)
        self._apply_lock = asyncio.Lock()
        self._plan_lock = threading.RLock()
        tools = load_tools().get("tools", [])
        self._tools = {tool["name"]: tool for tool in tools}

    def _page_connected(self, page_id: str) -> bool:
        return any(page.get("page") == page_id for page in self.broker.pages())

    def _require_session(self, page_id: str) -> AgentSession:
        if not page_id:
            raise AgentConflict("an explicit page_id is required")
        session = self.sessions.get(page_id)
        if session is None:
            raise AgentConflict(f"page is not pinned: {page_id}")
        if not self._page_connected(page_id):
            raise AgentConflict(f"page is disconnected: {page_id}")
        return session

    def attach(self, page_id: str) -> AgentSession:
        if not page_id or not self._page_connected(page_id):
            raise AgentConflict(f"page is not connected: {page_id}")
        session = self.sessions.get(page_id)
        if session is None:
            session = AgentSession(page_id=page_id)
            self.sessions[page_id] = session
        return session

    @staticmethod
    def _canonicalize(raw: Any) -> Dict[str, Any]:
        if not isinstance(raw, dict):
            raise AgentInputError("describe_workspace must return an object")
        # Keep the page result as the canonical source; only add agent metadata.
        return copy.deepcopy(raw)

    async def _read(self, page_id: str, *, force_increment: bool = False) -> Dict[str, Any]:
        session = self._require_session(page_id)
        try:
            raw = await self.broker.call("describe_workspace", {}, page_id=page_id)
        except NoPage as exc:
            raise AgentConflict(str(exc)) from None
        except (ActionError, asyncio.TimeoutError) as exc:
            raise AgentConflict(f"cannot read page state: {exc}") from None
        canonical = self._canonicalize(raw)
        if session.canonical is None:
            session.canonical = canonical
        elif canonical != session.canonical or force_increment:
            session.state_revision += 1
            session.canonical = canonical
        result = copy.deepcopy(canonical)
        result.update({"page_id": page_id, "state_revision": session.revision, "source": "page_canonical"})
        return result

    async def snapshot(self, page_id: str) -> Dict[str, Any]:
        return await self._read(page_id)

    async def propose(self, page_id: str, expected_revision: str, actions: List[AgentAction]) -> PendingPlan:
        current = await self._read(page_id)
        if expected_revision != current["state_revision"]:
            raise AgentConflict(f"stale revision: expected {expected_revision}, current {current['state_revision']}")
        normalized: List[Dict[str, Any]] = []
        for action in actions:
            tool = self._tools.get(action.name)
            if tool is None:
                raise AgentInputError(f"unknown action: {action.name}")
            _validate_schema(action.args, tool.get("inputSchema", {}), f"{action.name}.args")
            normalized.append({"name": action.name, "args": copy.deepcopy(action.args)})
        plan = PendingPlan(
            plan_id=f"p{next(self._ids)}",
            page_id=page_id,
            expected_revision=expected_revision,
            actions=normalized,
        )
        with self._plan_lock:
            self.plans[plan.plan_id] = plan
            while len(self.plans) > self.MAX_PLANS:
                self.plans.pop(next(iter(self.plans)))
        return plan

    def _plan(self, plan_id: str) -> PendingPlan:
        with self._plan_lock:
            try:
                return self.plans[plan_id]
            except KeyError:
                raise AgentConflict(f"unknown plan: {plan_id}") from None

    async def approve(self, plan_id: str) -> PendingPlan:
        with self._plan_lock:
            plan = self._plan(plan_id)
            if plan.status != "pending":
                raise AgentConflict(f"plan is {plan.status}")
        current = await self._read(plan.page_id)
        with self._plan_lock:
            # Reject may run on another request thread while the page snapshot is in flight.
            if plan.status != "pending":
                raise AgentConflict(f"plan is {plan.status}")
            if current["state_revision"] != plan.expected_revision:
                plan.status = "stale"
                raise AgentConflict(f"stale revision: expected {plan.expected_revision}, current {current['state_revision']}")
            plan.status = "approved"
        return plan

    def reject(self, plan_id: str) -> PendingPlan:
        with self._plan_lock:
            plan = self._plan(plan_id)
            if plan.status != "pending":
                raise AgentConflict(f"plan is {plan.status}")
            plan.status = "rejected"
            return plan

    async def apply(self, plan_id: str) -> PendingPlan:
        async with self._apply_lock:
            plan = self._plan(plan_id)
            if plan.status != "approved":
                raise AgentConflict(f"plan is not approved: {plan.status}")
            current = await self._read(plan.page_id)
            if current["state_revision"] != plan.expected_revision:
                plan.status = "stale"
                raise AgentConflict(f"stale revision: expected {plan.expected_revision}, current {current['state_revision']}")
            plan.results = []
            for action in plan.actions:
                try:
                    result = await self.broker.call(action["name"], action["args"], page_id=plan.page_id)
                    plan.results.append({"name": action["name"], "args": copy.deepcopy(action["args"]), "ok": True, "result": result})
                except Exception as exc:  # noqa: BLE001
                    plan.results.append({"name": action["name"], "args": copy.deepcopy(action["args"]), "ok": False, "error": str(exc)})
                    plan.status = "failed"
                    return plan
            try:
                canonical = await self._read(plan.page_id, force_increment=True)
            except AgentConflict as exc:
                plan.status = "failed"
                plan.results.append({"name": "describe_workspace", "ok": False, "error": str(exc)})
                return plan
            plan.status = "applied"
            plan.state_revision = canonical["state_revision"]
            plan.canonical = canonical
            return plan

    def status(self, plan_id: str) -> PendingPlan:
        return self._plan(plan_id)


def _validate_schema(value: Any, schema: Dict[str, Any], path: str) -> None:
    """Validate the JSON Schema subset used by ui_tools.json before accepting a plan."""
    expected = schema.get("type")
    matches = {
        "object": lambda v: isinstance(v, dict),
        "array": lambda v: isinstance(v, list),
        "string": lambda v: isinstance(v, str),
        "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
        "number": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
        "boolean": lambda v: isinstance(v, bool),
    }
    if expected in matches and not matches[expected](value):
        raise AgentInputError(f"{path} must be {expected}")
    if "enum" in schema and value not in schema["enum"]:
        choices = ", ".join(map(str, schema["enum"]))
        raise AgentInputError(f"{path} must be one of: {choices}")
    if isinstance(value, dict):
        for name in schema.get("required", []):
            if name not in value:
                raise AgentInputError(f"{path} requires: {name}")
        properties = schema.get("properties", {})
        for name, item in value.items():
            if name in properties:
                _validate_schema(item, properties[name], f"{path}.{name}")
    if isinstance(value, list) and "items" in schema:
        for index, item in enumerate(value):
            _validate_schema(item, schema["items"], f"{path}[{index}]")


def add_routes(app, state: AgentState) -> None:
    """Mount local-only agent endpoints."""
    from fastapi import HTTPException, Query

    def conflict(exc: AgentConflict) -> HTTPException:
        return HTTPException(409, str(exc))

    @app.get("/api/agent/pages")
    def agent_pages() -> List[Dict[str, Any]]:
        pinned = set(state.sessions)
        return [{**page, "pinned": page.get("page") in pinned} for page in state.broker.pages()]

    @app.post("/api/agent/attach")
    def agent_attach(req: AttachRequest) -> Dict[str, Any]:
        try:
            session = state.attach(req.page_id)
        except AgentConflict as exc:
            raise conflict(exc) from None
        return {"page_id": session.page_id, "state_revision": session.revision, "status": "attached"}

    @app.get("/api/agent/snapshot")
    async def agent_snapshot(page: Optional[str] = Query(None)) -> Dict[str, Any]:
        try:
            return await state.snapshot(page or "")
        except AgentConflict as exc:
            raise conflict(exc) from None

    @app.post("/api/agent/plans")
    async def agent_propose(req: PlanRequest) -> Dict[str, Any]:
        try:
            return (await state.propose(req.page_id, req.expected_revision, req.actions)).as_dict()
        except AgentConflict as exc:
            raise conflict(exc) from None
        except AgentInputError as exc:
            raise HTTPException(422, str(exc)) from None

    @app.get("/api/agent/plans/{plan_id}")
    def agent_status(plan_id: str) -> Dict[str, Any]:
        try:
            return state.status(plan_id).as_dict()
        except AgentConflict as exc:
            raise conflict(exc) from None

    @app.post("/api/agent/plans/{plan_id}/approve")
    async def agent_approve(plan_id: str) -> Dict[str, Any]:
        try:
            return (await state.approve(plan_id)).as_dict()
        except AgentConflict as exc:
            raise conflict(exc) from None

    @app.post("/api/agent/plans/{plan_id}/reject")
    def agent_reject(plan_id: str) -> Dict[str, Any]:
        try:
            return state.reject(plan_id).as_dict()
        except AgentConflict as exc:
            raise conflict(exc) from None

    @app.post("/api/agent/plans/{plan_id}/apply")
    async def agent_apply(plan_id: str) -> Dict[str, Any]:
        try:
            return (await state.apply(plan_id)).as_dict()
        except AgentConflict as exc:
            raise conflict(exc) from None
