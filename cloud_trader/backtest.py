"""Backtest framework for validating trading strategies."""
from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from .strategy import MarketSnapshot
from .strategies import StrategySelector, StrategySignal

logger = logging.getLogger(__name__)


@dataclass
class BacktestTrade:
    """Single trade in backtest."""
    timestamp: datetime
    symbol: str
    side: str  # BUY or SELL
    entry_price: float
    quantity: float
    strategy: str
    exit_price: Optional[float] = None
    exit_time: Optional[datetime] = None
    pnl_pct: Optional[float] = None
    pnl_abs: Optional[float] = None


@dataclass
class BacktestResults:
    """Backtest results summary."""
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    win_rate: float = 0.0
    total_return: float = 0.0
    annualized_return: float = 0.0
    max_drawdown: float = 0.0
    sharpe_ratio: float = 0.0
    profit_factor: float = 0.0
    avg_win: float = 0.0
    avg_loss: float = 0.0
    trades: List[BacktestTrade] = field(default_factory=list)
    equity_curve: List[float] = field(default_factory=list)
    strategy_performance: Dict[str, Dict[str, float]] = field(default_factory=dict)


class Backtester:
    """Backtests trading strategies on historical data."""
    
    def __init__(self, initial_capital: float = 10000.0):
        self.initial_capital = initial_capital
        self.capital = initial_capital
        self.positions: Dict[str, BacktestTrade] = {}
        self.closed_trades: List[BacktestTrade] = []
        self.equity_curve: List[float] = [initial_capital]
        self.strategy_selector = StrategySelector(enable_rl=False)  # Disable RL for backtesting
        
    async def run_backtest(self, 
                          symbols: List[str], 
                          start_date: datetime, 
                          end_date: datetime,
                          interval: str = "1h") -> BacktestResults:
        """Run backtest on historical data."""
        logger.info(f"Starting backtest from {start_date} to {end_date}")
        
        # Load historical data for all symbols
        all_data = {}
        for symbol in symbols:
            data = await self._load_historical_data(symbol, start_date, end_date, interval)
            if data is not None and len(data) > 0:
                all_data[symbol] = data
        
        if not all_data:
            logger.error("No historical data loaded")
            return BacktestResults()
        
        # Align timestamps across all symbols
        timestamps = self._get_aligned_timestamps(all_data)
        
        # Process each timestamp
        for timestamp in timestamps:
            await self._process_timestamp(timestamp, all_data)
        
        # Close any remaining positions at the end
        for symbol, trade in list(self.positions.items()):
            if symbol in all_data:
                last_data = all_data[symbol].iloc[-1]
                self._close_position(symbol, last_data['close'], timestamp)
        
        # Calculate results
        return self._calculate_results(start_date, end_date)
    
    async def _process_timestamp(self, timestamp: pd.Timestamp, 
                               all_data: Dict[str, pd.DataFrame]) -> None:
        """Process a single timestamp in the backtest."""
        current_data = {}
        
        # Get current data for each symbol
        for symbol, df in all_data.items():
            try:
                row = df.loc[timestamp]
                current_data[symbol] = row
            except KeyError:
                # Symbol doesn't have data at this timestamp
                continue
        
        if not current_data:
            return
        
        # Check existing positions for exit conditions
        self._check_exits(current_data, timestamp)
        
        # Evaluate entry signals
        await self._check_entries(current_data, timestamp, all_data)
        
        # Update equity curve
        self._update_equity(current_data)
    
    def _check_exits(self, current_data: Dict[str, pd.Series], 
                    timestamp: pd.Timestamp) -> None:
        """Check if any positions should be closed."""
        for symbol, trade in list(self.positions.items()):
            if symbol not in current_data:
                continue
                
            current_price = current_data[symbol]['close']
            
            # Calculate P&L
            if trade.side == "BUY":
                pnl_pct = (current_price - trade.entry_price) / trade.entry_price
            else:  # SELL
                pnl_pct = (trade.entry_price - current_price) / trade.entry_price
            
            # Exit conditions
            should_exit = False
            
            # Take profit at 2%
            if pnl_pct >= 0.02:
                should_exit = True
            
            # Stop loss at 1%
            elif pnl_pct <= -0.01:
                should_exit = True
            
            # Time-based exit (24 hours)
            elif (timestamp - trade.timestamp).total_seconds() > 86400:
                should_exit = True
            
            if should_exit:
                self._close_position(symbol, current_price, timestamp)
    
    async def _check_entries(self, current_data: Dict[str, pd.Series], 
                           timestamp: pd.Timestamp,
                           all_data: Dict[str, pd.DataFrame]) -> None:
        """Check for new entry signals."""
        # Limit number of concurrent positions
        if len(self.positions) >= 5:
            return
        
        for symbol, row in current_data.items():
            # Skip if already have position
            if symbol in self.positions:
                continue
            
            # Create market snapshot
            snapshot = MarketSnapshot(
                symbol=symbol,
                price=row['close'],
                volume=row['volume'],
                change_24h=self._calculate_24h_change(symbol, timestamp, all_data)
            )
            
            # Get historical data for strategies
            historical = self._get_historical_window(symbol, timestamp, all_data, 30)
            
            # Get strategy signal
            signal = await self.strategy_selector.select_best_strategy(
                symbol, snapshot, historical
            )
            
            if signal.direction != "HOLD" and signal.confidence > 0.6:
                # Calculate position size (max 2% of capital per trade)
                position_size = min(signal.position_size, 0.02) * self.capital
                quantity = position_size / row['close']
                
                # Open position
                trade = BacktestTrade(
                    timestamp=timestamp,
                    symbol=symbol,
                    side=signal.direction,
                    entry_price=row['close'],
                    quantity=quantity,
                    strategy=signal.strategy_name
                )
                
                self.positions[symbol] = trade
                
                # Deduct from capital (simulate margin)
                self.capital -= position_size * 0.1  # 10% margin
    
    def _close_position(self, symbol: str, exit_price: float, 
                       exit_time: pd.Timestamp) -> None:
        """Close a position and record the trade."""
        trade = self.positions.pop(symbol)
        
        # Calculate P&L
        if trade.side == "BUY":
            pnl_pct = (exit_price - trade.entry_price) / trade.entry_price
            pnl_abs = (exit_price - trade.entry_price) * trade.quantity
        else:  # SELL
            pnl_pct = (trade.entry_price - exit_price) / trade.entry_price
            pnl_abs = (trade.entry_price - exit_price) * trade.quantity
        
        # Update trade
        trade.exit_price = exit_price
        trade.exit_time = exit_time
        trade.pnl_pct = pnl_pct
        trade.pnl_abs = pnl_abs
        
        # Return margin and add P&L
        position_value = trade.entry_price * trade.quantity
        self.capital += position_value * 0.1 + pnl_abs
        
        self.closed_trades.append(trade)
    
    def _update_equity(self, current_data: Dict[str, pd.Series]) -> None:
        """Update equity curve with current positions."""
        total_equity = self.capital
        
        # Add unrealized P&L from open positions
        for symbol, trade in self.positions.items():
            if symbol in current_data:
                current_price = current_data[symbol]['close']
                if trade.side == "BUY":
                    unrealized_pnl = (current_price - trade.entry_price) * trade.quantity
                else:
                    unrealized_pnl = (trade.entry_price - current_price) * trade.quantity
                total_equity += unrealized_pnl
        
        self.equity_curve.append(total_equity)
    
    def _calculate_results(self, start_date: datetime, end_date: datetime) -> BacktestResults:
        """Calculate backtest performance metrics."""
        results = BacktestResults()
        
        if not self.closed_trades:
            return results
        
        # Basic metrics
        results.total_trades = len(self.closed_trades)
        results.winning_trades = sum(1 for t in self.closed_trades if t.pnl_pct > 0)
        results.losing_trades = results.total_trades - results.winning_trades
        results.win_rate = results.winning_trades / results.total_trades if results.total_trades > 0 else 0
        
        # Returns
        total_pnl = sum(t.pnl_abs for t in self.closed_trades)
        results.total_return = total_pnl / self.initial_capital
        
        # Annualized return
        days = (end_date - start_date).days
        years = days / 365.25
        if years > 0:
            results.annualized_return = (1 + results.total_return) ** (1/years) - 1
        
        # Max drawdown
        equity_array = np.array(self.equity_curve)
        peak = np.maximum.accumulate(equity_array)
        drawdown = (peak - equity_array) / peak
        results.max_drawdown = np.max(drawdown)
        
        # Sharpe ratio (assuming 0 risk-free rate)
        returns = np.diff(equity_array) / equity_array[:-1]
        if len(returns) > 0 and np.std(returns) > 0:
            results.sharpe_ratio = np.mean(returns) / np.std(returns) * np.sqrt(365 * 24)  # Hourly to annual
        
        # Profit factor
        gross_profit = sum(t.pnl_abs for t in self.closed_trades if t.pnl_abs > 0)
        gross_loss = abs(sum(t.pnl_abs for t in self.closed_trades if t.pnl_abs < 0))
        results.profit_factor = gross_profit / gross_loss if gross_loss > 0 else float('inf')
        
        # Average win/loss
        winning_trades = [t for t in self.closed_trades if t.pnl_pct > 0]
        losing_trades = [t for t in self.closed_trades if t.pnl_pct < 0]
        
        results.avg_win = np.mean([t.pnl_pct for t in winning_trades]) if winning_trades else 0
        results.avg_loss = np.mean([t.pnl_pct for t in losing_trades]) if losing_trades else 0
        
        # Strategy breakdown
        for trade in self.closed_trades:
            if trade.strategy not in results.strategy_performance:
                results.strategy_performance[trade.strategy] = {
                    'trades': 0,
                    'wins': 0,
                    'total_pnl': 0.0,
                    'win_rate': 0.0,
                    'avg_pnl': 0.0
                }
            
            stats = results.strategy_performance[trade.strategy]
            stats['trades'] += 1
            if trade.pnl_pct > 0:
                stats['wins'] += 1
            stats['total_pnl'] += trade.pnl_pct
        
        # Calculate strategy metrics
        for strategy, stats in results.strategy_performance.items():
            stats['win_rate'] = stats['wins'] / stats['trades'] if stats['trades'] > 0 else 0
            stats['avg_pnl'] = stats['total_pnl'] / stats['trades'] if stats['trades'] > 0 else 0
        
        results.trades = self.closed_trades
        results.equity_curve = self.equity_curve
        
        return results
    
    async def _load_historical_data(self, symbol: str, start_date: datetime, 
                                  end_date: datetime, interval: str) -> Optional[pd.DataFrame]:
        """Load historical data for a symbol."""
        # In production, this would fetch from exchange API or database
        # For now, generate synthetic data for testing
        
        periods = {
            '1h': timedelta(hours=1),
            '4h': timedelta(hours=4),
            '1d': timedelta(days=1)
        }
        
        period = periods.get(interval, timedelta(hours=1))
        
        # Generate timestamps
        timestamps = []
        current = start_date
        while current <= end_date:
            timestamps.append(current)
            current += period
        
        # Generate synthetic OHLCV data
        np.random.seed(hash(symbol) % 1000)  # Consistent data per symbol
        
        data = []
        base_price = 100.0 * (1 + hash(symbol) % 10)
        
        for i, ts in enumerate(timestamps):
            # Random walk with trend
            trend = 0.0001 * i  # Slight upward trend
            noise = np.random.normal(0, 0.02)  # 2% volatility
            
            close = base_price * (1 + trend + noise)
            open_price = close * (1 + np.random.normal(0, 0.005))
            high = max(open_price, close) * (1 + abs(np.random.normal(0, 0.003)))
            low = min(open_price, close) * (1 - abs(np.random.normal(0, 0.003)))
            volume = 1000000 * (1 + np.random.normal(0, 0.3))
            
            data.append({
                'timestamp': ts,
                'open': open_price,
                'high': high,
                'low': low,
                'close': close,
                'volume': volume
            })
            
            base_price = close
        
        df = pd.DataFrame(data)
        df.set_index('timestamp', inplace=True)
        
        return df
    
    def _get_aligned_timestamps(self, all_data: Dict[str, pd.DataFrame]) -> List[pd.Timestamp]:
        """Get timestamps that exist in at least one symbol's data."""
        all_timestamps = set()
        for df in all_data.values():
            all_timestamps.update(df.index)
        return sorted(all_timestamps)
    
    def _calculate_24h_change(self, symbol: str, timestamp: pd.Timestamp, 
                            all_data: Dict[str, pd.DataFrame]) -> float:
        """Calculate 24h percentage change."""
        df = all_data.get(symbol)
        if df is None:
            return 0.0
        
        try:
            current_idx = df.index.get_loc(timestamp)
            if current_idx >= 24:  # Assuming hourly data
                current_price = df.iloc[current_idx]['close']
                past_price = df.iloc[current_idx - 24]['close']
                return (current_price - past_price) / past_price * 100
        except:
            pass
        
        return 0.0
    
    def _get_historical_window(self, symbol: str, timestamp: pd.Timestamp,
                             all_data: Dict[str, pd.DataFrame], window: int) -> pd.DataFrame:
        """Get historical data window for technical analysis."""
        df = all_data.get(symbol)
        if df is None:
            return pd.DataFrame()
        
        try:
            current_idx = df.index.get_loc(timestamp)
            start_idx = max(0, current_idx - window + 1)
            return df.iloc[start_idx:current_idx + 1]
        except:
            return pd.DataFrame()
    
    def print_results(self, results: BacktestResults) -> None:
        """Print formatted backtest results."""
        print("\n" + "="*60)
        print("BACKTEST RESULTS")
        print("="*60)
        
        print(f"\nPerformance Summary:")
        print(f"  Total Trades: {results.total_trades}")
        print(f"  Win Rate: {results.win_rate:.2%}")
        print(f"  Total Return: {results.total_return:.2%}")
        print(f"  Annualized Return: {results.annualized_return:.2%}")
        print(f"  Max Drawdown: {results.max_drawdown:.2%}")
        print(f"  Sharpe Ratio: {results.sharpe_ratio:.2f}")
        print(f"  Profit Factor: {results.profit_factor:.2f}")
        
        print(f"\nTrade Statistics:")
        print(f"  Average Win: {results.avg_win:.2%}")
        print(f"  Average Loss: {results.avg_loss:.2%}")
        print(f"  Win/Loss Ratio: {abs(results.avg_win/results.avg_loss):.2f}" if results.avg_loss != 0 else "")
        
        print(f"\nStrategy Performance:")
        for strategy, stats in results.strategy_performance.items():
            print(f"\n  {strategy}:")
            print(f"    Trades: {stats['trades']}")
            print(f"    Win Rate: {stats['win_rate']:.2%}")
            print(f"    Avg P&L: {stats['avg_pnl']:.2%}")
            print(f"    Total P&L: {stats['total_pnl']:.2%}")
        
        print("\n" + "="*60)


async def run_strategy_validation():
    """Run backtest to validate strategy profitability."""
    backtester = Backtester(initial_capital=10000)
    
    # Test on multiple symbols
    symbols = ["BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "ARBUSDT", "AVAXUSDT"]
    
    # Last 30 days
    end_date = datetime.utcnow()
    start_date = end_date - timedelta(days=30)
    
    print(f"Running backtest from {start_date} to {end_date}")
    print(f"Symbols: {', '.join(symbols)}")
    
    results = await backtester.run_backtest(symbols, start_date, end_date, "1h")
    
    backtester.print_results(results)
    
    # Check if we meet profitability targets
    meets_target = results.annualized_return >= 0.49  # 49% minimum target
    
    if meets_target:
        print(f"\n✅ Strategy PASSES profitability target (49-85% annualized)")
    else:
        print(f"\n❌ Strategy FAILS profitability target (got {results.annualized_return:.2%})")
    
    return results
