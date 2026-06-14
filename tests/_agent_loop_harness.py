"""Shared test harness for driving ``ws_handler.run_agent_loop``.

The real agent loop talks to Anthropic through the *streaming* API:

    async with client.messages.stream(...) as stream:
        async for event in stream:
            ...                        # content_block_delta → agent_message_delta
        response = await stream.get_final_message()

So mocking ``client.messages.create`` (the old non-streaming call) no longer
exercises the loop. This module provides a fake client that mimics
``messages.stream`` as an async context manager, plus a couple of drivers so
each test can stay link-level: it feeds the loop a scripted sequence of Claude
"turns" and asserts on the artifacts / tool_results the loop produces, mocking
only the Anthropic boundary.

Underscore-prefixed filename → pytest does not collect it as a test module.
"""
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
import asyncio


# --- Building blocks for a scripted Claude response --------------------------

def text_block(text):
    """A text content block (what the agent says)."""
    return SimpleNamespace(type="text", text=text)


def tool_block(tool_id, name, inp):
    """A tool_use content block (what the agent calls)."""
    return SimpleNamespace(type="tool_use", id=tool_id, name=name, input=inp)


def turn(blocks, stop_reason):
    """One Claude response: a list of content blocks + a stop_reason."""
    return SimpleNamespace(content=blocks, stop_reason=stop_reason)


def single_tool_then_done(name, inp, tool_id="t1", final_text="done"):
    """The common script: call one tool, then end the turn.

    The loop dispatches the tool exactly once (stop_reason="tool_use"), feeds
    the tool_result back, then sees "end_turn" and exits.
    """
    return [
        turn([tool_block(tool_id, name, inp)], "tool_use"),
        turn([text_block(final_text)], "end_turn"),
    ]


# --- Fake streaming client ---------------------------------------------------

class _FakeStream:
    """Mimics anthropic's MessageStreamManager for a single turn.

    ``async with`` yields self; ``async for`` walks the streaming lifecycle
    (message_start → content_block_start/delta/stop → message_stop), mirroring
    the real Anthropic event sequence so the loop's lifecycle forwarding is
    exercised; ``get_final_message`` returns the turn's final response object.
    """

    def __init__(self, response, deltas, message_id="msg_fake"):
        self._response = response
        self._deltas = deltas
        self._message_id = message_id

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def __aiter__(self):
        yield SimpleNamespace(
            type="message_start",
            message=SimpleNamespace(id=self._message_id),
        )
        # Emit the text deltas as a single content block at index 0, bracketed
        # by content_block_start / content_block_stop.
        yield SimpleNamespace(
            type="content_block_start",
            index=0,
            content_block=SimpleNamespace(type="text"),
        )
        for d in self._deltas:
            yield SimpleNamespace(
                type="content_block_delta",
                index=0,
                delta=SimpleNamespace(type="text_delta", text=d),
            )
        yield SimpleNamespace(type="content_block_stop", index=0)
        yield SimpleNamespace(type="message_stop")

    async def get_final_message(self):
        return self._response


class FakeMessages:
    """Stand-in for ``client.messages``. Each ``.stream(...)`` call returns the
    next scripted turn. ``last_kwargs`` exposes the kwargs the loop passed (so
    a test can assert tools/system/model were forwarded)."""

    def __init__(self, turns, deltas=None):
        self._turns = list(turns)
        self._deltas = deltas if deltas is not None else [[] for _ in self._turns]
        self._i = 0
        self.last_kwargs = None

    def stream(self, **kwargs):
        # Real AsyncAnthropic().messages.stream is sync and returns an async-CM;
        # only the surrounding `async with` / iteration is awaited.
        self.last_kwargs = kwargs
        i = self._i
        self._i += 1
        return _FakeStream(self._turns[i], self._deltas[i], message_id=f"msg_fake_{i}")


class FakeClient:
    def __init__(self, turns, deltas=None):
        self.messages = FakeMessages(turns, deltas)


# --- Drivers -----------------------------------------------------------------

def _capture_ws(sent):
    """An AsyncMock websocket whose send_json appends to ``sent``."""
    ws = AsyncMock()

    async def _capture(obj):
        sent.append(obj)

    ws.send_json = _capture
    return ws


def run_loop(turns, history=None, deltas=None, session=None):
    """Drive run_agent_loop from a *synchronous* test via asyncio.run.

    Returns (sent, history, fake_client).
    """
    from webapp.backend import ws_handler

    history = history if history is not None else [{"role": "user", "content": "hi"}]
    sent = []
    fake = FakeClient(turns, deltas)
    with patch.object(ws_handler, "client", fake):
        asyncio.run(ws_handler.run_agent_loop(_capture_ws(sent), history, session))
    return sent, history, fake


async def drive_loop(turns, history=None, deltas=None, session=None):
    """Drive run_agent_loop from an ``@pytest.mark.asyncio`` test.

    Returns (sent, history, fake_client).
    """
    from webapp.backend import ws_handler

    history = history if history is not None else [{"role": "user", "content": "hi"}]
    sent = []
    fake = FakeClient(turns, deltas)
    with patch.object(ws_handler, "client", fake):
        await ws_handler.run_agent_loop(_capture_ws(sent), history, session)
    return sent, history, fake


# --- Assertions helpers ------------------------------------------------------

def artifacts(sent, artifact_type):
    """All agent_artifact messages of the given artifact_type."""
    return [
        m for m in sent
        if isinstance(m, dict) and m.get("artifact_type") == artifact_type
    ]


def tool_results(history):
    """All tool_result blocks the loop appended back into the conversation."""
    return [
        block
        for msg in history
        if msg.get("role") == "user" and isinstance(msg.get("content"), list)
        for block in msg["content"]
        if isinstance(block, dict) and block.get("type") == "tool_result"
    ]
