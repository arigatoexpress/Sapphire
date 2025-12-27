    async def get_agent_performance_metrics(self) -> List[Dict[str, Any]]:
        """
        Get performance metrics for all autonomous agents.
        Used by monitoring dashboard.
        """
        if not self.autonomous_agents:
            return []

        metrics = []
        for agent in self.autonomous_agents:
            strategy_summary = agent.get_strategy_summary()

            # Calculate recent performance (last 10 trades)
            recent_trades = agent.performance_history[-10:] if agent.performance_history else []
            recent_win_rate = 0.0
            if recent_trades:
                recent_wins = sum(1 for t in recent_trades if t.get('pnl_pct', 0) > 0)
                recent_win_rate = recent_wins / len(recent_trades)

            #  Determine health status
            health = "LEARNING"
            if agent.total_trades >= 5:
                if recent_win_rate > 0.6:
                    health = "HEALTHY"
                elif recent_win_rate > 0.4:
                    health = "PERFORMING"
                else:
                    health = "UNDERPERFORMING"

            metrics.append({
                "agent_id": agent.id,
                "name": agent.name,
                "specialization": agent.specialization,
                "total_trades": agent.total_trades,
                "winning_trades": agent.winning_trades,
                "win_rate": agent.get_win_rate(),
                "recent_win_rate": recent_win_rate,
                "health": health,
                "preferred_indicators": strategy_summary["preferred_indicators"],
                "indicator_scores": strategy_summary.get("indicator_scores", {}),
                "confidence_threshold": strategy_summary["confidence_threshold"]
            })

        return metrics

    async def get_consensus_history(self, limit: int = 20) -> List[Dict[str, Any]]:
        """
        Get recent consensus decisions with outcomes.
        Used by monitoring dashboard.
        """
        history = list(self._consensus_history)[:limit]

        # Enrich with outcome data if trade has closed
        for decision in history:
            symbol = decision.get("symbol")
            if symbol and symbol in self._open_positions:
                pos = self._open_positions[symbol]
                decision["position_status"] = "OPEN"
                decision["entry_price"] = pos.get("entry_price")
                decision["current_pnl"] = 0.0  # Could calculate if we had current price
            elif symbol:
                # Try to find in recent trades
                for trade in self._recent_trades:
                    if trade.get("symbol") == symbol:
                        decision["position_status"] = "CLOSED"
                        decision["final_pnl"] = trade.get("pnl", 0.0)
                        break

        return history

    async def get_agent_evolution(self, agent_id: str) -> Dict[str, Any]:
        """
        Get how an agent's strategy has evolved over time.
        Used by monitoring dashboard.
        """
        if agent_id not in self._agent_snapshots:
            return {"agent_id": agent_id, "snapshots": []}

        return {
            "agent_id": agent_id,
            "snapshots": self._agent_snapshots[agent_id]
        }

    async def _take_agent_snapshots(self):
        """
        Periodically snapshot agent strategies for evolution tracking.
        Call this every hour or after significant trades.
        """
        if not self.autonomous_agents:
            return

        current_time = time.time()

        # Take snapshot every hour
        if current_time - self._last_snapshot_time < 3600:
            return

        for agent in self.autonomous_agents:
            if agent.id not in self._agent_snapshots:
                self._agent_snapshots[agent.id] = []

            snapshot = {
                "timestamp": current_time,
                "total_trades": agent.total_trades,
                "win_rate": agent.get_win_rate(),
                "preferred_indicators": agent.strategy_config["preferred_indicators"].copy(),
                "indicator_scores": agent.strategy_config.get("indicator_scores", {}).copy(),
                "confidence_threshold": agent.strategy_config["confidence_threshold"]
            }

            self._agent_snapshots[agent.id].append(snapshot)

            # Keep only last 100 snapshots per agent
            if len(self._agent_snapshots[agent.id]) > 100:
                self._agent_snapshots[agent.id] = self._agent_snapshots[agent.id][-100:]

        self._last_snapshot_time = current_time
        logger.info(f"📸 Took strategy snapshots for {len(self.autonomous_agents)} agents")
