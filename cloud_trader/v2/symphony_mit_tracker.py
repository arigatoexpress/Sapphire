"""
Symphony MIT (Monad Implementation Treasury) Activation Tracker
================================================================
Tracks the "5 trade" activation threshold for Symphony platform.

This module is extracted from trading_service.py to maintain clean
separation of concerns per the V2 architecture guidelines.

Author: Sapphire V2 Architecture Team
Version: 2.1.0
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Optional

from google.cloud import firestore

# Configure logging with agentic persona
logger = logging.getLogger(__name__)


class MITActivationState(Enum):
    """MIT activation state machine."""
    PENDING = "pending"           # < 5 trades completed
    ACTIVATING = "activating"     # 5th trade in progress
    ACTIVE = "active"             # MIT fully activated
    SUSPENDED = "suspended"       # Temporarily paused
    FAILED = "failed"             # Activation failed


@dataclass
class MITTrade:
    """Represents a single MIT activation trade."""
    trade_id: str
    symbol: str
    side: str  # "BUY" or "SELL"
    quantity: float
    price: float
    timestamp: datetime
    status: str  # "pending", "filled", "failed"
    platform_response: dict = field(default_factory=dict)
    
    def to_dict(self) -> dict:
        """Serialize for Firestore persistence."""
        return {
            "trade_id": self.trade_id,
            "symbol": self.symbol,
            "side": self.side,
            "quantity": self.quantity,
            "price": self.price,
            "timestamp": self.timestamp.isoformat(),
            "status": self.status,
            "platform_response": self.platform_response,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "MITTrade":
        """Deserialize from Firestore."""
        return cls(
            trade_id=data["trade_id"],
            symbol=data["symbol"],
            side=data["side"],
            quantity=data["quantity"],
            price=data["price"],
            timestamp=datetime.fromisoformat(data["timestamp"]),
            status=data["status"],
            platform_response=data.get("platform_response", {}),
        )


@dataclass
class MITActivationProgress:
    """Tracks MIT activation progress with persistence."""
    state: MITActivationState = MITActivationState.PENDING
    trades: list[MITTrade] = field(default_factory=list)
    activation_started: Optional[datetime] = None
    activation_completed: Optional[datetime] = None
    last_updated: datetime = field(default_factory=datetime.utcnow)
    _persisted: bool = False
    
    ACTIVATION_THRESHOLD: int = 5
    
    @property
    def completed_trades(self) -> int:
        """Count of successfully filled trades."""
        return sum(1 for t in self.trades if t.status == "filled")
    
    @property
    def pending_trades(self) -> int:
        """Count of pending trades."""
        return sum(1 for t in self.trades if t.status == "pending")
    
    @property
    def progress_percent(self) -> float:
        """Activation progress as percentage."""
        return (self.completed_trades / self.ACTIVATION_THRESHOLD) * 100
    
    @property
    def trades_remaining(self) -> int:
        """Number of trades needed to activate."""
        return max(0, self.ACTIVATION_THRESHOLD - self.completed_trades)
    
    @property
    def is_activated(self) -> bool:
        """Check if MIT is fully activated."""
        return self.state == MITActivationState.ACTIVE
    
    def to_dict(self) -> dict:
        """Serialize for Firestore."""
        return {
            "state": self.state.value,
            "trades": [t.to_dict() for t in self.trades],
            "activation_started": self.activation_started.isoformat() if self.activation_started else None,
            "activation_completed": self.activation_completed.isoformat() if self.activation_completed else None,
            "last_updated": self.last_updated.isoformat(),
            "completed_trades": self.completed_trades,
            "progress_percent": self.progress_percent,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "MITActivationProgress":
        """Deserialize from Firestore."""
        progress = cls(
            state=MITActivationState(data.get("state", "pending")),
            trades=[MITTrade.from_dict(t) for t in data.get("trades", [])],
            activation_started=datetime.fromisoformat(data["activation_started"]) if data.get("activation_started") else None,
            activation_completed=datetime.fromisoformat(data["activation_completed"]) if data.get("activation_completed") else None,
            last_updated=datetime.fromisoformat(data.get("last_updated", datetime.utcnow().isoformat())),
        )
        progress._persisted = True
        return progress


class SymphonyMITTracker:
    """
    Tracks Symphony MIT activation with Firestore persistence.
    
    This class manages the "5 trade" activation threshold for the
    Monad Implementation Treasury (MIT) on the Symphony platform.
    
    Features:
    - Firestore persistence with fallback
    - Batch operation tracking
    - State machine for activation flow
    - Agentic logging with emojis
    
    Usage:
        tracker = SymphonyMITTracker()
        await tracker.initialize()
        
        # Record a trade
        await tracker.record_trade(trade_data)
        
        # Check activation status
        if tracker.is_activated:
            print("MIT is active!")
    """
    
    FIRESTORE_COLLECTION = "symphony_mit"
    FIRESTORE_DOC_ID = "activation_progress"
    
    def __init__(
        self,
        firestore_client: Optional[firestore.AsyncClient] = None,
        batch_size: int = 5,
    ):
        """
        Initialize MIT tracker.
        
        Args:
            firestore_client: Optional Firestore client (creates one if not provided)
            batch_size: Number of trades to batch before execution (default: 5)
        """
        self._db = firestore_client
        self._batch_size = batch_size
        self._progress: Optional[MITActivationProgress] = None
        self._initialized = False
        self._lock = asyncio.Lock()
        
    @property
    def progress(self) -> MITActivationProgress:
        """Get current activation progress."""
        if self._progress is None:
            self._progress = MITActivationProgress()
        return self._progress
    
    @property
    def is_activated(self) -> bool:
        """Check if MIT is fully activated."""
        return self.progress.is_activated
    
    @property
    def trades_remaining(self) -> int:
        """Number of trades needed to activate MIT."""
        return self.progress.trades_remaining
    
    async def initialize(self) -> bool:
        """
        Initialize tracker and load persisted state from Firestore.
        
        Returns:
            True if initialization successful, False otherwise
        """
        if self._initialized:
            return True
            
        logger.info("🚀 [MIT Tracker] Initializing Symphony MIT Tracker...")
        
        try:
            # Initialize Firestore client if not provided
            if self._db is None:
                self._db = firestore.AsyncClient()
            
            # Load persisted progress
            await self._load_progress()
            
            self._initialized = True
            logger.info(
                f"✅ [MIT Tracker] Initialized | "
                f"State: {self.progress.state.value} | "
                f"Progress: {self.progress.completed_trades}/{self.progress.ACTIVATION_THRESHOLD} "
                f"({self.progress.progress_percent:.1f}%)"
            )
            return True
            
        except Exception as e:
            logger.warning(
                f"⚠️ [MIT Tracker] Firestore unavailable - starting with empty state | "
                f"Error: {e}"
            )
            self._progress = MITActivationProgress()
            self._initialized = True
            return False
    
    async def _load_progress(self) -> None:
        """Load progress from Firestore."""
        if self._db is None:
            return
            
        doc_ref = self._db.collection(self.FIRESTORE_COLLECTION).document(self.FIRESTORE_DOC_ID)
        doc = await doc_ref.get()
        
        if doc.exists:
            self._progress = MITActivationProgress.from_dict(doc.to_dict())
            logger.info(f"📥 [MIT Tracker] Loaded persisted state from Firestore")
        else:
            self._progress = MITActivationProgress()
            logger.info(f"📝 [MIT Tracker] No persisted state found - starting fresh")
    
    async def _persist_progress(self) -> bool:
        """
        Persist current progress to Firestore.
        
        Returns:
            True if persistence successful, False otherwise
        """
        if self._db is None:
            logger.warning("⚠️ [MIT Tracker] Firestore client not available - skipping persistence")
            return False
            
        try:
            async with self._lock:
                doc_ref = self._db.collection(self.FIRESTORE_COLLECTION).document(self.FIRESTORE_DOC_ID)
                self.progress.last_updated = datetime.utcnow()
                await doc_ref.set(self.progress.to_dict())
                self.progress._persisted = True
                
            logger.debug(f"💾 [MIT Tracker] Progress persisted to Firestore")
            return True
            
        except Exception as e:
            logger.error(f"❌ [MIT Tracker] Failed to persist progress: {e}")
            self.progress._persisted = False
            return False
    
    async def record_trade(
        self,
        trade_id: str,
        symbol: str,
        side: str,
        quantity: float,
        price: float,
        status: str = "filled",
        platform_response: Optional[dict] = None,
    ) -> MITActivationProgress:
        """
        Record a trade toward MIT activation.
        
        Args:
            trade_id: Unique trade identifier
            symbol: Trading pair (e.g., "BTC-USDC")
            side: Trade side ("BUY" or "SELL")
            quantity: Trade quantity
            price: Execution price
            status: Trade status ("pending", "filled", "failed")
            platform_response: Raw response from Symphony platform
            
        Returns:
            Updated activation progress
        """
        if not self._initialized:
            await self.initialize()
        
        trade = MITTrade(
            trade_id=trade_id,
            symbol=symbol,
            side=side,
            quantity=quantity,
            price=price,
            timestamp=datetime.utcnow(),
            status=status,
            platform_response=platform_response or {},
        )
        
        async with self._lock:
            self.progress.trades.append(trade)
            
            # Update state machine
            if self.progress.activation_started is None:
                self.progress.activation_started = datetime.utcnow()
                self.progress.state = MITActivationState.PENDING
                logger.info(f"🎯 [MIT Tracker] Activation sequence STARTED")
            
            # Check for activation
            if self.progress.completed_trades >= self.progress.ACTIVATION_THRESHOLD:
                self.progress.state = MITActivationState.ACTIVE
                self.progress.activation_completed = datetime.utcnow()
                logger.info(
                    f"🎉 [MIT Tracker] MIT ACTIVATED! | "
                    f"Completed {self.progress.completed_trades} trades | "
                    f"Duration: {self.progress.activation_completed - self.progress.activation_started}"
                )
            else:
                logger.info(
                    f"📈 [MIT Tracker] Trade recorded | "
                    f"Progress: {self.progress.completed_trades}/{self.progress.ACTIVATION_THRESHOLD} | "
                    f"Remaining: {self.progress.trades_remaining}"
                )
        
        # Persist to Firestore
        await self._persist_progress()
        
        return self.progress
    
    async def update_trade_status(
        self,
        trade_id: str,
        new_status: str,
        platform_response: Optional[dict] = None,
    ) -> bool:
        """
        Update status of an existing trade.
        
        Args:
            trade_id: Trade to update
            new_status: New status ("pending", "filled", "failed")
            platform_response: Optional updated platform response
            
        Returns:
            True if trade found and updated, False otherwise
        """
        async with self._lock:
            for trade in self.progress.trades:
                if trade.trade_id == trade_id:
                    old_status = trade.status
                    trade.status = new_status
                    if platform_response:
                        trade.platform_response = platform_response
                    
                    logger.info(
                        f"🔄 [MIT Tracker] Trade {trade_id} status updated: "
                        f"{old_status} → {new_status}"
                    )
                    
                    # Re-check activation after status change
                    if (
                        new_status == "filled" 
                        and self.progress.completed_trades >= self.progress.ACTIVATION_THRESHOLD
                        and self.progress.state != MITActivationState.ACTIVE
                    ):
                        self.progress.state = MITActivationState.ACTIVE
                        self.progress.activation_completed = datetime.utcnow()
                        logger.info(f"🎉 [MIT Tracker] MIT ACTIVATED after trade confirmation!")
                    
                    await self._persist_progress()
                    return True
        
        logger.warning(f"⚠️ [MIT Tracker] Trade {trade_id} not found")
        return False
    
    async def get_batch_for_execution(self) -> list[dict]:
        """
        Get pending trades ready for batch execution.
        
        Returns:
            List of trade dictionaries ready for Symphony batch-open
        """
        pending = [
            {
                "symbol": t.symbol,
                "side": t.side,
                "quantity": t.quantity,
                "price": t.price,
                "trade_id": t.trade_id,
            }
            for t in self.progress.trades
            if t.status == "pending"
        ]
        
        if len(pending) >= self._batch_size:
            logger.info(
                f"📦 [MIT Tracker] Batch ready for execution | "
                f"Size: {len(pending)} trades"
            )
        
        return pending[:self._batch_size]
    
    async def reset_activation(self, reason: str = "manual_reset") -> None:
        """
        Reset activation progress (use with caution).
        
        Args:
            reason: Reason for reset (logged)
        """
        logger.warning(f"🔄 [MIT Tracker] Resetting activation | Reason: {reason}")
        
        async with self._lock:
            self._progress = MITActivationProgress()
            self._progress.last_updated = datetime.utcnow()
        
        await self._persist_progress()
        logger.info(f"✅ [MIT Tracker] Activation reset complete")
    
    def get_status_summary(self) -> dict:
        """
        Get human-readable status summary.
        
        Returns:
            Dictionary with status information
        """
        return {
            "state": self.progress.state.value,
            "is_activated": self.is_activated,
            "completed_trades": self.progress.completed_trades,
            "total_trades": len(self.progress.trades),
            "trades_remaining": self.trades_remaining,
            "progress_percent": round(self.progress.progress_percent, 1),
            "activation_started": self.progress.activation_started.isoformat() if self.progress.activation_started else None,
            "activation_completed": self.progress.activation_completed.isoformat() if self.progress.activation_completed else None,
            "last_updated": self.progress.last_updated.isoformat(),
            "persisted": self.progress._persisted,
        }


# Integration helper for main_v2.py
async def create_mit_tracker(
    firestore_client: Optional[Any] = None,
) -> SymphonyMITTracker:
    """
    Factory function to create and initialize MIT tracker.
    
    This is the recommended way to create a tracker instance
    in main_v2.py or other modules.
    
    Args:
        firestore_client: Optional Firestore client
        
    Returns:
        Initialized SymphonyMITTracker instance
    """
    tracker = SymphonyMITTracker(firestore_client=firestore_client)
    await tracker.initialize()
    return tracker


# Example usage and testing
if __name__ == "__main__":
    async def demo():
        """Demonstrate MIT tracker functionality."""
        print("🔷 Symphony MIT Tracker Demo\n")
        
        # Create tracker (without Firestore for demo)
        tracker = SymphonyMITTracker(firestore_client=None)
        await tracker.initialize()
        
        # Simulate 5 trades for activation
        for i in range(5):
            await tracker.record_trade(
                trade_id=f"demo-trade-{i+1}",
                symbol="BTC-USDC",
                side="BUY" if i % 2 == 0 else "SELL",
                quantity=0.01,
                price=42000.0 + (i * 100),
                status="filled",
            )
            print(f"  Trade {i+1}: {tracker.get_status_summary()}")
        
        print(f"\n📊 Final Status: {tracker.get_status_summary()}")
        print(f"✅ Is Activated: {tracker.is_activated}")
    
    asyncio.run(demo())
