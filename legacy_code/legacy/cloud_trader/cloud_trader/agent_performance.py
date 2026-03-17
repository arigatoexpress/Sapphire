"""
Per-symbol performance tracking for agent self-improvement.

Uses GCS-backed persistent storage to survive deployments.
"""

import asyncio
import json
import logging
import os
from collections import defaultdict
from datetime import datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Import persistent storage
try:
    from .persistent_metrics import (
        AGENT_PERFORMANCE_FILE,
        get_metrics_store,
        load_agent_performance,
        save_agent_performance,
    )

    GCS_AVAILABLE = True
except ImportError:
    GCS_AVAILABLE = False
    logger.warning("⚠️ Persistent metrics not available, using local-only mode")


class PerformanceTracker:
    """
    Tracks win rate per symbol per agent.
    Enables agents to bias toward profitable symbols.

    Now with GCS-backed persistence for durability across deployments.
    """

    def __init__(self, use_gcs: bool = True):
        """
        Initialize the performance tracker.

        Args:
            use_gcs: If True, use GCS-backed persistent storage
        """
        self.use_gcs = use_gcs and GCS_AVAILABLE
        self.cache_path = "/tmp/sapphire_metrics/agent_performance.json"
        self.data: Dict[str, Dict[str, Dict[str, Any]]] = {}
        self._initialized = False
        self._pending_save = False

        # Ensure cache directory exists
        os.makedirs(os.path.dirname(self.cache_path), exist_ok=True)

        # Load data synchronously for immediate availability
        self._load_sync()

    def _load_sync(self):
        """Load data synchronously from local cache."""
        if os.path.exists(self.cache_path):
            try:
                with open(self.cache_path, "r") as f:
                    loaded = json.load(f)
                    # Filter out metadata key
                    self.data = {k: v for k, v in loaded.items() if not k.startswith("_")}
                logger.info(f"📊 Loaded performance data: {len(self.data)} agents")
            except Exception as e:
                logger.warning(f"⚠️ Failed to load performance cache: {e}")
                self.data = {}
        else:
            self.data = {}

    async def initialize(self):
        """
        Async initialization - loads from GCS on startup.
        Call this after service starts to sync from cloud.
        """
        if self._initialized:
            return

        if self.use_gcs:
            try:
                loaded = await load_agent_performance()
                if loaded:
                    # Merge with any local data (prefer GCS for conflicts)
                    for agent_id, symbols in loaded.items():
                        if not agent_id.startswith("_"):
                            if agent_id not in self.data:
                                self.data[agent_id] = symbols
                            else:
                                # Merge symbol data, prefer newer
                                for symbol, stats in symbols.items():
                                    if symbol not in self.data[agent_id]:
                                        self.data[agent_id][symbol] = stats
                                    else:
                                        # Keep whichever has more trades
                                        local_trades = self.data[agent_id][symbol].get(
                                            "wins", 0
                                        ) + self.data[agent_id][symbol].get("losses", 0)
                                        gcs_trades = stats.get("wins", 0) + stats.get("losses", 0)
                                        if gcs_trades > local_trades:
                                            self.data[agent_id][symbol] = stats

                    logger.info(f"☁️ Synced performance data from GCS: {len(self.data)} agents")
            except Exception as e:
                logger.warning(f"⚠️ GCS sync failed: {e}, using local data")

        self._initialized = True

    def _save(self):
        """Save performance data to local cache and queue GCS sync."""
        try:
            # Save to local cache immediately
            with open(self.cache_path, "w") as f:
                json.dump(self.data, f, indent=2, default=str)

            # Schedule async GCS save
            if self.use_gcs:
                self._pending_save = True
                try:
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        asyncio.create_task(self._save_to_gcs())
                except RuntimeError:
                    # No event loop, skip async save
                    pass

        except Exception as e:
            logger.error(f"❌ Failed to save performance data: {e}")

    async def _save_to_gcs(self):
        """Async save to GCS."""
        if not self._pending_save:
            return

        try:
            await save_agent_performance(self.data)
            self._pending_save = False
        except Exception as e:
            logger.error(f"❌ GCS save failed: {e}")

    def record_trade(self, agent_id: str, symbol: str, pnl: float):
        """
        Record a completed trade for an agent on a symbol.

        Args:
            agent_id: The agent's ID
            symbol: Trading pair (e.g., "BTCUSDT")
            pnl: Profit/loss in USD
        """
        # Initialize nested structure if needed
        if agent_id not in self.data:
            self.data[agent_id] = {}
        if symbol not in self.data[agent_id]:
            self.data[agent_id][symbol] = {
                "wins": 0,
                "losses": 0,
                "total_pnl": 0.0,
                "trade_count": 0,
                "last_trade": None,
                "created_at": datetime.now().isoformat(),
            }

        # Update stats
        stats = self.data[agent_id][symbol]
        if pnl > 0:
            stats["wins"] += 1
        else:
            stats["losses"] += 1
        stats["total_pnl"] += pnl
        stats["trade_count"] = stats["wins"] + stats["losses"]
        stats["last_trade"] = datetime.now().isoformat()

        self._save()

        # Log significant trades
        win_rate = self.get_symbol_win_rate(agent_id, symbol)
        logger.info(
            f"📈 Trade recorded: {agent_id} | {symbol} | "
            f"PnL: ${pnl:+.2f} | Win Rate: {win_rate:.0%}"
        )

    def get_symbol_win_rate(self, agent_id: str, symbol: str) -> float:
        """
        Get win rate for a specific agent-symbol pair.

        Returns:
            Win rate (0.0 to 1.0), or 0.5 if no trades recorded.
        """
        if agent_id not in self.data or symbol not in self.data[agent_id]:
            return 0.5  # Default neutral

        stats = self.data[agent_id][symbol]
        total = stats["wins"] + stats["losses"]
        if total == 0:
            return 0.5
        return stats["wins"] / total

    def get_symbol_stats(self, agent_id: str, symbol: str) -> Optional[Dict]:
        """Get full stats for a symbol."""
        if agent_id not in self.data or symbol not in self.data[agent_id]:
            return None
        return self.data[agent_id][symbol]

    def get_preferred_symbols(
        self,
        agent_id: str,
        all_symbols: List[str],
        min_trades: int = 5,
        min_win_rate: float = 0.6,
    ) -> List[str]:
        """
        Get symbols that perform well for this agent.

        Args:
            agent_id: The agent's ID
            all_symbols: List of all available symbols
            min_trades: Minimum trades to consider a symbol
            min_win_rate: Minimum win rate to be "preferred"

        Returns:
            List of symbols sorted by win rate (best first),
            followed by untested symbols.
        """
        preferred = []
        tested = []
        untested = []

        for symbol in all_symbols:
            stats = self.get_symbol_stats(agent_id, symbol)
            if stats is None:
                untested.append(symbol)
                continue

            total = stats["wins"] + stats["losses"]
            if total < min_trades:
                untested.append(symbol)
                continue

            win_rate = stats["wins"] / total
            if win_rate >= min_win_rate:
                preferred.append((symbol, win_rate, stats["total_pnl"]))
            else:
                tested.append((symbol, win_rate))

        # Sort preferred by win rate (descending), then by PnL
        preferred.sort(key=lambda x: (x[1], x[2]), reverse=True)

        # Return: preferred symbols first, then some untested for exploration
        result = [s[0] for s in preferred]

        # Add some untested symbols for exploration (20% of selection)
        import random

        exploration_count = max(4, len(untested) // 5)
        result.extend(random.sample(untested, min(exploration_count, len(untested))))

        return result

    def get_agent_summary(self, agent_id: str) -> Dict[str, Any]:
        """Get summary stats for an agent across all symbols."""
        if agent_id not in self.data:
            return {"total_trades": 0, "win_rate": 0.0, "total_pnl": 0.0}

        total_wins = 0
        total_losses = 0
        total_pnl = 0.0
        symbols_traded = 0

        for symbol, stats in self.data[agent_id].items():
            total_wins += stats["wins"]
            total_losses += stats["losses"]
            total_pnl += stats["total_pnl"]
            symbols_traded += 1

        total_trades = total_wins + total_losses
        win_rate = total_wins / total_trades if total_trades > 0 else 0.0

        return {
            "total_trades": total_trades,
            "wins": total_wins,
            "losses": total_losses,
            "win_rate": round(win_rate, 3),
            "total_pnl": round(total_pnl, 2),
            "symbols_traded": symbols_traded,
        }

    def get_all_stats(self) -> Dict[str, Any]:
        """Get comprehensive stats for all agents."""
        result = {
            "agents": {},
            "totals": {
                "total_trades": 0,
                "total_wins": 0,
                "total_losses": 0,
                "total_pnl": 0.0,
                "overall_win_rate": 0.0,
            },
        }

        for agent_id in self.data:
            if agent_id.startswith("_"):
                continue
            summary = self.get_agent_summary(agent_id)
            result["agents"][agent_id] = summary
            result["totals"]["total_trades"] += summary["total_trades"]
            result["totals"]["total_wins"] += summary["wins"]
            result["totals"]["total_losses"] += summary["losses"]
            result["totals"]["total_pnl"] += summary["total_pnl"]

        if result["totals"]["total_trades"] > 0:
            result["totals"]["overall_win_rate"] = (
                result["totals"]["total_wins"] / result["totals"]["total_trades"]
            )

        return result


# Global instance
_tracker: Optional[PerformanceTracker] = None


def get_performance_tracker() -> PerformanceTracker:
    """Get or create the global performance tracker."""
    global _tracker
    if _tracker is None:
        _tracker = PerformanceTracker()
    return _tracker


async def initialize_performance_tracker():
    """Initialize the performance tracker with GCS sync."""
    tracker = get_performance_tracker()
    await tracker.initialize()
    return tracker
