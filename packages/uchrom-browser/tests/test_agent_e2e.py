"""Real-data local agent loop over the browser control SSE channel."""

from __future__ import annotations

import json
import socket
import threading
import time
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("requests")
pytest.importorskip("uvicorn")

from uchrom_browser import create_app

FIXTURE = Path(__file__).parent / "fixtures" / "sim_cell1" / "sim_cell1.cdz"


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest.fixture
def server():
    import requests
    import uvicorn

    port = _free_port()
    srv = uvicorn.Server(uvicorn.Config(create_app(), host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=srv.run, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{port}"
    for _ in range(200):
        try:
            if requests.get(base + "/api/health", timeout=0.2).ok:
                break
        except requests.ConnectionError:
            time.sleep(0.05)
    yield base
    srv.should_exit = True
    thread.join(5)


@pytest.fixture
def real_page(server):
    page = RealDataPage(server)
    page.start()
    assert page.ready.wait(5)
    yield page
    page.stop()
    assert not page.is_alive(), "SSE page adapter did not stop before its server"


class RealDataPage(threading.Thread):
    """Small deterministic page adapter backed by the real sim_cell1 store."""

    def __init__(self, base: str, page: str = "sim-cell1"):
        super().__init__(daemon=True)
        self.base = base
        self.page = page
        self.ready = threading.Event()
        self.stopping = threading.Event()
        self.response = None
        self.seen: list[dict] = []
        self.state: dict = {}
        self.canonical_cells: list[str] = []

    def stop(self):
        self.stopping.set()
        response = self.response
        if response is not None:
            sock = getattr(getattr(getattr(getattr(response.raw, "_fp", None), "fp", None), "raw", None), "_sock", None)
            if sock is not None:
                try:
                    sock.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
            response.close()
        self.join(3)

    def run(self):
        import base64
        import requests
        from uchrom_browser.data import DatasetStore

        dataset = DatasetStore().load(FIXTURE)
        summary = dataset.summary()
        self.canonical_cells = [item["cell_id"] for item in dataset.cells()["cells"]]
        chromosome = next(item for item in summary["chroms"] if item["name"] == "chr15")
        self.state = {
            "dataset": {
                "id": summary["id"],
                "name": summary["name"],
                "path": summary["path"],
                "n_cells": summary["n_cells"],
                "n_spots": summary["n_spots"],
                "cell_fields": [],
                "embeddings": [],
                "tracks": [],
                "contact_maps": [item["key"] for item in summary["contact_maps"]],
            },
            "views": [{"pane": "P1", "type": "3d", "cells": "focus"}],
            "active_view": "P1",
            "layout": "tabs",
            "focus": {"cell": None, "group": None},
            "selection": {"group": None, "n_cells": len(self.canonical_cells)},
            "saved_groups": [],
            "locus": None,
        }

        def describe():
            return json.loads(json.dumps(self.state))

        def action(name: str, args: dict):
            if name == "describe_workspace":
                return describe()
            if name == "get_selection":
                return {"cells": list(self.canonical_cells), "group": None, "name": None, "source": "cell"}
            if name == "set_locus":
                if args["chrom"] != chromosome["name"]:
                    raise ValueError(f"unknown chromosome: {args['chrom']}")
                start = max(chromosome["start"], int(args.get("start", chromosome["start"])))
                end = min(chromosome["end"], int(args.get("end", chromosome["end"])))
                if end <= start:
                    raise ValueError("end must be greater than start")
                self.state["locus"] = {"chrom": chromosome["name"], "start": start, "end": end}
                return dict(self.state["locus"])
            if name == "open_view":
                pane = f"P{len(self.state['views']) + 1}"
                view = {"pane": pane, "type": args["type"]}
                if args["type"] == "stats":
                    view.update({"stats": args.get("stats", "rg"), "chrom_scope": args.get("chrom_scope", "all")})
                if args["type"] == "genome":
                    view["rows"] = args.get("rows", [])
                self.state["views"].append(view)
                self.state["active_view"] = pane
                return {"pane": pane}
            if name == "arrange":
                self.state["layout"] = args["layout"]
                return {"layout": self.state["layout"]}
            if name == "capture_view":
                payload = base64.b64encode(b"real-data-capture").decode()
                return {
                    "data_base64": payload,
                    "png_base64": payload,
                    "mime": "image/png",
                    "format": args.get("format", "png"),
                    "width": 64,
                    "height": 48,
                    "filename": "sim_cell1.png",
                    "notes": [],
                }
            raise ValueError(f"unsupported action: {name}")

        while not self.stopping.is_set():
            try:
                with requests.get(f"{self.base}/api/control/events", params={"page": self.page}, stream=True,
                                  timeout=(5, 30)) as response:
                    self.response = response
                    event = None
                    for line in response.iter_lines(decode_unicode=True):
                        if self.stopping.is_set():
                            return
                        if line.startswith("event: "):
                            event = line[7:]
                        elif line.startswith("data: ") and event == "hello":
                            self.ready.set()
                        elif line.startswith("data: ") and event == "action":
                            message = json.loads(line[6:])
                            self.seen.append(message)
                            try:
                                body = {"ok": True, "result": action(message["name"], message["args"])}
                            except Exception as exc:  # noqa: BLE001
                                body = {"ok": False, "error": str(exc)}
                            if not self.stopping.is_set():
                                requests.post(f"{self.base}/api/control/results/{message['id']}", json=body, timeout=5)
            except requests.exceptions.RequestException:
                if not self.stopping.is_set():
                    self.stopping.wait(0.05)


def test_real_data_agent_loop_applies_canonical_locus_stats_and_genome_plan(server, real_page, tmp_path):
    """Exercise the real-data API loop; HTTP approval calls stand in for local AgentPanel buttons."""
    import requests

    from uchrom_browser import connect

    page = real_page
    ws = connect(server, timeout=5)
    assert ws.agent_pages()[0]["page"] == page.page
    ws._request("POST", "/api/agent/attach", {"page_id": page.page})

    snapshot = ws.agent_snapshot(page=page.page)
    assert snapshot["dataset"]["name"] == "sim_cell1"
    selection = ws.call("get_selection")
    assert selection["cells"] == page.canonical_cells
    assert snapshot["selection"]["n_cells"] == len(selection["cells"])

    plan = ws.propose_ui_changes(
        [
            {"name": "set_locus", "args": {"chrom": "chr15", "start": 0, "end": 200_000_000}},
            {"name": "open_view", "args": {"type": "stats", "stats": "rg", "chrom_scope": "locus"}},
            {"name": "open_view", "args": {"type": "genome", "rows": [{"kind": "contacts", "source": "cell1_contacts"}]}},
            {"name": "arrange", "args": {"layout": "grid"}},
        ],
        page=page.page,
        expected_revision=snapshot["state_revision"],
    )
    assert plan["status"] == "pending"
    ui_plan_url = f"{server}/api/agent/ui/plans/{plan['plan_id']}"
    apply_url = f"{ui_plan_url}/apply"
    assert requests.post(apply_url).status_code == 409
    assert requests.post(f"{ui_plan_url}/approve").json()["status"] == "approved"
    result = requests.post(apply_url).json()
    assert result["status"] == "applied"
    assert result["canonical"]["locus"] == page.state["locus"]
    assert result["canonical"]["layout"] == "grid"
    assert {view["type"] for view in result["canonical"]["views"]} >= {"stats", "genome"}
    stats = next(view for view in result["canonical"]["views"] if view["type"] == "stats")
    assert stats["chrom_scope"] == "locus"
    assert result["state_revision"] == "r_4"
    action_results = result["results"]
    assert action_results[0]["result"] == result["canonical"]["locus"]
    assert action_results[1]["result"]["pane"] == stats["pane"]
    assert action_results[2]["result"]["pane"] == next(view["pane"] for view in result["canonical"]["views"] if view["type"] == "genome")
    final_snapshot = ws.agent_snapshot(page=page.page)
    assert final_snapshot["state_revision"] == result["state_revision"]
    assert final_snapshot["views"] == result["canonical"]["views"]
    assert final_snapshot["locus"] == action_results[0]["result"]

    pending = ws.propose_ui_changes(
        [{"name": "arrange", "args": {"layout": "tabs"}}],
        page=page.page,
        expected_revision=result["state_revision"],
    )
    before_revision = ws.agent_snapshot(page=page.page)["state_revision"]
    before = ws._request("GET", f"/api/agent/plans?page={page.page}")
    capture = ws.capture(path=str(tmp_path / "sim_cell1.png"))
    assert capture["bytes"] == len(b"real-data-capture")
    assert (tmp_path / "sim_cell1.png").read_bytes() == b"real-data-capture"
    assert ws._request("GET", f"/api/agent/plans?page={page.page}") == before
    assert before[0]["plan_id"] == pending["plan_id"]
    assert ws.agent_snapshot(page=page.page)["state_revision"] == before_revision

