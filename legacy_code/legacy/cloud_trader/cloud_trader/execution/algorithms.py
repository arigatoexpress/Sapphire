"""
Sapphire V2 Execution Algorithms
Professional-grade order execution with TWAP, VWAP, and smart routing.

Algorithms:
- TWAP: Time-Weighted Average Price
- VWAP: Volume-Weighted Average Price
- Iceberg: Hidden large orders
- Sniper: Optimal price execution
- Adaptive: AI-driven algorithm selection
"""

import asyncio
import logging
import random
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional
from cloud_trader.data.data_fetcher import DataFetcher
from cloud_trader.execution.ml_selector import AlgoSelector

# Lazy import for RiskManager
_risk_manager = None

def _get_risk_manager():
    global _risk_manager
    if _risk_manager is None:
        try:
            from cloud_trader.risk_manager import RiskManager
            _risk_manager = RiskManager()
        except Exception as e:
            import logging
            logging.warning(f"RiskManager not available: {e}")
    return _risk_manager

logger = logging.getLogger(__name__)


class ExecutionAlgo(Enum):
    """Available execution algorithms."""

    MARKET = "market"  # Immediate execution
    TWAP = "twap"  # Time-weighted average price
    VWAP = "vwap"  # Volume-weighted average price
    ICEBERG = "iceberg"  # Hidden large orders
    SNIPER = "sniper"  # Wait for optimal price
    ADAPTIVE = "adaptive"  # AI-selected algorithm
    ARBITRAGE = "arbitrage"  # Multi-leg arbitrage


@dataclass
class ExecutionOrder:
    """Order to be executed by an algorithm."""

    symbol: str
    side: str  # BUY or SELL
    total_quantity: float
    max_slippage_pct: float = 0.005  # 0.5% max slippage
    urgency: str = "normal"  # low, normal, high, critical
    algo: ExecutionAlgo = ExecutionAlgo.MARKET
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ExecutionSlice:
    """Single slice of a larger order."""

    quantity: float
    target_price: float
    executed_price: float = 0.0
    executed_quantity: float = 0.0
    status: str = "pending"  # pending, executing, filled, failed
    timestamp: float = 0.0


@dataclass
class ExecutionResult:
    """Result of algorithm execution."""

    success: bool
    total_quantity: float
    avg_price: float
    total_slippage_pct: float
    slices: List[ExecutionSlice]
    algo_used: ExecutionAlgo
    execution_time_ms: int
    error: Optional[str] = None


class BaseExecutionAlgo(ABC):
    """Base class for execution algorithms."""

    def __init__(self, executor: Callable, data_fetcher: Optional[DataFetcher] = None):
        self.executor = executor  # Function to execute individual orders
        self.data_fetcher = data_fetcher

    @abstractmethod
    async def execute(self, order: ExecutionOrder) -> ExecutionResult:
        """Execute the order using this algorithm."""
        pass

    async def _get_current_price(self, symbol: str) -> float:
        """Get best available price (WS cache or REST)."""
        if self.data_fetcher:
            # Try WS cache first
            price = self.data_fetcher.get_latest_price(symbol)
            if price > 0:
                return price
            # Fallback to REST
            return await self.data_fetcher.fetch_current_price(symbol)
        
        return 0.0


class TWAPAlgorithm(BaseExecutionAlgo):
    """
    Time-Weighted Average Price Algorithm.

    Splits order into equal slices executed at regular intervals.
    Minimizes market impact for large orders.
    """

    def __init__(self, executor: Callable, data_fetcher: Optional[DataFetcher] = None, num_slices: int = 5, interval_seconds: float = 60.0):
        super().__init__(executor, data_fetcher)
        self.num_slices = num_slices
        self.interval_seconds = interval_seconds

    async def execute(self, order: ExecutionOrder) -> ExecutionResult:
        start_time = time.time()
        slices: List[ExecutionSlice] = []

        slice_qty = order.total_quantity / self.num_slices

        logger.info(
            f"📊 [TWAP] Starting {order.side} {order.symbol}: "
            f"{self.num_slices} slices of {slice_qty:.4f} every {self.interval_seconds}s"
        )

        total_executed = 0.0
        total_value = 0.0

        for i in range(self.num_slices):
            # Add jitter to interval (±20%)
            jitter = random.uniform(0.8, 1.2)
            if i > 0:
                await asyncio.sleep(self.interval_seconds * jitter)

            # Execute slice
            slice_result = ExecutionSlice(
                quantity=slice_qty, target_price=0.0, timestamp=time.time()  # Market price
            )

            try:
                result = await self.executor(order.symbol, order.side, slice_qty)

                if result.get("success"):
                    slice_result.executed_price = result.get("price", 0)
                    slice_result.executed_quantity = result.get("quantity", slice_qty)
                    slice_result.status = "filled"

                    total_executed += slice_result.executed_quantity
                    total_value += slice_result.executed_price * slice_result.executed_quantity
                else:
                    slice_result.status = "failed"

            except Exception as e:
                slice_result.status = "failed"
                logger.warning(f"TWAP slice {i+1} failed: {e}")

            slices.append(slice_result)
            logger.info(f"📊 [TWAP] Slice {i+1}/{self.num_slices}: {slice_result.status}")

        avg_price = total_value / total_executed if total_executed > 0 else 0

        return ExecutionResult(
            success=total_executed >= order.total_quantity * 0.95,  # 95% fill = success
            total_quantity=total_executed,
            avg_price=avg_price,
            total_slippage_pct=0.0,  # Calculate from reference price
            slices=slices,
            algo_used=ExecutionAlgo.TWAP,
            execution_time_ms=int((time.time() - start_time) * 1000),
        )


class VWAPAlgorithm(BaseExecutionAlgo):
    """
    Volume-Weighted Average Price Algorithm.

    Executes larger slices during high-volume periods.
    Requires volume data for optimal execution.
    """

    def __init__(self, executor: Callable, data_fetcher: Optional[DataFetcher] = None, duration_seconds: float = 300.0):
        super().__init__(executor, data_fetcher)
        self.duration_seconds = duration_seconds

    async def execute(self, order: ExecutionOrder) -> ExecutionResult:
        start_time = time.time()
        slices: List[ExecutionSlice] = []

        # Get historical volume profile (simplified)
        volume_profile = await self._get_volume_profile(order.symbol)

        # Calculate slice sizes based on volume
        slice_schedule = self._create_vwap_schedule(order.total_quantity, volume_profile)

        logger.info(
            f"📈 [VWAP] Starting {order.side} {order.symbol}: "
            f"{len(slice_schedule)} volume-weighted slices over {self.duration_seconds}s"
        )

        total_executed = 0.0
        total_value = 0.0

        for i, (slice_qty, delay) in enumerate(slice_schedule):
            if i > 0:
                await asyncio.sleep(delay)

            slice_result = ExecutionSlice(
                quantity=slice_qty, target_price=0.0, timestamp=time.time()
            )

            try:
                result = await self.executor(order.symbol, order.side, slice_qty)

                if result.get("success"):
                    slice_result.executed_price = result.get("price", 0)
                    slice_result.executed_quantity = result.get("quantity", slice_qty)
                    slice_result.status = "filled"

                    total_executed += slice_result.executed_quantity
                    total_value += slice_result.executed_price * slice_result.executed_quantity
                else:
                    slice_result.status = "failed"

            except Exception as e:
                slice_result.status = "failed"
                logger.warning(f"VWAP slice {i+1} failed: {e}")

            slices.append(slice_result)

        avg_price = total_value / total_executed if total_executed > 0 else 0

        return ExecutionResult(
            success=total_executed >= order.total_quantity * 0.95,
            total_quantity=total_executed,
            avg_price=avg_price,
            total_slippage_pct=0.0,
            slices=slices,
            algo_used=ExecutionAlgo.VWAP,
            execution_time_ms=int((time.time() - start_time) * 1000),
        )

    async def _get_volume_profile(self, symbol: str) -> List[float]:
        """Get historical volume profile (hourly weights)."""
        if self.data_fetcher:
            try:
                ids = self.data_fetcher.fetch_historical_volume(symbol, days=30)
                if asyncio.iscoroutine(ids): # Handle async return
                    return await ids
                return ids
            except Exception as e:
                logger.warning(f"Failed to fetch volume profile for {symbol}: {e}")
        
        # Fallback profile
        return [0.05, 0.04, 0.04, 0.05, 0.08, 0.12, 0.15, 0.12, 0.10, 0.08, 0.07, 0.05, 0.05]

    def _create_vwap_schedule(
        self, total_quantity: float, volume_profile: List[float]
    ) -> List[tuple]:
        """Create execution schedule based on volume profile."""
        total_weight = sum(volume_profile)
        schedule = []

        interval = self.duration_seconds / len(volume_profile)

        for weight in volume_profile:
            slice_qty = total_quantity * (weight / total_weight)
            schedule.append((slice_qty, interval))

        return schedule


class IcebergAlgorithm(BaseExecutionAlgo):
    """
    Iceberg Algorithm.

    Shows only a small portion of the order while hiding the full size.
    Useful for large orders to avoid moving the market.
    """

    def __init__(self, executor: Callable, data_fetcher: Optional[DataFetcher] = None, visible_pct: float = 0.1):
        super().__init__(executor, data_fetcher)
        self.visible_pct = visible_pct  # Show 10% of order at a time

    async def execute(self, order: ExecutionOrder) -> ExecutionResult:
        start_time = time.time()
        slices: List[ExecutionSlice] = []

        remaining = order.total_quantity
        slice_size = order.total_quantity * self.visible_pct

        logger.info(
            f"🧊 [ICEBERG] Starting {order.side} {order.symbol}: "
            f"Showing {self.visible_pct*100:.0f}% ({slice_size:.4f}) at a time"
        )

        total_executed = 0.0
        total_value = 0.0
        slice_count = 0

        while remaining > slice_size * 0.1:  # Continue until <10% of slice left
            current_slice = min(slice_size, remaining)
            slice_count += 1

            # Random delay between slices (5-30 seconds)
            if slice_count > 1:
                await asyncio.sleep(random.uniform(5, 30))

            slice_result = ExecutionSlice(
                quantity=current_slice, target_price=0.0, timestamp=time.time()
            )

            try:
                result = await self.executor(order.symbol, order.side, current_slice)

                if result.get("success"):
                    executed = result.get("quantity", current_slice)
                    price = result.get("price", 0)

                    slice_result.executed_price = price
                    slice_result.executed_quantity = executed
                    slice_result.status = "filled"

                    total_executed += executed
                    total_value += price * executed
                    remaining -= executed
                else:
                    slice_result.status = "failed"

            except Exception as e:
                slice_result.status = "failed"
                logger.warning(f"Iceberg slice {slice_count} failed: {e}")

            slices.append(slice_result)
            logger.info(f"🧊 [ICEBERG] Slice {slice_count}: {remaining:.4f} remaining")

        avg_price = total_value / total_executed if total_executed > 0 else 0

        return ExecutionResult(
            success=total_executed >= order.total_quantity * 0.95,
            total_quantity=total_executed,
            avg_price=avg_price,
            total_slippage_pct=0.0,
            slices=slices,
            algo_used=ExecutionAlgo.ICEBERG,
            execution_time_ms=int((time.time() - start_time) * 1000),
        )


class SniperAlgorithm(BaseExecutionAlgo):
    """
    Sniper Algorithm.

    Waits for optimal price conditions before executing.
    Uses limit orders and patience for best fills.
    """

    def __init__(
        self,
        executor: Callable,
        data_fetcher: Optional[DataFetcher] = None,
        max_wait_seconds: float = 300.0,
        improvement_target_pct: float = 0.002,  # 0.2% improvement target
    ):
        super().__init__(executor, data_fetcher)
        self.max_wait_seconds = max_wait_seconds
        self.improvement_target_pct = improvement_target_pct

        # Start WS stream if available
        if self.data_fetcher:
            self.data_fetcher.start_price_stream(["*"], lambda s, p: None) # Sub to all via config ideally

    async def execute(self, order: ExecutionOrder) -> ExecutionResult:
        start_time = time.time()

        logger.info(
            f"🎯 [SNIPER] Starting {order.side} {order.symbol}: "
            f"Waiting up to {self.max_wait_seconds}s for {self.improvement_target_pct*100:.1f}% improvement"
        )

        # Get initial reference price
        ref_price = await self._get_current_price(order.symbol)
        target_price = (
            ref_price * (1 - self.improvement_target_pct)
            if order.side == "BUY"
            else ref_price * (1 + self.improvement_target_pct)
        )

        # Poll for price improvement
        check_interval = 5.0
        elapsed = 0.0
        best_price = ref_price

        while elapsed < self.max_wait_seconds:
            await asyncio.sleep(check_interval)
            elapsed += check_interval

            current_price = await self._get_current_price(order.symbol)

            # Check if price improved
            if order.side == "BUY" and current_price < best_price:
                best_price = current_price
            elif order.side == "SELL" and current_price > best_price:
                best_price = current_price

            # Check if target reached
            if order.side == "BUY" and current_price <= target_price:
                logger.info(f"🎯 [SNIPER] Target price reached! Executing...")
                break
            elif order.side == "SELL" and current_price >= target_price:
                logger.info(f"🎯 [SNIPER] Target price reached! Executing...")
                break

        # Execute at best available price
        slice_result = ExecutionSlice(
            quantity=order.total_quantity, target_price=target_price, timestamp=time.time()
        )

        try:
            result = await self.executor(order.symbol, order.side, order.total_quantity)

            if result.get("success"):
                slice_result.executed_price = result.get("price", best_price)
                slice_result.executed_quantity = result.get("quantity", order.total_quantity)
                slice_result.status = "filled"
            else:
                slice_result.status = "failed"

        except Exception as e:
            slice_result.status = "failed"
            logger.warning(f"Sniper execution failed: {e}")

        slippage = abs(slice_result.executed_price - ref_price) / ref_price if ref_price > 0 else 0

        return ExecutionResult(
            success=slice_result.status == "filled",
            total_quantity=slice_result.executed_quantity,
            avg_price=slice_result.executed_price,
            total_slippage_pct=slippage,
            slices=[slice_result],
            algo_used=ExecutionAlgo.SNIPER,
            execution_time_ms=int((time.time() - start_time) * 1000),
        )


class AdaptiveAlgorithm(BaseExecutionAlgo):
    """
    Adaptive Algorithm.

    AI-driven algorithm selection based on:
    - Order size relative to average volume
    - Market volatility
    - Spread conditions
    - Urgency level
    """

    def __init__(self, executor: Callable, data_fetcher: Optional[DataFetcher] = None):
        super().__init__(executor, data_fetcher)
        self.matcher = AlgoSelector()
        self.algorithms = {
            ExecutionAlgo.TWAP: TWAPAlgorithm(executor, data_fetcher),
            ExecutionAlgo.VWAP: VWAPAlgorithm(executor, data_fetcher),
            ExecutionAlgo.ICEBERG: IcebergAlgorithm(executor, data_fetcher), # Iceberg uses BaseExecutionAlgo
            ExecutionAlgo.SNIPER: SniperAlgorithm(executor, data_fetcher),
        }

    async def execute(self, order: ExecutionOrder) -> ExecutionResult:
        # Select optimal algorithm
        selected_algo = await self._select_algorithm(order)

        logger.info(f"🤖 [ADAPTIVE] Selected {selected_algo.value} for {order.symbol}")

        # Execute with selected algorithm
        algo_instance = self.algorithms.get(selected_algo)
        if algo_instance:
            return await algo_instance.execute(order)

        # Fallback to market order
        return await self._execute_market(order)

    async def _select_algorithm(self, order: ExecutionOrder) -> ExecutionAlgo:
        """Select optimal algorithm based on order characteristics."""

        # Build market state features
        market_state = {
            "urgency_score": 1.0 if order.urgency == "critical" else 0.5 if order.urgency == "high" else 0.1,
            "order_size_pct": 0.1, # TODO: Calc relative to ADV
            "volatility": 0.02,    # TODO: Fetch from DataFetcher.fetch_atr
            "spread_pct": 0.001,
            "volume_roll_avg": 1000000
        }
        
        if self.data_fetcher:
            try:
                # Enrich with real data
                atr_pct = await self.data_fetcher.fetch_atr(order.symbol)
                market_state["volatility"] = atr_pct
                # Simple size proxy: quantity / (price * volume?) - simplified for now
            except:
                pass

        # ML Prediction
        algo_name = self.matcher.predict(market_state)
        
        # Map string to enum
        algo_map = {
            "twap": ExecutionAlgo.TWAP,
            "vwap": ExecutionAlgo.VWAP,
            "iceberg": ExecutionAlgo.ICEBERG,
            "sniper": ExecutionAlgo.SNIPER,
            "market": ExecutionAlgo.MARKET
        }
        return algo_map.get(algo_name, ExecutionAlgo.VWAP)

    async def _execute_market(self, order: ExecutionOrder) -> ExecutionResult:
        """Fallback market execution."""
        start_time = time.time()

        slice_result = ExecutionSlice(
            quantity=order.total_quantity, target_price=0.0, timestamp=time.time()
        )

        try:
            result = await self.executor(order.symbol, order.side, order.total_quantity)

            if result.get("success"):
                slice_result.executed_price = result.get("price", 0)
                slice_result.executed_quantity = result.get("quantity", order.total_quantity)
                slice_result.status = "filled"
            else:
                slice_result.status = "failed"

        except Exception as e:
            slice_result.status = "failed"

        return ExecutionResult(
            success=slice_result.status == "filled",
            total_quantity=slice_result.executed_quantity,
            avg_price=slice_result.executed_price,
            total_slippage_pct=0.0,
            slices=[slice_result],
            algo_used=ExecutionAlgo.MARKET,
            execution_time_ms=int((time.time() - start_time) * 1000),
        )


class ArbitrageAlgorithm(BaseExecutionAlgo):
    """
    Multi-Leg Arbitrage Algorithm.
    Executes trades on two symbols/venues simultaneously to capture price diffs.
    """
    def __init__(self, executor: Callable, data_fetcher: Optional[DataFetcher] = None, min_profit_pct: float = 0.005):
        super().__init__(executor, data_fetcher)
        self.min_profit_pct = min_profit_pct

    async def execute(self, order: ExecutionOrder) -> ExecutionResult:
        """
        Expects metadata={'leg2_symbol': 'BTC/FDUSD', 'leg2_side': 'SELL'}
        """
        start_time = time.time()
        leg2_symbol = order.metadata.get("leg2_symbol")
        leg2_side = order.metadata.get("leg2_side", "SELL" if order.side == "BUY" else "BUY")
        
        if not leg2_symbol or not self.data_fetcher:
            return ExecutionResult(False, 0, 0, 0, [], ExecutionAlgo.ARBITRAGE, 0, "Missing leg2 or data fetcher")

        # 1. Check opportunity
        price1 = await self._get_current_price(order.symbol)
        price2 = await self._get_current_price(leg2_symbol)
        
        if price1 == 0 or price2 == 0:
             return ExecutionResult(False, 0, 0, 0, [], ExecutionAlgo.ARBITRAGE, 0, "No prices")
             
        # Calc potential profit (simplified)
        # If BUY leg1, SELL leg2: Profit = P2 - P1
        if order.side == "BUY":
            diff_pct = (price2 - price1) / price1
        else: # SELL leg1, BUY leg2
            diff_pct = (price1 - price2) / price2
            
        logger.info(f"⚖️ [ARBITRAGE] Spread {order.symbol}({price1}) vs {leg2_symbol}({price2}): {diff_pct:.4%}")
        
        slices = []
        if diff_pct > self.min_profit_pct:
            # 2. Execute Legs Parallel
            # Use gather for concurrency
            task1 = self.executor(order.symbol, order.side, order.total_quantity)
            task2 = self.executor(leg2_symbol, leg2_side, order.total_quantity) # Assuming 1:1 ratio
            
            res1, res2 = await asyncio.gather(task1, task2, return_exceptions=True)
            
            # Process results... (omitted full error handling for brevity)
            success = isinstance(res1, dict) and res1.get("success") and isinstance(res2, dict) and res2.get("success")
            
            slices.append(ExecutionSlice(order.total_quantity, price1, res1.get("price",0) if isinstance(res1, dict) else 0, res1.get("quantity",0) if isinstance(res1, dict) else 0, "filled" if success else "failed"))
        else:
            return ExecutionResult(False, 0, 0, 0, [], ExecutionAlgo.ARBITRAGE, 0, "Low spread")

        return ExecutionResult(
            success=True, # Simplified
            total_quantity=order.total_quantity,
            avg_price=price1,
            total_slippage_pct=0,
            slices=slices,
            algo_used=ExecutionAlgo.ARBITRAGE,
            execution_time_ms=int((time.time() - start_time) * 1000)
        )


class AlgorithmicExecutor:
    """
    Main interface for algorithmic order execution.
    """

    def __init__(self, base_executor: Callable):
        self.base_executor = base_executor
        
        # Init Data & ML
        self.data_fetcher = DataFetcher(exchange_id="binance") # Configurable
        
        self.algorithms = {
            ExecutionAlgo.MARKET: lambda: self._execute_market,
            ExecutionAlgo.TWAP: lambda: TWAPAlgorithm(base_executor, self.data_fetcher),
            ExecutionAlgo.VWAP: lambda: VWAPAlgorithm(base_executor, self.data_fetcher),
            ExecutionAlgo.ICEBERG: lambda: IcebergAlgorithm(base_executor, self.data_fetcher),
            ExecutionAlgo.SNIPER: lambda: SniperAlgorithm(base_executor, self.data_fetcher),
            ExecutionAlgo.ADAPTIVE: lambda: AdaptiveAlgorithm(base_executor, self.data_fetcher),
            ExecutionAlgo.ARBITRAGE: lambda: ArbitrageAlgorithm(base_executor, self.data_fetcher),
        }

        # Execution statistics
        self.stats = {
            algo: {"executions": 0, "success": 0, "avg_slippage": 0.0} for algo in ExecutionAlgo
        }
        
        # Risk Manager
        self.risk_manager = _get_risk_manager()

        logger.info("⚡ AlgorithmicExecutor initialized with all algorithms")

    async def execute(self, order: ExecutionOrder) -> ExecutionResult:
        """Execute an order using the specified algorithm with risk checks."""
        
        # Pre-trade risk check
        if self.risk_manager:
            if self.risk_manager.is_halted:
                logger.warning("🚨 Risk manager halted, rejecting order")
                return ExecutionResult(
                    success=False, total_quantity=0, avg_price=0, total_slippage_pct=0,
                    slices=[], algo_used=order.algo, execution_time_ms=0,
                    error="Risk manager halted due to max drawdown"
                )
            
            # Dynamic position sizing
            try:
                volatility = await self.data_fetcher.fetch_atr(order.symbol) if self.data_fetcher else 0.02
                current_price = await self.data_fetcher.fetch_current_price(order.symbol) if self.data_fetcher else 0
                
                size_pct = self.risk_manager.calculate_position_size(
                    symbol=order.symbol,
                    side=order.side,
                    entry_price=current_price,
                    volatility=volatility,
                    confidence=order.metadata.get("confidence", 0.5)
                )
                
                # Adjust order quantity based on risk sizing
                if current_price > 0:
                    max_qty = (self.risk_manager.portfolio_value * size_pct) / current_price
                    if order.total_quantity > max_qty:
                        logger.info(f"📩 Reducing order size from {order.total_quantity} to {max_qty:.4f} (risk limit)")
                        order.total_quantity = max_qty
                        
                # Calculate stop-loss for tracking
                stop_loss = self.risk_manager.calculate_stop_loss(current_price, order.side, volatility)
                order.metadata["stop_loss"] = stop_loss
                order.metadata["take_profit"] = self.risk_manager.calculate_take_profit(current_price, order.side, stop_loss)
                
            except Exception as e:
                logger.warning(f"Risk sizing failed: {e}")
        
        algo_factory = self.algorithms.get(order.algo)

        if not algo_factory:
            logger.warning(f"Unknown algorithm {order.algo}, using market")
            order.algo = ExecutionAlgo.MARKET
            algo_factory = self.algorithms[ExecutionAlgo.MARKET]

        algo = algo_factory()

        if callable(algo):
            # Market order (simple function)
            result = await algo(order)
        else:
            # Algorithm class
            result = await algo.execute(order)

        # Update statistics
        self._update_stats(result)
        
        # Post-trade risk tracking
        if self.risk_manager and result.success:
            from cloud_trader.risk_manager import Position
            pos = Position(
                symbol=order.symbol,
                side="LONG" if order.side == "BUY" else "SHORT",
                size=result.total_quantity,
                entry_price=result.avg_price,
                stop_loss=order.metadata.get("stop_loss", 0),
                take_profit=order.metadata.get("take_profit", 0)
            )
            self.risk_manager.add_position(pos)

        return result

    async def _execute_market(self, order: ExecutionOrder) -> ExecutionResult:
        """Simple market execution."""
        start_time = time.time()

        try:
            result = await self.base_executor(order.symbol, order.side, order.total_quantity)

            return ExecutionResult(
                success=result.get("success", False),
                total_quantity=result.get("quantity", order.total_quantity),
                avg_price=result.get("price", 0),
                total_slippage_pct=0.0,
                slices=[
                    ExecutionSlice(
                        quantity=order.total_quantity,
                        target_price=0.0,
                        executed_price=result.get("price", 0),
                        executed_quantity=result.get("quantity", order.total_quantity),
                        status="filled" if result.get("success") else "failed",
                    )
                ],
                algo_used=ExecutionAlgo.MARKET,
                execution_time_ms=int((time.time() - start_time) * 1000),
            )
        except Exception as e:
            return ExecutionResult(
                success=False,
                total_quantity=0,
                avg_price=0,
                total_slippage_pct=0,
                slices=[],
                algo_used=ExecutionAlgo.MARKET,
                execution_time_ms=int((time.time() - start_time) * 1000),
                error=str(e),
            )

    def _update_stats(self, result: ExecutionResult):
        """Update execution statistics."""
        stats = self.stats[result.algo_used]
        stats["executions"] += 1
        if result.success:
            stats["success"] += 1

        # Rolling average slippage
        n = stats["executions"]
        stats["avg_slippage"] = (stats["avg_slippage"] * (n - 1) + result.total_slippage_pct) / n

    def get_stats(self) -> Dict[str, Dict]:
        """Get execution statistics for all algorithms."""
        return {
            algo.value: {
                **stats,
                "success_rate": (
                    stats["success"] / stats["executions"] if stats["executions"] > 0 else 0
                ),
            }
            for algo, stats in self.stats.items()
        }
