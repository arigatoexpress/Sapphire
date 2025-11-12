"""Advanced risk analysis for trading operations."""
from __future__ import annotations
import logging
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)

class RiskLevel(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

@dataclass
class RiskAssessment:
    """Comprehensive risk assessment."""
    overall_level: RiskLevel
    confidence: float
    risk_factors: List[str]
    mitigating_factors: List[str]
    recommendations: List[str]
    quantitative_metrics: Dict[str, float]
    timestamp: datetime = None

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now()

@dataclass
class PositionRisk:
    """Risk assessment for individual positions."""
    symbol: str
    position_size: float
    unrealized_pnl: float
    risk_level: RiskLevel
    var_95: float  # Value at Risk 95%
    max_loss_potential: float
    correlation_risk: float
    liquidity_risk: str
    recommendations: List[str]

class RiskAnalyzer:
    """Advanced risk analysis and management."""

    def __init__(self):
        self.max_portfolio_risk = 0.02  # 2% max daily loss
        self.max_position_risk = 0.005  # 0.5% max position risk
        self.var_confidence = 0.95
        self.risk_free_rate = 0.02  # 2% risk-free rate

    async def assess_portfolio_risk(
        self,
        portfolio_data: Dict[str, Any],
        market_conditions: Dict[str, Any]
    ) -> RiskAssessment:
        """Assess overall portfolio risk."""
        # Calculate various risk metrics
        metrics = self._calculate_risk_metrics(portfolio_data, market_conditions)

        # Determine overall risk level
        overall_level = self._determine_risk_level(metrics)

        # Identify risk factors and mitigations
        risk_factors = self._identify_risk_factors(metrics, portfolio_data)
        mitigating_factors = self._identify_mitigating_factors(metrics, portfolio_data)

        # Generate recommendations
        recommendations = self._generate_risk_recommendations(
            overall_level, metrics, portfolio_data
        )

        # Calculate confidence in assessment
        confidence = self._calculate_assessment_confidence(metrics)

        assessment = RiskAssessment(
            overall_level=overall_level,
            confidence=confidence,
            risk_factors=risk_factors,
            mitigating_factors=mitigating_factors,
            recommendations=recommendations,
            quantitative_metrics=metrics
        )

        return assessment

    async def assess_position_risk(
        self,
        symbol: str,
        position_data: Dict[str, Any],
        market_data: Dict[str, Any]
    ) -> PositionRisk:
        """Assess risk for individual position."""
        # Calculate position-specific risk metrics
        position_size = position_data.get('size', 0)
        entry_price = position_data.get('entry_price', 0)
        current_price = market_data.get('current_price', entry_price)

        unrealized_pnl = (current_price - entry_price) * position_size

        # Calculate VaR
        var_95 = self._calculate_position_var(symbol, position_data, market_data)

        # Assess various risk factors
        risk_level = self._assess_position_risk_level(position_data, market_data)
        correlation_risk = self._calculate_correlation_risk(symbol, portfolio_data={})
        liquidity_risk = self._assess_liquidity_risk(symbol, market_data)
        max_loss_potential = self._calculate_max_loss_potential(position_data, market_data)

        # Generate recommendations
        recommendations = self._generate_position_recommendations(
            symbol, risk_level, position_data, market_data
        )

        position_risk = PositionRisk(
            symbol=symbol,
            position_size=position_size,
            unrealized_pnl=unrealized_pnl,
            risk_level=risk_level,
            var_95=var_95,
            max_loss_potential=max_loss_potential,
            correlation_risk=correlation_risk,
            liquidity_risk=liquidity_risk,
            recommendations=recommendations
        )

        return position_risk

    async def monitor_risk_limits(
        self,
        current_metrics: Dict[str, float],
        limits: Dict[str, float]
    ) -> List[Dict[str, Any]]:
        """Monitor risk limits and generate alerts."""
        alerts = []

        for metric_name, limit in limits.items():
            current_value = current_metrics.get(metric_name, 0)

            if current_value > limit:
                alert = {
                    'metric': metric_name,
                    'current_value': current_value,
                    'limit': limit,
                    'breach_percentage': ((current_value - limit) / limit) * 100,
                    'severity': self._determine_alert_severity(current_value, limit),
                    'recommendation': self._generate_limit_breach_recommendation(metric_name)
                }
                alerts.append(alert)

        return alerts

    async def calculate_optimal_position_size(
        self,
        symbol: str,
        portfolio_value: float,
        risk_per_trade: float,
        stop_loss_percentage: float,
        market_volatility: float
    ) -> Dict[str, Any]:
        """Calculate optimal position size using risk management principles."""
        # Kelly Criterion based position sizing
        win_probability = 0.6  # Assume 60% win rate
        win_loss_ratio = 2.0   # Assume 2:1 reward to risk

        kelly_percentage = (win_probability * win_loss_ratio - 1) / win_loss_ratio
        kelly_percentage = max(0.01, min(kelly_percentage, 0.25))  # Cap at 25%

        # Adjust for volatility and risk tolerance
        volatility_adjustment = 1.0 / (1.0 + market_volatility * 2)
        risk_adjusted_kelly = kelly_percentage * volatility_adjustment

        # Calculate position size
        risk_amount = portfolio_value * risk_per_trade
        stop_loss_amount = risk_amount / stop_loss_percentage

        optimal_position_value = risk_amount / stop_loss_percentage
        optimal_position_percentage = optimal_position_value / portfolio_value

        # Apply Kelly adjustment
        final_position_percentage = min(optimal_position_percentage, risk_adjusted_kelly)

        sizing = {
            'kelly_percentage': kelly_percentage,
            'volatility_adjustment': volatility_adjustment,
            'optimal_position_percentage': optimal_position_percentage,
            'recommended_position_percentage': final_position_percentage,
            'max_position_value': final_position_percentage * portfolio_value,
            'risk_amount': risk_amount,
            'rationale': self._explain_position_sizing(final_position_percentage, risk_adjusted_kelly)
        }

        return sizing

    def _calculate_risk_metrics(
        self,
        portfolio_data: Dict[str, Any],
        market_conditions: Dict[str, Any]
    ) -> Dict[str, float]:
        """Calculate comprehensive risk metrics."""
        positions = portfolio_data.get('positions', [])
        portfolio_value = portfolio_data.get('total_value', 0)

        # Basic metrics
        total_exposure = sum(abs(pos.get('value', 0)) for pos in positions)
        exposure_ratio = total_exposure / portfolio_value if portfolio_value > 0 else 0

        # Calculate portfolio VaR
        portfolio_var = self._calculate_portfolio_var(positions, market_conditions)

        # Calculate diversification metrics
        concentration = self._calculate_concentration_risk(positions, portfolio_value)

        # Calculate liquidity risk
        liquidity_score = self._assess_portfolio_liquidity(positions)

        # Calculate stress test results
        stress_loss = self._calculate_stress_loss(positions, market_conditions)

        metrics = {
            'exposure_ratio': exposure_ratio,
            'portfolio_var_95': portfolio_var,
            'concentration_index': concentration,
            'liquidity_score': liquidity_score,
            'stress_test_loss': stress_loss,
            'position_count': len(positions),
            'largest_position_ratio': max(
                (pos.get('value', 0) / portfolio_value for pos in positions),
                default=0
            )
        }

        return metrics

    def _determine_risk_level(self, metrics: Dict[str, float]) -> RiskLevel:
        """Determine overall risk level from metrics."""
        risk_score = 0

        # Exposure risk
        if metrics['exposure_ratio'] > 0.3:
            risk_score += 3
        elif metrics['exposure_ratio'] > 0.2:
            risk_score += 2
        elif metrics['exposure_ratio'] > 0.1:
            risk_score += 1

        # VaR risk
        if metrics['portfolio_var_95'] > 0.05:
            risk_score += 3
        elif metrics['portfolio_var_95'] > 0.03:
            risk_score += 2
        elif metrics['portfolio_var_95'] > 0.02:
            risk_score += 1

        # Concentration risk
        if metrics['concentration_index'] > 0.7:
            risk_score += 2
        elif metrics['concentration_index'] > 0.5:
            risk_score += 1

        # Stress test risk
        if metrics['stress_test_loss'] > 0.1:
            risk_score += 3
        elif metrics['stress_test_loss'] > 0.05:
            risk_score += 2

        # Convert score to risk level
        if risk_score >= 8:
            return RiskLevel.CRITICAL
        elif risk_score >= 5:
            return RiskLevel.HIGH
        elif risk_score >= 3:
            return RiskLevel.MEDIUM
        else:
            return RiskLevel.LOW

    def _identify_risk_factors(
        self,
        metrics: Dict[str, float],
        portfolio_data: Dict[str, Any]
    ) -> List[str]:
        """Identify key risk factors."""
        factors = []

        if metrics['exposure_ratio'] > 0.25:
            factors.append("High portfolio exposure")

        if metrics['portfolio_var_95'] > 0.03:
            factors.append("Elevated value at risk")

        if metrics['concentration_index'] > 0.6:
            factors.append("Portfolio concentration risk")

        if metrics['liquidity_score'] < 0.5:
            factors.append("Liquidity concerns")

        if metrics['stress_test_loss'] > 0.05:
            factors.append("Vulnerable to market stress")

        if metrics['position_count'] > 10:
            factors.append("Over diversification complexity")

        return factors or ["No significant risk factors identified"]

    def _identify_mitigating_factors(
        self,
        metrics: Dict[str, float],
        portfolio_data: Dict[str, Any]
    ) -> List[str]:
        """Identify risk mitigating factors."""
        factors = []

        if metrics['exposure_ratio'] < 0.15:
            factors.append("Conservative exposure levels")

        if metrics['portfolio_var_95'] < 0.02:
            factors.append("Strong risk controls")

        if metrics['concentration_index'] < 0.4:
            factors.append("Good diversification")

        if metrics['liquidity_score'] > 0.7:
            factors.append("Strong liquidity position")

        if metrics['stress_test_loss'] < 0.03:
            factors.append("Resilient to market stress")

        return factors or ["Standard risk management practices"]

    def _generate_risk_recommendations(
        self,
        risk_level: RiskLevel,
        metrics: Dict[str, float],
        portfolio_data: Dict[str, Any]
    ) -> List[str]:
        """Generate risk management recommendations."""
        recommendations = []

        if risk_level in [RiskLevel.HIGH, RiskLevel.CRITICAL]:
            recommendations.append("Immediate risk reduction required")
            recommendations.append("Consider reducing position sizes")
            recommendations.append("Implement stricter stop losses")

        if metrics['exposure_ratio'] > 0.25:
            recommendations.append("Reduce portfolio exposure to below 25%")

        if metrics['concentration_index'] > 0.6:
            recommendations.append("Diversify portfolio to reduce concentration")

        if metrics['portfolio_var_95'] > 0.03:
            recommendations.append("Adjust position sizing to reduce VaR")

        if risk_level == RiskLevel.LOW:
            recommendations.append("Risk levels are well managed")
            recommendations.append("Continue monitoring and maintaining current practices")

        return recommendations

    def _calculate_assessment_confidence(self, metrics: Dict[str, float]) -> float:
        """Calculate confidence in risk assessment."""
        # Higher confidence when metrics are consistent and data quality is good
        metric_consistency = 1.0 - abs(metrics['exposure_ratio'] - 0.2) / 0.3  # Closer to 20% is better
        data_completeness = sum(1 for v in metrics.values() if v is not None) / len(metrics)

        confidence = (metric_consistency + data_completeness) / 2
        return round(confidence, 2)

    # Helper methods for position risk assessment
    def _calculate_position_var(
        self,
        symbol: str,
        position_data: Dict[str, Any],
        market_data: Dict[str, Any]
    ) -> float:
        """Calculate Value at Risk for position."""
        # Simplified VaR calculation
        position_value = position_data.get('value', 0)
        volatility = market_data.get('volatility', 0.02)
        confidence_factor = 1.645  # 95% confidence for normal distribution

        var = position_value * volatility * confidence_factor
        return abs(var)

    def _assess_position_risk_level(
        self,
        position_data: Dict[str, Any],
        market_data: Dict[str, Any]
    ) -> RiskLevel:
        """Assess risk level for individual position."""
        position_value = position_data.get('value', 0)
        unrealized_pnl = position_data.get('unrealized_pnl', 0)
        volatility = market_data.get('volatility', 0.02)

        # Risk scoring
        risk_score = 0

        # Size risk
        if position_value > 10000:
            risk_score += 2

        # P&L risk
        if unrealized_pnl < -1000:
            risk_score += 2
        elif unrealized_pnl < -500:
            risk_score += 1

        # Volatility risk
        if volatility > 0.05:
            risk_score += 2
        elif volatility > 0.03:
            risk_score += 1

        if risk_score >= 4:
            return RiskLevel.HIGH
        elif risk_score >= 2:
            return RiskLevel.MEDIUM
        else:
            return RiskLevel.LOW

    def _calculate_correlation_risk(self, symbol: str, portfolio_data: Dict[str, Any]) -> float:
        """Calculate correlation risk with portfolio."""
        # Simplified correlation calculation
        # In real implementation, would use historical correlation data
        return 0.3  # 30% correlation

    def _assess_liquidity_risk(self, symbol: str, market_data: Dict[str, Any]) -> str:
        """Assess liquidity risk for position."""
        volume_24h = market_data.get('volume_24h', 0)
        market_cap = market_data.get('market_cap', 0)

        if volume_24h > 1000000:  # High volume
            return 'low'
        elif volume_24h > 100000:  # Medium volume
            return 'medium'
        else:
            return 'high'

    def _calculate_max_loss_potential(
        self,
        position_data: Dict[str, Any],
        market_data: Dict[str, Any]
    ) -> float:
        """Calculate maximum potential loss."""
        position_value = position_data.get('value', 0)
        stop_loss_pct = position_data.get('stop_loss_percentage', 0.05)

        return position_value * stop_loss_pct

    def _generate_position_recommendations(
        self,
        symbol: str,
        risk_level: RiskLevel,
        position_data: Dict[str, Any],
        market_data: Dict[str, Any]
    ) -> List[str]:
        """Generate recommendations for position risk management."""
        recommendations = []

        if risk_level == RiskLevel.HIGH:
            recommendations.append("Consider reducing position size")
            recommendations.append("Tighten stop loss")
            recommendations.append("Monitor closely for exit signals")

        elif risk_level == RiskLevel.MEDIUM:
            recommendations.append("Monitor position closely")
            recommendations.append("Consider partial profit taking")

        else:  # LOW
            recommendations.append("Position risk is well managed")
            recommendations.append("Continue monitoring market conditions")

        return recommendations

    def _calculate_portfolio_var(
        self,
        positions: List[Dict[str, Any]],
        market_conditions: Dict[str, Any]
    ) -> float:
        """Calculate portfolio Value at Risk."""
        # Simplified portfolio VaR calculation
        total_value = sum(abs(pos.get('value', 0)) for pos in positions)
        avg_volatility = market_conditions.get('avg_volatility', 0.02)

        portfolio_var = total_value * avg_volatility * 1.645  # 95% confidence
        return portfolio_var / total_value if total_value > 0 else 0

    def _calculate_concentration_risk(
        self,
        positions: List[Dict[str, Any]],
        portfolio_value: float
    ) -> float:
        """Calculate portfolio concentration risk."""
        if not positions or portfolio_value == 0:
            return 0

        # Calculate Herfindahl-Hirschman Index for concentration
        position_weights = [abs(pos.get('value', 0)) / portfolio_value for pos in positions]
        hhi = sum(weight ** 2 for weight in position_weights)

        return hhi

    def _assess_portfolio_liquidity(self, positions: List[Dict[str, Any]]) -> float:
        """Assess overall portfolio liquidity."""
        if not positions:
            return 1.0

        # Average liquidity score across positions
        liquidity_scores = []
        for pos in positions:
            # Mock liquidity scoring based on market data
            volume = pos.get('volume_24h', 100000)
            if volume > 1000000:
                score = 0.9
            elif volume > 100000:
                score = 0.7
            else:
                score = 0.4
            liquidity_scores.append(score)

        return sum(liquidity_scores) / len(liquidity_scores)

    def _calculate_stress_loss(
        self,
        positions: List[Dict[str, Any]],
        market_conditions: Dict[str, Any]
    ) -> float:
        """Calculate potential loss under stress scenarios."""
        # Simulate 20% market downturn
        stress_factor = 0.2
        total_loss = 0

        for pos in positions:
            position_value = pos.get('value', 0)
            # Assume long positions lose value in downturn
            if position_value > 0:
                loss = position_value * stress_factor
                total_loss += loss

        portfolio_value = sum(abs(pos.get('value', 0)) for pos in positions)
        return total_loss / portfolio_value if portfolio_value > 0 else 0

    def _determine_alert_severity(self, current_value: float, limit: float) -> str:
        """Determine alert severity for limit breaches."""
        breach_ratio = (current_value - limit) / limit

        if breach_ratio > 0.5:
            return 'critical'
        elif breach_ratio > 0.25:
            return 'high'
        elif breach_ratio > 0.1:
            return 'medium'
        else:
            return 'low'

    def _generate_limit_breach_recommendation(self, metric_name: str) -> str:
        """Generate recommendation for limit breach."""
        recommendations = {
            'max_drawdown': 'Reduce position sizes and implement stricter risk controls',
            'exposure_ratio': 'Reduce portfolio exposure by closing positions',
            'daily_loss': 'Activate circuit breakers and review trading strategy',
            'position_size': 'Reduce individual position sizes',
            'correlation_risk': 'Diversify portfolio across uncorrelated assets'
        }

        return recommendations.get(metric_name, 'Review and adjust risk parameters')

    def _explain_position_sizing(
        self,
        final_percentage: float,
        kelly_percentage: float
    ) -> str:
        """Explain position sizing rationale."""
        if final_percentage >= kelly_percentage * 0.8:
            return f"Position size optimized using Kelly Criterion ({kelly_percentage:.1%})"
        else:
            return f"Conservative sizing applied to manage risk (Kelly: {kelly_percentage:.1%})"
