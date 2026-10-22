import json

import pytest

from uchrom_agent.lifecycle import _handoff_actions, _read_handoff


def test_read_handoff_accepts_large_inline_json_payload():
    payload = {"dataset": {"path": "/tmp/sample.cdz"}, "question": "x" * 512}

    assert _read_handoff(json.dumps(payload)) == payload


def test_read_handoff_accepts_inline_json_longer_than_a_filename():
    payload = {"dataset": {"path": "/tmp/sample.cdz"}, "question": "x" * 400}

    assert _read_handoff(json.dumps(payload)) == payload


def test_read_handoff_rejects_an_oversized_token_before_path_lookup():
    with pytest.raises(ValueError, match="too long"):
        _read_handoff("t" * 4097)


def test_handoff_actions_preserve_stats_scope_as_an_open_view_action():
    actions, warnings = _handoff_actions({
        "page_state": {
            "views": [{"type": "stats", "stats_kind": "rg", "chrom_scope": "locus"}],
        },
    })

    assert warnings == []
    assert actions == [{
        "name": "open_view",
        "args": {"type": "stats", "stats": "rg", "chrom_scope": "locus"},
    }]
