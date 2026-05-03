"""Tests for the Sapphire timetravel plugin tool."""

from __future__ import annotations

import importlib.util
import io
import json
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

INTERNAL = ROOT / "plugins" / "claw-sapphire" / "tools" / "internal" / "timetravel.py"

_spec = importlib.util.spec_from_file_location("timetravel_internal", INTERNAL)
assert _spec is not None and _spec.loader is not None
_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_module)


def _row(symbol: str, ts: str, **extras: Any) -> dict[str, Any]:
    payload = {
        "symbol": symbol,
        "timeframe": "1h",
        "edge_score": 0.42,
        "consensus": "AGREE_BULL",
        "contributing": 2,
        "corroborated_by": ["tradingview", "telegram"],
        "divergent_sources": [],
        "bull_sources": ["tradingview", "telegram"],
        "bear_sources": [],
        "neutral_sources": [],
        "freshness_seconds": 60.0,
        "raw_score": 0.4,
        "agreement_multiplier": 1.05,
        "contradict_factor": 1.0,
        "total_weight": 0.8,
        "generated_at": ts,
    }
    payload.update(extras)
    return payload


@pytest.fixture
def fake_repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Set up a fake repo and rebind ``lib.timetravel.snapshot`` roots."""
    base = tmp_path / "repo"
    for sub in (
        "data/correlated_signals/2026-04-26",
        "data/narratives/2026-04-26",
        "data/cross_asset/2026-04-26",
        "data/macro/2026-04-26",
        "data/onchain/2026-04-26",
        "data/events",
    ):
        (base / sub).mkdir(parents=True)

    cs = base / "data" / "correlated_signals" / "2026-04-26" / "signals.jsonl"
    with cs.open("w", encoding="utf-8") as fh:
        for row in [
            _row("BTC", "2026-04-26T10:00:00+00:00"),
            _row("ETH", "2026-04-26T10:30:00+00:00"),
        ]:
            fh.write(json.dumps(row, sort_keys=True, default=str) + "\n")

    # Pollution-resistant import: other plugin tests can leave the
    # `lib.timetravel.*` modules + the alias `timetravel_internal` cached
    # in `sys.modules` with stale `SCOPE_TO_ROOT`. Drop any existing entries
    # so the monkeypatch below applies to the freshly-imported module that
    # the internal tool also uses.
    for cached in [
        k for k in list(sys.modules) if k.startswith("lib.timetravel") or k == "timetravel_internal"
    ]:
        sys.modules.pop(cached, None)
    import lib.timetravel.snapshot as st_mod

    # Reload the internal tool too, so it binds to the freshly-imported
    # snapshot module (the one we're about to monkeypatch).
    _spec_local = importlib.util.spec_from_file_location("timetravel_internal", INTERNAL)
    assert _spec_local is not None and _spec_local.loader is not None
    _module_local = importlib.util.module_from_spec(_spec_local)
    _spec_local.loader.exec_module(_module_local)
    sys.modules["timetravel_internal"] = _module_local
    # Rebind the module-level alias so subsequent tests see the fresh one.
    globals()["_module"] = _module_local

    fake_map = {
        "correlated_signals": base / "data" / "correlated_signals",
        "narratives": base / "data" / "narratives",
        "cross_asset": base / "data" / "cross_asset",
        "macro": base / "data" / "macro",
        "onchain": base / "data" / "onchain",
        "events_bus": base / "data" / "events",
    }
    monkeypatch.setattr(st_mod, "REPO_ROOT", base)
    monkeypatch.setattr(st_mod, "SCOPE_TO_ROOT", fake_map)
    return base


def test_index_status_action_returns_status_when_missing(tmp_path: Path) -> None:
    response = _module.handle(
        {"action": "index-status", "cache_path": str(tmp_path / "missing.json")}
    )
    assert response["ok"] is True
    assert response["status"]["exists"] is False
    assert "snapshot" in response["valid_actions"]


def test_status_alias(tmp_path: Path) -> None:
    response = _module.handle({"action": "status", "cache_path": str(tmp_path / "missing.json")})
    assert response["ok"] is True


def test_snapshot_action_requires_at(tmp_path: Path, fake_repo: Path) -> None:
    response = _module.handle({"action": "snapshot", "cache_path": str(tmp_path / "idx.json")})
    assert "error" in response


def test_snapshot_action_returns_rows(tmp_path: Path, fake_repo: Path) -> None:
    response = _module.handle(
        {
            "action": "snapshot",
            "at": "2026-04-26T11:00:00+00:00",
            "cache_path": str(tmp_path / "idx.json"),
        }
    )
    assert response["ok"] is True
    entries = response["snapshot"]["entries"]
    cs = entries["correlated_signals"]
    assert cs["row_count"] == 2


def test_snapshot_action_truncates_rows(tmp_path: Path, fake_repo: Path) -> None:
    response = _module.handle(
        {
            "action": "snapshot",
            "at": "2026-04-26T11:00:00+00:00",
            "cache_path": str(tmp_path / "idx.json"),
            "max_rows_per_scope": 1,
        }
    )
    cs = response["snapshot"]["entries"]["correlated_signals"]
    assert len(cs["rows"]) == 1
    assert cs.get("truncated") is True


def test_replay_action_returns_replay_result(tmp_path: Path, fake_repo: Path) -> None:
    response = _module.handle(
        {
            "action": "replay",
            "at": "2026-04-26T11:00:00+00:00",
            "cache_path": str(tmp_path / "idx.json"),
        }
    )
    assert response["ok"] is True
    assert "result" in response
    pairs = {(s["symbol"], s["timeframe"]) for s in response["result"]["correlated_signals"]}
    assert ("BTC", "1h") in pairs
    assert ("ETH", "1h") in pairs


def test_diff_action_returns_summary(tmp_path: Path, fake_repo: Path) -> None:
    response = _module.handle(
        {
            "action": "diff",
            "at": "2026-04-26T11:00:00+00:00",
            "cache_path": str(tmp_path / "idx.json"),
        }
    )
    assert response["ok"] is True
    assert "summary" in response
    assert response["summary"]["total"] >= 2


def test_invalid_at_returns_error(tmp_path: Path, fake_repo: Path) -> None:
    response = _module.handle(
        {
            "action": "snapshot",
            "at": "not-a-timestamp",
            "cache_path": str(tmp_path / "idx.json"),
        }
    )
    assert "error" in response


def test_invalid_scope_returns_error(tmp_path: Path) -> None:
    response = _module.handle(
        {
            "action": "snapshot",
            "at": "2026-04-26T11:00:00+00:00",
            "scope": ["does-not-exist"],
            "cache_path": str(tmp_path / "idx.json"),
        }
    )
    assert "error" in response


def test_unknown_action_returns_valid_actions(tmp_path: Path) -> None:
    response = _module.handle({"action": "do-the-thing"})
    assert "error" in response
    assert "snapshot" in response["valid_actions"]


def test_main_reads_stdin_and_writes_json(tmp_path: Path, fake_repo: Path) -> None:
    inbuf = io.StringIO(
        json.dumps(
            {
                "action": "index-status",
                "cache_path": str(tmp_path / "idx.json"),
            }
        )
    )
    outbuf = io.StringIO()
    rc = _module.main(stream_in=inbuf, stream_out=outbuf)
    assert rc == 0
    body = json.loads(outbuf.getvalue())
    assert body["ok"] is True


def test_main_rejects_invalid_json() -> None:
    inbuf = io.StringIO("{not valid")
    outbuf = io.StringIO()
    rc = _module.main(stream_in=inbuf, stream_out=outbuf)
    assert rc == 2


def test_main_rejects_non_object_payload() -> None:
    inbuf = io.StringIO("[1, 2, 3]")
    outbuf = io.StringIO()
    rc = _module.main(stream_in=inbuf, stream_out=outbuf)
    assert rc == 2
