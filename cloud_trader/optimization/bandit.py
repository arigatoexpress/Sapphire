from __future__ import annotations

import random
from collections import defaultdict
from typing import DefaultDict


class EpsilonGreedyBandit:
    """Adaptive epsilon-greedy bandit for routing trade decisions."""

    def __init__(self, epsilon: float = 0.1, min_reward: float = -1.0) -> None:
        self._epsilon = epsilon
        self._min_reward = min_reward
        self._counts: DefaultDict[str, int] = defaultdict(int)
        self._values: DefaultDict[str, float] = defaultdict(float)

    def allow(self, symbol: str) -> bool:
        if random.random() < self._epsilon:
            return True
        return self._values[symbol] >= self._min_reward

    def update(self, symbol: str, reward: float) -> None:
        # Reward clipping keeps the bandit stable on outliers
        reward = max(min(reward, 10.0), -10.0)
        self._counts[symbol] += 1
        count = self._counts[symbol]
        prev = self._values[symbol]
        self._values[symbol] = prev + (reward - prev) / count


__all__ = ["EpsilonGreedyBandit"]

