"""Local agent page pin, revision and approval API tests."""

import json
import socket
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import pytest
import requests

pytest.importorskip("fastapi")
pytest.importorskip("httpx")
pytest.importorskip("requests")
pytest.importorskip("uvicorn")

from uchrom_browser import create_app


class FakePage(threading.Thread):
    def __init__(self, base, handler, page="ptest"):
        super().__init__(daemon=True)
        self.base, self.handler, self.page = base, handler, page
        self.seen = []
        self.ready = threading.Event()

    def run(self):
        import requests

        with requests.get(f"{self.base}/api/control/events", params={"page": self.page}, stream=True, timeout=30) as r:
            event = None
            for line in r.iter_lines(decode_unicode=True):
                if line.startswith("event: "):
                    event = line[7:]
                elif line.startswith("data: ") and event == "hello":
                    self.ready.set()
                elif line.startswith("data: ") and event == "action":
                    msg = json.loads(line[6:])
                    self.seen.append(msg)
                    try:
                        body = {"ok": True, "result": self.handler(msg["name"], msg["args"])}
                    except Exception as exc:  # noqa: BLE001
                        body = {"ok": False, "error": str(exc)}
                    requests.post(f"{self.base}/api/control/results/{msg['id']}", json=body, timeout=5)


def _free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def server():
    import requests
    import uvicorn

    port = _free_port()
    srv = uvicorn.Server(uvicorn.Config(create_app(), host="127.0.0.1", port=port, log_level="warning"))
    th = threading.Thread(target=srv.run, daemon=True)
    th.start()
    base = f"http://127.0.0.1:{port}"
    for _ in range(200):
        try:
            if requests.get(base + "/api/health", timeout=0.2).ok:
                break
        except requests.ConnectionError:
            time.sleep(0.05)
    yield base
    srv.should_exit = True
    th.join(5)



class API:
    def __init__(self, base):
        import requests
        self.base = base.rstrip("/")
        self.session = requests.Session()

    def get(self, path, **kwargs):
        return self.session.get(self.base + path, **kwargs)

    def post(self, path, **kwargs):
        return self.session.post(self.base + path, **kwargs)

def _page(server, handler):
    page = FakePage(server, handler)
    page.start()
    assert page.ready.wait(5)
    return page



def test_agent_snapshot_requires_explicit_page_and_returns_revision(server):
    state = {
        "dataset": {"id": "d1", "name": "toy"},
        "views": [{"pane": "P1", "type": "3d"}],
        "active_view": "P1",
        "layout": "tabs",
        "focus": {"cell": None, "group": None},
        "selection": {"group": "g1", "n_cells": 2},
        "saved_groups": [],
        "locus": {"chrom": "chr1", "start": 10, "end": 100},
    }
    page = _page(server, lambda name, args: state if name == "describe_workspace" else {})
    c = API(server)
    assert c.post("/api/agent/attach", json={"page_id": "ptest"}).status_code == 200
    r = c.get("/api/agent/snapshot", params={"page": "ptest"})
    assert r.status_code == 200
    body = r.json()
    assert body["page_id"] == "ptest"
    assert body["state_revision"] == "r_0"
    assert body["source"] == "page_canonical"
    assert body["dataset"] == state["dataset"]
    assert body["views"] == state["views"]
    assert body["locus"] == state["locus"]
    assert page.seen[-1]["name"] == "describe_workspace"


def test_propose_plan_requires_page_pin_and_expected_revision(server):
    _page(server, lambda name, args: {"dataset": {}, "views": [], "locus": None} if name == "describe_workspace" else {"ok": True})
    c = API(server)
    assert c.post("/api/agent/plans", json={"page_id": "ptest", "expected_revision": "r_0", "actions": [
        {"name": "arrange", "args": {"layout": "tabs"}},
    ]}).status_code == 409
    assert c.post("/api/agent/attach", json={"page_id": "ptest"}).status_code == 200
    actions = [{"name": "set_locus", "args": {"chrom": "chr1"}}, {"name": "arrange", "args": {"layout": "tabs"}}]
    r = c.post("/api/agent/plans", json={"page_id": "ptest", "expected_revision": "r_0", "actions": actions})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "pending"
    assert body["page_id"] == "ptest"
    assert body["expected_revision"] == "r_0"
    assert body["actions"] == actions
    assert c.post("/api/agent/plans", json={"page_id": "ptest", "expected_revision": "r_99", "actions": actions}).status_code == 409


def test_propose_rejects_invalid_action_schema_before_creating_plan(server):
    page = _page(server, lambda name, args: {"dataset": {}, "views": [], "locus": None})
    c = API(server)
    assert c.post("/api/agent/attach", json={"page_id": "ptest"}).status_code == 200
    r = c.post("/api/agent/plans", json={"page_id": "ptest", "expected_revision": "r_0", "actions": [
        {"name": "arrange", "args": {"layout": "sideways"}},
    ]})
    assert r.status_code == 422
    assert "layout" in r.json()["detail"]
    assert all(message["name"] == "describe_workspace" for message in page.seen)


def test_propose_rejects_empty_plan(server):
    _page(server, lambda name, args: {"dataset": {}, "views": [], "locus": None})
    c = API(server)
    assert c.post("/api/agent/attach", json={"page_id": "ptest"}).status_code == 200
    r = c.post("/api/agent/plans", json={"page_id": "ptest", "expected_revision": "r_0", "actions": []})
    assert r.status_code == 422
    assert "at least 1 item" in r.json()["detail"][0]["msg"]


def test_empty_plan_is_declared_in_openapi_as_invalid(server):
    schema = requests.get(server + "/api/openapi.json").json()
    actions = schema["components"]["schemas"]["PlanRequest"]["properties"]["actions"]
    assert actions["minItems"] == 1


def test_apply_releases_page_lease_when_lease_acquisition_fails(server):
    calls = []

    def handler(name, args):
        calls.append((name, args))
        if name == "describe_workspace":
            return {"dataset": {}, "views": [], "locus": None}
        if name == "__agent_lease__" and args["active"]:
            raise ValueError("lease unavailable")
        return {"ok": True}

    _page(server, handler)
    c = API(server)
    c.post("/api/agent/attach", json={"page_id": "ptest"})
    plan = c.post("/api/agent/plans", json={"page_id": "ptest", "expected_revision": "r_0", "actions": [
        {"name": "arrange", "args": {"layout": "grid"}},
    ]}).json()
    c.post(f"/api/agent/ui/plans/{plan['plan_id']}/approve")

    result = c.post(f"/api/agent/ui/plans/{plan['plan_id']}/apply")

    assert result.status_code == 409
    assert [(args["active"]) for name, args in calls if name == "__agent_lease__"] == [True, False]
    assert not any(name == "arrange" for name, _ in calls)
    assert c.get(f"/api/agent/plans/{plan['plan_id']}").json()["status"] == "approved"


def test_apply_requires_user_approval_and_records_results(server):
    state = {"dataset": {"id": "d1"}, "views": [], "locus": None}
    def handler(name, args):
        if name == "describe_workspace":
            return state
        if name == "__agent_lease__":
            return {"active": args["active"]}
        if name == "__agent_snapshot__":
            return {}
        state["last"] = {"name": name, "args": args}
        return {"applied": name, **args}
    page = _page(server, handler)
    c = API(server)
    c.post("/api/agent/attach", json={"page_id": "ptest"})
    plan = c.post("/api/agent/plans", json={"page_id": "ptest", "expected_revision": "r_0",
        "actions": [{"name": "set_locus", "args": {"chrom": "chr1"}}, {"name": "arrange", "args": {"layout": "tabs"}}]}).json()
    assert c.post(f"/api/agent/plans/{plan['plan_id']}/apply").status_code == 405
    assert c.post(f"/api/agent/ui/plans/{plan['plan_id']}/apply").status_code == 409
    assert c.post(f"/api/agent/ui/plans/{plan['plan_id']}/approve").status_code == 200
    r = c.post(f"/api/agent/ui/plans/{plan['plan_id']}/apply")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "applied"
    assert body["page_id"] == "ptest"
    assert len(body["results"]) == 2
    assert [x["ok"] for x in body["results"]] == [True, True]
    # The fake page mutates canonical state for each requested action, so the
    # revision advances once per actual state change (two actions -> r_2).
    assert body["state_revision"] == "r_2"
    public_seen = [x["name"] for x in page.seen if not x["name"].startswith("__agent_")]
    assert public_seen.count("set_locus") == 1
    assert public_seen.count("arrange") == 1
    assert public_seen.count("describe_workspace") >= 4


def test_reject_and_stale_plan_do_not_execute_actions(server):
    state = {"dataset": {}, "views": [], "locus": None}
    def handler(name, args):
        if name == "describe_workspace":
            return state
        if name == "__agent_lease__":
            return {"active": args["active"]}
        if name == "__agent_snapshot__":
            return {}
        state["mutated"] = True
        return {"ok": True}
    page = _page(server, handler)
    c = API(server)
    c.post("/api/agent/attach", json={"page_id": "ptest"})
    plan = c.post("/api/agent/plans", json={"page_id": "ptest", "expected_revision": "r_0", "actions": [{"name": "arrange", "args": {"layout": "grid"}}]}).json()
    assert c.post(f"/api/agent/ui/plans/{plan['plan_id']}/reject").json()["status"] == "rejected"
    assert not state.get("mutated")
    plan2 = c.post("/api/agent/plans", json={"page_id": "ptest", "expected_revision": "r_0", "actions": [{"name": "arrange", "args": {"layout": "grid"}}]}).json()
    state["locus"] = {"chrom": "chr2", "start": 0, "end": 10}
    assert c.post(f"/api/agent/ui/plans/{plan2['plan_id']}/approve").status_code == 409
    assert not state.get("mutated")
    assert all(x["name"] == "describe_workspace" for x in page.seen)


def test_reject_wins_when_approval_is_waiting_for_page_snapshot(server):
    pause_snapshot = threading.Event()
    snapshot_started = threading.Event()
    release_snapshot = threading.Event()

    def handler(name, args):
        if name == "describe_workspace":
            if pause_snapshot.is_set():
                snapshot_started.set()
                assert release_snapshot.wait(5)
            return {"dataset": {}, "views": [], "locus": None}
        return {"ok": True}

    _page(server, handler)
    c = API(server)
    assert c.post("/api/agent/attach", json={"page_id": "ptest"}).status_code == 200
    plan = c.post("/api/agent/plans", json={"page_id": "ptest", "expected_revision": "r_0", "actions": [
        {"name": "arrange", "args": {"layout": "grid"}},
    ]}).json()

    pause_snapshot.set()
    with ThreadPoolExecutor(max_workers=1) as pool:
        approving = pool.submit(c.post, f"/api/agent/ui/plans/{plan['plan_id']}/approve")
        assert snapshot_started.wait(5)
        rejected = c.post(f"/api/agent/ui/plans/{plan['plan_id']}/reject")
        assert rejected.status_code == 200
        assert rejected.json()["status"] == "rejected"
        release_snapshot.set()
        approved = approving.result(timeout=5)

    assert approved.status_code == 409
    assert c.get(f"/api/agent/plans/{plan['plan_id']}").json()["status"] == "rejected"


def test_action_failure_does_not_retry(server):
    state = {"dataset": {}, "views": [], "locus": None}
    calls = []
    def handler(name, args):
        calls.append(name)
        if name == "describe_workspace":
            return state
        if name == "__agent_lease__":
            return {"active": args["active"]}
        if name == "__agent_snapshot__":
            return {"dataset_id": "d1", "workspace": {}, "view": {}}
        if name == "arrange":
            raise ValueError("boom")
        return {"applied": name}
    page = _page(server, handler)
    c = API(server)
    c.post("/api/agent/attach", json={"page_id": "ptest"})
    plan = c.post("/api/agent/plans", json={"page_id": "ptest", "expected_revision": "r_0", "actions": [
        {"name": "set_locus", "args": {"chrom": "chr1"}}, {"name": "arrange", "args": {"layout": "grid"}}]}).json()
    c.post(f"/api/agent/ui/plans/{plan['plan_id']}/approve")
    r = c.post(f"/api/agent/ui/plans/{plan['plan_id']}/apply")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "failed"
    assert body["results"][0]["ok"] is True
    assert body["results"][1]["ok"] is False
    assert calls.count("set_locus") == 1
    assert calls.count("arrange") == 1


def test_apply_rechecks_revision_before_each_action_and_stops_when_page_changes(server):
    state = {"dataset": {}, "views": [], "locus": None}
    calls = []
    describes = 0

    def handler(name, args):
        nonlocal describes
        calls.append(name)
        if name == "describe_workspace":
            describes += 1
            result = dict(state)
            # Simulate a manual UI edit after the first plan action's readback.
            if describes == 5:
                state["layout"] = "tabs"
            return result
        if name.startswith("__agent_"):
            return {"ok": True}
        state["mutated"] = name
        if name == "set_locus":
            state["locus"] = {"chrom": "chr1", "start": 0, "end": 10}
        return {"ok": True}

    _page(server, handler)
    c = API(server)
    c.post("/api/agent/attach", json={"page_id": "ptest"})
    plan = c.post("/api/agent/plans", json={"page_id": "ptest", "expected_revision": "r_0", "actions": [
        {"name": "set_locus", "args": {"chrom": "chr1"}},
        {"name": "arrange", "args": {"layout": "grid"}},
    ]}).json()
    assert c.post(f"/api/agent/ui/plans/{plan['plan_id']}/approve").status_code == 200
    result = c.post(f"/api/agent/ui/plans/{plan['plan_id']}/apply")
    assert result.status_code == 200
    body = result.json()
    assert body["status"] == "stale"
    assert [item["name"] for item in body["results"]] == ["set_locus", "revision_check"]
    assert body["results"][0]["ok"] is True
    assert "arrange" not in calls


def test_failed_action_returns_canonical_readback_and_history(server):
    state = {"dataset": {}, "views": [], "locus": None}

    def handler(name, args):
        if name == "describe_workspace":
            return state
        if name == "__agent_lease__":
            return {"active": args["active"]}
        if name == "__agent_snapshot__":
            return {}
        raise ValueError("boom")

    _page(server, handler)
    c = API(server)
    c.post("/api/agent/attach", json={"page_id": "ptest"})
    plan = c.post("/api/agent/plans", json={"page_id": "ptest", "expected_revision": "r_0", "actions": [
        {"name": "arrange", "args": {"layout": "grid"}},
    ]}).json()
    c.post(f"/api/agent/ui/plans/{plan['plan_id']}/approve")
    result = c.post(f"/api/agent/ui/plans/{plan['plan_id']}/apply").json()
    assert result["status"] == "failed"
    assert result["state_revision"] == "r_0"
    assert result["canonical"]["source"] == "page_canonical"
    history = c.get("/api/agent/history", params={"page": "ptest"}).json()
    assert history[0]["plan_id"] == plan["plan_id"]
    assert history[0]["status"] == "failed"
    assert history[0]["canonical"]["source"] == "page_canonical"
    assert history[0]["state_revision"] == "r_0"


def test_history_supports_revision_checked_undo_for_latest_ui_plan(server):
    state = {"dataset": {"id": "d1"}, "views": [], "locus": None, "layout": "tabs"}
    ui_state = {"dataset_id": "d1", "workspace": {"layout": "tabs"}, "view": {"locus": None}}

    def handler(name, args):
        if name == "describe_workspace":
            return {key: value for key, value in state.items() if key != "dataset_id"}
        if name == "__agent_snapshot__":
            return {**ui_state, "canonical": {key: value for key, value in state.items() if key != "dataset_id"}}
        if name == "__agent_restore__":
            assert args["expected_canonical"] == {key: value for key, value in state.items() if key != "dataset_id"}
            state["layout"] = args["state"]["workspace"]["layout"]
            return {"ok": True}
        if name == "__agent_lease__":
            return {"active": args["active"]}
        if name == "arrange":
            state["layout"] = args["layout"]
            return {"layout": args["layout"]}
        raise AssertionError(name)

    _page(server, handler)
    c = API(server)
    c.post("/api/agent/attach", json={"page_id": "ptest"})
    plan = c.post("/api/agent/plans", json={"page_id": "ptest", "expected_revision": "r_0", "actions": [
        {"name": "arrange", "args": {"layout": "grid"}},
    ]}).json()
    c.post(f"/api/agent/ui/plans/{plan['plan_id']}/approve")
    applied = c.post(f"/api/agent/ui/plans/{plan['plan_id']}/apply").json()
    assert applied["status"] == "applied"
    history = c.get("/api/agent/history", params={"page": "ptest"}).json()
    assert history[0]["can_undo"] is True
    undone = c.post(f"/api/agent/ui/plans/{plan['plan_id']}/undo",
                    params={"page_id": "ptest", "expected_revision": applied["state_revision"]}).json()
    assert undone["status"] == "undone"
    assert state["layout"] == "tabs"


def test_workspace_and_agent_plan_surface_have_no_agent_approval_or_apply_tools(server):
    from uchrom_browser.client import connect

    ws = connect(server)
    assert not {"approve_plan", "reject_plan", "apply_plan", "undo_plan"} & set(dir(ws))
    assert not {"approve_plan", "apply_plan", "undo_plan"} & {tool["name"] for tool in ws.tools()}

    _page(server, lambda name, args: {"dataset": {}, "views": [], "locus": None})
    c = API(server)
    c.post("/api/agent/attach", json={"page_id": "ptest"})
    plan = c.post("/api/agent/plans", json={"page_id": "ptest", "expected_revision": "r_0", "actions": [
        {"name": "arrange", "args": {"layout": "grid"}},
    ]}).json()
    assert c.get("/api/agent/plans").json() == [plan]
    assert c.post(f"/api/agent/plans/{plan['plan_id']}/approve").status_code == 405
    assert c.post(f"/api/agent/plans/{plan['plan_id']}/apply").status_code == 405
