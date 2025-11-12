"""Persistent storage layer using PostgreSQL/TimescaleDB for time-series data."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Float,
    Integer,
    String,
    UniqueConstraint,
    Index,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from .config import Settings, get_settings

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    """Base class for SQLAlchemy models."""
    pass


class Trade(Base):
    """Trade execution records."""
    __tablename__ = "trades"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    symbol: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    side: Mapped[str] = mapped_column(String(10), nullable=False)  # BUY or SELL
    price: Mapped[float] = mapped_column(Float, nullable=False)
    quantity: Mapped[float] = mapped_column(Float, nullable=False)
    notional: Mapped[float] = mapped_column(Float, nullable=False)
    agent_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, index=True)
    agent_model: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    strategy: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    order_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, unique=True)
    execution_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    fee: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    slippage_bps: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    extra_metadata: Mapped[Optional[Dict[str, Any]]] = mapped_column("metadata", JSONB, nullable=True)

    __table_args__ = (
        Index("idx_trades_timestamp_symbol", "timestamp", "symbol"),
        Index("idx_trades_agent_timestamp", "agent_id", "timestamp"),
    )


class Position(Base):
    """Position history records."""
    __tablename__ = "positions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    symbol: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    agent_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, index=True)
    side: Mapped[str] = mapped_column(String(10), nullable=False)  # LONG or SHORT
    size: Mapped[float] = mapped_column(Float, nullable=False)
    entry_price: Mapped[float] = mapped_column(Float, nullable=False)
    current_price: Mapped[float] = mapped_column(Float, nullable=False)
    notional: Mapped[float] = mapped_column(Float, nullable=False)
    unrealized_pnl: Mapped[float] = mapped_column(Float, nullable=False)
    unrealized_pnl_pct: Mapped[float] = mapped_column(Float, nullable=False)
    leverage: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False)  # open, closed, partial
    extra_metadata: Mapped[Optional[Dict[str, Any]]] = mapped_column("metadata", JSONB, nullable=True)

    __table_args__ = (
        Index("idx_positions_timestamp_symbol", "timestamp", "symbol"),
        Index("idx_positions_agent_status", "agent_id", "status"),
    )


class MarketSnapshot(Base):
    """Market data snapshots."""
    __tablename__ = "market_snapshots"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    symbol: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    price: Mapped[float] = mapped_column(Float, nullable=False)
    volume_24h: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    change_24h: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    high_24h: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    low_24h: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    funding_rate: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    open_interest: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    extra_metadata: Mapped[Optional[Dict[str, Any]]] = mapped_column("metadata", JSONB, nullable=True)

    __table_args__ = (
        UniqueConstraint("timestamp", "symbol", name="uq_market_snapshot_timestamp_symbol"),
        Index("idx_market_snapshots_timestamp_symbol", "timestamp", "symbol"),
    )


class AgentPerformance(Base):
    """Agent performance metrics over time."""
    __tablename__ = "agent_performance"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    agent_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    total_trades: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_pnl: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    exposure: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    equity: Mapped[float] = mapped_column(Float, nullable=False)
    win_rate: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    sharpe_ratio: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    max_drawdown: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    active_positions: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    extra_metadata: Mapped[Optional[Dict[str, Any]]] = mapped_column("metadata", JSONB, nullable=True)

    __table_args__ = (
        Index("idx_agent_performance_timestamp_agent", "timestamp", "agent_id"),
    )


class AgentDecision(Base):
    """Agent decision records for training data."""
    __tablename__ = "agent_decisions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    agent_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    symbol: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    decision: Mapped[str] = mapped_column(String(20), nullable=False)  # BUY, SELL, HOLD
    confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    strategy: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    state_features: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    market_context: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    executed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    reward: Mapped[Optional[float]] = mapped_column(Float, nullable=True)  # Filled after execution
    extra_metadata: Mapped[Optional[Dict[str, Any]]] = mapped_column("metadata", JSONB, nullable=True)

    __table_args__ = (
        Index("idx_agent_decisions_timestamp_agent", "timestamp", "agent_id"),
        Index("idx_agent_decisions_symbol_timestamp", "symbol", "timestamp"),
    )


class TradingStorage:
    """Async storage manager for trading data."""
    
    def __init__(self, settings: Optional[Settings] = None):
        self._settings = settings or get_settings()
        self._engine = None
        self._session_factory = None
        self._initialized = False
    
    async def initialize(self) -> None:
        """Initialize database connection and create tables."""
        if self._initialized:
            return
        
        database_url = self._settings.database_url
        if not database_url:
            logger.warning("No DATABASE_URL configured, storage disabled")
            return
        
        try:
            # Convert postgres:// to postgresql+asyncpg:// for async support
            if database_url.startswith("postgres://"):
                database_url = database_url.replace("postgres://", "postgresql+asyncpg://", 1)
            elif not database_url.startswith("postgresql+asyncpg://"):
                database_url = f"postgresql+asyncpg://{database_url}"
            
            self._engine = create_async_engine(
                database_url,
                pool_size=10,
                max_overflow=20,
                pool_pre_ping=True,
                echo=False,
            )
            
            self._session_factory = async_sessionmaker(
                self._engine,
                class_=AsyncSession,
                expire_on_commit=False,
            )
            
            # Create tables (including TimescaleDB hypertables if available)
            async with self._engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
                
                # Try to create TimescaleDB hypertables
                try:
                    await conn.execute(text("CREATE EXTENSION IF NOT EXISTS timescaledb"))
                    await conn.execute(text("""
                        SELECT create_hypertable('trades', 'timestamp', if_not_exists => TRUE)
                    """))
                    await conn.execute(text("""
                        SELECT create_hypertable('positions', 'timestamp', if_not_exists => TRUE)
                    """))
                    await conn.execute(text("""
                        SELECT create_hypertable('market_snapshots', 'timestamp', if_not_exists => TRUE)
                    """))
                    await conn.execute(text("""
                        SELECT create_hypertable('agent_performance', 'timestamp', if_not_exists => TRUE)
                    """))
                    await conn.execute(text("""
                        SELECT create_hypertable('agent_decisions', 'timestamp', if_not_exists => TRUE)
                    """))
                    logger.info("TimescaleDB hypertables created")
                except Exception as e:
                    logger.warning(f"TimescaleDB not available, using regular tables: {e}")
            
            self._initialized = True
            logger.info("Database storage initialized")
        except Exception as e:
            logger.error(f"Failed to initialize database storage: {e}")
            self._engine = None
            self._session_factory = None
    
    async def close(self) -> None:
        """Close database connection."""
        if self._engine:
            await self._engine.dispose()
        self._engine = None
        self._session_factory = None
        self._initialized = False
        logger.info("Database connection closed")

    def is_ready(self) -> bool:
        """Return True if storage backend is initialized and ready."""
        return self._initialized and self._engine is not None and self._session_factory is not None
    
    async def insert_trade(
        self,
        timestamp: datetime,
        symbol: str,
        side: str,
        price: float,
        quantity: float,
        notional: float,
        agent_id: Optional[str] = None,
        agent_model: Optional[str] = None,
        strategy: Optional[str] = None,
        order_id: Optional[str] = None,
        execution_id: Optional[str] = None,
        fee: Optional[float] = None,
        slippage_bps: Optional[float] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[int]:
        """Insert a trade record."""
        if not self._initialized or not self._session_factory:
            return None
        
        try:
            async with self._session_factory() as session:
                trade = Trade(
                    timestamp=timestamp,
                    symbol=symbol.upper(),
                    side=side.upper(),
                    price=price,
                    quantity=quantity,
                    notional=notional,
                    agent_id=agent_id,
                    agent_model=agent_model,
                    strategy=strategy,
                    order_id=order_id,
                    execution_id=execution_id,
                    fee=fee,
                    slippage_bps=slippage_bps,
                    extra_metadata=metadata,
                )
                session.add(trade)
                await session.commit()
                return trade.id
        except Exception as e:
            logger.error(f"Failed to insert trade: {e}")
            return None
    
    async def insert_position(
        self,
        timestamp: datetime,
        symbol: str,
        agent_id: Optional[str],
        side: str,
        size: float,
        entry_price: float,
        current_price: float,
        notional: float,
        unrealized_pnl: float,
        unrealized_pnl_pct: float,
        leverage: Optional[float] = None,
        status: str = "open",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[int]:
        """Insert a position snapshot."""
        if not self._initialized or not self._session_factory:
            return None
        
        try:
            async with self._session_factory() as session:
                position = Position(
                    timestamp=timestamp,
                    symbol=symbol.upper(),
                    agent_id=agent_id,
                    side=side.upper(),
                    size=size,
                    entry_price=entry_price,
                    current_price=current_price,
                    notional=notional,
                    unrealized_pnl=unrealized_pnl,
                    unrealized_pnl_pct=unrealized_pnl_pct,
                    leverage=leverage,
                    status=status,
                    extra_metadata=metadata,
                )
                session.add(position)
                await session.commit()
                return position.id
        except Exception as e:
            logger.error(f"Failed to insert position: {e}")
            return None
    
    async def insert_market_snapshot(
        self,
        timestamp: datetime,
        symbol: str,
        price: float,
        volume_24h: Optional[float] = None,
        change_24h: Optional[float] = None,
        high_24h: Optional[float] = None,
        low_24h: Optional[float] = None,
        funding_rate: Optional[float] = None,
        open_interest: Optional[float] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[int]:
        """Insert a market data snapshot."""
        if not self._initialized or not self._session_factory:
            return None
        
        try:
            async with self._session_factory() as session:
                snapshot = MarketSnapshot(
                    timestamp=timestamp,
                    symbol=symbol.upper(),
                    price=price,
                    volume_24h=volume_24h,
                    change_24h=change_24h,
                    high_24h=high_24h,
                    low_24h=low_24h,
                    funding_rate=funding_rate,
                    open_interest=open_interest,
                    extra_metadata=metadata,
                )
                session.add(snapshot)
                await session.commit()
                return snapshot.id
        except Exception as e:
            logger.error(f"Failed to insert market snapshot: {e}")
            return None
    
    async def insert_agent_performance(
        self,
        timestamp: datetime,
        agent_id: str,
        equity: float,
        total_trades: int = 0,
        total_pnl: float = 0.0,
        exposure: float = 0.0,
        win_rate: Optional[float] = None,
        sharpe_ratio: Optional[float] = None,
        max_drawdown: Optional[float] = None,
        active_positions: int = 0,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[int]:
        """Insert agent performance snapshot."""
        if not self._initialized or not self._session_factory:
            return None
        
        try:
            async with self._session_factory() as session:
                performance = AgentPerformance(
                    timestamp=timestamp,
                    agent_id=agent_id,
                    equity=equity,
                    total_trades=total_trades,
                    total_pnl=total_pnl,
                    exposure=exposure,
                    win_rate=win_rate,
                    sharpe_ratio=sharpe_ratio,
                    max_drawdown=max_drawdown,
                    active_positions=active_positions,
                    extra_metadata=metadata,
                )
                session.add(performance)
                await session.commit()
                return performance.id
        except Exception as e:
            logger.error(f"Failed to insert agent performance: {e}")
            return None
    
    async def insert_agent_decision(
        self,
        timestamp: datetime,
        agent_id: str,
        symbol: str,
        decision: str,
        confidence: Optional[float] = None,
        strategy: Optional[str] = None,
        state_features: Optional[Dict[str, Any]] = None,
        market_context: Optional[Dict[str, Any]] = None,
        executed: bool = False,
        reward: Optional[float] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[int]:
        """Insert agent decision for training data."""
        if not self._initialized or not self._session_factory:
            return None
        
        try:
            async with self._session_factory() as session:
                decision_record = AgentDecision(
                    timestamp=timestamp,
                    agent_id=agent_id,
                    symbol=symbol.upper(),
                    decision=decision.upper(),
                    confidence=confidence,
                    strategy=strategy,
                    state_features=state_features,
                    market_context=market_context,
                    executed=executed,
                    reward=reward,
                    extra_metadata=metadata,
                )
                session.add(decision_record)
                await session.commit()
                return decision_record.id
        except Exception as e:
            logger.error(f"Failed to insert agent decision: {e}")
            return None
    
    async def get_trades(
        self,
        agent_id: Optional[str] = None,
        symbol: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        limit: int = 1000,
    ) -> List[Dict[str, Any]]:
        """Query trades with filters."""
        if not self._initialized or not self._session_factory:
            return []
        
        try:
            async with self._session_factory() as session:
                from sqlalchemy import select
                query = select(Trade)
                
                if agent_id:
                    query = query.where(Trade.agent_id == agent_id)
                if symbol:
                    query = query.where(Trade.symbol == symbol.upper())
                if start_date:
                    query = query.where(Trade.timestamp >= start_date)
                if end_date:
                    query = query.where(Trade.timestamp <= end_date)
                
                query = query.order_by(Trade.timestamp.desc()).limit(limit)
                result = await session.execute(query)
                trades = result.scalars().all()
                
                return [
                    {
                        "id": t.id,
                        "timestamp": t.timestamp.isoformat(),
                        "symbol": t.symbol,
                        "side": t.side,
                        "price": t.price,
                        "quantity": t.quantity,
                        "notional": t.notional,
                        "agent_id": t.agent_id,
                        "agent_model": t.agent_model,
                        "strategy": t.strategy,
                        "fee": t.fee,
                        "slippage_bps": t.slippage_bps,
                        "metadata": t.extra_metadata,
                    }
                    for t in trades
                ]
        except Exception as e:
            logger.error(f"Failed to query trades: {e}")
            return []
    
    async def get_agent_performance(
        self,
        agent_id: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        limit: int = 1000,
    ) -> List[Dict[str, Any]]:
        """Query agent performance history."""
        if not self._initialized or not self._session_factory:
            return []
        
        try:
            async with self._session_factory() as session:
                from sqlalchemy import select
                query = select(AgentPerformance).where(AgentPerformance.agent_id == agent_id)
                
                if start_date:
                    query = query.where(AgentPerformance.timestamp >= start_date)
                if end_date:
                    query = query.where(AgentPerformance.timestamp <= end_date)
                
                query = query.order_by(AgentPerformance.timestamp.desc()).limit(limit)
                result = await session.execute(query)
                performances = result.scalars().all()
                
                return [
                    {
                        "timestamp": p.timestamp.isoformat(),
                        "equity": p.equity,
                        "total_trades": p.total_trades,
                        "total_pnl": p.total_pnl,
                        "exposure": p.exposure,
                        "win_rate": p.win_rate,
                        "sharpe_ratio": p.sharpe_ratio,
                        "max_drawdown": p.max_drawdown,
                        "active_positions": p.active_positions,
                    }
                    for p in performances
                ]
        except Exception as e:
            logger.error(f"Failed to query agent performance: {e}")
            return []


# Global storage instance
_storage: Optional[TradingStorage] = None


async def get_storage() -> TradingStorage:
    """Get or create storage instance."""
    global _storage
    if _storage is None:
        _storage = TradingStorage()
        await _storage.initialize()
    return _storage


async def close_storage() -> None:
    """Close storage connection."""
    global _storage
    if _storage:
        await _storage.close()
        _storage = None

