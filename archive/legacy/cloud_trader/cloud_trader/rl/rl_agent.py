"""
RL Agent Module
PPO-based reinforcement learning agent for adaptive trading.
"""

import logging
import os
from typing import Optional, Dict, Any
import numpy as np

logger = logging.getLogger(__name__)

# Lazy imports to avoid dependency issues
_PPO = None
_TradingEnv = None


def _get_ppo():
    global _PPO
    if _PPO is None:
        try:
            from stable_baselines3 import PPO
            _PPO = PPO
        except ImportError:
            logger.error("stable-baselines3 not installed")
            return None
    return _PPO


def _get_trading_env():
    global _TradingEnv
    if _TradingEnv is None:
        from .trading_env import TradingEnv
        _TradingEnv = TradingEnv
    return _TradingEnv


class RLTradingAgent:
    """
    PPO-based RL agent for adaptive trading decisions.
    
    Features:
    - Train on historical or live data
    - Predict optimal actions (BUY/SELL/HOLD/CLOSE)
    - Avoid overfitting via entropy regularization
    """

    def __init__(
        self,
        model_path: str = "models/rl_trader.zip",
        learning_rate: float = 3e-4,
        n_steps: int = 2048,
        batch_size: int = 64,
        n_epochs: int = 10,
        gamma: float = 0.99,
        ent_coef: float = 0.01,  # Entropy coefficient to prevent overfitting
    ):
        self.model_path = model_path
        self.learning_rate = learning_rate
        self.n_steps = n_steps
        self.batch_size = batch_size
        self.n_epochs = n_epochs
        self.gamma = gamma
        self.ent_coef = ent_coef

        self.model = None
        self.env = None
        self._load_model()

    def _load_model(self):
        """Load trained model from disk if available."""
        PPO = _get_ppo()
        if PPO is None:
            return

        if os.path.exists(self.model_path):
            try:
                self.model = PPO.load(self.model_path)
                logger.info(f"Loaded RL model from {self.model_path}")
            except Exception as e:
                logger.warning(f"Failed to load model: {e}")
                self.model = None

    def train(
        self,
        data: Optional[np.ndarray] = None,
        total_timesteps: int = 100000,
        save: bool = True,
    ) -> Dict[str, float]:
        """
        Train the PPO agent.
        
        Args:
            data: Market data [timestamp, open, high, low, close, volume]
            total_timesteps: Training steps
            save: Save model after training
            
        Returns:
            Training metrics
        """
        PPO = _get_ppo()
        TradingEnv = _get_trading_env()

        if PPO is None or TradingEnv is None:
            return {"error": "Dependencies not available"}

        # Create environment
        self.env = TradingEnv(data=data)

        # Create or update model
        if self.model is None:
            self.model = PPO(
                "MlpPolicy",
                self.env,
                learning_rate=self.learning_rate,
                n_steps=self.n_steps,
                batch_size=self.batch_size,
                n_epochs=self.n_epochs,
                gamma=self.gamma,
                ent_coef=self.ent_coef,
                verbose=1,
            )
        else:
            self.model.set_env(self.env)

        # Train with divergence monitoring
        try:
            self.model.learn(
                total_timesteps=total_timesteps,
                progress_bar=True,
            )
        except Exception as e:
            logger.error(f"Training divergence: {e}")
            return {"error": str(e)}

        # Save model
        if save:
            os.makedirs(os.path.dirname(self.model_path), exist_ok=True)
            self.model.save(self.model_path)
            logger.info(f"Model saved to {self.model_path}")

        # Return metrics
        return {
            "total_timesteps": total_timesteps,
            "model_path": self.model_path,
        }

    def predict(self, observation: np.ndarray) -> int:
        """
        Predict action for given observation.
        
        Args:
            observation: Environment observation
            
        Returns:
            Action (0: HOLD, 1: BUY, 2: SELL, 3: CLOSE)
        """
        if self.model is None:
            logger.warning("No trained model, defaulting to HOLD")
            return 0

        action, _ = self.model.predict(observation, deterministic=True)
        return int(action)

    def action_to_signal(self, action: int) -> str:
        """Convert action index to trading signal."""
        mapping = {0: "HOLD", 1: "BUY", 2: "SELL", 3: "CLOSE"}
        return mapping.get(action, "HOLD")

    def evaluate(self, data: np.ndarray, episodes: int = 10) -> Dict[str, float]:
        """
        Evaluate agent performance.
        
        Returns:
            Performance metrics
        """
        TradingEnv = _get_trading_env()
        if TradingEnv is None or self.model is None:
            return {"error": "Model or env not available"}

        env = TradingEnv(data=data)
        total_rewards = []
        total_trades = []
        final_balances = []

        for _ in range(episodes):
            obs, _ = env.reset()
            done = False
            episode_reward = 0

            while not done:
                action = self.predict(obs)
                obs, reward, done, truncated, info = env.step(action)
                episode_reward += reward
                done = done or truncated

            total_rewards.append(episode_reward)
            total_trades.append(info.get("trades", 0))
            final_balances.append(info.get("balance", 0))

        return {
            "avg_reward": float(np.mean(total_rewards)),
            "std_reward": float(np.std(total_rewards)),
            "avg_trades": float(np.mean(total_trades)),
            "avg_final_balance": float(np.mean(final_balances)),
            "win_rate": sum(1 for b in final_balances if b > 10000) / len(final_balances),
        }
