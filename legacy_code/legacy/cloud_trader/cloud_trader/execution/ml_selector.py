"""
ML Selector Module
Uses XGBoost (LightGBM) to select the optimal execution algorithm based on market conditions.
"""

import logging
import pandas as pd
import lightgbm as lgb
import os
import joblib
from typing import Dict, Any, List

logger = logging.getLogger(__name__)

class AlgoSelector:
    """
    Predicts optimal execution algorithm using an ML model.
    """

    def __init__(self, model_path: str = "models/algo_selector.pkl"):
        self.model_path = model_path
        self.model = None
        self._load_model()
        
        # Label encoding for algorithms
        self.label_map = {
            0: "twap",
            1: "vwap", 
            2: "iceberg",
            3: "sniper",
            4: "market"
        }
        self.reverse_label_map = {v: k for k, v in self.label_map.items()}

    def _load_model(self):
        """Load trained model from disk."""
        if os.path.exists(self.model_path):
            try:
                self.model = joblib.load(self.model_path)
                logger.info(f"Loaded ML model from {self.model_path}")
            except Exception as e:
                logger.error(f"Failed to load model: {e}")
                self.model = None
        else:
            logger.warning(f"No ML model found at {self.model_path}. Using heuristics.")
            self.model = None

    def train(self, historical_data: pd.DataFrame):
        """
        Train the model on historical execution data.
        Data format: features (volatility, spread, volume, size_pct) -> target (best_algo)
        """
        if historical_data.empty:
            logger.warning("No data to train on.")
            return

        # Feature engineering
        features = ["volatility", "spread_pct", "volume_roll_avg", "order_size_pct", "urgency_score"]
        target = "best_algo_idx"
        
        X = historical_data[features]
        y = historical_data[target]
        
        # Train LightGBM
        params = {
            'objective': 'multiclass',
            'num_class': 5,
            'metric': 'multi_logloss',
            'verbosity': -1
        }
        
        train_data = lgb.Dataset(X, label=y)
        self.model = lgb.train(params, train_data, num_boost_round=100)
        
        # Save model
        os.makedirs(os.path.dirname(self.model_path), exist_ok=True)
        joblib.dump(self.model, self.model_path)
        logger.info("Model trained and saved.")

    def predict(self, market_state: Dict[str, float]) -> str:
        """
        Predict optimal algorithm index.
        market_state: {volatility, spread_pct, volume_roll_avg, order_size_pct, urgency_score}
        """
        if not self.model:
            return self._heuristic_fallback(market_state)

        try:
            # Prepare features in correct order
            features = [
                market_state.get("volatility", 0.0),
                market_state.get("spread_pct", 0.0),
                market_state.get("volume_roll_avg", 0.0),
                market_state.get("order_size_pct", 0.0),
                market_state.get("urgency_score", 0.0)
            ]
            
            # Predict
            pred_prob = self.model.predict([features])[0] # Returns probabilities
            pred_idx = pred_prob.argmax()
            
            return self.label_map.get(pred_idx, "vwap")
            
        except Exception as e:
            logger.error(f"Prediction failed: {e}")
            return self._heuristic_fallback(market_state)

    def _heuristic_fallback(self, state: Dict[str, float]) -> str:
        """Fallback logic if model is missing or fails."""
        urgency = state.get("urgency_score", 0.0)
        volatility = state.get("volatility", 0.0)
        size = state.get("order_size_pct", 0.0)
        
        # 1. Critical Urgency -> TWAP/Market
        if urgency > 0.8:
            return "twap"
            
        # 2. Large Size + Low Volatility -> Iceberg
        if size > 0.05 and volatility < 0.02:
            return "iceberg"
            
        # 3. High Volatility -> Sniper (limit orders)
        if volatility > 0.05:
            return "sniper"
            
        # Default -> VWAP
        return "vwap"
