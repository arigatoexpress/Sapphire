import asyncio
import os
import time
from typing import Any, Dict

from loguru import logger
from src.feeds.market_data import MarketDataAggregator


class AlphaStrategyEngine:
    STAGE_ORDER = ("paper", "staged_live", "full_live")

    def __init__(self, market_data: MarketDataAggregator):
        self.market_data = market_data
        self.running = False
        self.min_spread_pct = 0.001  # 0.1%
        self.last_execution_time = 0
        self.internal_arb_execution_enabled = (
            os.getenv("INTERNAL_ARB_EXECUTION_ENABLED", "false").strip().lower()
            in {"1", "true", "yes", "on"}
        )
        self.internal_arb_quantity = max(
            0.0,
            float(os.getenv("INTERNAL_ARB_EXECUTION_QUANTITY", "0.02")),
        )
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
        self._last_mode_log_at = 0.0

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

    def set_internal_execution_enabled(self, enabled: bool) -> Dict[str, Any]:
        self.internal_arb_execution_enabled = bool(enabled)
        return self.execution_state()

    def _stage_multiplier(self) -> float:
        if self.dex_execution_stage == "full_live":
            return self.full_live_multiplier
        if self.dex_execution_stage == "staged_live":
            return self.staged_live_multiplier
        return 0.0

    def execution_state(self) -> Dict[str, Any]:
        multiplier = self._stage_multiplier()
        live_dispatch = bool(self.internal_arb_execution_enabled and multiplier > 0)
        effective_quantity = float(self.internal_arb_quantity * multiplier)
        return {
            "dex_execution_stage": self.dex_execution_stage,
            "internal_arb_execution_enabled": bool(self.internal_arb_execution_enabled),
            "stage_multiplier": float(multiplier),
            "effective_live_dispatch": live_dispatch,
            "effective_quantity": float(round(effective_quantity, 8)),
            "base_quantity": float(self.internal_arb_quantity),
        }

    async def start(self):
        self.running = True
        asyncio.create_task(self._arb_loop())
        state = self.execution_state()
        logger.info(
            (
                "🧠 Alpha Strategy Engine Started | stage={} internal_arb_execution_enabled={} "
                "stage_multiplier={} effective_live_dispatch={} base_qty={} effective_qty={}"
            ),
            state["dex_execution_stage"],
            state["internal_arb_execution_enabled"],
            state["stage_multiplier"],
            state["effective_live_dispatch"],
            state["base_quantity"],
            state["effective_quantity"],
        )

    async def stop(self):
        self.running = False

    async def _arb_loop(self):
        """Core HFT Loop."""
        while self.running:
            try:
                aster_price = self.market_data.get_price("ASTER", "SOL")
                lighter_price = self.market_data.get_price("LIGHTER", "SOL")

                if aster_price > 0 and lighter_price > 0:
                    spread = abs(aster_price - lighter_price)
                    spread_pct = spread / min(aster_price, lighter_price)

                    if spread_pct > self.min_spread_pct:
                        now = time.time()
                        if now - self.last_execution_time > 5.0:  # 5s cooldown for now (debug mode)
                            logger.info(
                                f"⚡ ARB OPPORTUNITY: Aster={aster_price} Lighter={lighter_price} Spread={spread_pct:.4f}"
                            )

                            state = self.execution_state()
                            if state["effective_live_dispatch"] and state["effective_quantity"] > 0:
                                from src.execution.dispatcher import dispatcher

                                cmd = {
                                    "type": "ARB_EXECUTE",
                                    "side": "BUY" if aster_price < lighter_price else "SELL",
                                    "symbol": "SOL",
                                    "quantity": state["effective_quantity"],
                                    "spread": spread_pct,
                                    "source": "alpha_internal_arb",
                                    "execution_stage": state["dex_execution_stage"],
                                }
                                await dispatcher.send_command("ASTER", cmd)
                            else:
                                now = time.time()
                                if now - self._last_mode_log_at > 60:
                                    logger.info(
                                        (
                                            "Internal ARB in observe mode; opportunity logged only "
                                            "(stage={} internal_enabled={})"
                                        ),
                                        state["dex_execution_stage"],
                                        state["internal_arb_execution_enabled"],
                                    )
                                    self._last_mode_log_at = now
                            self.last_execution_time = now

                # Slower pace for Cloud Run stability (500ms)
                await asyncio.sleep(0.5)
            except Exception as e:
                logger.error(f"Strategy Loop Error: {e}")
                await asyncio.sleep(1)
