"""Advanced trade correlation analysis for portfolio risk management."""

from __future__ import annotations

import asyncio
import logging
import statistics
from collections import defaultdict
from dataclasses import dataclass
from typing import Deque, Dict, List, Optional, Set, Tuple

from .time_sync import get_timestamp_us

logger = logging.getLogger(__name__)


@dataclass
class CorrelationMatrix:
    """Correlation matrix between trading symbols."""

    symbols: List[str]
    correlations: Dict[Tuple[str, str], float]
    timestamp_us: int
    sample_size: int

    def get_correlation(self, symbol1: str, symbol2: str) -> float:
        """Get correlation between two symbols."""
        if symbol1 == symbol2:
            return 1.0
        key = tuple(sorted([symbol1, symbol2]))
        return self.correlations.get(key, 0.0)

    def get_symbol_correlations(self, symbol: str) -> Dict[str, float]:
        """Get all correlations for a specific symbol."""
        return {s: self.get_correlation(symbol, s) for s in self.symbols if s != symbol}

    def get_highly_correlated_groups(self, threshold: float = 0.7) -> List[Set[str]]:
        """Find groups of highly correlated symbols."""
        visited = set()
        groups = []

        for symbol in self.symbols:
            if symbol in visited:
                continue

            # Find all symbols correlated with this one above threshold
            group = {symbol}
            stack = [symbol]

            while stack:
                current = stack.pop()
                if current in visited:
                    continue
                visited.add(current)

                for other_symbol in self.symbols:
                    if (
                        other_symbol not in visited
                        and other_symbol not in group
                        and abs(self.get_correlation(current, other_symbol)) >= threshold
                    ):
                        group.add(other_symbol)
                        stack.append(other_symbol)

            if len(group) > 1:
                groups.append(group)

        return groups


@dataclass
class PositionExposure:
    """Position exposure analysis for risk management."""

    symbol: str
    position_size: float
    market_value: float
    beta: float  # Beta relative to portfolio
    contribution_to_risk: float
    diversification_ratio: float
    timestamp_us: int


@dataclass
class PortfolioCorrelationRisk:
    """Portfolio-level correlation risk assessment."""

    total_exposure: float
    correlated_exposure: float
    diversification_ratio: float
    concentration_risk: float
    beta_adjusted_exposure: float
    risk_concentration_score: float
    recommended_max_position: float
    risk_adjusted_limits: Dict[str, float]
    timestamp_us: int


class TradeCorrelationAnalyzer:
    """
    Advanced correlation analysis for portfolio risk management.
    Implements multiple correlation measures and risk concentration analysis.
    """

    def __init__(self, window_size: int = 1000, correlation_window: int = 500):
        # Price data storage
        self.price_history: Dict[str, Deque[float]] = defaultdict(lambda: Deque(maxlen=window_size))
        self.return_history: Dict[str, Deque[float]] = defaultdict(
            lambda: Deque(maxlen=correlation_window)
        )

        # Correlation tracking
        self.correlation_matrices: Deque[CorrelationMatrix] = Deque(
            maxlen=10
        )  # Keep last 10 matrices
        self.correlation_cache: Dict[Tuple[str, str], float] = {}

        # Risk analysis
        self.position_history: Deque[Dict] = Deque(maxlen=1000)
        self.portfolio_exposures: Dict[str, PositionExposure] = {}

        # Market beta calculations
        self.market_returns: Deque[float] = Deque(maxlen=correlation_window)
        self.symbol_betas: Dict[str, float] = {}

        # Risk thresholds
        self.max_correlation_exposure = 0.3  # Max 30% exposure to correlated assets
        self.min_diversification_ratio = 0.7  # Minimum diversification score
        self.max_concentration_score = 0.8  # Maximum concentration risk

    def add_price_data(self, symbol: str, price: float, volume: Optional[float] = None) -> None:
        """
        Add price data for correlation analysis.
        Calculates returns and updates correlation matrices.
        """
        self.price_history[symbol].append(price)

        # Calculate returns if we have enough price data
        prices = list(self.price_history[symbol])
        if len(prices) >= 2:
            ret = (prices[-1] - prices[-2]) / prices[-2] if prices[-2] != 0 else 0
            self.return_history[symbol].append(ret)

            # Update market returns (simple average for now)
            if len(self.return_history[symbol]) >= 10:
                self.market_returns.append(statistics.mean(list(self.return_history[symbol])[-10:]))

        # Update correlations periodically
        if len(self.return_history[symbol]) % 100 == 0:  # Every 100 data points
            self._update_correlations()

    def add_position_update(
        self, symbol: str, position_size: float, market_value: float, entry_price: float
    ) -> None:
        """Add position update for exposure analysis."""
        position_data = {
            "symbol": symbol,
            "position_size": position_size,
            "market_value": market_value,
            "entry_price": entry_price,
            "timestamp_us": get_timestamp_us(),
        }

        self.position_history.append(position_data)
        self._update_portfolio_exposures()

    def get_correlation_matrix(self) -> Optional[CorrelationMatrix]:
        """Get the latest correlation matrix."""
        return self.correlation_matrices[-1] if self.correlation_matrices else None

    def get_symbol_correlation_risk(self, symbol: str) -> Dict[str, float]:
        """
        Get correlation-based risk metrics for a symbol.
        Returns risk scores and recommended position limits.
        """
        matrix = self.get_correlation_matrix()
        if not matrix:
            return {"correlation_risk": 0.0, "recommended_limit": 1.0}

        correlations = matrix.get_symbol_correlations(symbol)

        # Calculate weighted correlation risk
        high_corr_symbols = [s for s, corr in correlations.items() if abs(corr) > 0.5]
        avg_high_corr = (
            statistics.mean([abs(correlations[s]) for s in high_corr_symbols])
            if high_corr_symbols
            else 0
        )

        # Risk score based on correlation concentration
        correlation_risk = min(avg_high_corr * len(high_corr_symbols) / 5.0, 1.0)

        # Recommended position limit based on correlation risk
        recommended_limit = max(0.1, 1.0 - correlation_risk)

        return {
            "correlation_risk": correlation_risk,
            "recommended_limit": recommended_limit,
            "highly_correlated_symbols": high_corr_symbols,
            "avg_correlation": avg_high_corr,
            "correlation_count": len(high_corr_symbols),
        }

    def analyze_portfolio_correlation_risk(
        self, current_positions: List[Dict]
    ) -> PortfolioCorrelationRisk:
        """
        Analyze portfolio-level correlation risk.
        Returns comprehensive risk assessment and position limits.
        """
        total_exposure = sum(abs(p.get("market_value", 0)) for p in current_positions)
        if total_exposure == 0:
            return PortfolioCorrelationRisk(
                total_exposure=0,
                correlated_exposure=0,
                diversification_ratio=1.0,
                concentration_risk=0,
                beta_adjusted_exposure=0,
                risk_concentration_score=0,
                recommended_max_position=0.1,
                risk_adjusted_limits={},
                timestamp_us=get_timestamp_us(),
            )

        matrix = self.get_correlation_matrix()
        correlated_groups = matrix.get_highly_correlated_groups(0.6) if matrix else []

        # Calculate correlated exposure
        correlated_exposure = 0
        symbol_exposures = {p["symbol"]: abs(p.get("market_value", 0)) for p in current_positions}

        for group in correlated_groups:
            group_symbols = [s for s in group if s in symbol_exposures]
            if len(group_symbols) > 1:
                # Add exposure from correlated positions (excluding the largest)
                exposures = [symbol_exposures[s] for s in group_symbols]
                exposures.sort(reverse=True)
                correlated_exposure += sum(exposures[1:])  # Sum all but the largest

        # Diversification ratio
        diversification_ratio = (
            1.0 - (correlated_exposure / total_exposure) if total_exposure > 0 else 1.0
        )

        # Concentration risk (Herfindahl-Hirschman Index style)
        concentration_risk = sum(
            (exposure / total_exposure) ** 2 for exposure in symbol_exposures.values()
        )

        # Beta-adjusted exposure
        beta_adjusted_exposure = sum(
            exposure * max(0.5, self.symbol_betas.get(symbol, 1.0))
            for symbol, exposure in symbol_exposures.items()
        )

        # Risk concentration score (0-1, higher = more concentrated risk)
        risk_concentration_score = (
            (1 - diversification_ratio) * 0.4  # Correlation concentration
            + concentration_risk * 0.4  # Position concentration
            + min(beta_adjusted_exposure / total_exposure, 2.0) * 0.2  # Beta concentration
        )

        # Recommended max position size based on risk
        recommended_max_position = max(0.05, 1.0 - risk_concentration_score)

        # Risk-adjusted position limits per symbol
        risk_adjusted_limits = {}
        for symbol in symbol_exposures.keys():
            symbol_risk = self.get_symbol_correlation_risk(symbol)
            portfolio_limit = recommended_max_position
            correlation_limit = symbol_risk["recommended_limit"]

            # Combine limits (take the more restrictive)
            risk_adjusted_limits[symbol] = min(portfolio_limit, correlation_limit)

        return PortfolioCorrelationRisk(
            total_exposure=total_exposure,
            correlated_exposure=correlated_exposure,
            diversification_ratio=diversification_ratio,
            concentration_risk=concentration_risk,
            beta_adjusted_exposure=beta_adjusted_exposure,
            risk_concentration_score=risk_concentration_score,
            recommended_max_position=recommended_max_position,
            risk_adjusted_limits=risk_adjusted_limits,
            timestamp_us=get_timestamp_us(),
        )

    def get_correlation_clusters(self, threshold: float = 0.6) -> List[Dict]:
        """
        Get correlation clusters for portfolio construction guidance.
        """
        matrix = self.get_correlation_matrix()
        if not matrix:
            return []

        groups = matrix.get_highly_correlated_groups(threshold)

        clusters = []
        for i, group in enumerate(groups):
            cluster_data = {
                "cluster_id": i,
                "symbols": list(group),
                "size": len(group),
                "avg_correlation": self._calculate_cluster_avg_correlation(group, matrix),
                "risk_score": len(group) * self._calculate_cluster_avg_correlation(group, matrix),
            }
            clusters.append(cluster_data)

        return sorted(clusters, key=lambda x: x["risk_score"], reverse=True)

    def _update_correlations(self) -> None:
        """Update correlation matrices for all symbol pairs."""
        symbols = list(self.return_history.keys())
        if len(symbols) < 2:
            return

        # Ensure all symbols have the same return history length
        min_length = min(len(self.return_history[s]) for s in symbols)
        if min_length < 30:  # Need minimum sample size
            return

        # Calculate correlation matrix
        correlations = {}
        sample_size = min_length

        for i, symbol1 in enumerate(symbols):
            for symbol2 in symbols[i + 1 :]:
                returns1 = list(self.return_history[symbol1])[-sample_size:]
                returns2 = list(self.return_history[symbol2])[-sample_size:]

                try:
                    correlation = statistics.correlation(returns1, returns2)
                    key = tuple(sorted([symbol1, symbol2]))
                    correlations[key] = correlation
                except (statistics.StatisticsError, ZeroDivisionError):
                    continue

        if correlations:
            matrix = CorrelationMatrix(
                symbols=symbols,
                correlations=correlations,
                timestamp_us=get_timestamp_us(),
                sample_size=sample_size,
            )
            self.correlation_matrices.append(matrix)

            # Update cache
            self.correlation_cache.update(correlations)

            # Update betas
            self._update_symbol_betas()

    def _update_symbol_betas(self) -> None:
        """Update beta calculations for all symbols."""
        if not self.market_returns or len(self.market_returns) < 30:
            return

        market_returns_list = list(self.market_returns)

        for symbol, returns in self.return_history.items():
            if len(returns) < 30:
                continue

            symbol_returns = list(returns)[-len(market_returns_list) :]

            if len(symbol_returns) != len(market_returns_list):
                continue

            try:
                beta = statistics.linear_regression(market_returns_list, symbol_returns).slope
                self.symbol_betas[symbol] = max(0.1, min(3.0, beta))  # Bound beta
            except (statistics.StatisticsError, ZeroDivisionError):
                self.symbol_betas[symbol] = 1.0  # Default beta

    def _update_portfolio_exposures(self) -> None:
        """Update portfolio exposure calculations."""
        if not self.position_history:
            return

        # Get latest positions
        latest_positions = {}
        for position in reversed(list(self.position_history)):
            symbol = position["symbol"]
            if symbol not in latest_positions:
                latest_positions[symbol] = position

        # Calculate exposures
        for symbol, position in latest_positions.items():
            beta = self.symbol_betas.get(symbol, 1.0)
            market_value = position["market_value"]

            # Contribution to portfolio risk (beta * exposure)
            contribution_to_risk = beta * market_value

            # Diversification ratio (lower beta = better diversification)
            diversification_ratio = 1.0 / max(beta, 0.5)

            exposure = PositionExposure(
                symbol=symbol,
                position_size=position["position_size"],
                market_value=market_value,
                beta=beta,
                contribution_to_risk=contribution_to_risk,
                diversification_ratio=diversification_ratio,
                timestamp_us=get_timestamp_us(),
            )

            self.portfolio_exposures[symbol] = exposure

    def _calculate_cluster_avg_correlation(
        self, cluster: Set[str], matrix: CorrelationMatrix
    ) -> float:
        """Calculate average correlation within a cluster."""
        if len(cluster) < 2:
            return 0.0

        correlations = []
        cluster_list = list(cluster)

        for i in range(len(cluster_list)):
            for j in range(i + 1, len(cluster_list)):
                corr = matrix.get_correlation(cluster_list[i], cluster_list[j])
                correlations.append(abs(corr))

        return statistics.mean(correlations) if correlations else 0.0

    def get_risk_management_recommendations(self) -> Dict[str, any]:
        """Get comprehensive risk management recommendations."""
        matrix = self.get_correlation_matrix()

        recommendations = {
            "correlation_clusters": self.get_correlation_clusters(),
            "high_risk_symbols": [],
            "diversification_opportunities": [],
            "rebalancing_needed": False,
            "risk_limits": {},
            "timestamp_us": get_timestamp_us(),
        }

        if matrix:
            # Identify high-risk symbols
            for symbol in matrix.symbols:
                risk = self.get_symbol_correlation_risk(symbol)
                if risk["correlation_risk"] > 0.7:
                    recommendations["high_risk_symbols"].append(
                        {
                            "symbol": symbol,
                            "risk_score": risk["correlation_risk"],
                            "recommended_limit": risk["recommended_limit"],
                        }
                    )

            # Find diversification opportunities (low correlation symbols)
            avg_correlations = {}
            for symbol in matrix.symbols:
                corr_values = [abs(c) for c in matrix.get_symbol_correlations(symbol).values()]
                avg_correlations[symbol] = statistics.mean(corr_values) if corr_values else 0

            # Symbols with low average correlation are diversification opportunities
            low_corr_symbols = sorted(avg_correlations.items(), key=lambda x: x[1])[:5]
            recommendations["diversification_opportunities"] = [
                {"symbol": s, "avg_correlation": c} for s, c in low_corr_symbols if c < 0.3
            ]

        return recommendations


# Global correlation analyzer instance
_correlation_analyzer: Optional[TradeCorrelationAnalyzer] = None


async def get_correlation_analyzer() -> TradeCorrelationAnalyzer:
    """Get global correlation analyzer instance."""
    global _correlation_analyzer
    if _correlation_analyzer is None:
        _correlation_analyzer = TradeCorrelationAnalyzer()
    return _correlation_analyzer
