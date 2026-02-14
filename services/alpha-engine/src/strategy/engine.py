import asyncio
import os
import re
import time
from typing import Any, Dict, List, Set

from loguru import logger
from shared.position_sizing import SizingConfig, apply_stage_multiplier
from src.feeds.market_data import MarketDataAggregator


# ---------------------------------------------------------------------------
# Venue Profiles — each venue is a specialist, not an arb counter-party.
# ---------------------------------------------------------------------------

VENUE_PROFILES: Dict[str, Dict[str, Any]] = {
    "ASTER": {
        "name": "Aster",
        "role": "High-leverage ultra-high-frequency trading",
        "description": (
            "Aster specialises in high-leverage perpetual futures with tight spreads "
            "and rapid execution. Use Aster when market conditions favour aggressive, "
            "short-duration trades with defined risk."
        ),
        "strengths": ["high leverage", "fast execution", "tight spreads", "futures"],
        "constraints": ["region restrictions possible", "requires USDT-quoted symbols"],
    },
    "LIGHTER": {
        "name": "Lighter",
        "role": "Secure private perpetuals trading",
        "description": (
            "Lighter provides secure, privacy-preserving perpetual trading on zkLighter. "
            "Use Lighter for steady, medium-frequency trades where privacy and security "
            "are prioritised over raw speed."
        ),
        "strengths": ["privacy", "security", "zk-rollup settlement", "base-symbol perps"],
        "constraints": ["lower leverage ceiling", "fewer trading pairs"],
    },
}

# ---------------------------------------------------------------------------
# Preferred Symbols — slight bias toward these when scanning for opportunities.
# Agents may still trade any symbol at their discretion.
# ---------------------------------------------------------------------------

_DEFAULT_PREFERRED_SYMBOLS = "BTC,ETH,SOL,BCH,ZEC,XMR,PENGU,MON,LIT,ASTER"


def _parse_preferred_symbols(raw: str) -> List[str]:
    """Parse a comma/semicolon/space separated symbol list into unique uppercase tokens."""
    tokens = re.split(r"[,;|\s]+", str(raw or "").strip())
    seen: Set[str] = set()
    result: List[str] = []
    for token in tokens:
        sym = token.strip().upper()
        if sym and sym not in seen:
            seen.add(sym)
            result.append(sym)
    return result


PREFERRED_SYMBOLS: List[str] = _parse_preferred_symbols(
    os.getenv("SAPPHIRE_PREFERRED_SYMBOLS", _DEFAULT_PREFERRED_SYMBOLS)
)


class AlphaStrategyEngine:
    """
    Strategy engine for Sapphire Alpha Hub.

    Each venue operates as an independent specialist — there is no cross-venue
    arbitrage.  The engine tracks execution stage, quantity guards, and exposes
    venue profiles / preferred symbols for downstream autonomy decisions.
    """

    STAGE_ORDER = ("paper", "staged_live", "full_live")

    def __init__(self, market_data: MarketDataAggregator):
        self.market_data = market_data
        self.running = False

        # --- Unified position sizing config (canonical source of truth) -------
        self.sizing_config = SizingConfig()

        # --- Execution stage --------------------------------------------------
        self.staged_live_multiplier = self._bounded_multiplier(
            os.getenv("SAPPHIRE_STAGED_LIVE_SIZE_MULTIPLIER", "0.25"),
            fallback=0.25,
        )
        self.full_live_multiplier = self._bounded_multiplier(
            os.getenv("SAPPHIRE_FULL_LIVE_SIZE_MULTIPLIER", "1.0"),
            fallback=1.0,
        )
        self.dex_execution_stage = self._normalize_stage(
            os.getenv("SAPPHIRE_DEX_EXECUTION_STAGE", "paper")
        )

        # --- Quantity guards (kept for TradingView signal dispatch) ------------
        self.min_notional = max(
            0.0,
            float(os.getenv("SAPPHIRE_MIN_NOTIONAL", os.getenv("SAPPHIRE_INTERNAL_ARB_MIN_NOTIONAL", "5.0"))),
        )
        self.notional_buffer_pct = max(
            0.0,
            float(os.getenv("SAPPHIRE_NOTIONAL_BUFFER_PCT", os.getenv("SAPPHIRE_INTERNAL_ARB_NOTIONAL_BUFFER_PCT", "0.05"))),
        )
        self.max_quantity = max(
            0.0,
            float(os.getenv("SAPPHIRE_MAX_QUANTITY", os.getenv("SAPPHIRE_INTERNAL_ARB_MAX_QUANTITY", "0.25"))),
        )
        self.default_quantity = max(
            0.0,
            float(os.getenv("SAPPHIRE_DEFAULT_QUANTITY", os.getenv("INTERNAL_ARB_EXECUTION_QUANTITY", "0.02"))),
        )

        # --- Venue profiles & preferred symbols (immutable after init) --------
        self.venue_profiles: Dict[str, Dict[str, Any]] = dict(VENUE_PROFILES)
        self.preferred_symbols: List[str] = list(PREFERRED_SYMBOLS)

        # --- Health monitoring loop -------------------------------------------
        self._health_log_interval_seconds = 300  # log venue health every 5 min
        self._last_health_log_at = 0.0

    # ------------------------------------------------------------------
    # Stage helpers
    # ------------------------------------------------------------------

    @classmethod
    def _normalize_stage(cls, raw: Any) -> str:
        value = str(raw or "").strip().lower().replace("-", "_")
        aliases = {
            "observe": "paper",
            "dry": "paper",
            "dry_run": "paper",
            "paper": "paper",
            "staged": "staged_live",
            "stagedlive": "staged_live",
            "staged_live": "staged_live",
            "stage": "staged_live",
            "live": "full_live",
            "full": "full_live",
            "full_live": "full_live",
            "production": "full_live",
        }
        normalized = aliases.get(value, value)
        if normalized not in cls.STAGE_ORDER:
            return "paper"
        return normalized

    @staticmethod
    def _bounded_multiplier(raw: Any, fallback: float) -> float:
        try:
            value = float(raw)
        except (TypeError, ValueError):
            return fallback
        if not value == value:  # NaN guard
            return fallback
        return max(0.0, min(1.0, value))

    def set_execution_stage(self, stage: str) -> Dict[str, Any]:
        previous = self.dex_execution_stage
        normalized = self._normalize_stage(stage)
        self.dex_execution_stage = normalized
        state = self.execution_state()
        state.update({"previous_stage": previous, "changed": previous != normalized})
        return state

    def _stage_multiplier(self) -> float:
        """Stage multiplier delegated to unified position_sizing module.

        Uses env-var overrides (SAPPHIRE_STAGED_LIVE_SIZE_MULTIPLIER /
        SAPPHIRE_FULL_LIVE_SIZE_MULTIPLIER) when they differ from the
        canonical defaults, otherwise falls through to the shared config.
        """
        if self.dex_execution_stage == "full_live":
            return self.full_live_multiplier
        if self.dex_execution_stage == "staged_live":
            return self.staged_live_multiplier
        return 0.0

    def apply_stage_to_quantity(self, base_qty: float) -> float:
        """Apply the current execution stage multiplier to a quantity.

        Uses the unified position_sizing module with the engine's
        stage-specific override multiplier.
        """
        mult = self._stage_multiplier()
        return apply_stage_multiplier(base_qty, self.dex_execution_stage, multiplier_override=mult)

    # ------------------------------------------------------------------
    # Execution state
    # ------------------------------------------------------------------

    def execution_state(self) -> Dict[str, Any]:
        multiplier = self._stage_multiplier()
        effective_quantity = self.apply_stage_to_quantity(self.default_quantity)
        return {
            "dex_execution_stage": self.dex_execution_stage,
            "stage_multiplier": float(multiplier),
            "effective_quantity": float(round(effective_quantity, 8)),
            "base_quantity": float(self.default_quantity),
            "min_notional": float(self.min_notional),
            "min_notional_buffer_pct": float(self.notional_buffer_pct),
            "max_quantity": float(self.max_quantity),
            "sizing_config": {
                "kelly_cap": float(self.sizing_config.kelly_cap),
                "max_position_pct": float(self.sizing_config.max_position_pct),
                "max_total_exposure_pct": float(self.sizing_config.max_total_exposure_pct),
                "min_position_usd": float(self.sizing_config.min_position_usd),
            },
            "preferred_symbols": list(self.preferred_symbols),
            "venue_profiles": {
                venue: {
                    "name": profile["name"],
                    "role": profile["role"],
                }
                for venue, profile in self.venue_profiles.items()
            },
        }

    # ------------------------------------------------------------------
    # Quantity resolution (used by TradingView signal dispatch)
    # ------------------------------------------------------------------

    def _resolve_dispatch_quantity(self, reference_price: float, baseline_quantity: float) -> Dict[str, Any]:
        quantity = max(0.0, float(baseline_quantity))
        if quantity <= 0:
            return {"quantity": 0.0, "adjusted": False, "blocked": False, "reason": "non_positive_quantity"}
        if reference_price <= 0 or self.min_notional <= 0:
            return {"quantity": quantity, "adjusted": False, "blocked": False, "reason": "no_notional_check"}

        target_notional = self.min_notional * (1.0 + self.notional_buffer_pct)
        required_quantity = target_notional / reference_price
        if required_quantity <= quantity:
            return {"quantity": quantity, "adjusted": False, "blocked": False, "reason": "baseline_satisfies_notional"}

        if self.max_quantity > 0 and required_quantity > self.max_quantity:
            return {
                "quantity": 0.0,
                "adjusted": False,
                "blocked": True,
                "reason": "required_quantity_exceeds_cap",
                "required_quantity": float(round(required_quantity, 8)),
                "cap_quantity": float(self.max_quantity),
            }
        return {
            "quantity": float(round(required_quantity, 8)),
            "adjusted": True,
            "blocked": False,
            "reason": "raised_to_min_notional",
            "required_quantity": float(round(required_quantity, 8)),
        }

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self):
        self.running = True
        asyncio.create_task(self._venue_health_loop())
        state = self.execution_state()
        logger.info(
            "🧠 Alpha Strategy Engine Started | stage={} multiplier={} preferred_symbols={}",
            state["dex_execution_stage"],
            state["stage_multiplier"],
            ",".join(self.preferred_symbols[:5]) + ("..." if len(self.preferred_symbols) > 5 else ""),
        )
        for venue, profile in self.venue_profiles.items():
            logger.info("  └─ {} → {}", venue, profile["role"])

    async def stop(self):
        self.running = False

    # ------------------------------------------------------------------
    # Venue health monitoring (replaces the old arb loop)
    # ------------------------------------------------------------------

    async def _venue_health_loop(self):
        """Periodic venue health logger — no cross-venue trading."""
        while self.running:
            try:
                now = time.time()
                if now - self._last_health_log_at >= self._health_log_interval_seconds:
                    for venue in self.venue_profiles:
                        symbol = self.preferred_symbols[0] if self.preferred_symbols else "SOL"
                        price = self.market_data.get_price(venue, symbol)
                        status = "online" if price > 0 else "no_price"
                        logger.info(
                            "📊 Venue health: {} | {} = {} | status={}",
                            venue,
                            symbol,
                            f"${price:,.2f}" if price > 0 else "n/a",
                            status,
                        )
                    self._last_health_log_at = now
            except Exception as e:
                logger.error(f"Venue health loop error: {e}")
            await asyncio.sleep(30)
