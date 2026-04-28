"""Pure counter-party tracking for public Hyperliquid trader data."""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any

MAX_TRADERS_TRACKED = 100
MIN_TRADER_30D_PNL_USD = 50_000.0
POSITION_CHANGE_SIGNAL_THRESHOLD_PCT = 15.0


@dataclass(frozen=True)
class TraderStats:
    """Public leaderboard statistics for one trader."""

    address: str
    display_name: str | None
    realized_pnl_30d_usd: float
    realized_pnl_90d_usd: float
    sharpe_30d: float
    win_rate_30d: float | None = None
    rank: int | None = None

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> TraderStats:
        return cls(
            address=str(raw.get("address") or raw.get("user") or raw.get("account") or "").lower(),
            display_name=(str(raw.get("display_name") or raw.get("name")) if raw.get("display_name") or raw.get("name") else None),
            realized_pnl_30d_usd=_float(raw.get("realized_pnl_30d_usd", raw.get("pnl30d", raw.get("pnl")))),
            realized_pnl_90d_usd=_float(raw.get("realized_pnl_90d_usd", raw.get("pnl90d"))),
            sharpe_30d=_float(raw.get("sharpe_30d", raw.get("sharpe"))),
            win_rate_30d=_maybe_float(raw.get("win_rate_30d", raw.get("winRate"))),
            rank=int(raw["rank"]) if raw.get("rank") is not None else None,
        )

    def quality_score(self) -> float:
        pnl_score = max(0.0, self.realized_pnl_30d_usd) + max(0.0, self.realized_pnl_90d_usd) * 0.35
        sharpe_multiplier = 1.0 + max(-0.5, min(self.sharpe_30d, 5.0)) / 5.0
        win_bonus = 1.0 + ((self.win_rate_30d or 0.0) - 0.5) * 0.25
        return pnl_score * sharpe_multiplier * max(0.75, win_bonus)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class TraderPosition:
    """Open position for a public trader."""

    trader: str
    asset: str
    side: str
    size_usd: float
    entry_price: float | None = None
    leverage: float | None = None
    updated_at: str | None = None

    @classmethod
    def from_dict(cls, trader: str, raw: dict[str, Any]) -> TraderPosition:
        asset = str(raw.get("asset") or raw.get("coin") or raw.get("symbol") or "").upper()
        raw_side = str(raw.get("side") or raw.get("direction") or "").lower()
        signed = _maybe_float(raw.get("signed_size_usd", raw.get("signedNotional")))
        size = _float(raw.get("size_usd", raw.get("notional", raw.get("positionValue"))))
        if signed is not None:
            side = "long" if signed >= 0 else "short"
            size = abs(signed)
        elif raw_side in {"short", "sell"}:
            side = "short"
        else:
            side = "long"
        return cls(
            trader=trader.lower(),
            asset=asset,
            side=side,
            size_usd=max(0.0, size),
            entry_price=_maybe_float(raw.get("entry_price", raw.get("entryPx"))),
            leverage=_maybe_float(raw.get("leverage")),
            updated_at=raw.get("updated_at"),
        )

    @property
    def signed_size_usd(self) -> float:
        return self.size_usd if self.side == "long" else -self.size_usd

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class PositionChange:
    """Material shift in a watchlisted trader's position."""

    trader: str
    asset: str
    old_side: str | None
    new_side: str | None
    old_size_usd: float
    new_size_usd: float
    change_pct: float
    side: str
    detected_at: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _float(value: Any) -> float:
    try:
        if value is None or (isinstance(value, float) and math.isnan(value)):
            return 0.0
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _maybe_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def rank_traders(
    rows: list[TraderStats | dict[str, Any]],
    *,
    top_n: int = 50,
    min_30d_pnl_usd: float = MIN_TRADER_30D_PNL_USD,
) -> list[TraderStats]:
    """Filter and rank public traders by realized PnL plus Sharpe."""
    capped = max(1, min(int(top_n), MAX_TRADERS_TRACKED))
    traders = [row if isinstance(row, TraderStats) else TraderStats.from_dict(row) for row in rows]
    eligible = [
        trader
        for trader in traders
        if trader.address and trader.realized_pnl_30d_usd >= min_30d_pnl_usd
    ]
    ranked = sorted(eligible, key=lambda t: (t.quality_score(), t.realized_pnl_30d_usd), reverse=True)
    return ranked[:capped]


def _position_map(positions: list[TraderPosition]) -> dict[tuple[str, str], TraderPosition]:
    return {(p.trader.lower(), p.asset.upper()): p for p in positions if p.asset}


def _change_pct(old: TraderPosition | None, new: TraderPosition | None) -> float:
    old_signed = old.signed_size_usd if old else 0.0
    new_signed = new.signed_size_usd if new else 0.0
    denom = max(abs(old_signed), 1.0)
    return abs(new_signed - old_signed) / denom * 100.0


def track_position_changes(
    previous: list[TraderPosition | dict[str, Any]],
    current: list[TraderPosition | dict[str, Any]],
    *,
    threshold_pct: float = POSITION_CHANGE_SIGNAL_THRESHOLD_PCT,
    detected_at: datetime | None = None,
) -> list[PositionChange]:
    """Return material position shifts without mutating upstream data."""
    prev = [p if isinstance(p, TraderPosition) else TraderPosition.from_dict(str(p.get("trader") or p.get("address") or ""), p) for p in previous]
    curr = [p if isinstance(p, TraderPosition) else TraderPosition.from_dict(str(p.get("trader") or p.get("address") or ""), p) for p in current]
    prev_map = _position_map(prev)
    curr_map = _position_map(curr)
    keys = sorted(set(prev_map) | set(curr_map))
    stamp = (detected_at or datetime.now(UTC)).astimezone(UTC).replace(microsecond=0).isoformat()
    changes: list[PositionChange] = []
    for key in keys:
        old = prev_map.get(key)
        new = curr_map.get(key)
        pct = _change_pct(old, new)
        if pct < threshold_pct:
            continue
        side = new.side if new is not None else ("flat" if old is not None else "unknown")
        changes.append(
            PositionChange(
                trader=key[0],
                asset=key[1],
                old_side=old.side if old else None,
                new_side=new.side if new else None,
                old_size_usd=old.size_usd if old else 0.0,
                new_size_usd=new.size_usd if new else 0.0,
                change_pct=round(pct, 6),
                side=side,
                detected_at=stamp,
            )
        )
    return changes
