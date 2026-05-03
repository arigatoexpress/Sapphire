"""Tests for the pine_generation plugin tool."""

from __future__ import annotations

import importlib.util
import io
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

INTERNAL = ROOT / "plugins" / "claw-sapphire" / "tools" / "internal" / "pine_generation.py"

_spec = importlib.util.spec_from_file_location("pine_generation_internal", INTERNAL)
assert _spec is not None and _spec.loader is not None
pg = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = pg
_spec.loader.exec_module(pg)


# ---------------------------------------------------------------------------
# 1) status (read-only)
# ---------------------------------------------------------------------------


def test_status_action() -> None:
    out = pg.handle({"action": "status"})
    assert out["ok"] is True
    assert "generate" in out["actions"]
    assert "RegimeAwareRSI" in out["supported_strategies"]
    assert out["live_push_gate"] == "SAPPHIRE_PINE_TV_PUSH_LIVE"


def test_status_default_action() -> None:
    """No action defaults to status."""
    out = pg.handle({})
    assert out["ok"] is True
    assert "version" in out


# ---------------------------------------------------------------------------
# 2) generate
# ---------------------------------------------------------------------------


def test_generate_action_smoke() -> None:
    out = pg.handle(
        {
            "action": "generate",
            "strategy": "RegimeAwareRSI",
            "symbol": "BTC-USD",
        }
    )
    assert out["ok"] is True
    assert "//@version=5" in out["pine_source"]
    assert out["validator"]["ok"] is True


def test_generate_action_with_params() -> None:
    out = pg.handle(
        {
            "action": "generate",
            "strategy": "SapphireComposite",
            "symbol": "BTC-USD",
            "params": {"rsi_period": 21, "composite_threshold": 65.0},
        }
    )
    assert out["ok"] is True
    assert "input.int(21," in out["pine_source"]
    assert "65.00" in out["pine_source"]


def test_generate_action_persist(tmp_path: Path) -> None:
    out = pg.handle(
        {
            "action": "generate",
            "strategy": "BaseStrategy",
            "symbol": "BTC-USD",
            "persist": True,
            "output_root": str(tmp_path),
        }
    )
    assert out["ok"] is True
    assert "path" in out
    persisted = Path(out["path"])
    assert persisted.exists()
    assert persisted.suffix == ".pine"


def test_generate_action_missing_strategy() -> None:
    out = pg.handle({"action": "generate", "symbol": "BTC"})
    assert out["ok"] is False
    assert "strategy" in out["error"]


def test_generate_action_missing_symbol() -> None:
    out = pg.handle({"action": "generate", "strategy": "RegimeAwareRSI"})
    assert out["ok"] is False
    assert "symbol" in out["error"]


def test_generate_action_unsupported_strategy() -> None:
    out = pg.handle({"action": "generate", "strategy": "GhostStrategy", "symbol": "BTC"})
    assert out["ok"] is False


# ---------------------------------------------------------------------------
# 3) latest
# ---------------------------------------------------------------------------


def test_latest_empty_directory(tmp_path: Path) -> None:
    out = pg.handle({"action": "latest", "output_root": str(tmp_path)})
    assert out["ok"] is True
    assert out["files"] == []


def test_latest_with_files(tmp_path: Path) -> None:
    date_dir = tmp_path / "2026-04-29"
    date_dir.mkdir()
    (date_dir / "alpha.pine").write_text('//@version=5\nstrategy("a")\nplot(close)\n')
    (date_dir / "beta.pine").write_text('//@version=5\nstrategy("b")\nplot(close)\n')
    out = pg.handle({"action": "latest", "output_root": str(tmp_path)})
    assert out["ok"] is True
    assert len(out["files"]) == 2
    names = sorted(f["name"] for f in out["files"])
    assert names == ["alpha.pine", "beta.pine"]
    assert out["directory"] == str(date_dir)


def test_latest_picks_most_recent_date_dir(tmp_path: Path) -> None:
    older = tmp_path / "2026-04-01"
    newer = tmp_path / "2026-04-29"
    older.mkdir()
    newer.mkdir()
    (older / "old.pine").write_text('//@version=5\nstrategy("a")\nplot(close)\n')
    (newer / "new.pine").write_text('//@version=5\nstrategy("b")\nplot(close)\n')
    out = pg.handle({"action": "latest", "output_root": str(tmp_path)})
    assert out["directory"] == str(newer)
    assert [f["name"] for f in out["files"]] == ["new.pine"]


# ---------------------------------------------------------------------------
# 4) validate
# ---------------------------------------------------------------------------


def test_validate_action_inline() -> None:
    src = '//@version=5\nstrategy("Test")\nplot(close)\n'
    out = pg.handle({"action": "validate", "pine_source": src})
    assert out["ok"] is True


def test_validate_action_rejects_bad() -> None:
    out = pg.handle({"action": "validate", "pine_source": "no version directive"})
    assert out["ok"] is False
    assert any("//@version=5" in e for e in out["validator"]["errors"])


def test_validate_action_from_path(tmp_path: Path) -> None:
    p = tmp_path / "x.pine"
    p.write_text('//@version=5\nstrategy("Test")\nplot(close)\n')
    out = pg.handle({"action": "validate", "pine_path": str(p)})
    assert out["ok"] is True


def test_validate_action_missing_input() -> None:
    out = pg.handle({"action": "validate"})
    assert out["ok"] is False


# ---------------------------------------------------------------------------
# 5) build
# ---------------------------------------------------------------------------


def test_build_action_with_synthetic_backtest_data(tmp_path: Path) -> None:
    bt = tmp_path / "backtests"
    bt.mkdir()
    payload = {
        "computed_at": "2026-04-29T00:00:00+00:00",
        "total_backtests": 1,
        "results": [
            {
                "strategy_cls": "SapphireComposite",
                "strategy_name": "Composite(p=14)",
                "symbol": "BTC-USD",
                "params": {"rsi_period": 14, "sl_pct": 0.05, "tp_pct": 0.10},
                "sortino": 2.5,
                "sharpe": 1.7,
                "win_rate": 0.6,
                "total_trades": 25,
                "total_return_pct": 0.45,
                "max_drawdown_pct": 0.08,
                "calmar": 1.5,
                "profit_factor": 2.2,
            }
        ],
    }
    (bt / "best_per_symbol_20260429T000000Z.json").write_text(json.dumps(payload))
    out_root = tmp_path / "out"
    out = pg.handle(
        {
            "action": "build",
            "backtest_dir": str(bt),
            "output_root": str(out_root),
        }
    )
    assert out["ok"] is True
    assert out["manifest"]["summary"]["generated"] == 1
    artifacts = out["manifest"]["artifacts"]
    assert len(artifacts) == 1
    assert artifacts[0]["strategy"] == "SapphireComposite"


def test_build_action_with_no_data(tmp_path: Path) -> None:
    """Build is safe when no backtest data is present — produces empty manifest."""
    out_root = tmp_path / "out"
    out = pg.handle(
        {
            "action": "build",
            "backtest_dir": str(tmp_path / "missing"),
            "output_root": str(out_root),
        }
    )
    assert out["ok"] is True
    assert out["manifest"]["summary"]["generated"] == 0


# ---------------------------------------------------------------------------
# 6) push-to-tv (operator gate)
# ---------------------------------------------------------------------------


def test_push_refused_when_env_flag_unset(monkeypatch) -> None:
    monkeypatch.delenv("SAPPHIRE_PINE_TV_PUSH_LIVE", raising=False)
    out = pg.handle(
        {
            "action": "push-to-tv",
            "pine_source": '//@version=5\nstrategy("a")\nplot(close)\n',
            "confirm": True,
        }
    )
    assert out["ok"] is False
    assert "SAPPHIRE_PINE_TV_PUSH_LIVE" in out["error"]


def test_push_refused_when_confirm_missing(monkeypatch) -> None:
    monkeypatch.setenv("SAPPHIRE_PINE_TV_PUSH_LIVE", "1")
    out = pg.handle(
        {
            "action": "push-to-tv",
            "pine_source": '//@version=5\nstrategy("a")\nplot(close)\n',
        }
    )
    assert out["ok"] is False
    assert "confirm" in out["error"]


def test_push_dry_run_when_gated(monkeypatch) -> None:
    monkeypatch.setenv("SAPPHIRE_PINE_TV_PUSH_LIVE", "1")
    out = pg.handle(
        {
            "action": "push-to-tv",
            "pine_source": '//@version=5\nstrategy("a")\nplot(close)\n',
            "confirm": True,
            "dry_run": True,
        }
    )
    assert out["ok"] is True
    assert out["push_result"]["status"] == "dry_run"


def test_push_underscore_alias(monkeypatch) -> None:
    """`push_to_tv` and `push-to-tv` should both be valid action names."""
    monkeypatch.delenv("SAPPHIRE_PINE_TV_PUSH_LIVE", raising=False)
    out = pg.handle(
        {
            "action": "push_to_tv",
            "pine_source": '//@version=5\nstrategy("a")\nplot(close)\n',
            "confirm": True,
        }
    )
    assert out["ok"] is False
    assert "SAPPHIRE_PINE_TV_PUSH_LIVE" in out["error"]


def test_push_with_path(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("SAPPHIRE_PINE_TV_PUSH_LIVE", "1")
    p = tmp_path / "x.pine"
    p.write_text('//@version=5\nstrategy("a")\nplot(close)\n')
    out = pg.handle(
        {
            "action": "push-to-tv",
            "pine_path": str(p),
            "confirm": True,
            "dry_run": True,
        }
    )
    assert out["ok"] is True
    assert out["push_result"]["bytes"] > 0


def test_push_invokes_mocked_mcp(monkeypatch) -> None:
    """When SAPPHIRE_PINE_TV_PUSH_LIVE=1 + confirm=true + dry_run=False, the
    MCP invocation function is called. We monkeypatch it to assert the call."""
    monkeypatch.setenv("SAPPHIRE_PINE_TV_PUSH_LIVE", "1")
    captured: dict = {}

    def fake_invoke(pine_source, *, title, dry_run):
        captured["pine_source"] = pine_source
        captured["title"] = title
        captured["dry_run"] = dry_run
        return {"ok": True, "status": "mocked", "message": "ok"}

    monkeypatch.setattr(pg, "_invoke_tv_mcp", fake_invoke)
    src = '//@version=5\nstrategy("a")\nplot(close)\n'
    out = pg.handle(
        {
            "action": "push-to-tv",
            "pine_source": src,
            "confirm": True,
            "dry_run": False,
            "title": "MyTitle",
        }
    )
    assert out["ok"] is True
    assert captured["pine_source"] == src
    assert captured["title"] == "MyTitle"
    assert captured["dry_run"] is False


# ---------------------------------------------------------------------------
# 7) main() stdin/stdout entrypoint
# ---------------------------------------------------------------------------


def test_main_reads_stdin_writes_json() -> None:
    out_buf = io.StringIO()
    rc = pg.main(
        stream_in=io.StringIO(json.dumps({"action": "status"})),
        stream_out=out_buf,
    )
    assert rc == 0
    parsed = json.loads(out_buf.getvalue())
    assert parsed["ok"] is True


def test_main_handles_invalid_json() -> None:
    out_buf = io.StringIO()
    rc = pg.main(stream_in=io.StringIO("not json"), stream_out=out_buf)
    assert rc == 2
    parsed = json.loads(out_buf.getvalue())
    assert parsed["ok"] is False


def test_main_handles_unknown_action() -> None:
    out_buf = io.StringIO()
    rc = pg.main(
        stream_in=io.StringIO(json.dumps({"action": "fooble"})),
        stream_out=out_buf,
    )
    assert rc == 1
    parsed = json.loads(out_buf.getvalue())
    assert parsed["ok"] is False
    assert "valid_actions" in parsed


def test_main_handles_empty_stdin() -> None:
    out_buf = io.StringIO()
    rc = pg.main(stream_in=io.StringIO(""), stream_out=out_buf)
    # Empty stdin => default action `status`
    assert rc == 0
    parsed = json.loads(out_buf.getvalue())
    assert parsed["ok"] is True


# ---------------------------------------------------------------------------
# 8) handle dispatch + error wrapping
# ---------------------------------------------------------------------------


def test_handle_rejects_non_dict_payload() -> None:
    out = pg.handle("not a dict")  # type: ignore[arg-type]
    assert out["ok"] is False


def test_handle_unknown_action_returns_valid_actions() -> None:
    out = pg.handle({"action": "wat"})
    assert out["ok"] is False
    assert "valid_actions" in out
