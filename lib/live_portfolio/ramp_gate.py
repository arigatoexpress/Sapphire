"""Ramp-gate evaluation for the live-capital ladder."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any, Iterable

from .ledger import LiveLedger, LiveTradeRecord, parse_utc
from .sortino import SortinoResult, last_n_sortino

SORTINO_THRESHOLD = 1.5
REQUIRED_TRADING_DAYS = 14
RAMP_NOTIONAL_BY_TIER = {1: 5.0, 2: 50.0, 3: 500.0}


@dataclass(frozen=True)
class RampGateStatus:
    """Status for the next live-capital rung."""

    current_tier: int
    target_tier: int
    gate_status: str
    days_in_tier: float
    sortino_14d: float | None
    blockers: list[str]
    sortino_reason: str
    requires_operator_approval: bool = True
    generated_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        if self.sortino_14d == float("inf"):
            data["sortino_14d"] = "inf"
        return data


def _now_utc() -> datetime:
    return datetime.now(UTC).replace(microsecond=0)


def trading_days_between(start: datetime, end: datetime) -> float:
    """Return elapsed weekday count from ``start`` to ``end``.

    The fill date itself is not counted until a later date has elapsed. This
    matches the ramp memo's soak framing: a same-day fill has zero days in tier.
    """

    if end <= start:
        return 0.0
    current: date = start.date() + timedelta(days=1)
    stop = end.date()
    days = 0
    while current <= stop:
        if current.weekday() < 5:
            days += 1
        current += timedelta(days=1)
    return float(days)


def _current_tier(records: list[LiveTradeRecord], explicit: int | None) -> int:
    if explicit is not None:
        return max(1, int(explicit))
    if not records:
        return 1
    return max(r.ramp_tier for r in records)


def _tier_start(records: list[LiveTradeRecord], tier: int) -> datetime | None:
    starts = [parse_utc(r.fill_at) for r in records if r.ramp_tier == tier]
    return min(starts) if starts else None


def evaluate_ramp_gate(
    ledger: LiveLedger,
    *,
    account_hash: str | None = None,
    returns: Iterable[float | int | str | None] = (),
    now: datetime | None = None,
    current_tier: int | None = None,
    kill_switch_active: bool = False,
    confirmation_firewall_pending: bool = False,
) -> RampGateStatus:
    """Evaluate whether the current rung has satisfied its soak gate."""

    records = ledger.load(account_hash)
    generated = (now or _now_utc()).astimezone(UTC).replace(microsecond=0)
    tier = _current_tier(records, current_tier)
    target = min(max(RAMP_NOTIONAL_BY_TIER), tier + 1)
    start = _tier_start(records, tier)
    days = trading_days_between(start, generated) if start else 0.0
    sortino: SortinoResult = last_n_sortino(returns, window=REQUIRED_TRADING_DAYS)

    blockers: list[str] = []
    if kill_switch_active:
        blockers.append("kill_switch_active")
    if confirmation_firewall_pending:
        blockers.append("confirmation_firewall_pending")
    if days < REQUIRED_TRADING_DAYS:
        blockers.append("days_in_tier_insufficient")
    if sortino.value is None or sortino.value <= SORTINO_THRESHOLD:
        blockers.append("sortino_below_threshold")

    if kill_switch_active or confirmation_firewall_pending:
        status = "blocked"
    elif days < REQUIRED_TRADING_DAYS:
        status = "soaking"
    elif sortino.value is None:
        status = "blocked"
    elif sortino.value <= SORTINO_THRESHOLD:
        status = "violated"
    else:
        status = "satisfied"

    return RampGateStatus(
        current_tier=tier,
        target_tier=target,
        gate_status=status,
        days_in_tier=days,
        sortino_14d=sortino.value,
        blockers=blockers,
        sortino_reason=sortino.reason,
        generated_at=generated.isoformat(),
    )


def forecast_rung_completion(
    start: datetime,
    *,
    required_days: int = REQUIRED_TRADING_DAYS,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Forecast the first date where the soak-day requirement can be met."""

    anchor = (now or _now_utc()).astimezone(UTC).replace(microsecond=0)
    elapsed = trading_days_between(start, anchor)
    remaining = max(0, required_days - int(elapsed))
    cursor = anchor.date()
    while remaining > 0:
        cursor += timedelta(days=1)
        if cursor.weekday() < 5:
            remaining -= 1
    return {
        "required_trading_days": required_days,
        "elapsed_trading_days": elapsed,
        "estimated_completion_date": cursor.isoformat(),
    }


def write_status_jsonl(
    ledger: LiveLedger,
    status: RampGateStatus,
    *,
    account_hash: str,
    root: str | Path | None = None,
) -> Path:
    """Append a ramp status row under the live portfolio data tree."""

    output_root = Path(root) if root is not None else ledger.root
    day = datetime.fromisoformat(status.generated_at).date().isoformat()
    path = output_root / account_hash / day / "ramp_status.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    import json

    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(status.to_dict(), sort_keys=True) + "\n")
    return path
