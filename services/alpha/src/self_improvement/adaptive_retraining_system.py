"""
Adaptive Retraining System

Self-improving AI system that monitors trading performance and automatically retrains models:
- Performance monitoring with drift detection
- Automated model retraining when performance degrades
- A/B testing framework for model improvements
- Feature importance analysis and selection
- Hyperparameter optimization
- Model versioning and rollback capabilities
- GPU-accelerated retraining for RTX 5070 Ti

Features:
- Real-time performance tracking
- Statistical significance testing
- Automatic model switching
- Data quality monitoring
- Computational resource management
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple, Callable
import pandas as pd
import numpy as np
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor
import torch
import torch.nn as nn
from sklearn.model_selection import TimeSeriesSplit
from sklearn.metrics import accuracy_score, precision_score, recall_score
import optuna
from scipy import stats
import json
import os
from pathlib import Path

from mcp_trader.ai.ppo_trading_model import PPOTradingModel
from mcp_trader.ai.ensemble_trading_system import EnsembleTradingSystem
from mcp_trader.backtesting.walk_forward_analysis import WalkForwardAnalyzer
from mcp_trader.backtesting.monte_carlo_simulation import MonteCarloSimulator

logger = logging.getLogger(__name__)


@dataclass
class PerformanceMetrics:
    """Performance metrics for model evaluation"""

    total_return: float = 0.0
    sharpe_ratio: float = 0.0
    max_drawdown: float = 0.0
    win_rate: float = 0.0
    profit_factor: float = 0.0
    calmar_ratio: float = 0.0
    sortino_ratio: float = 0.0
    alpha: float = 0.0
    beta: float = 0.0

    def to_dict(self) -> Dict[str, float]:
        return {
            'total_return': self.total_return,
            'sharpe_ratio': self.sharpe_ratio,
            'max_drawdown': self.max_drawdown,
            'win_rate': self.win_rate,
            'profit_factor': self.profit_factor,
            'calmar_ratio': self.calmar_ratio,
            'sortino_ratio': self.sortino_ratio,
            'alpha': self.alpha,
            'beta': self.beta
        }


@dataclass
class RetrainingConfig:
    """Configuration for adaptive retraining system"""

    # Performance monitoring
    performance_window: int = 252  # Trading days to evaluate
    evaluation_interval: int = 24  # Hours between evaluations
    min_performance_period: int = 30  # Minimum days before evaluation

    # Retraining triggers
    sharpe_threshold: float = 0.5  # Minimum Sharpe ratio
    max_drawdown_threshold: float = 0.15  # Maximum acceptable drawdown
    win_rate_threshold: float = 0.55  # Minimum win rate
    performance_decay_threshold: float = 0.1  # Performance decay trigger

    # Retraining settings
    retrain_batch_size: int = 1000
    validation_split: float = 0.2
    early_stopping_patience: int = 10
    max_training_time: int = 3600  # Seconds

    # A/B testing
    ab_test_duration: int = 168  # Hours (7 days)
    ab_test_confidence_level: float = 0.95
    min_sample_size: int = 100

    # Hyperparameter optimization
    optimization_trials: int = 50
    optimization_timeout: int = 1800  # Seconds

    # GPU settings
    gpu_acceleration: bool = True
    cuda_device: int = 0
    gpu_memory_limit: float = 0.9  # Use 90% of GPU memory

    # Model versioning
    max_model_versions: int = 10
    model_save_path: str = "models/saved"

    # Risk management
    max_retraining_frequency: int = 24  # Hours between retraining
    emergency_rollback_threshold: float = -0.05  # -5% return triggers rollback


@dataclass
class ModelVersion:
    """Model version information"""

    version_id: str
    timestamp: datetime
    performance_metrics: PerformanceMetrics
    hyperparameters: Dict[str, Any]
    training_data_hash: str
    model_path: str
    is_active: bool = False
    ab_test_results: Optional[Dict[str, Any]] = None


class PerformanceMonitor:
    """Monitors trading performance and detects degradation"""

    def __init__(self, config: RetrainingConfig):
        self.config = config
        self.performance_history = []
        self.prediction_history = []
        self.trade_history = []

    def add_trade_result(self, prediction: Any, actual_return: float, timestamp: datetime):
        """Add trade result for performance tracking"""

        self.trade_history.append({
            'timestamp': timestamp,
            'prediction': prediction,
            'actual_return': actual_return,
            'prediction_correct': (prediction > 0 and actual_return > 0) or
                                (prediction < 0 and actual_return < 0) or
                                (prediction == 0 and abs(actual_return) < 0.001)
        })

        # Keep history manageable
        if len(self.trade_history) > self.config.performance_window * 10:  # Assume ~10 trades per day
            self.trade_history = self.trade_history[-self.config.performance_window * 10:]

    def calculate_performance_metrics(self) -> PerformanceMetrics:
        """Calculate comprehensive performance metrics"""

        if len(self.trade_history) < self.config.min_performance_period:
            return PerformanceMetrics()

        # Extract returns
        returns = [trade['actual_return'] for trade in self.trade_history]

        # Basic metrics
        total_return = np.prod([1 + r for r in returns]) - 1

        # Sharpe ratio
        if len(returns) > 1:
            sharpe_ratio = np.mean(returns) / np.std(returns) * np.sqrt(252)  # Annualized
        else:
            sharpe_ratio = 0.0

        # Maximum drawdown
        cumulative = np.cumprod([1 + r for r in returns])
        running_max = np.maximum.accumulate(cumulative)
        drawdown = (cumulative - running_max) / running_max
        max_drawdown = abs(np.min(drawdown))

        # Win rate
        correct_predictions = sum(1 for trade in self.trade_history if trade['prediction_correct'])
        win_rate = correct_predictions / len(self.trade_history)

        # Profit factor
        winning_trades = [r for r in returns if r > 0]
        losing_trades = [r for r in returns if r < 0]

        if losing_trades:
            profit_factor = (sum(winning_trades) / abs(sum(losing_trades))) if winning_trades else 0.0
        else:
            profit_factor = float('inf') if winning_trades else 1.0

        # Calmar ratio
        calmar_ratio = total_return / max_drawdown if max_drawdown > 0 else 0.0

        # Sortino ratio (downside deviation)
        downside_returns = [r for r in returns if r < 0]
        if downside_returns:
            sortino_ratio = np.mean(returns) / np.std(downside_returns) * np.sqrt(252)
        else:
            sortino_ratio = float('inf')

        # Alpha and Beta (simplified - would need benchmark)
        alpha = total_return - 0.05  # Assuming 5% benchmark return
        beta = 1.0  # Simplified

        return PerformanceMetrics(
            total_return=total_return,
            sharpe_ratio=sharpe_ratio,
            max_drawdown=max_drawdown,
            win_rate=win_rate,
            profit_factor=profit_factor,
            calmar_ratio=calmar_ratio,
            sortino_ratio=sortino_ratio,
            alpha=alpha,
            beta=beta
        )

    def detect_performance_decay(self) -> bool:
        """Detect if performance has significantly decayed"""

        if len(self.trade_history) < self.config.min_performance_period * 2:
            return False

        # Split into recent and historical periods
        split_point = len(self.trade_history) // 2
        recent_trades = self.trade_history[split_point:]
        historical_trades = self.trade_history[:split_point]

        # Calculate metrics for both periods
        recent_returns = [t['actual_return'] for t in recent_trades]
        historical_returns = [t['actual_return'] for t in historical_trades]

        if not recent_returns or not historical_returns:
            return False

        # Statistical test for performance decay
        try:
            # T-test for difference in means
            t_stat, p_value = stats.ttest_ind(recent_returns, historical_returns)

            # Check if recent performance is significantly worse
            recent_mean = np.mean(recent_returns)
            historical_mean = np.mean(historical_returns)

            performance_decay = (historical_mean - recent_mean) / abs(historical_mean)

            return performance_decay > self.config.performance_decay_threshold

        except:
            # Fallback: simple comparison
            recent_avg = np.mean(recent_returns)
            historical_avg = np.mean(historical_returns)
            return recent_avg < historical_avg * (1 - self.config.performance_decay_threshold)

    def should_retrain(self, current_metrics: PerformanceMetrics) -> bool:
        """Determine if model should be retrained based on metrics"""

        # Check individual thresholds
        if current_metrics.sharpe_ratio < self.config.sharpe_threshold:
            logger.warning(f"Sharpe ratio {current_metrics.sharpe_ratio:.2f} below threshold {self.config.sharpe_threshold}")
            return True

        if current_metrics.max_drawdown > self.config.max_drawdown_threshold:
            logger.warning(f"Max drawdown {current_metrics.max_drawdown:.2f} above threshold {self.config.max_drawdown_threshold}")
            return True

        if current_metrics.win_rate < self.config.win_rate_threshold:
            logger.warning(f"Win rate {current_metrics.win_rate:.2f} below threshold {self.config.win_rate_threshold}")
            return True

        # Check performance decay
        if self.detect_performance_decay():
            logger.warning("Performance decay detected")
            return True

        return False


class ABTestingFramework:
    """A/B testing framework for model evaluation"""

    def __init__(self, config: RetrainingConfig):
        self.config = config
        self.test_results = {}

    def start_ab_test(self, model_a: Any, model_b: Any, test_id: str) -> str:
        """Start A/B test between two models"""

        test_data = {
            'test_id': test_id,
            'model_a': model_a,
            'model_b': model_b,
            'start_time': datetime.now(),
            'end_time': datetime.now() + timedelta(hours=self.config.ab_test_duration),
            'results_a': [],
            'results_b': [],
            'status': 'running'
        }

        self.test_results[test_id] = test_data
        logger.info(f"Started A/B test {test_id}")

        return test_id

    def add_test_result(self, test_id: str, model_version: str, prediction: Any,
                       actual_return: float):
        """Add result to A/B test"""

        if test_id not in self.test_results:
            return

        test_data = self.test_results[test_id]

        if model_version == 'A':
            test_data['results_a'].append(actual_return)
        elif model_version == 'B':
            test_data['results_b'].append(actual_return)

    def check_test_completion(self, test_id: str) -> Optional[Dict[str, Any]]:
        """Check if A/B test is complete and return winner"""

        if test_id not in self.test_results:
            return None

        test_data = self.test_results[test_id]

        # Check if test duration has passed
        if datetime.now() < test_data['end_time']:
            return None

        # Check minimum sample size
        if (len(test_data['results_a']) < self.config.min_sample_size or
            len(test_data['results_b']) < self.config.min_sample_size):
            return None

        # Statistical analysis
        results_a = np.array(test_data['results_a'])
        results_b = np.array(test_data['results_b'])

        # T-test
        try:
            t_stat, p_value = stats.ttest_ind(results_a, results_b)

            # Determine winner
            mean_a = np.mean(results_a)
            mean_b = np.mean(results_b)

            winner = 'A' if mean_a > mean_b else 'B'
            confidence = 1 - p_value

            if confidence >= self.config.ab_test_confidence_level:
                result = {
                    'winner': winner,
                    'confidence': confidence,
                    'mean_a': mean_a,
                    'mean_b': mean_b,
                    'p_value': p_value,
                    'sample_size_a': len(results_a),
                    'sample_size_b': len(results_b)
                }

                test_data['status'] = 'completed'
                test_data['final_result'] = result

                logger.info(f"A/B test {test_id} completed. Winner: {winner} (confidence: {confidence:.3f})")

                return result

        except Exception as e:
            logger.error(f"A/B test analysis failed: {str(e)}")

        return None


class HyperparameterOptimizer:
    """Hyperparameter optimization using Optuna"""

    def __init__(self, config: RetrainingConfig):
        self.config = config

    def optimize_ppo_hyperparameters(self, training_data: Any) -> Dict[str, Any]:
        """Optimize PPO hyperparameters"""

        def objective(trial):
            # Define hyperparameter search space
            params = {
                'learning_rate': trial.suggest_float('learning_rate', 1e-5, 1e-3, log=True),
                'batch_size': trial.suggest_categorical('batch_size', [32, 64, 128, 256]),
                'gamma': trial.suggest_float('gamma', 0.9, 0.999),
                'gae_lambda': trial.suggest_float('gae_lambda', 0.9, 0.99),
                'clip_range': trial.suggest_float('clip_range', 0.1, 0.4),
                'n_epochs': trial.suggest_int('n_epochs', 3, 10),
                'ent_coef': trial.suggest_float('ent_coef', 0.0, 0.1),
                'vf_coef': trial.suggest_float('vf_coef', 0.5, 1.0),
                'max_grad_norm': trial.suggest_float('max_grad_norm', 0.5, 1.0)
            }

            # Train model with these parameters
            try:
                # This would implement actual training and evaluation
                # For now, return a mock score
                score = self._evaluate_hyperparameters(params, training_data)
                return score

            except Exception as e:
                logger.error(f"Hyperparameter evaluation failed: {str(e)}")
                return -float('inf')

        # Run optimization
        study = optuna.create_study(direction='maximize')
        study.optimize(objective, n_trials=self.config.optimization_trials,
                      timeout=self.config.optimization_timeout)

        best_params = study.best_params
        logger.info(f"Hyperparameter optimization completed. Best params: {best_params}")

        return best_params

    def _evaluate_hyperparameters(self, params: Dict[str, Any], training_data: Any) -> float:
        """Evaluate hyperparameter combination"""

        # This would implement actual model training and cross-validation
        # For now, return a mock score based on parameter combinations

        # Favor certain parameter ranges
        score = 0.0

        if 1e-4 <= params['learning_rate'] <= 5e-4:
            score += 0.3

        if params['batch_size'] in [64, 128]:
            score += 0.2

        if 0.95 <= params['gamma'] <= 0.99:
            score += 0.2

        if 0.92 <= params['gae_lambda'] <= 0.97:
            score += 0.2

        # Add some randomness
        score += np.random.normal(0, 0.1)

        return max(0, min(1, score))


class AdaptiveRetrainingSystem:
    """
    Complete adaptive retraining system for trading models

    Features:
    - Continuous performance monitoring
    - Automatic retraining triggers
    - A/B testing for model improvements
    - Hyperparameter optimization
    - Model versioning and rollback
    - GPU-accelerated training
    """

    def __init__(self, config: RetrainingConfig = None):
        self.config = config or RetrainingConfig()

        # Core components
        self.performance_monitor = PerformanceMonitor(self.config)
        self.ab_testing = ABTestingFramework(self.config)
        self.hyper_optimizer = HyperparameterOptimizer(self.config)

        # Model management
        self.current_model = None
        self.model_versions = []
        self.active_ab_tests = {}

        # Training state
        self.last_retraining = None
        self.is_training = False

        # GPU setup
        self.device = torch.device(f'cuda:{self.config.cuda_device}' if
                                 self.config.gpu_acceleration and torch.cuda.is_available()
                                 else 'cpu')

        # Create model directory
        self.model_dir = Path(self.config.model_save_path)
        self.model_dir.mkdir(parents=True, exist_ok=True)

        logger.info("Adaptive Retraining System initialized")

    async def start_monitoring(self):
        """Start the adaptive retraining system"""

        logger.info("Starting adaptive retraining system...")

        # Start monitoring loop
        asyncio.create_task(self._monitoring_loop())

        # Start A/B test monitoring
        asyncio.create_task(self._ab_test_monitoring_loop())

    async def _monitoring_loop(self):
        """Main monitoring loop for performance evaluation"""

        while True:
            try:
                # Wait for evaluation interval
                await asyncio.sleep(self.config.evaluation_interval * 3600)  # Convert hours to seconds

                # Check if we have enough data
                if len(self.performance_monitor.trade_history) < self.config.min_performance_period:
                    continue

                # Calculate current performance
                current_metrics = self.performance_monitor.calculate_performance_metrics()

                logger.info(f"Performance metrics: Sharpe={current_metrics.sharpe_ratio:.2f}, "
                          f"Win Rate={current_metrics.win_rate:.2f}, "
                          f"Max DD={current_metrics.max_drawdown:.2f}")

                # Check if retraining is needed
                if self._should_retrain(current_metrics):
                    await self._trigger_retraining()

            except Exception as e:
                logger.error(f"Monitoring loop error: {str(e)}")
                await asyncio.sleep(60)  # Brief pause before retry

    async def _ab_test_monitoring_loop(self):
        """Monitor active A/B tests"""

        while True:
            try:
                await asyncio.sleep(3600)  # Check every hour

                # Check each active test
                completed_tests = []
                for test_id in list(self.active_ab_tests.keys()):
                    result = self.ab_testing.check_test_completion(test_id)
                    if result:
                        await self._handle_ab_test_completion(test_id, result)
                        completed_tests.append(test_id)

                # Remove completed tests
                for test_id in completed_tests:
                    del self.active_ab_tests[test_id]

            except Exception as e:
                logger.error(f"A/B test monitoring error: {str(e)}")

    def _should_retrain(self, metrics: PerformanceMetrics) -> bool:
        """Determine if retraining should be triggered"""

        # Check performance thresholds
        if self.performance_monitor.should_retrain(metrics):
            return True

        # Check retraining frequency
        if self.last_retraining:
            time_since_retraining = datetime.now() - self.last_retraining
            if time_since_retraining < timedelta(hours=self.config.max_retraining_frequency):
                return False

        # Check if currently training
        if self.is_training:
            return False

        return False

    async def _trigger_retraining(self):
        """Trigger model retraining process"""

        if self.is_training:
            logger.warning("Retraining already in progress")
            return

        self.is_training = True
        logger.info("Starting model retraining process...")

        try:
            # Collect fresh training data
            training_data = await self._collect_training_data()

            # Optimize hyperparameters
            best_params = self.hyper_optimizer.optimize_ppo_hyperparameters(training_data)

            # Train new model
            new_model = await self._train_new_model(best_params, training_data)

            # Create model version
            version = self._create_model_version(new_model, best_params, training_data)

            # Start A/B test
            if self.current_model:
                test_id = self.ab_testing.start_ab_test(self.current_model, new_model, version.version_id)
                self.active_ab_tests[test_id] = version
                logger.info(f"A/B test started for new model version {version.version_id}")
            else:
                # No current model, deploy immediately
                await self._deploy_model(version)

        except Exception as e:
            logger.error(f"Retraining failed: {str(e)}")

        finally:
            self.is_training = False
            self.last_retraining = datetime.now()

    async def _collect_training_data(self) -> Any:
        """Collect fresh training data"""

        # This would implement data collection from various sources
        # For now, return mock data
        logger.info("Collecting fresh training data...")
        await asyncio.sleep(1)  # Simulate data collection

        # Mock training data
        return {
            'observations': np.random.randn(10000, 50),
            'actions': np.random.randint(0, 3, 10000),
            'rewards': np.random.randn(10000),
            'dones': np.random.randint(0, 2, 10000)
        }

    async def _train_new_model(self, hyperparameters: Dict[str, Any], training_data: Any) -> PPOTradingModel:
        """Train new model with optimized hyperparameters"""

        logger.info("Training new model with optimized hyperparameters...")

        # Create new model instance
        model = PPOTradingModel()

        # Apply hyperparameters
        # This would configure the model with the optimized parameters
        model.set_hyperparameters(hyperparameters)

        # GPU acceleration
        if self.device.type == 'cuda':
            model.to_device(self.device)

        # Train model
        # This would implement actual training loop
        await model.train_async(training_data, max_time=self.config.max_training_time)

        logger.info("New model training completed")

        return model

    def _create_model_version(self, model: PPOTradingModel, hyperparameters: Dict[str, Any],
                            training_data: Any) -> ModelVersion:
        """Create new model version"""

        version_id = f"v_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        # Calculate training data hash
        data_hash = self._calculate_data_hash(training_data)

        # Save model
        model_path = self.model_dir / f"{version_id}.pt"
        model.save(str(model_path))

        # Evaluate performance (mock for now)
        performance_metrics = PerformanceMetrics(
            sharpe_ratio=1.2,
            win_rate=0.58,
            max_drawdown=0.08
        )

        version = ModelVersion(
            version_id=version_id,
            timestamp=datetime.now(),
            performance_metrics=performance_metrics,
            hyperparameters=hyperparameters,
            training_data_hash=data_hash,
            model_path=str(model_path)
        )

        self.model_versions.append(version)

        # Keep only recent versions
        if len(self.model_versions) > self.config.max_model_versions:
            old_version = self.model_versions.pop(0)
            if os.path.exists(old_version.model_path):
                os.remove(old_version.model_path)

        logger.info(f"Created model version {version_id}")

        return version

    async def _handle_ab_test_completion(self, test_id: str, result: Dict[str, Any]):
        """Handle A/B test completion"""

        version = self.active_ab_tests.get(test_id)
        if not version:
            return

        version.ab_test_results = result

        if result['winner'] == 'B':  # New model won
            logger.info(f"New model {version.version_id} won A/B test, deploying...")
            await self._deploy_model(version)
        else:
            logger.info(f"Current model retained, new model {version.version_id} not better")

    async def _deploy_model(self, version: ModelVersion):
        """Deploy new model version"""

        # Load model
        new_model = PPOTradingModel.load(version.model_path)

        # Update current model
        old_model = self.current_model
        self.current_model = new_model

        # Mark as active
        version.is_active = True

        # Mark old model as inactive
        if old_model:
            for v in self.model_versions:
                if v.is_active and v != version:
                    v.is_active = False

        logger.info(f"Deployed model version {version.version_id}")

        # Save deployment info
        self._save_deployment_info(version)

    def _calculate_data_hash(self, training_data: Any) -> str:
        """Calculate hash of training data for versioning"""

        # Simple hash based on data shape and basic statistics
        if isinstance(training_data, dict):
            data_str = json.dumps({
                k: str(v.shape) if hasattr(v, 'shape') else str(v)[:100]
                for k, v in training_data.items()
            }, sort_keys=True)
        else:
            data_str = str(training_data)[:1000]

        return hashlib.md5(data_str.encode()).hexdigest()[:16]

    def _save_deployment_info(self, version: ModelVersion):
        """Save deployment information"""

        deployment_info = {
            'version_id': version.version_id,
            'timestamp': version.timestamp.isoformat(),
            'performance_metrics': version.performance_metrics.to_dict(),
            'hyperparameters': version.hyperparameters,
            'ab_test_results': version.ab_test_results
        }

        deployment_file = self.model_dir / "deployments.jsonl"
        with open(deployment_file, 'a') as f:
            f.write(json.dumps(deployment_info) + '\n')

    async def emergency_rollback(self):
        """Emergency rollback to previous model version"""

        logger.warning("Emergency rollback triggered")

        # Find previous active model
        previous_version = None
        for version in reversed(self.model_versions):
            if not version.is_active:
                previous_version = version
                break

        if previous_version:
            await self._deploy_model(previous_version)
            logger.info(f"Rolled back to model version {previous_version.version_id}")
        else:
            logger.error("No previous model version available for rollback")

    async def check_ab_tests_and_promote(self):
        """Promotion gate: promote model only if it outperforms by threshold."""
        try:
            for test_id, version in list(self.active_ab_tests.items()):
                metrics = self.ab_testing.get_results(test_id)
                # Require statistically significant outperformance by at least 5% on Sharpe and win rate
                if metrics.get('is_significant') and \
                   metrics.get('sharpe_delta', 0) > 0.05 and \
                   metrics.get('win_rate_delta', 0) > 0.05:
                    await self._deploy_model(version)
                    self.ab_testing.stop_ab_test(test_id)
                    del self.active_ab_tests[test_id]
                    logger.info(f"Promoted model version {version.version_id} after successful A/B test")
        except Exception as e:
            logger.error(f"A/B promotion check failed: {e}")

    def add_trade_result(self, prediction: Any, actual_return: float):
        """Add trade result for performance monitoring"""

        self.performance_monitor.add_trade_result(prediction, actual_return, datetime.now())

    def get_system_status(self) -> Dict[str, Any]:
        """Get current system status"""

        current_metrics = self.performance_monitor.calculate_performance_metrics()

        return {
            'is_training': self.is_training,
            'active_ab_tests': len(self.active_ab_tests),
            'model_versions': len(self.model_versions),
            'current_performance': current_metrics.to_dict(),
            'last_retraining': self.last_retraining.isoformat() if self.last_retraining else None,
            'active_model_version': next((v.version_id for v in self.model_versions if v.is_active), None)
        }


# Convenience functions
def create_adaptive_retraining_system(config: RetrainingConfig = None) -> AdaptiveRetrainingSystem:
    """Create adaptive retraining system instance"""
    return AdaptiveRetrainingSystem(config)


async def start_adaptive_system(system: AdaptiveRetrainingSystem):
    """Start the adaptive retraining system"""
    await system.start_monitoring()


def get_system_status(system: AdaptiveRetrainingSystem) -> Dict[str, Any]:
    """Get adaptive system status"""
    return system.get_system_status()
