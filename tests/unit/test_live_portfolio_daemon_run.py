from __future__ import annotations

import importlib.util
import json
from datetime import UTC, datetime
from pathlib import Path

from lib.live_portfolio.ledger import LiveLedger
from tests.unit.test_live_portfolio_ledger import record

ROOT = Path(__file__).resolve().parents[2]
RUN_PATH = ROOT / "services" / "live_portfolio_daemon" / "run.py"
spec = importlib.util.spec_from_file_location("live_portfolio_daemon_run", RUN_PATH)
assert spec is not None and spec.loader is not None
daemon = importlib.util.module_from_spec(spec)
spec.loader.exec_module(daemon)


def test_run_once_no_accounts(tmp_path) -> None:
    out = daemon.run_once(ledger_root=tmp_path)
    assert out["ok"] is True
    assert out["accounts"] == []


def test_run_once_writes_status(tmp_path) -> None:
    ledger = LiveLedger(tmp_path)
    ledger.append(record())
    out = daemon.run_once(ledger_root=tmp_path, now=datetime(2026, 4, 30, tzinfo=UTC))
    assert out["statuses"]
    path = Path(out["statuses"][0]["path"])
    assert path.exists()


def test_run_once_adds_provenance(tmp_path) -> None:
    ledger = LiveLedger(tmp_path)
    ledger.append(record())
    out = daemon.run_once(ledger_root=tmp_path, now=datetime(2026, 4, 30, tzinfo=UTC))
    status = out["statuses"][0]["status"]
    assert status["provenance"]["generator"] == "services.live_portfolio_daemon"


def test_load_returns_skips_bad_rows(tmp_path) -> None:
    path = tmp_path / "returns.jsonl"
    path.write_text('{"return": 0.01}\nnot-json\n{"return": "bad"}\n', encoding="utf-8")
    assert daemon._load_returns(path) == [0.01]


def test_run_once_uses_returns_file(tmp_path) -> None:
    ledger = LiveLedger(tmp_path)
    ledger.append(record(fill_at="2026-04-01T04:06:00Z"))
    returns = tmp_path / "returns.jsonl"
    returns.write_text("\n".join(json.dumps({"return": 0.01}) for _ in range(14)), encoding="utf-8")
    out = daemon.run_once(
        ledger_root=tmp_path,
        returns_path=returns,
        now=datetime(2026, 4, 30, tzinfo=UTC),
    )
    assert out["statuses"][0]["status"]["gate_status"] == "satisfied"


def test_publish_change_off_by_default(monkeypatch) -> None:
    monkeypatch.delenv("SAPPHIRE_LIVE_PORTFOLIO_PUBLISH_BUS", raising=False)
    assert daemon._publish_change({"x": 1}) is None


def test_main_once_outputs_json(tmp_path, capsys) -> None:
    rc = daemon.main(["--ledger-root", str(tmp_path), "--once"])
    out = capsys.readouterr().out
    assert rc == 0
    assert json.loads(out)["ok"] is True


def test_status_jsonl_path_is_under_account(tmp_path) -> None:
    ledger = LiveLedger(tmp_path)
    ledger.append(record())
    out = daemon.run_once(ledger_root=tmp_path, now=datetime(2026, 4, 30, tzinfo=UTC))
    assert "EXAMPLE-account-hash" in out["statuses"][0]["path"]
