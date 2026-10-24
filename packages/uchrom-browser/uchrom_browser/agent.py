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
from starlette.requests import Request

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
    actions: List[AgentAction] = Field(min_length=1)


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
    before_state: Optional[Dict[str, Any]] = field(default=None, repr=False)
    after_state: Optional[Dict[str, Any]] = field(default=None, repr=False)
    undo_reason: Optional[str] = None
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
        if self.after_state is not None:
            out["after_state"] = copy.deepcopy(self.after_state)
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
        if not actions:
            raise AgentInputError("a plan must contain at least one action")
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
            try:
                try:
                    await self.broker.call("__agent_lease__", {"active": True}, page_id=plan.page_id)
                except (ActionError, NoPage, asyncio.TimeoutError) as exc:
                    raise AgentConflict(f"cannot acquire page lease: {exc}") from None
                result = await self._apply_plan(plan)
            finally:
                try:
                    await self.broker.call("__agent_lease__", {"active": False}, page_id=plan.page_id)
                except Exception as exc:  # noqa: BLE001
                    plan.status = "failed"
                    plan.results.append({"name": "__agent_lease__", "ok": False,
                                         "error": f"lease release failed: {exc}"})
                    plan.undo_reason = plan.undo_reason or f"The page lease could not be released: {exc}"
                    try:
                        await self.broker.call("__agent_clear_lease__", {}, page_id=plan.page_id)
                    except Exception:
                        pass
                    if 'result' not in locals():
                        return plan
            return result

    async def _apply_plan(self, plan: PendingPlan) -> PendingPlan:
            current = await self._read(plan.page_id)
            if current["state_revision"] != plan.expected_revision:
                plan.status = "stale"
                plan.state_revision = current["state_revision"]
                plan.canonical = current
                raise AgentConflict(f"stale revision: expected {plan.expected_revision}, current {current['state_revision']}")
            plan.results = []
            try:
                plan.before_state = await self.broker.call("__agent_snapshot__", {}, page_id=plan.page_id)
                if not isinstance(plan.before_state, dict) or not plan.before_state.get("dataset_id"):
                    plan.before_state = None
                    plan.undo_reason = "The page did not provide a restorable UI snapshot."
                elif any(action["name"] == "select_cells" for action in plan.actions):
                    plan.undo_reason = "select_cells registers a group on the data service, which this UI undo cannot remove."
            except Exception as exc:  # noqa: BLE001
                plan.undo_reason = f"The page could not capture a UI snapshot: {exc}"

            revision = plan.expected_revision
            canonical = current
            for action in plan.actions:
                # Read the canonical page immediately before each mutation. After a
                # successful action, the revision rolls forward to its readback.
                try:
                    current = await self._read(plan.page_id)
                except AgentConflict as exc:
                    plan.status = "failed"
                    plan.state_revision = self._known_revision(plan.page_id)
                    plan.results.append({"name": "describe_workspace", "ok": False, "error": str(exc)})
                    return plan
                if current["state_revision"] != revision:
                    plan.status = "stale"
                    plan.state_revision = current["state_revision"]
                    plan.canonical = current
                    plan.results.append({"name": "revision_check", "ok": False,
                                         "error": f"stale revision before {action['name']}"})
                    return plan
                try:
                    result = await self.broker.call(action["name"], action["args"], page_id=plan.page_id, agent_mutation=True)
                    plan.results.append({"name": action["name"], "args": copy.deepcopy(action["args"]), "ok": True, "result": result})
                except Exception as exc:  # noqa: BLE001
                    plan.results.append({"name": action["name"], "args": copy.deepcopy(action["args"]), "ok": False, "error": str(exc)})
                    plan.status = "failed"
                    await self._rollback_after_failure(plan)
                    return plan
                try:
                    canonical = await self._read(plan.page_id)
                    revision = canonical["state_revision"]
                except AgentConflict as exc:
                    plan.status = "failed"
                    plan.results.append({"name": "describe_workspace", "ok": False, "error": str(exc)})
                    await self._rollback_after_failure(plan)
                    return plan
            try:
                canonical = await self._read(plan.page_id)
            except AgentConflict as exc:
                plan.status = "failed"
                plan.state_revision = revision
                plan.canonical = copy.deepcopy(canonical)
                plan.results.append({"name": "describe_workspace", "ok": False, "error": str(exc)})
                await self._rollback_after_failure(plan)
                return plan
            plan.status = "applied"
            plan.state_revision = canonical["state_revision"]
            plan.canonical = canonical
            await self._capture_after_state(plan)
            return plan

    def _known_revision(self, page_id: str) -> str:
        session = self.sessions.get(page_id)
        return session.revision if session else ""

    async def _readback_after_failure(self, plan: PendingPlan) -> None:
        try:
            canonical = await self._read(plan.page_id)
            plan.canonical = canonical
            plan.state_revision = canonical["state_revision"]
        except AgentConflict as exc:
            plan.results.append({"name": "describe_workspace", "ok": False, "error": str(exc)})

    @staticmethod
    def _canonical_payload(snapshot: Dict[str, Any]) -> Dict[str, Any]:
        return {key: copy.deepcopy(value) for key, value in snapshot.items()
                if key not in {"page_id", "state_revision", "source"}}

    async def _capture_after_state(self, plan: PendingPlan) -> None:
        try:
            plan.after_state = await self.broker.call("__agent_snapshot__", {}, page_id=plan.page_id)
        except Exception as exc:  # noqa: BLE001
            plan.undo_reason = plan.undo_reason or f"The page could not capture the resulting UI snapshot: {exc}"
            plan.results.append({"name": "__agent_snapshot__", "ok": False, "error": str(exc)})

    async def _rollback_after_failure(self, plan: PendingPlan) -> None:
        """Restore the pre-plan UI once after a mutation failure, then read back canonical state."""
        if plan.before_state is None:
            plan.results.append({"name": "rollback", "ok": False,
                                 "error": "no restorable pre-plan UI snapshot was captured"})
            await self._capture_after_state(plan)
            await self._readback_after_failure(plan)
            return

        try:
            current = await self._read(plan.page_id)
        except AgentConflict as exc:
            plan.results.append({"name": "rollback", "ok": False,
                                 "error": f"cannot read current canonical state before rollback: {exc}"})
            plan.undo_reason = plan.undo_reason or f"Automatic rollback could not verify the current page state: {exc}"
            await self._capture_after_state(plan)
            await self._readback_after_failure(plan)
            return

        try:
            restored = await self.broker.call("__agent_restore__", {
                "state": plan.before_state,
                "expected_canonical": self._canonical_payload(current),
            }, page_id=plan.page_id, agent_mutation=True)
            plan.results.append({"name": "rollback", "ok": True, "result": restored})
        except Exception as exc:  # noqa: BLE001
            plan.results.append({"name": "rollback", "ok": False, "error": str(exc)})
            plan.undo_reason = plan.undo_reason or f"Automatic rollback failed; partial page changes may remain: {exc}"
        await self._capture_after_state(plan)
        await self._readback_after_failure(plan)

    def status(self, plan_id: str) -> PendingPlan:
        return self._plan(plan_id)

    def history(self, page_id: str) -> List[Dict[str, Any]]:
        with self._plan_lock:
            plans = [p for p in self.plans.values() if p.page_id == page_id and p.status in {"applied", "failed", "stale", "undone"}]
        plans.sort(key=lambda p: p.created_at, reverse=True)
        latest_applied = next((p.plan_id for p in plans if p.status in {"applied", "undone"}), None)
        result = []
        for plan in plans[:20]:
            can_undo = (plan.plan_id == latest_applied and plan.status == "applied" and plan.before_state is not None
                        and plan.after_state is not None and plan.undo_reason is None)
            item = plan.as_dict()
            item["can_undo"] = can_undo
            if plan.undo_reason:
                item["undo_reason"] = plan.undo_reason
            result.append(item)
        return result

    async def undo(self, plan_id: str, page_id: str, expected_revision: str) -> PendingPlan:
        async with self._apply_lock:
            plan = self._plan(plan_id)
            if plan.page_id != page_id:
                raise AgentConflict("undo page does not match the plan page")
            history = self.history(page_id)
            if not history or history[0]["plan_id"] != plan_id or not history[0]["can_undo"]:
                raise AgentConflict(history[0].get("undo_reason", "only the latest reversible applied plan can be undone") if history else "no applied plan to undo")
            try:
                await self.broker.call("__agent_lease__", {"active": True}, page_id=page_id)
                current = await self._read(page_id)
                if current["state_revision"] != expected_revision or current["state_revision"] != plan.state_revision:
                    raise AgentConflict(f"stale revision: expected {plan.state_revision}, current {current['state_revision']}")
                await self.broker.call("__agent_restore__", {
                    "state": plan.before_state,
                    "expected_canonical": (plan.after_state or {}).get("canonical", plan.canonical),
                }, page_id=page_id, agent_mutation=True)
                canonical = await self._read(page_id, force_increment=True)
                plan.status = "undone"
                plan.state_revision = canonical["state_revision"]
                plan.canonical = canonical
                result = plan
            finally:
                try:
                    await self.broker.call("__agent_lease__", {"active": False}, page_id=page_id)
                except Exception as exc:  # noqa: BLE001
                    plan.status = "failed"
                    plan.results.append({"name": "__agent_lease__", "ok": False,
                                         "error": f"lease release failed: {exc}"})
                    plan.undo_reason = plan.undo_reason or f"The page lease could not be released: {exc}"
                    try:
                        await self.broker.call("__agent_clear_lease__", {}, page_id=page_id)
                    except Exception:
                        pass
                    if 'result' not in locals():
                        return plan
            return result


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


def add_routes(app, state: AgentState, security=None) -> None:
    """Mount local-only agent endpoints."""
    from fastapi import HTTPException, Query
    from .control import LocalSecurity

    security = security or LocalSecurity()

    def conflict(exc: AgentConflict) -> HTTPException:
        return HTTPException(409, str(exc))

    @app.get("/api/agent/pages")
    def agent_pages(request: Request) -> List[Dict[str, Any]]:
        security._loopback(request)
        pinned = set(state.sessions)
        return [{**page, "pinned": page.get("page") in pinned} for page in state.broker.pages()]

    @app.post("/api/agent/attach")
    def agent_attach(request: Request, req: AttachRequest) -> Dict[str, Any]:
        security._loopback(request)
        try:
            session = state.attach(req.page_id)
        except AgentConflict as exc:
            raise conflict(exc) from None
        return {"page_id": session.page_id, "state_revision": session.revision, "status": "attached"}

    @app.get("/api/agent/snapshot")
    async def agent_snapshot(request: Request, page: Optional[str] = Query(None)) -> Dict[str, Any]:
        security._loopback(request)
        try:
            return await state.snapshot(page or "")
        except AgentConflict as exc:
            raise conflict(exc) from None

    @app.post("/api/agent/plans")
    async def agent_propose(request: Request, req: PlanRequest) -> Dict[str, Any]:
        security._loopback(request)
        try:
            return (await state.propose(req.page_id, req.expected_revision, req.actions)).as_dict()
        except AgentConflict as exc:
            raise conflict(exc) from None
        except AgentInputError as exc:
            raise HTTPException(422, str(exc)) from None
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from None

    @app.get("/api/agent/plans")
    def agent_plans(request: Request, page: Optional[str] = Query(None)) -> List[Dict[str, Any]]:
        security._loopback(request)
        with state._plan_lock:
            plans = list(state.plans.values())
        if page:
            plans = [plan for plan in plans if plan.page_id == page]
        return [plan.as_dict() for plan in plans if plan.status in {"pending", "approved"}]

    @app.get("/api/agent/history")
    def agent_history(request: Request, page: str) -> List[Dict[str, Any]]:
        security._loopback(request)
        return state.history(page)

    @app.get("/api/agent/plans/{plan_id}")
    def agent_status(request: Request, plan_id: str) -> Dict[str, Any]:
        security._loopback(request)
        try:
            return state.status(plan_id).as_dict()
        except AgentConflict as exc:
            raise conflict(exc) from None

    @app.post("/api/agent/ui/plans/{plan_id}/approve")
    async def agent_approve(request: Request, plan_id: str) -> Dict[str, Any]:
        security.verify(request, csrf=True, origin=True)
        try:
            return (await state.approve(plan_id)).as_dict()
        except AgentConflict as exc:
            raise conflict(exc) from None

    @app.post("/api/agent/ui/plans/{plan_id}/reject")
    def agent_reject(request: Request, plan_id: str) -> Dict[str, Any]:
        security.verify(request, csrf=True, origin=True)
        try:
            return state.reject(plan_id).as_dict()
        except AgentConflict as exc:
            raise conflict(exc) from None

    @app.post("/api/agent/ui/plans/{plan_id}/apply")
    async def agent_apply(request: Request, plan_id: str) -> Dict[str, Any]:
        security.verify(request, csrf=True, origin=True)
        try:
            return (await state.apply(plan_id)).as_dict()
        except AgentConflict as exc:
            raise conflict(exc) from None

    @app.post("/api/agent/ui/plans/{plan_id}/undo")
    async def agent_undo(request: Request, plan_id: str, page_id: str, expected_revision: str) -> Dict[str, Any]:
        security.verify(request, csrf=True, origin=True)
        try:
            return (await state.undo(plan_id, page_id, expected_revision)).as_dict()
        except AgentConflict as exc:
            raise conflict(exc) from None
