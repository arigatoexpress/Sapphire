"""Content calendar.

Weekly slots:
  Mon — weekly crypto brief
  Wed — AI intel
  Fri — security digest
  Daily — market pulse tweet (X only)

`today_plan()` returns the slots that should fire today. The LaunchAgent
runs once a day at 06:00, reads this, and dispatches each slot through the
pipeline: generate_report → format_* → quality.check → publisher.publish.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

# Weekday values match datetime.weekday(): Mon=0, Tue=1, ..., Sun=6
WEEKLY_CALENDAR: dict[int, list[str]] = {
    0: ["weekly_crypto_brief"],   # Monday
    2: ["ai_intel"],              # Wednesday
    4: ["security_digest"],       # Friday
}

DAILY_SLOTS: list[str] = ["market_pulse"]

TARGET_PLATFORMS: dict[str, list[str]] = {
    "weekly_crypto_brief": ["linkedin", "substack", "x"],
    "ai_intel": ["linkedin", "substack", "x"],
    "security_digest": ["linkedin", "substack", "x"],
    "market_pulse": ["x"],
}


@dataclass
class Slot:
    report_kind: str
    platforms: list[str]

    def to_dict(self) -> dict:
        return {"report_kind": self.report_kind, "platforms": self.platforms}


def plan_for(day: datetime) -> list[Slot]:
    """Slots scheduled for a given date."""
    out: list[Slot] = []
    for kind in WEEKLY_CALENDAR.get(day.weekday(), []):
        out.append(Slot(kind, TARGET_PLATFORMS.get(kind, [])))
    for kind in DAILY_SLOTS:
        out.append(Slot(kind, TARGET_PLATFORMS.get(kind, [])))
    return out


def today_plan() -> list[Slot]:
    return plan_for(datetime.now())
