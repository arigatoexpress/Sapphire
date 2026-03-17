"""In-memory metrics tracker for agent performance metrics."""

import threading
import time
from collections import defaultdict, deque
from datetime import datetime
from typing import Any, Dict, List, Optional


class AgentMetricsTracker:
    """Tracks performance metrics for each agent."""

    def __init__(self, max_history: int = 1000):
        self.max_history = max_history
        self.lock = threading.Lock()

        # Metrics storage
        self.inference_times: Dict[str, deque] = defaultdict(lambda: deque(maxlen=max_history))
        self.last_inference_time: Dict[str, float] = {}
        self.inference_count: Dict[str, int] = defaultdict(int)
        self.input_tokens: Dict[str, List[int]] = defaultdict(list)
        self.output_tokens: Dict[str, List[int]] = defaultdict(list)
        self.costs: Dict[str, List[float]] = defaultdict(list)
        self.throughput: Dict[str, int] = defaultdict(int)
        self.success_count: Dict[str, int] = defaultdict(int)
        self.error_count: Dict[str, int] = defaultdict(int)
        self.confidences: Dict[str, deque] = defaultdict(lambda: deque(maxlen=max_history))
        self.models: Dict[str, str] = {}
        self.decision_latencies: Dict[str, deque] = defaultdict(lambda: deque(maxlen=max_history))
        self.response_times: Dict[str, deque] = defaultdict(lambda: deque(maxlen=max_history))
        self.market_data_latencies: Dict[str, deque] = defaultdict(
            lambda: deque(maxlen=max_history)
        )
        self.trade_execution_latencies: Dict[str, deque] = defaultdict(
            lambda: deque(maxlen=max_history)
        )
        self.slippage: Dict[str, deque] = defaultdict(lambda: deque(maxlen=max_history))
        self.fees: Dict[str, deque] = defaultdict(lambda: deque(maxlen=max_history))

    def record_inference(
        self,
        agent_id: str,
        inference_time: float,
        model: str,
        input_tokens: Optional[int] = None,
        output_tokens: Optional[int] = None,
        cost: Optional[float] = None,
        confidence: Optional[float] = None,
    ):
        """Record an inference event."""
        with self.lock:
            self.inference_times[agent_id].append(inference_time)
            self.last_inference_time[agent_id] = inference_time
            self.inference_count[agent_id] += 1
            self.models[agent_id] = model

            if input_tokens is not None:
                self.input_tokens[agent_id].append(input_tokens)
                if len(self.input_tokens[agent_id]) > self.max_history:
                    self.input_tokens[agent_id].pop(0)

            if output_tokens is not None:
                self.output_tokens[agent_id].append(output_tokens)
                if len(self.output_tokens[agent_id]) > self.max_history:
                    self.output_tokens[agent_id].pop(0)

            if cost is not None:
                self.costs[agent_id].append(cost)
                if len(self.costs[agent_id]) > self.max_history:
                    self.costs[agent_id].pop(0)

            if confidence is not None:
                self.confidences[agent_id].append(confidence)

    def record_decision(self, agent_id: str, latency: float):
        """Record decision latency."""
        with self.lock:
            self.decision_latencies[agent_id].append(latency)
            self.throughput[agent_id] += 1

    def record_success(self, agent_id: str):
        """Record a successful decision."""
        with self.lock:
            self.success_count[agent_id] += 1

    def record_error(self, agent_id: str, error_type: str):
        """Record an error."""
        with self.lock:
            self.error_count[agent_id] += 1

    def record_response_time(self, agent_id: str, response_time: float):
        """Record total response time."""
        with self.lock:
            self.response_times[agent_id].append(response_time)

    def record_market_data_latency(self, agent_id: str, symbol: str, latency: float):
        """Record market data latency."""
        with self.lock:
            key = f"{agent_id}:{symbol}"
            self.market_data_latencies[key].append(latency)

    def record_trade_execution_latency(self, agent_id: str, symbol: str, latency: float):
        """Record trade execution latency."""
        with self.lock:
            key = f"{agent_id}:{symbol}"
            self.trade_execution_latencies[key].append(latency)

    def record_slippage(self, agent_id: str, slippage_pct: float):
        """Record trade slippage."""
        with self.lock:
            self.slippage[agent_id].append(slippage_pct)

    def record_fee(self, agent_id: str, fee_usd: float):
        """Record trade fee."""
        with self.lock:
            self.fees[agent_id].append(fee_usd)

    def get_metrics(self, agent_id: Optional[str] = None) -> Dict[str, Any]:
        """Get metrics for agent(s)."""
        with self.lock:
            result = {}
            agents = [agent_id] if agent_id else list(self.inference_count.keys())

            for agent in agents:
                if agent not in self.inference_count:
                    continue

                # Calculate latency statistics
                inference_times = list(self.inference_times[agent])
                avg_latency = (
                    sum(inference_times) / len(inference_times) * 1000 if inference_times else 0
                )
                p95_latency = 0
                if inference_times:
                    sorted_times = sorted(inference_times)
                    p95_index = int(len(sorted_times) * 0.95)
                    p95_latency = (
                        sorted_times[p95_index] * 1000
                        if p95_index < len(sorted_times)
                        else sorted_times[-1] * 1000
                    )

                last_inference = self.last_inference_time.get(agent, 0) * 1000

                # Calculate token totals
                total_input_tokens = sum(self.input_tokens.get(agent, []))
                total_output_tokens = sum(self.output_tokens.get(agent, []))

                # Calculate average cost
                costs = self.costs.get(agent, [])
                avg_cost = sum(costs) / len(costs) if costs else 0

                # Calculate success rate
                total_decisions = self.success_count[agent] + self.error_count[agent]
                success_rate = (
                    self.success_count[agent] / total_decisions if total_decisions > 0 else 1.0
                )

                # Calculate average confidence
                avg_confidence = sum(confidences) / len(confidences) if confidences else 0.5

                # Calculate avg slippage and total fees
                slippage_list = list(self.slippage[agent])
                avg_slippage = sum(slippage_list) / len(slippage_list) if slippage_list else 0.0
                total_fees = sum(self.fees[agent])

                result[agent] = {
                    "agent_id": agent,
                    "latency": {
                        "last_inference_ms": last_inference,
                        "avg_inference_ms": avg_latency,
                        "p95_inference_ms": p95_latency,
                    },
                    "inference": {
                        "total_count": self.inference_count[agent],
                        "total_tokens_input": total_input_tokens,
                        "total_tokens_output": total_output_tokens,
                        "avg_cost_usd": avg_cost,
                        "model": self.models.get(agent, "unknown"),
                    },
                    "performance": {
                        "throughput": self.throughput[agent],
                        "success_rate": success_rate,
                        "avg_confidence": avg_confidence,
                        "error_count": self.error_count[agent],
                    },
                    "financials": {
                        "avg_slippage_pct": avg_slippage,
                        "total_fees_usd": total_fees,
                    },
                    "timestamp": time.time(),
                }

            return result


# Global metrics tracker instance
_metrics_tracker: Optional[AgentMetricsTracker] = None


def get_metrics_tracker() -> AgentMetricsTracker:
    """Get the global metrics tracker instance."""
    global _metrics_tracker
    if _metrics_tracker is None:
        _metrics_tracker = AgentMetricsTracker()
    return _metrics_tracker
