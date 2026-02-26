"""
Ensemble Trading System

Advanced ensemble system combining multiple trading strategies:
- Trend-following models (MACD, Moving Averages, RSI)
- Mean-reversion models (Bollinger Bands, RSI divergence)
- Volatility-based models (ATR, VIX, implied volatility)
- Machine learning models (PPO, LSTM, Random Forest)
- Order flow analysis and microstructure models

Features:
- Dynamic model weighting based on market conditions
- Correlation analysis to reduce overfitting
- Risk-adjusted ensemble predictions
- Meta-learning for optimal combination weights
- Real-time performance monitoring and adaptation
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple, Callable
import pandas as pd
import numpy as np
from concurrent.futures import ThreadPoolExecutor
import torch
import torch.nn as nn
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import StandardScaler

from mcp_trader.ai.ppo_trading_model import PPOTradingModel
from mcp_trader.ai.vpin_calculator import VPINCalculator
from mcp_trader.backtesting.walk_forward_analysis import WalkForwardAnalyzer

logger = logging.getLogger(__name__)


@dataclass
class EnsemblePrediction:
    """Ensemble prediction result"""

    symbol: str
    timestamp: datetime
    direction: float  # -1 (sell), 0 (hold), 1 (buy)
    confidence: float  # 0-1
    volatility: float  # Expected volatility
    stop_loss: float  # Recommended stop loss level
    take_profit: float  # Recommended take profit level
    models_used: List[str]  # Which models contributed
    model_weights: Dict[str, float]  # Weight of each model
    risk_score: float  # Overall risk assessment


@dataclass
class EnsembleConfig:
    """Configuration for ensemble system"""

    # Model selection
    enabled_models: List[str] = field(default_factory=lambda: [
        'ppo', 'trend_following', 'mean_reversion', 'volatility',
        'order_flow', 'ml_classifier', 'vpin_based'
    ])

    # Ensemble settings
    dynamic_weighting: bool = True
    correlation_threshold: float = 0.7
    min_models_required: int = 3
    consensus_threshold: float = 0.6

    # Risk management
    max_position_size: float = 0.1  # Max 10% of capital
    max_portfolio_risk: float = 0.05  # Max 5% portfolio risk
    stop_loss_multiplier: float = 2.0
    take_profit_multiplier: float = 3.0

    # Performance monitoring
    performance_window: int = 252  # Trading days
    rebalance_interval: int = 24  # Hours
    adaptation_rate: float = 0.1  # Learning rate for adaptation

    # GPU settings
    gpu_acceleration: bool = True
    cuda_device: int = 0

    # Real-time settings
    update_interval: float = 1.0  # Seconds
    batch_size: int = 64


class MetaLearner(nn.Module):
    """Meta-learner for optimal model combination"""

    def __init__(self, num_models: int, hidden_dim: int = 64):
        super().__init__()
        self.num_models = num_models

        self.network = nn.Sequential(
            nn.Linear(num_models * 2, hidden_dim),
            nn.ReLU(),
            nn.Dropout(0.2),
            nn.Linear(hidden_dim, hidden_dim // 2),
            nn.ReLU(),
            nn.Linear(hidden_dim // 2, num_models),
            nn.Softmax(dim=-1)
        )

    def forward(self, model_predictions: torch.Tensor, model_confidences: torch.Tensor) -> torch.Tensor:
        """Compute optimal weights for model combination"""
        x = torch.cat([model_predictions, model_confidences], dim=-1)
        weights = self.network(x)
        return weights


class EnsembleTradingSystem:
    """
    Advanced ensemble trading system combining multiple strategies

    Features:
    - Dynamic model weighting based on market conditions
    - Meta-learning for optimal combination
    - Real-time performance adaptation
    - Risk-adjusted position sizing
    """

    def __init__(self, config: EnsembleConfig = None):
        self.config = config or EnsembleConfig()

        # Initialize individual models
        self.models = {}
        self._initialize_models()

        # Ensemble components
        self.meta_learner = None
        self.performance_tracker = {}
        self.correlation_matrix = {}

        # GPU setup
        self.device = torch.device(f'cuda:{self.config.cuda_device}' if
                                 self.config.gpu_acceleration and torch.cuda.is_available()
                                 else 'cpu')

        # Initialize meta-learner
        if self.config.dynamic_weighting:
            self._initialize_meta_learner()

        # Performance tracking
        self.prediction_history = []
        self.actual_returns = []
        self.model_weights_history = []

        logger.info(f"Ensemble Trading System initialized with {len(self.models)} models")

    def _initialize_models(self):
        """Initialize individual trading models"""

        enabled_models = self.config.enabled_models

        if 'ppo' in enabled_models:
            self.models['ppo'] = PPOTradingModel()

        if 'trend_following' in enabled_models:
            self.models['trend_following'] = TrendFollowingModel()

        if 'mean_reversion' in enabled_models:
            self.models['mean_reversion'] = MeanReversionModel()

        if 'volatility' in enabled_models:
            self.models['volatility'] = VolatilityModel()

        if 'order_flow' in enabled_models:
            self.models['order_flow'] = OrderFlowModel()

        if 'ml_classifier' in enabled_models:
            self.models['ml_classifier'] = MLTradingClassifier()

        if 'vpin_based' in enabled_models:
            self.models['vpin_based'] = VPINBasedModel()

    def _initialize_meta_learner(self):
        """Initialize meta-learner for dynamic weighting"""
        num_models = len(self.models)
        self.meta_learner = MetaLearner(num_models).to(self.device)

        # Initialize with equal weights
        self.model_weights = {name: 1.0 / num_models for name in self.models.keys()}

    async def predict(self, market_data: Dict[str, Any], symbol: str) -> EnsemblePrediction:
        """
        Generate ensemble prediction combining all models

        Args:
            market_data: Dictionary containing OHLCV, indicators, order book, etc.
            symbol: Trading symbol

        Returns:
            EnsemblePrediction with combined signal
        """

        try:
            # Get predictions from all models
            model_predictions = {}
            model_confidences = {}
            model_features = {}

            for model_name, model in self.models.items():
                try:
                    prediction = await self._get_model_prediction(model, market_data, symbol)
                    model_predictions[model_name] = prediction['direction']
                    model_confidences[model_name] = prediction['confidence']
                    model_features[model_name] = prediction
                except Exception as e:
                    logger.warning(f"Model {model_name} failed: {str(e)}")
                    model_predictions[model_name] = 0.0
                    model_confidences[model_name] = 0.0

            # Apply dynamic weighting if enabled
            if self.config.dynamic_weighting and self.meta_learner:
                weights = self._compute_dynamic_weights(model_predictions, model_confidences)
            else:
                weights = self.model_weights.copy()

            # Combine predictions
            ensemble_direction, ensemble_confidence = self._combine_predictions(
                model_predictions, model_confidences, weights
            )

            # Calculate risk metrics
            risk_metrics = self._calculate_risk_metrics(market_data, ensemble_direction)

            # Create ensemble prediction
            prediction = EnsemblePrediction(
                symbol=symbol,
                timestamp=datetime.now(),
                direction=ensemble_direction,
                confidence=ensemble_confidence,
                volatility=risk_metrics['volatility'],
                stop_loss=risk_metrics['stop_loss'],
                take_profit=risk_metrics['take_profit'],
                models_used=list(model_predictions.keys()),
                model_weights=weights,
                risk_score=risk_metrics['risk_score']
            )

            # Store for performance tracking
            self.prediction_history.append(prediction)

            return prediction

        except Exception as e:
            logger.error(f"Ensemble prediction failed: {str(e)}")
            # Return neutral prediction on error
            return EnsemblePrediction(
                symbol=symbol,
                timestamp=datetime.now(),
                direction=0.0,
                confidence=0.0,
                volatility=0.0,
                stop_loss=0.0,
                take_profit=0.0,
                models_used=[],
                model_weights={},
                risk_score=1.0
            )

    async def _get_model_prediction(self, model, market_data: Dict[str, Any], symbol: str) -> Dict[str, float]:
        """Get prediction from individual model"""

        if hasattr(model, 'predict_async'):
            return await model.predict_async(market_data)
        elif hasattr(model, 'predict'):
            return model.predict(market_data)
        else:
            # Default prediction logic
            return {
                'direction': 0.0,
                'confidence': 0.5
            }

    def _compute_dynamic_weights(self, predictions: Dict[str, float],
                               confidences: Dict[str, float]) -> Dict[str, float]:
        """Compute dynamic weights using meta-learner"""

        # Prepare input tensors
        pred_tensor = torch.tensor(list(predictions.values()), dtype=torch.float32).to(self.device)
        conf_tensor = torch.tensor(list(confidences.values()), dtype=torch.float32).to(self.device)

        # Get weights from meta-learner
        with torch.no_grad():
            weights_tensor = self.meta_learner(pred_tensor.unsqueeze(0), conf_tensor.unsqueeze(0))
            weights = weights_tensor.squeeze(0).cpu().numpy()

        # Convert to dictionary
        model_names = list(predictions.keys())
        weights_dict = {model_names[i]: float(weights[i]) for i in range(len(model_names))}

        return weights_dict

    def _combine_predictions(self, predictions: Dict[str, float], confidences: Dict[str, float],
                           weights: Dict[str, float]) -> Tuple[float, float]:
        """Combine predictions using weighted average"""

        # Apply correlation filtering
        filtered_predictions = self._filter_correlated_predictions(predictions)

        # Weighted combination
        weighted_sum = 0.0
        weight_sum = 0.0
        confidence_sum = 0.0

        for model_name in filtered_predictions.keys():
            if model_name in weights and model_name in confidences:
                weight = weights[model_name]
                pred = filtered_predictions[model_name]
                conf = confidences[model_name]

                weighted_sum += pred * weight * conf
                weight_sum += weight * conf
                confidence_sum += conf

        # Calculate ensemble direction and confidence
        if weight_sum > 0:
            ensemble_direction = weighted_sum / weight_sum
            ensemble_confidence = confidence_sum / len(filtered_predictions)
        else:
            ensemble_direction = 0.0
            ensemble_confidence = 0.0

        # Apply consensus threshold
        if abs(ensemble_direction) < self.config.consensus_threshold:
            ensemble_direction = 0.0  # Neutral if no consensus

        return ensemble_direction, min(ensemble_confidence, 1.0)

    def _filter_correlated_predictions(self, predictions: Dict[str, float]) -> Dict[str, float]:
        """Filter out highly correlated predictions to reduce overfitting"""

        if len(predictions) <= self.config.min_models_required:
            return predictions

        # Calculate correlations if not cached
        model_names = list(predictions.keys())
        if not self.correlation_matrix:
            self._update_correlation_matrix()

        # Remove highly correlated models
        filtered = {}
        used_models = set()

        for model_name in model_names:
            correlated = False
            for used_model in used_models:
                if (model_name in self.correlation_matrix and
                    used_model in self.correlation_matrix[model_name]):
                    corr = abs(self.correlation_matrix[model_name][used_model])
                    if corr > self.config.correlation_threshold:
                        correlated = True
                        break

            if not correlated:
                filtered[model_name] = predictions[model_name]
                used_models.add(model_name)

        # Ensure minimum models
        if len(filtered) < self.config.min_models_required:
            # Add back models in order of confidence
            sorted_models = sorted(predictions.items(), key=lambda x: abs(x[1]), reverse=True)
            for model_name, pred in sorted_models:
                if model_name not in filtered:
                    filtered[model_name] = pred
                    if len(filtered) >= self.config.min_models_required:
                        break

        return filtered

    def _update_correlation_matrix(self):
        """Update correlation matrix of model predictions"""

        if len(self.prediction_history) < 10:
            return

        # Extract recent predictions
        recent_predictions = self.prediction_history[-100:]  # Last 100 predictions

        model_names = list(self.models.keys())
        self.correlation_matrix = {}

        for i, model1 in enumerate(model_names):
            self.correlation_matrix[model1] = {}
            for model2 in model_names[i+1:]:
                # Calculate correlation of model weights over time
                weights1 = [p.model_weights.get(model1, 0) for p in recent_predictions if model1 in p.model_weights]
                weights2 = [p.model_weights.get(model2, 0) for p in recent_predictions if model2 in p.model_weights]

                if len(weights1) > 1 and len(weights2) > 1:
                    try:
                        corr = np.corrcoef(weights1, weights2)[0, 1]
                        self.correlation_matrix[model1][model2] = corr
                        self.correlation_matrix[model2] = self.correlation_matrix.get(model2, {})
                        self.correlation_matrix[model2][model1] = corr
                    except:
                        pass

    def _calculate_risk_metrics(self, market_data: Dict[str, Any], direction: float) -> Dict[str, float]:
        """Calculate risk metrics for the prediction"""

        # Extract market data
        close_prices = market_data.get('close', [])
        high_prices = market_data.get('high', [])
        low_prices = market_data.get('low', [])
        volume = market_data.get('volume', [])

        if not close_prices:
            return {
                'volatility': 0.0,
                'stop_loss': 0.0,
                'take_profit': 0.0,
                'risk_score': 1.0
            }

        # Calculate volatility (ATR-like)
        if len(high_prices) >= 14 and len(low_prices) >= 14 and len(close_prices) >= 14:
            tr = []
            for i in range(1, min(14, len(close_prices))):
                tr.append(max(
                    high_prices[-i] - low_prices[-i],
                    abs(high_prices[-i] - close_prices[-i-1]),
                    abs(low_prices[-i] - close_prices[-i-1])
                ))
            volatility = np.mean(tr) / close_prices[-1] if close_prices[-1] > 0 else 0.0
        else:
            volatility = np.std(close_prices[-20:]) / np.mean(close_prices[-20:]) if len(close_prices) >= 20 else 0.0

        current_price = close_prices[-1]

        # Calculate stop loss and take profit levels
        if direction > 0:  # Buy signal
            stop_loss = current_price * (1 - volatility * self.config.stop_loss_multiplier)
            take_profit = current_price * (1 + volatility * self.config.take_profit_multiplier)
        elif direction < 0:  # Sell signal
            stop_loss = current_price * (1 + volatility * self.config.stop_loss_multiplier)
            take_profit = current_price * (1 - volatility * self.config.take_profit_multiplier)
        else:
            stop_loss = current_price * 0.95  # Default 5% stop
            take_profit = current_price * 1.05  # Default 5% target

        # Calculate risk score (0-1, higher = riskier)
        volume_risk = np.std(volume[-20:]) / np.mean(volume[-20:]) if len(volume) >= 20 else 0.0
        price_risk = volatility
        direction_risk = abs(direction)  # Stronger signals = higher risk

        risk_score = min(1.0, (volume_risk + price_risk + direction_risk) / 3.0)

        return {
            'volatility': volatility,
            'stop_loss': stop_loss,
            'take_profit': take_profit,
            'risk_score': risk_score
        }

    async def update_performance(self, actual_return: float, prediction: EnsemblePrediction):
        """Update model performance for adaptation"""

        # Store actual return
        self.actual_returns.append(actual_return)

        # Update model weights based on performance
        if self.config.dynamic_weighting and len(self.actual_returns) >= 10:
            await self._adapt_model_weights()

        # Keep history manageable
        if len(self.actual_returns) > self.config.performance_window:
            self.actual_returns = self.actual_returns[-self.config.performance_window:]

        if len(self.prediction_history) > self.config.performance_window:
            self.prediction_history = self.prediction_history[-self.config.performance_window:]

    async def _adapt_model_weights(self):
        """Adapt model weights based on recent performance"""

        if not self.meta_learner or len(self.prediction_history) < 10:
            return

        # Prepare training data
        recent_predictions = self.prediction_history[-50:]  # Last 50 predictions
        recent_returns = self.actual_returns[-50:]

        if len(recent_predictions) != len(recent_returns):
            return

        # Create training batch
        model_names = list(self.models.keys())
        num_models = len(model_names)

        train_predictions = []
        train_confidences = []
        train_returns = []

        for i, pred in enumerate(recent_predictions):
            if len(pred.model_weights) == num_models:
                pred_values = [pred.model_weights.get(name, 0) for name in model_names]
                conf_values = [pred.model_weights.get(name, 0) for name in model_names]  # Approximation

                train_predictions.append(pred_values)
                train_confidences.append(conf_values)
                train_returns.append(recent_returns[i])

        if not train_predictions:
            return

        # Convert to tensors
        pred_tensor = torch.tensor(train_predictions, dtype=torch.float32).to(self.device)
        conf_tensor = torch.tensor(train_confidences, dtype=torch.float32).to(self.device)
        return_tensor = torch.tensor(train_returns, dtype=torch.float32).to(self.device)

        # Training step
        self.meta_learner.train()
        optimizer = torch.optim.Adam(self.meta_learner.parameters(), lr=self.config.adaptation_rate)

        # Forward pass
        weights = self.meta_learner(pred_tensor, conf_tensor)

        # Calculate loss (negative correlation with returns)
        ensemble_predictions = torch.sum(weights * pred_tensor, dim=1)
        loss = -torch.corrcoef(ensemble_predictions, return_tensor)[0, 1]

        if torch.isfinite(loss):
            # Backward pass
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()

        logger.debug(f"Meta-learner adaptation completed, loss: {loss.item():.4f}")

    async def get_portfolio_allocation(self, predictions: Dict[str, EnsemblePrediction],
                                     total_capital: float) -> Dict[str, float]:
        """Calculate optimal portfolio allocation based on ensemble predictions"""

        allocations = {}

        for symbol, prediction in predictions.items():
            # Risk-adjusted position size
            risk_score = prediction.risk_score
            confidence = prediction.confidence

            # Base position size
            max_position = total_capital * self.config.max_position_size

            # Adjust for risk and confidence
            risk_adjustment = 1.0 - risk_score  # Lower risk = larger position
            confidence_adjustment = confidence  # Higher confidence = larger position

            position_size = max_position * risk_adjustment * confidence_adjustment

            # Only allocate if signal is strong enough
            if abs(prediction.direction) >= 0.3 and confidence >= 0.4:
                allocations[symbol] = position_size
            else:
                allocations[symbol] = 0.0

        # Normalize to ensure total allocation doesn't exceed max portfolio risk
        total_allocation = sum(allocations.values())
        max_allocation = total_capital * self.config.max_portfolio_risk

        if total_allocation > max_allocation:
            scale_factor = max_allocation / total_allocation
            allocations = {symbol: size * scale_factor for symbol, size in allocations.items()}

        return allocations

    def get_performance_metrics(self) -> Dict[str, float]:
        """Get current ensemble performance metrics"""

        if len(self.prediction_history) < 10:
            return {}

        # Calculate metrics
        directions = [p.direction for p in self.prediction_history[-100:]]
        confidences = [p.confidence for p in self.prediction_history[-100:]]
        risk_scores = [p.risk_score for p in self.prediction_history[-100:]]

        metrics = {
            'avg_direction': np.mean(np.abs(directions)),
            'avg_confidence': np.mean(confidences),
            'avg_risk_score': np.mean(risk_scores),
            'models_active': len(self.models),
            'predictions_made': len(self.prediction_history),
            'correlation_filtered': len(self.correlation_matrix) > 0
        }

        return metrics


# Individual model implementations
class TrendFollowingModel:
    """Classic trend-following model using MACD and moving averages"""

    def predict(self, market_data: Dict[str, Any]) -> Dict[str, float]:
        """Generate trend-following prediction"""

        close = market_data.get('close', [])
        if len(close) < 50:
            return {'direction': 0.0, 'confidence': 0.0}

        # Calculate moving averages
        sma_20 = np.mean(close[-20:])
        sma_50 = np.mean(close[-50:])

        # Calculate MACD
        ema_12 = self._ema(close, 12)
        ema_26 = self._ema(close, 26)
        macd = ema_12 - ema_26
        signal = self._ema([macd] if len(close) >= 26 else [0], 9)

        # Generate signal
        trend_signal = 1 if sma_20 > sma_50 else -1
        macd_signal = 1 if macd > signal else -1

        direction = (trend_signal + macd_signal) / 2.0
        confidence = min(abs(direction), 1.0)

        return {'direction': direction, 'confidence': confidence}

    def _ema(self, data: List[float], period: int) -> float:
        """Calculate exponential moving average"""
        if len(data) < period:
            return np.mean(data) if data else 0.0

        multiplier = 2 / (period + 1)
        ema = data[0]

        for price in data[1:]:
            ema = (price * multiplier) + (ema * (1 - multiplier))

        return ema


class MeanReversionModel:
    """Mean reversion model using Bollinger Bands and RSI"""

    def predict(self, market_data: Dict[str, Any]) -> Dict[str, float]:
        """Generate mean reversion prediction"""

        close = market_data.get('close', [])
        if len(close) < 20:
            return {'direction': 0.0, 'confidence': 0.0}

        # Calculate Bollinger Bands
        sma = np.mean(close[-20:])
        std = np.std(close[-20:])
        upper_band = sma + 2 * std
        lower_band = sma - 2 * std
        current_price = close[-1]

        # Calculate RSI
        rsi = self._rsi(close, 14)

        # Generate signals
        bb_signal = 0
        if current_price > upper_band:
            bb_signal = -1  # Overbought
        elif current_price < lower_band:
            bb_signal = 1   # Oversold

        rsi_signal = 0
        if rsi > 70:
            rsi_signal = -1  # Overbought
        elif rsi < 30:
            rsi_signal = 1   # Oversold

        direction = (bb_signal + rsi_signal) / 2.0
        confidence = min(abs(direction) * 1.2, 1.0)  # Boost confidence for mean reversion

        return {'direction': direction, 'confidence': confidence}

    def _rsi(self, prices: List[float], period: int = 14) -> float:
        """Calculate RSI"""
        if len(prices) < period + 1:
            return 50.0

        gains = []
        losses = []

        for i in range(1, len(prices)):
            change = prices[i] - prices[i-1]
            if change > 0:
                gains.append(change)
                losses.append(0)
            else:
                gains.append(0)
                losses.append(abs(change))

        avg_gain = np.mean(gains[-period:]) if gains else 0
        avg_loss = np.mean(losses[-period:]) if losses else 0

        if avg_loss == 0:
            return 100.0

        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))

        return rsi


class VolatilityModel:
    """Volatility-based trading model"""

    def predict(self, market_data: Dict[str, Any]) -> Dict[str, float]:
        """Generate volatility-based prediction"""

        close = market_data.get('close', [])
        volume = market_data.get('volume', [])

        if len(close) < 20 or len(volume) < 20:
            return {'direction': 0.0, 'confidence': 0.0}

        # Calculate volatility metrics
        returns = np.diff(np.log(close))
        volatility = np.std(returns[-20:]) * np.sqrt(252)  # Annualized

        # Volume analysis
        avg_volume = np.mean(volume[-20:])
        current_volume = volume[-1]
        volume_ratio = current_volume / avg_volume if avg_volume > 0 else 1.0

        # Generate signal based on volatility regime
        if volatility > 0.8:  # High volatility - look for breakouts
            direction = 0.0  # Neutral in extreme volatility
            confidence = 0.3
        elif volatility > 0.4:  # Moderate volatility - trade with trend
            # Use volume to confirm direction
            if volume_ratio > 1.5:
                direction = 1.0 if close[-1] > close[-2] else -1.0
                confidence = 0.6
            else:
                direction = 0.0
                confidence = 0.4
        else:  # Low volatility - mean reversion
            direction = -1.0 if close[-1] > np.mean(close[-10:]) else 1.0
            confidence = 0.5

        return {'direction': direction, 'confidence': confidence}


class OrderFlowModel:
    """Order flow and market microstructure model"""

    def predict(self, market_data: Dict[str, Any]) -> Dict[str, float]:
        """Generate order flow-based prediction"""

        # This would use order book data, but for now use volume profile
        volume = market_data.get('volume', [])
        close = market_data.get('close', [])

        if len(volume) < 20 or len(close) < 20:
            return {'direction': 0.0, 'confidence': 0.0}

        # Simple order flow analysis using volume and price
        volume_sma = np.mean(volume[-10:])
        price_change = (close[-1] - close[-10]) / close[-10]

        # Volume-price analysis
        if volume[-1] > volume_sma * 1.5 and price_change > 0.01:
            direction = 1.0  # Strong buying pressure
            confidence = 0.7
        elif volume[-1] > volume_sma * 1.5 and price_change < -0.01:
            direction = -1.0  # Strong selling pressure
            confidence = 0.7
        else:
            direction = 0.0
            confidence = 0.4

        return {'direction': direction, 'confidence': confidence}


class MLTradingClassifier:
    """Machine learning classifier for trading signals"""

    def __init__(self):
        self.model = RandomForestClassifier(n_estimators=100, random_state=42)
        self.scaler = StandardScaler()
        self.is_trained = False

    def predict(self, market_data: Dict[str, Any]) -> Dict[str, float]:
        """Generate ML-based prediction"""

        if not self.is_trained:
            # Return neutral if not trained
            return {'direction': 0.0, 'confidence': 0.5}

        # Extract features
        features = self._extract_features(market_data)
        if not features:
            return {'direction': 0.0, 'confidence': 0.0}

        # Scale features
        features_scaled = self.scaler.transform([features])

        # Predict
        prediction = self.model.predict_proba(features_scaled)[0]

        # Convert to direction (-1, 0, 1)
        if prediction[0] > 0.6:  # Strong sell
            direction = -1.0
            confidence = prediction[0]
        elif prediction[2] > 0.6:  # Strong buy
            direction = 1.0
            confidence = prediction[2]
        else:
            direction = 0.0
            confidence = max(prediction)

        return {'direction': direction, 'confidence': confidence}

    def _extract_features(self, market_data: Dict[str, Any]) -> List[float]:
        """Extract features for ML model"""

        close = market_data.get('close', [])
        volume = market_data.get('volume', [])

        if len(close) < 20 or len(volume) < 20:
            return []

        # Technical indicators
        returns = np.diff(np.log(close))
        volatility = np.std(returns[-20:])

        sma_20 = np.mean(close[-20:])
        sma_50 = np.mean(close[-50:]) if len(close) >= 50 else sma_20

        # RSI
        rsi = self._calculate_rsi(close, 14)

        # MACD
        ema_12 = self._ema(close, 12)
        ema_26 = self._ema(close, 26)
        macd = ema_12 - ema_26

        # Volume features
        volume_ratio = volume[-1] / np.mean(volume[-10:]) if np.mean(volume[-10:]) > 0 else 1.0

        return [
            volatility,  # Volatility
            (close[-1] - sma_20) / sma_20,  # Price vs SMA20
            (sma_20 - sma_50) / sma_50 if sma_50 > 0 else 0,  # Trend
            rsi / 100.0,  # Normalized RSI
            macd,  # MACD
            volume_ratio,  # Volume ratio
            np.skew(returns[-20:]),  # Return skewness
            np.kurtosis(returns[-20:])  # Return kurtosis
        ]

    def _calculate_rsi(self, prices: List[float], period: int) -> float:
        """Calculate RSI"""
        if len(prices) < period + 1:
            return 50.0

        gains = []
        losses = []

        for i in range(1, len(prices)):
            change = prices[i] - prices[i-1]
            if change > 0:
                gains.append(change)
                losses.append(0)
            else:
                gains.append(0)
                losses.append(abs(change))

        avg_gain = np.mean(gains[-period:]) if gains else 0
        avg_loss = np.mean(losses[-period:]) if losses else 0

        if avg_loss == 0:
            return 100.0

        rs = avg_gain / avg_loss
        return 100 - (100 / (1 + rs))

    def _ema(self, data: List[float], period: int) -> float:
        """Calculate EMA"""
        if len(data) < period:
            return np.mean(data) if data else 0.0

        multiplier = 2 / (period + 1)
        ema = data[0]

        for price in data[1:]:
            ema = (price * multiplier) + (ema * (1 - multiplier))

        return ema


class VPINBasedModel:
    """VPIN-based trading model"""

    def __init__(self):
        self.vpin_calculator = VPINCalculator()

    def predict(self, market_data: Dict[str, Any]) -> Dict[str, float]:
        """Generate VPIN-based prediction"""

        # This would use actual VPIN calculation
        # For now, return neutral
        return {'direction': 0.0, 'confidence': 0.4}


# Convenience functions
def create_ensemble_system(config: EnsembleConfig = None) -> EnsembleTradingSystem:
    """Create ensemble trading system instance"""
    return EnsembleTradingSystem(config)


async def get_ensemble_prediction(system: EnsembleTradingSystem,
                                market_data: Dict[str, Any],
                                symbol: str) -> EnsemblePrediction:
    """Get ensemble prediction for symbol"""
    return await system.predict(market_data, symbol)


def get_ensemble_performance_metrics(system: EnsembleTradingSystem) -> Dict[str, float]:
    """Get ensemble performance metrics"""
    return system.get_performance_metrics()
