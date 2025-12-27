"""Reinforcement learning strategies for trading with online learning capabilities."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import pickle
from collections import deque
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    import numpy as np
except ImportError:
    np = None

logger = logging.getLogger(__name__)


@dataclass
class Experience:
    """Single experience tuple for replay buffer."""

    state: np.ndarray
    action: int
    reward: float
    next_state: np.ndarray
    done: bool
    metadata: Dict[str, Any]


class ReplayBuffer:
    """Experience replay buffer for DQN training."""

    def __init__(self, capacity: int = 10000):
        self.buffer = deque(maxlen=capacity)

    def push(self, experience: Experience) -> None:
        """Add experience to buffer."""
        self.buffer.append(experience)

    def sample(self, batch_size: int) -> List[Experience]:
        """Sample random batch of experiences."""
        indices = np.random.choice(len(self.buffer), batch_size, replace=False)
        return [self.buffer[i] for i in indices]

    def __len__(self) -> int:
        return len(self.buffer)


class NeuralNetwork:
    """Simple neural network for Q-function approximation."""

    def __init__(self, input_size: int, hidden_size: int, output_size: int):
        self.input_size = input_size
        self.hidden_size = hidden_size
        self.output_size = output_size

        # Initialize weights with Xavier initialization
        self.W1 = np.random.randn(input_size, hidden_size) * np.sqrt(2.0 / input_size)
        self.b1 = np.zeros((1, hidden_size))
        self.W2 = np.random.randn(hidden_size, hidden_size) * np.sqrt(2.0 / hidden_size)
        self.b2 = np.zeros((1, hidden_size))
        self.W3 = np.random.randn(hidden_size, output_size) * np.sqrt(2.0 / hidden_size)
        self.b3 = np.zeros((1, output_size))

    def forward(self, x: np.ndarray) -> np.ndarray:
        """Forward pass through the network."""
        # ReLU activations for hidden layers
        z1 = np.dot(x, self.W1) + self.b1
        a1 = np.maximum(0, z1)  # ReLU

        z2 = np.dot(a1, self.W2) + self.b2
        a2 = np.maximum(0, z2)  # ReLU

        z3 = np.dot(a2, self.W3) + self.b3
        return z3  # Linear output for Q-values

    def backward(self, x: np.ndarray, target: np.ndarray, learning_rate: float = 0.001) -> float:
        """Backward pass with gradient descent."""
        batch_size = x.shape[0]

        # Forward pass to get activations
        z1 = np.dot(x, self.W1) + self.b1
        a1 = np.maximum(0, z1)

        z2 = np.dot(a1, self.W2) + self.b2
        a2 = np.maximum(0, z2)

        z3 = np.dot(a2, self.W3) + self.b3
        output = z3

        # Calculate loss (MSE)
        loss = np.mean((output - target) ** 2)

        # Backward pass
        dz3 = 2 * (output - target) / batch_size
        dW3 = np.dot(a2.T, dz3)
        db3 = np.sum(dz3, axis=0, keepdims=True)

        da2 = np.dot(dz3, self.W3.T)
        dz2 = da2 * (z2 > 0)  # ReLU derivative
        dW2 = np.dot(a1.T, dz2)
        db2 = np.sum(dz2, axis=0, keepdims=True)

        da1 = np.dot(dz2, self.W2.T)
        dz1 = da1 * (z1 > 0)  # ReLU derivative
        dW1 = np.dot(x.T, dz1)
        db1 = np.sum(dz1, axis=0, keepdims=True)

        # Update weights
        self.W3 -= learning_rate * dW3
        self.b3 -= learning_rate * db3
        self.W2 -= learning_rate * dW2
        self.b2 -= learning_rate * db2
        self.W1 -= learning_rate * dW1
        self.b1 -= learning_rate * db1

        return loss

    def save(self, path: str) -> None:
        """Save network weights."""
        weights = {
            "W1": self.W1,
            "b1": self.b1,
            "W2": self.W2,
            "b2": self.b2,
            "W3": self.W3,
            "b3": self.b3,
        }
        with open(path, "wb") as f:
            pickle.dump(weights, f)

    def load(self, path: str) -> None:
        """Load network weights."""
        with open(path, "rb") as f:
            weights = pickle.load(f)
        self.W1 = weights["W1"]
        self.b1 = weights["b1"]
        self.W2 = weights["W2"]
        self.b2 = weights["b2"]
        self.W3 = weights["W3"]
        self.b3 = weights["b3"]


class DQNAgent:
    """Deep Q-Network agent for discrete action trading."""

    def __init__(
        self,
        state_size: int = 10,
        action_size: int = 3,
        learning_rate: float = 0.001,
        gamma: float = 0.95,
    ):
        self.state_size = state_size
        self.action_size = action_size  # BUY, SELL, HOLD
        self.learning_rate = learning_rate
        self.gamma = gamma  # Discount factor
        self.epsilon = 1.0  # Exploration rate
        self.epsilon_min = 0.01
        self.epsilon_decay = 0.995

        # Neural networks
        self.q_network = NeuralNetwork(state_size, 128, action_size)
        self.target_network = NeuralNetwork(state_size, 128, action_size)
        self._update_target_network()

        # Experience replay
        self.memory = ReplayBuffer(capacity=10000)
        self.batch_size = 32
        self.update_frequency = 100
        self.steps = 0

        # Performance tracking
        self.total_reward = 0
        self.episode_rewards = []

    def _update_target_network(self) -> None:
        """Copy weights from main network to target network."""
        self.target_network.W1 = self.q_network.W1.copy()
        self.target_network.b1 = self.q_network.b1.copy()
        self.target_network.W2 = self.q_network.W2.copy()
        self.target_network.b2 = self.q_network.b2.copy()
        self.target_network.W3 = self.q_network.W3.copy()
        self.target_network.b3 = self.q_network.b3.copy()

    def act(self, state: np.ndarray, training: bool = True) -> int:
        """Select action using epsilon-greedy policy."""
        if training and np.random.random() < self.epsilon:
            return np.random.choice(self.action_size)

        q_values = self.q_network.forward(state.reshape(1, -1))
        return int(np.argmax(q_values))

    def remember(
        self,
        state: np.ndarray,
        action: int,
        reward: float,
        next_state: np.ndarray,
        done: bool,
        metadata: Dict[str, Any],
    ) -> None:
        """Store experience in replay buffer."""
        experience = Experience(state, action, reward, next_state, done, metadata)
        self.memory.push(experience)

    def replay(self) -> Optional[float]:
        """Train the network on a batch of experiences."""
        if len(self.memory) < self.batch_size:
            return None

        batch = self.memory.sample(self.batch_size)
        states = np.array([e.state for e in batch])
        actions = np.array([e.action for e in batch])
        rewards = np.array([e.reward for e in batch])
        next_states = np.array([e.next_state for e in batch])
        dones = np.array([e.done for e in batch])

        # Current Q-values
        current_q_values = self.q_network.forward(states)

        # Next Q-values from target network
        next_q_values = self.target_network.forward(next_states)
        max_next_q = np.max(next_q_values, axis=1)

        # Calculate targets
        targets = current_q_values.copy()
        for i in range(self.batch_size):
            if dones[i]:
                targets[i, actions[i]] = rewards[i]
            else:
                targets[i, actions[i]] = rewards[i] + self.gamma * max_next_q[i]

        # Train the network
        loss = self.q_network.backward(states, targets, self.learning_rate)

        # Update target network periodically
        self.steps += 1
        if self.steps % self.update_frequency == 0:
            self._update_target_network()

        # Decay epsilon
        if self.epsilon > self.epsilon_min:
            self.epsilon *= self.epsilon_decay

        return loss

    def calculate_reward(self, pnl_pct: float, position_held: bool) -> float:
        """Calculate reward based on P&L and position status."""
        # Base reward on profit/loss
        reward = pnl_pct / 100.0  # Normalize to reasonable range

        # Penalty for holding losing positions
        if position_held and pnl_pct < -0.5:
            reward -= 0.1

        # Bonus for profitable exits
        if not position_held and pnl_pct > 1.0:
            reward += 0.2

        return np.clip(reward, -1.0, 1.0)


class PPOAgent:
    """Proximal Policy Optimization agent for continuous control."""

    def __init__(
        self,
        state_size: int = 10,
        action_size: int = 1,
        learning_rate: float = 0.0003,
        gamma: float = 0.99,
    ):
        self.state_size = state_size
        self.action_size = action_size  # Continuous: position size [-1, 1]
        self.learning_rate = learning_rate
        self.gamma = gamma
        self.clip_ratio = 0.2  # PPO clipping parameter

        # Actor-Critic networks
        self.actor = NeuralNetwork(state_size, 64, action_size * 2)  # Mean and std
        self.critic = NeuralNetwork(state_size, 64, 1)  # Value function

        # Experience buffer
        self.states = []
        self.actions = []
        self.rewards = []
        self.values = []
        self.log_probs = []

    def act(self, state: np.ndarray) -> Tuple[float, float]:
        """Select action from policy distribution."""
        # Get mean and log_std from actor
        output = self.actor.forward(state.reshape(1, -1))
        mean = output[0, 0]
        log_std = output[0, 1]
        std = np.exp(log_std)

        # Sample from Gaussian
        action = np.random.normal(mean, std)
        action = np.clip(action, -1.0, 1.0)  # Clip to valid range

        # Calculate log probability
        log_prob = -0.5 * ((action - mean) / std) ** 2 - log_std - 0.5 * np.log(2 * np.pi)

        return float(action), float(log_prob)

    def remember(
        self, state: np.ndarray, action: float, reward: float, value: float, log_prob: float
    ) -> None:
        """Store experience."""
        self.states.append(state)
        self.actions.append(action)
        self.rewards.append(reward)
        self.values.append(value)
        self.log_probs.append(log_prob)

    def train(self) -> Tuple[float, float]:
        """Train actor and critic networks."""
        if len(self.states) < 32:
            return 0.0, 0.0

        # Convert to arrays
        states = np.array(self.states)
        actions = np.array(self.actions)
        rewards = np.array(self.rewards)
        values = np.array(self.values)
        old_log_probs = np.array(self.log_probs)

        # Calculate returns and advantages
        returns = self._calculate_returns(rewards)
        advantages = returns - values
        advantages = (advantages - advantages.mean()) / (advantages.std() + 1e-8)

        # PPO update
        for _ in range(4):  # Multiple epochs
            # Actor loss
            output = self.actor.forward(states)
            means = output[:, 0]
            log_stds = output[:, 1]
            stds = np.exp(log_stds)

            # Calculate new log probabilities
            new_log_probs = (
                -0.5 * ((actions - means) / stds) ** 2 - log_stds - 0.5 * np.log(2 * np.pi)
            )

            # Ratio for PPO
            ratio = np.exp(new_log_probs - old_log_probs)
            clipped_ratio = np.clip(ratio, 1 - self.clip_ratio, 1 + self.clip_ratio)

            # Actor loss
            actor_loss = -np.mean(np.minimum(ratio * advantages, clipped_ratio * advantages))

            # Critic loss
            value_pred = self.critic.forward(states).squeeze()
            critic_loss = np.mean((returns - value_pred) ** 2)

            # Update networks (simplified - in practice would use proper optimizer)
            # This is a placeholder for actual gradient updates

        # Clear buffers
        self.states.clear()
        self.actions.clear()
        self.rewards.clear()
        self.values.clear()
        self.log_probs.clear()

        return actor_loss, critic_loss

    def _calculate_returns(self, rewards: np.ndarray) -> np.ndarray:
        """Calculate discounted returns."""
        returns = np.zeros_like(rewards)
        running_return = 0

        for t in reversed(range(len(rewards))):
            running_return = rewards[t] + self.gamma * running_return
            returns[t] = running_return

        return returns


class RLStrategyManager:
    """Manages reinforcement learning strategies with online learning."""

    def __init__(self, models_dir: Optional[str] = None):
        if np is None:
            logger.warning("Numpy not found. RL strategies disabled.")
            self.training_enabled = False
            self.dqn_agent = None
            self.ppo_agent = None
            return

        default_dir = Path(os.environ.get("RL_MODELS_DIR", "/tmp/models/rl"))
        self.models_dir = Path(models_dir) if models_dir else default_dir
        self.models_dir.mkdir(parents=True, exist_ok=True)

        # Initialize agents
        self.dqn_agent = DQNAgent()
        self.ppo_agent = PPOAgent()

        # Load existing models if available
        self._load_models()

        # Training state
        self.last_states = {}
        self.last_actions = {}
        self.training_enabled = True

    def _load_models(self) -> None:
        """Load pre-trained models if available."""
        dqn_path = self.models_dir / "dqn_model.pkl"
        ppo_path = self.models_dir / "ppo_model.pkl"

        try:
            if dqn_path.exists():
                self.dqn_agent.q_network.load(str(dqn_path))
                logger.info("Loaded DQN model")
        except Exception as e:
            logger.warning(f"Failed to load DQN model: {e}")

        try:
            if ppo_path.exists():
                self.ppo_agent.actor.load(str(ppo_path))
                logger.info("Loaded PPO model")
        except Exception as e:
            logger.warning(f"Failed to load PPO model: {e}")

    def save_models(self) -> None:
        """Save trained models."""
        try:
            self.dqn_agent.q_network.save(str(self.models_dir / "dqn_model.pkl"))
            self.ppo_agent.actor.save(str(self.models_dir / "ppo_model.pkl"))
            logger.info("Saved RL models")
        except Exception as e:
            logger.error(f"Failed to save models: {e}")

    async def get_dqn_action(self, symbol: str, state: np.ndarray) -> Tuple[int, Dict[str, Any]]:
        """Get action from DQN agent."""
        action = self.dqn_agent.act(state, training=self.training_enabled)

        # Store state-action pair for learning
        if self.training_enabled:
            self.last_states[f"dqn_{symbol}"] = state
            self.last_actions[f"dqn_{symbol}"] = action

        metadata = {
            "q_values": self.dqn_agent.q_network.forward(state.reshape(1, -1)).tolist(),
            "epsilon": self.dqn_agent.epsilon,
            "total_experiences": len(self.dqn_agent.memory),
        }

        return action, metadata

    async def get_ppo_action(self, symbol: str, state: np.ndarray) -> Tuple[float, Dict[str, Any]]:
        """Get action from PPO agent."""
        action, log_prob = self.ppo_agent.act(state)

        # Calculate value for advantage estimation
        value = float(self.ppo_agent.critic.forward(state.reshape(1, -1))[0, 0])

        # Store for learning
        if self.training_enabled:
            self.last_states[f"ppo_{symbol}"] = {
                "state": state,
                "action": action,
                "value": value,
                "log_prob": log_prob,
            }

        metadata = {"action": action, "value": value, "log_prob": log_prob}

        return action, metadata

    async def update_with_reward(
        self, symbol: str, agent_type: str, reward: float, new_state: np.ndarray, done: bool
    ) -> None:
        """Update agent with reward from executed trade."""
        if not self.training_enabled:
            return

        key = f"{agent_type}_{symbol}"

        if agent_type == "dqn" and key in self.last_states:
            # Update DQN
            state = self.last_states[key]
            action = self.last_actions[key]

            self.dqn_agent.remember(state, action, reward, new_state, done, {"symbol": symbol})

            # Train if enough experiences
            loss = self.dqn_agent.replay()
            if loss is not None:
                logger.debug(f"DQN training loss: {loss:.4f}")

            # Clean up
            if done:
                del self.last_states[key]
                del self.last_actions[key]

        elif agent_type == "ppo" and key in self.last_states:
            # Update PPO
            data = self.last_states[key]
            self.ppo_agent.remember(
                data["state"], data["action"], reward, data["value"], data["log_prob"]
            )

            # Train periodically
            if len(self.ppo_agent.states) >= 32:
                actor_loss, critic_loss = self.ppo_agent.train()
                logger.debug(f"PPO losses - Actor: {actor_loss:.4f}, Critic: {critic_loss:.4f}")

            # Update state
            if not done:
                self.last_states[key]["state"] = new_state
            else:
                del self.last_states[key]

        # Periodically save models
        if np.random.random() < 0.01:  # 1% chance
            self.save_models()
