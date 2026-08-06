from __future__ import annotations

from pathlib import Path

from lib.grok.plant_outcomes import record_closed_trade


def test_record_closed_trade(tmp_path: Path):
    p = tmp_path / "lessons.json"
    s = record_closed_trade(
        p,
        trade_id="t1",
        symbol="AXTI",
        rail="rh_agentic",
        realized_pnl_usd=50.0,
        tags=["test"],
    )
    assert s["wins"] == 1
    assert p.is_file()
    s2 = record_closed_trade(
        p,
        trade_id="t2",
        symbol="X",
        rail="rh_l2",
        realized_pnl_usd=-2.0,
    )
    assert s2["count"] == 2
    assert s2["losses"] == 1
