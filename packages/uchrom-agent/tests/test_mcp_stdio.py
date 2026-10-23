import io
import json

from uchrom_agent.mcp_stdio import serve


class FakeWorkspace:
    def __init__(self):
        self.url = "http://127.0.0.1:8765"
        self.pages = [{"page": "page-1", "active": True, "pinned": True}]
        self.proposals = []
        self.attached_pages = []
        self.health_ok = True

    def agent_pages(self):
        return self.pages

    def _request(self, method, path, body=None):
        if method == "GET" and path == "/api/health":
            if not self.health_ok:
                raise RuntimeError("browser is unavailable")
            return {"status": "ok"}
        assert method == "POST" and path == "/api/agent/attach"
        self.attached_pages.append(body["page_id"])
        return {"page_id": "page-1", "status": "attached"}

    def agent_snapshot(self, page=None):
        assert page == "page-1"
        return {
            "page_id": page,
            "state_revision": "r_4",
            "source": "page_canonical",
            "dataset": {"name": "fixture"},
            "selection": {"cells": ["cell-1"]},
        }

    def propose_ui_changes(self, actions, page, expected_revision):
        proposal = {"plan_id": "plan-1", "page_id": page,
                    "expected_revision": expected_revision, "actions": actions,
                    "status": "pending"}
        self.proposals.append(proposal)
        return proposal

    def plan_status(self, plan_id):
        return {"plan_id": plan_id, "status": "pending"}

    def call(self, action, **args):
        return {"action": action, "args": args}

    def capture(self, pane=None, path=None, format=None):
        return {"path": "/tmp/uchrom-view.png", "pane": pane, "format": format or "png"}


def _run(messages, workspace=None):
    incoming = io.StringIO("".join(json.dumps(message) + "\n" for message in messages))
    outgoing = io.StringIO()
    serve(incoming, outgoing, workspace=workspace)
    return [json.loads(line) for line in outgoing.getvalue().splitlines()], outgoing.getvalue()


def test_initialize_returns_protocol_version_capabilities_and_server_info():
    responses, _ = _run([{"jsonrpc": "2.0", "id": 1, "method": "initialize",
                          "params": {"protocolVersion": "2024-11-05", "capabilities": {},
                                     "clientInfo": {"name": "test", "version": "1"}}}])

    result = responses[0]["result"]
    assert result["protocolVersion"] == "2024-11-05"
    assert result["capabilities"] == {"tools": {}}
    assert result["serverInfo"]["name"] == "uchrom-agent"


def test_tools_list_exposes_only_the_fixed_uchrom_tool_surface():
    responses, _ = _run([{"jsonrpc": "2.0", "id": 1, "method": "tools/list"}])

    names = {tool["name"] for tool in responses[0]["result"]["tools"]}
    assert names == {
        "uchrom_setup_status",
        "uchrom_attach_handoff",
        "uchrom_workspace_snapshot",
        "uchrom_get_selection",
        "uchrom_export_selection",
        "uchrom_list_groups",
        "uchrom_capture_view",
        "uchrom_plan_status",
        "uchrom_export_snapshot",
        "uchrom_propose_ui_changes",
    }
    assert not any("shell" in name or "python" in name for name in names)


def test_setup_status_returns_structured_content():
    responses, _ = _run([{"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                          "params": {"name": "uchrom_setup_status", "arguments": {}}}],
                        workspace=FakeWorkspace())

    result = responses[0]["result"]
    assert result["structuredContent"]["mcp_status"] == "ready"
    assert result["content"][0]["type"] == "text"
    assert json.loads(result["content"][0]["text"]) == result["structuredContent"]


def test_setup_status_reports_not_running_when_health_fails():
    workspace = FakeWorkspace()
    workspace.health_ok = False
    responses, _ = _run([{"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                          "params": {"name": "uchrom_setup_status", "arguments": {}}}],
                        workspace=workspace)

    assert responses[0]["result"]["structuredContent"]["stage"] == "not_running"


def test_setup_status_reports_page_connected_for_one_unpinned_page():
    workspace = FakeWorkspace()
    workspace.pages = [{"page": "page-1", "active": True, "pinned": False}]
    responses, _ = _run([{"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                          "params": {"name": "uchrom_setup_status", "arguments": {}}}],
                        workspace=workspace)

    assert responses[0]["result"]["structuredContent"]["stage"] == "page_connected"


def test_setup_status_reports_page_pinned_for_a_pinned_page():
    responses, _ = _run([{"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                          "params": {"name": "uchrom_setup_status", "arguments": {}}}],
                        workspace=FakeWorkspace())

    assert responses[0]["result"]["structuredContent"]["stage"] == "page_pinned"


def test_workspace_snapshot_returns_page_canonical_state():
    responses, _ = _run([{"jsonrpc": "2.0", "id": 7, "method": "tools/call",
                          "params": {"name": "uchrom_workspace_snapshot", "arguments": {}}}],
                        workspace=FakeWorkspace())

    result = responses[0]["result"]["structuredContent"]
    assert result["state_revision"] == "r_4"
    assert result["source"] == "page_canonical"
    assert result["selection"]["cells"] == ["cell-1"]


def test_disconnected_pinned_page_is_never_replaced_by_another_connected_page():
    workspace = FakeWorkspace()
    messages = [
        {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {
            "name": "uchrom_workspace_snapshot", "arguments": {"page_id": "page-1"}}},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {
            "name": "uchrom_workspace_snapshot", "arguments": {}}},
    ]
    incoming = io.StringIO("".join(json.dumps(message) + "\n" for message in messages))
    outgoing = io.StringIO()

    def pages_after_first_snapshot():
        if len(workspace.attached_pages) == 1:
            workspace.pages = [{"page": "page-2", "active": True}]
        return workspace.pages

    workspace.agent_pages = pages_after_first_snapshot
    serve(incoming, outgoing, workspace=workspace)
    responses = [json.loads(line) for line in outgoing.getvalue().splitlines()]

    assert responses[0]["result"]["structuredContent"]["page_id"] == "page-1"
    assert responses[1]["result"]["isError"] is True
    assert workspace.attached_pages == ["page-1"]


def test_propose_ui_changes_creates_pending_plan_without_apply_tool():
    workspace = FakeWorkspace()
    responses, _ = _run([{"jsonrpc": "2.0", "id": 8, "method": "tools/call",
                          "params": {"name": "uchrom_propose_ui_changes", "arguments": {
                              "changes": [{"name": "arrange", "args": {"layout": "grid"}}]}}}],
                        workspace=workspace)

    result = responses[0]["result"]["structuredContent"]
    assert result["status"] == "pending"
    assert result["expected_revision"] == "r_4"
    assert workspace.proposals == [result]
    tool_names = {tool["name"] for tool in _run([{"jsonrpc": "2.0", "id": 1,
                                                   "method": "tools/list"}])[0][0]["result"]["tools"]}
    assert "uchrom_apply_ui_changes" not in tool_names


def test_unknown_tool_returns_jsonrpc_error_without_stdout_logs():
    responses, stdout = _run([{"jsonrpc": "2.0", "id": 9, "method": "tools/call",
                               "params": {"name": "run_python", "arguments": {}}}],
                             workspace=FakeWorkspace())

    assert responses[0]["error"]["code"] == -32602
    assert "unknown tool" in responses[0]["error"]["message"].lower()
    assert stdout == json.dumps(responses[0]) + "\n"


def test_malformed_call_returns_jsonrpc_error_without_stdout_logs():
    responses, stdout = _run([{"jsonrpc": "2.0", "id": 10, "method": "tools/call",
                               "params": {"name": "uchrom_propose_ui_changes", "arguments": {
                                   "changes": "not-an-action-list"}}}],
                             workspace=FakeWorkspace())

    assert responses[0]["error"]["code"] == -32602
    assert stdout == json.dumps(responses[0]) + "\n"


def test_malformed_json_is_reported_as_parse_error_without_logging():
    incoming = io.StringIO('{"jsonrpc":\n')
    outgoing = io.StringIO()
    serve(incoming, outgoing, workspace=FakeWorkspace())

    response = json.loads(outgoing.getvalue())
    assert response["error"]["code"] == -32700
    assert response["id"] is None
    assert outgoing.getvalue() == json.dumps(response) + "\n"


def test_stdio_eof_closes_the_browser_started_by_the_companion(monkeypatch, tmp_path):
    from uchrom_agent import lifecycle

    class BrowserProcess:
        terminated = False

        def poll(self):
            return None

        def terminate(self):
            self.terminated = True

        def wait(self, timeout):
            return 0

    browser = BrowserProcess()
    dataset_path = str(tmp_path / "sample.cdz")
    handoff = tmp_path / "handoff.json"
    handoff.write_text(json.dumps({"dataset": {"path": dataset_path}}))

    class LocalWorkspace(FakeWorkspace):
        url = "http://127.0.0.1:8765"

        def agent_snapshot(self, page=None):
            return {**super().agent_snapshot(page), "dataset": {"id": "sample", "path": dataset_path}}

    workspace = LocalWorkspace()
    monkeypatch.setattr(lifecycle.subprocess, "Popen", lambda *_args, **_kwargs: browser)
    monkeypatch.setattr(lifecycle, "_wait_for_server", lambda _browser: workspace)

    responses, _ = _run([{"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {
        "name": "uchrom_attach_handoff", "arguments": {"handoff_token": str(handoff)}}}], workspace=workspace)

    assert responses[0]["result"]["structuredContent"]["attached"] is True
    assert responses[0]["result"]["structuredContent"]["browser_reused"] is False
    assert browser.terminated is True
