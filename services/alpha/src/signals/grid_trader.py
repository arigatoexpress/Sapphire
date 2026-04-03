"""
Grid Trader — leveraged grid-style signal generation.

Generates BUY/SELL signals around an anchor price using a configurable grid.
Signals are emitted when price crosses grid levels; it does not place limit
orders directly (bots still execute market orders).

Safety:
- Disabled by default.
- Can be blocked when execution stage multiplier is 0 unless explicitly allowed.
"""

import asyncio
import os
import time
from dataclasses import dataclass
from typing import Any

from loguru import logger


def _env_flag(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int, minimum: int = 1, maximum: int = 1000) -> int:
    raw = os.getenv(name, str(default)).strip()
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(maximum, value))


def _env_float(name: str, default: float, minimum: float = 0.0, maximum: float = 1000.0) -> float:
    raw = os.getenv(name, str(default)).strip()
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return default
    if not value == value:
        return default
    return max(minimum, min(maximum, value))


def _parse_symbols(raw: str) -> list[str]:
    import re as _re
    tokens = _re.split(r"[,;|\s]+", str(raw or "").strip())
    seen = set()
    result: list[str] = []
    for token in tokens:
        sym = token.strip().upper()
        if sym and sym not in seen:
            seen.add(sym)
            result.append(sym)
    return result


def _parse_venues(raw: str) -> list[str]:
    tokens = _parse_symbols(raw)
    return [t for t in tokens if t]


@dataclass
class GridLevel:
    index: int
    buy_price: float
    sell_price: float
    last_buy_at: float = 0.0
    last_sell_at: float = 0.0
    buy_armed: bool = True
    sell_armed: bool = True


@dataclass
class GridState:
    anchor: float
    last_price: float
    levels: list[GridLevel]
    updated_at: float


class GridSignalPlanner:
    """Generate grid trading signals from live prices."""

    def __init__(
        self,
        market_data: Any,
        strategy: Any,
        *,
        enabled: bool = False,
        symbols: list[str] | None = None,
    ) -> None:
        self.market_data = market_data
        self.strategy = strategy
        self._enabled = enabled or _env_flag("SAPPHIRE_GRID_TRADER_ENABLED", default=False)
        self._interval = _env_int("SAPPHIRE_GRID_INTERVAL_SECONDS", 10, minimum=3, maximum=600)
        self._levels = _env_int("SAPPHIRE_GRID_LEVELS", 4, minimum=1, maximum=20)
        self._spacing_pct = _env_float("SAPPHIRE_GRID_SPACING_PCT", 0.35, minimum=0.01, maximum=20.0)
        self._rearm_pct = _env_float("SAPPHIRE_GRID_REARM_PCT", 0.15, minimum=0.01, maximum=10.0)
        self._recenter_pct = _env_float("SAPPHIRE_GRID_RECENTER_PCT", 2.5, minimum=0.5, maximum=25.0)
        self._max_signals_per_cycle = _env_int("SAPPHIRE_GRID_MAX_SIGNALS_PER_CYCLE", 4, minimum=1, maximum=50)
        self._level_cooldown = _env_int("SAPPHIRE_GRID_LEVEL_COOLDOWN_SECONDS", 60, minimum=5, maximum=3600)
        self._symbol_cooldown = _env_int("SAPPHIRE_GRID_SYMBOL_COOLDOWN_SECONDS", 10, minimum=1, maximum=600)
        self._min_price_age = _env_int("SAPPHIRE_GRID_MAX_PRICE_AGE_SECONDS", 120, minimum=10, maximum=1200)
        self._allow_paper = _env_flag("SAPPHIRE_GRID_ALLOW_PAPER", default=False)
        self._target_mode = str(os.getenv("SAPPHIRE_GRID_TARGET_MODE", "best")).strip().lower() or "best"
        self._target_venues = _parse_venues(os.getenv("SAPPHIRE_GRID_TARGET_VENUES", ""))
        self._base_quantity = _env_float("SAPPHIRE_GRID_BASE_QUANTITY", 0.0, minimum=0.0, maximum=1000.0)
        self._leverage = _env_float("SAPPHIRE_GRID_LEVERAGE", 5.0, minimum=1.0, maximum=125.0)
        self._mode = str(os.getenv("SAPPHIRE_GRID_MODE", "long_only")).strip().lower() or "long_only"
        self._running = False

        preferred = symbols or _parse_symbols(
            os.getenv("SAPPHIRE_GRID_SYMBOLS", os.getenv("SAPPHIRE_PREFERRED_SYMBOLS", ""))
        )
        self._symbols = preferred

        self._grid: dict[str, GridState] = {}
        self._last_symbol_signal: dict[str, float] = {}
        self._signals_emitted = 0
        self._cycles = 0

    @property
    def enabled(self) -> bool:
        return self._enabled

    def metrics(self) -> dict[str, Any]:
        return {
            "enabled": self._enabled,
            "interval_seconds": self._interval,
            "symbols": list(self._symbols),
            "levels": self._levels,
            "spacing_pct": self._spacing_pct,
            "rearm_pct": self._rearm_pct,
            "recenter_pct": self._recenter_pct,
            "signals_emitted": self._signals_emitted,
            "cycles": self._cycles,
            "target_mode": self._target_mode,
            "target_venues": list(self._target_venues),
            "base_quantity": self._base_quantity,
            "leverage": self._leverage,
            "mode": self._mode,
        }

    async def run_loop(self, signal_callback) -> None:
        if not self._enabled:
            logger.info("Grid trader disabled (SAPPHIRE_GRID_TRADER_ENABLED=false)")
            return

        self._running = True
        logger.info(
            "🧭 Grid trader starting — interval={}s symbols={} levels={} spacing={}pct",
            self._interval,
            ",".join(self._symbols[:6]),
            self._levels,
            self._spacing_pct,
        )

        while self._running:
            try:
                await asyncio.sleep(self._interval)
                signals = self._scan_cycle()
                for payload in signals:
                    try:
                        await signal_callback(payload)
                        self._signals_emitted += 1
                    except Exception as exc:
                        logger.warning("Grid trader callback error: {}", exc)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error("Grid trader cycle error: {}", exc)
                await asyncio.sleep(10)

        logger.info("Grid trader stopped")

    def stop(self) -> None:
        self._running = False

    def _scan_cycle(self) -> list[dict[str, Any]]:
        self._cycles += 1
        signals: list[dict[str, Any]] = []

        execution_state = self.strategy.execution_state()
        multiplier = float(execution_state.get("stage_multiplier", 0.0))
        stage = str(execution_state.get("dex_execution_stage", "paper"))
        if multiplier <= 0 and not self._allow_paper:
            logger.debug("Grid trader: stage={} multiplier=0, skipping", stage)
            return signals

        snapshot = self.market_data.get_multi_symbol_snapshot()
        now = time.time()

        for symbol in self._symbols:
            if len(signals) >= self._max_signals_per_cycle:
                break

            last_symbol = self._last_symbol_signal.get(symbol, 0.0)
            if now - last_symbol < self._symbol_cooldown:
                continue

            price_info = self._select_price(symbol, snapshot)
            if not price_info:
                continue

            venue, price, age = price_info
            if age is None or age > self._min_price_age or price <= 0:
                continue

            state = self._grid.get(symbol)
            if state is None or self._should_recenter(state.anchor, price):
                state = self._initialize_grid(price)
                self._grid[symbol] = state

            state.last_price = price
            state.updated_at = now

            # Check each grid level for trigger
            for level in state.levels:
                if len(signals) >= self._max_signals_per_cycle:
                    break

                # BUY trigger
                if level.buy_armed and price <= level.buy_price and (now - level.last_buy_at) >= self._level_cooldown:
                    payload = self._build_signal(
                        symbol=symbol,
                        action="BUY",
                        price=price,
                        anchor=state.anchor,
                        level=level.index,
                        venue=venue,
                        stage_multiplier=multiplier,
                    )
                    signals.append(payload)
                    level.last_buy_at = now
                    level.buy_armed = False
                    self._last_symbol_signal[symbol] = now
                    continue

                # SELL trigger
                if level.sell_armed and price >= level.sell_price and (now - level.last_sell_at) >= self._level_cooldown:
                    payload = self._build_signal(
                        symbol=symbol,
                        action="SELL",
                        price=price,
                        anchor=state.anchor,
                        level=level.index,
                        venue=venue,
                        stage_multiplier=multiplier,
                    )
                    signals.append(payload)
                    level.last_sell_at = now
                    level.sell_armed = False
                    self._last_symbol_signal[symbol] = now
                    continue

                # Rearm logic
                if not level.buy_armed and price >= level.buy_price * (1 + self._rearm_pct / 100.0):
                    level.buy_armed = True
                if not level.sell_armed and price <= level.sell_price * (1 - self._rearm_pct / 100.0):
                    level.sell_armed = True

        return signals

    def _select_price(
        self, symbol: str, snapshot: dict[str, dict[str, dict[str, Any]]]
    ) -> tuple[str, float, int | None] | None:
        # Prefer explicitly scoped venues if provided.
        venues = self._target_venues or ["ASTER", "LIGHTER"]
        best: tuple[str, float, int | None] | None = None
        for venue in venues:
            venue_data = snapshot.get(venue, {})
            data = venue_data.get(symbol, {})
            price = float(data.get("price") or 0.0)
            age = data.get("age_seconds")
            if price <= 0:
                continue
            if best is None:
                best = (venue, price, age)
                continue
            _, _, best_age = best
            # Prefer fresher data
            if best_age is None or (age is not None and age < best_age):
                best = (venue, price, age)
        return best

    def _initialize_grid(self, anchor: float) -> GridState:
        spacing = self._spacing_pct / 100.0
        levels: list[GridLevel] = []
        for idx in range(1, self._levels + 1):
            buy_price = anchor * (1 - spacing * idx)
            sell_price = anchor * (1 + spacing * idx)
            levels.append(GridLevel(index=idx, buy_price=buy_price, sell_price=sell_price))
        return GridState(anchor=anchor, last_price=anchor, levels=levels, updated_at=time.time())

    def _should_recenter(self, anchor: float, price: float) -> bool:
        if anchor <= 0:
            return True
        move_pct = abs(price - anchor) / anchor * 100.0
        return move_pct >= self._recenter_pct

    def _build_signal(
        self,
        *,
        symbol: str,
        action: str,
        price: float,
        anchor: float,
        level: int,
        venue: str,
        stage_multiplier: float,
    ) -> dict[str, Any]:
        base_quantity = self._base_quantity or float(self.strategy.default_quantity)
        # Quantity is a baseline size. The execution pipeline applies stage sizing once.
        quantity = float(base_quantity)

        target_platforms: list[str] = []
        if self._target_mode == "best":
            target_platforms = [venue.lower()]
        elif self._target_mode == "all":
            target_platforms = []

        reduce_only = bool(self._mode == "long_only" and str(action).upper() == "SELL")

        return {
            "source": "grid_trader",
            "strategy": "grid_trader",
            "action": action,
            "symbol": symbol,
            "price": float(price),
            "quantity": float(round(quantity, 8)),
            "target_platforms": target_platforms,
            "reduce_only": reduce_only,
            "grid": {
                "anchor": float(anchor),
                "level": int(level),
                "spacing_pct": float(self._spacing_pct),
                "recenter_pct": float(self._recenter_pct),
            },
            "leverage": float(self._leverage),
            "timestamp": int(time.time()),
        }
