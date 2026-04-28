"""Convert public counter-party position changes into Sapphire signals."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any

from .tracker import PositionChange


@dataclass(frozen=True)
class CounterpartySignal:
    asset: str
    side: str
    magnitude: float
    traders_corroborating: int
    smart_money_consensus: float
    notional_delta_usd: float
    generated_at: str
    source: str = "hyperliquid-counterparty-intel"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _coerce_change(raw: PositionChange | dict[str, Any]) -> PositionChange:
    if isinstance(raw, PositionChange):
        return raw
    return PositionChange(
        trader=str(raw.get("trader") or ""),
        asset=str(raw.get("asset") or "").upper(),
        old_side=raw.get("old_side"),
        new_side=raw.get("new_side"),
        old_size_usd=float(raw.get("old_size_usd") or 0.0),
        new_size_usd=float(raw.get("new_size_usd") or 0.0),
        change_pct=float(raw.get("change_pct") or 0.0),
        side=str(raw.get("side") or raw.get("new_side") or "unknown"),
        detected_at=str(raw.get("detected_at") or ""),
    )


def generate_signals(
    changes: list[PositionChange | dict[str, Any]],
    *,
    min_traders: int = 1,
    generated_at: datetime | None = None,
) -> list[CounterpartySignal]:
    """Aggregate material position changes by asset and side."""
    groups: dict[tuple[str, str], list[PositionChange]] = defaultdict(list)
    for raw in changes:
        change = _coerce_change(raw)
        if not change.asset or change.side not in {"long", "short", "flat"}:
            continue
        groups[(change.asset.upper(), change.side)].append(change)

    stamp = (generated_at or datetime.now(UTC)).astimezone(UTC).replace(microsecond=0).isoformat()
    signals: list[CounterpartySignal] = []
    for (asset, side), grouped in sorted(groups.items()):
        if len(grouped) < min_traders:
            continue
        old_total = sum(c.old_size_usd for c in grouped)
        new_total = sum(c.new_size_usd for c in grouped)
        delta = new_total - old_total
        if side == "short":
            delta = -abs(delta)
        elif side == "long":
            delta = abs(delta)
        consensus = max(-1.0, min(1.0, delta / max(abs(new_total), abs(old_total), 1.0)))
        magnitude = min(1.0, sum(c.change_pct for c in grouped) / (100.0 * len(grouped)))
        signals.append(
            CounterpartySignal(
                asset=asset,
                side=side,
                magnitude=round(magnitude, 6),
                traders_corroborating=len({c.trader for c in grouped}),
                smart_money_consensus=round(consensus, 6),
                notional_delta_usd=round(delta, 2),
                generated_at=stamp,
            )
        )
    return signals
