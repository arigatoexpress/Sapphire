from __future__ import annotations

import json
from datetime import UTC, datetime

from lib.macro.fred_loader import parse_fred_observations
from services.macro_intel import run as macro_run


class FakeFredLoader:
    def pull_series(self, series_id: str, **_kwargs):
        return parse_fred_observations(
            {
                "realtime_start": "2026-01-01",
                "realtime_end": "2026-01-31",
                "observation_start": "2026-01-01",
                "observation_end": "2026-01-31",
                "units": "lin",
                "frequency": "Daily",
                "observations": [
                    {
                        "realtime_start": "2026-01-01",
                        "realtime_end": "2026-01-31",
                        "date": "2026-01-02",
                        "value": "4.33",
                    }
                ],
            },
            series_id=series_id,
        )


def test_run_once_writes_fred_artifact_without_macro_live_env(tmp_path, monkeypatch):
    monkeypatch.delenv("SAPPHIRE_MACRO_INTEL_LIVE", raising=False)
    result = macro_run.run_once(
        include_fred=True,
        fred_series_ids=("DFF",),
        fred_loader=FakeFredLoader(),
        output_root=tmp_path,
        now=datetime(2026, 1, 5, tzinfo=UTC),
    )

    assert result["ok"] is True
    assert result["dry_run"] is True
    path = tmp_path / "2026-01-05" / "fred_observations.jsonl"
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 1
    assert rows[0]["series_id"] == "DFF"
    assert rows[0]["observation_date"] == "2026-01-02"
    assert result["writes"]["fred_observations"]["written"] == 1
