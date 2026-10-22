"""Local agent page pin, revision and approval API tests."""

import json
import socket
import threading
import time

import pytest

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
    assert c.post("/api/agent/plans", json={"page_id": "ptest", "expected_revision": "r_0", "actions": []}).status_code == 409
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


def test_apply_requires_user_approval_and_records_results(server):
    state = {"dataset": {"id": "d1"}, "views": [], "locus": None}
    def handler(name, args):
        if name == "describe_workspace":
            return state
        state["last"] = {"name": name, "args": args}
        return {"applied": name, **args}
    page = _page(server, handler)
    c = API(server)
    c.post("/api/agent/attach", json={"page_id": "ptest"})
    plan = c.post("/api/agent/plans", json={"page_id": "ptest", "expected_revision": "r_0",
        "actions": [{"name": "set_locus", "args": {"chrom": "chr1"}}, {"name": "arrange", "args": {"layout": "tabs"}}]}).json()
    assert c.post(f"/api/agent/plans/{plan['plan_id']}/apply").status_code == 409
    assert c.post(f"/api/agent/plans/{plan['plan_id']}/approve").status_code == 200
    r = c.post(f"/api/agent/plans/{plan['plan_id']}/apply")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "applied"
    assert body["page_id"] == "ptest"
    assert len(body["results"]) == 2
    assert [x["ok"] for x in body["results"]] == [True, True]
    assert body["state_revision"] == "r_1"
    assert [x["name"] for x in page.seen] == ["describe_workspace", "describe_workspace", "describe_workspace", "set_locus", "arrange", "describe_workspace"]


def test_reject_and_stale_plan_do_not_execute_actions(server):
    state = {"dataset": {}, "views": [], "locus": None}
    def handler(name, args):
        if name == "describe_workspace":
            return state
        state["mutated"] = True
        return {"ok": True}
    page = _page(server, handler)
    c = API(server)
    c.post("/api/agent/attach", json={"page_id": "ptest"})
    plan = c.post("/api/agent/plans", json={"page_id": "ptest", "expected_revision": "r_0", "actions": [{"name": "arrange", "args": {"layout": "grid"}}]}).json()
    assert c.post(f"/api/agent/plans/{plan['plan_id']}/reject").json()["status"] == "rejected"
    assert not state.get("mutated")
    plan2 = c.post("/api/agent/plans", json={"page_id": "ptest", "expected_revision": "r_0", "actions": [{"name": "arrange", "args": {"layout": "grid"}}]}).json()
    state["locus"] = {"chrom": "chr2", "start": 0, "end": 10}
    assert c.post(f"/api/agent/plans/{plan2['plan_id']}/approve").status_code == 409
    assert not state.get("mutated")
    assert all(x["name"] == "describe_workspace" for x in page.seen)


def test_action_failure_does_not_retry(server):
    state = {"dataset": {}, "views": [], "locus": None}
    calls = []
    def handler(name, args):
        calls.append(name)
        if name == "describe_workspace":
            return state
        if name == "arrange":
            raise ValueError("boom")
        return {"applied": name}
    page = _page(server, handler)
    c = API(server)
    c.post("/api/agent/attach", json={"page_id": "ptest"})
    plan = c.post("/api/agent/plans", json={"page_id": "ptest", "expected_revision": "r_0", "actions": [
        {"name": "set_locus", "args": {"chrom": "chr1"}}, {"name": "arrange", "args": {"layout": "grid"}}]}).json()
    c.post(f"/api/agent/plans/{plan['plan_id']}/approve")
    r = c.post(f"/api/agent/plans/{plan['plan_id']}/apply")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "failed"
    assert body["results"][0]["ok"] is True
    assert body["results"][1]["ok"] is False
    assert calls.count("set_locus") == 1
    assert calls.count("arrange") == 1
