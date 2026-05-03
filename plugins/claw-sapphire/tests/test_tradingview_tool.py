"""Tests for the sapphire_tradingview plugin tool.

Covers:
1. Schema / JSON-error handling at the ``main`` boundary.
2. Unknown-action dispatch + ``valid_actions`` shape.
3. Each action's happy-path return shape (orchestrator + pine_templates mocked).
4. Read-only invariants: dispatcher refuses every name in
   ``BLOCKED_MUTATION_ACTIONS`` and the action table references zero
   mutation methods (verified by source-text inspection).
5. Shim test: ``tools/tradingview.py`` re-execs the real impl.
"""

from __future__ import annotations

import importlib.util
import io
import json
import sys
from pathlib import Path

PLUGINS_ROOT = Path(__file__).resolve().parents[1]
ROOT = PLUGINS_ROOT.parents[1]
TOOLS = PLUGINS_ROOT / "tools"

# sys.path hygiene — pytest auto-inserts ``plugins/claw-sapphire`` (the
# parent of this tests package) onto sys.path. That directory contains a
# regular ``lib/`` package which shadows the repo's namespace ``lib/`` (a
# regular package always wins over a namespace package regardless of
# order). Evict it before loading the tool, restore after, so the tool's
# ``from lib.trading...`` imports resolve to the repo lib.
_PLUGIN_ROOT_STRS = {str(PLUGINS_ROOT), str(PLUGINS_ROOT) + "/"}
_evicted_paths = [p for p in sys.path if p in _PLUGIN_ROOT_STRS]
sys.path[:] = [p for p in sys.path if p not in _PLUGIN_ROOT_STRS]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

_spec = importlib.util.spec_from_file_location(
    "tradingview_tool", TOOLS / "internal" / "tradingview.py"
)
tradingview = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(tradingview)

for _p in _evicted_paths:
    if _p not in sys.path:
        sys.path.append(_p)


# ---------------------------------------------------------------------------
# Test doubles
# ---------------------------------------------------------------------------


class _FakeOrchestrator:
    """In-memory stand-in for ``TradingViewOrchestrator``.

    Every method returns a deterministic payload so the tests can assert
    exact return shapes without touching the ``tv`` CLI.
    """

    def __init__(self, *, tv_bin: str = "tv", mutation_enabled: bool = False) -> None:
        self.tv_bin = tv_bin
        self.mutation_enabled = mutation_enabled
        self.calls: list[tuple[str, tuple, dict]] = []

    def _record(self, name: str, *args, **kwargs) -> None:
        self.calls.append((name, args, kwargs))

    def probe_state(self) -> dict:
        self._record("probe_state")
        return {"connected": True, "symbol": "BINANCE:BTCUSDT", "timeframe": "60"}

    def probe_quote(self, symbol: str | None = None) -> dict:
        self._record("probe_quote", symbol=symbol)
        return {"symbol": symbol or "BINANCE:BTCUSDT", "last": 76_000.0}

    def probe_values(self) -> dict:
        self._record("probe_values")
        return {"rsi": 55.0, "macd": 12.3}

    def latest_scoring(self, top_n: int | None = None) -> dict:
        self._record("latest_scoring", top_n=top_n)
        return {"top_n": top_n, "rows": [{"symbol": "BTC", "score": 0.42}]}

    def pine_list(self) -> dict:
        self._record("pine_list")
        return {"scripts": [{"name": "Sapphire_Watch_BTC"}]}

    def alerts_list(self) -> dict:
        self._record("alerts_list")
        return {"alerts": []}

    def capture_sweep(
        self,
        symbols,
        *,
        session_id=None,
        primary_timeframe="60",
    ) -> dict:
        self._record(
            "capture_sweep",
            symbols=list(symbols),
            session_id=session_id,
            primary_timeframe=primary_timeframe,
        )
        return {
            "session_id": session_id or "session-X",
            "schema_version": 1,
            "primary_timeframe": primary_timeframe,
            "mutation_enabled": False,
            "manifest_path": "data/tradingview_ta/session-X/manifest.json",
            "symbols": [
                {
                    "symbol": "BTC",
                    "tradingview_symbol": "BINANCE:BTCUSDT",
                    "rank": 1,
                    "artifacts": [{"ok": True}, {"ok": True}, {"ok": False}],
                    "score": 0.7,
                }
            ],
        }


def _patch_orchestrator(monkeypatch) -> list[_FakeOrchestrator]:
    """Replace ``TradingViewOrchestrator`` with a recording fake.

    Returns the list that captures every constructed instance so tests
    can assert ``mutation_enabled=False`` was forced.
    """
    constructed: list[_FakeOrchestrator] = []

    def _factory(*args, **kwargs):
        fake = _FakeOrchestrator(*args, **kwargs)
        constructed.append(fake)
        return fake

    monkeypatch.setattr(tradingview, "TradingViewOrchestrator", _factory)
    return constructed


# ---------------------------------------------------------------------------
# 1. Schema / main() boundary
# ---------------------------------------------------------------------------


def test_main_empty_stdin_runs_default_probe(monkeypatch):
    _patch_orchestrator(monkeypatch)
    out = io.StringIO()

    code = tradingview.main(stream_in=io.StringIO(""), stream_out=out)

    # Empty stdin defaults to ``{}`` → action ``probe`` → ok=True → exit 0.
    assert code == 0
    payload = json.loads(out.getvalue())
    assert payload["action"] == "probe"
    assert payload["ok"] is True


def test_main_rejects_invalid_json():
    out = io.StringIO()

    code = tradingview.main(stream_in=io.StringIO("{not-json"), stream_out=out)

    assert code == 2
    body = json.loads(out.getvalue())
    assert "invalid JSON" in body["error"]


def test_main_rejects_non_object_json():
    out = io.StringIO()

    code = tradingview.main(stream_in=io.StringIO("[1,2,3]"), stream_out=out)

    assert code == 2
    body = json.loads(out.getvalue())
    assert "must be a JSON object" in body["error"]


def test_handle_rejects_non_dict_payload():
    result = tradingview.handle("not-a-dict")  # type: ignore[arg-type]

    assert result["ok"] is False
    assert result["action"] == "dispatch"
    assert "JSON object" in result["error"]


def test_run_returns_indented_sorted_json(monkeypatch):
    _patch_orchestrator(monkeypatch)

    text = tradingview.run("probe")
    parsed = json.loads(text)

    assert parsed["action"] == "probe"
    assert parsed["ok"] is True
    # ``run`` uses ``sort_keys=True`` so keys are alphabetical.
    assert list(parsed.keys()) == sorted(parsed.keys())


# ---------------------------------------------------------------------------
# 2. Unknown action
# ---------------------------------------------------------------------------


def test_unknown_action_reports_valid_actions():
    result = tradingview.handle({"action": "definitely-not-a-real-action"})

    assert result["ok"] is False
    assert "unknown action" in result["error"]
    assert set(result["valid_actions"]) == set(tradingview.VALID_ACTIONS)


def test_main_unknown_action_returns_exit_1():
    out = io.StringIO()

    code = tradingview.main(
        stream_in=io.StringIO('{"action":"bogus"}'), stream_out=out
    )

    assert code == 1
    body = json.loads(out.getvalue())
    assert body["ok"] is False
    assert "unknown" in body["error"]


def test_action_normalisation_is_case_and_dash_insensitive(monkeypatch):
    _patch_orchestrator(monkeypatch)

    result = tradingview.handle({"action": "LIST-PINE"})

    assert result["ok"] is True
    assert result["action"] == "list_pine"


# ---------------------------------------------------------------------------
# 3. Happy-path return shape per action (orchestrator mocked)
# ---------------------------------------------------------------------------


def test_probe_action_returns_state_quote_values(monkeypatch):
    constructed = _patch_orchestrator(monkeypatch)

    result = tradingview.handle({"action": "probe", "symbol": "BTCUSDT"})

    assert result["action"] == "probe"
    assert result["ok"] is True
    data = result["data"]
    assert set(data.keys()) >= {"state", "quote", "values", "mutation_enabled"}
    assert data["mutation_enabled"] is False
    assert data["quote"]["symbol"] == "BTCUSDT"
    # mutation_enabled=False MUST be enforced at construction time.
    assert constructed and constructed[-1].mutation_enabled is False


def test_score_action_passes_limit_to_orchestrator(monkeypatch):
    constructed = _patch_orchestrator(monkeypatch)

    result = tradingview.handle({"action": "score", "limit": 5})

    assert result["ok"] is True
    assert result["action"] == "score"
    assert result["data"]["top_n"] == 5
    # Latest call should record ``top_n=5``.
    name, _args, kwargs = constructed[-1].calls[-1]
    assert name == "latest_scoring"
    assert kwargs == {"top_n": 5}


def test_score_action_invalid_limit_returns_error(monkeypatch):
    _patch_orchestrator(monkeypatch)

    result = tradingview.handle({"action": "score", "limit": "abc"})

    assert result["ok"] is False
    assert result["action"] == "score"
    assert "invalid limit" in result["error"]


def test_score_action_zero_limit_falls_back_to_default(monkeypatch):
    constructed = _patch_orchestrator(monkeypatch)

    result = tradingview.handle({"action": "score", "limit": 0})

    assert result["ok"] is True
    name, _args, kwargs = constructed[-1].calls[-1]
    assert name == "latest_scoring"
    assert kwargs["top_n"] == tradingview.DEFAULT_SCORE_LIMIT


def test_list_pine_includes_account_and_local(monkeypatch):
    _patch_orchestrator(monkeypatch)
    monkeypatch.setattr(
        tradingview,
        "list_generated",
        lambda: [{"name": "local_one", "pine_path": "/tmp/local_one.pine"}],
    )

    result = tradingview.handle({"action": "list_pine"})

    assert result["ok"] is True
    assert result["action"] == "list_pine"
    assert "tv_account_scripts" in result["data"]
    assert result["data"]["generated_local"][0]["name"] == "local_one"


def test_list_alerts_returns_data(monkeypatch):
    _patch_orchestrator(monkeypatch)

    result = tradingview.handle({"action": "list_alerts"})

    assert result["ok"] is True
    assert result["action"] == "list_alerts"
    assert result["data"] == {"alerts": []}


def test_generate_pine_indicator_default_kind(monkeypatch):
    _patch_orchestrator(monkeypatch)
    monkeypatch.setattr(
        tradingview,
        "render_sapphire_watch_indicator",
        lambda symbol: f"// indicator for {symbol}",
    )
    monkeypatch.setattr(
        tradingview,
        "render_sapphire_watch_strategy",
        lambda symbol: "SHOULD-NOT-BE-CALLED",
    )
    captured: dict = {}

    def fake_write_template(name, source, *, metadata=None, **_kw):
        captured["name"] = name
        captured["source"] = source
        captured["metadata"] = metadata
        return {
            "name": name,
            "slug": name.lower().replace(" ", "_"),
            "pine_path": f"/tmp/{name}.pine",
            "metadata_path": f"/tmp/{name}.json",
            "metadata": {"byte_size": len(source)},
        }

    monkeypatch.setattr(tradingview, "write_template", fake_write_template)

    result = tradingview.handle({"action": "generate_pine", "symbol": "BTCUSDT"})

    assert result["ok"] is True
    assert result["action"] == "generate_pine"
    data = result["data"]
    assert data["kind"] == "sapphire_watch_indicator"
    assert data["name"] == "Sapphire_Watch_BTCUSDT"
    assert data["pine_path"].endswith(".pine")
    assert data["byte_size"] == len("// indicator for BTCUSDT")
    assert captured["metadata"]["kind"] == "sapphire_watch_indicator"


def test_generate_pine_strategy_kind(monkeypatch):
    _patch_orchestrator(monkeypatch)
    monkeypatch.setattr(
        tradingview,
        "render_sapphire_watch_strategy",
        lambda symbol: f"// strategy for {symbol}",
    )

    def fake_write_template(name, source, *, metadata=None, **_kw):
        return {
            "name": name,
            "slug": "x",
            "pine_path": f"/tmp/{name}.pine",
            "metadata_path": f"/tmp/{name}.json",
            "metadata": {"byte_size": len(source)},
        }

    monkeypatch.setattr(tradingview, "write_template", fake_write_template)

    result = tradingview.handle(
        {"action": "generate_pine", "symbol": "ETHUSDT", "kind": "strategy"}
    )

    assert result["ok"] is True
    assert result["data"]["kind"] == "sapphire_watch_strategy"
    assert result["data"]["name"] == "Sapphire_Strategy_ETHUSDT"


def test_generate_pine_missing_symbol_errors():
    result = tradingview.handle({"action": "generate_pine"})

    assert result["ok"] is False
    assert result["action"] == "generate_pine"
    assert "symbol" in result["error"]


def test_generate_pine_invalid_kind_errors():
    result = tradingview.handle(
        {"action": "generate_pine", "symbol": "BTC", "kind": "bogus"}
    )

    assert result["ok"] is False
    assert "invalid kind" in result["error"]


def test_generate_pine_custom_name_overrides_default(monkeypatch):
    _patch_orchestrator(monkeypatch)
    monkeypatch.setattr(
        tradingview, "render_sapphire_watch_indicator", lambda s: "// pine"
    )

    def fake_write_template(name, source, *, metadata=None, **_kw):
        return {
            "name": name,
            "slug": "custom",
            "pine_path": "/tmp/custom.pine",
            "metadata_path": "/tmp/custom.json",
            "metadata": {"byte_size": len(source)},
        }

    monkeypatch.setattr(tradingview, "write_template", fake_write_template)

    result = tradingview.handle(
        {"action": "generate_pine", "symbol": "BTC", "name": "MyCustomScript"}
    )

    assert result["data"]["name"] == "MyCustomScript"


def test_sweep_returns_summary_with_artifact_counts(monkeypatch):
    constructed = _patch_orchestrator(monkeypatch)

    fake_machine = {
        "watchlist": {"symbols": ["BTC", "ETH", "SOL", "AAPL", "TSLA", "SPY"]}
    }
    monkeypatch.setattr(
        tradingview,
        "build_tradingview_ta_machine",
        lambda *, fetch_live, limit: fake_machine,
        raising=False,
    )
    # ``build_tradingview_ta_machine`` is imported lazily inside the
    # action — register it under both the parent module and the
    # late-import path so whichever one resolves first hits our fake.
    import lib.trading.tradingview_ta_machine as _ta_machine_mod  # noqa: PLC0415

    monkeypatch.setattr(
        _ta_machine_mod,
        "build_tradingview_ta_machine",
        lambda *, fetch_live, limit: fake_machine,
    )

    result = tradingview.handle({"action": "sweep", "limit": 3})

    assert result["ok"] is True
    assert result["action"] == "sweep"
    data = result["data"]
    assert data["session_id"] == "session-X"
    assert data["mutation_enabled"] is False
    assert data["symbol_count"] == 1
    assert data["symbols"][0]["symbol"] == "BTC"
    assert data["symbols"][0]["artifacts_ok"] == 2  # 2 of 3 artifacts were ok
    # ``capture_sweep`` must have been called with the limited symbol slice.
    name, _args, kwargs = constructed[-1].calls[-1]
    assert name == "capture_sweep"
    assert kwargs["primary_timeframe"] == "60"


def test_sweep_invalid_limit_errors(monkeypatch):
    _patch_orchestrator(monkeypatch)

    result = tradingview.handle({"action": "sweep", "limit": "nope"})

    assert result["ok"] is False
    assert result["action"] == "sweep"
    assert "invalid limit" in result["error"]


def test_action_exception_is_caught_and_returned_as_error(monkeypatch):
    """Implementations may raise; the dispatcher must wrap as JSON error."""

    def boom(_payload):
        raise RuntimeError("boom")

    monkeypatch.setitem(tradingview._ACTION_TABLE, "probe", boom)

    result = tradingview.handle({"action": "probe"})

    assert result["ok"] is False
    assert result["action"] == "probe"
    assert "RuntimeError" in result["error"]
    assert "boom" in result["error"]


# ---------------------------------------------------------------------------
# 4. Read-only invariants
# ---------------------------------------------------------------------------


def test_blocked_mutation_actions_are_rejected_by_dispatch():
    for blocked in tradingview.BLOCKED_MUTATION_ACTIONS:
        result = tradingview.handle({"action": blocked})

        assert result["ok"] is False, f"{blocked!r} should be blocked"
        assert result["action"] == blocked
        assert "read-only" in result["error"]


def test_action_table_only_exposes_read_only_actions():
    """No mutation method names appear in the dispatch table or its values."""
    assert set(tradingview._ACTION_TABLE.keys()) == set(tradingview.VALID_ACTIONS)
    for blocked in tradingview.BLOCKED_MUTATION_ACTIONS:
        assert blocked not in tradingview._ACTION_TABLE


def test_source_does_not_reference_mutation_methods():
    """Static check: parse the source and confirm zero mutation calls.

    This catches a future regression where someone wires up a mutation
    method (e.g. ``orch.alert_create(...)``) inside an action body.
    """
    source = Path(tradingview.__file__).read_text(encoding="utf-8")

    # Mutation method names that would only appear if a developer
    # actually called them. The string ``alert_create`` legitimately
    # appears once in the ``BLOCKED_MUTATION_ACTIONS`` tuple, so we
    # strip that section before scanning.
    sentinel = "BLOCKED_MUTATION_ACTIONS = ("
    end = ")"
    start = source.index(sentinel)
    stop = source.index(end, start) + 1
    scrubbed = source[:start] + source[stop:]

    forbidden_calls = [
        ".set_symbol(",
        ".set_timeframe(",
        ".setup_chart(",
        ".apply_indicator_stack(",
        ".pine_set_from_file(",
        ".pine_compile(",
        ".pine_save(",
        ".pine_promote(",
        ".pine_open(",
        ".alert_create(",
        ".alert_delete(",
        ".clear_indicators(",
        ".add_indicator(",
        ".remove_indicator(",
    ]
    for needle in forbidden_calls:
        assert needle not in scrubbed, (
            f"tradingview tool unexpectedly calls mutation method: {needle}"
        )


def test_orchestrator_factory_forces_mutation_disabled(monkeypatch):
    constructed = _patch_orchestrator(monkeypatch)

    # Even when env var explicitly enables mutation, the factory must
    # construct the orchestrator with ``mutation_enabled=False``.
    monkeypatch.setenv("SAPPHIRE_TV_MUTATION_ENABLED", "1")

    tradingview._make_orchestrator()

    assert constructed[-1].mutation_enabled is False


# ---------------------------------------------------------------------------
# 5. Shim
# ---------------------------------------------------------------------------


def test_top_level_shim_re_exports_handle():
    spec = importlib.util.spec_from_file_location(
        "tradingview_shim", TOOLS / "tradingview.py"
    )
    shim = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(shim)

    assert hasattr(shim, "handle")
    assert hasattr(shim, "run")
    assert hasattr(shim, "main")
    assert hasattr(shim, "VALID_ACTIONS")


def test_shim_handle_routes_to_real_dispatcher(monkeypatch):
    spec = importlib.util.spec_from_file_location(
        "tradingview_shim2", TOOLS / "tradingview.py"
    )
    shim = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(shim)

    # Calling ``handle`` on the shim with an unknown action should
    # produce the same shape the real dispatcher emits.
    result = shim.handle({"action": "definitely-not-a-real-action"})

    assert result["ok"] is False
    assert "unknown action" in result["error"]
    assert "valid_actions" in result
