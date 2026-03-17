"""
System State Management & Graceful Recovery
Ensures the system can save its state and recover from failures to a 'pristine' state.
"""

import json
import logging
import os
import shutil
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

STATE_FILE = "system_state.json"
CHECKPOINT_DIR = "checkpoints"


@dataclass
class SystemState:
    timestamp: float
    active_positions: Dict[str, Any]
    pending_orders: Dict[str, Any]
    portfolio_balance: float
    strategy_state: Dict[str, Any]
    is_pristine: bool = True


class StateManager:
    """
    Manages system state checkpoints and recovery.
    """

    def __init__(self, data_dir: str = "data"):
        self.data_dir = data_dir
        self.checkpoint_dir = os.path.join(data_dir, CHECKPOINT_DIR)
        self.state_file = os.path.join(data_dir, STATE_FILE)

        os.makedirs(self.checkpoint_dir, exist_ok=True)
        os.makedirs(self.data_dir, exist_ok=True)

    def save_checkpoint(self, state_data: Dict[str, Any], is_pristine: bool = True):
        """
        Save the current system state.

        Args:
            state_data: Dictionary containing relevant system state
            is_pristine: Whether this state is considered 'safe/stable'
        """
        try:
            timestamp = datetime.now()
            state = {
                "timestamp": timestamp.isoformat(),
                "data": state_data,
                "is_pristine": is_pristine,
            }

            # Save to main state file
            tmp_file = f"{self.state_file}.tmp"
            with open(tmp_file, "w") as f:
                json.dump(state, f, indent=2)
            os.replace(tmp_file, self.state_file)

            # If pristine, create a timestamped checkpoint
            if is_pristine:
                filename = f"checkpoint_{timestamp.strftime('%Y%m%d_%H%M%S')}.json"
                shutil.copy2(self.state_file, os.path.join(self.checkpoint_dir, filename))

            logger.debug("💾 System state checkpoint saved")

        except Exception as e:
            logger.error(f"Failed to save system state: {e}")

    def load_last_good_state(self) -> Optional[Dict[str, Any]]:
        """
        Load the last known good (pristine) state.
        """
        try:
            if not os.path.exists(self.state_file):
                logger.warning("No system state file found.")
                return None

            with open(self.state_file, "r") as f:
                state = json.load(f)

            if state.get("is_pristine"):
                logger.info(f"♻️ Loaded pristine state from {state['timestamp']}")
                return state["data"]
            else:
                logger.warning(
                    "⚠️ Current state file is NOT marked pristine. searching checkpoints..."
                )
                return self._find_latest_checkpoint()

        except Exception as e:
            logger.error(f"Failed to load system state: {e}")
            return None

    def _find_latest_checkpoint(self) -> Optional[Dict[str, Any]]:
        """Find the most recent checkpoint file."""
        try:
            files = [f for f in os.listdir(self.checkpoint_dir) if f.startswith("checkpoint_")]
            if not files:
                return None

            latest_file = max(files)
            path = os.path.join(self.checkpoint_dir, latest_file)

            with open(path, "r") as f:
                state = json.load(f)
                logger.info(f"♻️ Recovered from checkpoint: {latest_file}")
                return state["data"]
        except Exception as e:
            logger.error(f"Error finding checkpoint: {e}")
            return None

    def clear_state(self):
        """Clear state file (e.g. after a full clean shutdown)."""
        if os.path.exists(self.state_file):
            os.remove(self.state_file)


# Global instance
_state_manager: Optional[StateManager] = None


def get_state_manager() -> StateManager:
    global _state_manager
    if _state_manager is None:
        _state_manager = StateManager()
    return _state_manager
