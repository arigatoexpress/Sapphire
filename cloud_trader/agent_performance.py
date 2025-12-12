"""Per-symbol performance tracking for agent self-improvement."""

import json
import os
from collections import defaultdict
from typing import Any, Dict, List, Optional
from datetime import datetime


class PerformanceTracker:
    """
    Tracks win rate per symbol per agent.
    Enables agents to bias toward profitable symbols.
    """

    def __init__(self, filepath: str = "data/agent_performance.json"):
        self.filepath = filepath
        self.data: Dict[str, Dict[str, Dict[str, Any]]] = {}
        self._load()

    def _load(self):
        """Load performance data from JSON file."""
        if os.path.exists(self.filepath):
            try:
                with open(self.filepath, "r") as f:
                    self.data = json.load(f)
            except (json.JSONDecodeError, IOError):
                self.data = {}
        else:
            self.data = {}

    def _save(self):
        """Save performance data to JSON file."""
        os.makedirs(os.path.dirname(self.filepath) or ".", exist_ok=True)
        with open(self.filepath, "w") as f:
            json.dump(self.data, f, indent=2)

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
                "last_trade": None,
            }

        # Update stats
        stats = self.data[agent_id][symbol]
        if pnl > 0:
            stats["wins"] += 1
        else:
            stats["losses"] += 1
        stats["total_pnl"] += pnl
        stats["last_trade"] = datetime.now().isoformat()

        self._save()

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


# Global instance
_tracker: Optional[PerformanceTracker] = None


def get_performance_tracker() -> PerformanceTracker:
    """Get or create the global performance tracker."""
    global _tracker
    if _tracker is None:
        _tracker = PerformanceTracker()
    return _tracker
