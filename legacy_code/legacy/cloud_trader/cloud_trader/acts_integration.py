"""
ACTS Integration Layer

Connects UMEP (Market Encoding) and Episodic Memory with the trading decision flow.
This is the bridge that enables agents to perceive markets semantically and learn from experience.
"""

import asyncio
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from .memory import Episode, TradeOutcome, create_episode, get_episodic_memory, get_reflection_agent
from .strategy import MarketSnapshot
from .umep import (
    AssetState,
    MacroContext,
    MarketRegime,
    MarketStateTensor,
    RiskAppetite,
    get_asset_encoder,
    get_macro_encoder,
)

logger = logging.getLogger(__name__)


class ACTSIntegration:
    """
    Integration layer that connects all ACTS components:
    - UMEP for market perception
    - Episodic Memory for learning
    - Trading agents for decisions

    This enables the flow:
    1. Encode market state (UMEP)
    2. Recall similar past experiences (Memory)
    3. Make decision with context (Agents)
    4. Execute and record outcome (Memory)
    5. Reflect and learn (Memory)
    """

    def __init__(self):
        self._asset_encoder = get_asset_encoder()
        self._macro_encoder = get_macro_encoder()
        self._memory = get_episodic_memory()
        self._reflection_agent = get_reflection_agent()

        # Track active trades for outcome updates
        self._active_episodes: Dict[str, str] = {}  # trade_id -> episode_id

        # Stats
        self._encode_count = 0
        self._episode_count = 0

    async def encode_current_market(
        self,
        prices: Dict[str, float],
        changes_24h: Dict[str, float],
        changes_1h: Optional[Dict[str, float]] = None,
        funding_rates: Optional[Dict[str, float]] = None,
    ) -> MarketStateTensor:
        """
        Encode current market state into a MarketStateTensor.

        This is the perception step - converting raw market data
        into semantic representation.
        """
        mst = MarketStateTensor()

        # Encode macro context
        btc_24h = changes_24h.get("BTC", changes_24h.get("BTC-USDC", 0))
        eth_24h = changes_24h.get("ETH", changes_24h.get("ETH-USDC", 0))
        sol_24h = changes_24h.get("SOL", changes_24h.get("SOL-USDC", 0))

        # Filter altcoins
        altcoins = {
            k: v
            for k, v in changes_24h.items()
            if k not in ["BTC", "ETH", "SOL", "BTC-USDC", "ETH-USDC", "SOL-USDC"]
        }

        mst.macro = self._macro_encoder.encode(
            btc_change_24h=btc_24h,
            eth_change_24h=eth_24h,
            sol_change_24h=sol_24h,
            altcoin_changes=altcoins,
            funding_rates=funding_rates,
        )

        # Encode asset states
        for symbol, price in prices.items():
            price_1h = None
            if changes_1h and symbol in changes_1h:
                # Back-calculate price 1h ago
                pct = changes_1h[symbol]
                if pct != 0:
                    price_1h = price / (1 + pct / 100)

            price_24h = None
            if symbol in changes_24h:
                pct = changes_24h[symbol]
                if pct != 0:
                    price_24h = price / (1 + pct / 100)

            mst.assets[symbol] = self._asset_encoder.encode(
                symbol=symbol,
                current_price=price,
                price_1h_ago=price_1h,
                price_24h_ago=price_24h,
            )

        self._encode_count += 1

        logger.debug(f"📊 Encoded market state: {mst.macro.regime.value}")

        return mst

    async def get_context_for_decision(
        self,
        symbol: str,
        signal_type: str,
        current_mst: MarketStateTensor,
    ) -> Dict[str, Any]:
        """
        Get full context for a trading decision.

        Returns:
        - Current market state (compressed)
        - Similar past episodes with lessons
        - Aggregate insights
        """
        # Compress market state for prompt injection
        market_text = current_mst.to_text(max_assets=3)
        embedding_text = current_mst.to_embedding_text()

        # Recall similar past experiences
        similar_episodes = await self._memory.recall_similar(
            current_state_text=embedding_text,
            symbol=symbol,
            limit=3,
            prefer_profitable=True,
        )

        # Format lessons
        lessons = []
        for ep in similar_episodes:
            if ep.lesson:
                lessons.append(
                    {
                        "date": ep.timestamp.strftime("%Y-%m-%d"),
                        "signal": ep.signal_type,
                        "pnl": ep.outcome.pnl if ep.outcome else 0,
                        "lesson": ep.lesson,
                    }
                )

        # Aggregate insights
        if similar_episodes:
            profitable_count = sum(1 for ep in similar_episodes if ep.was_profitable())
            avg_pnl = sum(ep.outcome.pnl for ep in similar_episodes if ep.outcome) / len(
                similar_episodes
            )
        else:
            profitable_count = 0
            avg_pnl = 0

        context = {
            "market_state": market_text,
            "regime": current_mst.macro.regime.value,
            "risk_appetite": current_mst.macro.risk_appetite.value,
            "similar_trades": len(similar_episodes),
            "historical_win_rate": (
                profitable_count / len(similar_episodes) if similar_episodes else 0.5
            ),
            "historical_avg_pnl": avg_pnl,
            "lessons": lessons,
        }

        logger.info(
            f"📚 Context for {symbol}: {len(lessons)} lessons, {context['historical_win_rate']:.0%} historical win rate"
        )

        return context

    async def record_decision(
        self,
        symbol: str,
        signal_type: str,
        entry_price: float,
        quantity: float,
        market_state: MarketStateTensor,
        agent_id: str,
        agent_reasoning: str = "",
        confidence: float = 0.5,
        trade_id: Optional[str] = None,
        platform: str = "unknown",
    ) -> str:
        """
        Record a trading decision as an episode.

        Returns the episode ID.
        """
        episode = create_episode(
            symbol=symbol,
            signal_type=signal_type,
            entry_price=entry_price,
            market_state_text=market_state.to_text(),
            agent_id=agent_id,
            agent_reasoning=agent_reasoning,
            confidence=confidence,
            platform=platform,
        )
        episode.quantity = quantity
        episode.market_state_embedding_text = market_state.to_embedding_text()

        episode_id = await self._memory.store(episode)

        # Track for outcome update
        if trade_id:
            self._active_episodes[trade_id] = episode_id

        self._episode_count += 1

        logger.info(f"📝 Recorded decision: {symbol} {signal_type} -> Episode {episode_id}")

        return episode_id

    async def record_outcome(
        self,
        episode_id: Optional[str] = None,
        trade_id: Optional[str] = None,
        pnl: float = 0.0,
        pnl_percent: float = 0.0,
        max_drawdown: float = 0.0,
        max_profit: float = 0.0,
        hold_duration_seconds: float = 0.0,
        exit_reason: str = "unknown",
    ) -> bool:
        """
        Record the outcome of a trade.

        Can lookup by episode_id or trade_id.
        """
        # Resolve episode ID
        if not episode_id and trade_id:
            episode_id = self._active_episodes.get(trade_id)

        if not episode_id:
            logger.warning("Cannot record outcome: no episode ID")
            return False

        outcome = TradeOutcome(
            success=pnl > 0,
            pnl=pnl,
            pnl_percent=pnl_percent,
            max_drawdown=max_drawdown,
            max_profit=max_profit,
            hold_duration_seconds=hold_duration_seconds,
            exit_reason=exit_reason,
        )

        success = await self._memory.update_outcome(episode_id, outcome)

        if success:
            # Trigger reflection
            asyncio.create_task(self._reflect_on_episode(episode_id))

            # Clean up tracking
            if trade_id and trade_id in self._active_episodes:
                del self._active_episodes[trade_id]

        return success

    async def _reflect_on_episode(self, episode_id: str):
        """Trigger reflection on completed episode."""
        try:
            episode = self._memory.get_by_id(episode_id)
            if not episode or not episode.outcome:
                return

            reflection = await self._reflection_agent.reflect(episode)

            await self._memory.add_reflection(
                episode_id=episode_id,
                what_worked=reflection["what_worked"],
                what_failed=reflection["what_failed"],
                lesson=reflection["lesson"],
            )

            logger.info(f"💭 Reflected on {episode_id}: {reflection['lesson'][:50]}...")

        except Exception as e:
            logger.warning(f"Reflection failed for {episode_id}: {e}")

    def get_stats(self) -> Dict[str, Any]:
        """Get integration statistics."""
        memory_stats = self._memory.get_stats()

        return {
            "encode_count": self._encode_count,
            "episode_count": self._episode_count,
            "active_trades": len(self._active_episodes),
            **memory_stats,
        }


# Global instance
_integration: Optional[ACTSIntegration] = None


def get_acts_integration() -> ACTSIntegration:
    """Get global ACTSIntegration instance."""
    global _integration
    if _integration is None:
        _integration = ACTSIntegration()
    return _integration


# Convenience functions
async def encode_market(
    prices: Dict[str, float], changes_24h: Dict[str, float]
) -> MarketStateTensor:
    """Convenience: Encode current market state."""
    integration = get_acts_integration()
    return await integration.encode_current_market(prices, changes_24h)


async def get_decision_context(
    symbol: str, signal_type: str, mst: MarketStateTensor
) -> Dict[str, Any]:
    """Convenience: Get context for a decision."""
    integration = get_acts_integration()
    return await integration.get_context_for_decision(symbol, signal_type, mst)


async def record_trade_decision(
    symbol: str,
    signal_type: str,
    entry_price: float,
    quantity: float,
    mst: MarketStateTensor,
    agent_id: str,
    trade_id: str,
) -> str:
    """Convenience: Record a trading decision."""
    integration = get_acts_integration()
    return await integration.record_decision(
        symbol=symbol,
        signal_type=signal_type,
        entry_price=entry_price,
        quantity=quantity,
        market_state=mst,
        agent_id=agent_id,
        trade_id=trade_id,
    )


async def record_trade_outcome(trade_id: str, pnl: float, exit_reason: str = "unknown") -> bool:
    """Convenience: Record trade outcome."""
    integration = get_acts_integration()
    return await integration.record_outcome(
        trade_id=trade_id,
        pnl=pnl,
        exit_reason=exit_reason,
    )
