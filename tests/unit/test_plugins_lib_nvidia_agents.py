"""Isolated unit coverage for ``plugins/claw-sapphire/lib/nvidia_agents.py``.

This module wires Hermes 3 (tool caller) → Nemotron / llama (synthesizer) into
a tiny agent loop that talks to Ollama via stdlib ``urllib``. Prior to this
commit there were zero test references against any of it. We mock every
network call (``urllib.request.urlopen`` and ``urllib.request.Request``) and
exercise:

* module surface: ``MODELS``, ``OLLAMA_ENDPOINTS``, ``SAPPHIRE_TOOLS`` shape
* ``_ollama_chat`` happy path on first endpoint, fallback to second, all-fail
* ``_ollama_chat`` includes ``tools`` payload only when supplied
* ``_execute_tool`` for every named tool: technical_analysis, quant_analysis,
  correlation, equity_quote, prediction_history, send_telegram, unknown
* ``run_agent`` end-to-end with mocked endpoints — single tool call, then
  empty tool_calls (terminate), then synthesis
* ``run_agent`` graceful failure when ``_ollama_chat`` returns ``error``
* ``AgentResponse`` dataclass shape

The module is loaded via ``importlib.util.spec_from_file_location`` so the
broader suite never needs ``plugins/claw-sapphire/lib`` on ``sys.path``.
NEVER asserts against real API keys / endpoints — every URL is the
documented localhost / Tailscale stub.
"""

from __future__ import annotations

import importlib.util
import json
import sys
import urllib.error
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
PLUGIN_LIB = REPO_ROOT / "plugins" / "claw-sapphire" / "lib"
NVIDIA_PATH = PLUGIN_LIB / "nvidia_agents.py"


# ─── Module loader ────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def nvidia():
    """Load nvidia_agents with plugin-lib paths exposed for its sibling imports.

    The module's ``_execute_tool`` helper does runtime ``sys.path.insert(0, ...)``
    when delegating to ``technical_analysis`` etc. — we don't reproduce that
    here because every tool path is patched in the tests below.
    """
    added = False
    if str(PLUGIN_LIB) not in sys.path:
        sys.path.insert(0, str(PLUGIN_LIB))
        added = True

    spec = importlib.util.spec_from_file_location(
        "claw_sapphire_nvidia_agents_under_test", NVIDIA_PATH
    )
    assert spec and spec.loader, f"could not load {NVIDIA_PATH}"
    module = importlib.util.module_from_spec(spec)
    sys.modules["claw_sapphire_nvidia_agents_under_test"] = module
    try:
        spec.loader.exec_module(module)
        yield module
    finally:
        if added and str(PLUGIN_LIB) in sys.path:
            sys.path.remove(str(PLUGIN_LIB))


# ─── helpers ─────────────────────────────────────────────────────────────────


class _FakeResponse:
    """Drop-in for the urlopen context-manager response."""

    def __init__(self, payload: dict):
        self._body = json.dumps(payload).encode()

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _success_response(payload):
    return _FakeResponse(payload)


def _connection_error():
    raise urllib.error.URLError("connection refused")


# ─── Module surface invariants ───────────────────────────────────────────────


def test_endpoints_have_label_and_url(nvidia):
    """OLLAMA_ENDPOINTS is a list of (label, base_url) tuples."""
    for entry in nvidia.OLLAMA_ENDPOINTS:
        assert isinstance(entry, tuple)
        assert len(entry) == 2
        label, url = entry
        assert isinstance(label, str)
        assert url.startswith("http://")


def test_models_dict_has_documented_keys(nvidia):
    """MODELS must include the three orchestration roles used by run_agent."""
    for key in ("tool_caller", "fast_reason", "deep_reason"):
        assert key in nvidia.MODELS
    # Tool caller is hermes3:8b per the module docstring contract.
    assert nvidia.MODELS["tool_caller"] == "hermes3:8b"


def test_tools_schema_well_formed(nvidia):
    """Each entry in SAPPHIRE_TOOLS is a function-tool with a unique name."""
    seen = set()
    for tool in nvidia.SAPPHIRE_TOOLS:
        assert tool["type"] == "function"
        fn = tool["function"]
        assert "name" in fn
        assert "description" in fn
        assert "parameters" in fn
        assert fn["name"] not in seen, f"duplicate tool name: {fn['name']}"
        seen.add(fn["name"])
    # Sanity: at least the six tools the module advertises.
    assert {
        "get_technical_analysis",
        "get_quant_analysis",
        "get_correlation",
        "get_equity_quote",
        "get_prediction_history",
        "send_telegram",
    }.issubset(seen)


def test_send_telegram_priority_enum_is_p_levels(nvidia):
    """send_telegram tool restricts priority to p0/p1/p2 strings."""
    tool = next(
        t["function"] for t in nvidia.SAPPHIRE_TOOLS
        if t["function"]["name"] == "send_telegram"
    )
    enum = tool["parameters"]["properties"]["priority"]["enum"]
    assert enum == ["p0", "p1", "p2"]


def test_agent_response_dataclass_shape(nvidia):
    fields = nvidia.AgentResponse.__dataclass_fields__
    for name in (
        "query", "tool_calls", "tool_results",
        "synthesis", "model_used", "timestamp",
    ):
        assert name in fields


# ─── _ollama_chat ────────────────────────────────────────────────────────────


def test_ollama_chat_first_endpoint_succeeds(nvidia):
    """Happy path — first endpoint returns JSON response."""
    payload = {"message": {"content": "ok"}}
    with patch.object(nvidia.urllib.request, "urlopen", return_value=_success_response(payload)):
        result = nvidia._ollama_chat("hermes3:8b", [{"role": "user", "content": "hi"}])
    assert result == payload


def test_ollama_chat_falls_through_to_second_endpoint(nvidia):
    """If endpoint 1 raises, endpoint 2 is tried."""
    payload = {"message": {"content": "fallback"}}
    calls = {"n": 0}

    def _side(req, timeout):
        calls["n"] += 1
        if calls["n"] == 1:
            raise urllib.error.URLError("first endpoint down")
        return _success_response(payload)

    with patch.object(nvidia.urllib.request, "urlopen", side_effect=_side):
        result = nvidia._ollama_chat("hermes3:8b", [{"role": "user", "content": "hi"}])
    assert result == payload
    assert calls["n"] == 2


def test_ollama_chat_all_endpoints_fail(nvidia):
    """All endpoints fail → returns the documented error sentinel."""
    with patch.object(
        nvidia.urllib.request, "urlopen", side_effect=urllib.error.URLError("down")
    ):
        result = nvidia._ollama_chat("hermes3:8b", [{"role": "user", "content": "hi"}])
    assert "error" in result
    assert "unavailable" in result["error"].lower()


def test_ollama_chat_tool_payload_only_when_supplied(nvidia):
    """Tools list is only embedded in payload when caller passes one."""
    captured = {}

    def _capture(req, timeout):
        # urllib.request.Request stores the body bytes on .data
        captured["body"] = json.loads(req.data.decode())
        return _success_response({"message": {"content": "ok"}})

    with patch.object(nvidia.urllib.request, "urlopen", side_effect=_capture):
        nvidia._ollama_chat(
            "hermes3:8b", [{"role": "user", "content": "hi"}],
            tools=[{"type": "function", "function": {"name": "noop", "parameters": {}}}],
        )
    assert "tools" in captured["body"]

    # Without tools, the field is omitted entirely.
    captured.clear()
    with patch.object(nvidia.urllib.request, "urlopen", side_effect=_capture):
        nvidia._ollama_chat("hermes3:8b", [{"role": "user", "content": "hi"}])
    assert "tools" not in captured["body"]


def test_ollama_chat_request_targets_chat_endpoint(nvidia):
    """The request URL ends in /api/chat (Ollama's native chat endpoint)."""
    captured = {}

    def _capture(req, timeout):
        captured["url"] = req.full_url
        captured["headers"] = dict(req.headers)
        return _success_response({"message": {"content": "ok"}})

    with patch.object(nvidia.urllib.request, "urlopen", side_effect=_capture):
        nvidia._ollama_chat("hermes3:8b", [{"role": "user", "content": "hi"}])
    assert captured["url"].endswith("/api/chat")
    # urllib.request.Request lowercases header names.
    assert captured["headers"].get("Content-type") == "application/json"


# ─── _execute_tool: get_technical_analysis ───────────────────────────────────


def test_execute_tool_get_technical_analysis_happy(nvidia):
    """Happy path: returns JSON-encoded fields from the technical profile."""
    fake_profile = MagicMock(
        symbol="BTC", price=50000.0, rsi_14=60.0, rsi_zone="neutral",
        macd_cross="none", ma_trend="bullish", bb_position="upper_half",
        net_signal="bullish", signal_count_bullish=3, signal_count_bearish=1,
        atr_pct=2.5, volume_signal="normal",
    )

    fake_module = MagicMock()
    fake_module.analyze.return_value = fake_profile

    with patch.dict(sys.modules, {"technical_analysis": fake_module}):
        result = nvidia._execute_tool("get_technical_analysis", {"symbol": "BTC"})
    parsed = json.loads(result)
    assert parsed["symbol"] == "BTC"
    assert parsed["price"] == 50000.0
    assert parsed["rsi"] == 60.0
    assert parsed["rsi_zone"] == "neutral"


def test_execute_tool_get_technical_analysis_no_data(nvidia):
    """When analyze returns None, output is JSON ``{"error": ...}``."""
    fake_module = MagicMock()
    fake_module.analyze.return_value = None
    with patch.dict(sys.modules, {"technical_analysis": fake_module}):
        result = nvidia._execute_tool("get_technical_analysis", {"symbol": "BTC"})
    parsed = json.loads(result)
    assert "error" in parsed


# ─── _execute_tool: get_quant_analysis ───────────────────────────────────────


def test_execute_tool_get_quant_analysis_happy(nvidia):
    sup = MagicMock(price=49000.0, strength=3)
    res = MagicMock(price=51000.0, strength=2)
    fake_profile = MagicMock(
        symbol="BTC", price=50000.0,
        nearest_support=49000.0, nearest_resistance=51000.0,
        risk_reward=1.5, trend_strength=70.0, trend_direction="up",
        support_levels=[sup], resistance_levels=[res],
    )
    fake_module = MagicMock()
    fake_module.analyze_full.return_value = fake_profile
    with patch.dict(sys.modules, {"quant_analysis": fake_module}):
        result = nvidia._execute_tool("get_quant_analysis", {"symbol": "BTC"})
    parsed = json.loads(result)
    assert parsed["symbol"] == "BTC"
    assert parsed["nearest_support"] == 49000.0
    assert parsed["support_levels"][0]["price"] == 49000.0
    assert parsed["resistance_levels"][0]["strength"] == 2


def test_execute_tool_get_quant_analysis_no_data(nvidia):
    fake_module = MagicMock()
    fake_module.analyze_full.return_value = None
    with patch.dict(sys.modules, {"quant_analysis": fake_module}):
        result = nvidia._execute_tool("get_quant_analysis", {"symbol": "BTC"})
    parsed = json.loads(result)
    assert "error" in parsed


# ─── _execute_tool: get_correlation ──────────────────────────────────────────


def test_execute_tool_get_correlation(nvidia):
    pair_a = MagicMock(asset_a="BTC", asset_b="ETH", correlation=0.85, interpretation="strong_positive")
    pair_b = MagicMock(asset_a="BTC", asset_b="SOL", correlation=0.5, interpretation="moderate_positive")
    fake_module = MagicMock()
    fake_module.correlation_matrix.return_value = [pair_a, pair_b]
    with patch.dict(sys.modules, {"quant_analysis": fake_module}):
        result = nvidia._execute_tool("get_correlation", {})
    parsed = json.loads(result)
    assert isinstance(parsed, list)
    assert parsed[0]["pair"] == "BTC/ETH"
    assert parsed[0]["correlation"] == 0.85


# ─── _execute_tool: get_equity_quote ─────────────────────────────────────────


def test_execute_tool_get_equity_quote_happy(nvidia):
    payload = {
        "results": [
            {"symbol": "AAPL", "last_price": 175.0, "volume": 1000000}
        ]
    }
    with patch.object(nvidia.urllib.request, "urlopen", return_value=_success_response(payload)):
        result = nvidia._execute_tool("get_equity_quote", {"symbol": "AAPL"})
    parsed = json.loads(result)
    assert parsed["symbol"] == "AAPL"
    assert parsed["price"] == 175.0
    assert parsed["volume"] == 1000000


def test_execute_tool_get_equity_quote_url_encodes_symbol(nvidia):
    """URL string contains the symbol passed in (sanity-check we don't drop args)."""
    captured = {}

    def _capture(url, timeout):
        # urllib.request.urlopen accepts a string URL here (not Request).
        captured["url"] = url
        return _success_response({"results": [{"symbol": "TSLA", "last_price": 200.0, "volume": 5000}]})

    with patch.object(nvidia.urllib.request, "urlopen", side_effect=_capture):
        nvidia._execute_tool("get_equity_quote", {"symbol": "TSLA"})
    assert "symbol=TSLA" in captured["url"]


def test_execute_tool_get_equity_quote_network_error(nvidia):
    """Network failures surface as a JSON-encoded error, not an exception."""
    with patch.object(
        nvidia.urllib.request, "urlopen",
        side_effect=urllib.error.URLError("connection refused"),
    ):
        result = nvidia._execute_tool("get_equity_quote", {"symbol": "AAPL"})
    parsed = json.loads(result)
    assert "error" in parsed


# ─── _execute_tool: get_prediction_history ───────────────────────────────────


def test_execute_tool_get_prediction_history_no_file(nvidia, tmp_path, monkeypatch):
    """Missing predictions file → returns ``{"total": 0, "accuracy": 0}``."""
    monkeypatch.setenv("HOME", str(tmp_path))
    # Path.home() reads HOME on POSIX.
    result = nvidia._execute_tool("get_prediction_history", {})
    parsed = json.loads(result)
    assert parsed == {"total": 0, "accuracy": 0}


def test_execute_tool_get_prediction_history_with_file(nvidia, tmp_path, monkeypatch):
    """Populated file is parsed and accuracy computed."""
    monkeypatch.setenv("HOME", str(tmp_path))
    target = tmp_path / "Code" / "Sapphire" / "data" / "trading_predictions.jsonl"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("\n".join([
        json.dumps({"correct": True}),
        json.dumps({"correct": True}),
        json.dumps({"correct": False}),
        json.dumps({"correct": None}),  # unscored
    ]))
    result = nvidia._execute_tool("get_prediction_history", {})
    parsed = json.loads(result)
    assert parsed["total"] == 4
    assert parsed["scored"] == 3
    assert parsed["correct"] == 2
    assert parsed["accuracy"] == pytest.approx(66.7, abs=0.5)


# ─── _execute_tool: send_telegram ────────────────────────────────────────────


def test_execute_tool_send_telegram(nvidia):
    """Mocked notify.send_telegram_message is invoked with the message + priority."""
    fake_notify = MagicMock()
    fake_notify.send_telegram_message.return_value = {"ok": True}

    with patch.dict(sys.modules, {"notify": fake_notify}):
        result = nvidia._execute_tool(
            "send_telegram", {"message": "hello", "priority": "p2"},
        )
    parsed = json.loads(result)
    assert parsed == {"sent": True}
    fake_notify.send_telegram_message.assert_called_once_with("hello", priority="p2")


# ─── _execute_tool: unknown ──────────────────────────────────────────────────


def test_execute_tool_unknown_returns_error(nvidia):
    result = nvidia._execute_tool("does_not_exist", {})
    parsed = json.loads(result)
    assert "error" in parsed
    assert "Unknown tool" in parsed["error"]


# ─── run_agent end-to-end ────────────────────────────────────────────────────


def test_run_agent_no_tool_calls_returns_synthesis_unavailable(nvidia):
    """If Hermes returns no tool_calls, we never enter the synthesis branch."""
    fake_response = {"message": {"content": "no tools needed", "tool_calls": []}}
    with patch.object(nvidia, "_ollama_chat", return_value=fake_response):
        result = nvidia.run_agent("ping")
    assert result.tool_calls == []
    assert result.tool_results == {}
    assert "no tools called" in result.synthesis.lower() or result.synthesis == "no tools needed"


def test_run_agent_handles_chat_error(nvidia):
    """If _ollama_chat returns the error sentinel, run_agent terminates cleanly."""
    error_response = {"error": "All Ollama endpoints unavailable"}
    with patch.object(nvidia, "_ollama_chat", return_value=error_response):
        result = nvidia.run_agent("ping")
    assert result.tool_calls == []
    assert result.tool_results == {}
    # The synthesis should be the fallback text — never the bare error dict.
    assert isinstance(result.synthesis, str)


def test_run_agent_invokes_tool_then_synthesizes(nvidia):
    """Full path: turn 1 returns a tool_call, turn 2 has no tool_calls (terminate),
    then a synthesis call returns the final analysis."""
    tool_call_response = {
        "message": {
            "tool_calls": [
                {"function": {"name": "get_technical_analysis", "arguments": {"symbol": "BTC"}}}
            ],
            "content": "",
        }
    }
    no_more_tools_response = {"message": {"content": "", "tool_calls": []}}
    synthesis_response = {"message": {"content": "BTC is bullish based on the data."}}

    chat_calls = []

    def _fake_chat(model, messages, tools=None, timeout=60):
        chat_calls.append({"model": model, "tool": tools is not None})
        # First two calls are tool-decision rounds; third is synthesis.
        if len(chat_calls) == 1:
            return tool_call_response
        if len(chat_calls) == 2:
            return no_more_tools_response
        return synthesis_response

    fake_tool_result = json.dumps({"symbol": "BTC", "price": 50000.0})
    with patch.object(nvidia, "_ollama_chat", side_effect=_fake_chat), patch.object(
        nvidia, "_execute_tool", return_value=fake_tool_result
    ) as exec_mock:
        result = nvidia.run_agent("How is BTC doing?")

    assert any(tc["name"] == "get_technical_analysis" for tc in result.tool_calls)
    exec_mock.assert_called_once()
    assert "get_technical_analysis" in result.tool_results
    assert result.synthesis == "BTC is bullish based on the data."
    assert result.model_used["tool_caller"] == nvidia.MODELS["tool_caller"]
    assert result.model_used["synthesizer"] == nvidia.MODELS["fast_reason"]


def test_run_agent_respects_max_turns(nvidia):
    """When tool-calls keep coming, we stop after max_turns."""
    forever_tool = {
        "message": {
            "tool_calls": [
                {"function": {"name": "get_correlation", "arguments": {}}}
            ],
            "content": "",
        }
    }
    synthesis = {"message": {"content": "summary"}}

    chat_calls = {"n": 0}

    def _fake_chat(model, messages, tools=None, timeout=60):
        chat_calls["n"] += 1
        # Reserve the synthesis-call response for after the agent loop exits.
        if tools is None:
            return synthesis
        return forever_tool

    with patch.object(nvidia, "_ollama_chat", side_effect=_fake_chat), patch.object(
        nvidia, "_execute_tool", return_value=json.dumps([])
    ) as exec_mock:
        result = nvidia.run_agent("loop me", max_turns=2)
    # 2 agent-loop iterations × 1 tool call each = 2 calls.
    assert exec_mock.call_count == 2
    assert len(result.tool_calls) == 2


def test_run_agent_response_timestamp_is_iso8601(nvidia):
    """AgentResponse.timestamp is an ISO-8601 string (UTC)."""
    fake = {"message": {"content": "ok", "tool_calls": []}}
    with patch.object(nvidia, "_ollama_chat", return_value=fake):
        result = nvidia.run_agent("hi")
    # Format is e.g. '2026-01-01T00:00:00.123456+00:00'.
    assert "T" in result.timestamp
    assert result.timestamp.endswith("+00:00") or result.timestamp.endswith("Z")


# ─── Auth header / request construction sanity ───────────────────────────────


def test_request_construction_does_not_include_auth_headers(nvidia):
    """Module advertises localhost / Tailscale only — no API key usage.

    This is a guardrail: regression to embedding bearer tokens / API keys
    in plaintext request headers would be visible in the captured headers.
    """
    captured = {}

    def _capture(req, timeout):
        captured["headers"] = dict(req.headers)
        return _success_response({"message": {"content": "ok"}})

    with patch.object(nvidia.urllib.request, "urlopen", side_effect=_capture):
        nvidia._ollama_chat("hermes3:8b", [{"role": "user", "content": "hi"}])
    headers = {k.lower(): v for k, v in captured["headers"].items()}
    assert "authorization" not in headers
    assert "x-api-key" not in headers


def test_endpoints_are_local_or_tailscale(nvidia):
    """Default endpoints must never reach a third-party domain."""
    for _, url in nvidia.OLLAMA_ENDPOINTS:
        # 100.64.0.0/10 is the Tailscale CGNAT range; localhost is 127.0.0.1.
        assert "127.0.0.1" in url or "localhost" in url or url.startswith("http://100.")


# ─── data shape determinism ──────────────────────────────────────────────────


def test_run_agent_output_is_serializable(nvidia):
    """The result of run_agent must be JSON-serializable (used by stdout JSON)."""
    fake = {"message": {"content": "ok", "tool_calls": []}}
    with patch.object(nvidia, "_ollama_chat", return_value=fake):
        result = nvidia.run_agent("ping")
    # AgentResponse is a dataclass — explicitly serialize each field.
    serialized = json.dumps(
        {
            "query": result.query,
            "tool_calls": result.tool_calls,
            "tool_results": result.tool_results,
            "synthesis": result.synthesis,
            "model_used": result.model_used,
            "timestamp": result.timestamp,
        }
    )
    assert isinstance(serialized, str)


def test_run_agent_synthesis_truncates_large_tool_payloads(nvidia):
    """Synthesis prompt slices tool results to 3000 chars to stay under context.

    Verifying we actually pass a bounded payload to the synthesizer is a soft
    guardrail against OOM / context-overflow regressions.
    """
    huge_payload = json.dumps({"data": "x" * 100_000})
    tool_call_response = {
        "message": {
            "tool_calls": [
                {"function": {"name": "get_technical_analysis", "arguments": {"symbol": "BTC"}}}
            ],
            "content": "",
        }
    }
    no_more = {"message": {"content": "", "tool_calls": []}}
    synthesis = {"message": {"content": "ok"}}
    captured_messages = []

    def _fake_chat(model, messages, tools=None, timeout=60):
        captured_messages.append(messages)
        if tools is None:  # synthesis call
            return synthesis
        if len(captured_messages) == 1:
            return tool_call_response
        return no_more

    with patch.object(nvidia, "_ollama_chat", side_effect=_fake_chat), patch.object(
        nvidia, "_execute_tool", return_value=huge_payload
    ):
        nvidia.run_agent("ping")

    # Last call is the synthesis prompt → the user-content body should be ≤
    # the upper bound the source documents (3000 char cap on dumped results +
    # constant prefix). Anything massively over implies the cap is ineffective.
    synthesis_user = next(
        m for m in captured_messages[-1] if m["role"] == "user"
    )
    assert len(synthesis_user["content"]) < 5_000
