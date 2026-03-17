"""
Backtester Module
Performance evaluation with Sharpe, Sortino, and Calmar ratios.
"""

import logging
import numpy as np
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class Trade:
    symbol: str
    side: str
    entry_price: float
    exit_price: float
    size: float
    entry_time: datetime
    exit_time: datetime
    pnl: float = 0.0
    pnl_pct: float = 0.0

    def __post_init__(self):
        if self.entry_price > 0:
            if self.side == "LONG":
                self.pnl = (self.exit_price - self.entry_price) * self.size
                self.pnl_pct = (self.exit_price - self.entry_price) / self.entry_price
            else:
                self.pnl = (self.entry_price - self.exit_price) * self.size
                self.pnl_pct = (self.entry_price - self.exit_price) / self.entry_price


@dataclass
class BacktestResult:
    total_return: float = 0.0
    annualized_return: float = 0.0
    sharpe_ratio: float = 0.0
    sortino_ratio: float = 0.0
    calmar_ratio: float = 0.0
    max_drawdown: float = 0.0
    win_rate: float = 0.0
    profit_factor: float = 0.0
    avg_trade_pnl: float = 0.0
    total_trades: int = 0
    trades: List[Trade] = field(default_factory=list)
    equity_curve: List[float] = field(default_factory=list)


class Backtester:
    """
    Backtests trading strategies and calculates performance metrics.
    """

    def __init__(
        self,
        initial_capital: float = 10000.0,
        risk_free_rate: float = 0.02,  # 2% annual
        trading_days: int = 365,  # Crypto trades 365 days
    ):
        self.initial_capital = initial_capital
        self.risk_free_rate = risk_free_rate
        self.trading_days = trading_days

    def run(
        self,
        trades: List[Trade],
        prices: Optional[Dict[str, List[float]]] = None,
    ) -> BacktestResult:
        """
        Run backtest on a list of trades.
        
        Args:
            trades: List of executed trades
            prices: Optional price history for equity curve
            
        Returns:
            BacktestResult with metrics
        """
        if not trades:
            return BacktestResult(total_trades=0)

        # Calculate equity curve
        equity = [self.initial_capital]
        for trade in trades:
            equity.append(equity[-1] + trade.pnl)

        equity = np.array(equity)

        # Returns
        returns = np.diff(equity) / equity[:-1]
        returns = np.nan_to_num(returns, nan=0.0, posinf=0.0, neginf=0.0)

        # Calculate metrics
        total_return = (equity[-1] - self.initial_capital) / self.initial_capital
        
        # Annualized return
        days = max(1, (trades[-1].exit_time - trades[0].entry_time).days)
        ann_factor = self.trading_days / days
        annualized_return = ((1 + total_return) ** ann_factor) - 1

        # Sharpe Ratio
        sharpe = self._calculate_sharpe(returns, ann_factor)

        # Sortino Ratio (only downside deviation)
        sortino = self._calculate_sortino(returns, ann_factor)

        # Max Drawdown
        max_dd = self._calculate_max_drawdown(equity)

        # Calmar Ratio (ann return / max dd)
        calmar = annualized_return / max_dd if max_dd > 0 else 0.0

        # Win Rate
        wins = sum(1 for t in trades if t.pnl > 0)
        win_rate = wins / len(trades) if trades else 0.0

        # Profit Factor
        gross_profit = sum(t.pnl for t in trades if t.pnl > 0)
        gross_loss = abs(sum(t.pnl for t in trades if t.pnl < 0))
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else float("inf")

        # Avg Trade PnL
        avg_pnl = sum(t.pnl for t in trades) / len(trades) if trades else 0.0

        return BacktestResult(
            total_return=total_return,
            annualized_return=annualized_return,
            sharpe_ratio=sharpe,
            sortino_ratio=sortino,
            calmar_ratio=calmar,
            max_drawdown=max_dd,
            win_rate=win_rate,
            profit_factor=profit_factor,
            avg_trade_pnl=avg_pnl,
            total_trades=len(trades),
            trades=trades,
            equity_curve=equity.tolist(),
        )

    def _calculate_sharpe(self, returns: np.ndarray, ann_factor: float) -> float:
        """Calculate Sharpe Ratio."""
        if len(returns) == 0:
            return 0.0

        excess_returns = returns - (self.risk_free_rate / self.trading_days)
        mean_excess = np.mean(excess_returns)
        std_excess = np.std(excess_returns)

        if std_excess == 0 or np.isnan(std_excess):
            return 0.0

        sharpe = (mean_excess / std_excess) * np.sqrt(self.trading_days)
        return float(np.nan_to_num(sharpe, nan=0.0))

    def _calculate_sortino(self, returns: np.ndarray, ann_factor: float) -> float:
        """Calculate Sortino Ratio (uses only downside deviation)."""
        if len(returns) == 0:
            return 0.0

        target = self.risk_free_rate / self.trading_days
        downside_returns = returns[returns < target]

        if len(downside_returns) == 0:
            return float("inf")  # No downside

        downside_std = np.std(downside_returns)

        if downside_std == 0 or np.isnan(downside_std):
            return 0.0

        mean_return = np.mean(returns)
        sortino = ((mean_return - target) / downside_std) * np.sqrt(self.trading_days)
        return float(np.nan_to_num(sortino, nan=0.0))

    def _calculate_max_drawdown(self, equity: np.ndarray) -> float:
        """Calculate maximum drawdown."""
        peak = np.maximum.accumulate(equity)
        drawdown = (peak - equity) / peak
        return float(np.max(drawdown))

    def generate_report(self, result: BacktestResult) -> str:
        """Generate human-readable report."""
        lines = [
            "=" * 50,
            "BACKTEST RESULTS",
            "=" * 50,
            f"Total Return:       {result.total_return:.2%}",
            f"Annualized Return:  {result.annualized_return:.2%}",
            f"Sharpe Ratio:       {result.sharpe_ratio:.2f}",
            f"Sortino Ratio:      {result.sortino_ratio:.2f}",
            f"Calmar Ratio:       {result.calmar_ratio:.2f}",
            f"Max Drawdown:       {result.max_drawdown:.2%}",
            "-" * 50,
            f"Win Rate:           {result.win_rate:.2%}",
            f"Profit Factor:      {result.profit_factor:.2f}",
            f"Avg Trade PnL:      ${result.avg_trade_pnl:.2f}",
            f"Total Trades:       {result.total_trades}",
            "=" * 50,
        ]
        return "\n".join(lines)


def quick_backtest(
    signals: List[Dict[str, Any]],
    prices: Dict[str, float],
    initial_capital: float = 10000.0,
) -> BacktestResult:
    """
    Quick backtest from signals.
    
    Args:
        signals: List of {symbol, signal, timestamp, price}
        prices: Exit prices for each symbol
        initial_capital: Starting capital
    """
    trades = []
    positions: Dict[str, Dict] = {}

    for sig in signals:
        symbol = sig["symbol"]
        signal = sig["signal"]
        price = sig.get("price", 0)
        ts = sig.get("timestamp", datetime.now())

        if signal in ["BUY", "LONG"]:
            if symbol not in positions:
                positions[symbol] = {
                    "side": "LONG",
                    "entry_price": price,
                    "entry_time": ts,
                    "size": initial_capital * 0.1 / price,
                }
        elif signal in ["SELL", "SHORT"]:
            if symbol in positions:
                pos = positions.pop(symbol)
                trades.append(
                    Trade(
                        symbol=symbol,
                        side=pos["side"],
                        entry_price=pos["entry_price"],
                        exit_price=price,
                        size=pos["size"],
                        entry_time=pos["entry_time"],
                        exit_time=ts,
                    )
                )

    backtester = Backtester(initial_capital=initial_capital)
    return backtester.run(trades)


class EnhancedBacktester(Backtester):
    """
    Enhanced backtester with realistic frictions and out-of-sample validation.
    """

    def __init__(
        self,
        initial_capital: float = 10000.0,
        risk_free_rate: float = 0.02,
        trading_days: int = 365,
        fee_pct: float = 0.001,  # 0.1% trading fee
        slippage_pct: float = 0.0005,  # 0.05% slippage
    ):
        super().__init__(initial_capital, risk_free_rate, trading_days)
        self.fee_pct = fee_pct
        self.slippage_pct = slippage_pct

    def run_with_frictions(
        self,
        trades: List[Trade],
    ) -> BacktestResult:
        """
        Run backtest with realistic fees and slippage applied.
        """
        adjusted_trades = []
        
        for trade in trades:
            # Apply slippage to entry/exit
            if trade.side == "LONG":
                adj_entry = trade.entry_price * (1 + self.slippage_pct)
                adj_exit = trade.exit_price * (1 - self.slippage_pct)
            else:
                adj_entry = trade.entry_price * (1 - self.slippage_pct)
                adj_exit = trade.exit_price * (1 + self.slippage_pct)
            
            # Calculate fee cost
            fee_cost = (adj_entry + adj_exit) * trade.size * self.fee_pct
            
            # Create adjusted trade
            adj_trade = Trade(
                symbol=trade.symbol,
                side=trade.side,
                entry_price=adj_entry,
                exit_price=adj_exit,
                size=trade.size,
                entry_time=trade.entry_time,
                exit_time=trade.exit_time,
            )
            # Subtract fees from PnL
            adj_trade.pnl -= fee_cost
            
            adjusted_trades.append(adj_trade)
        
        return self.run(adjusted_trades)

    def run_out_of_sample(
        self,
        trades: List[Trade],
        train_ratio: float = 0.7,
    ) -> Dict[str, BacktestResult]:
        """
        Run backtest with train/test split to detect overfitting.
        
        Args:
            trades: All trades
            train_ratio: Fraction of data for training (default 70%)
            
        Returns:
            Dict with 'in_sample' and 'out_of_sample' BacktestResults
        """
        if not trades:
            return {"in_sample": BacktestResult(), "out_of_sample": BacktestResult()}
        
        split_idx = int(len(trades) * train_ratio)
        train_trades = trades[:split_idx]
        test_trades = trades[split_idx:]
        
        logger.info(f"OOS Split: {len(train_trades)} train, {len(test_trades)} test")
        
        return {
            "in_sample": self.run_with_frictions(train_trades),
            "out_of_sample": self.run_with_frictions(test_trades),
        }

    def validate_strategy(
        self,
        trades: List[Trade],
        min_sharpe: float = 1.0,
        max_drawdown: float = 0.20,
    ) -> Dict[str, Any]:
        """
        Validate strategy against performance thresholds.
        
        Returns:
            Dict with validation results and warnings
        """
        oos_results = self.run_out_of_sample(trades)
        is_result = oos_results["in_sample"]
        oos_result = oos_results["out_of_sample"]
        
        warnings = []
        
        # Check for overfitting
        if is_result.sharpe_ratio > 0 and oos_result.sharpe_ratio > 0:
            sharpe_decay = (is_result.sharpe_ratio - oos_result.sharpe_ratio) / is_result.sharpe_ratio
            if sharpe_decay > 0.5:
                warnings.append(f"⚠️ High Sharpe decay ({sharpe_decay:.0%}): possible overfitting")
        
        # Check thresholds
        passed = True
        if oos_result.sharpe_ratio < min_sharpe:
            passed = False
            warnings.append(f"⚠️ OOS Sharpe ({oos_result.sharpe_ratio:.2f}) below threshold ({min_sharpe})")
        
        if oos_result.max_drawdown > max_drawdown:
            passed = False
            warnings.append(f"⚠️ OOS Drawdown ({oos_result.max_drawdown:.0%}) above threshold ({max_drawdown:.0%})")
        
        return {
            "passed": passed,
            "in_sample": is_result,
            "out_of_sample": oos_result,
            "warnings": warnings,
        }


async def fetch_historical_data(
    symbol: str = "BTC/USDT",
    timeframe: str = "1d",
    days: int = 365,
    exchange_id: str = "binance",
) -> List[List]:
    """
    Fetch historical OHLCV data via CCXT.
    
    Returns:
        List of [timestamp, open, high, low, close, volume]
    """
    try:
        import ccxt.async_support as ccxt
        
        exchange_class = getattr(ccxt, exchange_id)
        exchange = exchange_class({"enableRateLimit": True})
        
        since = exchange.milliseconds() - (days * 24 * 60 * 60 * 1000)
        ohlcv = await exchange.fetch_ohlcv(symbol, timeframe, since=since, limit=1000)
        
        await exchange.close()
        
        logger.info(f"Fetched {len(ohlcv)} candles for {symbol}")
        return ohlcv
        
    except Exception as e:
        logger.error(f"Failed to fetch historical data: {e}")
        return []
