"""Swarm Intelligence — Reputation-Weighted Trade Idea Aggregation.

Aggregates trade ideas from multiple contributing bots, weighting each
signal by the bot's reputation score.  Supports:

- Submitting trade ideas from external bots
- Reputation-weighted consensus aggregation
- Conviction scoring (strong consensus vs. split opinions)
- Prediction market sentiment as a virtual voter (Phase 8)
- Idea lifecycle: open → aggregated → expired
- Integration with BotReputationService for weights + recording
"""

import threading
import time
from collections import defaultdict
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from loguru import logger

from src.collaboration.reputation import BotReputationService

if TYPE_CHECKING:
    from src.feeds.prediction_aggregator import PredictionAggregator


class SwarmAggregator:
    """Aggregates trade ideas from bots using reputation-weighted voting."""

    # Conviction thresholds
    HIGH_CONVICTION_THRESHOLD = 0.70   # ≥70% weighted agreement = high conviction
    MODERATE_CONVICTION_THRESHOLD = 0.50

    # Idea expiry (seconds)
    IDEA_TTL_SECONDS = 3600  # Ideas expire after 1 hour
    MAX_IDEAS_PER_SYMBOL = 50  # Max open ideas per symbol

    # Prediction market virtual voter weight (0.0–1.0)
    # Controls how much prediction market sentiment influences consensus.
    PM_WEIGHT = 0.25  # 25% of a top-reputation bot

    def __init__(
        self,
        reputation: BotReputationService,
        prediction_aggregator: Optional["PredictionAggregator"] = None,
    ):
        self._reputation = reputation
        self._prediction_aggregator = prediction_aggregator
        self._lock = threading.Lock()
        # {symbol: [idea_dict, ...]}
        self._ideas: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        self._idea_counter = 0

    def submit_idea(
        self,
        bot_id: str,
        symbol: str,
        direction: str,
        confidence: float = 0.5,
        timeframe: str = "1h",
        rationale: str = "",
        target_price: float = 0.0,
        stop_loss: float = 0.0,
    ) -> Dict[str, Any]:
        """Submit a trade idea from a bot.

        Args:
            bot_id: The contributing bot's identifier.
            symbol: Trading pair (e.g., "BTC/USDT", "ETH").
            direction: "LONG" or "SHORT".
            confidence: Bot's own confidence 0.0–1.0.
            timeframe: Expected timeframe (e.g., "15m", "1h", "4h", "1d").
            rationale: Brief explanation of the trade thesis.
            target_price: Optional target price.
            stop_loss: Optional stop-loss price.

        Returns:
            Dict with ok, idea_id, reputation_weight, etc.
        """
        with self._lock:
            # Check if bot is banned
            if self._reputation.is_banned(bot_id):
                return {"ok": False, "error": "bot_is_banned"}

            # Normalize
            symbol = str(symbol or "").strip().upper()
            direction = str(direction or "").strip().upper()
            if direction not in ("LONG", "SHORT"):
                return {"ok": False, "error": "invalid_direction", "detail": "Must be LONG or SHORT"}
            if not symbol:
                return {"ok": False, "error": "missing_symbol"}

            confidence = max(0.0, min(1.0, float(confidence)))

            # Get reputation weight
            weight = self._reputation.reputation_weight(bot_id)

            # Record idea in reputation system
            self._idea_counter += 1
            idea_id = f"IDEA-{self._idea_counter:05d}"
            self._reputation.record_idea(bot_id, idea_id=idea_id)

            # Prune expired ideas for this symbol
            self._prune_expired_locked(symbol)

            # Create idea record
            idea = {
                "idea_id": idea_id,
                "bot_id": str(bot_id or "").strip().upper(),
                "symbol": symbol,
                "direction": direction,
                "confidence": confidence,
                "reputation_weight": weight,
                "weighted_score": weight * confidence,
                "timeframe": str(timeframe or "1h").strip(),
                "rationale": str(rationale or "")[:500],
                "target_price": float(target_price),
                "stop_loss": float(stop_loss),
                "submitted_at": int(time.time()),
                "status": "open",
            }

            ideas = self._ideas[symbol]
            # Enforce max ideas per symbol
            if len(ideas) >= self.MAX_IDEAS_PER_SYMBOL:
                ideas.pop(0)  # Remove oldest
            ideas.append(idea)

            logger.info(
                f"Swarm idea submitted: {idea_id} by {bot_id} — "
                f"{direction} {symbol} (conf={confidence:.2f}, weight={weight:.2f})"
            )

            return {
                "ok": True,
                "idea_id": idea_id,
                "symbol": symbol,
                "direction": direction,
                "confidence": confidence,
                "reputation_weight": weight,
                "weighted_score": idea["weighted_score"],
            }

    def aggregate(self, symbol: str) -> Dict[str, Any]:
        """Aggregate all open ideas for a symbol into a consensus signal.

        Returns a weighted consensus with conviction level.
        """
        with self._lock:
            symbol = str(symbol or "").strip().upper()
            if not symbol:
                return {"ok": False, "error": "missing_symbol"}

            self._prune_expired_locked(symbol)
            ideas = self._ideas.get(symbol, [])
            open_ideas = [i for i in ideas if i.get("status") == "open"]

            if not open_ideas:
                return {
                    "ok": True,
                    "symbol": symbol,
                    "consensus": "NEUTRAL",
                    "conviction": 0.0,
                    "total_ideas": 0,
                    "long_count": 0,
                    "short_count": 0,
                    "weighted_long": 0.0,
                    "weighted_short": 0.0,
                    "net_score": 0.0,
                    "contributors": [],
                }

            long_ideas = [i for i in open_ideas if i["direction"] == "LONG"]
            short_ideas = [i for i in open_ideas if i["direction"] == "SHORT"]

            # Weighted sums
            weighted_long = sum(i["weighted_score"] for i in long_ideas)
            weighted_short = sum(i["weighted_score"] for i in short_ideas)

            # Inject prediction market sentiment as virtual voter (Phase 8)
            pm_adjustment = self._get_pm_adjustment(symbol)
            if pm_adjustment:
                weighted_long += pm_adjustment.get("long_boost", 0.0)
                weighted_short += pm_adjustment.get("short_boost", 0.0)

            total_weight = weighted_long + weighted_short

            # Net directional score
            net_score = weighted_long - weighted_short

            # Conviction: how much of weighted signal is in one direction
            if total_weight > 0:
                dominant_weight = max(weighted_long, weighted_short)
                conviction = dominant_weight / total_weight
            else:
                conviction = 0.0

            # Consensus direction
            if conviction >= self.HIGH_CONVICTION_THRESHOLD:
                consensus = "LONG" if weighted_long > weighted_short else "SHORT"
            elif conviction >= self.MODERATE_CONVICTION_THRESHOLD:
                consensus = "LEAN_LONG" if weighted_long > weighted_short else "LEAN_SHORT"
            else:
                consensus = "NEUTRAL"

            # Contributors list
            contributors = []
            for idea in open_ideas:
                contributors.append({
                    "bot_id": idea["bot_id"],
                    "direction": idea["direction"],
                    "confidence": idea["confidence"],
                    "reputation_weight": idea["reputation_weight"],
                    "weighted_score": idea["weighted_score"],
                    "idea_id": idea["idea_id"],
                })

            # Average target/stop across dominant direction
            dominant_ideas = long_ideas if weighted_long >= weighted_short else short_ideas
            avg_target = 0.0
            avg_stop = 0.0
            target_count = 0
            stop_count = 0
            for di in dominant_ideas:
                if di["target_price"] > 0:
                    avg_target += di["target_price"] * di["weighted_score"]
                    target_count += 1
                if di["stop_loss"] > 0:
                    avg_stop += di["stop_loss"] * di["weighted_score"]
                    stop_count += 1
            dominant_total_weight = sum(d["weighted_score"] for d in dominant_ideas) or 1.0
            if target_count > 0:
                avg_target /= dominant_total_weight
            if stop_count > 0:
                avg_stop /= dominant_total_weight

            # Include PM virtual voter in contributors if it contributed
            if pm_adjustment:
                contributors.append({
                    "bot_id": "__PREDICTION_MARKET__",
                    "direction": pm_adjustment["direction"],
                    "confidence": pm_adjustment["confidence"],
                    "reputation_weight": self.PM_WEIGHT,
                    "weighted_score": pm_adjustment.get("long_boost", 0.0) + pm_adjustment.get("short_boost", 0.0),
                    "idea_id": "pm_virtual_voter",
                    "source": "prediction_market",
                    "sentiment": pm_adjustment.get("sentiment", "neutral"),
                })

            return {
                "ok": True,
                "symbol": symbol,
                "consensus": consensus,
                "conviction": round(conviction, 4),
                "total_ideas": len(open_ideas),
                "long_count": len(long_ideas),
                "short_count": len(short_ideas),
                "weighted_long": round(weighted_long, 4),
                "weighted_short": round(weighted_short, 4),
                "net_score": round(net_score, 4),
                "avg_target_price": round(avg_target, 6) if avg_target else 0.0,
                "avg_stop_loss": round(avg_stop, 6) if avg_stop else 0.0,
                "contributors": contributors,
                "pm_adjustment": pm_adjustment,
            }

    def get_idea(self, idea_id: str) -> Optional[Dict[str, Any]]:
        """Look up a specific idea by ID."""
        with self._lock:
            for ideas in self._ideas.values():
                for idea in ideas:
                    if idea.get("idea_id") == idea_id:
                        return dict(idea)
            return None

    def record_idea_outcome(
        self,
        idea_id: str,
        accurate: bool,
        profitable: bool,
        pnl: float = 0.0,
    ) -> Dict[str, Any]:
        """Record the outcome of a trade idea and update bot reputation.

        This closes the feedback loop — after a trade idea is executed and
        the result is known, we record it in the reputation system.
        """
        with self._lock:
            idea = None
            for ideas in self._ideas.values():
                for i in ideas:
                    if i.get("idea_id") == idea_id:
                        idea = i
                        break
                if idea:
                    break

            if not idea:
                return {"ok": False, "error": "idea_not_found"}

            bot_id = idea["bot_id"]
            idea["status"] = "resolved"

            # Record outcome in reputation system
            result = self._reputation.record_outcome(
                bot_id, accurate=accurate, profitable=profitable, pnl=pnl
            )

            logger.info(
                f"Swarm idea outcome: {idea_id} by {bot_id} — "
                f"accurate={accurate}, profitable={profitable}, pnl={pnl:.2f}"
            )

            return {
                "ok": True,
                "idea_id": idea_id,
                "bot_id": bot_id,
                "accurate": accurate,
                "profitable": profitable,
                "pnl": pnl,
                "new_score": result.get("score", 0),
                "new_status": result.get("status", "active"),
            }

    def open_ideas(self, symbol: str = "") -> List[Dict[str, Any]]:
        """List open ideas, optionally filtered by symbol."""
        with self._lock:
            result = []
            if symbol:
                symbol = str(symbol).strip().upper()
                self._prune_expired_locked(symbol)
                for idea in self._ideas.get(symbol, []):
                    if idea.get("status") == "open":
                        result.append(dict(idea))
            else:
                for sym in list(self._ideas.keys()):
                    self._prune_expired_locked(sym)
                    for idea in self._ideas[sym]:
                        if idea.get("status") == "open":
                            result.append(dict(idea))
            return result

    def active_symbols(self) -> List[str]:
        """Return symbols with at least one open idea."""
        with self._lock:
            symbols = []
            for sym in list(self._ideas.keys()):
                self._prune_expired_locked(sym)
                if any(i.get("status") == "open" for i in self._ideas[sym]):
                    symbols.append(sym)
            return sorted(symbols)

    def stats(self) -> Dict[str, Any]:
        """Return aggregation statistics."""
        with self._lock:
            total_open = 0
            total_resolved = 0
            total_expired = 0
            symbols_active = 0
            for sym in list(self._ideas.keys()):
                self._prune_expired_locked(sym)
                ideas = self._ideas[sym]
                open_count = sum(1 for i in ideas if i.get("status") == "open")
                resolved_count = sum(1 for i in ideas if i.get("status") == "resolved")
                expired_count = sum(1 for i in ideas if i.get("status") == "expired")
                total_open += open_count
                total_resolved += resolved_count
                total_expired += expired_count
                if open_count > 0:
                    symbols_active += 1
            return {
                "total_ideas_submitted": self._idea_counter,
                "open_ideas": total_open,
                "resolved_ideas": total_resolved,
                "expired_ideas": total_expired,
                "active_symbols": symbols_active,
            }

    def _get_pm_adjustment(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Derive a virtual vote from prediction market sentiment.

        Translates PM consensus (probability-based) into a directional
        weight boost for the swarm aggregation. Returns None if PM
        data is unavailable or neutral.
        """
        if not self._prediction_aggregator or not self._prediction_aggregator.enabled:
            return None

        try:
            sent = self._prediction_aggregator.get_symbol_sentiment(symbol)
        except Exception:
            return None

        if sent["signal_count"] == 0:
            return None

        sentiment = sent["sentiment"]
        confidence = sent["confidence"]
        prob = sent["weighted_probability"]

        # Map sentiment to directional boost
        if sentiment in ("strongly_bullish", "bullish"):
            direction = "LONG"
            # Strength scales with distance from 0.5
            strength = (prob - 0.5) * 2  # 0.6→0.2, 0.75→0.5, 0.9→0.8
            long_boost = self.PM_WEIGHT * strength * confidence
            return {
                "direction": direction,
                "sentiment": sentiment,
                "confidence": round(confidence, 4),
                "probability": round(prob, 4),
                "long_boost": round(max(0.0, long_boost), 4),
                "short_boost": 0.0,
                "signal_count": sent["signal_count"],
            }
        elif sentiment in ("strongly_bearish", "bearish"):
            direction = "SHORT"
            strength = (0.5 - prob) * 2  # 0.4→0.2, 0.25→0.5, 0.1→0.8
            short_boost = self.PM_WEIGHT * strength * confidence
            return {
                "direction": direction,
                "sentiment": sentiment,
                "confidence": round(confidence, 4),
                "probability": round(prob, 4),
                "long_boost": 0.0,
                "short_boost": round(max(0.0, short_boost), 4),
                "signal_count": sent["signal_count"],
            }

        return None  # Neutral — no adjustment

    def _prune_expired_locked(self, symbol: str) -> None:
        """Mark expired ideas (must be called under lock)."""
        now = int(time.time())
        for idea in self._ideas.get(symbol, []):
            if idea.get("status") == "open":
                if now - idea.get("submitted_at", 0) > self.IDEA_TTL_SECONDS:
                    idea["status"] = "expired"
