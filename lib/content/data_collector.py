"""Content engine data collection layer.

Aggregates structured facts from Sapphire's live data files for use by the
report generator.  This is a thin coordination layer — the actual data lives
in data/ and is read by functions in report_generator.py.

Exposes ``ContentDataCollector`` which pulls all data sources in one call
and returns a dict of typed fact objects suitable for ``Report.facts``.
"""

from __future__ import annotations

import contextlib
import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

_REPO = Path(__file__).resolve().parents[2]


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            with contextlib.suppress(json.JSONDecodeError):
                rows.append(json.loads(line))
    return rows


def _read_json(path: Path, default: Any = None) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


@dataclass
class CollectedData:
    predictions: list[dict]
    portfolio: dict
    signals: list[dict]
    events: list[dict]
    threat_summaries: list[str]
    collected_at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "predictions": self.predictions[-100:],
            "portfolio": self.portfolio,
            "signals": self.signals[-50:],
            "events": self.events[-50:],
            "threat_summaries": self.threat_summaries,
            "collected_at": self.collected_at,
        }


class ContentDataCollector:
    """Pulls all content-relevant data from Sapphire's data/ directory."""

    def __init__(self, repo_root: Path | None = None) -> None:
        self._root = repo_root or _REPO

    def collect(self) -> CollectedData:
        data = self._root / "data"
        predictions = _read_jsonl(data / "trading_predictions.jsonl")
        portfolio = _read_json(data / "paper_portfolio.json", default={})
        signals = _read_jsonl(data / "trading_signals.jsonl")
        events = _read_jsonl(data / "system_events.jsonl")

        # Latest threat intel summary files
        threat_dir = data / "threat_intel"
        threats: list[str] = []
        if threat_dir.exists():
            for f in sorted(threat_dir.glob("latest_*.md"), reverse=True)[:3]:
                threats.append(f.read_text(encoding="utf-8")[:2000])

        return CollectedData(
            predictions=predictions,
            portfolio=portfolio,
            signals=signals,
            events=events,
            threat_summaries=threats,
            collected_at=datetime.now(UTC).isoformat(),
        )
