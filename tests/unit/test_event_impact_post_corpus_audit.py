from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

from lib.event_impact.event_corpus import HistoricalEvent
from lib.event_impact.impact_modeler import ImpactModel, ImpactProfile, PriceBar
from services.event_impact.audit import audit_post_corpus_events, main

BASE = datetime(2024, 1, 1, tzinfo=UTC)


def _model() -> ImpactModel:
    return ImpactModel(
        generated_at=(BASE + timedelta(days=1)).isoformat(),
        horizons_hours=(6,),
        profiles=(
            ImpactProfile(
                "fomc_decision",
                "rate_hike",
                "BTC",
                6,
                2.0,
                2.0,
                8,
                1.0,
                (-1.0, 5.0),
                0.75,
            ),
        ),
    )


def _event(
    event_id: str,
    when: datetime,
    *,
    category: str = "fomc_decision",
    sub_category: str = "rate_hike",
    assets: tuple[str, ...] = ("BTC",),
) -> HistoricalEvent:
    return HistoricalEvent(
        event_id=event_id,
        timestamp=when,
        category=category,
        sub_category=sub_category,
        title=event_id,
        assets=assets,
        metadata={"source_url": "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm"},
    )


def _bars(*pairs: tuple[datetime, float]) -> list[PriceBar]:
    return [PriceBar(timestamp=ts, close=close) for ts, close in pairs]


def _write_events(path, events: list[HistoricalEvent]) -> None:
    path.write_text(
        "".join(json.dumps(event.to_dict(), sort_keys=True) + "\n" for event in events),
        encoding="utf-8",
    )


def test_post_corpus_audit_filters_pre_cutoff_events_and_scores_sign_accuracy() -> None:
    post = _event("post_hike", BASE + timedelta(days=2))
    pre = _event("pre_hike", BASE)
    report = audit_post_corpus_events(
        model=_model(),
        events=[post, pre],
        bars_by_asset={
            "BTC": _bars(
                (post.timestamp, 100.0),
                (post.timestamp + timedelta(hours=6), 103.0),
            )
        },
        horizons_hours=(6,),
    )

    rendered = report.to_dict()
    assert rendered["summary"]["post_corpus_events"] == 1
    assert rendered["summary"]["skipped_pre_cutoff_events"] == 1
    assert rendered["summary"]["sign_accuracy"] == 1.0
    assert rendered["summary"]["interval_hit_rate"] == 1.0
    assert rendered["rows"][0]["event_id"] == "post_hike"
    assert rendered["rows"][0]["actual_return_pct"] == 3.0


def test_post_corpus_audit_flags_sign_and_interval_misses() -> None:
    post = _event("surprise_hike", BASE + timedelta(days=3))
    report = audit_post_corpus_events(
        model=_model(),
        events=[post],
        bars_by_asset={
            "BTC": _bars(
                (post.timestamp, 100.0),
                (post.timestamp + timedelta(hours=6), 90.0),
            )
        },
        horizons_hours=(6,),
    ).to_dict()

    row = report["rows"][0]
    assert row["sign_scored"] is True
    assert row["sign_correct"] is False
    assert row["within_confidence_interval"] is False
    assert report["summary"]["sign_accuracy"] == 0.0
    assert report["summary"]["mean_absolute_error_pct"] == 12.0


def test_post_corpus_audit_keeps_no_data_and_missing_bars_unscored() -> None:
    hack = _event(
        "exchange_hack_post",
        BASE + timedelta(days=4),
        category="exchange_hack",
        sub_category="bridge_exploit",
        assets=("ETH",),
    )
    missing = _event("missing_bars_post", BASE + timedelta(days=5), assets=("SOL",))
    report = audit_post_corpus_events(
        model=_model(),
        events=[hack, missing],
        bars_by_asset={
            "ETH": _bars(
                (hack.timestamp, 100.0),
                (hack.timestamp + timedelta(hours=6), 105.0),
            )
        },
        horizons_hours=(6,),
    ).to_dict()

    by_event = {row["event_id"]: row for row in report["rows"]}
    assert by_event["exchange_hack_post"]["matched_level"] == "no_data"
    assert by_event["exchange_hack_post"]["skip_reason"] == "no_model_profile"
    assert by_event["missing_bars_post"]["skip_reason"] == "missing_price_window"
    assert report["summary"]["sign_scored"] == 0
    assert report["summary"]["interval_scored"] == 0


def test_post_corpus_audit_cli_writes_deterministic_json(tmp_path) -> None:
    event = _event("cli_hike", BASE + timedelta(days=2))
    model_path = tmp_path / "model.json"
    events_path = tmp_path / "heldout.jsonl"
    bars_path = tmp_path / "bars.json"
    output_path = tmp_path / "audit.json"

    model_path.write_text(json.dumps(_model().to_dict(), sort_keys=True), encoding="utf-8")
    _write_events(events_path, [event])
    bars_path.write_text(
        json.dumps(
            {
                "BTC": [
                    {"timestamp": event.timestamp.isoformat(), "close": 100.0},
                    {
                        "timestamp": (event.timestamp + timedelta(hours=6)).isoformat(),
                        "close": 102.0,
                    },
                ]
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )

    assert (
        main(
            [
                "--model",
                str(model_path),
                "--events",
                str(events_path),
                "--bars-json",
                str(bars_path),
                "--horizon",
                "6",
                "--output",
                str(output_path),
            ]
        )
        == 0
    )
    rendered = json.loads(output_path.read_text(encoding="utf-8"))
    assert rendered["ok"] is True
    assert rendered["audit_cutoff"] == "2024-01-02T00:00:00+00:00"
    assert rendered["rows"][0]["event_id"] == "cli_hike"
