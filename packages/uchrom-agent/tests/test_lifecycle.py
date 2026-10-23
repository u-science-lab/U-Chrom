import copy
import io
import json
from datetime import datetime

import pytest

from uchrom_agent import lifecycle
from uchrom_agent.lifecycle import _handoff_actions, _read_handoff, _redeem, attach_handoff
from uchrom_agent.mcp_stdio import _Bridge


TOKEN = "a" * 43
DATA_URL = "https://uchrom-atlas-r2.u-science.org/public/sample.chromdata.zarr"
CATALOG = {
    "version": 1,
    "updated": "2026-10-22T00:00:00Z",
    "datasets": [{"id": "sample", "path": "public/sample.chromdata.zarr"}],
}


class JsonResponse(io.BytesIO):
    headers = {}

    def __init__(self, payload, url="https://uchrom-atlas-r2.u-science.org/catalog.json"):
        super().__init__(json.dumps(payload).encode())
        self.url = url

    def geturl(self):
        return self.url


@pytest.fixture
def handoff(monkeypatch):
    monkeypatch.setattr(lifecycle.time, "time", lambda: datetime.fromisoformat("2026-10-23T12:05:00+00:00").timestamp())
    monkeypatch.setattr(lifecycle.urllib.request, "urlopen", lambda *_args, **_kwargs: JsonResponse(CATALOG))
    payload = {
        "version": 1,
        "issued_at": "2026-10-23T12:00:00Z",
        "expires_at": "2026-10-23T12:10:00Z",
        "dataset": {"id": "sample", "url": DATA_URL, "version": "2026-10-22T00:00:00Z"},
    }
    monkeypatch.setattr(lifecycle, "_redeem", lambda token: copy.deepcopy(payload))
    return payload


def test_read_handoff_accepts_a_current_catalog_bound_redeemed_payload(handoff):
    assert _read_handoff(TOKEN) == handoff


def test_read_handoff_rejects_inline_payloads_even_when_they_contain_a_local_path():
    with pytest.raises(ValueError, match="token|local handoff file"):
        _read_handoff(json.dumps({"dataset": {"path": "/tmp/sample.cdz"}}))


def test_read_handoff_preserves_explicit_local_file_support(tmp_path):
    dataset = tmp_path / "sample.cdz"
    dataset.touch()
    payload = {"dataset": {"path": str(dataset)}, "question": "x" * 512}
    handoff_file = tmp_path / "handoff.json"
    handoff_file.write_text(json.dumps(payload))

    assert _read_handoff(str(handoff_file)) == payload


@pytest.mark.parametrize("dataset", [
    {"url": "https://evil.test/private.cdz"},
    {"path": "https://evil.test/private.cdz"},
    {"path": "s3://private/sample.cdz"},
    {"path": "--host=0.0.0.0"},
    {"path": "/tmp/sample.cdz", "url": DATA_URL},
])
def test_local_handoff_file_cannot_bypass_remote_source_validation(tmp_path, dataset):
    handoff_file = tmp_path / "handoff.json"
    handoff_file.write_text(json.dumps({"dataset": dataset}))

    with pytest.raises(ValueError):
        _read_handoff(str(handoff_file))


@pytest.mark.parametrize("token", ["", "t" * 4097, "t" * 300, "bad-token", "a" * 42 + "/"])
def test_read_handoff_rejects_invalid_tokens(token, monkeypatch):
    def must_not_request(*_args, **_kwargs):
        pytest.fail("invalid tokens must be rejected before any network request")

    monkeypatch.setattr(lifecycle.urllib.request, "urlopen", must_not_request)
    with pytest.raises(ValueError, match="token"):
        _read_handoff(token)


def test_read_handoff_rejects_oversized_local_files(tmp_path):
    handoff_file = tmp_path / "handoff.json"
    handoff_file.write_text(json.dumps({"dataset": {"path": "/tmp/sample.cdz"}, "question": "x" * 1_048_576}))

    with pytest.raises(ValueError, match="1 MiB"):
        _read_handoff(str(handoff_file))


def test_local_handoff_resolves_dataset_paths_from_the_handoff_file(tmp_path):
    handoff_file = tmp_path / "handoff.json"
    handoff_file.write_text(json.dumps({"dataset": {"path": "sample.cdz"}}))

    assert _read_handoff(str(handoff_file))["dataset"] == {"path": str(tmp_path / "sample.cdz")}


def test_redeem_rejects_a_redirected_payload_source(monkeypatch):
    monkeypatch.setattr(lifecycle.urllib.request, "urlopen", lambda *_args, **_kwargs: JsonResponse({}, "https://evil.test/redeem"))

    with pytest.raises(ValueError, match="source"):
        _redeem(TOKEN)


def test_read_handoff_uses_the_catalog_weak_etag_when_updated_is_missing(handoff, monkeypatch):
    catalog = {"version": 1, "datasets": CATALOG["datasets"]}
    handoff["dataset"]["version"] = "catalog-etag"
    response = JsonResponse(catalog)
    response.headers = {"ETag": 'W/"catalog-etag"'}
    monkeypatch.setattr(lifecycle.urllib.request, "urlopen", lambda *_args, **_kwargs: response)

    assert _read_handoff(TOKEN) == handoff


def test_read_handoff_rejects_a_redirected_catalog(handoff, monkeypatch):
    monkeypatch.setattr(lifecycle.urllib.request, "urlopen", lambda *_args, **_kwargs: JsonResponse(CATALOG, "https://evil.test/catalog.json"))

    with pytest.raises(ValueError, match="source"):
        _read_handoff(TOKEN)


@pytest.mark.parametrize("path", ["../private.zarr", "public/%2e%2e/private.zarr", "https://evil.test/a", "public/%zz.zarr"])
def test_read_handoff_rejects_unsafe_catalog_paths(handoff, monkeypatch, path):
    catalog = copy.deepcopy(CATALOG)
    catalog["datasets"][0]["path"] = path
    handoff["dataset"]["url"] = "https://uchrom-atlas-r2.u-science.org/" + path
    monkeypatch.setattr(lifecycle.urllib.request, "urlopen", lambda *_args, **_kwargs: JsonResponse(catalog))

    with pytest.raises(ValueError):
        _read_handoff(TOKEN)


@pytest.mark.parametrize(("field", "value"), [
    ("version", 2),
    ("version", True),
    ("issued_at", "invalid"),
    ("issued_at", "2026-10-23T12:00:00"),
    ("issued_at", "2026-10-23T12:06:00Z"),
    ("expires_at", "2026-10-23T12:05:00Z"),
    ("expires_at", "2026-10-23T12:11:00Z"),
    ("question", {"command": "unsafe"}),
    ("question", "x" * 4001),
    ("command", "unsafe"),
])
def test_read_handoff_rejects_invalid_contract_fields(handoff, field, value):
    handoff[field] = value

    with pytest.raises(ValueError):
        _read_handoff(TOKEN)


@pytest.mark.parametrize("dataset", [
    {"id": "sample", "path": "/tmp/private.cdz", "version": "2026-10-22T00:00:00Z"},
    {"id": "sample", "url": "https://evil.test/private.cdz", "version": "2026-10-22T00:00:00Z"},
    {"id": "other", "url": DATA_URL, "version": "2026-10-22T00:00:00Z"},
    {"id": "sample", "url": DATA_URL, "version": "old-catalog"},
    {"id": "sample", "url": DATA_URL},
    {"id": "sample", "url": DATA_URL, "version": "2026-10-22T00:00:00Z", "command": "unsafe"},
])
def test_read_handoff_requires_exact_catalog_id_url_and_version(handoff, dataset):
    handoff["dataset"] = dataset

    with pytest.raises(ValueError):
        _read_handoff(TOKEN)


def test_handoff_actions_preserve_stats_scope_as_an_open_view_action():
    actions, warnings = _handoff_actions({
        "page_state": {
            "selection": {"cells": ["c1", "c2"], "source": "lasso"},
            "locus": {"chrom": "chr1", "start": 10, "end": 100},
            "views": [{"type": "stats", "stats_kind": "rg", "chrom_scope": "locus"}],
            "layout": "grid",
        },
    })

    assert warnings == []
    assert actions == [
        {"name": "select_cells", "args": {"cells": ["c1", "c2"]}},
        {"name": "set_locus", "args": {"chrom": "chr1", "start": 10, "end": 100}},
        {"name": "open_view", "args": {"type": "stats", "stats": "rg", "chrom_scope": "locus"}},
        {"name": "arrange", "args": {"layout": "grid"}},
    ]


@pytest.mark.parametrize("state", [
    None,
    [],
    {"command": "unsafe"},
    {"selection": "c1"},
    {"selection": {"cells": "c1"}},
    {"selection": {"cells": [1]}},
    {"selection": {"cells": [""]}},
    {"selection": {"cells": ["c1\n"]}},
    {"selection": {"cells": ["c1"], "command": "unsafe"}},
    {"selection": {"cells": ["c1"], "source": {}}},
    {"locus": "chr1"},
    {"locus": {"chrom": 1}},
    {"locus": {"chrom": "chr1", "start": True}},
    {"locus": {"chrom": "chr1", "start": -1}},
    {"locus": {"chrom": "chr1", "start": 100, "end": 10}},
    {"locus": {"chrom": "chr1", "command": "unsafe"}},
    {"views": "stats"},
    {"views": ["stats"]},
    {"views": [{"type": "unknown"}]},
    {"views": [{"type": "stats", "stats_kind": "unknown"}]},
    {"views": [{"type": "stats", "chrom_scope": "unknown"}]},
    {"views": [{"type": "stats", "command": "unsafe"}]},
    {"views": [{"type": "3d", "stats_kind": "rg"}]},
    {"views": [{"type": "stats", "cells": {"kind": "all"}}]},
    {"layout": "unknown"},
])
def test_handoff_actions_reject_invalid_or_unknown_fields(state):
    with pytest.raises(ValueError):
        _handoff_actions({"page_state": state})


def test_invalid_page_state_is_rejected_before_browser_connection(handoff):
    handoff["page_state"] = {"views": [{"type": "stats", "command": "unsafe"}]}

    def must_not_connect():
        pytest.fail("invalid handoff must be rejected before connecting or starting the browser")

    with pytest.raises(ValueError):
        attach_handoff(TOKEN, connect=must_not_connect, pin_page=lambda _page, _ws: None)


class ReusableWorkspace:
    url = "http://127.0.0.1:8765"

    def __init__(self, page_dataset):
        self.page_dataset = page_dataset
        self.proposals = []
        self.loaded = [{"id": "loaded-sample", "path": DATA_URL}]

    def _request(self, method, path, body=None):
        if (method, path) == ("GET", "/api/datasets"):
            return self.loaded
        assert (method, path, body) == ("POST", "/api/agent/attach", {"page_id": "page-1"})
        return {"page_id": "page-1", "status": "attached"}

    def agent_pages(self):
        return [{"page": "page-1", "active": True}]

    def agent_snapshot(self, page):
        return {"page_id": page, "source": "page_canonical", "state_revision": "r_4", "dataset": self.page_dataset}

    def propose_ui_changes(self, actions, page, revision):
        self.proposals.append({"actions": actions, "page_id": page, "expected_revision": revision})
        return {"plan_id": "plan-1", "status": "pending"}


def test_reuse_refuses_a_canonical_page_with_a_different_dataset(handoff):
    handoff["page_state"] = {"layout": "grid"}
    ws = ReusableWorkspace({"id": "other", "path": "https://uchrom-atlas-r2.u-science.org/other.zarr"})
    bindings = []

    with pytest.raises(RuntimeError, match="dataset"):
        attach_handoff(TOKEN, connect=lambda: ws, pin_page=lambda page, workspace: bindings.append((page, workspace)))

    assert ws.proposals == []
    assert bindings == []


def test_reuse_proposes_only_after_canonical_dataset_matches(handoff):
    handoff["page_state"] = {"layout": "grid"}
    ws = ReusableWorkspace({"id": "loaded-sample", "path": DATA_URL})

    bindings = []
    result = attach_handoff(TOKEN, connect=lambda: ws, pin_page=lambda page, workspace: bindings.append((page, workspace)))

    assert result["attached"] is True
    assert result["browser_reused"] is True
    assert result["page_state_status"] == "pending_review"
    assert bindings == [("page-1", ws)]
    assert ws.proposals == [{"actions": [{"name": "arrange", "args": {"layout": "grid"}}],
                             "page_id": "page-1", "expected_revision": "r_4"}]


def test_attach_retains_the_new_workspace_in_the_mcp_bridge(handoff, monkeypatch):
    previous = ReusableWorkspace({"id": "other", "path": "/tmp/other.cdz"})
    previous.loaded = []
    current = ReusableWorkspace({"id": "loaded-sample", "path": DATA_URL})
    monkeypatch.setattr(lifecycle.subprocess, "Popen", lambda *_args, **_kwargs: object())
    monkeypatch.setattr(lifecycle, "_wait_for_server", lambda _process: current)
    monkeypatch.setattr(lifecycle, "_started", None)
    bridge = _Bridge(previous)

    result = bridge._call("uchrom_attach_handoff", {"handoff_token": TOKEN})

    assert result["attached"] is True
    assert result["browser_reused"] is False
    assert bridge._snapshot()["dataset"]["path"] == DATA_URL
    assert bridge.workspace is current
