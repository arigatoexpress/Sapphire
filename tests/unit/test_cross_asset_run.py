from __future__ import annotations

from datetime import UTC, datetime

from services.cross_asset import run

FROZEN_NOW = datetime(2026, 4, 28, 12, 0, tzinfo=UTC)


def test_build_snapshot_is_cache_or_dry_run_by_default(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr("lib.cross_asset.sources.CACHE_ROOT", tmp_path)
    snapshot = run.build_snapshot(
        assets=["BTC", "ETH", "DXY"], live=False, now=FROZEN_NOW, limit=120
    )
    assert snapshot["ok"] is True
    assert snapshot["mode"] == "cache_or_dry_run"
    assert snapshot["provenance"]["schema_version"] == 1
    assert snapshot["regime"]["label"]


def test_persist_snapshot_writes_matrix_regime_and_sidecar(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("lib.cross_asset.sources.CACHE_ROOT", tmp_path / "cache")
    snapshot = run.build_snapshot(assets=["BTC", "ETH"], live=False, now=FROZEN_NOW, limit=120)
    artifacts = run.persist_snapshot(snapshot, output_root=tmp_path / "out", now=FROZEN_NOW)
    assert artifacts["matrix"].exists()
    assert artifacts["matrix_sidecar"].exists()
    assert artifacts["regimes"].exists()
    assert artifacts["lead_lag"].exists()


def test_run_once_does_not_publish_by_default(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("lib.cross_asset.sources.CACHE_ROOT", tmp_path / "cache")
    result = run.run_once(
        assets=["BTC", "ETH"],
        publish=False,
        output_root=tmp_path / "out",
        now=FROZEN_NOW,
    )
    assert result["ok"] is True
    assert result["published"] == {}


def test_publish_snapshot_emits_regime_and_breakdowns(monkeypatch) -> None:
    published = []

    class Bus:
        def publish(self, event_type, data, source=None):
            published.append((event_type, data, source))
            return "1-0"

    monkeypatch.setattr("lib.core.event_bus.get_bus", lambda source=None: Bus())
    snapshot = {
        "regime": {"label": "risk_on_correlated"},
        "breakdowns": [{"pair": ["BTC", "ETH"]}],
    }
    counts = run.publish_snapshot(snapshot)
    assert counts == {"regime.shift.detected": 1, "correlation.breakdown": 1}
    assert [item[0] for item in published] == ["regime.shift.detected", "correlation.breakdown"]


def test_main_once_writes_summary(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.setattr("lib.cross_asset.sources.CACHE_ROOT", tmp_path / "cache")
    rc = run.main(["--once", "--assets", "BTC,ETH", "--output-root", str(tmp_path / "out")])
    captured = capsys.readouterr()
    assert rc == 0
    assert '"ok": true' in captured.out
