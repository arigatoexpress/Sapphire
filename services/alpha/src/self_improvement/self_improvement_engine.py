"""
Self-Improvement Engine for Autonomous Trading System

This module implements the self-learning capabilities of the trading system,
including weekly model retraining, genetic algorithm optimization, and
performance-based strategy selection.
"""

import asyncio
import json
import logging
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor
import pickle
import os

from sklearn.ensemble import RandomForestRegressor, GradientBoostingRegressor
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_squared_error, r2_score
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler
import xgboost as xgb
import lightgbm as lgb

from mcp_trader.risk.risk_manager import RiskManager
from mcp_trader.strategies.market_making import MarketMakingStrategy
from mcp_trader.strategies.funding_arbitrage import FundingArbitrageStrategy
from mcp_trader.strategies.dmark_strategy import DMarkStrategy
from mcp_trader.strategies.degen_trading import DegenTradingStrategy
from mcp_trader.strategies.latency_arbitrage import LatencyArbitrageStrategy

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class StrategyPerformance:
    """Track performance metrics for each strategy"""
    strategy_name: str
    total_trades: int
    winning_trades: int
    losing_trades: int
    total_pnl: float
    win_rate: float
    avg_win: float
    avg_loss: float
    profit_factor: float
    sharpe_ratio: float
    max_drawdown: float
    last_updated: datetime

@dataclass
class OptimizationResult:
    """Results from genetic algorithm optimization"""
    strategy_name: str
    best_parameters: Dict[str, Any]
    performance_improvement: float
    validation_score: float
    optimization_date: datetime

class GeneticOptimizer:
    """Genetic algorithm for optimizing strategy parameters"""
    
    def __init__(self, population_size: int = 50, generations: int = 100):
        self.population_size = population_size
        self.generations = generations
        self.mutation_rate = 0.1
        self.crossover_rate = 0.8
        self.elite_size = 5
        
    def optimize_strategy(self, strategy_class, parameter_ranges: Dict[str, Tuple[float, float]], 
                         historical_data: pd.DataFrame, performance_metric: str = 'sharpe_ratio') -> OptimizationResult:
        """Optimize strategy parameters using genetic algorithm"""
        
        logger.info(f"Starting genetic optimization for {strategy_class.__name__}")
        
        # Initialize population with random parameters
        population = self._initialize_population(parameter_ranges)
        best_individual = None
        best_score = float('-inf')
        
        for generation in range(self.generations):
            # Evaluate fitness for each individual
            fitness_scores = []
            for individual in population:
                try:
                    score = self._evaluate_individual(individual, strategy_class, historical_data, performance_metric)
                    fitness_scores.append(score)
                    
                    if score > best_score:
                        best_score = score
                        best_individual = individual.copy()
                        
                except Exception as e:
                    logger.warning(f"Error evaluating individual: {e}")
                    fitness_scores.append(float('-inf'))
            
            # Select parents for next generation
            parents = self._selection(population, fitness_scores)
            
            # Create new generation through crossover and mutation
            new_population = []
            
            # Keep elite individuals
            elite_indices = np.argsort(fitness_scores)[-self.elite_size:]
            for idx in elite_indices:
                new_population.append(population[idx].copy())
            
            # Generate offspring
            while len(new_population) < self.population_size:
                parent1, parent2 = np.random.choice(parents, 2, replace=False)
                
                if np.random.random() < self.crossover_rate:
                    child1, child2 = self._crossover(parent1, parent2)
                    new_population.extend([child1, child2])
                else:
                    new_population.extend([parent1.copy(), parent2.copy()])
            
            # Apply mutation
            for individual in new_population[self.elite_size:]:
                if np.random.random() < self.mutation_rate:
                    self._mutate(individual, parameter_ranges)
            
            population = new_population[:self.population_size]
            
            if generation % 10 == 0:
                logger.info(f"Generation {generation}: Best score = {best_score:.4f}")
        
        return OptimizationResult(
            strategy_name=strategy_class.__name__,
            best_parameters=best_individual,
            performance_improvement=best_score,
            validation_score=best_score,
            optimization_date=datetime.now()
        )
    
    def _initialize_population(self, parameter_ranges: Dict[str, Tuple[float, float]]) -> List[Dict[str, float]]:
        """Initialize population with random parameters"""
        population = []
        for _ in range(self.population_size):
            individual = {}
            for param, (min_val, max_val) in parameter_ranges.items():
                individual[param] = np.random.uniform(min_val, max_val)
            population.append(individual)
        return population
    
    def _evaluate_individual(self, individual: Dict[str, float], strategy_class, 
                           historical_data: pd.DataFrame, performance_metric: str) -> float:
        """Evaluate fitness of an individual parameter set"""
        try:
            # Create strategy instance with parameters
            strategy = strategy_class(**individual)
            
            # Run backtest simulation
            trades = self._simulate_strategy(strategy, historical_data)
            
            if not trades:
                return float('-inf')
            
            # Calculate performance metric
            if performance_metric == 'sharpe_ratio':
                returns = [trade['pnl'] for trade in trades]
                if len(returns) < 2:
                    return float('-inf')
                return np.mean(returns) / np.std(returns) if np.std(returns) > 0 else 0
            elif performance_metric == 'profit_factor':
                wins = [trade['pnl'] for trade in trades if trade['pnl'] > 0]
                losses = [abs(trade['pnl']) for trade in trades if trade['pnl'] < 0]
                return sum(wins) / sum(losses) if losses else float('inf')
            else:
                return sum(trade['pnl'] for trade in trades)
                
        except Exception as e:
            logger.warning(f"Error evaluating individual: {e}")
            return float('-inf')
    
    def _simulate_strategy(self, strategy, historical_data: pd.DataFrame) -> List[Dict[str, Any]]:
        """Simulate strategy execution on historical data"""
        trades = []
        position = 0
        entry_price = 0
        
        for i, row in historical_data.iterrows():
            # Get strategy signal
            signal = strategy.generate_signal(row)
            
            if signal == 1 and position <= 0:  # Buy signal
                if position < 0:  # Close short position
                    pnl = entry_price - row['close']
                    trades.append({'pnl': pnl, 'type': 'close_short'})
                
                position = 1
                entry_price = row['close']
                
            elif signal == -1 and position >= 0:  # Sell signal
                if position > 0:  # Close long position
                    pnl = row['close'] - entry_price
                    trades.append({'pnl': pnl, 'type': 'close_long'})
                
                position = -1
                entry_price = row['close']
        
        return trades
    
    def _selection(self, population: List[Dict[str, float]], fitness_scores: List[float]) -> List[Dict[str, float]]:
        """Tournament selection for parents"""
        parents = []
        for _ in range(len(population)):
            # Tournament selection
            tournament_size = 3
            tournament_indices = np.random.choice(len(population), tournament_size, replace=False)
            tournament_scores = [fitness_scores[i] for i in tournament_indices]
            winner_idx = tournament_indices[np.argmax(tournament_scores)]
            parents.append(population[winner_idx])
        return parents
    
    def _crossover(self, parent1: Dict[str, float], parent2: Dict[str, float]) -> Tuple[Dict[str, float], Dict[str, float]]:
        """Uniform crossover between two parents"""
        child1 = {}
        child2 = {}
        
        for param in parent1:
            if np.random.random() < 0.5:
                child1[param] = parent1[param]
                child2[param] = parent2[param]
            else:
                child1[param] = parent2[param]
                child2[param] = parent1[param]
        
        return child1, child2
    
    def _mutate(self, individual: Dict[str, float], parameter_ranges: Dict[str, Tuple[float, float]]):
        """Mutate individual parameters"""
        for param, (min_val, max_val) in parameter_ranges.items():
            if np.random.random() < 0.1:  # 10% chance to mutate each parameter
                # Gaussian mutation
                mutation = np.random.normal(0, (max_val - min_val) * 0.1)
                individual[param] = np.clip(individual[param] + mutation, min_val, max_val)

class ModelRetrainer:
    """Handles weekly model retraining and validation"""
    
    def __init__(self, models_dir: str = "models"):
        self.models_dir = models_dir
        os.makedirs(models_dir, exist_ok=True)
        
    async def retrain_models(self, historical_data: pd.DataFrame, 
                           performance_data: pd.DataFrame) -> Dict[str, Any]:
        """Retrain all AI models with recent data"""
        
        logger.info("Starting weekly model retraining")
        
        # Prepare training data
        X, y = self._prepare_training_data(historical_data, performance_data)
        
        if len(X) < 100:
            logger.warning("Insufficient data for retraining")
            return {}
        
        # Split data
        X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
        
        # Scale features
        scaler = StandardScaler()
        X_train_scaled = scaler.fit_transform(X_train)
        X_test_scaled = scaler.transform(X_test)
        
        # Train multiple models
        models = {
            'random_forest': RandomForestRegressor(n_estimators=100, random_state=42),
            'gradient_boosting': GradientBoostingRegressor(n_estimators=100, random_state=42),
            'xgboost': xgb.XGBRegressor(n_estimators=100, random_state=42),
            'lightgbm': lgb.LGBMRegressor(n_estimators=100, random_state=42),
            'linear_regression': LinearRegression()
        }
        
        results = {}
        
        for name, model in models.items():
            try:
                # Train model
                if name in ['xgboost', 'lightgbm']:
                    model.fit(X_train, y_train)
                    y_pred = model.predict(X_test)
                else:
                    model.fit(X_train_scaled, y_train)
                    y_pred = model.predict(X_test_scaled)
                
                # Evaluate performance
                mse = mean_squared_error(y_test, y_pred)
                r2 = r2_score(y_test, y_pred)
                
                results[name] = {
                    'model': model,
                    'mse': mse,
                    'r2': r2,
                    'scaler': scaler if name not in ['xgboost', 'lightgbm'] else None
                }
                
                # Save model
                model_path = os.path.join(self.models_dir, f"{name}_model.pkl")
                with open(model_path, 'wb') as f:
                    pickle.dump({
                        'model': model,
                        'scaler': scaler if name not in ['xgboost', 'lightgbm'] else None,
                        'feature_columns': X.columns.tolist(),
                        'training_date': datetime.now()
                    }, f)
                
                logger.info(f"Trained {name}: MSE={mse:.4f}, R2={r2:.4f}")
                
            except Exception as e:
                logger.error(f"Error training {name}: {e}")
        
        return results
    
    def _prepare_training_data(self, historical_data: pd.DataFrame, 
                             performance_data: pd.DataFrame) -> Tuple[pd.DataFrame, pd.Series]:
        """Prepare features and targets for model training"""
        
        # Create features from historical data
        features = []
        
        # Technical indicators
        features.append(historical_data['close'].pct_change().fillna(0))
        features.append(historical_data['volume'].pct_change().fillna(0))
        features.append(historical_data['close'].rolling(5).mean().pct_change().fillna(0))
        features.append(historical_data['close'].rolling(20).mean().pct_change().fillna(0))
        features.append(historical_data['close'].rolling(50).mean().pct_change().fillna(0))
        
        # Volatility features
        features.append(historical_data['close'].rolling(20).std().fillna(0))
        features.append(historical_data['high'].rolling(20).max() / historical_data['low'].rolling(20).min() - 1)
        
        # Volume features
        features.append(historical_data['volume'].rolling(20).mean().fillna(0))
        features.append(historical_data['volume'] / historical_data['volume'].rolling(20).mean())
        
        # Time features
        features.append(historical_data.index.hour)
        features.append(historical_data.index.dayofweek)
        
        # Combine features
        X = pd.concat(features, axis=1)
        X.columns = [f'feature_{i}' for i in range(len(features))]
        X = X.fillna(0)
        
        # Create targets from performance data
        y = performance_data['pnl'].fillna(0)
        
        # Align data
        common_index = X.index.intersection(y.index)
        X = X.loc[common_index]
        y = y.loc[common_index]
        
        return X, y

class SelfImprovementEngine:
    """Main self-improvement engine that orchestrates all learning components"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.genetic_optimizer = GeneticOptimizer()
        self.model_retrainer = ModelRetrainer()
        self.strategy_performance = {}
        self.optimization_results = {}
        
        # Strategy parameter ranges for optimization
        self.strategy_parameter_ranges = {
            'MarketMakingStrategy': {
                'spread_multiplier': (0.5, 2.0),
                'inventory_skew_threshold': (0.1, 0.5),
                'max_position_size': (0.01, 0.1)
            },
            'FundingArbitrageStrategy': {
                'funding_rate_threshold': (0.0001, 0.01),
                'position_size': (0.01, 0.1),
                'max_leverage': (1.0, 5.0)
            },
            'DMarkStrategy': {
                'dmark_threshold': (0.1, 0.9),
                'stop_loss_pct': (0.01, 0.05),
                'take_profit_pct': (0.01, 0.1)
            }
        }
        
    async def run_weekly_improvement_cycle(self, historical_data: pd.DataFrame, 
                                         performance_data: pd.DataFrame) -> Dict[str, Any]:
        """Run the complete weekly improvement cycle"""
        
        logger.info("Starting weekly self-improvement cycle")
        
        results = {
            'optimization_results': {},
            'model_retraining_results': {},
            'strategy_performance_updates': {},
            'timestamp': datetime.now()
        }
        
        try:
            # 1. Update strategy performance metrics
            await self._update_strategy_performance(performance_data)
            
            # 2. Optimize strategy parameters using genetic algorithm
            for strategy_name, parameter_ranges in self.strategy_parameter_ranges.items():
                try:
                    strategy_class = self._get_strategy_class(strategy_name)
                    if strategy_class:
                        optimization_result = self.genetic_optimizer.optimize_strategy(
                            strategy_class, parameter_ranges, historical_data
                        )
                        results['optimization_results'][strategy_name] = optimization_result
                        self.optimization_results[strategy_name] = optimization_result
                        
                except Exception as e:
                    logger.error(f"Error optimizing {strategy_name}: {e}")
            
            # 3. Retrain AI models
            model_results = await self.model_retrainer.retrain_models(historical_data, performance_data)
            results['model_retraining_results'] = model_results
            
            # 4. Update strategy weights based on performance
            await self._update_strategy_weights()
            
            # 5. Save improvement results
            await self._save_improvement_results(results)
            
            logger.info("Weekly improvement cycle completed successfully")
            
        except Exception as e:
            logger.error(f"Error in weekly improvement cycle: {e}")
            results['error'] = str(e)
        
        return results
    
    async def _update_strategy_performance(self, performance_data: pd.DataFrame):
        """Update performance metrics for each strategy"""
        
        for strategy_name in self.strategy_parameter_ranges.keys():
            strategy_data = performance_data[performance_data['strategy'] == strategy_name]
            
            if len(strategy_data) == 0:
                continue
            
            total_trades = len(strategy_data)
            winning_trades = len(strategy_data[strategy_data['pnl'] > 0])
            losing_trades = len(strategy_data[strategy_data['pnl'] < 0])
            total_pnl = strategy_data['pnl'].sum()
            win_rate = winning_trades / total_trades if total_trades > 0 else 0
            
            avg_win = strategy_data[strategy_data['pnl'] > 0]['pnl'].mean() if winning_trades > 0 else 0
            avg_loss = abs(strategy_data[strategy_data['pnl'] < 0]['pnl'].mean()) if losing_trades > 0 else 0
            profit_factor = avg_win / avg_loss if avg_loss > 0 else float('inf')
            
            # Calculate Sharpe ratio
            returns = strategy_data['pnl'].values
            sharpe_ratio = np.mean(returns) / np.std(returns) if np.std(returns) > 0 else 0
            
            # Calculate max drawdown
            cumulative_returns = np.cumsum(returns)
            running_max = np.maximum.accumulate(cumulative_returns)
            drawdown = cumulative_returns - running_max
            max_drawdown = abs(np.min(drawdown)) if len(drawdown) > 0 else 0
            
            self.strategy_performance[strategy_name] = StrategyPerformance(
                strategy_name=strategy_name,
                total_trades=total_trades,
                winning_trades=winning_trades,
                losing_trades=losing_trades,
                total_pnl=total_pnl,
                win_rate=win_rate,
                avg_win=avg_win,
                avg_loss=avg_loss,
                profit_factor=profit_factor,
                sharpe_ratio=sharpe_ratio,
                max_drawdown=max_drawdown,
                last_updated=datetime.now()
            )
    
    async def _update_strategy_weights(self):
        """Update strategy weights based on recent performance"""
        
        if not self.strategy_performance:
            return
        
        # Calculate weights based on Sharpe ratio and profit factor
        weights = {}
        total_score = 0
        
        for strategy_name, performance in self.strategy_performance.items():
            # Combined score: 70% Sharpe ratio, 30% profit factor
            score = 0.7 * performance.sharpe_ratio + 0.3 * min(performance.profit_factor, 5.0)
            weights[strategy_name] = max(score, 0.1)  # Minimum weight of 0.1
            total_score += weights[strategy_name]
        
        # Normalize weights
        if total_score > 0:
            for strategy_name in weights:
                weights[strategy_name] = weights[strategy_name] / total_score
        
        # Save updated weights
        weights_path = os.path.join(self.model_retrainer.models_dir, 'strategy_weights.json')
        with open(weights_path, 'w') as f:
            json.dump(weights, f, indent=2)
        
        logger.info(f"Updated strategy weights: {weights}")
    
    def _get_strategy_class(self, strategy_name: str):
        """Get strategy class by name"""
        strategy_classes = {
            'MarketMakingStrategy': MarketMakingStrategy,
            'FundingArbitrageStrategy': FundingArbitrageStrategy,
            'DMarkStrategy': DMarkStrategy,
            'DegenTradingStrategy': DegenTradingStrategy,
            'LatencyArbitrageStrategy': LatencyArbitrageStrategy
        }
        return strategy_classes.get(strategy_name)
    
    async def _save_improvement_results(self, results: Dict[str, Any]):
        """Save improvement results to file"""
        
        results_path = os.path.join(self.model_retrainer.models_dir, 'improvement_results.json')
        
        # Convert datetime objects to strings for JSON serialization
        serializable_results = self._make_serializable(results)
        
        with open(results_path, 'w') as f:
            json.dump(serializable_results, f, indent=2)
    
    def _make_serializable(self, obj):
        """Convert datetime objects to strings for JSON serialization"""
        if isinstance(obj, dict):
            return {key: self._make_serializable(value) for key, value in obj.items()}
        elif isinstance(obj, list):
            return [self._make_serializable(item) for item in obj]
        elif isinstance(obj, datetime):
            return obj.isoformat()
        elif hasattr(obj, '__dict__'):
            return self._make_serializable(obj.__dict__)
        else:
            return obj
    
    def get_strategy_weights(self) -> Dict[str, float]:
        """Get current strategy weights"""
        weights_path = os.path.join(self.model_retrainer.models_dir, 'strategy_weights.json')
        
        if os.path.exists(weights_path):
            with open(weights_path, 'r') as f:
                return json.load(f)
        else:
            # Default equal weights
            strategies = list(self.strategy_parameter_ranges.keys())
            return {strategy: 1.0 / len(strategies) for strategy in strategies}
    
    def get_optimized_parameters(self, strategy_name: str) -> Dict[str, Any]:
        """Get optimized parameters for a strategy"""
        if strategy_name in self.optimization_results:
            return self.optimization_results[strategy_name].best_parameters
        else:
            return {}

# Example usage and testing
async def main():
    """Test the self-improvement engine"""
    
    # Create sample data
    dates = pd.date_range(start='2024-01-01', end='2024-01-31', freq='1H')
    historical_data = pd.DataFrame({
        'open': np.random.uniform(100, 200, len(dates)),
        'high': np.random.uniform(100, 200, len(dates)),
        'low': np.random.uniform(100, 200, len(dates)),
        'close': np.random.uniform(100, 200, len(dates)),
        'volume': np.random.uniform(1000, 10000, len(dates))
    }, index=dates)
    
    performance_data = pd.DataFrame({
        'strategy': np.random.choice(['MarketMakingStrategy', 'FundingArbitrageStrategy', 'DMarkStrategy'], 100),
        'pnl': np.random.normal(0, 10, 100),
        'timestamp': pd.date_range(start='2024-01-01', end='2024-01-31', freq='7H')[:100]
    })
    
    # Initialize engine
    config = {
        'retraining_frequency': 'weekly',
        'optimization_frequency': 'daily'
    }
    
    engine = SelfImprovementEngine(config)
    
    # Run improvement cycle
    results = await engine.run_weekly_improvement_cycle(historical_data, performance_data)
    
    print("Self-improvement results:")
    print(json.dumps(results, indent=2, default=str))

if __name__ == "__main__":
    asyncio.run(main())