"""
Trading Environment for RL
Gymnasium-compatible environment for training trading agents with PPO.
"""

import gymnasium as gym
from gymnasium import spaces
import numpy as np
import logging
from typing import Optional, Dict, Any, Tuple

logger = logging.getLogger(__name__)


class TradingEnv(gym.Env):
    """
    Custom Gymnasium environment for crypto trading.
    
    Observation Space:
        - price_change: Normalized price change
        - volume_ratio: Volume relative to average
        - position: Current position (-1, 0, +1)
        - pnl: Cumulative PnL
        - volatility: Recent volatility
        
    Action Space:
        - 0: HOLD
        - 1: BUY
        - 2: SELL
        - 3: CLOSE
    """

    metadata = {"render_modes": ["human"]}

    def __init__(
        self,
        initial_balance: float = 10000.0,
        max_position_size: float = 1.0,
        transaction_cost: float = 0.001,
        data: Optional[np.ndarray] = None,
        window_size: int = 30,
    ):
        super().__init__()

        self.initial_balance = initial_balance
        self.max_position_size = max_position_size
        self.transaction_cost = transaction_cost
        self.window_size = window_size

        # Market data: [timestamp, open, high, low, close, volume]
        self.data = data if data is not None else self._generate_synthetic_data()
        self.current_step = 0
        self.max_steps = len(self.data) - window_size - 1

        # State
        self.balance = initial_balance
        self.position = 0.0  # -1 to +1
        self.entry_price = 0.0
        self.total_pnl = 0.0
        self.trades = []

        # Spaces
        # Observation: [price_changes(30), volume_ratios(30), position, pnl, volatility]
        obs_dim = window_size * 2 + 3
        self.observation_space = spaces.Box(
            low=-np.inf, high=np.inf, shape=(obs_dim,), dtype=np.float32
        )
        self.action_space = spaces.Discrete(4)  # HOLD, BUY, SELL, CLOSE

    def _generate_synthetic_data(self, length: int = 1000) -> np.ndarray:
        """Generate synthetic market data for training."""
        np.random.seed(42)
        prices = [100.0]
        volumes = []

        for _ in range(length - 1):
            # Random walk with drift
            change = np.random.normal(0.0001, 0.02)
            prices.append(prices[-1] * (1 + change))
            volumes.append(np.random.uniform(1000, 10000))

        volumes.append(volumes[-1])

        return np.array(
            [[i, p, p * 1.01, p * 0.99, p, v] for i, (p, v) in enumerate(zip(prices, volumes))]
        )

    def reset(
        self, *, seed: Optional[int] = None, options: Optional[Dict[str, Any]] = None
    ) -> Tuple[np.ndarray, Dict[str, Any]]:
        super().reset(seed=seed)

        self.current_step = self.window_size
        self.balance = self.initial_balance
        self.position = 0.0
        self.entry_price = 0.0
        self.total_pnl = 0.0
        self.trades = []

        return self._get_observation(), {}

    def step(self, action: int) -> Tuple[np.ndarray, float, bool, bool, Dict[str, Any]]:
        current_price = self.data[self.current_step, 4]  # Close price
        reward = 0.0

        # Execute action
        if action == 1:  # BUY
            if self.position <= 0:
                self._close_position(current_price)
                self._open_position(1.0, current_price)
                reward -= self.transaction_cost * current_price

        elif action == 2:  # SELL
            if self.position >= 0:
                self._close_position(current_price)
                self._open_position(-1.0, current_price)
                reward -= self.transaction_cost * current_price

        elif action == 3:  # CLOSE
            pnl = self._close_position(current_price)
            reward += pnl - self.transaction_cost * current_price

        # Calculate unrealized PnL for reward shaping
        if self.position != 0:
            unrealized = (current_price - self.entry_price) * self.position
            reward += unrealized * 0.01  # Small reward for holding profitable positions

        # Advance step
        self.current_step += 1
        done = self.current_step >= self.max_steps
        truncated = False

        # Penalize excessive drawdown
        if self.balance < self.initial_balance * 0.5:
            reward -= 100
            done = True

        info = {
            "balance": self.balance,
            "position": self.position,
            "total_pnl": self.total_pnl,
            "trades": len(self.trades),
        }

        return self._get_observation(), reward, done, truncated, info

    def _get_observation(self) -> np.ndarray:
        """Build observation vector."""
        window_data = self.data[self.current_step - self.window_size : self.current_step]

        # Price changes
        prices = window_data[:, 4]
        price_changes = np.diff(prices) / prices[:-1]
        price_changes = np.concatenate([[0], price_changes])

        # Volume ratios
        volumes = window_data[:, 5]
        avg_volume = np.mean(volumes) + 1e-8
        volume_ratios = volumes / avg_volume

        # Volatility
        volatility = np.std(price_changes)

        # Handle NaN
        price_changes = np.nan_to_num(price_changes, nan=0.0)
        volume_ratios = np.nan_to_num(volume_ratios, nan=1.0)
        volatility = 0.0 if np.isnan(volatility) else volatility

        obs = np.concatenate(
            [
                price_changes,
                volume_ratios,
                [self.position, self.total_pnl / self.initial_balance, volatility],
            ]
        )

        return obs.astype(np.float32)

    def _open_position(self, size: float, price: float):
        """Open a new position."""
        self.position = size * self.max_position_size
        self.entry_price = price

    def _close_position(self, price: float) -> float:
        """Close current position and return PnL."""
        if self.position == 0:
            return 0.0

        pnl = (price - self.entry_price) * self.position * self.initial_balance * 0.1
        self.total_pnl += pnl
        self.balance += pnl

        self.trades.append(
            {
                "entry": self.entry_price,
                "exit": price,
                "position": self.position,
                "pnl": pnl,
            }
        )

        self.position = 0.0
        self.entry_price = 0.0

        return pnl

    def render(self):
        print(
            f"Step: {self.current_step} | "
            f"Balance: ${self.balance:.2f} | "
            f"Position: {self.position:.2f} | "
            f"PnL: ${self.total_pnl:.2f}"
        )
