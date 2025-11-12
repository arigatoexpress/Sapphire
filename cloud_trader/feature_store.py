"""Feature store integration for ML-ready features."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from .config import Settings, get_settings

logger = logging.getLogger(__name__)

try:
    from feast import FeatureStore
    FEAST_AVAILABLE = True
except ImportError:
    FEAST_AVAILABLE = False
    logger.warning("Feast not available, feature store disabled")


class TradingFeatureStore:
    """Feature store manager for trading features."""
    
    def __init__(self, settings: Optional[Settings] = None):
        self._settings = settings or get_settings()
        self._store: Optional[FeatureStore] = None
        self._initialized = False
    
    async def initialize(self) -> None:
        """Initialize feature store."""
        if not FEAST_AVAILABLE:
            logger.warning("Feast not available, feature store disabled")
            return
        
        try:
            # Try to load feature store from repo
            repo_path = "infra/data_toolkit/feast_repo"
            import os
            if os.path.exists(repo_path):
                self._store = FeatureStore(repo_path=repo_path)
                self._initialized = True
                logger.info("Feature store initialized")
            else:
                logger.warning(f"Feature store repo not found at {repo_path}")
        except Exception as e:
            logger.warning(f"Failed to initialize feature store: {e}")
    
    async def push_market_features(
        self,
        symbol: str,
        timestamp: datetime,
        price: float,
        volume_24h: Optional[float] = None,
        change_24h: Optional[float] = None,
        rolling_volatility: Optional[float] = None,
        funding_rate: Optional[float] = None,
        open_interest: Optional[float] = None,
        high_24h: Optional[float] = None,
        low_24h: Optional[float] = None,
    ) -> None:
        """Push market features to feature store."""
        if not self._initialized or not self._store:
            return
        
        try:
            import pandas as pd
            
            features_df = pd.DataFrame([{
                "symbol": symbol,
                "event_time": timestamp,
                "price": price,
                "volume_24h": volume_24h,
                "change_24h": change_24h,
                "rolling_volatility": rolling_volatility,
                "funding_rate": funding_rate,
                "open_interest": open_interest,
                "high_24h": high_24h,
                "low_24h": low_24h,
            }])
            
            # Push to online store
            self._store.push("market_features", features_df)
            logger.debug(f"Pushed market features for {symbol}")
        except Exception as e:
            logger.warning(f"Failed to push market features: {e}")
    
    async def push_agent_features(
        self,
        agent_id: str,
        timestamp: datetime,
        total_trades: int = 0,
        total_pnl: float = 0.0,
        exposure: float = 0.0,
        equity: float = 0.0,
        win_rate: Optional[float] = None,
        sharpe_ratio: Optional[float] = None,
        max_drawdown: Optional[float] = None,
        active_positions: int = 0,
    ) -> None:
        """Push agent performance features to feature store."""
        if not self._initialized or not self._store:
            return
        
        try:
            import pandas as pd
            
            features_df = pd.DataFrame([{
                "agent": agent_id,
                "event_time": timestamp,
                "total_trades": total_trades,
                "total_pnl": total_pnl,
                "exposure": exposure,
                "equity": equity,
                "win_rate": win_rate,
                "sharpe_ratio": sharpe_ratio,
                "max_drawdown": max_drawdown,
                "active_positions": active_positions,
            }])
            
            # Push to online store
            self._store.push("agent_features", features_df)
            logger.debug(f"Pushed agent features for {agent_id}")
        except Exception as e:
            logger.warning(f"Failed to push agent features: {e}")
    
    async def push_trading_signal(
        self,
        symbol: str,
        timestamp: datetime,
        strategy: str,
        signal_direction: str,
        confidence: float,
        position_size: float,
        kelly_fraction: Optional[float] = None,
        atr_stop_loss: Optional[float] = None,
        take_profit_target: Optional[float] = None,
    ) -> None:
        """Push trading signal features to feature store."""
        if not self._initialized or not self._store:
            return
        
        try:
            import pandas as pd
            
            features_df = pd.DataFrame([{
                "symbol": symbol,
                "event_time": timestamp,
                "strategy": strategy,
                "signal_direction": signal_direction,
                "confidence": confidence,
                "position_size": position_size,
                "kelly_fraction": kelly_fraction,
                "atr_stop_loss": atr_stop_loss,
                "take_profit_target": take_profit_target,
            }])
            
            # Push to online store
            self._store.push("trading_signals", features_df)
            logger.debug(f"Pushed trading signal for {symbol}")
        except Exception as e:
            logger.warning(f"Failed to push trading signal: {e}")
    
    async def get_features(
        self,
        entity_rows: List[Dict[str, Any]],
        features: List[str],
    ) -> Any:
        """Get features from feature store."""
        if not self._initialized or not self._store:
            return None
        
        try:
            import pandas as pd
            
            entity_df = pd.DataFrame(entity_rows)
            feature_df = self._store.get_online_features(
                features=features,
                entity_rows=entity_df.to_dict("records"),
            ).to_df()
            
            return feature_df
        except Exception as e:
            logger.warning(f"Failed to get features: {e}")
            return None

    def is_ready(self) -> bool:
        return self._initialized and self._store is not None


# Global feature store instance
_feature_store: Optional[TradingFeatureStore] = None


async def get_feature_store() -> TradingFeatureStore:
    """Get or create feature store instance."""
    global _feature_store
    if _feature_store is None:
        _feature_store = TradingFeatureStore()
        await _feature_store.initialize()
    return _feature_store

