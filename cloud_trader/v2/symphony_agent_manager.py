"""
Symphony Multi-Agent Manager
=============================
Manages multiple Symphony agents with individual activation tracking.

Current Agents:
- $MILF (Monad Implementation Treasury Agent) - ACTIVATED ✅
- $AGDG (Ari Gold Degen Agent) - ACTIVATED ✅  
- $MIT (Monad Implementation Treasury) - PENDING ACTIVATION ⏳

The MIT Agent requires 5 trades to activate via batch-open operations.

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

# Configure logging with agentic persona
logger = logging.getLogger(__name__)


class AgentStatus(Enum):
    """Symphony agent activation status."""
    INACTIVE = "inactive"           # Never started
    PENDING_ACTIVATION = "pending"  # Working toward activation
    ACTIVATING = "activating"       # Final trade in progress
    ACTIVE = "active"               # Fully operational
    SUSPENDED = "suspended"         # Temporarily paused
    DEACTIVATED = "deactivated"     # Permanently stopped


class AgentType(Enum):
    """Symphony agent types."""
    MILF = "milf"   # Monad Implementation Treasury Agent
    AGDG = "agdg"   # Ari Gold Degen Agent
    MIT = "mit"     # Monad Implementation Treasury


@dataclass
class SymphonyAgentConfig:
    """Configuration for a Symphony agent."""
    agent_type: AgentType
    ticker: str
    full_name: str
    activation_threshold: int = 5
    treasury_address: Optional[str] = None
    strategy: str = "default"
    risk_params: dict = field(default_factory=dict)
    
    # Trading parameters
    max_position_size: float = 1000.0  # USD
    allowed_symbols: list[str] = field(default_factory=lambda: ["BTC-USDC", "ETH-USDC", "SOL-USDC"])
    min_confidence: float = 0.6


@dataclass 
class AgentTrade:
    """Record of a trade executed by an agent."""
    trade_id: str
    agent_type: AgentType
    symbol: str
    side: str
    quantity: float
    price: float
    timestamp: datetime
    status: str  # "pending", "filled", "failed", "cancelled"
    pnl: Optional[float] = None
    fees: Optional[float] = None
    platform_order_id: Optional[str] = None
    batch_id: Optional[str] = None
    
    def to_dict(self) -> dict:
        return {
            "trade_id": self.trade_id,
            "agent_type": self.agent_type.value,
            "symbol": self.symbol,
            "side": self.side,
            "quantity": self.quantity,
            "price": self.price,
            "timestamp": self.timestamp.isoformat(),
            "status": self.status,
            "pnl": self.pnl,
            "fees": self.fees,
            "platform_order_id": self.platform_order_id,
            "batch_id": self.batch_id,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "AgentTrade":
        return cls(
            trade_id=data["trade_id"],
            agent_type=AgentType(data["agent_type"]),
            symbol=data["symbol"],
            side=data["side"],
            quantity=data["quantity"],
            price=data["price"],
            timestamp=datetime.fromisoformat(data["timestamp"]),
            status=data["status"],
            pnl=data.get("pnl"),
            fees=data.get("fees"),
            platform_order_id=data.get("platform_order_id"),
            batch_id=data.get("batch_id"),
        )


@dataclass
class SymphonyAgent:
    """
    Represents a single Symphony agent with full state tracking.
    """
    config: SymphonyAgentConfig
    status: AgentStatus = AgentStatus.INACTIVE
    trades: list[AgentTrade] = field(default_factory=list)
    
    # Activation tracking
    activation_started: Optional[datetime] = None
    activation_completed: Optional[datetime] = None
    
    # Performance metrics
    total_pnl: float = 0.0
    total_volume: float = 0.0
    win_count: int = 0
    loss_count: int = 0
    
    # Timestamps
    created_at: datetime = field(default_factory=datetime.utcnow)
    last_trade_at: Optional[datetime] = None
    last_updated: datetime = field(default_factory=datetime.utcnow)
    
    @property
    def ticker(self) -> str:
        return self.config.ticker
    
    @property
    def agent_type(self) -> AgentType:
        return self.config.agent_type
    
    @property
    def is_active(self) -> bool:
        return self.status == AgentStatus.ACTIVE
    
    @property
    def filled_trades(self) -> list[AgentTrade]:
        return [t for t in self.trades if t.status == "filled"]
    
    @property
    def activation_progress(self) -> int:
        """Number of filled trades toward activation."""
        return len(self.filled_trades)
    
    @property
    def trades_until_activation(self) -> int:
        """Trades remaining to activate."""
        if self.is_active:
            return 0
        return max(0, self.config.activation_threshold - self.activation_progress)
    
    @property
    def activation_percent(self) -> float:
        """Activation progress as percentage."""
        if self.is_active:
            return 100.0
        return (self.activation_progress / self.config.activation_threshold) * 100
    
    @property
    def win_rate(self) -> float:
        """Calculate win rate."""
        total = self.win_count + self.loss_count
        if total == 0:
            return 0.0
        return self.win_count / total
    
    def record_trade(self, trade: AgentTrade) -> None:
        """Record a new trade for this agent."""
        self.trades.append(trade)
        self.last_trade_at = trade.timestamp
        self.last_updated = datetime.utcnow()
        
        if trade.status == "filled":
            self.total_volume += trade.quantity * trade.price
            
            if trade.pnl is not None:
                self.total_pnl += trade.pnl
                if trade.pnl > 0:
                    self.win_count += 1
                else:
                    self.loss_count += 1
            
            # Check activation
            if not self.is_active and self.activation_progress >= self.config.activation_threshold:
                self.status = AgentStatus.ACTIVE
                self.activation_completed = datetime.utcnow()
                logger.info(
                    f"🎉 [Symphony:{self.ticker}] AGENT ACTIVATED! | "
                    f"Trades: {self.activation_progress} | "
                    f"Duration: {self.activation_completed - self.activation_started if self.activation_started else 'N/A'}"
                )
    
    def to_dict(self) -> dict:
        return {
            "agent_type": self.agent_type.value,
            "ticker": self.ticker,
            "full_name": self.config.full_name,
            "status": self.status.value,
            "is_active": self.is_active,
            "activation_progress": self.activation_progress,
            "activation_threshold": self.config.activation_threshold,
            "activation_percent": round(self.activation_percent, 1),
            "trades_until_activation": self.trades_until_activation,
            "total_trades": len(self.trades),
            "filled_trades": len(self.filled_trades),
            "total_pnl": round(self.total_pnl, 2),
            "total_volume": round(self.total_volume, 2),
            "win_rate": round(self.win_rate, 3),
            "activation_started": self.activation_started.isoformat() if self.activation_started else None,
            "activation_completed": self.activation_completed.isoformat() if self.activation_completed else None,
            "last_trade_at": self.last_trade_at.isoformat() if self.last_trade_at else None,
        }


class SymphonyAgentManager:
    """
    Manages all Symphony agents with centralized tracking.
    
    Current State:
    - $MILF: ACTIVE ✅
    - $AGDG: ACTIVE ✅
    - $MIT: PENDING ACTIVATION ⏳ (needs 5 trades)
    
    Usage:
        manager = SymphonyAgentManager()
        await manager.initialize()
        
        # Check MIT activation status
        mit_status = manager.get_agent_status(AgentType.MIT)
        
        # Record a trade toward MIT activation
        await manager.record_trade(
            agent_type=AgentType.MIT,
            symbol="BTC-USDC",
            side="BUY",
            quantity=0.01,
            price=42000.0,
        )
    """
    
    # Pre-configured agents
    AGENT_CONFIGS = {
        AgentType.MILF: SymphonyAgentConfig(
            agent_type=AgentType.MILF,
            ticker="$MILF",
            full_name="Monad Implementation Treasury Agent",
            activation_threshold=5,
            strategy="momentum",
            risk_params={"max_drawdown": 0.1, "position_limit": 5},
        ),
        AgentType.AGDG: SymphonyAgentConfig(
            agent_type=AgentType.AGDG,
            ticker="$AGDG",
            full_name="Ari Gold Degen Agent",
            activation_threshold=5,
            strategy="degen_momentum",
            risk_params={"max_drawdown": 0.15, "position_limit": 10},
        ),
        AgentType.MIT: SymphonyAgentConfig(
            agent_type=AgentType.MIT,
            ticker="$MIT",
            full_name="Monad Implementation Treasury",
            activation_threshold=5,  # KEY: 5 trades to activate
            strategy="treasury_management",
            risk_params={"max_drawdown": 0.05, "position_limit": 3},
        ),
    }
    
    # Known activation states (as of system initialization)
    INITIAL_STATES = {
        AgentType.MILF: AgentStatus.ACTIVE,      # Already activated ✅
        AgentType.AGDG: AgentStatus.ACTIVE,      # Already activated ✅
        AgentType.MIT: AgentStatus.PENDING_ACTIVATION,  # Needs activation ⏳
    }
    
    def __init__(
        self,
        firestore_client: Optional[Any] = None,
        symphony_client: Optional[Any] = None,
    ):
        """
        Initialize Symphony agent manager.
        
        Args:
            firestore_client: Optional Firestore client for persistence
            symphony_client: Optional Symphony platform client
        """
        self._db = firestore_client
        self._symphony = symphony_client
        
        self._agents: dict[AgentType, SymphonyAgent] = {}
        self._initialized = False
        self._lock = asyncio.Lock()
        
    async def initialize(self) -> None:
        """Initialize all agents with their known states."""
        if self._initialized:
            return
        
        logger.info("🎭 [Symphony] Initializing Multi-Agent Manager...")
        
        for agent_type, config in self.AGENT_CONFIGS.items():
            initial_status = self.INITIAL_STATES.get(agent_type, AgentStatus.INACTIVE)
            
            agent = SymphonyAgent(
                config=config,
                status=initial_status,
            )
            
            # Mark activation times for already-active agents
            if initial_status == AgentStatus.ACTIVE:
                agent.activation_completed = datetime.utcnow() - timedelta(days=1)  # Assumed past
                # Simulate that they had 5 activation trades
                agent.activation_started = agent.activation_completed - timedelta(hours=1)
            
            self._agents[agent_type] = agent
            
            status_emoji = "✅" if agent.is_active else "⏳"
            logger.info(
                f"  {status_emoji} {config.ticker} ({config.full_name}): {initial_status.value}"
            )
        
        # Load persisted state if available
        await self._load_persisted_state()
        
        self._initialized = True
        
        # Log MIT activation status prominently
        mit = self._agents[AgentType.MIT]
        logger.info(
            f"\n🎯 [Symphony] MIT Activation Status:\n"
            f"    Ticker: {mit.ticker}\n"
            f"    Status: {mit.status.value}\n"
            f"    Progress: {mit.activation_progress}/{mit.config.activation_threshold} trades\n"
            f"    Remaining: {mit.trades_until_activation} trades to activate\n"
        )
    
    async def _load_persisted_state(self) -> None:
        """Load persisted agent state from Firestore."""
        if self._db is None:
            logger.debug("[Symphony] No Firestore client - skipping state load")
            return
        
        try:
            for agent_type in self._agents:
                doc_ref = self._db.collection("symphony_agents").document(agent_type.value)
                doc = await doc_ref.get()
                
                if doc.exists:
                    data = doc.to_dict()
                    agent = self._agents[agent_type]
                    
                    # Restore trades
                    for trade_data in data.get("trades", []):
                        trade = AgentTrade.from_dict(trade_data)
                        agent.trades.append(trade)
                    
                    # Restore metrics
                    agent.total_pnl = data.get("total_pnl", 0.0)
                    agent.total_volume = data.get("total_volume", 0.0)
                    agent.win_count = data.get("win_count", 0)
                    agent.loss_count = data.get("loss_count", 0)
                    
                    # Update status based on trade count
                    if agent.activation_progress >= agent.config.activation_threshold:
                        agent.status = AgentStatus.ACTIVE
                        if data.get("activation_completed"):
                            agent.activation_completed = datetime.fromisoformat(data["activation_completed"])
                    
                    logger.info(f"📥 [Symphony:{agent.ticker}] Loaded persisted state")
                    
        except Exception as e:
            logger.warning(f"⚠️ [Symphony] Failed to load persisted state: {e}")
    
    async def _persist_agent_state(self, agent: SymphonyAgent) -> bool:
        """Persist agent state to Firestore."""
        if self._db is None:
            return False
        
        try:
            doc_ref = self._db.collection("symphony_agents").document(agent.agent_type.value)
            await doc_ref.set({
                **agent.to_dict(),
                "trades": [t.to_dict() for t in agent.trades],
            })
            return True
        except Exception as e:
            logger.error(f"❌ [Symphony:{agent.ticker}] Failed to persist state: {e}")
            return False
    
    def get_agent(self, agent_type: AgentType) -> SymphonyAgent:
        """Get agent by type."""
        return self._agents[agent_type]
    
    def get_mit_agent(self) -> SymphonyAgent:
        """Convenience method to get the MIT agent."""
        return self._agents[AgentType.MIT]
    
    def get_active_agents(self) -> list[SymphonyAgent]:
        """Get all active agents."""
        return [a for a in self._agents.values() if a.is_active]
    
    def get_pending_agents(self) -> list[SymphonyAgent]:
        """Get agents pending activation."""
        return [a for a in self._agents.values() if a.status == AgentStatus.PENDING_ACTIVATION]
    
    async def record_trade(
        self,
        agent_type: AgentType,
        trade_id: str,
        symbol: str,
        side: str,
        quantity: float,
        price: float,
        status: str = "filled",
        pnl: Optional[float] = None,
        platform_order_id: Optional[str] = None,
        batch_id: Optional[str] = None,
    ) -> SymphonyAgent:
        """
        Record a trade for an agent.
        
        For MIT activation, each filled trade counts toward the 5-trade threshold.
        
        Args:
            agent_type: Which agent executed the trade
            trade_id: Unique trade identifier
            symbol: Trading pair
            side: "BUY" or "SELL"
            quantity: Trade quantity
            price: Execution price
            status: Trade status
            pnl: Realized P&L (if known)
            platform_order_id: Symphony order ID
            batch_id: Batch operation ID (for batch-open)
            
        Returns:
            Updated agent
        """
        if not self._initialized:
            await self.initialize()
        
        async with self._lock:
            agent = self._agents[agent_type]
            
            # Mark activation start if this is first trade toward activation
            if (
                agent.status == AgentStatus.PENDING_ACTIVATION 
                and agent.activation_started is None
                and status == "filled"
            ):
                agent.activation_started = datetime.utcnow()
                logger.info(f"🎯 [Symphony:{agent.ticker}] Activation sequence STARTED")
            
            # Create trade record
            trade = AgentTrade(
                trade_id=trade_id,
                agent_type=agent_type,
                symbol=symbol,
                side=side,
                quantity=quantity,
                price=price,
                timestamp=datetime.utcnow(),
                status=status,
                pnl=pnl,
                platform_order_id=platform_order_id,
                batch_id=batch_id,
            )
            
            # Record the trade (this may trigger activation)
            was_active = agent.is_active
            agent.record_trade(trade)
            
            # Log progress for MIT
            if agent_type == AgentType.MIT and not was_active:
                if agent.is_active:
                    logger.info(
                        f"🎉🎉🎉 [Symphony:$MIT] ACTIVATED! 🎉🎉🎉\n"
                        f"    Monad Implementation Treasury is now LIVE!\n"
                        f"    Total activation trades: {agent.activation_progress}\n"
                        f"    Duration: {agent.activation_completed - agent.activation_started}"
                    )
                else:
                    logger.info(
                        f"📈 [Symphony:$MIT] Trade recorded | "
                        f"Progress: {agent.activation_progress}/{agent.config.activation_threshold} | "
                        f"Remaining: {agent.trades_until_activation} trades"
                    )
            
            # Persist state
            await self._persist_agent_state(agent)
            
            return agent
    
    async def execute_mit_activation_trade(
        self,
        symbol: str,
        side: str,
        quantity: float,
    ) -> dict:
        """
        Execute a trade specifically for MIT activation.
        
        This is a convenience method that:
        1. Validates MIT is not yet activated
        2. Executes trade via Symphony client
        3. Records the trade
        4. Returns activation status
        
        Args:
            symbol: Trading pair
            side: "BUY" or "SELL"
            quantity: Trade quantity
            
        Returns:
            Dict with trade result and activation status
        """
        mit = self.get_mit_agent()
        
        if mit.is_active:
            logger.info(f"✅ [Symphony:$MIT] Already activated - no activation trade needed")
            return {
                "success": True,
                "already_active": True,
                "agent": mit.to_dict(),
            }
        
        # Generate trade ID
        import hashlib
        trade_id = hashlib.sha256(
            f"MIT:{symbol}:{side}:{quantity}:{datetime.utcnow().timestamp()}".encode()
        ).hexdigest()[:16]
        
        logger.info(
            f"🎯 [Symphony:$MIT] Executing activation trade #{mit.activation_progress + 1} | "
            f"Symbol: {symbol} | Side: {side} | Qty: {quantity}"
        )
        
        # Execute via Symphony client if available
        execution_result = None
        if self._symphony:
            try:
                execution_result = await self._symphony.place_order(
                    symbol=symbol,
                    side=side,
                    quantity=quantity,
                    order_type="MARKET",
                )
            except Exception as e:
                logger.error(f"❌ [Symphony:$MIT] Execution failed: {e}")
                return {
                    "success": False,
                    "error": str(e),
                    "agent": mit.to_dict(),
                }
        
        # Record the trade
        price = execution_result.get("price", 0.0) if execution_result else 0.0
        platform_order_id = execution_result.get("order_id") if execution_result else None
        
        await self.record_trade(
            agent_type=AgentType.MIT,
            trade_id=trade_id,
            symbol=symbol,
            side=side,
            quantity=quantity,
            price=price,
            status="filled",
            platform_order_id=platform_order_id,
        )
        
        return {
            "success": True,
            "trade_id": trade_id,
            "activation_progress": mit.activation_progress,
            "trades_remaining": mit.trades_until_activation,
            "is_activated": mit.is_active,
            "agent": mit.to_dict(),
        }
    
    async def execute_mit_batch_activation(
        self,
        trades: list[dict],
    ) -> dict:
        """
        Execute multiple trades in a batch for MIT activation.
        
        This uses Symphony's batch-open capability to execute
        multiple trades in a single operation.
        
        Args:
            trades: List of trade dicts with symbol, side, quantity
            
        Returns:
            Batch execution result with activation status
        """
        mit = self.get_mit_agent()
        
        if mit.is_active:
            return {
                "success": True,
                "already_active": True,
                "agent": mit.to_dict(),
            }
        
        trades_needed = mit.trades_until_activation
        trades_to_execute = trades[:trades_needed]
        
        logger.info(
            f"📦 [Symphony:$MIT] Batch activation | "
            f"Executing {len(trades_to_execute)} trades | "
            f"Progress: {mit.activation_progress}/{mit.config.activation_threshold}"
        )
        
        # Generate batch ID
        import hashlib
        batch_id = hashlib.sha256(
            f"MIT_BATCH:{datetime.utcnow().timestamp()}".encode()
        ).hexdigest()[:12]
        
        results = []
        for i, trade_spec in enumerate(trades_to_execute):
            result = await self.execute_mit_activation_trade(
                symbol=trade_spec["symbol"],
                side=trade_spec["side"],
                quantity=trade_spec["quantity"],
            )
            result["batch_id"] = batch_id
            result["batch_index"] = i
            results.append(result)
            
            # Check if activated
            if mit.is_active:
                break
        
        return {
            "success": True,
            "batch_id": batch_id,
            "trades_executed": len(results),
            "results": results,
            "is_activated": mit.is_active,
            "agent": mit.to_dict(),
        }
    
    def get_all_status(self) -> dict:
        """Get status of all agents."""
        return {
            "agents": {
                agent.ticker: agent.to_dict()
                for agent in self._agents.values()
            },
            "summary": {
                "total_agents": len(self._agents),
                "active_agents": len(self.get_active_agents()),
                "pending_agents": len(self.get_pending_agents()),
                "active_tickers": [a.ticker for a in self.get_active_agents()],
                "pending_tickers": [a.ticker for a in self.get_pending_agents()],
            },
            "mit_activation": {
                "status": self._agents[AgentType.MIT].status.value,
                "progress": self._agents[AgentType.MIT].activation_progress,
                "threshold": self._agents[AgentType.MIT].config.activation_threshold,
                "remaining": self._agents[AgentType.MIT].trades_until_activation,
                "percent": round(self._agents[AgentType.MIT].activation_percent, 1),
            },
        }
    
    def log_status_summary(self) -> None:
        """Log comprehensive status summary."""
        status = self.get_all_status()
        
        logger.info(
            f"\n{'='*60}\n"
            f"🎭 SYMPHONY AGENT STATUS REPORT\n"
            f"{'='*60}\n"
        )
        
        for ticker, agent_data in status["agents"].items():
            status_emoji = "✅" if agent_data["is_active"] else "⏳"
            logger.info(
                f"  {status_emoji} {ticker}: {agent_data['status']}\n"
                f"     Trades: {agent_data['filled_trades']} | "
                f"Volume: ${agent_data['total_volume']:,.2f} | "
                f"PnL: ${agent_data['total_pnl']:,.2f}\n"
            )
        
        mit = status["mit_activation"]
        logger.info(
            f"\n🎯 MIT ACTIVATION STATUS:\n"
            f"   Progress: {mit['progress']}/{mit['threshold']} ({mit['percent']}%)\n"
            f"   Remaining: {mit['remaining']} trades\n"
            f"{'='*60}\n"
        )


# Factory function for main_v2.py
async def create_symphony_manager(
    firestore_client: Optional[Any] = None,
    symphony_client: Optional[Any] = None,
) -> SymphonyAgentManager:
    """
    Create and initialize Symphony agent manager.
    
    Args:
        firestore_client: Optional Firestore client
        symphony_client: Optional Symphony platform client
        
    Returns:
        Initialized SymphonyAgentManager
    """
    manager = SymphonyAgentManager(
        firestore_client=firestore_client,
        symphony_client=symphony_client,
    )
    await manager.initialize()
    return manager


# Example usage
if __name__ == "__main__":
    async def demo():
        """Demonstrate Symphony agent management."""
        print("🎭 Symphony Multi-Agent Manager Demo\n")
        
        # Create manager
        manager = SymphonyAgentManager()
        await manager.initialize()
        
        # Show current status
        manager.log_status_summary()
        
        # Simulate MIT activation trades
        print("\n📈 Simulating MIT activation trades...\n")
        
        activation_trades = [
            {"symbol": "BTC-USDC", "side": "BUY", "quantity": 0.001},
            {"symbol": "ETH-USDC", "side": "BUY", "quantity": 0.01},
            {"symbol": "SOL-USDC", "side": "SELL", "quantity": 0.1},
            {"symbol": "BTC-USDC", "side": "SELL", "quantity": 0.001},
            {"symbol": "ETH-USDC", "side": "BUY", "quantity": 0.02},
        ]
        
        for i, trade in enumerate(activation_trades):
            result = await manager.execute_mit_activation_trade(**trade)
            print(f"  Trade {i+1}: {result['activation_progress']}/5 - {'🎉 ACTIVATED!' if result.get('is_activated') else f'{result.get(\"trades_remaining\", 0)} remaining'}")
        
        # Final status
        print("\n")
        manager.log_status_summary()
    
    asyncio.run(demo())
