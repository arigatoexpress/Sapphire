"""
VPIN (Volume-Synchronized Probability of Informed Trading) Calculator

Advanced market microstructure analysis for detecting informed trading activity:
- Real-time VPIN calculation optimized for RTX 5070 Ti
- Bulk volume classification using order book imbalance
- High-frequency trade flow analysis
- GPU-accelerated computations for low-latency processing
- Integration with ML feature pipeline

Critical for HFT strategies and market manipulation detection.
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Any, Union
import numpy as np
import pandas as pd
import torch
import torch.nn as nn
from torch.utils.data import Dataset, DataLoader
import numba
from numba import cuda
import warnings

from mcp_trader.data.self_healing_endpoint_manager import SelfHealingEndpointManager, EndpointType

logger = logging.getLogger(__name__)


@dataclass
class VPINConfig:
    """Configuration for VPIN calculation"""

    # VPIN parameters
    volume_bucket_size: int = 1000  # Number of shares per bucket
    time_bucket_seconds: int = 300  # 5 minutes
    vpin_window_size: int = 50      # Rolling window for VPIN calculation
    imbalance_threshold: float = 0.1  # Threshold for significant imbalance

    # Bulk volume classification
    bulk_volume_threshold: float = 0.8  # 80% of volume considered bulk
    order_book_depth: int = 10          # Order book levels to analyze

    # GPU optimization
    gpu_acceleration: bool = True
    batch_size: int = 1024
    num_workers: int = 4

    # Real-time processing
    real_time_enabled: bool = True
    update_interval_seconds: float = 1.0
    max_latency_ms: float = 10.0

    # Alert thresholds
    vpin_alert_threshold: float = 0.15
    volume_spike_threshold: float = 2.0


@dataclass
class VPINResult:
    """Result of VPIN calculation"""

    timestamp: datetime
    symbol: str
    vpin: float
    imbalance: float
    bulk_volume_ratio: float
    order_flow_imbalance: float
    price_impact: float
    confidence_score: float

    # Additional metrics
    volume_bucket_count: int = 0
    total_volume: float = 0.0
    buy_volume: float = 0.0
    sell_volume: float = 0.0


@dataclass
class MarketMicrostructureFeatures:
    """Market microstructure features for ML"""

    vpin: float = 0.0
    order_imbalance: float = 0.0
    trade_flow_imbalance: float = 0.0
    price_impact: float = 0.0
    realized_spread: float = 0.0
    effective_spread: float = 0.0
    quoted_spread: float = 0.0
    depth_imbalance: float = 0.0
    volume_synchronized_pressure: float = 0.0

    def to_array(self) -> np.ndarray:
        """Convert to numpy array for ML input"""
        return np.array([
            self.vpin,
            self.order_imbalance,
            self.trade_flow_imbalance,
            self.price_impact,
            self.realized_spread,
            self.effective_spread,
            self.quoted_spread,
            self.depth_imbalance,
            self.volume_synchronized_pressure
        ])


class BulkVolumeClassifier(nn.Module):
    """
    Neural network for classifying bulk volume from order book data

    Uses deep learning to classify large trades as informed vs uninformed
    """

    def __init__(self, input_dim: int = 20, hidden_dim: int = 64):
        super().__init__()

        self.classifier = nn.Sequential(
            nn.Linear(input_dim, hidden_dim),
            nn.ReLU(),
            nn.Dropout(0.2),
            nn.Linear(hidden_dim, hidden_dim // 2),
            nn.ReLU(),
            nn.Linear(hidden_dim // 2, 2)  # Binary classification: informed vs uninformed
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """Forward pass for bulk volume classification"""
        return self.classifier(x)


@numba.jit(nopython=True, parallel=True)
def calculate_vpin_numba(volume_buckets: np.ndarray, buy_volume_buckets: np.ndarray,
                        sell_volume_buckets: np.ndarray, window_size: int) -> np.ndarray:
    """
    Numba-optimized VPIN calculation

    Args:
        volume_buckets: Array of volume buckets
        buy_volume_buckets: Array of buy volumes per bucket
        sell_volume_buckets: Array of sell volumes per bucket
        window_size: Rolling window size for VPIN calculation

    Returns:
        Array of VPIN values
    """

    n_buckets = len(volume_buckets)
    vpin_values = np.zeros(n_buckets)

    for i in range(window_size - 1, n_buckets):
        # Calculate imbalance over the window
        total_buy_volume = np.sum(buy_volume_buckets[i - window_size + 1:i + 1])
        total_sell_volume = np.sum(sell_volume_buckets[i - window_size + 1:i + 1])

        # VPIN formula: |Buy - Sell| / (Buy + Sell)
        total_volume = total_buy_volume + total_sell_volume
        if total_volume > 0:
            imbalance = abs(total_buy_volume - total_sell_volume) / total_volume
            vpin_values[i] = imbalance
        else:
            vpin_values[i] = 0.0

    return vpin_values


class GPUVPINCalculator:
    """
    GPU-accelerated VPIN calculator using RTX 5070 Ti

    Optimizes VPIN calculations for real-time HFT applications
    """

    def __init__(self, config: VPINConfig):
        self.config = config
        self.device = torch.device('cuda' if torch.cuda.is_available() and config.gpu_acceleration else 'cpu')

        # Initialize bulk volume classifier
        self.bulk_classifier = BulkVolumeClassifier().to(self.device)

        # GPU streams for parallel processing
        self.streams = [torch.cuda.current_stream(self.device) for _ in range(4)]

        # Pre-allocated GPU tensors for efficiency
        self._preallocate_tensors()

        logger.info(f"GPU VPIN Calculator initialized on {self.device}")

    def _preallocate_tensors(self):
        """Pre-allocate GPU tensors for performance"""

        self.max_batch_size = 1024
        self.feature_dim = 20

        # Pre-allocate feature tensors
        self.feature_buffer = torch.zeros(
            (self.max_batch_size, self.feature_dim),
            dtype=torch.float32,
            device=self.device
        )

        # Pre-allocate volume buckets
        self.volume_buffer = torch.zeros(
            (self.max_batch_size,),
            dtype=torch.float32,
            device=self.device
        )

        self.buy_volume_buffer = torch.zeros(
            (self.max_batch_size,),
            dtype=torch.float32,
            device=self.device
        )

        self.sell_volume_buffer = torch.zeros(
            (self.max_batch_size,),
            dtype=torch.float32,
            device=self.device
        )

    async def calculate_vpin_gpu(self, trades_df: pd.DataFrame, order_book_df: pd.DataFrame) -> VPINResult:
        """
        Calculate VPIN using GPU acceleration

        Args:
            trades_df: DataFrame with trade data
            order_book_df: DataFrame with order book data

        Returns:
            VPINResult with calculated metrics
        """

        start_time = datetime.now()

        try:
            # Classify bulk volume using GPU
            bulk_classification = await self._classify_bulk_volume_gpu(trades_df, order_book_df)

            # Calculate volume buckets
            volume_buckets, buy_buckets, sell_buckets = self._create_volume_buckets_gpu(
                trades_df, bulk_classification
            )

            # Calculate VPIN using optimized kernel
            vpin_values = await self._calculate_vpin_kernel_gpu(volume_buckets, buy_buckets, sell_buckets)

            # Calculate additional microstructure features
            microstructure_features = await self._calculate_microstructure_features_gpu(
                trades_df, order_book_df, vpin_values
            )

            # Create result
            result = VPINResult(
                timestamp=datetime.now(),
                symbol=trades_df['symbol'].iloc[0] if 'symbol' in trades_df.columns else 'UNKNOWN',
                vpin=float(vpin_values[-1]) if len(vpin_values) > 0 else 0.0,
                imbalance=float(microstructure_features.order_imbalance),
                bulk_volume_ratio=float(bulk_classification['bulk_ratio']),
                order_flow_imbalance=float(microstructure_features.trade_flow_imbalance),
                price_impact=float(microstructure_features.price_impact),
                confidence_score=self._calculate_confidence_score(vpin_values, trades_df)
            )

            # Check latency requirement
            latency = (datetime.now() - start_time).total_seconds() * 1000
            if latency > self.config.max_latency_ms:
                logger.warning(".1f")

            return result

        except Exception as e:
            logger.error(f"GPU VPIN calculation failed: {str(e)}")
            # Fallback to CPU calculation
            return await self._calculate_vpin_cpu_fallback(trades_df, order_book_df)

    async def _classify_bulk_volume_gpu(self, trades_df: pd.DataFrame,
                                       order_book_df: pd.DataFrame) -> Dict[str, Any]:
        """Classify bulk volume using GPU-accelerated neural network"""

        # Extract features for classification
        features = self._extract_bulk_features(trades_df, order_book_df)

        if len(features) == 0:
            return {'bulk_ratio': 0.0, 'classifications': []}

        # Convert to tensor
        feature_tensor = torch.FloatTensor(features).to(self.device)

        # Batch processing
        batch_size = min(self.config.batch_size, len(feature_tensor))
        classifications = []

        with torch.no_grad():
            for i in range(0, len(feature_tensor), batch_size):
                batch = feature_tensor[i:i + batch_size]
                outputs = self.bulk_classifier(batch)
                preds = torch.argmax(outputs, dim=1)
                classifications.extend(preds.cpu().numpy())

        # Calculate bulk volume ratio
        bulk_trades = sum(1 for pred in classifications if pred == 1)  # Informed trades
        bulk_ratio = bulk_trades / len(classifications) if classifications else 0.0

        return {
            'bulk_ratio': bulk_ratio,
            'classifications': classifications
        }

    def _extract_bulk_features(self, trades_df: pd.DataFrame, order_book_df: pd.DataFrame) -> np.ndarray:
        """Extract features for bulk volume classification"""

        features = []

        for _, trade in trades_df.iterrows():
            trade_features = []

            # Volume-based features
            trade_features.append(trade.get('size', 0) / self.config.volume_bucket_size)

            # Price impact features
            price_change = abs(trade.get('price', 0) - trade.get('prev_price', trade.get('price', 0)))
            trade_features.append(price_change / trade.get('price', 1))

            # Order book imbalance at trade time
            if not order_book_df.empty:
                # Simplified order book features
                bid_ask_spread = trade.get('ask_price', trade.get('price', 1)) - trade.get('bid_price', trade.get('price', 1))
                trade_features.append(bid_ask_spread / trade.get('price', 1))

                # Depth imbalance (simplified)
                bid_depth = sum(order_book_df.get('bid_size', [1]))
                ask_depth = sum(order_book_df.get('ask_size', [1]))
                depth_imbalance = (bid_depth - ask_depth) / (bid_depth + ask_depth + 1)
                trade_features.append(depth_imbalance)

            # Time-based features
            trade_features.append(trade.get('time_since_last_trade', 0))

            # Pad to fixed size
            while len(trade_features) < 20:
                trade_features.append(0.0)

            features.append(trade_features[:20])

        return np.array(features)

    async def _calculate_vpin_kernel_gpu(self, volume_buckets: torch.Tensor,
                                        buy_buckets: torch.Tensor,
                                        sell_buckets: torch.Tensor) -> torch.Tensor:
        """Calculate VPIN using GPU kernel"""

        # This would use a custom CUDA kernel for maximum performance
        # For now, use PyTorch operations

        window_size = self.config.vpin_window_size

        # Calculate rolling imbalances
        rolling_buy = torch.cumsum(buy_buckets, dim=0)
        rolling_sell = torch.cumsum(sell_buckets, dim=0)

        # Use convolution for efficient rolling window calculation
        kernel = torch.ones(window_size, device=self.device)

        rolling_buy_sum = torch.conv1d(
            rolling_buy.unsqueeze(0).unsqueeze(0),
            kernel.unsqueeze(0).unsqueeze(0),
            padding=window_size-1
        ).squeeze()

        rolling_sell_sum = torch.conv1d(
            rolling_sell.unsqueeze(0).unsqueeze(0),
            kernel.unsqueeze(0).unsqueeze(0),
            padding=window_size-1
        ).squeeze()

        # Calculate VPIN
        total_volume = rolling_buy_sum + rolling_sell_sum
        imbalance = torch.abs(rolling_buy_sum - rolling_sell_sum)
        vpin = torch.where(total_volume > 0, imbalance / total_volume, torch.zeros_like(total_volume))

        return vpin

    async def _calculate_microstructure_features_gpu(self, trades_df: pd.DataFrame,
                                                    order_book_df: pd.DataFrame,
                                                    vpin_values: torch.Tensor) -> MarketMicrostructureFeatures:
        """Calculate comprehensive microstructure features"""

        features = MarketMicrostructureFeatures()

        # VPIN
        features.vpin = float(vpin_values[-1]) if len(vpin_values) > 0 else 0.0

        # Order imbalance from order book
        if not order_book_df.empty:
            bid_sizes = order_book_df.get('bid_size', [1] * len(order_book_df))
            ask_sizes = order_book_df.get('ask_size', [1] * len(order_book_df))

            total_bid = sum(bid_sizes)
            total_ask = sum(ask_sizes)
            total_depth = total_bid + total_ask

            if total_depth > 0:
                features.order_imbalance = (total_bid - total_ask) / total_depth

        # Trade flow imbalance
        if not trades_df.empty:
            buy_trades = trades_df[trades_df.get('side', '') == 'buy']['size'].sum()
            sell_trades = trades_df[trades_df.get('side', '') == 'sell']['size'].sum()
            total_trades = buy_trades + sell_trades

            if total_trades > 0:
                features.trade_flow_imbalance = (buy_trades - sell_trades) / total_trades

        # Price impact (simplified Kyle's lambda)
        if not trades_df.empty:
            price_changes = trades_df['price'].pct_change().fillna(0)
            volume_signed = trades_df.apply(
                lambda x: x['size'] if x.get('side') == 'buy' else -x['size'], axis=1
            )

            # Simple price impact model
            if len(volume_signed) > 1 and len(price_changes) > 1:
                covariance = np.cov(volume_signed, price_changes)[0, 1]
                variance = np.var(volume_signed)
                if variance > 0:
                    features.price_impact = abs(covariance / variance)

        return features

    def _calculate_confidence_score(self, vpin_values: torch.Tensor, trades_df: pd.DataFrame) -> float:
        """Calculate confidence score for VPIN measurement"""

        if len(vpin_values) < 10:
            return 0.0

        # Confidence based on VPIN stability
        vpin_std = float(torch.std(vpin_values[-10:]))
        stability_score = max(0, 1 - vpin_std * 10)  # Higher stability = higher confidence

        # Confidence based on sample size
        sample_size = len(trades_df)
        size_score = min(1.0, sample_size / 1000)  # Full confidence with 1000+ samples

        # Combined confidence
        confidence = (stability_score + size_score) / 2

        return confidence

    async def _calculate_vpin_cpu_fallback(self, trades_df: pd.DataFrame,
                                          order_book_df: pd.DataFrame) -> VPINResult:
        """CPU fallback for VPIN calculation"""

        logger.warning("Using CPU fallback for VPIN calculation")

        # Simple VPIN calculation without GPU acceleration
        if trades_df.empty:
            return VPINResult(
                timestamp=datetime.now(),
                symbol='UNKNOWN',
                vpin=0.0,
                imbalance=0.0,
                bulk_volume_ratio=0.0,
                order_flow_imbalance=0.0,
                price_impact=0.0,
                confidence_score=0.0
            )

        # Basic volume imbalance calculation
        buy_volume = trades_df[trades_df.get('side') == 'buy']['size'].sum()
        sell_volume = trades_df[trades_df.get('side') == 'sell']['size'].sum()
        total_volume = buy_volume + sell_volume

        vpin = abs(buy_volume - sell_volume) / total_volume if total_volume > 0 else 0.0

        return VPINResult(
            timestamp=datetime.now(),
            symbol=trades_df['symbol'].iloc[0] if 'symbol' in trades_df.columns else 'UNKNOWN',
            vpin=vpin,
            imbalance=vpin,  # Simplified
            bulk_volume_ratio=0.5,  # Placeholder
            order_flow_imbalance=vpin,
            price_impact=0.0,
            confidence_score=0.5
        )


class RealTimeVPINProcessor:
    """
    Real-time VPIN processor for live trading

    Processes streaming trade and order book data for real-time VPIN calculation
    """

    def __init__(self, config: VPINConfig):
        self.config = config
        self.vpin_calculator = GPUVPINCalculator(config)

        # Data buffers
        self.trade_buffer: List[Dict[str, Any]] = []
        self.order_book_buffer: Dict[str, pd.DataFrame] = {}

        # Results cache
        self.vpin_cache: Dict[str, VPINResult] = {}
        self.last_update: Dict[str, datetime] = {}

        # Alert system
        self.alerts: List[Dict[str, Any]] = []

        # Monitoring
        self.processing_stats = {
            'total_calculations': 0,
            'average_latency_ms': 0.0,
            'alerts_triggered': 0
        }

    async def start_real_time_processing(self):
        """Start real-time VPIN processing"""

        logger.info("Starting real-time VPIN processing")

        while True:
            try:
                # Process buffered data
                await self._process_buffered_data()

                # Check for alerts
                self._check_alerts()

                # Update monitoring stats
                self._update_stats()

                # Sleep for update interval
                await asyncio.sleep(self.config.update_interval_seconds)

            except Exception as e:
                logger.error(f"Real-time processing error: {str(e)}")
                await asyncio.sleep(1.0)

    async def add_trade_data(self, symbol: str, trade_data: Dict[str, Any]):
        """Add real-time trade data"""

        self.trade_buffer.append({
            'symbol': symbol,
            'data': trade_data,
            'timestamp': datetime.now()
        })

        # Limit buffer size
        if len(self.trade_buffer) > 10000:
            self.trade_buffer = self.trade_buffer[-5000:]  # Keep last 5000 trades

    async def add_order_book_data(self, symbol: str, order_book_data: Dict[str, Any]):
        """Add real-time order book data"""

        # Convert to DataFrame for processing
        bids = order_book_data.get('bids', [])
        asks = order_book_data.get('asks', [])

        df_data = []
        for price, size in bids[:self.config.order_book_depth]:
            df_data.append({'side': 'bid', 'price': price, 'size': size})

        for price, size in asks[:self.config.order_book_depth]:
            df_data.append({'side': 'ask', 'price': price, 'size': size})

        self.order_book_buffer[symbol] = pd.DataFrame(df_data)

    async def _process_buffered_data(self):
        """Process buffered data and calculate VPIN"""

        if not self.trade_buffer:
            return

        # Group trades by symbol
        symbol_trades = {}
        for trade in self.trade_buffer:
            symbol = trade['symbol']
            if symbol not in symbol_trades:
                symbol_trades[symbol] = []
            symbol_trades[symbol].append(trade['data'])

        # Calculate VPIN for each symbol
        for symbol, trades in symbol_trades.items():
            try:
                # Convert to DataFrame
                trades_df = pd.DataFrame(trades)
                order_book_df = self.order_book_buffer.get(symbol, pd.DataFrame())

                # Calculate VPIN
                vpin_result = await self.vpin_calculator.calculate_vpin_gpu(trades_df, order_book_df)

                # Cache result
                self.vpin_cache[symbol] = vpin_result
                self.last_update[symbol] = datetime.now()

                self.processing_stats['total_calculations'] += 1

            except Exception as e:
                logger.error(f"VPIN calculation failed for {symbol}: {str(e)}")

        # Clear processed data
        self.trade_buffer.clear()

    def _check_alerts(self):
        """Check for VPIN-based alerts"""

        for symbol, vpin_result in self.vpin_cache.items():
            # VPIN threshold alert
            if vpin_result.vpin > self.config.vpin_alert_threshold:
                alert = {
                    'timestamp': datetime.now(),
                    'symbol': symbol,
                    'type': 'vpin_threshold',
                    'message': f'High VPIN detected: {vpin_result.vpin:.3f}',
                    'severity': 'warning' if vpin_result.vpin < 0.2 else 'critical'
                }
                self.alerts.append(alert)
                self.processing_stats['alerts_triggered'] += 1

                logger.warning(f"VPIN Alert for {symbol}: {vpin_result.vpin:.3f}")

    def _update_stats(self):
        """Update processing statistics"""

        # Simple moving average for latency
        if hasattr(self, '_latency_measurements'):
            self.processing_stats['average_latency_ms'] = np.mean(self._latency_measurements[-100:])
        else:
            self._latency_measurements = []

    def get_vpin_data(self, symbol: str) -> Optional[VPINResult]:
        """Get latest VPIN data for symbol"""

        return self.vpin_cache.get(symbol)

    def get_alerts(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get recent alerts"""

        return self.alerts[-limit:] if self.alerts else []

    def get_processing_stats(self) -> Dict[str, Any]:
        """Get processing statistics"""

        return self.processing_stats.copy()


# Convenience functions
def create_vpin_calculator(config: VPINConfig = None) -> GPUVPINCalculator:
    """Create VPIN calculator instance"""
    return GPUVPINCalculator(config or VPINConfig())


def create_real_time_vpin_processor(config: VPINConfig = None) -> RealTimeVPINProcessor:
    """Create real-time VPIN processor instance"""
    return RealTimeVPINProcessor(config or VPINConfig())


async def calculate_vpin_for_symbol(symbol: str, trades_df: pd.DataFrame,
                                   order_book_df: pd.DataFrame,
                                   config: VPINConfig = None) -> VPINResult:
    """Convenience function to calculate VPIN for a symbol"""

    calculator = create_vpin_calculator(config)
    return await calculator.calculate_vpin_gpu(trades_df, order_book_df)


def get_vpin_features(vpin_result: VPINResult) -> MarketMicrostructureFeatures:
    """Extract microstructure features from VPIN result"""

    features = MarketMicrostructureFeatures()
    features.vpin = vpin_result.vpin
    features.order_imbalance = vpin_result.imbalance
    features.trade_flow_imbalance = vpin_result.order_flow_imbalance
    features.price_impact = vpin_result.price_impact

    return features
